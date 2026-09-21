#!/usr/bin/env python3
"""The front door of alignment-machinery: hand out the input contract, then hold the caller to it.

A calling model cannot guess what this machinery needs, and a machinery that accepts whatever it is
given cannot promise anything afterwards. So invocation is two moves, both mechanical:

    invoke.py contract                          -> the inputs it needs, each one explained
    invoke.py validate --filled <file.json>     -> validated inputs written for the register, or a
                                                   refusal naming the field, what came back and what
                                                   would satisfy it

Nothing here judges meaning. It checks that the two documents exist, are readable as paragraphs, are
not the same document, and that the run's record has somewhere durable to live. It also checks the
one thing a caller can get wrong while every field looks right: the pairing. Two versions of one
document share most of their paragraphs, so the share is counted, and the versions sitting next to
the one the caller named are counted too. A share too low to be two versions of anything is refused;
a neighbour that answers the returned document far better than the named version is refused by name.
The register is the next step and runs only on inputs this step accepted.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import pathlib
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

CONTRACT_VERSION = 2

#: Every input, in the order a caller meets it. `explain` is written for the model that must fill it.
INPUTS: tuple[dict[str, object], ...] = (
    {
        "field": "client",
        "kind": "string",
        "explain": "The client whose page this is, named as the record names it (for example 'vivacom' or 'bteam'). "
                   "It is what keeps one client's wording from being applied to another.",
        "example": "<the client's short name as your record writes it>",
    },
    {
        "field": "returned_document",
        "kind": "path to a file",
        "explain": "The document the client sent back, as they sent it. A .docx, a .md, or a .paras.txt "
                   "of one paragraph per line. Never a description of it and never a retyped copy. "
                   "Do not judge a file by a paragraph count you read somewhere: this step counts a "
                   "document's own non-empty paragraphs, tables included, and a count written down "
                   "elsewhere was probably taken another way.",
        "example": "<path>/<the file they sent back>.docx",
    },
    {
        "field": "returned_label",
        "kind": "string",
        "explain": "How that document is named between you and the client, in their words, so the record says "
                   "which version was returned rather than a file name. It must name the version — v23, v23-2, "
                   "v17 — and that version must be the one the file's own name carries, because the label is "
                   "what every later step quotes.",
        "example": "<client> <document> <the version they returned>",
    },
    {
        "field": "our_document",
        "kind": "path to a file",
        "explain": "The exact version the returned document answers. Not the newest one we hold: the one they "
                   "were reading when they made these changes. If several versions of that document sit beside "
                   "it, this step compares them and refuses if one of them answers far better than the one you "
                   "named, so name the version they read rather than the version you have to hand.",
        "example": "<path>/<the version they were reading>.docx",
    },
    {
        "field": "our_label",
        "kind": "string",
        "explain": "How that version is named, in the same plain way, so the pair reads as two versions of one "
                   "document. It must name its version too, and that version must be the one its file's name "
                   "carries.",
        "example": "<client> <document> <the version they answered>",
    },
    {
        "field": "ours_is",
        "kind": "one of: sent-to-client, from-client",
        "explain": "What that version is. 'sent-to-client' when it is a document of ours the client was reading. "
                   "'from-client' when it is an earlier document the client themselves sent, which happens when "
                   "they return a second version the same week answering their own first. The difference decides "
                   "whether a change is the client answering us or the client correcting themselves, and nothing "
                   "downstream can work it out from the file.",
        "example": "sent-to-client",
    },
    {
        "field": "pairing_evidence",
        "kind": "string",
        "explain": "One sentence saying how you know the returned document answers that version of ours and not "
                   "another, and where that is written down. A client can return two versions on one day, and a "
                   "wrong pairing makes every difference after it wrong. If you cannot point at anything, say so "
                   "here in those words rather than guessing: a stated guess can be checked, a silent one cannot.",
        "example": "<where it is recorded that they were answering that version>",
    },
    {
        "field": "received_from",
        "kind": "string",
        "explain": "The person who sent it. A rule distilled from this document will be attributed to them, so "
                   "a name, not a company.",
        "example": "<the person who sent it>",
    },
    {
        "field": "received_on",
        "kind": "date, YYYY-MM-DD",
        "explain": "The day it arrived. It orders two returns from the same person, which is how a rule implied "
                   "twice is recognised rather than met twice.",
        "example": "<YYYY-MM-DD>",
    },
    {
        "field": "work",
        "kind": "path to a directory",
        "explain": "Where this run's record lives. It must sit inside a repository so the run survives, never in a "
                   "temporary folder: everything the machinery decides is written there and read back later.",
        "example": "Tasks/alignment-machinery/runs/<client>-<date>",
    },
)

#: what a document must be for the register to read it as paragraphs
READABLE = (".docx", ".md", ".txt")
TEMP_ROOTS = ("/tmp", "/private/tmp", "/var/folders")
OURS_IS = ("sent-to-client", "from-client")

#: Word's own namespace: a .docx is a zip, and its paragraphs are <w:p> runs of <w:t> text.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: How far two documents may be apart and still be two versions of one document. Measured on the
#: three returns of September 2026: right pairings 0.628, 0.656, 0.828; the same return against the
#: other client's page 0.363 and 0.390. Nothing real sits between 0.39 and 0.62.
PAIRING_FLOOR = 0.45
#: How much better a neighbouring version must answer the returned document before the named one is
#: refused for it. Her v23-2 scores 0.509 against v9 and 0.828 against the v23 beside it; the two
#: honest readings of her v23 (our REVIEW v12, her locked v9) sit 0.002 apart and must both stand.
NEIGHBOUR_MARGIN = 0.10
#: A neighbour this close to the returned document is that same document in another dress.
SAME_DOCUMENT = 0.97
#: Words a file name puts around its version, dropped when looking for that document's other versions.
_STATUS_WORDS = ("final", "review", "draft", "copy", "paras")
_VERSION = re.compile(r"v\d+(?:[-.]\d+)*", re.IGNORECASE)


def paragraphs(path: pathlib.Path) -> list[str]:
    """A document's non-empty paragraphs, tables included, with no dependency beyond the standard library."""
    if path.suffix.lower() == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml")
            root = ET.fromstring(xml)
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            raise Refused(f"{path.name} could not be read as a Word document ({exc}); "
                          f"give the file as the client sent it") from None
        found = []
        for para in root.iter(_W + "p"):
            text = re.sub(r"\s+", " ", "".join(t.text or "" for t in para.iter(_W + "t"))).strip()
            if text:
                found.append(text)
        return found
    text = path.read_text(encoding="utf-8", errors="replace")
    return [line for line in (re.sub(r"\s+", " ", raw).strip() for raw in text.splitlines()) if line]


