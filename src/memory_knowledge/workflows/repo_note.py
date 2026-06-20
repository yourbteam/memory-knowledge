"""Repo-scoped note authoring (Gap #1 §1.4 / repo-scoped-note-authoring plan).

A repo *note* is a human-asserted, evidence-free `learned_records` row anchored to a
per-repo **root entity** (`entity_type='repository'`). This module provides the root-entity
anchor (S1); the full `author_repo_note` write is S2.

Why a root entity: durable repo-scoped memory scopes through `scope_entity_id → catalog.entities`,
and entities are otherwise only file/symbol/chunk. A repo-level note is about no specific file,
so it anchors to a stable per-repo root instead.
"""
from __future__ import annotations

import hashlib
import time
import uuid

import neo4j
import asyncpg
import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.identity.entity_key import learned_record_entity_key, repository_root_entity_key
from memory_knowledge.projections.learned_memory_neo4j import project_learned_rule
from memory_knowledge.projections.learned_memory_qdrant import embed_and_upsert_learned_record
from memory_knowledge.projections.learned_memory_writer import upsert_learned_record
from memory_knowledge.workflows.base import WorkflowResult
from memory_knowledge.workflows.learned_memory import VALID_MEMORY_TYPES

logger = structlog.get_logger()

REPOSITORY_ROOT_ENTITY_TYPE = "repository"
NOTE_SOURCE_KIND = "operator_note"
NOTE_VERIFICATION_STATUS = "human_asserted"
# Trust tiers for a note: a human-confirmed assertion vs an auto-captured candidate (#2).
# Auto-capture writes 'unverified' candidates (evidence-grade) for later promotion.
VALID_NOTE_VERIFICATION = {"human_asserted", "unverified"}


