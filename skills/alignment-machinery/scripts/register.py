#!/usr/bin/env python3
"""The second step of alignment-machinery: hold every difference between the two documents.

The invocation accepted a pair and wrote its record. This step reads that record and lines the two
documents up paragraph by paragraph, so that afterwards there is one ordered list of what the client
changed, added and removed, with their words and ours kept verbatim beside each other.

    register.py hold --work <run directory>     -> differences.json beside the run's inputs.json
    register.py show --work <run directory>     -> what it holds, in a few lines

Nothing here judges meaning: it does not say whether a difference is this client's wording or
evidence of a rule, and it drops nothing on the grounds of looking unimportant. That is the whole
point of it. Reading every changed line is what proves nothing was missed; what the changes mean is
decided later, across all of them at once.

Two things make the record checkable rather than believed. Every paragraph of both documents is
accounted for exactly once, and the arithmetic is written into the file and recomputed on every read.
And both documents are checked against the contents the invocation pinned, so a record can never
describe a document that has since changed on disk.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from invoke import Refused, read_document  # noqa: E402  (the machinery reads a document one way)

REGISTER_VERSION = 1
#: what the invocation must have written for this step to run at all
NEEDS = ("client", "returned_document", "our_document", "returned_label", "our_label", "ours_is")


def _held(work: pathlib.Path) -> dict:
    record = work / "inputs.json"
    if not record.is_file():
        raise Refused(f"work: {work} holds no inputs.json — the register runs on a pair the "
                      f"invocation accepted; run `invoke.py validate` first")
    try:
        held = json.loads(record.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Refused(f"work: {record} could not be read as JSON ({exc})") from None
    missing = [field for field in NEEDS if not held.get(field)]
    if missing:
        raise Refused(f"work: {record} is missing {', '.join(missing)} — it was not written by this "
                      f"machinery's invocation, or it was written by hand")
    return held


def _document(held: dict, side: str) -> list[tuple[str, str]]:
    """The paragraphs of one side, refused unless the file is still the one that was accepted."""
    declared = held[side]
    path = pathlib.Path(str(declared["path"]))
    if not path.is_file():
        raise Refused(f"{side}: {path} is no longer there; the record describes a document this "
                      f"machine can no longer read")
    now = hashlib.sha256(path.read_bytes()).hexdigest()
    if now != declared.get("sha256"):
        raise Refused(
            f"{side}: {path.name} has changed since the invocation accepted it "
            f"({declared.get('sha256', '')[:12]}… became {now[:12]}…). A register of differences "
            f"describes two exact documents; run the invocation again on a fresh directory rather "
            f"than holding differences against a document that moved underneath it")
    return read_document(path)


def _sections(document: list[tuple[str, str]]) -> list[str]:
    """For each paragraph, the nearest heading above it: where a difference sits on the page."""
    where: list[str] = []
    standing = ""
    for text, style in document:
        if style.lower().startswith("heading") or style.lower() in ("title", "subtitle"):
            standing = text
        where.append(standing)
    return where


def hold(work: pathlib.Path) -> dict:
    """The ordered record of what the client changed, added and removed."""
    held = _held(work)
    ours = _document(held, "our_document")
    theirs = _document(held, "returned_document")
    if not ours or not theirs:
        raise Refused("the documents: one of them has no paragraphs to compare")

    our_text = [text for text, _ in ours]
    their_text = [text for text, _ in theirs]
    our_where = _sections(ours)
    their_where = _sections(theirs)

    differences: list[dict] = []
    passages: list[dict] = []
    carried = 0

    def note(kind: str, ours_at: int | None, theirs_at: int | None) -> None:
        differences.append({
            "id": f"d-{len(differences) + 1:04d}",
            "passage": passages[-1]["id"],
            "kind": kind,
            "ours": our_text[ours_at] if ours_at is not None else None,
            "theirs": their_text[theirs_at] if theirs_at is not None else None,
            "at": {"ours": ours_at, "theirs": theirs_at},
            "section": (their_where[theirs_at] if theirs_at is not None
                        else our_where[ours_at]) or None,
        })

    def open_passage(kind: str, i1: int, i2: int, j1: int, j2: int) -> None:
        """One stretch the client worked on, and the differences that came out of it.

        A rewritten passage of nine paragraphs answered by four is four rewrites and five
        paragraphs that went; on their own those five read as deletions, which is a different
        claim about the client. They arrived together, so the record says so, and the step that
        asks what a difference means can read the passage whole.
        """
        passages.append({
            "id": f"p-{len(passages) + 1:04d}",
            "kind": kind,
            "ours": {"from": i1, "to": i2, "paragraphs": i2 - i1},
            "theirs": {"from": j1, "to": j2, "paragraphs": j2 - j1},
            "section": ((their_where[j1] if j1 < len(their_where) else "") if j2 > j1
                        else (our_where[i1] if i1 < len(our_where) else "")) or None,
            "differences": [],
        })

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, our_text, their_text,
                                                       autojunk=False).get_opcodes():
        if tag == "equal":
            carried += i2 - i1
            continue
        open_passage({"replace": "rewritten", "delete": "cut", "insert": "inserted"}[tag],
                     i1, i2, j1, j2)
        if tag == "delete":
            for index in range(i1, i2):
                note("removed", index, None)
        elif tag == "insert":
            for index in range(j1, j2):
                note("added", None, index)
        else:
            # replace: pair them up in order, and whatever is left over on either side is its own
            # difference — but it keeps the passage it came from, so it is never read as a lone
            # deletion when it was part of a rewrite.
            paired = min(i2 - i1, j2 - j1)
            for offset in range(paired):
                note("changed", i1 + offset, j1 + offset)
            for index in range(i1 + paired, i2):
                note("removed", index, None)
            for index in range(j1 + paired, j2):
                note("added", None, index)
        passages[-1]["differences"] = [d["id"] for d in differences
                                       if d["passage"] == passages[-1]["id"]]

    counts = {
        "paragraphs_ours": len(our_text),
        "paragraphs_theirs": len(their_text),
        "carried": carried,
        "changed": sum(1 for d in differences if d["kind"] == "changed"),
        "added": sum(1 for d in differences if d["kind"] == "added"),
        "removed": sum(1 for d in differences if d["kind"] == "removed"),
        "differences": len(differences),
        "passages": len(passages),
    }
    check(counts)
    return {
        "machinery": "alignment-machinery",
        "step": "register",
        "register_version": REGISTER_VERSION,
        "client": held["client"],
        "returned_label": held["returned_label"],
        "our_label": held["our_label"],
        "ours_is": held["ours_is"],
        "returned_document": held["returned_document"],
        "our_document": held["our_document"],
        "counts": counts,
        "passages": passages,
        "held_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "differences": differences,
        "next_step": "disposition",
    }


def check(counts: dict) -> None:
    """Every paragraph of both documents accounted for exactly once, or nothing is written.

    This is the only promise the register makes, so it is the one thing that must not be taken on
    trust. It is recomputed whenever the record is read back, not only when it is written.
    """
    ours = counts["carried"] + counts["changed"] + counts["removed"]
    theirs = counts["carried"] + counts["changed"] + counts["added"]
    wrong = []
    if ours != counts["paragraphs_ours"]:
        wrong.append(f"ours: {counts['paragraphs_ours']} paragraphs, but {ours} accounted for "
                     f"({counts['carried']} carried, {counts['changed']} changed, "
                     f"{counts['removed']} removed)")
    if theirs != counts["paragraphs_theirs"]:
        wrong.append(f"theirs: {counts['paragraphs_theirs']} paragraphs, but {theirs} accounted for "
                     f"({counts['carried']} carried, {counts['changed']} changed, "
                     f"{counts['added']} added)")
    if counts.get("passages") is not None and counts["passages"] > counts["differences"]:
        wrong.append(f"{counts['passages']} passages hold {counts['differences']} differences; a "
                     f"passage with nothing in it is a passage that was not read")
    if counts["differences"] != counts["changed"] + counts["added"] + counts["removed"]:
        wrong.append(f"the list holds {counts['differences']} differences and the counts say "
                     f"{counts['changed'] + counts['added'] + counts['removed']}")
    if wrong:
        raise Refused("the register does not add up, so it was not written — " + "; ".join(wrong))


def write(work: pathlib.Path, record: dict) -> pathlib.Path:
    target = work / "differences.json"
    if target.is_file():
        standing = json.loads(target.read_text(encoding="utf-8"))
        same = all(standing.get(k) == record.get(k) for k in
                   ("client", "returned_document", "our_document", "counts", "differences"))
        if not same:
            raise Refused(
                f"work: {work} already holds a register of "
                f"{standing.get('counts', {}).get('differences')} differences for "
                f"{standing.get('returned_label')} against {standing.get('our_label')}, and this one "
                f"differs from it; a run's record is never written over — give a fresh directory")
        record = dict(record, held_at=standing.get("held_at", record["held_at"]),
                      re_held_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def show(work: pathlib.Path) -> dict:
    target = work / "differences.json"
    if not target.is_file():
        raise Refused(f"work: {work} holds no differences.json — run `register.py hold` first")
    record = json.loads(target.read_text(encoding="utf-8"))
    check(record["counts"])
    kinds: dict[str, int] = {}
    for difference in record["differences"]:
        section = difference.get("section") or "(no heading above it)"
        kinds[section] = kinds.get(section, 0) + 1
    shapes: dict[str, int] = {}
    for passage in record.get("passages", []):
        shapes[passage["kind"]] = shapes.get(passage["kind"], 0) + 1
    widest = sorted(record.get("passages", []),
                    key=lambda p: -(p["ours"]["paragraphs"] + p["theirs"]["paragraphs"]))[:3]
    return {
        "client": record["client"],
        "returned": record["returned_label"],
        "ours": record["our_label"],
        "counts": record["counts"],
        "passages": shapes,
        "the_largest_passages": [
            {"id": p["id"], "kind": p["kind"], "section": p["section"],
             "ours": p["ours"]["paragraphs"], "theirs": p["theirs"]["paragraphs"]} for p in widest],
        "where_they_sit": dict(sorted(kinds.items(), key=lambda item: -item[1])[:12]),
        "next_step": record["next_step"],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="register.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for action, help_text in (("hold", "line the two documents up and hold every difference"),
                              ("show", "what the register holds, in a few lines")):
        step = sub.add_parser(action, help=help_text)
        step.add_argument("--work", required=True, help="the run directory the invocation wrote")
    args = parser.parse_args(argv)
    work = pathlib.Path(args.work).resolve()

    try:
        if args.action == "hold":
            record = hold(work)
            target = write(work, record)
            print(json.dumps({"status": "held", "differences": str(target),
                              "counts": record["counts"], "next_step": record["next_step"]},
                             indent=2, ensure_ascii=False))
        else:
            print(json.dumps(show(work), indent=2, ensure_ascii=False))
    except Refused as exc:
        print(json.dumps({"status": "refused", "because": str(exc)}, indent=2, ensure_ascii=False),
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
