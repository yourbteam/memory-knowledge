from __future__ import annotations

import uuid
from typing import Any

import asyncpg


async def resolve_repository_ids(
    pool: asyncpg.Pool, repository_keys: list[str]
) -> list[int]:
    if not repository_keys:
        return []
    rows = await pool.fetch(
        """
        SELECT repository_key, id
        FROM catalog.repositories
        WHERE repository_key = ANY($1::text[])
        """,
        repository_keys,
    )
    found = {row["repository_key"]: row["id"] for row in rows}
    missing = [key for key in repository_keys if key not in found]
    if missing:
        raise ValueError(f"Repositories not found: {', '.join(missing)}")
    return [found[key] for key in repository_keys]


async def resolve_repository_id(pool: asyncpg.Pool, repository_key: str) -> int:
    row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1",
        repository_key,
    )
    if row is None:
        raise ValueError(f"Repository not found: {repository_key}")
    return row["id"]


async def ensure_project_has_repository(
    pool: asyncpg.Pool,
    project_id: int,
    repository_id: int,
) -> None:
    row = await pool.fetchrow(
        """
        SELECT 1
        FROM planning.project_repositories
        WHERE project_id = $1 AND repository_id = $2
        """,
        project_id,
        repository_id,
    )
    if row is None:
        raise ValueError("Repository is not linked to the project")


async def ensure_feature_has_repository(
    pool: asyncpg.Pool,
    feature_id: int,
    repository_id: int,
) -> None:
    row = await pool.fetchrow(
        """
        SELECT 1
        FROM planning.feature_repositories
        WHERE feature_id = $1 AND repository_id = $2
        """,
        feature_id,
        repository_id,
    )
    if row is None:
        raise ValueError("Repository is not linked to the feature")


async def resolve_project_id(pool: asyncpg.Pool, project_key: str) -> int:
    row = await pool.fetchrow(
        "SELECT id FROM planning.projects WHERE project_key = $1",
        uuid.UUID(project_key),
    )
    if row is None:
        raise ValueError(f"Project not found: {project_key}")
    return row["id"]


async def resolve_feature_id(pool: asyncpg.Pool, feature_key: str) -> int:
    row = await pool.fetchrow(
        "SELECT id FROM planning.features WHERE feature_key = $1",
        uuid.UUID(feature_key),
    )
    if row is None:
        raise ValueError(f"Feature not found: {feature_key}")
    return row["id"]


async def resolve_feature_context(pool: asyncpg.Pool, feature_key: str) -> dict[str, int]:
    row = await pool.fetchrow(
        "SELECT id, project_id FROM planning.features WHERE feature_key = $1",
        uuid.UUID(feature_key),
    )
    if row is None:
        raise ValueError(f"Feature not found: {feature_key}")
    return {"feature_id": row["id"], "project_id": row["project_id"]}


async def resolve_task_id(pool: asyncpg.Pool, task_key: str) -> int:
    row = await pool.fetchrow(
        "SELECT id FROM planning.tasks WHERE task_key = $1",
        uuid.UUID(task_key),
    )
    if row is None:
        raise ValueError(f"Task not found: {task_key}")
    return row["id"]


async def create_project(
    pool: asyncpg.Pool,
    project_status_id: int,
    name: str,
    description: str | None = None,
    repository_keys: list[str] | None = None,
) -> dict[str, Any]:
    project_key = uuid.uuid4()
    row = await pool.fetchrow(
        """
        INSERT INTO planning.projects (project_key, name, description, project_status_id)
        VALUES ($1, $2, $3, $4)
        RETURNING id, project_key
        """,
        project_key,
        name,
        description,
        project_status_id,
    )
    repo_ids = await resolve_repository_ids(pool, repository_keys or [])
    for repo_id in repo_ids:
        await pool.execute(
            """
            INSERT INTO planning.project_repositories (project_id, repository_id)
            VALUES ($1, $2)
            ON CONFLICT (project_id, repository_id) DO NOTHING
            """,
            row["id"],
            repo_id,
        )
    return {"project_id": row["id"], "project_key": str(row["project_key"]), "repository_count": len(repo_ids)}


