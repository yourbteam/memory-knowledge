# Q&A Knowledge Preservation — Implementation Plan (v1)

**Source of truth:** `docs/QA_KNOWLEDGE_PRESERVATION_RESEARCH.md` (F1–F12). This plan turns that research into an ordered, change-by-change execution sequence with ready-to-apply code and per-step validation gates. All code is grounded in verified clone targets (`triage_memory.py`, `db/qdrant.py`, `server.py`, `qdrant_payload_schemas.py`, migrations `025`).

**Scope:** v1 only — F1–F6, F8–F12. Phase 2 (route-policy fusion, F7) is explicitly out of scope.

**Execution rule (per CLAUDE.md):** each step below is a discrete, approval-gated change. I will present the exact diff for a step, wait for approval, apply it, run its validation gate, then move to the next. memory-knowledge ships and is verified in prod **before** any MAWF-side change.

**Ordering & dependency graph:**
```
Step 1 (migration) ─┐
Step 2 (qa_memory) ─┼─► Step 5 (server tools) ─► Step 6 (tests) ─► Step 7 (local gate)
Step 3 (COLLECTIONS)┤                                                      │
Step 4 (payload)  ──┘                                                      ▼
                                                          Step 8 (deploy + prod verify)
                                                                           │
                                                          Step 9 (MAWF wiring) ─► Step 10 (E2E accept)
```
Steps 1–4 are independent and can be written in any order; Step 5 imports Step 2; Step 6 tests Steps 2/5; Step 7 gates deploy.

---

## Step 0 — Pre-flight (no code)

- **Branch:** create `feature/qa-knowledge` off the current default branch (do not commit to default).
- **Env:** remote/prod per project norms — do **not** switch to local env. AUTH_MODE stays `codex`. Embeddings stay self-hosted fastembed.
- **Confirm head:** `grep -rE "^revision|^down_revision" migrations/versions/025_ingestion_checkpoints.py` → `025_ingestion_checkpoints` is head (verified).
- **Validation gate:** `git status` clean; on the new branch.

---

## Step 1 — Migration `migrations/versions/026_qa_pairs.py` (CREATE)

**Why:** Creates the canonical `memory.qa_pairs` table + indexes (F1). Runs automatically on memory-knowledge startup ("Running database migrations…"). Additive; touches no existing table.

**Action:** new file. Match the header style of `025_ingestion_checkpoints.py` exactly (`revision = "..."`, `down_revision = "..."`, `op.execute("""…""")`).

```python
"""qa_pairs: standalone per-repo Q&A knowledge store."""

from alembic import op

revision = "026_qa_pairs"
down_revision = "025_ingestion_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory.qa_pairs (
            qa_pair_id      UUID PRIMARY KEY,
            repository_id   BIGINT NOT NULL REFERENCES catalog.repositories(id),
            feature_key     VARCHAR(255),
            task_key        VARCHAR(255),
            question        TEXT NOT NULL,
            answer          TEXT NOT NULL,
            question_hash   TEXT NOT NULL,
            question_tsv    TSVECTOR,
            source          JSONB NOT NULL DEFAULT '{}'::jsonb,
            confidence      NUMERIC(3,2) NOT NULL DEFAULT 0.80,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            superseded_by   UUID REFERENCES memory.qa_pairs(qa_pair_id),
            created_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_qa_pairs_repo_qhash
            ON memory.qa_pairs(repository_id, question_hash);
        CREATE INDEX IF NOT EXISTS ix_qa_pairs_repo_active
            ON memory.qa_pairs(repository_id) WHERE is_active;
        CREATE INDEX IF NOT EXISTS ix_qa_pairs_qtsv
            ON memory.qa_pairs USING GIN (question_tsv);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory.qa_pairs;")
```

**Validation gate:** `alembic heads` (or the same revision-chain scan used for `025`) shows a single head `026_qa_pairs`; `python -c "import importlib; importlib.import_module('migrations.versions.026_qa_pairs')"` imports clean.