async def ensure_repo_root_entity(
    pool: asyncpg.Pool,
    repository_key: str,
    neo4j_driver: neo4j.AsyncDriver | None = None,
) -> tuple[str, int]:
    """Idempotently ensure a repo has a root entity; return (entity_key, entity_id).

    PG is authoritative. `catalog.entities.repo_revision_id` is NOT NULL, so the repo must
    have at least one ingested revision — raises a clear error otherwise (a non-ingested repo
    cannot hold repo-scoped memory). The Neo4j node is best-effort: repo-note retrieval rides
    the direct `learned_memory` Qdrant search, not the `APPLIES_TO` edge (see plan §3).
    """
    repo_row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1",
        repository_key,
    )
    if repo_row is None:
        raise ValueError(f"Repository not found: {repository_key}")
    repository_id = repo_row["id"]

    rev_row = await pool.fetchrow(
        "SELECT id FROM catalog.repo_revisions WHERE repository_id = $1 ORDER BY id DESC LIMIT 1",
        repository_id,
    )
    if rev_row is None:
        raise ValueError(
            f"Repository {repository_key} has no ingested revision; cannot anchor repo-scoped memory."
        )
    repo_revision_id = rev_row["id"]

    entity_key = repository_root_entity_key(repository_key)

    # Idempotent: same repo -> same deterministic entity_key -> insert-or-noop, then read the id.
    row = await pool.fetchrow(
        """
        INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (entity_key) DO NOTHING
        RETURNING id
        """,
        entity_key,
        REPOSITORY_ROOT_ENTITY_TYPE,
        repository_id,
        repo_revision_id,
    )
    if row is not None:
        entity_id = row["id"]
    else:
        existing = await pool.fetchrow(
            "SELECT id FROM catalog.entities WHERE entity_key = $1", entity_key
        )
        entity_id = existing["id"]

    # Best-effort Neo4j node so the (optional) APPLIES_TO edge can MATCH it. Never block on it.
    if neo4j_driver is not None:
        try:
            await neo4j_driver.execute_query(
                """
                MERGE (root:RepositoryRoot {entity_key: $entity_key})
                SET root.repository_key = $repository_key
                """,
                entity_key=str(entity_key),
                repository_key=repository_key,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort; retrieval does not depend on it
            logger.warning("repo_root_neo4j_merge_failed", repository_key=repository_key, error=str(exc))

    return str(entity_key), entity_id


async def run_author_note(
    *,
    repository_key: str,
    title: str,
    body_text: str,
    run_id: uuid.UUID,
    memory_type: str = "note",
    confidence: float = 0.8,
    applicability_mode: str = "repository",
    verification_status: str = NOTE_VERIFICATION_STATUS,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    """Author a human-asserted, evidence-free repo-scoped note.

    Single write: ensure the repo-root anchor (S1), insert the `learned_records` row
    (human-asserted, NULL evidence), embed it into the `learned_memory` Qdrant collection
    (repo-scoped payload — what the retrieval extension filters on), and best-effort-project
    the Neo4j edge. Idempotent: the learned-record entity_key is derived from
    (repository_key, memory_type, title-hash), so re-authoring the same note upserts in place.
    """
    start = time.monotonic()
    tool = "author_repo_note"
    try:
        if pool is None or settings is None:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error",
                error="Missing required dependency: pool/settings.",
            )
        if not title or not body_text:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error",
                error="title and body_text are required.",
            )
        if memory_type not in VALID_MEMORY_TYPES:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error",
                error=f"Invalid memory_type: {memory_type}. Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}",
            )
        if verification_status not in VALID_NOTE_VERIFICATION:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error",
                error=f"Invalid verification_status: {verification_status}. Must be one of: {', '.join(sorted(VALID_NOTE_VERIFICATION))}",
            )

        # S1 anchor (also validates repo + ingested revision; raises with a clear message otherwise)
        root_entity_key, root_entity_id = await ensure_repo_root_entity(
            pool, repository_key, neo4j_driver=neo4j_driver
        )

        # learned_records.valid_from_revision_id: the repo's latest revision
        rev_row = await pool.fetchrow(
            "SELECT id FROM catalog.repo_revisions WHERE repository_id = "
            "(SELECT id FROM catalog.repositories WHERE repository_key = $1) ORDER BY id DESC LIMIT 1",
            repository_key,
        )
        valid_from_revision_id = rev_row["id"] if rev_row else 0

        title_hash = hashlib.sha256(title.encode()).hexdigest()[:16]
        entity_key = learned_record_entity_key(repository_key, memory_type, title_hash)

        learned_record_id = await upsert_learned_record(
            pool=pool,
            entity_key=entity_key,
            entity_id=root_entity_id,        # inherit repo/revision from the root
            scope_entity_id=root_entity_id,  # the note applies to the repo (root)
            memory_type=memory_type,
            title=title,
            body_text=body_text,
            source_kind=NOTE_SOURCE_KIND,
            confidence=confidence,
            applicability_mode=applicability_mode,
            valid_from_revision_id=valid_from_revision_id,
            evidence_entity_id=None,   # evidence-free
            evidence_chunk_id=None,
            verification_status=verification_status,
            is_active=True,
        )

        # Retrieval path: embed into the learned_memory collection (repository_key payload).
        if qdrant_client is not None:
            await embed_and_upsert_learned_record(
                client=qdrant_client,
                entity_key=str(entity_key),
                body_text=body_text,
                repository_key=repository_key,
                memory_type=memory_type,
                confidence=confidence,
                applicability_mode=applicability_mode,
                scope_entity_key=root_entity_key,
                settings=settings,
            )

        # Best-effort Neo4j edge (retrieval does not depend on it — see plan §3).
        if neo4j_driver is not None:
            try:
                await project_learned_rule(
                    driver=neo4j_driver,
                    entity_key=str(entity_key),
                    memory_type=memory_type,
                    title=title,
                    scope_entity_key=root_entity_key,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("repo_note_neo4j_project_failed", repository_key=repository_key, error=str(exc))

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("repo_note_authored", repository_key=repository_key, entity_key=str(entity_key))
        return WorkflowResult(
            run_id=str(run_id), tool_name=tool, status="success",
            data={"entity_key": str(entity_key), "learned_record_id": learned_record_id,
                  "repository_key": repository_key, "verification_status": NOTE_VERIFICATION_STATUS},
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("repo_note_author_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id), tool_name=tool, status="error", error=str(exc), duration_ms=duration_ms
        )
