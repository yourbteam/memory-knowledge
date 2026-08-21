#!/usr/bin/env python3
"""Bind every incomplete source unit to one exact clarification obligation."""

from __future__ import annotations

import hashlib
import json


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def bind(
    qualification: dict[str, object], qualification_event_sha256: str
) -> dict[str, object]:
    if not _is_digest(qualification_event_sha256):
        return {"complete": False, "why": "qualification event digest is invalid"}
    outcomes = qualification.get("outcomes")
    if not isinstance(outcomes, list):
        return {"complete": False, "why": "qualification outcomes are missing"}
    obligations: list[dict[str, object]] = []
    for source_position, item in enumerate(outcomes, 1):
        if not isinstance(item, dict):
            return {
                "complete": False,
                "why": f"qualification outcome {source_position} is malformed",
            }
        source_id = item.get("source_id")
        status = item.get("qualification")
        gaps = item.get("gaps")
        if not isinstance(source_id, str) or not isinstance(gaps, list):
            return {
                "complete": False,
                "why": (
                    f"qualification outcome {source_position} lost its identity or gaps"
                ),
            }
        if status == "readable_projection_complete":
            if gaps:
                return {
                    "complete": False,
                    "why": f"complete source {source_id} still contains gaps",
                }
            continue
        if status not in {
            "readable_projection_incomplete",
            "conversion_incomplete",
        } or not gaps:
            return {
                "complete": False,
                "why": f"incomplete source {source_id} has no exact gaps",
            }
        for gap_position, gap in enumerate(gaps, 1):
            if (
                not isinstance(gap, dict)
                or gap.get("source_id") != source_id
                or gap.get("unit") in {None, ""}
                or not isinstance(gap.get("reason"), str)
                or not str(gap["reason"]).strip()
            ):
                return {
                    "complete": False,
                    "why": (
                        f"gap {gap_position} for {source_id} contradicts its source "
                        "or lacks exact evidence"
                    ),
                }
            if status == "readable_projection_incomplete" and (
                not isinstance(item.get("projection_id"), str)
                or not _is_digest(item.get("projection_sha256"))
                or not isinstance(item.get("method"), str)
            ):
                return {
                    "complete": False,
                    "why": f"readable gap for {source_id} lost its projection identity",
                }
            obligations.append({
                "id": f"clarification-obligation-{len(obligations) + 1:06d}",
                "qualification_event_sha256": qualification_event_sha256,
                "source_position": source_position,
                "gap_position": gap_position,
                "source_id": source_id,
                "projection_id": item.get("projection_id"),
                "projection_sha256": item.get("projection_sha256"),
                "method": item.get("method"),
                "qualification": status,
                "unit": gap["unit"],
                "reason": gap["reason"],
                "gap_sha256": _digest(gap),
            })
    return {"complete": True, "obligations": obligations}
