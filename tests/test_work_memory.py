from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import work_memory


def event(kind: str, **fields):
    return {
        "schema_version": 1, "event_id": str(uuid.uuid4()), "event_type": kind,
        "recorded_at_utc": fields.pop("recorded_at_utc", "2026-01-01T00:00:00Z"), **fields,
    }


def run_events(index: int, *, result: str = "passed", duration: int = 10, bundle: str = "a" * 64):
    run_id = str(uuid.uuid4())
    started = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
    start = event(
        "run_started", run_id=run_id, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="other", source_bundle=[], source_bundle_hash=bundle,
        classification_receipt_hash="b" * 64, selection_receipt_hash="c" * 64,
        started_at_utc=started.isoformat(), recorded_at_utc=started.isoformat(),
    )
    verification = event(
        "verification_recorded", run_id=run_id, subject_id="sequence", lineage_id="lineage",
        source_bundle_hash=bundle, outcome=result, quality="same-path", evidence="test passed",
        blocker_ids=[], correction_ids=[], changed_artifact_hashes=[],
        recorded_at_utc=(started + timedelta(seconds=duration - 1)).isoformat(),
    )
    close = event(
        "run_closed", run_id=run_id, subject_id="sequence", lineage_id="lineage", result=result,
        completed_at_utc=(started + timedelta(seconds=duration)).isoformat(), correction_count=0,
        blocker_ids=[], sequence_updated=False, verification_quality="same-path",
        recorded_at_utc=(started + timedelta(seconds=duration)).isoformat(),
    )
    return [start, verification, close]


def test_merge_ledger_appends_source_only_events_through_canonical_writer(tmp_path: Path):
    target_events = run_events(0)
    source_only = run_events(1)
    target = tmp_path / "target.jsonl"
    source = tmp_path / "source.jsonl"
    view = tmp_path / "BLOCKERS.md"
    target.write_bytes(b"".join(work_memory.canonical_bytes(item) for item in target_events))
    source.write_bytes(b"".join(
        work_memory.canonical_bytes(item) for item in target_events + source_only
    ))

    result = work_memory.cmd_merge_ledger(SimpleNamespace(
        source_ledger=str(source), ledger=str(target), view=str(view),
    ))

    merged, _ = work_memory.load_ledger(target)
    assert result["appended_event_count"] == len(source_only)
    assert [item["event_id"] for item in merged] == [
        item["event_id"] for item in target_events + source_only
    ]
    assert not work_memory.blocker_view_stale(result["ledger_hash"], view)


def test_merge_ledger_preserves_bounded_legacy_status_from_valid_source(tmp_path: Path):
    target_events = run_events(0)
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "9" * 24
    source_events = [
        event(
            "run_started", run_id=run_id, subject_id="legacy", lineage_id="legacy-lineage",
            mode="discovery", operation_kind="other", source_bundle=[],
            source_bundle_hash="9" * 64, classification_receipt_hash="8" * 64,
            selection_receipt_hash="7" * 64, started_at_utc="2026-01-02T00:00:00Z",
        ),
        event(
            "blocker_opened", run_id=run_id, blocker_id=blocker_id,
            occurrence_id=str(uuid.uuid4()), fingerprint="6" * 64, subject_id="legacy",
            lineage_id="legacy-lineage", step_id="step", surface="surface",
            symptom="legacy premature status", evidence="persisted before strict correction rule",
            impact="stranded", boundary="historical ledger", status="open",
        ),
        event(
            "blocker_transitioned", run_id=run_id, blocker_id=blocker_id,
            from_status="open", to_status="fixed-awaiting-verification",
        ),
    ]
    target = tmp_path / "target.jsonl"
    source = tmp_path / "source.jsonl"
    view = tmp_path / "BLOCKERS.md"
    target.write_bytes(b"".join(work_memory.canonical_bytes(item) for item in target_events))
    source.write_bytes(b"".join(work_memory.canonical_bytes(item) for item in source_events))

    result = work_memory.cmd_merge_ledger(SimpleNamespace(
        source_ledger=str(source), ledger=str(target), view=str(view),
    ))

    merged, _ = work_memory.load_ledger(target)
    assert result["appended_event_count"] == len(source_events)
    assert merged[-1]["event_id"] == source_events[-1]["event_id"]


def corrected_successor_events():
    run_a, run_b = str(uuid.uuid4()), str(uuid.uuid4())
    occurrence, correction_id = str(uuid.uuid4()), str(uuid.uuid4())
    blocker_id, fingerprint = "blk-" + "1" * 24, "1" * 64
    bundle_a, bundle_b = "a" * 64, "b" * 64
    successor_bundle = [{
        "repository_key": "memory-knowledge",
        "path": "scripts/deploy.sh",
        "sha256": "e" * 64,
    }]
    start_a = event(
        "run_started", run_id=run_a, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="deploy", source_bundle=[], source_bundle_hash=bundle_a,
        classification_receipt_hash="c" * 64, selection_receipt_hash="d" * 64,
        started_at_utc="2026-01-01T00:00:00Z",
    )
    opened = event(
        "blocker_opened", run_id=run_a, blocker_id=blocker_id, occurrence_id=occurrence,
        fingerprint=fingerprint, subject_id="sequence", lineage_id="lineage", step_id="deploy",
        surface="deploy", symptom="failed", evidence="exit 1", impact="blocked",
        boundary="script", status="open",
    )
    correction = event(
        "correction_recorded", run_id=run_a, blocker_id=blocker_id, occurrence_id=occurrence,
        correction_id=correction_id, subject_id="sequence", lineage_id="lineage", step_id="deploy",
        changed_artifacts=["scripts/deploy.sh"], changed_artifact_hashes=["e" * 64],
        reusable_behavior_changed=True, solution="use the corrected flag",
    )
    transition = event(
        "bundle_transition_recorded", lineage_id="lineage", old_bundle_hash=bundle_a,
        new_bundle_hash=bundle_b, transition_reason="correction", run_id=run_a,
        correction_ids=[correction_id], changed_artifacts=["scripts/deploy.sh"],
        changed_artifact_hashes=["e" * 64],
    )
    awaiting = event(
        "blocker_transitioned", run_id=run_a, blocker_id=blocker_id,
        from_status="open", to_status="fixed-awaiting-verification",
    )
    close_a = event(
        "run_closed", run_id=run_a, subject_id="sequence", lineage_id="lineage", result="failed",
        completed_at_utc="2026-01-01T00:01:00Z", correction_count=1,
        blocker_ids=[blocker_id], sequence_updated=True, verification_quality="none",
    )
    start_b = event(
        "run_started", run_id=run_b, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="deploy",
        source_bundle=successor_bundle,
        source_bundle_hash=bundle_b,
        classification_receipt_hash="f" * 64, selection_receipt_hash="0" * 64,
        started_at_utc="2026-01-01T00:02:00Z", predecessor_run_id=run_a,
        verifies_correction_ids=[correction_id],
    )
    verification = event(
        "verification_recorded", run_id=run_b, subject_id="sequence", lineage_id="lineage",
        source_bundle_hash=bundle_b, outcome="passed", quality="same-path", evidence="same path passed",
        blocker_ids=[blocker_id], correction_ids=[correction_id],
        changed_artifact_hashes=["e" * 64],
    )
    verified = event(
        "blocker_transitioned", run_id=run_b, blocker_id=blocker_id,
        from_status="fixed-awaiting-verification", to_status="verified",
        verification_event_id=verification["event_id"],
    )
    closed = event(
        "blocker_transitioned", run_id=run_b, blocker_id=blocker_id,
        from_status="verified", to_status="closed", verification_event_id=verification["event_id"],
        remaining_work="none",
    )
    close_b = event(
        "run_closed", run_id=run_b, subject_id="sequence", lineage_id="lineage", result="passed",
        completed_at_utc="2026-01-01T00:03:00Z", correction_count=0,
        blocker_ids=[blocker_id], sequence_updated=False, verification_quality="same-path",
    )
    return [start_a, opened, correction, transition, awaiting, close_a,
            start_b, verification, verified, closed, close_b]


