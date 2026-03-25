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
