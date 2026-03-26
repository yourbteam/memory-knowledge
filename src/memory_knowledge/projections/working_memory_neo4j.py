from __future__ import annotations

from typing import Any

import neo4j
import structlog

logger = structlog.get_logger()

# Map observation types to Neo4j relationship types
_OBSERVATION_TYPE_TO_REL = {
    "inspected": "INSPECTED",
    "hypothesized_about": "HYPOTHESIZED_ABOUT",
    "proposed_change_to": "PROPOSED_CHANGE_TO",
    "issue_found": "FOUND_ISSUE_IN",
    "plan_note": "PLANNED_FOR",
    "rejected_path": "REJECTED_PATH_IN",
}


async def project_working_session(
    driver: neo4j.AsyncDriver,
    session_key: str,
    repository_key: str,
    observations: list[dict[str, Any]],
) -> None:
    """MERGE WorkingSession node and create observation edges to entities."""
    # MERGE the session node and link to repository
    await driver.execute_query(
        """
        MERGE (ws:WorkingSession {entity_key: $session_key})
        SET ws.repository_key = $repository_key

        WITH ws
        MATCH (repo:Repository {entity_key: $repository_key})
        MERGE (ws)-[:BELONGS_TO]->(repo)
        """,
        session_key=session_key,
        repository_key=repository_key,
    )

    # Create edges for each observation that has a valid entity_key
    for obs in observations:
        entity_key = obs.get("entity_key")
        if not entity_key:
            continue

        obs_type = obs.get("observation_type", "inspected")
        rel_type = _OBSERVATION_TYPE_TO_REL.get(obs_type, "INSPECTED")

        await driver.execute_query(
            f"""
            MATCH (ws:WorkingSession {{entity_key: $session_key}})
            MATCH (target {{entity_key: $entity_key}})
            MERGE (ws)-[:{rel_type}]->(target)
            """,
            session_key=session_key,
            entity_key=entity_key,
        )

    logger.info(
        "working_session_projected",
        session_key=session_key,
        observation_count=len(observations),
    )
