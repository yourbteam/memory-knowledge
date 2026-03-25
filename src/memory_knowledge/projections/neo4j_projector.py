from __future__ import annotations

from typing import Any

import neo4j
import structlog

logger = structlog.get_logger()


async def project_repository_graph(
    driver: neo4j.AsyncDriver,
    repository_key: str,
    commit_sha: str,
    branch_name: str,
    file_symbols: list[dict[str, Any]],
) -> None:
    """MERGE Repository→Revision→File→Symbol graph using UNWIND with WITH."""
    query = """
    MERGE (repo:Repository {entity_key: $repository_key})
    SET repo.name = $repository_key

    MERGE (rev:Revision {entity_key: $commit_sha})
    SET rev.commit_sha = $commit_sha, rev.branch_name = $branch_name

    MERGE (repo)-[:HAS_REVISION]->(rev)

    WITH rev
    UNWIND $files AS f
    MERGE (file:File {entity_key: f.entity_key})
    SET file.file_path = f.file_path
    MERGE (rev)-[:HAS_FILE]->(file)

    WITH file, f
    UNWIND f.symbols AS s
    MERGE (sym:Symbol {entity_key: s.entity_key})
    SET sym.symbol_name = s.name, sym.symbol_kind = s.kind
    MERGE (file)-[:CONTAINS]->(sym)
    """

    files_param = [
        {
            "entity_key": str(fs["file_entity_key"]),
            "file_path": fs["file_path"],
            "symbols": [
                {
                    "entity_key": str(s["entity_key"]),
                    "name": s["name"],
                    "kind": s["kind"],
                }
                for s in fs.get("symbols", [])
            ],
        }
        for fs in file_symbols
    ]

    await driver.execute_query(
        query,
        repository_key=repository_key,
        commit_sha=commit_sha,
        branch_name=branch_name,
        files=files_param,
    )
    logger.info(
        "neo4j_projection_complete",
        file_count=len(file_symbols),
    )


async def project_dependency_edges(
    driver: neo4j.AsyncDriver,
    file_imports: list[dict[str, str]],
    symbol_calls: list[dict[str, str]],
) -> None:
    """MERGE IMPORTS and CALLS edges between existing File/Symbol nodes."""
    if file_imports:
        await driver.execute_query(
            """
            UNWIND $edges AS e
            MATCH (f1:File {entity_key: e.importer_ek})
            MATCH (f2:File {entity_key: e.imported_ek})
            MERGE (f1)-[:IMPORTS]->(f2)
            """,
            edges=file_imports,
        )
        logger.info("neo4j_imports_projected", count=len(file_imports))

    if symbol_calls:
        await driver.execute_query(
            """
            UNWIND $edges AS e
            MATCH (s1:Symbol {entity_key: e.caller_ek})
            MATCH (s2:Symbol {entity_key: e.callee_ek})
            MERGE (s1)-[:CALLS]->(s2)
            """,
            edges=symbol_calls,
        )
        logger.info("neo4j_calls_projected", count=len(symbol_calls))
