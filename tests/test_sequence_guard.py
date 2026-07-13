from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import scripts.sequence_guard as sequence_guard
from scripts import work_memory
from scripts.directive_guard import write_directive_read_state


@pytest.fixture
def receipt_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    directives = tmp_path / "DIRECTIVES.md"; directives.write_text("# Test\n")
    directive_state = tmp_path / "directive-state.json"
    write_directive_read_state(directives_path=directives, state_path=directive_state, mode="test")
    monkeypatch.setattr(sequence_guard, "DEFAULT_DIRECTIVES_PATH", directives)
    monkeypatch.setattr(sequence_guard, "DEFAULT_DIRECTIVE_STATE_PATH", directive_state)
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path / "receipts")

    document = tmp_path / "operations/sequences/example/sequence.md"
    document.parent.mkdir(parents=True)
    command = "python3 scripts/example.py run"
    external_command = "python3 scripts/external.py run"
    document.write_text(f"# Example\n\n```bash\n{command}\n{external_command}\n```\n")
    script = tmp_path / "scripts/example.py"; script.parent.mkdir(); script.write_text("print('ok')\n")
    external_root = tmp_path / "external"; external_script = external_root / "scripts/external.py"
    external_script.parent.mkdir(parents=True); external_script.write_text("print('external')\n")
    manifest = document.with_name("dependencies.json"); manifest.write_text("{}\n")
    bundle = [
        {"repository_key": "memory-knowledge", "path": str(document), "sha256": "a" * 64},
        {"repository_key": "memory-knowledge", "path": str(script), "sha256": "b" * 64},
        {"repository_key": "external", "path": "scripts/external.py", "sha256": "e" * 64},
    ]
    bundle_hash = "c" * 64
    registry_hash = "d" * 64
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([{
        "sequence_id": "example", "lineage_id": "example", "operation_kinds": "other",
    }], registry_hash))
    monkeypatch.setattr(work_memory, "resolve_bundle", lambda **kwargs: (bundle, bundle_hash, "example"))
    monkeypatch.setattr(work_memory, "ROOT", Path("/"))
    monkeypatch.setattr(work_memory, "_repo_roots", lambda path=None: {
        "memory-knowledge": Path("/"), "external": external_root,
    })

    task_id = "task-example"
    now = datetime.now(UTC).replace(microsecond=0)
    classification = {
        "schema_version": 1, "task_id": task_id, "operation_kind": "other",
        "repeatable": True, "meaningful_steps": 3, "verdict": "operational",
        "reason": "repeatable-or-multistep", "created_at_utc": now.isoformat(),
        "expires_at_utc": (now + timedelta(hours=24)).isoformat(),
    }
    _, class_hash = work_memory.write_receipt(task_id, "classification", classification)
    selection = {
        "schema_version": 1, "task_id": task_id, "created_at_utc": now.isoformat(),
        "expires_at_utc": (now + timedelta(hours=24)).isoformat(),
        "classification_receipt_hash": class_hash, "registry_hash": registry_hash,
        "mode": "registered", "subject_id": "example", "lineage_id": "example",
        "document": str(document), "manifest": str(manifest), "source_bundle": bundle,
        "source_bundle_hash": bundle_hash,
    }
    work_memory.write_receipt(task_id, "selection", selection)
    return task_id, document, script, command


def test_missing_receipts_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    with pytest.raises(work_memory.WorkMemoryError, match="missing-classification-receipt"):
        sequence_guard.verify_receipts("missing")


def test_activation_rejects_retired_sequence_id(receipt_flow):
    task_id, document, _, _ = receipt_flow
    assert sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-id", "example",
        "--sequence-doc", str(document),
    ]) == 2


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


def test_guard_rejects_ungrounded_command(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow; state = tmp_path / "active.json"
    sequence_guard.main(["activate", "--task-id", task_id, "--sequence-doc", str(document), "--state", str(state)])
    assert sequence_guard.main([
        "guard", "--task-id", task_id, "--step", "invent", "--command", "python3 made-up.py",
        "--source", "sequence_doc", "--source-ref", str(document), "--state", str(state),
    ]) == 4


def test_tool_help_can_ground_command_with_explicit_evidence(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow
    state = tmp_path / "active.json"
    sequence_guard.main([
        "activate", "--task-id", task_id, "--sequence-doc", str(document), "--state", str(state),
    ])
    common = [
        "guard", "--task-id", task_id, "--step", "help-derived",
        "--command", "python3 scripts/example.py status", "--source", "tool_help",
        "--source-ref", str(document), "--state", str(state),
    ]
    assert sequence_guard.main(common) == 4
    assert sequence_guard.main([
        *common, "--evidence-text", "example.py --help documents the status subcommand",
    ]) == 0


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


def test_status_is_read_only_and_receipt_bound(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow; state = tmp_path / "active.json"
    sequence_guard.main(["activate", "--task-id", task_id, "--sequence-doc", str(document), "--state", str(state)])
    before = state.read_bytes()
    assert sequence_guard.main(["status", "--task-id", task_id, "--state", str(state)]) == 0
    assert state.read_bytes() == before


def test_activate_still_requires_directive_read_state(receipt_flow, tmp_path: Path):
    task_id, document, _, _ = receipt_flow
    with pytest.raises(SystemExit, match="directive read state not found"):
        sequence_guard.main([
            "activate", "--task-id", task_id, "--sequence-doc", str(document),
            "--directive-state", str(tmp_path / "missing.json"),
        ])
