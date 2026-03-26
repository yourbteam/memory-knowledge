from __future__ import annotations

from typing import Any

import openai
import structlog
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.projections.qdrant_projector import embed_chunks

logger = structlog.get_logger()

BATCH_SIZE = 100


async def embed_and_upsert_summaries(
    client: AsyncQdrantClient,
    summaries_list: list[dict[str, Any]],
    repository_key: str,
    commit_sha: str,
    settings: Settings,
) -> None:
    """Batch embed summary texts and upsert to summary_units collection."""
    if not summaries_list:
        return

    texts = [s["summary_text"] for s in summaries_list]
    embeddings = await embed_chunks(texts, settings)

    points = [
        models.PointStruct(
            id=s["entity_key"],
            vector=emb,
            payload={
                "entity_key": s["entity_key"],
                "repository_key": repository_key,
                "commit_sha": commit_sha,
                "summary_level": s["summary_level"],
                "is_active": True,
                "content_kind": "summary",
            },
        )
        for s, emb in zip(summaries_list, embeddings)
    ]

    for i in range(0, len(points), BATCH_SIZE):
        await client.upsert(
            collection_name="summary_units",
            points=points[i : i + BATCH_SIZE],
        )

    logger.info("summaries_embedded", count=len(points))


async def deactivate_old_summary_points(
    client: AsyncQdrantClient,
    repository_key: str,
    new_commit_sha: str,
) -> None:
    """Set is_active=False on old summary points for this repo."""
    await client.set_payload(
        collection_name="summary_units",
        payload={"is_active": False},
        points=models.Filter(
            must=[
                models.FieldCondition(
                    key="repository_key",
                    match=models.MatchValue(value=repository_key),
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
    logger.info("old_summary_points_deactivated", repository_key=repository_key)
