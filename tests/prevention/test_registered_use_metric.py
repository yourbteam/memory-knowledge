from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from scripts.prevention_metrics import MetricIntegrityError, registered_use_metric


NOW = "2026-07-17T12:00:00Z"


def intent_events(index: int, *, selected: bool = True) -> list[dict]:
    intent_id = f"intent-{index}"
    owner_hash = f"{index + 1:064x}"
    events = [
        {"event_type": "action_intent_recorded", "intent_id": intent_id, "recorded_at_utc": NOW},
        {
            "event_type": "action_eligibility_recorded",
            "intent_id": intent_id,
            "recorded_at_utc": NOW,
            "registry_sha256": "a" * 64,
            "owner_sequence_id": "discovery-bootstrap",
            "owner_contract_sha256": owner_hash,
            "recurrence_policy": "RECURRENT",
            "availability_policy": "AVAILABLE",
            "eligibility": True,
            "ineligible_reason_code": None,
        },
    ]
    if selected:
        events.append({
            "event_type": "dispatch_selected",
            "intent_id": intent_id,
            "recorded_at_utc": NOW,
            "selected_owner_sequence_id": "discovery-bootstrap",
            "selected_owner_contract_sha256": owner_hash,
        })
    return events


def test_exact_95_percent_boundary_uses_only_durable_pre_dispatch_facts():
    events = [event for index in range(20) for event in intent_events(index, selected=index < 19)]
    metric = registered_use_metric(events)

    assert metric.eligible_recurring_actions == 20
    assert metric.registered_dispatches == 19
    assert metric.ratio == 0.95
    assert metric.passes_95_percent is True

    later_state = copy.deepcopy(events)
    later_state.extend([
        {"event_type": "owner_became_unavailable", "recorded_at_utc": NOW},
        {"event_type": "dispatch_outcome_failed", "recorded_at_utc": NOW},
    ])
    assert registered_use_metric(later_state) == metric


def test_one_below_threshold_fails_and_identity_mismatch_fails_closed():
    events = [event for index in range(20) for event in intent_events(index, selected=index < 18)]
    assert registered_use_metric(events).passes_95_percent is False

    mismatched = intent_events(1)
    mismatched[-1]["selected_owner_contract_sha256"] = "f" * 64
    with pytest.raises(MetricIntegrityError, match="selected-owner-identity-mismatch"):
        registered_use_metric(mismatched)


def test_missing_or_duplicate_eligibility_fails_closed():
    missing = intent_events(1)
    del missing[1]
    with pytest.raises(MetricIntegrityError, match="missing-eligibility"):
        registered_use_metric(missing)

    duplicate = intent_events(2)
    duplicate.insert(2, copy.deepcopy(duplicate[1]))
    with pytest.raises(MetricIntegrityError, match="duplicate-eligibility"):
        registered_use_metric(duplicate)


def test_matching_dispatch_after_window_still_counts_frozen_eligibility():
    events = intent_events(3)
    events[-1]["recorded_at_utc"] = "2026-07-18T00:00:00Z"

    metric = registered_use_metric(
        events,
        window_end=datetime(2026, 7, 17, 23, 59, tzinfo=timezone.utc),
    )

    assert metric.eligible_recurring_actions == 1
    assert metric.registered_dispatches == 1


def test_intent_before_window_with_eligibility_inside_window_is_not_orphaned():
    events = intent_events(4)
    events[0]["recorded_at_utc"] = "2026-07-16T23:59:59Z"

    metric = registered_use_metric(
        events,
        window_start=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )

    assert metric.eligible_recurring_actions == 1
    assert metric.registered_dispatches == 1
