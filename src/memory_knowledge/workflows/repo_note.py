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
from typing import Any

import neo4j
import asyncpg
import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.identity.entity_key import learned_record_entity_key, repository_root_entity_key
from memory_knowledge.projections.learned_memory_neo4j import project_learned_rule
from memory_knowledge.projections.learned_memory_qdrant import (
    deactivate_learned_record_point,
    embed_and_upsert_learned_record,
)
from memory_knowledge.projections.learned_memory_writer import (
    deactivate_learned_record,
    insert_operator_note_create_only,
)
from memory_knowledge.structure.entity_registrar import upsert_repo_revision
from memory_knowledge.workflows.base import WorkflowResult
from memory_knowledge.workflows.learned_memory import (
    VALID_MEMORY_TYPES,
    learned_record_is_eligible,
    resolve_evidence_refs,
    validate_operational_content,
)

logger = structlog.get_logger()

REPOSITORY_ROOT_ENTITY_TYPE = "repository"
NOTE_SOURCE_KIND = "operator_note"
NOTE_VERIFICATION_STATUS = "human_asserted"
# Trust tiers for a note: a human-confirmed assertion vs an auto-captured candidate (#2).
# Auto-capture writes 'unverified' candidates (evidence-grade) for later promotion.
VALID_NOTE_VERIFICATION = {"human_asserted", "unverified"}
# A2: sentinel revision created on demand so notes can anchor WITHOUT full source ingestion.
# Source-retrieval / branch_heads readers never see it (no files/chunks, branch_heads untouched);
# direct latest-`repo_revisions` readers (integrity freshness/repair) must filter it out.
NOTE_ANCHOR_COMMIT_SHA = "__note_anchor__"
NOTE_ANCHOR_BRANCH = "__notes__"


async def _resolve_repository(
    pool: asyncpg.Pool, repository_key: str
) -> asyncpg.Record | None:
    """Resolve a repo by **case-insensitive exact** match; return its row (canonical key + id) or None.

    A1 (Locked Decision 2): `lower(repository_key) = lower($1)`, no wildcards. Prefer an exact-case
    hit, else lowest id (deterministic). On a pathological case-collision (>1 row differing only by
    case) log `repo_key_case_collision` and take the deterministic pick.
    """
    rows = await pool.fetch(
        """
        SELECT id, repository_key
        FROM catalog.repositories
        WHERE lower(repository_key) = lower($1)
        ORDER BY (repository_key = $1) DESC, id ASC
        """,
        repository_key,
    )
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "repo_key_case_collision",
            given=repository_key,
            matches=[r["repository_key"] for r in rows],
            picked=rows[0]["repository_key"],
        )
    return rows[0]


