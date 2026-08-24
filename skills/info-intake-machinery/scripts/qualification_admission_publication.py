#!/usr/bin/env python3
"""Prepare the exact append-only payload for one qualification admission."""

from __future__ import annotations


ROUTES = {"first_layer_complete", "clarification_required"}


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def prepare(
    route: object,
    obligations: list[dict[str, object]],
    qualification_event_sha256: object,
) -> dict[str, object]:
    if route not in ROUTES:
        return {"complete": False, "why": f"unsupported admission route {route!r}"}
    if not _is_digest(qualification_event_sha256):
        return {
            "complete": False,
            "why": "publication lost its qualification event digest",
        }
    if route == "first_layer_complete" and obligations:
        return {
            "complete": False,
            "why": "first-layer completion cannot carry clarification obligations",
        }
    if route == "clarification_required" and not obligations:
        return {
            "complete": False,
            "why": "clarification admission requires at least one exact obligation",
        }
    return {
        "complete": True,
        "publication": {
            "qualification_event_sha256": qualification_event_sha256,
            "route": route,
            "clarification_obligations": obligations,
        },
    }
