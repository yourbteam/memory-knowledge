from __future__ import annotations

import base64
import json
import shlex
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import scripts.sequence_guard as sequence_guard
from scripts import work_memory
from scripts.directive_guard import write_directive_read_state


WRITER_THREAD_ID = "019f75a9-fd91-7650-a43f-d20de5e3ae16"


@pytest.fixture
def receipt_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    directives = tmp_path / "DIRECTIVES.md"; directives.write_text("# Test\n")
    directive_state = tmp_path / "directive-state.json"
    write_directive_read_state(directives_path=directives, state_path=directive_state, mode="test")
    monkeypatch.setattr(sequence_guard, "DEFAULT_DIRECTIVES_PATH", directives)
    monkeypatch.setattr(sequence_guard, "DEFAULT_DIRECTIVE_STATE_PATH", directive_state)
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path / "receipts")
    monkeypatch.setattr(work_memory, "LEDGER", tmp_path / "operations/work-memory/events.jsonl")
    monkeypatch.setattr(work_memory, "BLOCKER_VIEW", tmp_path / "operations/blockers/BLOCKERS.md")
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_THREAD_ID)

    document = tmp_path / "operations/sequences/example/sequence.md"
    document.parent.mkdir(parents=True)
    command = "python3 scripts/example.py run"
    external_command = "python3 scripts/external.py run"
    observable_materializer_command = "python3 scripts/prevention_observable_materializer.py"
    contract_materializer_command = "python3 scripts/prevention_contract_materializer.py"
    correction_shape = (
        "python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> "
        "--occurrence-id <occurrence-id> --step-id <step-id> "
        "--changed-artifact <path> --solution <solution> --reusable-behavior-changed yes"
    )
    bootstrap_correction_shape = (
        "python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> "
        "--run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> "
        "--step-id <step-id> --changed-artifact <path> --solution <solution> "
        "--reusable-behavior-changed yes"
    )
    launcher_correction_shape = (
        "python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> "
        "--run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> "
        "--step-id <step-id> --changed-artifact <path> --solution <solution> "
        "--reusable-behavior-changed yes"
    )
    transition_shape = (
        "python3 scripts/blocker_catalog.py transition --run-id <run-id> "
        "--blocker-id <blocker-id> --to-status fixed-awaiting-verification"
    )
    close_shape = "python3 scripts/work_memory.py run-close --run-id <run-id> --result failed"
    document.write_text(
        f"# Example\n\n```bash\n{command}\n{external_command}\n{correction_shape}\n"
        f"{bootstrap_correction_shape}\n{launcher_correction_shape}\n"
        f"{transition_shape}\n{close_shape}\n{observable_materializer_command}\n"
        f"{contract_materializer_command}\n```\n"
    )
    script = tmp_path / "scripts/example.py"; script.parent.mkdir(); script.write_text("print('ok')\n")
    work_memory_script = tmp_path / "scripts/work_memory.py"; work_memory_script.write_text("print('work memory')\n")
    bootstrap_script = tmp_path / "scripts/work_memory_bootstrap.py"
    bootstrap_script.write_text("print('bootstrap')\n")
    launcher_script = tmp_path / "scripts/work_memory_bootstrap_launcher.py"
    launcher_script.write_text("print('launcher')\n")
    blocker_catalog_script = tmp_path / "scripts/blocker_catalog.py"
    blocker_catalog_script.write_text("print('blocker catalog')\n")
    observable_materializer_script = tmp_path / "scripts/prevention_observable_materializer.py"
    observable_materializer_script.write_text("print('observable materializer')\n")
    contract_materializer_script = tmp_path / "scripts/prevention_contract_materializer.py"
    contract_materializer_script.write_text("print('contract materializer')\n")
    changed_artifact = tmp_path / "working-agreement/install_skills.py"
    changed_artifact.parent.mkdir(); changed_artifact.write_text("print('before')\n")
    external_root = tmp_path / "external"; external_script = external_root / "scripts/external.py"
    external_script.parent.mkdir(parents=True); external_script.write_text("print('external')\n")
    manifest = document.with_name("dependencies.json"); manifest.write_text("{}\n")
    bundle = [
        {"repository_key": "memory-knowledge", "path": str(document.relative_to(tmp_path)), "sha256": "a" * 64},
        {"repository_key": "memory-knowledge", "path": str(script.relative_to(tmp_path)), "sha256": "b" * 64},
        {"repository_key": "memory-knowledge", "path": "scripts/work_memory.py",
         "sha256": work_memory.sha256_bytes(work_memory_script.read_bytes())},
        {"repository_key": "memory-knowledge", "path": "scripts/work_memory_bootstrap.py",
         "sha256": work_memory.sha256_bytes(bootstrap_script.read_bytes())},
        {"repository_key": "memory-knowledge", "path": "scripts/work_memory_bootstrap_launcher.py",
         "sha256": work_memory.sha256_bytes(launcher_script.read_bytes())},
        {"repository_key": "memory-knowledge", "path": "scripts/blocker_catalog.py", "sha256": "7" * 64},
        {"repository_key": "memory-knowledge", "path": "scripts/prevention_observable_materializer.py",
         "sha256": work_memory.sha256_bytes(observable_materializer_script.read_bytes())},
        {"repository_key": "memory-knowledge", "path": "scripts/prevention_contract_materializer.py",
         "sha256": work_memory.sha256_bytes(contract_materializer_script.read_bytes())},
        {"repository_key": "memory-knowledge", "path": "working-agreement/install_skills.py", "sha256": "1" * 64},
        {"repository_key": "external", "path": "scripts/external.py", "sha256": "e" * 64},
    ]
    bundle_hash = "c" * 64
    registry_hash = "d" * 64
    monkeypatch.setattr(work_memory, "registry_rows", lambda **_kwargs: ([{
        "sequence_id": "example", "lineage_id": "example", "operation_kinds": "other",
    }], registry_hash))
    monkeypatch.setattr(work_memory, "resolve_bundle", lambda **kwargs: (bundle, bundle_hash, "example"))
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "_repo_roots", lambda path=None: {
        "memory-knowledge": tmp_path, "external": external_root,
    })

    task_id = "task-example"
    owner_state = work_memory._claim_task_writer(task_id)
    ownership = work_memory._ownership_receipt_fields(task_id, owner_state)
    now = datetime.now(UTC).replace(microsecond=0)
    classification = {
        "schema_version": 1, "task_id": task_id, "operation_kind": "other",
        "repeatable": True, "meaningful_steps": 3, "verdict": "operational",
        "reason": "repeatable-or-multistep", "created_at_utc": now.isoformat(),
        "expires_at_utc": (now + timedelta(hours=24)).isoformat(),
        **ownership,
    }
    _, class_hash = work_memory.write_receipt(task_id, "classification", classification)
    selection = {
        "schema_version": 1, "task_id": task_id, "created_at_utc": now.isoformat(),
        "expires_at_utc": (now + timedelta(hours=24)).isoformat(),
        "classification_receipt_hash": class_hash, "registry_hash": registry_hash,
        "mode": "registered", "subject_id": "example", "lineage_id": "example",
        "document": str(document), "manifest": str(manifest), "source_bundle": bundle,
        "source_bundle_hash": bundle_hash,
        **ownership,
    }
    work_memory.write_receipt(task_id, "selection", selection)
    return task_id, document, script, command


