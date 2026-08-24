from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from scripts import (
    discovery_bootstrap, sequence_candidate_contract,
    sequence_discovery_log, work_memory,
)
from scripts.directive_guard import write_directive_read_state


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "memory-knowledge"
    (root / "scripts").mkdir(parents=True)
    (root / "working-agreement").mkdir(parents=True)
    (root / "operations/sequences").mkdir(parents=True)
    (root / "operations/sequences/SEQUENCES.md").write_text("# Sequences\n", encoding="utf-8")
    (root / "working-agreement/DIRECTIVES.md").write_text("# Directives\n", encoding="utf-8")
    for name in work_memory.BOOTSTRAP_TRUST_ANCHORS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")
    (root / "scripts/example.py").write_text("print('ok')\n", encoding="utf-8")
    return root


def _spec() -> dict[str, object]:
    return {
        "schema_version": 1,
        "task_id": "bootstrap-test-task",
        "operation_kind": "other",
        "date": "2026-07-15",
        "sequence_name": "Example Discovery",
        "outcome": "Start the exact governed discovery.",
        "why_repeatable": "This missing operation will recur.",
        "steps": [{
            "step": "run-example",
            "command": "python3 scripts/example.py run",
            "result": "required",
            "note": "Execute only after activation.",
        }],
        "inputs": ["A checked-out memory-knowledge repository."],
        "failure_handling": "Stop on the first non-zero exit and retain its error envelope.",
        "verified_path": "The first command passes sequence_guard before execution.",
        "dependencies": [{
            "kind": "file",
            "repository_key": "memory-knowledge",
            "path_or_sequence_id": "scripts/example.py",
        }],
    }


def _v2_spec() -> dict[str, object]:
    identity, fingerprint = sequence_candidate_contract.build_candidate_identity({
        "intended_outcome": "Start the exact governed discovery.",
        "repeatability_reason": "The operation recurs.",
        "repeatability_evidence_ids": ["prior-run"],
        "required_inputs": ["A checked-out memory-knowledge repository."],
        "dependencies": [{"repository_key": "memory-knowledge", "path": "scripts/example.py"}],
        "failure_handling": [{
            "fingerprint": "a" * 64, "symptom": "example exits nonzero", "response": "stop",
        }],
        "verification_contract": {
            "quality": "same-path", "expected_outcome": "passed",
            "success_evidence": "the example command exits zero",
        },
        "effect_class": "idempotent-local", "environment_annotations": [],
        "semantic_flag_annotations": [], "volatility_annotations": [],
    }, [{
        "step_ordinal": 0, "step_id": "run-example",
        "argv": ["python3", "scripts/example.py", "run"], "command_source": "script",
        "source_ref": {"repository_key": "memory-knowledge", "path": "scripts/example.py"},
        "operation_kind": "other",
    }])
    return {
        **_spec(),
        "task_id": "bootstrap-v2-test-task",
        "sequence_name": "Example Discovery V2",
        "candidate_identity": identity,
        "candidate_fingerprint": fingerprint,
        "observer_provenance": {
            "decision_id": str(uuid.uuid4()),
            "observer_version": 1,
            "rule_version": 1,
        },
    }


def test_registered_sequence_declares_protected_correction_launcher() -> None:
    sequence = (
        Path(__file__).parents[1]
        / "operations/sequences/discovery-bootstrap/sequence.md"
    ).read_text(encoding="utf-8")

    assert "python3 scripts/work_memory_bootstrap_launcher.py correct" in sequence
    assert "--changed-environment-artifact <absolute-host-path>" in sequence


def test_normalize_spec_rejects_unknown_keys_and_secret_shapes() -> None:
    with pytest.raises(work_memory.WorkMemoryError, match="invalid-bootstrap-spec-shape"):
        discovery_bootstrap.normalize_spec({**_spec(), "unknown": True})
    with pytest.raises(work_memory.WorkMemoryError, match="prohibited-secret-shape"):
        discovery_bootstrap.normalize_spec({
            **_spec(), "outcome": "Use Bearer abcdefghijklmnopqrstuvwxyz123456",
        })


