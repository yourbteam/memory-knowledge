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


async def upsert_repo_revision(
    pool: asyncpg.Pool,
    repository_id: int,
    commit_sha: str,
    branch_name: str,
    parent_sha: str | None = None,
) -> int:
    """Upsert a revision. Returns repo_revision_id."""
    row = await pool.fetchrow(
        """
        INSERT INTO catalog.repo_revisions (repository_id, commit_sha, branch_name, parent_sha)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (repository_id, commit_sha) DO UPDATE
            SET branch_name = EXCLUDED.branch_name
        RETURNING id
        """,
        repository_id,
        commit_sha,
        branch_name,
        parent_sha,
    )
    logger.info("revision_upserted", repo_revision_id=row["id"], commit_sha=commit_sha)
    return row["id"]


async def upsert_file(
    pool: asyncpg.Pool,
    entity_key: uuid.UUID,
    repository_id: int,
    repo_revision_id: int,
    file_path: str,
    language: str | None,
    size_bytes: int | None,
    checksum: str | None,
    external_hash: str | None = None,
) -> tuple[int, int]:
    """Upsert entity + file. Returns (entity_id, file_id)."""
    # Upsert entity
    entity_row = await pool.fetchrow(
        """
        INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id, external_hash)
        VALUES ($1, 'file', $2, $3, $4)
        ON CONFLICT (entity_key) DO UPDATE
            SET repo_revision_id = EXCLUDED.repo_revision_id,
                external_hash = EXCLUDED.external_hash
        RETURNING id
        """,
        entity_key,
        repository_id,
        repo_revision_id,
        external_hash,
    )
    entity_id = entity_row["id"]

    # Upsert file
    file_row = await pool.fetchrow(
        """
        INSERT INTO catalog.files (entity_id, repo_revision_id, file_path, language, size_bytes, checksum)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (repo_revision_id, file_path) DO UPDATE
            SET entity_id = EXCLUDED.entity_id,
                language = EXCLUDED.language,
                size_bytes = EXCLUDED.size_bytes,
                checksum = EXCLUDED.checksum
        RETURNING id
        """,
        entity_id,
        repo_revision_id,
        file_path,
        language,
        size_bytes,
        checksum,
    )
    return entity_id, file_row["id"]