@pytest.fixture
def stale_correction_flow(receipt_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    task_id, document, _, _ = receipt_flow
    selection, _, _ = work_memory.load_receipt(task_id, "selection")
    selection = {**selection, "mode": "discovery"}
    work_memory.write_receipt(task_id, "selection", selection)
    state = tmp_path / "active.json"
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--discovery-log", str(document), "--state", str(state),
    ]) == 0

    classification, class_hash, _ = work_memory.load_receipt(task_id, "classification")
    selection, selection_hash, _ = work_memory.load_receipt(task_id, "selection")
    old_bundle = selection["source_bundle"]
    current_bundle = [
        {**item, "sha256": "2" * 64}
        if item["path"] == "working-agreement/install_skills.py" else item
        for item in old_bundle
    ]
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: (current_bundle, "3" * 64, selection["lineage_id"]),
    )

    run_id = "11111111-1111-4111-8111-111111111111"
    occurrence_id = "22222222-2222-4222-8222-222222222222"
    blocker_id = "blk-" + "1" * 24
    step_id = "record-correction"
    events = [
        {
            "schema_version": 1, "event_id": "33333333-3333-4333-8333-333333333333",
            "event_type": "run_started", "recorded_at_utc": "2026-07-14T00:00:00Z",
            "run_id": run_id, "subject_id": selection["subject_id"],
            "lineage_id": selection["lineage_id"], "mode": selection["mode"],
            "operation_kind": classification["operation_kind"], "source_bundle": old_bundle,
            "source_bundle_hash": selection["source_bundle_hash"],
            "classification_receipt_hash": class_hash, "selection_receipt_hash": selection_hash,
            "started_at_utc": "2026-07-14T00:00:00Z",
        },
        {
            "schema_version": 1, "event_id": "44444444-4444-4444-8444-444444444444",
            "event_type": "blocker_opened", "recorded_at_utc": "2026-07-14T00:01:00Z",
            "run_id": run_id, "blocker_id": blocker_id, "occurrence_id": occurrence_id,
            "fingerprint": "4" * 64, "subject_id": selection["subject_id"],
            "lineage_id": selection["lineage_id"], "step_id": step_id,
            "surface": "sequence-guard", "symptom": "stale", "evidence": "stale-source-bundle",
            "impact": "correction blocked", "boundary": "correction bootstrap", "status": "open",
        },
    ]
    monkeypatch.setattr(work_memory, "load_ledger", lambda *args, **kwargs: (events, "5" * 64))

    command = (
        f"python3 scripts/work_memory.py correct --run-id {run_id} --blocker-id {blocker_id} "
        f"--occurrence-id {occurrence_id} --step-id {step_id} "
        "--changed-artifact working-agreement/install_skills.py "
        "--solution 'record exact correction' --reusable-behavior-changed yes"
    )
    return {
        "task_id": task_id, "document": document, "state": state,
        "work_memory_script": tmp_path / "scripts/work_memory.py", "command": command,
        "blocker_catalog_script": tmp_path / "scripts/blocker_catalog.py",
        "run_id": run_id, "blocker_id": blocker_id, "occurrence_id": occurrence_id,
        "step_id": step_id, "events": events, "current_bundle": current_bundle,
    }


@pytest.fixture
def post_correction_flow(stale_correction_flow) -> dict[str, Any]:
    flow = stale_correction_flow
    flow["events"].append({
        "event_type": "correction_recorded",
        "run_id": flow["run_id"],
        "blocker_id": flow["blocker_id"],
        "occurrence_id": flow["occurrence_id"],
        "correction_id": "55555555-5555-4555-8555-555555555555",
        "subject_id": "example",
        "lineage_id": "example",
        "step_id": flow["step_id"],
        "changed_artifacts": ["working-agreement/install_skills.py"],
        "changed_artifact_hashes": ["2" * 64],
        "reusable_behavior_changed": True,
        "solution": "record exact correction",
    })
    flow["transition_command"] = (
        f"python3 scripts/blocker_catalog.py transition --run-id {flow['run_id']} "
        f"--blocker-id {flow['blocker_id']} --to-status fixed-awaiting-verification"
    )
    return flow


@pytest.fixture
def post_transition_flow(post_correction_flow) -> dict[str, Any]:
    flow = post_correction_flow
    flow["events"].append({
        "event_type": "blocker_transitioned",
        "run_id": flow["run_id"],
        "blocker_id": flow["blocker_id"],
        "from_status": "open",
        "to_status": "fixed-awaiting-verification",
    })
    flow["close_command"] = (
        f"python3 scripts/work_memory.py run-close --run-id {flow['run_id']} --result failed"
    )
    return flow


def test_missing_receipts_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    with pytest.raises(work_memory.WorkMemoryError, match="missing-classification-receipt"):
        sequence_guard.verify_receipts("missing")


def test_discovery_receipt_ignores_unrelated_registry_change(
    receipt_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    task_id, document, _, command = receipt_flow
    selection, _, _ = work_memory.load_receipt(task_id, "selection")
    work_memory.write_receipt(task_id, "selection", {**selection, "mode": "discovery"})
    monkeypatch.setattr(
        work_memory,
        "registry_rows",
        lambda **_kwargs: (
            [{"sequence_id": "unrelated", "lineage_id": "unrelated"}], "e" * 64
        ),
    )
    state = tmp_path / "active.json"

    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--discovery-log", str(document),
        "--state", str(state),
    ]) == 0
    assert sequence_guard.main([
        "guard", "--task-id", task_id, "--step", "run", "--command", command,
        "--source", "discovery_log", "--source-ref", str(document),
        "--state", str(state),
    ]) == 0


def test_registered_receipt_rejects_registry_change(
    receipt_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    task_id, document, _, _ = receipt_flow
    monkeypatch.setattr(
        work_memory,
        "registry_rows",
        lambda **_kwargs: (
            [{"sequence_id": "unrelated", "lineage_id": "unrelated"}], "e" * 64
        ),
    )

    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document),
        "--state", str(tmp_path / "active.json"),
    ]) == 4


def test_activation_rejects_retired_sequence_id(receipt_flow):
    task_id, document, _, _ = receipt_flow
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-id", "example",
        "--sequence-doc", str(document),
    ]) == 2


