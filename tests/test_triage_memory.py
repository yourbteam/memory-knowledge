import json
import uuid
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from memory_knowledge import server
from memory_knowledge import triage_memory


class FakeQdrant:
    def __init__(self):
        self.upserts = []
        self.search_calls = []

    async def upsert(self, collection_name, points):
        self.upserts.append((collection_name, points))

    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return [SimpleNamespace(id="11111111-1111-1111-1111-111111111111", score=0.91, payload={})]


class EmptySearchQdrant(FakeQdrant):
    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return []


class ReprojectableQdrant(FakeQdrant):
    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        if not self.upserts:
            return []
        point = self.upserts[-1][1][0]
        return [SimpleNamespace(id=str(point.id), score=0.91, payload={})]


class QueryPointsQdrant(FakeQdrant):
    async def query_points(self, **kwargs):
        self.search_calls.append(kwargs)
        return SimpleNamespace(
            points=[SimpleNamespace(id="11111111-1111-1111-1111-111111111111", score=0.91, payload={})]
        )


class TriagePool:
    def __init__(self):
        self.fetchrow_calls = []
        self.fetch_calls = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "SELECT id FROM catalog.repositories WHERE repository_key = $1" in query:
            return {"id": 7} if args[0] == "repo-a" else None
        if "INSERT INTO ops.triage_cases" in query:
            return {
                "triage_case_id": uuid.UUID(str(args[0])),
                "request_kind": args[4],
                "selected_workflow_name": args[7],
                "project_key": args[15],
                "feature_key": args[16],
                "policy_version": args[19],
                "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                "lifecycle_updated_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
            }
        if "SELECT triage_case_id FROM ops.triage_cases" in query:
            return {"triage_case_id": uuid.UUID(args[0])} if args[0] == "11111111-1111-1111-1111-111111111111" else None
        if "FROM core.reference_values rv" in query and "WHERE rt.internal_code = $1 AND rv.internal_code = $2" in query:
            type_code, value_code = args
            if type_code == "TRIAGE_OUTCOME_STATUS" and value_code == "TRIAGE_OUTCOME_CORRECTED":
                return {"id": 201}
            if type_code == "TRIAGE_OUTCOME_STATUS" and value_code == "TRIAGE_OUTCOME_CONFIRMED_CORRECT":
                return {"id": 202}
            if type_code == "TRIAGE_DECISION_LIFECYCLE_STATE" and value_code == "TRIAGE_LIFECYCLE_PROPOSED":
                return {"id": 401}
            if type_code == "TRIAGE_DECISION_LIFECYCLE_STATE" and value_code == "TRIAGE_LIFECYCLE_VALIDATED":
                return {"id": 402}
            if type_code == "TRIAGE_DECISION_LIFECYCLE_STATE" and value_code == "TRIAGE_LIFECYCLE_NEEDS_RETRIAGE":
                return {"id": 403}
            if type_code == "TRIAGE_DECISION_LIFECYCLE_STATE" and value_code == "TRIAGE_LIFECYCLE_HUMAN_REJECTED":
                return {"id": 404}
            if type_code == "TRIAGE_DECISION_LIFECYCLE_STATE" and value_code == "TRIAGE_LIFECYCLE_FEEDBACK_RECORDED":
                return {"id": 405}
            if type_code == "TRIAGE_DECISION_LIFECYCLE_STATE" and value_code == "TRIAGE_LIFECYCLE_SUPERSEDED":
                return {"id": 406}
            return None
        if "INSERT INTO ops.triage_case_feedback" in query:
            return {"id": 1}
        if "UPDATE ops.triage_cases" in query and "SET lifecycle_state_id = $2" in query:
            return {"triage_case_id": uuid.UUID(args[0])}
        return None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        if "/* triage_analysis_rows */" in query:
            return [
                {
                    "prompt_text": "Need planning help",
                    "request_kind": "task",
                    "selected_workflow_name": "planning-workflow",
                    "selected_run_action": None,
                    "requires_clarification": False,
                    "created_utc": datetime(2026, 4, 10, tzinfo=timezone.utc),
                    "outcome_status": "confirmed_correct",
                    "corrected_request_kind": None,
                },
                {
                    "prompt_text": "Need planning help urgently",
                    "request_kind": "task",
                    "selected_workflow_name": "planning-workflow",
                    "selected_run_action": None,
                    "requires_clarification": True,
                    "created_utc": datetime(2026, 4, 11, tzinfo=timezone.utc),
                    "outcome_status": "corrected",
                    "corrected_request_kind": "feature",
                },
                {
                    "prompt_text": "Need planning help urgently",
                    "request_kind": "task",
                    "selected_workflow_name": "planning-workflow",
                    "selected_run_action": None,
                    "requires_clarification": True,
                    "created_utc": datetime(2026, 4, 12, tzinfo=timezone.utc),
                    "outcome_status": "corrected",
                    "corrected_request_kind": "feature",
                },
                {
                    "prompt_text": "Deploy this workflow",
                    "request_kind": "run_operation",
                    "selected_workflow_name": "deploy-workflow",
                    "selected_run_action": "deploy",
                    "requires_clarification": True,
                    "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                    "outcome_status": "insufficient_context",
                    "corrected_request_kind": None,
                },
            ]
        if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
            return [
                {
                    "triage_case_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
                    "prompt_text": "Need planning help",
                    "request_kind": "task",
                    "execution_mode": "autonomous_safe",
                    "knowledge_mode": "memory_knowledge",
                    "selected_workflow_name": "planning-workflow",
                    "selected_run_action": None,
                    "requires_clarification": False,
                    "confidence": 0.8,
                    "project_key": "PAY",
                    "feature_key": "payments",
                    "repository_key": "repo-a",
                    "policy_version": None,
                    "created_utc": None,
                    "lifecycle_state": "validated",
                    "lifecycle_updated_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                    "superseded_by_case_id": None,
                    "outcome_status": "confirmed_correct",
                    "corrected_request_kind": None,
                }
            ]
        if "FROM ops.triage_cases tc" in query and "corrected_request_kind" in query:
            return [
                {
                    "prompt_text": "Need planning help",
                    "request_kind": "task",
                    "requires_clarification": False,
                    "created_utc": datetime(2026, 4, 12, tzinfo=timezone.utc),
                    "outcome_status": "confirmed_correct",
                    "corrected_request_kind": None,
                },
                {
                    "prompt_text": "Implement this feature",
                    "request_kind": "task",
                    "requires_clarification": True,
                    "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                    "outcome_status": "corrected",
                    "corrected_request_kind": "feature",
                },
            ]
        return []