async def bulk_upsert_files(
    pool: asyncpg.Pool,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Batch upsert file entities and files. Returns per-file IDs keyed by file_path."""
    if not rows:
        return []

    entity_rows = [
        (
            row["entity_key"],
            "file",
            row["repository_id"],
            row["repo_revision_id"],
            row.get("external_hash"),
        )
        for row in rows
    ]
    entity_ids_by_key: dict[str, int] = {}
    for i in range(0, len(entity_rows), BATCH_SIZE):
        batch = entity_rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        results = await pool.fetch(
            """
            INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id, external_hash)
            SELECT * FROM UNNEST($1::uuid[], $2::text[], $3::bigint[], $4::bigint[], $5::text[])
            ON CONFLICT (entity_key) DO UPDATE
                SET repo_revision_id = EXCLUDED.repo_revision_id,
                    external_hash = EXCLUDED.external_hash
            RETURNING id, entity_key
            """,
            *arrays,
        )
        entity_ids_by_key.update({str(result["entity_key"]): result["id"] for result in results})

    file_rows = [
        (
            entity_ids_by_key[str(row["entity_key"])],
            row["repo_revision_id"],
            row["file_path"],
            row.get("language"),
            row.get("size_bytes"),
            row.get("checksum"),
        )
        for row in rows
    ]
    file_meta_by_entity_id = {
        entity_ids_by_key[str(row["entity_key"])]: {
            "entity_key": str(row["entity_key"]),
            "file_path": row["file_path"],
        }
        for row in rows
    }
    saved: list[dict[str, Any]] = []
    for i in range(0, len(file_rows), BATCH_SIZE):
        batch = file_rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        results = await pool.fetch(
            """
            INSERT INTO catalog.files (entity_id, repo_revision_id, file_path, language, size_bytes, checksum)
            SELECT * FROM UNNEST($1::bigint[], $2::bigint[], $3::text[], $4::text[], $5::bigint[], $6::text[])
            ON CONFLICT ON CONSTRAINT uq_files_revision_path DO UPDATE
                SET entity_id = EXCLUDED.entity_id,
                    language = EXCLUDED.language,
                    size_bytes = EXCLUDED.size_bytes,
                    checksum = EXCLUDED.checksum
            RETURNING id, entity_id, file_path
            """,
            *arrays,
        )
        for result in results:
            meta = file_meta_by_entity_id[result["entity_id"]]
            saved.append(
                {
                    "entity_id": result["entity_id"],
                    "file_id": result["id"],
                    "file_path": result["file_path"],
                    "entity_key": meta["entity_key"],
                }
            )
    return saved


async def upsert_symbol(
    pool: asyncpg.Pool,
    entity_key: uuid.UUID,
    repository_id: int,
    repo_revision_id: int,
    file_id: int,
    symbol_name: str,
    symbol_kind: str,
    line_start: int | None,
    line_end: int | None,
    signature: str | None,
    external_hash: str | None = None,
) -> tuple[int, int]:
    """Upsert entity + symbol. Returns (entity_id, symbol_id)."""
    # Upsert entity
    entity_row = await pool.fetchrow(
        """
        INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id, external_hash)
        VALUES ($1, 'symbol', $2, $3, $4)
        ON CONFLICT (entity_key) DO UPDATE
            SET repo_revision_id = EXCLUDED.repo_revision_id,
                external_hash = EXCLUDED.external_hash
        RETURNING id
        """,
        entity_key,
        repository_id,
        repo_revision_id,
        external_hash,
    )
    entity_id = entity_row["id"]

    # Upsert symbol
    symbol_row = await pool.fetchrow(
        """
        INSERT INTO catalog.symbols (entity_id, file_id, symbol_name, symbol_kind, line_start, line_end, signature)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (entity_id) DO UPDATE
            SET file_id = EXCLUDED.file_id,
                symbol_name = EXCLUDED.symbol_name,
                symbol_kind = EXCLUDED.symbol_kind,
                line_start = EXCLUDED.line_start,
                line_end = EXCLUDED.line_end,
                signature = EXCLUDED.signature
        RETURNING id
        """,
        entity_id,
        file_id,
        symbol_name,
        symbol_kind,
        line_start,
        line_end,
        signature,
    )
    return entity_id, symbol_row["id"]


async def bulk_upsert_symbols(
    pool: asyncpg.Pool,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Batch upsert symbol entities and symbols."""
    if not rows:
        return []

    entity_rows = [
        (
            row["entity_key"],
            "symbol",
            row["repository_id"],
            row["repo_revision_id"],
            row.get("external_hash"),
        )
        for row in rows
    ]
    entity_ids_by_key: dict[str, int] = {}
    for i in range(0, len(entity_rows), BATCH_SIZE):
        batch = entity_rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        results = await pool.fetch(
            """
            INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id, external_hash)
            SELECT * FROM UNNEST($1::uuid[], $2::text[], $3::bigint[], $4::bigint[], $5::text[])
            ON CONFLICT (entity_key) DO UPDATE
                SET repo_revision_id = EXCLUDED.repo_revision_id,
                    external_hash = EXCLUDED.external_hash
            RETURNING id, entity_key
            """,
            *arrays,
        )
        entity_ids_by_key.update({str(result["entity_key"]): result["id"] for result in results})

    symbol_rows = [
        (
            entity_ids_by_key[str(row["entity_key"])],
            row["file_id"],
            row["symbol_name"],
            row["symbol_kind"],
            row.get("line_start"),
            row.get("line_end"),
            row.get("signature"),
        )
        for row in rows
    ]
    symbol_meta_by_entity_id = {
        entity_ids_by_key[str(row["entity_key"])]: {
            "entity_key": str(row["entity_key"]),
            "file_path": row["file_path"],
            "symbol_name": row["symbol_name"],
        }
        for row in rows
    }
    saved: list[dict[str, Any]] = []
    for i in range(0, len(symbol_rows), BATCH_SIZE):
        batch = symbol_rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        results = await pool.fetch(
            """
            INSERT INTO catalog.symbols (entity_id, file_id, symbol_name, symbol_kind, line_start, line_end, signature)
            SELECT * FROM UNNEST($1::bigint[], $2::bigint[], $3::text[], $4::text[], $5::int[], $6::int[], $7::text[])
            ON CONFLICT (entity_id) DO UPDATE
                SET file_id = EXCLUDED.file_id,
                    symbol_name = EXCLUDED.symbol_name,
                    symbol_kind = EXCLUDED.symbol_kind,
                    line_start = EXCLUDED.line_start,
                    line_end = EXCLUDED.line_end,
                    signature = EXCLUDED.signature
            RETURNING id, entity_id
            """,
            *arrays,
        )
        for result in results:
            meta = symbol_meta_by_entity_id[result["entity_id"]]
            saved.append(
                {
                    "entity_id": result["entity_id"],
                    "symbol_id": result["id"],
                    "entity_key": meta["entity_key"],
                    "file_path": meta["file_path"],
                    "symbol_name": meta["symbol_name"],
                }
            )
    return saved


async def upsert_file_import(
    pool: asyncpg.Pool,
    importer_file_id: int,
    imported_file_id: int,
) -> None:
    """Register a file-imports-file edge. Idempotent."""
    await pool.execute(
        """
        INSERT INTO catalog.file_imports_file (importer_file_id, imported_file_id)
        VALUES ($1, $2)
        ON CONFLICT ON CONSTRAINT uq_file_imports DO NOTHING
        """,
        importer_file_id,
        imported_file_id,
    )


async def bulk_upsert_file_imports(
    pool: asyncpg.Pool,
    rows: list[tuple[int, int]],
) -> None:
    if not rows:
        return
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        await pool.execute(
            """
            INSERT INTO catalog.file_imports_file (importer_file_id, imported_file_id)
            SELECT * FROM UNNEST($1::bigint[], $2::bigint[])
            ON CONFLICT ON CONSTRAINT uq_file_imports DO NOTHING
            """,
            *arrays,
        )


async def upsert_symbol_call(
    pool: asyncpg.Pool,
    caller_symbol_id: int,
    callee_symbol_id: int,
) -> None:
    """Register a symbol-calls-symbol edge. Idempotent."""
    await pool.execute(
        """
        INSERT INTO catalog.symbol_calls_symbol (caller_symbol_id, callee_symbol_id)
        VALUES ($1, $2)
        ON CONFLICT ON CONSTRAINT uq_symbol_calls DO NOTHING
        """,
        caller_symbol_id,
        callee_symbol_id,
    )


async def bulk_upsert_symbol_calls(
    pool: asyncpg.Pool,
    rows: list[tuple[int, int]],
) -> None:
    if not rows:
        return
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        await pool.execute(
            """
            INSERT INTO catalog.symbol_calls_symbol (caller_symbol_id, callee_symbol_id)
            SELECT * FROM UNNEST($1::bigint[], $2::bigint[])
            ON CONFLICT ON CONSTRAINT uq_symbol_calls DO NOTHING
            """,
            *arrays,
        )
