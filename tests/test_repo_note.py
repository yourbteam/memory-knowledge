"""Tests for repo-scoped note authoring — S1: ensure_repo_root_entity; S2: run_author_note."""

import hashlib
import json as _json
import uuid as _uuid
from types import SimpleNamespace

import pytest

from memory_knowledge import server
from memory_knowledge.identity.entity_key import learned_record_entity_key, repository_root_entity_key
from memory_knowledge.workflows import repo_note
from memory_knowledge.workflows import retrieval as _retrieval
from memory_knowledge.workflows.base import WorkflowResult


class FakePool:
    """Pattern-matches the queries ensure_repo_root_entity issues."""

    def __init__(self, *, repo_id=1, revision_id=10, insert_returns_id=99, existing_id=99):
        self.repo_id = repo_id
        self.revision_id = revision_id
        self.insert_returns_id = insert_returns_id  # None simulates ON CONFLICT no-op
        self.existing_id = existing_id
        self.calls: list[str] = []

    async def fetchrow(self, query, *args):
        self.calls.append(query)
        if "FROM catalog.repositories WHERE repository_key" in query:
            return {"id": self.repo_id} if self.repo_id is not None else None
        if "FROM catalog.repo_revisions" in query:
            return {"id": self.revision_id} if self.revision_id is not None else None
        if "INSERT INTO catalog.entities" in query:
            return {"id": self.insert_returns_id} if self.insert_returns_id is not None else None
        if "SELECT id FROM catalog.entities WHERE entity_key" in query:
            return {"id": self.existing_id}
        raise AssertionError(f"unexpected query: {query}")


class FakeNeo4j:
    def __init__(self):
        self.queries: list[str] = []

    async def execute_query(self, query, **kw):
        self.queries.append(query)


@pytest.mark.asyncio
async def test_creates_root_entity_with_repository_type():
    pool, neo = FakePool(insert_returns_id=99), FakeNeo4j()
    ek, eid = await repo_note.ensure_repo_root_entity(pool, "taggable-server", neo4j_driver=neo)
    assert ek == str(repository_root_entity_key("taggable-server"))  # deterministic key
    assert eid == 99
    insert = next(q for q in pool.calls if "INSERT INTO catalog.entities" in q)
    assert "entity_type" in insert and "ON CONFLICT (entity_key) DO NOTHING" in insert
    assert any("MERGE (root:RepositoryRoot" in q for q in neo.queries)  # best-effort node


@pytest.mark.asyncio
async def test_idempotent_returns_existing_id_on_conflict():
    pool = FakePool(insert_returns_id=None, existing_id=42)  # conflict path
    ek, eid = await repo_note.ensure_repo_root_entity(pool, "fcsapi")
    assert eid == 42
    assert ek == str(repository_root_entity_key("fcsapi"))


@pytest.mark.asyncio
async def test_raises_when_repo_missing():
    with pytest.raises(ValueError, match="Repository not found"):
        await repo_note.ensure_repo_root_entity(FakePool(repo_id=None), "nope")


@pytest.mark.asyncio
async def test_raises_when_no_revision():
    with pytest.raises(ValueError, match="no ingested revision"):
        await repo_note.ensure_repo_root_entity(FakePool(revision_id=None), "taggable-api")


@pytest.mark.asyncio
async def test_neo4j_failure_is_best_effort():
    class BoomNeo4j:
        async def execute_query(self, *a, **k):
            raise RuntimeError("neo4j down")

    pool = FakePool()
    ek, eid = await repo_note.ensure_repo_root_entity(pool, "taggable-server", neo4j_driver=BoomNeo4j())
    assert eid == 99  # PG write still succeeds; Neo4j failure swallowed


# --- S2: run_author_note orchestration -----------------------------------------


class _RevPool:
    async def fetchrow(self, query, *args):
        assert "repo_revisions" in query
        return {"id": 10}


