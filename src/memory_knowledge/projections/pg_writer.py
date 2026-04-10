from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()
BATCH_SIZE = 250


def _column_arrays(rows: list[tuple[Any, ...]]) -> list[list[Any]]:
    if not rows:
        return []
    return [list(col) for col in zip(*rows)]


async def upsert_chunk(
    pool: asyncpg.Pool,
    entity_key: uuid.UUID,
    entity_id: int,
    file_id: int,
    title: str | None,
    content_text: str,
    chunk_type: str | None,
    line_start: int | None,
    line_end: int | None,
    checksum: str | None,
) -> int:
    """Upsert entity + chunk with inline tsvector computation. Returns chunk id."""
    # Ensure entity exists
    ent_row = await pool.fetchrow(
        """
        INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id)
        SELECT $1, 'chunk', e.repository_id, e.repo_revision_id
        FROM catalog.entities e
        WHERE e.id = $2
        ON CONFLICT (entity_key) DO UPDATE
            SET repo_revision_id = EXCLUDED.repo_revision_id
        RETURNING id
        """,
        entity_key,
        entity_id,
    )
    chunk_entity_id = ent_row["id"]

    row = await pool.fetchrow(
        """
        INSERT INTO catalog.chunks
            (entity_id, file_id, title, content_text, content_tsv, chunk_type,
             line_start, line_end, checksum)
        VALUES ($1, $2, $3, $4, to_tsvector('english', $4), $5, $6, $7, $8)
        ON CONFLICT (entity_id) DO UPDATE
            SET content_text = EXCLUDED.content_text,
                content_tsv = to_tsvector('english', EXCLUDED.content_text),
                checksum = EXCLUDED.checksum,
                title = EXCLUDED.title
        RETURNING id
        """,
        chunk_entity_id,
        file_id,
        title,
        content_text,
        chunk_type,
        line_start,
        line_end,
        checksum,
    )
    return row["id"]


async def bulk_upsert_chunks(
    pool: asyncpg.Pool,
    rows: list[dict[str, Any]],
) -> None:
    """Batch upsert chunk entities and chunks."""
    if not rows:
        return

    entity_rows = [
        (
            row["entity_key"],
            "chunk",
            row["repository_id"],
            row["repo_revision_id"],
        )
        for row in rows
    ]
    entity_ids_by_key: dict[str, int] = {}
    for i in range(0, len(entity_rows), BATCH_SIZE):
        batch = entity_rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        results = await pool.fetch(
            """
            INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id)
            SELECT * FROM UNNEST($1::uuid[], $2::text[], $3::bigint[], $4::bigint[])
            ON CONFLICT (entity_key) DO UPDATE
                SET repo_revision_id = EXCLUDED.repo_revision_id
            RETURNING id, entity_key
            """,
            *arrays,
        )
        entity_ids_by_key.update({str(result["entity_key"]): result["id"] for result in results})

    chunk_rows = [
        (
            entity_ids_by_key[str(row["entity_key"])],
            row["file_id"],
            row.get("title"),
            row["content_text"],
            row.get("chunk_type"),
            row.get("line_start"),
            row.get("line_end"),
            row.get("checksum"),
        )
        for row in rows
    ]
    for i in range(0, len(chunk_rows), BATCH_SIZE):
        batch = chunk_rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        await pool.execute(
            """
            INSERT INTO catalog.chunks
                (entity_id, file_id, title, content_text, content_tsv, chunk_type,
                 line_start, line_end, checksum)
            SELECT entity_id, file_id, title, content_text, to_tsvector('english', content_text), chunk_type,
                   line_start, line_end, checksum
            FROM UNNEST($1::bigint[], $2::bigint[], $3::text[], $4::text[], $5::text[], $6::int[], $7::int[], $8::text[])
                AS t(entity_id, file_id, title, content_text, chunk_type, line_start, line_end, checksum)
            ON CONFLICT (entity_id) DO UPDATE
                SET content_text = EXCLUDED.content_text,
                    content_tsv = to_tsvector('english', EXCLUDED.content_text),
                    checksum = EXCLUDED.checksum,
                    title = EXCLUDED.title
            """,
            *arrays,
        )


