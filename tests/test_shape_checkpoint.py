"""A4: offline/manual runs (no job_id) checkpoint by (repo, commit, branch)."""

import json
import uuid

import pytest

from memory_knowledge.jobs.job_checkpoint_manager import (
    clear_shape_checkpoint,
    load_shape_checkpoint,
    save_shape_checkpoint,
)
from memory_knowledge.workflows import ingestion as ing


class _FakePool:
    def __init__(self, load_row=None):
        self.execute_calls: list[tuple] = []
        self.load_row = load_row

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))

    async def fetchrow(self, query, *args):
        return self.load_row


@pytest.mark.asyncio
async def test_save_shape_checkpoint_upserts():
    pool = _FakePool()
    await save_shape_checkpoint(pool, 1, "abc", "main", {"phase": "x"})
    query, args = pool.execute_calls[0]
    assert "ops.ingestion_checkpoints" in query and "ON CONFLICT" in query
    assert args[:3] == (1, "abc", "main")
    assert json.loads(args[3]) == {"phase": "x"}


@pytest.mark.asyncio
async def test_load_shape_checkpoint_parses_and_absent():
    pool = _FakePool(load_row={"checkpoint_data": json.dumps({"phase": "y"})})
    assert await load_shape_checkpoint(pool, 1, "abc", "main") == {"phase": "y"}
    assert await load_shape_checkpoint(_FakePool(load_row=None), 1, "abc", "main") is None


@pytest.mark.asyncio
async def test_clear_shape_checkpoint_deletes():
    pool = _FakePool()
    await clear_shape_checkpoint(pool, 1, "abc", "main")
    query, args = pool.execute_calls[0]
    assert "DELETE FROM ops.ingestion_checkpoints" in query
    assert args == (1, "abc", "main")


def _spies(monkeypatch):
    calls = {"manifest": 0, "shape": 0}

    async def fake_save_checkpoint(pool, job_id, data):
        calls["manifest"] += 1

    async def fake_save_shape(pool, repo_id, commit, branch, data):
        calls["shape"] += 1

    monkeypatch.setattr(ing, "save_checkpoint", fake_save_checkpoint)
    monkeypatch.setattr(ing, "save_shape_checkpoint", fake_save_shape)
    return calls


@pytest.mark.asyncio
async def test_routes_to_manifest_when_job_id_present(monkeypatch):
    calls = _spies(monkeypatch)
    # _FakePool with load_row=None → _is_cancelled (B1 chokepoint) reads a non-cancelled state.
    await ing._save_ingestion_checkpoint(_FakePool(), uuid.uuid4(), {}, phase="p", shape=(1, "c", "b"))
    assert calls == {"manifest": 1, "shape": 0}  # dispatcher path unchanged


@pytest.mark.asyncio
async def test_chokepoint_raises_when_cancelled(monkeypatch):
    # B1 cooperative abort: a cancelled manifest makes the checkpoint raise JobCancelled.
    _spies(monkeypatch)
    pool = _FakePool(load_row={"state_code": "cancelled"})
    with pytest.raises(ing.JobCancelled):
        await ing._save_ingestion_checkpoint(pool, uuid.uuid4(), {}, phase="p", shape=(1, "c", "b"))


@pytest.mark.asyncio
async def test_routes_to_shape_when_no_job_id(monkeypatch):
    calls = _spies(monkeypatch)
    await ing._save_ingestion_checkpoint(object(), None, {}, phase="p", shape=(1, "c", "b"))
    assert calls == {"manifest": 0, "shape": 1}


@pytest.mark.asyncio
async def test_noop_when_no_job_id_and_no_shape(monkeypatch):
    calls = _spies(monkeypatch)
    await ing._save_ingestion_checkpoint(object(), None, {}, phase="p", shape=None)
    assert calls == {"manifest": 0, "shape": 0}
