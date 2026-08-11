#!/usr/bin/env python3
"""Collect the parts a requirement was broken into, and refuse a set that does not cover them all.

The measuring stage had one failure and it was always the same one: two readers agreed on what the
code does and split on how much of a half-built requirement counts as done. Twelve of twenty-four
disagreements were 'is this partly done or not done'; eleven were 'is a partial attempt an addition
or a change'. Sharper wording had already been tried on exactly that and moved it by one.

So the question is taken away from the reader. A requirement is broken into parts — each one thing
that is plainly true or false — every part is answered yes or no with a cited line, and the verdict
is arithmetic: all yes is already met; all-no work of one kind is add or remove; partial or mixed
work is change. Measured on the
twenty-four that had defeated the whole-requirement method, this produced agreement on fourteen.

The split itself is produced once, not twice, and that is deliberate. Two splitters given the same
twenty-four requirements produced seventy-three parts and sixty-one; every mismatch was one part
apart and none was about substance. The split is *material*, like the pairs the merge judges read —
it has to be the same for both judges, not reproducible by both. A split that is too coarse shows
up as a part nobody can answer, and a split that is too fine shows up as a disagreement; neither
hides.

Usage:  python3 gather_parts.py --parts <dir> --requirements <requirements.json>
Prints every part with the requirement it came from, and refuses when a requirement has none.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def gather(parts_dir: Path, requirements: list[dict[str, object]]) -> dict[str, object]:
    by_id = {str(row["id"]): row for row in requirements}
    parts: list[dict[str, object]] = []
    seen: set[str] = set()
    refused: list[dict[str, object]] = []

    for path in sorted(parts_dir.glob("*.json")):
        if path.name == "summary.json":
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as error:
            refused.append({"file": path.name, "why": f"not readable as a split: {error}"})
            continue

        rid = str(record.get("id") or path.stem)
        if rid not in by_id:
            refused.append({"file": path.name, "why": f"no requirement called {rid}"})
            continue
        rows = record.get("parts") or []
        if not rows:
            refused.append({"id": rid, "why": "split into no parts at all"})
            continue

        seen.add(rid)
        for index, row in enumerate(rows, start=1):
            text = str(row.get("part") or "").strip()
            if not text:
                refused.append({"id": rid, "why": f"part {index} is empty"})
                continue
            parts.append({
                "part_id": str(row.get("part_id") or f"{rid}.p{index}"),
                "requirement_id": rid,
                "requirement": by_id[rid]["requirement"],
                "part": text,
            })

    # The completeness arithmetic this machinery applies everywhere: a requirement with no parts is
    # a requirement nothing will judge, and it would leave the report quietly short.
    missing = sorted(set(by_id) - seen)

    return {
        "parts": parts,
        "count": len(parts),
        "requirements": len(by_id),
        "requirements_with_parts": len(seen),
        "requirements_with_no_parts": missing,
        "refusals": refused,
        "balances": not missing and not refused,
        "note": (
            "Every requirement must be split before anything is judged. The split is produced once "
            "and read by both judges, the way the pairs are."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    args = parser.parse_args(argv)

    final = json.loads(args.requirements.read_text(encoding="utf-8"))
    result = gather(args.parts.resolve(), final["requirements"])
    print(json.dumps(result, indent=2))
    return 0 if result["balances"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
