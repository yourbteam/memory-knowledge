from __future__ import annotations

import json
import base64
import binascii
import hashlib
import hmac
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog

from memory_knowledge.workflows.learned_memory import (
    normalize_import_owned_record,
    resolve_evidence_refs,
)

logger = structlog.get_logger()


def order_learned_insert_items(
    items: list[dict[str, Any]], available_entity_keys: set[str]
) -> list[dict[str, Any]]:
    """Topologically order absent learned records by stable supersession identity."""
    remaining = {item["row"]["_entity_key"]: item for item in items}
    available = set(available_entity_keys)
    ordered: list[dict[str, Any]] = []
    while remaining:
        ready = [
            key for key, item in remaining.items()
            if not item["row"].get("_supersedes_entity_key")
            or item["row"]["_supersedes_entity_key"] in available
        ]
        if not ready:
            raise ValueError("import-learned-record-missing-or-cyclic-supersedes")
        for key in sorted(ready):
            ordered.append(remaining.pop(key))
            available.add(key)
    return ordered

# Tables to export in FK-safe order (parents before children)
_EXPORT_TABLES = [
    ("catalog.repositories", "SELECT * FROM catalog.repositories WHERE repository_key = $1"),
    (
        "catalog.repo_revisions",
        """
        SELECT rr.*, r.repository_key AS _repository_key
        FROM catalog.repo_revisions rr
        JOIN catalog.repositories r ON rr.repository_id = r.id
        WHERE r.repository_key = $1
    """,
    ),
    (
        "catalog.branch_heads",
        """
        SELECT bh.*, r.repository_key AS _repository_key,
               rr.commit_sha AS _revision_commit_sha
        FROM catalog.branch_heads bh
        JOIN catalog.repositories r ON bh.repository_id = r.id
        JOIN catalog.repo_revisions rr ON bh.repo_revision_id = rr.id
        WHERE r.repository_key = $1
    """,
    ),
    (
        "catalog.retrieval_surfaces",
        """
        SELECT rs.*, r.repository_key AS _repository_key,
               rr.commit_sha AS _revision_commit_sha
        FROM catalog.retrieval_surfaces rs
        JOIN catalog.repositories r ON rs.repository_id = r.id
        JOIN catalog.repo_revisions rr ON rs.repo_revision_id = rr.id
        WHERE r.repository_key = $1
    """,
    ),
    (
        "catalog.entities",
        """
        SELECT e.*, r.repository_key AS _repository_key,
               rr.commit_sha AS _revision_commit_sha
        FROM catalog.entities e
        JOIN catalog.repositories r ON e.repository_id = r.id
        LEFT JOIN catalog.repo_revisions rr ON e.repo_revision_id = rr.id
        WHERE r.repository_key = $1
    """,
    ),
    (
        "catalog.files",
        """
        SELECT f.*, e.entity_key AS _entity_key,
               rr.commit_sha AS _revision_commit_sha
        FROM catalog.files f
        JOIN catalog.entities e ON f.entity_id = e.id
        JOIN catalog.repo_revisions rr ON f.repo_revision_id = rr.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """,
    ),
    (
        "catalog.symbols",
        """
        SELECT s.*, e.entity_key AS _entity_key,
               e_file.entity_key AS _file_entity_key
        FROM catalog.symbols s
        JOIN catalog.entities e ON s.entity_id = e.id
        JOIN catalog.files f ON s.file_id = f.id
        JOIN catalog.entities e_file ON f.entity_id = e_file.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """,
    ),
    (
        "catalog.chunks",
        """
        SELECT c.*, e.entity_key AS _entity_key,
               e_file.entity_key AS _file_entity_key
        FROM catalog.chunks c
        JOIN catalog.entities e ON c.entity_id = e.id
        JOIN catalog.files f ON c.file_id = f.id
        JOIN catalog.entities e_file ON f.entity_id = e_file.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """,
    ),
    (
        "catalog.summaries",
        """
        SELECT s.*, e.entity_key AS _entity_key
        FROM catalog.summaries s
        JOIN catalog.entities e ON s.entity_id = e.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """,
    ),
    (
        "catalog.file_imports_file",
        """
        SELECT e1.entity_key AS importer_entity_key, e2.entity_key AS imported_entity_key
        FROM catalog.file_imports_file fif
        JOIN catalog.files f1 ON fif.importer_file_id = f1.id
        JOIN catalog.entities e1 ON f1.entity_id = e1.id
        JOIN catalog.files f2 ON fif.imported_file_id = f2.id
        JOIN catalog.entities e2 ON f2.entity_id = e2.id
        WHERE e1.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """,
    ),
    (
        "catalog.symbol_calls_symbol",
        """
        SELECT e1.entity_key AS caller_entity_key, e2.entity_key AS callee_entity_key
        FROM catalog.symbol_calls_symbol scs
        JOIN catalog.symbols s1 ON scs.caller_symbol_id = s1.id
        JOIN catalog.entities e1 ON s1.entity_id = e1.id
        JOIN catalog.symbols s2 ON scs.callee_symbol_id = s2.id
        JOIN catalog.entities e2 ON s2.entity_id = e2.id
        WHERE e1.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """,
    ),
    (
        "memory.learned_records",
        """
        SELECT lr.*, e.entity_key AS _entity_key,
               scope_e.entity_key AS _scope_entity_key,
               ev_e.entity_key AS _evidence_entity_key,
               ev_ce.entity_key AS _evidence_chunk_entity_key,
               sup_e.entity_key AS _supersedes_entity_key,
               vf_rr.commit_sha AS _valid_from_commit_sha,
               vt_rr.commit_sha AS _valid_to_commit_sha
        FROM memory.learned_records lr
        JOIN catalog.entities e ON lr.entity_id = e.id
        JOIN catalog.entities scope_e ON lr.scope_entity_id = scope_e.id
        LEFT JOIN catalog.entities ev_e ON lr.evidence_entity_id = ev_e.id
        LEFT JOIN catalog.chunks ev_c ON lr.evidence_chunk_id = ev_c.id
        LEFT JOIN catalog.entities ev_ce ON ev_c.entity_id = ev_ce.id
        LEFT JOIN (
            memory.learned_records lr2
            JOIN catalog.entities sup_e ON lr2.entity_id = sup_e.id
        ) ON lr.supersedes_learned_record_id = lr2.id
        LEFT JOIN catalog.repo_revisions vf_rr ON lr.valid_from_revision_id = vf_rr.id
        LEFT JOIN catalog.repo_revisions vt_rr ON lr.valid_to_revision_id = vt_rr.id
        WHERE e.repository_id = (SELECT id FROM catalog.repositories WHERE repository_key = $1)
    """,
    ),
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


async def export_repo_memory(pool: asyncpg.Pool, repository_key: str) -> list[str]:
    """Export repository memory as JSONL lines. Returns list of JSON strings."""
    lines: list[str] = []

    for table_name, query in _EXPORT_TABLES:
        rows = await pool.fetch(query, repository_key)
        for row in rows:
            line = json.dumps(
                {
                    "table": table_name,
                    "data": _serialize_row(dict(row)),
                },
                default=str,
            )
            lines.append(line)

    logger.info("export_complete", repository_key=repository_key, lines=len(lines))
    return lines


async def import_repo_memory(pool: asyncpg.Pool, lines: list[str]) -> dict[str, Any]:
    """Import repository memory from JSONL lines with full FK remapping.

    Uses batched writes (executemany) for speed — ~100x faster than individual
    INSERT queries against remote databases.
    """
    rows_by_table: dict[str, list[dict]] = {}
    for line in lines:
        record = json.loads(line)
        table = record["table"]
        rows_by_table.setdefault(table, []).append(record["data"])

    imported: dict[str, int] = {}
    BATCH = 500

    def _log(table: str, done: int, total: int) -> None:
        imported[table] = done
        logger.info("import_progress", table=table, done=done, total=total)

    # Maps for FK remapping
    repo_key_to_id: dict[str, int] = {}
    rev_key_to_id: dict[tuple[str, str], int] = {}
    ek_to_entity_id: dict[str, int] = {}
    ek_to_file_id: dict[str, int] = {}
    ek_to_symbol_id: dict[str, int] = {}
    ek_to_chunk_id: dict[str, int] = {}
    ek_to_lr_id: dict[str, int] = {}

    # Helper: batch INSERT using UNNEST arrays with RETURNING
    async def _batch_unnest(
        sql: str,
        args_list: list[tuple],
        table: str,
        cast_types: list[str],
    ) -> list[asyncpg.Record]:
        """Batch INSERT using UNNEST arrays. Each batch sends N rows in 1 query.

        sql: INSERT ... SELECT * FROM UNNEST($1::type[], $2::type[], ...) ON CONFLICT ... RETURNING ...
        args_list: list of tuples, one per row
        cast_types: PostgreSQL array type casts matching the UNNEST columns
        """
        results: list[asyncpg.Record] = []
        for i in range(0, len(args_list), BATCH):
            batch = args_list[i : i + BATCH]
            # Transpose rows into column arrays
            columns = list(zip(*batch))
            arrays = [list(col) for col in columns]
            batch_results = await pool.fetch(sql, *arrays)
            results.extend(batch_results)
            _log(table, len(results), len(args_list))
        return results

    # Helper: batch executemany (no RETURNING needed)
    async def _batch_execute(sql: str, args_list: list[tuple], table: str) -> None:
        for i in range(0, len(args_list), BATCH):
            batch = args_list[i : i + BATCH]
            await pool.executemany(sql, batch)
            _log(table, min(i + BATCH, len(args_list)), len(args_list))

    # 1. Repositories (tiny, keep individual). Post-016 the catalog requires
    # mawf_repository_id + status_id (NOT NULL, no default) — these are checked
    # before ON CONFLICT can fire, so a bare 3-column upsert always errors. A new
    # repo must therefore be pre-registered via the MAWF contract
    # (mawf_upsert_repository); resolve its existing id here, and only fall back to
    # a full insert (carrying the export's mawf fields) when it is genuinely absent.
    for row in rows_by_table.get("catalog.repositories", []):
        existing = await pool.fetchrow(
            "SELECT id FROM catalog.repositories WHERE repository_key = $1",
            row["repository_key"],
        )
        if existing is not None:
            await pool.execute(
                "UPDATE catalog.repositories SET name = $2, origin_url = $3, updated_utc = NOW() WHERE id = $1",
                existing["id"],
                row["name"],
                row.get("origin_url"),
            )
            repo_key_to_id[row["repository_key"]] = existing["id"]
        else:
            r = await pool.fetchrow(
                """INSERT INTO catalog.repositories
                       (repository_key, name, origin_url, mawf_repository_id, status_id,
                        provider, owner, repo_name)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   RETURNING id""",
                row["repository_key"],
                row["name"],
                row.get("origin_url"),
                row.get("mawf_repository_id"),
                row.get("status_id"),
                row.get("provider"),
                row.get("owner"),
                row.get("repo_name"),
            )
            repo_key_to_id[row["repository_key"]] = r["id"]
    _log("catalog.repositories", len(repo_key_to_id), len(rows_by_table.get("catalog.repositories", [])))

    # 2. Repo revisions (tiny, keep individual)
    for row in rows_by_table.get("catalog.repo_revisions", []):
        rk = row.get("_repository_key", "")
        repo_id = repo_key_to_id.get(rk)
        if not repo_id:
            continue
        r = await pool.fetchrow(
            """INSERT INTO catalog.repo_revisions (repository_id, commit_sha, branch_name, parent_sha)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (repository_id, commit_sha) DO UPDATE SET branch_name = EXCLUDED.branch_name
            RETURNING id""",
            repo_id,
            row["commit_sha"],
            row.get("branch_name"),
            row.get("parent_sha"),
        )
        rev_key_to_id[(rk, row["commit_sha"])] = r["id"]
    _log("catalog.repo_revisions", len(rev_key_to_id), len(rows_by_table.get("catalog.repo_revisions", [])))

    # 3. Entities — UNNEST batched (largest table)
    entity_args = []
    for row in rows_by_table.get("catalog.entities", []):
        rk = row.get("_repository_key", "")
        repo_id = repo_key_to_id.get(rk)
        if not repo_id:
            continue
        commit_sha = row.get("_revision_commit_sha")
        rev_id = rev_key_to_id.get((rk, commit_sha)) if commit_sha else None
        if commit_sha and not rev_id:
            continue
        entity_args.append(
            (uuid.UUID(row["entity_key"]), row["entity_type"], repo_id, rev_id, row.get("external_hash"))
        )

    results = await _batch_unnest(
        """INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id, external_hash)
        SELECT * FROM UNNEST($1::uuid[], $2::text[], $3::bigint[], $4::bigint[], $5::text[])
        ON CONFLICT (entity_key) DO UPDATE SET repo_revision_id = EXCLUDED.repo_revision_id, external_hash = EXCLUDED.external_hash
        RETURNING id, entity_key""",
        entity_args,
        "catalog.entities",
        [],
    )
    for r in results:
        ek_to_entity_id[str(r["entity_key"])] = r["id"]

    # 4. Files — UNNEST batched
    file_args = []
    file_ek_order = []
    for row in rows_by_table.get("catalog.files", []):
        ek = row.get("_entity_key")
        entity_id = ek_to_entity_id.get(ek)
        if not entity_id:
            continue
        commit_sha = row.get("_revision_commit_sha")
        rev_id = None
        for rk in repo_key_to_id:
            rev_id = rev_key_to_id.get((rk, commit_sha))
            if rev_id:
                break
        if not rev_id:
            continue
        file_args.append(
            (entity_id, rev_id, row["file_path"], row.get("language"), row.get("size_bytes"), row.get("checksum"))
        )
        file_ek_order.append(ek)

    results = await _batch_unnest(
        """INSERT INTO catalog.files (entity_id, repo_revision_id, file_path, language, size_bytes, checksum)
        SELECT * FROM UNNEST($1::bigint[], $2::bigint[], $3::text[], $4::text[], $5::bigint[], $6::text[])
        ON CONFLICT ON CONSTRAINT uq_files_revision_path DO UPDATE
            SET entity_id = EXCLUDED.entity_id, language = EXCLUDED.language, size_bytes = EXCLUDED.size_bytes, checksum = EXCLUDED.checksum
        RETURNING id, entity_id""",
        file_args,
        "catalog.files",
        [],
    )
    eid_to_ek = {ek_to_entity_id[ek]: ek for ek in file_ek_order if ek in ek_to_entity_id}
    for r in results:
        file_ek = eid_to_ek.get(r["entity_id"])
        if file_ek:
            ek_to_file_id[file_ek] = r["id"]

    # 5. Symbols — UNNEST batched
    sym_args = []
    sym_ek_order = []
    for row in rows_by_table.get("catalog.symbols", []):
        ek = row.get("_entity_key")
        entity_id = ek_to_entity_id.get(ek)
        file_ek = row.get("_file_entity_key")
        file_id = ek_to_file_id.get(file_ek)
        if not entity_id or not file_id:
            continue
        sym_args.append(
            (
                entity_id,
                file_id,
                row["symbol_name"],
                row["symbol_kind"],
                row.get("line_start"),
                row.get("line_end"),
                row.get("signature"),
            )
        )
        sym_ek_order.append(ek)

    results = await _batch_unnest(
        """INSERT INTO catalog.symbols (entity_id, file_id, symbol_name, symbol_kind, line_start, line_end, signature)
        SELECT * FROM UNNEST($1::bigint[], $2::bigint[], $3::text[], $4::text[], $5::int[], $6::int[], $7::text[])
        ON CONFLICT (entity_id) DO UPDATE SET file_id = EXCLUDED.file_id, symbol_name = EXCLUDED.symbol_name, symbol_kind = EXCLUDED.symbol_kind
        RETURNING id, entity_id""",
        sym_args,
        "catalog.symbols",
        [],
    )
    sym_eid_to_ek = {ek_to_entity_id[ek]: ek for ek in sym_ek_order if ek in ek_to_entity_id}
    for r in results:
        sym_ek = sym_eid_to_ek.get(r["entity_id"])
        if sym_ek:
            ek_to_symbol_id[sym_ek] = r["id"]

    # 6. Chunks — UNNEST batched (largest data table)
    chunk_args = []
    chunk_ek_order = []
    for row in rows_by_table.get("catalog.chunks", []):
        ek = row.get("_entity_key")
        entity_id = ek_to_entity_id.get(ek)
        file_ek = row.get("_file_entity_key")
        file_id = ek_to_file_id.get(file_ek)
        if not entity_id or not file_id:
            continue
        chunk_args.append(
            (
                entity_id,
                file_id,
                row.get("title"),
                row.get("content_text"),
                row.get("chunk_type"),
                row.get("line_start"),
                row.get("line_end"),
                row.get("checksum"),
            )
        )
        chunk_ek_order.append(ek)

    results = await _batch_unnest(
        """INSERT INTO catalog.chunks (entity_id, file_id, title, content_text, content_tsv, chunk_type, line_start, line_end, checksum)
        SELECT e, f, t, c, to_tsvector('english', c), ct, ls, le, cs
        FROM UNNEST($1::bigint[], $2::bigint[], $3::text[], $4::text[], $5::text[], $6::int[], $7::int[], $8::text[])
            AS t(e, f, t, c, ct, ls, le, cs)
        ON CONFLICT (entity_id) DO UPDATE SET content_text = EXCLUDED.content_text, content_tsv = to_tsvector('english', EXCLUDED.content_text)
        RETURNING id, entity_id""",
        chunk_args,
        "catalog.chunks",
        [],
    )
    chunk_eid_to_ek = {ek_to_entity_id[ek]: ek for ek in chunk_ek_order if ek in ek_to_entity_id}
    for r in results:
        chunk_ek = chunk_eid_to_ek.get(r["entity_id"])
        if chunk_ek:
            ek_to_chunk_id[chunk_ek] = r["id"]

    # 7. Summaries — BATCHED with executemany
    summary_args = []
    for row in rows_by_table.get("catalog.summaries", []):
        ek = row.get("_entity_key")
        entity_id = ek_to_entity_id.get(ek)
        if entity_id:
            summary_args.append((entity_id, row["summary_level"], row.get("summary_text")))
    if summary_args:
        await _batch_execute(
            """INSERT INTO catalog.summaries (entity_id, summary_level, summary_text, summary_tsv)
            VALUES ($1, $2, $3, to_tsvector('english', COALESCE($3, '')))
            ON CONFLICT (entity_id, summary_level) DO UPDATE
                SET summary_text = EXCLUDED.summary_text, summary_tsv = to_tsvector('english', COALESCE(EXCLUDED.summary_text, ''))""",
            summary_args,
            "catalog.summaries",
        )

    # 8. Branch heads — executemany
    bh_args = []
    for row in rows_by_table.get("catalog.branch_heads", []):
        rk = row.get("_repository_key", "")
        repo_id = repo_key_to_id.get(rk)
        commit_sha = row.get("_revision_commit_sha")
        rev_id = rev_key_to_id.get((rk, commit_sha)) if commit_sha else None
        if repo_id and rev_id:
            bh_args.append((repo_id, row["branch_name"], rev_id))
    if bh_args:
        await _batch_execute(
            """INSERT INTO catalog.branch_heads (repository_id, branch_name, repo_revision_id)
            VALUES ($1, $2, $3) ON CONFLICT (repository_id, branch_name) DO UPDATE SET repo_revision_id = EXCLUDED.repo_revision_id""",
            bh_args,
            "catalog.branch_heads",
        )

    # 9. Retrieval surfaces — executemany
    rs_args = []
    for row in rows_by_table.get("catalog.retrieval_surfaces", []):
        rk = row.get("_repository_key", "")
        repo_id = repo_key_to_id.get(rk)
        commit_sha = row.get("_revision_commit_sha")
        rev_id = rev_key_to_id.get((rk, commit_sha)) if commit_sha else None
        if repo_id and rev_id:
            rs_args.append(
                (
                    repo_id,
                    row.get("surface_type", "live_branch"),
                    row.get("branch_name"),
                    row.get("commit_sha"),
                    rev_id,
                    row.get("is_default", False),
                )
            )
    if rs_args:
        await _batch_execute(
            """INSERT INTO catalog.retrieval_surfaces (repository_id, surface_type, branch_name, commit_sha, repo_revision_id, is_default)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (repository_id, surface_type, branch_name) DO UPDATE
                SET commit_sha = EXCLUDED.commit_sha, repo_revision_id = EXCLUDED.repo_revision_id""",
            rs_args,
            "catalog.retrieval_surfaces",
        )

    # 10. File imports — executemany
    fi_args = []
    for row in rows_by_table.get("catalog.file_imports_file", []):
        imp_fid = ek_to_file_id.get(row.get("importer_entity_key"))
        imported_fid = ek_to_file_id.get(row.get("imported_entity_key"))
        if imp_fid and imported_fid:
            fi_args.append((imp_fid, imported_fid))
    if fi_args:
        await _batch_execute(
            """INSERT INTO catalog.file_imports_file (importer_file_id, imported_file_id)
            VALUES ($1, $2) ON CONFLICT ON CONSTRAINT uq_file_imports DO NOTHING""",
            fi_args,
            "catalog.file_imports_file",
        )

    # 11. Symbol calls — executemany
    sc_args = []
    for row in rows_by_table.get("catalog.symbol_calls_symbol", []):
        caller_sid = ek_to_symbol_id.get(row.get("caller_entity_key"))
        callee_sid = ek_to_symbol_id.get(row.get("callee_entity_key"))
        if caller_sid and callee_sid:
            sc_args.append((caller_sid, callee_sid))
    if sc_args:
        await _batch_execute(
            """INSERT INTO catalog.symbol_calls_symbol (caller_symbol_id, callee_symbol_id)
            VALUES ($1, $2) ON CONFLICT ON CONSTRAINT uq_symbol_calls DO NOTHING""",
            sc_args,
            "catalog.symbol_calls_symbol",
        )

    # 12. Learned records: collision-safe, destination-resolved, one transaction.
    lr_rows = rows_by_table.get("memory.learned_records", [])
    non_superseding = [r for r in lr_rows if not r.get("_supersedes_entity_key")]
    superseding = [r for r in lr_rows if r.get("_supersedes_entity_key")]
    destination_key = next(iter(repo_key_to_id), None)
    destination_repo_id = repo_key_to_id.get(destination_key) if destination_key else None
    prepared: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for row in sorted(lr_rows, key=lambda item: str(item.get("_entity_key", ""))):
        ek = row.get("_entity_key")
        entity_id = ek_to_entity_id.get(ek)
        scope_id = ek_to_entity_id.get(row.get("_scope_entity_key"))
        if not destination_key or not destination_repo_id or not entity_id or not scope_id:
            continue
        source_errors = row.get("evidence_resolution_errors")
        if source_errors is not None and (
            not isinstance(source_errors, list)
            or any(not isinstance(item, dict) or set(item) - {
                "reason_code", "ref_index", "kind", "repository_key", "entity_key",
                "file_path", "revision_commit",
            } for item in source_errors)
        ):
            raise ValueError("invalid-source-evidence-diagnostics")
        source_refs = row.get("evidence_refs")
        canonical_refs: list[dict[str, Any]] | None = None
        destination_errors: list[dict[str, Any]] = []
        if source_refs is not None:
            if not isinstance(source_refs, list):
                raise ValueError("invalid-evidence-refs")
            canonical_refs = []
            for ref_index, source_ref in enumerate(source_refs):
                safe_ref = dict(source_ref) if isinstance(source_ref, dict) else {}
                safe_ref["repository_key"] = destination_key
                try:
                    _, resolved = await resolve_evidence_refs(pool, destination_key, [safe_ref])
                    canonical_refs.extend(resolved)
                except ValueError as exc:
                    reason = str(exc).split(":", 1)[0]
                    detail = {"reason_code": reason, "ref_index": ref_index}
                    for field in ("kind", "repository_key", "entity_key", "file_path", "revision_commit"):
                        if field in safe_ref:
                            detail[field] = safe_ref[field]
                    destination_errors.append(detail)
                    canonical_refs.append(safe_ref)
            canonical_refs.sort(key=lambda item: (
                item.get("kind", ""), item.get("repository_key", ""),
                item.get("entity_key") or item.get("file_path") or "",
                item.get("revision_commit") or "",
            ))
        imported = dict(row)
        imported["evidence_refs"] = canonical_refs
        imported["evidence_resolution_errors"] = destination_errors
        if destination_errors:
            imported["verification_status"] = "legacy-unclassified"
            imported["is_active"] = False
            unresolved.append({"entity_key": ek, "reason_codes": destination_errors})
        vf_sha, vt_sha = row.get("_valid_from_commit_sha"), row.get("_valid_to_commit_sha")
        prepared.append({
            "stable": normalize_import_owned_record(imported), "row": imported,
            "entity_id": entity_id, "scope_id": scope_id,
            "ev_id": ek_to_entity_id.get(row.get("_evidence_entity_key")) if row.get("_evidence_entity_key") else None,
            "ev_chunk_id": ek_to_chunk_id.get(row.get("_evidence_chunk_entity_key")) if row.get("_evidence_chunk_entity_key") else None,
            "vf_rev_id": rev_key_to_id.get((destination_key, vf_sha)) if vf_sha else None,
            "vt_rev_id": rev_key_to_id.get((destination_key, vt_sha)) if vt_sha else None,
        })

    import_id = uuid.uuid4()
    cursor_secret = os.urandom(32)
    created = datetime.now(UTC).replace(microsecond=0)
    expires = created + timedelta(days=7)
    async with pool.acquire() as conn:
        async with conn.transaction():
            if destination_repo_id:
                expired = await conn.fetch(
                    "SELECT import_id FROM memory.learned_import_reports WHERE repository_id=$1 "
                    "AND expired_utc IS NULL AND expires_utc<=$2 FOR UPDATE",
                    destination_repo_id, created,
                )
                for report in expired:
                    await conn.execute(
                        "DELETE FROM memory.learned_import_unresolved WHERE import_id=$1",
                        report["import_id"],
                    )
                    await conn.execute(
                        "UPDATE memory.learned_import_reports SET cursor_secret=NULL,expired_utc=$2 "
                        "WHERE import_id=$1", report["import_id"], created,
                    )
            absent: list[dict[str, Any]] = []
            for item in prepared:
                row = item["row"]
                existing = await conn.fetchrow(
                    """
                    SELECT lr.*,e.entity_key AS _entity_key,se.entity_key AS _scope_entity_key,
                           ee.entity_key AS _evidence_entity_key,ce.entity_key AS _evidence_chunk_entity_key,
                           sue.entity_key AS _supersedes_entity_key,vf.commit_sha AS _valid_from_commit_sha,
                           vt.commit_sha AS _valid_to_commit_sha
                    FROM memory.learned_records lr
                    JOIN catalog.entities e ON e.id=lr.entity_id
                    JOIN catalog.entities se ON se.id=lr.scope_entity_id
                    LEFT JOIN catalog.entities ee ON ee.id=lr.evidence_entity_id
                    LEFT JOIN catalog.chunks ec ON ec.id=lr.evidence_chunk_id
                    LEFT JOIN catalog.entities ce ON ce.id=ec.entity_id
                    LEFT JOIN memory.learned_records sulr ON sulr.id=lr.supersedes_learned_record_id
                    LEFT JOIN catalog.entities sue ON sue.id=sulr.entity_id
                    LEFT JOIN catalog.repo_revisions vf ON vf.id=lr.valid_from_revision_id
                    LEFT JOIN catalog.repo_revisions vt ON vt.id=lr.valid_to_revision_id
                    WHERE e.entity_key=$1 FOR UPDATE OF lr
                    """,
                    uuid.UUID(row["_entity_key"]),
                )
                if existing is not None:
                    if normalize_import_owned_record(existing) != item["stable"]:
                        raise ValueError("import-learned-record-conflict")
                    ek_to_lr_id[row["_entity_key"]] = existing["id"]
                    continue
                absent.append(item)

            ordered_absent = order_learned_insert_items(absent, set(ek_to_lr_id))
            for item in ordered_absent:
                row = item["row"]
                supersedes_lr_id = ek_to_lr_id.get(row.get("_supersedes_entity_key"))
                if row.get("_supersedes_entity_key") and supersedes_lr_id is None:
                    raise ValueError("import-learned-record-missing-supersedes")
                inserted = await conn.fetchrow(
                    """INSERT INTO memory.learned_records
                       (entity_id,scope_entity_id,memory_type,title,body_text,body_tsv,source_kind,
                        confidence,applicability_mode,valid_from_revision_id,valid_to_revision_id,
                        evidence_entity_id,evidence_chunk_id,verification_status,verification_notes,
                        is_active,supersedes_learned_record_id,created_utc,content_kind,evidence_refs,
                        evidence_resolution_errors)
                       VALUES ($1,$2,$3,$4,$5,to_tsvector('english',COALESCE($5,'')),$6,$7,$8,$9,
                               $10,$11,$12,$13,$14,$15,$16,$17,$18,$19::jsonb,$20::jsonb)
                       RETURNING id""",
                    item["entity_id"], item["scope_id"], row.get("memory_type"), row.get("title"),
                    row.get("body_text"), row.get("source_kind"), float(row.get("confidence") or 0.5),
                    row.get("applicability_mode") or "repository", item["vf_rev_id"], item["vt_rev_id"],
                    item["ev_id"], item["ev_chunk_id"], row.get("verification_status") or "unverified",
                    row.get("verification_notes"), bool(row.get("is_active")), supersedes_lr_id,
                    row.get("created_utc") or created, row.get("content_kind"),
                    json.dumps(row.get("evidence_refs")) if row.get("evidence_refs") is not None else None,
                    json.dumps(row.get("evidence_resolution_errors")) if row.get("evidence_resolution_errors") is not None else None,
                )
                ek_to_lr_id[row["_entity_key"]] = inserted["id"]
            if destination_repo_id:
                await conn.execute(
                    "INSERT INTO memory.learned_import_reports "
                    "(import_id,repository_id,cursor_secret,unresolved_total,created_utc,expires_utc) "
                    "VALUES ($1,$2,$3,$4,$5,$6)",
                    import_id, destination_repo_id, cursor_secret, len(unresolved), created, expires,
                )
                for ordinal, item in enumerate(sorted(
                    unresolved,
                    key=lambda value: (value["entity_key"], json.dumps(value["reason_codes"], sort_keys=True)),
                )):
                    await conn.execute(
                        "INSERT INTO memory.learned_import_unresolved "
                        "(import_id,ordinal,entity_key,reason_codes) VALUES ($1,$2,$3,$4::jsonb)",
                        import_id, ordinal, uuid.UUID(item["entity_key"]),
                        json.dumps(item["reason_codes"], sort_keys=True, separators=(",", ":")),
                    )
    _log("memory.learned_records", len(ek_to_lr_id), len(lr_rows))

    total = sum(imported.values())
    logger.info("import_complete", tables=list(imported.keys()), total_rows=total)
    page = sorted(unresolved, key=lambda value: value["entity_key"])[:100]
    next_cursor = None
    if len(unresolved) > 100 and destination_key:
        next_cursor = _encode_import_cursor(
            cursor_secret, import_id, destination_key, 99, expires
        )
    return {
        "tables_imported": list(imported.keys()), "rows_imported": total, "detail": imported,
        "unresolved_report": {
            "import_id": str(import_id), "unresolved_total": len(unresolved),
            "returned_count": len(page), "truncated": len(unresolved) > 100,
            "next_cursor": next_cursor, "expires_utc": expires.isoformat(), "items": page,
        },
    }


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _encode_import_cursor(
    secret: bytes, import_id: uuid.UUID, repository_key: str,
    after_ordinal: int, expires_utc: datetime,
) -> str:
    payload = {
        "v": 1, "import_id": str(import_id), "repository_key": repository_key,
        "after_ordinal": after_ordinal, "expires_utc": expires_utc.isoformat(),
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return _b64(body) + "." + _b64(hmac.new(secret, body, hashlib.sha256).digest())


async def list_import_unresolved(
    pool: asyncpg.Pool, repository_key: str, import_id: str,
    *, limit: int = 100, cursor: str | None = None,
) -> dict[str, Any]:
    if limit < 1 or limit > 100:
        raise ValueError("invalid-limit")
    report = await pool.fetchrow(
        """
        SELECT ir.*,r.repository_key FROM memory.learned_import_reports ir
        JOIN catalog.repositories r ON r.id=ir.repository_id
        WHERE ir.import_id=$1 AND lower(r.repository_key)=lower($2)
        """,
        uuid.UUID(import_id), repository_key,
    )
    if report is None:
        raise ValueError("import-result-not-found")
    if report["expired_utc"] is not None or report["expires_utc"] <= datetime.now(UTC):
        raise ValueError("import-result-expired")
    secret = bytes(report["cursor_secret"])
    after = -1
    if cursor:
        try:
            body_text, signature_text = cursor.split(".", 1)
            body = _unb64(body_text)
            signature = _unb64(signature_text)
            if not hmac.compare_digest(signature, hmac.new(secret, body, hashlib.sha256).digest()):
                raise ValueError
            payload = json.loads(body)
            if payload != {
                "v": 1, "import_id": str(report["import_id"]),
                "repository_key": report["repository_key"],
                "after_ordinal": payload.get("after_ordinal"),
                "expires_utc": report["expires_utc"].isoformat(),
            } or not isinstance(payload["after_ordinal"], int):
                raise ValueError
            after = payload["after_ordinal"]
            exists = await pool.fetchrow(
                "SELECT 1 FROM memory.learned_import_unresolved WHERE import_id=$1 AND ordinal=$2",
                report["import_id"], after,
            )
            if exists is None:
                raise ValueError
        except (ValueError, KeyError, json.JSONDecodeError, binascii.Error):
            raise ValueError("invalid-import-cursor") from None
    rows = await pool.fetch(
        "SELECT ordinal,entity_key,reason_codes FROM memory.learned_import_unresolved "
        "WHERE import_id=$1 AND ordinal>$2 ORDER BY ordinal ASC LIMIT $3",
        report["import_id"], after, limit + 1,
    )
    page = rows[:limit]
    items = [{"entity_key": str(row["entity_key"]), "reason_codes": row["reason_codes"]} for row in page]
    truncated = len(rows) > limit
    next_cursor = _encode_import_cursor(
        secret, report["import_id"], report["repository_key"],
        page[-1]["ordinal"], report["expires_utc"],
    ) if truncated and page else None
    return {
        "import_id": str(report["import_id"]), "unresolved_total": report["unresolved_total"],
        "returned_count": len(items), "truncated": truncated, "next_cursor": next_cursor,
        "expires_utc": report["expires_utc"].isoformat(), "items": items,
    }
