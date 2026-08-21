#!/usr/bin/env python3
"""Code-owned decision boundary for independent intake source collection."""

from __future__ import annotations


ALLOWED_ACTIONS = ("add_source", "finish_sources")
TERMINAL_OUTCOMES = {"projected", "failed"}


def decide(action: object, outcomes: list[dict[str, object]]) -> dict[str, object]:
    if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
        return {
            "accepted": False,
            "why": "action must be exactly one of: add_source, finish_sources",
        }
    pending = [
        item.get("source_id")
        for item in outcomes
        if item.get("outcome") not in TERMINAL_OUTCOMES
    ]
    if action == "finish_sources" and pending:
        return {
            "accepted": False,
            "why": "finish_sources requires a terminal outcome for: "
            + ", ".join(str(item) for item in pending),
        }
    return {"accepted": True, "action": action}
