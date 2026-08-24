from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/assessment_return.py"


def _module():
    spec = importlib.util.spec_from_file_location("assessment_return_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _package(tmp_path: Path):
    value = {
        "artifact_sha256": "package-artifact",
        "purpose": "Assess the returned evidence.",
        "decision": "Update only grounded findings.",
        "unresolved_source_requests": [
            {
                "request_id": "request-000001",
                "role": "criterion",
                "gap_ids": ["gap-000001", "gap-000002"],
                "unit_ids": ["unit-000001"],
                "question": "Provide criterion evidence.",
                "missing_evidence": ["formula", "value"],
            },
            {
                "request_id": "request-000002",
                "role": "observation",
                "gap_ids": ["gap-000003"],
                "unit_ids": ["unit-000002"],
                "question": "Provide observation evidence.",
                "missing_evidence": ["binding"],
            },
        ],
    }
    path = tmp_path / "assessment-package.json"
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return path, value


def _trust_exact_bytes(module, path: Path):
    expected = hashlib.sha256(path.read_bytes()).hexdigest()

    def verify(candidate: Path):
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            raise RuntimeError("assessment package changed")
        return json.loads(candidate.read_text())

    module.package_contract.verify = verify


def test_admits_exact_package_requests_and_replays_without_duplication(tmp_path):
    module = _module()
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"

    first = module.start(package_path, work)
    before = (work / "ledger.jsonl").read_bytes()
    second = module.start(package_path, work)

    assert second == first
    assert first["request_count"] == 2
    assert first["gap_count"] == 3
    assert [item["request_id"] for item in first["requests"]] == [
        "request-000001", "request-000002"
    ]
    assert first["current_request_id"] == "request-000001"
    assert (work / "ledger.jsonl").read_bytes() == before
    assert len(before.splitlines()) == 2


def test_refuses_package_changed_after_admission(tmp_path):
    module = _module()
    package_path, package = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)

    package["unresolved_source_requests"][0]["question"] = "changed"
    package_path.write_text(json.dumps(package, sort_keys=True) + "\n")

    with pytest.raises(module.AssessmentReturnError, match="verification failed"):
        module.verify(work / "assessment-return.json")


def test_refuses_duplicate_gap_identity_even_after_package_verification(tmp_path):
    module = _module()
    package_path, package = _package(tmp_path)
    package["unresolved_source_requests"][1]["gap_ids"] = ["gap-000002"]
    package_path.write_text(json.dumps(package, sort_keys=True) + "\n")
    module.package_contract.verify = lambda candidate: json.loads(candidate.read_text())

    with pytest.raises(module.AssessmentReturnError, match="repeats gaps"):
        module.start(package_path, tmp_path / "return")


def test_refuses_tampered_return_artifact(tmp_path):
    module = _module()
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)
    artifact_path = work / "assessment-return.json"
    value = json.loads(artifact_path.read_text())
    value["requests"][0]["question"] = "changed"
    artifact_path.write_text(json.dumps(value, sort_keys=True) + "\n")

    with pytest.raises(module.AssessmentReturnError, match="bindings changed"):
        module.verify(artifact_path)


def test_interviews_exactly_one_request_with_code_owned_action_enum(tmp_path):
    module = _module()
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)

    state = module.prepare(work)
    assert state["stage"] == "request-action"
    assert state["current_request_id"] == "request-000001"
    assert state["question"]["choices"] == ["add-source", "unavailable", "finish"]
    assert state["question"]["request"]["gap_ids"] == ["gap-000001", "gap-000002"]

    state = module.answer_action(work, "request-000001", "unavailable")
    assert state["current_request_id"] == "request-000002"
    assert state["completed_request_ids"] == ["request-000001"]
    assert len((work / "ledger.jsonl").read_text().splitlines()) == 4


@pytest.mark.parametrize("answer", ["skip", ["add-source", "finish"], None])
def test_action_enum_refuses_unknown_or_batch_answers(tmp_path, answer):
    module = _module()
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)

    with pytest.raises(module.AssessmentReturnError, match="choose one of"):
        module.answer_action(work, "request-000001", answer)
    assert len((work / "ledger.jsonl").read_text().splitlines()) == 2


def test_add_source_action_stops_at_source_input_for_same_request(tmp_path):
    module = _module()
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)

    state = module.answer_action(work, "request-000001", "add-source")

    assert state["stage"] == "source-input"
    assert state["current_request_id"] == "request-000001"
    assert state["question"] is None


