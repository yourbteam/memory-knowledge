"""One-time migration: recreate all Qdrant collections at the configured embedding
dimension and re-embed all ACTIVE content from the PG source of truth, using whatever
embedding backend `embed()` currently resolves to (local fastembed in codex mode).

Run OFFLINE against the remote stores. Destructive: drops and recreates collections.
Take a snapshot first (snapshot_collections). Per-revision payload values are preserved
so retrieval filters (branch_name / commit_sha / retrieval_surface / is_active) stay correct.
"""
from __future__ import annotations

import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.db.qdrant import COLLECTIONS, ensure_collections
from memory_knowledge.llm.openai_client import embed
from memory_knowledge.projections.qdrant_payload_schemas import (
    CodeChunkPayload,
    LearnedMemoryPayload,
    SummaryPayload,
)

logger = structlog.get_logger()

BATCH_SIZE = 256


async def snapshot_collections(client: AsyncQdrantClient) -> dict[str, str]:
    """Best-effort snapshot of each existing collection (rollback point)."""
    result: dict[str, str] = {}
    existing = {c.name for c in (await client.get_collections()).collections}
    for name in COLLECTIONS:
        if name not in existing:
            result[name] = "absent"
            continue
        try:
            snap = await client.create_snapshot(collection_name=name, wait=True)
            result[name] = getattr(snap, "name", "ok")
        except Exception as exc:
            result[name] = f"error: {exc}"
            logger.warning("snapshot_failed", collection=name, error=str(exc))
    logger.info("snapshots_taken", result=result)
    return result


async def recreate_all(client: AsyncQdrantClient, settings: Settings) -> None:
    """Drop every collection then recreate at settings.embedding_dimensions (+indexes)."""
    for name in COLLECTIONS:
        try:
            await client.delete_collection(collection_name=name)
        except Exception as exc:
            logger.warning("delete_collection_failed", collection=name, error=str(exc))
    await ensure_collections(client, settings)  # recreates all at current dim + payload indexes
    logger.info("collections_recreated", dim=settings.embedding_dimensions)


async def _embed_and_upsert(
    client: AsyncQdrantClient,
    settings: Settings,
    collection: str,
    rows: list[dict],
) -> int:
    """rows: [{'id': str, 'text': str, 'payload': dict}]. Embeds text, upserts points."""
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        vectors = await embed([r["text"] for r in batch], settings)
        points = [
            models.PointStruct(id=r["id"], vector=v, payload=r["payload"])
            for r, v in zip(batch, vectors)
        ]
        await client.upsert(collection_name=collection, points=points)
        total += len(points)
    return total


async def reembed_code_chunks(pool, client, settings, repository_id, repository_key) -> int:
    rows = await pool.fetch(
        """
        SELECT e.entity_key, c.content_text, c.chunk_type, c.title,
               f.file_path, rr.commit_sha, rr.branch_name
        FROM catalog.chunks c
        JOIN catalog.entities e ON c.entity_id = e.id
        JOIN catalog.files f ON c.file_id = f.id
        JOIN catalog.repo_revisions rr ON e.repo_revision_id = rr.id
        WHERE e.repository_id = $1 AND c.is_active = TRUE
        """,
        repository_id,
    )
    payload_rows = []
    for r in rows:
        if not r["content_text"]:
            continue
        branch = r["branch_name"] or "main"
        symbol_name = None
        title = r["title"] or ""
        if ":" in title:
            symbol_name = title.split(":", 1)[1].split("[")[0]
        payload = {
            "entity_key": str(r["entity_key"]),
            "repository_key": repository_key,
            "commit_sha": r["commit_sha"],
            "branch_name": branch,
            "file_path": r["file_path"],
            "symbol_name": symbol_name,
            "chunk_type": r["chunk_type"],
            "is_active": True,
            "retrieval_surface": f"live_branch:{branch}",
            "content_kind": "code_chunk",
        }
        CodeChunkPayload.model_validate(payload)
        payload_rows.append(
            {"id": str(r["entity_key"]), "text": r["content_text"], "payload": payload}
        )
    return await _embed_and_upsert(client, settings, "code_chunks", payload_rows)


async def reembed_summaries(pool, client, settings, repository_id, repository_key) -> int:
    rows = await pool.fetch(
        """
        SELECT e.entity_key, s.summary_text, s.summary_level, rr.commit_sha
        FROM catalog.summaries s
        JOIN catalog.entities e ON s.entity_id = e.id
        JOIN catalog.repo_revisions rr ON e.repo_revision_id = rr.id
        WHERE e.repository_id = $1 AND s.is_active = TRUE
        """,
        repository_id,
    )
    payload_rows = []
    for r in rows:
        if not r["summary_text"]:
            continue
        payload = {
            "entity_key": str(r["entity_key"]),
            "repository_key": repository_key,
            "commit_sha": r["commit_sha"],
            "summary_level": r["summary_level"],
            "is_active": True,
            "content_kind": "summary",
        }
        SummaryPayload.model_validate(payload)
        payload_rows.append(
            {"id": str(r["entity_key"]), "text": r["summary_text"], "payload": payload}
        )
    return await _embed_and_upsert(client, settings, "summary_units", payload_rows)


async def reembed_learned(pool, client, settings, repository_id, repository_key) -> int:
    rows = await pool.fetch(
        """
        SELECT e.entity_key, lr.body_text, lr.memory_type, lr.confidence,
               lr.applicability_mode, se.entity_key AS scope_entity_key
        FROM memory.learned_records lr
        JOIN catalog.entities e ON lr.entity_id = e.id
        LEFT JOIN catalog.entities se ON lr.scope_entity_id = se.id
        WHERE e.repository_id = $1 AND lr.is_active = TRUE
          AND lr.verification_status = 'verified'
        """,
        repository_id,
    )
    payload_rows = []
    for r in rows:
        if not r["body_text"]:
            continue
        scope_key = str(r["scope_entity_key"]) if r["scope_entity_key"] else str(r["entity_key"])
        payload = {
            "entity_key": str(r["entity_key"]),
            "repository_key": repository_key,
            "memory_type": r["memory_type"] or "",
            "confidence": float(r["confidence"]) if r["confidence"] is not None else 0.0,
            "applicability_mode": r["applicability_mode"] or "repository",
            "scope_entity_key": scope_key,
            "is_active": True,
            "content_kind": "learned_rule",
        }
        LearnedMemoryPayload.model_validate(payload)
        payload_rows.append(
            {"id": str(r["entity_key"]), "text": r["body_text"], "payload": payload}
        )
    return await _embed_and_upsert(client, settings, "learned_memory", payload_rows)
