#!/usr/bin/env python3
"""Collect the parts the two answering passes answered differently, with both sides' evidence.

Everywhere else in this machinery, a disagreement between two readers is handed to a person. That is
right for a judgement — a merge that turns on what a requirement is for — and wrong here, because a
part is a fact about the repository and a fact can be looked up. It was being handed over only
because nothing had been built to look it up.

Three wording changes to the answering stage failed to reduce the disagreements: spelling out that
half-satisfied counts as a change moved 68 to 69 of 91; demanding a reason for every 'no' moved 55
to 64 of 354, the wrong way. Between two rounds of the *same* instruction the yes-count moved by
twelve. The noise is larger than anything the wording achieved, so the answer is not a better
instruction; it is a reader that can see both answers and the lines behind them.

This tool takes no view on any of it. It pairs the two answers, carries each side's citations and
its account of what it looked at, and hands the set on. Whether a dispute can be settled is the next
stage's business, and a part it refuses to settle still reaches the person who owns the goal.

Usage:  python3 gather_disputes.py --answers <dir> --answers <dir> --parts <parts.json>
Prints one entry per disputed part, both answers side by side.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(directory: Path) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for path in sorted(directory.glob("*.json")):
        if path.name == "summary.json":
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        out[str(record.get("part_id") or path.stem)] = record
    return out


def gather(answer_dirs: list[Path], parts: list[dict[str, object]]) -> dict[str, object]:
    passes = [_load(d) for d in answer_dirs]
    by_id = {str(part["part_id"]): part for part in parts}

    disputed, agreed, missing = [], 0, []
    for part_id, part in by_id.items():
        calls = [p.get(part_id) for p in passes]
        if any(call is None for call in calls):
            missing.append(part_id)
            continue
        answers = {str(call.get("answer") or "").strip().lower() for call in calls}
        if len(answers) == 1:
            agreed += 1
            continue
        disputed.append({
            "part_id": part_id,
            "requirement_id": part.get("requirement_id"),
            "requirement": part.get("requirement"),
            "part": part.get("part"),
            "sides": [
                {
                    "read_by": answer_dirs[index].name,
                    "answer": str(call.get("answer") or "").strip().lower(),
                    "citations": call.get("citations") or [],
                    "looked_at": call.get("looked_at"),
                    "note": call.get("note"),
                }
                for index, call in enumerate(calls)
            ],
        })

    return {
        "disputed": disputed,
        "count": len(disputed),
        "agreed": agreed,
        "parts": len(by_id),
        "parts_with_no_answer": missing,
        "note": (
            "Both sides are carried whole, including what each says it looked at. A settling pass "
            "that cannot decide from these must say so; it is never required to pick one."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", type=Path, action="append", required=True)
    parser.add_argument("--parts", type=Path, required=True)
    args = parser.parse_args(argv)

    parts = json.loads(args.parts.read_text(encoding="utf-8"))["parts"]
    result = gather([d.resolve() for d in args.answers], parts)
    print(json.dumps(result, indent=2))
    return 1 if result["parts_with_no_answer"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
