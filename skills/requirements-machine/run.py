#!/usr/bin/env python3
"""The requirements machinery, driven from one command.

Everything here already existed as separate tools, and the order they run in lived in one
conversation. That is not machinery — it is a habit. This owns the order, owns the gates, and
refuses to advance when a stage has not finished its job.

It does not do the reading. Reading a description and judging a requirement are the parts a model
does, and this hands each of them out as a work packet: a prompt, the exact input file, and the
directory the answers go in. It then checks the answers before the next stage starts. Every
narrowing this machinery has earned came from code fixing what gets looked at and a model judging
what it means; the runner is that division made permanent.

    python3 run.py --subject "<what is being described>" \
                   --description <file.md> --work <dir> [--built <repo>]

State lives in the work directory, so the command is re-runnable: a stage whose output is already
there and passes its gate is not run again. Stopping and resuming is the normal case, because two
of the stages need a person.

Stages, in order, each with the gate that must pass before the next begins:

  1  divide       code   the description becomes obligations + leftover; the counts must balance
  2  oblige       model  every obligation ends in a requirement or a recorded dismissal
  3  leftover     model  the leftover is read on its own, by someone who cannot see stage 2
  4  pair         code   possible duplicates are found; no judgement is made
  5  merge        model  each pair judged twice, independently
  6  consolidate  code   only merges both judgements agreed are applied
  7  split        model  every requirement becomes parts, each separately true or false — once,
                         because the parts are material both judges read, not a judgement
  8  answer       model  every part answered yes or no, twice, each yes citing a line
 8a  check        code   every cited line is read back; a record whose evidence does not resolve
                         is refused, because the packets promise the readers exactly that
 8b  settle       model  the parts the two passes answered differently are given to two readers
                         with both answers in front of them; both must agree, and either may
                         refuse, in which case the part goes to the person who owns the goal
  9  report       code   the verdict is arithmetic over the parts; two documents are written

Run with no `--built` to skip factual measuring after the requirements are split. Every part is
then work to add, and both promised documents are still written.

Stages 7 and 8 replaced a single stage that asked one reader for one verdict per requirement. That
stage failed the same way every time: two readers agreed on what the code does and split on how much
of a half-built requirement counted as done, twenty-four times out of a hundred and forty-three.
Sharpening its wording had already been tried and moved it by one. A part is one thing, and one
thing has an answer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))

import stage_gate  # noqa: E402


class StageCommandError(RuntimeError):
    """A mechanical stage failed without returning its documented JSON result."""

#: What each model stage is asked to do. Held here rather than in the caller's head, because a
#: stage whose instruction is retyped each time is a stage that drifts.
PACKETS = {
    "verify": (
        "The description states {count} things as facts about the code as it stands. They are in "
        "{input}. Everything this machinery produces rests on them, and nothing has ever checked "
        "them — one of them was wrong, and requirements were built expecting something that never "
        "arrives. For each, write one file into {out} named <id>.json holding "
        "{{'candidate_id','citations':[{{'where','line','text'}}],'verdict'}} where verdict is "
        "'holds' when the citation shows the claim is true today, or 'wrong' when the code says "
        "otherwise — and then say in 'what_must_change' what the description should say instead. "
        "Citations are checked by a program. Read the code; do not reason about what it probably "
        "does."
    ),
    "oblige": (
        "Read {skill}. Account for EVERY entry in {input}. For each write one file into {out} "
        "named <id>.json: either a requirement with the fields the skill lists plus "
        "'candidate_id', or a dismissal {{'candidate_id', 'not_a_requirement_because', "
        "'evidence'}}. Dismiss only for a reason you can point at in the text. Read only the "
        "description and this list — not the built system."
    ),
    "leftover": (
        "Read {skill}. The entries in {input} are every part of the description a first reader "
        "did NOT take, because none carries an obliging word. Find the places that oblige the "
        "subject to do something anyway — a definition it must honour, a fact stated about the "
        "output, a consequence named as a reason, a capability promised to a reader. Account for "
        "EVERY entry in {input}. For each, write one file into {out} named <id>.json: either a "
        "requirement with the fields the skill lists plus 'candidate_id', or a dismissal "
        "{{'candidate_id', 'not_a_requirement_because', 'evidence'}}. Finding nothing in an entry "
        "is legitimate only when its dismissal records why. Do not open the description itself "
        "or the built system."
    ),
    "merge": (
        "Judge every pair in {input}. Merge ONLY where the same thing must become true: two "
        "requirements can share a sentence, share almost every word, and still differ — one "
        "saying a section exists and the other what it must contain, one forbidding something "
        "and the other saying what to do instead. Write one file per pair into {out}: "
        "{{'left','right','verdict':'merge'|'keep both','surviving_requirement','why'}}. Read "
        "nothing but the pairs."
    ),
    "measure": (
        "Give every requirement in {input} exactly one verdict against what is actually built in "
        "{built}: 'already met', 'change', 'add', or 'remove'. Write one file per requirement "
        "into {out}: {{'candidate_id','verdict','citations','what_must_change'}}, where citations "
        "is a list of {{'where','line','text'}} — the path, the line number, and that line's exact "
        "text. Any verdict other than 'add' MUST cite at least one line carrying the behaviour; "
        "'add' cites nothing. Citations are checked by a program and a record whose evidence does "
        "not resolve is refused. Requiring this took a set of twenty-two requirements two readers "
        "disagreed on completely and brought sixteen of them into agreement. Read the code "
        "and the real output — a verdict from reasoning about what the code probably does is "
        "worthless. Do not rewrite or reinterpret a requirement; judge the one you were given. "
        "'Already met' means EVERY part of the requirement is done and you can point at what does "
        "each part. A requirement that is half satisfied, or satisfied by something that would "
        "not survive its own check, is 'change' — never 'already met'. 'Add' is for a requirement "
        "nothing addresses at all; a partial attempt is a change, not an addition."
    ),
    "settle": (
        "Two readers answered each part in {input} differently. Both sides are there: each one's "
        "answer, the lines it cited, and what it says it looked at. Settle each one against the "
        "build in {built}, or say plainly that you cannot. Write one file per dispute into {out} "
        "named <part_id>.json holding {{'part_id','answer','needed','citations':[{{'where','line','text'}}],"
        "'why_the_other_side_is_wrong'}} where answer is 'yes', 'no', or 'cannot settle'. A 'yes' "
        "or 'no' MUST cite the line that decides it and must say, in one sentence, what the other "
        "side missed or misread. When the answer is 'no', needed must be 'add', 'change', or "
        "'remove': remove means the existing behavior itself must cease and no replacement is "
        "needed; mixed or replacement work is change. 'Cannot settle' cites nothing and is a "
        "legitimate answer: a part "
        "nobody can decide from the repository belongs in front of the person who owns the goal, "
        "and guessing to make the number look better is the one thing this machinery must not do. "
        "Go and read the code and the real output yourself — do not decide by weighing which side "
        "sounds more confident, and do not treat a longer citation as a stronger one. Three "
        "rewordings of the answering instruction failed to reduce these disagreements and one made "
        "them worse, which is why you exist: the question was never how to ask better, it was that "
        "nobody was looking at both answers at once."
    ),
    "split": (
        "Break every requirement in {input} into its parts. A part is one thing that is separately "
        "true or false about the built system. A requirement saying 'every block carries exactly "
        "one state, and no verbatim sentence sits in a recommended block, and each failure is "
        "recorded' has three parts; a requirement saying one thing has one part, which is a common "
        "and legitimate answer. A part must be answerable yes or no by looking at code or real "
        "output: 'the step is given an acceptance record' is a part, 'the step behaves well' is "
        "not. Parts must not overlap, and together they must cover the whole requirement and add "
        "nothing to it. Use the requirement's own words wherever you can. Do NOT judge whether any "
        "part is done — you are splitting, not measuring. Write one file per requirement into {out} "
        "named <id>.json holding {{'id','parts':[{{'part_id','part'}}]}} with part_id as <id>.p1, "
        "<id>.p2 and so on. Read only the input file: not the code, not the description."
    ),
    "answer": (
        "Answer every part in {input} against what is actually built in {built}. Each part is one "
        "thing that is either true or false of the built system today: give it exactly one answer, "
        "'yes' or 'no'. There is no partial answer, and that is the entire point — a set of "
        "requirements judged whole rather than in parts sent twenty-four decisions to a person "
        "because two readers could agree on what the code does and still split on how much of it "
        "counted. Write one file per part into {out} named <part_id>.json holding "
        "{{'part_id','answer','needed','citations':[{{'where','line','text'}}],'looked_at'}}. A "
        "'yes' MUST "
        "cite at least one line carrying the behaviour — the path, the line number, and that line's "
        "exact text. A 'no' MUST fill 'looked_at': name the nearest thing in the build that "
        "addresses this part and say in one sentence why it does not satisfy it, citing its line "
        "the same way; and when nothing in the build is even near it, say what you searched for and "
        "where. A bare 'no' is refused. This is not bureaucracy: on the run that made this rule, 45 "
        "of the 55 parts the two readers split on had one citing a line for 'yes' and the other "
        "offering nothing at all for 'no', so there was no way to tell which had looked in the "
        "right place — and a disagreement nobody can settle is worse than a wrong answer, because "
        "it goes to a person with nothing to decide on. For every 'no', set 'needed' to exactly "
        "one of 'add', 'change', or 'remove'. Add means nothing in the build addresses the part; "
        "change means something must be altered or replaced; remove means the existing behavior "
        "itself must cease and no replacement is needed. This is classified per part so a pure "
        "removal can reach the remove section without turning a mixed requirement into one. "
        "Citations are checked by a program and a record whose evidence does "
        "not resolve is refused. Read the code and the real output; an answer from reasoning about "
        "what the code probably does is worthless. Do not rewrite or reinterpret a part; answer the "
        "one you were given. If a part holds only on some code paths or only when a flag is set, "
        "answer 'no' and say which path in an optional 'note' — the run that made this rule "
        "necessary had one reader cite a refusal in a module and the other cite the caller that "
        "never lets it fire, and both were reading the same repository correctly."
    ),
}

#: A model stage is run twice, by readers who cannot see each other. Agreement is the only
#: evidence this machinery has ever accepted that a stage is reliable.
PASSES = 2


def _run(args: list[str]) -> dict[str, object]:
    result = subprocess.run(
        args, capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode not in (0, 1):
        raise StageCommandError(
            f"{' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise StageCommandError(
            f"{' '.join(args)} returned no valid JSON: {result.stderr.strip() or result.stdout.strip()}"
        ) from error
    if not isinstance(payload, dict):
        raise StageCommandError(f"{' '.join(args)} returned JSON that is not an object")
    return payload


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _requirement_record(row: dict[str, object]) -> list[str]:
    """Validate the two legitimate outcomes of reading one description entry."""

    if row.get("not_a_requirement_because") and row.get("requirement"):
        return ["one record cannot both dismiss an entry and turn it into a requirement"]
    if row.get("not_a_requirement_because"):
        return [] if row.get("evidence") else ["a dismissal must carry evidence from the input"]
    missing = [field for field in ("requirement", "check") if not str(row.get(field) or "").strip()]
    return [f"a requirement must carry {', '.join(missing)}"] if missing else []


def _split_record(row: dict[str, object]) -> list[str]:
    rid = str(row.get("id") or "")
    parts = row.get("parts")
    if not isinstance(parts, list) or not parts:
        return ["parts must be a non-empty list"]
    reasons = []
    for index, part in enumerate(parts, start=1):
        if not isinstance(part, dict):
            reasons.append(f"part {index} must be an object")
            continue
        if str(part.get("part_id") or "") != f"{rid}.p{index}":
            reasons.append(f"part {index} id must be {rid}.p{index}")
        if not str(part.get("part") or "").strip():
            reasons.append(f"part {index} must state one testable thing")
    return reasons


def _merge_record(row: dict[str, object]) -> list[str]:
    reasons = stage_gate.enum("verdict", {"merge", "keep both"})(row)
    verdict = str(row.get("verdict") or "").strip().lower()
    if verdict == "merge" and not str(row.get("surviving_requirement") or "").strip():
        reasons.append("a merge must carry the surviving requirement")
    if verdict in {"merge", "keep both"} and not str(row.get("why") or "").strip():
        reasons.append("a pair verdict must say why")
    return reasons


def _answer_record(row: dict[str, object]) -> list[str]:
    answer = str(row.get("answer") or "").strip().lower()
    reasons = stage_gate.enum(
        "answer", {"yes", "no"}, require_needed_for_no=True,
    )(row)
    if answer == "yes":
        reasons.extend(stage_gate.citation_reasons(row))
    if answer == "no" and not row.get("looked_at"):
        reasons.append("a no answer must say what was looked at")
    return reasons


def _settle_record(row: dict[str, object]) -> list[str]:
    answer = str(row.get("answer") or "").strip().lower()
    reasons = [] if answer in {"yes", "no", "cannot settle"} else [
        "answer must be yes, no, or cannot settle",
    ]
    if answer == "no" and str(row.get("needed") or "").strip().lower() not in {
        "add", "change", "remove",
    }:
        reasons.append("a no answer needs add, change, or remove")
    if answer in {"yes", "no"}:
        reasons.extend(stage_gate.citation_reasons(row))
    if answer == "cannot settle" and row.get("citations"):
        reasons.append("cannot settle must cite nothing")
    return reasons


def _verify_record(row: dict[str, object]) -> list[str]:
    reasons = stage_gate.enum(
        "verdict", {"holds", "wrong"}, require_citations=True,
    )(row)
    if str(row.get("verdict") or "").strip().lower() == "wrong" and not str(
        row.get("what_must_change") or ""
    ).strip():
        reasons.append("a wrong verdict must say what the description should say instead")
    return reasons


def _quarantine(directory: Path, work: Path, filenames: list[str], reasons: object) -> Path | None:
    """Move refused model output aside so the next reader can replace it cleanly."""

    existing = [directory / name for name in filenames if (directory / name).is_file()]
    if not existing:
        return None
    aside = work / f"{directory.name}-refused"
    aside.mkdir(parents=True, exist_ok=True)
    for source in existing:
        serial = len(list(aside.glob(f"{source.stem}-*.json"))) + 1
        source.replace(aside / f"{source.stem}-{serial}.json")
    _write(aside / "why.json", {
        "refusals": reasons if isinstance(reasons, list) else [],
        "gate": reasons,
    })
    return aside


def _files_for_ids(directory: Path, identifiers: set[str], field: str) -> list[str]:
    found = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "summary.json":
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if str(row.get(field) or path.stem) in identifiers:
            found.append(path.name)
    return found


def _retry_packet(packet: dict[str, object], gate: dict[str, object]) -> dict[str, object]:
    """Tell a replacement reader exactly what the executable gate refused."""

    details = {
        key: gate.get(key) for key in (
            "missing", "unreadable", "unknown", "duplicates", "misnamed", "invalid",
        )
        if gate.get(key)
    }
    packet["instruction"] = (
        "The executable gate refused the previous output. Replace the missing or refused records "
        f"described here, and leave accepted records untouched: {json.dumps(details, sort_keys=True)}\n\n"
        + str(packet["instruction"])
    )
    return packet


def _finish(report: dict[str, object], work: Path) -> dict[str, object]:
    """Write both promised artifacts and return their paths with the machine-readable report."""

    report_path = work / "report.json"
    _write(report_path, report)
    written = _run([
        sys.executable, str(HERE / "write_document.py"),
        "--report", str(report_path),
        "--requirements", str(work / "requirements.json"),
        "--out", str(work / "requirements.md"),
        "--parts-out", str(work / "what-to-build.md"),
    ])
    return {**report, "document": written["document"], "breakdown": written.get("breakdown")}


def _requirement_verdict(calls: list[dict[str, str]]) -> str:
    """Derive one requirement verdict from its independently classified parts."""

    yes = sum(call.get("answer") == "yes" for call in calls)
    needed = {call.get("needed") for call in calls if call.get("answer") == "no"}
    if yes == len(calls):
        return "already met"
    if yes == 0 and needed == {"add"}:
        return "add"
    if yes == 0 and needed == {"remove"}:
        return "remove"
    return "change"


#: Appended to every packet. Two of these sentences are about *how* a reader works rather than what
#: it judges, and both were learned the hard way. A reader that reads everything before writing
#: anything is indistinguishable from a stalled one, and on that mistaken reading a live reader was
#: killed mid-read. And a second pass is only evidence while it cannot see the first — which has to
#: be said to the reader, because nothing stops it looking.
#:
#: It lives here rather than in the caller, because for one whole run it lived in the caller: the
#: instruction the readers received was not the instruction this file emitted, while the skill
#: demanded it be handed over verbatim. Anything a reader must be told belongs in this file.
#: Telling a reader not to look at its twin is not enough on its own: on the first full run both
#: measuring readers wrote working files into the shared directory under the same obvious names —
#: batch1.json, batch2.json — and silently overwrote each other. One of them noticed its own input
#: had changed under it and said so; the other did not. Independence has to be a place, not a
#: promise, so every reader is given a directory of its own for anything it writes while thinking.
#: It sits beside the answers rather than inside them, because the gate counts the answers.
HOW_TO_READ = (
    " Write files as you go — the first ten before doing further reading — so progress is visible; "
    "a reader that writes nothing until the end cannot be told apart from one that has stopped. "
    "Put every working, scratch or intermediate file in {scratch} and nowhere else — that "
    "directory is yours alone. Writing scratch beside another reader's is how two readers "
    "overwrote each other's inputs on the run that made this sentence necessary. "
    "Before you finish, write {scratch}/reader.json holding "
    "{{'model': '<the model you are, as you are identified>', 'harness': '<the tool you are "
    "running inside>'}}. This machinery never chooses a reader — whoever runs it supplies one, so "
    "the same command run elsewhere is read by whatever that place runs. That is deliberate, and "
    "it is why the record has to say who read it: a count of agreements means nothing next to a "
    "later count unless both say what did the reading."
)


#: Said only to a reader that has a twin. Telling a lone reader it is one of two invites it to look
#: for the other, and the split stage runs once on purpose — its output is material both judges
#: read, not a judgement needing a second opinion.
BLIND = (
    " You are one of two independent readers of this same input: do not open any sibling output or "
    "scratch directory, and do not look for what the other found. Agreement between two readers who "
    "could not see each other is the only evidence this machinery accepts."
)


def _packet(name: str, work: Path, twinned: bool = True, **fields: object) -> dict[str, object]:
    """A stage a person or an agent has to run, stated completely enough to hand over."""

    out = Path(str(fields.get("out")))
    scratch = out.parent / f"{out.name}-scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    instruction = PACKETS[name].format(**fields)
    if twinned:
        instruction += BLIND
    return {
        "stage": name,
        "instruction": instruction + HOW_TO_READ.format(scratch=scratch),
        "waiting_for": str(out),
        "scratch": str(scratch),
    }


def _again(packet: dict[str, object], work: Path, index: int) -> dict[str, object]:
    """Narrow an answering packet to the parts a refusal set aside, and say why each was refused.

    A packet that says "answer every part" is the right thing to hand a reader the first time and
    the wrong thing to hand one afterwards: it would send them back over forty-three parts to
    replace one, and the reason the one was refused — the only thing that can make the second
    attempt differ from the first — would never reach them. Which parts are missing is read off
    disk rather than remembered, so it survives the run stopping and being started again.
    """

    kept = work / f"answer-{index}-refused"
    if not kept.is_dir():
        return packet
    if (kept / "why.json").is_file():
        refused = json.loads((kept / "why.json").read_text(encoding="utf-8")).get("refusals") or []
    else:
        # A directory of set-aside answers with no record of why they were set aside is what an
        # earlier version of this step left behind. The ids are still recoverable from the file
        # names, and naming them is most of the value: without it the packet asks for all
        # forty-three parts again to replace the two that were refused.
        refused = []
    if not refused:
        refused = [{"id": path.name.rsplit("-", 1)[0], "unresolved": []}
                   for path in sorted(kept.glob("*.json")) if path.name != "why.json"]
    answers = work / f"answer-{index}"
    missing = [row for row in refused if not (answers / f"{row['id']}.json").exists()]
    if not missing:
        return packet
    why = "; ".join(f"{row['id']}: {' '.join(row.get('unresolved') or [])}" for row in missing)
    packet["instruction"] = (
        f"Only these parts are being asked again, and only their files are missing from {answers}: "
        f"{', '.join(row['id'] for row in missing)}. Every other part is already answered and must "
        f"be left exactly as it is. Each was refused because its evidence did not resolve when it "
        f"was read back — {why} Answer those parts again against the build as it stands now, "
        f"under everything below.\n\n"
    ) + str(packet["instruction"])
    return packet


def _drive(subject: str, description: Path, work: Path, built: Path | None) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    skill = HERE / "FIRST-HALF-STEP-ONE.md"

    # Everything below is derived from the description and kept, so the run can stop and resume.
    # That only holds while the description is the one it was derived from. When the gate below
    # refuses a statement, the description gets corrected — and on the run that made this check
    # necessary, the corrected file sat on disk while the machinery went on handing readers the
    # sentences extracted before the correction. Two readers spent a full round proving a statement
    # wrong that had already been rewritten. Cached work is only a saving when it is still about the
    # same thing.
    stamp = work / "description.sha256"
    now = hashlib.sha256(description.read_bytes()).hexdigest()
    if stamp.exists():
        was = stamp.read_text(encoding="utf-8").strip()
        if was != now:
            return {
                "stopped": "the description changed after this run derived its material",
                "why": "every list here was taken from the earlier text, so the readers would be "
                       "answering about sentences that no longer exist",
                "do": f"run again with a fresh --work directory, or delete {work}/split.json, "
                      f"{work}/claims.json and the verify directories to re-derive from the "
                      "corrected description",
                "derived_from": was,
                "description_is_now": now,
            }
    else:
        stamp.write_text(now, encoding="utf-8")

    # 1 · split — code. The gate is arithmetic: nothing may be in neither list.
    split_path = work / "split.json"
    if not split_path.exists():
        _write(split_path, _run([
            sys.executable, str(HERE / "enumerate_obligations.py"),
            "--description", str(description),
        ]))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    if not split["partition"]["balances"]:
        return {"stopped": "split", "why": "the description did not partition", "split": split["partition"]}

    # 1b · verify — model. The description's claims about the code are checked before anything is
    # built on them. Skipped only when there is nothing built to check them against.
    if built is not None:
        claims_path = work / "claims.json"
        if not claims_path.exists():
            _write(claims_path, _run([
                sys.executable, str(HERE / "extract_claims.py"),
                "--description", str(description),
            ]))
        claims = json.loads(claims_path.read_text(encoding="utf-8"))
        claim_ids = {str(row["id"]) for row in claims["claims_to_cite"]}
        wanted = len(claim_ids)
        # Two readers, as everywhere else. One pass here was the one place this rule was not
        # applied, and it cost: a third pass found two statements the second had read and passed.
        waiting = []
        for index in range(1, PASSES + 1):
            out = work / f"verify-{index}"
            gate = stage_gate.inspect(
                out, claim_ids, stage_gate.field_identity("candidate_id"),
                _verify_record, require_filename=True,
            )
            if not gate["complete"]:
                _quarantine(out, work, list(gate["reject_files"]), gate)
                waiting.append(_retry_packet(
                    _packet("verify", work, input=claims_path, out=out, count=wanted), gate,
                ))
                continue
            checked = _run([
                sys.executable, str(HERE / "check_citations.py"),
                "--records", str(out), "--built", str(built),
            ])
            if checked["refused"]:
                refused_ids = {str(row.get("id")) for row in checked["refusals"]}
                files = _files_for_ids(out, refused_ids, "candidate_id")
                _quarantine(out, work, files, checked["refusals"])
                citation_gate = {"missing": sorted(refused_ids), "invalid": checked["refusals"]}
                waiting.append(_retry_packet(
                    _packet("verify", work, input=claims_path, out=out, count=wanted),
                    citation_gate,
                ))
        if waiting:
            return {"stopped": "verifying the description", "claims": wanted, "work": waiting}
        wrong = []
        for index in range(1, PASSES + 1):
            for path in sorted((work / f"verify-{index}").glob("*.json")):
                row = json.loads(path.read_text(encoding="utf-8"))
                # Either reader calling a statement wrong is enough to stop. Agreement is what
                # makes a 'holds' trustworthy; a lone 'wrong' is still a reason to look.
                if str(row.get("verdict")) == "wrong":
                    wrong.append({"claim": row.get("candidate_id"), "found_by": f"pass-{index}",
                                  "should_say": row.get("what_must_change")})
        if wrong:
            return {"stopped": "the description states things the code contradicts",
                    "why": "requirements built on a false premise are confidently wrong",
                    "correct_the_description_then_rerun": wrong}

    obligations_in = work / "obligations.json"
    leftover_in = work / "leftover.json"
    _write(obligations_in, {"obligations": split["obligations"]})
    _write(leftover_in, {"leftover": split["leftover"]})

    # 2 and 3 · oblige and leftover — model, two passes each, run in either order. Both passes
    # account for the complete enumerated input; a directory existing is not evidence that a
    # reader covered it, and one pass cannot stand in for its blind twin.
    waiting = []
    for stage, source, rows in (
        ("oblige", obligations_in, split["obligations"]),
        ("leftover", leftover_in, split["leftover"]),
    ):
        expected = {str(row["id"]) for row in rows}
        for index in range(1, PASSES + 1):
            out = work / f"{stage}-{index}"
            gate = stage_gate.inspect(
                out, expected, stage_gate.field_identity("candidate_id"), _requirement_record,
                require_filename=True,
            )
            if not gate["complete"]:
                _quarantine(out, work, list(gate["reject_files"]), gate)
                waiting.append(_retry_packet(
                    _packet(stage, work, skill=skill, input=source, out=out), gate,
                ))
    if waiting:
        return {"stopped": "reading", "why": "a reading stage has not finished", "work": waiting}

    # Coverage remains a separate arithmetic proof over both reading stages and both passes.
    for stage, source in (("oblige", obligations_in), ("leftover", leftover_in)):
        for index in range(1, PASSES + 1):
            coverage = _run([
                sys.executable, str(HERE / "check_coverage.py"),
                "--candidates", str(source), "--records", str(work / f"{stage}-{index}"),
            ])
            if not coverage["complete"]:
                return {"stopped": "coverage", "stage": stage, "pass": index,
                        "unaccounted": coverage["unaccounted"], "coverage": coverage}

    # 4 · pair — code. It proposes; it never merges.
    pairs_path = work / "pairs.json"
    if not pairs_path.exists():
        _write(pairs_path, _run([
            sys.executable, str(HERE / "pair_candidates.py"),
            *sum((["--records", str(work / f"{stage}-{index}")]
                  for stage in ("oblige", "leftover")
                  for index in range(1, PASSES + 1)), []),
        ]))
    pairs = json.loads(pairs_path.read_text(encoding="utf-8"))

    # 5 · merge — model, twice.
    expected_pairs = {"|".join(sorted((str(row["left"]), str(row["right"]))))
                      for row in pairs["pairs"]}
    waiting = []
    for index in range(1, PASSES + 1):
        out = work / f"merge-{index}"
        gate = stage_gate.inspect(
            out, expected_pairs, stage_gate.pair_identity,
            _merge_record,
        )
        if not gate["complete"]:
            _quarantine(out, work, list(gate["reject_files"]), gate)
            waiting.append(_retry_packet(_packet("merge", work, input=pairs_path, out=out), gate))
    if waiting:
        return {"stopped": "merging", "why": "a merge pass has not judged every pair",
                "pairs": pairs["pairs_to_read"], "work": waiting}

    # 6 · consolidate — code. Only merges every pass agreed on.
    final_path = work / "requirements.json"
    if not final_path.exists():
        _write(final_path, _run([
            sys.executable, str(HERE / "consolidate.py"),
            *sum((["--records", str(work / f"{stage}-{index}")]
                  for stage in ("oblige", "leftover")
                  for index in range(1, PASSES + 1)), []),
            *sum((["--merges", str(work / f"merge-{i}")] for i in range(1, PASSES + 1)), []),
        ]))
    final = json.loads(final_path.read_text(encoding="utf-8"))

    # 7 · split — model, once. The split is material, not judgement: both judges read the same
    # parts, exactly as both merge judges read the same pairs. Two splitters on the same twenty-four
    # requirements produced seventy-three parts and sixty-one, every mismatch one part apart and
    # none about substance — so a second split buys a reconciliation problem and no evidence.
    split_dir = work / "split-1"
    requirement_ids = {str(row["id"]) for row in final["requirements"]}
    split_gate = stage_gate.inspect(
        split_dir, requirement_ids, stage_gate.field_identity("id"), _split_record,
        require_filename=True,
    )
    if not split_gate["complete"]:
        _quarantine(split_dir, work, list(split_gate["reject_files"]), split_gate)
        return {"stopped": "splitting", "why": "not every requirement is broken into parts",
                "requirements": final["count"],
                "work": [_retry_packet(_packet("split", work, twinned=False,
                                                input=final_path, out=split_dir), split_gate)]}

    parts_path = work / "parts.json"
    if not parts_path.exists():
        _write(parts_path, _run([
            sys.executable, str(HERE / "gather_parts.py"),
            "--parts", str(split_dir), "--requirements", str(final_path),
        ]))
    parts = json.loads(parts_path.read_text(encoding="utf-8"))
    if not parts["balances"]:
        return {"stopped": "splitting", "why": "the split does not cover every requirement",
                "requirements_with_no_parts": parts["requirements_with_no_parts"],
                "refusals": parts["refusals"]}

    # With no build, every part is false by definition and no measuring reader is needed. The
    # split is still required because the breakdown is one of the two promised deliverables.
    if built is None:
        report = {
            "subject": subject,
            "requirements": final["count"],
            "add": sorted(requirement_ids),
            "change": [],
            "remove": [],
            "already_met": [],
            "parts": parts["count"],
            "part_answers": [
                {**part, "calls": {"not-built": "no"}, "answer": "no",
                 "needed": "add", "evidence": None}
                for part in parts["parts"]
            ],
            "for_a_person": _decisions(final),
            "read_by": _readers(work),
            "measured_against_build": False,
            "note": "Nothing is built, so every requirement and every part is work to add.",
        }
        return _finish(report, work)

    # 8 · answer — model, twice. Yes or no per part, never a degree.
    part_ids = {str(row["part_id"]) for row in parts["parts"]}
    waiting = []
    for index in range(1, PASSES + 1):
        out = work / f"answer-{index}"
        gate = stage_gate.inspect(
            out, part_ids, stage_gate.field_identity("part_id"), _answer_record,
            require_filename=True,
        )
        if not gate["complete"]:
            _quarantine(out, work, list(gate["reject_files"]), gate)
            packet = _again(_packet("answer", work, input=parts_path, out=out, built=built),
                            work, index)
            waiting.append(_retry_packet(packet, gate))
    if waiting:
        return {"stopped": "answering", "why": "a pass has not answered every part",
                "parts": parts["count"], "work": waiting}

    # 8a · check the citations — code. Every answering packet tells its reader that "citations are
    # checked by a program and a record whose evidence does not resolve is refused". For one whole
    # run that sentence was false: the checker existed and the runner never called it, so the only
    # thing standing behind every 'yes' in the document was each reader's own promise to have
    # checked itself. A claim the machinery makes to its readers has to be one it keeps.
    for index in range(1, PASSES + 1):
        checked = _run([
            sys.executable, str(HERE / "check_citations.py"),
            "--records", str(work / f"answer-{index}"), "--built", str(built),
        ])
        if checked["refused"]:
            # A refusal has to lead somewhere. For one run it did not: the step refused seven
            # answers whose quoted lines had moved under them — the built system was being changed
            # while they were read — and then handed back no work at all. Nothing advanced until a
            # person deleted the refused files by hand, which is the one thing nobody should be
            # doing to a machinery's own output. So the refusal now sets the answer aside itself
            # and asks for it again, exactly as the build step re-asks a refused change.
            aside = work / f"answer-{index}-refused"
            aside.mkdir(parents=True, exist_ok=True)
            for refusal in checked["refusals"]:
                stale = work / f"answer-{index}" / f"{refusal['id']}.json"
                if stale.exists():
                    kept = aside / f"{refusal['id']}-{len(list(aside.glob(f'{refusal["id"]}-*')))}.json"
                    kept.write_text(stale.read_text(encoding="utf-8"), encoding="utf-8")
                    stale.unlink()
            # Why each was refused is written down beside the answers it was taken from, because
            # the run stops here and the next invocation reaches the count gate above before it
            # ever reaches this one. Held only in this return value, the reason — the single thing
            # that can make a second attempt differ from the first — would be gone by the time a
            # reader was actually launched.
            _write(aside / "why.json", {"refusals": checked["refusals"]})
            again = _again(_packet("answer", work, input=parts_path,
                                   out=work / f"answer-{index}", built=built), work, index)
            return {"stopped": "answering again",
                    "why": "cited evidence that does not resolve, so those parts are being asked "
                           "again against the built system as it now stands",
                    "pass": f"answer-{index}", "set_aside": str(aside),
                    "asking_again": [refusal["id"] for refusal in checked["refusals"]],
                    "refusals": checked["refusals"],
                    "work": [again]}

    # 9 · report — code. The verdict is arithmetic over the parts, not a whole-requirement label:
    # every part yes is already met; all-no work of one kind is add or remove; partial or mixed
    # work is change. The reader classifies one false part, and code combines those facts.
    answers: dict[str, dict[str, dict[str, str]]] = {}
    for index in range(1, PASSES + 1):
        for path in sorted((work / f"answer-{index}").glob("*.json")):
            if path.name == "summary.json":
                continue
            row = json.loads(path.read_text(encoding="utf-8"))
            answer = str(row.get("answer") or "").strip().lower()
            answers.setdefault(str(row.get("part_id")), {})[f"pass-{index}"] = {
                "answer": answer,
                "needed": str(row.get("needed") or "").strip().lower() if answer == "no" else "",
            }

    unanswered = [p["part_id"] for p in parts["parts"] if p["part_id"] not in answers]
    if unanswered:
        return {"stopped": "report", "why": "parts with no answer", "missing": unanswered}

    # 8b · settle — code finds the disputes, a model settles them. A part is a fact about the
    # repository, and a fact can be looked up; it was going to a person only because nothing had
    # been built to look it up. Two settling passes, as everywhere: a dispute counts as settled only
    # when both agree, so this can shrink what a person is handed and can never invent agreement.
    disputes_path = work / "disputes.json"
    if not disputes_path.exists():
        _write(disputes_path, _run([
            sys.executable, str(HERE / "gather_disputes.py"),
            *sum((["--answers", str(work / f"answer-{i}")] for i in range(1, PASSES + 1)), []),
            "--parts", str(parts_path),
        ]))
    disputes = json.loads(disputes_path.read_text(encoding="utf-8"))

    settled: dict[str, dict[str, dict[str, str]]] = {}
    if disputes["count"]:
        dispute_ids = {str(row["part_id"]) for row in disputes["disputed"]}
        waiting = []
        for index in range(1, PASSES + 1):
            out = work / f"settle-{index}"
            gate = stage_gate.inspect(
                out, dispute_ids, stage_gate.field_identity("part_id"), _settle_record,
                require_filename=True,
            )
            if not gate["complete"]:
                _quarantine(out, work, list(gate["reject_files"]), gate)
                waiting.append(_retry_packet(
                    _packet("settle", work, input=disputes_path, out=out, built=built), gate,
                ))
                continue
            checked = _run([
                sys.executable, str(HERE / "check_citations.py"),
                "--records", str(out), "--built", str(built),
            ])
            if checked["refused"]:
                refused_ids = {str(row.get("id")) for row in checked["refusals"]}
                files = _files_for_ids(out, refused_ids, "part_id")
                _quarantine(out, work, files, checked["refusals"])
                waiting.append(_retry_packet(
                    _packet("settle", work, input=disputes_path, out=out, built=built),
                    {"missing": sorted(refused_ids), "invalid": checked["refusals"]},
                ))
        if waiting:
            return {"stopped": "settling", "why": "a settling pass has not judged every dispute",
                    "disputes": disputes["count"], "work": waiting}

        for index in range(1, PASSES + 1):
            for path in sorted((work / f"settle-{index}").glob("*.json")):
                if path.name == "summary.json":
                    continue
                row = json.loads(path.read_text(encoding="utf-8"))
                answer = str(row.get("answer") or "").strip().lower()
                settled.setdefault(str(row.get("part_id")), {})[f"pass-{index}"] = {
                    "answer": answer,
                    "needed": str(row.get("needed") or "").strip().lower()
                    if answer == "no" else "",
                }

        # Only a dispute both settlers called the same way, and neither refused, is settled.
        for part_id, calls in settled.items():
            values = {(call["answer"], call["needed"]) for call in calls.values()}
            if len(values) == 1 and next(iter(values))[0] != "cannot settle":
                answer, needed = next(iter(values))
                answers[part_id] = {
                    f"pass-{i}": {"answer": answer, "needed": needed}
                    for i in range(1, PASSES + 1)
                }

    verdicts: dict[str, dict[str, str]] = {}
    part_splits: list[dict[str, object]] = []
    for index in range(1, PASSES + 1):
        held: dict[str, list[dict[str, str]]] = {}
        for part in parts["parts"]:
            held.setdefault(str(part["requirement_id"]), []).append(
                answers[str(part["part_id"])].get(f"pass-{index}", {}),
            )
        for rid, calls in held.items():
            verdicts.setdefault(rid, {})[f"pass-{index}"] = _requirement_verdict(calls)

    for part in parts["parts"]:
        calls = answers[str(part["part_id"])]
        values = {(call["answer"], call["needed"]) for call in calls.values()}
        if len(values) > 1:
            part_splits.append({
                "part_id": part["part_id"], "part": part["part"],
                "calls": {name: call["answer"] for name, call in calls.items()},
                "needed_by_pass": {name: call["needed"] for name, call in calls.items()
                                   if call["answer"] == "no"},
            })

    missing = [row["id"] for row in final["requirements"] if row["id"] not in verdicts]
    if missing:
        return {"stopped": "report", "why": "requirements with no verdict", "missing": missing}

    agreed = {rid: list(calls.values())[0] for rid, calls in verdicts.items()
              if len(set(calls.values())) == 1}
    split_calls = {rid: calls for rid, calls in verdicts.items() if len(set(calls.values())) > 1}

    report = {
        "subject": subject,
        "requirements": final["count"],
        "add": sorted(r for r, v in agreed.items() if v == "add"),
        "change": sorted(r for r, v in agreed.items() if v == "change"),
        "remove": sorted(r for r, v in agreed.items() if v == "remove"),
        "already_met": sorted(r for r, v in agreed.items() if v == "already met"),
        "parts": parts["count"],
        # The document's unit is the part, not the requirement: a part is one thing that is
        # separately true or false, which makes it the thing somebody can pick up and build. The
        # requirement above it is context. Everything a reader answered travels with it — the
        # answer, both calls when they differ, and the line behind a yes — so the document can be
        # read without opening the records beside it.
        "part_answers": [
            {
                **part,
                "calls": {name: call["answer"]
                          for name, call in answers[str(part["part_id"])].items()},
                "needed_by_pass": {name: call["needed"]
                                   for name, call in answers[str(part["part_id"])].items()
                                   if call["answer"] == "no"},
                "answer": (
                    next(iter(answers[str(part["part_id"])].values()))["answer"]
                    if len({(call["answer"], call["needed"])
                            for call in answers[str(part["part_id"])].values()}) == 1 else "split"
                ),
                "needed": (
                    next(iter(answers[str(part["part_id"])].values()))["needed"] or None
                    if len({(call["answer"], call["needed"])
                            for call in answers[str(part["part_id"])].values()}) == 1 else None
                ),
                "evidence": _first_citation(work, str(part["part_id"])),
            }
            for part in parts["parts"]
        ],
        "for_a_person": _decisions(final) + [
            {"kind": "verdicts disagree", "requirement": rid, "calls": calls,
             "because_these_parts_were_answered_differently": [
                 row for row in part_splits
                 if str(row["part_id"]).split(".")[0] == rid
             ]}
            for rid, calls in sorted(split_calls.items())
        ],
        "read_by": _readers(work),
        "measured_against_build": True,
    }

    # Both, always. The breakdown is what gets implemented and the requirements are what the
    # breakdown is made from — losing either leaves the other unusable.
    return _finish(report, work)


def _first_citation(work: Path, part_id: str) -> dict[str, object] | None:
    """The line a reader pointed at when it answered yes.

    A part that is done is worth nothing to whoever picks this up unless they can see what does it,
    and a part that is not done needs no evidence at all — that asymmetry is why a 'no' cites
    nothing. The first resolving citation is enough: the citation checker has already refused any
    that does not exist.
    """

    for index in range(1, PASSES + 1):
        path = work / f"answer-{index}" / f"{part_id}.json"
        if not path.is_file():
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        for citation in record.get("citations") or []:
            if isinstance(citation, dict) and citation.get("where"):
                return citation
    return None


def _readers(work: Path) -> dict[str, object]:
    """Who did the reading. The machinery never picks — it records.

    Nothing here names a model, and that is the design: the machinery says what a reader must do,
    and whoever runs it supplies the reader, so running it from a different tool reads it with that
    tool's model. What was missing is the other half. A run that agreed on 119 of 143 cannot be set
    beside a later run's number unless both say what did the reading, and for one whole run the
    only place that fact existed was the memory of the person who started it.
    """

    found: dict[str, object] = {}
    for scratch in sorted(work.glob("*-scratch")):
        stage = scratch.name[: -len("-scratch")]
        record = scratch / "reader.json"
        if not record.is_file():
            found[stage] = "not recorded — this reader did not say what it was"
            continue
        try:
            found[stage] = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as error:
            found[stage] = f"unreadable: {error}"
    return found


def _decisions(final: dict[str, object]) -> list[dict[str, object]]:
    """The places this machinery will not decide for anyone."""

    return [
        {"kind": "merge split between judgements", **row}
        for row in final.get("merges_refused_for_disagreement", [])
    ]


def drive(subject: str, description: Path, work: Path, built: Path | None) -> dict[str, object]:
    """Return one of four finite controller states; never leak a mechanical-stage traceback."""

    try:
        result = _drive(subject, description, work, built)
    except Exception as error:
        return {
            "status": "blocked",
            "stopped": "a mechanical stage failed",
            "why": f"{type(error).__name__}: {error}",
            "do": "correct the named work record or mechanical-stage failure, then rerun the same command",
        }
    if result.get("status"):
        return result
    if not result.get("stopped"):
        return {"status": "complete", **result}
    if result.get("work"):
        return {"status": "waiting_for_readers", **result}
    if result.get("correct_the_description_then_rerun"):
        return {"status": "needs_owner", **result}
    return {"status": "blocked", **result}


def _exit_code(result: dict[str, object]) -> int:
    return {
        "complete": 0,
        "waiting_for_readers": 2,
        "blocked": 3,
        "needs_owner": 4,
    }.get(str(result.get("status") or ""), 3)


def _progress_key(result: dict[str, object]) -> str:
    stable = {
        "status": result.get("status"),
        "stopped": result.get("stopped"),
        "work": [job.get("waiting_for") for job in result.get("work") or []],
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--description", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--built", type=Path, default=None,
                        help="the repository to measure against; omit when nothing is built yet")
    parser.add_argument("--reader-command", default=None,
                        help="a command that takes an instruction on standard input. Given one, "
                             "the controller launches every blind reader itself and runs until a "
                             "terminal status; an installed client policy is enforced before launch")
    args = parser.parse_args(argv)

    description = args.description.resolve()
    work = args.work.resolve()
    built = args.built.resolve() if args.built else None
    if not args.reader_command:
        state = drive(args.subject, description, work, built)
        print(json.dumps(state, indent=2))
        return _exit_code(state)

    import readers  # noqa: WPS433  # loaded only when the controller owns reader launches

    stuck, seen = 0, None
    while True:
        state = drive(args.subject, description, work, built)
        jobs = state.get("work") or []
        if state.get("status") != "waiting_for_readers" or not jobs:
            print(json.dumps(state, indent=2))
            return _exit_code(state)
        here = _progress_key(state)
        stuck = stuck + 1 if here == seen else 0
        seen = here
        if stuck >= 2:
            blocked = {
                "status": "blocked",
                "stopped": "reader loop stalled",
                "why": "two launch rounds produced no gate-visible progress",
                "last_state": state,
            }
            print(json.dumps(blocked, indent=2))
            return _exit_code(blocked)
        try:
            readers.launch(jobs, args.reader_command, built or description.parent, work, "read")
        except ValueError as error:
            blocked = {
                "status": "blocked",
                "stopped": "reader command refused before launch",
                "why": str(error),
            }
            print(json.dumps(blocked, indent=2))
            return _exit_code(blocked)


if __name__ == "__main__":
    raise SystemExit(main())
