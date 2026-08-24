#!/usr/bin/env python3
"""Derive one intake route from every exact source qualification outcome."""

from __future__ import annotations


ALLOWED_QUALIFICATIONS = {
    "readable_projection_complete",
    "readable_projection_incomplete",
    "conversion_incomplete",
}


def decide(qualification: dict[str, object]) -> dict[str, object]:
    outcomes = qualification.get("outcomes")
    declared = qualification.get("qualification")
    if (
        not isinstance(outcomes, list)
        or not outcomes
        or qualification.get("source_count") != len(outcomes)
    ):
        return {
            "complete": False,
            "why": "source-set qualification lost its complete outcome set",
        }
    if any(
        not isinstance(item, dict)
        or item.get("qualification") not in ALLOWED_QUALIFICATIONS
        for item in outcomes
    ):
        return {
            "complete": False,
            "why": "source-set qualification contains an invalid source outcome",
        }
    for item in outcomes:
        gaps = item.get("gaps")
        if not isinstance(gaps, list):
            return {
                "complete": False,
                "why": f"source {item.get('source_id')} lost its exact gap inventory",
            }
        if item["qualification"] == "readable_projection_complete" and gaps:
            return {
                "complete": False,
                "why": f"complete source {item.get('source_id')} still contains gaps",
            }
        if item["qualification"] != "readable_projection_complete" and not gaps:
            return {
                "complete": False,
                "why": f"incomplete source {item.get('source_id')} has no exact gaps",
            }
    identities = [item.get("source_id") for item in outcomes]
    if (
        any(not isinstance(value, str) or not value for value in identities)
        or len(identities) != len(set(identities))
    ):
        return {
            "complete": False,
            "why": "source-set qualification has invalid or duplicate source identities",
        }
    all_readable = all(
        item["qualification"] == "readable_projection_complete"
        for item in outcomes
    )
    expected = (
        "readable_source_set_complete"
        if all_readable
        else "readable_source_set_incomplete"
    )
    if declared != expected:
        return {
            "complete": False,
            "why": (
                f"aggregate qualification {declared!r} contradicts exact source "
                f"outcomes; expected {expected!r}"
            ),
        }
    return {
        "complete": True,
        "route": (
            "first_layer_complete" if all_readable else "clarification_required"
        ),
    }
