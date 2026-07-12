"""Tests for repo-scoped note authoring — anchor (A2), authoring, deactivation, A1 canonicalization."""

import hashlib
import json as _json
import uuid as _uuid
from types import SimpleNamespace

import pytest

from memory_knowledge import server
from memory_knowledge.identity.entity_key import learned_record_entity_key, repository_root_entity_key
from memory_knowledge.workflows import repo_note
from memory_knowledge.workflows.learned_memory import validate_operational_content
from memory_knowledge.workflows import retrieval as _retrieval
from memory_knowledge.workflows.base import WorkflowResult


class _AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _AsyncContextWithHooks:
    def __init__(self, enter, exit):
        self.enter, self.exit = enter, exit

    async def __aenter__(self):
        self.enter()

    async def __aexit__(self, exc_type, exc, tb):
        self.exit()
        return False


@pytest.mark.parametrize("body", [
    "Kamen prefers tea",
    "Bearer%20abcdefghijklmnopqrstuvwxyz",
])
def test_operator_note_validator_rejects_personal_and_encoded_secret(body):
    with pytest.raises(ValueError, match="prohibited"):
        validate_operational_content(
            title="Repository observation", body_text=body,
            content_kind="repository-fact",
            evidence_refs=[{"kind": "revision", "repository_key": "repo",
                            "revision_commit": "a" * 40}],
        )


class FakePool:
    """Pattern-matches the queries ensure_repo_root_entity / run_author_note issue.

    `repo_id=None` → repo not found (resolve returns []). `revision_id=None` → no existing
    revision (exercises the A2 auto-create path). `canonical_key` is what the resolve returns
    as the stored key (A1).
    """

    def __init__(self, *, repo_id=1, canonical_key="taggable-server", revision_id=10,
                 insert_returns_id=99, existing_id=99):
        self.repo_id = repo_id
        self.canonical_key = canonical_key
        self.revision_id = revision_id
        self.insert_returns_id = insert_returns_id
        self.existing_id = existing_id
        self.calls: list[str] = []
        self.created_revision: dict | None = None  # captures A2 synthetic revision args

    def acquire(self):
        return _AsyncContext(self)

    def transaction(self):
        return _AsyncContext()

    async def fetch(self, query, *args):
        self.calls.append(query)
        if "lower(repository_key) = lower($1)" in query:  # A1 _resolve_repository
            if self.repo_id is None:
                return []
            return [{"id": self.repo_id, "repository_key": self.canonical_key}]
        raise AssertionError(f"unexpected fetch: {query}")

    async def fetchrow(self, query, *args):
        self.calls.append(query)
        if "INSERT INTO catalog.repo_revisions" in query:  # A2 upsert_repo_revision
            self.created_revision = {"commit_sha": args[1], "branch_name": args[2]}
            return {"id": 777}
        if "SELECT id FROM catalog.repo_revisions" in query:
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


# --- A1 + anchor: ensure_repo_root_entity --------------------------------------


@pytest.mark.asyncio
async def test_creates_root_entity_with_repository_type():
    pool, neo = FakePool(insert_returns_id=99), FakeNeo4j()
    ek, eid, canon = await repo_note.ensure_repo_root_entity(pool, "taggable-server", neo4j_driver=neo)
    assert ek == str(repository_root_entity_key("taggable-server"))  # deterministic key
    assert eid == 99 and canon == "taggable-server"
    insert = next(q for q in pool.calls if "INSERT INTO catalog.entities" in q)
    assert "entity_type" in insert and "ON CONFLICT (entity_key) DO NOTHING" in insert
    assert any("MERGE (root:RepositoryRoot" in q for q in neo.queries)  # best-effort node


@pytest.mark.asyncio
async def test_idempotent_returns_existing_id_on_conflict():
    pool = FakePool(canonical_key="fcsapi", insert_returns_id=None, existing_id=42)  # conflict path
    ek, eid, canon = await repo_note.ensure_repo_root_entity(pool, "fcsapi")
    assert eid == 42 and canon == "fcsapi"
    assert ek == str(repository_root_entity_key("fcsapi"))


@pytest.mark.asyncio
async def test_resolves_repo_key_case_insensitively():
    # A1: given "FCSAPI" resolves to the stored canonical "fcsapi" and keys off the canonical.
    pool = FakePool(canonical_key="fcsapi")
    ek, eid, canon = await repo_note.ensure_repo_root_entity(pool, "FCSAPI")
    assert canon == "fcsapi"
    assert ek == str(repository_root_entity_key("fcsapi"))  # canonical, not "FCSAPI"