def test_foreign_writer_cannot_activate_or_write_active_state(
    receipt_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    task_id, document, _, _ = receipt_flow
    state = tmp_path / "foreign-active.json"
    monkeypatch.setenv(
        "CODEX_THREAD_ID", "019ee569-0b44-7292-b806-a19fc34c09a2",
    )

    assert sequence_guard.main([
        "activate", "--task-id", task_id,
        "--sequence-doc", str(document), "--state", str(state),
    ]) == 4
    assert not state.exists()


def test_paused_old_owner_cannot_overwrite_active_state_after_handoff(
    receipt_flow, tmp_path: Path,
):
    from argparse import Namespace

    task_id, document, _, _ = receipt_flow
    state_path = tmp_path / "handoff-active.json"
    assert sequence_guard.main([
        "activate", "--task-id", task_id,
        "--sequence-doc", str(document), "--state", str(state_path),
    ]) == 0
    stale_state = json.loads(state_path.read_text())
    work_memory.cmd_task_writer_handoff(Namespace(
        task_id=task_id,
        to_thread_id="019ee569-0b44-7292-b806-a19fc34c09a2",
        event_id=None,
    ))
    before = state_path.read_bytes()

    with pytest.raises(work_memory.WorkMemoryError, match="task-writer-not-owner"):
        sequence_guard._atomic_json(task_id, state_path, stale_state)
    assert state_path.read_bytes() == before


def test_registered_receipts_activate_and_guard(receipt_flow, tmp_path: Path):
    task_id, document, _, command = receipt_flow
    state = tmp_path / "active.json"
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document), "--state", str(state),
    ]) == 0
    assert sequence_guard.main([
        "guard", "--task-id", task_id, "--step", "run", "--command", command,
        "--source", "sequence_doc", "--source-ref", str(document), "--state", str(state),
    ]) == 0


def test_activate_rejects_selection_from_a_different_controller_checkout(
    receipt_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    task_id, document, _, _ = receipt_flow
    foreign_checkout = tmp_path / "foreign-checkout"
    foreign_checkout.mkdir()
    selection, _, _ = work_memory.load_receipt(task_id, "selection")
    selection["repository_roots"] = {
        "memory-knowledge": str(foreign_checkout),
    }
    work_memory.write_receipt(task_id, "selection", selection)
    monkeypatch.setattr(
        work_memory, "_repo_roots",
        lambda path=None, snapshot=None: {
            "memory-knowledge": Path(
                (snapshot or {"memory-knowledge": str(tmp_path)})[
                    "memory-knowledge"
                ]
            ).resolve(),
        },
    )

    assert sequence_guard.main([
        "activate", "--task-id", task_id,
        "--sequence-doc", str(document),
        "--state", str(tmp_path / "active.json"),
    ]) == 4
    assert "controller-checkout-mismatch" in capsys.readouterr().err
    assert not (tmp_path / "active.json").exists()


def test_guard_rejects_ungrounded_command(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow; state = tmp_path / "active.json"
    sequence_guard.main(["activate", "--task-id", task_id, "--sequence-doc", str(document), "--state", str(state)])
    assert sequence_guard.main([
        "guard", "--task-id", task_id, "--step", "invent", "--command", "python3 made-up.py",
        "--source", "sequence_doc", "--source-ref", str(document), "--state", str(state),
    ]) == 4


def test_shape_match_requires_explicit_authorization_for_56_repeated_options() -> None:
    shape = (
        "python3 scripts/work_memory.py correct --changed-artifact <path> "
        "--solution <solution>"
    )
    artifact_options = " ".join(
        f"--changed-artifact scripts/artifact-{index}.py"
        for index in range(56)
    )
    command = (
        f"python3 scripts/work_memory.py correct {artifact_options} "
        "--solution bounded"
    )

    assert not sequence_guard._shape_match(command, shape)
    assert sequence_guard._shape_match(
        command,
        shape,
        repeatable_options=frozenset({"--changed-artifact"}),
    )


def test_selected_sequence_grounds_repeated_co_blockers_and_changed_artifacts() -> None:
    document = Path(
        "operations/sequences/discovery/"
        "2026-07-17-prevention-owner-runtime-five-defect-convergence.md"
    ).read_text()
    command = (
        "python3 scripts/work_memory_bootstrap_launcher.py correct "
        f"--task-id exact-task --run-id {uuid.uuid4()} "
        f"--blocker-id blk-{'1' * 24} "
        f"--co-blocker-id blk-{'2' * 24} --co-blocker-id blk-{'3' * 24} "
        f"--occurrence-id {uuid.uuid4()} --step-id exact-step "
        "--changed-artifact scripts/work_memory.py "
        "--changed-artifact scripts/work_memory_bootstrap.py "
        "--solution exact-fix --reusable-behavior-changed yes "
        f"--correction-id {uuid.uuid4()}"
    )

    assert sequence_guard._shape_match(
        command, document,
        repeatable_options=sequence_guard.CORRECTION_REPEATABLE_SHAPE_OPTIONS,
    )


def test_guard_accepts_only_declared_runtime_placeholder_position(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow
    shape = (
        "python3 skills/_shared/agent_slot_ledger.py bind-agent /tmp/slots.json "
        "--label research-internal-1 --agent-id <agent-id>"
    )
    document.write_text(
        document.read_text()
        + "\n| step | command or action | result | note |\n"
        + "| --- | --- | --- | --- |\n"
        + f"| bind | {shape} | planned | runtime id is produced after spawn |\n"
    )
    state = tmp_path / "active.json"
    sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document), "--state", str(state),
    ])
    concrete = shape.replace("<agent-id>", "agent-7f3d")
    common = [
        "guard", "--task-id", task_id, "--step", "bind-agent", "--source", "sequence_doc",
        "--source-ref", str(document), "--state", str(state),
    ]
    assert sequence_guard.main([*common, "--command", concrete]) == 0
    assert sequence_guard.main([
        *common, "--command", concrete.replace("research-internal-1", "research-coverage-1"),
    ]) == 4
    assert sequence_guard.main([
        *common, "--command", concrete.replace("agent_slot_ledger.py", "other.py"),
    ]) == 4


def test_guard_parses_markdown_command_cell_independently_from_prose(
    receipt_flow, tmp_path: Path
):
    task_id, document, _, _ = receipt_flow
    shape = "python3 scripts/example.py init <state> --mode <mode>"
    document.write_text(
        document.read_text()
        + "\n| step | command or action | result | note |\n"
        + "| --- | --- | --- | --- |\n"
        + f"| init | {shape} | required | Freeze one case's scope before execution. |\n"
    )
    state = tmp_path / "active.json"
    sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document),
        "--state", str(state),
    ])

    assert sequence_guard.main([
        "guard", "--task-id", task_id, "--step", "init",
        "--command", "python3 scripts/example.py init /tmp/state.json --mode CURRENT_RUNTIME",
        "--source", "sequence_doc", "--source-ref", str(document),
        "--state", str(state),
    ]) == 0