async def create_feature(
    pool: asyncpg.Pool,
    project_id: int,
    feature_status_id: int,
    priority_id: int,
    title: str,
    description: str | None = None,
    repository_keys: list[str] | None = None,
) -> dict[str, Any]:
    if not repository_keys:
        raise ValueError("create_feature requires at least one repository_key")
    feature_key = uuid.uuid4()
    repo_ids = await resolve_repository_ids(pool, repository_keys)
    for repo_id in repo_ids:
        await ensure_project_has_repository(pool, project_id, repo_id)
    row = await pool.fetchrow(
        """
        INSERT INTO planning.features
            (feature_key, project_id, title, description, feature_status_id, priority_id)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, feature_key
        """,
        feature_key,
        project_id,
        title,
        description,
        feature_status_id,
        priority_id,
    )
    for repo_id in repo_ids:
        await pool.execute(
            """
            INSERT INTO planning.feature_repositories (feature_id, repository_id)
            VALUES ($1, $2)
            ON CONFLICT (feature_id, repository_id) DO NOTHING
            """,
            row["id"],
            repo_id,
        )
    return {"feature_id": row["id"], "feature_key": str(row["feature_key"]), "repository_count": len(repo_ids)}


async def create_task(
    pool: asyncpg.Pool,
    project_id: int,
    repository_id: int,
    feature_id: int | None,
    task_status_id: int,
    priority_id: int,
    title: str,
    description: str | None = None,
) -> dict[str, Any]:
    await ensure_project_has_repository(pool, project_id, repository_id)
    if feature_id is not None:
        await ensure_feature_has_repository(pool, feature_id, repository_id)
    task_key = uuid.uuid4()
    row = await pool.fetchrow(
        """
        INSERT INTO planning.tasks
            (task_key, project_id, repository_id, feature_id, title, description, task_status_id, priority_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, task_key
        """,
        task_key,
        project_id,
        repository_id,
        feature_id,
        title,
        description,
        task_status_id,
        priority_id,
    )
    return {"task_id": row["id"], "task_key": str(row["task_key"]), "repository_id": repository_id}


async def link_task_to_workflow_run(
    pool: asyncpg.Pool,
    task_id: int,
    workflow_run_uuid: str,
    relation_type: str,
) -> dict[str, Any]:
    run_row = await pool.fetchrow(
        "SELECT id FROM ops.workflow_runs WHERE run_id = $1",
        uuid.UUID(workflow_run_uuid),
    )
    if run_row is None:
        raise ValueError(f"Workflow run not found: {workflow_run_uuid}")
    await pool.execute(
        """
        INSERT INTO planning.task_workflow_runs (task_id, workflow_run_id, relation_type)
        VALUES ($1, $2, $3)
        ON CONFLICT (task_id, workflow_run_id, relation_type) DO NOTHING
        """,
        task_id,
        run_row["id"],
        relation_type,
    )
    return {"task_id": task_id, "workflow_run_id": run_row["id"], "relation_type": relation_type}