@pytest.fixture
def triage_env(monkeypatch):
    pool = TriagePool()
    qdrant = FakeQdrant()
    settings = SimpleNamespace(embedding_dimensions=8)
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(server, "get_settings", lambda: settings)
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    monkeypatch.setattr("memory_knowledge.triage_memory.embed_single", lambda text, settings: asyncio.sleep(0, result=[0.1] * 8))
    return pool, qdrant


@pytest.mark.asyncio
async def test_save_triage_case_tool_success(triage_env):
    pool, qdrant = triage_env
    result = await server.save_triage_case(
        repository_key="repo-a",
        prompt_text="Need planning help",
        request_kind="task",
        execution_mode="autonomous_safe",
        knowledge_mode="memory_knowledge",
        suggested_workflows=["planning-workflow"],
        requires_clarification=False,
        clarifying_questions=[],
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["saved"] is True
    assert qdrant.upserts
    insert_query, insert_args = next(
        (query, args) for query, args in pool.fetchrow_calls if "INSERT INTO ops.triage_cases" in query
    )
    assert "INSERT INTO ops.triage_cases" in insert_query
    assert insert_args[8] == json.dumps(["planning-workflow"])
    assert insert_args[11] == json.dumps([])
    assert insert_args[22] == json.dumps([])
    assert insert_args[23] == 401


@pytest.mark.asyncio
async def test_save_triage_case_tool_rejects_unknown_repository(triage_env):
    result = await server.save_triage_case(
        repository_key="missing-repo",
        prompt_text="Need planning help",
        request_kind="task",
        execution_mode="autonomous_safe",
        knowledge_mode="memory_knowledge",
        suggested_workflows=["planning-workflow"],
        requires_clarification=False,
        clarifying_questions=[],
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "not found" in payload["error"]


@pytest.mark.asyncio
async def test_save_triage_case_tool_rejects_non_list_matched_case_ids(triage_env):
    result = await server.save_triage_case(
        repository_key="repo-a",
        prompt_text="Need planning help",
        request_kind="task",
        execution_mode="autonomous_safe",
        knowledge_mode="memory_knowledge",
        suggested_workflows=["planning-workflow"],
        requires_clarification=False,
        clarifying_questions=[],
        matched_case_ids="not-a-list",
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "matched_case_ids must be a list"


@pytest.mark.asyncio
async def test_search_triage_cases_tool_returns_advisory_shape(triage_env):
    _pool, qdrant = triage_env
    result = await server.search_triage_cases(prompt_text="Need planning help", repository_key="repo-a")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["advisory_only"] is True
    assert payload["data"]["rows"][0]["triage_case_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["data"]["rows"][0]["lifecycle_state"] == "validated"
    assert qdrant.search_calls


@pytest.mark.asyncio
async def test_search_triage_cases_tool_uses_query_points_when_available(monkeypatch):
    pool = TriagePool()
    qdrant = QueryPointsQdrant()
    settings = SimpleNamespace(embedding_dimensions=8)
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(server, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "memory_knowledge.triage_memory.embed_single",
        lambda text, settings: asyncio.sleep(0, result=[0.1] * 8),
    )

    result = await server.search_triage_cases(prompt_text="Need planning help", repository_key="repo-a")

    payload = json.loads(result)
    assert payload["status"] == "success"
    assert qdrant.search_calls


@pytest.mark.asyncio
async def test_search_triage_cases_semantic_path_applies_hybrid_ranking(monkeypatch):
    class SemanticQdrant(FakeQdrant):
        async def search(self, **kwargs):
            self.search_calls.append(kwargs)
            return [
                SimpleNamespace(id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", score=0.92, payload={}),
                SimpleNamespace(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", score=0.91, payload={}),
            ]

    class SemanticPool(TriagePool):
        async def fetch(self, query, *args):
            self.fetch_calls.append((query, args))
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "prompt_text": "Repo local prompt",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    },
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "prompt_text": "Remote prompt",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": True,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-b",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "corrected",
                        "corrected_request_kind": "feature",
                    },
                ]
            return await super().fetch(query, *args)

    pool = SemanticPool()
    qdrant = SemanticQdrant()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace(embedding_dimensions=8))
    monkeypatch.setattr("memory_knowledge.triage_memory.embed_single", lambda text, settings: asyncio.sleep(0, result=[0.1] * 8))

    result = await server.search_triage_cases(prompt_text="Need planning help")
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["rows"][0]["triage_case_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert payload["data"]["rows"][0]["similarity_score"] > payload["data"]["rows"][1]["similarity_score"]
    assert qdrant.search_calls


@pytest.mark.asyncio
async def test_search_triage_cases_tool_does_not_lexically_fallback_on_zero_semantic_hits(monkeypatch):
    pool = TriagePool()
    qdrant = EmptySearchQdrant()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace(embedding_dimensions=8))
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    monkeypatch.setattr("memory_knowledge.triage_memory.embed_single", lambda text, settings: asyncio.sleep(0, result=[0.1] * 8))

    result = await server.search_triage_cases(prompt_text="Need planning help", repository_key="repo-a")
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["rows"] == []
    assert payload["data"]["retrieval_summary"]["returned"] == 0
    assert qdrant.search_calls
    assert len(pool.fetch_calls) == 0


async def test_search_triage_cases_hybrid_score_penalizes_clarification_and_rewards_outcome_quality(monkeypatch):
    class RankingPool(TriagePool):
        async def fetch(self, query, *args):
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "prompt_text": "Stable prompt",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    },
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "prompt_text": "Clarification prompt",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": True,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "corrected",
                        "corrected_request_kind": "feature",
                    },
                ]
            return await super().fetch(query, *args)

    pool = RankingPool()

    result = await triage_memory.search_triage_cases(
        pool,
        SimpleNamespace(embedding_dimensions=8),
        prompt_text="Need planning help",
        repository_key="repo-a",
        qdrant_client=None,
    )

    assert result["rows"][0]["triage_case_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert result["rows"][0]["similarity_score"] > result["rows"][1]["similarity_score"]
    assert "ranking_features" in result["rows"][0]


@pytest.mark.asyncio
async def test_search_triage_cases_prefers_validated_lifecycle_when_semantics_are_close(monkeypatch):
    class LifecycleRankingPool(TriagePool):
        async def fetch(self, query, *args):
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "prompt_text": "Validated prompt",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": "PAY",
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "lifecycle_state": "validated",
                        "lifecycle_updated_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "superseded_by_case_id": None,
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    },
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "prompt_text": "Retriage prompt",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": "PAY",
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "lifecycle_state": "needs_retriage",
                        "lifecycle_updated_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "superseded_by_case_id": None,
                        "outcome_status": "corrected",
                        "corrected_request_kind": "feature",
                    },
                ]
            return await super().fetch(query, *args)

    pool = LifecycleRankingPool()
    result = await triage_memory.search_triage_cases(
        pool,
        SimpleNamespace(embedding_dimensions=8),
        prompt_text="Need planning help",
        repository_key="repo-a",
        project_key="PAY",
        qdrant_client=None,
    )

    assert result["rows"][0]["triage_case_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert result["rows"][0]["ranking_features"]["lifecycle_quality"] > result["rows"][1]["ranking_features"]["lifecycle_quality"]


@pytest.mark.asyncio
async def test_search_triage_cases_uses_local_policy_alignment_prior(monkeypatch):
    class PolicyPriorPool(TriagePool):
        async def fetch(self, query, *args):
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "prompt_text": "Strong planning example 1",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                        "lifecycle_state": "validated",
                        "lifecycle_updated_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                        "superseded_by_case_id": None,
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    },
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "prompt_text": "Strong planning example 2",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "lifecycle_state": "validated",
                        "lifecycle_updated_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "superseded_by_case_id": None,
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    },
                    {
                        "triage_case_id": uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
                        "prompt_text": "Deploy example",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "deploy-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                        "lifecycle_state": "validated",
                        "lifecycle_updated_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                        "superseded_by_case_id": None,
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    },
                ]
            return await super().fetch(query, *args)

    candidate_scores = {
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": 0.82,
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": 0.81,
        "cccccccc-cccc-cccc-cccc-cccccccccccc": 0.83,
    }
    result = await triage_memory._fetch_search_rows(
        PolicyPriorPool(),
        candidate_ids=list(candidate_scores.keys()),
        candidate_scores=candidate_scores,
        prompt_text="Need planning help",
        repository_key="repo-a",
        project_key=None,
        feature_key=None,
        request_kind="task",
        execution_mode=None,
        selected_workflow_name=None,
        selected_run_action=None,
        policy_version=None,
        include_corrected=True,
        max_age_days=180,
        limit=3,
        lexical_fallback=False,
    )

    assert result[0]["selected_workflow_name"] == "planning-workflow"
    assert result[0]["ranking_features"]["policy_alignment"] >= result[-1]["ranking_features"]["policy_alignment"]


