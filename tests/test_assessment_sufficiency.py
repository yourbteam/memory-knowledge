from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/assessment_sufficiency.py"


def _module():
    spec = importlib.util.spec_from_file_location("assessment_sufficiency", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _fixture(tmp_path: Path, unit_count: int = 2):
    module = _module()
    intake = _write(tmp_path / "intake.json", {"intake_id": "intake-1"})
    charter_body = {
        "schema_version": 1,
        "artifact_type": "info-intake-assessment-charter",
        "status": "charter-ready",
        "intake": {"path": str(intake), "sha256": module._digest(intake.read_bytes()), "intake_id": "intake-1"},
        "assessment": {
            "purpose": "Are values correct?",
            "decision": "Find mismatches.",
            "unit_definition": "One field.",
            "completion_policy": "all-purpose-relevant-units",
            "unresolved_policy": "allow-incomplete-verdict",
            "downstream_use": "Fix confirmed mismatches.",
        },
    }
    charter_body["artifact_sha256"] = module._digest(module._canonical(charter_body))
    charter = _write(tmp_path / "charter.json", charter_body)
    source = _write(tmp_path / "facts.json", {"fact": "value"})
    units = []
    for sequence in range(1, unit_count + 1):
        unit_id = f"unit-{sequence}"
        obligations = []
        for role in ("criterion", "observation", "context"):
            evidence_id = f"{unit_id}:{role}:evidence"
            obligations.append({
                "id": f"{unit_id}:{role}",
                "role": role,
                "required": True,
                "question": f"question {role}",
                "status": "bound",
                "evidence": [{
                    "evidence_id": evidence_id,
                    "source": {"path": str(source), "sha256": module._digest(source.read_bytes())},
                    "locator": {"kind": "json-pointer", "pointer": ""},
                    "representation": json.loads(source.read_text()),
                    "representation_sha256": module._digest(module._canonical(json.loads(source.read_text()))),
                }],
            })
        units.append({
            "sequence": sequence,
            "unit_id": unit_id,
            "label": unit_id,
            "subject": {"identity": f"field-{sequence}", "kind": "metric"},
            "obligations": obligations,
        })
    evidence_body = {
        "schema_version": 1,
        "artifact_type": "info-intake-assessment-evidence",
        "status": "evidence-state-ready",
        "obligations_source": {},
        "plan_source": {},
        "unit_count": unit_count,
        "obligation_count": unit_count * 3,
        "bound_count": unit_count * 3,
        "unbound_count": 0,
        "unbound_obligation_ids": [],
        "units": units,
    }
    evidence_body["artifact_sha256"] = module._digest(module._canonical(evidence_body))
    evidence = _write(tmp_path / "evidence.json", evidence_body)
    return module, charter, evidence, source


def _response(unit_id: str, *, observation_verdict: str = "sufficient") -> str:
    assessments = []
    for role in ("criterion", "observation", "context"):
        verdict = observation_verdict if role == "observation" else "sufficient"
        assessments.append({
            "obligation_id": f"{unit_id}:{role}",
            "verdict": verdict,
            "reason": f"reason for {role}",
            "evidence_ids": [f"{unit_id}:{role}:evidence"],
            "missing_evidence": None if verdict == "sufficient" else "runtime payload",
        })
    return json.dumps({"unit_id": unit_id, "assessments": assessments})


def test_runs_one_unit_at_a_time_and_publishes_exact_gaps(tmp_path: Path, monkeypatch) -> None:
    module, charter, evidence, _source = _fixture(tmp_path)
    monkeypatch.setattr(module.evidence_contract, "verify", lambda _path: {})
    answers = iter([_response("unit-1", observation_verdict="insufficient"), _response("unit-2")])

    result = module.run(charter, evidence, tmp_path / "work", input_fn=lambda _prompt: next(answers))

    assert result["unit_count"] == 2
    assert result["obligation_count"] == 6
    assert result["verdict_counts"] == {"sufficient": 5, "insufficient": 1, "cannot-assess": 0}
    assert result["gap_count"] == 1
    assert result["gaps"][0]["obligation_id"] == "unit-1:observation"
    events = [json.loads(line)["event"] for line in (tmp_path / "work/interview.jsonl").read_text().splitlines()]
    assert events.count("unit_question_asked") == 2
    assert module.verify(tmp_path / "work/sufficiency.json") == result


def test_rejected_answer_is_preserved_and_same_unit_reasked(tmp_path: Path, monkeypatch) -> None:
    module, charter, evidence, _source = _fixture(tmp_path, unit_count=1)
    monkeypatch.setattr(module.evidence_contract, "verify", lambda _path: {})
    bad = json.loads(_response("unit-1"))
    bad["assessments"][0]["verdict"] = "probably"
    answers = iter([json.dumps(bad), _response("unit-1")])
    messages = []

    result = module.run(charter, evidence, tmp_path / "work", input_fn=lambda _prompt: next(answers), output_fn=messages.append)

    assert result["gap_count"] == 0
    entries = [json.loads(line) for line in (tmp_path / "work/interview.jsonl").read_text().splitlines()]
    recorded = [entry for entry in entries if entry["event"] == "unit_answer_recorded"]
    assert [entry["accepted"] for entry in recorded] == [False, True]
    assert len(messages) == 1


def test_pause_and_resume_preserve_exact_progress(tmp_path: Path, monkeypatch) -> None:
    module, charter, evidence, _source = _fixture(tmp_path)
    monkeypatch.setattr(module.evidence_contract, "verify", lambda _path: {})

    paused = module.run(charter, evidence, tmp_path / "work", input_fn=lambda _prompt: _response("unit-1"), max_units=1)
    assert paused["status"] == "paused"
    assert paused["accepted_unit_count"] == 1
    result = module.run(charter, evidence, tmp_path / "work", input_fn=lambda _prompt: _response("unit-2"))
    assert result["unit_count"] == 2


def test_source_change_is_refused_before_resume(tmp_path: Path, monkeypatch) -> None:
    module, charter, evidence, source = _fixture(tmp_path, unit_count=1)
    monkeypatch.setattr(module.evidence_contract, "verify", lambda _path: {})
    module.run(charter, evidence, tmp_path / "work", input_fn=lambda _prompt: _response("unit-1"))
    source.write_text("{}\n", encoding="utf-8")

    with pytest.raises(module.AssessmentSufficiencyError, match="source digest"):
        module.verify(tmp_path / "work/sufficiency.json")


def test_prepare_and_submit_transport_one_schema_bound_unit_without_pty(tmp_path: Path, monkeypatch) -> None:
    module, charter, evidence, _source = _fixture(tmp_path)
    monkeypatch.setattr(module.evidence_contract, "verify", lambda _path: {})
    work = tmp_path / "work"

    prepared = module.prepare_question(charter, evidence, work)

    assert prepared["status"] == "question-ready"
    assert prepared["question"]["unit"]["unit_id"] == "unit-1"
    schema = prepared["response_schema"]
    assert schema["properties"]["unit_id"]["enum"] == ["unit-1"]
    assessment_schema = schema["properties"]["assessments"]
    assert isinstance(assessment_schema["items"], dict)
    provider_schema = json.dumps(schema, sort_keys=True)
    for unsupported_keyword in (
        "prefixItems",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
    ):
        assert unsupported_keyword not in provider_schema
    duplicate = json.loads(_response("unit-1"))
    duplicate["assessments"][0]["evidence_ids"] *= 2
    _parsed, duplicate_error = module._validate_response(
        prepared["question"], duplicate
    )
    assert "choose unique ids" in duplicate_error
    reordered = json.loads(_response("unit-1"))
    reordered["assessments"].reverse()
    _parsed, reordered_error = module._validate_response(
        prepared["question"], reordered
    )
    assert "provide exactly ['unit-1:criterion', 'unit-1:observation', 'unit-1:context'] in order" in reordered_error

    submitted = module.submit_response(
        charter, evidence, work, _response("unit-1")
    )

    assert submitted["status"] == "accepted"
    next_question = module.prepare_question(charter, evidence, work)
    assert next_question["question"]["unit"]["unit_id"] == "unit-2"