def test_finalize_correction_is_one_atomic_idempotent_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sequence = tmp_path / "operations/sequences/example/sequence.md"
    sequence.parent.mkdir(parents=True)
    sequence.write_text("# example\n")
    artifact = tmp_path / "scripts/fix.py"
    artifact.parent.mkdir()
    artifact.write_text("fixed = True\n")
    run_id = str(uuid.uuid4())
    occurrence_id = str(uuid.uuid4())
    correction_id = str(uuid.uuid4())
    blocker_id = "blk-" + "7" * 24
    start = event(
        "run_started", run_id=run_id, subject_id="example", lineage_id="lineage",
        mode="registered", operation_kind="workflow-drive",
        source_bundle=[{
            "repository_key": "memory-knowledge",
            "path": "operations/sequences/example/sequence.md", "sha256": "a" * 64,
        }], source_bundle_hash="a" * 64,
        classification_receipt_hash="b" * 64, selection_receipt_hash="c" * 64,
        started_at_utc="2026-01-01T00:00:00Z",
    )
    opened = event(
        "blocker_opened", run_id=run_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, fingerprint="7" * 64, subject_id="example",
        lineage_id="lineage", step_id="review", surface="lifecycle", symptom="gap",
        evidence="review", impact="blocked", boundary="controller", status="open",
    )
    current = [start, opened]
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "load_ledger", lambda: (current, "a" * 64))
    new_bundle = [
        start["source_bundle"][0],
        {
            "repository_key": "memory-knowledge", "path": "scripts/fix.py",
            "sha256": work_memory.sha256_bytes(artifact.read_bytes()),
        },
    ]
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: (new_bundle, "d" * 64, "lineage"),
    )
    calls = []

    def transact(request):
        calls.append(request)
        raw = b"".join(work_memory.canonical_bytes(item) for item in current)
        ledger, _, result = work_memory.stage_event_batch(raw, request)
        current[:] = work_memory.parse_ledger_bytes(ledger)
        return result

    monkeypatch.setattr(work_memory, "transact", transact)
    args = SimpleNamespace(
        run_id=run_id, blocker_id=blocker_id, occurrence_id=occurrence_id,
        step_id="review", changed_artifact=[str(artifact)], solution="stable fix",
        reusable_behavior_changed="yes", supersedes_correction_id=None,
        correction_id=correction_id, event_id=None, transition_event_id=None,
        repo_roots_file=None, finalize_failed_run=True,
    )

    first = work_memory.cmd_correct(args)
    second = work_memory.cmd_correct(args)

    assert [item["event_type"] for item in calls[0]["events"]] == [
        "correction_recorded", "bundle_transition_recorded",
        "blocker_transitioned", "run_closed",
    ]
    assert len(calls) == 1
    assert first["correction_id"] == second["correction_id"] == correction_id
    assert second["already_recorded"] is True


def test_finalize_correction_preserves_existing_verification_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sequence = tmp_path / "operations/sequences/example/sequence.md"
    sequence.parent.mkdir(parents=True)
    sequence.write_text("# example\n")
    artifact = tmp_path / "scripts/fix.py"
    artifact.parent.mkdir()
    artifact.write_text("fixed = True\n")
    run_id, occurrence_id = str(uuid.uuid4()), str(uuid.uuid4())
    blocker_id = "blk-" + "6" * 24
    start = event(
        "run_started", run_id=run_id, subject_id="example", lineage_id="lineage",
        mode="registered", operation_kind="workflow-drive",
        source_bundle=[{
            "repository_key": "memory-knowledge",
            "path": "operations/sequences/example/sequence.md", "sha256": "a" * 64,
        }], source_bundle_hash="a" * 64,
        classification_receipt_hash="b" * 64, selection_receipt_hash="c" * 64,
        started_at_utc="2026-01-01T00:00:00Z",
    )
    verification = event(
        "verification_recorded", run_id=run_id, subject_id="example",
        lineage_id="lineage", source_bundle_hash="a" * 64, outcome="passed",
        quality="same-path", evidence="earlier correction verified",
        blocker_ids=[], correction_ids=[], changed_artifact_hashes=[],
    )
    opened = event(
        "blocker_opened", run_id=run_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, fingerprint="6" * 64, subject_id="example",
        lineage_id="lineage", step_id="review", surface="lifecycle", symptom="gap",
        evidence="review", impact="blocked", boundary="controller", status="open",
    )
    current = [start, verification, opened]
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "load_ledger", lambda: (current, "a" * 64))
    new_bundle = [
        start["source_bundle"][0],
        {
            "repository_key": "memory-knowledge", "path": "scripts/fix.py",
            "sha256": work_memory.sha256_bytes(artifact.read_bytes()),
        },
    ]
    monkeypatch.setattr(
        work_memory, "resolve_bundle", lambda **kwargs: (new_bundle, "d" * 64, "lineage"),
    )
    captured = {}
    monkeypatch.setattr(
        work_memory, "transact",
        lambda request: captured.update(request=request) or {"ok": True},
    )

    work_memory.cmd_correct(SimpleNamespace(
        run_id=run_id, blocker_id=blocker_id, occurrence_id=occurrence_id,
        step_id="review", changed_artifact=[str(artifact)], solution="stable fix",
        reusable_behavior_changed="yes", supersedes_correction_id=None,
        correction_id=str(uuid.uuid4()), event_id=None, transition_event_id=None,
        repo_roots_file=None, finalize_failed_run=True,
    ))

    close = captured["request"]["events"][-1]
    assert close["event_type"] == "run_closed"
    assert close["verification_quality"] == "same-path"


