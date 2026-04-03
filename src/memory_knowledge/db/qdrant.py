from __future__ import annotations

from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings

_client: AsyncQdrantClient | None = None

COLLECTIONS = [
    "code_chunks",
    "summary_units",
    "learned_memory",
    "routing_archetypes",
]


async def init_qdrant(settings: Settings) -> AsyncQdrantClient:
    global _client
    _client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    return _client


async def ensure_collections(
    client: AsyncQdrantClient, settings: Settings
) -> None:
    existing = await client.get_collections()
    existing_names = {c.name for c in existing.collections}

    for name in COLLECTIONS:
        if name not in existing_names:
            await client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=settings.embedding_dimensions,
                    distance=models.Distance.COSINE,
                ),
            )

    # Ensure payload indexes for filtered queries
    for name in COLLECTIONS:
        for field, schema in [
            ("repository_key", models.PayloadSchemaType.KEYWORD),
            ("is_active", models.PayloadSchemaType.KEYWORD),
            ("branch_name", models.PayloadSchemaType.KEYWORD),
            ("commit_sha", models.PayloadSchemaType.KEYWORD),
        ]:
            try:
                await client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema=schema,
                )
            except Exception:
                pass  # index may already exist


def get_qdrant_client() -> AsyncQdrantClient:
    if _client is None:
        raise RuntimeError("Qdrant client not initialized")
    return _client


async def close_qdrant() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