@pytest.mark.asyncio
async def test_raises_when_repo_missing():
    with pytest.raises(ValueError, match="Repository not found"):
        await repo_note.ensure_repo_root_entity(FakePool(repo_id=None), "nope")


@pytest.mark.asyncio
async def test_auto_creates_note_anchor_revision_when_none(monkeypatch):
    # A2 keystone: a registered-but-never-ingested repo gets a synthetic note-anchor revision.
    pool = FakePool(revision_id=None)
    ek, eid, canon = await repo_note.ensure_repo_root_entity(pool, "taggable-server")
    assert eid == 99
    assert pool.created_revision == {"commit_sha": "__note_anchor__", "branch_name": "__notes__"}


@pytest.mark.asyncio
async def test_strict_mode_still_raises_without_revision():
    # auto_create_revision=False preserves the old strict behavior.
    with pytest.raises(ValueError, match="no ingested revision"):
        await repo_note.ensure_repo_root_entity(
            FakePool(revision_id=None, canonical_key="taggable-api"), "taggable-api",
            auto_create_revision=False,
        )


@pytest.mark.asyncio
async def test_no_source_embedded_by_anchor(monkeypatch):
    # A2: the anchor path creates ONLY a repo_revisions row + the root entity — no files/chunks.
    pool = FakePool(revision_id=None)
    await repo_note.ensure_repo_root_entity(pool, "taggable-server")
    assert not any("catalog.files" in q or "catalog.chunks" in q for q in pool.calls)


@pytest.mark.asyncio
async def test_neo4j_failure_is_best_effort():
    class BoomNeo4j:
        async def execute_query(self, *a, **k):
            raise RuntimeError("neo4j down")

    pool = FakePool()
    ek, eid, canon = await repo_note.ensure_repo_root_entity(pool, "taggable-server", neo4j_driver=BoomNeo4j())
    assert eid == 99  # PG write still succeeds; Neo4j failure swallowed


# --- run_author_note orchestration ---------------------------------------------


class _RevPool:
    def acquire(self):
        return _AsyncContext(self)

    def transaction(self):
        return _AsyncContext()

    async def fetchrow(self, query, *args):
        assert "repo_revisions" in query
        return {"id": 10}


@pytest.mark.asyncio
async def test_run_author_note_human_asserted_evidence_backed(monkeypatch):
    calls = {}

    async def fake_ensure(pool, repository_key, neo4j_driver=None):
        return ("rootkey-uuid", 7, "taggable-server")

    async def fake_insert(**kw):
        calls["insert"] = kw
        return 55, False

    async def fake_resolve(pool, repository_key, refs):
        return "taggable-server", refs

    async def fake_embed(**kw):
        calls["embed"] = kw

    async def fake_project(**kw):
        calls["project"] = kw

    monkeypatch.setattr(repo_note, "ensure_repo_root_entity", fake_ensure)
    monkeypatch.setattr(repo_note, "insert_operator_note_create_only", fake_insert)
    monkeypatch.setattr(repo_note, "resolve_evidence_refs", fake_resolve)
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
        content_kind="repository-decision",
        evidence_refs=[{"kind": "revision", "repository_key": "taggable-server",
                        "revision_commit": "a" * 40}],
    )
    assert res.status == "success"
    up = calls["insert"]
    assert up["verification_status"] == "human_asserted"
    assert up["scope_entity_id"] == 7
    assert up["entity_key"] == learned_record_entity_key(
        "taggable-server", "note", hashlib.sha256(b"React migration underway").hexdigest()[:16]
    )
    assert calls["embed"]["repository_key"] == "taggable-server"
    assert calls["embed"]["scope_entity_key"] == "rootkey-uuid"
    assert "project" in calls


