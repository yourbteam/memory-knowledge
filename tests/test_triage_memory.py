import json
import uuid
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from memory_knowledge import server


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


class TriagePool:
    def __init__(self):
        self.fetchrow_calls = []
        self.fetch_calls = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "SELECT id FROM catalog.repositories WHERE repository_key = $1" in query:
            return {"id": 7} if args[0] == "repo-a" else None
        if "INSERT INTO ops.triage_cases" in query:
            return {"triage_case_id": uuid.UUID(str(args[0]))}
        if "SELECT triage_case_id FROM ops.triage_cases" in query:
            return {"triage_case_id": uuid.UUID(args[0])} if args[0] == "11111111-1111-1111-1111-111111111111" else None
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
