from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import discovery_bootstrap, sequence_discovery_log, work_memory
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


def test_normalize_spec_rejects_unknown_keys_and_secret_shapes() -> None:
    with pytest.raises(work_memory.WorkMemoryError, match="invalid-bootstrap-spec-shape"):
        discovery_bootstrap.normalize_spec({**_spec(), "unknown": True})
    with pytest.raises(work_memory.WorkMemoryError, match="prohibited-secret-shape"):
        discovery_bootstrap.normalize_spec({
            **_spec(), "outcome": "Use Bearer abcdefghijklmnopqrstuvwxyz123456",
        })


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
        first = discovery_bootstrap.bootstrap(spec, root=root, repo_roots_file=None)
        second = discovery_bootstrap.bootstrap(spec, root=root, repo_roots_file=None)
    finally:
        work_memory.ROOT = original_root
        work_memory.LEDGER = original_ledger
        work_memory.BLOCKER_VIEW = original_view
        work_memory.REGISTRY = original_registry

    assert first["ok"] is True
    assert first["recovered"] is False
    assert second["recovered"] is True
    assert second["run_id"] == first["run_id"]
    assert second["event_id"] == first["event_id"]
    events = [
        json.loads(line)
        for line in (root / "operations/work-memory/events.jsonl").read_text().splitlines()
    ]
    assert [event["event_type"] for event in events] == ["run_started"]
    document = Path(first["discovery_path"])
    assert f"BootstrapRequestSha256: {first['bootstrap_request_sha256']}" in document.read_text()
    assert "| run-example | python3 scripts/example.py run | required |" in document.read_text()


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
        result = discovery_bootstrap.bootstrap(spec, root=root, repo_roots_file=None)
    finally:
        work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW, work_memory.REGISTRY = original

    assert result["ok"] is True
    assert document.with_suffix(".dependencies.json").is_file()
