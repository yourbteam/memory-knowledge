from __future__ import annotations

import json
import uuid

import asyncpg
import structlog

from memory_knowledge.jobs.state_transition_guard import validate_transition

logger = structlog.get_logger()


async def create_job(
    pool: asyncpg.Pool,
    run_id: uuid.UUID,
    job_type: str,
    tool_name: str,
    repository_key: str,
    commit_sha: str | None = None,
    branch_name: str | None = None,
    correlation_id: str | None = None,
    job_params: dict | None = None,
) -> uuid.UUID:
    """Create a new job manifest entry. Returns job_id."""
    job_id = uuid.uuid4()
    checkpoint_data = json.dumps(job_params) if job_params else None
    await pool.execute(
        """
        INSERT INTO ops.job_manifests
            (run_id, job_id, repository_key, commit_sha, branch_name,
             tool_name, state_code, job_type, correlation_id, checkpoint_data)
        VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8, $9::jsonb)
        """,
        run_id,
        job_id,
        repository_key,
        commit_sha,
        branch_name,
        tool_name,
        job_type,
        correlation_id,
        checkpoint_data,
    )
    logger.info("job_created", job_id=str(job_id), job_type=job_type)
    return job_id


async def update_job_state(
    pool: asyncpg.Pool,
    job_id: uuid.UUID,
    state_code: str,
    checkpoint_data: str | None = None,
    error_code: str | None = None,
    error_text: str | None = None,
) -> None:
    """Update job state with transition validation."""
    row = await pool.fetchrow(
        "SELECT state_code FROM ops.job_manifests WHERE job_id = $1",
        job_id,
    )
    if row is None:
        raise ValueError(f"Job not found: {job_id}")

    current_state = row["state_code"]
    validate_transition(current_state, state_code)

    if state_code in ("completed", "failed", "dead_letter"):
        await pool.execute(
            """
            UPDATE ops.job_manifests
            SET state_code = $2, completed_utc = NOW(),
                checkpoint_data = COALESCE($3, checkpoint_data),
                error_code = $4, error_text = $5
            WHERE job_id = $1
            """,
            job_id,
            state_code,
            checkpoint_data,
            error_code,
            error_text,
        )
    else:
        await pool.execute(
            """
            UPDATE ops.job_manifests
            SET state_code = $2,
                checkpoint_data = COALESCE($3, checkpoint_data),
                error_code = $4, error_text = $5
            WHERE job_id = $1
            """,
            job_id,
            state_code,
            checkpoint_data,
            error_code,
            error_text,
        )

    logger.info("job_state_updated", job_id=str(job_id), state=state_code)


async def complete_job(pool: asyncpg.Pool, job_id: uuid.UUID) -> None:
    """Mark a job as completed."""
    await update_job_state(pool, job_id, "completed")
