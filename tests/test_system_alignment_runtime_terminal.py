from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/system-alignment-assessment-machinery/scripts/runtime_terminal.py"


def module():
    spec = importlib.util.spec_from_file_location("runtime_terminal", SCRIPT)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules["runtime_terminal"] = value
    spec.loader.exec_module(value)
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path, *, verdict: str) -> tuple[Path, Path]:
    mod = module()
    package = {"schema_version": 1, "artifact_type": "system-alignment-evidence-package", "status": "assessment-ready", "package_id": "terminal", "purpose": "Assess total.", "sources": [], "subjects": [{"subject_id": "total", "sequence": 1, "label": "Total", "intent": "Actual equals reference.", "supporting_evidence": [], "validation_cases": [{"case_id": "case", "sequence": 1}]}]}
    package["artifact_sha256"] = mod.artifact_digest(package)
    package_path = tmp_path / "package.json"
    package_path.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n")
    execution = tmp_path / "execution.json"
    execution.write_text("{}\n")
    question = {"question_id": "runtime:total:case", "sequence": 1, "subject_id": "total", "case_id": "case", "intent": "Actual equals reference.", "evidence": [{"evidence_id": "execution:total:case", "path": str(execution), "sha256": sha(execution)}]}
    if verdict == "cannot-assess":
        questions = []
        dispositions = [{"subject_id": "total", "case_id": "case", "verdict": "cannot-assess", "reason": "Actual lane failed.", "missing_evidence": [{"lane": "actual", "request": "Repair and rerun actual."}], "execution_evidence": {"path": str(execution), "sha256": sha(execution)}}]
    else:
        questions = [question]
        dispositions = []
    catalog = {"schema_version": 1, "artifact_type": "system-alignment-runtime-question-catalog", "status": "questions-ready", "evidence_package": {"path": str(package_path), "sha256": sha(package_path), "artifact_sha256": package["artifact_sha256"]}, "question_count": len(questions), "disposition_count": len(dispositions), "questions": questions, "dispositions": dispositions, "interview_mode": "one-question-at-a-time"}
    catalog["artifact_sha256"] = mod.artifact_digest(catalog)
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n")
    results_ref = None
    if questions:
        answer = {"schema_version": 1, "question_id": "runtime:total:case", "verdict": verdict, "measure": {"kind": "numeric-delta", "expected": "42", "actual": "40"}, "reason": "Actual differs from reference.", "evidence_ids": ["execution:total:case"]}
        results = {"schema_version": 1, "artifact_type": "system-alignment-runtime-results", "status": "runtime-assessment-complete", "catalog_artifact_sha256": catalog["artifact_sha256"], "results": [answer], "dispositions": []}
        results["artifact_sha256"] = mod.artifact_digest(results)
        results_path = tmp_path / "results.json"
        results_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
        results_ref = {"path": str(results_path), "sha256": sha(results_path)}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({"schema_version": 1, "catalog": {"path": str(catalog_path), "sha256": sha(catalog_path)}, "runtime_results": results_ref}, indent=2, sort_keys=True) + "\n")
    return spec_path, package_path


def test_public_cli_emits_misaligned_atom_candidate(tmp_path: Path):
    spec, _ = fixture(tmp_path, verdict="misaligned")
    output = tmp_path / "terminal.json"
    completed = subprocess.run([sys.executable, str(SCRIPT), "create", "--spec", str(spec), "--output", str(output)], cwd=ROOT, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text())
    assert result["summary"]["overall_verdict"] == "misaligned"
    assert result["atom_building_candidates"][0]["status"] == "requires-owner-envelope"
    assert result["missing_evidence_requests"] == []


def test_failed_lane_emits_gap_and_no_false_defect(tmp_path: Path):
    mod = module()
    spec, _ = fixture(tmp_path, verdict="cannot-assess")
    result = mod.create(json.loads(spec.read_text()))
    assert result["summary"]["overall_verdict"] == "cannot-assess"
    assert result["missing_evidence_requests"][0]["requests"][0]["lane"] == "actual"
    assert result["atom_building_candidates"] == []


def test_changed_evidence_package_refuses_terminal_rebuild(tmp_path: Path):
    mod = module()
    spec, package = fixture(tmp_path, verdict="misaligned")
    package.write_text("{}\n")
    with pytest.raises(mod.RuntimeTerminalError, match="evidence package bytes"):
        mod.create(json.loads(spec.read_text()))