def test_guard_rejects_source_outside_bundle(receipt_flow, tmp_path: Path):
    task_id, document, _, command = receipt_flow; state = tmp_path / "active.json"
    other = tmp_path / "other.py"; other.write_text("pass\n")
    sequence_guard.main(["activate", "--task-id", task_id, "--sequence-doc", str(document), "--state", str(state)])
    assert sequence_guard.main([
        "guard", "--task-id", task_id, "--step", "run", "--command", command,
        "--source", "script", "--source-ref", str(other), "--state", str(state),
    ]) == 4


def test_guard_accepts_manifest_covered_external_script(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow; state = tmp_path / "active.json"
    sequence_guard.main(["activate", "--task-id", task_id, "--sequence-doc", str(document), "--state", str(state)])
    external = tmp_path / "external/scripts/external.py"
    assert sequence_guard.main([
        "guard", "--task-id", task_id, "--step", "external",
        "--command", "python3 scripts/external.py run", "--source", "script",
        "--source-ref", str(external), "--state", str(state),
    ]) == 0


def test_guard_accepts_selected_script_command_not_predeclared_in_document(
    receipt_flow, tmp_path: Path,
) -> None:
    task_id, document, _, _ = receipt_flow
    state = tmp_path / "active.json"
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document),
        "--state", str(state),
    ]) == 0
    blocker_catalog = tmp_path / "scripts/blocker_catalog.py"

    assert sequence_guard.main([
        "guard", "--task-id", task_id, "--step", "catalog",
        "--command", "python3 scripts/blocker_catalog.py open --run-id example",
        "--source", "script", "--source-ref", str(blocker_catalog),
        "--state", str(state),
    ]) == 0


def test_selected_script_source_rejects_shell_control_syntax(
    receipt_flow, tmp_path: Path,
) -> None:
    task_id, document, _, _ = receipt_flow
    state = tmp_path / "active.json"
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document),
        "--state", str(state),
    ]) == 0
    blocker_catalog = tmp_path / "scripts/blocker_catalog.py"

    assert sequence_guard.main([
        "guard", "--task-id", task_id, "--step", "catalog",
        "--command", "python3 scripts/blocker_catalog.py open; python3 other.py",
        "--source", "script", "--source-ref", str(blocker_catalog),
        "--state", str(state),
    ]) == 4


def test_selected_script_source_accepts_literal_backticks_in_structured_argv(
    receipt_flow, tmp_path: Path,
) -> None:
    task_id, document, _, _ = receipt_flow
    state = tmp_path / "active.json"
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document),
        "--state", str(state),
    ]) == 0
    blocker_catalog = tmp_path / "scripts/blocker_catalog.py"
    argv = [
        "python3", "scripts/blocker_catalog.py", "open", "--description",
        "Update `src/memory_knowledge/db/health.py`.",
    ]
    args = sequence_guard.build_parser().parse_args([
        "guard", "--task-id", task_id, "--step", "catalog",
        "--command", shlex.join(argv), "--source", "script",
        "--source-ref", str(blocker_catalog), "--state", str(state),
    ])
    args.command_argv = argv

    result = sequence_guard.cmd_guard(args)

    assert result["ok"] is True


def test_selected_script_source_rejects_mismatched_structured_command(
    receipt_flow, tmp_path: Path,
) -> None:
    task_id, document, _, _ = receipt_flow
    state = tmp_path / "active.json"
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document),
        "--state", str(state),
    ]) == 0
    args = sequence_guard.build_parser().parse_args([
        "guard", "--task-id", task_id, "--step", "catalog",
        "--command", "different-command", "--source", "script",
        "--source-ref", str(tmp_path / "scripts/blocker_catalog.py"),
        "--state", str(state),
    ])
    args.command_argv = ["python3", "scripts/blocker_catalog.py", "open"]

    with pytest.raises(work_memory.WorkMemoryError, match="invalid-guarded-command"):
        sequence_guard.cmd_guard(args)


@pytest.mark.parametrize("invalid_token", ["bad\x00token", "bad\ntoken"])
def test_selected_script_source_rejects_invalid_structured_argv_tokens(
    receipt_flow, tmp_path: Path, invalid_token: str,
) -> None:
    task_id, document, _, _ = receipt_flow
    state = tmp_path / "active.json"
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document),
        "--state", str(state),
    ]) == 0
    args = sequence_guard.build_parser().parse_args([
        "guard", "--task-id", task_id, "--step", "catalog",
        "--command", "unused-structured-command", "--source", "script",
        "--source-ref", str(tmp_path / "scripts/blocker_catalog.py"),
        "--state", str(state),
    ])
    args.command_argv = ["python3", "scripts/blocker_catalog.py", invalid_token]

    with pytest.raises(work_memory.WorkMemoryError, match="invalid-guarded-command"):
        sequence_guard.cmd_guard(args)


def test_status_is_read_only_and_receipt_bound(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow; state = tmp_path / "active.json"
    sequence_guard.main(["activate", "--task-id", task_id, "--sequence-doc", str(document), "--state", str(state)])
    before = state.read_bytes()
    assert sequence_guard.main(["status", "--task-id", task_id, "--state", str(state)]) == 0
    assert state.read_bytes() == before


def test_activate_seals_selected_controller_and_bootstrap(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow
    state_path = tmp_path / "active.json"
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document),
        "--state", str(state_path),
    ]) == 0

    state = json.loads(state_path.read_text())
    controller = tmp_path / state["sealed_controller_path"]
    bootstrap = tmp_path / state["bootstrap_path"]
    launcher = tmp_path / state["bootstrap_launcher_path"]
    assert work_memory.sha256_bytes(base64.b64decode(state["sealed_controller_b64"])) == state["sealed_controller_sha256"]
    assert work_memory.sha256_bytes(controller.read_bytes()) == state["sealed_controller_sha256"]
    assert work_memory.sha256_bytes(bootstrap.read_bytes()) == state["bootstrap_sha256"]
    assert work_memory.sha256_bytes(base64.b64decode(state["sealed_bootstrap_b64"])) == state["bootstrap_sha256"]
    assert work_memory.sha256_bytes(
        base64.b64decode(state["sealed_bootstrap_launcher_b64"])
    ) == state["bootstrap_launcher_sha256"]
    assert work_memory.sha256_bytes(launcher.read_bytes()) == state["bootstrap_launcher_sha256"]


