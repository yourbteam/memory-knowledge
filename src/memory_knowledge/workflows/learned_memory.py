from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.identity.entity_key import learned_record_entity_key
from memory_knowledge.projections.learned_memory_neo4j import project_learned_rule
from memory_knowledge.projections.learned_memory_qdrant import (
    deactivate_learned_record_point,
    embed_and_upsert_learned_record,
)
from memory_knowledge.projections.learned_memory_writer import (
    deactivate_learned_record,
    supersede_learned_record,
    update_verification_status,
    upsert_learned_record,
)
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()


async def _resolve_entity_key_to_id(
    pool: asyncpg.Pool, entity_key_str: str
) -> int | None:
    """Resolve a UUID entity_key string to its PG integer id."""
    row = await pool.fetchrow(
        "SELECT id FROM catalog.entities WHERE entity_key = $1",
        uuid.UUID(entity_key_str),
    )
    return row["id"] if row else None


async def run_proposal(
    repository_key: str,
    memory_type: str,
    title: str,
    body_text: str,
    evidence_entity_key: str,
    scope_entity_key: str,
    confidence: float,
    applicability_mode: str,
    run_id: uuid.UUID,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    start = time.monotonic()

    try:
        if pool is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name="run_learned_memory_proposal_workflow",
                status="error",
                error="Missing required dependency: pool.",
            )

        # Step 1: Resolve repository
        repo_row = await pool.fetchrow(
            "SELECT id FROM catalog.repositories WHERE repository_key = $1",
            repository_key,
        )
        if repo_row is None:
            raise ValueError(f"Repository not found: {repository_key}")
        repository_id = repo_row["id"]

        # Step 2: Validate evidence entity exists
        evidence_entity_id = await _resolve_entity_key_to_id(pool, evidence_entity_key)
        if evidence_entity_id is None:
            raise ValueError(f"Evidence entity not found: {evidence_entity_key}")

        # Step 3: Validate scope entity exists
        scope_entity_id = await _resolve_entity_key_to_id(pool, scope_entity_key)
        if scope_entity_id is None:
            raise ValueError(f"Scope entity not found: {scope_entity_key}")

        # Step 4: Look up evidence chunk
        chunk_row = await pool.fetchrow(
            "SELECT id FROM catalog.chunks WHERE entity_id = $1",
            evidence_entity_id,
        )
        if chunk_row is None:
            raise ValueError(
                f"Evidence entity {evidence_entity_key} has no associated chunk"
            )
        evidence_chunk_id = chunk_row["id"]

        # Step 5: Get current revision
        rev_row = await pool.fetchrow(
            "SELECT id FROM catalog.repo_revisions WHERE repository_id = $1 ORDER BY id DESC LIMIT 1",
            repository_id,
        )
        valid_from_revision_id = rev_row["id"] if rev_row else 0

        # Step 6: Generate entity key
        title_hash = hashlib.sha256(title.encode()).hexdigest()[:16]
        entity_key = learned_record_entity_key(repository_key, memory_type, title_hash)

        # Step 7: Upsert to PG (unverified, not yet in Qdrant/Neo4j)
        learned_record_id = await upsert_learned_record(
            pool=pool,
            entity_key=entity_key,
            entity_id=evidence_entity_id,  # use evidence entity as reference for repo/revision lookup
            scope_entity_id=scope_entity_id,
            memory_type=memory_type,
            title=title,
            body_text=body_text,
            source_kind="agent_proposal",
            confidence=confidence,
            applicability_mode=applicability_mode,
            valid_from_revision_id=valid_from_revision_id,
            evidence_entity_id=evidence_entity_id,
            evidence_chunk_id=evidence_chunk_id,
            verification_status="unverified",
            is_active=True,
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "proposal_created",
            entity_key=str(entity_key),
            learned_record_id=learned_record_id,
        )

        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_learned_memory_proposal_workflow",
            status="success",
            data={
                "proposal_id": str(entity_key),
                "learned_record_id": learned_record_id,
                "verification_status": "unverified",
            },
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("proposal_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_learned_memory_proposal_workflow",
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )


