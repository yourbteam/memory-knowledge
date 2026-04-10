import json
import uuid
from types import SimpleNamespace

import pytest

from memory_knowledge import server
from memory_knowledge.admin import findings
from memory_knowledge.jobs import job_worker


class FindingsPool:
    def __init__(self):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.fetch_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "FROM catalog.repositories WHERE repository_key = $1" in query:
            return {"id": 7}
        if "FROM ops.workflow_runs wr" in query and "WHERE wr.run_id = $1" in query:
            return {
                "id": 11,
                "repository_id": 7,
                "workflow_name": "wf-a",
            }
        if "FROM core.reference_values rv" in query and "WHERE rt.internal_code = $1 AND rv.internal_code = $2" in query:
            type_code, value_code = args
            if type_code == server.WORKFLOW_FINDING_KIND_TYPE:
                return {"id": 21, "internal_code": value_code, "display_name": value_code.title(), "is_terminal": False}
            if type_code == server.WORKFLOW_FINDING_STATUS_TYPE:
                return {"id": 22, "internal_code": value_code, "display_name": value_code.title(), "is_terminal": value_code != "OPEN"}
            if type_code == server.WORKFLOW_FINDING_DECISION_BUCKET_TYPE:
                return {"id": 23, "internal_code": value_code, "display_name": value_code.title(), "is_terminal": False}
            if type_code == server.WORKFLOW_FINDING_SUPPRESSION_SCOPE_TYPE:
                return {"id": 24, "internal_code": value_code, "display_name": value_code.title(), "is_terminal": False}
            return None
        if "INSERT INTO ops.workflow_findings" in query:
            return {
                "id": 101,
                "phase_id": args[3],
                "attempt_number": args[5],
                "finding_fingerprint": args[9],
            }
        if "INSERT INTO ops.workflow_finding_decisions" in query:
            return {"id": 202, "workflow_finding_id": args[2]}
        return None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        if "FROM ops.workflow_findings" in query and "ORDER BY id ASC" in query:
            phase_filter = args[3]
            if phase_filter:
                return [{"id": 99, "phase_id": phase_filter}]
            return [{"id": 99, "phase_id": "review"}]
        return []


@pytest.fixture
def findings_pool(monkeypatch):
    pool = FindingsPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name, is_destructive=False: None)
    return pool