def test_activate_still_requires_directive_read_state(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow
    with pytest.raises(SystemExit, match="directive read state not found"):
        sequence_guard.main([
            "activate", "--task-id", task_id, "--sequence-doc", str(document),
            "--directive-state", str(tmp_path / "missing.json"),
        ])


def test_activate_accepts_old_directive_receipt_when_bound_bytes_are_unchanged(
    receipt_flow, tmp_path: Path,
) -> None:
    task_id, document, _, _ = receipt_flow
    directive_state = sequence_guard.DEFAULT_DIRECTIVE_STATE_PATH
    state = json.loads(directive_state.read_text(encoding="utf-8"))
    state["readAtUtc"] = "2020-01-01T00:00:00Z"
    directive_state.write_text(json.dumps(state), encoding="utf-8")

    assert sequence_guard.main([
        "activate", "--task-id", task_id,
        "--sequence-doc", str(document),
        "--state", str(tmp_path / "active.json"),
    ]) == 0


def test_activate_rejects_old_receipt_when_directive_bytes_changed(
    receipt_flow, tmp_path: Path,
) -> None:
    task_id, document, _, _ = receipt_flow
    directive_state = sequence_guard.DEFAULT_DIRECTIVE_STATE_PATH
    state = json.loads(directive_state.read_text(encoding="utf-8"))
    state["readAtUtc"] = "2020-01-01T00:00:00Z"
    directive_state.write_text(json.dumps(state), encoding="utf-8")
    sequence_guard.DEFAULT_DIRECTIVES_PATH.write_text(
        "# Changed directives\n", encoding="utf-8",
    )

    with pytest.raises(
        SystemExit, match="directive read state is stale because directives SHA changed",
    ):
        sequence_guard.main([
            "activate", "--task-id", task_id,
            "--sequence-doc", str(document),
            "--state", str(tmp_path / "active.json"),
        ])


@pytest.mark.parametrize("source", ["discovery_log", "script"])
def test_ordinary_guard_still_rejects_stale_source_bundle(stale_correction_flow, source, capsys):
    flow = stale_correction_flow
    source_ref = flow["document"] if source == "discovery_log" else flow["work_memory_script"]
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", source, "--source-ref", str(source_ref),
        "--state", str(flow["state"]),
    ]) == 4
    assert "stale-source-bundle" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("step", "command", "script_name"),
    [
        (
            "materialize-owner-observables",
            "python3 scripts/prevention_observable_materializer.py",
            "prevention_observable_materializer.py",
        ),
        (
            "materialize-owner-contracts",
            "python3 scripts/prevention_contract_materializer.py",
            "prevention_contract_materializer.py",
        ),
    ],
)
def test_stale_guard_authorizes_exact_declared_source_derived_materializer(
    stale_correction_flow, tmp_path: Path, step: str, command: str, script_name: str,
) -> None:
    flow = stale_correction_flow

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", step,
        "--command", command, "--source", "script",
        "--source-ref", str(tmp_path / "scripts" / script_name),
        "--state", str(flow["state"]),
    ]) == 0


@pytest.mark.parametrize(
    ("step", "command", "source_ref", "expected_error"),
    [
        (
            "materialize-owner-contracts",
            "python3 scripts/prevention_observable_materializer.py",
            "scripts/prevention_observable_materializer.py",
            "stale-source-bundle",
        ),
        (
            "materialize-owner-observables",
            "python3 scripts/prevention_observable_materializer.py --output elsewhere.json",
            "scripts/prevention_observable_materializer.py",
            "stale-source-bundle",
        ),
        (
            "materialize-owner-observables",
            "python3 scripts/prevention_observable_materializer.py",
            "scripts/prevention_contract_materializer.py",
            "invalid-source-derived-materializer-source",
        ),
    ],
)
def test_stale_guard_rejects_materializer_binding_tampering(
    stale_correction_flow, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    step: str, command: str, source_ref: str, expected_error: str,
) -> None:
    flow = stale_correction_flow

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", step,
        "--command", command, "--source", "script",
        "--source-ref", str(tmp_path / source_ref), "--state", str(flow["state"]),
    ]) == 4
    assert expected_error in capsys.readouterr().err


def test_stale_guard_rejects_drifted_source_derived_materializer(
    stale_correction_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    flow = stale_correction_flow
    current_bundle = [
        {**item, "sha256": "9" * 64}
        if item["path"] == "scripts/prevention_observable_materializer.py" else item
        for item in flow["current_bundle"]
    ]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, "8" * 64, "example"),
    )

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"],
        "--step", "materialize-owner-observables",
        "--command", "python3 scripts/prevention_observable_materializer.py",
        "--source", "script",
        "--source-ref", str(tmp_path / "scripts/prevention_observable_materializer.py"),
        "--state", str(flow["state"]),
    ]) == 4
    assert (
        "source-derived-materializer-preliminary-correction-required"
        in capsys.readouterr().err
    )


def test_stale_guard_authorizes_drifted_materializer_only_after_exact_preliminary_correction(
    stale_correction_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = stale_correction_flow
    correction_id = "55555555-5555-4555-8555-555555555555"
    current_hash = "8" * 64
    materializer_hash = "9" * 64
    materializer_path = "scripts/prevention_observable_materializer.py"
    current_bundle = [
        {**item, "sha256": materializer_hash}
        if item["path"] == materializer_path else item
        for item in flow["current_bundle"]
    ]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, current_hash, "example"),
    )
    flow["events"][0]["task_id"] = flow["task_id"]
    flow["events"][1]["step_id"] = "materialize-owner-observables"
    changed_artifacts = [materializer_path, "working-agreement/install_skills.py"]
    changed_hashes = [materializer_hash, "2" * 64]
    flow["events"].extend([
        {
            "schema_version": 1,
            "event_id": "66666666-6666-4666-8666-666666666666",
            "event_type": "correction_recorded",
            "recorded_at_utc": "2026-07-14T00:02:00Z",
            "run_id": flow["run_id"],
            "blocker_id": flow["blocker_id"],
            "occurrence_id": flow["occurrence_id"],
            "correction_id": correction_id,
            "subject_id": "example",
            "lineage_id": "example",
            "step_id": "materialize-owner-observables",
            "changed_artifacts": changed_artifacts,
            "changed_artifact_hashes": changed_hashes,
            "reusable_behavior_changed": True,
            "solution": "authenticate the changed materializer before regeneration",
        },
        {
            "schema_version": 1,
            "event_id": "77777777-7777-4777-8777-777777777777",
            "event_type": "bundle_transition_recorded",
            "recorded_at_utc": "2026-07-14T00:02:00Z",
            "lineage_id": "example",
            "old_bundle_hash": "c" * 64,
            "new_bundle_hash": current_hash,
            "transition_reason": "correction",
            "run_id": flow["run_id"],
            "correction_ids": [correction_id],
            "changed_artifacts": changed_artifacts,
            "changed_artifact_hashes": changed_hashes,
        },
    ])

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"],
        "--step", "materialize-owner-observables",
        "--command", "python3 scripts/prevention_observable_materializer.py",
        "--source", "script",
        "--source-ref", str(tmp_path / materializer_path),
        "--state", str(flow["state"]),
        "--authorizing-correction-id", correction_id,
    ]) == 0


