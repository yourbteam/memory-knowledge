"""Unit tests for qa_memory (clone of tests/test_triage_memory.py patterns)."""

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from structlog.testing import capture_logs

from memory_knowledge import qa_memory
from memory_knowledge import server
from memory_knowledge.identity.entity_key import NAMESPACE_MK


# --- Fakes (mirror tests/test_triage_memory.py:13-42) ---------------------------


class FakeQdrant:
    """Returns all upserted points as semantic hits (round-trip friendly)."""

    def __init__(self):
        self.upserts = []
        self.query_calls = []

    async def upsert(self, collection_name, points):
        self.upserts.append((collection_name, points))

    async def query_points(self, **kwargs):
        self.query_calls.append(kwargs)
        pts = [SimpleNamespace(id=str(p.id), score=0.83, payload={}) for (_, points) in self.upserts for p in points]
        return SimpleNamespace(points=pts)


class EmptyQdrant(FakeQdrant):
    async def query_points(self, **kwargs):
        self.query_calls.append(kwargs)
        return SimpleNamespace(points=[])


class QAPool:
    """In-memory stand-in for asyncpg.Pool covering the qa SQL surface."""

    def __init__(self):
        self.rows = {}  # qa_pair_id(str) -> row dict
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        if "SELECT id FROM catalog.repositories WHERE repository_key = $1" in query:
            return {"id": 7} if args[0] == "taggable-server" else None
        return None

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        if "INSERT INTO memory.qa_pairs" in query:
            qid = str(args[0])
            qh = args[6]
            # Simulate ON CONFLICT (repository_id, question_hash) overwrite.
            for k in [k for k, v in self.rows.items() if v["question_hash"] == qh]:
                del self.rows[k]
            self.rows[qid] = {
                "qa_pair_id": uuid.UUID(qid),
                "repository_id": args[1],
                "feature_key": args[2],
                "task_key": args[3],
                "question": args[4],
                "answer": args[5],
                "question_hash": qh,
                "source": args[7],  # JSON string
                "confidence": 0.80,
                "is_active": True,
            }

    async def fetch(self, query, *args):
        if "ts_rank" in query:  # lexical fallback
            return [{"qa_pair_id": v["qa_pair_id"], "score": 0.5} for v in self.rows.values()]
        if "WHERE qa_pair_id = ANY" in query:  # hydrate
            ids = {str(x) for x in args[0]}
            return [
                {
                    "qa_pair_id": v["qa_pair_id"],
                    "question": v["question"],
                    "answer": v["answer"],
                    "confidence": v["confidence"],
                    "source": v["source"],
                }
                for k, v in self.rows.items()
                if k in ids
            ]
        return []


def _embed(text, settings):
    return asyncio.sleep(0, result=[0.1] * 8)


@pytest.fixture
def patch_embed(monkeypatch):
    monkeypatch.setattr("memory_knowledge.qa_memory.embed_single", _embed)


SETTINGS = SimpleNamespace(embedding_dimensions=8, qa_search_min_similarity=0.45, qa_lexical_min_overlap=0.6)


# --- Module-level: ingest -------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_writes_row_and_upserts_point(patch_embed):
    pool, qdrant = QAPool(), FakeQdrant()
    res = await qa_memory.ingest_qa_pairs(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        pairs=[
            {
                "question": "When a tag is deleted, what happens?",
                "answer": "Untagged, not deleted.",
                "source": {"node_key": "analysis", "question_id": "q3"},
            }
        ],
        source={"session_key": "S-99", "feature_key": "F-12", "task_key": "T-4821"},
        qdrant_client=qdrant,
    )
    assert res["ingested"] == 1 and res["skipped"] == []
    assert len(pool.rows) == 1 and len(qdrant.upserts) == 1

    qid = res["qa_pair_ids"][0]
    # deterministic uuid5 over the normalized question
    qh = qa_memory._question_hash("When a tag is deleted, what happens?")
    assert qid == str(uuid.uuid5(NAMESPACE_MK, f"qa:taggable-server:{qh}"))
    # point id == qa_pair_id; merged source persisted
    _, points = qdrant.upserts[0]
    assert str(points[0].id) == qid
    assert points[0].payload["content_kind"] == "qa_pair"
    assert "task_key" not in points[0].payload  # PG-only
    stored_source = json.loads(pool.rows[qid]["source"])
    assert stored_source == {
        "session_key": "S-99",
        "feature_key": "F-12",
        "task_key": "T-4821",
        "node_key": "analysis",
        "question_id": "q3",
    }


