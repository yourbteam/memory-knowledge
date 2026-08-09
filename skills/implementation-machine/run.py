#!/usr/bin/env python3
"""Drive the whole machinery: propose the pairs, hand back the reading, put the work in order.

The steps have to happen in one order and each one refuses to run before the one before it is
finished. That was true from the start and lived nowhere: it lived in whoever was typing the
commands, and on the day this file was written that person fed three separate slices to a step
that compares one whole pass against another. It would have found nothing in common and reported
an empty answer that looked like a finished one. A rule kept in a person's head is a rule the
machinery does not have.

So this owns the order and the gates. Run it, do whatever it hands back, run it again. It is safe
to run at any moment: it re-derives nothing that already exists and hands back only what is still
outstanding.

    python3 run.py --report <requirements-report.json> --work <dir> [--per-reader 550]

The report is the requirements machinery's own output — the one that says, part by part, what is
already true of the built system and what is not. Only the parts answered 'no' are work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import order_work  # noqa: E402
import pair_requirements  # noqa: E402
import read_dependencies  # noqa: E402


def drive(report_path: Path, work: Path, per_reader: int, floor: float) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    # Everything below is derived from one report and kept so the run can stop and resume. That
    # only holds while it is the same report. The requirements machinery learned this the hard
    # way: its readers spent a round proving a sentence wrong that had already been rewritten.
    stamp = work / "report.sha256"
    now = hashlib.sha256(report_path.read_bytes()).hexdigest()
    if stamp.exists():
        was = stamp.read_text(encoding="utf-8").strip()
        if was != now:
            return {
                "stopped": "the requirements report changed after this run derived its material",
                "why": "the pairs and the readings were taken from the earlier report, so the "
                       "readers would be judging requirements that no longer say the same thing",
                "do": f"run again with a fresh --work directory, or delete {work}/pairs.json and "
                      "the depends directories to derive from the current report",
                "derived_from": was,
                "report_is_now": now,
            }
    else:
        stamp.write_text(now, encoding="utf-8")

    # 1 · pair — code. It proposes what is worth reading and judges nothing.
    pairs_path = work / "pairs.json"
    if not pairs_path.exists():
        proposed = pair_requirements.propose(report, floor, cap=10 ** 6)
        pairs_path.write_text(json.dumps(proposed, indent=2), encoding="utf-8")
    pairs = json.loads(pairs_path.read_text(encoding="utf-8"))
    if not pairs["pairs"]:
        return {"stopped": "nothing to pair",
                "why": "the report holds no part still to build, or no two of them share a word",
                "requirements": pairs["requirements"]}

    # 2 · depend — model, twice, in slices small enough for one reader to finish.
    reading = read_dependencies.hand_back(pairs, work, per_reader)
    if reading["outstanding"]:
        return {
            "stopped": "reading the pairs",
            "why": "every pair is judged by two readers who cannot see each other, and some "
                   "slice is not finished",
            "pairs": reading["pairs"],
            "slices": reading["slices"],
            "work": reading["work"],
        }

    # 3 · order — code. It merges nothing; it puts the work in the order the readers found.
    ordered = order_work.order(report, [Path(p) for p in reading["collected"]])
    out = work / "order.json"
    out.write_text(json.dumps(ordered, indent=2), encoding="utf-8")
    return {
        "subject": report.get("subject"),
        "requirements": ordered["requirements"],
        "parts": ordered["parts"],
        "rounds": ordered["rounds"],
        "in_each_round": ordered["in_each_round"],
        "dependencies_kept": ordered["dependencies_kept"],
        "for_a_person": ordered["for_a_person"],
        "circular_for_a_person": ordered["circular_for_a_person"],
        "order": str(out),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--per-reader", type=int, default=550)
    parser.add_argument("--floor", type=float, default=0.15)
    args = parser.parse_args(argv)

    print(json.dumps(
        drive(args.report.resolve(), args.work.resolve(), args.per_reader, args.floor), indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
