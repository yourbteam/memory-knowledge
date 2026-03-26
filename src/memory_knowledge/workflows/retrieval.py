from __future__ import annotations

import re
import time
import uuid
from typing import Any

import asyncpg
import neo4j
import openai
import structlog
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_retrieval_workflow"

# Prompt classification patterns — match code-like identifiers
_EXACT_PATTERNS = re.compile(
    r"\b[a-z]+[A-Z][a-zA-Z]*\b"  # camelCase (getUserById)
    r"|\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b"  # PascalCase (UserService, but not PostgreSQL-style)
    r"|[a-zA-Z_]+\.[a-zA-Z_]+\.[a-zA-Z_]+"  # dotted path (foo.bar.baz)
    r'|"[^"]+"'  # quoted identifiers
    r"|'[^']+'"
)
_IMPACT_KEYWORDS = {"impact", "affect", "change", "break", "breaking", "depends"}
_PATTERN_KEYWORDS = {"pattern", "how does", "approach", "design", "architecture"}
_DECISION_KEYWORDS = {"decision", "why did", "history", "chose", "rationale"}


# ---------------------------------------------------------------------------
# Sub-step functions
# ---------------------------------------------------------------------------


async def resolve_repository(pool: asyncpg.Pool, repository_key: str) -> int:
    row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1",
        repository_key,
    )
    if row is None:
        raise ValueError(f"Repository not found: {repository_key}")
    return row["id"]


def classify_prompt(query: str) -> str:
    q = query.lower()
    if _EXACT_PATTERNS.search(query):
        return "exact_lookup"
    if any(kw in q for kw in _IMPACT_KEYWORDS):
        return "impact_analysis"
    if any(kw in q for kw in _DECISION_KEYWORDS):
        return "decision_history"
    if any(kw in q for kw in _PATTERN_KEYWORDS):
        return "pattern_search"
    return "conceptual_lookup"


async def load_route_policy(
    pool: asyncpg.Pool, prompt_class: str
) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        "SELECT * FROM routing.route_policies WHERE prompt_class = $1 LIMIT 1",
        prompt_class,
    )
    return dict(row) if row else None


async def load_retrieval_surfaces(
    pool: asyncpg.Pool, repository_id: int
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        "SELECT * FROM catalog.retrieval_surfaces WHERE repository_id = $1",
        repository_id,
    )
    return [dict(r) for r in rows]


