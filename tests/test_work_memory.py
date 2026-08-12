from __future__ import annotations

import base64
import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import work_memory


WRITER_A = "019f75a9-fd91-7650-a43f-d20de5e3ae16"
WRITER_B = "019ee569-0b44-7292-b806-a19fc34c09a2"


@pytest.fixture(autouse=True)
def isolated_writer_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    # Clear ambient client identity before setting the test's own. Without this the suite inherits
    # whatever the host session exports (a Claude Code session exports CLAUDE_CODE_SESSION_ID), so a
    # test that deletes CODEX_THREAD_ID to assert "no writer identity" would silently resolve a
    # claude writer instead and stop testing anything.
    for _ambient in (
        "MK_CLIENT_KIND", "MK_CLIENT_SESSION_ID",
        *work_memory.CLAUDE_SESSION_ENVS,
    ):
        monkeypatch.delenv(_ambient, raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_A)
    monkeypatch.setattr(
        work_memory, "LEDGER", tmp_path / "work-memory/events.jsonl",
    )
    monkeypatch.setattr(
        work_memory, "BLOCKER_VIEW", tmp_path / "blockers/BLOCKERS.md",
    )
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path / "receipts")


def event(kind: str, **fields):
    return {
        "schema_version": 1, "event_id": str(uuid.uuid4()), "event_type": kind,
        "recorded_at_utc": fields.pop("recorded_at_utc", "2026-01-01T00:00:00Z"), **fields,
    }


def test_resolve_bundle_maps_absolute_executable_to_declared_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    memory_root = tmp_path / "memory-knowledge"
    external_root = tmp_path / "united-partners"
    document = memory_root / "operations/sequences/discovery/example.md"
    manifest = document.with_suffix(".dependencies.json")
    executable = external_root / "scripts/run_canary.py"
    executable.parent.mkdir(parents=True)
    executable.write_text("print('ok')\n")
    document.parent.mkdir(parents=True)
    document.write_text(
        "CreatedAtUtc: 2026-01-01T00:00:00Z\n"
        "## Intended Outcome\nRun the canary.\n"
        "## Why This Looks Repeatable\nIt is scripted.\n"
        "## Required Inputs, Auth, Or Environment\nNone.\n"
        f"## Commands And Observations\npython3 {executable}\n"
        "## Failure Handling\nStop.\n"
        "## Verified Path\nPending.\n"
        "## Promotion Readiness\nPending.\n"
    )
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": "discovery-example",
        "dependencies": [{
            "kind": "file",
            "repository_key": "united-partners",
            "path_or_sequence_id": "scripts/run_canary.py",
        }],
    }))
    monkeypatch.setattr(work_memory, "ROOT", memory_root)

    bundle, _, lineage = work_memory.resolve_bundle(
        mode="discovery",
        subject_id="discovery-example",
        document=document,
        manifest=manifest,
        repository_roots={
            "memory-knowledge": str(memory_root),
            "united-partners": str(external_root),
        },
    )

    assert lineage == "discovery-example"
    assert any(
        item["repository_key"] == "united-partners"
        and item["path"] == "scripts/run_canary.py"
        for item in bundle
    )


def _resolve_nested_executable_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, declare_executable: bool,
):
    executable_path = "skills/research-playbook/scripts/research_package.py"
    executable = tmp_path / executable_path
    executable.parent.mkdir(parents=True)
    executable.write_text("print('controller')\n", encoding="utf-8")
    document = tmp_path / "operations/sequences/example/sequence.md"
    document.parent.mkdir(parents=True)
    document.write_text(
        "# example\n\n"
        f"python3 {executable_path} init state.json --charter charter.json\n",
        encoding="utf-8",
    )
    manifest = document.with_name("dependencies.json")
    dependencies = []
    if declare_executable:
        dependencies.append({
            "kind": "file",
            "repository_key": "memory-knowledge",
            "path_or_sequence_id": executable_path,
        })
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": "lineage-skill-controller",
        "dependencies": dependencies,
    }, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    return work_memory.resolve_bundle(
        mode="registered",
        subject_id="example",
        document=document,
        manifest=manifest,
        repository_roots={"memory-knowledge": str(tmp_path)},
    )


def test_resolve_bundle_accepts_manifest_covered_nested_executable_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    bundle, _, _ = _resolve_nested_executable_bundle(
        tmp_path, monkeypatch, declare_executable=True,
    )

    assert "skills/research-playbook/scripts/research_package.py" in {
        item["path"] for item in bundle
    }


def test_resolve_bundle_rejects_undeclared_nested_executable_with_full_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    with pytest.raises(
        work_memory.WorkMemoryError,
        match=(
            "executable-outside-manifest::skills/research-playbook/"
            "scripts/research_package.py"
        ),
    ):
        _resolve_nested_executable_bundle(
            tmp_path, monkeypatch, declare_executable=False,
        )


def test_resolve_bundle_collapses_identical_parent_child_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    shared = tmp_path / "scripts/shared.py"
    shared.parent.mkdir(parents=True)
    shared.write_text("print('shared')\n", encoding="utf-8")
    parent = tmp_path / "operations/sequences/parent/sequence.md"
    child = tmp_path / "operations/sequences/child/sequence.md"
    parent.parent.mkdir(parents=True)
    child.parent.mkdir(parents=True)
    parent.write_text("# Parent\n", encoding="utf-8")
    child.write_text("# Child\n", encoding="utf-8")
    shared_dependency = {
        "kind": "file",
        "repository_key": "memory-knowledge",
        "path_or_sequence_id": "scripts/shared.py",
    }
    parent.with_name("dependencies.json").write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": "parent",
        "dependencies": [
            shared_dependency,
            {
                "kind": "sequence",
                "repository_key": "memory-knowledge",
                "path_or_sequence_id": "child",
            },
        ],
    }), encoding="utf-8")
    child.with_name("dependencies.json").write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": "child",
        "dependencies": [shared_dependency],
    }), encoding="utf-8")
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)

    bundle, _, _ = work_memory.resolve_bundle(
        mode="registered",
        subject_id="parent",
        document=parent,
        manifest=parent.with_name("dependencies.json"),
        repository_roots={"memory-knowledge": str(tmp_path)},
    )

    matches = [
        item for item in bundle
        if item["repository_key"] == "memory-knowledge"
        and item["path"] == "scripts/shared.py"
    ]
    assert len(matches) == 1


def _intake_control_bundle_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    document = tmp_path / "operations/sequences/example/sequence.md"
    document.parent.mkdir(parents=True)
    document.write_text("# example\n", encoding="utf-8")
    launcher = tmp_path / "scripts/sequence_intake_launch.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("print('launch')\n", encoding="utf-8")
    contract = tmp_path / "operations/sequences/sequence-intake-contracts.json"
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text("{}\n", encoding="utf-8")
    regenerator = tmp_path / "scripts/regenerate_intake_contracts.py"
    regenerator.write_text("print('regenerate')\n", encoding="utf-8")
    manifest = document.with_name("dependencies.json")
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": "example",
        "dependencies": [{
            "kind": "file",
            "repository_key": "memory-knowledge",
            "path_or_sequence_id": "scripts/sequence_intake_launch.py",
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    return document, manifest, contract


def test_resolve_bundle_seals_intake_contract_and_regenerator_centrally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    document, manifest, _ = _intake_control_bundle_fixture(tmp_path, monkeypatch)

    bundle, _, _ = work_memory.resolve_bundle(
        mode="registered",
        subject_id="example",
        document=document,
        manifest=manifest,
        repository_roots={"memory-knowledge": str(tmp_path)},
    )

    paths = {item["path"] for item in bundle}
    assert "operations/sequences/sequence-intake-contracts.json" in paths
    assert "scripts/regenerate_intake_contracts.py" in paths


def test_resolve_bundle_fails_closed_when_intake_contract_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    document, manifest, contract = _intake_control_bundle_fixture(tmp_path, monkeypatch)
    contract.unlink()

    with pytest.raises(work_memory.WorkMemoryError, match="missing-dependency"):
        work_memory.resolve_bundle(
            mode="registered",
            subject_id="example",
            document=document,
            manifest=manifest,
            repository_roots={"memory-knowledge": str(tmp_path)},
        )


def _observer_context_payload():
    return {
        "intended_outcome": "Run a repeatable deployment.",
        "repeatability_reason": "It recurs across releases.",
        "repeatability_evidence_ids": ["task-repeatable"],
        "required_inputs": ["target environment"],
        "dependencies": [{"repository_key": "memory-knowledge", "path": "scripts/deploy.py"}],
        "failure_handling": [],
        "verification_contract": {
            "quality": "same-path", "expected_outcome": "passed", "success_evidence": "DEPLOY OK",
        },
        "effect_class": "external-reversible",
        "environment_annotations": [],
        "semantic_flag_annotations": [],
        "volatility_annotations": [],
    }


def _configure_observer_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger = tmp_path / "operations/work-memory/events.jsonl"
    view = tmp_path / "operations/blockers/BLOCKERS.md"
    registry = tmp_path / "operations/sequences/SEQUENCES.md"
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "LEDGER", ledger)
    monkeypatch.setattr(work_memory, "BLOCKER_VIEW", view)
    monkeypatch.setattr(work_memory, "REGISTRY", registry)
    task_id = "observer-task"
    state = work_memory._claim_task_writer(task_id)
    run_id = str(uuid.uuid4())
    start = event(
        "run_started", run_id=run_id, subject_id="discovery", lineage_id="lineage",
        mode="discovery", operation_kind="deploy", source_bundle=[],
        source_bundle_hash="a" * 64, classification_receipt_hash="b" * 64,
        selection_receipt_hash="c" * 64, started_at_utc="2026-01-01T00:00:00Z",
        repository_roots={"memory-knowledge": str(tmp_path)},
        task_id=task_id, **work_memory._ownership_receipt_fields(task_id, state),
    )
    work_memory.transact({"schema_version": 1, "expected_ledger_hash": None, "events": [start]})
    return run_id


def test_operation_context_claim_and_return_are_durable_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    run_id = _configure_observer_ledger(tmp_path, monkeypatch)
    context_file = tmp_path / "context.json"
    context_file.write_text(json.dumps(_observer_context_payload()), encoding="utf-8")
    context = work_memory.cmd_record_operation_context(SimpleNamespace(
        run_id=run_id, context_file=str(context_file),
    ))
    roots_hash = work_memory.sha256_bytes(work_memory.canonical_bytes({"memory-knowledge": str(tmp_path)}))
    claim_args = SimpleNamespace(
        run_id=run_id, context_id=context["context_id"], step_ordinal=0, step_id="deploy",
        argv_json=json.dumps(["python3", "scripts/deploy.py"]), command_source="script",
        source_ref_repository="memory-knowledge", source_ref_path="scripts/deploy.py",
        repository_roots_hash=roots_hash,
    )
    claim = work_memory.cmd_execution_claim(claim_args)
    returned = work_memory.cmd_execution_return(SimpleNamespace(
        execution_id=claim["execution_id"], exit_code=0,
    ))

    monkeypatch.setattr(work_memory, "utc_now", lambda: "2030-01-01T00:00:00Z")
    assert work_memory.cmd_record_operation_context(SimpleNamespace(
        run_id=run_id, context_file=str(context_file),
    ))["already_recorded"] is True
    assert work_memory.cmd_execution_claim(claim_args)["already_recorded"] is True
    assert work_memory.cmd_execution_return(SimpleNamespace(
        execution_id=claim["execution_id"], exit_code=0,
    ))["already_recorded"] is True
    events, _ = work_memory.load_ledger()
    assert [item["event_type"] for item in events[-3:]] == [
        "operation_context_recorded", "execution_claimed", "execution_returned",
    ]
    assert returned["execution_id"] == claim["execution_id"]


def test_execution_claim_requires_context_and_exact_root_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    run_id = _configure_observer_ledger(tmp_path, monkeypatch)
    with pytest.raises(work_memory.WorkMemoryError, match="operation-context-not-found"):
        work_memory.cmd_execution_claim(SimpleNamespace(
            run_id=run_id, context_id=str(uuid.uuid4()), step_ordinal=0, step_id="deploy",
            argv_json='["true"]', command_source="script",
            source_ref_repository="memory-knowledge", source_ref_path="scripts/deploy.py",
            repository_roots_hash="f" * 64,
        ))


@pytest.mark.parametrize("secret_argument", [
    "--password=hunter2",
    "--api-key=abcdefghijklmnopqrstuvwxyz",
    base64.urlsafe_b64encode(b"Bearer abcdefghijklmnopqrstuvwxyz").decode(),
    '{"password":"hunter2"}',
    '--config={"api_key":"abcdefghijklmnopqrstuvwxyz"}',
    base64.urlsafe_b64encode(b'{"password":"hunter2"}').decode(),
])
def test_execution_claim_rejects_credential_shaped_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, secret_argument: str,
) -> None:
    run_id = _configure_observer_ledger(tmp_path, monkeypatch)
    context_file = tmp_path / "context.json"
    context_file.write_text(json.dumps(_observer_context_payload()), encoding="utf-8")
    context = work_memory.cmd_record_operation_context(SimpleNamespace(
        run_id=run_id, context_file=str(context_file),
    ))
    roots_hash = work_memory.sha256_bytes(
        work_memory.canonical_bytes({"memory-knowledge": str(tmp_path)})
    )

    with pytest.raises(work_memory.WorkMemoryError, match="prohibited"):
        work_memory.cmd_execution_claim(SimpleNamespace(
            run_id=run_id, context_id=context["context_id"], step_ordinal=0,
            step_id="deploy", argv_json=json.dumps([
                "python3", "scripts/deploy.py", secret_argument,
            ]), command_source="script", source_ref_repository="memory-knowledge",
            source_ref_path="scripts/deploy.py", repository_roots_hash=roots_hash,
        ))


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


def owned_run_events(index: int, task_id: str) -> list[dict[str, object]]:
    claim = event(
        "task_writer_claimed", task_id=task_id, writer_thread_id=WRITER_A,
        ownership_generation=1,
    )
    state = {
        "writer_thread_id": WRITER_A, "ownership_generation": 1,
        "ownership_event_id": claim["event_id"],
    }
    records = run_events(index)
    records[0].update(
        task_id=task_id, **work_memory._ownership_receipt_fields(task_id, state),
    )
    return [claim, *records]


def test_merge_ledger_appends_source_only_events_through_canonical_writer(tmp_path: Path):
    target_events = owned_run_events(0, "merge-target")
    source_only = owned_run_events(1, "merge-source")
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


def test_merge_ledger_reconciles_already_persisted_legacy_history(tmp_path: Path):
    target_events = run_events(0)
    source_events = run_events(1)
    target = tmp_path / "target.jsonl"
    source = tmp_path / "source.jsonl"
    view = tmp_path / "BLOCKERS.md"
    target.write_bytes(
        b"".join(work_memory.canonical_bytes(item) for item in target_events)
    )
    source.write_bytes(
        b"".join(work_memory.canonical_bytes(item) for item in source_events)
    )

    result = work_memory.cmd_merge_ledger(SimpleNamespace(
        source_ledger=str(source), ledger=str(target), view=str(view),
        reconcile_persisted_source=True,
    ))

    merged, _ = work_memory.load_ledger(target)
    assert result["appended_event_count"] == len(source_events)
    assert [item["event_id"] for item in merged] == [
        item["event_id"] for item in target_events + source_events
    ]


