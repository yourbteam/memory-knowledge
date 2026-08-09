#!/usr/bin/env python3
"""Put the work in the order the readers found, and merge nothing.

This replaces an assembler that merged. Given the same readings, that one joined every pair the
readers agreed on and then joined the joins: A grounds B, B grounds C, and on the real subject
seventy-six of a hundred and forty-two requirements collapsed into a single job holding a hundred
and thirty-seven parts. It was the same lump the very first attempt produced by matching wording,
reached the other way round, and it teaches the same lesson twice: what two readers give when they
say "one of these must exist first" is an *order*, not a grouping. Grouping throws the order away
and then chains on it.

So nothing is merged here. Every requirement stays itself and carries what must exist before it.
The order comes out in rounds: everything that needs nothing, then everything whose needs are all
satisfied by the rounds before it, and so on. A round is a set of work that can be done in any
order, or at the same time, which is the thing somebody picking up the work actually needs to know.

Two things are reported rather than resolved. A dependency both readers agreed on while naming
different foundations is left for a person, because which comes first is the whole content of the
judgement. And a cycle — A before B before A — is left for a person too, since no order satisfies
it and picking one would be inventing an answer neither reader gave.

Usage:  python3 order_work.py --report <report.json> --depends <pass-dir> --depends <pass-dir>
Prints the work in rounds, each item with what it needs and why.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _verdicts(directory: Path) -> dict[tuple[str, str], dict[str, object]]:
    out: dict[tuple[str, str], dict[str, object]] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or "left" not in record or "right" not in record:
            continue
        left, right = str(record.get("left")), str(record.get("right"))
        out[tuple(sorted((left, right)))] = {
            "verdict": record.get("verdict"),
            "foundation": record.get("foundation"),
            "why": record.get("why"),
        }
    return out


def order(report: dict[str, object], depends: list[Path]) -> dict[str, object]:
    rows = [row for row in (report.get("part_answers") or []) if str(row.get("answer")) == "no"]
    by_requirement: dict[str, dict[str, object]] = {}
    for row in rows:
        entry = by_requirement.setdefault(str(row["requirement_id"]),
                                          {"requirement": row["requirement"], "parts": []})
        entry["parts"].append({"part_id": row["part_id"], "part": row["part"]})

    passes = [_verdicts(d) for d in depends]
    shared = set.intersection(*[set(p) for p in passes]) if passes else set()

    needs: dict[str, list[dict[str, object]]] = {rid: [] for rid in by_requirement}
    for_a_person = []
    for pair in sorted(shared):
        calls = [p[pair] for p in passes]
        if {c["verdict"] for c in calls} != {"one job"}:
            continue
        foundations = {str(c["foundation"]) for c in calls}
        if len(foundations) != 1:
            # Both say one must come first and they disagree about which. That is the judgement
            # itself, so it is not settled by preferring a reader.
            for_a_person.append({"kind": "agreed on the dependency, not on which comes first",
                                 "pair": list(pair), "foundations": sorted(foundations)})
            continue
        first = next(iter(foundations))
        second = pair[0] if pair[1] == first else pair[1]
        if first in needs and second in needs:
            needs[second].append({"needs": first, "why": calls[0]["why"]})

    # Rounds: everything whose needs are already satisfied, then the next such set, and so on.
    rounds: list[list[str]] = []
    placed: set[str] = set()
    remaining = set(by_requirement)
    while remaining:
        ready = sorted(rid for rid in remaining
                       if all(n["needs"] in placed for n in needs[rid]))
        if not ready:
            break
        rounds.append(ready)
        placed |= set(ready)
        remaining -= set(ready)

    # Whatever is left cannot be ordered: its needs depend on it, directly or round the loop.
    circular = sorted(remaining)

    work = []
    for number, ready in enumerate(rounds, start=1):
        for rid in ready:
            work.append({
                "round": number,
                "requirement_id": rid,
                "requirement": by_requirement[rid]["requirement"],
                "parts": by_requirement[rid]["parts"],
                "part_count": len(by_requirement[rid]["parts"]),
                "needs": [n["needs"] for n in needs[rid]],
                "because": [n["why"] for n in needs[rid]],
            })

    return {
        "work": work,
        "rounds": len(rounds),
        "in_each_round": [len(r) for r in rounds],
        "requirements": len(by_requirement),
        "parts": len(rows),
        "ordered": len(work),
        "dependencies_kept": sum(len(n) for n in needs.values()),
        "pairs_read": len(shared),
        "for_a_person": for_a_person,
        "circular_for_a_person": circular,
        "note": (
            "Nothing is merged. A requirement waits only for what both readers said it stands on, "
            "and anything in the same round can be built in any order."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--depends", type=Path, action="append", required=True)
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    print(json.dumps(order(report, [d.resolve() for d in args.depends]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
