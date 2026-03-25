from __future__ import annotations

import openai
import structlog
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings

logger = structlog.get_logger()


async def embed_and_upsert_learned_record(
    client: AsyncQdrantClient,
    entity_key: str,
    body_text: str,
    repository_key: str,
    memory_type: str,
    confidence: float,
    applicability_mode: str,
    scope_entity_key: str,
    settings: Settings,
) -> None:
    """Embed body_text and upsert to learned_memory collection."""
    # Embed
    if settings.auth_mode == "codex":
        from memory_knowledge.auth.codex import codex_token_provider

        api_key = await codex_token_provider(settings.codex_auth_path)
    else:
        api_key = settings.openai_api_key

    openai_client = AsyncOpenAI(api_key=api_key)
    try:
        response = await openai_client.embeddings.create(
            model=settings.embedding_model,
            input=body_text,
            dimensions=settings.embedding_dimensions,
        )
    except openai.AuthenticationError:
        if settings.auth_mode == "codex":
            raise RuntimeError(
                "Codex OAuth token rejected — run 'codex auth' to re-authenticate"
            )
        raise

    embedding = response.data[0].embedding

    # Upsert point
    await client.upsert(
        collection_name="learned_memory",
        points=[
            models.PointStruct(
                id=entity_key,
                vector=embedding,
                payload={
                    "entity_key": entity_key,
                    "repository_key": repository_key,
                    "memory_type": memory_type,
                    "confidence": confidence,
                    "applicability_mode": applicability_mode,
                    "scope_entity_key": scope_entity_key,
                    "is_active": True,
                    "content_kind": "learned_rule",
                },
            )
        ],
    )
    logger.info("learned_record_embedded", entity_key=entity_key)


async def deactivate_learned_record_point(
    client: AsyncQdrantClient, entity_key: str
) -> None:
    """Set is_active=False on a learned memory Qdrant point."""
    await client.set_payload(
        collection_name="learned_memory",
        payload={"is_active": False},
        points=[entity_key],
    )
    logger.info("learned_record_point_deactivated", entity_key=entity_key)
