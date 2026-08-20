from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "experiment-machinery" / "scripts" / "run_experiment.py"
ADAPTER = ROOT / "skills" / "experiment-machinery" / "scripts" / "intake_purpose_probe.py"
INTAKE_ROOT = ROOT / "skills" / "info-intake-machinery"
REAL_PURPOSE = (
    "the important thing the intake is for is the description in the red rectangles, but each "
    "description is related through its arrow to the element in the page underneath it came from"
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _answers(harness: str) -> list[str]:
    return [
        "test-reader",
        harness,
        "yes",
        "The purpose explicitly names the descriptions and their arrow relationships.",
        REAL_PURPOSE,
    ]


def _source_sha256(path: Path) -> str:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--hash-source", str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _write_spec(
    root: Path,
    variants: list[tuple[str, list[str]]],
    *,
    input_sha256: str | None = None,
) -> Path:
    frozen = root / "purpose-input.json"
    frozen.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "opening": "There is a new intake",
                "purpose": REAL_PURPOSE,
                "expected_boundary": "awaiting_first_source",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    spec = root / "experiment.json"
    spec.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "experiment_id": "intake-purpose-assessment",
                "hypothesis": (
                    "The unchanged Intake purpose phase can compare isolated setups from one "
                    "frozen purpose and deterministically recommend the setup that reaches the "
                    "expected boundary with the fewest rejected answers."
                ),
                "target": {
                    "machinery": "info-intake-machinery",
                    "phase": "assess-intake-purpose",
                    "source": {
                        "path": str(INTAKE_ROOT),
                        "sha256": _source_sha256(INTAKE_ROOT),
                    },
                    "entrypoint": "scripts/start_intake.py",
                },
                "frozen_input": {
                    "path": frozen.name,
                    "sha256": input_sha256 or _digest(frozen),
                },
                "variants": [
                    {
                        "id": variant_id,
                        "command": [
                            sys.executable,
                            str(ADAPTER),
                        ],
                        "configuration": {"answers": answers},
                    }
                    for variant_id, answers in variants
                ],
                "evaluation": {
                    "metrics": [
                        {"name": "reached-expected-boundary", "direction": "maximize"},
                        {"name": "rejected-answer-count", "direction": "minimize"},
                        {"name": "answer-count", "direction": "minimize"},
                    ]
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return spec


def _run(spec: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), "--spec", str(spec), "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _assert_hash_chain(path: Path) -> None:
    previous = None
    for sequence, record in enumerate(_records(path), start=1):
        assert record["sequence"] == sequence
        assert record["previous_entry_sha256"] == previous
        claimed = record.pop("entry_sha256")
        assert claimed == hashlib.sha256(_canonical(record)).hexdigest()
        previous = claimed


def test_real_intake_phase_runs_three_isolated_variants_and_repeats_champion(
    tmp_path: Path,
) -> None:
    spec = _write_spec(
        tmp_path,
        [
            ("control", _answers("experiment-control")),
            (
                "cautious",
                [
                    "test-reader",
                    "experiment-cautious",
                    "no",
                    "The purpose does not state a complete preservation boundary.",
                    "What exact arrow relationships must the projection preserve?",
                ],
            ),
            (
                "recovery",
                [
                    "test-reader",
                    "experiment-recovery",
                    "yes",
                    "The purpose names the descriptions and their arrow relationships.",
                    "a paraphrase rather than source words",
                    REAL_PURPOSE,
                ],
            ),
        ],
    )
    intake_before = _source_sha256(INTAKE_ROOT)
    first_output = tmp_path / "run-one"
    second_output = tmp_path / "run-two"

    first = _run(spec, first_output)
    second = _run(spec, second_output)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_summary = json.loads((first_output / "summary.json").read_text())
    second_summary = json.loads((second_output / "summary.json").read_text())
    assert first_summary["champion"] == second_summary["champion"] == "control"
    assert first_summary["ranking"] == second_summary["ranking"]
    assert first_summary["promotion_applied"] is False
    assert len(first_summary["variants"]) == 3
    assert all(row["status"] == "completed" for row in first_summary["variants"])
    assert _source_sha256(INTAKE_ROOT) == intake_before

    ledger = _records(first_output / "ledger.jsonl")
    events = [record["event"] for record in ledger]
    assert events == [
        "experiment_started",
        "variant_started",
        "variant_started",
        "variant_started",
        "variant_finished",
        "variant_finished",
        "variant_finished",
        "evaluation_completed",
    ]
    assert ledger[-1]["promotion_applied"] is False
    _assert_hash_chain(first_output / "ledger.jsonl")

    frozen_sha256 = first_summary["frozen_input_sha256"]
    assert (os.stat(first_output / "frozen-input.bin").st_mode & 0o222) == 0
    for variant_id in ("control", "cautious", "recovery"):
        variant_root = first_output / "variants" / variant_id
        assert _digest(variant_root / "frozen-input.bin") == frozen_sha256
        assert (os.stat(variant_root / "target" / "scripts" / "start_intake.py").st_mode & 0o222) == 0
        assert (variant_root / "target-work" / "ledger.jsonl").is_file()
        _assert_hash_chain(variant_root / "telemetry.jsonl")

    recovery_events = _records(first_output / "variants" / "recovery" / "telemetry.jsonl")
    assert sum(record["event"] == "answer_rejected" for record in recovery_events) == 1
    recovery = next(
        row for row in first_summary["variants"] if row["variant_id"] == "recovery"
    )
    assert recovery["metrics"]["rejected-answer-count"] == 1


def test_failed_variant_is_preserved_and_excluded_without_blocking_a_champion(
    tmp_path: Path,
) -> None:
    spec = _write_spec(
        tmp_path,
        [
            ("control", _answers("experiment-control")),
            ("broken", ["test-reader"]),
        ],
    )
    output = tmp_path / "run"

    completed = _run(spec, output)

    assert completed.returncode == 0, completed.stderr
    summary = json.loads((output / "summary.json").read_text())
    assert summary["champion"] == "control"
    broken = next(row for row in summary["variants"] if row["variant_id"] == "broken")
    assert broken["status"] == "failed"
    assert broken["eligible"] is False
    assert (output / "variants" / "broken" / "result.json").is_file()
    assert "ended before Info Intake completed" in (
        output / "variants" / "broken" / "stderr.txt"
    ).read_text(encoding="utf-8")
    assert summary["promotion_applied"] is False


def test_wrong_frozen_input_hash_is_refused_before_any_run_artifact(tmp_path: Path) -> None:
    spec = _write_spec(
        tmp_path,
        [
            ("control", _answers("experiment-control")),
            ("variation", _answers("experiment-variation")),
        ],
        input_sha256="0" * 64,
    )
    output = tmp_path / "run"

    completed = _run(spec, output)

    assert completed.returncode == 2
    assert "does not match the exact input bytes" in completed.stderr
    assert not output.exists()