@pytest.mark.asyncio
async def test_reingest_same_question_overwrites(patch_embed):
    pool, qdrant = QAPool(), FakeQdrant()
    args = dict(repository_key="taggable-server", source={"feature_key": "F-12"}, qdrant_client=qdrant)
    r1 = await qa_memory.ingest_qa_pairs(pool, SETTINGS, pairs=[{"question": "Q one?", "answer": "first"}], **args)
    r2 = await qa_memory.ingest_qa_pairs(
        pool, SETTINGS, pairs=[{"question": "  q   ONE? ", "answer": "second"}], **args
    )
    assert r1["qa_pair_ids"] == r2["qa_pair_ids"]  # same deterministic id
    assert len(pool.rows) == 1  # overwrite, not accumulate
    assert pool.rows[r2["qa_pair_ids"][0]]["answer"] == "second"


@pytest.mark.asyncio
async def test_unknown_repo_raises(patch_embed):
    with pytest.raises(ValueError, match="not found"):
        await qa_memory.ingest_qa_pairs(
            QAPool(),
            SETTINGS,
            repository_key="nope",
            pairs=[{"question": "q", "answer": "a"}],
            qdrant_client=FakeQdrant(),
        )


@pytest.mark.asyncio
async def test_blank_qa_skipped(patch_embed):
    pool = QAPool()
    res = await qa_memory.ingest_qa_pairs(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        pairs=[
            {"question": "", "answer": "x"},
            {"question": "y", "answer": ""},
            {"question": "real?", "answer": "yes"},
        ],
        qdrant_client=FakeQdrant(),
    )
    assert res["ingested"] == 1 and len(res["skipped"]) == 2


# --- Module-level: search -------------------------------------------------------


@pytest.mark.asyncio
async def test_search_round_trip(patch_embed):
    pool, qdrant = QAPool(), FakeQdrant()
    await qa_memory.ingest_qa_pairs(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        pairs=[{"question": "When a tag is deleted, what happens?", "answer": "Untagged."}],
        source={"session_key": "S-1"},
        qdrant_client=qdrant,
    )
    res = await qa_memory.search_qa_knowledge(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        question="If we remove a tag, are assets deleted?",
        qdrant_client=qdrant,
    )
    assert res["advisory_only"] is True
    assert len(res["rows"]) == 1
    row = res["rows"][0]
    assert row["answer"] == "Untagged." and row["score"] == 0.83
    assert isinstance(row["source"], dict) and row["source"]["session_key"] == "S-1"


@pytest.mark.asyncio
async def test_search_unknown_repo_returns_advisory_empty(patch_embed):
    res = await qa_memory.search_qa_knowledge(
        QAPool(), SETTINGS, repository_key="nope", question="anything", qdrant_client=FakeQdrant()
    )
    assert res == {"advisory_only": True, "rows": [], "warnings": ["unknown repository"]}


