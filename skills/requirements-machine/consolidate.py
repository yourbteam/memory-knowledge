#!/usr/bin/env python3
"""First half, last step: one numbered requirement list, with the merges actually agreed.

Three passes produced requirements and two passes judged which of them are the same requirement.
This applies the result. It is deliberately the dullest tool here, because the judgements were
made elsewhere and this must not quietly add one of its own.

Two rules it keeps:

**A merge is applied only when every judging pass agreed to it.** One pass merging and another
keeping apart is a disagreement, not a merge, and the pair is carried into the list unmerged and
flagged, because deleting a requirement on a split verdict is exactly the silent loss the merge
rule exists to prevent.

**Merging is transitive but never inferred.** If A merges with B and B with C, the three become
one entry naming all three sources. Nothing else is folded in on similarity.

Usage:  python3 consolidate.py --records <dir> [--records <dir>] --merges <dir> [--merges <dir>]
Prints the final numbered list, the merges applied, and the merges refused for want of agreement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pair_candidates import _load


def _verdicts(directories: list[Path]) -> dict[str, list[dict[str, object]]]:
    """Every pair verdict, keyed by the pair, one entry per judging pass."""

    byPair: dict[str, list[dict[str, object]]] = {}
    for directory in directories:
        for path in sorted(directory.glob("*.json")):
            if path.name == "summary.json":
                continue
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if not isinstance(row, dict) or not row.get("left") or not row.get("right"):
                continue
            key = "|".join(sorted((str(row["left"]), str(row["right"]))))
            byPair.setdefault(key, []).append({**row, "pass": directory.name})
    return byPair


class _Groups:
    """Which requirements have been joined into one. Plain union-find, no cleverness."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self._parent.setdefault(item, item)
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def join(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self._parent[b] = a


def consolidate(record_dirs: list[Path], merge_dirs: list[Path]) -> dict[str, object]:
    records = {row["id"]: row for row in _load(record_dirs)}
    verdicts = _verdicts(merge_dirs)

    groups = _Groups()
    applied, refused = [], []
    for key, judgements in sorted(verdicts.items()):
        left, right = key.split("|")
        calls = {str(row.get("verdict", "")).strip().lower() for row in judgements}
        if calls == {"merge"} and len(judgements) == len(merge_dirs):
            groups.join(left, right)
            applied.append({
                "left": left, "right": right,
                "surviving_requirement": next(
                    (str(row.get("surviving_requirement")) for row in judgements
                     if row.get("surviving_requirement")), "",
                ),
            })
        elif "merge" in calls:
            # One pass merged and another did not. The pair stays two requirements and the
            # disagreement is printed, because a split verdict is a question for a person.
            refused.append({
                "left": left, "right": right,
                "verdicts": {str(row["pass"]): row.get("verdict") for row in judgements},
                "why": [str(row.get("why", "")) for row in judgements],
            })

    grouped: dict[str, list[str]] = {}
    for identifier in sorted(records):
        grouped.setdefault(groups.find(identifier), []).append(identifier)

    final = []
    for index, (_, members) in enumerate(sorted(grouped.items()), start=1):
        merged_text = next(
            (row["surviving_requirement"] for row in applied
             if row["left"] in members and row["right"] in members
             and row["surviving_requirement"]),
            None,
        )
        primary = records[sorted(members)[0]]
        final.append({
            "id": f"r{index}",
            "requirement": merged_text or primary["requirement"],
            "from": sorted(members),
            "check": primary["check"],
        })

    return {
        "requirements": final,
        "count": len(final),
        "read": len(records),
        "merges_applied": applied,
        "merges_refused_for_disagreement": refused,
        "note": (
            "A merge was applied only where every judging pass agreed. A pair one pass merged and "
            "another kept apart is listed under the refusals and remains two requirements."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, action="append", required=True)
    parser.add_argument("--merges", type=Path, action="append", required=True)
    args = parser.parse_args(argv)

    print(json.dumps(consolidate(
        [d.resolve() for d in args.records], [d.resolve() for d in args.merges],
    ), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
