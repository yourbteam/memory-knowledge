#!/usr/bin/env python3
"""Exact reconciliation gate for independent source collection closure."""

from __future__ import annotations


TERMINAL_OUTCOMES = {"projected", "failed"}


def reconcile(
    declared_source_ids: list[object], outcomes: list[dict[str, object]]
) -> dict[str, object]:
    declared: list[str] = []
    declared_seen: set[str] = set()
    issues: list[str] = []
    for value in declared_source_ids:
        if not isinstance(value, str) or not value:
            issues.append(f"invalid declared source identity: {value!r}")
            continue
        if value in declared_seen:
            issues.append(f"duplicate declared source identity: {value}")
            continue
        declared_seen.add(value)
        declared.append(value)

    indexed: dict[str, dict[str, object]] = {}
    duplicate_outcomes: list[str] = []
    unknown: list[str] = []
    for outcome in outcomes:
        source_id = outcome.get("source_id")
        if not isinstance(source_id, str):
            issues.append(f"outcome has invalid source identity: {source_id!r}")
            continue
        if source_id not in declared_seen:
            unknown.append(source_id)
            continue
        if source_id in indexed:
            duplicate_outcomes.append(source_id)
            continue
        indexed[source_id] = outcome

    missing = [source_id for source_id in declared if source_id not in indexed]
    nonterminal = [
        source_id
        for source_id in declared
        if source_id in indexed
        and indexed[source_id].get("outcome") not in TERMINAL_OUTCOMES
    ]
    if missing:
        issues.append("missing outcomes: " + ", ".join(missing))
    if duplicate_outcomes:
        issues.append("duplicate outcomes: " + ", ".join(sorted(set(duplicate_outcomes))))
    if unknown:
        issues.append("unknown outcomes: " + ", ".join(sorted(set(unknown))))
    if nonterminal:
        issues.append("nonterminal outcomes: " + ", ".join(nonterminal))
    if issues:
        return {"complete": False, "why": "; ".join(issues)}
    return {
        "complete": True,
        "source_ids": declared,
        "outcomes": [indexed[source_id] for source_id in declared],
    }
