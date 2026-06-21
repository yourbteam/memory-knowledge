"""B1 (cancel jobs) + B3 (register_repository NOT-NULL fix)."""

import json as _json
import uuid as _uuid
from types import SimpleNamespace

import pytest

from memory_knowledge import server
from memory_knowledge.jobs import manifest_writer
from memory_knowledge.jobs import manifest_reader
from memory_knowledge.jobs.state_transition_guard import InvalidStateTransition, validate_transition
from memory_knowledge.workflows.base import WorkflowResult


# --- B1: state transition guard ------------------------------------------------


def test_running_can_be_cancelled():
    assert validate_transition("running", "cancelled") is None
    assert validate_transition("retrying", "cancelled") is None
    assert validate_transition("pending", "cancelled") is None


def test_cancelled_is_terminal():
    for target in ("running", "completed", "failed", "retrying"):
        with pytest.raises(InvalidStateTransition):
            validate_transition("cancelled", target)


# --- B1: update_job_state no-ops on a cancelled job ----------------------------


class _StatePool:
    def __init__(self, current):
        self.current = current
        self.executed: list[str] = []

    async def fetchrow(self, query, *args):
        return {"state_code": self.current}

    async def execute(self, query, *args):
        self.executed.append(query)


@pytest.mark.asyncio
async def test_update_job_state_noop_when_already_cancelled():
    pool = _StatePool("cancelled")
    await manifest_writer.update_job_state(pool, _uuid.uuid4(), "failed")
    assert pool.executed == []  # terminal: never flipped to failed/completed


@pytest.mark.asyncio
async def test_update_job_state_cancel_stamps_completed():
    pool = _StatePool("running")
    await manifest_writer.update_job_state(pool, _uuid.uuid4(), "cancelled")
    assert any("completed_utc = NOW()" in q for q in pool.executed)  # cancelled is terminal-stamped


# --- B1: cancel_job MCP tool ---------------------------------------------------


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setattr(server, "get_pg_pool", lambda: object())
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)


@pytest.mark.asyncio
async def test_cancel_job_running_to_cancelled(monkeypatch, _env):
    async def fake_get(pool, jid):
        return {"job_id": str(jid), "state_code": "running"}

    updated = {}

    async def fake_update(pool, jid, state, **kw):
        updated["state"] = state

    monkeypatch.setattr(manifest_reader, "get_job_by_id", fake_get)
    monkeypatch.setattr(manifest_writer, "update_job_state", fake_update)

    out = _json.loads(await server.cancel_job(job_id=str(_uuid.uuid4())))
    assert out["status"] == "success"
    assert out["data"]["state_code"] == "cancelled" and updated["state"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_job_idempotent_on_terminal(monkeypatch, _env):
    async def fake_get(pool, jid):
        return {"job_id": str(jid), "state_code": "completed"}

    async def fake_update(pool, jid, state, **kw):  # must NOT be called
        raise AssertionError("update_job_state should not run on a terminal job")

    monkeypatch.setattr(manifest_reader, "get_job_by_id", fake_get)
    monkeypatch.setattr(manifest_writer, "update_job_state", fake_update)

    out = _json.loads(await server.cancel_job(job_id=str(_uuid.uuid4())))
    assert out["status"] == "success" and out["data"]["already_terminal"] is True


@pytest.mark.asyncio
async def test_cancel_job_race_to_terminal(monkeypatch, _env):
    async def fake_get(pool, jid):
        return {"job_id": str(jid), "state_code": "running"}

    async def fake_update(pool, jid, state, **kw):
        raise InvalidStateTransition("completed", "cancelled")  # raced to terminal

    monkeypatch.setattr(manifest_reader, "get_job_by_id", fake_get)
    monkeypatch.setattr(manifest_writer, "update_job_state", fake_update)

    out = _json.loads(await server.cancel_job(job_id=str(_uuid.uuid4())))
    assert out["status"] == "success" and out["data"]["already_terminal"] is True


@pytest.mark.asyncio
async def test_cancel_job_not_found(monkeypatch, _env):
    async def fake_get(pool, jid):
        return None

    monkeypatch.setattr(manifest_reader, "get_job_by_id", fake_get)
    out = _json.loads(await server.cancel_job(job_id=str(_uuid.uuid4())))
    assert out["status"] == "error" and "not found" in out["error"].lower()


@pytest.mark.asyncio
async def test_cancel_job_blocked_by_guard(monkeypatch, _env):
    blocked = WorkflowResult(run_id="x", tool_name="cancel_job", status="error",
                             error="ALLOW_REMOTE_WRITES not set")
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: blocked)
    out = _json.loads(await server.cancel_job(job_id=str(_uuid.uuid4())))
    assert out["status"] == "error"


# --- B3: register_repository supplies mawf_repository_id + status_id -----------


class _RegisterPool:
    def __init__(self):
        self.insert_query = None

    async def fetchrow(self, query, *args):
        self.insert_query = query
        return {"id": 123, "is_insert": True}


@pytest.mark.asyncio
async def test_register_repository_sets_notnull_columns(monkeypatch):
    pool = _RegisterPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)

    import memory_knowledge.admin.mawf as _mawf

    async def fake_ref(p, type_code, value_code):
        assert (type_code, value_code) == ("REPOSITORY_STATUS", "active")
        return 78

    monkeypatch.setattr(_mawf, "_reference_id", fake_ref)

    out = _json.loads(await server.register_repository(repository_key="taggable-database", name="taggable-database"))
    assert out["status"] == "success" and out["data"]["created"] is True
    assert "mawf_repository_id" in pool.insert_query and "status_id" in pool.insert_query
    assert "gen_random_uuid()" in pool.insert_query
