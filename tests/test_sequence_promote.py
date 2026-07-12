from __future__ import annotations

import json
import uuid
from argparse import Namespace
from pathlib import Path

import pytest

from scripts import sequence_promote, work_memory


def configure_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state = tmp_path / "state"; state.mkdir()
    monkeypatch.setattr(sequence_promote, "STATE_DIR", state)
    monkeypatch.setattr(sequence_promote, "JOURNAL", state / "promotion.json")
    monkeypatch.setattr(sequence_promote, "PROMOTION_LOCK", state / "promotion.lock")
    return state


def journal_target(tmp_path: Path, name: str, pre: bytes, staged: bytes, observed: bytes | None = None):
    target = tmp_path / name; target.write_bytes(pre if observed is None else observed)
    staged_path = tmp_path / f"{name}.staged"; staged_path.write_bytes(staged)
    backup = tmp_path / f"{name}.backup"; backup.write_bytes(pre)
    return {
        "path": str(target), "preimage_hash": work_memory.sha256_bytes(pre),
        "staged_hash": work_memory.sha256_bytes(staged), "staged_path": str(staged_path),
        "backup_path": str(backup), "preimage_bytes": sequence_promote._encode(pre),
    }


def write_journal(phase: str, targets: list[dict]):
    sequence_promote.JOURNAL.write_text(json.dumps({
        "schema_version": 1, "phase": phase, "targets": targets,
    }))


def test_recovery_prepared_cleans_without_target_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    configure_state(tmp_path, monkeypatch); target = journal_target(tmp_path, "one", b"old", b"new")
    write_journal("PREPARED", [target])
    assert sequence_promote.recover() == {"recovered": "prepared-cleaned"}
    assert Path(target["path"]).read_bytes() == b"old" and not sequence_promote.JOURNAL.exists()


def test_recovery_applying_mixture_restores_all_preimages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    configure_state(tmp_path, monkeypatch)
    first = journal_target(tmp_path, "one", b"old1", b"new1", b"new1")
    second = journal_target(tmp_path, "two", b"old2", b"new2", b"old2")
    write_journal("APPLYING", [first, second])
    assert sequence_promote.recover() == {"recovered": "applying-rolled-back"}
    assert Path(first["path"]).read_bytes() == b"old1"
    assert Path(second["path"]).read_bytes() == b"old2"


def test_recovery_unknown_hash_conflicts_and_preserves_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    configure_state(tmp_path, monkeypatch)
    target = journal_target(tmp_path, "one", b"old", b"new", b"unknown")
    write_journal("APPLYING", [target])
    with pytest.raises(work_memory.WorkMemoryError, match="promotion-recovery-conflict"):
        sequence_promote.recover()
    assert sequence_promote.JOURNAL.exists() and Path(target["backup_path"]).exists()


def promoted_discovery(path: Path, discovery_id: str, sequence_id: str):
    path.parent.mkdir(parents=True)
    path.write_text(f"""# Sequence Discovery Log: retry

DiscoveryId: {discovery_id}
Status: promoted
PromotedSequenceId: {sequence_id}
CreatedAtUtc: 2026-01-01T00:00:00Z
RegisteredSequenceMatch: none

## Intended Outcome

Retry promotion.

## Why This Looks Repeatable

Stable.

## Required Inputs, Auth, Or Environment

- input

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| run | echo ok | passed | none |

## Failure Handling

Stop.

## Verified Path

- Passed twice.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
""")


def test_exact_committed_promotion_retry_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    configure_state(tmp_path, monkeypatch); monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    discovery_id, sequence_id = "discovery-id", "registered-id"
    discovery = tmp_path / "operations/sequences/discovery/retry.md"
    promoted_discovery(discovery, discovery_id, sequence_id)
    source_manifest = {"schema_version": 1, "lineage_id": discovery_id, "dependencies": []}
    discovery.with_suffix(".dependencies.json").write_text(json.dumps(source_manifest))
    sequence_path = tmp_path / f"operations/sequences/{sequence_id}/sequence.md"
    sequence_path.parent.mkdir(parents=True)
    args = Namespace(
        file=str(discovery), sequence_id=sequence_id, use_when="Use for retries.",
        operation_kind=["other"], automation_display="none", pass_signal="PASS",
    )
    sequence_path.write_bytes(sequence_promote._sequence_text(discovery, sequence_id, args.use_when, args.pass_signal))
    sequence_path.with_name("dependencies.json").write_bytes(work_memory.canonical_bytes(source_manifest))
    monkeypatch.setattr(sequence_promote.sequence_discovery_log, "discovery_state", lambda path: {
        "status": "promoted", "discovery_id": discovery_id, "source_bundle_hash": "a" * 64,
    })
    monkeypatch.setattr(work_memory, "resolve_bundle", lambda **kwargs: ([], "b" * 64, discovery_id))
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([{
        "sequence_id": sequence_id, "lineage_id": discovery_id, "use_when": args.use_when,
        "automation": args.automation_display, "pass_signal": args.pass_signal,
        "operation_kinds": "other",
    }], "c" * 64))
    promoted = {"event_type": "discovery_promoted", "discovery_id": discovery_id,
                "sequence_id": sequence_id, "old_bundle_hash": "a" * 64,
                "new_bundle_hash": "b" * 64, "event_id": str(uuid.uuid4())}
    transition = {"event_type": "bundle_transition_recorded", "transition_reason": "promotion",
                  "discovery_id": discovery_id, "promoted_sequence_id": sequence_id,
                  "new_bundle_hash": "b" * 64, "event_id": str(uuid.uuid4())}
    monkeypatch.setattr(work_memory, "load_ledger", lambda: ([promoted, transition], "d" * 64))
    result = sequence_promote.cmd_promote(args)
    assert result["idempotent_retry"] and result["event_id"] == promoted["event_id"]
