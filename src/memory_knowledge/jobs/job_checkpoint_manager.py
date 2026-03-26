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