@pytest.mark.asyncio
async def test_author_note_canonicalizes_key_end_to_end(monkeypatch):
    # A1 end-to-end: author with "FCSAPI"; the note must be keyed + embedded under canonical "fcsapi"
    # so run_retrieval_workflow("fcsapi", ...) can read it back.
    calls = {}

    async def fake_insert(**kw):
        calls["insert"] = kw
        return 1, False

    async def fake_resolve(pool, repository_key, refs):
        return "fcsapi", [{**refs[0], "repository_key": "fcsapi"}]

    async def fake_embed(**kw):
        calls["embed"] = kw

    async def noop(**kw):
        pass

    monkeypatch.setattr(repo_note, "insert_operator_note_create_only", fake_insert)
    monkeypatch.setattr(repo_note, "resolve_evidence_refs", fake_resolve)
    monkeypatch.setattr(repo_note, "embed_and_upsert_learned_record", fake_embed)
    monkeypatch.setattr(repo_note, "project_learned_rule", noop)

    res = await repo_note.run_author_note(
        repository_key="FCSAPI", title="t", body_text="b", run_id=_uuid.uuid4(),
        pool=FakePool(canonical_key="fcsapi"), qdrant_client=object(), settings=SimpleNamespace(),
        content_kind="repository-fact",
        evidence_refs=[{"kind": "revision", "repository_key": "FCSAPI",
                        "revision_commit": "b" * 40}],
    )
    assert res.status == "success"
    expected_key = learned_record_entity_key("fcsapi", "note", hashlib.sha256(b"t").hexdigest()[:16])
    assert calls["insert"]["entity_key"] == expected_key   # canonical, not FCSAPI
    assert calls["embed"]["repository_key"] == "fcsapi"     # read-back-critical payload key
    assert res.data["repository_key"] == "fcsapi"


@pytest.mark.asyncio
async def test_author_note_auto_anchor_for_unrevisioned_repo(monkeypatch):
    # A2 end-to-end: a repo with no revision still authors (synthetic anchor created, no source).
    async def noop(**kw):
        pass

    async def fake_insert(**kw):
        return 1, False

    async def fake_resolve(pool, repository_key, refs):
        return "taggable-server", refs

    monkeypatch.setattr(repo_note, "insert_operator_note_create_only", fake_insert)
    monkeypatch.setattr(repo_note, "resolve_evidence_refs", fake_resolve)
    monkeypatch.setattr(repo_note, "embed_and_upsert_learned_record", noop)
    monkeypatch.setattr(repo_note, "project_learned_rule", noop)

    pool = FakePool(revision_id=None)
    res = await repo_note.run_author_note(
        repository_key="taggable-server", title="t", body_text="b", run_id=_uuid.uuid4(),
        pool=pool, qdrant_client=object(), settings=SimpleNamespace(),
        content_kind="repository-fact",
        evidence_refs=[{"kind": "revision", "repository_key": "taggable-server",
                        "revision_commit": "c" * 40}],
    )
    assert res.status == "success"
    assert pool.created_revision == {"commit_sha": "__note_anchor__", "branch_name": "__notes__"}


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


# --- author_repo_note MCP tool wiring ------------------------------------------


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


# --- learned_memory retrieval search (repo isolation) --------------------------
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


# --- candidate tier (verification_status) --------------------------------------
@pytest.mark.asyncio
async def test_run_author_note_candidate_tier(monkeypatch):
    cap = {}

    async def fake_ensure(pool, repository_key, neo4j_driver=None):
        return ("rk", 7, "r")

    async def fake_insert(**kw):
        cap["vs"] = kw["verification_status"]
        return 1, False

    async def fake_resolve(pool, repository_key, refs):
        return "r", refs

    async def noop(**kw):
        pass

    monkeypatch.setattr(repo_note, "ensure_repo_root_entity", fake_ensure)
    monkeypatch.setattr(repo_note, "insert_operator_note_create_only", fake_insert)
    monkeypatch.setattr(repo_note, "resolve_evidence_refs", fake_resolve)
    monkeypatch.setattr(repo_note, "embed_and_upsert_learned_record", noop)
    monkeypatch.setattr(repo_note, "project_learned_rule", noop)

    evidence = [{"kind": "revision", "repository_key": "r", "revision_commit": "d" * 40}]
    r = await repo_note.run_author_note(repository_key="r", title="t", body_text="b",
                                        run_id=_uuid.uuid4(), pool=_RevPool(), settings=SimpleNamespace(),
                                        content_kind="repository-fact", evidence_refs=evidence)
    assert r.status == "success" and cap["vs"] == "human_asserted"
    r2 = await repo_note.run_author_note(repository_key="r", title="t", body_text="b",
                                         run_id=_uuid.uuid4(), verification_status="unverified",
                                         pool=_RevPool(), settings=SimpleNamespace(),
                                         content_kind="root-cause", evidence_refs=evidence)
    assert r2.status == "success" and cap["vs"] == "unverified"
    assert r2.data["verification_status"] == "unverified"


