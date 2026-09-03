#!/usr/bin/env python3
"""Exercise independent-judge inputs through the candidate's real machinery paths."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_final_validator(script: Path) -> object:
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("candidate_final_validation", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_experiment_probe(root: Path, work: Path) -> tuple[bool, bool]:
    work.mkdir()
    runner = root / "skills/experiment-machinery/scripts/run_experiment.py"
    target = work / "target"
    target.mkdir()
    (target / "entry.py").write_text("VALUE = 'frozen'\n", encoding="utf-8")
    frozen = work / "input.json"
    frozen.write_text('{"case":"self-verdict-flip"}\n', encoding="utf-8")
    candidate = work / "candidate.py"
    candidate.write_text(
        """from __future__ import annotations
import json
import os
from pathlib import Path
configuration = json.loads(Path(os.environ["EXPERIMENT_VARIANT_PATH"]).read_text())["configuration"]
Path(os.environ["EXPERIMENT_TELEMETRY_PATH"]).write_text(json.dumps({"event":"observation","quality":1}) + "\\n")
Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps({
    "schema_version":1,
    "variant_id":os.environ["EXPERIMENT_VARIANT_ID"],
    "status":"completed",
    "outcome":{"correct":configuration["correct"],"verdict":configuration["verdict"]},
    "metrics":{"quality":configuration["claimed_score"]},
    "error":None,
}) + "\\n")
""",
        encoding="utf-8",
    )
    evaluator = work / "evaluator.py"
    evaluator.write_text(
        """from __future__ import annotations
import json
import sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text())
scores = []
for candidate in request["candidates"]:
    telemetry = next(item for item in candidate["evidence"] if item["id"] == "telemetry")
    events = [json.loads(line) for line in Path(telemetry["path"]).read_text().splitlines()]
    observed = next(item for item in events if item.get("event") == "observation")
    scores.append({"variant_id":candidate["variant_id"],"metrics":{"quality":observed["quality"]}})
