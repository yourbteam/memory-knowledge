#!/usr/bin/env python3
"""Reconcile exactly one qualification outcome for every collected source."""

from __future__ import annotations


ALLOWED_QUALIFICATIONS = {
    "readable_projection_complete",
    "readable_projection_incomplete",
    "conversion_incomplete",
}


def reconcile(
    closure: dict[str, object], qualifications: list[dict[str, object]]
) -> dict[str, object]:
    outcomes = closure.get("outcomes")
    if not isinstance(outcomes, list):
        return {"complete": False, "why": "closure outcomes must be one ordered list"}
    declared = [
        item.get("source_id") if isinstance(item, dict) else None
        for item in outcomes
    ]
    if any(not isinstance(value, str) or not value for value in declared):
        return {"complete": False, "why": "closure has an invalid source identity"}
    if len(declared) != len(set(declared)):
        return {"complete": False, "why": "closure source identities are duplicated"}

    indexed: dict[object, list[dict[str, object]]] = {}
    for item in qualifications:
        indexed.setdefault(item.get("source_id"), []).append(item)
    missing = [source_id for source_id in declared if source_id not in indexed]
    duplicate = [
        source_id for source_id in declared if len(indexed.get(source_id, [])) > 1
    ]
    unknown = sorted(
        str(source_id) for source_id in indexed if source_id not in set(declared)
    )
    if missing or duplicate or unknown:
        return {
            "complete": False,
            "why": (
                "qualification reconciliation failed: "
                f"missing={missing}; duplicate={duplicate}; unknown={unknown}"
            ),
        }
    ordered = [indexed[source_id][0] for source_id in declared]
    invalid = [
        item.get("source_id")
        for item in ordered
        if item.get("qualification") not in ALLOWED_QUALIFICATIONS
    ]
    if invalid:
        return {
            "complete": False,
            "why": f"invalid qualification outcomes for {invalid}",
        }
    return {
        "complete": True,
        "qualification": {
            "qualification": (
                "readable_source_set_complete"
                if all(
                    item["qualification"] == "readable_projection_complete"
                    for item in ordered
                )
                else "readable_source_set_incomplete"
            ),
            "source_count": len(declared),
            "outcomes": ordered,
        },
    }