def test_merge_ledger_preserves_bounded_legacy_status_from_valid_source(tmp_path: Path):
    target_events = owned_run_events(0, "merge-target")
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "9" * 24
    source_claim = event(
        "task_writer_claimed", task_id="merge-legacy-status",
        writer_thread_id=WRITER_A, ownership_generation=1,
    )
    source_state = {
        "writer_thread_id": WRITER_A, "ownership_generation": 1,
        "ownership_event_id": source_claim["event_id"],
    }
    source_events = [
        source_claim,
        event(
            "run_started", run_id=run_id, subject_id="legacy", lineage_id="legacy-lineage",
            mode="discovery", operation_kind="other", source_bundle=[],
            source_bundle_hash="9" * 64, classification_receipt_hash="8" * 64,
            selection_receipt_hash="7" * 64, started_at_utc="2026-01-02T00:00:00Z",
            task_id="merge-legacy-status",
            **work_memory._ownership_receipt_fields("merge-legacy-status", source_state),
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


def test_sealed_replay_finalizes_an_existing_unfinished_correction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduce the live dead end with the real cmd_correct replay branch."""
    sequence = tmp_path / "operations/sequences/example/sequence.md"
    sequence.parent.mkdir(parents=True)
    sequence.write_text("# example\n")
    artifact = tmp_path / "scripts/fix.py"
    artifact.parent.mkdir()
    artifact.write_text("fixed = True\n")
    run_id = str(uuid.uuid4())
    occurrence_id = str(uuid.uuid4())
    correction_id = str(uuid.uuid4())
    blocker_id = "blk-" + "8" * 24
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
        occurrence_id=occurrence_id, fingerprint="8" * 64, subject_id="example",
        lineage_id="lineage", step_id="review", surface="lifecycle", symptom="gap",
        evidence="captured live correction dead end", impact="blocked",
        boundary="sealed correction replay", status="open",
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
        repo_roots_file=None, finalize_failed_run=False,
    )

    recorded = work_memory.cmd_correct(args)
    assert [item["event_type"] for item in calls[0]["events"]] == [
        "correction_recorded", "bundle_transition_recorded",
    ]

    args.finalize_failed_run = True
    args.solution = "altered fix"
    with pytest.raises(work_memory.WorkMemoryError, match="correction-id-conflict"):
        work_memory.cmd_correct(args)
    args.solution = "stable fix"

    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: (new_bundle, "e" * 64, "lineage"),
    )
    with pytest.raises(
        work_memory.WorkMemoryError, match="existing-correction-bundle-mismatch",
    ):
        work_memory.cmd_correct(args)
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: (new_bundle, "d" * 64, "lineage"),
    )

    partial = event(
        "blocker_transitioned", run_id=run_id, blocker_id=blocker_id,
        from_status="open", to_status="fixed-awaiting-verification",
    )
    current.append(partial)
    with pytest.raises(
        work_memory.WorkMemoryError,
        match="existing-correction-finalization-conflict",
    ):
        work_memory.cmd_correct(args)
    current.pop()

    finalized = work_memory.cmd_correct(args)
    replayed = work_memory.cmd_correct(args)

    assert recorded["correction_id"] == finalized["correction_id"] == correction_id
    assert [item["event_type"] for item in calls[1]["events"]] == [
        "blocker_transitioned", "run_closed",
    ]
    assert len(calls) == 2
    assert replayed["already_recorded"] is True
    assert sum(item["event_type"] == "correction_recorded" for item in current) == 1
    assert sum(item["event_type"] == "bundle_transition_recorded" for item in current) == 1
    assert sum(item["event_type"] == "blocker_transitioned" for item in current) == 1
    assert sum(item["event_type"] == "run_closed" for item in current) == 1


def _co_correction_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, recovered_co: bool = False,
):
    sequence = tmp_path / "operations/sequences/example/sequence.md"
    sequence.parent.mkdir(parents=True)
    sequence.write_text("# example\n")
    artifact = tmp_path / "scripts/fix.py"
    artifact.parent.mkdir()
    artifact.write_text("fixed = True\n")
    run_id = str(uuid.uuid4())
    primary_id = "blk-" + "1" * 24
    co_id = "blk-" + "2" * 24
    primary_occurrence = str(uuid.uuid4())
    co_occurrence = str(uuid.uuid4())
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
    primary = event(
        "blocker_opened", run_id=run_id, blocker_id=primary_id,
        occurrence_id=primary_occurrence, fingerprint="1" * 64,
        subject_id="example", lineage_id="lineage", step_id="primary-step",
        surface="lifecycle", symptom="primary gap", evidence="review",
        impact="blocked", boundary="controller", status="open",
    )
    co_run_id = str(uuid.uuid4()) if recovered_co else run_id
    co = event(
        "blocker_opened", run_id=co_run_id, blocker_id=co_id,
        occurrence_id=co_occurrence, fingerprint="2" * 64,
        subject_id="example", lineage_id="lineage", step_id="co-step",
        surface="lifecycle", symptom="co gap", evidence="review",
        impact="blocked", boundary="controller", status="open",
    )
    if recovered_co:
        co_start = event(
            "run_started", run_id=co_run_id, subject_id="example", lineage_id="lineage",
            mode="registered", operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash="0" * 64, classification_receipt_hash="1" * 64,
            selection_receipt_hash="2" * 64, started_at_utc="2025-12-31T23:58:00Z",
        )
        co_close = event(
            "run_closed", run_id=co_run_id, subject_id="example", lineage_id="lineage",
            result="failed", completed_at_utc="2025-12-31T23:59:00Z",
            correction_count=0, blocker_ids=[co_id], sequence_updated=False,
            verification_quality="none",
        )
        recovered = event(
            "blocker_transitioned", run_id=run_id, blocker_id=co_id,
            from_status="open", to_status="open",
            recovery_evidence="carry the co-blocker to the active run",
        )
        current = [co_start, co, co_close, start, primary, recovered]
    else:
        current = [start, primary, co]
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
    correction_id = str(uuid.uuid4())
    args = SimpleNamespace(
        run_id=run_id, blocker_id=primary_id, occurrence_id=primary_occurrence,
        co_blocker_id=[co_id], step_id="primary-step",
        changed_artifact=[str(artifact)], solution="one fix closes both defects",
        reusable_behavior_changed="yes", supersedes_correction_id=None,
        correction_id=correction_id, event_id=None, transition_event_id=None,
        repo_roots_file=None, finalize_failed_run=True,
    )
    return current, calls, args, co_id, co_occurrence, correction_id


def test_finalize_correction_atomically_records_explicit_co_blocker_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, calls, args, co_id, co_occurrence, correction_id = _co_correction_flow(
        tmp_path, monkeypatch,
    )

    first = work_memory.cmd_correct(args)
    second = work_memory.cmd_correct(args)

    derived = str(uuid.uuid5(uuid.UUID(correction_id), co_id))
    assert [item["event_type"] for item in calls[0]["events"]] == [
        "correction_recorded", "correction_recorded", "bundle_transition_recorded",
        "blocker_transitioned", "blocker_transitioned", "run_closed",
    ]
    co_correction = calls[0]["events"][1]
    assert co_correction["correction_id"] == derived
    assert co_correction["primary_correction_id"] == correction_id
    assert co_correction["blocker_id"] == co_id
    assert co_correction["occurrence_id"] == co_occurrence
    assert co_correction["step_id"] == "co-step"
    assert calls[0]["events"][2]["correction_ids"] == [correction_id, derived]
    assert calls[0]["events"][-1]["correction_count"] == 2
    assert len(calls) == 1
    assert first["co_correction_ids"] == second["co_correction_ids"] == [derived]
    assert second["already_recorded"] is True
    assert current[-1]["event_type"] == "run_closed"


def test_co_correction_explicitly_supersedes_prior_attempt_for_same_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, calls, args, co_id, co_occurrence, correction_id = _co_correction_flow(
        tmp_path, monkeypatch,
    )
    prior_correction_id = str(uuid.uuid4())
    current.append(event(
        "correction_recorded", run_id=args.run_id, blocker_id=co_id,
        occurrence_id=co_occurrence, correction_id=prior_correction_id,
        subject_id="example", lineage_id="lineage", step_id="co-step",
        changed_artifacts=["scripts/old-fix.py"],
        changed_artifact_hashes=["e" * 64], reusable_behavior_changed=True,
        solution="earlier incomplete attempt",
    ))
    args.co_supersedes_correction_id = [prior_correction_id]

    first = work_memory.cmd_correct(args)
    second = work_memory.cmd_correct(args)

    derived = str(uuid.uuid5(uuid.UUID(correction_id), co_id))
    co_correction = calls[0]["events"][1]
    assert co_correction["correction_id"] == derived
    assert co_correction["supersedes_correction_id"] == prior_correction_id
    assert first["co_correction_ids"] == second["co_correction_ids"] == [derived]
    assert second["already_recorded"] is True

    superseded = {
        correction_id
        for item in current
        if item["event_type"] == "correction_recorded"
        for correction_id in work_memory._superseded_correction_ids(item)
    }
    active = {
        item["correction_id"]
        for item in current
        if item["event_type"] == "correction_recorded"
        and item["blocker_id"] == co_id
        and item["correction_id"] not in superseded
    }
    assert active == {derived}


def test_finalize_correction_accepts_co_blocker_recovered_to_primary_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, calls, args, co_id, co_occurrence, _ = _co_correction_flow(
        tmp_path, monkeypatch, recovered_co=True,
    )

    result = work_memory.cmd_correct(args)

    co_correction = next(
        item for item in calls[0]["events"]
        if item["event_type"] == "correction_recorded" and item["blocker_id"] == co_id
    )
    assert co_correction["occurrence_id"] == co_occurrence
    assert result["co_correction_ids"] == [co_correction["correction_id"]]
    assert current[-1]["event_type"] == "run_closed"


def test_finalize_correction_omitted_co_blocker_rejects_run_close_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, _, args, _, _, _ = _co_correction_flow(tmp_path, monkeypatch)
    before = list(current)
    args.co_blocker_id = []

    with pytest.raises(work_memory.WorkMemoryError, match="terminal-run-has-open-blockers"):
        work_memory.cmd_correct(args)

    assert current == before


def test_run_close_allows_open_incidental_blocker_assigned_downstream() -> None:
    run_id = "d199be4d-a762-4727-a787-c010088151ec"
    incidental_blocker_id = "blk-c85e95150851b3c431fc1f04"
    occurrence_id = "f98571ae-b516-4854-a16b-f6bd5e59540c"
    events = [
        event(
            "run_started", run_id=run_id, subject_id="vivacom",
            lineage_id="vivacom-lineage", mode="discovery",
            operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash="a" * 64, classification_receipt_hash="b" * 64,
            selection_receipt_hash="c" * 64,
            started_at_utc="2026-07-24T12:00:00Z",
        ),
        event(
            "blocker_opened", run_id=run_id,
            blocker_id=incidental_blocker_id, occurrence_id=occurrence_id,
            fingerprint="d" * 64, subject_id="vivacom",
            lineage_id="vivacom-lineage",
            step_id="monitor-strategy-semantic-rejection",
            surface="united-partners-strategy-telemetry-identity",
            symptom="The watcher emitted a false deviation.",
            evidence="The workflow continued while monitor identity validation failed.",
            impact="Monitoring is unreliable but the strategy deliverable can continue.",
            boundary="Monitoring attempt identity contract.", status="open",
        ),
        event(
            "blocker_assigned_downstream", run_id=run_id,
            blocker_id=incidental_blocker_id, occurrence_id=occurrence_id,
            classification="incidental-system-defect",
            downstream_owner="united-partners-monitoring",
            evidence="Assigned outside the Vivacom phase-20 deliverable.",
        ),
        event(
            "run_closed", run_id=run_id, subject_id="vivacom",
            lineage_id="vivacom-lineage", result="failed",
            completed_at_utc="2026-07-24T12:30:00Z",
            correction_count=0, blocker_ids=[incidental_blocker_id],
            sequence_updated=False, verification_quality="none",
        ),
    ]

    _, view_bytes, _ = work_memory.stage_event_batch(
        b"", {
            "schema_version": 1,
            "expected_ledger_hash": work_memory.sha256_bytes(b""),
            "events": events,
        },
    )
    view = view_bytes.decode()
    assert f"## {incidental_blocker_id}" in view
    assert "- Status: `open`" in view
    assert "- Classification: `incidental-system-defect`" in view
    assert "- Downstream owner: `united-partners-monitoring`" in view


def test_downstream_assignment_cannot_bypass_corrected_open_blocker() -> None:
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    occurrence_id = str(uuid.uuid4())
    events = [
        event(
            "run_started", run_id=run_id, subject_id="example",
            lineage_id="lineage", mode="discovery",
            operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash="a" * 64, classification_receipt_hash="b" * 64,
            selection_receipt_hash="c" * 64,
            started_at_utc="2026-07-24T12:00:00Z",
        ),
        event(
            "blocker_opened", run_id=run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, fingerprint="d" * 64,
            subject_id="example", lineage_id="lineage", step_id="deliverable",
            surface="phase-output", symptom="The deliverable failed.",
            evidence="The production phase rejected its output.",
            impact="The requested deliverable cannot complete.",
            boundary="Phase output contract.", status="open",
        ),
        event(
            "correction_recorded", run_id=run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, correction_id=str(uuid.uuid4()),
            subject_id="example", lineage_id="lineage", step_id="deliverable",
            changed_artifacts=["scripts/fix.py"],
            changed_artifact_hashes=["e" * 64],
            reusable_behavior_changed=True, solution="Fix the output contract.",
        ),
        event(
            "blocker_assigned_downstream", run_id=run_id,
            blocker_id=blocker_id, occurrence_id=occurrence_id,
            classification="incidental-system-defect",
            downstream_owner="another-task",
            evidence="Attempted reassignment.",
        ),
    ]

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="invalid-downstream-blocker-assignment",
    ):
        work_memory.stage_event_batch(
            b"", {
                "schema_version": 1,
                "expected_ledger_hash": work_memory.sha256_bytes(b""),
                "events": events,
            },
        )


def test_downstream_assigned_blocker_cannot_receive_current_run_correction() -> None:
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "2" * 24
    occurrence_id = str(uuid.uuid4())
    opened = event(
        "blocker_opened", run_id=run_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, fingerprint="d" * 64,
        subject_id="example", lineage_id="lineage", step_id="monitor",
        surface="telemetry", symptom="Monitoring identity failed.",
        evidence="Captured monitor failure.", impact="Monitoring is unreliable.",
        boundary="Monitoring contract.", status="open",
    )
    assignment = event(
        "blocker_assigned_downstream", run_id=run_id,
        blocker_id=blocker_id, occurrence_id=occurrence_id,
        classification="incidental-system-defect",
        downstream_owner="monitoring-maintenance",
        evidence="Assigned outside the current deliverable.",
    )
    correction = event(
        "correction_recorded", run_id=run_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, correction_id=str(uuid.uuid4()),
        subject_id="example", lineage_id="lineage", step_id="monitor",
        changed_artifacts=["scripts/fix.py"],
        changed_artifact_hashes=["e" * 64],
        reusable_behavior_changed=True, solution="Attempted current-run fix.",
    )
    events = [
        event(
            "run_started", run_id=run_id, subject_id="example",
            lineage_id="lineage", mode="discovery",
            operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash="a" * 64, classification_receipt_hash="b" * 64,
            selection_receipt_hash="c" * 64,
            started_at_utc="2026-07-24T12:00:00Z",
        ),
        opened, assignment, correction,
    ]

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="correction-for-downstream-blocker",
    ):
        work_memory.stage_event_batch(
            b"", {
                "schema_version": 1,
                "expected_ledger_hash": work_memory.sha256_bytes(b""),
                "events": events,
            },
        )


def test_stock_correct_appends_sequential_cumulative_correction_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sequence = tmp_path / "operations/sequences/example/sequence.md"
    sequence.parent.mkdir(parents=True)
    sequence.write_text("# example\n")
    phase20 = tmp_path / "scripts/phase20.py"
    lifecycle = tmp_path / "scripts/lifecycle.py"
    phase20.parent.mkdir()
    phase20.write_text("phase20 = 'fixed'\n")
    lifecycle.write_text("lifecycle = 'fixed'\n")
    run_id = str(uuid.uuid4())
    prior_blocker_id = "blk-" + "1" * 24
    incidental_blocker_id = "blk-" + "2" * 24
    lifecycle_blocker_id = "blk-" + "3" * 24
    prior_occurrence = str(uuid.uuid4())
    incidental_occurrence = str(uuid.uuid4())
    lifecycle_occurrence = str(uuid.uuid4())
    prior_correction_id = str(uuid.uuid4())
    lifecycle_correction_id = str(uuid.uuid4())
    start_hash = "a" * 64
    prior_bundle_hash = "b" * 64
    current_bundle_hash = "c" * 64
    sequence_row = {
        "repository_key": "memory-knowledge",
        "path": "operations/sequences/example/sequence.md",
        "sha256": "d" * 64,
    }
    start = event(
        "run_started", run_id=run_id, subject_id="example", lineage_id="lineage",
        mode="registered", operation_kind="workflow-drive",
        source_bundle=[
            sequence_row,
            {
                "repository_key": "memory-knowledge",
                "path": "scripts/phase20.py", "sha256": "e" * 64,
            },
        ],
        source_bundle_hash=start_hash,
        classification_receipt_hash="f" * 64,
        selection_receipt_hash="0" * 64,
        started_at_utc="2026-07-24T12:00:00Z",
    )
    prior_opened = event(
        "blocker_opened", run_id=run_id, blocker_id=prior_blocker_id,
        occurrence_id=prior_occurrence, fingerprint="1" * 64,
        subject_id="example", lineage_id="lineage", step_id="phase-20",
        surface="strategy", symptom="phase 20 failed", evidence="captured failure",
        impact="deliverable blocked", boundary="phase-20 contract", status="open",
    )
    phase20_hash = work_memory.sha256_bytes(phase20.read_bytes())
    prior_correction = event(
        "correction_recorded", run_id=run_id, blocker_id=prior_blocker_id,
        occurrence_id=prior_occurrence, correction_id=prior_correction_id,
        subject_id="example", lineage_id="lineage", step_id="phase-20",
        changed_artifacts=["scripts/phase20.py"],
        changed_artifact_hashes=[phase20_hash],
        reusable_behavior_changed=True, solution="repair phase 20",
    )
    prior_transition = event(
        "bundle_transition_recorded", lineage_id="lineage",
        old_bundle_hash=start_hash, new_bundle_hash=prior_bundle_hash,
        transition_reason="correction", run_id=run_id,
        correction_ids=[prior_correction_id],
        changed_artifacts=["scripts/phase20.py"],
        changed_artifact_hashes=[phase20_hash],
    )
    prior_awaiting = event(
        "blocker_transitioned", run_id=run_id,
        blocker_id=prior_blocker_id, from_status="open",
        to_status="fixed-awaiting-verification",
    )
    incidental_opened = event(
        "blocker_opened", run_id=run_id, blocker_id=incidental_blocker_id,
        occurrence_id=incidental_occurrence, fingerprint="2" * 64,
        subject_id="example", lineage_id="lineage", step_id="monitor",
        surface="telemetry", symptom="monitor identity failed",
        evidence="captured monitor deviation", impact="monitoring unreliable",
        boundary="monitoring contract", status="open",
    )
    incidental_assignment = event(
        "blocker_assigned_downstream", run_id=run_id,
        blocker_id=incidental_blocker_id, occurrence_id=incidental_occurrence,
        classification="incidental-system-defect",
        downstream_owner="monitoring-maintenance",
        evidence="Outside the current deliverable.",
    )
    lifecycle_opened = event(
        "blocker_opened", run_id=run_id, blocker_id=lifecycle_blocker_id,
        occurrence_id=lifecycle_occurrence, fingerprint="3" * 64,
        subject_id="example", lineage_id="lineage",
        step_id="activate-correction-successor", surface="work-memory",
        symptom="successor activation blocked", evidence="stale source bundle",
        impact="live verification blocked", boundary="correction lifecycle",
        status="open",
    )
    current = [
        start, prior_opened, prior_correction, prior_transition, prior_awaiting,
        incidental_opened, incidental_assignment, lifecycle_opened,
    ]
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "load_ledger", lambda: (current, "4" * 64))
    current_bundle = [
        sequence_row,
        {
            "repository_key": "memory-knowledge",
            "path": "scripts/phase20.py", "sha256": phase20_hash,
        },
        {
            "repository_key": "memory-knowledge",
            "path": "scripts/lifecycle.py",
            "sha256": work_memory.sha256_bytes(lifecycle.read_bytes()),
        },
    ]
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: (current_bundle, current_bundle_hash, "lineage"),
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
        run_id=run_id, blocker_id=lifecycle_blocker_id,
        occurrence_id=lifecycle_occurrence, co_blocker_id=None,
        step_id="activate-correction-successor",
        changed_artifact=[str(lifecycle)],
        solution="support cumulative sequential corrections",
        reusable_behavior_changed="yes", supersedes_correction_id=None,
        correction_id=lifecycle_correction_id, event_id=None,
        transition_event_id=None, repo_roots_file=None,
        finalize_failed_run=True,
    )

    first = work_memory.cmd_correct(args)
    second = work_memory.cmd_correct(args)

    recorded = calls[0]["events"]
    transition = next(
        item for item in recorded
        if item["event_type"] == "bundle_transition_recorded"
    )
    assert transition["old_bundle_hash"] == prior_bundle_hash
    assert transition["new_bundle_hash"] == current_bundle_hash
    assert transition["correction_ids"] == [
        prior_correction_id, lifecycle_correction_id,
    ]
    assert transition["changed_artifacts"] == ["scripts/lifecycle.py"]
    assert first["old_bundle_hash"] == prior_bundle_hash
    assert second["already_recorded"] is True
    assert len(calls) == 1
    assert current[-1]["event_type"] == "run_closed"
    assert current[-1]["correction_count"] == 2
    assert next(
        item for item in current
        if item.get("blocker_id") == prior_blocker_id
        and item["event_type"] == "blocker_transitioned"
    )["to_status"] == "fixed-awaiting-verification"
    view = work_memory.render_blocker_view(current, "5" * 64)
    incidental_section = view.split(f"## {incidental_blocker_id}", 1)[1]
    assert "- Status: `open`" in incidental_section
    assert "- Classification: `incidental-system-defect`" in incidental_section
    work_memory._validate_successor_corrections(
        current, lineage_id="lineage", source_bundle=current_bundle,
        predecessor_run_id=run_id,
        correction_ids=[prior_correction_id, lifecycle_correction_id],
        repository_roots={"memory-knowledge": str(tmp_path)},
        source_bundle_hash=current_bundle_hash,
    )


def test_effective_correction_bundle_rejects_broken_sequential_chain() -> None:
    run_id = str(uuid.uuid4())
    first_correction_id = str(uuid.uuid4())
    second_correction_id = str(uuid.uuid4())
    start = event(
        "run_started", run_id=run_id, subject_id="example",
        lineage_id="lineage", mode="registered",
        operation_kind="workflow-drive", source_bundle=[],
        source_bundle_hash="a" * 64,
        classification_receipt_hash="b" * 64,
        selection_receipt_hash="c" * 64,
        started_at_utc="2026-07-24T12:00:00Z",
    )
    transitions = [
        event(
            "bundle_transition_recorded", lineage_id="lineage",
            old_bundle_hash="a" * 64, new_bundle_hash="d" * 64,
            transition_reason="correction", run_id=run_id,
            correction_ids=[first_correction_id],
            changed_artifacts=["scripts/first.py"],
            changed_artifact_hashes=["e" * 64],
        ),
        event(
            "bundle_transition_recorded", lineage_id="lineage",
            old_bundle_hash="f" * 64, new_bundle_hash="0" * 64,
            transition_reason="correction", run_id=run_id,
            correction_ids=[first_correction_id, second_correction_id],
            changed_artifacts=["scripts/second.py"],
            changed_artifact_hashes=["1" * 64],
        ),
    ]

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="noncumulative-correction-transition",
    ):
        work_memory._effective_correction_bundle(start, transitions)


def test_non_gap_transition_cannot_dismiss_anomaly_with_free_text_only() -> None:
    transition = event(
        "blocker_transitioned",
        run_id=str(uuid.uuid4()),
        blocker_id="blk-" + "9" * 24,
        from_status="open",
        to_status="non-gap",
        non_gap_evidence="not a defect",
    )

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="non-gap-verification-required",
    ):
        work_memory.stage_event_batch(b"", {
            "schema_version": 1,
            "expected_ledger_hash": None,
            "events": [transition],
        })


def test_non_gap_transition_requires_bound_same_path_proof() -> None:
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "8" * 24
    start = event(
        "run_started",
        run_id=run_id,
        subject_id="phase20-resume",
        lineage_id="phase20-resume",
        mode="registered",
        operation_kind="workflow-drive",
        source_bundle=[],
        source_bundle_hash="a" * 64,
        classification_receipt_hash="b" * 64,
        selection_receipt_hash="c" * 64,
        started_at_utc="2026-07-24T12:00:00Z",
    )
    opened = event(
        "blocker_opened",
        run_id=run_id,
        blocker_id=blocker_id,
        occurrence_id=str(uuid.uuid4()),
        fingerprint="d" * 64,
        subject_id="phase20-resume",
        lineage_id="phase20-resume",
        step_id="captured-anomaly",
        surface="phase20-live-resume",
        symptom="unexpected result",
        evidence="captured live output",
        impact="success remains unproven",
        boundary="same-path investigation",
        status="open",
    )
    verification = event(
        "verification_recorded",
        run_id=run_id,
        subject_id="phase20-resume",
        lineage_id="phase20-resume",
        source_bundle_hash="a" * 64,
        outcome="passed",
        quality="same-path",
        evidence="same public entry point proves the observation is not a defect",
        blocker_ids=[blocker_id],
        correction_ids=[],
        changed_artifact_hashes=[],
    )
    dismissed = event(
        "blocker_transitioned",
        run_id=run_id,
        blocker_id=blocker_id,
        from_status="open",
        to_status="non-gap",
        verification_event_id=verification["event_id"],
        non_gap_evidence="proved by the bound same-path verification",
    )

    work_memory.validate_lifecycle([start, opened, verification, dismissed])


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("unknown", "unknown-co-blocker"),
        ("different-run", "co-blocker-different-run"),
        ("different-task", "co-blocker-different-task"),
        ("non-open", "co-blocker-not-open"),
        ("duplicate", "duplicate-co-blocker"),
        ("primary-duplicate", "duplicate-co-blocker"),
    ],
)
def test_explicit_co_blocker_contract_rejects_invalid_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, error: str,
) -> None:
    current, _, args, co_id, _, _ = _co_correction_flow(tmp_path, monkeypatch)
    if case == "unknown":
        args.co_blocker_id = ["blk-" + "9" * 24]
    elif case in {"different-run", "different-task"}:
        other_run = str(uuid.uuid4())
        if case == "different-task":
            current[0]["task_id"] = "task-a"
        current.append(event(
            "run_started", run_id=other_run, subject_id="example", lineage_id="lineage",
            mode="registered", operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash="3" * 64, classification_receipt_hash="4" * 64,
            selection_receipt_hash="5" * 64, started_at_utc="2026-01-01T00:01:00Z",
            **({"task_id": "task-b"} if case == "different-task" else {}),
        ))
        current[2]["run_id"] = other_run
    elif case == "non-open":
        current.append(event(
            "blocker_transitioned", run_id=args.run_id, blocker_id=co_id,
            from_status="open", to_status="non-gap", non_gap_evidence="not a defect",
        ))
    elif case == "duplicate":
        args.co_blocker_id = [co_id, co_id]
    else:
        args.co_blocker_id = [args.blocker_id]

    with pytest.raises(work_memory.WorkMemoryError, match=error):
        work_memory.cmd_correct(args)


def test_discovery_correction_selects_subject_document_after_registered_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = tmp_path / "operations/sequences/discovery/example.md"
    discovery.parent.mkdir(parents=True)
    discovery.write_text("# example\n\nDiscoveryId: discovery-example\n")
    manifest = discovery.with_suffix(".dependencies.json")
    manifest.write_text(json.dumps({
        "schema_version": 1, "lineage_id": "discovery-example", "dependencies": [],
    }))
    artifact = tmp_path / "scripts/fix.py"
    artifact.parent.mkdir()
    artifact.write_text("fixed = True\n")
    run_id, occurrence_id = str(uuid.uuid4()), str(uuid.uuid4())
    blocker_id = "blk-" + "5" * 24
    subject_path = str(discovery.relative_to(tmp_path))
    manifest_path = str(manifest.relative_to(tmp_path))
    dependency_path = "operations/sequences/dependency/sequence.md"
    old_bundle = [
        {"repository_key": "memory-knowledge", "path": dependency_path, "sha256": "1" * 64},
        {"repository_key": "memory-knowledge", "path": subject_path, "sha256": "2" * 64},
        {"repository_key": "memory-knowledge", "path": manifest_path, "sha256": "3" * 64},
    ]
    rows = [
        event(
            "run_started", run_id=run_id, subject_id="discovery-example",
            lineage_id="discovery-example", mode="discovery", operation_kind="other",
            source_bundle=old_bundle, source_bundle_hash="4" * 64,
            classification_receipt_hash="5" * 64, selection_receipt_hash="6" * 64,
            started_at_utc="2026-01-01T00:00:00Z",
        ),
        event(
            "blocker_opened", run_id=run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, fingerprint="7" * 64,
            subject_id="discovery-example", lineage_id="discovery-example",
            step_id="audit", surface="controller", symptom="gap", evidence="audit",
            impact="blocked", boundary="subject document", status="open",
        ),
    ]
    captured: dict[str, object] = {}
    new_bundle = old_bundle + [{
        "repository_key": "memory-knowledge", "path": "scripts/fix.py", "sha256": "8" * 64,
    }]
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "load_ledger", lambda: (rows, "9" * 64))
    monkeypatch.setattr(
        work_memory, "_artifact_hashes", lambda *args, **kwargs: (["scripts/fix.py"], ["8" * 64]),
    )
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: captured.update(kwargs) or (new_bundle, "a" * 64, "discovery-example"),
    )
    monkeypatch.setattr(work_memory, "transact", lambda request: {"ok": True})

    work_memory.cmd_correct(SimpleNamespace(
        run_id=run_id, blocker_id=blocker_id, occurrence_id=occurrence_id,
        step_id="audit", changed_artifact=[str(artifact)], solution="stable fix",
        reusable_behavior_changed="yes", supersedes_correction_id=None,
        correction_id=str(uuid.uuid4()), event_id=None, transition_event_id=None,
        repo_roots_file=None, finalize_failed_run=False,
    ))

    assert captured["document"] == discovery
    assert captured["manifest"] == manifest


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


def test_artifact_hashes_round_trips_repository_qualified_identity(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    artifact = external / "scripts/fix.py"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("fixed = True\n")
    roots_file = tmp_path / "roots.json"
    roots_file.write_text(json.dumps({"external": str(external)}))

    artifacts, hashes = work_memory._artifact_hashes(
        [str(artifact)], str(roots_file)
    )
    replayed_artifacts, replayed_hashes = work_memory._artifact_hashes(
        artifacts, str(roots_file)
    )

    assert replayed_artifacts == artifacts
    assert replayed_hashes == hashes


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


def test_persisted_event_after_terminal_loads_but_new_append_still_fails():
    persisted = run_events(0)
    late = event(
        "verification_recorded", run_id=persisted[0]["run_id"], subject_id="sequence",
        lineage_id="lineage", source_bundle_hash="a" * 64, outcome="passed",
        quality="same-path", evidence="historical late event", blocker_ids=[],
        correction_ids=[], changed_artifact_hashes=[],
    )
    existing = b"".join(
        work_memory.canonical_bytes(item) for item in [*persisted, late]
    )

    assert work_memory.parse_ledger_bytes(existing)[-1] == late
    with pytest.raises(work_memory.WorkMemoryError, match="event-after-terminal"):
        work_memory.stage_event_batch(
            b"".join(work_memory.canonical_bytes(item) for item in persisted),
            {
                "schema_version": 1,
                "expected_ledger_hash": None,
                "events": [late],
            },
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


def test_open_blocker_recovery_rebinds_terminal_occurrence_to_active_same_lineage_run():
    old_run_id, recovery_run_id = str(uuid.uuid4()), str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    occurrence_id = str(uuid.uuid4())
    legacy = [
        event(
            "run_started", run_id=old_run_id, subject_id="sequence", lineage_id="lineage",
            mode="discovery", operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash="a" * 64, classification_receipt_hash="1" * 64,
            selection_receipt_hash="2" * 64, started_at_utc="2026-01-01T00:00:00Z",
        ),
        event(
            "blocker_opened", run_id=old_run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, fingerprint="f" * 64, subject_id="sequence",
            lineage_id="lineage", step_id="verify", surface="ledger", symptom="blocked",
            evidence="confirmed", impact="cannot continue", boundary="event lifecycle", status="open",
        ),
        event(
            "run_closed", run_id=old_run_id, subject_id="sequence", lineage_id="lineage",
            result="failed", completed_at_utc="2026-01-01T00:01:00Z", correction_count=0,
            blocker_ids=[blocker_id], sequence_updated=False, verification_quality="none",
        ),
    ]
    additions = [
        event(
            "run_started", run_id=recovery_run_id, subject_id="sequence", lineage_id="lineage",
            mode="discovery", operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash="a" * 64, classification_receipt_hash="3" * 64,
            selection_receipt_hash="4" * 64, started_at_utc="2026-01-01T00:02:00Z",
        ),
        event(
            "blocker_transitioned", run_id=recovery_run_id, blocker_id=blocker_id,
            from_status="open", to_status="open",
            recovery_evidence="carry the unchanged occurrence to the active same-lineage run",
        ),
        event(
            "correction_recorded", run_id=recovery_run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, correction_id=str(uuid.uuid4()),
            subject_id="sequence", lineage_id="lineage", step_id="verify",
            changed_artifacts=["scripts/verify.py"], changed_artifact_hashes=["e" * 64],
            reusable_behavior_changed=True, solution="repair the stable boundary",
        ),
    ]

    legacy_bytes = b"".join(work_memory.canonical_bytes(item) for item in legacy)
    ledger, _, _ = work_memory.stage_event_batch(
        legacy_bytes,
        {"schema_version": 1, "expected_ledger_hash": None, "events": additions},
    )

    parsed = work_memory.parse_ledger_bytes(ledger)
    assert parsed[-2]["from_status"] == parsed[-2]["to_status"] == "open"
    assert parsed[-1]["occurrence_id"] == occurrence_id


def test_open_blocker_recovery_rejects_same_run_open_to_open_transition():
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    events = [
        event(
            "run_started", run_id=run_id, subject_id="sequence", lineage_id="lineage",
            mode="discovery", operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash="a" * 64, classification_receipt_hash="1" * 64,
            selection_receipt_hash="2" * 64, started_at_utc="2026-01-01T00:00:00Z",
        ),
        event(
            "blocker_opened", run_id=run_id, blocker_id=blocker_id,
            occurrence_id=str(uuid.uuid4()), fingerprint="f" * 64, subject_id="sequence",
            lineage_id="lineage", step_id="verify", surface="ledger", symptom="blocked",
            evidence="confirmed", impact="cannot continue", boundary="event lifecycle", status="open",
        ),
        event(
            "blocker_transitioned", run_id=run_id, blocker_id=blocker_id,
            from_status="open", to_status="open", recovery_evidence="same run is not recovery",
        ),
    ]

    with pytest.raises(work_memory.WorkMemoryError, match="invalid-open-blocker-recovery"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events},
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


def test_backlog_reconciliation_can_close_stranded_verified_correction():
    base = corrected_successor_events()
    start_a, opened, correction, transition, awaiting, close_a = base[:6]
    start_b, verification, _, _, close_b = base[6:]
    reconciliation_run_id = str(uuid.uuid4())
    reconciliation_start = event(
        "run_started", run_id=reconciliation_run_id,
        subject_id="blocker-backlog-reconciliation",
        lineage_id="blocker-backlog-reconciliation",
        mode="registered", operation_kind="other", source_bundle=[],
        source_bundle_hash="4" * 64, classification_receipt_hash="5" * 64,
        selection_receipt_hash="6" * 64,
        started_at_utc="2026-01-01T00:04:00Z",
    )
    verified = event(
        "blocker_transitioned", run_id=reconciliation_run_id,
        blocker_id=opened["blocker_id"],
        from_status="fixed-awaiting-verification", to_status="verified",
        verification_event_id=verification["event_id"],
        reconciliation_basis_event_id=verification["event_id"],
    )
    closed = event(
        "blocker_transitioned", run_id=reconciliation_run_id,
        blocker_id=opened["blocker_id"], from_status="verified",
        to_status="closed", verification_event_id=verification["event_id"],
        reconciliation_basis_event_id=verification["event_id"],
        remaining_work="none",
    )

    work_memory.stage_event_batch(
        b"",
        {
            "schema_version": 1,
            "expected_ledger_hash": None,
            "events": [
                start_a, opened, correction, transition, awaiting, close_a,
                start_b, verification, close_b, reconciliation_start,
                verified, closed,
            ],
        },
    )


def test_only_registered_backlog_reconciliation_can_reuse_historical_verification():
    base = corrected_successor_events()
    start_a, opened, correction, transition, awaiting, close_a = base[:6]
    start_b, verification, _, _, close_b = base[6:]
    unrelated_run_id = str(uuid.uuid4())
    unrelated_start = event(
        "run_started", run_id=unrelated_run_id, subject_id="unrelated-sequence",
        lineage_id="unrelated-sequence", mode="registered",
        operation_kind="other", source_bundle=[], source_bundle_hash="4" * 64,
        classification_receipt_hash="5" * 64,
        selection_receipt_hash="6" * 64,
        started_at_utc="2026-01-01T00:04:00Z",
    )
    forged = event(
        "blocker_transitioned", run_id=unrelated_run_id,
        blocker_id=opened["blocker_id"],
        from_status="fixed-awaiting-verification", to_status="verified",
        verification_event_id=verification["event_id"],
        reconciliation_basis_event_id=verification["event_id"],
    )

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="invalid-blocker-reconciliation-authority",
    ):
        work_memory.stage_event_batch(
            b"",
            {
                "schema_version": 1,
                "expected_ledger_hash": None,
                "events": [
                    start_a, opened, correction, transition, awaiting, close_a,
                    start_b, verification, close_b, unrelated_start, forged,
                ],
            },
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


def _large_source_bundle(size: int) -> list[dict[str, str]]:
    return [
        {
            "repository_key": "memory-knowledge",
            "path": f"scripts/generated-{index:04d}.py",
            "sha256": f"{index:064x}",
        }
        for index in range(size)
    ]


def test_run_started_accepts_authenticated_source_bundle_above_generic_array_limit():
    start = run_events(0)[0]
    start["source_bundle"] = _large_source_bundle(101)
    start["source_bundle_hash"] = work_memory.sha256_bytes(
        work_memory.canonical_bytes(start["source_bundle"])
    )

    work_memory._validate_event_shape(start)
    assert work_memory.parse_ledger_bytes(
        work_memory.canonical_bytes(start) + b"\n"
    ) == [start]


def test_run_started_rejects_source_bundle_above_its_explicit_limit():
    start = run_events(0)[0]
    start["source_bundle"] = _large_source_bundle(
        work_memory.SOURCE_BUNDLE_MAX_ITEMS + 1
    )

    with pytest.raises(
        work_memory.WorkMemoryError,
        match=r"work-memory-array-too-large:\$\.source_bundle",
    ):
        work_memory._validate_event_shape(start)


def test_work_only_validator_keeps_generic_array_limit():
    with pytest.raises(
        work_memory.WorkMemoryError,
        match=r"work-memory-array-too-large:\$\.items",
    ):
        work_memory._validate_work_only(
            {"items": list(range(work_memory.WORK_MEMORY_ARRAY_MAX_ITEMS + 1))}
        )


def _observer_decision(evidence_count: int) -> dict:
    return event(
        "observer_decision_recorded",
        decision_id=str(uuid.uuid4()), observer_version=1, rule_version=1,
        config_hash="1" * 64, trigger_event_id=str(uuid.uuid4()),
        trigger_type="run_closed", ledger_snapshot_hash="2" * 64,
        evidence_event_ids=[str(uuid.uuid4()) for _ in range(evidence_count)],
        evidence_set_hash="3" * 64, candidate_identity=None,
        candidate_fingerprint=None,
        eligibility={"version": 1, "eligible": False, "triggers": [], "reasons": []},
        value_components=[], threshold=20, considered_registered_ids=[],
        considered_discovery_ids=[], disposition="NO_CANDIDATE",
        target_kind=None, target_id=None,
        suppression={
            "rule_version": 1, "suppressed": False, "reason": None,
            "expires_at_utc": None,
        },
        cap_cursor=None, safe_failure_code="CAP_REACHED",
    )


def test_observer_decision_evidence_uses_explicit_bounded_limit():
    work_memory._validate_event_shape(_observer_decision(512))

    with pytest.raises(
        work_memory.WorkMemoryError,
        match=r"work-memory-array-too-large:\$\.evidence_event_ids",
    ):
        work_memory._validate_event_shape(_observer_decision(513))


@pytest.mark.parametrize("bundle,error", [
    ([{"repository_key": "memory-knowledge", "path": "scripts/a.py"}],
     "invalid-source-bundle-entry"),
    (_large_source_bundle(1) * 2, "duplicate-source-bundle-entry"),
])
def test_run_started_rejects_invalid_source_bundle_entries(bundle, error):
    start = run_events(0)[0]
    start["source_bundle"] = bundle

    with pytest.raises(work_memory.WorkMemoryError, match=error):
        work_memory._validate_event_shape(start)


def test_transact_commits_ledger_and_generated_view(tmp_path: Path):
    ledger, view = tmp_path / "events.jsonl", tmp_path / "BLOCKERS.md"
    work_memory.LEDGER = ledger
    work_memory.BLOCKER_VIEW = view
    task_id = "transact-task"
    state = work_memory._claim_task_writer(task_id)
    records = run_events(0)
    records[0].update(
        task_id=task_id,
        **work_memory._ownership_receipt_fields(task_id, state),
    )
    result = work_memory.transact(
        {"schema_version": 1, "expected_ledger_hash": None, "events": records}, ledger, view
    )
    assert result["ledger_hash"] == work_memory.sha256_bytes(ledger.read_bytes())
    assert f"Ledger-SHA256: `{result['ledger_hash']}`" in view.read_text()


def test_custom_ledger_cannot_default_to_the_canonical_blocker_view(tmp_path: Path):
    custom_ledger = tmp_path / "custom-events.jsonl"
    canonical_before = (
        work_memory.BLOCKER_VIEW.read_bytes()
        if work_memory.BLOCKER_VIEW.is_file() else None
    )
    with pytest.raises(
        work_memory.WorkMemoryError, match="ledger-view-authority-mismatch",
    ):
        work_memory.transact(
            {"schema_version": 1, "expected_ledger_hash": None, "events": []},
            ledger=custom_ledger,
        )
    assert not custom_ledger.exists()
    assert (
        work_memory.BLOCKER_VIEW.read_bytes()
        if work_memory.BLOCKER_VIEW.is_file() else None
    ) == canonical_before


def test_merge_and_repair_require_an_explicit_custom_ledger_view_pair(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    source.write_bytes(b"")
    custom_ledger = tmp_path / "custom-events.jsonl"
    canonical_before = (
        work_memory.BLOCKER_VIEW.read_bytes()
        if work_memory.BLOCKER_VIEW.is_file() else None
    )
    with pytest.raises(
        work_memory.WorkMemoryError, match="ledger-view-authority-mismatch",
    ):
        work_memory.cmd_merge_ledger(SimpleNamespace(
            source_ledger=str(source), ledger=str(custom_ledger), view=None,
        ))
    with pytest.raises(
        work_memory.WorkMemoryError, match="ledger-view-authority-mismatch",
    ):
        work_memory.cmd_repair_view(SimpleNamespace(
            ledger=str(custom_ledger), view=None,
        ))
    assert (
        work_memory.BLOCKER_VIEW.read_bytes()
        if work_memory.BLOCKER_VIEW.is_file() else None
    ) == canonical_before


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


def _owned_run_start(task_id: str, state: dict[str, object]) -> dict[str, object]:
    return event(
        "run_started", run_id=str(uuid.uuid4()), subject_id="sequence",
        lineage_id="lineage", mode="discovery", operation_kind="other",
        source_bundle=[], source_bundle_hash="a" * 64,
        classification_receipt_hash="b" * 64,
        selection_receipt_hash="c" * 64,
        started_at_utc="2026-01-01T00:00:00Z",
        task_id=task_id,
        **work_memory._ownership_receipt_fields(task_id, state),
    )


def test_pre_run_blocker_open_is_bound_to_current_task_writer_ownership(
    monkeypatch: pytest.MonkeyPatch,
):
    task_id = "selection-blocked-task"
    state = work_memory._claim_task_writer(task_id)
    opened = event(
        "pre_run_blocker_opened", task_id=task_id,
        ownership_event_id=state["ownership_event_id"],
        blocker_id="blk-" + "1" * 24, occurrence_id=str(uuid.uuid4()),
        fingerprint="2" * 64, subject_id=task_id, lineage_id=task_id,
        step_id="select", surface="registry", symptom="selection blocked",
        evidence="source hash drift", impact="no run can start",
        boundary="owner source binding", status="open",
    )

    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [opened],
    })
    assert work_memory.parse_ledger_bytes(work_memory.LEDGER.read_bytes())[-1] == opened

    other_task = "different-task"
    other_state = work_memory._claim_task_writer(other_task)
    rejected = {
        **opened, "event_id": str(uuid.uuid4()), "blocker_id": "blk-" + "3" * 24,
        "occurrence_id": str(uuid.uuid4()), "ownership_event_id": other_state["ownership_event_id"],
    }
    with pytest.raises(work_memory.WorkMemoryError, match="pre-run-blocker-ownership-mismatch"):
        work_memory.transact({
            "schema_version": 1, "expected_ledger_hash": None, "events": [rejected],
        })


def test_pre_run_blocker_lifecycle_requires_bound_correction_and_same_command_verification():
    task_id = "selection-blocked-task"
    ownership_event_id = str(uuid.uuid4())
    blocker_id = "blk-" + "4" * 24
    occurrence_id = str(uuid.uuid4())
    correction_id = str(uuid.uuid4())
    opened = event(
        "pre_run_blocker_opened", task_id=task_id,
        ownership_event_id=ownership_event_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, fingerprint="5" * 64,
        subject_id=task_id, lineage_id=task_id, step_id="select",
        surface="registry", symptom="selection blocked", evidence="hash drift",
        impact="no run", boundary="owner source binding", status="open",
    )
    correction = event(
        "pre_run_correction_recorded", task_id=task_id,
        ownership_event_id=ownership_event_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, correction_id=correction_id,
        step_id="select", changed_artifacts=["scripts/work_memory.py"],
        changed_artifact_hashes=["6" * 64], solution="refresh owner binding",
        reusable_behavior_changed=True,
    )
    fixed = event(
        "pre_run_blocker_transitioned", task_id=task_id,
        ownership_event_id=ownership_event_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, from_status="open",
        to_status="fixed-awaiting-verification",
    )
    verification = event(
        "pre_run_verification_recorded", task_id=task_id,
        ownership_event_id=ownership_event_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, correction_id=correction_id,
        verification_command="python3 scripts/work_memory.py select --task-id selection-blocked-task",
        outcome="passed", quality="same-command",
        evidence="original drift cleared; selector reached ordinary ambiguity",
        changed_artifact_hashes=["6" * 64],
    )
    verified = event(
        "pre_run_blocker_transitioned", task_id=task_id,
        ownership_event_id=ownership_event_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, from_status="fixed-awaiting-verification",
        to_status="verified", verification_event_id=verification["event_id"],
    )
    closed = event(
        "pre_run_blocker_transitioned", task_id=task_id,
        ownership_event_id=ownership_event_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, from_status="verified", to_status="closed",
        verification_event_id=verification["event_id"], remaining_work="none",
    )

    work_memory.validate_lifecycle([opened, correction, fixed, verification, verified, closed])

    with pytest.raises(work_memory.WorkMemoryError, match="invalid-pre-run-transition-verification"):
        work_memory.validate_lifecycle([opened, correction, fixed, verified])


def test_pre_run_blocker_lifecycle_transacts_under_task_ownership():
    task_id = "selection-blocked-task"
    state = work_memory._claim_task_writer(task_id)
    blocker_id = "blk-" + "7" * 24
    occurrence_id = str(uuid.uuid4())
    correction_id = str(uuid.uuid4())
    opened = event(
        "pre_run_blocker_opened", task_id=task_id,
        ownership_event_id=state["ownership_event_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, fingerprint="8" * 64,
        subject_id=task_id, lineage_id=task_id, step_id="select",
        surface="registry", symptom="selection blocked", evidence="hash drift",
        impact="no run", boundary="owner source binding", status="open",
    )
    work_memory.transact({"schema_version": 1, "expected_ledger_hash": None, "events": [opened]})
    correction = event(
        "pre_run_correction_recorded", task_id=task_id,
        ownership_event_id=state["ownership_event_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, correction_id=correction_id, step_id="select",
        changed_artifacts=["scripts/work_memory.py"],
        changed_artifact_hashes=["9" * 64], solution="refresh owner binding",
        reusable_behavior_changed=True,
    )
    fixed = event(
        "pre_run_blocker_transitioned", task_id=task_id,
        ownership_event_id=state["ownership_event_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, from_status="open",
        to_status="fixed-awaiting-verification",
    )
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None,
        "events": [correction, fixed],
    })
    verification = event(
        "pre_run_verification_recorded", task_id=task_id,
        ownership_event_id=state["ownership_event_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, correction_id=correction_id,
        verification_command="python3 scripts/work_memory.py select --task-id selection-blocked-task",
        outcome="passed", quality="same-command", evidence="original drift cleared",
        changed_artifact_hashes=["9" * 64],
    )
    verified = event(
        "pre_run_blocker_transitioned", task_id=task_id,
        ownership_event_id=state["ownership_event_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, from_status="fixed-awaiting-verification",
        to_status="verified", verification_event_id=verification["event_id"],
    )
    closed = event(
        "pre_run_blocker_transitioned", task_id=task_id,
        ownership_event_id=state["ownership_event_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, from_status="verified", to_status="closed",
        verification_event_id=verification["event_id"], remaining_work="none",
    )
    work_memory.transact({"schema_version": 1, "expected_ledger_hash": None, "events": [verification]})
    work_memory.transact({"schema_version": 1, "expected_ledger_hash": None, "events": [verified]})
    work_memory.transact({"schema_version": 1, "expected_ledger_hash": None, "events": [closed]})

    assert f"## {blocker_id}" in work_memory.BLOCKER_VIEW.read_text()
    assert "- Status: `closed`" in work_memory.BLOCKER_VIEW.read_text()


def test_same_writer_mutates_owned_run_and_other_writer_cannot(
    monkeypatch: pytest.MonkeyPatch,
):
    state = work_memory._claim_task_writer("owned-task")
    start = _owned_run_start("owned-task", state)
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [start],
    })
    before = work_memory.LEDGER.read_bytes()
    terminal = event(
        "run_abandoned", run_id=start["run_id"], subject_id="sequence",
        lineage_id="lineage", completed_at_utc="2026-01-01T00:01:00Z",
        reason="bounded stop",
    )

    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        work_memory.transact({
            "schema_version": 1, "expected_ledger_hash": None, "events": [terminal],
        })
    assert work_memory.LEDGER.read_bytes() == before

    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_A)
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [terminal],
    })
    assert work_memory.parse_ledger_bytes(work_memory.LEDGER.read_bytes())[-1] == terminal


def test_foreign_task_cannot_mutate_an_existing_blocker_lineage(
    monkeypatch: pytest.MonkeyPatch,
):
    state_a = work_memory._claim_task_writer("blocker-task-a")
    start_a = _owned_run_start("blocker-task-a", state_a)
    blocker_id = "blk-" + "1" * 24
    occurrence_id = str(uuid.uuid4())
    opened = event(
        "blocker_opened", run_id=start_a["run_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, fingerprint="d" * 64,
        subject_id="sequence", lineage_id="lineage", step_id="owned-step",
        surface="work-memory", symptom="shared mutation", evidence="captured",
        impact="wrong task can change blocker", boundary="writer ownership",
        status="open",
    )
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None,
        "events": [start_a, opened],
    })

    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    state_b = work_memory._claim_task_writer("blocker-task-b")
    start_b = _owned_run_start("blocker-task-b", state_b)
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [start_b],
    })
    before = work_memory.LEDGER.read_bytes()
    correction = event(
        "correction_recorded", run_id=start_b["run_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, correction_id=str(uuid.uuid4()),
        subject_id="sequence", lineage_id="lineage", step_id="owned-step",
        changed_artifacts=["scripts/work_memory.py"],
        changed_artifact_hashes=["e" * 64], reusable_behavior_changed=True,
        solution="foreign mutation must be rejected",
    )
    with pytest.raises(
        work_memory.WorkMemoryError, match="cross-task-blocker-mutation",
    ):
        work_memory.transact({
            "schema_version": 1, "expected_ledger_hash": None,
            "events": [correction],
        })
    assert work_memory.LEDGER.read_bytes() == before


def test_owned_recovery_adopts_matching_legacy_open_blocker(
    monkeypatch: pytest.MonkeyPatch,
):
    legacy_run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    occurrence_id = str(uuid.uuid4())
    legacy = [
        event(
            "run_started", run_id=legacy_run_id, subject_id="sequence", lineage_id="lineage",
            mode="discovery", operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash="a" * 64, classification_receipt_hash="1" * 64,
            selection_receipt_hash="2" * 64, started_at_utc="2026-01-01T00:00:00Z",
        ),
        event(
            "blocker_opened", run_id=legacy_run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, fingerprint="f" * 64, subject_id="sequence",
            lineage_id="lineage", step_id="verify", surface="ledger", symptom="blocked",
            evidence="confirmed", impact="cannot continue", boundary="event lifecycle", status="open",
        ),
        event(
            "run_closed", run_id=legacy_run_id, subject_id="sequence", lineage_id="lineage",
            result="failed", completed_at_utc="2026-01-01T00:01:00Z", correction_count=0,
            blocker_ids=[blocker_id], sequence_updated=False, verification_quality="none",
        ),
    ]
    work_memory.LEDGER.parent.mkdir(parents=True, exist_ok=True)
    work_memory.LEDGER.write_bytes(
        b"".join(work_memory.canonical_bytes(item) for item in legacy)
    )
    state = work_memory._claim_task_writer("recovery-task")
    recovery_start = _owned_run_start("recovery-task", state)
    recovery_start["subject_id"] = "sequence"
    recovery_start["lineage_id"] = "lineage"
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [recovery_start],
    })
    recovery = event(
        "blocker_transitioned", run_id=recovery_start["run_id"], blocker_id=blocker_id,
        from_status="open", to_status="open",
        recovery_evidence="adopt the legacy blocker into its matching active task",
    )

    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [recovery],
    })
    correction = event(
        "correction_recorded", run_id=recovery_start["run_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, correction_id=str(uuid.uuid4()),
        subject_id="sequence", lineage_id="lineage", step_id="verify",
        changed_artifacts=["scripts/work_memory.py"], changed_artifact_hashes=["e" * 64],
        reusable_behavior_changed=True, solution="repair the stable boundary",
    )
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [correction],
    })

    assert work_memory.parse_ledger_bytes(work_memory.LEDGER.read_bytes())[-2:] == [
        recovery, correction,
    ]


def test_successor_selection_must_keep_the_predecessor_task_identity():
    state = work_memory._claim_task_writer("predecessor-task")
    start = _owned_run_start("predecessor-task", state)
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [start],
    })
    events, _ = work_memory.load_ledger()

    work_memory._require_predecessor_task_ownership(
        events, start["run_id"], "predecessor-task",
    )
    with pytest.raises(
        work_memory.WorkMemoryError, match="cross-task-successor-selection",
    ):
        work_memory._require_predecessor_task_ownership(
            events, start["run_id"], "foreign-task",
        )


def test_direct_successor_selection_derives_task_identity_before_core_selection(
    monkeypatch: pytest.MonkeyPatch,
):
    predecessor_run_id = str(uuid.uuid4())
    monkeypatch.setattr(work_memory, "load_ledger", lambda: ([], "a" * 64))
    monkeypatch.setattr(
        work_memory,
        "_successor_selection_request",
        lambda _events, run_id: {
            "task_id": "predecessor-task",
            "sequence_id": "workflow-resume-from-phase-live-confirmation",
            "verification_successor_of": run_id,
            "verifies_correction_ids": [str(uuid.uuid4())],
            "repository_roots": {
                "memory-knowledge": "/repos/memory",
                "united-partners": "/repos/up",
            },
        },
    )
    observed = {}
    monkeypatch.setattr(
        work_memory,
        "_cmd_select_for_task",
        lambda args: (
            observed.update(task_id=args.task_id)
            or {"ok": True, "task_id": args.task_id}
        ),
        raising=False,
    )

    result = work_memory.cmd_select(
        SimpleNamespace(
            task_id="wrong-new-task",
            verification_successor_of=predecessor_run_id,
        )
    )

    assert observed["task_id"] == "predecessor-task"
    assert result["task_id"] == "predecessor-task"
    assert result["requested_task_id"] == "wrong-new-task"
    assert result["task_identity_source"] == "predecessor-run"


def test_select_successor_parser_requires_only_predecessor_run_id():
    args = work_memory.build_parser().parse_args([
        "select-successor",
        "--predecessor-run-id", "11111111-1111-4111-8111-111111111111",
    ])

    assert args.func is work_memory.cmd_select_successor
    assert args.predecessor_run_id == "11111111-1111-4111-8111-111111111111"


def test_successor_request_derives_sequence_roots_and_active_corrections():
    state = work_memory._claim_task_writer("predecessor-task")
    start = _owned_run_start("predecessor-task", state)
    start.update({
        "mode": "registered",
        "subject_id": "workflow-resume-from-phase-live-confirmation",
        "repository_roots": {
            "memory-knowledge": "/repos/memory",
            "united-partners": "/repos/up",
        },
    })
    blocker_ids = ["blk-" + "1" * 24, "blk-" + "2" * 24]
    correction_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    occurrence_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    events = [start]
    for blocker_id, occurrence_id, correction_id in zip(
        blocker_ids, occurrence_ids, correction_ids, strict=True,
    ):
        events.extend([
            event(
                "blocker_opened", run_id=start["run_id"],
                blocker_id=blocker_id, occurrence_id=occurrence_id,
                fingerprint="f" * 64, subject_id=start["subject_id"],
                lineage_id=start["lineage_id"], step_id="verify",
                surface="phase20", symptom="blocked", evidence="captured",
                impact="cannot continue", boundary="correction", status="open",
            ),
            event(
                "correction_recorded", run_id=start["run_id"],
                blocker_id=blocker_id, occurrence_id=occurrence_id,
                correction_id=correction_id, subject_id=start["subject_id"],
                lineage_id=start["lineage_id"], step_id="verify",
                changed_artifacts=["scripts/work_memory.py"],
                changed_artifact_hashes=["e" * 64],
                reusable_behavior_changed=True, solution="stable fix",
            ),
            event(
                "blocker_transitioned", run_id=start["run_id"],
                blocker_id=blocker_id, from_status="open",
                to_status="fixed-awaiting-verification",
            ),
        ])
    events.extend([
        event(
            "bundle_transition_recorded", run_id=start["run_id"],
            lineage_id=start["lineage_id"],
            old_bundle_hash=start["source_bundle_hash"],
            new_bundle_hash="b" * 64,
            transition_reason="correction",
            correction_ids=correction_ids,
            changed_artifacts=["scripts/work_memory.py"],
            changed_artifact_hashes=["e" * 64],
        ),
        event(
            "run_closed", run_id=start["run_id"],
            subject_id=start["subject_id"], lineage_id=start["lineage_id"],
            result="failed", completed_at_utc="2026-01-01T00:01:00Z",
            correction_count=2, blocker_ids=blocker_ids,
            sequence_updated=True, verification_quality="none",
        ),
    ])

    request = work_memory._successor_selection_request(
        events, start["run_id"],
    )

    assert request == {
        "task_id": "predecessor-task",
        "sequence_id": "workflow-resume-from-phase-live-confirmation",
        "verification_successor_of": start["run_id"],
        "verifies_correction_ids": correction_ids,
        "repository_roots": start["repository_roots"],
    }


def test_successor_request_carries_inherited_and_new_corrections_cumulatively():
    task_id = "predecessor-task"
    state = work_memory._claim_task_writer(task_id)
    first_start = _owned_run_start(task_id, state)
    first_start.update({
        "mode": "registered",
        "subject_id": "workflow-resume-from-phase-live-confirmation",
        "repository_roots": {
            "memory-knowledge": "/repos/memory",
            "united-partners": "/repos/up",
        },
    })
    first_blocker_id = "blk-" + "1" * 24
    first_occurrence_id = str(uuid.uuid4())
    first_correction_id = str(uuid.uuid4())
    first_transition_hash = "b" * 64
    second_run_id = str(uuid.uuid4())
    second_blocker_id = "blk-" + "2" * 24
    second_occurrence_id = str(uuid.uuid4())
    second_correction_id = str(uuid.uuid4())
    events = [
        first_start,
        event(
            "blocker_opened", run_id=first_start["run_id"],
            blocker_id=first_blocker_id,
            occurrence_id=first_occurrence_id, fingerprint="1" * 64,
            subject_id=first_start["subject_id"],
            lineage_id=first_start["lineage_id"], step_id="phase-20",
            surface="strategy", symptom="blocked", evidence="captured",
            impact="cannot continue", boundary="phase-20", status="open",
        ),
        event(
            "correction_recorded", run_id=first_start["run_id"],
            blocker_id=first_blocker_id,
            occurrence_id=first_occurrence_id,
            correction_id=first_correction_id,
            subject_id=first_start["subject_id"],
            lineage_id=first_start["lineage_id"], step_id="phase-20",
            changed_artifacts=["scripts/phase20.py"],
            changed_artifact_hashes=["1" * 64],
            reusable_behavior_changed=True, solution="fix phase 20",
        ),
        event(
            "bundle_transition_recorded", run_id=first_start["run_id"],
            lineage_id=first_start["lineage_id"],
            old_bundle_hash=first_start["source_bundle_hash"],
            new_bundle_hash=first_transition_hash,
            transition_reason="correction",
            correction_ids=[first_correction_id],
            changed_artifacts=["scripts/phase20.py"],
            changed_artifact_hashes=["1" * 64],
        ),
        event(
            "blocker_transitioned", run_id=first_start["run_id"],
            blocker_id=first_blocker_id, from_status="open",
            to_status="fixed-awaiting-verification",
        ),
        event(
            "run_closed", run_id=first_start["run_id"],
            subject_id=first_start["subject_id"],
            lineage_id=first_start["lineage_id"], result="failed",
            completed_at_utc="2026-01-01T00:01:00Z",
            correction_count=1, blocker_ids=[first_blocker_id],
            sequence_updated=True, verification_quality="none",
        ),
        event(
            "run_started", run_id=second_run_id,
            subject_id=first_start["subject_id"],
            lineage_id=first_start["lineage_id"], mode="registered",
            operation_kind=first_start["operation_kind"],
            source_bundle=first_start["source_bundle"],
            source_bundle_hash=first_transition_hash,
            classification_receipt_hash="3" * 64,
            selection_receipt_hash="4" * 64,
            started_at_utc="2026-01-01T00:02:00Z",
            predecessor_run_id=first_start["run_id"],
            verifies_correction_ids=[first_correction_id],
            repository_roots=first_start["repository_roots"],
            task_id=task_id,
            **work_memory._ownership_receipt_fields(task_id, state),
        ),
        event(
            "blocker_opened", run_id=second_run_id,
            blocker_id=second_blocker_id,
            occurrence_id=second_occurrence_id, fingerprint="2" * 64,
            subject_id=first_start["subject_id"],
            lineage_id=first_start["lineage_id"], step_id="controller",
            surface="sequence", symptom="blocked", evidence="captured",
            impact="cannot continue", boundary="sequence contract",
            status="open",
        ),
        event(
            "correction_recorded", run_id=second_run_id,
            blocker_id=second_blocker_id,
            occurrence_id=second_occurrence_id,
            correction_id=second_correction_id,
            subject_id=first_start["subject_id"],
            lineage_id=first_start["lineage_id"], step_id="controller",
            changed_artifacts=["operations/sequences/resume/sequence.md"],
            changed_artifact_hashes=["2" * 64],
            reusable_behavior_changed=True, solution="fix sequence contract",
        ),
        event(
            "bundle_transition_recorded", run_id=second_run_id,
            lineage_id=first_start["lineage_id"],
            old_bundle_hash=first_transition_hash,
            new_bundle_hash="c" * 64,
            transition_reason="correction",
            correction_ids=[second_correction_id],
            changed_artifacts=["operations/sequences/resume/sequence.md"],
            changed_artifact_hashes=["2" * 64],
        ),
        event(
            "blocker_transitioned", run_id=second_run_id,
            blocker_id=second_blocker_id, from_status="open",
            to_status="fixed-awaiting-verification",
        ),
        event(
            "run_closed", run_id=second_run_id,
            subject_id=first_start["subject_id"],
            lineage_id=first_start["lineage_id"], result="failed",
            completed_at_utc="2026-01-01T00:03:00Z",
            correction_count=1,
            blocker_ids=[first_blocker_id, second_blocker_id],
            sequence_updated=True, verification_quality="none",
        ),
    ]

    request = work_memory._successor_selection_request(
        events, second_run_id,
    )

    assert request["verifies_correction_ids"] == [
        first_correction_id,
        second_correction_id,
    ]


def test_effective_correction_bundle_seeds_successor_inherited_corrections():
    inherited_correction_id = str(uuid.uuid4())
    start = event(
        "run_started",
        source_bundle=[],
        source_bundle_hash="a" * 64,
        verifies_correction_ids=[inherited_correction_id],
    )

    _, bundle_hash, correction_ids = work_memory._effective_correction_bundle(
        start,
        [],
    )

    assert bundle_hash == "a" * 64
    assert correction_ids == [inherited_correction_id]


def test_successor_validation_carries_inherited_correction_across_overlap(
    tmp_path: Path,
):
    artifact = tmp_path / "scripts/phase20.py"
    artifact.parent.mkdir()
    artifact.write_text("new combined behavior\n")
    controller = tmp_path / "scripts/work_memory.py"
    controller.write_text("corrected selector\n")
    sequence = tmp_path / "operations/sequences/resume/sequence.md"
    sequence.parent.mkdir(parents=True)
    sequence.write_text("unchanged sequence\n")
    old_correction_id = str(uuid.uuid4())
    new_correction_id = str(uuid.uuid4())
    predecessor_run_id = str(uuid.uuid4())
    ownership_event_id = str(uuid.uuid4())
    ownership_state = {
        "writer_thread_id": str(uuid.uuid4()),
        "ownership_generation": 1,
        "ownership_event_id": ownership_event_id,
    }
    pre_run_blocker_id = "blk-" + "6" * 24
    pre_run_occurrence_id = str(uuid.uuid4())
    pre_run_correction_id = str(uuid.uuid4())
    old_blocker_id = "blk-" + "4" * 24
    new_blocker_id = "blk-" + "5" * 24
    old_hash = "1" * 64
    new_hash = work_memory.sha256_bytes(artifact.read_bytes())
    controller_hash = work_memory.sha256_bytes(controller.read_bytes())
    sequence_hash = work_memory.sha256_bytes(sequence.read_bytes())
    current_bundle = [
        {
            "repository_key": "memory-knowledge",
            "path": "scripts/phase20.py",
            "sha256": new_hash,
        },
        {
            "repository_key": "memory-knowledge",
            "path": "scripts/work_memory.py",
            "sha256": controller_hash,
        },
        {
            "repository_key": "memory-knowledge",
            "path": "operations/sequences/resume/sequence.md",
            "sha256": sequence_hash,
        },
    ]
    current_bundle_hash = work_memory.sha256_bytes(
        work_memory.canonical_bytes(current_bundle)
    )
    pre_controller_bundle = [
        current_bundle[0],
        {**current_bundle[1], "sha256": "2" * 64},
    ]
    pre_controller_bundle_hash = work_memory.sha256_bytes(
        work_memory.canonical_bytes(pre_controller_bundle)
    )
    events = [
        event(
            "task_writer_claimed",
            event_id=ownership_event_id,
            task_id="task",
            writer_thread_id=ownership_state["writer_thread_id"],
            ownership_generation=1,
        ),
        event(
            "run_started",
            run_id=str(uuid.uuid4()),
            lineage_id="lineage",
            source_bundle=[],
            source_bundle_hash="a" * 64,
        ),
        event(
            "blocker_opened",
            run_id=str(uuid.uuid4()),
            blocker_id=old_blocker_id,
            occurrence_id=str(uuid.uuid4()),
            lineage_id="lineage",
        ),
        event(
            "correction_recorded",
            correction_id=old_correction_id,
            blocker_id=old_blocker_id,
            occurrence_id=str(uuid.uuid4()),
            lineage_id="lineage",
            changed_artifacts=["scripts/phase20.py"],
            changed_artifact_hashes=[old_hash],
        ),
        event(
            "bundle_transition_recorded",
            run_id=str(uuid.uuid4()),
            lineage_id="lineage",
            transition_reason="correction",
            correction_ids=[old_correction_id],
            new_bundle_hash="b" * 64,
        ),
        event(
            "blocker_transitioned",
            blocker_id=old_blocker_id,
            to_status="fixed-awaiting-verification",
        ),
        event(
            "run_started",
            run_id=predecessor_run_id,
            lineage_id="lineage",
            source_bundle=[{
                "repository_key": "memory-knowledge",
                "path": "scripts/phase20.py",
                "sha256": old_hash,
            }, {
                "repository_key": "memory-knowledge",
                "path": "scripts/work_memory.py",
                "sha256": "2" * 64,
            }, {
                "repository_key": "memory-knowledge",
                "path": "operations/sequences/resume/sequence.md",
                "sha256": sequence_hash,
            }],
            source_bundle_hash="b" * 64,
            verifies_correction_ids=[old_correction_id],
            task_id="task",
            **work_memory._ownership_receipt_fields(
                "task",
                ownership_state,
            ),
        ),
        event(
            "blocker_opened",
            run_id=predecessor_run_id,
            blocker_id=new_blocker_id,
            occurrence_id=str(uuid.uuid4()),
            lineage_id="lineage",
        ),
        event(
            "correction_recorded",
            correction_id=new_correction_id,
            blocker_id=new_blocker_id,
            occurrence_id=str(uuid.uuid4()),
            lineage_id="lineage",
            changed_artifacts=["scripts/phase20.py"],
            changed_artifact_hashes=[new_hash],
        ),
        event(
            "bundle_transition_recorded",
            run_id=predecessor_run_id,
            lineage_id="lineage",
            transition_reason="correction",
            correction_ids=[new_correction_id],
            old_bundle_hash="b" * 64,
            new_bundle_hash=pre_controller_bundle_hash,
            changed_artifacts=["scripts/phase20.py"],
            changed_artifact_hashes=[new_hash],
        ),
        event(
            "blocker_transitioned",
            blocker_id=new_blocker_id,
            to_status="fixed-awaiting-verification",
        ),
        event(
            "run_closed",
            run_id=predecessor_run_id,
        ),
        event(
            "pre_run_blocker_opened",
            task_id="task",
            ownership_event_id=ownership_event_id,
            blocker_id=pre_run_blocker_id,
            occurrence_id=pre_run_occurrence_id,
            lineage_id="lineage",
        ),
        event(
            "pre_run_correction_recorded",
            task_id="task",
            ownership_event_id=ownership_event_id,
            blocker_id=pre_run_blocker_id,
            occurrence_id=pre_run_occurrence_id,
            correction_id=pre_run_correction_id,
            changed_artifacts=["scripts/work_memory.py"],
            changed_artifact_hashes=[controller_hash],
        ),
        event(
            "pre_run_blocker_transitioned",
            blocker_id=pre_run_blocker_id,
            to_status="closed",
        ),
        event(
            "pre_run_blocker_opened",
            task_id="task",
            ownership_event_id=ownership_event_id,
            blocker_id="blk-" + "7" * 24,
            occurrence_id=str(uuid.uuid4()),
            lineage_id="lineage",
        ),
        event(
            "pre_run_correction_recorded",
            task_id="task",
            ownership_event_id=ownership_event_id,
            blocker_id="blk-" + "7" * 24,
            occurrence_id=str(uuid.uuid4()),
            correction_id=str(uuid.uuid4()),
            changed_artifacts=[
                "operations/sequences/resume/sequence.md",
            ],
            changed_artifact_hashes=[sequence_hash],
        ),
        event(
            "pre_run_blocker_transitioned",
            blocker_id="blk-" + "7" * 24,
            to_status="closed",
        ),
    ]
    old_correction = next(
        row for row in events
        if row.get("correction_id") == old_correction_id
    )
    old_opened = next(
        row for row in events
        if row.get("blocker_id") == old_blocker_id
        and row["event_type"] == "blocker_opened"
    )
    old_correction["occurrence_id"] = old_opened["occurrence_id"]
    new_correction = next(
        row for row in events
        if row.get("correction_id") == new_correction_id
    )
    new_opened = next(
        row for row in events
        if row.get("blocker_id") == new_blocker_id
        and row["event_type"] == "blocker_opened"
    )
    new_correction["occurrence_id"] = new_opened["occurrence_id"]

    work_memory._validate_successor_corrections(
        events,
        lineage_id="lineage",
        source_bundle=current_bundle,
        source_bundle_hash=current_bundle_hash,
        predecessor_run_id=predecessor_run_id,
        correction_ids=[old_correction_id, new_correction_id],
        repository_roots={"memory-knowledge": str(tmp_path)},
    )


def test_different_task_ids_allow_different_writers(
    monkeypatch: pytest.MonkeyPatch,
):
    first = work_memory._claim_task_writer("task-a")
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    second = work_memory._claim_task_writer("task-b")

    assert first["writer_thread_id"] == WRITER_A
    assert second["writer_thread_id"] == WRITER_B
    tasks, _ = work_memory._ownership_snapshot(
        work_memory.parse_ledger_bytes(work_memory.LEDGER.read_bytes()),
    )
    assert tasks["task-a"]["writer_thread_id"] == WRITER_A
    assert tasks["task-b"]["writer_thread_id"] == WRITER_B


def test_foreign_writer_cannot_select_or_create_a_selection_receipt(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    work_memory.cmd_classify(Namespace(
        task_id="foreign-selection", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        work_memory.cmd_select(Namespace(
            task_id="foreign-selection", sequence_id=None, discovery_log=None,
            fingerprint=None, verification_successor_of=None,
            verifies_correction_id=None, repo_roots_file=None,
        ))
    assert not work_memory.receipt_path("foreign-selection", "selection").exists()


def test_owner_handoff_invalidates_old_owner_and_enables_new_owner(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    work_memory.cmd_classify(Namespace(
        task_id="handoff-task", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    classification, _, _ = work_memory.load_receipt(
        "handoff-task", "classification",
    )
    result = work_memory.cmd_task_writer_handoff(Namespace(
        task_id="handoff-task", to_thread_id=WRITER_B, event_id=None,
    ))
    assert result["writer_thread_id"] == WRITER_B

    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        work_memory.validate_ownership_receipt("handoff-task", classification)

    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    work_memory.cmd_classify(Namespace(
        task_id="handoff-task", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    refreshed, _, _ = work_memory.load_receipt(
        "handoff-task", "classification",
    )
    work_memory.validate_ownership_receipt("handoff-task", refreshed)
    assert refreshed["ownership_generation"] == 2


def test_paused_old_owner_receipt_write_revalidates_after_handoff(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    work_memory.cmd_classify(Namespace(
        task_id="paused-writer", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    stale_payload, _, _ = work_memory.load_receipt(
        "paused-writer", "classification",
    )
    work_memory.cmd_task_writer_handoff(Namespace(
        task_id="paused-writer", to_thread_id=WRITER_B, event_id=None,
    ))
    current_bytes = work_memory.receipt_path(
        "paused-writer", "classification",
    ).read_bytes()

    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        work_memory.write_receipt(
            "paused-writer", "classification", stale_payload,
        )
    assert work_memory.receipt_path(
        "paused-writer", "classification",
    ).read_bytes() == current_bytes


def test_non_owner_cannot_handoff_and_ledger_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    work_memory._claim_task_writer("handoff-denied")
    before = work_memory.LEDGER.read_bytes()
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        work_memory.cmd_task_writer_handoff(Namespace(
            task_id="handoff-denied", to_thread_id=WRITER_A, event_id=None,
        ))
    assert work_memory.LEDGER.read_bytes() == before


def test_raw_handoff_cannot_bypass_receipt_rotation():
    from argparse import Namespace

    work_memory.cmd_classify(Namespace(
        task_id="handoff-refresh-bound", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    state = work_memory.require_task_writer("handoff-refresh-bound")
    before = work_memory.LEDGER.read_bytes()
    incomplete = event(
        "task_writer_handoff_recorded", task_id="handoff-refresh-bound",
        from_writer_thread_id=WRITER_A, to_writer_thread_id=WRITER_B,
        ownership_generation=state["ownership_generation"] + 1,
        previous_ownership_event_id=state["ownership_event_id"],
    )
    with pytest.raises(
        work_memory.WorkMemoryError, match="task-writer-handoff-refresh-mismatch",
    ):
        work_memory.transact({
            "schema_version": 1, "expected_ledger_hash": None,
            "events": [incomplete],
        })
    assert work_memory.LEDGER.read_bytes() == before


def test_missing_host_thread_id_rejects_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("CODEX_THREAD_ID")
    with pytest.raises(
        work_memory.WorkMemoryError, match="writer-identity-required",
    ):
        work_memory.transact({
            "schema_version": 1,
            "expected_ledger_hash": None,
            "events": [event(
                "task_writer_claimed", task_id="missing-host",
                writer_thread_id=WRITER_A, ownership_generation=1,
            )],
        })
    assert not work_memory.LEDGER.exists()


def test_prevention_only_transaction_does_not_require_host_thread_id_but_work_does(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("CODEX_THREAD_ID")
    prevention = event(
        "action_intent_recorded", task_id="task-123",
        run_id="4f642f31-f326-4b2c-92e4-753826ecad9f",
        branch_ref="task/task-123", worktree_id="a" * 64,
        intent_id=str(uuid.uuid4()), requested_sequence_id="discovery-bootstrap",
        requested_implementation_id="b" * 64, compatibility_key="c" * 64,
        action_class="BASH",
        parameters=[{"name": "spec", "value": {"tag": "PATH", "value": "spec.json"}}],
    )

    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None,
        "events": [prevention],
    })
    before = work_memory.LEDGER.read_bytes()
    with pytest.raises(
        work_memory.WorkMemoryError, match="writer-identity-required",
    ):
        work_memory.transact({
            "schema_version": 1, "expected_ledger_hash": None,
            "events": [event(
                "task_writer_claimed", task_id="work-task",
                writer_thread_id=WRITER_A, ownership_generation=1,
            )],
        })
    assert work_memory.LEDGER.read_bytes() == before


def test_non_run_observer_event_does_not_require_host_thread_id(
    monkeypatch: pytest.MonkeyPatch,
):
    records = owned_run_events(0, "observer-owner-task")
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": records,
    })
    terminal = records[-1]
    decision = event(
        "observer_decision_recorded", decision_id=str(uuid.uuid4()),
        observer_version=1, rule_version=1, config_hash="1" * 64,
        trigger_event_id=terminal["event_id"], trigger_type="run_closed",
        ledger_snapshot_hash="2" * 64, evidence_event_ids=[],
        evidence_set_hash="3" * 64, candidate_identity=None,
        candidate_fingerprint=None,
        eligibility={"version": 1, "eligible": False, "triggers": [], "reasons": []},
        value_components=[], threshold=1, considered_registered_ids=[],
        considered_discovery_ids=[], disposition="NO_CANDIDATE",
        target_kind=None, target_id=None,
        suppression={
            "rule_version": 1, "suppressed": False, "reason": None,
            "expires_at_utc": None,
        },
        cap_cursor=None, safe_failure_code="NO_ELIGIBLE_CANDIDATE",
    )
    monkeypatch.delenv("CODEX_THREAD_ID")

    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [decision],
    })
    assert work_memory.parse_ledger_bytes(work_memory.LEDGER.read_bytes())[-1] == decision


def test_atomic_claim_race_selects_exactly_one_writer(
    monkeypatch: pytest.MonkeyPatch,
):
    barrier = threading.Barrier(2)
    writers = {"writer-a": WRITER_A, "writer-b": WRITER_B}
    monkeypatch.setattr(
        work_memory, "host_thread_id",
        lambda: writers[threading.current_thread().name],
    )
    results: list[tuple[str, str]] = []

    def claim() -> None:
        barrier.wait()
        try:
            state = work_memory._claim_task_writer("raced-task")
            results.append(("ok", state["writer_thread_id"]))
        except work_memory.WorkMemoryError as exc:
            results.append(("error", exc.code))

    threads = [
        threading.Thread(target=claim, name="writer-a"),
        threading.Thread(target=claim, name="writer-b"),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [status for status, _ in results].count("ok") == 1
    assert [status for status, _ in results].count("error") == 1
    claims = [
        item for item in work_memory.parse_ledger_bytes(
            work_memory.LEDGER.read_bytes(),
        )
        if item["event_type"] == "task_writer_claimed"
        and item["task_id"] == "raced-task"
    ]
    assert len(claims) == 1


def _write_legacy_run(task_id: str = "legacy-task") -> tuple[str, str, str]:
    classification = {
        "schema_version": 1, "task_id": task_id, "operation_kind": "other",
        "repeatable": True, "meaningful_steps": 3, "verdict": "operational",
        "reason": "repeatable-or-multistep", "created_at_utc": "2026-01-01T00:00:00Z",
        "expires_at_utc": "2030-01-01T00:00:00Z",
    }
    classification_bytes = work_memory.canonical_bytes(classification)
    classification_path = work_memory.receipt_path(task_id, "classification")
    classification_path.parent.mkdir(parents=True, exist_ok=True)
    classification_path.write_bytes(classification_bytes)
    class_hash = work_memory.sha256_bytes(classification_bytes)
    selection = {
        "schema_version": 1, "task_id": task_id,
        "created_at_utc": "2026-01-01T00:00:00Z",
        "expires_at_utc": "2030-01-01T00:00:00Z",
        "classification_receipt_hash": class_hash, "registry_hash": "d" * 64,
        "mode": "discovery", "subject_id": "legacy-sequence",
        "lineage_id": "legacy-lineage", "document": "/tmp/legacy-sequence.md",
        "manifest": "/tmp/legacy-dependencies.json", "source_bundle": [],
        "source_bundle_hash": "a" * 64,
    }
    selection_bytes = work_memory.canonical_bytes(selection)
    work_memory.receipt_path(task_id, "selection").write_bytes(selection_bytes)
    selection_hash = work_memory.sha256_bytes(selection_bytes)
    active = {
        "schema_version": 1, "task_id": task_id, "mode": "discovery",
        "subject_id": "legacy-sequence", "lineage_id": "legacy-lineage",
        "document": str(Path("/tmp/legacy-sequence.md").resolve()),
        "source_bundle_hash": "a" * 64,
        "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash,
        "sealed_controller_b64": base64.b64encode(b"sealed controller").decode(),
        "sealed_bootstrap_b64": base64.b64encode(b"sealed bootstrap").decode(),
        "sealed_bootstrap_launcher_b64": base64.b64encode(b"sealed launcher").decode(),
    }
    active_path = work_memory.receipt_path(task_id, "active")
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_bytes(work_memory.canonical_bytes(active))
    run_id = str(uuid.uuid4())
    start = event(
        "run_started", run_id=run_id, subject_id="legacy-sequence",
        lineage_id="legacy-lineage", mode="discovery", operation_kind="other",
        source_bundle=[], source_bundle_hash="a" * 64,
        classification_receipt_hash=class_hash,
        selection_receipt_hash=selection_hash,
        started_at_utc="2026-01-01T00:00:00Z",
    )
    work_memory.LEDGER.parent.mkdir(parents=True, exist_ok=True)
    work_memory.LEDGER.write_bytes(work_memory.canonical_bytes(start))
    return run_id, class_hash, selection_hash


def test_legacy_run_claim_binds_owner_upgrades_receipts_and_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    run_id, old_class_hash, old_selection_hash = _write_legacy_run()
    first = work_memory.cmd_legacy_run_writer_claim(Namespace(
        task_id="legacy-task", run_id=run_id, event_id=None, state=None,
    ))
    events = work_memory.parse_ledger_bytes(work_memory.LEDGER.read_bytes())
    assert [item["event_type"] for item in events[-2:]] == [
        "task_writer_claimed", "legacy_run_writer_bound",
    ]
    binding = work_memory.validate_legacy_run_binding(
        events, "legacy-task", run_id, events[0],
        work_memory.load_receipt("legacy-task", "selection")[0],
    )
    assert binding["classification_receipt_hash"] == old_class_hash
    assert binding["selection_receipt_hash"] == old_selection_hash
    classification, class_hash, _ = work_memory.load_receipt(
        "legacy-task", "classification",
    )
    selection, selection_hash, _ = work_memory.load_receipt(
        "legacy-task", "selection",
    )
    work_memory.validate_ownership_receipt("legacy-task", classification)
    work_memory.validate_ownership_receipt("legacy-task", selection)
    active = json.loads(work_memory.receipt_path("legacy-task", "active").read_text())
    assert active["classification_receipt_hash"] == class_hash
    assert active["selection_receipt_hash"] == selection_hash
    assert active["sealed_controller_b64"] == base64.b64encode(b"sealed controller").decode()
    assert active["sealed_bootstrap_launcher_b64"] == base64.b64encode(
        b"sealed launcher",
    ).decode()

    before = work_memory.LEDGER.read_bytes()
    retry = work_memory.cmd_legacy_run_writer_claim(Namespace(
        task_id="legacy-task", run_id=run_id, event_id=None, state=None,
    ))
    assert work_memory.LEDGER.read_bytes() == before
    assert retry["legacy_run_writer_binding_event_id"] == first[
        "legacy_run_writer_binding_event_id"
    ]

    work_memory.cmd_task_writer_handoff(Namespace(
        task_id="legacy-task", to_thread_id=WRITER_B, event_id=None,
    ))
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    after_handoff = work_memory.cmd_legacy_run_writer_claim(Namespace(
        task_id="legacy-task", run_id=run_id, event_id=None, state=None,
    ))
    assert after_handoff["writer_thread_id"] == WRITER_B


def test_active_trust_snapshot_validation_requires_launcher_bytes_for_durable_state():
    snapshots = {
        "scripts/work_memory.py": b"controller\n",
        "scripts/work_memory_bootstrap.py": b"bootstrap\n",
        "scripts/work_memory_bootstrap_launcher.py": b"launcher\n",
    }
    selection = {
        "source_bundle": [
            {
                "repository_key": "memory-knowledge", "path": path,
                "sha256": work_memory.sha256_bytes(value),
            }
            for path, value in snapshots.items()
        ],
    }
    active = {
        "sealed_controller_sha256": work_memory.sha256_bytes(snapshots["scripts/work_memory.py"]),
        "sealed_controller_b64": base64.b64encode(snapshots["scripts/work_memory.py"]).decode(),
        "bootstrap_sha256": work_memory.sha256_bytes(
            snapshots["scripts/work_memory_bootstrap.py"],
        ),
        "sealed_bootstrap_b64": base64.b64encode(
            snapshots["scripts/work_memory_bootstrap.py"],
        ).decode(),
        "bootstrap_launcher_sha256": work_memory.sha256_bytes(
            snapshots["scripts/work_memory_bootstrap_launcher.py"],
        ),
        "sealed_bootstrap_launcher_b64": base64.b64encode(
            snapshots["scripts/work_memory_bootstrap_launcher.py"],
        ).decode(),
    }
    work_memory._validate_active_trust_snapshots(active, selection)
    legacy = {**active}
    del legacy["sealed_bootstrap_launcher_b64"]
    with pytest.raises(work_memory.WorkMemoryError, match="active-trust-snapshot-invalid"):
        work_memory._validate_active_trust_snapshots(legacy, selection)
    work_memory._validate_active_trust_snapshots(
        legacy, selection, allow_legacy_missing_launcher=True,
    )


def _write_active_owned_receipts(task_id: str) -> tuple[dict[str, object], str, str]:
    from argparse import Namespace

    classified = work_memory.cmd_classify(Namespace(
        task_id=task_id, operation_kind="other", repeatable="yes",
        meaningful_steps=3,
    ))
    classification, class_hash, _ = work_memory.load_receipt(task_id, "classification")
    ownership = {
        key: classification[key] for key in (
            "writer_thread_id", "ownership_generation", "ownership_event_id",
            "ownership_sha256",
        )
    }
    selection = {
        "schema_version": 1, "task_id": task_id,
        "created_at_utc": "2026-01-01T00:00:00Z",
        "expires_at_utc": "2030-01-01T00:00:00Z",
        "classification_receipt_hash": class_hash, "registry_hash": "d" * 64,
        "mode": "discovery", "subject_id": "sequence", "lineage_id": "lineage",
        "document": "/tmp/sequence.md", "manifest": "/tmp/dependencies.json",
        "source_bundle": [], "source_bundle_hash": "a" * 64, **ownership,
    }
    _, selection_hash = work_memory.write_receipt(task_id, "selection", selection)
    active = {
        "schema_version": 1, "task_id": task_id, "mode": "discovery",
        "subject_id": "sequence", "lineage_id": "lineage",
        "document": str(Path("/tmp/sequence.md").resolve()),
        "source_bundle_hash": "a" * 64,
        "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash,
        "sealed_controller_b64": base64.b64encode(b"controller").decode(),
        "sealed_bootstrap_b64": base64.b64encode(b"bootstrap").decode(),
        "sealed_bootstrap_launcher_b64": base64.b64encode(b"launcher").decode(),
        **ownership,
    }
    active_path = work_memory.receipt_path(task_id, "active")
    active_path.write_bytes(work_memory.canonical_bytes(active))
    return classified, class_hash, selection_hash


def test_handoff_preserves_active_run_and_refreshes_target_receipts(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    state, class_hash, selection_hash = _write_active_owned_receipts("active-task")
    start = event(
        "run_started", run_id=str(uuid.uuid4()), subject_id="sequence",
        lineage_id="lineage", mode="discovery", operation_kind="other",
        source_bundle=[], source_bundle_hash="a" * 64,
        classification_receipt_hash=class_hash,
        selection_receipt_hash=selection_hash,
        started_at_utc="2026-01-01T00:00:00Z", task_id="active-task",
        **{
            key: state[key] for key in (
                "writer_thread_id", "ownership_generation", "ownership_event_id",
                "ownership_sha256",
            )
        },
    )
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [start],
    })
    work_memory.cmd_task_writer_handoff(Namespace(
        task_id="active-task", to_thread_id=WRITER_B, event_id=None,
    ))
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    classification, refreshed_class_hash, _ = work_memory.load_receipt(
        "active-task", "classification",
    )
    selection, refreshed_selection_hash, _ = work_memory.load_receipt(
        "active-task", "selection",
    )
    work_memory.validate_ownership_receipt("active-task", classification)
    work_memory.validate_ownership_receipt("active-task", selection)
    active = json.loads(work_memory.receipt_path("active-task", "active").read_text())
    assert active["classification_receipt_hash"] == refreshed_class_hash
    assert active["selection_receipt_hash"] == refreshed_selection_hash
    assert active["sealed_bootstrap_launcher_b64"] == base64.b64encode(b"launcher").decode()
    events = work_memory.parse_ledger_bytes(work_memory.LEDGER.read_bytes())
    assert work_memory.validate_run_writer_continuity(
        events, "active-task", start["run_id"], start, selection,
    ) == start


def test_target_can_repair_receipts_after_handoff_commit_interruption(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    _write_active_owned_receipts("repair-task")
    apply_refresh = work_memory._apply_owner_refresh_plan
    delayed_writes: list[tuple[Path, str, bytes]] = []

    def interrupt_after_commit(task_id, writes):
        delayed_writes.extend(writes)
        raise OSError("simulated interruption")

    monkeypatch.setattr(
        work_memory, "_apply_owner_refresh_plan", interrupt_after_commit,
    )
    with pytest.raises(OSError, match="simulated interruption"):
        work_memory.cmd_task_writer_handoff(Namespace(
            task_id="repair-task", to_thread_id=WRITER_B, event_id=None,
        ))

    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    monkeypatch.setattr(work_memory, "_apply_owner_refresh_plan", apply_refresh)
    refreshed = work_memory.cmd_task_writer_refresh(Namespace(task_id="repair-task"))
    assert refreshed["writer_thread_id"] == WRITER_B
    repaired_active = json.loads(
        work_memory.receipt_path("repair-task", "active").read_text(),
    )
    assert repaired_active["sealed_bootstrap_launcher_b64"] == base64.b64encode(
        b"launcher",
    ).decode()
    work_memory.cmd_classify(Namespace(
        task_id="repair-task", operation_kind="other",
        repeatable="yes", meaningful_steps=4,
    ))
    target_classification = work_memory.receipt_path(
        "repair-task", "classification",
    ).read_bytes()
    with pytest.raises(
        work_memory.WorkMemoryError, match="task-writer-refresh-cas-mismatch",
    ):
        apply_refresh("repair-task", delayed_writes)
    assert work_memory.receipt_path(
        "repair-task", "classification",
    ).read_bytes() == target_classification
    selection, _, _ = work_memory.load_receipt("repair-task", "selection")
    assert selection["writer_thread_id"] == WRITER_B


def test_merge_ledger_rejects_foreign_owner_without_mutating_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    state = work_memory._claim_task_writer("merge-owned-task")
    start = _owned_run_start("merge-owned-task", state)
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [start],
    })
    before = work_memory.LEDGER.read_bytes()
    source = tmp_path / "foreign-events.jsonl"
    source.write_bytes(before + work_memory.canonical_bytes(event(
        "run_abandoned", run_id=start["run_id"], subject_id="sequence",
        lineage_id="lineage", completed_at_utc="2026-01-01T00:01:00Z",
        reason="foreign writer",
    )))
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)

    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        work_memory.cmd_merge_ledger(SimpleNamespace(
            source_ledger=str(source), ledger=None, view=None,
        ))
    assert work_memory.LEDGER.read_bytes() == before


def test_merge_ledger_accepts_current_owner_after_canonical_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    state, class_hash, selection_hash = _write_active_owned_receipts("merge-handoff-task")
    start = event(
        "run_started", run_id=str(uuid.uuid4()), subject_id="sequence",
        lineage_id="lineage", mode="discovery", operation_kind="other",
        source_bundle=[], source_bundle_hash="a" * 64,
        classification_receipt_hash=class_hash,
        selection_receipt_hash=selection_hash,
        started_at_utc="2026-01-01T00:00:00Z", task_id="merge-handoff-task",
        **{
            key: state[key] for key in (
                "writer_thread_id", "ownership_generation", "ownership_event_id",
                "ownership_sha256",
            )
        },
    )
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [start],
    })
    work_memory.cmd_task_writer_handoff(Namespace(
        task_id="merge-handoff-task", to_thread_id=WRITER_B, event_id=None,
    ))
    canonical = work_memory.LEDGER.read_bytes()
    terminal = event(
        "run_abandoned", run_id=start["run_id"], subject_id="sequence",
        lineage_id="lineage", completed_at_utc="2026-01-01T00:01:00Z",
        reason="current owner import",
    )
    source = tmp_path / "current-owner-events.jsonl"
    source.write_bytes(canonical + work_memory.canonical_bytes(terminal))

    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)
    result = work_memory.cmd_merge_ledger(SimpleNamespace(
        source_ledger=str(source), ledger=None, view=None,
    ))
    assert result["appended_event_count"] == 1
    assert work_memory.parse_ledger_bytes(work_memory.LEDGER.read_bytes())[-1] == terminal


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
    monkeypatch.setattr(work_memory, "registry_rows", lambda **_kwargs: ([{
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


def test_explicit_discovery_selection_does_not_load_registered_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argparse import Namespace

    discovery = tmp_path / "operations/sequences/discovery/repair.md"
    discovery.parent.mkdir(parents=True)
    discovery.write_text("# repair\n\nDiscoveryId: discovery-repair\n")
    manifest = discovery.with_suffix(".dependencies.json")
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": "discovery-repair",
        "dependencies": [],
    }))
    bundle = [
        {
            "repository_key": "memory-knowledge",
            "path": str(discovery.relative_to(tmp_path)),
            "sha256": "a" * 64,
        },
        {
            "repository_key": "memory-knowledge",
            "path": str(manifest.relative_to(tmp_path)),
            "sha256": "b" * 64,
        },
    ]
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path / "receipts")
    monkeypatch.setattr(
        work_memory,
        "registry_rows",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("registry must not load")),
    )
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (bundle, "c" * 64, "discovery-repair"),
    )
    monkeypatch.setattr(work_memory, "load_ledger", lambda: ([], "d" * 64))

    work_memory.cmd_classify(Namespace(
        task_id="registry-repair", operation_kind="workflow-drive",
        repeatable="yes", meaningful_steps=3,
    ))
    selected = work_memory.cmd_select(Namespace(
        task_id="registry-repair", sequence_id=None,
        discovery_log=str(discovery), fingerprint=None,
        verification_successor_of=None, verifies_correction_id=None,
        repo_roots_file=None, repository_roots=None,
    ))

    assert selected["mode"] == "discovery"
    assert selected["subject_id"] == "discovery-repair"
    assert selected["registry_hash"] == work_memory.sha256_bytes(
        work_memory.canonical_bytes([])
    )


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
    monkeypatch.setattr(work_memory, "registry_rows", lambda **_kwargs: ([{
        "sequence_id": "sequence", "folder": "operations/sequences/sequence/",
        "operation_kinds": "deploy", "lineage_id": "lineage",
    }], "9" * 64))
    monkeypatch.setattr(
        work_memory, "resolve_bundle", lambda **kwargs: (bundle, "b" * 64, "lineage"),
    )
    work_memory.cmd_classify(Namespace(
        task_id="successor", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))
    ownership_events, _ = work_memory.load_ledger()
    claim = next(
        item for item in ownership_events
        if item["event_type"] == "task_writer_claimed"
        and item["task_id"] == "successor"
    )
    owner_state = {
        "writer_thread_id": claim["writer_thread_id"],
        "ownership_generation": claim["ownership_generation"],
        "ownership_event_id": claim["event_id"],
    }
    ownership = work_memory._ownership_receipt_fields("successor", owner_state)

    def owned_fixture_ledger(path=work_memory.LEDGER):
        for item in events:
            if item["event_type"] == "run_started" and "task_id" not in item:
                item.update(
                    task_id="successor",
                    repository_roots={"memory-knowledge": str(tmp_path)},
                    **ownership,
                )
        return [claim, *events], "8" * 64

    monkeypatch.setattr(work_memory, "load_ledger", owned_fixture_ledger)
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


def test_successor_selection_accepts_older_correction_after_non_overlapping_bundle_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    Namespace, events, artifact, correction_id = _prepare_successor_selection(
        tmp_path, monkeypatch,
    )
    artifact_hash = work_memory.sha256_bytes(artifact.read_bytes())
    current_bundle = [
        {
            "repository_key": "memory-knowledge",
            "path": "scripts/deploy.sh",
            "sha256": artifact_hash,
        },
        {
            "repository_key": "memory-knowledge",
            "path": "scripts/unrelated.py",
            "sha256": "9" * 64,
        },
    ]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, "c" * 64, "lineage"),
    )

    selected = work_memory.cmd_select(Namespace(
        task_id="successor", sequence_id="sequence", discovery_log=None, fingerprint=None,
        verification_successor_of=events[0]["run_id"],
        verifies_correction_id=[correction_id], repo_roots_file=None,
    ))

    assert selected["source_bundle_hash"] == "c" * 64
    assert selected["verifies_correction_ids"] == [correction_id]


def test_successor_selection_compares_carried_correction_to_raw_artifact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    Namespace, events, _, correction_id = _prepare_successor_selection(
        tmp_path, monkeypatch,
    )
    discovery = tmp_path / "operations/sequences/discovery/case.md"
    discovery.parent.mkdir(parents=True)
    discovery.write_text("# discovery\nStatus: discovery\n")
    raw_hash = work_memory.sha256_bytes(discovery.read_bytes())
    correction = next(
        item for item in events if item["event_type"] == "correction_recorded"
    )
    transition = next(
        item for item in events if item["event_type"] == "bundle_transition_recorded"
    )
    correction["changed_artifacts"] = [
        "operations/sequences/discovery/case.md",
    ]
    correction["changed_artifact_hashes"] = [raw_hash]
    transition["changed_artifacts"] = correction["changed_artifacts"]
    transition["changed_artifact_hashes"] = [raw_hash]
    current_bundle = [{
        "repository_key": "memory-knowledge",
        "path": "operations/sequences/discovery/case.md",
        "sha256": "9" * 64,
    }]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, "c" * 64, "lineage"),
    )

    selected = work_memory.cmd_select(Namespace(
        task_id="successor", sequence_id="sequence", discovery_log=None,
        fingerprint=None, verification_successor_of=events[0]["run_id"],
        verifies_correction_id=[correction_id], repo_roots_file=None,
    ))

    assert selected["source_bundle_hash"] == "c" * 64
    assert selected["verifies_correction_ids"] == [correction_id]


def test_successor_selection_rejects_older_correction_removed_by_later_bundle_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    Namespace, events, _, correction_id = _prepare_successor_selection(
        tmp_path, monkeypatch, include_artifact=False,
    )
    events[0]["source_bundle"] = [{
        "repository_key": "memory-knowledge",
        "path": "scripts/deploy.sh",
        "sha256": "a" * 64,
    }]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: ([], "c" * 64, "lineage"),
    )

    with pytest.raises(work_memory.WorkMemoryError, match="successor-correction-bundle-mismatch"):
        work_memory.cmd_select(Namespace(
            task_id="successor", sequence_id="sequence", discovery_log=None, fingerprint=None,
            verification_successor_of=events[0]["run_id"],
            verifies_correction_id=[correction_id], repo_roots_file=None,
        ))


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
    artifact.write_text("regenerated after correction\n")

    selected = work_memory.cmd_select(Namespace(
        task_id="successor", sequence_id="sequence", discovery_log=None, fingerprint=None,
        verification_successor_of=predecessor_run_id,
        verifies_correction_id=[correction_id], repo_roots_file=None,
    ))

    assert selected["source_bundle"] == []
    assert artifact.is_file()


def test_run_start_accepts_regenerated_explicitly_removed_artifact(
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
    work_memory.cmd_select(Namespace(
        task_id="successor", sequence_id="sequence", discovery_log=None,
        fingerprint=None, verification_successor_of=predecessor_run_id,
        verifies_correction_id=[correction_id], repo_roots_file=None,
    ))
    artifact.write_text("regenerated between selection and run start\n")
    captured: dict[str, object] = {}

    def capture_transaction(batch):
        captured["event"] = batch["events"][0]
        return {"ok": True, "event_ids": [batch["events"][0]["event_id"]]}

    monkeypatch.setattr(work_memory, "transact", capture_transaction)
    work_memory.cmd_run_start(Namespace(task_id="successor", run_id=None, event_id=None))

    started = captured["event"]
    assert isinstance(started, dict)
    assert started["predecessor_run_id"] == predecessor_run_id
    assert started["verifies_correction_ids"] == [correction_id]
    assert started["source_bundle_hash"] == "b" * 64


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
    monkeypatch.setattr(work_memory, "registry_rows", lambda **_kwargs: ([
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
    monkeypatch.setattr(work_memory, "registry_rows", lambda **_kwargs: ([{
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
    monkeypatch.setattr(work_memory, "registry_rows", lambda **_kwargs: ([
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


def test_discovery_bootstrap_is_selectable_for_missing_deploy_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    rows, _ = work_memory.registry_rows()
    bootstrap = next(
        row for row in rows if row["sequence_id"] == "discovery-bootstrap"
    )
    assert "deploy" in bootstrap["operation_kinds"].split(",")

    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path / "receipts")
    monkeypatch.setattr(work_memory, "load_ledger", lambda: ([], "8" * 64))
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: ([], "b" * 64, bootstrap["lineage_id"]),
    )
    work_memory.cmd_classify(Namespace(
        task_id="missing-deploy", operation_kind="deploy",
        repeatable="yes", meaningful_steps=3,
    ))

    selected = work_memory.cmd_select(Namespace(
        task_id="missing-deploy", sequence_id="discovery-bootstrap",
        discovery_log=None, fingerprint=None, verification_successor_of=None,
        verifies_correction_id=None, repo_roots_file=None,
    ))

    assert selected["subject_id"] == "discovery-bootstrap"
    assert selected["selection_reason"] == "explicit-override"


def test_no_retired_run_ledger_or_stale_activation_examples():
    assert not (work_memory.ROOT / "scripts/sequence_run_ledger.py").exists()
    tracked = [path for path in (work_memory.ROOT / "operations/sequences").rglob("*.md")]
    tracked.extend((work_memory.ROOT / "skills" / name / "SKILL.md") for name in (
        "working-agreement", "task-intake", "sequence-runner", "blocker-catalog",
    ))
    assert not any("sequence_guard.py activate --sequence-id" in path.read_text() for path in tracked)


def test_repository_work_memory_ledger_replays_and_view_is_current():
    ledger = work_memory.ROOT / "operations/work-memory/events.jsonl"
    view = work_memory.ROOT / "operations/blockers/BLOCKERS.md"
    events, ledger_hash = work_memory.load_ledger(ledger)

    assert events
    assert len(ledger_hash) == 64
    assert not work_memory.blocker_view_stale(ledger_hash, view)


def test_only_canonical_scripts_write_event_ledger():
    writers = []
    for path in (work_memory.ROOT / "scripts").glob("*.py"):
        text = path.read_text()
        if "events.jsonl" in text or "stage_event_batch(" in text:
            writers.append(path.name)
    assert sorted(writers) == [
        "prevention_journal.py",
        "prevention_owner_acceptance_fixtures.py",
        "sequence_promote.py",
        "work_memory.py",
    ]


CLAUDE_SESSION_A = "7c0f2c4e-9b1d-4c53-8a10-2f47c4b6de01"
CLAUDE_SESSION_B = "8d1e3d5f-0c2e-4d64-9b21-3a58d5c7ef12"


def _claude_identity(monkeypatch: pytest.MonkeyPatch, session: str) -> None:
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("MK_CLIENT_KIND", "claude")
    monkeypatch.setenv("MK_CLIENT_SESSION_ID", session)


def test_claude_identity_claims_v2_ownership_without_codex_thread(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    _claude_identity(monkeypatch, CLAUDE_SESSION_A)
    work_memory.cmd_classify(Namespace(
        task_id="claude-owned-task", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    receipt, _, _ = work_memory.load_receipt("claude-owned-task", "classification")
    assert receipt["writer_client_kind"] == "claude"
    assert receipt["writer_session_id"] == CLAUDE_SESSION_A
    assert "writer_thread_id" not in receipt
    work_memory.validate_ownership_receipt("claude-owned-task", receipt)
    events, _ = work_memory.load_ledger(work_memory.LEDGER)
    claim = next(e for e in events if e["event_type"] == "task_writer_claimed")
    assert claim["schema_version"] == 2
    assert claim["writer_client_kind"] == "claude"
    identity = work_memory.writer_identity()
    assert claim["writer_id"] == identity["writer_id"]
    assert identity["writer_id"] != CLAUDE_SESSION_A


def test_codex_to_claude_handoff_preserves_v1_claim_and_creates_v2_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    work_memory.cmd_classify(Namespace(
        task_id="cross-client-task", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    frozen_v1_receipt, _, _ = work_memory.load_receipt(
        "cross-client-task", "classification",
    )
    assert frozen_v1_receipt["writer_thread_id"] == WRITER_A
    result = work_memory.cmd_task_writer_handoff(Namespace(
        task_id="cross-client-task", to_thread_id=None,
        to_client_kind="claude", to_session_id=CLAUDE_SESSION_A, event_id=None,
    ))
    assert result["writer_client_kind"] == "claude"
    assert result["ownership_generation"] == 2

    events, _ = work_memory.load_ledger(work_memory.LEDGER)
    claim = next(e for e in events if e["event_type"] == "task_writer_claimed")
    assert claim["schema_version"] == 1
    assert claim["writer_thread_id"] == WRITER_A
    handoff = next(e for e in events if e["event_type"] == "task_writer_handoff_recorded")
    assert handoff["schema_version"] == 2
    assert handoff["from_writer_id"] == WRITER_A

    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        work_memory.validate_ownership_receipt("cross-client-task", frozen_v1_receipt)

    _claude_identity(monkeypatch, CLAUDE_SESSION_A)
    work_memory.cmd_classify(Namespace(
        task_id="cross-client-task", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    refreshed, _, _ = work_memory.load_receipt("cross-client-task", "classification")
    assert refreshed["ownership_generation"] == 2
    assert refreshed["writer_client_kind"] == "claude"
    work_memory.validate_ownership_receipt("cross-client-task", refreshed)


def test_colliding_session_from_other_host_identity_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    _claude_identity(monkeypatch, CLAUDE_SESSION_A)
    work_memory.cmd_classify(Namespace(
        task_id="claude-collision-task", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    _claude_identity(monkeypatch, CLAUDE_SESSION_B)
    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        work_memory.cmd_classify(Namespace(
            task_id="claude-collision-task", operation_kind="other",
            repeatable="yes", meaningful_steps=3,
        ))
    monkeypatch.delenv("MK_CLIENT_KIND", raising=False)
    monkeypatch.delenv("MK_CLIENT_SESSION_ID", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", CLAUDE_SESSION_A)
    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        work_memory.cmd_classify(Namespace(
            task_id="claude-collision-task", operation_kind="other",
            repeatable="yes", meaningful_steps=3,
        ))


def test_frozen_v1_ledger_and_receipts_replay_unchanged(
    monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    work_memory.cmd_classify(Namespace(
        task_id="frozen-v1-task", operation_kind="other",
        repeatable="yes", meaningful_steps=3,
    ))
    frozen_ledger = work_memory.LEDGER.read_bytes()
    receipt, _, _ = work_memory.load_receipt("frozen-v1-task", "classification")
    expected_sha = work_memory._ownership_sha256(
        "frozen-v1-task", receipt["writer_thread_id"],
        receipt["ownership_generation"], receipt["ownership_event_id"],
    )
    assert receipt["ownership_sha256"] == expected_sha

    events, digest = work_memory.load_ledger(work_memory.LEDGER)
    assert work_memory.LEDGER.read_bytes() == frozen_ledger
    for entry in events:
        assert entry["schema_version"] == 1
    work_memory.validate_ownership_receipt("frozen-v1-task", receipt)


# --- writer identity: the env var Claude Code actually exports -----------------------------------
# Live 2026-07-28: every governed command (classify/select/run-start/correct/blocker_catalog) failed
# from a Claude Code session with `host-codex-thread-id-required`. The schema-v2 claude writer path
# existed, but read CLAUDE_SESSION_ID -- a name nothing sets. Claude Code exports
# CLAUDE_CODE_SESSION_ID. Producer spelled it one way, consumer read another.

CLAUDE_CODE_SESSION = "9e2f4a60-1d3f-4e75-ac32-4b69e6d8fa23"


def _no_ambient_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CODEX_THREAD_ID", "MK_CLIENT_KIND", "MK_CLIENT_SESSION_ID",
        "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID",
    ):
        monkeypatch.delenv(name, raising=False)


def test_claude_code_session_id_alone_yields_a_claude_writer(
    monkeypatch: pytest.MonkeyPatch,
):
    """The live defect: this is the exact environment a Claude Code session presents, and it raised
    instead of resolving a writer."""
    _no_ambient_identity(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", CLAUDE_CODE_SESSION)
    identity = work_memory.writer_identity()
    assert identity["schema_version"] == 2
    assert identity["writer_client_kind"] == "claude"
    assert identity["writer_session_id"] == CLAUDE_CODE_SESSION


def test_legacy_claude_session_id_is_still_accepted(
    monkeypatch: pytest.MonkeyPatch,
):
    """NO REGRESSION: anything already exporting the old name keeps working."""
    _no_ambient_identity(monkeypatch)
    monkeypatch.setenv("CLAUDE_SESSION_ID", CLAUDE_SESSION_A)
    identity = work_memory.writer_identity()
    assert identity["writer_client_kind"] == "claude"
    assert identity["writer_session_id"] == CLAUDE_SESSION_A


def test_claude_code_session_id_wins_over_the_legacy_name(
    monkeypatch: pytest.MonkeyPatch,
):
    """Both present -> the name Claude Code actually exports is authoritative, so the writer id is
    stable across a session rather than depending on which name a caller happened to set."""
    _no_ambient_identity(monkeypatch)
    monkeypatch.setenv("CLAUDE_SESSION_ID", CLAUDE_SESSION_A)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", CLAUDE_CODE_SESSION)
    assert work_memory.writer_identity()["writer_session_id"] == CLAUDE_CODE_SESSION


def test_explicit_claude_kind_resolves_the_session_from_either_name(
    monkeypatch: pytest.MonkeyPatch,
):
    """MK_CLIENT_KIND=claude with no MK_CLIENT_SESSION_ID must fall back to the real env var."""
    _no_ambient_identity(monkeypatch)
    monkeypatch.setenv("MK_CLIENT_KIND", "claude")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", CLAUDE_CODE_SESSION)
    assert work_memory.writer_identity()["writer_session_id"] == CLAUDE_CODE_SESSION


def test_no_identity_at_all_names_both_writer_paths(
    monkeypatch: pytest.MonkeyPatch,
):
    """The old error said `host-codex-thread-id-required` even when the caller was not Codex at all,
    which sent every Claude reader looking for a thread id that does not apply to them."""
    _no_ambient_identity(monkeypatch)
    with pytest.raises(work_memory.WorkMemoryError, match="writer-identity-required"):
        work_memory.writer_identity()


# --- environment-surface corrections -------------------------------------------------------------
# Live 2026-07-28: the fix for blk-1ab692114088d3bbc2129027 changed ~/.config/memory-knowledge/
# repositories.json -- the machine registry that decides which repositories a sequence can even
# operate on. `correct` rejected it (changed-artifact-outside-repository, then
# correction-artifact-drift-mismatch) because a correction was defined as "a file in this sequence's
# dependency bundle drifted". A machine surface is in no bundle, so no flag could ever record it and
# the blocker could not be closed. Environment surfaces are now a distinct, separately-hashed
# category; the bundle drift invariant is unchanged.

_ENV_SHA = "a" * 64


def _correction_event(**overrides):
    base = {
        "schema_version": 1, "event_id": str(uuid.uuid4()),
        "event_type": "correction_recorded",
        "run_id": str(uuid.uuid4()), "blocker_id": "blk-" + "1" * 24,
        "occurrence_id": str(uuid.uuid4()), "correction_id": str(uuid.uuid4()),
        "subject_id": "commit-push-main", "lineage_id": "lineage-1", "step_id": "dry-run",
        "changed_artifacts": ["scripts/work_memory.py"],
        "changed_artifact_hashes": ["b" * 64],
        "reusable_behavior_changed": True, "solution": "fixed",
    }
    base.update(overrides)
    return base


def test_environment_only_correction_validates_without_bundle_artifacts():
    work_memory._validate_event_values(_correction_event(
        changed_artifacts=[], changed_artifact_hashes=[],
        environment_artifacts=[{
            "repository_key": "machine-config", "path": "repositories.json",
        }],
        environment_artifact_hashes=[_ENV_SHA],
    ))


def test_correction_naming_nothing_at_all_is_still_rejected():
    """The relaxation is scoped: empty bundle artifacts are allowed ONLY alongside an environment
    surface, never as a way to record a correction that changed nothing."""
    with pytest.raises(work_memory.WorkMemoryError, match="invalid-changed-artifacts"):
        work_memory._validate_event_values(_correction_event(
            changed_artifacts=[], changed_artifact_hashes=[],
        ))


def test_historical_correction_without_the_field_still_validates():
    """NO REGRESSION: every correction recorded before this field existed omits it entirely."""
    work_memory._validate_event_values(_correction_event())


def test_environment_hash_must_be_a_real_digest():
    with pytest.raises(work_memory.WorkMemoryError, match="invalid-environment-artifact-hash"):
        work_memory._validate_event_values(_correction_event(
            changed_artifacts=[], changed_artifact_hashes=[],
            environment_artifacts=[{
                "repository_key": "machine-config", "path": "repositories.json",
            }],
            environment_artifact_hashes=["not-a-hash"],
        ))


def _transition_event(**overrides):
    base = {
        "schema_version": 1, "event_id": str(uuid.uuid4()),
        "event_type": "bundle_transition_recorded",
        "lineage_id": "lineage-1", "old_bundle_hash": "c" * 64, "new_bundle_hash": "c" * 64,
        "transition_reason": "correction", "run_id": str(uuid.uuid4()),
        "correction_ids": [str(uuid.uuid4())],
        "changed_artifacts": [], "changed_artifact_hashes": [],
        "environment_artifacts": [{
            "repository_key": "machine-config", "path": "repositories.json",
        }],
        "environment_artifact_hashes": [_ENV_SHA],
    }
    base.update(overrides)
    return base


def test_environment_transition_records_an_unmoved_bundle():
    work_memory._validate_event_values(_transition_event())


def test_environment_transition_cannot_hide_a_moved_bundle():
    """If the bundle hash moved, real bundle files changed and must be named. An environment
    surface must never become a way to record a bundle change without listing it."""
    with pytest.raises(
        work_memory.WorkMemoryError, match="environment-transition-moved-the-bundle",
    ):
        work_memory._validate_event_values(_transition_event(new_bundle_hash="d" * 64))


def test_bundle_transition_without_environment_still_requires_its_artifacts():
    with pytest.raises(work_memory.WorkMemoryError, match="invalid-changed-artifacts"):
        work_memory._validate_event_values(_transition_event(
            environment_artifacts=[], environment_artifact_hashes=[],
        ))
