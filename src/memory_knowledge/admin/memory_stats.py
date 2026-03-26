from __future__ import annotations

from typing import Any

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.db.qdrant import COLLECTIONS

logger = structlog.get_logger()


async def collect_memory_stats(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    neo4j_driver: neo4j.AsyncDriver,
    repository_key: str,
) -> dict[str, Any]:
    """Collect comprehensive memory architecture statistics for a repository."""
    stats: dict[str, Any] = {"repository_key": repository_key}

    # PG: Entity counts by type
    try:
        entity_rows = await pool.fetch(
            """
            SELECT e.entity_type, COUNT(*) AS cnt
            FROM catalog.entities e
            JOIN catalog.repositories r ON e.repository_id = r.id
            WHERE r.repository_key = $1
            GROUP BY e.entity_type
            """,
            repository_key,
        )
        stats["entity_counts"] = {r["entity_type"]: r["cnt"] for r in entity_rows}
    except Exception as exc:
        stats["entity_counts"] = {"error": str(exc)}

    # PG: Learned record counts by status
    try:
        lr_rows = await pool.fetch(
            """
            SELECT lr.verification_status, lr.is_active, COUNT(*) AS cnt
            FROM memory.learned_records lr
            JOIN catalog.entities e ON lr.entity_id = e.id
            JOIN catalog.repositories r ON e.repository_id = r.id
            WHERE r.repository_key = $1
            GROUP BY lr.verification_status, lr.is_active
            """,
            repository_key,
        )
        stats["learned_records"] = [
            {
                "verification_status": r["verification_status"],
                "is_active": r["is_active"],
                "count": r["cnt"],
            }
            for r in lr_rows
        ]
    except Exception as exc:
        stats["learned_records"] = {"error": str(exc)}

    # PG: Recent ingestion runs
    try:
        run_rows = await pool.fetch(
            """
            SELECT ir.id, ir.commit_sha, ir.branch_name, ir.run_type,
                   ir.status, ir.started_utc, ir.completed_utc
            FROM ops.ingestion_runs ir
            JOIN catalog.repositories r ON ir.repository_id = r.id
            WHERE r.repository_key = $1
            ORDER BY ir.id DESC LIMIT 10
            """,
            repository_key,
        )
        stats["recent_ingestion_runs"] = [
            {
                "id": r["id"],
                "commit_sha": r["commit_sha"],
                "run_type": r["run_type"],
                "status": r["status"],
                "started_utc": r["started_utc"].isoformat() if r["started_utc"] else None,
                "completed_utc": r["completed_utc"].isoformat() if r["completed_utc"] else None,
            }
            for r in run_rows
        ]
    except Exception as exc:
        stats["recent_ingestion_runs"] = {"error": str(exc)}

    # Qdrant: Point counts per collection
    qdrant_stats: dict[str, int] = {}
    for coll_name in COLLECTIONS:
        try:
            count_result = await qdrant_client.count(
                collection_name=coll_name,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="repository_key",
                            match=models.MatchValue(value=repository_key),
                        ),
                    ]
                ),
            )
            qdrant_stats[coll_name] = count_result.count
        except Exception:
            qdrant_stats[coll_name] = -1  # error indicator
    stats["qdrant_points"] = qdrant_stats

    # Neo4j: Node and edge counts
    try:
        neo4j_records, _, _ = await neo4j_driver.execute_query(
            """
            MATCH (n)
            WHERE n.entity_key IS NOT NULL
            RETURN labels(n)[0] AS label, COUNT(n) AS cnt
            """,
        )
        stats["neo4j_nodes"] = {r["label"]: r["cnt"] for r in neo4j_records}

        edge_records, _, _ = await neo4j_driver.execute_query(
            "MATCH ()-[r]->() RETURN type(r) AS rel_type, COUNT(r) AS cnt",
        )
        stats["neo4j_edges"] = {r["rel_type"]: r["cnt"] for r in edge_records}
    except Exception as exc:
        stats["neo4j_nodes"] = {"error": str(exc)}
        stats["neo4j_edges"] = {"error": str(exc)}

    return stats
