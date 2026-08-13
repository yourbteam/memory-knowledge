#!/usr/bin/env python3
"""Hand back the reading that turns proposed pairs into agreed dependencies.

The pairing tool proposes; two readers who cannot see each other judge. Until now the
instruction those readers received was written by whoever was driving, in the message that
started them — which means the machinery could not be run by anyone else, and no two runs
were guaranteed to have asked the same question. Anything a reader must be told belongs in
a file the machinery owns, so it is here.

The second thing this settles is size. On the first subject the pairing proposed 549 pairs
and one reader carried them. On the second it proposed 1,131 at the same setting, which is
more than one reader finishes in a sitting — and lowering the net to fit the reader would
change what gets looked at to suit the tool, which is backwards. So the pairs are cut into
slices, each small enough to finish, and each pass reads every slice. Two passes over the
same slice, blind to each other, is still the evidence; the slicing only decides how much
one reader holds at once.

Usage:  python3 read_dependencies.py --pairs <pairs.json> --work <dir> [--per-reader 550]
Prints the jobs still outstanding, each stated completely enough to hand over. Run it again
after they are done: a slice whose answers are all present is not handed out twice.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PASSES = 2

#: What the reader judges. The relation is existence, not resemblance: the first version of this
#: step grouped by shared wording and nearly everything ended up alone, because two requirements
#: can share almost every word and still be two jobs.
JUDGE = (
    "Judge every pair in {slice_file}. For each pair answer one question: must one of these two "
    "already exist before the other can be built at all? Not whether they are similar, not whether "
    "they would be convenient to do together — whether one is the ground the other stands on. A "
    "section and the rule for what goes in it are one job; a prohibition and the thing to do "
    "instead are two. Write one file per pair into {out}: "
    "{{'left','right','verdict':'one job'|'separate','foundation','why'}}, where 'foundation' is "
    "the id of the one that must exist first and is null when the verdict is 'separate'. Read "
    "nothing but the pairs."
)

#: Said only to a reader that has a twin, which here is every reader.
BLIND = (
    " You are one of two independent readers of this same input: do not open any sibling output or "
    "scratch directory, and do not look for what the other found. Agreement between two readers who "
    "could not see each other is the only evidence this machinery accepts."
)

#: Learned on the requirements machinery and true here for the same reasons: a reader that writes
#: nothing until the end cannot be told apart from a stalled one, and two readers sharing a scratch
#: directory overwrote each other's working files under the same obvious names.
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


def _answers_in(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return len(list(directory.glob("*.json")))


def hand_back(pairs: dict, work: Path, per_reader: int) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    rows = pairs["pairs"]
    slices = [rows[start:start + per_reader] for start in range(0, len(rows), per_reader)]

    for number, chunk in enumerate(slices, start=1):
        path = work / f"pairs-{number}.json"
        if not path.exists():
            path.write_text(json.dumps({"pairs": chunk}, indent=2), encoding="utf-8")

    jobs = []
    for pass_number in range(1, PASSES + 1):
        for number, chunk in enumerate(slices, start=1):
            out = work / f"depends-{pass_number}-{number}"
            delivered = _answers_in(out)
            if delivered >= len(chunk):
                continue
            scratch = work / f"depends-{pass_number}-{number}-scratch"
            scratch.mkdir(parents=True, exist_ok=True)
            out.mkdir(parents=True, exist_ok=True)
            instruction = JUDGE.format(
                slice_file=work / f"pairs-{number}.json", out=out,
            ) + BLIND + HOW_TO_READ.format(scratch=scratch)
            jobs.append({
                "stage": "depends",
                "instruction": instruction,
                "waiting_for": str(out),
                "pairs": len(chunk),
                "expect": len(chunk),
                "wants": "*.json",
                "delivered": delivered,
            })

    if jobs:
        return {
            "pairs": len(rows),
            "slices": len(slices),
            "passes": PASSES,
            "outstanding": len(jobs),
            "work": jobs,
        }

    # Slicing is not finished until the slices are one pass again. The assembling step compares a
    # pass against a pass by intersecting what each judged, so handing it six part-passes would
    # intersect three disjoint slices and find nothing in common — every join lost, silently, with
    # a plausible-looking empty answer. So each pass is collected back into one directory here.
    collected = []
    for pass_number in range(1, PASSES + 1):
        whole = work / f"pass-{pass_number}"
        whole.mkdir(parents=True, exist_ok=True)
        for number in range(1, len(slices) + 1):
            for path in sorted((work / f"depends-{pass_number}-{number}").glob("*.json")):
                (whole / f"{number}-{path.name}").write_text(
                    path.read_text(encoding="utf-8"), encoding="utf-8",
                )
        collected.append(str(whole))

    return {
        "pairs": len(rows),
        "slices": len(slices),
        "passes": PASSES,
        "outstanding": 0,
        "work": [],
        "collected": collected,
        "then": (
            "every pair is judged twice. Assemble the jobs with group_parts.py, giving it each "
            "collected pass as a --depends — one --depends per pass, never one per slice"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--per-reader", type=int, default=550,
                        help="how many pairs one reader is asked to hold at once")
    args = parser.parse_args(argv)

    pairs = json.loads(args.pairs.read_text(encoding="utf-8"))
    print(json.dumps(hand_back(pairs, args.work.resolve(), args.per_reader), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