async def run_commit(
    repository_key: str,
    proposal_id: str,
    approval_status: str,
    run_id: uuid.UUID,
    verification_notes: str | None = None,
    supersedes_id: str | None = None,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    start = time.monotonic()

    try:
        if pool is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name="run_learned_memory_commit_workflow",
                status="error",
                error="Missing required dependency: pool.",
            )

        if approval_status not in ("approve", "reject", "supersede"):
            raise ValueError(
                f"Invalid approval_status: {approval_status}. Must be approve, reject, or supersede."
            )

        # Load proposal from PG
        row = await pool.fetchrow(
            """
            SELECT lr.id, lr.entity_id, lr.scope_entity_id, lr.memory_type,
                   lr.title, lr.body_text, lr.confidence, lr.applicability_mode,
                   e.entity_key, e.repository_id
            FROM memory.learned_records lr
            JOIN catalog.entities e ON lr.entity_id = e.id
            WHERE e.entity_key = $1
            """,
            uuid.UUID(proposal_id),
        )
        if row is None:
            raise ValueError(f"Proposal not found: {proposal_id}")

        learned_record_id = row["id"]
        entity_key_str = str(row["entity_key"])

        # Resolve scope and evidence entity_keys once (shared by approve + supersede)
        scope_ek_row = await pool.fetchrow(
            "SELECT entity_key FROM catalog.entities WHERE id = $1",
            row["scope_entity_id"],
        )
        scope_ek = str(scope_ek_row["entity_key"]) if scope_ek_row else ""

        evidence_ek_row = await pool.fetchrow(
            "SELECT e2.entity_key FROM memory.learned_records lr "
            "JOIN catalog.entities e2 ON lr.evidence_entity_id = e2.id "
            "WHERE lr.id = $1",
            learned_record_id,
        )
        evidence_ek = str(evidence_ek_row["entity_key"]) if evidence_ek_row else None

        async def _approve_and_project() -> None:
            """Shared logic: verify status, embed to Qdrant, project to Neo4j."""
            await update_verification_status(
                pool, learned_record_id, "verified", verification_notes
            )
            if qdrant_client is not None and settings is not None:
                await embed_and_upsert_learned_record(
                    client=qdrant_client,
                    entity_key=entity_key_str,
                    body_text=row["body_text"],
                    repository_key=repository_key,
                    memory_type=row["memory_type"],
                    confidence=float(row["confidence"]) if row["confidence"] else 0.5,
                    applicability_mode=row["applicability_mode"] or "repository",
                    scope_entity_key=scope_ek,
                    settings=settings,
                )
            if neo4j_driver is not None:
                await project_learned_rule(
                    driver=neo4j_driver,
                    entity_key=entity_key_str,
                    memory_type=row["memory_type"],
                    title=row["title"],
                    scope_entity_key=scope_ek,
                    evidence_entity_key=evidence_ek,
                )

        if approval_status == "approve":
            await _approve_and_project()
            logger.info("proposal_approved", entity_key=entity_key_str)
            result_data: dict[str, Any] = {"status": "verified", "entity_key": entity_key_str}

        elif approval_status == "reject":
            await update_verification_status(
                pool, learned_record_id, "rejected", verification_notes, is_active=False
            )
            logger.info("proposal_rejected", entity_key=entity_key_str)
            result_data = {"status": "rejected", "entity_key": entity_key_str}

        elif approval_status == "supersede":
            if supersedes_id is None:
                raise ValueError("supersedes_id is required for approval_status='supersede'")

            await _approve_and_project()

            # Resolve and supersede old record
            old_row = await pool.fetchrow(
                """
                SELECT lr.id FROM memory.learned_records lr
                JOIN catalog.entities e ON lr.entity_id = e.id
                WHERE e.entity_key = $1
                """,
                uuid.UUID(supersedes_id),
            )
            if old_row:
                await supersede_learned_record(pool, old_row["id"], learned_record_id)
                if qdrant_client is not None:
                    await deactivate_learned_record_point(qdrant_client, supersedes_id)
                if neo4j_driver is not None:
                    from memory_knowledge.projections.learned_memory_neo4j import (
                        deactivate_learned_rule,
                    )

                    await deactivate_learned_rule(neo4j_driver, supersedes_id)

            logger.info(
                "proposal_superseded",
                new_entity_key=entity_key_str,
                old_entity_key=supersedes_id,
            )
            result_data = {
                "status": "superseded",
                "new_entity_key": entity_key_str,
                "old_entity_key": supersedes_id,
            }

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_learned_memory_commit_workflow",
            status="success",
            data=result_data,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("commit_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_learned_memory_commit_workflow",
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
