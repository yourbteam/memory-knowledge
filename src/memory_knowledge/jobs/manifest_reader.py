from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg


async def get_job_by_id(
    pool: asyncpg.Pool, job_id: uuid.UUID
) -> dict[str, Any] | None:
    """Get a single job manifest by job_id."""
    row = await pool.fetchrow(
        "SELECT * FROM ops.job_manifests WHERE job_id = $1",
        job_id,
    )
    if row is None:
        return None
    result = dict(row)
    # Convert UUIDs and timestamps to strings for JSON serialization
    for key in ("run_id", "job_id"):
        if result.get(key):
            result[key] = str(result[key])
    for key in ("started_utc", "completed_utc", "created_utc"):
        if result.get(key):
            result[key] = result[key].isoformat()
    # Parse checkpoint_data if it's a string
    if isinstance(result.get("checkpoint_data"), str):
        try:
            result["checkpoint_data"] = json.loads(result["checkpoint_data"])
        except (json.JSONDecodeError, TypeError):
            pass
    return result


async def get_jobs_for_run(
    pool: asyncpg.Pool, run_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Get all job manifests for a run."""
    rows = await pool.fetch(
        "SELECT * FROM ops.job_manifests WHERE run_id = $1 ORDER BY created_utc",
        run_id,
    )
    return [dict(r) for r in rows]


async def get_failed_jobs(
    pool: asyncpg.Pool, repository_key: str
) -> list[dict[str, Any]]:
    """Get all failed jobs for a repository."""
    rows = await pool.fetch(
        """
        SELECT * FROM ops.job_manifests
        WHERE repository_key = $1 AND state_code = 'failed'
        ORDER BY created_utc DESC
        """,
        repository_key,
    )
    return [dict(r) for r in rows]


async def get_job_checkpoint(
    pool: asyncpg.Pool, job_id: uuid.UUID
) -> dict[str, Any] | None:
    """Get checkpoint data for a job."""
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


async def get_latest_resume_checkpoint(
    pool: asyncpg.Pool,
    repository_key: str,
    commit_sha: str,
    branch_name: str,
    tool_name: str,
) -> dict[str, Any] | None:
    """Return the latest saved workflow checkpoint for an identical job shape."""
    row = await pool.fetchrow(
        """
        SELECT checkpoint_data
        FROM ops.job_manifests
        WHERE repository_key = $1
          AND commit_sha = $2
          AND branch_name = $3
          AND tool_name = $4
          AND checkpoint_data IS NOT NULL
        ORDER BY created_utc DESC
        LIMIT 1
        """,
        repository_key,
        commit_sha,
        branch_name,
        tool_name,
    )
    if row is None or row["checkpoint_data"] is None:
        return None
    checkpoint_data = row["checkpoint_data"]
    if isinstance(checkpoint_data, str):
        checkpoint_data = json.loads(checkpoint_data)
    if not checkpoint_data:
        return None
    checkpoint = checkpoint_data.get("checkpoint")
    if checkpoint is None:
        return None
    return dict(checkpoint) if isinstance(checkpoint, dict) else checkpoint


async def get_active_job_for_shape(
    pool: asyncpg.Pool,
    repository_key: str,
    commit_sha: str,
    branch_name: str,
    tool_name: str,
) -> dict[str, Any] | None:
    """Return the newest pending/running job for an identical workflow shape."""
    row = await pool.fetchrow(
        """
        SELECT *
        FROM ops.job_manifests
        WHERE repository_key = $1
          AND commit_sha = $2
          AND branch_name = $3
          AND tool_name = $4
          AND state_code IN ('pending', 'running')
        ORDER BY created_utc DESC
        LIMIT 1
        """,
        repository_key,
        commit_sha,
        branch_name,
        tool_name,
    )
    return dict(row) if row else None
