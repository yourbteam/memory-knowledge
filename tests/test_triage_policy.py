import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from memory_knowledge import server


class PolicyPool:
    def __init__(self):
        self.fetch_calls: list[tuple[str, tuple]] = []
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "SELECT id FROM catalog.repositories WHERE repository_key = $1" in query:
            return {"id": 7} if args[0] == "repo-a" else None
        return None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        if "FROM ops.triage_policy_artifacts tpa" in query:
            return [
                {
                    "policy_kind": "routing_recommendation",
                    "policy_key": "task|planning-workflow|",
                    "version": "triage-policy-v1",
                    "confidence": 0.75,
                    "case_count": 2,
                    "rollout_stage": "advisory",
                    "confidence_threshold": 0.75,
                    "minimum_evidence_threshold": 2,
                    "drift_state": "stable",
                    "is_suppressed": False,
                    "last_reviewed_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                    "governance_notes": None,
                }
            ]
        if "/* triage_policy_source_rows */" in query:
            return [
                {
                    "repository_key": "repo-a",
                    "project_key": "PAY",
                    "prompt_text": "Need planning help",
                    "request_kind": "task",
                    "selected_workflow_name": "planning-workflow",
                    "selected_run_action": None,
                    "requires_clarification": False,
                    "clarifying_questions": [],
                    "created_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                    "lifecycle_state": "validated",
                    "lifecycle_updated_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                    "superseded_by_case_id": None,
                    "outcome_status": "confirmed_correct",
                    "corrected_request_kind": None,
                    "successful_execution": True,
                },
                {
                    "repository_key": "repo-a",
                    "project_key": "PAY",
                    "prompt_text": "Need another plan",
                    "request_kind": "task",
                    "selected_workflow_name": "planning-workflow",
                    "selected_run_action": None,
                    "requires_clarification": True,
                    "clarifying_questions": ["What repo path is in scope?"],
                    "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                    "lifecycle_state": "feedback_recorded",
                    "lifecycle_updated_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                    "superseded_by_case_id": None,
                    "outcome_status": "pending",
                    "corrected_request_kind": None,
                    "successful_execution": None,
                },
                {
                    "repository_key": "repo-a",
                    "project_key": "PAY",
                    "prompt_text": "Run deploy",
                    "request_kind": "run_operation",
                    "selected_workflow_name": "deploy-workflow",
                    "selected_run_action": "deploy",
                    "requires_clarification": True,
                    "clarifying_questions": ["Which environment should I deploy to?"],
                    "created_utc": datetime(2026, 4, 12, tzinfo=timezone.utc),
                    "lifecycle_state": "needs_retriage",
                    "lifecycle_updated_utc": datetime(2026, 4, 12, tzinfo=timezone.utc),
                    "superseded_by_case_id": None,
                    "outcome_status": "corrected",
                    "corrected_request_kind": None,
                    "successful_execution": False,
                },
            ]
        return []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "OK"


@pytest.fixture
def policy_env(monkeypatch):
    pool = PolicyPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    return pool


@pytest.mark.asyncio
async def test_get_routing_policy_recommendations_tool_success(policy_env):
    result = await server.get_routing_policy_recommendations(
        repository_key="repo-a",
        project_key="PAY",
        min_case_count=1,
        min_confidence=0.5,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["advisory_only"] is True
    assert payload["data"]["recommendation_count"] == 1
    recommendation = payload["data"]["recommendations"][0]
    assert recommendation["recommended_workflow_name"] == "planning-workflow"
    assert recommendation["request_kind"] == "task"
    assert recommendation["confidence"] >= 0.5


@pytest.mark.asyncio
async def test_get_routing_policy_recommendations_tool_empty_scope(policy_env):
    result = await server.get_routing_policy_recommendations(
        repository_key="repo-a",
        request_kind="feature",
        min_case_count=5,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["recommendations"] == []


@pytest.mark.asyncio
async def test_get_clarification_policy_tool_success(policy_env):
    result = await server.get_clarification_policy(
        repository_key="repo-a",
        project_key="PAY",
        min_case_count=1,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["policy_count"] >= 1
    first_policy = payload["data"]["policies"][0]
    assert "suggested_questions" in first_policy
    assert first_policy["confidence"] > 0.0


@pytest.mark.asyncio
async def test_list_triage_behavior_profiles_tool_success(policy_env):
    result = await server.list_triage_behavior_profiles(repository_key="repo-a", project_key="PAY")
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["profile_count"] == 2
    assert payload["data"]["profiles"][0]["case_count"] >= payload["data"]["profiles"][1]["case_count"]


@pytest.mark.asyncio
async def test_policy_tools_validate_arguments(policy_env):
    result = await server.get_routing_policy_recommendations(repository_key="", min_case_count=0)
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "repository_key is required"

    result = await server.get_clarification_policy(repository_key="repo-a", limit=0)
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "limit must be >= 1"

    result = await server.list_triage_behavior_profiles(repository_key="repo-a", lookback_days=0)
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "lookback_days must be >= 1"

    result = await server.get_routing_policy_recommendations(repository_key="repo-a", min_confidence="bad")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "min_confidence must be between 0 and 1"


@pytest.mark.asyncio
async def test_refresh_triage_policy_artifacts_tool_persists_artifacts(policy_env):
    result = await server.refresh_triage_policy_artifacts(
        repository_key="repo-a",
        project_key="PAY",
        routing_min_case_count=1,
        clarification_min_case_count=1,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["persisted_artifact_count"] >= 1
    assert any("DELETE FROM ops.triage_policy_artifacts" in query for query, _args in policy_env.execute_calls)
    assert any("INSERT INTO ops.triage_policy_artifacts" in query for query, _args in policy_env.execute_calls)
    insert_query, insert_args = next(
        (query, args) for query, args in policy_env.execute_calls if "INSERT INTO ops.triage_policy_artifacts" in query
    )
    assert "rollout_stage" in insert_query
    assert insert_args[9] == "advisory"


@pytest.mark.asyncio
async def test_get_behavior_policy_status_tool_success(policy_env):
    result = await server.get_behavior_policy_status(repository_key="repo-a", project_key="PAY")
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["artifact_count"] == 1
    assert payload["data"]["artifacts"][0]["rollout_stage"] == "advisory"


@pytest.mark.asyncio
async def test_triage_request_with_memory_tool_success(policy_env):
    result = await server.triage_request_with_memory(
        repository_key="repo-a",
        project_key="PAY",
        prompt_text="Need planning help",
        request_kind="task",
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["recommended_workflow_name"] == "planning-workflow"
    assert "ranking_features" in payload["data"]
    assert payload["data"]["policy_status"][0]["rollout_stage"] == "advisory"


@pytest.mark.asyncio
async def test_finalize_triage_outcome_tool_success(monkeypatch, policy_env):
    async def _record_feedback(*args, **kwargs):
        return True

    monkeypatch.setattr("memory_knowledge.triage_memory.record_triage_case_feedback", _record_feedback)

    result = await server.finalize_triage_outcome(
        triage_case_id="11111111-1111-1111-1111-111111111111",
        repository_key="repo-a",
        project_key="PAY",
        outcome_status="confirmed_correct",
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["policy_artifacts_refreshed"] is True
    assert payload["data"]["policy_status"]["artifact_count"] == 1
