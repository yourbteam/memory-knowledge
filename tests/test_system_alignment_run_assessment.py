from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/system-alignment-assessment-machinery/scripts"
RUNNER = ROOT / "skills/experiment-machinery/scripts/run_experiment.py"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(tmp_path: Path) -> Path:
    evidence = load("run_assessment_evidence", SCRIPTS / "evidence_package.py")
    source = tmp_path / "source.txt"; source.write_text("Actual and reference should match.\n")
    frozen = tmp_path / "input.json"; frozen.write_text('{"value":42}\n')
    adapter = tmp_path / "adapter.py"
    adapter.write_text('''import json,os,sys\nfrom pathlib import Path\nvalue={"value":42}\nPath(sys.argv[2]).write_text(json.dumps({"schema_version":1,"variant_id":os.environ["EXPERIMENT_VARIANT_ID"],"status":"completed","outcome":value,"metrics":{},"error":None}))\nPath(sys.argv[3]).write_text("{}\\n")\n''')
    runner = {"adapter": {"path": str(adapter), "sha256": sha(adapter)}, "command": [
        "{python}", "{adapter}", "{frozen-input}", "{result-path}", "{telemetry-path}",
    ]}
    spec = {"schema_version": 1, "package_id": "controller", "purpose": "Assess a value.",
            "sources": [{"path": str(source), "sha256": sha(source)}], "subjects": [{
                "subject_id": "value", "sequence": 1, "label": "Value",
                "intent": "Actual equals reference.",
                "supporting_evidence": [{"path": str(source), "sha256": sha(source)}],
                "validation_cases": [{"case_id": "fixed", "sequence": 1,
                    "frozen_input": {"path": str(frozen), "sha256": sha(frozen)},
                    "actual": runner, "reference": runner}],
            }]}
    path = tmp_path / "package.json"
    evidence.write_once(evidence.admit(spec), path)
    return path


def test_standalone_controller_runs_experiment_and_one_question_to_terminal(tmp_path: Path):
    controller = load("run_assessment_controller", SCRIPTS / "run_assessment.py")
    work = tmp_path / "work"
    first = controller.start(work=work, experiment_runner=RUNNER.resolve(), package_path=package(tmp_path))
    assert first["status"] == "needs-model-answer"
    question = first["question"]
    response = tmp_path / "response.json"
    response.write_text(json.dumps({"schema_version": 1, "question_id": question["question_id"],
        "verdict": "aligned", "measure": {"kind": "exact-match", "expected": "42", "actual": "42"},
        "reason": "The executed outcomes match.", "evidence_ids": [question["evidence"][0]["evidence_id"]]}) + "\n")
    terminal = controller.resume(work, response)
    assert terminal["status"] == "assessment-complete"
    assert terminal["overall_verdict"] == "aligned"
    assert controller.status(work) == terminal


def test_controller_refuses_to_restart_over_existing_work(tmp_path: Path):
    controller = load("run_assessment_restart", SCRIPTS / "run_assessment.py")
    work = tmp_path / "work"; work.mkdir()
    try:
        controller.start(work=work, experiment_runner=RUNNER.resolve(), package_path=package(tmp_path))
    except controller.AssessmentRunError as error:
        assert "already exists" in str(error)
    else:
        raise AssertionError("existing work was overwritten")