def test_stale_guard_requires_materializer_declaration_in_selected_document(
    stale_correction_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    flow = stale_correction_flow
    monkeypatch.setattr(sequence_guard, "_shape_match", lambda *args, **kwargs: False)

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"],
        "--step", "materialize-owner-observables",
        "--command", "python3 scripts/prevention_observable_materializer.py",
        "--source", "script",
        "--source-ref", str(tmp_path / "scripts/prevention_observable_materializer.py"),
        "--state", str(flow["state"]),
    ]) == 4
    assert "source-derived-materializer-not-declared" in capsys.readouterr().err


def test_stale_guard_requires_materializer_active_selection_binding(
    stale_correction_flow, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    flow = stale_correction_flow
    state = json.loads(flow["state"].read_text())
    state["selection_receipt_hash"] = "0" * 64
    flow["state"].write_text(json.dumps(state))

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"],
        "--step", "materialize-owner-observables",
        "--command", "python3 scripts/prevention_observable_materializer.py",
        "--source", "script",
        "--source-ref", str(tmp_path / "scripts/prevention_observable_materializer.py"),
        "--state", str(flow["state"]),
    ]) == 4
    assert "source-derived-materializer-active-state-mismatch" in capsys.readouterr().err


def test_correction_bootstrap_authorizes_exact_work_memory_correct(stale_correction_flow):
    flow = stale_correction_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 0


def test_correction_bootstrap_authorizes_repeated_declared_changed_artifact_shape(
    stale_correction_flow, monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = stale_correction_flow
    current_bundle = [
        {**item, "sha256": "6" * 64}
        if item["path"] == "scripts/example.py" else item
        for item in flow["current_bundle"]
    ]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, "7" * 64, "example"),
    )
    command = flow["command"].replace(
        "--changed-artifact working-agreement/install_skills.py",
        "--changed-artifact working-agreement/install_skills.py "
        "--changed-artifact scripts/example.py",
    )

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", command, "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 0


def test_correction_bootstrap_uses_latest_sequential_correction_bundle(
    stale_correction_flow, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    flow = stale_correction_flow
    prior_blocker_id = "blk-" + "2" * 24
    prior_occurrence_id = "66666666-6666-4666-8666-666666666666"
    prior_correction_id = "77777777-7777-4777-8777-777777777777"
    flow["events"][1:1] = [
        {
            "event_id": "99999999-9999-4999-8999-999999999999",
            "event_type": "blocker_opened", "run_id": flow["run_id"],
            "blocker_id": prior_blocker_id,
            "occurrence_id": prior_occurrence_id,
            "subject_id": "example", "lineage_id": "example",
            "step_id": "prior-correction", "status": "open",
        },
        {
            "event_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "event_type": "correction_recorded", "run_id": flow["run_id"],
            "blocker_id": prior_blocker_id,
            "occurrence_id": prior_occurrence_id,
            "correction_id": prior_correction_id,
            "subject_id": "example", "lineage_id": "example",
            "step_id": "prior-correction",
            "changed_artifacts": ["working-agreement/install_skills.py"],
            "changed_artifact_hashes": ["2" * 64],
            "reusable_behavior_changed": True,
            "solution": "record prior correction",
        },
        {
            "event_type": "bundle_transition_recorded",
            "event_id": "88888888-8888-4888-8888-888888888888",
            "run_id": flow["run_id"], "lineage_id": "example",
            "old_bundle_hash": "c" * 64, "new_bundle_hash": "3" * 64,
            "transition_reason": "correction",
            "correction_ids": [prior_correction_id],
            "changed_artifacts": ["working-agreement/install_skills.py"],
            "changed_artifact_hashes": ["2" * 64],
        },
        {
            "event_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "event_type": "blocker_transitioned", "run_id": flow["run_id"],
            "blocker_id": prior_blocker_id, "from_status": "open",
            "to_status": "fixed-awaiting-verification",
        },
    ]
    current_bundle = [
        {**item, "sha256": "6" * 64}
        if item["path"] == "scripts/example.py" else item
        for item in flow["current_bundle"]
    ]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, "7" * 64, "example"),
    )
    command = flow["command"].replace(
        "--changed-artifact working-agreement/install_skills.py",
        "--changed-artifact scripts/example.py",
    )
    start, related = work_memory._run_state(flow["events"], flow["run_id"])
    effective_bundle, effective_hash, correction_ids = (
        work_memory._effective_correction_bundle(start, related)
    )
    effective_keys = sequence_guard._bundle_keys(effective_bundle)
    current_keys = sequence_guard._bundle_keys(current_bundle)
    assert effective_hash == "3" * 64
    assert correction_ids == [prior_correction_id]
    assert {
        key for key in effective_keys.keys() | current_keys.keys()
        if effective_keys.get(key) != current_keys.get(key)
    } == {("memory-knowledge", "scripts/example.py")}

    guard_args = [
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", command, "--source", "script",
        "--source-ref", str(flow["work_memory_script"]),
        "--state", str(flow["state"]), "--correction-bootstrap",
    ]
    assert sequence_guard.main(guard_args) == 0

    prior_transition = next(
        item for item in flow["events"]
        if item["event_type"] == "bundle_transition_recorded"
    )
    prior_transition["old_bundle_hash"] = "f" * 64
    assert sequence_guard.main(guard_args) == 4
    assert "noncumulative-correction-transition" in capsys.readouterr().err


def test_correction_bootstrap_authorizes_authenticated_launcher_rotation(
    stale_correction_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = stale_correction_flow
    trust_paths = {
        "scripts/work_memory.py",
        "scripts/work_memory_bootstrap.py",
        "scripts/work_memory_bootstrap_launcher.py",
    }
    current_bundle = [
        {**item, "sha256": "6" * 64}
        if item["path"] in trust_paths else item
        for item in flow["current_bundle"]
    ]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, "7" * 64, "example"),
    )
    command = (
        "python3 scripts/work_memory_bootstrap_launcher.py correct "
        f"--task-id {flow['task_id']} --run-id {flow['run_id']} "
        f"--blocker-id {flow['blocker_id']} --occurrence-id {flow['occurrence_id']} "
        f"--step-id {flow['step_id']} "
        "--changed-artifact working-agreement/install_skills.py "
        "--changed-artifact scripts/work_memory.py "
        "--changed-artifact scripts/work_memory_bootstrap.py "
        "--changed-artifact scripts/work_memory_bootstrap_launcher.py "
        "--solution 'rotate authenticated trust anchors' --reusable-behavior-changed yes"
    )

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", command, "--source", "script",
        "--source-ref", str(tmp_path / "scripts/work_memory_bootstrap_launcher.py"),
        "--state", str(flow["state"]), "--correction-bootstrap",
    ]) == 0


