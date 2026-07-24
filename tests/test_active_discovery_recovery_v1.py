from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import active_discovery_recovery_v1 as recovery
from scripts import work_memory


@pytest.fixture
def recovery_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    source_root = Path(__file__).parents[1]
    for relative in work_memory.BOOTSTRAP_TRUST_ANCHORS:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative, destination)
    target = scripts / "target.py"
    target.write_text("before\n", encoding="utf-8")

    lineage = "discovery-active-recovery-test"
    document = root / "operations/sequences/discovery/active-recovery-test.md"
    document.parent.mkdir(parents=True)
    document.write_text(
        f"# Active Recovery Test\n\nDiscoveryId: {lineage}\n"
        "CreatedAtUtc: 2026-07-20T00:00:00Z\n\n"
        "## Intended Outcome\nRecover one stale active discovery atomically.\n\n"
        "## Why This Looks Repeatable\nActive discovery source bundles can change.\n\n"
        "## Required Inputs, Auth, Or Environment\nCurrent task owner.\n\n"
        "## Commands And Observations\n"
        "python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> "
        "--run-id <run-id> --blocker-id <blocker-id> "
        "--occurrence-id <occurrence-id> --step-id <step-id> "
        "--changed-artifact <path> --solution <solution> "
        "--reusable-behavior-changed yes\n\n"
        "## Failure Handling\nFail closed.\n\n"
        "## Verified Path\nFocused integration test.\n\n"
        "## Promotion Readiness\nNot ready.\n",
        encoding="utf-8",
    )
    manifest = document.with_suffix(".dependencies.json")
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": lineage,
        "dependencies": [{
            "kind": "file",
            "repository_key": "memory-knowledge",
            "path_or_sequence_id": "scripts/target.py",
        }],
    }, sort_keys=True) + "\n", encoding="utf-8")

    ledger = root / "operations/work-memory/events.jsonl"
    blocker_view = root / "operations/blockers/BLOCKERS.md"
    ledger.parent.mkdir(parents=True)
    blocker_view.parent.mkdir(parents=True)
    monkeypatch.setattr(work_memory, "ROOT", root)
    monkeypatch.setattr(work_memory, "LEDGER", ledger)
    monkeypatch.setattr(work_memory, "BLOCKER_VIEW", blocker_view)

    roots = {"memory-knowledge": str(root)}
    old_bundle, old_hash, resolved = work_memory.resolve_bundle(
        mode="discovery", subject_id=lineage, document=document, manifest=manifest,
        repository_roots=roots, include_bootstrap_trust_anchors=True,
    )
    assert resolved == lineage
    task_id = "active-recovery-target"
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    co_blocker_id = "blk-" + "2" * 24
    occurrence_id = str(uuid.uuid4())
    co_occurrence_id = str(uuid.uuid4())
    owner = "019f79bc-aaf1-7d32-bc29-45a2f7ef3dbb"
    monkeypatch.setenv("CODEX_THREAD_ID", owner)
    owner_state = work_memory._claim_task_writer(task_id)
    ownership = work_memory._ownership_receipt_fields(task_id, owner_state)
    events = [
        work_memory._event(
            "run_started", run_id=run_id, task_id=task_id,
            subject_id=lineage, lineage_id=lineage, mode="discovery",
            operation_kind="workflow-drive", source_bundle=old_bundle,
            source_bundle_hash=old_hash, repository_roots=roots,
            classification_receipt_hash="a" * 64,
            selection_receipt_hash="b" * 64,
            **ownership,
            started_at_utc="2026-07-20T00:00:00Z",
        ),
        work_memory._event(
            "blocker_opened", run_id=run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, fingerprint="1" * 64,
            subject_id=lineage, lineage_id=lineage, step_id="recover-run",
            surface="sequence guard", symptom="stale source bundle",
            evidence="captured", impact="rerun blocked",
            boundary="active discovery lifecycle", status="open",
        ),
        work_memory._event(
            "blocker_opened", run_id=run_id, blocker_id=co_blocker_id,
            occurrence_id=co_occurrence_id, fingerprint="2" * 64,
            subject_id=lineage, lineage_id=lineage, step_id="fix-product",
            surface="live workflow", symptom="terminal critic discarded",
            evidence="captured", impact="phase blocked",
            boundary="phase ledger", status="open",
        ),
    ]
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": events,
    })
    target.write_text("after\n", encoding="utf-8")
    return {
        "root": root, "roots": roots, "document": document, "manifest": manifest,
        "target": target, "task_id": task_id, "run_id": run_id,
        "blocker_id": blocker_id, "co_blocker_id": co_blocker_id,
        "occurrence_id": occurrence_id, "owner": owner,
    }