@pytest.mark.asyncio
async def test_search_triage_cases_hybrid_score_prefers_newer_row_on_tie(monkeypatch):
    class RankingPool(TriagePool):
        async def fetch(self, query, *args):
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "prompt_text": "Older prompt",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 1, 1, tzinfo=timezone.utc),
                        "outcome_status": "pending",
                        "corrected_request_kind": None,
                    },
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "prompt_text": "Newer prompt",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "pending",
                        "corrected_request_kind": None,
                    },
                ]
            return await super().fetch(query, *args)

    pool = RankingPool()

    result = await triage_memory.search_triage_cases(
        pool,
        SimpleNamespace(embedding_dimensions=8),
        prompt_text="Need planning help",
        repository_key="repo-a",
        qdrant_client=None,
    )

    assert result["rows"][0]["triage_case_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.mark.asyncio
async def test_search_triage_cases_lexical_fallback_order_is_deterministic(monkeypatch):
    class RankingPool(TriagePool):
        async def fetch(self, query, *args):
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "prompt_text": "Prompt A",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "pending",
                        "corrected_request_kind": None,
                    },
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "prompt_text": "Prompt B",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "pending",
                        "corrected_request_kind": None,
                    },
                ]
            return await super().fetch(query, *args)

    pool = RankingPool()

    first = await triage_memory.search_triage_cases(
        pool,
        SimpleNamespace(embedding_dimensions=8),
        prompt_text="Need planning help",
        repository_key="repo-a",
        qdrant_client=None,
    )
    second = await triage_memory.search_triage_cases(
        pool,
        SimpleNamespace(embedding_dimensions=8),
        prompt_text="Need planning help",
        repository_key="repo-a",
        qdrant_client=None,
    )

    first_ids = [row["triage_case_id"] for row in first["rows"]]
    second_ids = [row["triage_case_id"] for row in second["rows"]]
    assert first_ids == second_ids == [
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    ]


