from __future__ import annotations

from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.llm.openai_client import embed

logger = structlog.get_logger()

BATCH_SIZE = 100


async def embed_chunks(
    chunks_text: list[str], settings: Settings
) -> list[list[float]]:
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
    points = [
        models.PointStruct(
            id=c["entity_key"],  # UUID string — Qdrant accepts this natively
            vector=c["embedding"],
            payload={
                "entity_key": c["entity_key"],
                "repository_key": repository_key,
                "commit_sha": commit_sha,
                "branch_name": branch_name,
                "file_path": c["file_path"],
                "symbol_name": c.get("symbol_name"),
                "chunk_type": c["chunk_type"],
                "is_active": True,
                "retrieval_surface": f"live_branch:{branch_name}",
            },
        )
        for c in chunks_with_embeddings
    ]

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