def _share(returned: set[str], other: set[str]) -> float:
    """The share of the smaller document's paragraphs the two have in common."""
    if not returned or not other:
        return 0.0
    return len(returned & other) / min(len(returned), len(other))


def _family(name: str) -> str:
    """A file name with its version and status words removed: what its other versions share.

    The version comes out whole before anything is split, because a version can carry a hyphen
    (v23-2, a client's second return of one day) and splitting first would leave the 2 behind and
    give that file a family of its own, which is how a document ends up with no versions beside it.
    """
    stem = name[: name.index(".")] if "." in name else name
    parts = [p for p in re.split(r"[._-]", _VERSION.sub("", stem)) if p]
    while parts and (parts[-1].lower() in _STATUS_WORDS or parts[-1].isdigit()):
        parts.pop()
    return "_".join(parts)


def _versions(name: str) -> frozenset[str]:
    """The version tokens a file name carries, as v23 / v23-2."""
    return frozenset(m.group(0).lower().replace(".", "-") for m in _VERSION.finditer(name))


def _folders(ours: pathlib.Path, returned: pathlib.Path) -> list[pathlib.Path]:
    """Where a version of this document might sit: beside either file, and beside those folders."""
    out: dict[pathlib.Path, None] = {}
    for near in (ours.parent, returned.parent):
        if near.is_dir():
            out.setdefault(near.resolve(), None)
    for near in (ours.parent, returned.parent):
        parent = near.parent
        if not parent.is_dir():
            continue
        for child in sorted(parent.iterdir()):
            if child.is_dir() and not child.is_symlink():
                out.setdefault(child.resolve(), None)
    return list(out)[:20]


