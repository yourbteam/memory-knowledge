from __future__ import annotations

import asyncpg
import neo4j
import structlog
from pydantic import BaseModel

logger = structlog.get_logger()

BATCH_SIZE = 100


class PgNeo4jReport(BaseModel):
    total_files: int = 0
    total_symbols: int = 0
    missing_file_nodes: list[str] = []
    missing_symbol_nodes: list[str] = []
    missing_edges: int = 0


async def check_pg_neo4j(
    pool: asyncpg.Pool,
    neo4j_driver: neo4j.AsyncDriver,
    repository_key: str,
) -> PgNeo4jReport:
    """Check alignment between PG file/symbol entities and Neo4j nodes."""
    report = PgNeo4jReport()

    # Check file nodes
    offset = 0
    while True:
        rows = await pool.fetch(
            """
            SELECT e.entity_key
            FROM catalog.entities e
            JOIN catalog.repositories r ON e.repository_id = r.id
            WHERE r.repository_key = $1 AND e.entity_type = 'file'
            ORDER BY e.id
            LIMIT $2 OFFSET $3
            """,
            repository_key,
            BATCH_SIZE,
            offset,
        )
        if not rows:
            break

        report.total_files += len(rows)
        keys = [str(r["entity_key"]) for r in rows]

        try:
            records, _, _ = await neo4j_driver.execute_query(
                "UNWIND $keys AS k MATCH (n:File {entity_key: k}) RETURN n.entity_key AS ek",
                keys=keys,
            )
            found = {r["ek"] for r in records}
            for key in keys:
                if key not in found:
                    report.missing_file_nodes.append(key)
        except Exception as exc:
            logger.error("neo4j_file_check_failed", error=str(exc))

        offset += BATCH_SIZE

    # Check symbol nodes
    offset = 0
    while True:
        rows = await pool.fetch(
            """
            SELECT e.entity_key
            FROM catalog.entities e
            JOIN catalog.repositories r ON e.repository_id = r.id
            WHERE r.repository_key = $1 AND e.entity_type = 'symbol'
            ORDER BY e.id
            LIMIT $2 OFFSET $3
            """,
            repository_key,
            BATCH_SIZE,
            offset,
        )
        if not rows:
            break

        report.total_symbols += len(rows)
        keys = [str(r["entity_key"]) for r in rows]

        try:
            records, _, _ = await neo4j_driver.execute_query(
                "UNWIND $keys AS k MATCH (n:Symbol {entity_key: k}) RETURN n.entity_key AS ek",
                keys=keys,
            )
            found = {r["ek"] for r in records}
            for key in keys:
                if key not in found:
                    report.missing_symbol_nodes.append(key)
        except Exception as exc:
            logger.error("neo4j_symbol_check_failed", error=str(exc))

        offset += BATCH_SIZE

    # Sample relationship check — verify HAS_FILE edges for found file nodes
    if report.total_files > 0 and not report.missing_file_nodes:
        try:
            records, _, _ = await neo4j_driver.execute_query(
                """
                MATCH (f:File)
                WHERE NOT (f)<-[:HAS_FILE]-(:Revision)
                RETURN count(f) AS orphan_count
                """,
            )
            report.missing_edges = records[0]["orphan_count"] if records else 0
        except Exception as exc:
            logger.error("neo4j_edge_check_failed", error=str(exc))

    logger.info(
        "pg_neo4j_check_complete",
        files=report.total_files,
        symbols=report.total_symbols,
        missing_files=len(report.missing_file_nodes),
        missing_symbols=len(report.missing_symbol_nodes),
        missing_edges=report.missing_edges,
    )
    return report