def test_binds_frozen_source_to_exact_request_then_offers_next_action(tmp_path):
    module = _module()
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)
    module.answer_action(work, "request-000001", "add-source")
    supplied = tmp_path / "report.cs"
    supplied.write_text("formula source\n")

    state = module.bind_source(work, "request-000001", supplied)
    supplied.write_text("changed after binding\n")
    replayed = module.prepare(work)

    assert state == replayed
    assert state["stage"] == "request-action"
    assert state["current_request_id"] == "request-000001"
    assert state["question"]["id"] == "request-000001:action:2"
    assert state["bound_sources"][0]["request_id"] == "request-000001"
    assert (work / state["bound_sources"][0]["stored_path"]).read_text() == "formula source\n"


def test_refuses_changed_stored_source(tmp_path):
    module = _module()
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)
    module.answer_action(work, "request-000001", "add-source")
    supplied = tmp_path / "report.cs"
    supplied.write_text("formula source\n")
    state = module.bind_source(work, "request-000001", supplied)
    (work / state["bound_sources"][0]["stored_path"]).write_text("changed\n")

    with pytest.raises(module.AssessmentReturnError, match="stored source changed"):
        module.prepare(work)


def test_reuses_only_complete_verbatim_projection(tmp_path):
    module = _module()
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)
    module.answer_action(work, "request-000001", "add-source")
    supplied = tmp_path / "report.cs"
    supplied.write_text("formula source\n")
    module.bind_source(work, "request-000001", supplied)

    state = module.bind_verbatim_projection(work, "return-source-000001", supplied)

    assert state["projections"][0]["qualification"]["qualification"] == "readable_projection_complete"
    assert state["projections"][0]["sha256"] == state["bound_sources"][0]["sha256"]


def test_refuses_nonverbatim_projection_for_verbatim_terminal(tmp_path):
    module = _module()
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)
    module.answer_action(work, "request-000001", "add-source")
    supplied = tmp_path / "report.cs"
    supplied.write_text("formula source\n")
    module.bind_source(work, "request-000001", supplied)
    changed = tmp_path / "projection.txt"
    changed.write_text("partial source\n")

    with pytest.raises(module.AssessmentReturnError, match="not a complete verbatim"):
        module.bind_verbatim_projection(work, "return-source-000001", changed)


def _projected_return(module, tmp_path):
    package_path, _package_value = _package(tmp_path)
    _trust_exact_bytes(module, package_path)
    work = tmp_path / "return"
    module.start(package_path, work)
    module.answer_action(work, "request-000001", "add-source")
    supplied = tmp_path / "report.cs"
    supplied.write_text("formula source\n")
    module.bind_source(work, "request-000001", supplied)
    module.bind_verbatim_projection(work, "return-source-000001", supplied)
    return work


def test_assesses_each_bound_gap_one_at_a_time_with_exact_enum(tmp_path):
    module = _module()
    work = _projected_return(module, tmp_path)

    first = module.prepare_gap_question(work)
    assert first["question"]["unit"]["unit_id"] == "gap-000001"
    assert first["question"]["allowed_verdicts"] == ["sufficient", "insufficient", "cannot-assess"]
    assert len(first["question"]["obligations"]) == 1
    rejected = module.submit_gap_response(work, json.dumps({
        "unit_id": "gap-000001",
        "assessments": [{
            "obligation_id": "gap-999999", "verdict": "maybe", "reason": "guess",
            "evidence_ids": ["invented"], "missing_evidence": None,
        }],
    }))
    assert rejected["status"] == "rejected"

    while True:
        prepared = module.prepare_gap_question(work)
        if prepared["status"] == "complete":
            break
        question = prepared["question"]
        obligation = question["obligations"][0]
        result = module.submit_gap_response(work, json.dumps({
            "unit_id": question["unit"]["unit_id"],
            "assessments": [{
                "obligation_id": obligation["obligation_id"],
                "verdict": "sufficient",
                "reason": "The frozen projection contains the requested evidence.",
                "evidence_ids": [obligation["evidence"][0]["evidence_id"]],
                "missing_evidence": None,
            }],
        }))
        if result["status"] == "complete":
            prepared = result
            break

    assert prepared["result"]["gap_count"] == 2
    assert prepared["result"]["verdict_counts"]["sufficient"] == 2
    source_ref = prepared["result"]["assessment_return_source"]
    assert Path(source_ref["path"]) == (work / "assessment-return.json").resolve()
    assert source_ref["sha256"] == hashlib.sha256((work / "assessment-return.json").read_bytes()).hexdigest()