def _neighbours(ours: pathlib.Path, returned: pathlib.Path) -> list[pathlib.Path]:
    """The other versions of this document that the client could have been reading.

    Two kinds are left out, because neither can be the version they answered: the returned document
    itself under another name or format, and any version written after the return arrived. That
    second one matters more than it sounds. Our own regenerations carry the client's words back, so
    a draft written the morning after their return answers it better than anything they ever read —
    on 20 September our REVIEW v13, written nine hours after her v23 landed, matched it far closer
    than the v12 she was actually reading.
    """
    family = _family(ours.name)
    if len(family) < 8:
        return []
    returned_versions = _versions(returned.name)
    try:
        cutoff = returned.stat().st_mtime
    except OSError:
        cutoff = None
    seen: dict[pathlib.Path, None] = {}
    for folder in _folders(ours, returned):
        for candidate in sorted(folder.iterdir()):
            if not (candidate.is_file() and not candidate.is_symlink()
                    and candidate.suffix.lower() in READABLE
                    and _family(candidate.name) == family):
                continue
            if candidate.resolve() in (ours.resolve(), returned.resolve()):
                continue
            if returned_versions and _versions(candidate.name) == returned_versions:
                continue  # the returned document itself, under another name or format
            if cutoff is not None and candidate.stat().st_mtime >= cutoff:
                continue  # written after the return arrived: not what they were reading
            seen.setdefault(candidate.resolve(), None)
    return list(seen)[:60]


def contract() -> dict:
    """The input contract, as the caller receives it."""
    return {
        "machinery": "alignment-machinery",
        "step": "invocation",
        "contract_version": CONTRACT_VERSION,
        "what_it_does": "Turns one client's returned document into candidate rules, each ruled by a person "
                        "before anything is carried. This step only collects and checks its inputs.",
        "how_to_answer": "Copy this structure, replace every 'value' with the real value, and pass the file to "
                         "`invoke.py validate --filled <file.json>`. Leave no field out and add none.",
        "inputs": [dict(item, value=None) for item in INPUTS],
    }


class Refused(Exception):
    """A refusal that names the field, what came back, and what would satisfy it."""


def _fail(field: str, got: object, want: str) -> None:
    raise Refused(f"{field}: {got!r} — {want}")