@pytest.mark.asyncio
async def test_search_triage_cases_consensus_strength_uses_hybrid_similarity_scores(monkeypatch):
    class RankingPool(TriagePool):
        async def fetch(self, query, *args):
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "prompt_text": "Prompt A",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    },
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "prompt_text": "Prompt B",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": True,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "corrected",
                        "corrected_request_kind": "feature",
                    },
                ]
            return await super().fetch(query, *args)

    pool = RankingPool()

    result = await triage_memory.search_triage_cases(
        pool,
        SimpleNamespace(embedding_dimensions=8),
        prompt_text="Need planning help",
        repository_key="repo-a",
        qdrant_client=None,
    )

    scores = [row["similarity_score"] for row in result["rows"]]
    expected = round(sum(scores) / len(scores), 4)
    assert result["retrieval_summary"]["consensus_strength"] == expected


@pytest.mark.asyncio
async def test_search_triage_cases_semantic_path_consensus_strength_uses_ranked_scores(monkeypatch):
    class SemanticQdrant(FakeQdrant):
        async def search(self, **kwargs):
            self.search_calls.append(kwargs)
            return [
                SimpleNamespace(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", score=0.9, payload={}),
                SimpleNamespace(id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", score=0.88, payload={}),
            ]

    class SemanticPool(TriagePool):
        async def fetch(self, query, *args):
            self.fetch_calls.append((query, args))
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "prompt_text": "Prompt A",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    },
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "prompt_text": "Prompt B",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": True,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-b",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "corrected",
                        "corrected_request_kind": "feature",
                    },
                ]
            return await super().fetch(query, *args)

    pool = SemanticPool()
    qdrant = SemanticQdrant()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace(embedding_dimensions=8))
    monkeypatch.setattr("memory_knowledge.triage_memory.embed_single", lambda text, settings: asyncio.sleep(0, result=[0.1] * 8))

    result = await server.search_triage_cases(prompt_text="Need planning help")
    payload = json.loads(result)

    scores = [row["similarity_score"] for row in payload["data"]["rows"]]
    expected = round(sum(scores) / len(scores), 4)
    assert payload["data"]["retrieval_summary"]["consensus_strength"] == expected
    assert payload["data"]["rows"][0]["triage_case_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.mark.asyncio
async def test_search_triage_cases_warns_when_prefer_same_repository_is_disabled(monkeypatch):
    class RankingPool(TriagePool):
        async def fetch(self, query, *args):
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "prompt_text": "Prompt A",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.8,
                        "project_key": None,
                        "feature_key": None,
                        "repository_key": "repo-a",
                        "policy_version": None,
                        "created_utc": datetime(2026, 4, 13, tzinfo=timezone.utc),
                        "outcome_status": "pending",
                        "corrected_request_kind": None,
                    }
                ]
            return await super().fetch(query, *args)

    pool = RankingPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_qdrant_client", lambda: None)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace(embedding_dimensions=8))

    result = await server.search_triage_cases(
        prompt_text="Need planning help",
        repository_key="repo-a",
        prefer_same_repository=False,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert "prefer_same_repository is retained for compatibility" in payload["data"]["warnings"][0]


@pytest.mark.asyncio
async def test_record_triage_case_feedback_tool_rejects_unknown_case(triage_env):
    result = await server.record_triage_case_feedback(
        triage_case_id="22222222-2222-2222-2222-222222222222",
        outcome_status="corrected",
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "not found" in payload["error"]


@pytest.mark.asyncio
async def test_record_triage_case_feedback_tool_rejects_malformed_uuid(triage_env):
    result = await server.record_triage_case_feedback(
        triage_case_id="not-a-uuid",
        outcome_status="corrected",
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "valid UUID" in payload["error"]


@pytest.mark.asyncio
async def test_record_triage_case_feedback_tool_resolves_canonical_status_id(triage_env):
    pool, _qdrant = triage_env
    result = await server.record_triage_case_feedback(
        triage_case_id="11111111-1111-1111-1111-111111111111",
        outcome_status=" corrected ",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    insert_query, insert_args = next(
        (query, args) for query, args in pool.fetchrow_calls if "INSERT INTO ops.triage_case_feedback" in query
    )
    assert "status_id" in insert_query
    assert insert_args[2] == 201
    update_query, update_args = next(
        (query, args) for query, args in pool.fetchrow_calls if "UPDATE ops.triage_cases" in query
    )
    assert "lifecycle_state_id" in update_query
    assert update_args[1] == 403


@pytest.mark.asyncio
async def test_record_triage_case_feedback_tool_preserves_unknown_status_without_reference_id(triage_env):
    pool, _qdrant = triage_env
    result = await server.record_triage_case_feedback(
        triage_case_id="11111111-1111-1111-1111-111111111111",
        outcome_status="custom_status_from_integrator",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    _insert_query, insert_args = next(
        (query, args)
        for query, args in reversed(pool.fetchrow_calls)
        if "INSERT INTO ops.triage_case_feedback" in query
    )
    assert insert_args[1] == "custom_status_from_integrator"
    assert insert_args[2] is None
    _update_query, update_args = next(
        (query, args)
        for query, args in reversed(pool.fetchrow_calls)
        if "UPDATE ops.triage_cases" in query
    )
    assert update_args[1] == 405


@pytest.mark.asyncio
async def test_get_triage_feedback_summary_tool_success(triage_env):
    result = await server.get_triage_feedback_summary(repository_key="repo-a")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["case_count"] == 2
    assert payload["data"]["corrected_rate"] == 0.5
    assert payload["data"]["clarification_rate"] == 0.5


@pytest.mark.asyncio
async def test_get_triage_feedback_summary_tool_empty_scope(monkeypatch):
    class EmptyPool(TriagePool):
        async def fetch(self, query, *args):
            return []

    pool = EmptyPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    result = await server.get_triage_feedback_summary(repository_key="repo-a")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["case_count"] == 0
    assert payload["data"]["top_misroutes"] == []


@pytest.mark.asyncio
async def test_get_triage_confusion_clusters_tool_success(triage_env):
    result = await server.get_triage_confusion_clusters(repository_key="repo-a", limit=5)
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["analyzed_case_count"] == 4
    assert payload["data"]["cluster_count"] == 2
    assert payload["data"]["clusters"][0]["corrected_request_kind"] == "feature"
    assert payload["data"]["clusters"][0]["case_count"] == 2
    assert payload["data"]["clusters"][0]["clarification_count"] == 2


@pytest.mark.asyncio
async def test_get_triage_confusion_clusters_tool_empty_scope(monkeypatch):
    class EmptyPool(TriagePool):
        async def fetch(self, query, *args):
            if "/* triage_analysis_rows */" in query:
                return []
            return await super().fetch(query, *args)

    pool = EmptyPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())

    result = await server.get_triage_confusion_clusters(repository_key="repo-a")
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["cluster_count"] == 0
    assert payload["data"]["clusters"] == []


@pytest.mark.asyncio
async def test_get_triage_confusion_clusters_tool_rejects_non_positive_limit(triage_env):
    result = await server.get_triage_confusion_clusters(limit=0)
    payload = json.loads(result)

    assert payload["status"] == "error"
    assert payload["error"] == "limit must be >= 1"


@pytest.mark.asyncio
async def test_get_triage_confusion_clusters_tool_rejects_non_positive_lookback_days(triage_env):
    result = await server.get_triage_confusion_clusters(lookback_days=0)
    payload = json.loads(result)

    assert payload["status"] == "error"
    assert payload["error"] == "lookback_days must be >= 1"


@pytest.mark.asyncio
async def test_get_triage_confusion_clusters_forwards_filters_to_analysis_query(triage_env):
    pool, _qdrant = triage_env

    result = await server.get_triage_confusion_clusters(
        repository_key="repo-a",
        request_kind="run_operation",
        selected_workflow_name="deploy-workflow",
        selected_run_action="deploy",
        lookback_days=14,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    _query, args = next(
        (query, args)
        for query, args in reversed(pool.fetch_calls)
        if "/* triage_analysis_rows */" in query
    )
    assert args[0] == "repo-a"
    assert args[2] == "run_operation"
    assert args[3] == "deploy-workflow"
    assert args[4] == "deploy"
    assert args[5] == 14


@pytest.mark.asyncio
async def test_get_triage_confusion_clusters_orders_ties_by_corrected_request_kind(monkeypatch):
    class OrderedPool(TriagePool):
        async def fetch(self, query, *args):
            if "/* triage_analysis_rows */" in query:
                return [
                    {
                        "prompt_text": "Need feature work",
                        "request_kind": "task",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": True,
                        "created_utc": datetime(2026, 4, 12, tzinfo=timezone.utc),
                        "outcome_status": "corrected",
                        "corrected_request_kind": "feature",
                    },
                    {
                        "prompt_text": "Need bug help",
                        "request_kind": "task",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": True,
                        "created_utc": datetime(2026, 4, 12, tzinfo=timezone.utc),
                        "outcome_status": "corrected",
                        "corrected_request_kind": "bug",
                    },
                ]
            return await super().fetch(query, *args)

    pool = OrderedPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())

    result = await server.get_triage_confusion_clusters(repository_key="repo-a")
    payload = json.loads(result)

    assert payload["status"] == "success"
    corrected_kinds = [row["corrected_request_kind"] for row in payload["data"]["clusters"]]
    assert corrected_kinds == ["feature", "bug"]


@pytest.mark.asyncio
async def test_get_triage_clarification_recommendations_tool_success(triage_env):
    result = await server.get_triage_clarification_recommendations(repository_key="repo-a", limit=5, min_case_count=2)
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["analyzed_case_count"] == 4
    assert payload["data"]["recommendation_count"] == 1
    recommendation = payload["data"]["recommendations"][0]
    assert recommendation["request_kind"] == "task"
    assert recommendation["clarification_rate"] == 0.6667
    assert recommendation["sample_prompts"] == ["Need planning help urgently"]


@pytest.mark.asyncio
async def test_get_triage_clarification_recommendations_tool_rejects_non_positive_lookback_days(triage_env):
    result = await server.get_triage_clarification_recommendations(lookback_days=0)
    payload = json.loads(result)

    assert payload["status"] == "error"
    assert payload["error"] == "lookback_days must be >= 1"


@pytest.mark.asyncio
async def test_get_triage_clarification_recommendations_tool_empty_scope(monkeypatch):
    class EmptyPool(TriagePool):
        async def fetch(self, query, *args):
            if "/* triage_analysis_rows */" in query:
                return []
            return await super().fetch(query, *args)

    pool = EmptyPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())

    result = await server.get_triage_clarification_recommendations(repository_key="repo-a")
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["recommendation_count"] == 0
    assert payload["data"]["recommendations"] == []


@pytest.mark.asyncio
async def test_get_triage_clarification_recommendations_tool_rejects_non_positive_min_case_count(triage_env):
    result = await server.get_triage_clarification_recommendations(min_case_count=0)
    payload = json.loads(result)

    assert payload["status"] == "error"
    assert payload["error"] == "min_case_count must be >= 1"


@pytest.mark.asyncio
async def test_get_triage_clarification_recommendations_orders_ties_by_selected_run_action(monkeypatch):
    class OrderedPool(TriagePool):
        async def fetch(self, query, *args):
            if "/* triage_analysis_rows */" in query:
                return [
                    {
                        "prompt_text": "Run a deploy",
                        "request_kind": "run_operation",
                        "selected_workflow_name": "deploy-workflow",
                        "selected_run_action": "deploy",
                        "requires_clarification": True,
                        "created_utc": datetime(2026, 4, 12, tzinfo=timezone.utc),
                        "outcome_status": "insufficient_context",
                        "corrected_request_kind": None,
                    },
                    {
                        "prompt_text": "Run a rollback",
                        "request_kind": "run_operation",
                        "selected_workflow_name": "deploy-workflow",
                        "selected_run_action": "rollback",
                        "requires_clarification": True,
                        "created_utc": datetime(2026, 4, 12, tzinfo=timezone.utc),
                        "outcome_status": "insufficient_context",
                        "corrected_request_kind": None,
                    },
                ]
            return await super().fetch(query, *args)

    pool = OrderedPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())

    result = await server.get_triage_clarification_recommendations(
        repository_key="repo-a",
        request_kind="run_operation",
        min_case_count=1,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    run_actions = [row["selected_run_action"] for row in payload["data"]["recommendations"]]
    assert run_actions == ["rollback", "deploy"]


@pytest.mark.asyncio
async def test_get_triage_feedback_summary_problem_prompt_recency_uses_only_problem_rows(monkeypatch):
    class ProblemPromptPool(TriagePool):
        async def fetch(self, query, *args):
            if "FROM ops.triage_cases tc" in query and "corrected_request_kind" in query:
                return [
                    {
                        "prompt_text": "Prompt A",
                        "request_kind": "task",
                        "requires_clarification": False,
                        "created_utc": datetime(2026, 4, 10, tzinfo=timezone.utc),
                        "outcome_status": "corrected",
                        "corrected_request_kind": "feature",
                    },
                    {
                        "prompt_text": "Prompt A",
                        "request_kind": "task",
                        "requires_clarification": False,
                        "created_utc": datetime(2026, 4, 14, tzinfo=timezone.utc),
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    },
                    {
                        "prompt_text": "Prompt B",
                        "request_kind": "task",
                        "requires_clarification": False,
                        "created_utc": datetime(2026, 4, 11, tzinfo=timezone.utc),
                        "outcome_status": "corrected",
                        "corrected_request_kind": "feature",
                    },
                ]
            return await super().fetch(query, *args)

    pool = ProblemPromptPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())

    result = await server.get_triage_feedback_summary(repository_key="repo-a")
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["top_problem_prompts"][:2] == ["Prompt B", "Prompt A"]


@pytest.mark.asyncio
async def test_list_reference_values_returns_triage_outcome_domain(monkeypatch):
    class ReferencePool(TriagePool):
        async def fetchrow(self, query, *args):
            if "FROM core.reference_types WHERE internal_code = $1" in query:
                return {"id": 301} if args[0] == "TRIAGE_OUTCOME_STATUS" else None
            return await super().fetchrow(query, *args)

        async def fetch(self, query, *args):
            if "FROM core.reference_values rv" in query and "WHERE rv.reference_type_id = $1" in query:
                return [
                    {
                        "id": 301,
                        "internal_code": "TRIAGE_OUTCOME_PENDING",
                        "display_name": "Pending",
                        "description": None,
                        "sort_order": 10,
                        "is_active": True,
                        "is_terminal": False,
                    },
                    {
                        "id": 302,
                        "internal_code": "TRIAGE_OUTCOME_CORRECTED",
                        "display_name": "Corrected",
                        "description": None,
                        "sort_order": 50,
                        "is_active": True,
                        "is_terminal": True,
                    },
                ]
            return await super().fetch(query, *args)

    pool = ReferencePool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())

    result = await server.list_reference_values("TRIAGE_OUTCOME_STATUS")
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["count"] == 2
    assert payload["data"]["values"][0]["internal_code"] == "TRIAGE_OUTCOME_PENDING"


@pytest.mark.asyncio
async def test_reproject_triage_cases_uses_pg_created_utc_in_payload(monkeypatch):
    class ProjectionPool(TriagePool):
        async def fetch(self, query, *args):
            if "ORDER BY tc.created_utc, tc.id" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                        "repository_key": "repo-a",
                        "prompt_text": "Historic prompt",
                        "request_kind": "task",
                        "selected_workflow_name": "planning-workflow",
                        "project_key": "PAY",
                        "feature_key": "payments",
                        "policy_version": "v1",
                        "created_utc": datetime(2024, 1, 15, tzinfo=timezone.utc),
                    }
                ]
            return await super().fetch(query, *args)

    pool = ProjectionPool()
    qdrant = ReprojectableQdrant()
    monkeypatch.setattr("memory_knowledge.triage_memory.embed", lambda texts, settings: asyncio.sleep(0, result=[[0.3] * 8 for _ in texts]))

    result = await triage_memory.reproject_triage_cases(
        pool=pool,
        qdrant_client=qdrant,
        settings=SimpleNamespace(embedding_dimensions=8),
        repository_key="repo-a",
    )

    assert result["repaired"] == 1
    assert result["skipped"] == 0
    point = qdrant.upserts[0][1][0]
    assert point.payload["created_utc"] == "2024-01-15T00:00:00+00:00"


