from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import work_memory


LEGACY_REOPEN_EVENT_ID = "f83c057e-7d00-434e-9a74-27ae58855291"
VERIFICATION_EVENT_ID = "92b861b1-ce7e-4c8b-b656-9674928ecea6"
REOPEN_RUN_ID = "ab62948c-92a6-426a-9d90-dbc5b08d89fd"
VERIFICATION_RUN_ID = "374f1574-382f-4676-9498-c0c7be817934"
PREDECESSOR_RUN_ID = "09413e63-fac1-40b8-b838-5b3017c3c2be"
BLOCKER_ID = "blk-e6936e8474bdc730de173c29"
OCCURRENCE_ID = "b61c8a8a-4cb3-4584-b45d-d04c2bdede3a"
CORRECTION_ID = "33ade852-2a7c-4cb3-85fe-8a67bd63b17e"
SUBJECT_ID = "discovery-603202c7-6007-5dc5-ba35-a67c69205d56"
LINEAGE_ID = SUBJECT_ID
SOURCE_HASH = "b" * 64
ARTIFACT_HASH = "a" * 64
ARTIFACT = {"repository_key": "memory-knowledge", "path": "scripts/fix.py"}


def _event(kind: str, event_id: str, **fields: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": kind,
        "recorded_at_utc": "2026-09-12T16:00:00Z",
        **fields,
    }


def _run_start(
    run_id: str,
    *,
    predecessor_run_id: str | None = None,
    source_bundle_hash: str = SOURCE_HASH,
    artifact_hash: str = ARTIFACT_HASH,
) -> dict[str, object]:
    start = _event(
        "run_started", str(uuid.uuid5(uuid.NAMESPACE_URL, f"start:{run_id}")),
        run_id=run_id,
        subject_id=SUBJECT_ID,
        lineage_id=LINEAGE_ID,
        mode="discovery",
        operation_kind="single-test",
        source_bundle=[{
            "repository_key": ARTIFACT["repository_key"],
            "path": ARTIFACT["path"],
            "sha256": artifact_hash,
        }],
        source_bundle_hash=source_bundle_hash,
        classification_receipt_hash="c" * 64,
        selection_receipt_hash="d" * 64,
        started_at_utc="2026-09-12T16:00:00Z",
    )
    if predecessor_run_id is not None:
        start["predecessor_run_id"] = predecessor_run_id
        start["verifies_correction_ids"] = [CORRECTION_ID]
    return start


def _history(
    *,
    reopen_event_id: str = LEGACY_REOPEN_EVENT_ID,
    reopen_source_hash: str = SOURCE_HASH,
    reopen_predecessor: str | None = None,
    reopen_artifact_hash: str = ARTIFACT_HASH,
    verification_outcome: str = "failed",
    verification_quality: str = "same-path",
) -> tuple[list[dict[str, object]], dict[str, object]]:
    original_run_id = "1a111111-1111-4111-8111-111111111111"
    original_start = _run_start(original_run_id)
    opened = _event(
        "blocker_opened", "2a222222-2222-4222-8222-222222222222",
        run_id=original_run_id,
        blocker_id=BLOCKER_ID,
        occurrence_id=OCCURRENCE_ID,
        fingerprint="e" * 64,
        subject_id=SUBJECT_ID,
        lineage_id=LINEAGE_ID,
        step_id="select",
        surface="selection",
        symptom="captured failure",
        evidence="captured evidence",
        impact="verification blocked",
        boundary="same-path verification binding",
        status="open",
    )
    correction = _event(
        "correction_recorded", "3a333333-3333-4333-8333-333333333333",
        run_id=original_run_id,
        blocker_id=BLOCKER_ID,
        occurrence_id=OCCURRENCE_ID,
        correction_id=CORRECTION_ID,
        subject_id=SUBJECT_ID,
        lineage_id=LINEAGE_ID,
        step_id="select",
        changed_artifacts=[ARTIFACT],
        changed_artifact_hashes=[ARTIFACT_HASH],
        reusable_behavior_changed=True,
        solution="corrected selection behavior",
    )
    fixed = _event(
        "blocker_transitioned", "4a444444-4444-4444-8444-444444444444",
        run_id=original_run_id,
        blocker_id=BLOCKER_ID,
        from_status="open",
        to_status="fixed-awaiting-verification",
    )
    original_closed = _event(
        "run_closed", "5a555555-5555-4555-8555-555555555555",
        run_id=original_run_id,
        subject_id=SUBJECT_ID,
        lineage_id=LINEAGE_ID,
        result="failed",
        completed_at_utc="2026-09-12T16:01:00Z",
        correction_count=1,
        blocker_ids=[BLOCKER_ID],
        sequence_updated=True,
        verification_quality="none",
    )
    verification_start = _run_start(
        VERIFICATION_RUN_ID, predecessor_run_id=original_run_id,
    )
    verification = _event(
        "verification_recorded", VERIFICATION_EVENT_ID,
        run_id=VERIFICATION_RUN_ID,
        subject_id=SUBJECT_ID,
        lineage_id=LINEAGE_ID,
        source_bundle_hash=SOURCE_HASH,
        outcome=verification_outcome,
        quality=verification_quality,
        evidence="same-path verification failed",
        blocker_ids=[BLOCKER_ID],
        correction_ids=[CORRECTION_ID],
        changed_artifact_hashes=[ARTIFACT_HASH],
    )
    verification_closed = _event(
        "run_closed", "6a666666-6666-4666-8666-666666666666",
        run_id=VERIFICATION_RUN_ID,
        subject_id=SUBJECT_ID,
        lineage_id=LINEAGE_ID,
        result="failed",
        completed_at_utc="2026-09-12T16:02:00Z",
        correction_count=0,
        blocker_ids=[],
        sequence_updated=False,
        verification_quality=verification_quality,
    )
    reopen_start = _run_start(
        REOPEN_RUN_ID,
        predecessor_run_id=reopen_predecessor,
        source_bundle_hash=reopen_source_hash,
        artifact_hash=reopen_artifact_hash,
    )
    reopen = _event(
        "blocker_transitioned", reopen_event_id,
        run_id=REOPEN_RUN_ID,
        blocker_id=BLOCKER_ID,
        from_status="fixed-awaiting-verification",
        to_status="open",
        verification_event_id=VERIFICATION_EVENT_ID,
        reopen_evidence="same-path verification failed",
    )
    prefix = [
        original_start, opened, correction, fixed, original_closed,
        verification_start, verification, verification_closed, reopen_start,
    ]
    return prefix, reopen


