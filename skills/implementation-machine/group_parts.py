#!/usr/bin/env python3
"""Assemble the jobs: parts that must become true together, joined only where both readers agreed.

The first attempt grouped by shared wording and was measured against the first subject: at every
threshold nearly everything stood alone — 47 jobs of 52, then 64 of 72, then 88 of 90 — and whatever
did join chained into one lump of twenty-five requirements linked by pairs sharing nothing more than
"client" and "names". Similar wording is not what makes two things one job.

What makes them one job is that one cannot exist until the other does. Code proposes the pairs worth
reading; two readers who cannot see each other say which are real dependencies and which of the two
must exist first. This assembles the answer and judges nothing: a pair joins only when both said so,
and a pair they both called a dependency while disagreeing about which comes first is reported for a
person rather than resolved by picking a reader.

Measured on the first subject: 549 pairs read, 524 answered the same way by both, 17 joins agreed,
16 of those with the same foundation.

Usage:  python3 group_parts.py --report <report.json> --depends <dir> --depends <dir>
Prints the jobs, largest first, each with the order its foundations impose.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _verdicts(directory: Path) -> dict[tuple[str, str], dict[str, object]]:
    out: dict[tuple[str, str], dict[str, object]] = {}
    for path in sorted(directory.glob("*.json")):
        if path.name in {"summary.json", "reader.json"}:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        left, right = str(record.get("left")), str(record.get("right"))
        out[tuple(sorted((left, right)))] = {
            "verdict": str(record.get("verdict") or "").strip().lower(),
            "foundation": record.get("foundation"),
            "why": record.get("why"),
        }
    return out


def assemble(report: dict[str, object], depends: list[Path]) -> dict[str, object]:
    rows = [row for row in (report.get("part_answers") or []) if str(row.get("answer")) == "no"]
    by_requirement: dict[str, dict[str, object]] = {}
    for row in rows:
        entry = by_requirement.setdefault(str(row["requirement_id"]),
                                          {"requirement": row["requirement"], "parts": []})
        entry["parts"].append({"part_id": row["part_id"], "part": row["part"]})

    passes = [_verdicts(d) for d in depends]
    shared = set.intersection(*[set(p) for p in passes]) if passes else set()

    joins, for_a_person, unread = [], [], []
    for pair in sorted(shared):
        calls = [p[pair] for p in passes]
        verdicts = {c["verdict"] for c in calls}
        if verdicts != {"one job"}:
            continue
        foundations = {c["foundation"] for c in calls}
        if len(foundations) == 1:
            joins.append({"pair": list(pair), "foundation": next(iter(foundations)),
                          "why": calls[0]["why"]})
        else:
            # Both call it one job and disagree on which comes first. That ordering is the whole
            # point of the join, so it is not something to settle by preferring a reader.
            for_a_person.append({"kind": "same job, different foundation", "pair": list(pair),
                                 "foundations": sorted(str(f) for f in foundations)})

    for pass_index, judged in enumerate(passes, start=1):
        missing = sorted(set(shared) ^ set(judged))
        unread += [{"pass": pass_index, "pair": list(p)} for p in missing]

    parent = {rid: rid for rid in by_requirement}

    def find(rid: str) -> str:
        while parent[rid] != rid:
            parent[rid] = parent[parent[rid]]
            rid = parent[rid]
        return rid

    for join in joins:
        left, right = join["pair"]
        if left in parent and right in parent:
            parent[find(left)] = find(right)

    grouped: dict[str, list[str]] = {}
    for rid in sorted(by_requirement):
        grouped.setdefault(find(rid), []).append(rid)

    jobs = []
    for members in sorted(grouped.values(), key=lambda m: (-len(m), m)):
        inside = [j for j in joins if set(j["pair"]) <= set(members)]
        jobs.append({
            "requirements": members,
            "parts": [p for rid in members for p in by_requirement[rid]["parts"]],
            "part_count": sum(len(by_requirement[rid]["parts"]) for rid in members),
            "build_first": sorted({str(j["foundation"]) for j in inside}),
            "because": [j["why"] for j in inside],
        })

    return {
        "jobs": jobs,
        "job_count": len(jobs),
        "parts": len(rows),
        "requirements": len(by_requirement),
        "joined_by_both_readers": len(joins),
        "pairs_read": len(shared),
        "for_a_person": for_a_person,
        "pairs_one_pass_did_not_judge": unread,
        "note": (
            "A pair joins only when every reading pass called it a dependency. Agreement on the "
            "dependency but not on which comes first is left for a person, because the order is "
            "the reason for joining at all."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--depends", type=Path, action="append", required=True)
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    print(json.dumps(assemble(report, [d.resolve() for d in args.depends]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