@pytest.mark.asyncio
async def test_search_semantic_empty_falls_back_to_lexical(patch_embed):
    pool, qdrant = QAPool(), EmptyQdrant()
    await qa_memory.ingest_qa_pairs(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        pairs=[{"question": "stored q?", "answer": "stored a"}],
        qdrant_client=FakeQdrant(),
    )
    # semantic runs (qdrant not None) and returns nothing → lexical fallback kicks in (Step 2).
    # Near-exact re-ask clears the lexical overlap floor.
    res = await qa_memory.search_qa_knowledge(
        pool, SETTINGS, repository_key="taggable-server", question="stored q", qdrant_client=qdrant
    )
    assert len(res["rows"]) == 1 and res["rows"][0]["answer"] == "stored a"
    assert "lexical fallback" in " ".join(res["warnings"])


@pytest.mark.asyncio
async def test_search_threshold_default_and_override(patch_embed):
    pool, qdrant = QAPool(), FakeQdrant()
    await qa_memory.ingest_qa_pairs(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        pairs=[{"question": "q?", "answer": "a"}],
        qdrant_client=qdrant,
    )
    # default param (0.45) reaches query_points
    await qa_memory.search_qa_knowledge(
        pool, SETTINGS, repository_key="taggable-server", question="q", qdrant_client=qdrant
    )
    assert qdrant.query_calls[-1]["score_threshold"] == 0.45
    # explicit override is forwarded
    await qa_memory.search_qa_knowledge(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        question="q",
        min_similarity=0.9,
        qdrant_client=qdrant,
    )
    assert qdrant.query_calls[-1]["score_threshold"] == 0.9


@pytest.mark.asyncio
async def test_search_logs_empty_result(patch_embed):
    # No rows ingested → semantic empty → lexical empty → empty result, but the
    # qa_search_done event must still fire with repository_key/returned/lexical_used (R4).
    pool = QAPool()
    with capture_logs() as logs:
        res = await qa_memory.search_qa_knowledge(
            pool,
            SETTINGS,
            repository_key="taggable-server",
            question="nothing here",
            qdrant_client=EmptyQdrant(),
        )
    assert res["rows"] == []
    done = [e for e in logs if e.get("event") == "qa_search_done"]
    assert done, "expected a qa_search_done log event"
    assert done[-1]["repository_key"] == "taggable-server"
    assert done[-1]["returned"] == 0 and "lexical_used" in done[-1]


@pytest.mark.asyncio
async def test_search_lexical_fallback_when_qdrant_none(patch_embed):
    pool = QAPool()
    await qa_memory.ingest_qa_pairs(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        pairs=[{"question": "stored q?", "answer": "stored a"}],
        qdrant_client=FakeQdrant(),
    )
    res = await qa_memory.search_qa_knowledge(
        pool, SETTINGS, repository_key="taggable-server", question="stored q", qdrant_client=None
    )  # forces lexical path; near-exact re-ask clears the overlap floor
    assert len(res["rows"]) == 1 and res["rows"][0]["answer"] == "stored a"
    assert "lexical fallback" in " ".join(res["warnings"])


@pytest.mark.asyncio
async def test_search_lexical_fallback_filters_low_overlap(patch_embed):
    # Fix A: the lexical fallback must drop loose token-overlap matches (the "plain stupid
    # suggestions" at low volume), surfacing nothing rather than guessing.
    pool, qdrant = QAPool(), EmptyQdrant()
    await qa_memory.ingest_qa_pairs(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        pairs=[{"question": "How do I rotate the API signing key?", "answer": "Use rotate-key."}],
        qdrant_client=FakeQdrant(),
    )
    res = await qa_memory.search_qa_knowledge(
        pool, SETTINGS, repository_key="taggable-server", question="delete a user account", qdrant_client=qdrant
    )
    assert res["rows"] == []  # no near-exact overlap → suppressed