---

## Step 2 — Module `src/memory_knowledge/qa_memory.py` (CREATE)

**Why:** The projection + search core (F2). Clone of `triage_memory.py` with the deliberate deviation: deterministic `uuid5` point id (not `uuid4`), so ingest is idempotent (F8).

**Action:** new file.

```python
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import asyncpg
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.db.qdrant import semantic_query_points
from memory_knowledge.identity.entity_key import NAMESPACE_MK
from memory_knowledge.llm.openai_client import embed_single

logger = structlog.get_logger()

QA_PAIRS_COLLECTION = "qa_pairs"


async def _resolve_repository_id(pool: asyncpg.Pool, repository_key: str) -> int | None:
    row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1",
        repository_key,
    )
    return row["id"] if row else None


def _normalize_question(q: str) -> str:
    return " ".join(q.strip().lower().split())


def _question_hash(q: str) -> str:
    # Same sha256 pattern as triage's _prompt_hash, but over the NORMALIZED question.
    return hashlib.sha256(_normalize_question(q).encode("utf-8")).hexdigest()


def _qa_pair_id(repository_key: str, question_hash: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE_MK, f"qa:{repository_key}:{question_hash}")


def _qa_payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "qa_pair_id": str(row["qa_pair_id"]),
        "repository_key": row["repository_key"],
        "feature_key": row.get("feature_key"),
        "is_active": True,
        "content_kind": "qa_pair",
    }


def _qa_point_from_row(row: dict[str, Any], embedding: list[float]) -> models.PointStruct:
    return models.PointStruct(
        id=str(row["qa_pair_id"]),
        vector=embedding,
        payload=_qa_payload_from_row(row),
    )


def _qdrant_filter(*, repository_key: str, feature_key: str | None = None) -> models.Filter:
    conditions: list[models.FieldCondition] = [
        models.FieldCondition(key="repository_key", match=models.MatchValue(value=repository_key)),
        models.FieldCondition(key="is_active", match=models.MatchValue(value=True)),
    ]
    if feature_key:
        conditions.append(
            models.FieldCondition(key="feature_key", match=models.MatchValue(value=feature_key))
        )
    return models.Filter(must=conditions)


async def ingest_qa_pairs(
    pool: asyncpg.Pool,
    settings: Settings,
    *,
    repository_key: str,
    pairs: list[dict[str, Any]],
    source: dict[str, Any] | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
) -> dict[str, Any]:
    repository_id = await _resolve_repository_id(pool, repository_key)
    if repository_id is None:
        raise ValueError(f"Repository '{repository_key}' not found")

    qa_pair_ids: list[uuid.UUID] = []
    skipped: list[dict[str, Any]] = []

    for pair in pairs:
        q = (pair.get("question") or "").strip()
        a = (pair.get("answer") or "").strip()
        if not q or not a:
            skipped.append({"question": pair.get("question"), "reason": "empty question/answer"})
            continue

        eff_source = {**(source or {}), **(pair.get("source") or {})}
        qh = _question_hash(q)
        qid = _qa_pair_id(repository_key, qh)
        feature_key = eff_source.get("feature_key")
        task_key = eff_source.get("task_key")

        await pool.execute(
            """
            INSERT INTO memory.qa_pairs (
                qa_pair_id, repository_id, feature_key, task_key,
                question, answer, question_hash, question_tsv, source, confidence
            )
            VALUES (
                $1::uuid, $2, $3, $4,
                $5, $6, $7, to_tsvector('english', $5), $8::jsonb, 0.80
            )
            ON CONFLICT (repository_id, question_hash) DO UPDATE SET
                answer = EXCLUDED.answer,
                feature_key = EXCLUDED.feature_key,
                task_key = EXCLUDED.task_key,
                source = EXCLUDED.source,
                updated_utc = NOW()
            """,
            str(qid), repository_id, feature_key, task_key,
            q, a, qh, json.dumps(eff_source),
        )

        if qdrant_client is not None:
            try:
                embedding = await embed_single(q, settings)
                await qdrant_client.upsert(
                    collection_name=QA_PAIRS_COLLECTION,
                    points=[
                        _qa_point_from_row(
                            {
                                "qa_pair_id": qid,
                                "repository_key": repository_key,
                                "feature_key": feature_key,
                            },
                            embedding,
                        )
                    ],
                )
            except Exception:
                logger.warning("qa_pair_embedding_upsert_failed", qa_pair_id=str(qid), exc_info=True)

        qa_pair_ids.append(qid)

    return {
        "ingested": len(qa_pair_ids),
        "qa_pair_ids": [str(x) for x in qa_pair_ids],
        "skipped": skipped,
    }


async def search_qa_knowledge(
    pool: asyncpg.Pool,
    settings: Settings,
    *,
    repository_key: str,
    question: str,
    limit: int = 5,
    min_similarity: float = 0.65,
    qdrant_client: AsyncQdrantClient | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    repository_id = await _resolve_repository_id(pool, repository_key)
    if repository_id is None:
        return {"advisory_only": True, "rows": [], "warnings": ["unknown repository"]}

    candidates: list[tuple[str, float]] = []
    fallback_to_lexical = qdrant_client is None

    if qdrant_client is not None:
        try:
            qe = await embed_single(question, settings)
            results = await semantic_query_points(
                qdrant_client,
                collection_name=QA_PAIRS_COLLECTION,
                query_vector=qe,
                limit=max(limit * 5, limit),
                score_threshold=min_similarity,
                query_filter=_qdrant_filter(repository_key=repository_key),
            )
            candidates = [(str(r.id), float(r.score)) for r in results]
        except Exception:
            warnings.append("Semantic retrieval unavailable; using lexical fallback.")
            logger.warning("qa_search_semantic_failed", exc_info=True)
            fallback_to_lexical = True
    else:
        warnings.append("Semantic retrieval unavailable; using lexical fallback.")

    # Semantic ran and found nothing → return empty (matches search_triage_cases:762-768).
    if qdrant_client is not None and not fallback_to_lexical and not candidates:
        return {"advisory_only": True, "rows": [], "warnings": warnings}

    if fallback_to_lexical:
        lex = await pool.fetch(
            """
            SELECT qa_pair_id,
                   ts_rank(question_tsv, plainto_tsquery('english', $2)) AS score
            FROM memory.qa_pairs
            WHERE repository_id = $1 AND is_active
              AND question_tsv @@ plainto_tsquery('english', $2)
            ORDER BY score DESC
            LIMIT $3
            """,
            repository_id, question, limit,
        )
        candidates = [(str(r["qa_pair_id"]), float(r["score"])) for r in lex]

    if not candidates:
        return {"advisory_only": True, "rows": [], "warnings": warnings}

    score_by_id = {cid: score for cid, score in candidates}
    hydrated = await pool.fetch(
        """
        SELECT qa_pair_id, question, answer, confidence, source
        FROM memory.qa_pairs
        WHERE qa_pair_id = ANY($1::uuid[]) AND is_active
        """,
        [cid for cid, _ in candidates],
    )

    rows: list[dict[str, Any]] = []
    for r in hydrated:
        raw_source = r["source"]
        src = raw_source if isinstance(raw_source, dict) else json.loads(raw_source or "{}")
        rows.append(
            {
                "qa_pair_id": str(r["qa_pair_id"]),
                "question": r["question"],
                "answer": r["answer"],
                "confidence": float(r["confidence"]),
                "source": src,
                "score": score_by_id.get(str(r["qa_pair_id"]), 0.0),
            }
        )
    rows.sort(key=lambda x: x["score"], reverse=True)  # PG = ANY() does not preserve order
    return {"advisory_only": True, "rows": rows[:limit], "warnings": warnings}
```