@pytest.mark.asyncio
async def test_search_triage_cases_restored_point_is_searchable_with_widened_max_age(monkeypatch):
    class SearchableProjectionPool(TriagePool):
        async def fetch(self, query, *args):
            self.fetch_calls.append((query, args))
            if "ORDER BY tc.created_utc, tc.id" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "repository_key": "repo-a",
                        "prompt_text": "Historic prompt",
                        "request_kind": "task",
                        "selected_workflow_name": "planning-workflow",
                        "project_key": "PAY",
                        "feature_key": "payments",
                        "policy_version": "v1",
                        "created_utc": datetime(2024, 1, 15, tzinfo=timezone.utc),
                    }
                ]
            if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                        "prompt_text": "Historic prompt",
                        "request_kind": "task",
                        "execution_mode": "autonomous_safe",
                        "knowledge_mode": "memory_knowledge",
                        "selected_workflow_name": "planning-workflow",
                        "selected_run_action": None,
                        "requires_clarification": False,
                        "confidence": 0.7,
                        "project_key": "PAY",
                        "feature_key": "payments",
                        "repository_key": "repo-a",
                        "policy_version": "v1",
                        "created_utc": datetime(2024, 1, 15, tzinfo=timezone.utc),
                        "outcome_status": "confirmed_correct",
                        "corrected_request_kind": None,
                    }
                ]
            return await super().fetch(query, *args)

    pool = SearchableProjectionPool()
    qdrant = ReprojectableQdrant()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace(embedding_dimensions=8))
    monkeypatch.setattr("memory_knowledge.triage_memory.embed", lambda texts, settings: asyncio.sleep(0, result=[[0.3] * 8 for _ in texts]))
    monkeypatch.setattr("memory_knowledge.triage_memory.embed_single", lambda text, settings: asyncio.sleep(0, result=[0.1] * 8))

    reprojection = await triage_memory.reproject_triage_cases(
        pool=pool,
        qdrant_client=qdrant,
        settings=SimpleNamespace(embedding_dimensions=8),
        repository_key="repo-a",
    )
    assert reprojection["repaired"] == 1

    result = await server.search_triage_cases(
        prompt_text="Historic prompt",
        repository_key="repo-a",
        max_age_days=800,
    )
    payload = json.loads(result)

    assert payload["status"] == "success"
    assert payload["data"]["rows"][0]["triage_case_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    _query, args = next(
        (query, args)
        for query, args in reversed(pool.fetch_calls)
        if "FROM ops.triage_cases tc" in query and "tc.execution_mode" in query
    )
    assert args[10] == 800


