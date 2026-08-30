#!/usr/bin/env python3
"""Require every extracted rule identity at exactly one terminal destination."""

from __future__ import annotations

from collections import Counter


def check(source_count: int, items: list[dict]) -> dict:
    identities = [source_id for item in items for source_id in item.get("source_rule_ids", [])]
    counts = Counter(identities)
    expected = set(range(1, source_count + 1))
    actual = set(identities)
    missing = sorted(expected - actual)
    duplicates = sorted(
        identity for identity, count in counts.items() if identity in expected and count != 1
    )
    unknown = sorted(actual - expected)
    return {
        "source_count": source_count,
        "terminal_count": len(items),
        "represented_count": len(identities),
        "missing": missing,
        "duplicates": duplicates,
        "unknown": unknown,
        "valid": not missing and not duplicates and not unknown,
    }