@pytest.mark.parametrize("tampered_head", [False, True])
def test_legacy_launcher_rotation_requires_hash_verified_head_blob(
    stale_correction_flow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    tampered_head: bool,
) -> None:
    flow = stale_correction_flow
    state = json.loads(flow["state"].read_text())
    launcher_blob = base64.b64decode(state.pop("sealed_bootstrap_launcher_b64"))
    flow["state"].write_text(json.dumps(state))
    trust_paths = {
        "scripts/work_memory.py",
        "scripts/work_memory_bootstrap.py",
        "scripts/work_memory_bootstrap_launcher.py",
    }
    current_bundle = [
        {**item, "sha256": "6" * 64}
        if item["path"] in trust_paths else item
        for item in flow["current_bundle"]
    ]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, "7" * 64, "example"),
    )
    monkeypatch.setattr(
        sequence_guard,
        "_read_head_launcher_blob",
        lambda root: b"tampered\n" if tampered_head else launcher_blob,
    )
    command = (
        "python3 scripts/work_memory_bootstrap_launcher.py correct "
        f"--task-id {flow['task_id']} --run-id {flow['run_id']} "
        f"--blocker-id {flow['blocker_id']} --occurrence-id {flow['occurrence_id']} "
        f"--step-id {flow['step_id']} "
        "--changed-artifact working-agreement/install_skills.py "
        "--changed-artifact scripts/work_memory.py "
        "--changed-artifact scripts/work_memory_bootstrap.py "
        "--changed-artifact scripts/work_memory_bootstrap_launcher.py "
        "--solution 'rotate legacy trust anchors' --reusable-behavior-changed yes"
    )

    result = sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", command, "--source", "script",
        "--source-ref", str(tmp_path / "scripts/work_memory_bootstrap_launcher.py"),
        "--state", str(flow["state"]), "--correction-bootstrap",
    ])
    assert result == (4 if tampered_head else 0)


def test_correction_bootstrap_authorizes_wrapper_for_external_artifact(
    stale_correction_flow, monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = stale_correction_flow
    selection, _, _ = work_memory.load_receipt(flow["task_id"], "selection")
    external = next(item for item in selection["source_bundle"] if item["repository_key"] == "external")
    current_bundle = [
        {**item, "sha256": "9" * 64}
        if item["repository_key"] == "external" and item["path"] == external["path"]
        else item
        for item in selection["source_bundle"]
    ]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, "8" * 64, selection["lineage_id"]),
    )
    command = (
        "python3 scripts/work_memory_bootstrap.py correct "
        f"--task-id {flow['task_id']} --run-id {flow['run_id']} "
        f"--blocker-id {flow['blocker_id']} --occurrence-id {flow['occurrence_id']} "
        f"--step-id {flow['step_id']} "
        f"--changed-artifact {work_memory._repo_roots()['external'] / external['path']} "
        "--solution 'record external correction' --reusable-behavior-changed yes"
    )

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", command, "--source", "script",
        "--source-ref", str(work_memory.ROOT / "scripts/work_memory_bootstrap.py"),
        "--state", str(flow["state"]), "--correction-bootstrap",
    ]) == 0


def test_correction_bootstrap_rejects_partial_bundle_drift(
    stale_correction_flow, monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = stale_correction_flow
    current_bundle = [
        {**item, "sha256": "6" * 64}
        if item["path"] in {"working-agreement/install_skills.py", "scripts/example.py"}
        else item
        for item in flow["current_bundle"]
    ]
    monkeypatch.setattr(
        work_memory,
        "resolve_bundle",
        lambda **kwargs: (current_bundle, "7" * 64, "example"),
    )

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 4


def test_correction_bootstrap_rejects_wrapper_task_mismatch(stale_correction_flow) -> None:
    flow = stale_correction_flow
    command = flow["command"].replace(
        "python3 scripts/work_memory.py correct",
        "python3 scripts/work_memory_bootstrap.py correct --task-id another-task",
    )
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", command, "--source", "script",
        "--source-ref", str(work_memory.ROOT / "scripts/work_memory_bootstrap.py"),
        "--state", str(flow["state"]), "--correction-bootstrap",
    ]) == 4


def test_discovery_correction_bootstrap_ignores_unrelated_registry_change(
    stale_correction_flow, monkeypatch: pytest.MonkeyPatch
):
    flow = stale_correction_flow
    monkeypatch.setattr(
        work_memory,
        "registry_rows",
        lambda **_kwargs: (
            [{"sequence_id": "unrelated", "lineage_id": "unrelated"}], "e" * 64
        ),
    )

    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 0


def test_correction_bootstrap_parser_accepts_multiple_superseded_corrections():
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    parsed = sequence_guard._parse_correction_command(
        "python3 scripts/work_memory.py correct "
        f"--run-id {uuid.uuid4()} --blocker-id blk-{'1' * 24} "
        f"--occurrence-id {uuid.uuid4()} --step-id correction-schema "
        "--changed-artifact scripts/work_memory.py --solution bounded-list "
        "--reusable-behavior-changed yes "
        f"--supersedes-correction-id {first} "
        f"--supersedes-correction-id {second}"
    )
    assert parsed["--supersedes-correction-id"] == [first, second]


def test_correction_bootstrap_parser_accepts_explicit_repeated_co_blockers():
    first = "blk-" + "2" * 24
    second = "blk-" + "3" * 24
    parsed = sequence_guard._parse_correction_command(
        "python3 scripts/work_memory_bootstrap_launcher.py correct "
        f"--task-id example --run-id {uuid.uuid4()} --blocker-id blk-{'1' * 24} "
        f"--co-blocker-id {first} --co-blocker-id {second} "
        f"--occurrence-id {uuid.uuid4()} --step-id correction-schema "
        "--changed-artifact scripts/work_memory.py --solution exact-co-fix "
        "--reusable-behavior-changed yes"
    )

    assert parsed["--co-blocker-id"] == [first, second]