async def list_projects(
    pool: asyncpg.Pool, project_status_id: int | None = None
) -> list[dict[str, Any]]:
    if project_status_id is not None:
        rows = await pool.fetch(
            """
            SELECT p.project_key, p.name, p.description,
                   rv.internal_code AS status_code,
                   rv.display_name AS status_display_name,
                   p.created_utc, p.updated_utc,
                   COUNT(DISTINCT pr.repository_id) AS repository_count
            FROM planning.projects p
            JOIN core.reference_values rv ON rv.id = p.project_status_id
            LEFT JOIN planning.project_repositories pr ON pr.project_id = p.id
            WHERE p.project_status_id = $1
            GROUP BY p.id, rv.id
            ORDER BY p.created_utc DESC
            """,
            project_status_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT p.project_key, p.name, p.description,
                   rv.internal_code AS status_code,
                   rv.display_name AS status_display_name,
                   p.created_utc, p.updated_utc,
                   COUNT(DISTINCT pr.repository_id) AS repository_count
            FROM planning.projects p
            JOIN core.reference_values rv ON rv.id = p.project_status_id
            LEFT JOIN planning.project_repositories pr ON pr.project_id = p.id
            GROUP BY p.id, rv.id
            ORDER BY p.created_utc DESC
            """
        )
    return [
        {
            "project_key": str(r["project_key"]),
            "name": r["name"],
            "description": r["description"],
            "status_code": r["status_code"],
            "status_display_name": r["status_display_name"],
            "repository_count": r["repository_count"],
            "created_utc": r["created_utc"].isoformat() if r["created_utc"] else None,
            "updated_utc": r["updated_utc"].isoformat() if r["updated_utc"] else None,
        }
        for r in rows
    ]


async def list_features(
    pool: asyncpg.Pool,
    project_id: int | None = None,
    repository_key: str | None = None,
    feature_status_id: int | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    args: list[Any] = []
    if project_id is not None:
        args.append(project_id)
        conditions.append(f"f.project_id = ${len(args)}")
    if repository_key is not None:
        args.append(repository_key)
        conditions.append(f"r.repository_key = ${len(args)}")
    if feature_status_id is not None:
        args.append(feature_status_id)
        conditions.append(f"f.feature_status_id = ${len(args)}")
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"""
        SELECT DISTINCT f.feature_key, f.title, f.description,
               p.project_key,
               s.internal_code AS status_code, s.display_name AS status_display_name,
               prio.internal_code AS priority_code, prio.display_name AS priority_display_name,
               f.created_utc, f.updated_utc
        FROM planning.features f
        JOIN planning.projects p ON p.id = f.project_id
        JOIN core.reference_values s ON s.id = f.feature_status_id
        JOIN core.reference_values prio ON prio.id = f.priority_id
        LEFT JOIN planning.feature_repositories fr ON fr.feature_id = f.id
        LEFT JOIN catalog.repositories r ON r.id = fr.repository_id
        {where_sql}
        ORDER BY f.created_utc DESC
        """,
        *args,
    )
    return [
        {
            "feature_key": str(r["feature_key"]),
            "project_key": str(r["project_key"]),
            "title": r["title"],
            "description": r["description"],
            "status_code": r["status_code"],
            "status_display_name": r["status_display_name"],
            "priority_code": r["priority_code"],
            "priority_display_name": r["priority_display_name"],
            "created_utc": r["created_utc"].isoformat() if r["created_utc"] else None,
            "updated_utc": r["updated_utc"].isoformat() if r["updated_utc"] else None,
        }
        for r in rows
    ]


async def list_tasks(
    pool: asyncpg.Pool,
    project_id: int | None = None,
    feature_id: int | None = None,
    repository_key: str | None = None,
    task_status_id: int | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    args: list[Any] = []
    if project_id is not None:
        args.append(project_id)
        conditions.append(f"t.project_id = ${len(args)}")
    if feature_id is not None:
        args.append(feature_id)
        conditions.append(f"t.feature_id = ${len(args)}")
    if repository_key is not None:
        args.append(repository_key)
        conditions.append(f"r.repository_key = ${len(args)}")
    if task_status_id is not None:
        args.append(task_status_id)
        conditions.append(f"t.task_status_id = ${len(args)}")
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"""
        SELECT DISTINCT t.task_key, t.title, t.description,
               proj.project_key,
               repo.repository_key,
               f.feature_key,
               s.internal_code AS status_code, s.display_name AS status_display_name,
               p.internal_code AS priority_code, p.display_name AS priority_display_name,
               t.created_utc, t.updated_utc
        FROM planning.tasks t
        JOIN planning.projects proj ON proj.id = t.project_id
        JOIN catalog.repositories repo ON repo.id = t.repository_id
        LEFT JOIN planning.features f ON f.id = t.feature_id
        JOIN core.reference_values s ON s.id = t.task_status_id
        JOIN core.reference_values p ON p.id = t.priority_id
        LEFT JOIN catalog.repositories r ON r.id = t.repository_id
        {where_sql}
        ORDER BY t.created_utc DESC
        """,
        *args,
    )
    return [
        {
            "task_key": str(r["task_key"]),
            "project_key": str(r["project_key"]),
            "repository_key": r["repository_key"],
            "feature_key": str(r["feature_key"]) if r["feature_key"] else None,
            "title": r["title"],
            "description": r["description"],
            "status_code": r["status_code"],
            "status_display_name": r["status_display_name"],
            "priority_code": r["priority_code"],
            "priority_display_name": r["priority_display_name"],
            "created_utc": r["created_utc"].isoformat() if r["created_utc"] else None,
            "updated_utc": r["updated_utc"].isoformat() if r["updated_utc"] else None,
        }
        for r in rows
    ]


async def get_backlog(
    pool: asyncpg.Pool,
    project_id: int | None = None,
    repository_key: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    feature_conditions = ["s.internal_code IN ('FEAT_IDEA', 'FEAT_BACKLOG', 'FEAT_PLANNED')"]
    task_conditions = ["s.internal_code IN ('TASK_TODO', 'TASK_READY', 'TASK_BLOCKED')"]
    feature_args: list[Any] = []
    task_args: list[Any] = []
    if project_id is not None:
        feature_args.append(project_id)
        task_args.append(project_id)
        feature_conditions.append(f"f.project_id = ${len(feature_args)}")
        task_conditions.append(f"f.project_id = ${len(task_args)}")
    if repository_key is not None:
        feature_args.append(repository_key)
        task_args.append(repository_key)
        feature_conditions.append(f"r.repository_key = ${len(feature_args)}")
        task_conditions.append(f"r.repository_key = ${len(task_args)}")

    feature_rows = await pool.fetch(
        f"""
        SELECT DISTINCT f.feature_key, f.title, s.internal_code AS status_code,
               p.internal_code AS priority_code, f.created_utc
        FROM planning.features f
        JOIN core.reference_values s ON s.id = f.feature_status_id
        JOIN core.reference_values p ON p.id = f.priority_id
        LEFT JOIN planning.feature_repositories fr ON fr.feature_id = f.id
        LEFT JOIN catalog.repositories r ON r.id = fr.repository_id
        WHERE {' AND '.join(feature_conditions)}
        ORDER BY p.sort_order DESC, f.created_utc DESC
        LIMIT {limit}
        """,
        *feature_args,
    )
    task_rows = await pool.fetch(
        f"""
        SELECT DISTINCT t.task_key, t.title, s.internal_code AS status_code,
               p.internal_code AS priority_code, t.created_utc
        FROM planning.tasks t
        JOIN planning.projects proj ON proj.id = t.project_id
        LEFT JOIN planning.features f ON f.id = t.feature_id
        JOIN core.reference_values s ON s.id = t.task_status_id
        JOIN core.reference_values p ON p.id = t.priority_id
        LEFT JOIN catalog.repositories r ON r.id = t.repository_id
        WHERE {' AND '.join(task_conditions)}
        ORDER BY p.sort_order DESC, t.created_utc DESC
        LIMIT {limit}
        """,
        *task_args,
    )
    return {
        "features": [
            {
                "feature_key": str(r["feature_key"]),
                "title": r["title"],
                "status_code": r["status_code"],
                "priority_code": r["priority_code"],
                "created_utc": r["created_utc"].isoformat() if r["created_utc"] else None,
            }
            for r in feature_rows
        ],
        "tasks": [
            {
                "task_key": str(r["task_key"]),
                "title": r["title"],
                "status_code": r["status_code"],
                "priority_code": r["priority_code"],
                "created_utc": r["created_utc"].isoformat() if r["created_utc"] else None,
            }
            for r in task_rows
        ],
    }