def test_correction_rejects_manifest_that_does_not_exhaust_bundle_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = tmp_path / "operations/sequences/example/sequence.md"
    document.parent.mkdir(parents=True)
    document.write_text("# example\n")
    run_id = str(uuid.uuid4())
    occurrence_id = str(uuid.uuid4())
    blocker_id = "blk-" + "8" * 24
    old_bundle = [
        {"repository_key": "memory-knowledge", "path": "operations/sequences/example/sequence.md", "sha256": "a" * 64},
        {"repository_key": "memory-knowledge", "path": "scripts/one.py", "sha256": "b" * 64},
        {"repository_key": "memory-knowledge", "path": "scripts/two.py", "sha256": "c" * 64},
    ]
    rows = [
        event(
            "run_started", run_id=run_id, subject_id="example", lineage_id="lineage",
            mode="registered", operation_kind="workflow-drive", source_bundle=old_bundle,
            source_bundle_hash="d" * 64, classification_receipt_hash="e" * 64,
            selection_receipt_hash="f" * 64, started_at_utc="2026-01-01T00:00:00Z",
        ),
        event(
            "blocker_opened", run_id=run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, fingerprint="8" * 64, subject_id="example",
            lineage_id="lineage", step_id="review", surface="lifecycle", symptom="gap",
            evidence="review", impact="blocked", boundary="controller", status="open",
        ),
    ]
    new_bundle = [
        old_bundle[0],
        {**old_bundle[1], "sha256": "1" * 64},
        {**old_bundle[2], "sha256": "2" * 64},
    ]
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "load_ledger", lambda: (rows, "a" * 64))
    monkeypatch.setattr(
        work_memory, "_artifact_hashes", lambda *args, **kwargs: (["scripts/one.py"], ["1" * 64]),
    )
    monkeypatch.setattr(
        work_memory, "resolve_bundle", lambda **kwargs: (new_bundle, "9" * 64, "lineage"),
    )
    monkeypatch.setattr(
        work_memory, "transact", lambda request: pytest.fail("partial drift must not transact"),
    )
    args = SimpleNamespace(
        run_id=run_id, blocker_id=blocker_id, occurrence_id=occurrence_id,
        step_id="review", changed_artifact=["scripts/one.py"], solution="partial fix",
        reusable_behavior_changed="yes", supersedes_correction_id=None,
        correction_id=str(uuid.uuid4()), event_id=None, transition_event_id=None,
        repo_roots_file=None, finalize_failed_run=True,
    )

    with pytest.raises(work_memory.WorkMemoryError, match="correction-artifact-drift-mismatch"):
        work_memory.cmd_correct(args)


def test_successor_rejects_bundle_drift_after_recorded_correction() -> None:
    rows = corrected_successor_events()[:6]
    correction = next(item for item in rows if item["event_type"] == "correction_recorded")
    changed_bundle = [{
        "repository_key": "memory-knowledge", "path": "scripts/deploy.sh", "sha256": "f" * 64,
    }]

    with pytest.raises(work_memory.WorkMemoryError, match="successor-correction-bundle-mismatch"):
        work_memory._validate_successor_corrections(
            rows, lineage_id="lineage", source_bundle=changed_bundle,
            predecessor_run_id=rows[0]["run_id"],
            correction_ids=[correction["correction_id"]],
        )


def test_cross_repository_correction_identity_survives_successor_validation(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    artifact = external / "scripts/fix.py"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("fixed = True\n")
    roots_file = tmp_path / "roots.json"
    roots_file.write_text(json.dumps({"external": str(external)}))
    artifacts, hashes = work_memory._artifact_hashes([str(artifact)], str(roots_file))
    rows = corrected_successor_events()[:6]
    correction = next(item for item in rows if item["event_type"] == "correction_recorded")
    correction["changed_artifacts"] = artifacts
    correction["changed_artifact_hashes"] = hashes
    transition = next(item for item in rows if item["event_type"] == "bundle_transition_recorded")
    transition["changed_artifacts"] = artifacts
    transition["changed_artifact_hashes"] = hashes
    source_bundle = [{
        "repository_key": "external", "path": "scripts/fix.py", "sha256": hashes[0],
    }]
    transition["new_bundle_hash"] = work_memory.sha256_bytes(
        work_memory.canonical_bytes(source_bundle)
    )

    work_memory._validate_successor_corrections(
        rows, lineage_id="lineage",
        source_bundle=source_bundle, predecessor_run_id=rows[0]["run_id"],
        correction_ids=[correction["correction_id"]], repo_roots_file=str(roots_file),
    )

    assert artifacts == [{"repository_key": "external", "path": "scripts/fix.py"}]


def legacy_stranded_events(*, terminal: bool) -> list[dict]:
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "9" * 24
    occurrence_id = str(uuid.uuid4())
    start = event(
        "run_started", run_id=run_id, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="deploy", source_bundle=[],
        source_bundle_hash="a" * 64, classification_receipt_hash="b" * 64,
        selection_receipt_hash="c" * 64, started_at_utc="2026-01-01T00:00:00Z",
    )
    opened = event(
        "blocker_opened", run_id=run_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, fingerprint="9" * 64, subject_id="sequence",
        lineage_id="lineage", step_id="deploy", surface="deploy", symptom="failed",
        evidence="exit 1", impact="blocked", boundary="script", status="open",
    )
    premature_fixed = event(
        "blocker_transitioned", run_id=run_id, blocker_id=blocker_id,
        from_status="open", to_status="fixed-awaiting-verification",
    )
    events = [start, opened, premature_fixed]
    if terminal:
        events.append(event(
            "run_closed", run_id=run_id, subject_id="sequence", lineage_id="lineage",
            result="failed", completed_at_utc="2026-01-01T00:01:00Z",
            correction_count=0, blocker_ids=[blocker_id], sequence_updated=False,
            verification_quality="none",
        ))
    return events


def test_stage_batch_is_atomic_and_exact_retry_is_idempotent():
    events = run_events(0)
    request = {"schema_version": 1, "expected_ledger_hash": work_memory.sha256_bytes(b""), "events": events}
    ledger, view, first = work_memory.stage_event_batch(b"", request)
    retry = {"schema_version": 1, "expected_ledger_hash": work_memory.sha256_bytes(ledger), "events": events}
    ledger2, view2, second = work_memory.stage_event_batch(ledger, retry)
    assert ledger2 == ledger and view2 == view
    assert second["idempotent_event_ids"] == [item["event_id"] for item in events]
    assert first["ledger_hash"] == work_memory.sha256_bytes(ledger)


def test_event_id_collision_rejects_without_output():
    events = run_events(0)
    ledger, _, _ = work_memory.stage_event_batch(
        b"", {"schema_version": 1, "expected_ledger_hash": work_memory.sha256_bytes(b""), "events": events}
    )
    conflict = dict(events[0]); conflict["operation_kind"] = "deploy"
    with pytest.raises(work_memory.WorkMemoryError, match="event-id-conflict"):
        work_memory.stage_event_batch(
            ledger, {"schema_version": 1, "expected_ledger_hash": None, "events": [conflict]}
        )


def test_closed_schema_rejects_unknown_and_personal_fields():
    bad = run_events(0)[0]; bad["diary"] = "today"
    with pytest.raises(work_memory.WorkMemoryError, match="unknown-event-fields"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": [bad]}
        )


def test_event_after_terminal_fails():
    events = run_events(0)
    events.append(event(
        "verification_recorded", run_id=events[0]["run_id"], subject_id="sequence",
        lineage_id="lineage", source_bundle_hash="a" * 64, outcome="passed", quality="same-path",
        evidence="late", blocker_ids=[], correction_ids=[], changed_artifact_hashes=[],
    ))
    with pytest.raises(work_memory.WorkMemoryError, match="event-after-terminal"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events}
        )


