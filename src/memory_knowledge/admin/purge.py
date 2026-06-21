from __future__ import annotations

from typing import Any

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.db.qdrant import COLLECTIONS

logger = structlog.get_logger()


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    schema, table = table_name.split(".", 1)
    row = await conn.fetchrow(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = $1
          AND table_name = $2
        """,
        schema,
        table,
    )
    return row is not None


async def _delete_if_exists(
    conn: asyncpg.Connection,
    table_name: str,
    sql: str,
    *args: Any,
) -> int:
    if not await _table_exists(conn, table_name):
        return 0
    result = await conn.execute(sql, *args)
    try:
        return int(result.rsplit(" ", 1)[-1])
    except (IndexError, ValueError):
        return 0


async def _purge_postgres(pool: asyncpg.Pool, repository_key: str, repository_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}

    async with pool.acquire() as conn:
        async with conn.transaction():
            run_ids = [
                row["id"]
                for row in await conn.fetch("SELECT id FROM ops.ingestion_runs WHERE repository_id = $1", repository_id)
            ]
            route_ids = [
                row["id"]
                for row in await conn.fetch(
                    "SELECT id FROM routing.route_executions WHERE repository_id = $1",
                    repository_id,
                )
            ]

            async def delete(table_name: str, sql: str, *args: Any) -> None:
                counts[table_name] = await _delete_if_exists(conn, table_name, sql, *args)

            await delete(
                "ops.ingestion_run_items",
                "DELETE FROM ops.ingestion_run_items WHERE ingestion_run_id = ANY($1::bigint[])",
                run_ids,
            )
            await delete("ops.ingestion_runs", "DELETE FROM ops.ingestion_runs WHERE repository_id = $1", repository_id)
            await delete(
                "ops.ingestion_checkpoints",
                "DELETE FROM ops.ingestion_checkpoints WHERE repository_id = $1",
                repository_id,
            )
            await delete(
                "ops.job_manifests",
                "DELETE FROM ops.job_manifests WHERE repository_key = $1",
                repository_key,
            )

            await delete(
                "routing.route_feedback",
                "DELETE FROM routing.route_feedback WHERE route_execution_id = ANY($1::bigint[])",
                route_ids,
            )
            await delete(
                "routing.route_executions",
                "DELETE FROM routing.route_executions WHERE repository_id = $1",
                repository_id,
            )

            await delete("memory.qa_pairs", "DELETE FROM memory.qa_pairs WHERE repository_id = $1", repository_id)
            await delete(
                "memory.working_observations",
                """
                DELETE FROM memory.working_observations wo
                USING memory.working_sessions ws
                WHERE wo.session_id = ws.id
                  AND ws.repository_id = $1
                """,
                repository_id,
            )
            await delete(
                "memory.working_sessions",
                "DELETE FROM memory.working_sessions WHERE repository_id = $1",
                repository_id,
            )
            await delete(
                "memory.learned_records",
                """
                UPDATE memory.learned_records lr
                SET supersedes_learned_record_id = NULL
                FROM catalog.entities e
                WHERE lr.entity_id = e.id
                  AND e.repository_id = $1
                """,
                repository_id,
            )
            await delete(
                "memory.learned_records",
                """
                DELETE FROM memory.learned_records lr
                USING catalog.entities e
                WHERE lr.entity_id = e.id
                  AND e.repository_id = $1
                """,
                repository_id,
            )

            await delete(
                "catalog.file_imports_file",
                """
                DELETE FROM catalog.file_imports_file fif
                USING catalog.files f, catalog.entities e
                WHERE fif.importer_file_id = f.id
                  AND f.entity_id = e.id
                  AND e.repository_id = $1
                """,
                repository_id,
            )
            await delete(
                "catalog.symbol_calls_symbol",
                """
                DELETE FROM catalog.symbol_calls_symbol scs
                USING catalog.symbols s, catalog.entities e
                WHERE scs.caller_symbol_id = s.id
                  AND s.entity_id = e.id
                  AND e.repository_id = $1
                """,
                repository_id,
            )
            await delete(
                "catalog.summaries",
                """
                DELETE FROM catalog.summaries s
                USING catalog.entities e
                WHERE s.entity_id = e.id
                  AND e.repository_id = $1
                """,
                repository_id,
            )
            await delete(
                "catalog.chunks",
                """
                DELETE FROM catalog.chunks c
                USING catalog.entities e
                WHERE c.entity_id = e.id
                  AND e.repository_id = $1
                """,
                repository_id,
            )
            await delete(
                "catalog.symbols",
                """
                DELETE FROM catalog.symbols s
                USING catalog.entities e
                WHERE s.entity_id = e.id
                  AND e.repository_id = $1
                """,
                repository_id,
            )
            await delete(
                "catalog.files",
                """
                DELETE FROM catalog.files f
                USING catalog.entities e
                WHERE f.entity_id = e.id
                  AND e.repository_id = $1
                """,
                repository_id,
            )
            await delete(
                "catalog.entities",
                "DELETE FROM catalog.entities WHERE repository_id = $1",
                repository_id,
            )
            await delete(
                "catalog.retrieval_surfaces",
                "DELETE FROM catalog.retrieval_surfaces WHERE repository_id = $1",
                repository_id,
            )
            await delete(
                "catalog.branch_heads",
                "DELETE FROM catalog.branch_heads WHERE repository_id = $1",
                repository_id,
            )
            await delete(
                "catalog.repo_revisions",
                "DELETE FROM catalog.repo_revisions WHERE repository_id = $1",
                repository_id,
            )

    return counts


async def _purge_qdrant(client: AsyncQdrantClient, repository_key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    flt = models.Filter(
        must=[
            models.FieldCondition(
                key="repository_key",
                match=models.MatchValue(value=repository_key),
            )
        ]
    )
    selector = models.FilterSelector(filter=flt)
    for collection in COLLECTIONS:
        try:
            before = await client.count(collection_name=collection, count_filter=flt, exact=True)
            if before.count:
                await client.delete(collection_name=collection, points_selector=selector)
            counts[collection] = int(before.count)
        except Exception as exc:
            logger.warning("qdrant_repo_purge_skipped", collection=collection, error=str(exc))
            counts[collection] = -1
    return counts


async def _purge_neo4j(driver: neo4j.AsyncDriver, repository_key: str) -> dict[str, int]:
    records, _, _ = await driver.execute_query(
        """
        MATCH (repo:Repository {entity_key: $repository_key})
        OPTIONAL MATCH (repo)-[:HAS_REVISION]->(rev:Revision)
        OPTIONAL MATCH (rev)-[:HAS_FILE]->(file:File)
        OPTIONAL MATCH (file)-[:CONTAINS]->(sym:Symbol)
        WITH collect(DISTINCT repo) + collect(DISTINCT rev) + collect(DISTINCT file) + collect(DISTINCT sym) AS nodes
        UNWIND nodes AS n
        WITH DISTINCT n
        WHERE n IS NOT NULL
        DETACH DELETE n
        RETURN count(n) AS deleted
        """,
        repository_key=repository_key,
    )
    deleted = int(records[0]["deleted"]) if records else 0
    return {"nodes": deleted}


async def purge_repository(
    *,
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    neo4j_driver: neo4j.AsyncDriver,
    repository_key: str,
) -> dict[str, Any]:
    """Purge repo-owned memory/projection data across PG, Qdrant, and Neo4j.

    The catalog.repositories row is intentionally retained so MAWF/planning
    references remain intact and the repo can be re-imported cleanly.
    """
    row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1",
        repository_key,
    )
    if row is None:
        raise ValueError(f"Repository not found: {repository_key}")

    repository_id = int(row["id"])

    # Isolate each store: one store failing must not abort the others or swallow the cause.
    # Capture repr(exc) so even empty-message exceptions reveal their type (root-causes the
    # previously-opaque "Error executing tool purge_repository:" blank failures).
    result: dict[str, Any] = {"repository_key": repository_key, "repository_id": repository_id}
    errors: dict[str, str] = {}

    try:
        result["postgres"] = await _purge_postgres(pool, repository_key, repository_id)
    except Exception as exc:  # noqa: BLE001 — per-store isolation + diagnostic capture
        errors["postgres"] = repr(exc)
        logger.error("purge_postgres_failed", repository_key=repository_key, error=repr(exc))
    try:
        result["qdrant"] = await _purge_qdrant(qdrant_client, repository_key)
    except Exception as exc:  # noqa: BLE001
        errors["qdrant"] = repr(exc)
        logger.error("purge_qdrant_failed", repository_key=repository_key, error=repr(exc))
    try:
        result["neo4j"] = await _purge_neo4j(neo4j_driver, repository_key)
    except Exception as exc:  # noqa: BLE001
        errors["neo4j"] = repr(exc)
        logger.error("purge_neo4j_failed", repository_key=repository_key, error=repr(exc))

    if errors:
        result["errors"] = errors
        logger.warning("repository_purge_partial", repository_key=repository_key, errors=errors)
    else:
        logger.info("repository_purged", **result)
    return result
