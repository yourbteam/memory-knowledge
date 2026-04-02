from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.llm.openai_client import embed_single
from memory_knowledge.projections.pg_writer import record_route_feedback
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_retrieval_workflow"

from memory_knowledge.routing.prompt_feature_extractor import (
    extract_prompt_features,
    match_archetype,
)


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


def classify_prompt(query: str) -> tuple[str, float]:
    """Classify a prompt into a routing category.

    Returns (prompt_class, confidence) where confidence is 0.0-1.0.
    Strong keyword matches get 1.0, default fallback gets 0.5.
    """
    features = extract_prompt_features(query)
    # Graph-first for traversal queries
    if features.get("has_traversal_phrases"):
        return "impact_analysis", 1.0
    # Mixed when multiple keyword categories match
    keyword_hits = sum([
        features["has_impact_keywords"],
        features["has_decision_keywords"],
        features["has_pattern_keywords"],
    ])
    if keyword_hits >= 2:
        return "mixed", 0.7
    if features["identifier_count"] > 0:
        return "exact_lookup", 1.0
    if features["has_impact_keywords"]:
        return "impact_analysis", 1.0
    if features["has_decision_keywords"]:
        return "decision_history", 1.0
    if features["has_pattern_keywords"]:
        return "pattern_search", 1.0
    return "conceptual_lookup", 0.5


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


def _clean_query_for_fulltext(query: str) -> str:
    """Strip file paths from query so PG full-text searches remaining terms.

    'config/app.php timezone' → 'timezone'
    'image_created_at column' → 'image_created_at column' (snake_case kept — valid search term)
    """
    import re
    # Remove file paths (word/word.ext patterns) that break plainto_tsquery
    cleaned = re.sub(r"(?<!/)(?<!//)[\w]+(?:/[\w.]+)+", " ", query)
    return " ".join(cleaned.split())  # normalize whitespace


