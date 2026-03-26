from __future__ import annotations

import neo4j

from memory_knowledge.config import Settings

_driver: neo4j.AsyncDriver | None = None

NODE_LABELS = [
    "Repository", "Revision", "File", "Symbol", "LearnedRule", "WorkingSession",
    "Module", "DbTable", "StoredProcedure", "ApiEndpoint",
]


async def init_neo4j(settings: Settings) -> neo4j.AsyncDriver:
    global _driver
    _driver = neo4j.AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        max_connection_pool_size=settings.neo4j_max_pool_size,
    )
    await _driver.verify_connectivity()
    return _driver


async def apply_constraints(driver: neo4j.AsyncDriver) -> None:
    for label in NODE_LABELS:
        query = (
            f"CREATE CONSTRAINT IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.entity_key IS UNIQUE"
        )
        await driver.execute_query(query)


def get_neo4j_driver() -> neo4j.AsyncDriver:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized")
    return _driver


async def close_neo4j() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