def test_fixed_transition_requires_correction_for_current_occurrence():
    events = corrected_successor_events()
    run_id = str(uuid.uuid4())
    blocker_id = events[1]["blocker_id"]
    events.extend([
        event(
            "run_started", run_id=run_id, subject_id="sequence", lineage_id="lineage",
            mode="registered", operation_kind="deploy", source_bundle=[],
            source_bundle_hash="b" * 64, classification_receipt_hash="1" * 64,
            selection_receipt_hash="2" * 64, started_at_utc="2026-01-01T00:04:00Z",
        ),
        event(
            "blocker_recurred", run_id=run_id, blocker_id=blocker_id,
            occurrence_id=str(uuid.uuid4()), previous_status="closed", status="open",
            evidence="same failure recurred",
        ),
        event(
            "blocker_transitioned", run_id=run_id, blocker_id=blocker_id,
            from_status="open", to_status="fixed-awaiting-verification",
        ),
    ])

    with pytest.raises(work_memory.WorkMemoryError, match="blocker-correction-required"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events}
        )


def test_legacy_stranded_blocker_recovers_then_completes_normal_lifecycle():
    legacy = legacy_stranded_events(terminal=True)
    legacy_bytes = b"".join(work_memory.canonical_bytes(item) for item in legacy)
    old_run_id = legacy[0]["run_id"]
    blocker_id = legacy[1]["blocker_id"]
    occurrence_id = legacy[1]["occurrence_id"]
    recovery_run_id, successor_run_id = str(uuid.uuid4()), str(uuid.uuid4())
    correction_id = str(uuid.uuid4())
    recovery_run = event(
        "run_started", run_id=recovery_run_id, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="deploy", source_bundle=[],
        source_bundle_hash="a" * 64, classification_receipt_hash="3" * 64,
        selection_receipt_hash="4" * 64, started_at_utc="2026-01-01T00:02:00Z",
    )
    recovered = event(
        "blocker_transitioned", run_id=recovery_run_id, blocker_id=blocker_id,
        from_status="fixed-awaiting-verification", to_status="open",
        recovery_evidence="captured legacy event has no correction",
    )
    correction = event(
        "correction_recorded", run_id=recovery_run_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, correction_id=correction_id, subject_id="sequence",
        lineage_id="lineage", step_id="deploy", changed_artifacts=["scripts/deploy.sh"],
        changed_artifact_hashes=["e" * 64], reusable_behavior_changed=True,
        solution="use the corrected flag",
    )
    bundle_transition = event(
        "bundle_transition_recorded", lineage_id="lineage", old_bundle_hash="a" * 64,
        new_bundle_hash="b" * 64, transition_reason="correction", run_id=recovery_run_id,
        correction_ids=[correction_id], changed_artifacts=["scripts/deploy.sh"],
        changed_artifact_hashes=["e" * 64],
    )
    awaiting = event(
        "blocker_transitioned", run_id=recovery_run_id, blocker_id=blocker_id,
        from_status="open", to_status="fixed-awaiting-verification",
    )
    recovery_close = event(
        "run_closed", run_id=recovery_run_id, subject_id="sequence", lineage_id="lineage",
        result="failed", completed_at_utc="2026-01-01T00:03:00Z", correction_count=1,
        blocker_ids=[blocker_id], sequence_updated=True, verification_quality="none",
    )
    successor = event(
        "run_started", run_id=successor_run_id, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="deploy", source_bundle=[{
            "repository_key": "memory-knowledge",
            "path": "scripts/deploy.sh",
            "sha256": "e" * 64,
        }],
        source_bundle_hash="b" * 64, classification_receipt_hash="5" * 64,
        selection_receipt_hash="6" * 64, started_at_utc="2026-01-01T00:04:00Z",
        predecessor_run_id=recovery_run_id, verifies_correction_ids=[correction_id],
    )
    verification = event(
        "verification_recorded", run_id=successor_run_id, subject_id="sequence",
        lineage_id="lineage", source_bundle_hash="b" * 64, outcome="passed",
        quality="same-path", evidence="same path passed", blocker_ids=[blocker_id],
        correction_ids=[correction_id], changed_artifact_hashes=["e" * 64],
    )
    verified = event(
        "blocker_transitioned", run_id=successor_run_id, blocker_id=blocker_id,
        from_status="fixed-awaiting-verification", to_status="verified",
        verification_event_id=verification["event_id"],
    )
    closed = event(
        "blocker_transitioned", run_id=successor_run_id, blocker_id=blocker_id,
        from_status="verified", to_status="closed",
        verification_event_id=verification["event_id"], remaining_work="none",
    )
    successor_close = event(
        "run_closed", run_id=successor_run_id, subject_id="sequence", lineage_id="lineage",
        result="passed", completed_at_utc="2026-01-01T00:05:00Z", correction_count=0,
        blocker_ids=[blocker_id], sequence_updated=False, verification_quality="same-path",
    )
    additions = [
        recovery_run, recovered, correction, bundle_transition, awaiting, recovery_close,
        successor, verification, verified, closed, successor_close,
    ]

    ledger, _, _ = work_memory.stage_event_batch(
        legacy_bytes,
        {"schema_version": 1, "expected_ledger_hash": None, "events": additions},
    )

    parsed = work_memory.parse_ledger_bytes(ledger)
    assert old_run_id == parsed[0]["run_id"]
    assert [
        item["to_status"] for item in parsed
        if item["event_type"] == "blocker_transitioned" and item["blocker_id"] == blocker_id
    ] == ["fixed-awaiting-verification", "open", "fixed-awaiting-verification", "verified", "closed"]