def test_v2_bootstrap_preserves_identity_and_observer_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    receipts = tmp_path / "receipts-v2"
    directive_state = tmp_path / "directive-state-v2.json"
    write_directive_read_state(
        directives_path=root / "working-agreement/DIRECTIVES.md",
        state_path=directive_state,
        mode="test",
    )
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", receipts)
    monkeypatch.setenv("MK_DIRECTIVE_STATE_PATH", str(directive_state))
    spec = discovery_bootstrap.normalize_spec(_v2_spec())
    original = (work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW, work_memory.REGISTRY)
    try:
        monkeypatch.setenv(
            "WORK_MEMORY_REGISTRY_GOVERNANCE_LEVEL", "UNGOVERNED_DIAGNOSTIC"
        )
        result = discovery_bootstrap.bootstrap(spec, root=root, repo_roots_file=None)
    finally:
        work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW, work_memory.REGISTRY = original
        work_memory.REGISTRY_GOVERNANCE_LEVEL = "FULLY_GOVERNED"

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["candidate_identity"] == spec["candidate_identity"]
    assert manifest["candidate_fingerprint"] == spec["candidate_fingerprint"]
    assert manifest["observer_provenance"] == spec["observer_provenance"]


def test_bootstrap_creates_exact_bundle_and_recovers_same_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    receipts = tmp_path / "receipts"
    directive_state = tmp_path / "directive-state.json"
    write_directive_read_state(
        directives_path=root / "working-agreement/DIRECTIVES.md",
        state_path=directive_state,
        mode="test",
    )
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", receipts)
    monkeypatch.setenv("MK_DIRECTIVE_STATE_PATH", str(directive_state))
    original_root = work_memory.ROOT
    original_ledger = work_memory.LEDGER
    original_view = work_memory.BLOCKER_VIEW
    original_registry = work_memory.REGISTRY
    try:
        spec = discovery_bootstrap.normalize_spec(_spec())
        monkeypatch.setenv(
            "WORK_MEMORY_REGISTRY_GOVERNANCE_LEVEL", "UNGOVERNED_DIAGNOSTIC"
        )
        first = discovery_bootstrap.bootstrap(spec, root=root, repo_roots_file=None)
        second = discovery_bootstrap.bootstrap(spec, root=root, repo_roots_file=None)
    finally:
        work_memory.ROOT = original_root
        work_memory.LEDGER = original_ledger
        work_memory.BLOCKER_VIEW = original_view
        work_memory.REGISTRY = original_registry
        work_memory.REGISTRY_GOVERNANCE_LEVEL = "FULLY_GOVERNED"

    assert first["ok"] is True
    assert first["recovered"] is False
    assert second["recovered"] is True
    assert second["run_id"] == first["run_id"]
    assert second["event_id"] == first["event_id"]
    events = [
        json.loads(line)
        for line in (root / "operations/work-memory/events.jsonl").read_text().splitlines()
    ]
    assert [event["event_type"] for event in events] == [
        "task_writer_claimed", "run_started",
    ]
    assert events[0]["task_id"] == spec["task_id"]
    assert events[1]["task_id"] == spec["task_id"]
    assert events[1]["ownership_event_id"] == events[0]["event_id"]
    document = Path(first["discovery_path"])
    assert f"BootstrapRequestSha256: {first['bootstrap_request_sha256']}" in document.read_text()
    assert "| run-example | python3 scripts/example.py run | required |" in document.read_text()