**Implementation notes (verified):** `asyncpg` returns JSONB as `str` unless a codec is registered → `search` defensively `json.loads` when `source` is not already a dict. `embed_single(text, settings)` requires `settings` at **both** call sites. `superseded_by`/`is_active`/timestamps use table defaults (not in the INSERT column list). `reproject_qa_pairs` (optional compaction parity, clone `reproject_triage_cases:460`) is deferred — not required for v1 acceptance.

**Validation gate:** `python -c "import memory_knowledge.qa_memory"` imports clean.

---

## Step 3 — `src/memory_knowledge/db/qdrant.py` (EDIT — COLLECTIONS)

**Why:** Adding `"qa_pairs"` makes `ensure_collections` auto-create it at 768/COSINE and apply the standard payload indexes (`repository_key`, `feature_key`, `is_active`, …) on startup (F3). `task_key` is intentionally not indexed.

**Action:** one-line addition to the `COLLECTIONS` list.

```python
COLLECTIONS = [
    "code_chunks",
    "summary_units",
    "learned_memory",
    "routing_archetypes",
    "triage_cases",
    "qa_pairs",          # <-- add
]
```

**Validation gate:** `python -c "from memory_knowledge.db.qdrant import COLLECTIONS; assert 'qa_pairs' in COLLECTIONS"`.

