#!/usr/bin/env python3
"""Print the one number this machinery is judged by, from the run's own files.

The number: of the things that went into a description, how many came out of the requirements
machinery as an accepted requirement carrying a verdict. It is the only claim this machinery makes
about itself, and it decides whether its output is usable without the person who owns the goal
rewriting it first.

It exists because that number was computed by hand four times on one run and was wrong three of
them: 33, which counted requirements rather than things; 15, which read a reference like `L11` as a
line in the description when it is an index into a list; and 21, which resolved only the references
beginning `leftover-` and so lost every thing that arrived as an obligation. Each was a careful
reading of a real file and each was a different number, which is exactly what a number nobody can
reproduce looks like. Arithmetic over files a person can open is the whole of the fix.

Nothing here is a judgement. Every step is a lookup:

  a thing        a heading in the description — one observation, one intent, one topic
  a unit         one sentence or heading the split produced, which records the thing it sits under
  a requirement  names the units it came from, as `<stage>:<unit id>`
  a verdict      the report lists every requirement as add, change, remove or already met

A thing counts when some requirement naming one of its units appears in one of those four lists.
Nothing else counts, and a requirement with no verdict is not a result.

Usage:  python3 measure.py --split <split.json> --requirements <requirements.json> \
                           --report <report.json>
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

#: How a requirement names where it came from: a stage, then the unit's id within it.
FROM = re.compile(r":([A-Za-z]\d+)$")

def _things(units: list[dict[str, object]]) -> set[str]:
    """The headings that name a thing, which is every heading except the document's own title.

    A description opens with one heading naming the whole document and then a heading per thing.
    Counting the title as a thing makes the measure read one worse than it is, every time, and no
    reader can see why. The split records how deep each heading sits, so the shallowest is the
    title and everything below it is a thing. A description with no title — every heading at the
    same depth — has no shallowest to drop, and all of them count.
    """

    depths = {int(unit.get("under_depth") or 0) for unit in units if str(unit.get("under") or "")}
    title = min(depths) if len(depths) > 1 else None
    return {
        str(unit["under"]) for unit in units
        if str(unit.get("under") or "").strip() and int(unit.get("under_depth") or 0) != title
    }


def measure(split: Path, requirements: Path, report: Path) -> dict[str, object]:
    divided = json.loads(split.read_text(encoding="utf-8"))
    units = list(divided.get("obligations") or []) + list(divided.get("leftover") or [])
    thing_of = {str(unit["id"]): str(unit["under"]) for unit in units if unit.get("id")}
    things = _things(units)

    verdicts = json.loads(report.read_text(encoding="utf-8"))
    settled = {
        str(row): kind
        for kind in ("add", "change", "remove", "already_met")
        for row in verdicts.get(kind) or []
    }

    came_out: dict[str, list[str]] = {}
    unresolved: list[str] = []
    for row in json.loads(requirements.read_text(encoding="utf-8")).get("requirements") or []:
        if str(row["id"]) not in settled:
            continue
        for reference in row.get("from") or []:
            found = FROM.search(str(reference))
            if not found or found.group(1) not in thing_of:
                # A reference the arithmetic cannot resolve is reported, never ignored: an
                # unresolvable reference is how the count silently went to 21 instead of 22.
                unresolved.append(str(reference))
                continue
            came_out.setdefault(thing_of[found.group(1)], []).append(str(row["id"]))

    produced_nothing = sorted(things - set(came_out))
    return {
        "things_in": len(things),
        "came_out_as_a_requirement_with_a_verdict": len(came_out),
        "measure": f"{len(came_out)} of {len(things)}",
        "produced_nothing": produced_nothing,
        "requirements_per_thing": {thing: sorted(set(ids)) for thing, ids in sorted(came_out.items())},
        "references_that_do_not_resolve": sorted(set(unresolved)),
        "note": (
            "A thing counts when a requirement naming one of its units carries a verdict. This is "
            "arithmetic over the run's own files; nothing here judges anything."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    print(json.dumps(measure(args.split, args.requirements, args.report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
