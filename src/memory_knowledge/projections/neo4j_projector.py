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


async def project_additive_labels(
    driver: neo4j.AsyncDriver,
    file_symbols: list[dict[str, Any]],
) -> None:
    """Add DbTable/StoredProcedure labels to Symbol nodes based on symbol_kind."""
    db_table_keys: list[str] = []
    stored_proc_keys: list[str] = []

    for fs in file_symbols:
        for s in fs.get("symbols", []):
            if s["kind"] in ("table", "view"):
                db_table_keys.append(str(s["entity_key"]))
            elif s["kind"] in ("procedure", "function") and fs.get("language") == "sql":
                stored_proc_keys.append(str(s["entity_key"]))

    if db_table_keys:
        await driver.execute_query(
            """
            UNWIND $keys AS ek
            MATCH (s:Symbol {entity_key: ek})
            SET s:DbTable
            """,
            keys=db_table_keys,
        )
        logger.info("neo4j_dbtable_labels_set", count=len(db_table_keys))

    if stored_proc_keys:
        await driver.execute_query(
            """
            UNWIND $keys AS ek
            MATCH (s:Symbol {entity_key: ek})
            SET s:StoredProcedure
            """,
            keys=stored_proc_keys,
        )
        logger.info("neo4j_storedproc_labels_set", count=len(stored_proc_keys))


async def project_modules(
    driver: neo4j.AsyncDriver,
    repository_key: str,
    modules: list[dict[str, Any]],
) -> None:
    """MERGE Module nodes and CONTAINS_FILE edges."""
    if not modules:
        return
    await driver.execute_query(
        """
        UNWIND $modules AS m
        MERGE (mod:Module {entity_key: m.entity_key})
        SET mod.path = m.path, mod.name = m.name

        WITH mod, m
        UNWIND m.file_keys AS fk
        MATCH (f:File {entity_key: fk})
        MERGE (mod)-[:CONTAINS_FILE]->(f)
        """,
        modules=modules,
    )
    logger.info("neo4j_modules_projected", count=len(modules))


async def project_api_endpoints(
    driver: neo4j.AsyncDriver,
    endpoints: list[dict[str, Any]],
) -> None:
    """MERGE ApiEndpoint nodes and EXPOSES_ENDPOINT edges from files."""
    if not endpoints:
        return
    await driver.execute_query(
        """
        UNWIND $endpoints AS ep
        MERGE (e:ApiEndpoint {entity_key: ep.entity_key})
        SET e.method = ep.method, e.path = ep.path

        WITH e, ep
        MATCH (f:File {entity_key: ep.file_entity_key})
        MERGE (f)-[:EXPOSES_ENDPOINT]->(e)
        """,
        endpoints=endpoints,
    )
    logger.info("neo4j_endpoints_projected", count=len(endpoints))


async def project_sql_edges(
    driver: neo4j.AsyncDriver,
    sql_edges: list[dict[str, str]],
) -> None:
    """Create READS_TABLE / WRITES_TABLE edges from SQL object references."""
    reads = [e for e in sql_edges if e["rel_type"] == "READS_TABLE"]
    writes = [e for e in sql_edges if e["rel_type"] == "WRITES_TABLE"]

    if reads:
        await driver.execute_query(
            """
            UNWIND $edges AS e
            MATCH (src:File {entity_key: e.source_ek})
            MATCH (tbl:DbTable {entity_key: e.target_ek})
            MERGE (src)-[:READS_TABLE]->(tbl)
            """,
            edges=reads,
        )
    if writes:
        await driver.execute_query(
            """
            UNWIND $edges AS e
            MATCH (src:File {entity_key: e.source_ek})
            MATCH (tbl:DbTable {entity_key: e.target_ek})
            MERGE (src)-[:WRITES_TABLE]->(tbl)
            """,
            edges=writes,
        )
