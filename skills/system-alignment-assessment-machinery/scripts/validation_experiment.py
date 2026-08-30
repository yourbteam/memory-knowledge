#!/usr/bin/env python3
"""Execute actual and reference prototypes through Experiment Machinery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

class ValidationExperimentError(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def source_sha(runner: Path, source: Path) -> str:
    completed = subprocess.run([sys.executable, str(runner), "--hash-source", str(source)], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise ValidationExperimentError(completed.stderr.strip() or "Experiment Machinery could not hash its target source")
    return completed.stdout.strip()


def bridge() -> int:
    variant = json.loads(Path(os.environ["EXPERIMENT_VARIANT_PATH"]).read_text())
    configuration = variant["configuration"]
    runner = configuration["runner"]
    adapter = Path(runner["adapter"]["path"])
    if sha(adapter) != runner["adapter"]["sha256"]:
        raise ValidationExperimentError("prototype adapter bytes changed")
    replacements = {"{python}": sys.executable, "{adapter}": str(adapter), "{frozen-input}": os.environ["EXPERIMENT_INPUT_PATH"], "{result-path}": os.environ["EXPERIMENT_RESULT_PATH"], "{telemetry-path}": os.environ["EXPERIMENT_TELEMETRY_PATH"]}
    command = [replacements.get(item, item) for item in runner["command"]]
    environment = os.environ.copy()
    environment["EXPERIMENT_VARIANT_ID"] = configuration["role"]
    completed = subprocess.run(command, cwd=os.environ["EXPERIMENT_WORK_DIR"], env=environment, check=False)
    result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
    if completed.returncode == 0 and result_path.is_file():
        result = json.loads(result_path.read_text())
        result["variant_id"] = variant["variant_id"]
        result_path.write_text(json.dumps(result, sort_keys=True) + "\n")
    return completed.returncode


def evaluate(request: Path, response: Path) -> int:
    value = json.loads(request.read_text())
    scores = [{"variant_id": item["variant_id"], "metrics": {"execution-complete": 1}} for item in value["candidates"]]
    response.write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n")
    return 0


def run(package_path: Path, subject_id: str, case_id: str, experiment_runner: Path, output: Path) -> dict:
    from evidence_package import verify as verify_package

    package = verify_package(package_path)
    subject = next((item for item in package["subjects"] if item["subject_id"] == subject_id), None)
    if subject is None:
        raise ValidationExperimentError(f"unknown subject_id {subject_id!r}")
    case = next((item for item in subject["validation_cases"] if item["case_id"] == case_id), None)
    if case is None:
        raise ValidationExperimentError(f"unknown case_id {case_id!r} for subject {subject_id!r}")
    if output.exists():
        raise ValidationExperimentError(f"output already exists: {output}")
    output.mkdir(parents=True)
    script = Path(__file__).resolve()
    scripts_root = script.parent
    spec = {
        "schema_version": 4,
        "experiment_id": f"alignment-{package['package_id']}-{subject_id}-{case_id}",
        "hypothesis": "Actual and reference prototypes can execute independently on one byte-identical frozen input before any alignment verdict is considered.",
        "target": {"machinery": "system-alignment-assessment-machinery", "phase": "execute-validation-case", "source": {"path": str(scripts_root), "sha256": source_sha(experiment_runner, scripts_root)}, "entrypoint": script.name},
        "frozen_input": case["frozen_input"],
        "execution_limits": {"variant_timeout_ms": 300000, "evaluator_timeout_ms": 300000},
        "variants": [
            {"id": variant_id, "adapter": {"path": str(script), "sha256": sha(script)}, "command": [sys.executable, str(script), "bridge"], "configuration": {"role": role, "runner": case[role]}}
            for variant_id, role in (("control", "actual"), ("reference", "reference"))
        ],
        "evaluation": {"metrics": [{"name": "execution-complete", "direction": "maximize"}], "evaluator": {"adapter": {"path": str(script), "sha256": sha(script)}, "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]}}
    }
    spec_path = output / "experiment-spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    experiment = output / "experiment"
    completed = subprocess.run([sys.executable, str(experiment_runner), "--spec", str(spec_path), "--output", str(experiment)], text=True, capture_output=True, check=False)
    (output / "experiment.stdout.txt").write_text(completed.stdout)
    (output / "experiment.stderr.txt").write_text(completed.stderr)
    summary_path = experiment / "summary.json"
    ledger_path = experiment / "ledger.jsonl"
    if not summary_path.is_file() or not ledger_path.is_file():
        raise ValidationExperimentError(completed.stderr.strip() or "Experiment Machinery produced no complete evidence")
    summary = json.loads(summary_path.read_text())
    variants = {item["variant_id"]: item for item in summary["variants"]}
    lane_variants = {"actual": variants["control"], "reference": variants["reference"]}
    result = {"schema_version": 1, "artifact_type": "system-alignment-validation-execution", "status": "execution-complete", "package": {"path": str(package_path), "sha256": sha(package_path), "artifact_sha256": package["artifact_sha256"]}, "subject_id": subject_id, "case_id": case_id, "frozen_input_sha256": case["frozen_input"]["sha256"], "experiment": {"spec": {"path": str(spec_path), "sha256": sha(spec_path)}, "summary": {"path": str(summary_path), "sha256": sha(summary_path)}, "ledger": {"path": str(ledger_path), "sha256": sha(ledger_path)}}, "lanes": [{"role": role, "status": lane_variants[role]["status"], "eligible": lane_variants[role]["eligible"], "result_sha256": lane_variants[role]["result_sha256"], "error": lane_variants[role]["error"]} for role in ("actual", "reference")]}
    result["artifact_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    result_path = output / "validation-execution.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def development_probe(case_path: Path, result_path: Path, telemetry_path: Path) -> int:
    case = json.loads(case_path.read_text())
    run_root = result_path.parent / "operator-run"
    result = run(Path(case["package"]), "total", case["case_id"], Path(case["experiment_runner"]), run_root)
    ledger_present = Path(result["experiment"]["ledger"]["path"]).is_file()
    roles = [item["role"] for item in result["lanes"]]
    failure_preserved = not case["expect_actual_failure"] or next(item for item in result["lanes"] if item["role"] == "actual")["status"] != "completed"
    correct = ledger_present and roles == ["actual", "reference"] and failure_preserved
    outcome = {"ledger_present": ledger_present, "roles": roles, "failure_preserved": failure_preserved, "correct": correct}
    result_path.write_text(json.dumps({"schema_version": 1, "variant_id": os.environ["EXPERIMENT_VARIANT_ID"], "status": "completed", "outcome": outcome, "metrics": {"experiment-ledger": int(ledger_present), "both-lanes-preserved": int(roles == ["actual", "reference"]), "failure-preserved": int(failure_preserved)}, "error": None}))
    telemetry_path.write_text(json.dumps({"event": "validation-experiment-probed", "outcome": outcome}) + "\n")
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "bridge":
        return bridge()
    if len(sys.argv) == 3 and Path(sys.argv[1]).is_file():
        request = json.loads(Path(sys.argv[1]).read_text())
        if "candidates" in request:
            return evaluate(Path(sys.argv[1]), Path(sys.argv[2]))
    if len(sys.argv) == 4 and sys.argv[1] not in {"run"}:
        return development_probe(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("run")
    command.add_argument("--package", required=True, type=Path)
    command.add_argument("--subject", required=True)
    command.add_argument("--case", required=True)
    command.add_argument("--experiment-runner", required=True, type=Path)
    command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        value = run(args.package, args.subject, args.case, args.experiment_runner, args.output)
    except (ValidationExperimentError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Validation experiment refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": value["status"], "subject_id": value["subject_id"], "case_id": value["case_id"], "artifact_sha256": value["artifact_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