def test_correction_bootstrap_rejects_non_script_source(stale_correction_flow):
    flow = stale_correction_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", "discovery_log",
        "--source-ref", str(flow["document"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 4


@pytest.mark.parametrize("mutation", [
    lambda flow: "python3 scripts/example.py run",
    lambda flow: flow["command"] + "; python3 made-up.py",
    lambda flow: flow["command"].replace(flow["run_id"], "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    lambda flow: flow["command"].replace(flow["blocker_id"], "blk-" + "a" * 24),
    lambda flow: flow["command"].replace(flow["occurrence_id"], "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    lambda flow: flow["command"].replace("--step-id record-correction", "--step-id another-step"),
    lambda flow: flow["command"].replace(
        "--changed-artifact working-agreement/install_skills.py",
        "--changed-artifact scripts/work_memory.py",
    ),
])
def test_correction_bootstrap_rejects_command_or_binding_tampering(stale_correction_flow, mutation):
    flow = stale_correction_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", mutation(flow), "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 4


def test_correction_bootstrap_rejects_tampered_old_active_chain(stale_correction_flow):
    flow = stale_correction_flow
    state = json.loads(flow["state"].read_text())
    state["source_bundle_hash"] = "0" * 64
    flow["state"].write_text(json.dumps(state))
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 4


def test_correction_bootstrap_rejects_changed_lineage(stale_correction_flow, monkeypatch):
    flow = stale_correction_flow
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: (flow["current_bundle"], "3" * 64, "different-lineage"),
    )
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 4


def test_correction_bootstrap_rejects_changed_document_identity(stale_correction_flow, monkeypatch):
    flow = stale_correction_flow
    current_bundle = [
        item for item in flow["current_bundle"]
        if item["path"] != str(flow["document"].relative_to(work_memory.ROOT))
    ]
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: (current_bundle, "3" * 64, "example"),
    )
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 4


def test_correction_bootstrap_rejects_changed_work_memory_script(stale_correction_flow, monkeypatch):
    flow = stale_correction_flow
    current_bundle = [
        {**item, "sha256": "6" * 64} if item["path"] == "scripts/work_memory.py" else item
        for item in flow["current_bundle"]
    ]
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: (current_bundle, "3" * 64, "example"),
    )
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 4


def test_correction_bootstrap_rejects_terminal_run(stale_correction_flow):
    flow = stale_correction_flow
    flow["events"].append({"event_type": "run_closed", "run_id": flow["run_id"]})
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", flow["step_id"],
        "--command", flow["command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--correction-bootstrap",
    ]) == 4


@pytest.mark.parametrize("operation", ["transition", "run-close"])
def test_ordinary_guard_rejects_stale_post_correction_operations(
    post_transition_flow, operation, capsys,
):
    flow = post_transition_flow
    if operation == "transition":
        command = flow["transition_command"]
        source_ref = flow["blocker_catalog_script"]
    else:
        command = flow["close_command"]
        source_ref = flow["work_memory_script"]
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", operation,
        "--command", command, "--source", "script", "--source-ref", str(source_ref),
        "--state", str(flow["state"]),
    ]) == 4
    assert "stale-source-bundle" in capsys.readouterr().err


def test_post_correction_bootstrap_authorizes_fixed_transition(post_correction_flow):
    flow = post_correction_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "transition-fixed",
        "--command", flow["transition_command"], "--source", "script",
        "--source-ref", str(flow["blocker_catalog_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 0


def test_post_correction_bootstrap_rejects_wrong_transition_step(post_correction_flow):
    flow = post_correction_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "arbitrary-step",
        "--command", flow["transition_command"], "--source", "script",
        "--source-ref", str(flow["blocker_catalog_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 4


@pytest.mark.parametrize("mutation", [
    lambda flow: flow["transition_command"].replace(
        "fixed-awaiting-verification", "verified",
    ),
    lambda flow: flow["transition_command"] + "; python3 made-up.py",
    lambda flow: flow["transition_command"].replace(
        flow["run_id"], "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    ),
    lambda flow: flow["transition_command"].replace(
        flow["blocker_id"], "blk-" + "a" * 24,
    ),
])
def test_post_correction_bootstrap_rejects_transition_tampering(post_correction_flow, mutation):
    flow = post_correction_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "transition-fixed",
        "--command", mutation(flow), "--source", "script",
        "--source-ref", str(flow["blocker_catalog_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 4


def test_post_correction_bootstrap_transition_requires_current_occurrence_correction(
    post_correction_flow,
):
    flow = post_correction_flow
    correction = next(
        event for event in flow["events"] if event["event_type"] == "correction_recorded"
    )
    correction["occurrence_id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "transition-fixed",
        "--command", flow["transition_command"], "--source", "script",
        "--source-ref", str(flow["blocker_catalog_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 4


def test_post_correction_bootstrap_transition_requires_blocker_catalog_source(post_correction_flow):
    flow = post_correction_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "transition-fixed",
        "--command", flow["transition_command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 4


def test_post_correction_bootstrap_authorizes_failed_run_close(post_transition_flow):
    flow = post_transition_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "close-failed-run",
        "--command", flow["close_command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 0


def test_post_correction_bootstrap_rejects_wrong_run_close_step(post_transition_flow):
    flow = post_transition_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "arbitrary-step",
        "--command", flow["close_command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 4


@pytest.mark.parametrize("mutation", [
    lambda flow: flow["close_command"].replace("--result failed", "--result passed"),
    lambda flow: flow["close_command"] + " && python3 made-up.py",
    lambda flow: flow["close_command"].replace(
        flow["run_id"], "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    ),
    lambda flow: "python3 scripts/example.py run",
])
def test_post_correction_bootstrap_rejects_run_close_tampering(post_transition_flow, mutation):
    flow = post_transition_flow
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "close-failed-run",
        "--command", mutation(flow), "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 4


def test_post_correction_bootstrap_run_close_requires_corrections(stale_correction_flow):
    flow = stale_correction_flow
    command = f"python3 scripts/work_memory.py run-close --run-id {flow['run_id']} --result failed"
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "close-failed-run",
        "--command", command, "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 4


def test_post_correction_bootstrap_run_close_requires_all_corrected_blockers_fixed(
    post_correction_flow,
):
    flow = post_correction_flow
    command = f"python3 scripts/work_memory.py run-close --run-id {flow['run_id']} --result failed"
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "close-failed-run",
        "--command", command, "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 4


def test_post_correction_bootstrap_run_close_checks_every_corrected_blocker(
    post_transition_flow,
):
    flow = post_transition_flow
    second_blocker = "blk-" + "2" * 24
    second_occurrence = "66666666-6666-4666-8666-666666666666"
    flow["events"].extend([
        {
            "event_type": "blocker_opened", "run_id": flow["run_id"],
            "blocker_id": second_blocker, "occurrence_id": second_occurrence,
            "subject_id": "example", "lineage_id": "example", "step_id": "second-correction",
        },
        {
            "event_type": "correction_recorded", "run_id": flow["run_id"],
            "blocker_id": second_blocker, "occurrence_id": second_occurrence,
            "correction_id": "77777777-7777-4777-8777-777777777777",
            "subject_id": "example", "lineage_id": "example", "step_id": "second-correction",
        },
    ])
    assert sequence_guard.main([
        "guard", "--task-id", flow["task_id"], "--step", "close-failed-run",
        "--command", flow["close_command"], "--source", "script",
        "--source-ref", str(flow["work_memory_script"]), "--state", str(flow["state"]),
        "--post-correction-bootstrap",
    ]) == 4