@pytest.mark.asyncio
async def test_run_author_note_human_asserted_evidence_free(monkeypatch):
    calls = {}

    async def fake_ensure(pool, repository_key, neo4j_driver=None):
        return ("rootkey-uuid", 7)

    async def fake_upsert(**kw):
        calls["upsert"] = kw
        return 55

    async def fake_embed(**kw):
        calls["embed"] = kw

    async def fake_project(**kw):
        calls["project"] = kw

    monkeypatch.setattr(repo_note, "ensure_repo_root_entity", fake_ensure)
    monkeypatch.setattr(repo_note, "upsert_learned_record", fake_upsert)
    monkeypatch.setattr(repo_note, "embed_and_upsert_learned_record", fake_embed)
    monkeypatch.setattr(repo_note, "project_learned_rule", fake_project)

    res = await repo_note.run_author_note(
        repository_key="taggable-server",
        title="React migration underway",
        body_text="Frontend migration to React is in progress.",
        run_id=_uuid.uuid4(),
        pool=_RevPool(),
        qdrant_client=object(),
        neo4j_driver=object(),
        settings=SimpleNamespace(),
    )
    assert res.status == "success"
    # human-asserted, evidence-free, scoped to the repo root
    up = calls["upsert"]
    assert up["source_kind"] == "operator_note"
    assert up["verification_status"] == "human_asserted"
    assert up["evidence_entity_id"] is None and up["evidence_chunk_id"] is None
    assert up["scope_entity_id"] == 7
    assert up["entity_key"] == learned_record_entity_key(
        "taggable-server", "note", hashlib.sha256(b"React migration underway").hexdigest()[:16]
    )
    # embedded into learned_memory with repo-scoped payload key
    assert calls["embed"]["repository_key"] == "taggable-server"
    assert calls["embed"]["scope_entity_key"] == "rootkey-uuid"
    # best-effort graph edge issued
    assert "project" in calls


@pytest.mark.asyncio
async def test_run_author_note_rejects_invalid_memory_type():
    res = await repo_note.run_author_note(
        repository_key="r", title="t", body_text="b", run_id=_uuid.uuid4(),
        memory_type="bogus", pool=_RevPool(), settings=SimpleNamespace(),
    )
    assert res.status == "error" and "Invalid memory_type" in res.error


@pytest.mark.asyncio
async def test_run_author_note_requires_title_body():
    res = await repo_note.run_author_note(
        repository_key="r", title="", body_text="b", run_id=_uuid.uuid4(),
        pool=_RevPool(), settings=SimpleNamespace(),
    )
    assert res.status == "error"


# --- S3: author_repo_note MCP tool wiring --------------------------------------


@pytest.fixture
def _server_env(monkeypatch):
    monkeypatch.setattr(server, "get_pg_pool", lambda: object())
    monkeypatch.setattr(server, "get_qdrant_client", lambda: object())
    monkeypatch.setattr(server, "get_neo4j_driver", lambda: object())
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())


@pytest.mark.asyncio
async def test_tool_author_repo_note_success(monkeypatch, _server_env):
    captured = {}

    async def fake(**kw):
        captured.update(kw)
        return WorkflowResult(run_id="r", tool_name="author_repo_note", status="success",
                              data={"entity_key": "ek", "repository_key": kw["repository_key"]})

    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    monkeypatch.setattr(server._repo_note, "run_author_note", fake)

    out = await server.author_repo_note(repository_key="taggable-server", title="t", body_text="b")
    data = _json.loads(out)
    assert data["status"] == "success"
    assert captured["repository_key"] == "taggable-server"
    assert captured["memory_type"] == "note"  # default
    # deps wired through
    assert "pool" in captured and "qdrant_client" in captured and "neo4j_driver" in captured


@pytest.mark.asyncio
async def test_tool_author_repo_note_blocked_by_guard(monkeypatch, _server_env):
    blocked = WorkflowResult(run_id="x", tool_name="author_repo_note", status="error",
                             error="ALLOW_REMOTE_WRITES not set")
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: blocked)
    called = {"n": 0}

    async def fake(**kw):
        called["n"] += 1
        return WorkflowResult(run_id="r", tool_name="author_repo_note", status="success")

    monkeypatch.setattr(server._repo_note, "run_author_note", fake)
    out = await server.author_repo_note(repository_key="r", title="t", body_text="b")
    assert _json.loads(out)["status"] == "error"
    assert called["n"] == 0  # guard short-circuits before the workflow runs


# --- S4: learned_memory retrieval search (repo isolation) ----------------------
class _FakeQdrantLM:
    def __init__(self):
        self.captured = {}

    async def query_points(self, **kw):
        self.captured = kw
        return SimpleNamespace(points=[SimpleNamespace(payload={"entity_key": "ek1"}, score=0.9)])