---

## Step 4 — `src/memory_knowledge/projections/qdrant_payload_schemas.py` (EDIT — QAPairPayload)

**Why:** Pydantic payload model for the qa point (F3), mirroring `LearnedMemoryPayload` but adapted to the standalone model (`qa_pair_id` not `entity_key`).

**Action:** append a class.

```python
class QAPairPayload(BaseModel):
    qa_pair_id: str
    repository_key: str
    feature_key: str | None = None
    is_active: bool
    content_kind: str = "qa_pair"
```

**Validation gate:** `python -c "from memory_knowledge.projections.qdrant_payload_schemas import QAPairPayload"`.

---

## Step 5 — `src/memory_knowledge/server.py` (EDIT — 2 MCP tools + import)

**Why:** Exposes ingest (WRITE, guarded) and search (READ) over MCP (F4), cloning the `save_triage_case`/`search_triage_cases` tool boilerplate exactly (`@mcp.tool()` → `@track_tool_metrics` → run-context → guard → call module → `WorkflowResult`).

**Action 5a — import** (near the other `from memory_knowledge import …`):
```python
from memory_knowledge import qa_memory as _qa_memory
```

**Action 5b — tools** (place near the triage tools, ~`server.py:1380`):
```python
@mcp.tool()
@track_tool_metrics("ingest_qa_pairs")
async def ingest_qa_pairs(
    repository_key: str,
    pairs: list[dict],
    source: dict | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "ingest_qa_pairs")
    guard = check_remote_write_guard(get_settings(), "ingest_qa_pairs")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        if not str(repository_key or "").strip() or not pairs:
            return WorkflowResult(
                run_id=str(rid), tool_name="ingest_qa_pairs", status="error",
                error="repository_key and non-empty pairs are required",
            ).model_dump_json()
        data = await _qa_memory.ingest_qa_pairs(
            get_pg_pool(), get_settings(),
            repository_key=repository_key, pairs=pairs, source=source or {},
            qdrant_client=get_qdrant_client(),
        )
        return WorkflowResult(
            run_id=str(rid), tool_name="ingest_qa_pairs", status="success", data=data,
        ).model_dump_json()
    except ValueError as exc:  # unknown repository_key
        return WorkflowResult(
            run_id=str(rid), tool_name="ingest_qa_pairs", status="error", error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("search_qa_knowledge")
async def search_qa_knowledge(
    repository_key: str,
    question: str,
    limit: int = 5,
    min_similarity: float = 0.65,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "search_qa_knowledge")
    try:
        if not str(question or "").strip():
            return WorkflowResult(
                run_id=str(rid), tool_name="search_qa_knowledge", status="error",
                error="question is required",
            ).model_dump_json()
        data = await _qa_memory.search_qa_knowledge(
            get_pg_pool(), get_settings(),
            repository_key=repository_key, question=question, limit=limit,
            min_similarity=min_similarity, qdrant_client=get_qdrant_client(),
        )
        return WorkflowResult(
            run_id=str(rid), tool_name="search_qa_knowledge", status="success", data=data,
        ).model_dump_json()
    finally:
        clear_run_context()
```

