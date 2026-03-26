from __future__ import annotations

import time
import uuid
from typing import Any

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.workflows import retrieval as _retrieval
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_context_assembly_workflow"


async def _fetch_applicable_learned_rules(
    pool: asyncpg.Pool,
    neo4j_driver: neo4j.AsyncDriver | None,
    entity_keys: list[str],
    repository_id: int,
) -> list[dict[str, Any]]:
    """Fetch learned rules that apply to entities in the result set."""
    rules: list[dict[str, Any]] = []

    # Try Neo4j APPLIES_TO edges first
    if neo4j_driver is not None and entity_keys:
        try:
            records, _, _ = await neo4j_driver.execute_query(
                """
                MATCH (lr:LearnedRule)-[:APPLIES_TO]->(scope)
                WHERE scope.entity_key IN $entity_keys AND lr.is_active = true
                RETURN lr.entity_key AS entity_key, lr.title AS title,
                       lr.memory_type AS memory_type
                """,
                entity_keys=entity_keys,
            )
            for r in records:
                rules.append({
                    "entity_key": r["entity_key"],
                    "title": r["title"],
                    "memory_type": r["memory_type"],
                    "source": "neo4j",
                })
        except Exception:
            pass  # LearnedRule label may not exist yet — graceful degradation

    # Also query PG for active rules in this repository
    try:
        rows = await pool.fetch(
            """
            SELECT e.entity_key, lr.title, lr.memory_type, lr.confidence,
                   lr.applicability_mode, lr.body_text
            FROM memory.learned_records lr
            JOIN catalog.entities e ON lr.entity_id = e.id
            WHERE e.repository_id = $1 AND lr.is_active = TRUE
              AND lr.verification_status = 'verified'
            ORDER BY lr.confidence DESC
            LIMIT 20
            """,
            repository_id,
        )
        seen = {r["entity_key"] for r in rules}
        for row in rows:
            key = str(row["entity_key"])
            if key not in seen:
                rules.append({
                    "entity_key": key,
                    "title": row["title"],
                    "memory_type": row["memory_type"],
                    "confidence": float(row["confidence"]) if row["confidence"] else None,
                    "applicability_mode": row["applicability_mode"],
                    "body_text": row["body_text"],
                    "source": "postgres",
                })
    except Exception:
        pass  # table may be empty — graceful degradation

    return rules


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
        if pool is None or settings is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error="Missing required dependencies.",
            )

        # Step 1: Run retrieval to get raw results
        retrieval_result = await _retrieval.run(
            repository_key, query, run_id,
            pool=pool, qdrant_client=qdrant_client,
            neo4j_driver=neo4j_driver, settings=settings,
        )

        if retrieval_result.status != "success":
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error=f"Retrieval failed: {retrieval_result.error}",
            )

        evidence = retrieval_result.data.get("evidence", [])

        # Step 2: Resolve repository_id for learned rules query
        row = await pool.fetchrow(
            "SELECT id FROM catalog.repositories WHERE repository_key = $1",
            repository_key,
        )
        repository_id = row["id"] if row else 0

        # Step 3: Resolve file/symbol entity_keys for learned rules lookup
        # Retrieval returns chunk entity_keys, but learned rules APPLY_TO
        # file/symbol entities. Resolve via file_path → catalog.files → entity_key.
        file_paths = list({e["file_path"] for e in evidence if e.get("file_path")})
        scope_entity_keys: list[str] = []
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

        learned_rules = await _fetch_applicable_learned_rules(
            pool, neo4j_driver, scope_entity_keys, repository_id,
        )

        # Step 4: Assemble structured bundle
        exact_matches = [e for e in evidence if e.get("source_store") == "postgres"]
        semantic_matches = [e for e in evidence if e.get("source_store") == "qdrant"]
        graph_expansions = [e for e in evidence if e.get("source_store") == "both"]
        summary_evidence = [e for e in evidence if e.get("source_store") == "summary"]

        duration_ms = int((time.monotonic() - start) * 1000)

        bundle = {
            "repository_key": repository_key,
            "exact_matches": exact_matches,
            "semantic_matches": semantic_matches,
            "graph_expansions": graph_expansions,
            "summary_evidence": summary_evidence,
            "applicable_learned_rules": learned_rules,
            "route_metadata": {
                "query": query,
                "duration_ms": duration_ms,
            },
            "total_evidence": len(evidence),
        }

        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="success",
            data=bundle,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("context_assembly_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