async def pg_fulltext_search(
    pool: asyncpg.Pool,
    query: str,
    repository_id: int,
    limit: int = 40,
) -> list[dict[str, Any]]:
    # Extract file paths from query for path-based matching
    import re
    file_paths = re.findall(r"(?<!/)(?<!//)[\w]+(?:/[\w.]+)+", query)
    search_text = _clean_query_for_fulltext(query)

    # Two-pronged search: full-text on cleaned query OR file path match
    if file_paths and search_text.strip():
        # Search by content AND by file path
        rows = await pool.fetch(
            """
            SELECT c.id AS chunk_id, c.entity_id, e.entity_key, c.title,
                   c.content_text, c.chunk_type, c.line_start, c.line_end,
                   f.file_path,
                   ts_rank(c.content_tsv, plainto_tsquery('english', $1))
                   + CASE WHEN f.file_path = ANY($4::text[]) THEN 1.0 ELSE 0.0 END
                   AS rank
            FROM catalog.chunks c
            JOIN catalog.files f ON c.file_id = f.id
            JOIN catalog.entities e ON c.entity_id = e.id
            WHERE e.repository_id = $2
              AND (c.content_tsv @@ plainto_tsquery('english', $1)
                   OR f.file_path = ANY($4::text[]))
            ORDER BY rank DESC
            LIMIT $3
            """,
            search_text,
            repository_id,
            limit,
            file_paths,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT c.id AS chunk_id, c.entity_id, e.entity_key, c.title,
                   c.content_text, c.chunk_type, c.line_start, c.line_end,
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
    """Embed a single query string with retry."""
    return await embed_single(query, settings)


async def qdrant_semantic_search(
    client: AsyncQdrantClient,
    query_embedding: list[float],
    repository_key: str,
    limit: int = 40,
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
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Full-text search on catalog.summaries."""
    search_text = _clean_query_for_fulltext(query)
    if not search_text.strip():
        search_text = query  # fallback to raw query if cleaning removed everything
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
        search_text,
        repository_id,
        limit,
    )
    return [dict(r) for r in rows]


async def qdrant_summary_search(
    client: AsyncQdrantClient,
    query_embedding: list[float],
    repository_key: str,
    limit: int = 20,
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
    depth: int = 2,
) -> list[dict[str, Any]]:
    if not entity_keys:
        return []
    # Two traversals: structural (siblings) + dependency (callees)
    # Structural: undirected CONTAINS/HAS_FILE for sibling symbols and parent files
    # Dependency: directed CALLS/IMPORTS outbound to find what the code depends on
    d = int(depth)
    records, _, _ = await driver.execute_query(
        f"MATCH (n)-[:CONTAINS|HAS_FILE*1..{d}]-(m) "
        f"WHERE n.entity_key IN $entity_keys AND m.entity_key IS NOT NULL "
        f"RETURN DISTINCT m.entity_key AS entity_key, labels(m) AS labels "
        f"LIMIT 100 "
        f"UNION "
        f"MATCH (n)-[:CALLS|IMPORTS*1..{d}]->(m) "
        f"WHERE n.entity_key IN $entity_keys AND m.entity_key IS NOT NULL "
        f"RETURN DISTINCT m.entity_key AS entity_key, labels(m) AS labels "
        f"LIMIT 100",
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

    # Boost graph-connected results AND add new graph-discovered entities
    if graph_entity_keys:
        for key in graph_entity_keys:
            if key in scores:
                scores[key]["graph_boost"] = 0.1
            else:
                # New entity discovered via graph traversal — add with graph-only score
                scores[key] = {
                    "entity_key": key,
                    "pg_score": 0.0,
                    "qdrant_score": 0.0,
                    "graph_boost": 0.3,
                    "source": "graph",
                    "data": {},
                }

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
    raw_keys = [r["entity_key"] for r in ranked_results[:40]]
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
    for r in ranked_results[:40]:
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


# ── Auto-feedback heuristics ────────────────────────────────────────

_CLASS_PROFILES: dict[str, dict[str, tuple[int, int]]] = {
    "exact_lookup":      {"ideal_range": (1, 5)},
    "conceptual_lookup": {"ideal_range": (5, 20)},
    "impact_analysis":   {"ideal_range": (3, 15)},
    "pattern_search":    {"ideal_range": (5, 20)},
    "decision_history":  {"ideal_range": (1, 10)},
    "mixed":             {"ideal_range": (5, 20)},
}


def compute_auto_feedback(
    ranked_results: list[dict[str, Any]],
    result_count: int,
    fanout_used: bool,
    graph_expansion_used: bool,
    stores_queried: list[str],
    prompt_class: str,
    duration_ms: int,
) -> dict[str, Any]:
    """Compute heuristic feedback signals from retrieval results.

    Pure function — no DB, no LLM, no async. Returns a dict with keys:
    usefulness_score, precision_score, expansion_needed, notes.
    """
    profile = _CLASS_PROFILES.get(prompt_class, _CLASS_PROFILES["mixed"])
    low, high = profile["ideal_range"]

    # ── usefulness_score (0.00–0.85) ──
    if result_count == 0:
        usefulness = 0.05
    elif low <= result_count <= high:
        usefulness = 0.70
    elif result_count < low:
        usefulness = 0.25 + 0.35 * (result_count / low)
    else:
        usefulness = 0.55 - 0.10 * min((result_count - high) / high, 1.0)

    if len(ranked_results) >= 3:
        avg_top3 = sum(r["combined_score"] for r in ranked_results[:3]) / 3
        if avg_top3 >= 1.0:
            usefulness = min(usefulness + 0.10, 0.85)

    # ── precision_score (0.00–0.85) ──
    top_5 = [r["combined_score"] for r in ranked_results[:5]]
    if not top_5:
        precision = 0.05
    else:
        avg_top5 = sum(top_5) / len(top_5)
        max_possible = max(len(stores_queried), 1)
        precision = min(avg_top5 / max_possible, 1.0) * 0.85

        if len(top_5) >= 2:
            spread = top_5[0] - top_5[-1]
            if spread > 0.5:
                precision = min(precision + 0.10, 0.85)

    # ── expansion_needed ──
    expansion_needed = (
        result_count < low
        and not fanout_used
        and not graph_expansion_used
    )

    # ── notes ──
    top_score = ranked_results[0]["combined_score"] if ranked_results else 0.0
    notes = (
        f"[auto] class={prompt_class} results={result_count} "
        f"stores={','.join(stores_queried)} "
        f"fanout={'Y' if fanout_used else 'N'} "
        f"graph={'Y' if graph_expansion_used else 'N'} "
        f"top_score={top_score:.2f} duration={duration_ms}ms"
    )

    return {
        "usefulness_score": round(usefulness, 2),
        "precision_score": round(precision, 2),
        "expansion_needed": expansion_needed,
        "notes": notes,
    }


async def _persist_auto_feedback(
    pool: asyncpg.Pool,
    route_execution_id: int,
    feedback: dict[str, Any],
) -> None:
    """Fire-and-forget wrapper — logs warnings on failure, never raises."""
    try:
        await record_route_feedback(
            pool, route_execution_id,
            usefulness_score=feedback["usefulness_score"],
            precision_score=feedback["precision_score"],
            expansion_needed=feedback["expansion_needed"],
            notes=feedback["notes"],
            is_auto=True,
        )
        logger.debug("auto_feedback_recorded", route_execution_id=route_execution_id)
    except Exception:
        logger.warning(
            "auto_feedback_failed",
            route_execution_id=route_execution_id,
            exc_info=True,
        )


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
) -> int | None:
    row = await pool.fetchrow(
        """
        INSERT INTO routing.route_executions
            (run_id, repository_id, prompt_text, prompt_class, route_policy_id,
             first_store_queried, stores_queried, fanout_used, graph_expansion_used,
             rerank_strategy, result_count, duration_ms)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        RETURNING id
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
    return row["id"] if row else None


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

        # Step 1: Classify prompt (keyword-based + optional archetype override)
        prompt_class, keyword_confidence = classify_prompt(query)

        # Try semantic archetype matching as override for low-confidence classification
        archetype = await match_archetype(query, qdrant_client, settings)
        if archetype and archetype.get("archetype_score", 0) > keyword_confidence:
            original_class = prompt_class
            prompt_class = archetype["prompt_class"]
            logger.info(
                "archetype_override",
                keyword_class=original_class,
                archetype_class=archetype["prompt_class"],
                archetype_score=archetype["archetype_score"],
            )

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

        # Freshness check
        from datetime import datetime, timezone, timedelta

        freshness_warning = None
        if active_surface is not None and active_surface.get("updated_utc"):
            age = datetime.now(timezone.utc) - active_surface["updated_utc"]
            if age > timedelta(hours=settings.max_surface_age_hours):
                hours_old = int(age.total_seconds() / 3600)
                freshness_warning = (
                    f"Data is {hours_old} hours old. "
                    f"Last ingestion: {active_surface['updated_utc'].isoformat()}"
                )
                logger.warning("stale_retrieval_surface", hours_old=hours_old)

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
                    neo4j_driver, all_entity_keys[:20]
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

        # Step 7.5: Surface applicable learned rules (best-effort, never crashes retrieval)
        learned_rules: list[dict[str, Any]] = []
        try:
            from memory_knowledge.workflows.context_assembly import (
                _fetch_applicable_learned_rules,
            )
            file_paths = list({
                e["file_path"] for e in context_bundle.get("evidence", [])
                if e.get("file_path")
            })
            if file_paths:
                scope_rows = await pool.fetch(
                    """
                    SELECT DISTINCT e.entity_key
                    FROM catalog.files f
                    JOIN catalog.entities e ON f.entity_id = e.id
                    WHERE f.file_path = ANY($1::text[])
                      AND e.repository_id = $2
                    """,
                    file_paths,
                    repository_id,
                )
                scope_entity_keys = [str(r["entity_key"]) for r in scope_rows]
                if scope_entity_keys:
                    learned_rules = await _fetch_applicable_learned_rules(
                        pool, neo4j_driver, scope_entity_keys, repository_id,
                    )
        except Exception:
            logger.warning("learned_rules_fetch_failed", exc_info=True)
        context_bundle["applicable_learned_rules"] = learned_rules

        # Step 8: Persist route execution (skipped in remote read-only mode)
        duration_ms = int((time.monotonic() - start) * 1000)
        route_exec_id = None
        if not (settings and settings.is_any_remote() and not settings.allow_remote_writes):
            route_exec_id = await persist_route_execution(
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

        if route_exec_id is not None:
            context_bundle["route_execution_id"] = route_exec_id
            # Auto-generate heuristic feedback (fire-and-forget)
            feedback = compute_auto_feedback(
                ranked_results=ranked,
                result_count=context_bundle["count"],
                fanout_used=fanout_used,
                graph_expansion_used=graph_expansion_used,
                stores_queried=stores_queried,
                prompt_class=prompt_class,
                duration_ms=duration_ms,
            )
            asyncio.create_task(_persist_auto_feedback(pool, route_exec_id, feedback))
        if freshness_warning:
            context_bundle["freshness_warning"] = freshness_warning

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
