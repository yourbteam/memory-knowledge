from __future__ import annotations

import uuid
import json
from typing import Any

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
    evidence_entity_id: int | None,
    evidence_chunk_id: int | None,
    verification_status: str = "unverified",
    is_active: bool = True,
    content_kind: str | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    evidence_resolution_errors: list[dict[str, Any]] | None = None,
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
             verification_status, is_active, content_kind, evidence_refs,
             evidence_resolution_errors)
        VALUES ($1, $2, $3, $4, $5, to_tsvector('english', $5), $6, $7, $8,
                $9, $10, $11, $12, $13, $14, $15::jsonb, $16::jsonb)
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
        content_kind,
        json.dumps(evidence_refs) if evidence_refs is not None else None,
        json.dumps(evidence_resolution_errors) if evidence_resolution_errors is not None else None,
    )
    logger.info("learned_record_upserted", entity_key=str(entity_key), status=verification_status)
    return row["id"]


async def insert_operator_note_create_only(
    pool: asyncpg.Pool,
    *,
    entity_key: uuid.UUID,
    entity_id: int,
    scope_entity_id: int,
    title: str,
    body_text: str,
    confidence: float,
    applicability_mode: str,
    valid_from_revision_id: int,
    verification_status: str,
    content_kind: str,
    evidence_refs: list[dict[str, Any]],
) -> tuple[int, bool]:
    """Insert one operator note without ever overwriting an existing record.

    Returns ``(learned_record_id, idempotent_retry)``. Only an active unverified
    byte-identical record is replayable; every other identity collision fails.
    """
    ent_row = await pool.fetchrow(
        """
        INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id)
        SELECT $1, 'learned_record', e.repository_id, e.repo_revision_id
        FROM catalog.entities e WHERE e.id = $2
        ON CONFLICT (entity_key) DO NOTHING
        RETURNING id
        """,
        entity_key,
        entity_id,
    )
    if ent_row is None:
        ent_row = await pool.fetchrow(
            "SELECT id FROM catalog.entities WHERE entity_key = $1",
            entity_key,
        )
    learned_entity_id = ent_row["id"]
    existing = await pool.fetchrow(
        """
        SELECT id, title, body_text, confidence, applicability_mode,
               verification_status, is_active, content_kind, evidence_refs
        FROM memory.learned_records WHERE entity_id = $1 FOR UPDATE
        """,
        learned_entity_id,
    )
    canonical_refs = json.dumps(evidence_refs, sort_keys=True, separators=(",", ":"))
    if existing is not None:
        existing_refs = json.dumps(
            existing["evidence_refs"] or [], sort_keys=True, separators=(",", ":")
        )
        identical = (
            existing["verification_status"] == "unverified"
            and bool(existing["is_active"])
            and existing["title"] == title
            and existing["body_text"] == body_text
            and float(existing["confidence"]) == float(confidence)
            and (existing["applicability_mode"] or "repository") == applicability_mode
            and existing["content_kind"] == content_kind
            and existing_refs == canonical_refs
        )
        if identical:
            return existing["id"], True
        raise ValueError("candidate-identity-conflict")

    row = await pool.fetchrow(
        """
        INSERT INTO memory.learned_records
            (entity_id, scope_entity_id, memory_type, title, body_text, body_tsv,
             source_kind, confidence, applicability_mode, valid_from_revision_id,
             evidence_entity_id, evidence_chunk_id, verification_status, is_active,
             content_kind, evidence_refs, evidence_resolution_errors)
        VALUES ($1,$2,'operator_note',$3,$4,to_tsvector('english',$4),
                'operator_note',$5,$6,$7,NULL,NULL,$8,TRUE,$9,$10::jsonb,'[]'::jsonb)
        RETURNING id
        """,
        learned_entity_id,
        scope_entity_id,
        title,
        body_text,
        confidence,
        applicability_mode,
        valid_from_revision_id,
        verification_status,
        content_kind,
        canonical_refs,
    )
    return row["id"], False


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


async def supersede_learned_record(pool: asyncpg.Pool, old_record_id: int, new_record_id: int) -> None:
    """Link new record as superseding old, deactivate old."""
    await pool.execute(
        "UPDATE memory.learned_records SET supersedes_learned_record_id = $2 WHERE id = $1",
        old_record_id,
        new_record_id,
    )
    await deactivate_learned_record(pool, old_record_id)
    logger.info("learned_record_superseded", old_id=old_record_id, new_id=new_record_id)
