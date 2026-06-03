"""Compaction / GC — remove superseded (is_active=False) data the system never
serves, plus orphaned Neo4j nodes from old commits.

Destructive when dry_run=False. PG deletes are FK-safe: inactive chunks are
guarded against memory.learned_records.evidence_chunk_id; nothing references
catalog.summaries. Orphaned chunk/summary *entity* rows are intentionally left
(tiny; FK-entangled with ingestion_run_items/working_observations) — the storage
lives in chunks.content_text/tsv, which these deletes reclaim.
"""
from __future__ import annotations

import asyncpg
import neo4j
import structlog
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings

logger = structlog.get_logger()

BATCH_SIZE = 500


class CompactionReport(BaseModel):
    repository_key: str
    dry_run: bool
    pg_chunks_deleted: int = 0
    pg_summaries_deleted: int = 0
    qdrant_points_deleted: int = 0
    neo4j_nodes_deleted: int = 0
    skipped: list[str] = []
    errors: list[str] = []


def _affected(status: str) -> int:
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError):
        return 0


async def compact_repository(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    neo4j_driver: neo4j.AsyncDriver | None,
    settings: Settings,
    repository_key: str,
    *,
    dry_run: bool = True,
) -> CompactionReport:
    report = CompactionReport(repository_key=repository_key, dry_run=dry_run)

    repo_id = await pool.fetchval(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1", repository_key
    )
    if repo_id is None:
        report.errors.append(f"repository not found: {repository_key}")
        return report

    # ── PostgreSQL: inactive chunks (FK-guarded) + summaries ──
    chunk_where = """
        FROM catalog.chunks c
        JOIN catalog.entities e ON c.entity_id = e.id
        WHERE e.repository_id = $1 AND NOT c.is_active
          AND c.id NOT IN (
              SELECT evidence_chunk_id FROM memory.learned_records
              WHERE evidence_chunk_id IS NOT NULL
          )
    """
    summary_where = """
        FROM catalog.summaries s
        JOIN catalog.entities e ON s.entity_id = e.id
        WHERE e.repository_id = $1 AND NOT s.is_active
    """
    if dry_run:
        report.pg_chunks_deleted = await pool.fetchval("SELECT count(*) " + chunk_where, repo_id)
        report.pg_summaries_deleted = await pool.fetchval("SELECT count(*) " + summary_where, repo_id)
    else:
        report.pg_chunks_deleted = _affected(
            await pool.execute(
                """
                DELETE FROM catalog.chunks c
                USING catalog.entities e
                WHERE c.entity_id = e.id AND e.repository_id = $1 AND NOT c.is_active
                  AND c.id NOT IN (
                      SELECT evidence_chunk_id FROM memory.learned_records
                      WHERE evidence_chunk_id IS NOT NULL
                  )
                """,
                repo_id,
            )
        )
        report.pg_summaries_deleted = _affected(
            await pool.execute(
                """
                DELETE FROM catalog.summaries s
                USING catalog.entities e
                WHERE s.entity_id = e.id AND e.repository_id = $1 AND NOT s.is_active
                """,
                repo_id,
            )
        )

    # ── Qdrant: inactive points per repo (already clean post-reembed; future drift) ──
    try:
        for coll in ("code_chunks", "summary_units"):
            flt = models.Filter(
                must=[
                    models.FieldCondition(key="repository_key", match=models.MatchValue(value=repository_key)),
                    models.FieldCondition(key="is_active", match=models.MatchValue(value=False)),
                ]
            )
            cnt = (await qdrant_client.count(collection_name=coll, count_filter=flt)).count
            if cnt and not dry_run:
                await qdrant_client.delete(
                    collection_name=coll, points_selector=models.FilterSelector(filter=flt)
                )
            report.qdrant_points_deleted += cnt
    except Exception as exc:
        report.errors.append(f"qdrant: {exc}")

    # ── Neo4j: orphaned File/Symbol nodes (graph key not in active PG set) ──
    if neo4j_driver is None:
        report.skipped.append("neo4j (driver unavailable)")
    else:
        try:
            # "Current" = files/symbols backed by active chunks, UNION files/symbols in the
            # current branch-head revisions (covers chunkless-but-current files). Old-commit
            # versions (whose chunks were superseded/pruned) fall out → graph orphans.
            rows = await pool.fetch(
                """
                SELECT DISTINCT fe.entity_key
                FROM catalog.files f
                JOIN catalog.entities fe ON f.entity_id = fe.id
                WHERE fe.repository_id = $1
                  AND EXISTS (SELECT 1 FROM catalog.chunks c WHERE c.file_id = f.id AND c.is_active)
                UNION
                SELECT DISTINCT se.entity_key
                FROM catalog.symbols s
                JOIN catalog.entities se ON s.entity_id = se.id
                WHERE se.repository_id = $1
                  AND EXISTS (SELECT 1 FROM catalog.chunks c WHERE c.file_id = s.file_id AND c.is_active)
                UNION
                SELECT e.entity_key
                FROM catalog.entities e
                JOIN catalog.branch_heads bh ON bh.repo_revision_id = e.repo_revision_id
                WHERE e.repository_id = $1 AND e.entity_type IN ('file', 'symbol')
                """,
                repo_id,
            )
            active_keys = {str(r["entity_key"]) for r in rows}
            records, _, _ = await neo4j_driver.execute_query(
                """
                MATCH (repo:Repository {entity_key: $rk})-[:HAS_REVISION]->(:Revision)-[:HAS_FILE]->(f:File)
                RETURN f.entity_key AS k
                UNION
                MATCH (repo:Repository {entity_key: $rk})-[:HAS_REVISION]->(:Revision)
                      -[:HAS_FILE]->(:File)-[:CONTAINS]->(s:Symbol)
                RETURN s.entity_key AS k
                """,
                rk=repository_key,
            )
            graph_keys = {r["k"] for r in records if r["k"]}
            orphans = sorted(graph_keys - active_keys)
            report.neo4j_nodes_deleted = len(orphans)
            if orphans and not dry_run:
                for i in range(0, len(orphans), BATCH_SIZE):
                    await neo4j_driver.execute_query(
                        """
                        UNWIND $keys AS k
                        MATCH (n {entity_key: k}) WHERE n:File OR n:Symbol
                        DETACH DELETE n
                        """,
                        keys=orphans[i : i + BATCH_SIZE],
                    )
        except (neo4j.exceptions.ServiceUnavailable, neo4j.exceptions.SessionExpired, TimeoutError) as exc:
            # Neo4j unavailable/degraded (the dispatcher injects a live-but-dead driver during an
            # outage) — treat as skipped, not a failure, so PG/Qdrant compaction still reports success.
            report.skipped.append(f"neo4j (unavailable: {type(exc).__name__})")
            logger.warning("compaction_neo4j_unavailable", repository_key=repository_key, error=str(exc))
        except Exception as exc:
            report.errors.append(f"neo4j: {exc}")
            report.skipped.append("neo4j (error)")

    logger.info(
        "compaction_complete",
        repository_key=repository_key, dry_run=dry_run,
        chunks=report.pg_chunks_deleted, summaries=report.pg_summaries_deleted,
        qdrant=report.qdrant_points_deleted, neo4j=report.neo4j_nodes_deleted,
    )
    return report
