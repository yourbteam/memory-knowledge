#!/usr/bin/env python3
"""Take the next thing off the build order, have it built, and decide whether it is really done.

Everything before this step decided *what* to build and *in what order*. This one changes the
built system, and it is the first step in this machinery whose output is not a document. So it is
also the first that can quietly do damage, and the gates are shaped around that.

Three of them, in this order:

**What passes now.** The built system's tests are run *before* the change and the failures are
written down. On the subject this was built against, eight tests already failed for reasons that
have nothing to do with the work — so "all tests pass" would have refused every change forever,
and "the tests ran" would have accepted a change that broke twenty. The gate is neither: nothing
that passed before may fail after. That is the question a person actually cares about.

**The parts, answered again.** The requirements machinery already asked whether each part is true
of the built system and recorded 'no'. After the change, two readers who cannot see each other are
asked the same question against the changed code, and each 'yes' must quote the line it rests on.
A change that convinces one reader is not done.

**One thing at a time.** The builder is given one requirement, its parts, and nothing else. It may
not fix what it notices in passing: an unrelated repair inside this change makes it impossible to
say which edit made the part true, and the next run inherits the confusion.

Usage:
    python3 build_next.py --order <order.json> --work <dir> --built <repo> --tests '<command>'

Prints what is outstanding for the current item, or the verdict when it is finished. Run it,
do what it hands back, run it again.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

PASSES = 2

#: How many times one item may be handed back to a builder before it goes to a person. A refusal is
#: information, not failure — the first item refused here was refused rightly, and a machinery with
#: no second attempt would have stalled on it. But an item that cannot be made true in three tries
#: is telling us something the builder cannot fix by trying again.
ATTEMPTS = 3

#: Said when a previous attempt was refused. The objection is quoted rather than summarised: on the
#: refusal that made this necessary, the readers' own words — that the change marks the sentence and
#: a mark stops nothing — were the whole content of what had to change.
AGAIN = (
    "\n\nAn earlier attempt at this was refused. What it changed: {what_changed}\n\nWhy the "
    "readers refused it, in their words:\n{objections}\n\nThat earlier change is still in the "
    "system. Decide for yourself whether to build on it, narrow it, or take it out — but the "
    "sentences above must end up true, and the objection above must no longer hold."
)

#: The change itself. It says what must become true, never how — the how is the builder's judgement
#: against the code in front of it, and a machinery that dictates the edit is just a slower author.
BUILD = (
    "In the system at {built}, make this true: {requirement}\n\nIt is true when all of these are "
    "true:\n{parts}\n\nRules. Change as little as possible, and change nothing that is not needed "
    "for the sentences above — if you notice something else wrong, leave it and say so at the end, "
    "because a repair mixed into this change makes it impossible to tell which edit made the part "
    "true. Do not change any test to make it agree with you; if a test contradicts the sentences "
    "above, stop and say so. When you are done, write {out}/change.json holding "
    "{{'files': ['<path you changed>', ...], 'what_changed': '<a few sentences a person can "
    "read>', 'left_alone': '<anything you noticed and did not touch>'}}."
)

#: The reading that decides it. Deliberately the same question the requirements machinery asked, so
#: a 'yes' here is comparable with the 'no' that put this on the list in the first place.
VERIFY = (
    "For each of these sentences, answer whether it is true of the system at {built} right now. "
    "Each one is given with the name it must be answered under, and that name must come back "
    "exactly as written — the first time this step ran, two readers answered the same sentence "
    "under two different names, and the gate that counts one answer per reader could not tell it "
    "had only heard from one of them:\n{named_parts}\n\nWrite one file per sentence into {out}: "
    "{{'part_id','answer':'yes'|'no','citations':[{{'where':'<absolute file path>','line':<number>,"
    "'text':'<that line, exactly>'}}],'looked_at':'<what you read and where>'}}. A 'yes' carries at "
    "least one citation whose text is that line character for character; a 'no' says what you "
    "looked at and names the nearest thing to it in the system. Read the built system, nothing else."
)

BLIND = (
    " You are one of two independent readers of this same question: do not open any sibling output "
    "or scratch directory, and do not look for what the other found. Agreement between two readers "
    "who could not see each other is the only evidence this machinery accepts."
)

HOW_TO_READ = (
    " Write files as you go so progress is visible; a reader that writes nothing until the end "
    "cannot be told apart from one that has stopped. Put every working, scratch or intermediate "
    "file in {scratch} and nowhere else — that directory is yours alone. Before you finish, write "
    "{scratch}/reader.json holding {{'model': '<the model you are, as you are identified>', "
    "'harness': '<the tool you are running inside>'}}. This machinery never chooses a reader — "
    "whoever runs it supplies one, so the record has to say who did the reading."
)


def _failures(built: Path, tests: str) -> dict[str, object]:
    """Run the built system's own tests and note which ones fail, in its own words."""

    done = subprocess.run(tests, shell=True, cwd=built, capture_output=True, text=True)
    output = done.stdout + done.stderr
    failed = sorted(set(re.findall(r"^FAILED (\S+)", output, re.M)))
    return {"command": tests, "exit_code": done.returncode, "failed": failed,
            "tail": output.strip().splitlines()[-1:] or [""]}


def _answers_in(directory: Path) -> int:
    return len(list(directory.glob("*.json"))) if directory.is_dir() else 0


def _packet(instruction: str, out: Path, scratch: Path, blind: bool) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    if blind:
        instruction += BLIND
    return {"instruction": instruction + HOW_TO_READ.format(scratch=scratch),
            "waiting_for": str(out)}


