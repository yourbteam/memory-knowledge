#!/usr/bin/env python3
"""Step four: turn completeness into a count.

The playbook this replaces stopped when two rounds in a row produced nothing new. That is a
feeling wearing a rule's clothes: it says the author ran out of ideas, not that the subject ran
out of faults. Nine runs of it produced nine different documents, and none of them could say what
was left.

Steps two and three made the faults countable. So completeness is now arithmetic: every candidate
in the enumerated list ends in exactly one of two places — a requirement, or a recorded reason it
is not one. Anything in neither place is unaccounted for, and the number of those is how far the
document is from done.

This checks that arithmetic. It decides nothing about whether a requirement is good or a reason is
honest; it only refuses to let a candidate quietly disappear.

It also prints, every time, what the enumeration cannot see. A count over a list is only a
completeness claim if the list's boundary is stated with it, and stating it in the output means
nobody has to remember it.

Usage:  python3 check_coverage.py --candidates <numbered-list.json> --records <dir>
Every *.json in the records directory is read. A record covers a candidate when it carries
`candidate_id`; it dismisses one when it carries `candidate_id` and `not_a_requirement_because`.
Exit status is 0 when nothing is unaccounted for, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

#: What a list of structural inconsistencies cannot contain, printed with every count so the
#: number is never read as more than it is.
BLIND_SPOT = (
    "This counts only faults where members of the set disagree. A fault every member shares is "
    "invisible to it — three of five record sets tried returned no candidates at all because "
    "every member was structurally identical. Zero unaccounted means the enumerated list is "
    "covered, never that the subject is faultless."
)


def _load_records(directory: Path) -> list[dict[str, object]]:
    records = []
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(record, dict):
            record["_file"] = path.name
            records.append(record)
    return records


def check(candidates_path: Path, records_dir: Path) -> dict[str, object]:
    listing = json.loads(candidates_path.read_text(encoding="utf-8"))
    # The second half enumerates candidate faults, the first half enumerates the obligations a
    # description states. Completeness is the same arithmetic over either, so the checker takes
    # whichever list it is given rather than one being reshaped to look like the other.
    rows = listing.get("candidates") or listing.get("obligations") or []
    candidates = {str(row["id"]): row for row in rows}
    records = _load_records(records_dir)

    required: dict[str, list[str]] = {}
    dismissed: dict[str, list[str]] = {}
    unknown: list[dict[str, str]] = []

    for record in records:
        candidate_id = record.get("candidate_id")
        if not candidate_id:
            continue
        candidate_id = str(candidate_id)
        if candidate_id not in candidates:
            # A record about a candidate that is not on the list. Either the list changed under
            # it or the id was mistyped; both make the count wrong, so neither is swallowed.
            unknown.append({"file": str(record.get("_file")), "candidate_id": candidate_id})
            continue
        target = dismissed if record.get("not_a_requirement_because") else required
        target.setdefault(candidate_id, []).append(str(record.get("_file")))

    accounted = set(required) | set(dismissed)
    unaccounted = [cid for cid in candidates if cid not in accounted]
    # One candidate both required and dismissed is a contradiction, not coverage.
    contradicted = sorted(set(required) & set(dismissed))

    return {
        "candidates": len(candidates),
        "required": len(required),
        "dismissed": len(dismissed),
        "unaccounted": sorted(unaccounted, key=lambda cid: int(cid.lstrip("c") or 0)),
        "contradicted": contradicted,
        "records_about_unknown_candidates": unknown,
        "complete": not unaccounted and not contradicted and not unknown,
        "blind_spot": BLIND_SPOT,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    args = parser.parse_args(argv)

    result = check(args.candidates, args.records)
    print(json.dumps(result, indent=2))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
