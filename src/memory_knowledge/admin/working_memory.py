from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()

VALID_OBSERVATION_TYPES = {
    "inspected",
    "hypothesized_about",
    "proposed_change_to",
    "issue_found",
    "plan_note",
    "rejected_path",
}


async def create_session(
    pool: asyncpg.Pool, repository_key: str
) -> uuid.UUID:
    """Create a new working session. Returns session_key."""
    row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1",
        repository_key,
    )
    if row is None:
        raise ValueError(f"Repository not found: {repository_key}")
    repository_id = row["id"]

    session_key = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO memory.working_sessions (repository_id, session_key)
        VALUES ($1, $2)
        """,
        repository_id,
        session_key,
    )
    logger.info("working_session_created", session_key=str(session_key))
    return session_key


async def record_observation(
    pool: asyncpg.Pool,
    session_key: uuid.UUID,
    entity_key: str,
    observation_type: str,
    observation_text: str,
) -> int:
    """Record a working observation for a session."""
    if observation_type not in VALID_OBSERVATION_TYPES:
        raise ValueError(
            f"Invalid observation_type: {observation_type}. "
            f"Must be one of: {', '.join(sorted(VALID_OBSERVATION_TYPES))}"
        )

    # Resolve session_id
    session_row = await pool.fetchrow(
        "SELECT id FROM memory.working_sessions WHERE session_key = $1",
        session_key,
    )
    if session_row is None:
        raise ValueError(f"Session not found: {session_key}")
    session_id = session_row["id"]

    # Resolve entity_id
    entity_row = await pool.fetchrow(
        "SELECT id FROM catalog.entities WHERE entity_key = $1",
        uuid.UUID(entity_key),
    )
    entity_id = entity_row["id"] if entity_row else None

    row = await pool.fetchrow(
        """
        INSERT INTO memory.working_observations
            (session_id, entity_id, observation_type, observation_text)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        session_id,
        entity_id,
        observation_type,
        observation_text,
    )
    return row["id"]


async def end_session(pool: asyncpg.Pool, session_key: uuid.UUID) -> None:
    """End a working session."""
    await pool.execute(
        "UPDATE memory.working_sessions SET ended_utc = NOW() WHERE session_key = $1",
        session_key,
    )
    logger.info("working_session_ended", session_key=str(session_key))


async def get_session_observations(
    pool: asyncpg.Pool, session_key: uuid.UUID
) -> list[dict[str, Any]]:
    """Get all observations for a session."""
    rows = await pool.fetch(
        """
        SELECT wo.id, wo.observation_type, wo.observation_text,
               wo.created_utc, e.entity_key,
               f.file_path, s.symbol_name
        FROM memory.working_observations wo
        JOIN memory.working_sessions ws ON wo.session_id = ws.id
        LEFT JOIN catalog.entities e ON wo.entity_id = e.id
        LEFT JOIN catalog.files f ON f.entity_id = e.id AND e.entity_type = 'file'
        LEFT JOIN catalog.symbols s ON s.entity_id = e.id AND e.entity_type = 'symbol'
        WHERE ws.session_key = $1
        ORDER BY wo.created_utc
        """,
        session_key,
    )
    return [
        {
            "id": r["id"],
            "observation_type": r["observation_type"],
            "observation_text": r["observation_text"],
            "entity_key": str(r["entity_key"]) if r["entity_key"] else None,
            "file_path": r["file_path"],
            "symbol_name": r["symbol_name"],
            "created_utc": r["created_utc"].isoformat() if r["created_utc"] else None,
        }
        for r in rows
    ]


async def get_recent_sessions(
    pool: asyncpg.Pool, repository_key: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Get recent working sessions for a repository."""
    rows = await pool.fetch(
        """
        SELECT ws.session_key, ws.started_utc, ws.ended_utc,
               COUNT(wo.id) AS observation_count
        FROM memory.working_sessions ws
        JOIN catalog.repositories r ON ws.repository_id = r.id
        LEFT JOIN memory.working_observations wo ON wo.session_id = ws.id
        WHERE r.repository_key = $1
        GROUP BY ws.id, ws.session_key, ws.started_utc, ws.ended_utc
        ORDER BY ws.started_utc DESC
        LIMIT $2
        """,
        repository_key,
        limit,
    )
    return [
        {
            "session_key": str(r["session_key"]),
            "started_utc": r["started_utc"].isoformat() if r["started_utc"] else None,
            "ended_utc": r["ended_utc"].isoformat() if r["ended_utc"] else None,
            "observation_count": r["observation_count"],
        }
        for r in rows
    ]
