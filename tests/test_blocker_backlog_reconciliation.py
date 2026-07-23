from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import blocker_backlog_reconciliation as reconciliation


def _event(event_type: str, **fields):
    return {
        "schema_version": 1,
        "event_type": event_type,
        "event_id": fields.pop("event_id", f"{event_type}-event"),
        "recorded_at_utc": fields.pop("recorded_at_utc", "2026-07-23T00:00:00Z"),
        **fields,
    }


@pytest.fixture
def ledger_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, list[dict]]:
    events = [
        _event(
            "run_started", run_id="run-open", subject_id="subject-open",
            lineage_id="lineage-open",
        ),
        _event(
            "blocker_opened", event_id="open-event", run_id="run-open",
            blocker_id="blk-open", occurrence_id="occ-open",
            subject_id="subject-open", lineage_id="lineage-open",
            step_id="step-open", surface="surface-open", symptom="Still broken.",
            evidence="Captured failure.", impact="Outcome blocked.",
            boundary="Stable open boundary.",
        ),
        _event("run_closed", run_id="run-open", result="failed"),
        _event(
            "run_started", run_id="run-fixed", subject_id="subject-fixed",
            lineage_id="lineage-fixed",
        ),
        _event(
            "blocker_opened", event_id="fixed-open-event", run_id="run-fixed",
            blocker_id="blk-fixed", occurrence_id="occ-fixed",
            subject_id="subject-fixed", lineage_id="lineage-fixed",
            step_id="step-fixed", surface="surface-fixed", symptom="Was broken.",
            evidence="Captured failure.", impact="Outcome blocked.",
            boundary="Stable fixed boundary.",
        ),
        _event(
            "correction_recorded", run_id="run-fixed", blocker_id="blk-fixed",
            occurrence_id="occ-fixed", correction_id="correction-fixed",
        ),
        _event(
            "blocker_transitioned", run_id="run-fixed", blocker_id="blk-fixed",
            from_status="open", to_status="fixed-awaiting-verification",
        ),
        _event("run_closed", run_id="run-fixed", result="failed"),
        _event(
            "run_started", run_id="run-successor", subject_id="subject-fixed",
            lineage_id="lineage-fixed",
        ),
        _event(
            "verification_recorded", event_id="verification-fixed",
            run_id="run-successor", subject_id="subject-fixed",
            lineage_id="lineage-fixed", outcome="passed", quality="same-path",
            blocker_ids=["blk-fixed"], correction_ids=["correction-fixed"],
        ),
        _event("run_closed", run_id="run-successor", result="passed"),
        _event(
            "run_started", run_id="run-verified", subject_id="subject-verified",
            lineage_id="lineage-verified",
        ),
        _event(
            "blocker_opened", event_id="verified-open-event",
            run_id="run-verified", blocker_id="blk-verified",
            occurrence_id="occ-verified", subject_id="subject-verified",
            lineage_id="lineage-verified", step_id="step-verified",
            surface="surface-verified", symptom="Was broken.",
            evidence="Captured failure.", impact="Outcome blocked.",
            boundary="Stable verified boundary.",
        ),
        _event(
            "correction_recorded", run_id="run-verified",
            blocker_id="blk-verified", occurrence_id="occ-verified",
            correction_id="correction-verified",
        ),
        _event(
            "blocker_transitioned", run_id="run-verified",
            blocker_id="blk-verified", from_status="open",
            to_status="fixed-awaiting-verification",
        ),
        _event(
            "verification_recorded", event_id="verification-verified",
            run_id="run-verified", subject_id="subject-verified",
            lineage_id="lineage-verified", outcome="passed", quality="same-path",
            blocker_ids=["blk-verified"], correction_ids=["correction-verified"],
        ),
        _event(
            "blocker_transitioned", event_id="verified-transition",
            run_id="run-verified", blocker_id="blk-verified",
            from_status="fixed-awaiting-verification", to_status="verified",
            verification_event_id="verification-verified",
        ),
    ]
    monkeypatch.setattr(
        reconciliation.work_memory,
        "load_ledger",
        lambda path=None: (deepcopy(events), reconciliation._sha(events)),
    )
    return tmp_path, events


def _decide(payload: dict) -> None:
    payload["approval"] = {
        "approved": True,
        "approved_by": "Kamen",
        "approved_at_utc": "2026-07-23T00:00:00Z",
    }
    for row in payload["candidates"]:
        row["decision_reason"] = "Reviewed against captured evidence."
        if row["blocker_id"] == "blk-open":
            row.update(
                disposition="remediate",
                priority="high",
                resolution_owner="subject-open",
                route="prototype-driven-implementation",
                next_action="Open a bounded root-fix implementation.",
            )
        else:
            row.update(
                disposition="close",
                terminal_evidence="Named same-path verification is present.",
            )