def test_normally_corrected_fixed_blocker_cannot_recover_with_evidence():
    events = corrected_successor_events()
    awaiting = events[4]
    recovery = event(
        "blocker_transitioned", run_id=awaiting["run_id"], blocker_id=awaiting["blocker_id"],
        from_status="fixed-awaiting-verification", to_status="open",
        recovery_evidence="operator supplied evidence cannot override lifecycle provenance",
    )
    events.insert(5, recovery)

    with pytest.raises(work_memory.WorkMemoryError, match="recovery-source-not-legacy-stranded"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events}
        )


def test_later_correction_can_explicitly_supersede_multiple_fixed_corrections():
    run_id = str(uuid.uuid4())
    events = [event(
        "run_started", run_id=run_id, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="other", source_bundle=[],
        source_bundle_hash="a" * 64, classification_receipt_hash="b" * 64,
        selection_receipt_hash="c" * 64, started_at_utc="2026-01-01T00:00:00Z",
    )]
    prior: list[tuple[str, str]] = []
    for index in range(3):
        blocker_id = f"blk-{index + 1:024d}"
        occurrence_id = str(uuid.uuid4())
        correction_id = str(uuid.uuid4())
        prior.append((blocker_id, correction_id))
        events.extend([
            event(
                "blocker_opened", run_id=run_id, blocker_id=blocker_id,
                occurrence_id=occurrence_id, fingerprint=f"{index + 1}" * 64,
                subject_id="sequence", lineage_id="lineage", step_id=f"step-{index}",
                surface="sequence", symptom="stale revision", evidence="hash mismatch",
                impact="cannot select successor", boundary="correction schema", status="open",
            ),
            event(
                "correction_recorded", run_id=run_id, blocker_id=blocker_id,
                occurrence_id=occurrence_id, correction_id=correction_id,
                subject_id="sequence", lineage_id="lineage", step_id=f"step-{index}",
                changed_artifacts=["operations/sequence.md"],
                changed_artifact_hashes=[f"{index + 1:x}" * 64],
                reusable_behavior_changed=True, solution=f"revision {index}",
            ),
            event(
                "blocker_transitioned", run_id=run_id, blocker_id=blocker_id,
                from_status="open", to_status="fixed-awaiting-verification",
            ),
        ])

    final_blocker = "blk-" + "9" * 24
    final_occurrence = str(uuid.uuid4())
    final_correction = str(uuid.uuid4())
    events.extend([
        event(
            "blocker_opened", run_id=run_id, blocker_id=final_blocker,
            occurrence_id=final_occurrence, fingerprint="9" * 64,
            subject_id="sequence", lineage_id="lineage", step_id="final",
            surface="sequence", symptom="latest revision", evidence="all behavior preserved",
            impact="needs one active correction", boundary="correction schema", status="open",
        ),
        event(
            "correction_recorded", run_id=run_id, blocker_id=final_blocker,
            occurrence_id=final_occurrence, correction_id=final_correction,
            subject_id="sequence", lineage_id="lineage", step_id="final",
            changed_artifacts=["operations/sequence.md"],
            changed_artifact_hashes=["f" * 64], reusable_behavior_changed=True,
            solution="one final preserving revision",
            supersedes_correction_ids=[correction_id for _, correction_id in prior],
        ),
    ])
    for blocker_id, _ in prior:
        events.append(event(
            "blocker_transitioned", run_id=run_id, blocker_id=blocker_id,
            from_status="fixed-awaiting-verification", to_status="superseded",
            supersession_evidence="final correction explicitly replaces this revision",
        ))

    ledger, _, _ = work_memory.stage_event_batch(
        b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events}
    )
    parsed = work_memory.parse_ledger_bytes(ledger)
    final = next(
        item for item in parsed
        if item["event_type"] == "correction_recorded"
        and item["correction_id"] == final_correction
    )
    assert set(final["supersedes_correction_ids"]) == {
        correction_id for _, correction_id in prior
    }


def test_multi_correction_supersession_rejects_duplicate_ids():
    correction_id = str(uuid.uuid4())
    correction = event(
        "correction_recorded", run_id=str(uuid.uuid4()),
        blocker_id="blk-" + "1" * 24, occurrence_id=str(uuid.uuid4()),
        correction_id=str(uuid.uuid4()), subject_id="sequence", lineage_id="lineage",
        step_id="step", changed_artifacts=["operations/sequence.md"],
        changed_artifact_hashes=["a" * 64], reusable_behavior_changed=True,
        solution="invalid duplicate", supersedes_correction_ids=[correction_id, correction_id],
    )
    with pytest.raises(
        work_memory.WorkMemoryError, match="duplicate-superseded-correction-id"
    ):
        work_memory._validate_event_shape(correction)


def test_direct_correction_while_legacy_blocker_is_fixed_remains_rejected():
    legacy = legacy_stranded_events(terminal=False)
    correction = event(
        "correction_recorded", run_id=legacy[0]["run_id"], blocker_id=legacy[1]["blocker_id"],
        occurrence_id=legacy[1]["occurrence_id"], correction_id=str(uuid.uuid4()),
        subject_id="sequence", lineage_id="lineage", step_id="deploy",
        changed_artifacts=["scripts/deploy.sh"], changed_artifact_hashes=["e" * 64],
        reusable_behavior_changed=True, solution="use the corrected flag",
    )
    legacy_bytes = b"".join(work_memory.canonical_bytes(item) for item in legacy)

    with pytest.raises(work_memory.WorkMemoryError, match="correction-for-nonopen-blocker"):
        work_memory.stage_event_batch(
            legacy_bytes,
            {"schema_version": 1, "expected_ledger_hash": None, "events": [correction]},
        )


@pytest.mark.parametrize("recovery_evidence", [None, "", "   "])
def test_recovery_requires_nonempty_evidence(recovery_evidence):
    legacy = legacy_stranded_events(terminal=False)
    fields = {
        "run_id": legacy[0]["run_id"], "blocker_id": legacy[1]["blocker_id"],
        "from_status": "fixed-awaiting-verification", "to_status": "open",
    }
    if recovery_evidence is not None:
        fields["recovery_evidence"] = recovery_evidence
    recovery = event("blocker_transitioned", **fields)
    legacy_bytes = b"".join(work_memory.canonical_bytes(item) for item in legacy)

    with pytest.raises(work_memory.WorkMemoryError, match="invalid-blocker-transition-fields|reopen-evidence-required"):
        work_memory.stage_event_batch(
            legacy_bytes,
            {"schema_version": 1, "expected_ledger_hash": None, "events": [recovery]},
        )


