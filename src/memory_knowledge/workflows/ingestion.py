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

from memory_knowledge.config import Settings
from memory_knowledge.git.clone import checkout_commit, ensure_repo, list_python_files
from memory_knowledge.identity.entity_key import (
    chunk_entity_key,
    file_entity_key,
    symbol_entity_key,
)
from memory_knowledge.parsers.python_adapter import parse_python_file
from memory_knowledge.projections.neo4j_projector import (
    project_dependency_edges,
    project_repository_graph,
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

        # Step 1: Create ingestion run
        ingestion_run_id = await create_ingestion_run(
            pool, repository_id, commit_sha, branch_name, run_type="full"
        )

        # Step 2: Clone/fetch repo, checkout commit (run in thread to avoid blocking event loop)
        repo = await asyncio.to_thread(
            ensure_repo, repository_key, origin_url, settings.repo_clone_base_path
        )
        await asyncio.to_thread(checkout_commit, repo, commit_sha)

        # Step 3: List Python files
        py_files = await asyncio.to_thread(list_python_files, repo)
        logger.info("python_files_found", count=len(py_files))

        # Step 4: Register revision
        repo_revision_id = await upsert_repo_revision(
            pool, repository_id, commit_sha, branch_name
        )

        # Step 5: Process each file
        all_chunks_for_embedding: list[dict[str, Any]] = []
        neo4j_file_symbols: list[dict[str, Any]] = []
        file_path_to_file_id: dict[str, int] = {}
        file_path_to_entity_key: dict[str, str] = {}
        symbol_lookup: dict[tuple[str, str], int] = {}  # (file_path, symbol_name) → symbol_id
        all_imports: list[tuple[str, str]] = []  # (importer_file_path, module_path)
        all_calls: list[tuple[str, str, str, str]] = []  # (file_path, caller_name, callee_name, caller_ek)
        repo_dir = Path(settings.repo_clone_base_path) / repository_key

        for file_path in py_files:
            try:
                source = (repo_dir / file_path).read_text(
                    encoding="utf-8", errors="replace"
                )
                source_lines = source.splitlines()
                size_bytes = len(source.encode("utf-8"))
                checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()

                # Parse
                parse_output = parse_python_file(file_path, source)

                # Register file entity
                f_ek = file_entity_key(repository_key, commit_sha, file_path)
                entity_id, file_id = await upsert_file(
                    pool, f_ek, repository_id, repo_revision_id,
                    file_path, "python", size_bytes, checksum,
                )
                file_path_to_file_id[file_path] = file_id
                file_path_to_entity_key[file_path] = str(f_ek)

                # Register symbols
                file_symbol_records: list[dict[str, Any]] = []
                for sym in parse_output.symbols:
                    s_ek = symbol_entity_key(
                        repository_key, commit_sha, file_path, sym.name, sym.kind
                    )
                    _sym_entity_id, _sym_id = await upsert_symbol(
                        pool, s_ek, repository_id, repo_revision_id, file_id,
                        sym.name, sym.kind, sym.line_start, sym.line_end, sym.signature,
                    )
                    symbol_lookup[(file_path, sym.name)] = _sym_id
                    file_symbol_records.append(
                        {"entity_key": str(s_ek), "name": sym.name, "kind": sym.kind}
                    )

                neo4j_file_symbols.append(
                    {
                        "file_path": file_path,
                        "file_entity_key": str(f_ek),
                        "symbols": file_symbol_records,
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
        py_file_set = set(py_files)

        for importer_path, module_path in all_imports:
            # Resolve module_path to file_path with suffix matching
            candidates = [
                module_path.replace(".", "/") + ".py",
                module_path.replace(".", "/") + "/__init__.py",
            ]
            imported_file_id = None
            imported_ek = None
            for candidate in candidates:
                for known_path in file_path_to_file_id:
                    if known_path.endswith(candidate):
                        imported_file_id = file_path_to_file_id[known_path]
                        imported_ek = file_path_to_entity_key[known_path]
                        break
                if imported_file_id is not None:
                    break
            if imported_file_id is not None:
                importer_file_id = file_path_to_file_id.get(importer_path)
                if importer_file_id:
                    await upsert_file_import(pool, importer_file_id, imported_file_id)
                    importer_ek = file_path_to_entity_key.get(importer_path, "")
                    if importer_ek and imported_ek:
                        neo4j_import_edges.append({
                            "importer_ek": importer_ek,
                            "imported_ek": imported_ek,
                        })

        for file_path_call, caller_name, callee_name, caller_ek in all_calls:
            caller_sid = symbol_lookup.get((file_path_call, caller_name))
            callee_sid = symbol_lookup.get((file_path_call, callee_name))
            if caller_sid and callee_sid:
                await upsert_symbol_call(pool, caller_sid, callee_sid)
                callee_ek = str(symbol_entity_key(
                    repository_key, commit_sha, file_path_call, callee_name,
                    next((s.kind for s in [] ), "function"),  # kind not needed for entity_key lookup
                ))
                # Look up callee entity_key from the symbol records
                for fs in neo4j_file_symbols:
                    if fs["file_path"] == file_path_call:
                        for s in fs["symbols"]:
                            if s["name"] == callee_name:
                                callee_ek = s["entity_key"]
                                break
                        break
                neo4j_call_edges.append({
                    "caller_ek": caller_ek,
                    "callee_ek": callee_ek,
                })

        logger.info("edges_resolved", imports=len(neo4j_import_edges), calls=len(neo4j_call_edges))

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

            # Step 8: Deactivate old points
            await deactivate_old_points(
                qdrant_client, repository_key, branch_name, commit_sha
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
