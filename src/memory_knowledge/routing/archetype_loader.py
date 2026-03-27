from __future__ import annotations

import uuid

import asyncpg
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.llm.openai_client import embed

logger = structlog.get_logger()

# Representative query templates per prompt_class.
# These are embedded and stored in routing_archetypes for semantic matching.
ARCHETYPE_TEMPLATES: dict[str, list[str]] = {
    "exact_lookup": [
        "What is the function signature of getUserById",
        "Where is class UserService defined",
        "Show me the implementation of handleRequest",
        "Find the definition of parseConfig",
    ],
    "conceptual_lookup": [
        "How does authentication work in this codebase",
        "Explain the data flow for user registration",
        "What patterns are used for error handling",
        "How is caching implemented",
    ],
    "impact_analysis": [
        "What would break if I change the database schema",
        "What depends on the auth middleware",
        "Show the callers of processPayment",
        "What is affected by removing this function",
    ],
    "pattern_search": [
        "Find all usages of the singleton pattern",
        "Where is dependency injection used",
        "Show me examples of the repository pattern",
        "How is the observer pattern implemented here",
    ],
    "decision_history": [
        "Why was the auth system implemented this way",
        "What decisions led to the current architecture",
        "What learned rules apply to the API layer",
        "Why did we choose this approach for caching",
    ],
    "mixed": [
        "Summarize the auth module and its dependencies",
        "How does getUserById work and what calls it",
        "Explain the payment flow and what would break if we change it",
    ],
}


async def load_archetypes(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    settings: Settings,
) -> int:
    """Embed archetype templates and upsert to routing_archetypes collection.

    Returns the number of points upserted.
    """
    # Read route policies to get policy metadata
    policies = await pool.fetch("SELECT * FROM routing.route_policies")
    policy_by_class: dict[str, dict] = {
        p["prompt_class"]: dict(p) for p in policies
    }

    all_texts: list[str] = []
    all_metadata: list[dict] = []

    for prompt_class, templates in ARCHETYPE_TEMPLATES.items():
        policy = policy_by_class.get(prompt_class)
        for template in templates:
            all_texts.append(template)
            all_metadata.append({
                "prompt_class": prompt_class,
                "policy_id": policy["id"] if policy else None,
                "first_store": policy["first_store"] if policy else "postgres",
                "second_store": policy["second_store"] if policy else None,
                "allow_fanout": policy["allow_fanout"] if policy else False,
                "allow_graph_expansion": policy["allow_graph_expansion"] if policy else False,
                "template_text": template,
            })

    if not all_texts:
        return 0

    # Embed all templates
    embeddings = await embed(all_texts, settings)

    # Upsert as points
    points = []
    for emb, meta in zip(embeddings, all_metadata):
        # Deterministic point ID from prompt_class + template text (stable across reordering)
        point_id = str(uuid.uuid5(
            uuid.UUID("b7e15163-2a0e-4e29-8f3a-d4b612c8a1f7"),
            f"archetype:{meta['prompt_class']}:{meta['template_text']}",
        ))
        points.append(
            models.PointStruct(
                id=point_id,
                vector=emb,
                payload=meta,
            )
        )

    await qdrant_client.upsert(
        collection_name="routing_archetypes",
        points=points,
    )

    logger.info("archetypes_loaded", count=len(points))
    return len(points)