def test_recovery_does_not_enable_unrelated_invalid_transition():
    legacy = legacy_stranded_events(terminal=False)
    invalid = event(
        "blocker_transitioned", run_id=legacy[0]["run_id"], blocker_id=legacy[1]["blocker_id"],
        from_status="fixed-awaiting-verification", to_status="superseded",
        supersession_evidence="another blocker owns this failure",
    )
    legacy_bytes = b"".join(work_memory.canonical_bytes(item) for item in legacy)

    with pytest.raises(
        work_memory.WorkMemoryError, match="blocker-correction-not-superseded"
    ):
        work_memory.stage_event_batch(
            legacy_bytes,
            {"schema_version": 1, "expected_ledger_hash": None, "events": [invalid]},
        )


def test_only_exact_same_path_successor_can_close_blocker():
    valid = corrected_successor_events()
    work_memory.stage_event_batch(
        b"", {"schema_version": 1, "expected_ledger_hash": None, "events": valid}
    )
    unrelated = run_events(9)
    forged = valid[:8] + unrelated[:-1]
    forged_verification = unrelated[1]
    forged.extend([
        {**valid[8], "event_id": str(uuid.uuid4()), "run_id": unrelated[0]["run_id"],
         "verification_event_id": forged_verification["event_id"]},
    ])
    with pytest.raises(work_memory.WorkMemoryError, match="invalid-transition-verification"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": forged}
        )


def test_one_successor_verification_can_close_two_corrected_blockers():
    base = corrected_successor_events()
    start_a, opened_a, correction_a, transition_a, awaiting_a, close_a = base[:6]
    start_b, verification, verified_a, closed_a, close_b = base[6:]
    blocker_b = "blk-" + "2" * 24
    occurrence_b, correction_b_id = str(uuid.uuid4()), str(uuid.uuid4())
    opened_b = {
        **opened_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
        "occurrence_id": occurrence_b, "fingerprint": "2" * 64,
    }
    correction_b = {
        **correction_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
        "occurrence_id": occurrence_b, "correction_id": correction_b_id,
    }
    transition_b = {
        **transition_a, "event_id": str(uuid.uuid4()), "correction_ids": [correction_b_id],
    }
    awaiting_b = {
        **awaiting_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
    }
    verification = {
        **verification,
        "blocker_ids": [opened_a["blocker_id"], blocker_b],
        "correction_ids": [correction_a["correction_id"], correction_b_id],
        "changed_artifact_hashes": ["e" * 64, "e" * 64],
    }
    start_b = {
        **start_b,
        "verifies_correction_ids": [correction_a["correction_id"], correction_b_id],
    }
    verified_b = {
        **verified_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
        "verification_event_id": verification["event_id"],
    }
    closed_b = {
        **closed_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
        "verification_event_id": verification["event_id"],
    }
    close_a = {**close_a, "correction_count": 2, "blocker_ids": [opened_a["blocker_id"], blocker_b]}
    close_b = {**close_b, "blocker_ids": [opened_a["blocker_id"], blocker_b]}

    events = [
        start_a, opened_a, correction_a, transition_a, awaiting_a,
        opened_b, correction_b, transition_b, awaiting_b, close_a,
        start_b, verification, verified_a, closed_a, verified_b, closed_b, close_b,
    ]
    work_memory.stage_event_batch(
        b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events}
    )


def test_carried_correction_can_verify_after_an_intermediate_run() -> None:
    events = corrected_successor_events()
    successor = next(item for item in events if item["event_type"] == "run_started" and "predecessor_run_id" in item)
    successor["predecessor_run_id"] = str(uuid.uuid4())

    work_memory.stage_event_batch(
        b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events}
    )


@pytest.mark.parametrize("value", [
    "Bearer abcdefghijklmnopqrstuvwxyz",
    "Bearer%20abcdefghijklmnopqrstuvwxyz",
    "Kamen prefers tea",
])
def test_work_only_event_validator_rejects_secret_and_personal_text(value):
    item = run_events(0)[1]; item["evidence"] = value
    with pytest.raises(work_memory.WorkMemoryError, match="prohibited"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": run_events(0)[:1] + [item]}
        )


def test_transact_commits_ledger_and_generated_view(tmp_path: Path):
    ledger, view = tmp_path / "events.jsonl", tmp_path / "BLOCKERS.md"
    result = work_memory.transact(
        {"schema_version": 1, "expected_ledger_hash": None, "events": run_events(0)}, ledger, view
    )
    assert result["ledger_hash"] == work_memory.sha256_bytes(ledger.read_bytes())
    assert f"Ledger-SHA256: `{result['ledger_hash']}`" in view.read_text()


def test_malformed_ledger_reports_line_number():
    with pytest.raises(work_memory.WorkMemoryError, match="malformed-ledger-line:2"):
        work_memory.parse_ledger_bytes(b'\nnot-json\n')


def test_summary_uses_six_run_equal_windows():
    events = []
    for index in range(6):
        events.extend(run_events(index, duration=30 if index < 3 else 10))
    summary = work_memory.summarize(events, "sequence", "a" * 64)
    assert summary["history_status"] == "sufficient"
    assert summary["trend"]["speed_status"] == "improved"
    assert summary["metrics"]["pass_rate"] == [6, 6]


def test_summary_counts_abandoned_runs_with_active_records_present():
    active = run_events(0)[0]
    abandoned = run_events(1)[0]
    abandoned_close = event(
        "run_abandoned",
        run_id=abandoned["run_id"],
        subject_id="sequence",
        lineage_id="lineage",
    )

    summary = work_memory.summarize([active, abandoned, abandoned_close], "sequence")

    assert summary["abandoned_runs"] == 1


def test_recurrence_counts_as_repeated_blocker():
    first, second = run_events(0), run_events(1)
    blocker_id = "blk-" + "2" * 24
    first.insert(1, {"event_type": "blocker_opened", "run_id": first[0]["run_id"], "blocker_id": blocker_id,
                     "fingerprint": "2" * 64})
    second.insert(1, {"event_type": "blocker_recurred", "run_id": second[0]["run_id"], "blocker_id": blocker_id})
    summary = work_memory.summarize(first + second, "sequence", "a" * 64)
    assert summary["metrics"]["repeated_blocker_count"] == 1


