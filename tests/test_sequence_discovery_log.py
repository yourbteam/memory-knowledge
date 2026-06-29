from __future__ import annotations

from pathlib import Path

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