@pytest.mark.asyncio
async def test_learned_memory_search_is_repo_scoped():
    q = _FakeQdrantLM()
    hits = await _retrieval.qdrant_learned_memory_search(q, [0.1, 0.2], "taggable-server")
    assert q.captured["collection_name"] == "learned_memory"
    must = q.captured["query_filter"].must
    by_key = {c.key: c for c in must}
    assert "repository_key" in by_key and "is_active" in by_key  # isolation contract
    assert by_key["repository_key"].match.value == "taggable-server"  # repo X only
    assert hits[0]["entity_key"] == "ek1"


# --- 2a: candidate tier (verification_status) ----------------------------------
@pytest.mark.asyncio
async def test_run_author_note_candidate_tier(monkeypatch):
    cap = {}

    async def fake_ensure(pool, repository_key, neo4j_driver=None):
        return ("rk", 7)

    async def fake_upsert(**kw):
        cap["vs"] = kw["verification_status"]
        return 1

    async def noop(**kw):
        pass

    monkeypatch.setattr(repo_note, "ensure_repo_root_entity", fake_ensure)
    monkeypatch.setattr(repo_note, "upsert_learned_record", fake_upsert)
    monkeypatch.setattr(repo_note, "embed_and_upsert_learned_record", noop)
    monkeypatch.setattr(repo_note, "project_learned_rule", noop)

    # default = human_asserted
    r = await repo_note.run_author_note(repository_key="r", title="t", body_text="b",
                                        run_id=_uuid.uuid4(), pool=_RevPool(), settings=SimpleNamespace())
    assert r.status == "success" and cap["vs"] == "human_asserted"
    # auto-capture candidate = unverified
    r2 = await repo_note.run_author_note(repository_key="r", title="t", body_text="b",
                                         run_id=_uuid.uuid4(), verification_status="unverified",
                                         pool=_RevPool(), settings=SimpleNamespace())
    assert r2.status == "success" and cap["vs"] == "unverified"
    assert r2.data["verification_status"] == "unverified"  # response echoes the stored tier


@pytest.mark.asyncio
async def test_run_author_note_rejects_bad_verification_status():
    r = await repo_note.run_author_note(repository_key="r", title="t", body_text="b",
                                        run_id=_uuid.uuid4(), verification_status="bogus",
                                        pool=_RevPool(), settings=SimpleNamespace())
    assert r.status == "error" and "verification_status" in r.error


# --- run_deactivate_note (counterpart to run_author_note) ---

class FakeDeactivatePool:
    """Matches run_deactivate_note's lookup + the deactivate UPDATE."""

    def __init__(self, found=True, is_active=True):
        self.found = found
        self.is_active = is_active
        self.executed: list[tuple] = []

    async def fetchrow(self, query, *args):
        if "FROM memory.learned_records WHERE entity_key" in query:
            return {"id": 5, "is_active": self.is_active} if self.found else None
        raise AssertionError(f"unexpected query: {query}")

    async def execute(self, query, *args):
        self.executed.append((query, args))


class FakeQdrant:
    def __init__(self):
        self.set_payload_calls: list[dict] = []

    async def set_payload(self, **kw):
        self.set_payload_calls.append(kw)


@pytest.mark.asyncio
async def test_deactivate_note_deactivates_pg_and_qdrant():
    pool, q = FakeDeactivatePool(found=True), FakeQdrant()
    res = await repo_note.run_deactivate_note(
        repository_key="taggable-server", title="S5 verification note",
        run_id=_uuid.uuid4(), pool=pool, qdrant_client=q,
    )
    assert res.status == "success"
    assert any("SET is_active = FALSE" in qy for qy, _ in pool.executed)  # PG deactivated
    assert q.set_payload_calls and q.set_payload_calls[0]["payload"] == {"is_active": False}  # Qdrant deactivated
    expected = str(learned_record_entity_key(
        "taggable-server", "note", hashlib.sha256(b"S5 verification note").hexdigest()[:16]))
    assert res.data["entity_key"] == expected  # resolves the same key author used


@pytest.mark.asyncio
async def test_deactivate_note_errors_when_missing():
    res = await repo_note.run_deactivate_note(
        repository_key="x", title="does not exist", run_id=_uuid.uuid4(), pool=FakeDeactivatePool(found=False))
    assert res.status == "error" and "No repo note found" in res.error


@pytest.mark.asyncio
async def test_deactivate_note_requires_title():
    res = await repo_note.run_deactivate_note(
        repository_key="x", title="", run_id=_uuid.uuid4(), pool=FakeDeactivatePool())
    assert res.status == "error" and "title is required" in res.error