@pytest.mark.asyncio
async def test_save_workflow_finding_defaults_kind_and_status(findings_pool):
    result = await server.save_workflow_finding(
        repository_key="repo-a",
        run_id=str(uuid.uuid4()),
        workflow_name="wf-a",
        phase_id="review",
        agent_name="verifier",
        attempt_number=1,
        finding_fingerprint="fp-1",
        finding_title="Title",
        finding_message="Message",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    reference_calls = [
        args for query, args in findings_pool.fetchrow_calls
        if "FROM core.reference_values rv" in query
    ]
    assert (server.WORKFLOW_FINDING_KIND_TYPE, server.DEFAULT_WORKFLOW_FINDING_KIND) in reference_calls
    assert (server.WORKFLOW_FINDING_STATUS_TYPE, server.DEFAULT_WORKFLOW_FINDING_STATUS) in reference_calls


@pytest.mark.asyncio
async def test_save_workflow_finding_rejects_workflow_name_mismatch(findings_pool):
    result = await server.save_workflow_finding(
        repository_key="repo-a",
        run_id=str(uuid.uuid4()),
        workflow_name="wf-other",
        phase_id="review",
        agent_name="verifier",
        attempt_number=1,
        finding_fingerprint="fp-1",
        finding_title="Title",
        finding_message="Message",
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "workflow_name does not match" in payload["error"]


@pytest.mark.asyncio
async def test_save_workflow_finding_decision_rejects_duplicate(monkeypatch, findings_pool):
    async def fake_save_decision(*args, **kwargs):
        return None

    monkeypatch.setattr(server._findings, "save_workflow_finding_decision", fake_save_decision)
    result = await server.save_workflow_finding_decision(
        repository_key="repo-a",
        run_id=str(uuid.uuid4()),
        workflow_name="wf-a",
        critic_phase_id="critic",
        critic_agent_name="critic-1",
        attempt_number=1,
        finding_fingerprint="fp-1",
        decision_bucket_code="DISMISS",
        actionable=False,
        suppress_on_rerun=True,
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "Duplicate workflow finding decision" in payload["error"]


@pytest.mark.asyncio
async def test_list_workflow_finding_suppressions_returns_payload_under_data(monkeypatch, findings_pool):
    async def fake_list(*args, **kwargs):
        return {
            "items": [{"finding_fingerprint": "fp-1", "decision_bucket": "DISMISS"}],
            "ordering": ["created_utc DESC", "finding_fingerprint ASC"],
            "filters": {"phase_id": "review"},
            "count": 1,
        }

    monkeypatch.setattr(server._findings, "list_workflow_finding_suppressions", fake_list)
    result = await server.list_workflow_finding_suppressions(
        repository_key="repo-a",
        run_id=str(uuid.uuid4()),
        workflow_name="wf-a",
        phase_id="review",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["items"][0]["finding_fingerprint"] == "fp-1"


@pytest.mark.asyncio
async def test_get_finding_pattern_summary_returns_empty_summary():
    class Pool:
        async def fetch(self, query, *args):
            return []

    data = await findings.get_finding_pattern_summary(Pool(), repository_key="repo-a")
    assert data["summary"] == []
    assert data["eligible_run_count"] == 0
    assert data["excluded_run_count"] == 0


@pytest.mark.asyncio
async def test_get_agent_failure_mode_summary_returns_empty_summary():
    class Pool:
        async def fetch(self, query, *args):
            return []

    data = await findings.get_agent_failure_mode_summary(Pool(), repository_key="repo-a")
    assert data["summary"] == []
    assert data["eligible_run_count"] == 0
    assert data["excluded_run_count"] == 0


@pytest.mark.asyncio
async def test_run_ingestion_background_uses_manifest_job_id_only(monkeypatch):
    captured = {}

    async def fake_execute_job(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(job_worker, "execute_job", fake_execute_job)
    monkeypatch.setattr(server, "get_pg_pool", lambda: object())
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "get_qdrant_client", lambda: object())
    monkeypatch.setattr(server, "get_neo4j_driver", lambda: object())

    await server._run_ingestion_background(uuid.uuid4(), uuid.uuid4(), "repo-a", "abc", "main")

    assert "job_id" not in captured
    assert "manifest_job_id" in captured


@pytest.mark.asyncio
async def test_list_workflow_finding_suppressions_picks_latest_decision_before_filtering():
    class Pool:
        def __init__(self):
            self.query = ""

        async def fetch(self, query, *args):
            self.query = query
            return []

    pool = Pool()
    await findings.list_workflow_finding_suppressions(
        pool,
        repository_id=1,
        workflow_run_id=2,
        workflow_name="wf-a",
        phase_id="review",
        artifact_name=None,
        artifact_iteration=None,
        artifact_hash=None,
        limit=10,
    )
    assert "wfd.suppress_on_rerun = TRUE" not in pool.query
    assert "ld.suppress_on_rerun = TRUE" in pool.query


@pytest.mark.asyncio
async def test_save_workflow_finding_decision_dedupes_without_created_utc_in_conflict_target():
    class Pool:
        def __init__(self):
            self.query = ""

        async def fetchrow(self, query, *args):
            self.query = query
            return {"id": 1, "workflow_finding_id": 99}

    pool = Pool()
    await findings.save_workflow_finding_decision(
        pool,
        repository_id=1,
        workflow_run_id=2,
        workflow_finding_id=99,
        workflow_name="wf-a",
        critic_phase_id="critic",
        critic_agent_name="critic-1",
        attempt_number=1,
        finding_fingerprint="fp-1",
        decision_bucket_id=3,
        actionable=False,
        reason_text=None,
        evidence_text=None,
        suppression_scope_id=4,
        suppress_on_rerun=True,
        artifact_name=None,
        artifact_iteration=None,
        artifact_hash=None,
        actor_email=None,
        context_json=None,
        created_utc=None,
    )
    assert "decision_bucket_id, created_utc\n        ) DO NOTHING" not in pool.query
    assert "decision_bucket_id\n        ) DO NOTHING" in pool.query