def _args(flow: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        authorization_task_id="active-recovery-authorization",
        authorization_run_id=str(uuid.uuid4()),
        task_id=flow["task_id"], run_id=flow["run_id"],
        blocker_id=flow["blocker_id"], occurrence_id=flow["occurrence_id"],
        co_blocker_id=[flow["co_blocker_id"]], step_id="recover-run",
        changed_artifact=[str(flow["target"])], changed_artifacts_file=None,
        solution="atomically bind the exact current bundle and close the stale run",
        reusable_behavior_changed="yes", supersedes_correction_id=None,
        correction_id=None, event_id=None, transition_event_id=None,
        directives_path=None, directive_state=None, directive_max_age_minutes=30,
    )


def _install_authorization_stubs(
    monkeypatch: pytest.MonkeyPatch, flow: dict[str, object],
) -> None:
    monkeypatch.setattr(recovery.bootstrap, "_require_directives", lambda args: None)
    monkeypatch.setattr(recovery, "_authorize_recovery", lambda task_id, run_id: {
        "writer_thread_id": flow["owner"],
    })
    monkeypatch.setattr(work_memory, "require_task_writer", lambda task_id: {
        "writer_thread_id": flow["owner"], "ownership_generation": 1,
    })


def test_correct_atomically_finalizes_all_blockers_and_is_idempotent(
    recovery_flow: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = recovery_flow
    _install_authorization_stubs(monkeypatch, flow)
    args = _args(flow)

    first = recovery.cmd_correct(args)
    assert first["new_bundle_hash"]
    assert len(first["co_correction_ids"]) == 1

    events, _ = work_memory.load_ledger()
    related = [event for event in events if event.get("run_id") == flow["run_id"]]
    assert [event["event_type"] for event in related[-6:]] == [
        "correction_recorded", "correction_recorded", "bundle_transition_recorded",
        "blocker_transitioned", "blocker_transitioned", "run_closed",
    ]
    assert related[-1]["result"] == "failed"
    assert {
        event["blocker_id"] for event in related
        if event["event_type"] == "blocker_transitioned"
    } == {flow["blocker_id"], flow["co_blocker_id"]}

    second = recovery.cmd_correct(_args(flow))
    assert second["already_recorded"] is True
    assert second["correction_id"] == first["correction_id"]
    events_after_retry, _ = work_memory.load_ledger()
    assert events_after_retry == events


def test_exact_drift_rejects_an_incomplete_artifact_set(
    recovery_flow: dict[str, object],
) -> None:
    flow = recovery_flow
    events, _ = work_memory.load_ledger()
    start, _ = work_memory._run_state(events, str(flow["run_id"]))
    current, _, roots, _ = recovery._resolve_target_transition(start)

    with pytest.raises(recovery.ActiveDiscoveryRecoveryError) as raised:
        recovery._validate_exact_drift(
            start=start, current_bundle=current, changed_values=[],
            repository_roots=roots,
        )
    assert raised.value.code == "recovery-changed-artifacts-required"


def test_exact_drift_rejects_an_extra_artifact(
    recovery_flow: dict[str, object],
) -> None:
    flow = recovery_flow
    extra = Path(flow["root"]) / "scripts/extra.py"
    extra.write_text("unchanged\n", encoding="utf-8")
    events, _ = work_memory.load_ledger()
    start, _ = work_memory._run_state(events, str(flow["run_id"]))
    current, _, roots, _ = recovery._resolve_target_transition(start)

    with pytest.raises(recovery.ActiveDiscoveryRecoveryError) as raised:
        recovery._validate_exact_drift(
            start=start, current_bundle=current,
            changed_values=[str(flow["target"]), str(extra)], repository_roots=roots,
        )
    assert raised.value.code == "recovery-artifact-drift-mismatch"


def test_target_transition_rejects_trust_anchor_drift(
    recovery_flow: dict[str, object],
) -> None:
    flow = recovery_flow
    events, _ = work_memory.load_ledger()
    start, _ = work_memory._run_state(events, str(flow["run_id"]))
    anchor = Path(flow["root"]) / work_memory.BOOTSTRAP_TRUST_ANCHORS[0]
    anchor.write_text(anchor.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")

    with pytest.raises(recovery.ActiveDiscoveryRecoveryError) as raised:
        recovery._resolve_target_transition(start)
    assert raised.value.code == "recovery-trust-anchor-drift"


def test_target_run_rejects_terminal_state_without_its_recovery_correction(
    recovery_flow: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = recovery_flow
    _install_authorization_stubs(monkeypatch, flow)
    events, digest = work_memory.load_ledger()
    events.append(work_memory._event(
        "run_closed", run_id=flow["run_id"], subject_id="discovery-active-recovery-test",
        lineage_id="discovery-active-recovery-test", result="failed",
        completed_at_utc="2026-07-20T00:01:00Z", correction_count=0,
        blocker_ids=[flow["blocker_id"]], sequence_updated=False,
        verification_quality="none",
    ))
    monkeypatch.setattr(work_memory, "load_ledger", lambda: (events, digest))

    with pytest.raises(recovery.ActiveDiscoveryRecoveryError) as raised:
        recovery._load_target_run(
            task_id=str(flow["task_id"]), run_id=str(flow["run_id"]),
            authorization={"writer_thread_id": flow["owner"]},
            correction_id=str(uuid.uuid4()),
        )
    assert raised.value.code == "recovery-target-run-invalid"


def test_blocker_validation_rejects_a_co_blocker_from_another_run(
    recovery_flow: dict[str, object],
) -> None:
    flow = recovery_flow
    events, _ = work_memory.load_ledger()
    start, _ = work_memory._run_state(events, str(flow["run_id"]))
    args = _args(flow)
    args.co_blocker_id = ["blk-" + "9" * 24]
    events.append(work_memory._event(
        "blocker_opened", run_id=str(uuid.uuid4()), blocker_id=args.co_blocker_id[0],
        occurrence_id=str(uuid.uuid4()), fingerprint="9" * 64,
        subject_id=start["subject_id"], lineage_id=start["lineage_id"],
        step_id="elsewhere", surface="test", symptom="wrong run",
        evidence="captured", impact="none", boundary="test", status="open",
    ))

    with pytest.raises(recovery.ActiveDiscoveryRecoveryError) as raised:
        recovery._validate_blockers(
            events=events, start=start, args=args, correction_id=str(uuid.uuid4()),
        )
    assert raised.value.code == "recovery-blocker-mismatch"


def test_target_transition_requires_a_canonical_correction_row(
    recovery_flow: dict[str, object],
) -> None:
    flow = recovery_flow
    document = Path(flow["document"])
    document.write_text("# No correction command\n", encoding="utf-8")
    events, _ = work_memory.load_ledger()
    start, _ = work_memory._run_state(events, str(flow["run_id"]))

    with pytest.raises(recovery.ActiveDiscoveryRecoveryError) as raised:
        recovery._resolve_target_transition(start)
    assert raised.value.code == "recovery-correction-command-not-grounded"