def test_audit_uses_active_projection_and_real_lifecycle_facts(
    ledger_case: tuple[Path, list[dict]], tmp_path: Path,
) -> None:
    ledger_root, _ = ledger_case
    output = tmp_path / "audit.json"
    result = reconciliation.cmd_audit(
        SimpleNamespace(root=str(ledger_root), output=str(output)),
    )
    payload = json.loads(output.read_text())

    assert result["candidate_count"] == 3
    assert result["suggested_counts"] == {"remediate": 1, "close": 2}
    rows = {row["blocker_id"]: row for row in payload["candidates"]}
    assert rows["blk-open"]["originating_run_terminal"] is True
    assert rows["blk-fixed"]["closure_verification_event_id"] == "verification-fixed"
    assert rows["blk-verified"]["status"] == "verified"
    assert all(row["disposition"] == "pending" for row in rows.values())


def test_validate_accepts_owned_active_work_and_evidence_backed_closure(
    ledger_case: tuple[Path, list[dict]], tmp_path: Path,
) -> None:
    ledger_root, _ = ledger_case
    payload = reconciliation.audit(ledger_root)
    _decide(payload)
    manifest = tmp_path / "approved.json"
    manifest.write_text(json.dumps(payload))

    validated = reconciliation.validate_manifest(manifest, ledger_root)

    assert len(validated["candidates"]) == 3


def test_validate_rejects_open_blocker_closure_without_verification(
    ledger_case: tuple[Path, list[dict]], tmp_path: Path,
) -> None:
    ledger_root, _ = ledger_case
    payload = reconciliation.audit(ledger_root)
    _decide(payload)
    row = next(item for item in payload["candidates"] if item["blocker_id"] == "blk-open")
    row.update(
        disposition="close",
        terminal_evidence="No qualifying evidence.",
    )
    manifest = tmp_path / "invalid.json"
    manifest.write_text(json.dumps(payload))

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="close-status-not-eligible:blk-open",
    ):
        reconciliation.validate_manifest(manifest, ledger_root)


def test_validate_ignores_non_blocker_ledger_appends_but_rejects_state_drift(
    ledger_case: tuple[Path, list[dict]], tmp_path: Path,
) -> None:
    ledger_root, events = ledger_case
    payload = reconciliation.audit(ledger_root)
    _decide(payload)
    manifest = tmp_path / "approved.json"
    manifest.write_text(json.dumps(payload))
    events.append(_event(
        "task_writer_claimed", event_id="ownership-event",
        task_id="unrelated-task", writer_thread_id="thread",
        ownership_generation=1,
    ))
    reconciliation.validate_manifest(manifest, ledger_root)
    events.append(_event(
        "blocker_transitioned", event_id="non-gap-transition",
        run_id="run-open", blocker_id="blk-open",
        from_status="open", to_status="non-gap",
    ))

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="active-blocker-projection-drift",
    ):
        reconciliation.validate_manifest(manifest, ledger_root)


def test_execute_applies_one_atomic_terminal_batch_and_renders_active_queue(
    ledger_case: tuple[Path, list[dict]], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger_root, events = ledger_case
    payload = reconciliation.audit(ledger_root)
    _decide(payload)
    manifest = tmp_path / "approved.json"
    manifest.write_text(json.dumps(payload))
    events.append(_event(
        "run_started", event_id="reconciliation-run-start",
        run_id="reconciliation-run",
        subject_id="blocker-backlog-reconciliation",
        lineage_id="blocker-backlog-reconciliation",
    ))
    requests: list[dict] = []
    monkeypatch.setattr(
        reconciliation.work_memory,
        "transact",
        lambda request: requests.append(request) or {"ok": True},
    )
    active_index = ledger_root / "operations/blockers/ACTIVE.md"

    result = reconciliation.cmd_execute(SimpleNamespace(
        root=str(ledger_root),
        manifest=str(manifest),
        run_id="reconciliation-run",
        active_index=str(active_index),
    ))

    assert result["transition_count"] == 3
    assert result["active_count"] == 1
    assert len(requests) == 1
    transitions = requests[0]["events"]
    assert [
        (item["blocker_id"], item["from_status"], item["to_status"])
        for item in transitions
    ] == [
        ("blk-fixed", "fixed-awaiting-verification", "verified"),
        ("blk-fixed", "verified", "closed"),
        ("blk-verified", "verified", "closed"),
    ]
    rendered = active_index.read_text()
    assert "blk-open" in rendered
    assert "prototype-driven-implementation" in rendered
    assert "blk-fixed" not in rendered
    assert "blk-verified" not in rendered


def test_execute_rejects_non_reconciliation_run(
    ledger_case: tuple[Path, list[dict]], tmp_path: Path,
) -> None:
    ledger_root, events = ledger_case
    payload = reconciliation.audit(ledger_root)
    _decide(payload)
    manifest = tmp_path / "approved.json"
    manifest.write_text(json.dumps(payload))
    events.append(_event(
        "run_started", event_id="wrong-run-start", run_id="wrong-run",
        subject_id="another-sequence", lineage_id="another-sequence",
    ))

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="reconciliation-run-subject-mismatch",
    ):
        reconciliation.cmd_execute(SimpleNamespace(
            root=str(ledger_root),
            manifest=str(manifest),
            run_id="wrong-run",
            active_index=str(ledger_root / "operations/blockers/ACTIVE.md"),
        ))
