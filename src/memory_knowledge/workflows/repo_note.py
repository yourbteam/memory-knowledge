"""Repo-scoped note authoring (Gap #1 §1.4 / repo-scoped-note-authoring plan).

A repo *note* is a human-asserted, evidence-free `learned_records` row anchored to a
per-repo **root entity** (`entity_type='repository'`). This module provides the root-entity
anchor (S1); the full `author_repo_note` write is S2.

Why a root entity: durable repo-scoped memory scopes through `scope_entity_id → catalog.entities`,
and entities are otherwise only file/symbol/chunk. A repo-level note is about no specific file,
so it anchors to a stable per-repo root instead.
"""
from __future__ import annotations

import neo4j
import asyncpg
import structlog

from memory_knowledge.identity.entity_key import repository_root_entity_key

logger = structlog.get_logger()

REPOSITORY_ROOT_ENTITY_TYPE = "repository"


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