**Validation gate:** `python -c "import memory_knowledge.server"`; the two tool names appear in the FastMCP registry.

---

## Step 6 — `tests/test_qa_memory.py` (CREATE — clone `tests/test_triage_memory.py`)

**Why:** Unit coverage (F9) — quality gate. Clone the fakes from `tests/test_triage_memory.py:13-42` (`FakeQdrant`, `QueryPointsQdrant`, `EmptySearchQdrant` + fake pool).

**Action:** new file covering:
1. `ingest_qa_pairs` writes a row, computes deterministic `qa_pair_id` (`uuid5`), embeds + upserts a point.
2. Re-ingest of the same (normalized) question → same `qa_pair_id`, one upsert (overwrite), answer changes.
3. Unknown `repository_key` → `ValueError`.
4. Blank question/answer → recorded in `skipped`, not ingested.
5. `search_qa_knowledge`: builds `_qdrant_filter` requiring `repository_key`+`is_active`; thresholds at `min_similarity`; hydrates active rows; re-sorts by score; semantic-ran-but-empty → `{rows: []}`; unknown repo → `{rows: [], warnings:["unknown repository"]}`.
6. `_question_hash`: trivial phrasing variants (case/whitespace) collapse to the same hash.
7. (MCP) `ingest_qa_pairs` honors the write guard; `search_qa_knowledge` rejects empty question.

**Validation gate:** `.venv/bin/python -m pytest tests/test_qa_memory.py -q` → all pass.

---

## Step 7 — Local validation gate (no code)

Run before any deploy:
- `.venv/bin/python -m pytest tests/test_qa_memory.py -q` → green.
- Import smoke: `.venv/bin/python -c "import memory_knowledge.qa_memory, memory_knowledge.server"`.
- Migration chain: single head `026_qa_pairs`.
- Full suite: green except the known pre-existing `test_config.py`/`test_guards.py` env failures.
- `git diff --check` clean.

**Gate:** all green → proceed to deploy. Any failure → fix before Step 8.

---

## Step 8 — Deploy memory-knowledge + prod verification (no app code)

**Why:** memory-knowledge must be live with the table, collection, and tools **before** MAWF calls them (F10 deploy ordering).

**Action (per `reference_deploy_process.md`):**
1. `az acr build --registry workfloworchreg --image memory-knowledge:<sha> .`
2. `az webapp config container set …` to the new SHA-tagged image (RG `workflow-orch-rg`, app `memory-knowledge`).
3. `az webapp restart …`.
4. Watch startup logs (Kudu vfs via AAD bearer) for "Running database migrations…" and `ensure_collections`.

**Prod verification (F12):**
- `SELECT to_regclass('memory.qa_pairs') IS NOT NULL;` → `true`.
- `SELECT version_num FROM alembic_version;` → `026_qa_pairs`.
- `feature_key`/`task_key`/`question_tsv` columns present.
- Qdrant `count` on `qa_pairs` returns without error (collection exists).
- MCP `tools/list` includes `ingest_qa_pairs` and `search_qa_knowledge`.

**Gate:** all verifications pass → proceed to MAWF wiring.

---

## Step 9 — MAWF wiring (`mcp-agents-workflow`) (EDIT)

