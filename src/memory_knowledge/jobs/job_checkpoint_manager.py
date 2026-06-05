from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg


async def save_checkpoint(
    pool: asyncpg.Pool, job_id: uuid.UUID, data: dict[str, Any]
) -> None:
    """Save checkpoint data for a job (JSONB upsert)."""
    await pool.execute(
        "UPDATE ops.job_manifests SET checkpoint_data = $2::jsonb WHERE job_id = $1",
        job_id,
        json.dumps(data),
    )


async def load_checkpoint(
    pool: asyncpg.Pool, job_id: uuid.UUID
) -> dict[str, Any] | None:
    """Load checkpoint data for a job."""
    row = await pool.fetchrow(
        "SELECT checkpoint_data FROM ops.job_manifests WHERE job_id = $1",
        job_id,
    )
    if row is None or row["checkpoint_data"] is None:
        return None
    cp = row["checkpoint_data"]
    if isinstance(cp, str):
        return json.loads(cp)
    return dict(cp) if cp else None


# --- Shape-keyed checkpoints for runs without a job manifest (offline/manual) ---


async def save_shape_checkpoint(
    pool: asyncpg.Pool,
    repository_id: int,
    commit_sha: str,
    branch_name: str,
    data: dict[str, Any],
) -> None:
    """Persist a checkpoint keyed by (repository_id, commit_sha, branch_name)."""
    await pool.execute(
        """
        INSERT INTO ops.ingestion_checkpoints
            (repository_id, commit_sha, branch_name, checkpoint_data, updated_utc)
        VALUES ($1, $2, $3, $4::jsonb, NOW())
        ON CONFLICT (repository_id, commit_sha, branch_name) DO UPDATE
            SET checkpoint_data = EXCLUDED.checkpoint_data, updated_utc = NOW()
        """,
        repository_id,
        commit_sha,
        branch_name,
        json.dumps(data),
    )


async def load_shape_checkpoint(
    pool: asyncpg.Pool,
    repository_id: int,
    commit_sha: str,
    branch_name: str,
) -> dict[str, Any] | None:
    """Load a shape-keyed checkpoint, or None if absent."""
    row = await pool.fetchrow(
        """
        SELECT checkpoint_data FROM ops.ingestion_checkpoints
        WHERE repository_id = $1 AND commit_sha = $2 AND branch_name = $3
        """,
        repository_id,
        commit_sha,
        branch_name,
    )
    if row is None or row["checkpoint_data"] is None:
        return None
    cp = row["checkpoint_data"]
    if isinstance(cp, str):
        return json.loads(cp)
    return dict(cp) if cp else None


async def clear_shape_checkpoint(
    pool: asyncpg.Pool,
    repository_id: int,
    commit_sha: str,
    branch_name: str,
) -> None:
    """Remove a shape-keyed checkpoint (called when its run completes)."""
    await pool.execute(
        """
        DELETE FROM ops.ingestion_checkpoints
        WHERE repository_id = $1 AND commit_sha = $2 AND branch_name = $3
        """,
        repository_id,
        commit_sha,
        branch_name,
    )
