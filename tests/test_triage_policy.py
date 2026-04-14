import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

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
            rows = [
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
            repository_key, project_key, request_kind, selected_workflow_name, selected_run_action, _lookback_days = args
            filtered = []
            for row in rows:
                conditional_run_action = row["selected_run_action"] if row["request_kind"] == "run_operation" else None
                if repository_key is not None and row["repository_key"] != repository_key:
                    continue
                if project_key is not None and row["project_key"] != project_key:
                    continue
                if request_kind is not None and row["request_kind"] != request_kind:
                    continue
                if selected_workflow_name is not None and row["selected_workflow_name"] != selected_workflow_name:
                    continue
                if selected_run_action is not None and conditional_run_action != selected_run_action:
                    continue
                filtered.append(row)
            return filtered
        if "WHERE ($1::boolean = FALSE OR tc.triage_case_id::text = ANY($2::text[]))" in query:
            return [
                {
                    "triage_case_id": uuid4(),
                    "prompt_text": "Need planning help",
                    "request_kind": "task",
                    "execution_mode": "advisory",
                    "knowledge_mode": "memory_first",
                    "selected_workflow_name": "planning-workflow",
                    "selected_run_action": None,
                    "requires_clarification": False,
                    "confidence": 0.88,
                    "project_key": "PAY",
                    "feature_key": None,
                    "repository_key": "repo-a",
                    "policy_version": "triage-policy-v1",
                    "created_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                    "lifecycle_state": "validated",
                    "lifecycle_updated_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                    "superseded_by_case_id": None,
                    "outcome_status": "confirmed_correct",
                    "corrected_request_kind": None,
                }
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
    async def _default_actor_summary(*args, **kwargs):
        return {
            "match_found": False,
            "adaptation_mode": "balanced",
            "confidence_delta": 0.0,
            "requires_stronger_clarification": False,
            "preferred_route_posture": "standard",
            "team_key": "team:unknown",
            "evidence": {"run_count": 0, "avg_score": 0.0, "entropy_target_count": 0, "primary_recommendation": None},
            "planning_context": {"projects": [], "features": [], "tasks": []},
        }
    monkeypatch.setattr("memory_knowledge.triage_policy.actor_adaptation.get_actor_adaptation_summary", _default_actor_summary)
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
    assert "required_missing_fields" in first_policy
    assert "mode" in first_policy
    assert first_policy["confidence"] > 0.0


@pytest.mark.asyncio
async def test_get_required_clarification_policy_tool_success(policy_env):
    result = await server.get_required_clarification_policy(
        repository_key="repo-a",
        project_key="PAY",
        request_kind="run_operation",
        min_case_count=1,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["match_found"] is True
    assert payload["data"]["policy"]["selected_workflow_name"] == "deploy-workflow"
    assert "required_missing_fields" in payload["data"]["policy"]


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

    result = await server.get_required_clarification_policy(repository_key="repo-a", min_case_count=0)
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "min_case_count must be >= 1"

    result = await server.get_policy_governance_rollout_summary(repository_key="")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "repository_key is required"

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
async def test_get_policy_governance_rollout_summary_tool_success(policy_env):
    result = await server.get_policy_governance_rollout_summary(repository_key="repo-a", project_key="PAY")
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["artifact_count"] == 1
    assert payload["data"]["overall_stage"] == "promotion_candidate"
    assert payload["data"]["trust_ready_count"] == 1
    assert payload["data"]["proposed_actions"] == ["promote_stable_advisory_candidates"]


@pytest.mark.asyncio
async def test_get_outcome_weighted_routing_summary_tool_success(policy_env):
    result = await server.get_outcome_weighted_routing_summary(
        repository_key="repo-a",
        project_key="PAY",
        min_case_count=1,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["route_count"] == 2
    top_route = payload["data"]["routes"][0]
    assert top_route["selected_workflow_name"] == "planning-workflow"
    assert top_route["route_bias"] in {"prefer", "neutral", "clarify_first", "avoid"}
    assert "failure_rate" in top_route


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
    assert "route_failure_penalty" in payload["data"]["ranking_features"]
    assert payload["data"]["outcome_weighted_routes"][0]["selected_workflow_name"] == "planning-workflow"
    assert payload["data"]["required_clarification_policy"]["selected_workflow_name"] == "planning-workflow"
    assert payload["data"]["requires_clarification_recommendation"] in {True, False}
    assert payload["data"]["policy_status"][0]["rollout_stage"] == "advisory"


@pytest.mark.asyncio
async def test_triage_request_with_memory_applies_actor_adaptation(policy_env, monkeypatch):
    async def _actor_summary(*args, **kwargs):
        return {
            "match_found": True,
            "adaptation_mode": "cautious",
            "confidence_delta": -0.1,
            "requires_stronger_clarification": True,
            "preferred_route_posture": "safer_default",
            "team_key": "project:pay",
            "evidence": {"run_count": 3, "avg_score": 58.0, "entropy_target_count": 1, "primary_recommendation": "ADD_PRE_RETRY_GROUNDING"},
            "planning_context": {"projects": [{"project_key": "pay", "project_name": "Pay"}], "features": [], "tasks": []},
        }

    monkeypatch.setattr("memory_knowledge.triage_policy.actor_adaptation.get_actor_adaptation_summary", _actor_summary)

    result = await server.triage_request_with_memory(
        repository_key="repo-a",
        project_key="PAY",
        prompt_text="Need planning help",
        request_kind="task",
        actor_email="user@example.com",
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["actor_adaptation"]["adaptation_mode"] == "cautious"
    assert payload["data"]["recommendation_confidence"] == 0.675
    assert payload["data"]["requires_clarification_recommendation"] is True


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
