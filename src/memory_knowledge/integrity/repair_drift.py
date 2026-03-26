from __future__ import annotations

from typing import Any

import asyncpg
import neo4j
import structlog
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.projections.learned_memory_qdrant import embed_and_upsert_learned_record
from memory_knowledge.projections.neo4j_projector import project_repository_graph
from memory_knowledge.projections.qdrant_projector import embed_chunks, upsert_points
from memory_knowledge.projections.summary_qdrant import embed_and_upsert_summaries

logger = structlog.get_logger()


class RepairReport(BaseModel):
    scope: str
    qdrant_points_repaired: int = 0
    summary_points_repaired: int = 0
    learned_records_repaired: int = 0
    neo4j_nodes_repaired: int = 0
    errors: list[str] = []


async def repair(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    neo4j_driver: neo4j.AsyncDriver,
    settings: Settings,
    repository_key: str,
    repair_scope: str = "full",
) -> RepairReport:
    """Re-project PG canonical data to Qdrant and/or Neo4j."""
    report = RepairReport(scope=repair_scope)

    # Resolve repository and latest revision
    row = await pool.fetchrow(
        """
        SELECT r.id AS repo_id, rr.id AS rev_id, rr.commit_sha, rr.branch_name
        FROM catalog.repositories r
        JOIN catalog.repo_revisions rr ON rr.repository_id = r.id
        WHERE r.repository_key = $1
        ORDER BY rr.created_utc DESC
        LIMIT 1
        """,
        repository_key,
    )
    if row is None:
        report.errors.append(f"No revisions found for {repository_key}")
        return report

    repo_id = row["repo_id"]
    rev_id = row["rev_id"]
    commit_sha = row["commit_sha"]
    branch_name = row["branch_name"] or "main"

    # Qdrant repair
    if repair_scope in ("full", "qdrant"):
        try:
            chunk_rows = await pool.fetch(
                """
                SELECT e.entity_key, c.content_text, c.chunk_type,
                       f.file_path, c.title
                FROM catalog.chunks c
                JOIN catalog.entities e ON c.entity_id = e.id
                JOIN catalog.files f ON c.file_id = f.id
                WHERE e.repository_id = $1 AND e.repo_revision_id = $2
                """,
                repo_id,
                rev_id,
            )

            if chunk_rows:
                texts = [r["content_text"] for r in chunk_rows]
                embeddings = await embed_chunks(texts, settings)

                chunks_with_embeddings: list[dict[str, Any]] = []
                for r, emb in zip(chunk_rows, embeddings):
                    # Extract symbol_name from title if chunk_type is "symbol"
                    symbol_name = None
                    title = r["title"] or ""
                    if ":" in title:
                        symbol_name = title.split(":", 1)[1].split("[")[0]

                    chunks_with_embeddings.append({
                        "entity_key": str(r["entity_key"]),
                        "embedding": emb,
                        "file_path": r["file_path"],
                        "symbol_name": symbol_name,
                        "chunk_type": r["chunk_type"],
                    })

                await upsert_points(
                    qdrant_client, chunks_with_embeddings,
                    repository_key, commit_sha, branch_name,
                )
                report.qdrant_points_repaired = len(chunks_with_embeddings)
                logger.info("qdrant_repair_complete", points=report.qdrant_points_repaired)
        except Exception as exc:
            report.errors.append(f"Qdrant repair failed: {exc}")
            logger.error("qdrant_repair_failed", error=str(exc))

    # Summary repair (summary_units collection)
    if repair_scope in ("full", "qdrant"):
        try:
            summary_rows = await pool.fetch(
                """
                SELECT e.entity_key, s.summary_text, s.summary_level
                FROM catalog.summaries s
                JOIN catalog.entities e ON s.entity_id = e.id
                WHERE e.repository_id = $1
                """,
                repo_id,
            )
            if summary_rows:
                summaries_list = [
                    {
                        "entity_key": str(r["entity_key"]),
                        "summary_text": r["summary_text"],
                        "summary_level": r["summary_level"],
                    }
                    for r in summary_rows
                ]
                await embed_and_upsert_summaries(
                    qdrant_client, summaries_list, repository_key, commit_sha, settings,
                )
                report.summary_points_repaired = len(summaries_list)
                logger.info("summary_repair_complete", points=report.summary_points_repaired)
        except Exception as exc:
            report.errors.append(f"Summary repair failed: {exc}")
            logger.error("summary_repair_failed", error=str(exc))

    # Learned memory repair (learned_memory collection)
    if repair_scope in ("full", "qdrant"):
        try:
            lr_rows = await pool.fetch(
                """
                SELECT e.entity_key, lr.body_text, lr.memory_type, lr.confidence,
                       lr.applicability_mode,
                       scope_e.entity_key AS scope_entity_key
                FROM memory.learned_records lr
                JOIN catalog.entities e ON lr.entity_id = e.id
                JOIN catalog.entities scope_e ON lr.scope_entity_id = scope_e.id
                WHERE e.repository_id = $1 AND lr.is_active = TRUE
                  AND lr.verification_status = 'verified'
                """,
                repo_id,
            )
            for lr in lr_rows:
                await embed_and_upsert_learned_record(
                    client=qdrant_client,
                    entity_key=str(lr["entity_key"]),
                    body_text=lr["body_text"],
                    repository_key=repository_key,
                    memory_type=lr["memory_type"],
                    confidence=float(lr["confidence"]) if lr["confidence"] else 0.5,
                    applicability_mode=lr["applicability_mode"] or "repository",
                    scope_entity_key=str(lr["scope_entity_key"]),
                    settings=settings,
                )
            report.learned_records_repaired = len(lr_rows)
            logger.info("learned_memory_repair_complete", records=report.learned_records_repaired)
        except Exception as exc:
            report.errors.append(f"Learned memory repair failed: {exc}")
            logger.error("learned_memory_repair_failed", error=str(exc))

    # Neo4j repair
    if repair_scope in ("full", "neo4j"):
        try:
            file_rows = await pool.fetch(
                """
                SELECT e.entity_key AS file_entity_key, f.file_path
                FROM catalog.files f
                JOIN catalog.entities e ON f.entity_id = e.id
                WHERE e.repository_id = $1 AND e.repo_revision_id = $2
                """,
                repo_id,
                rev_id,
            )

            # Batch-fetch all symbols for this revision in one query
            all_symbols = await pool.fetch(
                """
                SELECT e_file.entity_key AS file_entity_key,
                       e_sym.entity_key AS symbol_entity_key,
                       s.symbol_name, s.symbol_kind
                FROM catalog.symbols s
                JOIN catalog.entities e_sym ON s.entity_id = e_sym.id
                JOIN catalog.files f ON s.file_id = f.id
                JOIN catalog.entities e_file ON f.entity_id = e_file.id
                WHERE e_file.repository_id = $1 AND e_file.repo_revision_id = $2
                """,
                repo_id,
                rev_id,
            )

            # Group symbols by file entity_key
            symbols_by_file: dict[str, list[dict[str, str]]] = {}
            for sr in all_symbols:
                fek = str(sr["file_entity_key"])
                if fek not in symbols_by_file:
                    symbols_by_file[fek] = []
                symbols_by_file[fek].append({
                    "entity_key": str(sr["symbol_entity_key"]),
                    "name": sr["symbol_name"],
                    "kind": sr["symbol_kind"],
                })

            file_symbols: list[dict[str, Any]] = [
                {
                    "file_path": fr["file_path"],
                    "file_entity_key": str(fr["file_entity_key"]),
                    "symbols": symbols_by_file.get(str(fr["file_entity_key"]), []),
                }
                for fr in file_rows
            ]

            if file_symbols:
                await project_repository_graph(
                    neo4j_driver, repository_key, commit_sha,
                    branch_name, file_symbols,
                )
                report.neo4j_nodes_repaired = len(file_symbols)
                logger.info("neo4j_repair_complete", files=report.neo4j_nodes_repaired)
        except Exception as exc:
            report.errors.append(f"Neo4j repair failed: {exc}")
            logger.error("neo4j_repair_failed", error=str(exc))

    return report