@pytest.mark.asyncio
async def test_candidate_authoring_uses_one_explicit_transaction(monkeypatch):
    class AtomicPool(_RevPool):
        def __init__(self):
            self.active = False

        def transaction(self):
            return _AsyncContextWithHooks(
                enter=lambda: setattr(self, "active", True),
                exit=lambda: setattr(self, "active", False),
            )

    pool = AtomicPool(); observed = []

    async def fake_resolve(conn, repository_key, refs):
        observed.append(conn is pool and pool.active); return "r", refs

    async def fake_ensure(conn, repository_key, neo4j_driver=None):
        observed.append(conn is pool and pool.active); return "root", 7, "r"

    async def fake_insert(**kwargs):
        observed.append(kwargs["pool"] is pool and pool.active); return 1, False

    monkeypatch.setattr(repo_note, "resolve_evidence_refs", fake_resolve)
    monkeypatch.setattr(repo_note, "ensure_repo_root_entity", fake_ensure)
    monkeypatch.setattr(repo_note, "insert_operator_note_create_only", fake_insert)
    evidence = [{"kind": "revision", "repository_key": "r", "revision_commit": "e" * 40}]
    result = await repo_note.run_author_note(
        repository_key="r", title="Cause", body_text="Stable cause", run_id=_uuid.uuid4(),
        pool=pool, settings=SimpleNamespace(), verification_status="unverified",
        content_kind="root-cause", evidence_refs=evidence,
    )
    assert result.status == "success" and all(observed) and not pool.active


@pytest.mark.asyncio
async def test_run_author_note_rejects_bad_verification_status():
    r = await repo_note.run_author_note(repository_key="r", title="t", body_text="b",
                                        run_id=_uuid.uuid4(), verification_status="bogus",
                                        pool=_RevPool(), settings=SimpleNamespace())
    assert r.status == "error" and "verification_status" in r.error


# --- run_deactivate_note (counterpart to run_author_note) ----------------------

class FakeDeactivatePool:
    """Matches run_deactivate_note: A1 resolve (fetch) + entity_key lookup + the UPDATE."""

    def __init__(self, found=True, is_active=True, repo_found=True, canonical_key="taggable-server"):
        self.found = found
        self.is_active = is_active
        self.repo_found = repo_found
        self.canonical_key = canonical_key
        self.executed: list[tuple] = []

    async def fetch(self, query, *args):
        if "lower(repository_key) = lower($1)" in query:  # A1 resolve
            return [{"id": 1, "repository_key": self.canonical_key}] if self.repo_found else []
        raise AssertionError(f"unexpected fetch: {query}")

    async def fetchrow(self, query, *args):
        if "FROM memory.learned_records lr" in query and "JOIN catalog.entities e" in query:
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
    assert q.set_payload_calls and q.set_payload_calls[0]["payload"] == {"is_active": False}  # Qdrant
    expected = str(learned_record_entity_key(
        "taggable-server", "note", hashlib.sha256(b"S5 verification note").hexdigest()[:16]))
    assert res.data["entity_key"] == expected


@pytest.mark.asyncio
async def test_deactivate_note_canonicalizes_key():
    # A1: deactivate under "FCSAPI" resolves canonical "fcsapi" and computes the same entity_key
    # authoring (under any casing) wrote.
    pool = FakeDeactivatePool(found=True, canonical_key="fcsapi")
    res = await repo_note.run_deactivate_note(
        repository_key="FCSAPI", title="lesson", run_id=_uuid.uuid4(), pool=pool)
    assert res.status == "success"
    expected = str(learned_record_entity_key(
        "fcsapi", "note", hashlib.sha256(b"lesson").hexdigest()[:16]))
    assert res.data["entity_key"] == expected


@pytest.mark.asyncio
async def test_deactivate_note_errors_when_repo_missing():
    res = await repo_note.run_deactivate_note(
        repository_key="x", title="t", run_id=_uuid.uuid4(),
        pool=FakeDeactivatePool(repo_found=False))
    assert res.status == "error" and "No repo note found" in res.error


@pytest.mark.asyncio
async def test_deactivate_note_errors_when_missing():
    res = await repo_note.run_deactivate_note(
        repository_key="x", title="does not exist", run_id=_uuid.uuid4(),
        pool=FakeDeactivatePool(found=False))
    assert res.status == "error" and "No repo note found" in res.error


@pytest.mark.asyncio
async def test_deactivate_note_requires_title():
    res = await repo_note.run_deactivate_note(
        repository_key="x", title="", run_id=_uuid.uuid4(), pool=FakeDeactivatePool())
    assert res.status == "error" and "title is required" in res.error
