"""Unit tests for the Tier-2 corpus path (mirrors tests/test_qa_memory.py patterns).

All deps are faked, so these run without fastembed, a live DB, or a live Qdrant.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from memory_knowledge import server
from memory_knowledge.identity.entity_key import corpus_entry_key
from memory_knowledge.workflows import corpus


# --- Fakes ----------------------------------------------------------------------


class CorpusPool:
    """In-memory stand-in for asyncpg.Pool covering the corpus SQL surface."""

    def __init__(self):
        self.rows = {}  # entry_key(uuid) -> row dict
        self._next_id = 0

    async def fetchrow(self, query, *args):
        if "INSERT INTO memory.corpus_entries" in query:
            (entry_key, kind, title, body_text, tags, link_slug, confidence, is_active, supersedes_key) = args
            existing = self.rows.get(entry_key)
            rid = existing["id"] if existing else self._next_step()
            self.rows[entry_key] = {
                "id": rid,
                "entry_key": entry_key,
                "kind": kind,
                "title": title,
                "body_text": body_text,
                "tags": tags,
                "link_slug": link_slug,
                "confidence": confidence,
                "is_active": is_active,
                "supersedes_key": supersedes_key,
            }
            return {"id": rid}
        return None

    def _next_step(self):
        self._next_id += 1
        return self._next_id

    async def execute(self, query, *args):
        if "UPDATE memory.corpus_entries SET is_active = FALSE" in query:
            row = self.rows.get(args[0])
            if row:
                row["is_active"] = False
                return "UPDATE 1"
            return "UPDATE 0"
        return "UPDATE 0"

    async def fetch(self, query, *args):
        if "WHERE entry_key = ANY" in query:
            ids = set(args[0])
            return [
                {"entry_key": v["entry_key"], "title": v["title"], "body_text": v["body_text"]}
                for v in self.rows.values()
                if v["entry_key"] in ids and v["is_active"]
            ]
        return []


class FakeQdrant:
    """Stores upserts; returns them as query hits with their payloads."""

    def __init__(self):
        self.points = {}  # id -> payload
        self.query_calls = []

    async def upsert(self, collection_name, points):
        for p in points:
            self.points[str(p.id)] = dict(p.payload)

    async def set_payload(self, collection_name, payload, points):
        for pid in points:
            if str(pid) not in self.points:
                raise KeyError(f"point {pid} not found")  # mirror real Qdrant 404 on missing point
            self.points[str(pid)].update(payload)

    async def query_points(self, **kwargs):
        self.query_calls.append(kwargs)
        pts = [SimpleNamespace(id=pid, score=0.9, payload=pl) for pid, pl in self.points.items()]
        return SimpleNamespace(points=pts)


def _embed(text, settings):
    return asyncio.sleep(0, result=[0.1] * 8)


SETTINGS = SimpleNamespace(embedding_dimensions=8)


@pytest.fixture
def patch_embed(monkeypatch):
    monkeypatch.setattr("memory_knowledge.workflows.corpus.embed_single", _embed)
    monkeypatch.setattr("memory_knowledge.projections.corpus_qdrant.embed_single", _embed)


# --- entry_key (pure unit) ------------------------------------------------------


def test_entry_key_deterministic():
    assert corpus_entry_key("reference", "g2", "Title") == corpus_entry_key("reference", "g2", "Title")


def test_entry_key_unique_by_field():
    base = corpus_entry_key("reference", "g2", "Title")
    assert base != corpus_entry_key("example", "g2", "Title")
    assert base != corpus_entry_key("reference", "g3", "Title")
    assert base != corpus_entry_key("reference", "g2", "Other")
    assert base.version == 5


# --- run_upsert -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_writes_pg_and_qdrant(patch_embed):
    pool, q = CorpusPool(), FakeQdrant()
    res = await corpus.run_upsert(
        kind="reference",
        title="confirm word",
        body_text="lock it",
        tags=["g0"],
        link_slug="g0",
        confidence=0.9,
        run_id=uuid.uuid4(),
        pool=pool,
        qdrant_client=q,
        settings=SETTINGS,
    )
    assert res.status == "success"
    ek = corpus_entry_key("reference", "g0", "confirm word")
    assert pool.rows[ek]["is_active"] is True
    assert str(ek) in q.points
    assert q.points[str(ek)]["kind"] == "reference"


@pytest.mark.asyncio
async def test_upsert_rejects_invalid_kind(patch_embed):
    pool, q = CorpusPool(), FakeQdrant()
    res = await corpus.run_upsert(
        kind="bogus", title="t", body_text="b", run_id=uuid.uuid4(), pool=pool, qdrant_client=q, settings=SETTINGS
    )
    assert res.status == "error"
    assert "Invalid kind" in res.error
    assert pool.rows == {} and q.points == {}


@pytest.mark.asyncio
async def test_upsert_requires_title_and_body(patch_embed):
    pool, q = CorpusPool(), FakeQdrant()
    res = await corpus.run_upsert(
        kind="reference", title="", body_text="b", run_id=uuid.uuid4(), pool=pool, qdrant_client=q, settings=SETTINGS
    )
    assert res.status == "error"
    assert pool.rows == {}


@pytest.mark.asyncio
async def test_upsert_is_idempotent(patch_embed):
    pool, q = CorpusPool(), FakeQdrant()
    args = dict(kind="reference", title="t", body_text="b", link_slug="g0", settings=SETTINGS)
    r1 = await corpus.run_upsert(**args, run_id=uuid.uuid4(), pool=pool, qdrant_client=q)
    r2 = await corpus.run_upsert(**args, run_id=uuid.uuid4(), pool=pool, qdrant_client=q)
    assert r1.data["corpus_entry_id"] == r2.data["corpus_entry_id"]
    assert len(pool.rows) == 1


@pytest.mark.asyncio
async def test_supersede_deactivates_old(patch_embed):
    pool, q = CorpusPool(), FakeQdrant()
    old = await corpus.run_upsert(
        kind="reference",
        title="old",
        body_text="b",
        link_slug="g0",
        run_id=uuid.uuid4(),
        pool=pool,
        qdrant_client=q,
        settings=SETTINGS,
    )
    old_key = old.data["entry_key"]
    new = await corpus.run_upsert(
        kind="reference",
        title="new",
        body_text="b2",
        link_slug="g0",
        supersedes_id=old_key,
        run_id=uuid.uuid4(),
        pool=pool,
        qdrant_client=q,
        settings=SETTINGS,
    )
    assert new.status == "success"
    assert pool.rows[uuid.UUID(old_key)]["is_active"] is False  # PG old deactivated
    assert q.points[old_key]["is_active"] is False  # Qdrant old deactivated
    new_key = new.data["entry_key"]
    assert pool.rows[uuid.UUID(new_key)]["supersedes_key"] == uuid.UUID(old_key)


# --- run_deactivate -------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_sets_inactive_pg_and_qdrant(patch_embed):
    pool, q = CorpusPool(), FakeQdrant()
    await corpus.run_upsert(
        kind="directive_rationale",
        title="G5 · Ask one at a time",
        body_text="b",
        link_slug="g5",
        run_id=uuid.uuid4(),
        pool=pool,
        qdrant_client=q,
        settings=SETTINGS,
    )
    ek = corpus_entry_key("directive_rationale", "g5", "G5 · Ask one at a time")
    assert pool.rows[ek]["is_active"] is True
    res = await corpus.run_deactivate(
        kind="directive_rationale",
        title="G5 · Ask one at a time",
        link_slug="g5",
        run_id=uuid.uuid4(),
        pool=pool,
        qdrant_client=q,
    )
    assert res.status == "success"
    assert res.data["entry_key"] == str(ek)
    assert pool.rows[ek]["is_active"] is False  # PG deactivated
    assert q.points[str(ek)]["is_active"] is False  # Qdrant deactivated


@pytest.mark.asyncio
async def test_deactivate_idempotent_when_missing(patch_embed):
    # Deactivating an entry that was never written is a no-op success (sync re-run safety).
    pool, q = CorpusPool(), FakeQdrant()
    res = await corpus.run_deactivate(
        kind="directive_rationale",
        title="never existed",
        link_slug="g9",
        run_id=uuid.uuid4(),
        pool=pool,
        qdrant_client=q,
    )
    assert res.status == "success"
    assert pool.rows == {}


@pytest.mark.asyncio
async def test_deactivate_rejects_invalid_kind(patch_embed):
    pool, q = CorpusPool(), FakeQdrant()
    res = await corpus.run_deactivate(
        kind="bogus", title="t", link_slug="g0", run_id=uuid.uuid4(), pool=pool, qdrant_client=q
    )
    assert res.status == "error"
    assert "Invalid kind" in res.error


# --- run_query ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_filters_is_active_and_hydrates(patch_embed):
    pool, q = CorpusPool(), FakeQdrant()
    await corpus.run_upsert(
        kind="reference",
        title="hit",
        body_text="body",
        link_slug="g0",
        run_id=uuid.uuid4(),
        pool=pool,
        qdrant_client=q,
        settings=SETTINGS,
    )
    res = await corpus.run_query(
        query_text="anything",
        kind="reference",
        link_slug="g0",
        limit=5,
        run_id=uuid.uuid4(),
        pool=pool,
        qdrant_client=q,
        settings=SETTINGS,
    )
    assert res.status == "success"
    # the query carried an is_active=true filter plus kind + link_slug conditions
    flt = q.query_calls[0]["query_filter"]
    keys = {c.key for c in flt.must}
    assert {"is_active", "kind", "link_slug"} <= keys
    # results are hydrated from PG
    assert res.data["results"][0]["title"] == "hit"
    assert res.data["results"][0]["body_text"] == "body"


@pytest.mark.asyncio
async def test_query_requires_text(patch_embed):
    res = await corpus.run_query(
        query_text="", run_id=uuid.uuid4(), pool=CorpusPool(), qdrant_client=FakeQdrant(), settings=SETTINGS
    )
    assert res.status == "error"


# --- MCP tools (server wiring) --------------------------------------------------


@pytest.fixture
def corpus_env(monkeypatch):
    pool, q = CorpusPool(), FakeQdrant()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_qdrant_client", lambda: q)
    monkeypatch.setattr(server, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    monkeypatch.setattr("memory_knowledge.workflows.corpus.embed_single", _embed)
    monkeypatch.setattr("memory_knowledge.projections.corpus_qdrant.embed_single", _embed)
    return pool, q


@pytest.mark.asyncio
async def test_tool_upsert_success(corpus_env):
    import json

    out = await server.run_corpus_upsert_workflow(kind="reference", title="t", body_text="b", link_slug="g0")
    assert json.loads(out)["status"] == "success"


@pytest.mark.asyncio
async def test_tool_upsert_blocked_by_guard(monkeypatch, corpus_env):
    import json
    from memory_knowledge.workflows.base import WorkflowResult

    blocked = WorkflowResult(
        run_id="x", tool_name="run_corpus_upsert_workflow", status="error", error="ALLOW_REMOTE_WRITES not set"
    )
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: blocked)
    pool, q = corpus_env
    out = await server.run_corpus_upsert_workflow(kind="reference", title="t", body_text="b")
    assert json.loads(out)["status"] == "error"
    assert pool.rows == {}  # guard blocked before any write


@pytest.mark.asyncio
async def test_tool_deactivate_success(corpus_env):
    import json

    pool, q = corpus_env
    await server.run_corpus_upsert_workflow(
        kind="directive_rationale", title="G5 · t", body_text="b", link_slug="g5"
    )
    out = await server.corpus_deactivate(kind="directive_rationale", title="G5 · t", link_slug="g5")
    assert json.loads(out)["status"] == "success"
    ek = corpus_entry_key("directive_rationale", "g5", "G5 · t")
    assert pool.rows[ek]["is_active"] is False


@pytest.mark.asyncio
async def test_tool_deactivate_blocked_by_guard(monkeypatch, corpus_env):
    import json
    from memory_knowledge.workflows.base import WorkflowResult

    pool, q = corpus_env
    await server.run_corpus_upsert_workflow(
        kind="directive_rationale", title="G5 · t", body_text="b", link_slug="g5"
    )
    blocked = WorkflowResult(run_id="x", tool_name="corpus_deactivate", status="error", error="ALLOW_REMOTE_WRITES not set")
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: blocked)
    out = await server.corpus_deactivate(kind="directive_rationale", title="G5 · t", link_slug="g5")
    assert json.loads(out)["status"] == "error"
    ek = corpus_entry_key("directive_rationale", "g5", "G5 · t")
    assert pool.rows[ek]["is_active"] is True  # guard blocked before any write


@pytest.mark.asyncio
async def test_tool_query_success(corpus_env):
    import json

    await server.run_corpus_upsert_workflow(kind="reference", title="t", body_text="b", link_slug="g0")
    out = await server.corpus_query(query_text="anything", link_slug="g0")
    assert json.loads(out)["status"] == "success"
