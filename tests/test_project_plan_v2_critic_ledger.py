from __future__ import annotations

import json

from scripts import project_plan_v2_critic_ledger as projector


def test_projects_critic_approvals_and_open_findings(tmp_path):
    ledger_path = tmp_path / "verification-ledger.json"
    critic_path = tmp_path / "critic.json"
    output_path = tmp_path / "projected.json"
    ledger_path.write_text(json.dumps({
        "iteration": 0,
        "findings": [],
        "coverage_queue": [
            {"id": "C-CHECKED", "status": "unverified"},
            {"id": "C-GAP", "status": "unverified"},
        ],
        "plan_verification": {
            "inventory_sha256": "inventory",
            "inventories": [{
                "inventory_sha256": "inventory",
                "completeness_approval": None,
                "completeness_approval_ref": None,
                "obligations": [
                    {"id": "O1", "coverage_id": "C-GAP"},
                    {"id": "O2", "coverage_id": "C-CHECKED"},
                ],
            }],
            "assignments": [],
            "obligation_assessments": [],
            "critic_outputs": [],
        },
    }))
    finding = {"id": "F1", "obligation_ids": ["O1"]}
    gap_assessment = {
        "iteration": 1,
        "obligation_id": "O1",
        "binding_sha256": "binding",
        "status": "GAP",
        "evidence": [{"id": "E1"}],
        "finding_snapshots": [{"id": "F1"}],
        "blocked_boundary": None,
    }
    supported_assessment = {
        "iteration": 1,
        "obligation_id": "O2",
        "binding_sha256": "binding-2",
        "status": "SUPPORTED",
        "evidence": [{"id": "E2"}],
        "finding_snapshots": [],
        "blocked_boundary": None,
    }
    critic_path.write_text(json.dumps({
        "attempt_id": "attempt",
        "verification_iteration": 1,
        "assigned_obligation_ids": ["O1", "O2"],
        "findings": [finding],
        "dispositions": [{"finding_id": "F1", "decision": "FIX NOW"}],
        "obligation_assessments": [gap_assessment, supported_assessment],
        "assessment_approvals": [
            {
                "obligation_id": "O1",
                "assessment_fingerprint": "agent-value",
                "decision": "APPROVED",
            },
            {
                "obligation_id": "O2",
                "assessment_fingerprint": "agent-value-2",
                "decision": "APPROVED",
            },
        ],
        "inventory_approval": {"decision": "APPROVED"},
        "coverage_exclusion_approvals": [],
    }))

    projector.project(ledger_path, critic_path, output_path)

    projected = json.loads(output_path.read_text())
    plan = projected["plan_verification"]
    assert projected["iteration"] == 1
    assert projected["findings"][0]["status"] == "open"
    assert plan["assignments"][0]["assigned_obligation_ids"] == ["O1", "O2"]
    assert len(plan["obligation_assessments"]) == 2
    assert all(
        item["approval"]["decision"] == "APPROVED"
        for item in plan["obligation_assessments"]
    )
    statuses = {item["id"]: item["status"] for item in projected["coverage_queue"]}
    assert statuses == {"C-CHECKED": "checked", "C-GAP": "unverified"}
    snapshot = ledger_path.parent / plan["critic_outputs"][0]["snapshot_path"]
    assert projector.digest(snapshot.read_bytes()) == plan["critic_outputs"][0]["output_sha256"]


def test_preserves_contiguous_history_across_iterations(tmp_path):
    ledger_path = tmp_path / "verification-ledger.json"
    critic_path = tmp_path / "critic.json"
    first_output = tmp_path / "projected-1.json"
    second_output = tmp_path / "projected-2.json"
    ledger_path.write_text(json.dumps({
        "iteration": 0,
        "findings": [],
        "coverage_queue": [{"id": "C1", "status": "unverified"}],
        "plan_verification": {
            "inventory_sha256": "inventory",
            "inventories": [{
                "inventory_sha256": "inventory",
                "completeness_approval": None,
                "completeness_approval_ref": None,
                "obligations": [{"id": "O1", "coverage_id": "C1"}],
            }],
            "assignments": [],
            "obligation_assessments": [],
            "critic_outputs": [],
        },
    }))

    def critic(iteration, attempt_id):
        assessment = {
            "iteration": iteration,
            "obligation_id": "O1",
            "binding_sha256": "binding",
            "status": "SUPPORTED",
            "evidence": [{"id": "E1"}],
            "finding_snapshots": [],
            "blocked_boundary": None,
        }
        return {
            "attempt_id": attempt_id,
            "verification_iteration": iteration,
            "assigned_obligation_ids": ["O1"],
            "findings": [],
            "dispositions": [],
            "obligation_assessments": [assessment],
            "assessment_approvals": [{
                "obligation_id": "O1",
                "assessment_fingerprint": "agent-value",
                "decision": "APPROVED",
            }],
            "inventory_approval": {"decision": "APPROVED"},
            "coverage_exclusion_approvals": [],
        }

    critic_path.write_text(json.dumps(critic(1, "attempt-1")))
    projector.project(ledger_path, critic_path, first_output)
    critic_path.write_text(json.dumps(critic(2, "attempt-2")))
    projector.project(first_output, critic_path, second_output)

    projected = json.loads(second_output.read_text())
    plan = projected["plan_verification"]
    assert [item["iteration"] for item in plan["assignments"]] == [1, 2]
    assert [item["iteration"] for item in plan["obligation_assessments"]] == [1, 2]
    assert {item["attempt_id"] for item in plan["critic_outputs"]} == {
        "attempt-1", "attempt-2",
    }


def test_rejected_inventory_keeps_supported_coverage_unverified(tmp_path):
    ledger_path = tmp_path / "verification-ledger.json"
    critic_path = tmp_path / "critic.json"
    output_path = tmp_path / "projected.json"
    ledger_path.write_text(json.dumps({
        "iteration": 0,
        "findings": [],
        "coverage_queue": [{"id": "C1", "status": "unverified"}],
        "plan_verification": {
            "inventory_sha256": "inventory",
            "inventories": [{
                "inventory_sha256": "inventory",
                "completeness_approval": None,
                "completeness_approval_ref": None,
                "obligations": [{"id": "O1", "coverage_id": "C1"}],
            }],
            "assignments": [],
            "obligation_assessments": [],
            "critic_outputs": [],
        },
    }))
    critic_path.write_text(json.dumps({
        "attempt_id": "attempt",
        "verification_iteration": 1,
        "assigned_obligation_ids": ["O1"],
        "findings": [],
        "dispositions": [],
        "obligation_assessments": [{
            "iteration": 1,
            "obligation_id": "O1",
            "binding_sha256": "binding",
            "status": "SUPPORTED",
            "evidence": [{"id": "E1"}],
            "finding_snapshots": [],
            "blocked_boundary": None,
        }],
        "assessment_approvals": [{
            "obligation_id": "O1",
            "assessment_fingerprint": "agent-value",
            "decision": "APPROVED",
        }],
        "inventory_approval": {"decision": "REJECTED"},
        "coverage_exclusion_approvals": [],
    }))

    projector.project(ledger_path, critic_path, output_path)

    projected = json.loads(output_path.read_text())
    assert projected["coverage_queue"] == [{"id": "C1", "status": "unverified"}]
