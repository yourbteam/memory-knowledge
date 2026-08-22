"""Prepare exact next-round obligations from current unmatched qualification gaps."""

from __future__ import annotations

import hashlib
import json


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def prepare(
    source_set_qualification: object,
    remaining_gaps: object,
    evidence_event_sha256: object,
    round_number: int,
) -> dict[str, object]:
    if (
        not isinstance(source_set_qualification, dict)
        or not isinstance(source_set_qualification.get("outcomes"), list)
        or not isinstance(remaining_gaps, list)
        or not remaining_gaps
        or any(not isinstance(item, dict) for item in remaining_gaps)
        or not isinstance(evidence_event_sha256, str)
        or len(evidence_event_sha256) != 64
        or not isinstance(round_number, int)
        or round_number < 2
    ):
        return {
            "complete": False,
            "why": "provide current qualification, nonempty remaining gaps, evidence digest, and follow-up round number",
        }
    declared: list[tuple[int, int, dict[str, object], dict[str, object]]] = []
    for source_position, outcome in enumerate(
        source_set_qualification["outcomes"], 1
    ):
        if not isinstance(outcome, dict) or not isinstance(outcome.get("gaps"), list):
            return {
                "complete": False,
                "why": f"qualification outcome received {outcome!r}; provide its exact gap list",
            }
        for gap_position, gap in enumerate(outcome["gaps"], 1):
            if not isinstance(gap, dict):
                return {
                    "complete": False,
                    "why": f"qualification gap received {gap!r}; provide one gap object",
                }
            declared.append((source_position, gap_position, outcome, gap))
    used: set[tuple[int, int]] = set()
    obligations: list[dict[str, object]] = []
    for position, remaining in enumerate(remaining_gaps, 1):
        matches = [
            item
            for item in declared
            if item[3] == remaining and item[:2] not in used
        ]
        if len(matches) != 1:
            return {
                "complete": False,
                "why": (
                    f"remaining gap {position} received {remaining!r}; provide one "
                    "exact unused current qualification gap"
                ),
            }
        source_position, gap_position, outcome, gap = matches[0]
        used.add((source_position, gap_position))
        obligations.append({
            "id": f"qualification-follow-up-{round_number:06d}-{position:06d}",
            "qualification_event_sha256": evidence_event_sha256,
            "source_position": source_position,
            "gap_position": gap_position,
            "source_id": gap.get("source_id"),
            "projection_id": outcome.get("projection_id"),
            "projection_sha256": outcome.get("projection_sha256"),
            "method": outcome.get("method"),
            "qualification": outcome.get("qualification"),
            "unit": gap.get("unit"),
            "reason": gap.get("reason"),
            "gap_sha256": _digest(gap),
        })
    return {
        "complete": True,
        "round": round_number,
        "obligation_count": len(obligations),
        "obligations": obligations,
    }