async def rebuild_revision(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    neo4j_driver: neo4j.AsyncDriver,
    settings: Settings,
    repository_key: str,
    commit_sha: str,
    repair_scope: str = "full",
) -> RepairReport:
    """Re-project PG canonical data for a specific revision to Qdrant and/or Neo4j."""
    report = RepairReport(scope=repair_scope)

    row = await pool.fetchrow(
        """
        SELECT r.id AS repo_id, rr.id AS rev_id, rr.branch_name
        FROM catalog.repositories r
        JOIN catalog.repo_revisions rr ON rr.repository_id = r.id
        WHERE r.repository_key = $1 AND rr.commit_sha = $2
        """,
        repository_key,
        commit_sha,
    )
    if row is None:
        report.errors.append(f"Revision {commit_sha} not found for {repository_key}")
        return report

    repo_id = row["repo_id"]
    rev_id = row["rev_id"]
    branch_name = row["branch_name"] or "main"

    if repair_scope in ("full", "qdrant"):
        try:
            chunk_rows = await pool.fetch(
                """
                SELECT e.entity_key, c.content_text, c.chunk_type,
                       f.file_path, c.title
                FROM catalog.chunks c
                JOIN catalog.entities e ON c.entity_id = e.id
                JOIN catalog.files f ON c.file_id = f.id
                WHERE e.repository_id = $1 AND e.repo_revision_id = $2
                """,
                repo_id,
                rev_id,
            )
            if chunk_rows:
                texts = [r["content_text"] for r in chunk_rows]
                embeddings = await embed_chunks(texts, settings)
                chunks_with_embeddings: list[dict[str, Any]] = []
                for r, emb in zip(chunk_rows, embeddings):
                    symbol_name = None
                    title = r["title"] or ""
                    if ":" in title:
                        symbol_name = title.split(":", 1)[1].split("[")[0]
                    chunks_with_embeddings.append({
                        "entity_key": str(r["entity_key"]),
                        "embedding": emb,
                        "file_path": r["file_path"],
                        "symbol_name": symbol_name,
                        "chunk_type": r["chunk_type"],
                    })
                await upsert_points(
                    qdrant_client, chunks_with_embeddings,
                    repository_key, commit_sha, branch_name,
                )
                report.qdrant_points_repaired = len(chunks_with_embeddings)
        except Exception as exc:
            report.errors.append(f"Qdrant rebuild failed: {exc}")

    if repair_scope in ("full", "neo4j"):
        try:
            file_rows = await pool.fetch(
                """
                SELECT e.entity_key AS file_entity_key, f.file_path
                FROM catalog.files f
                JOIN catalog.entities e ON f.entity_id = e.id
                WHERE e.repository_id = $1 AND e.repo_revision_id = $2
                """,
                repo_id,
                rev_id,
            )
            all_symbols = await pool.fetch(
                """
                SELECT e_file.entity_key AS file_entity_key,
                       e_sym.entity_key AS symbol_entity_key,
                       s.symbol_name, s.symbol_kind
                FROM catalog.symbols s
                JOIN catalog.entities e_sym ON s.entity_id = e_sym.id
                JOIN catalog.files f ON s.file_id = f.id
                JOIN catalog.entities e_file ON f.entity_id = e_file.id
                WHERE e_file.repository_id = $1 AND e_file.repo_revision_id = $2
                """,
                repo_id,
                rev_id,
            )
            symbols_by_file: dict[str, list[dict[str, str]]] = {}
            for sr in all_symbols:
                fek = str(sr["file_entity_key"])
                symbols_by_file.setdefault(fek, []).append({
                    "entity_key": str(sr["symbol_entity_key"]),
                    "name": sr["symbol_name"],
                    "kind": sr["symbol_kind"],
                })
            file_symbols: list[dict[str, Any]] = [
                {
                    "file_path": fr["file_path"],
                    "file_entity_key": str(fr["file_entity_key"]),
                    "symbols": symbols_by_file.get(str(fr["file_entity_key"]), []),
                }
                for fr in file_rows
            ]
            if file_symbols:
                await project_repository_graph(
                    neo4j_driver, repository_key, commit_sha,
                    branch_name, file_symbols,
                )
                report.neo4j_nodes_repaired = len(file_symbols)
        except Exception as exc:
            report.errors.append(f"Neo4j rebuild failed: {exc}")

    logger.info("rebuild_revision_complete", commit_sha=commit_sha)
    return report
