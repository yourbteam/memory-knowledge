from __future__ import annotations

from typing import Any

import asyncpg
import neo4j
import structlog
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.projections.neo4j_projector import project_repository_graph
from memory_knowledge.projections.qdrant_projector import embed_chunks, upsert_points

logger = structlog.get_logger()


class RepairReport(BaseModel):
    scope: str
    qdrant_points_repaired: int = 0
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

            file_symbols: list[dict[str, Any]] = []
            for fr in file_rows:
                symbol_rows = await pool.fetch(
                    """
                    SELECT e.entity_key, s.symbol_name, s.symbol_kind
                    FROM catalog.symbols s
                    JOIN catalog.entities e ON s.entity_id = e.id
                    WHERE s.file_id = (
                        SELECT f2.id FROM catalog.files f2
                        JOIN catalog.entities e2 ON f2.entity_id = e2.id
                        WHERE e2.entity_key = $1
                        LIMIT 1
                    )
                    """,
                    fr["file_entity_key"],
                )
                file_symbols.append({
                    "file_path": fr["file_path"],
                    "file_entity_key": str(fr["file_entity_key"]),
                    "symbols": [
                        {
                            "entity_key": str(sr["entity_key"]),
                            "name": sr["symbol_name"],
                            "kind": sr["symbol_kind"],
                        }
                        for sr in symbol_rows
                    ],
                })

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