def test_reassessment_removes_only_resolved_gap_and_preserves_other_findings(tmp_path):
    module = _module()
    findings = [
        {"unit_id": "unit-1", "verdict": "incomplete", "gap_ids": ["gap-1", "gap-2"], "missing_evidence": ["one", "two"]},
        {"unit_id": "unit-2", "verdict": "misaligned", "gap_ids": [], "missing_evidence": [], "measure": "different"},
    ]
    gaps = {
        "gap-1": {"gap_id": "gap-1", "unit_id": "unit-1", "obligation_id": "unit-1:criterion"},
        "gap-2": {"gap_id": "gap-2", "unit_id": "unit-1", "obligation_id": "unit-1:observation"},
    }
    assessments = {"assessments": [
        {"unit_id": "gap-1", "assessments": [{"verdict": "sufficient"}]},
        {"unit_id": "gap-2", "assessments": [{"verdict": "insufficient"}]},
    ]}

    result, resolved, changed, unchanged = module._reassessed_findings(findings, gaps, assessments)

    assert result[0]["gap_ids"] == ["gap-2"]
    assert result[0]["missing_evidence"] == ["two"]
    assert result[0]["reason"] == "Evidence is incomplete for unit-1:observation."
    assert result[1] == findings[1]
    assert resolved == ["gap-1"]
    assert changed == ["unit-1"]
    assert unchanged == ["unit-2"]


def test_successor_requests_remove_only_resolved_gaps_and_restore_exact_units():
    module = _module()
    requests = [{
        "request_id": "request-1",
        "role": "criterion",
        "gap_ids": ["gap-1", "gap-2", "gap-3"],
        "unit_ids": ["unit-1", "unit-2"],
        "question": "Provide criterion evidence.",
        "missing_evidence": ["one", "two", "three"],
    }]
    gaps = {
        "gap-1": {"gap_id": "gap-1", "unit_id": "unit-1"},
        "gap-2": {"gap_id": "gap-2", "unit_id": "unit-1"},
        "gap-3": {"gap_id": "gap-3", "unit_id": "unit-2"},
    }

    result = module._remaining_requests(requests, gaps, ["gap-1", "gap-3"])

    assert result == [{
        "request_id": "request-1",
        "role": "criterion",
        "gap_ids": ["gap-1", "gap-3"],
        "unit_ids": ["unit-1", "unit-2"],
        "question": "Provide criterion evidence.",
        "missing_evidence": ["one", "three"],
    }]


def test_successor_requests_refuse_uncovered_remaining_gap():
    module = _module()
    requests = [{
        "request_id": "request-1",
        "gap_ids": ["gap-1"],
        "missing_evidence": ["one"],
    }]
    gaps = {
        "gap-1": {"gap_id": "gap-1", "unit_id": "unit-1"},
        "gap-2": {"gap_id": "gap-2", "unit_id": "unit-2"},
    }

    with pytest.raises(module.AssessmentReturnError, match="exactly cover"):
        module._remaining_requests(requests, gaps, ["gap-1", "gap-2"])


def test_successor_verifier_refuses_changed_recomputed_summary(tmp_path, monkeypatch):
    module = _module()
    work = tmp_path / "return"
    output = work / "successor-package-v1" / "assessment-package.json"
    output.parent.mkdir(parents=True)
    expected = {
        "schema_version": 1,
        "artifact_type": "info-intake-assessment-successor-package",
        "status": "assessment-ready",
        "lineage": {
            "assessment_return": {"path": str((work / "assessment-return.json").resolve())},
        },
        "summary": {"gap_count": 1},
    }
    changed = json.loads(json.dumps(expected))
    changed["summary"]["gap_count"] = 0
    output.write_text(json.dumps(changed, sort_keys=True) + "\n")
    monkeypatch.setattr(module, "_successor_package_value", lambda candidate: expected)

    with pytest.raises(module.AssessmentReturnError, match="source bindings changed"):
        module.verify_successor_package(output)
