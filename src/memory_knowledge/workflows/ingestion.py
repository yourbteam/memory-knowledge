from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient

from qdrant_client import models as qdrant_models

from memory_knowledge.config import Settings, get_supported_extensions
from memory_knowledge.git.clone import checkout_commit, ensure_repo, list_source_files
from memory_knowledge.git.diff import changed_files
from memory_knowledge.parsers.factory import detect_language, get_import_resolver, get_parser
from memory_knowledge.identity.entity_key import (
    chunk_entity_key,
    file_entity_key,
    summary_entity_key,
    symbol_entity_key,
)
from memory_knowledge.llm.complete import llm_complete
# Parser dispatch via factory — no direct adapter import
from memory_knowledge.projections.neo4j_projector import (
    project_additive_labels,
    project_api_endpoints,
    project_dependency_edges,
    project_inheritance_edges,
    project_modules,
    project_repository_graph,
    project_sql_edges,
)
from memory_knowledge.projections.pg_writer import (
    complete_ingestion_run,
    create_ingestion_run,
    record_ingestion_item,
    upsert_branch_head,
    upsert_chunk,
    upsert_retrieval_surface,
)
from memory_knowledge.projections.qdrant_projector import (
    deactivate_old_points,
    embed_chunks,
    upsert_points,
)
from memory_knowledge.projections.summary_qdrant import (
    deactivate_old_summary_points,
    embed_and_upsert_summaries,
)
from memory_knowledge.projections.summary_writer import upsert_summary
from memory_knowledge.structure.chunk_builder import build_chunks
from memory_knowledge.structure.entity_registrar import (
    upsert_file,
    upsert_file_import,
    upsert_repo_revision,
    upsert_symbol,
    upsert_symbol_call,
)
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_repo_ingestion_workflow"

def _summary_prompt(language: str) -> str:
    return (
        f"Summarize the following {language} code in 2-3 sentences. "
        "Focus on what it does, its inputs/outputs, and key behaviors."
    )