async def upsert_branch_head(
    pool: asyncpg.Pool,
    repository_id: int,
    branch_name: str,
    repo_revision_id: int,
) -> int:
    """Upsert branch head pointer."""
    row = await pool.fetchrow(
        """
        INSERT INTO catalog.branch_heads (repository_id, branch_name, repo_revision_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (repository_id, branch_name) DO UPDATE
            SET repo_revision_id = EXCLUDED.repo_revision_id,
                updated_utc = NOW()
        RETURNING id
        """,
        repository_id,
        branch_name,
        repo_revision_id,
    )
    return row["id"]


async def upsert_retrieval_surface(
    pool: asyncpg.Pool,
    repository_id: int,
    surface_type: str,
    branch_name: str | None,
    commit_sha: str | None,
    repo_revision_id: int,
) -> int:
    """Upsert retrieval surface."""
    row = await pool.fetchrow(
        """
        INSERT INTO catalog.retrieval_surfaces
            (repository_id, surface_type, branch_name, commit_sha, repo_revision_id, is_default)
        VALUES ($1, $2::catalog.surface_type_enum, $3, $4, $5, TRUE)
        ON CONFLICT ON CONSTRAINT uq_retrieval_surfaces DO UPDATE
            SET commit_sha = EXCLUDED.commit_sha,
                repo_revision_id = EXCLUDED.repo_revision_id,
                updated_utc = NOW()
        RETURNING id
        """,
        repository_id,
        surface_type,
        branch_name,
        commit_sha,
        repo_revision_id,
    )
    return row["id"]


async def create_ingestion_run(
    pool: asyncpg.Pool,
    repository_id: int,
    commit_sha: str,
    branch_name: str,
    run_type: str = "full",
) -> int:
    """Create an ingestion run record. Returns ingestion_run_id."""
    row = await pool.fetchrow(
        """
        INSERT INTO ops.ingestion_runs
            (repository_id, commit_sha, branch_name, run_type, status, started_utc)
        VALUES ($1, $2, $3, $4, 'running', NOW())
        RETURNING id
        """,
        repository_id,
        commit_sha,
        branch_name,
        run_type,
    )
    logger.info("ingestion_run_created", ingestion_run_id=row["id"])
    return row["id"]


async def complete_ingestion_run(
    pool: asyncpg.Pool,
    ingestion_run_id: int,
    status: str,
    error_text: str | None = None,
) -> None:
    """Mark an ingestion run as completed or failed."""
    await pool.execute(
        """
        UPDATE ops.ingestion_runs
        SET status = $2, completed_utc = NOW(), error_text = $3
        WHERE id = $1
        """,
        ingestion_run_id,
        status,
        error_text,
    )


async def record_ingestion_item(
    pool: asyncpg.Pool,
    ingestion_run_id: int,
    entity_id: int | None,
    item_type: str,
    status: str,
    error_text: str | None = None,
) -> None:
    """Record an individual item's ingestion status."""
    await pool.execute(
        """
        INSERT INTO ops.ingestion_run_items
            (ingestion_run_id, entity_id, item_type, status, error_text)
        VALUES ($1, $2, $3, $4, $5)
        """,
        ingestion_run_id,
        entity_id,
        item_type,
        status,
        error_text,
    )


async def bulk_record_ingestion_items(
    pool: asyncpg.Pool,
    rows: list[tuple[int, int | None, str, str, str | None]],
) -> None:
    """Batch record ingestion item statuses."""
    if not rows:
        return
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        await pool.execute(
            """
            INSERT INTO ops.ingestion_run_items
                (ingestion_run_id, entity_id, item_type, status, error_text)
            SELECT * FROM UNNEST($1::bigint[], $2::bigint[], $3::text[], $4::text[], $5::text[])
            """,
            *arrays,
        )


async def record_route_feedback(
    pool: asyncpg.Pool,
    route_execution_id: int,
    usefulness_score: float | None = None,
    precision_score: float | None = None,
    expansion_needed: bool | None = None,
    notes: str | None = None,
    is_auto: bool = False,
) -> int:
    """Record feedback for a route execution."""
    row = await pool.fetchrow(
        """
        INSERT INTO routing.route_feedback
            (route_execution_id, usefulness_score, precision_score,
             expansion_needed, notes, is_auto)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        route_execution_id,
        usefulness_score,
        precision_score,
        expansion_needed,
        notes,
        is_auto,
    )
    return row["id"]