def test_change_effect_keeps_operation_kinds_isolated():
    events = corrected_successor_events()
    for index, bundle in ((-2, "a" * 64), (-1, "a" * 64), (4, "b" * 64), (5, "b" * 64)):
        records = run_events(index, bundle=bundle)
        records[0]["operation_kind"] = "deploy"
        events.extend(records)
    for index, bundle in ((-5, "a" * 64), (-4, "a" * 64), (-3, "a" * 64),
                          (6, "b" * 64), (7, "b" * 64), (8, "b" * 64)):
        records = run_events(index, bundle=bundle)
        records[0]["operation_kind"] = "database"
        events.extend(records)
    effect = work_memory.summarize(events, "sequence")["change_effects"][0]
    assert effect["status"] == "sufficient"
    assert effect["comparison"]["before"]["closed_runs"] == 3
    assert effect["comparison"]["after"]["closed_runs"] == 3


def test_classification_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    from argparse import Namespace
    nonop = work_memory.cmd_classify(Namespace(
        task_id="one", operation_kind="single-test", repeatable="no", meaningful_steps=1,
    ))
    operational = work_memory.cmd_classify(Namespace(
        task_id="two", operation_kind="single-test", repeatable="yes", meaningful_steps=1,
    ))
    assert nonop["verdict"] == "non-operational"
    assert operational["verdict"] == "operational"


def test_selection_uses_verified_fingerprint_correction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from argparse import Namespace

    events = corrected_successor_events()
    fingerprint = next(item["fingerprint"] for item in events if item["event_type"] == "blocker_opened")
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([{
        "sequence_id": "sequence", "folder": "operations/sequences/sequence/",
        "operation_kinds": "deploy", "lineage_id": "lineage",
    }], "9" * 64))
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: ([], "b" * 64, "lineage"),
    )
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: (events, "8" * 64))
    work_memory.cmd_classify(Namespace(
        task_id="selection", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))
    selected = work_memory.cmd_select(Namespace(
        task_id="selection", sequence_id=None, discovery_log=None, fingerprint=fingerprint,
        verification_successor_of=None, verifies_correction_id=None, repo_roots_file=None,
    ))
    assert selected["selection_reason"] == "fingerprint-link"
    assert selected["eligible_corrections"][0]["solution"] == "use the corrected flag"
    assert selected["recent_run_ids"][0] == events[6]["run_id"]


def _prepare_successor_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, include_artifact: bool = True,
):
    from argparse import Namespace

    artifact = tmp_path / "scripts/deploy.sh"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("corrected\n")
    artifact_hash = work_memory.sha256_bytes(artifact.read_bytes())
    events = corrected_successor_events()[:6]
    correction = next(item for item in events if item["event_type"] == "correction_recorded")
    correction["changed_artifact_hashes"] = [artifact_hash]
    transition = next(item for item in events if item["event_type"] == "bundle_transition_recorded")
    transition["changed_artifact_hashes"] = [artifact_hash]
    bundle = ([{
        "repository_key": "memory-knowledge", "path": "scripts/deploy.sh",
        "sha256": artifact_hash,
    }] if include_artifact else [])

    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path / "receipts")
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([{
        "sequence_id": "sequence", "folder": "operations/sequences/sequence/",
        "operation_kinds": "deploy", "lineage_id": "lineage",
    }], "9" * 64))
    monkeypatch.setattr(
        work_memory, "resolve_bundle", lambda **kwargs: (bundle, "b" * 64, "lineage"),
    )
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: (events, "8" * 64))
    work_memory.cmd_classify(Namespace(
        task_id="successor", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))
    return Namespace, events, artifact, correction["correction_id"]


def test_successor_selection_carries_active_correction_after_intermediate_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    Namespace, events, _, correction_id = _prepare_successor_selection(tmp_path, monkeypatch)
    intermediate_run_id = str(uuid.uuid4())
    events.extend([
        event(
            "run_started", run_id=intermediate_run_id, subject_id="sequence", lineage_id="lineage",
            mode="registered", operation_kind="deploy", source_bundle=[], source_bundle_hash="b" * 64,
            classification_receipt_hash="1" * 64, selection_receipt_hash="2" * 64,
            started_at_utc="2026-01-01T00:03:00Z",
        ),
        event(
            "run_closed", run_id=intermediate_run_id, subject_id="sequence", lineage_id="lineage",
            result="failed", completed_at_utc="2026-01-01T00:04:00Z", correction_count=0,
            blocker_ids=[], sequence_updated=False, verification_quality="none",
        ),
    ])

    selected = work_memory.cmd_select(Namespace(
        task_id="successor", sequence_id="sequence", discovery_log=None, fingerprint=None,
        verification_successor_of=intermediate_run_id,
        verifies_correction_id=[correction_id], repo_roots_file=None,
    ))

    assert selected["predecessor_run_id"] == intermediate_run_id
    assert selected["verifies_correction_ids"] == [correction_id]


def test_successor_selection_rejects_current_raw_artifact_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    Namespace, events, artifact, correction_id = _prepare_successor_selection(tmp_path, monkeypatch)
    artifact.write_text("changed after correction\n")
    predecessor_run_id = events[0]["run_id"]

    with pytest.raises(work_memory.WorkMemoryError, match="successor-correction-artifact-hash-mismatch"):
        work_memory.cmd_select(Namespace(
            task_id="successor", sequence_id="sequence", discovery_log=None, fingerprint=None,
            verification_successor_of=predecessor_run_id,
            verifies_correction_id=[correction_id], repo_roots_file=None,
        ))


def test_successor_selection_requires_corrected_artifact_in_sealed_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    Namespace, events, _, correction_id = _prepare_successor_selection(
        tmp_path, monkeypatch, include_artifact=False,
    )
    predecessor_run_id = events[0]["run_id"]

    with pytest.raises(work_memory.WorkMemoryError, match="successor-correction-artifact-outside-bundle"):
        work_memory.cmd_select(Namespace(
            task_id="successor", sequence_id="sequence", discovery_log=None, fingerprint=None,
            verification_successor_of=predecessor_run_id,
            verifies_correction_id=[correction_id], repo_roots_file=None,
        ))


def test_successor_selection_accepts_an_explicitly_removed_bundle_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    Namespace, events, artifact, correction_id = _prepare_successor_selection(
        tmp_path, monkeypatch, include_artifact=False,
    )
    predecessor = events[0]
    predecessor["source_bundle"] = [{
        "repository_key": "memory-knowledge", "path": "scripts/deploy.sh",
        "sha256": "a" * 64,
    }]
    predecessor_run_id = predecessor["run_id"]

    selected = work_memory.cmd_select(Namespace(
        task_id="successor", sequence_id="sequence", discovery_log=None, fingerprint=None,
        verification_successor_of=predecessor_run_id,
        verifies_correction_id=[correction_id], repo_roots_file=None,
    ))

    assert selected["source_bundle"] == []
    assert artifact.is_file()


