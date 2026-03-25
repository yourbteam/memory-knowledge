from __future__ import annotations

import uuid

import asyncpg
import structlog

logger = structlog.get_logger()


async def upsert_learned_record(
    pool: asyncpg.Pool,
    entity_key: uuid.UUID,
    entity_id: int,
    scope_entity_id: int,
    memory_type: str,
    title: str,
    body_text: str,
    source_kind: str,
    confidence: float,
    applicability_mode: str,
    valid_from_revision_id: int,
    evidence_entity_id: int,
    evidence_chunk_id: int,
    verification_status: str = "unverified",
    is_active: bool = True,
) -> int:
    """Upsert a learned record with inline tsvector computation. Returns learned_record id."""
    # Ensure entity exists
    ent_row = await pool.fetchrow(
        """
        INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id)
        SELECT $1, 'learned_record', e.repository_id, e.repo_revision_id
        FROM catalog.entities e
        WHERE e.id = $2
        ON CONFLICT (entity_key) DO UPDATE
            SET repo_revision_id = EXCLUDED.repo_revision_id
        RETURNING id
        """,
        entity_key,
        entity_id,
    )
    learned_entity_id = ent_row["id"]

    row = await pool.fetchrow(
        """
        INSERT INTO memory.learned_records
            (entity_id, scope_entity_id, memory_type, title, body_text,
             body_tsv, source_kind, confidence, applicability_mode,
             valid_from_revision_id, evidence_entity_id, evidence_chunk_id,
             verification_status, is_active)
        VALUES ($1, $2, $3, $4, $5, to_tsvector('english', $5), $6, $7, $8,
                $9, $10, $11, $12, $13)
        ON CONFLICT (entity_id) DO UPDATE
            SET body_text = EXCLUDED.body_text,
                body_tsv = to_tsvector('english', EXCLUDED.body_text),
                confidence = EXCLUDED.confidence,
                verification_status = EXCLUDED.verification_status,
                is_active = EXCLUDED.is_active
        RETURNING id
        """,
        learned_entity_id,
        scope_entity_id,
        memory_type,
        title,
        body_text,
        source_kind,
        confidence,
        applicability_mode,
        valid_from_revision_id,
        evidence_entity_id,
        evidence_chunk_id,
        verification_status,
        is_active,
    )
    logger.info("learned_record_upserted", entity_key=str(entity_key), status=verification_status)
    return row["id"]


async def update_verification_status(
    pool: asyncpg.Pool,
    learned_record_id: int,
    verification_status: str,
    verification_notes: str | None = None,
    is_active: bool | None = None,
) -> None:
    """Update verification status and optionally deactivate."""
    if is_active is not None:
        await pool.execute(
            """
            UPDATE memory.learned_records
            SET verification_status = $2, verification_notes = $3, is_active = $4
            WHERE id = $1
            """,
            learned_record_id,
            verification_status,
            verification_notes,
            is_active,
        )
    else:
        await pool.execute(
            """
            UPDATE memory.learned_records
            SET verification_status = $2, verification_notes = $3
            WHERE id = $1
            """,
            learned_record_id,
            verification_status,
            verification_notes,
        )


async def deactivate_learned_record(pool: asyncpg.Pool, learned_record_id: int) -> None:
    """Set is_active=FALSE on a learned record."""
    await pool.execute(
        "UPDATE memory.learned_records SET is_active = FALSE WHERE id = $1",
        learned_record_id,
    )


async def supersede_learned_record(
    pool: asyncpg.Pool, old_record_id: int, new_record_id: int
) -> None:
    """Link new record as superseding old, deactivate old."""
    await pool.execute(
        "UPDATE memory.learned_records SET supersedes_learned_record_id = $2 WHERE id = $1",
        new_record_id,
        old_record_id,
    )
    await deactivate_learned_record(pool, old_record_id)
    logger.info("learned_record_superseded", old_id=old_record_id, new_id=new_record_id)