@pytest.mark.asyncio
async def test_search_lexical_overlap_threshold_configurable(patch_embed):
    # A loose re-ask (overlap ~0.5) is surfaced under a permissive threshold and suppressed
    # under a strict one — proving qa_lexical_min_overlap governs the floor.
    pool = QAPool()
    await qa_memory.ingest_qa_pairs(
        pool,
        SETTINGS,
        repository_key="taggable-server",
        pairs=[{"question": "stored q?", "answer": "stored a"}],
        qdrant_client=FakeQdrant(),
    )
    permissive = SimpleNamespace(embedding_dimensions=8, qa_search_min_similarity=0.45, qa_lexical_min_overlap=0.1)
    strict = SimpleNamespace(embedding_dimensions=8, qa_search_min_similarity=0.45, qa_lexical_min_overlap=0.9)
    loose = await qa_memory.search_qa_knowledge(
        pool, permissive, repository_key="taggable-server", question="stored", qdrant_client=EmptyQdrant()
    )
    assert len(loose["rows"]) == 1  # 0.5 overlap >= 0.1
    tight = await qa_memory.search_qa_knowledge(
        pool, strict, repository_key="taggable-server", question="stored", qdrant_client=EmptyQdrant()
    )
    assert tight["rows"] == []  # 0.5 overlap < 0.9


def test_question_hash_normalization():
    a = qa_memory._question_hash("  When a Tag is   Deleted? ")
    b = qa_memory._question_hash("when a tag is deleted?")
    assert a == b


# --- MCP tools (mirror triage_env fixture) --------------------------------------


class FakeGuard:
    def __init__(self):
        self.run_id = None

    def model_dump_json(self):
        return json.dumps({"status": "blocked", "run_id": self.run_id})


@pytest.fixture
def qa_env(monkeypatch):
    pool, qdrant = QAPool(), FakeQdrant()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(server, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    monkeypatch.setattr("memory_knowledge.qa_memory.embed_single", _embed)
    return pool, qdrant


@pytest.mark.asyncio
async def test_tool_ingest_success(qa_env):
    result = await server.ingest_qa_pairs(
        repository_key="taggable-server", pairs=[{"question": "q?", "answer": "a"}], source={"session_key": "S-1"}
    )
    payload = json.loads(result)
    assert payload["status"] == "success" and payload["data"]["ingested"] == 1


@pytest.mark.asyncio
async def test_tool_ingest_unknown_repo_is_error(qa_env):
    result = await server.ingest_qa_pairs(repository_key="missing", pairs=[{"question": "q?", "answer": "a"}])
    payload = json.loads(result)
    assert payload["status"] == "error" and "not found" in payload["error"]


@pytest.mark.asyncio
async def test_tool_ingest_honors_write_guard(qa_env, monkeypatch):
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: FakeGuard())
    result = await server.ingest_qa_pairs(repository_key="taggable-server", pairs=[{"question": "q?", "answer": "a"}])
    assert json.loads(result)["status"] == "blocked"


@pytest.mark.asyncio
async def test_tool_ingest_rejects_empty_pairs(qa_env):
    result = await server.ingest_qa_pairs(repository_key="taggable-server", pairs=[])
    assert json.loads(result)["status"] == "error"


@pytest.mark.asyncio
async def test_tool_search_rejects_empty_question(qa_env):
    result = await server.search_qa_knowledge(repository_key="taggable-server", question="   ")
    payload = json.loads(result)
    assert payload["status"] == "error" and "question is required" in payload["error"]


@pytest.mark.asyncio
async def test_tool_search_resolves_threshold_from_settings(qa_env):
    # Step 3c / R7: the server tool resolves min_similarity None → settings value (the
    # deployed path), and an explicit arg overrides it.
    pool, qdrant = qa_env
    await server.ingest_qa_pairs(repository_key="taggable-server", pairs=[{"question": "q?", "answer": "a"}])
    await server.search_qa_knowledge(repository_key="taggable-server", question="q")
    assert qdrant.query_calls[-1]["score_threshold"] == SETTINGS.qa_search_min_similarity
    await server.search_qa_knowledge(repository_key="taggable-server", question="q", min_similarity=0.9)
    assert qdrant.query_calls[-1]["score_threshold"] == 0.9
