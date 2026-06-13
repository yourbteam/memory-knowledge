from __future__ import annotations

import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.llm.openai_client import embed_single
from memory_knowledge.projections.qdrant_payload_schemas import CorpusEntryPayload

logger = structlog.get_logger()

COLLECTION = "corpus_entries"


async def embed_and_upsert_corpus_entry(
    client: AsyncQdrantClient,
    *,
    entry_key: str,
    body_text: str,
    kind: str,
    link_slug: str | None,
    confidence: float | None,
    settings: Settings,
) -> None:
    """Embed body_text and upsert the point into the corpus_entries collection.

    The Qdrant point id is the entry_key (same UUID as the PG row), keeping PG and Qdrant
    key-symmetric. The query side must embed with this same model (see corpus_query).
    """
    embedding = await embed_single(body_text, settings)
    payload = {
        "entry_key": entry_key,
        "kind": kind,
        "link_slug": link_slug,
        "confidence": confidence,
        "is_active": True,
        "content_kind": "corpus_entry",
    }
    CorpusEntryPayload.model_validate(payload)

    await client.upsert(
        collection_name=COLLECTION,
        points=[models.PointStruct(id=entry_key, vector=embedding, payload=payload)],
    )
    logger.info("corpus_entry_embedded", entry_key=entry_key, kind=kind)


async def deactivate_corpus_point(client: AsyncQdrantClient, entry_key: str) -> None:
    """Set is_active=False on a corpus Qdrant point (point retained, not deleted)."""
    await client.set_payload(
        collection_name=COLLECTION,
        payload={"is_active": False},
        points=[entry_key],
    )
    logger.info("corpus_point_deactivated", entry_key=entry_key)
