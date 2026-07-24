from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from scripts import prevention_journal, work_memory


TASK_ID = "task-123"
RUN_ID = "4f642f31-f326-4b2c-92e4-753826ecad9f"
WORKTREE_ID = "a" * 64


def ownership() -> prevention_journal.JournalOwnership:
    return prevention_journal.JournalOwnership(
        task_id=TASK_ID,
        run_id=RUN_ID,
        branch_ref=f"task/{TASK_ID}",
        worktree_id=WORKTREE_ID,
    )


def intent_payload() -> dict:
    return {
        "intent_id": str(uuid.uuid4()),
        "requested_sequence_id": "discovery-bootstrap",
        "requested_implementation_id": "b" * 64,
        "compatibility_key": "c" * 64,
        "action_class": "BASH",
        "parameters": [{"name": "spec", "value": {"tag": "PATH", "value": "spec.json"}}],
    }


def test_journal_appends_replays_and_repairs_checkpoint(tmp_path: Path):
    journal = prevention_journal.PreventionJournal(tmp_path / "run", ownership())

    result = journal.append("action_intent_recorded", intent_payload())

    assert result["checkpoint"]["event_count"] == 1
    events, ledger_hash = journal.replay()
    assert events[0]["task_id"] == TASK_ID
    assert events[0]["branch_ref"] == f"task/{TASK_ID}"
    assert result["checkpoint"]["ledger_sha256"] == ledger_hash
    journal.checkpoint.write_text("{}", encoding="utf-8")
    repaired = journal.load_checkpoint()
    assert repaired["event_count"] == 1
    assert json.loads(journal.checkpoint.read_text(encoding="utf-8")) == repaired


def test_journal_rejects_caller_supplied_ownership(tmp_path: Path):
    journal = prevention_journal.PreventionJournal(tmp_path / "run", ownership())
    payload = {**intent_payload(), "task_id": "foreign"}

    with pytest.raises(work_memory.WorkMemoryError, match="caller-supplied-journal-ownership"):
        journal.append("action_intent_recorded", payload)


def test_journal_rejects_foreign_task_branch():
    with pytest.raises(work_memory.WorkMemoryError, match="task-branch-ownership-mismatch"):
        prevention_journal.JournalOwnership(
            task_id=TASK_ID,
            run_id=RUN_ID,
            branch_ref="task/foreign",
            worktree_id=WORKTREE_ID,
        )


def test_event_contract_rejects_extra_and_missing_fields(tmp_path: Path):
    journal = prevention_journal.PreventionJournal(tmp_path / "run", ownership())
    payload = intent_payload()
    payload["raw_command"] = "echo unsafe"
    with pytest.raises(work_memory.WorkMemoryError, match="unknown-event-fields"):
        journal.append("action_intent_recorded", payload)

    payload = intent_payload()
    del payload["parameters"]
    with pytest.raises(work_memory.WorkMemoryError, match="missing-event-fields"):
        journal.append("action_intent_recorded", payload)


def test_timing_interval_requires_exact_duration(tmp_path: Path):
    journal = prevention_journal.PreventionJournal(tmp_path / "run", ownership())
    with pytest.raises(work_memory.WorkMemoryError, match="invalid-timing-duration"):
        journal.append("timing_interval_recorded", {
            "interval_id": str(uuid.uuid4()),
            "timing_class": "MECHANICAL_RETRY",
            "started_at_utc": "2026-07-17T10:00:00Z",
            "ended_at_utc": "2026-07-17T10:00:01Z",
            "duration_milliseconds": 999,
        })
