from __future__ import annotations

import time
import uuid
from typing import Any

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_impact_analysis_workflow"


async def _resolve_query_to_entity_key(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient | None,
    settings: Settings | None,
    repository_key: str,
    query: str,
) -> str | None:
    """Resolve a free-text query to an entity_key for graph traversal."""
    # Try 1: symbol name search
    row = await pool.fetchrow(
        """
        SELECT e.entity_key
        FROM catalog.symbols s
        JOIN catalog.entities e ON s.entity_id = e.id
        JOIN catalog.repositories r ON e.repository_id = r.id
        WHERE r.repository_key = $1 AND s.symbol_name ILIKE $2
        LIMIT 1
        """,
        repository_key,
        query.strip(),
    )
    if row:
        return str(row["entity_key"])

    # Try 2: file path search
    row = await pool.fetchrow(
        """
        SELECT e.entity_key
        FROM catalog.files f
        JOIN catalog.entities e ON f.entity_id = e.id
        JOIN catalog.repositories r ON e.repository_id = r.id
        WHERE r.repository_key = $1 AND f.file_path ILIKE '%' || $2 || '%'
        LIMIT 1
        """,
        repository_key,
        query.strip(),
    )
    if row:
        return str(row["entity_key"])

    # Try 3: Qdrant semantic search fallback
    if qdrant_client is not None and settings is not None:
        try:
            from memory_knowledge.workflows.retrieval import embed_query
            from qdrant_client import models

            embedding = await embed_query(query, settings)
            results = await qdrant_client.query_points(
                collection_name="code_chunks",
                query=embedding,
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
                limit=1,
                with_payload=True,
            )
            if results.points:
                return results.points[0].payload.get("entity_key") if results.points[0].payload else None
        except Exception as exc:
            logger.warning("semantic_fallback_failed", error=str(exc))

    return None


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
        if pool is None or neo4j_driver is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error="Missing required dependencies.",
            )

        # Step 1: Resolve query to entity_key
        entity_key = await _resolve_query_to_entity_key(
            pool, qdrant_client, settings, repository_key, query
        )
        if entity_key is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error=f"Could not resolve '{query}' to a known entity in {repository_key}.",
            )

        logger.info("entity_resolved", entity_key=entity_key, query=query)

        # Step 2: Scoped Neo4j traversal
        records, _, _ = await neo4j_driver.execute_query(
            """
            MATCH path = (start)-[:CALLS|IMPORTS|CONTAINS|HAS_FILE*1..3]-(affected)
            WHERE (start:File OR start:Symbol) AND start.entity_key = $ek
              AND (affected:File OR affected:Symbol)
            RETURN DISTINCT affected.entity_key AS entity_key,
                   labels(affected) AS labels,
                   length(path) AS distance
            ORDER BY distance
            """,
            ek=entity_key,
        )

        affected_keys = [str(r["entity_key"]) for r in records]
        logger.info("traversal_complete", affected_count=len(affected_keys))

        # Step 3: Hydrate from PG
        affected: list[dict[str, Any]] = []
        if affected_keys:
            hydrated_rows = await pool.fetch(
                """
                SELECT e.entity_key, e.entity_type,
                       f.file_path, s.symbol_name, s.symbol_kind
                FROM catalog.entities e
                LEFT JOIN catalog.files f ON f.entity_id = e.id AND e.entity_type = 'file'
                LEFT JOIN catalog.symbols s ON s.entity_id = e.id AND e.entity_type = 'symbol'
                WHERE e.entity_key = ANY($1::uuid[])
                """,
                affected_keys,
            )
            hydrated_map = {str(r["entity_key"]): r for r in hydrated_rows}

            for rec in records:
                key = str(rec["entity_key"])
                dist = rec["distance"]
                h = hydrated_map.get(key, {})
                affected.append({
                    "entity_key": key,
                    "entity_type": h.get("entity_type", "unknown") if h else "unknown",
                    "file_path": h.get("file_path") if h else None,
                    "symbol_name": h.get("symbol_name") if h else None,
                    "symbol_kind": h.get("symbol_kind") if h else None,
                    "distance": dist,
                    "labels": rec["labels"],
                })

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("impact_analysis_complete", duration_ms=duration_ms, affected_count=len(affected))

        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="success",
            data={
                "start_entity_key": entity_key,
                "query": query,
                "affected": affected,
                "count": len(affected),
            },
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("impact_analysis_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
