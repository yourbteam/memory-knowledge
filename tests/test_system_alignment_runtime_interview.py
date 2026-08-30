from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/system-alignment-assessment-machinery/scripts/runtime_interview.py"


def module():
    spec = importlib.util.spec_from_file_location("runtime_interview", SCRIPT)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules["runtime_interview"] = value
    spec.loader.exec_module(value)
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def catalog(tmp_path: Path) -> Path:
    mod = module()
    evidence = tmp_path / "execution.json"
    evidence.write_text('{"actual":42,"reference":42}\n')
    value = {"schema_version": 1, "artifact_type": "system-alignment-runtime-question-catalog", "status": "questions-ready", "evidence_package": {}, "question_count": 1, "disposition_count": 0, "questions": [{"question_id": "runtime:total:case", "sequence": 1, "subject_id": "total", "case_id": "case", "intent": "Actual equals reference.", "frozen_input_sha256": "a" * 64, "actual_outcome": {"value": 42}, "reference_outcome": {"value": 42}, "allowed_verdicts": ["aligned", "misaligned", "cannot-assess"], "allowed_measures": ["exact-match", "numeric-delta", "structural-equivalence", "semantic-equivalence"], "evidence": [{"evidence_id": "execution:total:case", "path": str(evidence), "sha256": sha(evidence)}]}], "dispositions": [], "interview_mode": "one-question-at-a-time"}
    value["artifact_sha256"] = hashlib.sha256(mod.canonical(value)).hexdigest()
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return path


def response(tmp_path: Path, *, verdict: str = "aligned", evidence_id: str = "execution:total:case") -> Path:
    value = {"schema_version": 1, "question_id": "runtime:total:case", "verdict": verdict, "measure": {"kind": "exact-match", "expected": "42", "actual": "42"}, "reason": "The executed values match.", "evidence_ids": [evidence_id]}
    path = tmp_path / "response.json"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return path


def test_public_cli_presents_one_question_and_persists_grounded_answer(tmp_path: Path):
    work = tmp_path / "work"
    prepared = subprocess.run([sys.executable, str(SCRIPT), "prepare", "--catalog", str(catalog(tmp_path)), "--work", str(work)], cwd=ROOT, text=True, capture_output=True, check=False)
    assert prepared.returncode == 0, prepared.stderr
    assert json.loads(prepared.stdout)["question"]["question_id"] == "runtime:total:case"
    answered = subprocess.run([sys.executable, str(SCRIPT), "answer", "--work", str(work), "--response", str(response(tmp_path))], cwd=ROOT, text=True, capture_output=True, check=False)
    assert answered.returncode == 0, answered.stderr
    assert (work / "answers/answer-000001.json").is_file()
    assert json.loads((work / "runtime-results.json").read_text())["status"] == "runtime-assessment-complete"


def test_unknown_verdict_is_refused_before_answer_persistence(tmp_path: Path):
    mod = module()
    work = tmp_path / "work"
    mod.prepare(catalog(tmp_path), work)
    with pytest.raises(mod.RuntimeInterviewError, match="outside the presented choices"):
        mod.answer(work, response(tmp_path, verdict="probably-aligned"))
    assert not list((work / "answers").iterdir())


def test_invented_evidence_is_refused(tmp_path: Path):
    mod = module()
    work = tmp_path / "work"
    mod.prepare(catalog(tmp_path), work)
    with pytest.raises(mod.RuntimeInterviewError, match="presented with this question"):
        mod.answer(work, response(tmp_path, evidence_id="invented"))
