from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from memory_knowledge import server
from memory_knowledge.admin import playbooks


class DummyPool:
    pass


@pytest.mark.asyncio
async def test_failure_mode_playbooks_synthesizes_multiple_sources(monkeypatch):
    async def fake_convergence(*args, **kwargs):
        return {
            "summary": [
                {
                    "workflow_name": "wf-a",
                    "actor_email": "unknown",
                    "run_count": 3,
                    "latest_run_grade": "F",
                    "max_iteration_count": 4,
                    "dominant_retry_phase": "validate",
                    "dominant_failed_validator": "OUTPUT_CONTRACT",
                    "reason_counts": [{"reason_code": "RUN_ERROR", "count": 2}],
                    "primary_recommendation": "ADD_PRE_RETRY_GROUNDING",
                }
            ]
        }

    async def fake_finding_patterns(*args, **kwargs):
        return {
            "summary": [
                {
                    "workflow_name": "wf-a",
                    "finding_kind": "STYLE",
                    "phase_id": "review",
                    "occurrence_count": 4,
                    "dismiss_count": 3,
                    "actionable_count": 1,
                }
            ]
        }

    async def fake_failure_modes(*args, **kwargs):
        return {
            "summary": [
                {
                    "workflow_name": "wf-a",
                    "agent_name": "verifier",
                    "finding_kind": "STYLE",
                    "phase_id": "review",
                    "finding_count": 5,
                    "repeat_rate": 0.4,
                    "critic_actionable_rate": 0.6,
                }
            ]
        }

    async def fake_confusion(*args, **kwargs):
        return {
            "clusters": [
                {
                    "cluster_key": "task|planning-workflow||feature|corrected",
                    "request_kind": "task",
                    "selected_workflow_name": "planning-workflow",
                    "selected_run_action": None,
                    "corrected_request_kind": "feature",
                    "case_count": 2,
                    "clarification_count": 2,
                }
            ]
        }

    monkeypatch.setattr(playbooks.analytics, "get_convergence_recommendation_summary", fake_convergence)
    monkeypatch.setattr(playbooks.findings, "get_finding_pattern_summary", fake_finding_patterns)
    monkeypatch.setattr(playbooks.findings, "get_agent_failure_mode_summary", fake_failure_modes)
    monkeypatch.setattr(playbooks.triage_memory, "get_triage_confusion_clusters", fake_confusion)

    data = await playbooks.get_failure_mode_playbooks(DummyPool(), repository_key="repo-a")

    assert data["count"] == 4
    assert data["playbooks"][0]["playbook_code"] == "RERUN_RETRIEVAL_CONTEXT"
    assert any(item["playbook_code"] == "SUPPRESS_LOW_VALUE_NOISE" for item in data["playbooks"])
    assert any(item["playbook_code"] == "ADD_PHASE_GUARDRAIL" for item in data["playbooks"])
    assert any(item["playbook_code"] == "ESCALATE_TO_PLANNING_FIRST" for item in data["playbooks"])
    assert data["source_counts"]["triage_confusion_clusters"] == 1


@pytest.mark.asyncio
async def test_failure_mode_playbooks_returns_empty_collections(monkeypatch):
    async def empty_summary(*args, **kwargs):
        return {"summary": []}

    async def empty_clusters(*args, **kwargs):
        return {"clusters": []}

    monkeypatch.setattr(playbooks.analytics, "get_convergence_recommendation_summary", empty_summary)
    monkeypatch.setattr(playbooks.findings, "get_finding_pattern_summary", empty_summary)
    monkeypatch.setattr(playbooks.findings, "get_agent_failure_mode_summary", empty_summary)
    monkeypatch.setattr(playbooks.triage_memory, "get_triage_confusion_clusters", empty_clusters)

    data = await playbooks.get_failure_mode_playbooks(DummyPool(), repository_key="repo-a")

    assert data["playbooks"] == []
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_get_failure_mode_playbooks_tool_validates_and_returns_data(monkeypatch):
    monkeypatch.setattr(server, "get_pg_pool", lambda: DummyPool())
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())

    async def fake_tool(*args, **kwargs):
        return {"playbooks": [{"playbook_code": "REQUEST_CLARIFICATION"}], "count": 1, "source_counts": {}}

    monkeypatch.setattr(server._playbooks, "get_failure_mode_playbooks", fake_tool)

    result = await server.get_failure_mode_playbooks(repository_key="repo-a", limit=5)
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["playbooks"][0]["playbook_code"] == "REQUEST_CLARIFICATION"

    result = await server.get_failure_mode_playbooks(repository_key="repo-a", limit=0)
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "limit must be >= 1"

    result = await server.get_failure_mode_playbooks(repository_key="", limit=1)
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "repository_key is required"