def _ledger_bytes(events: list[dict[str, object]]) -> bytes:
    return b"".join(work_memory.canonical_bytes(event) for event in events)


def test_exact_persisted_historical_reopen_replays() -> None:
    prefix, reopen = _history()

    parsed = work_memory.parse_ledger_bytes(_ledger_bytes([*prefix, reopen]))

    assert parsed[-1]["event_id"] == LEGACY_REOPEN_EVENT_ID
    with pytest.raises(
        work_memory.WorkMemoryError,
        match="invalid-failed-verification-reopen",
    ):
        work_memory.stage_event_batch(
            _ledger_bytes(prefix),
            {"schema_version": 1, "expected_ledger_hash": None, "events": [reopen]},
        )


def test_new_or_unlisted_reopen_remains_ancestry_bound() -> None:
    prefix, reopen = _history(
        reopen_event_id="7a777777-7777-4777-8777-777777777777",
    )

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="invalid-failed-verification-reopen",
    ):
        work_memory.stage_event_batch(
            _ledger_bytes(prefix),
            {"schema_version": 1, "expected_ledger_hash": None, "events": [reopen]},
        )

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="invalid-failed-verification-reopen",
    ):
        work_memory.parse_ledger_bytes(_ledger_bytes([*prefix, reopen]))


@pytest.mark.parametrize(
    ("reopen_source_hash", "reopen_predecessor"),
    [
        ("f" * 64, None),
        (SOURCE_HASH, "7b777777-7777-4777-8777-777777777777"),
    ],
)
def test_legacy_event_does_not_bypass_bundle_or_predecessor_binding(
    reopen_source_hash: str,
    reopen_predecessor: str | None,
) -> None:
    prefix, reopen = _history(
        reopen_source_hash=reopen_source_hash,
        reopen_predecessor=reopen_predecessor,
    )
    if reopen_predecessor is not None:
        prefix.insert(0, _run_start(reopen_predecessor))

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="invalid-failed-verification-reopen",
    ):
        work_memory.parse_ledger_bytes(_ledger_bytes([*prefix, reopen]))


@pytest.mark.parametrize(
    ("verification_outcome", "verification_quality"),
    [("passed", "same-path"), ("failed", "proxy")],
)
def test_legacy_event_still_requires_failed_same_path_verification(
    verification_outcome: str,
    verification_quality: str,
) -> None:
    prefix, reopen = _history(
        verification_outcome=verification_outcome,
        verification_quality=verification_quality,
    )

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="invalid-failed-verification-reopen",
    ):
        work_memory.parse_ledger_bytes(_ledger_bytes([*prefix, reopen]))


def test_ancestor_reopen_still_requires_active_correction_artifacts_preserved() -> None:
    prefix, reopen = _history(
        reopen_source_hash="f" * 64,
        reopen_predecessor=VERIFICATION_RUN_ID,
        reopen_artifact_hash="9" * 64,
    )

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="invalid-failed-verification-reopen",
    ):
        work_memory.parse_ledger_bytes(_ledger_bytes([*prefix, reopen]))


def test_ordinary_merge_rejects_unseen_legacy_event_but_reconciliation_accepts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix, reopen = _history()
    target = tmp_path / "target/events.jsonl"
    source = tmp_path / "source/events.jsonl"
    view = tmp_path / "blockers/BLOCKERS.md"
    target.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    target.write_bytes(_ledger_bytes(prefix))
    source.write_bytes(_ledger_bytes([*prefix, reopen]))
    monkeypatch.setattr(work_memory, "_authorize_event_batch", lambda *_args: None)

    ordinary_args = SimpleNamespace(
        ledger=str(target), view=str(view), source_ledger=str(source),
        reconcile_persisted_source=False,
    )
    with pytest.raises(
        work_memory.WorkMemoryError,
        match="invalid-failed-verification-reopen",
    ):
        work_memory.cmd_merge_ledger(ordinary_args)
    assert target.read_bytes() == _ledger_bytes(prefix)

    reconciliation_args = SimpleNamespace(
        ledger=str(target), view=str(view), source_ledger=str(source),
        reconcile_persisted_source=True,
    )
    result = work_memory.cmd_merge_ledger(reconciliation_args)

    assert result["appended_event_count"] == 1
    assert work_memory.parse_ledger_bytes(target.read_bytes())[-1]["event_id"] == (
        LEGACY_REOPEN_EVENT_ID
    )
