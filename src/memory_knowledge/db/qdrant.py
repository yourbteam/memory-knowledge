from __future__ import annotations

from typing import Any

from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings

_client: AsyncQdrantClient | None = None

COLLECTIONS = [
    "code_chunks",
    "summary_units",
    "learned_memory",
    "routing_archetypes",
    "triage_cases",
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
            ("project_key", models.PayloadSchemaType.KEYWORD),
            ("feature_key", models.PayloadSchemaType.KEYWORD),
            ("request_kind", models.PayloadSchemaType.KEYWORD),
            ("selected_workflow_name", models.PayloadSchemaType.KEYWORD),
            ("policy_version", models.PayloadSchemaType.KEYWORD),
            ("is_active", models.PayloadSchemaType.BOOL),
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


async def semantic_query_points(
    client: AsyncQdrantClient,
    *,
    collection_name: str,
    query_vector: list[float],
    limit: int,
    score_threshold: float | None = None,
    query_filter: models.Filter | None = None,
    with_payload: bool = True,
) -> list[Any]:
    """Bridge Qdrant async client query API differences across versions."""
    query_points = getattr(client, "query_points", None)
    if callable(query_points):
        result = await query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=with_payload,
        )
        return list(result.points)

    return list(
        await client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=with_payload,
        )
    )


def get_qdrant_client() -> AsyncQdrantClient:
    if _client is None:
        raise RuntimeError("Qdrant client not initialized")
    return _client


async def close_qdrant() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
