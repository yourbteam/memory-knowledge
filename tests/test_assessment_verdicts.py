from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "skills/info-intake-machinery/scripts/assessment_verdicts.py"
RUNNER = ROOT / "skills/info-intake-machinery/scripts/run_assessment_verdicts_with_model.py"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return path


def _fixture(tmp_path: Path):
    module = _module(CONTROLLER, "assessment_verdict_test_controller")
    charter = _write(tmp_path / "charter.json", {"assessment": {"purpose": "Are values correct?", "decision": "Find misalignments."}})
    units = []
    for sequence in (1, 2):
        unit_id = f"unit-{sequence}"
        obligations = []
        for role in ("criterion", "observation", "context"):
            representation = {"text": f"{unit_id}-{role}"}
            obligations.append({
                "id": f"{unit_id}:{role}",
                "role": role,
                "evidence": [{
                    "evidence_id": f"{unit_id}:{role}:evidence",
                    "representation": representation,
                    "representation_sha256": module._digest(module._canonical(representation)),
                }],
            })
        units.append({"sequence": sequence, "unit_id": unit_id, "label": unit_id, "subject": {"identity": f"field-{sequence}", "kind": "field"}, "obligations": obligations})
    evidence = _write(tmp_path / "evidence.json", {"units": units})
    evidence_value = json.loads(evidence.read_text())
    assessments = []
    for sequence in (1, 2):
        unit_id = f"unit-{sequence}"
        rows = []
        for role in ("criterion", "observation", "context"):
            incomplete = sequence == 1 and role == "observation"
            rows.append({
                "obligation_id": f"{unit_id}:{role}",
                "verdict": "insufficient" if incomplete else "sufficient",
                "reason": f"reason {role}",
                "evidence_ids": [f"{unit_id}:{role}:evidence"],
                "missing_evidence": "runtime value" if incomplete else None,
            })
        assessments.append({"unit_id": unit_id, "assessments": rows})
    sufficiency = _write(tmp_path / "sufficiency.json", {
        "charter_source": module._ref(charter, charter.read_bytes(), json.loads(charter.read_text())),
        "evidence_source": module._ref(evidence, evidence.read_bytes(), evidence_value),
        "units": assessments,
        "gaps": [{
            "gap_id": "gap-000001",
            "unit_id": "unit-1",
            "obligation_id": "unit-1:observation",
            "verdict": "insufficient",
            "reason": "reason observation",
            "evidence_ids": ["unit-1:observation:evidence"],
            "missing_evidence": "runtime value",
        }],
    })
    module.evidence_contract.verify = lambda _path: {}
    module.sufficiency_contract.verify = lambda _path: {}
    return module, evidence, sufficiency


def _response(unit_id: str = "unit-2", verdict: str = "misaligned") -> str:
    return json.dumps({
        "unit_id": unit_id,
        "verdict": verdict,
        "measure": "Expected 10; observed 11; difference 1.",
        "reason": "The observed value is one higher.",
        "evidence_ids": [f"{unit_id}:criterion:evidence", f"{unit_id}:observation:evidence", f"{unit_id}:context:evidence"],
    })


def test_incomplete_is_deterministic_and_complete_unit_is_model_judged(tmp_path: Path) -> None:
    module, evidence, sufficiency = _fixture(tmp_path)
    work = tmp_path / "work"

    prepared = module.prepare_question(evidence, sufficiency, work)

    assert prepared["status"] == "question-ready"
    assert prepared["recorded_unit_count"] == 1
    assert prepared["question"]["unit"]["unit_id"] == "unit-2"
    assert prepared["response_schema"]["properties"]["verdict"]["enum"] == ["aligned", "misaligned"]
    submitted = module.submit_response(evidence, sufficiency, work, _response())
    assert submitted["status"] == "complete"
    result = json.loads((work / "verdicts.json").read_text())
    assert result["verdict_counts"] == {"aligned": 0, "misaligned": 1, "incomplete": 1}
    assert result["actionable_misalignment_unit_ids"] == ["unit-2"]
    assert result["units"][0]["model_used"] is False
    assert result["units"][0]["gap_ids"] == ["gap-000001"]
    assert module.verify(work / "verdicts.json") == result


def test_invalid_model_evidence_is_preserved_and_same_unit_reasked(tmp_path: Path) -> None:
    module, evidence, sufficiency = _fixture(tmp_path)
    work = tmp_path / "work"
    module.prepare_question(evidence, sufficiency, work)
    bad = json.loads(_response())
    bad["evidence_ids"] = ["unit-2:criterion:evidence", "invented", "unit-2:context:evidence"]

    rejected = module.submit_response(evidence, sufficiency, work, json.dumps(bad))

    assert rejected["status"] == "rejected"
    assert "invented" in rejected["error"]
    assert "observation" in rejected["error"]
    assert module.prepare_question(evidence, sufficiency, work)["question"]["unit"]["unit_id"] == "unit-2"
    assert module.submit_response(evidence, sufficiency, work, _response())["status"] == "complete"
    entries = [json.loads(line) for line in (work / "interview.jsonl").read_text().splitlines()]
    assert [entry["accepted"] for entry in entries if entry["event"] == "unit_answer_recorded"] == [False, True]


def test_source_change_is_refused_before_resume(tmp_path: Path) -> None:
    module, evidence, sufficiency = _fixture(tmp_path)
    module.prepare_question(evidence, sufficiency, tmp_path / "work")
    evidence.write_text("{}\n")

    try:
        module.prepare_question(evidence, sufficiency, tmp_path / "work")
    except module.AssessmentVerdictError as error:
        assert "different evidence" in str(error)
    else:
        raise AssertionError("changed evidence was accepted")


def test_model_runner_records_deterministic_and_model_verdicts_once(tmp_path: Path, monkeypatch) -> None:
    controller, evidence, sufficiency = _fixture(tmp_path)
    runner = _module(RUNNER, "assessment_verdict_test_runner")
    monkeypatch.setattr(runner, "_controller_module", lambda: controller)
    monkeypatch.setattr(runner, "_executable", lambda _client: "/bin/codex")

    def model_run(argv, **_kwargs):
        response_path = Path(argv[argv.index("--output-last-message") + 1])
        response_path.write_text(_response() + "\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = runner.run(evidence, sufficiency, tmp_path / "work", model_run_fn=model_run, environ={"MK_CLIENT_KIND": "codex"})

    assert result["status"] == "complete"
    assert result["recorded_before"] == 0
    assert result["recorded_after"] == 2
    assert result["deterministic_verdicts_this_run"] == 1
    assert result["model_answers_this_run"] == 1
    assert Path(result["artifact"]).is_file()