Path(sys.argv[2]).write_text(json.dumps({"schema_version":1,"scores":scores}) + "\\n")
""",
        encoding="utf-8",
    )
    hashed = subprocess.run(
        [sys.executable, str(runner), "--hash-source", str(target)],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    spec_path = work / "experiment.json"
    write_json(
        spec_path,
        {
            "schema_version": 4,
            "experiment_id": "atom-independent-evaluation",
            "hypothesis": "Changing a producer conclusion cannot change official scoring.",
            "target": {
                "machinery": "experiment-machinery",
                "phase": "independent-evaluation-input",
                "source": {"path": str(target), "sha256": hashed},
                "entrypoint": "entry.py",
            },
            "frozen_input": {"path": str(frozen), "sha256": digest(frozen)},
            "execution_limits": {"variant_timeout_ms": 5000, "evaluator_timeout_ms": 5000},
            "variants": [
                {
                    "id": "control",
                    "command": [sys.executable, str(candidate)],
                    "adapter": {"path": str(candidate), "sha256": digest(candidate)},
                    "configuration": {"correct": True, "verdict": "pass", "claimed_score": 0},
                },
                {
                    "id": "flipped",
                    "command": [sys.executable, str(candidate)],
                    "adapter": {"path": str(candidate), "sha256": digest(candidate)},
                    "configuration": {"correct": False, "verdict": "fail", "claimed_score": 999},
                },
            ],
            "evaluation": {
                "metrics": [{"name": "quality", "direction": "maximize"}],
                "evaluator": {
                    "adapter": {"path": str(evaluator), "sha256": digest(evaluator)},
                    "command": [
                        "{python}",
                        "{evaluation-adapter}",
                        "{evaluation-request}",
                        "{evaluation-response}",
                    ],
                },
            },
        },
    )
    output = work / "experiment-output"
    completed = subprocess.run(
        [sys.executable, str(runner), "--spec", str(spec_path), "--output", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "experiment runner failed")
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    request = json.loads((output / "evaluation/request.json").read_text(encoding="utf-8"))
    scores = [row["metrics"] for row in summary["variants"]]
    return scores == [{"quality": 1.0}, {"quality": 1.0}], all(
        "outcome" not in candidate for candidate in request["candidates"]
    )


def run_final_probe(root: Path, work: Path) -> tuple[bool, bool, bool]:
    work.mkdir()
    module = load_final_validator(
        root / "skills/experiment-machinery/scripts/development_probe_final_validation.py"
    )
    telemetry = work / "final-telemetry.jsonl"
    telemetry.write_text('{"event":"observation","quality":1}\n', encoding="utf-8")
    manifest = {
        "atomic_step": {"id": "atom-independent-evaluation", "outcome": "Independent verdicts."},
        "composition": {
            "final_validation": {
                "success_criterion": "Independent evidence satisfies the criterion.",
                "failure_criterion": "Independent evidence shows refusal.",
                "operator_path": "operator_adapter.py",
            }
        },
    }
    case = {
        "id": "self-verdict-flip",
        "kind": "success",
        "expected_outcome": "Producer claims are withheld.",
    }
    base = {
        "case_id": case["id"],
        "status": "completed",
        "returncode": 0,
        "error": None,
        "output": str(work),
        "evidence": [
            {"id": "candidate-telemetry", "path": str(telemetry), "sha256": digest(telemetry)}
        ],
    }
    first = dict(base, result={"outcome": {"correct": True, "verdict": "pass"}})
    second = dict(base, result={"outcome": {"correct": False, "verdict": "fail"}})
    question_one = module._question(manifest, "a" * 64, case, first)
    question_two = module._question(manifest, "a" * 64, case, second)
    withheld = (
        question_one == question_two
        and "execution_result" not in question_one
        and "execution-result" not in {item["id"] for item in question_one["execution_evidence"]}
    )
    missing = dict(base, result={"outcome": {"correct": True}}, evidence=[])
    missing_question = module._question(manifest, "a" * 64, case, missing)
    try:
        module._validate_response(
            {
                "case_id": case["id"],
                "verdict": "satisfied",
                "reason": "Producer says it passed.",
                "evidence_pointers": ["execution-result"],
            },
            missing_question,
        )
        missing_refused = False
    except module.FinalValidationError:
        missing_refused = True
    telemetry.write_text('{"event":"observation","quality":0}\n', encoding="utf-8")
    has_hash_bound_telemetry = any(
        item["id"] == "candidate-telemetry" and "sha256" in item
        for item in question_one["execution_evidence"]
    )
    tamper_refused = False
    if has_hash_bound_telemetry:
        try:
            module._validate_response(
                {
                    "case_id": case["id"],
                    "verdict": "not-satisfied",
                    "reason": "Independent observation changed.",
                    "evidence_pointers": ["candidate-telemetry"],
                },
                question_one,
            )
        except module.FinalValidationError:
            tamper_refused = True
    return withheld, missing_refused, tamper_refused


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    work = Path(os.environ["EXPERIMENT_WORK_DIR"])
    score_inert, experiment_withheld = run_experiment_probe(root, work / "generic")
    final_withheld, missing_refused, tamper_refused = run_final_probe(root, work / "final")
    metrics = {
        "self-verdict-inert": int(score_inert),
        "experiment-outcome-withheld": int(experiment_withheld),
        "final-result-withheld": int(final_withheld),
        "missing-evidence-refused": int(missing_refused),
        "evidence-hash-enforced": int(tamper_refused),
    }
    result = {
        "schema_version": 1,
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "status": "completed",
        "outcome": {"case": json.loads(Path(os.environ["EXPERIMENT_INPUT_PATH"]).read_text())["case"]},
        "metrics": metrics,
        "error": None,
    }
    Path(os.environ["EXPERIMENT_TELEMETRY_PATH"]).write_text(
        json.dumps({"event": "independent-boundary-observed", "metrics": metrics}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_json(Path(os.environ["EXPERIMENT_RESULT_PATH"]), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