async def pg_fulltext_search(
    pool: asyncpg.Pool,
    query: str,
    repository_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT c.id AS chunk_id,
               c.entity_id,
               e.entity_key,
               c.title,
               c.content_text,
               c.chunk_type,
               c.line_start,
               c.line_end,
               f.file_path,
               ts_rank(c.content_tsv, plainto_tsquery('english', $1)) AS rank
        FROM catalog.chunks c
        JOIN catalog.files f ON c.file_id = f.id
        JOIN catalog.entities e ON c.entity_id = e.id
        WHERE e.repository_id = $2
          AND c.content_tsv @@ plainto_tsquery('english', $1)
        ORDER BY rank DESC
        LIMIT $3
        """,
        query,
        repository_id,
        limit,
    )
    return [dict(r) for r in rows]


async def embed_query(query: str, settings: Settings) -> list[float]:
    if settings.auth_mode == "codex":
        from memory_knowledge.auth.codex import codex_token_provider

        api_key = await codex_token_provider(settings.codex_auth_path)
    else:
        api_key = settings.openai_api_key
    client = AsyncOpenAI(api_key=api_key)
    try:
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=query,
            dimensions=settings.embedding_dimensions,
        )
    except openai.AuthenticationError:
        if settings.auth_mode == "codex":
            raise RuntimeError(
                "Codex OAuth token rejected by OpenAI API — run 'codex auth' to re-authenticate, "
                "or check that your ChatGPT Pro subscription includes API embedding access"
            )
        raise
    return response.data[0].embedding


async def qdrant_semantic_search(
    client: AsyncQdrantClient,
    query_embedding: list[float],
    repository_key: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    results = await client.query_points(
        collection_name="code_chunks",
        query=query_embedding,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="repository_key",
                    match=models.MatchValue(value=repository_key),
                ),
                models.FieldCondition(
                    key="is_active",
                    match=models.MatchValue(value=True),
                ),
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    return [
        {
            "entity_key": p.payload.get("entity_key") if p.payload else None,
            "score": p.score,
            "payload": p.payload or {},
        }
        for p in results.points
    ]


async def pg_summary_search(
    pool: asyncpg.Pool,
    query: str,
    repository_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Full-text search on catalog.summaries."""
    rows = await pool.fetch(
        """
        SELECT e.entity_key,
               s.summary_text,
               s.summary_level,
               ts_rank(s.summary_tsv, plainto_tsquery('english', $1)) AS rank
        FROM catalog.summaries s
        JOIN catalog.entities e ON s.entity_id = e.id
        WHERE e.repository_id = $2
          AND s.summary_tsv @@ plainto_tsquery('english', $1)
        ORDER BY rank DESC
        LIMIT $3
        """,
        query,
        repository_id,
        limit,
    )
    return [dict(r) for r in rows]


async def qdrant_summary_search(
    client: AsyncQdrantClient,
    query_embedding: list[float],
    repository_key: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Semantic search on summary_units Qdrant collection."""
    results = await client.query_points(
        collection_name="summary_units",
        query=query_embedding,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="repository_key",
                    match=models.MatchValue(value=repository_key),
                ),
                models.FieldCondition(
                    key="is_active",
                    match=models.MatchValue(value=True),
                ),
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    return [
        {
            "entity_key": p.payload.get("entity_key") if p.payload else None,
            "score": p.score,
            "summary_level": p.payload.get("summary_level") if p.payload else None,
            "payload": p.payload or {},
        }
        for p in results.points
    ]


async def neo4j_graph_expansion(
    driver: neo4j.AsyncDriver,
    entity_keys: list[str],
    depth: int = 1,
) -> list[dict[str, Any]]:
    if not entity_keys:
        return []
    # Neo4j does not support parameter substitution in relationship length
    # patterns — depth must be inlined. int() cast prevents injection.
    query = (
        f"MATCH (n)-[:CONTAINS|HAS_FILE*1..{int(depth)}]-(m) "
        f"WHERE n.entity_key IN $entity_keys "
        f"RETURN DISTINCT m.entity_key AS entity_key, labels(m) AS labels"
    )
    records, _, _ = await driver.execute_query(
        query,
        entity_keys=entity_keys,
    )
    return [{"entity_key": r["entity_key"], "labels": r["labels"]} for r in records]


def rerank_results(
    pg_results: list[dict[str, Any]],
    qdrant_results: list[dict[str, Any]],
    graph_entity_keys: list[str] | None = None,
    summary_pg_results: list[dict[str, Any]] | None = None,
    summary_qdrant_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}

    # Normalize PG ts_rank to 0-1
    max_rank = max((r["rank"] for r in pg_results), default=0) or 1e-9
    for r in pg_results:
        key = str(r["entity_key"])
        norm_score = float(r["rank"]) / max_rank
        scores[key] = {
            "entity_key": key,
            "pg_score": norm_score,
            "qdrant_score": 0.0,
            "graph_boost": 0.0,
            "source": "postgres",
            "data": r,
        }

    # Qdrant scores are already 0-1 cosine similarity
    for r in qdrant_results:
        key = str(r["entity_key"])
        if key in scores:
            scores[key]["qdrant_score"] = float(r["score"])
            scores[key]["source"] = "both"
        else:
            scores[key] = {
                "entity_key": key,
                "pg_score": 0.0,
                "qdrant_score": float(r["score"]),
                "graph_boost": 0.0,
                "source": "qdrant",
                "data": r.get("payload", {}),
            }

    # Small boost for graph-connected results
    if graph_entity_keys:
        for key in graph_entity_keys:
            if key in scores:
                scores[key]["graph_boost"] = 0.1

    # Add summary results with 0.8x weight
    SUMMARY_WEIGHT = 0.8
    if summary_pg_results:
        max_srank = max((r["rank"] for r in summary_pg_results), default=0) or 1e-9
        for r in summary_pg_results:
            key = str(r["entity_key"])
            norm = float(r["rank"]) / max_srank * SUMMARY_WEIGHT
            if key not in scores:
                scores[key] = {
                    "entity_key": key,
                    "pg_score": norm,
                    "qdrant_score": 0.0,
                    "graph_boost": 0.0,
                    "source": "summary",
                    "data": r,
                }
            else:
                scores[key]["pg_score"] = max(scores[key]["pg_score"], norm)

    if summary_qdrant_results:
        for r in summary_qdrant_results:
            key = str(r["entity_key"])
            score = float(r["score"]) * SUMMARY_WEIGHT
            if key not in scores:
                scores[key] = {
                    "entity_key": key,
                    "pg_score": 0.0,
                    "qdrant_score": score,
                    "graph_boost": 0.0,
                    "source": "summary",
                    "data": r.get("payload", {}),
                }
            else:
                scores[key]["qdrant_score"] = max(scores[key]["qdrant_score"], score)

    # Combined score and sort
    for entry in scores.values():
        entry["combined_score"] = (
            entry["pg_score"] + entry["qdrant_score"] + entry["graph_boost"]
        )

    ranked = sorted(scores.values(), key=lambda x: x["combined_score"], reverse=True)
    return ranked


async def assemble_context_bundle(
    pool: asyncpg.Pool,
    ranked_results: list[dict[str, Any]],
    repository_key: str,
    commit_sha: str | None = None,
    branch_name: str | None = None,
) -> dict[str, Any]:
    # Filter to valid UUID strings only — Qdrant payloads may have None or malformed keys
    raw_keys = [r["entity_key"] for r in ranked_results[:20]]
    entity_keys = []
    for k in raw_keys:
        if k is None:
            continue
        try:
            uuid.UUID(str(k))
            entity_keys.append(str(k))
        except ValueError:
            continue
    if not entity_keys:
        return {"repository_key": repository_key, "evidence": [], "count": 0}

    # Hydrate: chunks from PG
    rows = await pool.fetch(
        """
        SELECT e.entity_key,
               c.title,
               c.content_text,
               c.chunk_type,
               c.line_start,
               c.line_end,
               f.file_path,
               s.symbol_name,
               s.symbol_kind
        FROM catalog.entities e
        JOIN catalog.chunks c ON c.entity_id = e.id
        JOIN catalog.files f ON c.file_id = f.id
        LEFT JOIN catalog.symbols s ON s.entity_id = e.id
        WHERE e.entity_key = ANY($1::uuid[])
        """,
        entity_keys,
    )

    # Hydrate: summaries from PG (for summary entity_keys that have no chunks)
    summary_rows = await pool.fetch(
        """
        SELECT e.entity_key,
               sm.summary_text,
               sm.summary_level
        FROM catalog.summaries sm
        JOIN catalog.entities e ON sm.entity_id = e.id
        WHERE e.entity_key = ANY($1::uuid[])
        """,
        entity_keys,
    )

    # Build lookup from chunk hydration
    hydrated = {}
    for row in rows:
        key = str(row["entity_key"])
        hydrated[key] = {
            "entity_key": key,
            "title": row["title"],
            "content_text": row["content_text"],
            "chunk_type": row["chunk_type"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "file_path": row["file_path"],
            "symbol_name": row["symbol_name"],
            "symbol_kind": row["symbol_kind"],
        }

    # Add summary hydration (for entity_keys not found in chunks)
    for row in summary_rows:
        key = str(row["entity_key"])
        if key not in hydrated:
            hydrated[key] = {
                "entity_key": key,
                "content_text": row["summary_text"],
                "content_kind": "summary",
                "summary_level": row["summary_level"],
            }

    # Merge ranked scores with hydrated data — only include valid entity_keys
    evidence = []
    for r in ranked_results[:20]:
        key = r["entity_key"]
        if key not in entity_keys:
            continue
        item = dict(hydrated.get(key, {"entity_key": key}))
        item["retrieval_score"] = r.get("combined_score", 0)
        item["retrieval_reason"] = r.get("source", "unknown")
        item["source_store"] = r.get("source", "unknown")
        if commit_sha:
            item["commit_sha"] = commit_sha
        if branch_name:
            item["branch_name"] = branch_name
        evidence.append(item)

    return {
        "repository_key": repository_key,
        "evidence": evidence,
        "count": len(evidence),
    }


async def persist_route_execution(
    pool: asyncpg.Pool,
    run_id: uuid.UUID,
    repository_id: int,
    prompt_text: str,
    prompt_class: str,
    route_policy_id: int | None,
    first_store_queried: str,
    stores_queried: list[str],
    fanout_used: bool,
    graph_expansion_used: bool,
    rerank_strategy: str,
    result_count: int,
    duration_ms: int,
) -> None:
    await pool.execute(
        """
        INSERT INTO routing.route_executions
            (run_id, repository_id, prompt_text, prompt_class, route_policy_id,
             first_store_queried, stores_queried, fanout_used, graph_expansion_used,
             rerank_strategy, result_count, duration_ms)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """,
        run_id,
        repository_id,
        prompt_text,
        prompt_class,
        route_policy_id,
        first_store_queried,
        stores_queried,
        fanout_used,
        graph_expansion_used,
        rerank_strategy,
        result_count,
        duration_ms,
    )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def run(
    repository_key: str,
    query: str,
    run_id: uuid.UUID,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    start = time.monotonic()

    try:
        if pool is None or qdrant_client is None or settings is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error="Missing required dependencies (pool, qdrant_client, settings).",
            )

        # Step 0: Resolve repository
        repository_id = await resolve_repository(pool, repository_key)
        logger.info("repository_resolved", repository_key=repository_key, repository_id=repository_id)

        # Step 1: Classify prompt
        prompt_class = classify_prompt(query)
        logger.info("prompt_classified", prompt_class=prompt_class)

        # Step 2: Load route policy and retrieval surfaces
        policy = await load_route_policy(pool, prompt_class)
        surfaces = await load_retrieval_surfaces(pool, repository_id)
        policy_id = policy["id"] if policy else None
        first_store = policy["first_store"] if policy else "postgres"
        second_store = policy["second_store"] if policy else None
        allow_fanout = policy["allow_fanout"] if policy else False
        allow_graph = policy["allow_graph_expansion"] if policy else False
        logger.info("policy_loaded", policy_name=policy["policy_name"] if policy else "none")

        # Extract active surface metadata for context bundle
        active_surface = next((s for s in surfaces if s["is_default"]), None)
        surface_commit_sha = active_surface["commit_sha"] if active_surface else None
        surface_branch_name = active_surface["branch_name"] if active_surface else None

        # Step 3: Query first store
        FANOUT_THRESHOLD = 5
        stores_queried = [first_store]
        pg_results: list[dict[str, Any]] = []
        qdrant_results: list[dict[str, Any]] = []
        query_embedding: list[float] | None = None

        if first_store == "postgres":
            pg_results = await pg_fulltext_search(pool, query, repository_id)
            logger.info("pg_search_complete", result_count=len(pg_results))
        elif first_store == "qdrant":
            query_embedding = await embed_query(query, settings)
            qdrant_results = await qdrant_semantic_search(
                qdrant_client, query_embedding, repository_key
            )
            logger.info("qdrant_search_complete", result_count=len(qdrant_results))

        # Step 4: Conditional fan-out to second store
        first_store_count = len(pg_results) + len(qdrant_results)
        fanout_used = False

        if allow_fanout and first_store_count < FANOUT_THRESHOLD and second_store:
            fanout_used = True
            stores_queried.append(second_store)
            if second_store == "postgres" and not pg_results:
                pg_results = await pg_fulltext_search(pool, query, repository_id)
                logger.info("fanout_pg_search", result_count=len(pg_results))
            elif second_store == "qdrant" and not qdrant_results:
                if query_embedding is None:
                    query_embedding = await embed_query(query, settings)
                qdrant_results = await qdrant_semantic_search(
                    qdrant_client, query_embedding, repository_key
                )
                logger.info("fanout_qdrant_search", result_count=len(qdrant_results))

        # Step 5: Optional Neo4j graph expansion
        graph_entity_keys: list[str] | None = None
        graph_expansion_used = False
        if allow_graph and neo4j_driver is not None:
            all_entity_keys = [
                str(r["entity_key"]) for r in pg_results
            ] + [
                str(r["entity_key"]) for r in qdrant_results if r.get("entity_key")
            ]
            if all_entity_keys:
                stores_queried.append("neo4j")
                graph_results = await neo4j_graph_expansion(
                    neo4j_driver, all_entity_keys[:10]
                )
                graph_entity_keys = [r["entity_key"] for r in graph_results]
                graph_expansion_used = True
                logger.info("graph_expansion_complete", expanded_count=len(graph_entity_keys))

        # Step 5.5: Summary searches
        summary_pg = await pg_summary_search(pool, query, repository_id)
        summary_qdrant: list[dict[str, Any]] = []
        if query_embedding is not None:
            summary_qdrant = await qdrant_summary_search(
                qdrant_client, query_embedding, repository_key
            )

        # Step 6: Rerank and fuse (including summaries at 0.8x weight)
        ranked = rerank_results(
            pg_results, qdrant_results, graph_entity_keys,
            summary_pg_results=summary_pg if summary_pg else None,
            summary_qdrant_results=summary_qdrant if summary_qdrant else None,
        )
        logger.info("rerank_complete", result_count=len(ranked))

        # Step 7: Assemble context bundle with surface metadata
        context_bundle = await assemble_context_bundle(
            pool, ranked, repository_key,
            commit_sha=surface_commit_sha,
            branch_name=surface_branch_name,
        )

        # Step 8: Persist route execution
        duration_ms = int((time.monotonic() - start) * 1000)
        await persist_route_execution(
            pool=pool,
            run_id=run_id,
            repository_id=repository_id,
            prompt_text=query,
            prompt_class=prompt_class,
            route_policy_id=policy_id,
            first_store_queried=first_store,
            stores_queried=stores_queried,
            fanout_used=fanout_used,
            graph_expansion_used=graph_expansion_used,
            rerank_strategy="score_sort",
            result_count=context_bundle["count"],
            duration_ms=duration_ms,
        )

        logger.info("retrieval_complete", duration_ms=duration_ms, result_count=context_bundle["count"])

        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="success",
            data=context_bundle,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("retrieval_failed", error=str(exc), duration_ms=duration_ms)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