def test_run_start_rechecks_raw_successor_artifact_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    Namespace, events, artifact, correction_id = _prepare_successor_selection(tmp_path, monkeypatch)
    predecessor_run_id = events[0]["run_id"]
    work_memory.cmd_select(Namespace(
        task_id="successor", sequence_id="sequence", discovery_log=None, fingerprint=None,
        verification_successor_of=predecessor_run_id,
        verifies_correction_id=[correction_id], repo_roots_file=None,
    ))
    artifact.write_text("changed between selection and run start\n")

    with pytest.raises(work_memory.WorkMemoryError, match="successor-correction-artifact-hash-mismatch"):
        work_memory.cmd_run_start(Namespace(task_id="successor", run_id=None, event_id=None))


def test_verified_fingerprint_link_precedes_operation_kind_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    events = corrected_successor_events()
    fingerprint = next(item["fingerprint"] for item in events if item["event_type"] == "blocker_opened")
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([
        {"sequence_id": "sequence", "folder": "operations/sequences/sequence/",
         "operation_kinds": "repair", "lineage_id": "lineage"},
        {"sequence_id": "unrelated-deploy", "folder": "operations/sequences/unrelated-deploy/",
         "operation_kinds": "deploy", "lineage_id": "unrelated"},
    ], "9" * 64))
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: ([], "b" * 64, kwargs["subject_id"] == "sequence" and "lineage" or "unrelated"),
    )
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: (events, "8" * 64))
    work_memory.cmd_classify(Namespace(
        task_id="cross-kind", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))

    selected = work_memory.cmd_select(Namespace(
        task_id="cross-kind", sequence_id=None, discovery_log=None, fingerprint=fingerprint,
        verification_successor_of=None, verifies_correction_id=None, repo_roots_file=None,
    ))

    assert selected["subject_id"] == "sequence"
    assert selected["selection_reason"] == "fingerprint-link"
    assert selected["relevant_blocker_ids"]
    assert selected["eligible_corrections"]


def test_fingerprint_link_rejects_stale_current_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from argparse import Namespace

    events = corrected_successor_events()
    fingerprint = next(item["fingerprint"] for item in events if item["event_type"] == "blocker_opened")
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([{
        "sequence_id": "sequence", "folder": "operations/sequences/sequence/",
        "operation_kinds": "deploy", "lineage_id": "lineage",
    }], "9" * 64))
    monkeypatch.setattr(work_memory, "resolve_bundle", lambda **kwargs: ([], "c" * 64, "lineage"))
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: (events, "8" * 64))
    work_memory.cmd_classify(Namespace(
        task_id="stale", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))
    with pytest.raises(work_memory.WorkMemoryError, match="fingerprint-linked-sequence-stale"):
        work_memory.cmd_select(Namespace(
            task_id="stale", sequence_id=None, discovery_log=None, fingerprint=fingerprint,
            verification_successor_of=None, verifies_correction_id=None, repo_roots_file=None,
        ))


def test_fingerprint_tie_break_prefers_higher_success_count_before_lexical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    fingerprint = "7" * 64
    events = []
    for subject, successes in (("alpha", 1), ("zeta", 2)):
        blocker = f"blk-{subject}"
        events.extend([
            {"event_type": "blocker_opened", "blocker_id": blocker,
             "fingerprint": fingerprint, "subject_id": subject, "lineage_id": subject},
            {"event_type": "blocker_transitioned", "blocker_id": blocker,
             "to_status": "verified", "recorded_at_utc": "2026-01-01T00:00:00Z"},
        ])
        for index in range(successes):
            run_id = str(uuid.uuid4()); bundle = subject[0] * 64
            events.extend([
                {"event_type": "run_started", "run_id": run_id, "subject_id": subject,
                 "lineage_id": subject, "source_bundle_hash": bundle,
                 "started_at_utc": f"2026-01-01T00:0{index}:00Z"},
                {"event_type": "verification_recorded", "run_id": run_id, "subject_id": subject,
                 "lineage_id": subject, "source_bundle_hash": bundle,
                 "outcome": "passed", "quality": "same-path", "correction_ids": []},
                {"event_type": "run_closed", "run_id": run_id, "subject_id": subject,
                 "result": "passed"},
            ])
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([
        {"sequence_id": subject, "folder": f"operations/sequences/{subject}/",
         "operation_kinds": "deploy", "lineage_id": subject}
        for subject in ("alpha", "zeta")
    ], "9" * 64))
    monkeypatch.setattr(work_memory, "resolve_bundle", lambda **kwargs: (
        [], kwargs["subject_id"][0] * 64, kwargs["subject_id"],
    ))
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: (events, "8" * 64))
    work_memory.cmd_classify(Namespace(
        task_id="tie", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))
    selected = work_memory.cmd_select(Namespace(
        task_id="tie", sequence_id=None, discovery_log=None, fingerprint=fingerprint,
        verification_successor_of=None, verifies_correction_id=None, repo_roots_file=None,
    ))
    assert selected["subject_id"] == "zeta"


def test_registry_and_manifest_coverage():
    rows, _ = work_memory.registry_rows()
    assert rows
    assert len({row["sequence_id"] for row in rows}) == len(rows)
    for row in rows:
        manifest = work_memory.ROOT / row["folder"] / "dependencies.json"
        data = json.loads(manifest.read_text())
        assert data["schema_version"] == 1
        assert data["lineage_id"] == row["lineage_id"]


def test_no_retired_run_ledger_or_stale_activation_examples():
    assert not (work_memory.ROOT / "scripts/sequence_run_ledger.py").exists()
    tracked = [path for path in (work_memory.ROOT / "operations/sequences").rglob("*.md")]
    tracked.extend((work_memory.ROOT / "skills" / name / "SKILL.md") for name in (
        "working-agreement", "task-intake", "sequence-runner", "blocker-catalog",
    ))
    assert not any("sequence_guard.py activate --sequence-id" in path.read_text() for path in tracked)


def test_repository_work_memory_ledger_replays_and_view_is_current():
    events, ledger_hash = work_memory.load_ledger()

    assert events
    assert len(ledger_hash) == 64
    assert not work_memory.blocker_view_stale(ledger_hash)


def test_only_canonical_scripts_write_event_ledger():
    writers = []
    for path in (work_memory.ROOT / "scripts").glob("*.py"):
        text = path.read_text()
        if "events.jsonl" in text or "stage_event_batch(" in text:
            writers.append(path.name)
    assert sorted(writers) == ["sequence_promote.py", "work_memory.py"]