def _resolve(root: pathlib.Path, value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    return path if path.is_absolute() else (root / path)


def _document(field: str, value: object, root: pathlib.Path) -> tuple[pathlib.Path, str]:
    if not isinstance(value, str) or not value.strip():
        _fail(field, value, "give the path to the document itself, as a non-empty string")
    path = _resolve(root, value.strip())
    if path.is_symlink():
        _fail(field, value, "the path is a symlink; give the real file, so its bytes can be recorded")
    if not path.is_file():
        _fail(field, value, f"no file is there (looked at {path}); give the path to a document that exists")
    if path.suffix.lower() not in READABLE:
        _fail(field, value, f"a {path.suffix or 'nameless'} file cannot be read as paragraphs; "
                            f"give a {', '.join(READABLE)} file")
    data = path.read_bytes()
    if not data.strip():
        _fail(field, value, "the file is empty; give the document that was actually exchanged")
    return path, hashlib.sha256(data).hexdigest()


def _text(field: str, value: object, want: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(field, value, want)
    return value.strip()


def _date(field: str, value: object) -> str:
    text = _text(field, value, "give the day it arrived as YYYY-MM-DD")
    try:
        return _dt.date.fromisoformat(text).isoformat()
    except ValueError:
        _fail(field, value, "give the day it arrived as YYYY-MM-DD, for example 2026-09-20")
    return text  # unreachable


def _label(field: str, value: object, document: pathlib.Path | None, want: str) -> str:
    """A label that names its version, and names the version its own file carries."""
    text = _text(field, value, want)
    said = {m.group(0).lower().replace(".", "-") for m in _VERSION.finditer(text)}
    if not said:
        _fail(field, value, "name the version in the label, as the client would say it "
                            "(for example 'Vivacom Step 9 toolkit FINAL v23'); a label without a "
                            "version cannot say which document a later step is quoting")
    if document is None:
        return text
    carried = {m.group(0).lower().replace(".", "-") for m in _VERSION.finditer(document.name)}
    if carried and not (said & carried):
        _fail(field, value, f"the label says {', '.join(sorted(said))} but the file it names is "
                            f"{document.name}, which carries {', '.join(sorted(carried))}; "
                            f"label the version the file actually is, or name the other file")
    return text


def _one_of(field: str, value: object, allowed: tuple[str, ...], want: str) -> str:
    text = _text(field, value, want)
    if text.lower() not in allowed:
        _fail(field, value, f"answer with one of: {', '.join(allowed)} — {want}")
    return text.lower()


def _work(field: str, value: object, root: pathlib.Path) -> pathlib.Path:
    text = _text(field, value, "give a directory inside a repository where this run's record will live")
    path = _resolve(root, text)
    resolved = path.resolve()
    for temp in TEMP_ROOTS:
        if str(resolved) == temp or str(resolved).startswith(temp + "/"):
            _fail(field, value, f"{resolved} is a temporary folder; give a directory inside a repository, "
                                f"so the run and everything it decides survive")
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            break
    else:
        _fail(field, value, f"{resolved} is not inside a repository; give a directory under one, "
                            f"for example Tasks/alignment-machinery/runs/<client>-<date>")
    if resolved.exists() and not resolved.is_dir():
        _fail(field, value, f"{resolved} is a file, not a directory")
    return resolved


def validate(filled: dict, root: pathlib.Path) -> dict:
    """The validated inputs, or a refusal naming every field that is wrong."""
    if not isinstance(filled, dict):
        raise Refused("the filled contract: not an object — send back the structure `contract` gave you")
    items = filled.get("inputs")
    if not isinstance(items, list):
        raise Refused("inputs: missing — send back the structure `contract` gave you, with each value filled")
    given: dict[str, object] = {}
    for entry in items:
        if not isinstance(entry, dict) or "field" not in entry:
            raise Refused(f"inputs: {entry!r} has no 'field' — keep each input's own name on it")
        given[str(entry["field"])] = entry.get("value")
    expected = [str(item["field"]) for item in INPUTS]
    missing = [f for f in expected if f not in given]
    extra = [f for f in given if f not in expected]
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing " + ", ".join(missing))
        if extra:
            parts.append("unknown " + ", ".join(extra))
        raise Refused("inputs: " + "; ".join(parts) + f" — the contract asks for exactly: {', '.join(expected)}")

    refusals: list[str] = []
    out: dict[str, object] = {}

    def attempt(fn, *args):
        try:
            return fn(*args)
        except Refused as exc:
            refusals.append(str(exc))
            return None

    out["client"] = attempt(_text, "client", given["client"], "name the client as the record names it")
    returned = attempt(_document, "returned_document", given["returned_document"], root)
    ours = attempt(_document, "our_document", given["our_document"], root)
    out["returned_label"] = attempt(_label, "returned_label", given["returned_label"],
                                    returned[0] if returned else None,
                                    "say how the returned version is named between you and the client")
    out["our_label"] = attempt(_label, "our_label", given["our_label"], ours[0] if ours else None,
                               "say how that version is named between you and the client")
    out["ours_is"] = attempt(_one_of, "ours_is", given["ours_is"], OURS_IS,
                             "say whether the version they answered is one we sent them "
                             "(sent-to-client) or an earlier document they sent us (from-client)")
    out["pairing_evidence"] = attempt(_text, "pairing_evidence", given["pairing_evidence"],
                                      "say in one sentence how you know the returned document answers that version "
                                      "of ours, and where that is recorded; if nothing records it, say that here")
    out["received_from"] = attempt(_text, "received_from", given["received_from"],
                                   "name the person who sent it, not their company")
    out["received_on"] = attempt(_date, "received_on", given["received_on"])
    work = attempt(_work, "work", given["work"], root)

    pairing: dict[str, object] = {}
    if returned and ours and returned[1] == ours[1]:
        refusals.append(
            f"returned_document and our_document: the same document ({returned[1][:12]}…) — "
            f"there is nothing to align; give the version they answered, not the version they returned")
    elif returned and ours:
        try:
            said_back = set(paragraphs(returned[0]))
            answered = set(paragraphs(ours[0]))
        except Refused as exc:
            refusals.append(str(exc))
            said_back = answered = set()
        if said_back and answered:
            share = _share(said_back, answered)
            pairing = {"paragraphs_returned": len(said_back), "paragraphs_ours": len(answered),
                       "shared_paragraphs": len(said_back & answered), "share": round(share, 3)}
            if share < PAIRING_FLOOR:
                refusals.append(
                    f"returned_document and our_document: they have {round(share * 100)}% of their "
                    f"paragraphs in common ({len(said_back & answered)} of "
                    f"{min(len(said_back), len(answered))}), which is too little to be two versions of "
                    f"one document — two versions of one page share most of their text. Check that "
                    f"{ours[0].name} is the document {returned[0].name} answers, and not another "
                    f"client's page, another step's page, or another deliverable")
            else:
                better = []
                nearby = _neighbours(ours[0], returned[0])
                pairing["neighbours_checked"] = len(nearby)
                for other in nearby:
                    try:
                        theirs = set(paragraphs(other))
                    except Refused:
                        continue
                    other_share = _share(said_back, theirs)
                    if other_share >= SAME_DOCUMENT:
                        continue  # the returned document itself, in another format
                    if other_share - share >= NEIGHBOUR_MARGIN:
                        better.append((round(other_share, 3), other))
                if better:
                    better.sort(reverse=True)
                    named = "; ".join(f"{path.name} at {value}" for value, path in better[:3])
                    pairing["closer_versions"] = [f"{path.name} at {value}" for value, path in better[:5]]
                    # A closer version is not proof of a wrong pairing: our own drafts converge on a
                    # client's style, so a later draft of ours can answer their return better than the
                    # one they actually read. What it is, is a question the caller must have faced. So
                    # it stands only if the pairing evidence names that version.
                    said = _versions(str(out.get("pairing_evidence") or ""))
                    rival = _versions(better[0][1].name)
                    if not (rival and said & rival):
                        refusals.append(
                            f"our_document: {ours[0].name} shares {round(share, 3)} of its paragraphs with "
                            f"{returned[0].name}, but a version sitting beside it answers it much better "
                            f"({named}). Either that closer version is the one they were reading — name it "
                            f"as our_document — or it is not, and pairing_evidence must say so naming it, "
                            f"for example why a version of ours written later answers their return better "
                            f"than the one they had")
                    else:
                        pairing["closer_versions_answered"] = sorted(said & rival)
    if refusals:
        raise Refused(" | ".join(refusals))

    out["returned_document"] = {"path": str(returned[0]), "sha256": returned[1],
                                "paragraphs": pairing.get("paragraphs_returned")}
    out["our_document"] = {"path": str(ours[0]), "sha256": ours[1],
                           "paragraphs": pairing.get("paragraphs_ours")}
    out["pairing"] = pairing
    out["work"] = str(work)
    out["contract_version"] = CONTRACT_VERSION
    out["accepted_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    return out


def write_accepted(accepted: dict) -> pathlib.Path:
    work = pathlib.Path(str(accepted["work"]))
    work.mkdir(parents=True, exist_ok=True)
    target = work / "inputs.json"
    if target.is_file():
        try:
            held = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Refused(f"work: {work} already holds an inputs.json that cannot be read ({exc}); "
                          f"give a fresh directory rather than writing over a run's record") from None
        if held.get("contract_version") != accepted.get("contract_version"):
            raise Refused(
                f"work: {work} holds a record written against contract version "
                f"{held.get('contract_version')}, and this one is version {accepted.get('contract_version')}; "
                f"a record is never rewritten under a later contract — give a fresh directory, and leave "
                f"the earlier run's record as the run that produced it")
        stamps = ("accepted_at", "re_accepted_at")
        differing = sorted(
            {k for k in (set(held) | set(accepted)) if k not in stamps}
            - {k for k in (set(held) & set(accepted)) if held.get(k) == accepted.get(k)}
        )
        if differing:
            raise Refused(
                f"work: {work} already holds the record of another run "
                f"({held.get('client')}, {held.get('returned_label')} against {held.get('our_label')}, "
                f"accepted {held.get('accepted_at')}), and this fill differs from it on "
                f"{', '.join(differing)}; a run's record is never written over — "
                f"give a fresh directory, one per return. Re-running the identical fill is allowed; "
                f"changing a word of it is a different run")
        accepted = dict(accepted, accepted_at=held.get("accepted_at", accepted["accepted_at"]),
                        re_accepted_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
    target.write_text(json.dumps(accepted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="invoke.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("contract", help="print the inputs this machinery needs, each one explained")
    filled = sub.add_parser("validate", help="check a filled contract and write the validated inputs")
    filled.add_argument("--filled", required=True, help="the filled contract, as JSON")
    filled.add_argument("--root", default=".", help="what relative paths are relative to (default: here)")
    args = parser.parse_args(argv)

    if args.action == "contract":
        print(json.dumps(contract(), indent=2, ensure_ascii=False))
        return 0

    root = pathlib.Path(args.root).resolve()
    try:
        payload = json.loads(pathlib.Path(args.filled).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "refused", "because": f"the filled contract could not be read as JSON: {exc}"},
                         indent=2), file=sys.stderr)
        return 2
    try:
        accepted = validate(payload, root)
    except Refused as exc:
        print(json.dumps({"status": "refused", "because": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        target = write_accepted(accepted)
    except Refused as exc:
        print(json.dumps({"status": "refused", "because": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": "accepted", "inputs": str(target), "next_step": "register",
                      "client": accepted["client"], "returned": accepted["returned_label"],
                      "ours": accepted["our_label"], "ours_is": accepted["ours_is"],
                      "pairing": accepted["pairing"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