async def run(
    repository_key: str,
    commit_sha: str,
    branch_name: str,
    run_id: uuid.UUID,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    start = time.monotonic()
    ingestion_run_id: int | None = None

    try:
        if pool is None or qdrant_client is None or neo4j_driver is None or settings is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error="Missing required dependencies.",
            )

        # Step 0: Resolve repository
        row = await pool.fetchrow(
            "SELECT id, origin_url FROM catalog.repositories WHERE repository_key = $1",
            repository_key,
        )
        if row is None:
            raise ValueError(f"Repository not found: {repository_key}")
        repository_id = row["id"]
        origin_url = row["origin_url"]
        logger.info("repository_resolved", repository_key=repository_key)

        # Step 0.5: Determine old_sha for incremental detection
        old_sha_row = await pool.fetchrow(
            """
            SELECT rr.commit_sha
            FROM catalog.branch_heads bh
            JOIN catalog.repo_revisions rr ON bh.repo_revision_id = rr.id
            WHERE bh.repository_id = $1 AND bh.branch_name = $2
            """,
            repository_id,
            branch_name,
        )
        old_sha = old_sha_row["commit_sha"] if old_sha_row else None

        # Step 1: Clone/fetch repo, checkout commit
        repo = await asyncio.to_thread(
            ensure_repo, repository_key, origin_url, settings.repo_clone_base_path
        )
        await asyncio.to_thread(checkout_commit, repo, commit_sha)

        # Step 2: Determine file list (incremental or full)
        if old_sha is not None:
            extensions = get_supported_extensions(settings.supported_languages)
            diff_files = await asyncio.to_thread(changed_files, repo, old_sha, commit_sha, extensions)
        else:
            diff_files = None

        if diff_files is not None:
            py_files = diff_files
            run_type = "incremental"
        else:
            extensions = get_supported_extensions(settings.supported_languages)
            py_files = await asyncio.to_thread(list_source_files, repo, extensions)
            run_type = "full"

        logger.info("files_determined", count=len(py_files), run_type=run_type)

        # Step 3: Create ingestion run
        ingestion_run_id = await create_ingestion_run(
            pool, repository_id, commit_sha, branch_name, run_type=run_type
        )

        # Step 4: Register revision
        repo_revision_id = await upsert_repo_revision(
            pool, repository_id, commit_sha, branch_name
        )

        # Step 4.5: Pre-load existing file maps for incremental edge resolution
        all_chunks_for_embedding: list[dict[str, Any]] = []
        neo4j_file_symbols: list[dict[str, Any]] = []
        file_path_to_file_id: dict[str, int] = {}
        file_path_to_entity_key: dict[str, str] = {}
        file_path_to_entity_id: dict[str, int] = {}
        file_path_to_source: dict[str, str] = {}  # for summary generation
        symbol_lookup: dict[tuple[str, str], int] = {}
        all_imports: list[tuple[str, str]] = []
        all_calls: list[tuple[str, str, str, str]] = []

        if run_type == "incremental":
            existing_files = await pool.fetch(
                """
                SELECT f.file_path, f.id, e.entity_key, e.id AS entity_id
                FROM catalog.files f
                JOIN catalog.entities e ON f.entity_id = e.id
                WHERE e.repository_id = $1
                """,
                repository_id,
            )
            for ef in existing_files:
                fp = ef["file_path"]
                if fp not in file_path_to_file_id:
                    file_path_to_file_id[fp] = ef["id"]
                    file_path_to_entity_key[fp] = str(ef["entity_key"])
                    file_path_to_entity_id[fp] = ef["entity_id"]

        # Step 5: Process each file
        file_path_to_parse_output: dict[str, Any] = {}
        repo_dir = Path(settings.repo_clone_base_path) / repository_key

        for file_path in py_files:
            try:
                # Handle deleted files in incremental mode
                full_path = repo_dir / file_path
                if not full_path.exists():
                    logger.info("file_deleted", file_path=file_path)
                    await qdrant_client.set_payload(
                        collection_name="code_chunks",
                        payload={"is_active": False},
                        points=qdrant_models.Filter(
                            must=[
                                qdrant_models.FieldCondition(
                                    key="repository_key",
                                    match=qdrant_models.MatchValue(value=repository_key),
                                ),
                                qdrant_models.FieldCondition(
                                    key="file_path",
                                    match=qdrant_models.MatchValue(value=file_path),
                                ),
                                qdrant_models.FieldCondition(
                                    key="is_active",
                                    match=qdrant_models.MatchValue(value=True),
                                ),
                            ]
                        ),
                    )
                    await record_ingestion_item(
                        pool, ingestion_run_id, None, "file", "deleted"
                    )
                    continue

                # Deactivate old Qdrant points for this file (incremental)
                if run_type == "incremental":
                    await qdrant_client.set_payload(
                        collection_name="code_chunks",
                        payload={"is_active": False},
                        points=qdrant_models.Filter(
                            must=[
                                qdrant_models.FieldCondition(
                                    key="repository_key",
                                    match=qdrant_models.MatchValue(value=repository_key),
                                ),
                                qdrant_models.FieldCondition(
                                    key="file_path",
                                    match=qdrant_models.MatchValue(value=file_path),
                                ),
                                qdrant_models.FieldCondition(
                                    key="is_active",
                                    match=qdrant_models.MatchValue(value=True),
                                ),
                            ]
                        ),
                    )

                source = full_path.read_text(
                    encoding="utf-8", errors="replace"
                )
                source_lines = source.splitlines()
                size_bytes = len(source.encode("utf-8"))
                checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()

                # Parse
                parse_output = get_parser(file_path)(file_path, source)
                file_path_to_parse_output[file_path] = parse_output

                # Register file entity
                f_ek = file_entity_key(repository_key, commit_sha, file_path)
                entity_id, file_id = await upsert_file(
                    pool, f_ek, repository_id, repo_revision_id,
                    file_path, detect_language(file_path), size_bytes, checksum,
                    external_hash=checksum,
                )
                file_path_to_file_id[file_path] = file_id
                file_path_to_entity_key[file_path] = str(f_ek)
                file_path_to_entity_id[file_path] = entity_id
                file_path_to_source[file_path] = source

                # Register symbols
                file_symbol_records: list[dict[str, Any]] = []
                for sym in parse_output.symbols:
                    s_ek = symbol_entity_key(
                        repository_key, commit_sha, file_path, sym.name, sym.kind
                    )
                    sym_source = "\n".join(
                        source_lines[sym.line_start - 1 : sym.line_end]
                    )
                    sym_hash = hashlib.sha256(sym_source.encode("utf-8")).hexdigest()
                    _sym_entity_id, _sym_id = await upsert_symbol(
                        pool, s_ek, repository_id, repo_revision_id, file_id,
                        sym.name, sym.kind, sym.line_start, sym.line_end, sym.signature,
                        external_hash=sym_hash,
                    )
                    symbol_lookup[(file_path, sym.name)] = _sym_id
                    file_symbol_records.append(
                        {"entity_key": str(s_ek), "name": sym.name, "kind": sym.kind}
                    )

                neo4j_file_symbols.append(
                    {
                        "file_path": file_path,
                        "file_entity_key": str(f_ek),
                        "language": detect_language(file_path),
                        "symbols": file_symbol_records,
                        "routes": [
                            {"method": r.method, "path": r.path, "handler_name": r.handler_name}
                            for r in parse_output.routes
                        ],
                        "sql_refs": [
                            {"object_name": sr.object_name, "operation": sr.operation}
                            for sr in parse_output.sql_refs
                        ],
                    }
                )

                # Build chunks
                chunks = build_chunks(parse_output, source_lines)
                for chunk in chunks:
                    c_ek = chunk_entity_key(
                        repository_key, commit_sha, file_path, chunk.chunk_index
                    )
                    chunk_checksum = hashlib.sha256(
                        chunk.content_text.encode("utf-8")
                    ).hexdigest()
                    await upsert_chunk(
                        pool, c_ek, entity_id, file_id, chunk.title,
                        chunk.content_text, chunk.chunk_type,
                        chunk.line_start, chunk.line_end, chunk_checksum,
                    )
                    all_chunks_for_embedding.append(
                        {
                            "entity_key": str(c_ek),
                            "content_text": chunk.content_text,
                            "file_path": file_path,
                            "symbol_name": chunk.symbol_name,
                            "chunk_type": chunk.chunk_type,
                        }
                    )

                # Collect edges for post-loop resolution
                for imp in parse_output.imports:
                    all_imports.append((file_path, imp.module_path))
                for call in parse_output.calls:
                    caller_ek = str(symbol_entity_key(
                        repository_key, commit_sha, file_path, call.caller_name,
                        next((s.kind for s in parse_output.symbols if s.name == call.caller_name), "function"),
                    ))
                    all_calls.append((file_path, call.caller_name, call.callee_name, caller_ek))

                await record_ingestion_item(
                    pool, ingestion_run_id, entity_id, "file", "success"
                )
            except Exception as e:
                logger.error("file_ingestion_failed", file_path=file_path, error=str(e))
                await record_ingestion_item(
                    pool, ingestion_run_id, None, "file", "error", error_text=str(e)
                )

        # Step 5b: Resolve and upsert edges (post-loop)
        neo4j_import_edges: list[dict[str, str]] = []
        neo4j_call_edges: list[dict[str, str]] = []

        for importer_path, module_path in all_imports:
            # Per-language import resolution via factory
            language = detect_language(importer_path)
            resolver = get_import_resolver(language)
            if resolver is None:
                continue  # Language has no file-based imports (e.g., C#, SQL)
            result = resolver(module_path, file_path_to_file_id, file_path_to_entity_key)
            if result is not None:
                imported_file_id, imported_ek = result
                importer_file_id = file_path_to_file_id.get(importer_path)
                if importer_file_id:
                    await upsert_file_import(pool, importer_file_id, imported_file_id)
                    importer_ek = file_path_to_entity_key.get(importer_path, "")
                    if importer_ek and imported_ek:
                        neo4j_import_edges.append({
                            "importer_ek": importer_ek,
                            "imported_ek": imported_ek,
                        })

        # Build cross-file lookup indices
        name_to_symbols: dict[str, list[tuple[str, int]]] = {}
        for (fp, sname), sid in symbol_lookup.items():
            name_to_symbols.setdefault(sname, []).append((fp, sid))

        # Build file import target mapping for disambiguation
        file_import_targets: dict[str, set[str]] = {}
        for importer_path, module_path in all_imports:
            language = detect_language(importer_path)
            resolver = get_import_resolver(language)
            if resolver is None:
                continue
            result = resolver(module_path, file_path_to_file_id, file_path_to_entity_key)
            if result is not None:
                imported_fid, _ = result
                for fp, fid in file_path_to_file_id.items():
                    if fid == imported_fid:
                        file_import_targets.setdefault(importer_path, set()).add(fp)
                        break

        # Build symbol entity_key lookup from neo4j_file_symbols
        symbol_ek_lookup: dict[tuple[str, str], str] = {}
        for fs in neo4j_file_symbols:
            for s in fs["symbols"]:
                symbol_ek_lookup[(fs["file_path"], s["name"])] = s["entity_key"]

        for file_path_call, caller_name, callee_name, caller_ek in all_calls:
            caller_sid = symbol_lookup.get((file_path_call, caller_name))
            callee_sid = symbol_lookup.get((file_path_call, callee_name))
            callee_file = file_path_call  # assume same file initially

            # Cross-file resolution if same-file lookup fails
            if callee_sid is None:
                candidates = name_to_symbols.get(callee_name, [])
                if len(candidates) == 1:
                    callee_file, callee_sid = candidates[0]
                elif len(candidates) > 1:
                    imported = file_import_targets.get(file_path_call, set())
                    for cand_fp, cand_sid in candidates:
                        if cand_fp in imported:
                            callee_file, callee_sid = cand_fp, cand_sid
                            break

            if caller_sid and callee_sid:
                await upsert_symbol_call(pool, caller_sid, callee_sid)
                callee_ek = symbol_ek_lookup.get((callee_file, callee_name))
                if callee_ek:
                    neo4j_call_edges.append({
                        "caller_ek": caller_ek,
                        "callee_ek": callee_ek,
                    })

        logger.info("edges_resolved", imports=len(neo4j_import_edges), calls=len(neo4j_call_edges))

        # Step 5c-pre: Check and invalidate stale learned records
        changed_file_paths = list(file_path_to_source.keys())
        if changed_file_paths:
            try:
                stale_rows = await pool.fetch(
                    """
                    SELECT lr.id, e.entity_key
                    FROM memory.learned_records lr
                    JOIN catalog.entities e ON lr.entity_id = e.id
                    JOIN catalog.entities scope_e ON lr.scope_entity_id = scope_e.id
                    JOIN catalog.files f ON f.entity_id = scope_e.id
                    WHERE f.file_path = ANY($1::text[])
                      AND lr.is_active = TRUE
                      AND scope_e.repository_id = $2
                    """,
                    changed_file_paths,
                    repository_id,
                )
                if stale_rows:
                    from memory_knowledge.lifecycle.staleness_checker import mark_stale
                    from memory_knowledge.projections.learned_memory_neo4j import deactivate_learned_rule
                    from memory_knowledge.projections.learned_memory_qdrant import deactivate_learned_record_point

                    stale_ids = [r["id"] for r in stale_rows]
                    await mark_stale(pool, stale_ids)
                    for r in stale_rows:
                        ek = str(r["entity_key"])
                        try:
                            await deactivate_learned_record_point(qdrant_client, ek)
                        except Exception:
                            pass
                        try:
                            await deactivate_learned_rule(neo4j_driver, ek)
                        except Exception:
                            pass
                    logger.info("stale_records_invalidated", count=len(stale_ids))
            except Exception as exc:
                logger.warning("staleness_check_failed", error=str(exc))

        # Step 5c: Generate summaries (if enabled)
        all_summaries_for_embedding: list[dict[str, Any]] = []
        summaries_created = 0

        if settings.generate_summaries:
            for fp, source in file_path_to_source.items():
                file_eid = file_path_to_entity_id.get(fp)
                file_ek = file_path_to_entity_key.get(fp, "")
                if not file_eid:
                    continue

                # File-level summary
                try:
                    file_summary = await llm_complete(
                        source[:8000], settings, system_prompt=_summary_prompt(detect_language(fp))
                    )
                    if not file_summary or not file_summary.strip():
                        logger.warning("empty_file_summary_skipped", file_path=fp)
                        continue
                    s_ek = summary_entity_key(repository_key, commit_sha, file_ek, "file")
                    await upsert_summary(pool, s_ek, file_eid, "file", file_summary)
                    all_summaries_for_embedding.append({
                        "entity_key": str(s_ek),
                        "summary_text": file_summary,
                        "summary_level": "file",
                    })
                    summaries_created += 1
                except Exception as exc:
                    logger.warning("file_summary_failed", file_path=fp, error=str(exc))
                    await record_ingestion_item(
                        pool, ingestion_run_id, file_eid, "summary", "error", error_text=str(exc)
                    )

                # Symbol-level summaries
                for fs in neo4j_file_symbols:
                    if fs["file_path"] != fp:
                        continue
                    source_lines = source.splitlines()
                    for sym_rec in fs["symbols"]:
                        try:
                            # Extract symbol source using cached parse output
                            sym_source = None
                            cached_parse = file_path_to_parse_output.get(fp)
                            if cached_parse:
                                for psym in cached_parse.symbols:
                                    if psym.name == sym_rec["name"]:
                                        sym_source = "\n".join(
                                            source_lines[psym.line_start - 1 : psym.line_end]
                                        )
                                        break
                            if not sym_source:
                                continue  # skip summary if symbol source not found
                            sym_ek = sym_rec["entity_key"]
                            s_ek = summary_entity_key(
                                repository_key, commit_sha, sym_ek, "symbol"
                            )
                            sym_summary = await llm_complete(
                                f"Symbol: {sym_rec['name']} ({sym_rec['kind']})\n\n{sym_source[:4000]}",
                                settings,
                                system_prompt=_summary_prompt(detect_language(fp)),
                            )
                            if not sym_summary or not sym_summary.strip():
                                continue
                            # Look up symbol entity_id
                            sym_eid_row = await pool.fetchrow(
                                "SELECT id FROM catalog.entities WHERE entity_key = $1",
                                uuid.UUID(sym_ek),
                            )
                            if sym_eid_row:
                                await upsert_summary(pool, s_ek, sym_eid_row["id"], "symbol", sym_summary)
                                all_summaries_for_embedding.append({
                                    "entity_key": str(s_ek),
                                    "summary_text": sym_summary,
                                    "summary_level": "symbol",
                                })
                                summaries_created += 1
                        except Exception as exc:
                            logger.warning(
                                "symbol_summary_failed",
                                symbol=sym_rec["name"],
                                error=str(exc),
                            )

            logger.info("summaries_generated", count=summaries_created)

        # Step 6: Embed all chunks
        if all_chunks_for_embedding:
            texts = [c["content_text"] for c in all_chunks_for_embedding]
            embeddings = await embed_chunks(texts, settings)
            for c, emb in zip(all_chunks_for_embedding, embeddings):
                c["embedding"] = emb

            # Step 7: Upsert to Qdrant
            await upsert_points(
                qdrant_client, all_chunks_for_embedding,
                repository_key, commit_sha, branch_name,
            )

        # Step 7b: Embed and upsert summaries to Qdrant
        if all_summaries_for_embedding:
            await embed_and_upsert_summaries(
                qdrant_client, all_summaries_for_embedding,
                repository_key, commit_sha, settings,
            )

        # Step 8: Deactivate old points (only for full runs)
        if run_type == "full":
            await deactivate_old_points(
                qdrant_client, repository_key, branch_name, commit_sha
            )
            await deactivate_old_summary_points(
                qdrant_client, repository_key, commit_sha
            )

        # Step 9: Neo4j projection (structure + dependency edges)
        if neo4j_file_symbols:
            await project_repository_graph(
                neo4j_driver, repository_key, commit_sha,
                branch_name, neo4j_file_symbols,
            )
        if neo4j_import_edges or neo4j_call_edges:
            await project_dependency_edges(
                neo4j_driver, neo4j_import_edges, neo4j_call_edges,
            )

        # Step 9b: Additive labels (DbTable, StoredProcedure) + Modules + Endpoints
        if neo4j_file_symbols:
            await project_additive_labels(neo4j_driver, neo4j_file_symbols)

            # Module detection: directories with 2+ source files or __init__.py
            from collections import defaultdict
            import os
            dir_files: dict[str, list[str]] = defaultdict(list)
            has_init: set[str] = set()
            for fs in neo4j_file_symbols:
                fp = fs["file_path"]
                dir_path = os.path.dirname(fp)
                if dir_path:
                    dir_files[dir_path].append(fs["file_entity_key"])
                    if os.path.basename(fp) == "__init__.py":
                        has_init.add(dir_path)

            modules_data = []
            for dir_path, file_keys in dir_files.items():
                if len(file_keys) >= 2 or dir_path in has_init:
                    mod_ek = str(uuid.uuid5(
                        uuid.UUID("b7e15163-2a0e-4e29-8f3a-d4b612c8a1f7"),
                        f"{repository_key}:module:{dir_path}",
                    ))
                    modules_data.append({
                        "entity_key": mod_ek,
                        "path": dir_path,
                        "name": os.path.basename(dir_path) or dir_path,
                        "file_keys": file_keys,
                    })
            await project_modules(neo4j_driver, repository_key, modules_data)

            # ApiEndpoint projection from route data
            endpoints_data = []
            for fs in neo4j_file_symbols:
                for route in fs.get("routes", []):
                    ep_ek = str(uuid.uuid5(
                        uuid.UUID("b7e15163-2a0e-4e29-8f3a-d4b612c8a1f7"),
                        f"{repository_key}:endpoint:{route['method']}:{route['path']}",
                    ))
                    endpoints_data.append({
                        "entity_key": ep_ek,
                        "method": route["method"],
                        "path": route["path"],
                        "file_entity_key": fs["file_entity_key"],
                    })
            await project_api_endpoints(neo4j_driver, endpoints_data)

            # SQL READS_TABLE/WRITES_TABLE edges
            sql_edge_data: list[dict[str, str]] = []
            for fs in neo4j_file_symbols:
                for sr in fs.get("sql_refs", []):
                    # Find DbTable entity_key by matching symbol name
                    table_ek = None
                    for fs2 in neo4j_file_symbols:
                        for s in fs2.get("symbols", []):
                            if s["name"].lower() == sr["object_name"].lower() and s["kind"] in ("table", "view"):
                                table_ek = s["entity_key"]
                                break
                        if table_ek:
                            break
                    if table_ek:
                        rel = "READS_TABLE" if sr["operation"] == "select" else "WRITES_TABLE"
                        sql_edge_data.append({
                            "source_ek": fs["file_entity_key"],
                            "target_ek": table_ek,
                            "rel_type": rel,
                        })
            await project_sql_edges(neo4j_driver, sql_edge_data)

            # Inheritance edges (EXTENDS/IMPLEMENTS)
            inheritance_edges: list[dict[str, str]] = []

            def _find_symbol_ek(name: str) -> str | None:
                for fs2 in neo4j_file_symbols:
                    for s in fs2["symbols"]:
                        if s["name"] == name:
                            return s["entity_key"]
                return None

            for fs in neo4j_file_symbols:
                cached = file_path_to_parse_output.get(fs["file_path"])
                if not cached:
                    continue
                for sym in cached.symbols:
                    if sym.kind != "class":
                        continue
                    child_ek = symbol_ek_lookup.get((fs["file_path"], sym.name))
                    if not child_ek:
                        continue

                    # EXTENDS edges from base_classes
                    for base_name in sym.base_classes:
                        # For C#, base_classes may include interfaces (: Base, IFoo)
                        if cached.language == "csharp":
                            is_iface = base_name.startswith("I") and len(base_name) > 1 and base_name[1].isupper()
                            rel = "IMPLEMENTS" if is_iface else "EXTENDS"
                        else:
                            rel = "EXTENDS"
                        target_ek = _find_symbol_ek(base_name)
                        if target_ek:
                            inheritance_edges.append({
                                "child_ek": child_ek, "target_ek": target_ek, "rel_type": rel,
                            })

                    # IMPLEMENTS edges from implements field (TS, PHP)
                    for iface_name in sym.implements:
                        target_ek = _find_symbol_ek(iface_name)
                        if target_ek:
                            inheritance_edges.append({
                                "child_ek": child_ek, "target_ek": target_ek, "rel_type": "IMPLEMENTS",
                            })

            await project_inheritance_edges(neo4j_driver, inheritance_edges)

        # Step 10: Update branch head + retrieval surface
        await upsert_branch_head(pool, repository_id, branch_name, repo_revision_id)
        await upsert_retrieval_surface(
            pool, repository_id, "live_branch",
            branch_name, commit_sha, repo_revision_id,
        )

        # Step 11: Complete ingestion run
        await complete_ingestion_run(pool, ingestion_run_id, status="completed")

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "ingestion_complete",
            duration_ms=duration_ms,
            files=len(py_files),
            chunks=len(all_chunks_for_embedding),
        )

        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="success",
            data={
                "files_processed": len(py_files),
                "chunks_created": len(all_chunks_for_embedding),
                "summaries_created": summaries_created,
                "run_type": run_type,
            },
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("ingestion_failed", error=str(exc), duration_ms=duration_ms)
        if pool is not None and ingestion_run_id is not None:
            try:
                await complete_ingestion_run(
                    pool, ingestion_run_id, "failed", str(exc)
                )
            except Exception:
                pass
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
