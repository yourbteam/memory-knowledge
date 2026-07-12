from __future__ import annotations

from pathlib import Path
import uuid

import pytest

from scripts import sequence_discovery_log, work_memory
from scripts.sequence_discovery_log import main


def test_start_creates_discovery_log_with_stable_name(tmp_path: Path) -> None:
    result = main(
        [
            "start",
            "--sequence-name",
            "Missing Sequence Smoke",
            "--outcome",
            "Prove the missing-sequence branch records a file.",
            "--why-repeatable",
            "This is the path used when no registered sequence matches.",
            "--root",
            str(tmp_path),
            "--date",
            "2026-06-22",
        ]
    )

    assert result == 0
    log_path = tmp_path / "operations/sequences/discovery/2026-06-22-missing-sequence-smoke.md"
    text = log_path.read_text(encoding="utf-8")
    assert "RegisteredSequenceMatch: none" in text
    assert "Prove the missing-sequence branch records a file." in text
    assert "This is the path used when no registered sequence matches." in text


def test_append_step_records_command_result(tmp_path: Path) -> None:
    main(
        [
            "start",
            "--sequence-name",
            "Missing Sequence Smoke",
            "--outcome",
            "Prove the missing-sequence branch records a file.",
            "--why-repeatable",
            "This is the path used when no registered sequence matches.",
            "--root",
            str(tmp_path),
            "--date",
            "2026-06-22",
        ]
    )
    log_path = tmp_path / "operations/sequences/discovery/2026-06-22-missing-sequence-smoke.md"

    result = main(
        [
            "append-step",
            "--file",
            str(log_path),
            "--step",
            "Confirm registry",
            "--command",
            "test -f operations/sequences/SEQUENCES.md",
            "--result",
            "passed",
            "--note",
            "registry exists",
        ]
    )

    assert result == 0
    text = log_path.read_text(encoding="utf-8")
    assert "| Confirm registry | test -f operations/sequences/SEQUENCES.md | passed | registry exists |" in text


def test_recurred_blocker_prevents_discovery_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    main([
        "start", "--sequence-name", "Recurring", "--outcome", "Run safely.",
        "--why-repeatable", "It recurs.", "--root", str(tmp_path), "--date", "2026-01-01",
    ])
    path = tmp_path / "operations/sequences/discovery/2026-01-01-recurring.md"
    discovery_id = next(
        line.split(":", 1)[1].strip() for line in path.read_text().splitlines()
        if line.startswith("DiscoveryId:")
    )
    run_one, run_two = str(uuid.uuid4()), str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    events = [
        {"event_type": "run_started", "run_id": run_one, "mode": "discovery",
         "subject_id": discovery_id, "source_bundle_hash": "a" * 64},
        {"event_type": "blocker_opened", "run_id": run_one, "blocker_id": blocker_id,
         "lineage_id": discovery_id},
        {"event_type": "blocker_transitioned", "run_id": run_one, "blocker_id": blocker_id,
         "to_status": "closed"},
        {"event_type": "run_started", "run_id": run_two, "mode": "discovery",
         "subject_id": discovery_id, "source_bundle_hash": "a" * 64},
        {"event_type": "blocker_recurred", "run_id": run_two, "blocker_id": blocker_id},
    ]
    monkeypatch.setattr(sequence_discovery_log, "_bundle", lambda path: ([], "a" * 64, discovery_id))
    monkeypatch.setattr(work_memory, "load_ledger", lambda: (events, "b" * 64))
    state = sequence_discovery_log.discovery_state(path)
    assert blocker_id in state["open_blocker_ids"]
    assert "open-blockers" in state["unmet_predicates"]