def next_item(order: dict[str, object], work: Path) -> dict[str, object] | None:
    """The earliest round first, and inside a round the smallest piece of work."""

    for item in sorted(order["work"], key=lambda w: (w["round"], w["part_count"],
                                                     str(w["requirement_id"]))):
        if not (work / f"build-{item['requirement_id']}" / "done.json").exists():
            return item
    return None


def drive(order: dict[str, object], work: Path, built: Path, tests: str) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    item = next_item(order, work)
    if item is None:
        return {"finished": "every item in the order has been built and verified"}

    rid = str(item["requirement_id"])
    out = work / f"build-{rid}"
    out.mkdir(parents=True, exist_ok=True)
    parts = "\n".join(f"- {p['part']}" for p in item["parts"])
    named_parts = "\n".join(f"- [{p['part_id']}] {p['part']}" for p in item["parts"])

    # 1 · what passes now, recorded before anything is touched.
    before_path = out / "tests-before.json"
    if not before_path.exists():
        before_path.write_text(json.dumps(_failures(built, tests), indent=2), encoding="utf-8")
    before = json.loads(before_path.read_text(encoding="utf-8"))

    # 2 · the change. A refused attempt is moved aside so the builder is asked again, carrying what
    # the readers objected to. Without this the step returned 'not built' and handed back nothing,
    # and the whole order stalled on the first honest refusal.
    change_path = out / "change.json"
    refused = sorted(out.glob("refused-*.json"))
    if not change_path.exists():
        instruction = BUILD.format(
            built=built, requirement=item["requirement"], parts=parts, out=out,
        )
        if refused:
            last = json.loads(refused[-1].read_text(encoding="utf-8"))
            instruction += AGAIN.format(
                what_changed=last["what_changed"],
                objections="\n".join(f"- {line}" for line in last["objections"]),
            )
        return {
            "stopped": "building" if not refused else "building again",
            "item": rid,
            "requirement": item["requirement"],
            "attempt": len(refused) + 1,
            "already_failing_before_the_change": len(before["failed"]),
            "work": [_packet(
                instruction, out, out.parent / f"build-{rid}-scratch", blind=False,
            )],
        }
    change = json.loads(change_path.read_text(encoding="utf-8"))

    # 3 · the same question, asked again, by two readers who cannot see each other.
    waiting = []
    for index in range(1, PASSES + 1):
        checked = work / f"check-{rid}-{index}"
        if _answers_in(checked) < len(item["parts"]):
            waiting.append(_packet(
                VERIFY.format(built=built, named_parts=named_parts, out=checked),
                checked, work / f"check-{rid}-{index}-scratch", blind=True,
            ))
    if waiting:
        return {"stopped": "checking the change", "item": rid, "changed": change["files"],
                "work": waiting}

    # 4 · the verdict. Nothing that passed before may fail now, and both readers must say yes.
    after = _failures(built, tests)
    (out / "tests-after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
    broke = sorted(set(after["failed"]) - set(before["failed"]))

    # One answer per part per pass, and every one of them yes. Counting distinct answers instead
    # of answers-per-pass is how the first run of this step passed a part that only one reader had
    # answered: the two readers had named the same sentence differently, so each name carried a
    # single 'yes' and the set of answers looked unanimous.
    said: dict[str, list[str]] = {}
    for index in range(1, PASSES + 1):
        for path in sorted((work / f"check-{rid}-{index}").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            said.setdefault(str(record.get("part_id")), []).append(str(record.get("answer")))
    wanted = {str(p["part_id"]) for p in item["parts"]}
    unproven = sorted(pid for pid in wanted
                      if said.get(pid, []).count("yes") < PASSES)
    missing = sorted(pid for pid in wanted if pid not in said)
    unnamed = sorted(set(said) - wanted)

    verdict = {
        "item": rid,
        "requirement": item["requirement"],
        "changed": change["files"],
        "what_changed": change.get("what_changed"),
        "left_alone": change.get("left_alone"),
        "tests_that_broke": broke,
        "parts_both_readers_call_true": sorted(wanted - set(unproven)),
        "parts_not_agreed": unproven,
        "parts_no_reader_answered": missing,
        "answers_under_a_name_no_part_has": unnamed,
        "built": not broke and not unproven and not missing and not unnamed,
    }
    if verdict["built"]:
        (out / "done.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        return verdict

    # Refused. Keep everything — the change stays in place and the reading stays on disk — but
    # record why, set this attempt aside, and let the next run hand it back to a builder.
    objections = []
    for index in range(1, PASSES + 1):
        for path in sorted((work / f"check-{rid}-{index}").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if str(record.get("answer")) != "yes":
                objections.append(
                    f"{record.get('part_id')}: {record.get('looked_at') or 'no reason given'}"
                )
    if broke:
        objections.append("these tests passed before the change and fail after it: "
                          + ", ".join(broke))

    attempt = len(refused) + 1
    verdict["attempt"] = attempt
    verdict["objections"] = objections
    (out / f"refused-{attempt}.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    change_path.rename(out / f"change-{attempt}.json")
    for index in range(1, PASSES + 1):
        checked = work / f"check-{rid}-{index}"
        if checked.is_dir():
            checked.rename(work / f"check-{rid}-{index}-attempt-{attempt}")

    if attempt >= ATTEMPTS:
        verdict["for_a_person"] = (
            f"{attempt} attempts have been refused. What is being asked may not be buildable as "
            "stated, or the sentences may be describing something the system does elsewhere."
        )
    return verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--built", type=Path, required=True)
    parser.add_argument("--tests", required=True,
                        help="the built system's own test command, run from its root")
    args = parser.parse_args(argv)

    order = json.loads(args.order.read_text(encoding="utf-8"))
    print(json.dumps(
        drive(order, args.work.resolve(), args.built.resolve(), args.tests), indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
