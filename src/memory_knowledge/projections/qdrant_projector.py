from __future__ import annotations

from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.llm.openai_client import embed

logger = structlog.get_logger()

BATCH_SIZE = 100


async def embed_chunks(chunks_text: list[str], settings: Settings) -> list[list[float]]:
    """Batch embed chunk texts using OpenAI with retry."""
    all_embeddings = await embed(chunks_text, settings)
    logger.info("chunks_embedded", total=len(all_embeddings))
    return all_embeddings


async def upsert_points(
    client: AsyncQdrantClient,
    chunks_with_embeddings: list[dict[str, Any]],
    repository_key: str,
    commit_sha: str,
    branch_name: str,
) -> None:
    """Upsert points to code_chunks collection. Point ID = entity_key UUID string."""
    from memory_knowledge.projections.qdrant_payload_schemas import CodeChunkPayload

    points = []
    for c in chunks_with_embeddings:
        payload = {
            "entity_key": c["entity_key"],
            "repository_key": repository_key,
            "commit_sha": commit_sha,
            "branch_name": branch_name,
            "file_path": c["file_path"],
            "symbol_name": c.get("symbol_name"),
            "chunk_type": c["chunk_type"],
            "is_active": True,
            "retrieval_surface": f"live_branch:{branch_name}",
            "content_kind": "code_chunk",
        }
        CodeChunkPayload.model_validate(payload)
        points.append(
            models.PointStruct(
                id=c["entity_key"],
                vector=c["embedding"],
                payload=payload,
            )
        )

    for i in range(0, len(points), BATCH_SIZE):
        await client.upsert(
            collection_name="code_chunks",
            points=points[i : i + BATCH_SIZE],
        )

    logger.info("qdrant_points_upserted", count=len(points))


async def deactivate_old_points(
    client: AsyncQdrantClient,
    repository_key: str,
    branch_name: str,
    new_commit_sha: str,
) -> None:
    """Set is_active=False on old points for this repo+branch."""
    await client.set_payload(
        collection_name="code_chunks",
        payload={"is_active": False},
        points=models.Filter(
            must=[
                models.FieldCondition(
                    key="repository_key",
                    match=models.MatchValue(value=repository_key),
                ),
                models.FieldCondition(
                    key="branch_name",
                    match=models.MatchValue(value=branch_name),
                ),
            ],
            must_not=[
                models.FieldCondition(
                    key="commit_sha",
                    match=models.MatchValue(value=new_commit_sha),
                ),
            ],
        ),
    )
    logger.info(
        "old_points_deactivated",
        repository_key=repository_key,
        branch_name=branch_name,
    )


async def deactivate_unbacked_points(
    client: AsyncQdrantClient,
    collection_name: str,
    repository_key: str,
    active_entity_keys: set[str],
) -> int:
    """Set is_active=False on currently-active points not backed by active PG.

    The point ID is the entity_key (which embeds commit_sha), so an additive
    re-project can never overwrite or deactivate superseded/orphaned points from
    other commits. This reconciles the collection to PG (the source of truth):
    any point that is active in Qdrant but whose entity_key is not in the active
    PG set is deactivated. Caller must pass a NON-EMPTY active set — an empty set
    would deactivate everything, so the caller skips reconciliation in that case.
    """
    if not active_entity_keys:
        return 0
    active = {str(k).lower() for k in active_entity_keys}
    orphan_ids: list[Any] = []
    offset = None
    flt = models.Filter(
        must=[
            models.FieldCondition(key="repository_key", match=models.MatchValue(value=repository_key)),
            models.FieldCondition(key="is_active", match=models.MatchValue(value=True)),
        ]
    )
    while True:
        points, offset = await client.scroll(
            collection_name=collection_name,
            scroll_filter=flt,
            limit=1000,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        orphan_ids.extend(p.id for p in points if str(p.id).lower() not in active)
        if offset is None:
            break
    for i in range(0, len(orphan_ids), 500):
        await client.set_payload(
            collection_name=collection_name,
            payload={"is_active": False},
            points=orphan_ids[i : i + 500],
        )
    logger.info(
        "unbacked_points_deactivated",
        collection=collection_name,
        repository_key=repository_key,
        deactivated=len(orphan_ids),
    )
    return len(orphan_ids)
