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

Run with no `--built` to stop after stage 6: that is the correct behaviour when nothing has been
built yet, and the first six stages are the whole answer.

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
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

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
        "output, a consequence named as a reason, a capability promised to a reader. Write one "
        "file per find into {out}, named after the entry id, with the skill's fields plus "
        "'candidate_id'. Finding nothing in a section is a legitimate result. Do not open the "
        "description itself or the built system."
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
        "named <part_id>.json holding {{'part_id','answer','citations':[{{'where','line','text'}}],"
        "'why_the_other_side_is_wrong'}} where answer is 'yes', 'no', or 'cannot settle'. A 'yes' "
        "or 'no' MUST cite the line that decides it and must say, in one sentence, what the other "
        "side missed or misread. 'Cannot settle' cites nothing and is a legitimate answer: a part "
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
        "{{'part_id','answer','citations':[{{'where','line','text'}}],'looked_at'}}. A 'yes' MUST "
        "cite at least one line carrying the behaviour — the path, the line number, and that line's "
        "exact text. A 'no' MUST fill 'looked_at': name the nearest thing in the build that "
        "addresses this part and say in one sentence why it does not satisfy it, citing its line "
        "the same way; and when nothing in the build is even near it, say what you searched for and "
        "where. A bare 'no' is refused. This is not bureaucracy: on the run that made this rule, 45 "
        "of the 55 parts the two readers split on had one citing a line for 'yes' and the other "
        "offering nothing at all for 'no', so there was no way to tell which had looked in the "
        "right place — and a disagreement nobody can settle is worse than a wrong answer, because "
        "it goes to a person with nothing to decide on. "
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
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 1):
        raise SystemExit(f"{' '.join(args)}\n{result.stderr.strip()}")
    return json.loads(result.stdout)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _records_in(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return len([p for p in directory.glob("*.json") if p.name != "summary.json"])


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
        refused = [{"id": path.name.rsplit("-", 1)[0], "unresolved": []}
                   for path in sorted(kept.glob("*.json"))]
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


def drive(subject: str, description: Path, work: Path, built: Path | None) -> dict[str, object]:
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
        wanted = len(claims["claims_to_cite"])
        # Two readers, as everywhere else. One pass here was the one place this rule was not
        # applied, and it cost: a third pass found two statements the second had read and passed.
        waiting = [
            _packet("verify", work, input=claims_path, out=work / f"verify-{index}", count=wanted)
            for index in range(1, PASSES + 1)
            if wanted and _records_in(work / f"verify-{index}") < wanted
        ]
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

    # 2 and 3 · oblige and leftover — model, two passes each, run in either order.
    waiting = []
    for stage, source, count in (
        ("oblige", obligations_in, len(split["obligations"])),
        ("leftover", leftover_in, len(split["leftover"])),
    ):
        for index in range(1, PASSES + 1):
            out = work / f"{stage}-{index}"
            if stage == "oblige" and _records_in(out) < count:
                waiting.append(_packet(stage, work, skill=skill, input=source, out=out))
            elif stage == "leftover" and not out.is_dir():
                waiting.append(_packet(stage, work, skill=skill, input=source, out=out))
    if waiting:
        return {"stopped": "reading", "why": "a reading stage has not finished", "work": waiting}

    # The obligation stage's gate is coverage: every obligation accounted for, in both passes.
    for index in range(1, PASSES + 1):
        coverage = _run([
            sys.executable, str(HERE / "check_coverage.py"),
            "--candidates", str(obligations_in), "--records", str(work / f"oblige-{index}"),
        ])
        if not coverage["complete"]:
            return {"stopped": "coverage", "pass": index, "unaccounted": coverage["unaccounted"]}

    # 4 · pair — code. It proposes; it never merges.
    pairs_path = work / "pairs.json"
    if not pairs_path.exists():
        _write(pairs_path, _run([
            sys.executable, str(HERE / "pair_candidates.py"),
            "--records", str(work / "oblige-1"), "--records", str(work / "leftover-1"),
        ]))
    pairs = json.loads(pairs_path.read_text(encoding="utf-8"))

    # 5 · merge — model, twice.
    waiting = [
        _packet("merge", work, input=pairs_path, out=work / f"merge-{index}")
        for index in range(1, PASSES + 1)
        if _records_in(work / f"merge-{index}") < pairs["pairs_to_read"]
    ]
    if waiting:
        return {"stopped": "merging", "why": "a merge pass has not judged every pair",
                "pairs": pairs["pairs_to_read"], "work": waiting}

    # 6 · consolidate — code. Only merges every pass agreed on.
    final_path = work / "requirements.json"
    if not final_path.exists():
        _write(final_path, _run([
            sys.executable, str(HERE / "consolidate.py"),
            "--records", str(work / "oblige-1"), "--records", str(work / "leftover-1"),
            *sum((["--merges", str(work / f"merge-{i}")] for i in range(1, PASSES + 1)), []),
        ]))
    final = json.loads(final_path.read_text(encoding="utf-8"))

    if built is None:
        return {
            "subject": subject,
            "requirements": final["count"],
            "for_a_person": _decisions(final),
            "note": "nothing is built, so the requirements are what must be added. Stages 7 and 8 "
                    "do not apply.",
        }

    # 7 · split — model, once. The split is material, not judgement: both judges read the same
    # parts, exactly as both merge judges read the same pairs. Two splitters on the same twenty-four
    # requirements produced seventy-three parts and sixty-one, every mismatch one part apart and
    # none about substance — so a second split buys a reconciliation problem and no evidence.
    split_dir = work / "split-1"
    if _records_in(split_dir) < final["count"]:
        return {"stopped": "splitting", "why": "not every requirement is broken into parts",
                "requirements": final["count"],
                "work": [_packet("split", work, twinned=False,
                                 input=final_path, out=split_dir)]}

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

    # 8 · answer — model, twice. Yes or no per part, never a degree.
    waiting = [
        _again(_packet("answer", work, input=parts_path,
                       out=work / f"answer-{index}", built=built), work, index)
        for index in range(1, PASSES + 1)
        if _records_in(work / f"answer-{index}") < parts["count"]
    ]
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

    # 9 · report — code. The verdict is arithmetic over the parts, not a judgement anyone made:
    # every part yes is already met, no part yes is add, anything between is change. That is the
    # whole of the fix — the reader answers what it can answer, and the counting is not its job.
    answers: dict[str, dict[str, str]] = {}
    for index in range(1, PASSES + 1):
        for path in sorted((work / f"answer-{index}").glob("*.json")):
            if path.name == "summary.json":
                continue
            row = json.loads(path.read_text(encoding="utf-8"))
            answers.setdefault(str(row.get("part_id")), {})[f"pass-{index}"] = str(
                row.get("answer"),
            ).strip().lower()

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

    settled: dict[str, dict[str, str]] = {}
    if disputes["count"]:
        waiting = [
            _packet("settle", work, input=disputes_path, out=work / f"settle-{index}", built=built)
            for index in range(1, PASSES + 1)
            if _records_in(work / f"settle-{index}") < disputes["count"]
        ]
        if waiting:
            return {"stopped": "settling", "why": "a settling pass has not judged every dispute",
                    "disputes": disputes["count"], "work": waiting}

        for index in range(1, PASSES + 1):
            for path in sorted((work / f"settle-{index}").glob("*.json")):
                if path.name == "summary.json":
                    continue
                row = json.loads(path.read_text(encoding="utf-8"))
                settled.setdefault(str(row.get("part_id")), {})[f"pass-{index}"] = str(
                    row.get("answer"),
                ).strip().lower()

        # Only a dispute both settlers called the same way, and neither refused, is settled.
        for part_id, calls in settled.items():
            values = set(calls.values())
            if len(values) == 1 and values != {"cannot settle"}:
                answers[part_id] = {f"pass-{i}": next(iter(values)) for i in range(1, PASSES + 1)}

    verdicts: dict[str, dict[str, str]] = {}
    part_splits: list[dict[str, object]] = []
    for index in range(1, PASSES + 1):
        held: dict[str, list[str]] = {}
        for part in parts["parts"]:
            held.setdefault(str(part["requirement_id"]), []).append(
                answers[str(part["part_id"])].get(f"pass-{index}", ""),
            )
        for rid, calls in held.items():
            yes = calls.count("yes")
            verdicts.setdefault(rid, {})[f"pass-{index}"] = (
                "already met" if yes == len(calls) else "add" if yes == 0 else "change"
            )

    for part in parts["parts"]:
        calls = answers[str(part["part_id"])]
        if len(set(calls.values())) > 1:
            part_splits.append({"part_id": part["part_id"], "part": part["part"], "calls": calls})

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
                "calls": answers[str(part["part_id"])],
                "answer": (
                    list(answers[str(part["part_id"])].values())[0]
                    if len(set(answers[str(part["part_id"])].values())) == 1 else "split"
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
    }

    # The document is the deliverable, and for one whole run this stage ended by printing a list of
    # identifiers to a terminal — so whether the machinery had produced a requirements document
    # depended on whether the caller remembered to redirect the output. It writes the file itself.
    report_path = work / "report.json"
    _write(report_path, report)
    written = _run([
        "python3", str(HERE / "write_document.py"),
        "--report", str(report_path),
        "--requirements", str(work / "requirements.json"),
        "--out", str(work / "requirements.md"),
        # Both, always. The breakdown is what gets implemented and the requirements are what the
        # breakdown is made from — losing either leaves the other unusable: jobs with no reason
        # behind them, or reasons nobody can pick up.
        "--parts-out", str(work / "what-to-build.md"),
    ])
    return {**report, "document": written["document"],
            "breakdown": written.get("breakdown")}


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--description", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--built", type=Path, default=None,
                        help="the repository to measure against; omit when nothing is built yet")
    args = parser.parse_args(argv)

    state = drive(
        args.subject, args.description.resolve(), args.work.resolve(),
        args.built.resolve() if args.built else None,
    )
    print(json.dumps(state, indent=2))
    return 1 if state.get("stopped") else 0


if __name__ == "__main__":
    raise SystemExit(main())