async def ensure_repo_root_entity(
    pool: asyncpg.Pool,
    repository_key: str,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    auto_create_revision: bool = True,
) -> tuple[str, int, str]:
    """Idempotently ensure a repo has a root entity; return (entity_key, entity_id, canonical_key).

    A1: the repo is resolved **case-insensitively** and the **canonical** stored key is returned
    so every downstream key/payload uses one casing (read-back consistency).

    A2: `catalog.entities.repo_revision_id` is NOT NULL. Rather than require full source ingestion,
    when the repo has no revision and ``auto_create_revision`` is True we create a synthetic
    note-anchor revision (`__note_anchor__`) — no source files/chunks/embeddings — so a note can
    anchor. With ``auto_create_revision=False`` the old strict behavior (raise) is preserved.

    The Neo4j node is best-effort: repo-note retrieval rides the direct `learned_memory` Qdrant
    search, not the `APPLIES_TO` edge.
    """
    repo_row = await _resolve_repository(pool, repository_key)
    if repo_row is None:
        raise ValueError(f"Repository not found: {repository_key}")
    repository_id = repo_row["id"]
    canonical_key = repo_row["repository_key"]

    rev_row = await pool.fetchrow(
        "SELECT id FROM catalog.repo_revisions WHERE repository_id = $1 ORDER BY id DESC LIMIT 1",
        repository_id,
    )
    if rev_row is not None:
        repo_revision_id = rev_row["id"]
    elif auto_create_revision:
        # A2 keystone: anchor notes without embedding source. Idempotent via
        # ON CONFLICT (repository_id, commit_sha) inside upsert_repo_revision.
        repo_revision_id = await upsert_repo_revision(
            pool, repository_id, NOTE_ANCHOR_COMMIT_SHA, NOTE_ANCHOR_BRANCH
        )
        logger.info(
            "note_anchor_revision_created",
            repository_key=canonical_key,
            repo_revision_id=repo_revision_id,
        )
    else:
        raise ValueError(
            f"Repository {canonical_key} has no ingested revision; cannot anchor repo-scoped memory."
        )

    entity_key = repository_root_entity_key(canonical_key)

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
                repository_key=canonical_key,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort; retrieval does not depend on it
            logger.warning("repo_root_neo4j_merge_failed", repository_key=canonical_key, error=str(exc))

    return str(entity_key), entity_id, canonical_key


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
    content_kind: str | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    """Author an evidence-anchored repo-scoped note without identity overwrite."""
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
        if content_kind is None or evidence_refs is None:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error",
                error="content_kind and evidence_refs are required.",
            )

        validate_operational_content(
            title=title, body_text=body_text, content_kind=content_kind,
            evidence_refs=evidence_refs,
        )
        async with pool.acquire() as conn:
            async with conn.transaction():
                canonical_evidence_repo, canonical_refs = await resolve_evidence_refs(
                    conn, repository_key, evidence_refs
                )
                root_entity_key, root_entity_id, canonical_key = await ensure_repo_root_entity(
                    conn, repository_key, neo4j_driver=None
                )
                if canonical_evidence_repo != canonical_key:
                    raise ValueError("cross-repository-evidence")
                rev_row = await conn.fetchrow(
                    "SELECT id FROM catalog.repo_revisions WHERE repository_id = "
                    "(SELECT id FROM catalog.repositories WHERE repository_key = $1) "
                    "ORDER BY id DESC LIMIT 1", canonical_key,
                )
                valid_from_revision_id = rev_row["id"] if rev_row else 0
                title_hash = hashlib.sha256(title.encode()).hexdigest()[:16]
                entity_key = learned_record_entity_key(canonical_key, memory_type, title_hash)
                learned_record_id, idempotent_retry = await insert_operator_note_create_only(
                    pool=conn, entity_key=entity_key, entity_id=root_entity_id,
                    scope_entity_id=root_entity_id, title=title, body_text=body_text,
                    confidence=confidence, applicability_mode=applicability_mode,
                    valid_from_revision_id=valid_from_revision_id,
                    verification_status=verification_status, content_kind=content_kind,
                    evidence_refs=canonical_refs,
                )
                eligible = learned_record_is_eligible({
                    "memory_type": "operator_note", "source_kind": NOTE_SOURCE_KIND,
                    "verification_status": verification_status, "is_active": True,
                    "content_kind": content_kind, "evidence_refs": canonical_refs,
                    "evidence_resolution_errors": [],
                })
                if eligible and qdrant_client is not None:
                    await embed_and_upsert_learned_record(
                        client=qdrant_client, entity_key=str(entity_key), body_text=body_text,
                        repository_key=canonical_key, memory_type=memory_type,
                        confidence=confidence, applicability_mode=applicability_mode,
                        scope_entity_key=root_entity_key, settings=settings,
                    )
                if eligible and neo4j_driver is not None:
                    try:
                        await project_learned_rule(
                            driver=neo4j_driver, entity_key=str(entity_key),
                            memory_type=memory_type, title=title,
                            scope_entity_key=root_entity_key,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "repo_note_neo4j_project_failed",
                            repository_key=repository_key, error=str(exc),
                        )

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("repo_note_authored", repository_key=canonical_key, entity_key=str(entity_key))
        return WorkflowResult(
            run_id=str(run_id), tool_name=tool, status="success",
            data={"entity_key": str(entity_key), "learned_record_id": learned_record_id,
                  "repository_key": canonical_key, "verification_status": verification_status,
                  "content_kind": content_kind, "evidence_refs": canonical_refs,
                  "idempotent_retry": idempotent_retry, "eligible": eligible},
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("repo_note_author_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id), tool_name=tool, status="error", error=str(exc), duration_ms=duration_ms
        )


async def run_deactivate_note(
    *,
    repository_key: str,
    title: str,
    run_id: uuid.UUID,
    memory_type: str = "note",
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
) -> WorkflowResult:
    """Deactivate a repo-scoped note — the counterpart to ``run_author_note``.

    Resolves the note by its deterministic ``entity_key`` (repository_key, memory_type,
    title-hash — the same derivation ``run_author_note`` used), then deactivates it
    **symmetrically**: ``is_active=FALSE`` in PG (authoritative) and on the Qdrant
    ``learned_memory`` point (what repo-scoped retrieval filters on, retrieval.py:319/868),
    so the note stops surfacing. Idempotent: re-running on an already-inactive note succeeds.
    """
    start = time.monotonic()
    tool = "deactivate_repo_note"
    try:
        if pool is None:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error", error="Missing required dependency: pool.",
            )
        if not title:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error", error="title is required.",
            )
        if memory_type not in VALID_MEMORY_TYPES:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error",
                error=f"Invalid memory_type: {memory_type}. Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}",
            )

        # A1: canonicalize the repo key BEFORE deriving the entity_key, so a deactivate call under
        # any casing computes the same entity_key authoring wrote under. Read-only (never creates a
        # revision). Repo absent -> "no note found" (symmetric with the not-found case below).
        repo_row = await _resolve_repository(pool, repository_key)
        if repo_row is None:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error",
                error=(f"No repo note found for repository_key={repository_key!r}, title={title!r} "
                       f"(repository not found)."),
            )
        canonical_key = repo_row["repository_key"]

        title_hash = hashlib.sha256(title.encode()).hexdigest()[:16]
        entity_key = learned_record_entity_key(canonical_key, memory_type, title_hash)

        # learned_records has no entity_key column; the note's entity_key lives on catalog.entities,
        # referenced by learned_records.entity_id (see upsert_learned_record). Resolve via the join.
        row = await pool.fetchrow(
            """
            SELECT lr.id, lr.is_active
            FROM memory.learned_records lr
            JOIN catalog.entities e ON lr.entity_id = e.id
            WHERE e.entity_key = $1
            """,
            entity_key,
        )
        if row is None:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error",
                error=(f"No repo note found for repository_key={repository_key!r}, title={title!r} "
                       f"(memory_type={memory_type}, entity_key={entity_key})."),
            )

        await deactivate_learned_record(pool, row["id"])  # PG authoritative

        # Qdrant payload flag (what retrieval filters on). Best-effort: PG is the source of truth.
        if qdrant_client is not None:
            try:
                await deactivate_learned_record_point(qdrant_client, str(entity_key))
            except Exception as exc:  # noqa: BLE001
                logger.warning("repo_note_qdrant_deactivate_failed", repository_key=repository_key, error=str(exc))

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("repo_note_deactivated", repository_key=repository_key, entity_key=str(entity_key))
        return WorkflowResult(
            run_id=str(run_id), tool_name=tool, status="success",
            data={"entity_key": str(entity_key), "learned_record_id": row["id"],
                  "repository_key": repository_key, "was_active": row["is_active"]},
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("repo_note_deactivate_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id), tool_name=tool, status="error", error=str(exc), duration_ms=duration_ms
        )
