from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()

# Tables to export in FK-safe order (parents before children)
_EXPORT_TABLES = [
    ("catalog.repositories", "SELECT * FROM catalog.repositories WHERE repository_key = $1"),
    ("catalog.repo_revisions", """
        SELECT rr.* FROM catalog.repo_revisions rr
        JOIN catalog.repositories r ON rr.repository_id = r.id
        WHERE r.repository_key = $1
    """),
    ("catalog.entities", """
        SELECT e.* FROM catalog.entities e
        JOIN catalog.repositories r ON e.repository_id = r.id
        WHERE r.repository_key = $1
    """),
    ("catalog.files", """
        SELECT f.*, e.entity_key AS _entity_key
        FROM catalog.files f
        JOIN catalog.entities e ON f.entity_id = e.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """),
    ("catalog.symbols", """
        SELECT s.*, e.entity_key AS _entity_key,
               e_file.entity_key AS _file_entity_key
        FROM catalog.symbols s
        JOIN catalog.entities e ON s.entity_id = e.id
        JOIN catalog.files f ON s.file_id = f.id
        JOIN catalog.entities e_file ON f.entity_id = e_file.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """),
    ("catalog.chunks", """
        SELECT c.*, e.entity_key AS _entity_key
        FROM catalog.chunks c
        JOIN catalog.entities e ON c.entity_id = e.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """),
    ("catalog.summaries", """
        SELECT s.*, e.entity_key AS _entity_key
        FROM catalog.summaries s
        JOIN catalog.entities e ON s.entity_id = e.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """),
    ("catalog.file_imports_file", """
        SELECT e1.entity_key AS importer_entity_key, e2.entity_key AS imported_entity_key
        FROM catalog.file_imports_file fif
        JOIN catalog.files f1 ON fif.importer_file_id = f1.id
        JOIN catalog.entities e1 ON f1.entity_id = e1.id
        JOIN catalog.files f2 ON fif.imported_file_id = f2.id
        JOIN catalog.entities e2 ON f2.entity_id = e2.id
        WHERE e1.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """),
    ("catalog.symbol_calls_symbol", """
        SELECT e1.entity_key AS caller_entity_key, e2.entity_key AS callee_entity_key
        FROM catalog.symbol_calls_symbol scs
        JOIN catalog.symbols s1 ON scs.caller_symbol_id = s1.id
        JOIN catalog.entities e1 ON s1.entity_id = e1.id
        JOIN catalog.symbols s2 ON scs.callee_symbol_id = s2.id
        JOIN catalog.entities e2 ON s2.entity_id = e2.id
        WHERE e1.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """),
    ("memory.learned_records", """
        SELECT lr.*, e.entity_key AS _entity_key,
               scope_e.entity_key AS _scope_entity_key,
               ev_e.entity_key AS _evidence_entity_key,
               sup_e.entity_key AS _supersedes_entity_key
        FROM memory.learned_records lr
        JOIN catalog.entities e ON lr.entity_id = e.id
        JOIN catalog.entities scope_e ON lr.scope_entity_id = scope_e.id
        LEFT JOIN catalog.entities ev_e ON lr.evidence_entity_id = ev_e.id
        LEFT JOIN (
            memory.learned_records lr2
            JOIN catalog.entities sup_e ON lr2.entity_id = sup_e.id
        ) ON lr.supersedes_learned_record_id = lr2.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """),
]


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert asyncpg Record values to JSON-serializable types."""
    result: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            result[key] = str(value)
        elif hasattr(value, "isoformat"):
            result[key] = value.isoformat()
        elif isinstance(value, (bytes, bytearray)):
            result[key] = value.hex()
        else:
            result[key] = value
    return result


async def export_repo_memory(
    pool: asyncpg.Pool, repository_key: str
) -> list[str]:
    """Export repository memory as JSONL lines. Returns list of JSON strings."""
    lines: list[str] = []

    for table_name, query in _EXPORT_TABLES:
        rows = await pool.fetch(query, repository_key)
        for row in rows:
            line = json.dumps({
                "table": table_name,
                "data": _serialize_row(dict(row)),
            }, default=str)
            lines.append(line)

    logger.info("export_complete", repository_key=repository_key, lines=len(lines))
    return lines


async def import_repo_memory(
    pool: asyncpg.Pool, lines: list[str]
) -> dict[str, Any]:
    """Import repository memory from JSONL lines.

    Currently imports repository metadata. Full entity/chunk/edge import
    requires re-ingestion after repository registration.
    """
    rows_by_table: dict[str, list[dict]] = {}
    for line in lines:
        record = json.loads(line)
        table = record["table"]
        rows_by_table.setdefault(table, []).append(record["data"])

    imported: dict[str, int] = {}
    skipped_tables: list[str] = []

    # Import repositories
    for row in rows_by_table.get("catalog.repositories", []):
        await pool.execute(
            """
            INSERT INTO catalog.repositories (repository_key, name, origin_url)
            VALUES ($1, $2, $3)
            ON CONFLICT (repository_key) DO UPDATE
                SET name = EXCLUDED.name, origin_url = EXCLUDED.origin_url
            """,
            row["repository_key"],
            row["name"],
            row.get("origin_url"),
        )
        imported["catalog.repositories"] = imported.get("catalog.repositories", 0) + 1

    # Track tables present in export but not imported
    for table in rows_by_table:
        if table != "catalog.repositories" and rows_by_table[table]:
            skipped_tables.append(table)

    logger.info(
        "import_complete",
        tables=list(imported.keys()),
        total_rows=sum(imported.values()),
        skipped_tables=skipped_tables,
    )
    return {
        "tables_imported": list(imported.keys()),
        "rows_imported": sum(imported.values()),
        "detail": imported,
        "skipped_tables": skipped_tables,
        "note": "Entity/chunk data requires re-ingestion after repository import" if skipped_tables else None,
    }
