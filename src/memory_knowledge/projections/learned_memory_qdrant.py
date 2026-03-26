from __future__ import annotations

import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.llm.openai_client import embed_single

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
    embedding = await embed_single(body_text, settings)

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