@pytest.mark.asyncio
async def test_reproject_triage_cases_counts_missing_embeddings_as_skipped(monkeypatch):
    class ProjectionPool(TriagePool):
        async def fetch(self, query, *args):
            if "ORDER BY tc.created_utc, tc.id" in query:
                return [
                    {
                        "triage_case_id": uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
                        "repository_key": "repo-a",
                        "prompt_text": "Prompt A",
                        "request_kind": "task",
                        "selected_workflow_name": "planning-workflow",
                        "project_key": "PAY",
                        "feature_key": "payments",
                        "policy_version": "v1",
                        "created_utc": datetime(2024, 1, 15, tzinfo=timezone.utc),
                    },
                    {
                        "triage_case_id": uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
                        "repository_key": "repo-a",
                        "prompt_text": "Prompt B",
                        "request_kind": "task",
                        "selected_workflow_name": "planning-workflow",
                        "project_key": "PAY",
                        "feature_key": "payments",
                        "policy_version": "v1",
                        "created_utc": datetime(2024, 1, 16, tzinfo=timezone.utc),
                    },
                ]
            return await super().fetch(query, *args)

    pool = ProjectionPool()
    qdrant = ReprojectableQdrant()
    monkeypatch.setattr("memory_knowledge.triage_memory.embed", lambda texts, settings: asyncio.sleep(0, result=[[0.3] * 8]))

    result = await triage_memory.reproject_triage_cases(
        pool=pool,
        qdrant_client=qdrant,
        settings=SimpleNamespace(embedding_dimensions=8),
        repository_key="repo-a",
    )

    assert result["repaired"] == 1
    assert result["skipped"] == 1
    assert "embedding missing" in result["errors"][0]
