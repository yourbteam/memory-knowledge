"""Decide layer-one completion from current gaps and exact resolved obligations."""

from __future__ import annotations

import hashlib
import json


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _current_gap_identity(
    outcome: dict[str, object], gap: dict[str, object]
) -> tuple[object, ...]:
    return (
        gap.get("source_id"),
        outcome.get("projection_id"),
        outcome.get("projection_sha256"),
        outcome.get("method"),
        outcome.get("qualification"),
        gap.get("unit"),
        gap.get("reason"),
        _digest(gap),
    )


def _obligation_identity(item: dict[str, object]) -> tuple[object, ...]:
    return (
        item.get("source_id"),
        item.get("projection_id"),
        item.get("projection_sha256"),
        item.get("method"),
        item.get("qualification"),
        item.get("unit"),
        item.get("reason"),
        item.get("gap_sha256"),
    )


def decide(
    source_set_qualification: object,
    obligations: object,
    resolved_obligation_ids: object,
) -> dict[str, object]:
    if (
        not isinstance(source_set_qualification, dict)
        or not isinstance(source_set_qualification.get("outcomes"), list)
        or not isinstance(obligations, list)
        or any(not isinstance(item, dict) for item in obligations)
        or not isinstance(resolved_obligation_ids, list)
        or any(not isinstance(item, str) for item in resolved_obligation_ids)
    ):
        return {
            "decided": False,
            "why": "provide current qualification outcomes, exact obligations, and resolved obligation ids",
        }
    current_gaps: list[tuple[dict[str, object], tuple[object, ...]]] = []
    for outcome in source_set_qualification["outcomes"]:
        if not isinstance(outcome, dict) or not isinstance(outcome.get("gaps"), list):
            return {
                "decided": False,
                "why": f"qualification outcome received {outcome!r}; provide its exact gap list",
            }
        for gap in outcome["gaps"]:
            if not isinstance(gap, dict):
                return {
                    "decided": False,
                    "why": f"qualification gap received {gap!r}; provide one gap object",
                }
            current_gaps.append((gap, _current_gap_identity(outcome, gap)))
    resolved = set(resolved_obligation_ids)
    covered = {
        _obligation_identity(item)
        for item in obligations
        if item.get("id") in resolved
    }
    remaining = [
        gap
        for gap, identity in current_gaps
        if identity not in covered
    ]
    return {
        "decided": True,
        "disposition": (
            "first_layer_complete" if not remaining else "clarification_required"
        ),
        "source_count": source_set_qualification.get("source_count"),
        "current_gap_count": len(current_gaps),
        "covered_gap_count": len(current_gaps) - len(remaining),
        "remaining_gap_count": len(remaining),
        "remaining_gaps": remaining,
    }
