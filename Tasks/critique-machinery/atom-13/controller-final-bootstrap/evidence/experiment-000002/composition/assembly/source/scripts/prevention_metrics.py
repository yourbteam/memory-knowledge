#!/usr/bin/env python3
"""Reproducible enforcement metrics derived only from durable prevention events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence


class MetricIntegrityError(ValueError):
    """Raised when durable metric inputs are incomplete or contradictory."""


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise MetricIntegrityError("invalid-event-time")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetricIntegrityError("invalid-event-time") from exc


@dataclass(frozen=True)
class RegisteredUseMetric:
    registered_dispatches: int
    eligible_recurring_actions: int
    ratio: float
    passes_95_percent: bool
    denominator_intent_ids: tuple[str, ...]
    numerator_intent_ids: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "registered_dispatches": self.registered_dispatches,
            "eligible_recurring_actions": self.eligible_recurring_actions,
            "ratio": self.ratio,
            "passes_95_percent": self.passes_95_percent,
            "denominator_intent_ids": list(self.denominator_intent_ids),
            "numerator_intent_ids": list(self.numerator_intent_ids),
        }


def registered_use_metric(
    events: Sequence[Mapping[str, Any]],
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> RegisteredUseMetric:
    """Compute registered use without consulting current registry or outcome state."""
    in_window: list[Mapping[str, Any]] = []
    for event in events:
        recorded = _parse_utc(str(event.get("recorded_at_utc", "")))
        if window_start is not None and recorded < window_start:
            continue
        if window_end is not None and recorded >= window_end:
            continue
        in_window.append(event)

    all_intents = {
        str(event["intent_id"])
        for event in events
        if event.get("event_type") == "action_intent_recorded"
    }
    in_window_intents = {
        str(event["intent_id"])
        for event in in_window
        if event.get("event_type") == "action_intent_recorded"
    }
    eligibility_by_intent: dict[str, Mapping[str, Any]] = {}
    dispatch_by_intent: dict[str, Mapping[str, Any]] = {}
    for event in in_window:
        event_type = event.get("event_type")
        if event_type == "action_eligibility_recorded":
            intent_id = str(event["intent_id"])
            if intent_id in eligibility_by_intent:
                raise MetricIntegrityError(f"duplicate-eligibility:{intent_id}")
            eligibility_by_intent[intent_id] = event
    # Dispatch can complete after the eligibility measurement window closes.
    # Numerator identity is joined to the frozen in-window eligibility fact,
    # while the durable matching dispatch may be recorded later.
    for event in events:
        if event.get("event_type") == "dispatch_selected":
            intent_id = str(event["intent_id"])
            if intent_id in dispatch_by_intent:
                raise MetricIntegrityError(f"duplicate-selected-dispatch:{intent_id}")
            dispatch_by_intent[intent_id] = event

    missing = sorted(in_window_intents - set(eligibility_by_intent))
    orphaned = sorted(set(eligibility_by_intent) - all_intents)
    if missing:
        raise MetricIntegrityError("missing-eligibility:" + ",".join(missing))
    if orphaned:
        raise MetricIntegrityError("orphaned-eligibility:" + ",".join(orphaned))

    denominator: list[str] = []
    numerator: list[str] = []
    for intent_id, eligibility in eligibility_by_intent.items():
        eligible = (
            eligibility.get("recurrence_policy") == "RECURRENT"
            and eligibility.get("availability_policy") == "AVAILABLE"
            and eligibility.get("eligibility") is True
        )
        if not eligible:
            continue
        owner_id = eligibility.get("owner_sequence_id")
        contract_hash = eligibility.get("owner_contract_sha256")
        if not owner_id or not contract_hash:
            raise MetricIntegrityError(f"eligible-owner-unresolved:{intent_id}")
        denominator.append(intent_id)
        selected = dispatch_by_intent.get(intent_id)
        if selected is None:
            continue
        if (
            selected.get("selected_owner_sequence_id") != owner_id
            or selected.get("selected_owner_contract_sha256") != contract_hash
        ):
            raise MetricIntegrityError(f"selected-owner-identity-mismatch:{intent_id}")
        numerator.append(intent_id)

    denominator.sort()
    numerator.sort()
    denominator_count = len(denominator)
    numerator_count = len(numerator)
    ratio = numerator_count / denominator_count if denominator_count else 0.0
    return RegisteredUseMetric(
        registered_dispatches=numerator_count,
        eligible_recurring_actions=denominator_count,
        ratio=ratio,
        passes_95_percent=denominator_count > 0 and ratio >= 0.95,
        denominator_intent_ids=tuple(denominator),
        numerator_intent_ids=tuple(numerator),
    )
