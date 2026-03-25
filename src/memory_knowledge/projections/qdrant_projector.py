from __future__ import annotations

from typing import Any

import openai
import structlog
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings

logger = structlog.get_logger()

BATCH_SIZE = 100


async def embed_chunks(
    chunks_text: list[str], settings: Settings
) -> list[list[float]]:
    """Batch embed chunk texts using OpenAI. Uses auth_mode branching."""
    if settings.auth_mode == "codex":
        from memory_knowledge.auth.codex import codex_token_provider

        api_key = await codex_token_provider(settings.codex_auth_path)
    else:
        api_key = settings.openai_api_key

    client = AsyncOpenAI(api_key=api_key)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(chunks_text), BATCH_SIZE):
        batch = chunks_text[i : i + BATCH_SIZE]
        try:
            response = await client.embeddings.create(
                model=settings.embedding_model,
                input=batch,
                dimensions=settings.embedding_dimensions,
            )
            all_embeddings.extend([d.embedding for d in response.data])
        except openai.AuthenticationError:
            if settings.auth_mode == "codex":
                raise RuntimeError(
                    "Codex OAuth token rejected — run 'codex auth' to re-authenticate"
                )
            raise

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
