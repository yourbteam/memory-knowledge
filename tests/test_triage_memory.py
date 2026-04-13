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
            }
        if "SELECT triage_case_id FROM ops.triage_cases" in query:
            return {"triage_case_id": uuid.UUID(args[0])} if args[0] == "11111111-1111-1111-1111-111111111111" else None
        if "FROM core.reference_values rv" in query and "WHERE rt.internal_code = $1 AND rv.internal_code = $2" in query:
            type_code, value_code = args
            if type_code == "TRIAGE_OUTCOME_STATUS" and value_code == "TRIAGE_OUTCOME_CORRECTED":
                return {"id": 201}
            if type_code == "TRIAGE_OUTCOME_STATUS" and value_code == "TRIAGE_OUTCOME_CONFIRMED_CORRECT":
                return {"id": 202}
            return None
        if "INSERT INTO ops.triage_case_feedback" in query:
            return {"id": 1}
        return None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
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
