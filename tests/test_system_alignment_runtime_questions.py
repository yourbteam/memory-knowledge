from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/system-alignment-assessment-machinery/scripts"
SCRIPT = SCRIPTS / "runtime_questions.py"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path, *, actual_complete: bool) -> Path:
    evidence = load("evidence_package", SCRIPTS / "evidence_package.py")
    runtime = load("runtime_questions", SCRIPT)
    source = tmp_path / "source.txt"
    source.write_text("Actual equals reference.\n")
    frozen = tmp_path / "input.json"
    frozen.write_text("{}\n")
    adapter = tmp_path / "adapter.py"
    adapter.write_text("# adapter\n")
    runner = {"adapter": {"path": str(adapter), "sha256": sha(adapter)}, "command": ["{python}", "{adapter}", "{frozen-input}", "{result-path}", "{telemetry-path}"]}
    package_value = evidence.admit({"schema_version": 1, "package_id": "runtime", "purpose": "Assess a runtime value.", "sources": [{"path": str(source), "sha256": sha(source)}], "subjects": [{"subject_id": "total", "sequence": 1, "label": "Total", "intent": "Actual equals reference.", "supporting_evidence": [], "validation_cases": [{"case_id": "case", "sequence": 1, "frozen_input": {"path": str(frozen), "sha256": sha(frozen)}, "actual": runner, "reference": runner}]}]})
    package_path = tmp_path / "package.json"
    evidence.write_once(package_value, package_path)
    spec_path = tmp_path / "experiment-spec.json"
    spec_path.write_text("{}\n")
    variants = [
        {"variant_id": "control", "status": "completed" if actual_complete else "failed", "eligible": actual_complete, "result_sha256": "a" * 64 if actual_complete else None, "error": None, "outcome": {"value": 42} if actual_complete else None},
        {"variant_id": "reference", "status": "completed", "eligible": True, "result_sha256": "b" * 64, "error": None, "outcome": {"value": 42}},
    ]
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"frozen_input_sha256": sha(frozen), "variants": variants}, sort_keys=True) + "\n")
    ledger_record = {"schema_version": 1, "sequence": 1, "previous_entry_sha256": None, "event": "experiment_started"}
    ledger_record["entry_sha256"] = hashlib.sha256(runtime.canonical(ledger_record)).hexdigest()
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(json.dumps(ledger_record, sort_keys=True) + "\n")
    execution = {"schema_version": 1, "artifact_type": "system-alignment-validation-execution", "status": "execution-complete", "package": {"path": str(package_path), "sha256": sha(package_path), "artifact_sha256": package_value["artifact_sha256"]}, "subject_id": "total", "case_id": "case", "frozen_input_sha256": sha(frozen), "experiment": {"spec": {"path": str(spec_path), "sha256": sha(spec_path)}, "summary": {"path": str(summary_path), "sha256": sha(summary_path)}, "ledger": {"path": str(ledger_path), "sha256": sha(ledger_path)}}, "lanes": [{"role": "actual"}, {"role": "reference"}]}
    execution["artifact_sha256"] = runtime.digest_without_artifact(execution)
    execution_path = tmp_path / "execution.json"
    execution_path.write_text(json.dumps(execution, indent=2, sort_keys=True) + "\n")
    spec = {"schema_version": 1, "evidence_package": {"path": str(package_path), "sha256": sha(package_path)}, "executions": [{"path": str(execution_path), "sha256": sha(execution_path)}]}
    input_path = tmp_path / "questions-spec.json"
    input_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    return input_path


def test_completed_runtime_pair_becomes_public_cli_question(tmp_path: Path):
    output = tmp_path / "catalog.json"
    completed = subprocess.run([sys.executable, str(SCRIPT), "create", "--spec", str(fixture(tmp_path, actual_complete=True)), "--output", str(output)], cwd=ROOT, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    catalog = json.loads(output.read_text())
    assert catalog["question_count"] == 1
    assert catalog["disposition_count"] == 0
    assert catalog["questions"][0]["actual_outcome"] == {"value": 42}


def test_failed_lane_becomes_precise_cannot_assess_gap(tmp_path: Path):
    runtime = load("runtime_questions", SCRIPT)
    spec = json.loads(fixture(tmp_path, actual_complete=False).read_text())
    catalog = runtime.create(spec)
    assert catalog["question_count"] == 0
    assert catalog["dispositions"][0]["verdict"] == "cannot-assess"
    assert catalog["dispositions"][0]["missing_evidence"][0]["lane"] == "actual"
