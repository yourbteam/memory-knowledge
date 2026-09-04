#!/usr/bin/env python3
"""Remap duplicate neocurrency-dashboard repository rows to the canonical row.

This is a focused production maintenance script. It is dry-run by default:
all changes are executed inside a transaction and rolled back unless --apply
is passed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import asyncpg

DUPLICATE_REPOSITORY_IDS = (93, 227)
DUPLICATE_REPOSITORY_KEYS = (
    "thebteambg/neocurrency-dashboard",
    "yourbteam/mcp-agents-workflow",
)
CANONICAL_REPOSITORY_ID = 410
CANONICAL_REPOSITORY_KEY = "neocurrency-dashboard"


class DryRunRollback(RuntimeError):
    """Raised to roll back a dry-run transaction."""


async def _fetch_counts(conn: asyncpg.Connection) -> dict[str, int]:
    duplicate_ids = list(DUPLICATE_REPOSITORY_IDS)
    task_rows = await conn.fetch(
        "select id, mawf_task_id from planning.tasks where repository_id = any($1::bigint[])",
        duplicate_ids,
    )
    task_ids = [row["id"] for row in task_rows]
    mawf_task_ids = [row["mawf_task_id"] for row in task_rows if row["mawf_task_id"]]
    workflow_run_ids = [
        row["id"]
        for row in await conn.fetch(
            "select id from ops.workflow_runs where repository_id = any($1::bigint[])",
            duplicate_ids,
        )
    ]
    return {
        "catalog.repositories": await conn.fetchval(
            "select count(*) from catalog.repositories where id = any($1::bigint[])",
            duplicate_ids,
        ),
        "planning.tasks": len(task_ids),
        "ops.workflow_runs": len(workflow_run_ids),
        "memory.qa_pairs": await conn.fetchval(
            "select count(*) from memory.qa_pairs where repository_id = any($1::bigint[])",
            duplicate_ids,
        ),
        "planning.project_repositories": await conn.fetchval(
            "select count(*) from planning.project_repositories where repository_id = any($1::bigint[])",
            duplicate_ids,
        ),
        "planning.task_workflow_runs": await conn.fetchval(
            """
            select count(*)
            from planning.task_workflow_runs
            where task_id = any($1::bigint[]) or workflow_run_id = any($2::bigint[])
            """,
            task_ids,
            workflow_run_ids,
        ),
        "ops.mawf_task_execution_leases": await conn.fetchval(
            """
            select count(*)
            from ops.mawf_task_execution_leases
            where task_id = any($1::bigint[]) or workflow_run_id = any($2::bigint[])
            """,
            task_ids,
            workflow_run_ids,
        ),
        "planning.mawf_artifact_refs": await conn.fetchval(
            "select count(*) from planning.mawf_artifact_refs where mawf_task_id = any($1::text[])",
            mawf_task_ids,
        ),
    }


async def _validate_expected_rows(conn: asyncpg.Connection) -> None:
    rows = await conn.fetch(
        """
        select id, repository_key, origin_url
        from catalog.repositories
        where id = any($1::bigint[]) or id = $2
        order by id
        for update
        """,
        list(DUPLICATE_REPOSITORY_IDS),
        CANONICAL_REPOSITORY_ID,
    )
    by_id = {row["id"]: row for row in rows}
    canonical = by_id.get(CANONICAL_REPOSITORY_ID)
    if not canonical or canonical["repository_key"] != CANONICAL_REPOSITORY_KEY or not canonical["origin_url"]:
        raise RuntimeError("Canonical neocurrency-dashboard repository row is missing or malformed")
    found_keys = {row["repository_key"] for row in rows if row["id"] in DUPLICATE_REPOSITORY_IDS}
    if found_keys != set(DUPLICATE_REPOSITORY_KEYS):
        missing = sorted(set(DUPLICATE_REPOSITORY_KEYS) - found_keys)
        if missing and len(found_keys) == 0:
            return
        raise RuntimeError(f"Duplicate repository rows do not match expected keys; missing={missing}")


async def _assert_no_remaining_direct_references(conn: asyncpg.Connection) -> None:
    duplicate_ids = list(DUPLICATE_REPOSITORY_IDS)
    checks = {
        "planning.tasks": "select count(*) from planning.tasks where repository_id = any($1::bigint[])",
        "ops.workflow_runs": "select count(*) from ops.workflow_runs where repository_id = any($1::bigint[])",
        "memory.qa_pairs": "select count(*) from memory.qa_pairs where repository_id = any($1::bigint[])",
        "planning.project_repositories": (
            "select count(*) from planning.project_repositories where repository_id = any($1::bigint[])"
        ),
    }
    remaining = {}
    for table, sql in checks.items():
        count = await conn.fetchval(sql, duplicate_ids)
        if count:
            remaining[table] = count
    if remaining:
        raise RuntimeError(f"Duplicate repository references remain before delete: {remaining}")


async def remap(database_url: str, *, apply: bool) -> dict[str, Any]:
    conn = await asyncpg.connect(database_url, ssl="require", statement_cache_size=0)
    summary: dict[str, Any] = {"mode": "apply" if apply else "dry-run"}
    try:
        try:
            async with conn.transaction():
                await conn.execute("select pg_advisory_xact_lock($1)", 41022793)
                await _validate_expected_rows(conn)
                summary["before"] = await _fetch_counts(conn)

                inserted_links = await conn.fetch(
                    """
                    insert into planning.project_repositories (project_id, repository_id, created_utc)
                    select dup.project_id, $2, min(dup.created_utc)
                    from planning.project_repositories dup
                    where dup.repository_id = any($1::bigint[])
                      and not exists (
                        select 1
                        from planning.project_repositories canon
                        where canon.project_id = dup.project_id
                          and canon.repository_id = $2
                      )
                    group by dup.project_id
                    on conflict do nothing
                    returning 1
                    """,
                    list(DUPLICATE_REPOSITORY_IDS),
                    CANONICAL_REPOSITORY_ID,
                )
                deleted_links = await conn.fetch(
                    """
                    delete from planning.project_repositories
                    where repository_id = any($1::bigint[])
                    returning project_id
                    """,
                    list(DUPLICATE_REPOSITORY_IDS),
                )
                updated_tasks = await conn.fetch(
                    """
                    update planning.tasks
                    set repository_id = $2
                    where repository_id = any($1::bigint[])
                    returning id
                    """,
                    list(DUPLICATE_REPOSITORY_IDS),
                    CANONICAL_REPOSITORY_ID,
                )
                updated_runs = await conn.fetch(
                    """
                    update ops.workflow_runs
                    set repository_id = $2
                    where repository_id = any($1::bigint[])
                    returning id
                    """,
                    list(DUPLICATE_REPOSITORY_IDS),
                    CANONICAL_REPOSITORY_ID,
                )
                updated_qa = await conn.fetch(
                    """
                    update memory.qa_pairs
                    set repository_id = $2
                    where repository_id = any($1::bigint[])
                    returning qa_pair_id
                    """,
                    list(DUPLICATE_REPOSITORY_IDS),
                    CANONICAL_REPOSITORY_ID,
                )

                await _assert_no_remaining_direct_references(conn)
                deleted_repos = await conn.fetch(
                    """
                    delete from catalog.repositories
                    where id = any($1::bigint[])
                    returning id, repository_key
                    """,
                    list(DUPLICATE_REPOSITORY_IDS),
                )
                summary["changes"] = {
                    "project_links_inserted": len(inserted_links),
                    "project_links_deleted": len(deleted_links),
                    "tasks_updated": len(updated_tasks),
                    "workflow_runs_updated": len(updated_runs),
                    "qa_pairs_updated": len(updated_qa),
                    "repositories_deleted": [dict(row) for row in deleted_repos],
                }
                summary["after"] = await _fetch_counts(conn)
                if not apply:
                    raise DryRunRollback
        except DryRunRollback:
            summary["rolled_back"] = True
        return summary
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--database-url-file", type=Path)
    parser.add_argument("--apply", action="store_true", help="Commit the remap; default is dry-run rollback.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_url = args.database_url
    if args.database_url_file:
        database_url = args.database_url_file.read_text().strip()
    if not database_url:
        raise SystemExit("Provide --database-url, --database-url-file, or DATABASE_URL.")
    summary = asyncio.run(remap(database_url, apply=args.apply))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
