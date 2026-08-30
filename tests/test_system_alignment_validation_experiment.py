from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/system-alignment-assessment-machinery/scripts"
VALIDATION = SCRIPTS / "validation_experiment.py"
EXPERIMENT = ROOT / "skills/experiment-machinery/scripts/run_experiment.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_module():
    spec = importlib.util.spec_from_file_location("evidence_package", SCRIPTS / "evidence_package.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules["evidence_package"] = value
    spec.loader.exec_module(value)
    return value


def package(tmp_path: Path, *, fail_actual: bool) -> Path:
    source = tmp_path / "source.txt"
    source.write_text("Observed total must equal reference total.\n")
    frozen = tmp_path / "input.json"
    frozen.write_text(json.dumps({"actual_value": 42, "reference_value": 42, "fail_actual": fail_actual}) + "\n")
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "value=json.loads(Path(sys.argv[1]).read_text())\n"
        "role=os.environ['EXPERIMENT_VARIANT_ID']\n"
        "if role == 'actual' and value['fail_actual']: raise SystemExit(3)\n"
        "result={'schema_version':1,'variant_id':role,'status':'completed','outcome':{'role':role},'metrics':{'execution-complete':1},'error':None}\n"
        "Path(sys.argv[2]).write_text(json.dumps(result))\n"
        "Path(sys.argv[3]).write_text(json.dumps({'event':'ran','role':role})+'\\n')\n"
    )
    runner = {"adapter": {"path": str(adapter), "sha256": sha(adapter)}, "command": ["{python}", "{adapter}", "{frozen-input}", "{result-path}", "{telemetry-path}"]}
    spec = {"schema_version": 1, "package_id": "controlled-run", "purpose": "Compare actual with reference.", "sources": [{"path": str(source), "sha256": sha(source)}], "subjects": [{"subject_id": "total", "sequence": 1, "label": "Total", "intent": "Actual equals reference.", "supporting_evidence": [{"path": str(source), "sha256": sha(source)}], "validation_cases": [{"case_id": "case", "sequence": 1, "frozen_input": {"path": str(frozen), "sha256": sha(frozen)}, "actual": runner, "reference": runner}]}]}
    mod = evidence_module()
    output = tmp_path / "package.json"
    mod.write_once(mod.admit(spec), output)
    return output


def run_case(tmp_path: Path, *, fail_actual: bool) -> dict:
    output = tmp_path / "run"
    completed = subprocess.run([sys.executable, str(VALIDATION), "run", "--package", str(package(tmp_path, fail_actual=fail_actual)), "--subject", "total", "--case", "case", "--experiment-runner", str(EXPERIMENT), "--output", str(output)], cwd=ROOT, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return json.loads((output / "validation-execution.json").read_text())


def test_public_path_executes_both_lanes_under_experiment_machinery(tmp_path: Path):
    result = run_case(tmp_path, fail_actual=False)
    assert [item["role"] for item in result["lanes"]] == ["actual", "reference"]
    assert all(item["status"] == "completed" for item in result["lanes"])
    assert Path(result["experiment"]["ledger"]["path"]).is_file()


def test_failed_actual_lane_and_reference_evidence_are_both_preserved(tmp_path: Path):
    result = run_case(tmp_path, fail_actual=True)
    assert result["lanes"][0]["status"] == "failed"
    assert result["lanes"][1]["status"] == "completed"
    assert Path(result["experiment"]["ledger"]["path"]).is_file()
