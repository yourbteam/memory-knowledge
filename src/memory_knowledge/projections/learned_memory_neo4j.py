from __future__ import annotations

import neo4j
import structlog

logger = structlog.get_logger()


async def project_learned_rule(
    driver: neo4j.AsyncDriver,
    entity_key: str,
    memory_type: str,
    title: str,
    scope_entity_key: str,
    evidence_entity_key: str | None = None,
) -> None:
    """MERGE LearnedRule node + APPLIES_TO edge. MATCH (not MERGE) for evidence."""
    # MERGE the LearnedRule and APPLIES_TO edge
    await driver.execute_query(
        """
        MERGE (lr:LearnedRule {entity_key: $entity_key})
        SET lr.memory_type = $memory_type, lr.title = $title, lr.is_active = true

        WITH lr
        MATCH (scope {entity_key: $scope_entity_key})
        MERGE (lr)-[:APPLIES_TO]->(scope)
        """,
        entity_key=entity_key,
        memory_type=memory_type,
        title=title,
        scope_entity_key=scope_entity_key,
    )

    # Optionally link to evidence node if it exists in the graph
    if evidence_entity_key:
        await driver.execute_query(
            """
            MATCH (lr:LearnedRule {entity_key: $entity_key})
            MATCH (evidence {entity_key: $evidence_entity_key})
            MERGE (lr)-[:DERIVED_FROM]->(evidence)
            """,
            entity_key=entity_key,
            evidence_entity_key=evidence_entity_key,
        )

    logger.info("learned_rule_projected", entity_key=entity_key)


async def deactivate_learned_rule(
    driver: neo4j.AsyncDriver, entity_key: str
) -> None:
    """Set is_active=false on a LearnedRule node in Neo4j."""
    await driver.execute_query(
        "MATCH (lr:LearnedRule {entity_key: $ek}) SET lr.is_active = false",
        ek=entity_key,
    )
    logger.info("learned_rule_deactivated", entity_key=entity_key)


async def project_conflicts(
    driver: neo4j.AsyncDriver,
    entity_key: str,
    scope_entity_key: str,
    memory_type: str,
) -> None:
    """MERGE CONFLICTS_WITH edges for rules with same scope+type."""
    await driver.execute_query(
        """
        MATCH (new:LearnedRule {entity_key: $entity_key})
        MATCH (existing:LearnedRule)
        WHERE existing.entity_key <> $entity_key
          AND existing.is_active = true
          AND existing.memory_type = $memory_type
        MATCH (existing)-[:APPLIES_TO]->(scope {entity_key: $scope_entity_key})
        MERGE (new)-[:CONFLICTS_WITH]-(existing)
        """,
        entity_key=entity_key,
        memory_type=memory_type,
        scope_entity_key=scope_entity_key,
    )
    logger.info("conflicts_projected", entity_key=entity_key)
