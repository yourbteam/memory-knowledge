from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "experiment-machinery" / "scripts" / "run_experiment.py"
ADAPTER = ROOT / "skills" / "experiment-machinery" / "scripts" / "intake_purpose_probe.py"
TERMINAL_ADAPTER = (
    ROOT
    / "skills"
    / "experiment-machinery"
    / "scripts"
    / "intake_projection_terminal_probe.py"
)
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


def _terminal_adapter_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "test_intake_projection_terminal_probe", TERMINAL_ADAPTER,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_terminal_probe_schema_keeps_citation_uniqueness_out_of_provider_schema() -> None:
    adapter = _terminal_adapter_module()

    schema = adapter._response_schema()

    citations = schema["properties"]["compared_relationship_ids"]
    assert "uniqueItems" not in citations
    assert adapter._controlled_citations(["relationship-1", "relationship-2"]) == [
        "relationship-1", "relationship-2",
    ]
    try:
        adapter._controlled_citations(["relationship-1", "relationship-1"])
    except adapter.ProbeError as error:
        assert str(error) == "model response contains duplicate relationship citations"
    else:
        raise AssertionError("duplicate citations must fail closed")


def _write_spec(
    root: Path,
    variants: list[tuple[str, list[str]]],
    *,
    input_sha256: str | None = None,
) -> Path:
    evaluator = root / "evaluator.py"
    evaluator.write_text(
        """from __future__ import annotations
import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
scores = []
for candidate in request["candidates"]:
    telemetry = next(item["path"] for item in candidate["evidence"] if item["id"] == "telemetry")
    events = [json.loads(line) for line in Path(telemetry).read_text(encoding="utf-8").splitlines()]
    finished = next(item for item in events if item["event"] == "phase_finished")
    scores.append({"variant_id": candidate["variant_id"], "metrics": finished["metrics"]})
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
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
                "schema_version": 4,
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
                "execution_limits": {
                    "variant_timeout_ms": 5000,
                    "evaluator_timeout_ms": 5000,
                },
                "variants": [
                    {
                        "id": variant_id,
                        "command": [
                            sys.executable,
                            str(ADAPTER),
                        ],
                        "adapter": {
                            "path": str(ADAPTER),
                            "sha256": _digest(ADAPTER),
                        },
                        "configuration": {"answers": answers},
                    }
                    for variant_id, answers in variants
                ],
                "evaluation": {
                    "metrics": [
                        {"name": "reached-expected-boundary", "direction": "maximize"},
                        {"name": "rejected-answer-count", "direction": "minimize"},
                        {"name": "answer-count", "direction": "minimize"},
                    ],
                    "evaluator": {
                        "adapter": {
                            "path": str(evaluator),
                            "sha256": _digest(evaluator),
                        },
                        "command": [
                            "{python}",
                            "{evaluation-adapter}",
                            "{evaluation-request}",
                            "{evaluation-response}"
                        ]
                    }
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
        "evaluator_started",
        "evaluator_finished",
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


def _independent_scoring_spec(tmp_path: Path) -> tuple[Path, Path]:
    target = tmp_path / "target"
    target.mkdir()
    (target / "entry.py").write_text("VALUE = 'target'\n", encoding="utf-8")
    frozen = tmp_path / "input.json"
    frozen.write_text('{"case":"self-score"}\n', encoding="utf-8")
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        """from __future__ import annotations
import json
import os
import time
from pathlib import Path

variant = json.loads(Path(os.environ["EXPERIMENT_VARIANT_PATH"]).read_text(encoding="utf-8"))
configuration = variant["configuration"]
print("candidate-started", flush=True)
if configuration.get("hang"):
    while True:
        time.sleep(1)
result = {
    "schema_version": 1,
    "variant_id": variant["variant_id"],
    "status": "completed",
    "outcome": {"correct": configuration["correct"]},
    "metrics": {"quality": configuration["claimed_quality"]},
    "error": None,
}
Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps(result, sort_keys=True) + "\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text(
        """from __future__ import annotations
import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
scores = [
    {"variant_id": item["variant_id"], "metrics": {"quality": 1 if item["outcome"]["correct"] else 0}}
    for item in request["candidates"]
]
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    spec = {
        "schema_version": 4,
        "experiment_id": "independent-self-score",
        "hypothesis": "Candidate claims cannot determine the winner.",
        "target": {
            "machinery": "experiment-machinery",
            "phase": "independent-scoring",
            "source": {"path": str(target), "sha256": _source_sha256(target)},
            "entrypoint": "entry.py",
        },
        "frozen_input": {"path": str(frozen), "sha256": _digest(frozen)},
        "execution_limits": {
            "variant_timeout_ms": 5000,
            "evaluator_timeout_ms": 5000,
        },
        "variants": [
            {
                "id": "control",
                "command": [sys.executable, str(candidate)],
                "adapter": {"path": str(candidate), "sha256": _digest(candidate)},
                "configuration": {"correct": True, "claimed_quality": 1},
            },
            {
                "id": "inflated",
                "command": [sys.executable, str(candidate)],
                "adapter": {"path": str(candidate), "sha256": _digest(candidate)},
                "configuration": {"correct": False, "claimed_quality": 999},
            },
        ],
        "evaluation": {
            "metrics": [{"name": "quality", "direction": "maximize"}],
            "evaluator": {
                "adapter": {"path": str(evaluator), "sha256": _digest(evaluator)},
                "command": [
                    "{python}",
                    "{evaluation-adapter}",
                    "{evaluation-request}",
                    "{evaluation-response}",
                ],
            },
        },
    }
    spec_path = tmp_path / "independent-experiment.json"
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return spec_path, evaluator


def test_independent_evaluator_ignores_inflated_candidate_score(tmp_path: Path) -> None:
    spec, _ = _independent_scoring_spec(tmp_path)
    output = tmp_path / "run"

    completed = _run(spec, output)

    assert completed.returncode == 0, completed.stderr
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["champion"] == "control"
    inflated = next(item for item in summary["variants"] if item["variant_id"] == "inflated")
    assert inflated["reported_metrics"] == {"quality": 999}
    assert inflated["metrics"] == {"quality": 0.0}


def test_changed_evaluator_is_refused_before_variant_execution(tmp_path: Path) -> None:
    spec, evaluator = _independent_scoring_spec(tmp_path)
    evaluator.write_text(evaluator.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    output = tmp_path / "run"

    completed = _run(spec, output)

    assert completed.returncode == 2
    assert "evaluation.evaluator.adapter changed" in completed.stderr
    assert not output.exists()


def test_hung_variant_is_terminated_and_preserved_without_blocking_a_champion(
    tmp_path: Path,
) -> None:
    spec_path, _ = _independent_scoring_spec(tmp_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["execution_limits"]["variant_timeout_ms"] = 100
    spec["variants"][0]["configuration"]["hang"] = True
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = tmp_path / "run"

    started = time.monotonic()
    completed = _run(spec_path, output)

    assert completed.returncode == 0, completed.stderr
    assert time.monotonic() - started < 2
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    control = next(item for item in summary["variants"] if item["variant_id"] == "control")
    assert control["timed_out"] is True
    assert control["eligible"] is False
    assert control["status"] == "failed"
    assert summary["champion"] == "inflated"
    assert "candidate-started" in (output / "variants" / "control" / "stdout.txt").read_text()
    assert any(
        record["event"] == "variant_finished" and record["timed_out"] is True
        for record in _records(output / "ledger.jsonl")
    )


def test_hung_evaluator_is_terminated_with_terminal_summary_and_evidence(
    tmp_path: Path,
) -> None:
    spec_path, evaluator = _independent_scoring_spec(tmp_path)
    evaluator.write_text(
        "import time\nprint('evaluator-started', flush=True)\nwhile True:\n    time.sleep(1)\n",
        encoding="utf-8",
    )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["execution_limits"]["evaluator_timeout_ms"] = 100
    spec["evaluation"]["evaluator"]["adapter"]["sha256"] = _digest(evaluator)
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = tmp_path / "run"

    started = time.monotonic()
    completed = _run(spec_path, output)

    assert completed.returncode == 3, completed.stderr
    assert time.monotonic() - started < 2
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "evaluator-timeout"
    assert summary["champion"] is None
    assert summary["evaluation_error"]["kind"] == "timeout"
    assert (output / "evaluation" / "timeout.json").is_file()
    assert "evaluator-started" in (output / "evaluation" / "stdout.txt").read_text()
    assert [record["event"] for record in _records(output / "ledger.jsonl")][-2:] == [
        "evaluator_timed_out",
        "evaluation_completed",
    ]


def test_complete_probe_runner_prevents_parent_and_child_bytecode(tmp_path: Path) -> None:
    import shutil

    source = ROOT / "skills" / "experiment-machinery" / "scripts"
    scripts = tmp_path / "scripts"
    shutil.copytree(source, scripts)
    wrapper = tmp_path / "exercise.py"
    wrapper.write_text(
        "import os, runpy, subprocess, sys\n"
        "from pathlib import Path\n"
        "scripts = Path(sys.argv[1])\n"
        "os.environ.pop('PYTHONDONTWRITEBYTECODE', None)\n"
        "sys.path.insert(0, str(scripts))\n"
        "runpy.run_path(str(scripts / 'development_probe_run.py'), run_name='probe_import')\n"
        "child = subprocess.run([sys.executable, '-c', 'import development_probe_manifest'], cwd=scripts)\n"
        "raise SystemExit(child.returncode)\n"
    )
    env = os.environ.copy()
    env.pop("PYTHONDONTWRITEBYTECODE", None)

    completed = subprocess.run(
        [sys.executable, str(wrapper), str(scripts)], env=env, capture_output=True, text=True
    )

    assert completed.returncode == 0, completed.stderr
    assert list(scripts.rglob("__pycache__")) == []


def test_every_public_entrypoint_prevents_source_bytecode(tmp_path: Path) -> None:
    import shutil

    source = ROOT / "skills" / "experiment-machinery" / "scripts"
    scripts = tmp_path / "scripts"
    shutil.copytree(source, scripts)
    env = os.environ.copy()
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    entrypoints = sorted(path for path in scripts.glob("*.py") if "if __name__" in path.read_text())

    for entrypoint in entrypoints:
        completed = subprocess.run(
            [sys.executable, str(entrypoint), "--help"],
            cwd=scripts,
            env=env,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, f"{entrypoint.name}: {completed.stderr}"

    assert list(scripts.rglob("__pycache__")) == []