def test_bootstrap_persists_source_visible_prevention_identity_before_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    receipts = tmp_path / "receipts-prevention"
    directive_state = tmp_path / "directive-state-prevention.json"
    write_directive_read_state(
        directives_path=root / "working-agreement/DIRECTIVES.md",
        state_path=directive_state,
        mode="test",
    )
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", receipts)
    monkeypatch.setenv("MK_DIRECTIVE_STATE_PATH", str(directive_state))
    effect_id = "e" * 64
    preparation_sha256 = "f" * 64
    original = (
        work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW,
        work_memory.REGISTRY,
    )
    try:
        monkeypatch.setenv(
            "WORK_MEMORY_REGISTRY_GOVERNANCE_LEVEL", "UNGOVERNED_DIAGNOSTIC"
        )
        result = discovery_bootstrap.bootstrap(
            discovery_bootstrap.normalize_spec(_spec()),
            root=root,
            repo_roots_file=None,
            prevention_effect_id=effect_id,
            prevention_preparation_sha256=preparation_sha256,
        )
    finally:
        (
            work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW,
            work_memory.REGISTRY,
        ) = original
        work_memory.REGISTRY_GOVERNANCE_LEVEL = "FULLY_GOVERNED"

    receipt_path = Path(result["preventionReceiptPath"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt == {
        "schema_version": 1,
        "owner_sequence_id": "discovery-bootstrap",
        "profile_id": "start",
        "effect_id": effect_id,
        "preparation_artifact_sha256": preparation_sha256,
        "status": "APPLIED",
        "source_identity": {
            "bootstrap_request_sha256": result["bootstrap_request_sha256"],
            "discovery_path": result["discovery_path"],
            "manifest_path": result["manifest_path"],
            "run_id": result["run_id"],
            "event_id": result["event_id"],
        },
    }
    assert result["preventionReceiptSha256"] == work_memory.sha256_bytes(
        work_memory.canonical_bytes(receipt)
    )


def test_bootstrap_rejects_half_bound_prevention_identity(tmp_path: Path) -> None:
    with pytest.raises(
        work_memory.WorkMemoryError,
        match="incomplete-prevention-effect-identity",
    ):
        discovery_bootstrap.bootstrap(
            discovery_bootstrap.normalize_spec(_spec()),
            root=_root(tmp_path),
            repo_roots_file=None,
            prevention_effect_id="e" * 64,
        )


def test_matching_document_without_manifest_is_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    receipts = tmp_path / "receipts"
    directive_state = tmp_path / "directive-state.json"
    write_directive_read_state(
        directives_path=root / "working-agreement/DIRECTIVES.md",
        state_path=directive_state,
        mode="test",
    )
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", receipts)
    monkeypatch.setenv("MK_DIRECTIVE_STATE_PATH", str(directive_state))
    spec = discovery_bootstrap.normalize_spec(_spec())
    request_digest = work_memory.sha256_bytes(work_memory.canonical_bytes({
        "spec": spec, "repo_roots_file": None,
    }))
    document, text, _ = sequence_discovery_log.render_discovery_bundle(
        root=root, date_text=str(spec["date"]), sequence_name=str(spec["sequence_name"]),
        outcome=str(spec["outcome"]), why_repeatable=str(spec["why_repeatable"]),
        created_at_utc="2026-07-15T00:00:00Z", steps=spec["steps"],
        inputs=spec.get("inputs"), failure_handling=spec.get("failure_handling"),
        verified_path=spec.get("verified_path"), dependencies=spec["dependencies"],
        bootstrap_request_sha256=request_digest,
    )
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(text, encoding="utf-8")
    original = (work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW, work_memory.REGISTRY)
    try:
        monkeypatch.setenv(
            "WORK_MEMORY_REGISTRY_GOVERNANCE_LEVEL", "UNGOVERNED_DIAGNOSTIC"
        )
        result = discovery_bootstrap.bootstrap(spec, root=root, repo_roots_file=None)
    finally:
        work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW, work_memory.REGISTRY = original
        work_memory.REGISTRY_GOVERNANCE_LEVEL = "FULLY_GOVERNED"

    assert result["ok"] is True
    assert document.with_suffix(".dependencies.json").is_file()


def test_bootstrap_persists_cross_repository_root_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    external = tmp_path / "external"
    dependency = external / "scripts/external.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("print('external')\n", encoding="utf-8")
    directive_state = tmp_path / "directive-state-cross-root.json"
    write_directive_read_state(
        directives_path=root / "working-agreement/DIRECTIVES.md",
        state_path=directive_state,
        mode="test",
    )
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path / "receipts-cross-root")
    monkeypatch.setenv("MK_DIRECTIVE_STATE_PATH", str(directive_state))
    spec = discovery_bootstrap.normalize_spec({
        **_spec(),
        "task_id": "bootstrap-cross-root-task",
        "sequence_name": "Cross Root Discovery",
        "steps": [{
            "step": "run-external", "command": "python3 scripts/external.py run",
            "result": "required", "note": "Execute only after activation.",
        }],
        "dependencies": [{
            "kind": "file", "repository_key": "external",
            "path_or_sequence_id": "scripts/external.py",
        }],
    })
    roots = {"memory-knowledge": str(root), "external": str(external)}
    original = (work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW, work_memory.REGISTRY)
    try:
        monkeypatch.setenv(
            "WORK_MEMORY_REGISTRY_GOVERNANCE_LEVEL", "UNGOVERNED_DIAGNOSTIC"
        )
        result = discovery_bootstrap.bootstrap(
            spec, root=root, repo_roots_file=None, repository_roots=roots,
        )
        selection, _, _ = work_memory.load_receipt(spec["task_id"], "selection")
        events, _ = work_memory.load_ledger()
    finally:
        work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW, work_memory.REGISTRY = original
        work_memory.REGISTRY_GOVERNANCE_LEVEL = "FULLY_GOVERNED"

    assert result["ok"] is True
    assert selection["repository_roots"] == roots
    started = next(event for event in events if event["event_type"] == "run_started")
    assert started["repository_roots"] == roots
