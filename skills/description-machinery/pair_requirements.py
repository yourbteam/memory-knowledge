#!/usr/bin/env python3
"""Propose the requirement pairs worth reading, and judge none of them.

Grouping by shared wording was tried first and measured: at every threshold almost everything ended
up alone — 47 jobs of 52, then 64 of 72, then 88 of 90 — while whatever did join chained into one
lump of twenty-five requirements linked by pairs sharing nothing but "client" and "names". Similar
wording is not what makes two things one job.

What makes them one job is that one cannot exist before the other. The blocks before the block
states. That is a judgement about meaning, so it goes to a reader — and this tool does what code
does everywhere in this approach: it fixes what gets looked at, and proposes nothing.

The net is deliberately wide. A pair missed here can never be joined later, while a pair proposed
and refused costs one reading. So the floor is low and the ordering puts the most-shared first;
the reader throws away what does not belong.

Usage:  python3 pair_requirements.py --report <report.json> [--floor 0.15] [--cap 250]
Prints each pair with both requirement texts, ready to be judged.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

_EVERYWHERE = {
    "a", "an", "the", "is", "are", "be", "been", "it", "its", "that", "this", "of", "in", "on",
    "to", "for", "and", "or", "not", "no", "any", "every", "each", "with", "by", "as", "at",
    "from", "must", "may", "than", "then", "so", "which", "what", "where", "when", "step", "run",
    "carries", "carry", "says", "said", "same", "one", "two", "all", "into", "out", "before",
    "after", "own", "them", "they", "there", "have", "has", "does", "do", "can",
}


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9-]+", text.lower())
            if w not in _EVERYWHERE and len(w) > 3}


def propose(report: dict[str, object], floor: float, cap: int) -> dict[str, object]:
    rows = [row for row in (report.get("part_answers") or []) if str(row.get("answer")) == "no"]

    by_requirement: dict[str, dict[str, object]] = {}
    for row in rows:
        entry = by_requirement.setdefault(str(row["requirement_id"]),
                                          {"requirement": row["requirement"], "parts": []})
        entry["parts"].append({"part_id": row["part_id"], "part": row["part"]})

    # A word in most of the requirements cannot separate any of them. Measured, not listed, so a
    # different subject's vocabulary needs no edit here.
    seen = Counter()
    for entry in by_requirement.values():
        seen.update(_terms(str(entry["requirement"])))
    common = {word for word, count in seen.items() if count > max(3, len(by_requirement) // 4)}
    terms = {rid: _terms(str(e["requirement"])) - common for rid, e in by_requirement.items()}

    scored = []
    ids = sorted(by_requirement)
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            shared = terms[left] & terms[right]
            if not shared:
                continue
            score = len(shared) / min(len(terms[left]) or 1, len(terms[right]) or 1)
            if score >= floor:
                scored.append((score, left, right, sorted(shared)))

    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    kept = scored[:cap]

    return {
        "pairs": [
            {
                "left": left,
                "left_requirement": by_requirement[left]["requirement"],
                "left_parts": by_requirement[left]["parts"],
                "right": right,
                "right_requirement": by_requirement[right]["requirement"],
                "right_parts": by_requirement[right]["parts"],
                "shared_words": shared,
                "share": round(score, 2),
            }
            for score, left, right, shared in kept
        ],
        "pairs_to_read": len(kept),
        "requirements": len(by_requirement),
        "comparisons": len(ids) * (len(ids) - 1) // 2,
        "proposed_before_cap": len(scored),
        "dropped_by_cap": max(0, len(scored) - len(kept)),
        "words_too_common_to_separate": sorted(common),
        "note": (
            "These are candidates, not groups. One requirement presuming another is a judgement; "
            "this tool makes none. A pair dropped by the cap is reported rather than hidden."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--floor", type=float, default=0.15)
    parser.add_argument("--cap", type=int, default=250)
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    print(json.dumps(propose(report, args.floor, args.cap), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