**Why:** Closes the loop — capture on intake finalize, optional pre-surface on new questions (F6). Cross-repo change; only after Step 8 is green in prod.

**Action 9a — `src/workflow_orch/knowledge_client.py`:** add two thin wrappers over the existing `call_tool_json` (`:358`), mirroring `propose_learned_memory:476`/`query_knowledge:408`:
```python
async def ingest_qa_pairs(self, repository_key, pairs, source=None):
    return await self.call_tool_json("ingest_qa_pairs", {
        "repository_key": repository_key, "pairs": pairs, "source": source or {},
    })

async def search_qa_knowledge(self, repository_key, question, limit=5, min_similarity=0.65):
    return await self.call_tool_json("search_qa_knowledge", {
        "repository_key": repository_key, "question": question,
        "limit": limit, "min_similarity": min_similarity,
    })
```

**Action 9b — `src/workflow_orch/intake.py`:** at finalize (where `answeredQuestionsByNode` is produced, `:333`), flatten and push (Option A, the verified shape `{node_key: [{id, node, text, answerText, …}]}`):
```python
pairs = []
for node_key, entries in (projection.get("answeredQuestionsByNode") or {}).items():
    for e in entries:
        q, a = (e.get("text") or "").strip(), (e.get("answerText") or "").strip()
        if q and a:
            pairs.append({"question": q, "answer": a,
                          "source": {"node_key": node_key, "question_id": e.get("id")}})
if pairs:
    await knowledge_client.ingest_qa_pairs(
        repository_key=session_repository_key,                  # confirm finalize-path value (F11)
        pairs=pairs,
        source={"session_key": session_key, "feature_key": feature_key, "task_key": task_key},
    )
```
Optionally, when generating a new clarifying question, call `search_qa_knowledge` first (Scenario B closed loop).

**Pre-implementation confirm (F11):** the exact finalize-path variable carrying `repository_key`/`session_key`/`feature_key`/`task_key` (grounded near `intake.py:612`); the guard's behavior for `ingest_qa_pairs` under the deployment data-mode (precedent: `save_triage_case` is a guarded write MAWF already uses successfully).

**Validation gate:** MAWF unit tests green; a finalize dry-run logs one `ingest_qa_pairs` call with non-empty `pairs` and populated `source.question_id`.

---

## Step 10 — End-to-end acceptance (F12)

1. `ingest_qa_pairs(repo, source={session_key,feature_key,task_key}, pairs=[{question, answer, source:{node_key,question_id}}])` → `{"ingested":1,"qa_pair_ids":[id],"skipped":[]}`; row in `memory.qa_pairs`, active point in `qa_pairs`.
2. `search_qa_knowledge(repo, <paraphrase>)` → returns that row, `score ≥ 0.65`.
3. Re-`ingest_qa_pairs` same question, new answer → still **one** row/point; answer overwritten (F8).
4. `search_qa_knowledge(repo, <unrelated>)` → `rows: []`.
5. `ingest_qa_pairs(unknown_repo, …)` → `status:"error"`, no row written.

**No-regression:** dispatcher/retrieval unchanged (`memory.qa_pairs` + `qa_pairs` collection are additive).

**Gate:** all 5 pass → v1 complete.

---

## Commit & PR (on approval)

- memory-knowledge: one commit for Steps 1–6 on `feature/qa-knowledge` (no `Co-Authored-By`/AI attribution per CLAUDE.md). PR body references this plan + the research doc.
- mcp-agents-workflow: separate commit/PR for Step 9, opened only after Step 8 prod verification.

## Open confirmations carried into execution (none are blockers)
- F11-1: MAWF finalize-path provenance variable names (Step 9 pre-confirm).
- F11-3: write-guard allowance for `ingest_qa_pairs` in the MAWF-calling context (precedent: `save_triage_case`).
- Multi-repo features ingest under the session's `repository_key` (locked per-repo decision).
