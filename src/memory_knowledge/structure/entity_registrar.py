from __future__ import annotations

import uuid

import asyncpg
import structlog

logger = structlog.get_logger()


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
) -> tuple[int, int]:
    """Upsert entity + file. Returns (entity_id, file_id)."""
    # Upsert entity
    entity_row = await pool.fetchrow(
        """
        INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id)
        VALUES ($1, 'file', $2, $3)
        ON CONFLICT (entity_key) DO UPDATE
            SET repo_revision_id = EXCLUDED.repo_revision_id
        RETURNING id
        """,
        entity_key,
        repository_id,
        repo_revision_id,
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
) -> tuple[int, int]:
    """Upsert entity + symbol. Returns (entity_id, symbol_id)."""
    # Upsert entity
    entity_row = await pool.fetchrow(
        """
        INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id)
        VALUES ($1, 'symbol', $2, $3)
        ON CONFLICT (entity_key) DO UPDATE
            SET repo_revision_id = EXCLUDED.repo_revision_id
        RETURNING id
        """,
        entity_key,
        repository_id,
        repo_revision_id,
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
