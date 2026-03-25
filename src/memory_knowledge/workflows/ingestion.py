from __future__ import annotations

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
from memory_knowledge.projections.neo4j_projector import project_repository_graph
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
    upsert_repo_revision,
    upsert_symbol,
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

        # Step 2: Clone/fetch repo, checkout commit
        repo = ensure_repo(repository_key, origin_url, settings.repo_clone_base_path)
        checkout_commit(repo, commit_sha)

        # Step 3: List Python files
        py_files = list_python_files(repo)
        logger.info("python_files_found", count=len(py_files))

        # Step 4: Register revision
        repo_revision_id = await upsert_repo_revision(
            pool, repository_id, commit_sha, branch_name
        )

        # Step 5: Process each file
        all_chunks_for_embedding: list[dict[str, Any]] = []
        neo4j_file_symbols: list[dict[str, Any]] = []
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

                # Register symbols
                file_symbol_records: list[dict[str, Any]] = []
                for sym in parse_output.symbols:
                    s_ek = symbol_entity_key(
                        repository_key, commit_sha, file_path, sym.name, sym.kind
                    )
                    await upsert_symbol(
                        pool, s_ek, repository_id, repo_revision_id, file_id,
                        sym.name, sym.kind, sym.line_start, sym.line_end, sym.signature,
                    )
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

                await record_ingestion_item(
                    pool, ingestion_run_id, entity_id, "file", "success"
                )
            except Exception as e:
                logger.error("file_ingestion_failed", file_path=file_path, error=str(e))
                await record_ingestion_item(
                    pool, ingestion_run_id, None, "file", "error", error_text=str(e)
                )

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

        # Step 9: Neo4j projection
        if neo4j_file_symbols:
            await project_repository_graph(
                neo4j_driver, repository_key, commit_sha,
                branch_name, neo4j_file_symbols,
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
