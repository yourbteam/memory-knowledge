#!/usr/bin/env python3
"""Ingest a repo locally, then promote it to the remote stores.

Fast path:
1. call the local MCP server to register and ingest a branch/commit
2. export repo memory from local PostgreSQL
3. optionally purge existing remote repo-owned data across PostgreSQL/Qdrant/Neo4j
4. import the PostgreSQL JSONL into remote PostgreSQL
5. copy already-embedded Qdrant points from local Qdrant to remote Qdrant
6. rebuild the remote Neo4j projection from imported PostgreSQL canonical data

The script assumes local and remote memory-knowledge services/databases are
already reachable. For Docker local mode, host-side defaults translate
postgres/qdrant/neo4j service hostnames to localhost.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg
import neo4j
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from qdrant_client import AsyncQdrantClient, models

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_MCP_URL = "http://localhost:8000/mcp/"
DEFAULT_REMOTE_MCP_URL = "https://memory-knowledge.azurewebsites.net/mcp/"
DEFAULT_ARTIFACT_DIR = ROOT / "Tasks" / "tpp-petkey-onboarding-rollout" / "artifacts"


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _host_default(value: str) -> str:
    return (
        value.replace("@postgres:5432/", "@localhost:5432/")
        .replace("http://qdrant:6333", "http://localhost:6333")
        .replace("bolt://neo4j:7687", "bolt://localhost:7687")
    )


def _tool_text(result: Any) -> str:
    for block in result.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


def _parse_tool_json(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Tool returned non-JSON output: {raw[:500]}") from exc


async def call_tool(url: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            return _parse_tool_json(_tool_text(result))


async def poll_job(url: str, job_id: str, *, interval: float, timeout: float) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        data = await call_tool(url, "check_job_status", {"job_id": job_id})
        job = data.get("data") or {}
        state = job.get("state_code")
        print(f"job {job_id} state={state}")
        if state in {"succeeded", "success", "failed", "dead_letter", "cancelled"}:
            return data
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Timed out waiting for job {job_id}; last state={state}")
        await asyncio.sleep(interval)


async def export_repo_memory(database_url: str, repository_key: str, artifact_path: Path) -> tuple[int, int]:
    from memory_knowledge.admin.export_import import export_repo_memory as _export

    pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=5)
    try:
        lines = await _export(pool, repository_key)
    finally:
        await pool.close()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return len(lines), artifact_path.stat().st_size


async def import_repo_memory(database_url: str, artifact_path: Path) -> dict[str, Any]:
    from memory_knowledge.admin.export_import import import_repo_memory as _import

    pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=5, statement_cache_size=0)
    try:
        lines = [line for line in artifact_path.read_text().splitlines() if line.strip()]
        return await _import(pool, lines)
    finally:
        await pool.close()


def _repo_filter(repository_key: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="repository_key",
                match=models.MatchValue(value=repository_key),
            )
        ]
    )


async def copy_qdrant_points(
    *,
    local_url: str,
    local_api_key: str | None,
    remote_url: str,
    remote_api_key: str | None,
    repository_key: str,
    purge_remote: bool,
) -> dict[str, int]:
    from memory_knowledge.config import Settings
    from memory_knowledge.db.qdrant import COLLECTIONS, ensure_collections

    local = AsyncQdrantClient(url=local_url, api_key=local_api_key or None, timeout=120)
    remote = AsyncQdrantClient(url=remote_url, api_key=remote_api_key or None, timeout=120)
    counts: dict[str, int] = {}
    try:
        await ensure_collections(remote, Settings())
        flt = _repo_filter(repository_key)
        for collection in COLLECTIONS:
            if purge_remote:
                await remote.delete(collection_name=collection, points_selector=models.FilterSelector(filter=flt))
            copied = 0
            offset = None
            while True:
                points, offset = await local.scroll(
                    collection_name=collection,
                    scroll_filter=flt,
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )
                if points:
                    await remote.upsert(
                        collection_name=collection,
                        points=[
                            models.PointStruct(id=p.id, vector=p.vector, payload=p.payload or {})
                            for p in points
                        ],
                    )
                    copied += len(points)
                if offset is None:
                    break
            counts[collection] = copied
            print(f"qdrant {collection}: copied={copied}")
    finally:
        await local.close()
        await remote.close()
    return counts


async def purge_remote(database_url: str, qdrant_url: str, qdrant_api_key: str | None, neo4j_uri: str, neo4j_user: str, neo4j_password: str, repository_key: str) -> dict[str, Any]:
    from memory_knowledge.admin.purge import purge_repository

    pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=5, statement_cache_size=0)
    qdrant = AsyncQdrantClient(url=qdrant_url, api_key=qdrant_api_key or None, timeout=120)
    driver = neo4j.AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        try:
            return await purge_repository(
                pool=pool,
                qdrant_client=qdrant,
                neo4j_driver=driver,
                repository_key=repository_key,
            )
        except ValueError as exc:
            if "not found" not in str(exc).lower():
                raise
            return {"repository_key": repository_key, "already_absent": True}
    finally:
        await driver.close()
        await qdrant.close()
        await pool.close()


async def rebuild_remote_neo4j(
    *,
    database_url: str,
    qdrant_url: str,
    qdrant_api_key: str | None,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    repository_key: str,
    commit_sha: str,
) -> dict[str, Any]:
    from memory_knowledge.config import Settings
    from memory_knowledge.integrity.repair_drift import rebuild_revision

    pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=5, statement_cache_size=0)
    qdrant = AsyncQdrantClient(url=qdrant_url, api_key=qdrant_api_key or None, timeout=120)
    driver = neo4j.AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        settings = Settings()
        report = await rebuild_revision(
            pool=pool,
            qdrant_client=qdrant,
            neo4j_driver=driver,
            settings=settings,
            repository_key=repository_key,
            commit_sha=commit_sha,
            repair_scope="neo4j",
        )
        return report.model_dump()
    finally:
        await driver.close()
        await qdrant.close()
        await pool.close()


async def main_async(args: argparse.Namespace) -> int:
    local_env = _load_env(Path(args.local_env))
    remote_env = _load_env(Path(args.remote_env))

    local_db = args.local_database_url or _host_default(local_env["DATABASE_URL"])
    remote_db = args.remote_database_url or remote_env["DATABASE_URL"]
    local_qdrant = args.local_qdrant_url or _host_default(local_env["QDRANT_URL"])
    remote_qdrant = args.remote_qdrant_url or remote_env["QDRANT_URL"]
    local_neo4j = args.local_neo4j_uri or _host_default(local_env["NEO4J_URI"])
    remote_neo4j = args.remote_neo4j_uri or remote_env["NEO4J_URI"]

    artifact = Path(args.artifact) if args.artifact else DEFAULT_ARTIFACT_DIR / f"{args.repository_key}-{args.branch_name}-{args.commit_sha}.jsonl"

    if not args.skip_local_ingest:
        print("upserting MAWF repository contract locally")
        mawf_repo = await call_tool(
            args.local_mcp_url,
            "mawf_upsert_repository",
            {
                "repository_key": args.repository_key,
                "provider": "github",
                "owner": "thebteambg",
                "repo_name": args.repository_key,
                "remote_url": args.origin_url,
                "status_code": "active",
            },
        )
        print(json.dumps(mawf_repo, indent=2, default=str))
        if mawf_repo.get("status") != "success":
            raise RuntimeError(f"local MAWF repository upsert failed: {mawf_repo}")

        print(f"submitting local ingestion branch={args.branch_name} commit={args.commit_sha}")
        submitted = await call_tool(
            args.local_mcp_url,
            "run_repo_ingestion_workflow",
            {
                "repository_key": args.repository_key,
                "branch_name": args.branch_name,
                "commit_sha": args.commit_sha,
            },
        )
        print(json.dumps(submitted, indent=2, default=str))
        job_id = (submitted.get("data") or {}).get("job_id")
        if not job_id:
            raise RuntimeError(f"local ingestion did not return job_id: {submitted}")
        done = await poll_job(args.local_mcp_url, job_id, interval=args.poll_interval, timeout=args.ingest_timeout)
        job = done.get("data") or {}
        if job.get("state_code") not in {"succeeded", "success"}:
            raise RuntimeError(f"local ingestion failed: {done}")

    print(f"exporting local PostgreSQL memory to {artifact}")
    line_count, size = await export_repo_memory(local_db, args.repository_key, artifact)
    print(f"exported line_count={line_count} size_bytes={size}")
    if line_count == 0:
        raise RuntimeError("export produced zero lines")

    if args.purge_remote:
        print("purging existing remote repo-owned data")
        purged = await purge_remote(
            remote_db,
            remote_qdrant,
            remote_env.get("QDRANT_API_KEY"),
            remote_neo4j,
            remote_env["NEO4J_USER"],
            remote_env["NEO4J_PASSWORD"],
            args.repository_key,
        )
        print(json.dumps(purged, indent=2, default=str))

    print("importing PostgreSQL memory into remote")
    imported = await import_repo_memory(remote_db, artifact)
    print(json.dumps(imported, indent=2, default=str))

    print("copying Qdrant points local -> remote")
    qdrant_counts = await copy_qdrant_points(
        local_url=local_qdrant,
        local_api_key=local_env.get("QDRANT_API_KEY"),
        remote_url=remote_qdrant,
        remote_api_key=remote_env.get("QDRANT_API_KEY"),
        repository_key=args.repository_key,
        purge_remote=args.purge_remote,
    )
    print(json.dumps({"qdrant": qdrant_counts}, indent=2))

    print("rebuilding remote Neo4j from imported PostgreSQL canonical data")
    neo4j_report = await rebuild_remote_neo4j(
        database_url=remote_db,
        qdrant_url=remote_qdrant,
        qdrant_api_key=remote_env.get("QDRANT_API_KEY"),
        neo4j_uri=remote_neo4j,
        neo4j_user=remote_env["NEO4J_USER"],
        neo4j_password=remote_env["NEO4J_PASSWORD"],
        repository_key=args.repository_key,
        commit_sha=args.commit_sha,
    )
    print(json.dumps({"neo4j": neo4j_report}, indent=2, default=str))

    print("remote verification via MCP")
    repos = await call_tool(args.remote_mcp_url, "list_repositories", {})
    stats = await call_tool(args.remote_mcp_url, "get_memory_stats", {"repository_key": args.repository_key})
    print(json.dumps({"list_repositories": repos, "get_memory_stats": stats}, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-key", default="tpp-petkey")
    parser.add_argument("--origin-url", default="https://github.com/thebteambg/tpp-petkey.git")
    parser.add_argument("--branch-name", default="main")
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--local-mcp-url", default=DEFAULT_LOCAL_MCP_URL)
    parser.add_argument("--remote-mcp-url", default=DEFAULT_REMOTE_MCP_URL)
    parser.add_argument("--local-env", default=str(ROOT / ".env.local"))
    parser.add_argument("--remote-env", default=str(ROOT / ".env"))
    parser.add_argument("--local-database-url")
    parser.add_argument("--remote-database-url")
    parser.add_argument("--local-qdrant-url")
    parser.add_argument("--remote-qdrant-url")
    parser.add_argument("--local-neo4j-uri")
    parser.add_argument("--remote-neo4j-uri")
    parser.add_argument("--artifact")
    parser.add_argument("--poll-interval", type=float, default=20.0)
    parser.add_argument("--ingest-timeout", type=float, default=21600.0)
    parser.add_argument("--skip-local-ingest", action="store_true")
    parser.add_argument("--purge-remote", action="store_true")
    args = parser.parse_args()

    os.chdir(ROOT)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)
