from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from typing import Any

import asyncpg


class PlanningValidationError(ValueError):
    """Canonical, typed validation failure crossing the planning boundary."""

    def __init__(self, error_code: str, message: str, *, field: str | None = None,
                 references: list[str] | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.field = field
        self.references = sorted(references or [])


@asynccontextmanager
async def _transaction_connection(pool: Any, connection: Any | None = None):
    if connection is not None:
        yield connection
        return
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn


async def resolve_repository_ids(pool: asyncpg.Pool, repository_keys: list[str]) -> list[int]:
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
        raise PlanningValidationError("REPOSITORY_NOT_FOUND", f"Repositories not found: {', '.join(missing)}", field="related_repository_keys", references=missing)
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


async def resolve_project_id_by_external(pool: asyncpg.Pool, external_system: str, external_id: str) -> int:
    row = await pool.fetchrow(
        """
        SELECT p.id
        FROM planning.project_external_links pel
        JOIN planning.projects p ON p.id = pel.project_id
        WHERE pel.external_system = $1 AND pel.external_id = $2
        """,
        external_system,
        external_id,
    )
    if row is None:
        raise ValueError(f"Project external reference not found: {external_system}:{external_id}")
    return row["id"]


async def resolve_feature_id(pool: asyncpg.Pool, feature_key: str) -> int:
    row = await pool.fetchrow(
        "SELECT id FROM planning.features WHERE feature_key = $1",
        uuid.UUID(feature_key),
    )
    if row is None:
        raise ValueError(f"Feature not found: {feature_key}")
    return row["id"]


async def resolve_feature_context_by_external(
    pool: asyncpg.Pool, external_system: str, external_id: str
) -> dict[str, int]:
    row = await pool.fetchrow(
        """
        SELECT f.id, f.project_id
        FROM planning.feature_external_links fel
        JOIN planning.features f ON f.id = fel.feature_id
        WHERE fel.external_system = $1 AND fel.external_id = $2
        """,
        external_system,
        external_id,
    )
    if row is None:
        raise ValueError(f"Feature external reference not found: {external_system}:{external_id}")
    return {"feature_id": row["id"], "project_id": row["project_id"]}


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
        raise PlanningValidationError("TASK_NOT_FOUND", f"Task not found: {task_key}", field="task_key")
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


async def create_external_link(
    pool: asyncpg.Pool,
    table_name: str,
    owner_column: str,
    owner_id: int,
    external_system: str,
    external_object_type: str,
    external_id: str,
    external_parent_id: str | None = None,
    external_url: str | None = None,
) -> dict[str, Any]:
    row = await pool.fetchrow(
        f"""
        INSERT INTO {table_name}
            ({owner_column}, external_system, external_object_type, external_id, external_parent_id, external_url)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT ({owner_column}, external_system, external_object_type) DO UPDATE SET
            external_id = EXCLUDED.external_id,
            external_parent_id = EXCLUDED.external_parent_id,
            external_url = EXCLUDED.external_url,
            updated_utc = NOW()
        RETURNING id, external_system, external_object_type, external_id
        """,
        owner_id,
        external_system,
        external_object_type,
        external_id,
        external_parent_id,
        external_url,
    )
    return {
        "link_id": row["id"],
        "external_system": row["external_system"],
        "external_object_type": row["external_object_type"],
        "external_id": row["external_id"],
    }


async def add_repository_to_project(
    pool: asyncpg.Pool,
    project_id: int,
    repository_id: int,
) -> None:
    await pool.execute(
        """
        INSERT INTO planning.project_repositories (project_id, repository_id)
        VALUES ($1, $2)
        ON CONFLICT (project_id, repository_id) DO NOTHING
        """,
        project_id,
        repository_id,
    )


async def list_project_repositories(
    pool: asyncpg.Pool,
    project_id: int,
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT r.repository_key, r.name,
               COUNT(DISTINCT f.id) FILTER (WHERE fr.repository_id = r.id) AS feature_count,
               COUNT(DISTINCT t.id) FILTER (WHERE t.repository_id = r.id) AS task_count
        FROM planning.project_repositories pr
        JOIN catalog.repositories r ON r.id = pr.repository_id
        LEFT JOIN planning.features f ON f.project_id = pr.project_id
        LEFT JOIN planning.feature_repositories fr ON fr.feature_id = f.id
        LEFT JOIN planning.tasks t ON t.project_id = pr.project_id
        WHERE pr.project_id = $1
        GROUP BY r.id
        ORDER BY r.name
        """,
        project_id,
    )
    return [
        {
            "repository_key": r["repository_key"],
            "name": r["name"],
            "feature_count": r["feature_count"],
            "task_count": r["task_count"],
        }
        for r in rows
    ]


async def remove_repository_from_project(
    pool: asyncpg.Pool,
    project_id: int,
    repository_id: int,
) -> dict[str, int]:
    feature_count = await pool.fetchval(
        """
        SELECT COUNT(*)
        FROM planning.features f
        JOIN planning.feature_repositories fr ON fr.feature_id = f.id
        WHERE f.project_id = $1 AND fr.repository_id = $2
        """,
        project_id,
        repository_id,
    )
    task_count = await pool.fetchval(
        """
        SELECT COUNT(*)
        FROM planning.tasks
        WHERE project_id = $1 AND repository_id = $2
        """,
        project_id,
        repository_id,
    )
    if feature_count or task_count:
        raise ValueError(
            f"Repository cannot be removed from project because {feature_count} features "
            f"and {task_count} tasks still reference it"
        )
    await pool.execute(
        """
        DELETE FROM planning.project_repositories
        WHERE project_id = $1 AND repository_id = $2
        """,
        project_id,
        repository_id,
    )
    return {"feature_count": feature_count, "task_count": task_count}


async def add_repository_to_feature(
    pool: asyncpg.Pool,
    feature_id: int,
    repository_id: int,
) -> None:
    await pool.execute(
        """
        INSERT INTO planning.feature_repositories (feature_id, repository_id)
        VALUES ($1, $2)
        ON CONFLICT (feature_id, repository_id) DO NOTHING
        """,
        feature_id,
        repository_id,
    )


async def list_feature_repositories(
    pool: asyncpg.Pool,
    feature_id: int,
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT r.repository_key, r.name,
               COUNT(DISTINCT t.id) FILTER (WHERE t.repository_id = r.id) AS task_count
        FROM planning.feature_repositories fr
        JOIN catalog.repositories r ON r.id = fr.repository_id
        LEFT JOIN planning.tasks t ON t.feature_id = fr.feature_id
        WHERE fr.feature_id = $1
        GROUP BY r.id
        ORDER BY r.name
        """,
        feature_id,
    )
    return [
        {
            "repository_key": r["repository_key"],
            "name": r["name"],
            "task_count": r["task_count"],
        }
        for r in rows
    ]


async def remove_repository_from_feature(
    pool: asyncpg.Pool,
    feature_id: int,
    repository_id: int,
) -> dict[str, int]:
    task_count = await pool.fetchval(
        """
        SELECT COUNT(*)
        FROM planning.tasks
        WHERE feature_id = $1 AND repository_id = $2
        """,
        feature_id,
        repository_id,
    )
    if task_count:
        raise ValueError(f"Repository cannot be removed from feature because {task_count} tasks still reference it")
    await pool.execute(
        """
        DELETE FROM planning.feature_repositories
        WHERE feature_id = $1 AND repository_id = $2
        """,
        feature_id,
        repository_id,
    )
    return {"task_count": task_count}


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
    task_type: str | None = None,
    parent_task_id: int | None = None,
    feature_task_id: int | None = None,
    graph_node_id: str | None = None,
    depends_on_task_ids: list[int] | None = None,
    blocked_by_task_ids: list[int] | None = None,
    coordination_task_ids: list[int] | None = None,
    related_repository_ids: list[int] | None = None,
    is_runnable: bool = True,
    task_metadata: dict[str, Any] | None = None,
    legacy_task_id: int | None = None,
    connection: Any | None = None,
) -> dict[str, Any]:
    await ensure_project_has_repository(pool, project_id, repository_id)
    if feature_id is not None:
        await ensure_feature_has_repository(pool, feature_id, repository_id)
    task_key = uuid.uuid4()
    if graph_node_id is not None:
        if connection is not None:
            return await _create_graph_task_on_connection(
                connection, task_key=task_key, project_id=project_id, repository_id=repository_id,
                feature_id=feature_id, task_status_id=task_status_id, priority_id=priority_id,
                title=title, description=description, task_type=task_type,
                parent_task_id=parent_task_id, feature_task_id=feature_task_id,
                graph_node_id=graph_node_id, depends_on_task_ids=depends_on_task_ids or [],
                blocked_by_task_ids=blocked_by_task_ids or [],
                coordination_task_ids=coordination_task_ids or [],
                related_repository_ids=related_repository_ids or [], is_runnable=is_runnable,
                task_metadata=task_metadata or {}, legacy_task_id=legacy_task_id,
            )
        async with pool.acquire() as conn:
            async with conn.transaction():
                return await _create_graph_task_on_connection(
                    conn, task_key=task_key, project_id=project_id, repository_id=repository_id,
                    feature_id=feature_id, task_status_id=task_status_id, priority_id=priority_id,
                    title=title, description=description, task_type=task_type,
                    parent_task_id=parent_task_id, feature_task_id=feature_task_id,
                    graph_node_id=graph_node_id, depends_on_task_ids=depends_on_task_ids or [],
                    blocked_by_task_ids=blocked_by_task_ids or [],
                    coordination_task_ids=coordination_task_ids or [],
                    related_repository_ids=related_repository_ids or [], is_runnable=is_runnable,
                    task_metadata=task_metadata or {}, legacy_task_id=legacy_task_id,
                )
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


async def _create_graph_task_on_connection(conn: Any, **values: Any) -> dict[str, Any]:
    # Validate every graph edge against the owning project before any write.
    task_ids = [
        *values["depends_on_task_ids"], *values["blocked_by_task_ids"],
        *values["coordination_task_ids"],
        *([values["parent_task_id"]] if values["parent_task_id"] is not None else []),
        *([values["feature_task_id"]] if values["feature_task_id"] is not None else []),
    ]
    if task_ids:
        rows = await conn.fetch(
            "SELECT id, project_id FROM planning.tasks WHERE id=ANY($1::bigint[])", task_ids
        )
        found = {row["id"]: row for row in rows}
        if len(found) != len(set(task_ids)):
            raise ValueError("task reference not found")
        if any(row["project_id"] != values["project_id"] for row in rows):
            raise ValueError("task reference belongs to a different project")
    if values["related_repository_ids"]:
        rows = await conn.fetch(
            "SELECT id FROM catalog.repositories WHERE id=ANY($1::bigint[])",
            values["related_repository_ids"],
        )
        if len(rows) != len(set(values["related_repository_ids"])):
            raise ValueError("related repository not found")
        ownership = await conn.fetch(
            "SELECT repository_id FROM planning.project_repositories WHERE project_id=$1 AND repository_id=ANY($2::bigint[])",
            values["project_id"], values["related_repository_ids"],
        )
        if len(ownership) != len(set(values["related_repository_ids"])):
            raise ValueError("related repository is not linked to the project")
        if values["feature_id"] is not None:
            feature_ownership = await conn.fetch(
                "SELECT repository_id FROM planning.feature_repositories WHERE feature_id=$1 AND repository_id=ANY($2::bigint[])",
                values["feature_id"], values["related_repository_ids"],
            )
            if len(feature_ownership) != len(set(values["related_repository_ids"])):
                raise ValueError("related repository is not linked to the feature")
    existing = await conn.fetchrow(
        "SELECT id, task_key FROM planning.tasks WHERE project_id=$1 AND feature_id=$2 "
        "AND graph_node_id=$3 FOR UPDATE",
        values["project_id"], values["feature_id"], values["graph_node_id"],
    )
    if existing is None and values["legacy_task_id"] is not None:
        existing = await conn.fetchrow(
            "SELECT id, task_key FROM planning.tasks WHERE id=$1 AND project_id=$2 AND feature_id=$3 "
            "AND repository_id=$4 AND graph_node_id IS NULL FOR UPDATE",
            values["legacy_task_id"], values["project_id"], values["feature_id"], values["repository_id"],
        )
        if existing is None:
            raise ValueError("legacy task identity mismatch")
    if existing is None:
        existing = await conn.fetchrow(
            """INSERT INTO planning.tasks
               (task_key,project_id,repository_id,feature_id,title,description,task_status_id,priority_id,
                task_type,parent_task_id,feature_task_id,graph_node_id,is_runnable,task_metadata)
               VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb)
               ON CONFLICT (project_id,feature_id,graph_node_id) WHERE graph_node_id IS NOT NULL
               DO NOTHING RETURNING id,task_key""",
            values["task_key"], values["project_id"], values["repository_id"], values["feature_id"],
            values["title"], values["description"], values["task_status_id"], values["priority_id"],
            values["task_type"], values["parent_task_id"], values["feature_task_id"],
            values["graph_node_id"], values["is_runnable"],
            json.dumps(values["task_metadata"], sort_keys=True, separators=(",", ":")),
        )
        if existing is None:
            existing = await conn.fetchrow(
                "SELECT id,task_key FROM planning.tasks WHERE project_id=$1 AND feature_id=$2 "
                "AND graph_node_id=$3 FOR UPDATE",
                values["project_id"], values["feature_id"], values["graph_node_id"],
            )
    await conn.execute(
        """UPDATE planning.tasks SET repository_id=$2,title=$3,description=$4,task_type=$5,
           parent_task_id=$6,feature_task_id=$7,graph_node_id=$8,is_runnable=$9,
           task_metadata=$10::jsonb,updated_utc=NOW() WHERE id=$1""",
        existing["id"], values["repository_id"], values["title"], values["description"], values["task_type"],
        values["parent_task_id"], values["feature_task_id"], values["graph_node_id"], values["is_runnable"],
        json.dumps(values["task_metadata"], sort_keys=True, separators=(",", ":")),
    )
    await _replace_task_relations(
        conn, existing["id"], values["depends_on_task_ids"], values["blocked_by_task_ids"],
        values["coordination_task_ids"], values["related_repository_ids"],
    )
    return {"task_id": existing["id"], "task_key": str(existing["task_key"]),
            "repository_id": values["repository_id"]}


async def _replace_task_relations(
    conn: Any,
    task_id: int,
    depends_on: list[int],
    blocked_by: list[int],
    coordination: list[int],
    repositories: list[int],
) -> None:
    specs = (
        ("planning.task_dependencies", "depends_on_task_id", depends_on),
        ("planning.task_blockers", "blocked_by_task_id", blocked_by),
        ("planning.task_coordination", "coordination_task_id", coordination),
        ("planning.task_related_repositories", "repository_id", repositories),
    )
    for table, column, values in specs:
        await conn.execute(f"DELETE FROM {table} WHERE task_id=$1", task_id)
        if values:
            await conn.executemany(
                f"INSERT INTO {table} (task_id, {column}) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                [(task_id, value) for value in values],
            )


async def link_task_to_workflow_run(
    pool: asyncpg.Pool,
    task_id: int,
    workflow_run_uuid: str,
    relation_type: str,
) -> dict[str, Any]:
    task_row = await pool.fetchrow(
        "SELECT repository_id FROM planning.tasks WHERE id = $1",
        task_id,
    )
    if task_row is None:
        raise ValueError(f"Task not found: {task_id}")
    run_row = await pool.fetchrow(
        "SELECT id, repository_id FROM ops.workflow_runs WHERE run_id = $1",
        uuid.UUID(workflow_run_uuid),
    )
    if run_row is None:
        raise ValueError(f"Workflow run not found: {workflow_run_uuid}")
    if run_row["repository_id"] != task_row["repository_id"]:
        raise ValueError("Task repository does not match workflow run repository")
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


async def list_projects(pool: asyncpg.Pool, project_status_id: int | None = None) -> list[dict[str, Any]]:
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
    graph_node_id: str | None = None,
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
    if graph_node_id is not None:
        args.append(graph_node_id)
        conditions.append(f"t.graph_node_id = ${len(args)}")
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"""
        SELECT DISTINCT t.task_key, t.title, t.description,
               proj.project_key,
               repo.repository_key,
               f.feature_key,
               s.internal_code AS status_code, s.display_name AS status_display_name,
               p.internal_code AS priority_code, p.display_name AS priority_display_name,
               t.task_type, pt.task_key AS parent_task_key, ft.task_key AS feature_task_key,
               t.graph_node_id, t.is_runnable, t.task_metadata,
               COALESCE((SELECT array_agg(dt.task_key::text ORDER BY dt.task_key::text)
                         FROM planning.task_dependencies d JOIN planning.tasks dt ON dt.id=d.depends_on_task_id
                         WHERE d.task_id=t.id), ARRAY[]::text[]) AS depends_on_task_keys,
               COALESCE((SELECT array_agg(bt.task_key::text ORDER BY bt.task_key::text)
                         FROM planning.task_blockers b JOIN planning.tasks bt ON bt.id=b.blocked_by_task_id
                         WHERE b.task_id=t.id), ARRAY[]::text[]) AS blocked_by_task_keys,
               COALESCE((SELECT array_agg(ct.task_key::text ORDER BY ct.task_key::text)
                         FROM planning.task_coordination c JOIN planning.tasks ct ON ct.id=c.coordination_task_id
                         WHERE c.task_id=t.id), ARRAY[]::text[]) AS coordination_task_keys,
               COALESCE((SELECT array_agg(rr.repository_key ORDER BY rr.repository_key)
                         FROM planning.task_related_repositories tr
                         JOIN catalog.repositories rr ON rr.id=tr.repository_id
                         WHERE tr.task_id=t.id), ARRAY[]::text[]) AS related_repository_keys,
               t.created_utc, t.updated_utc
        FROM planning.tasks t
        JOIN planning.projects proj ON proj.id = t.project_id
        JOIN catalog.repositories repo ON repo.id = t.repository_id
        LEFT JOIN planning.features f ON f.id = t.feature_id
        JOIN core.reference_values s ON s.id = t.task_status_id
        JOIN core.reference_values p ON p.id = t.priority_id
        LEFT JOIN planning.tasks pt ON pt.id = t.parent_task_id
        LEFT JOIN planning.tasks ft ON ft.id = t.feature_task_id
        LEFT JOIN catalog.repositories r ON r.id = t.repository_id
        {where_sql}
        ORDER BY t.task_key ASC
        """,
        *args,
    )
    result = []
    for r in rows:
        metadata = r["task_metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if not isinstance(metadata, dict):
            raise ValueError("task_metadata must be a JSON object")
        result.append({
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
            "task_type": r["task_type"],
            "parent_task_key": str(r["parent_task_key"]) if r["parent_task_key"] else None,
            "feature_task_key": str(r["feature_task_key"]) if r["feature_task_key"] else None,
            "graph_node_id": r["graph_node_id"],
            "depends_on_task_keys": list(r["depends_on_task_keys"] or []),
            "blocked_by_task_keys": list(r["blocked_by_task_keys"] or []),
            "coordination_task_keys": list(r["coordination_task_keys"] or []),
            "related_repository_keys": list(r["related_repository_keys"] or []),
            "is_runnable": bool(r["is_runnable"]),
            "task_metadata": metadata,
            "created_utc": r["created_utc"].isoformat() if r["created_utc"] else None,
            "updated_utc": r["updated_utc"].isoformat() if r["updated_utc"] else None,
        })
    return result


async def update_task(pool: asyncpg.Pool, task_key: str, patch: dict[str, Any], connection: Any | None = None) -> int:
    """Apply a graph-owned patch atomically and return the internal task id."""
    async with _transaction_connection(pool, connection) as conn:
            row = await conn.fetchrow(
                "SELECT id, project_id, feature_id FROM planning.tasks WHERE task_key=$1 FOR UPDATE",
                uuid.UUID(task_key),
            )
            if row is None:
                raise ValueError(f"Task not found: {task_key}")
            task_id, project_id, feature_id = row["id"], row["project_id"], row["feature_id"]

            async def task_ids(keys: list[str], field: str) -> list[int]:
                if not keys:
                    return []
                rows = await conn.fetch(
                    "SELECT id, task_key, project_id FROM planning.tasks WHERE task_key=ANY($1::uuid[])",
                    [uuid.UUID(key) for key in keys],
                )
                found = {str(item["task_key"]): item for item in rows}
                missing = sorted(set(keys) - set(found))
                if missing:
                    raise ValueError(f"{field} not found: {', '.join(missing)}")
                if any(item["project_id"] != project_id for item in rows):
                    raise ValueError(f"{field} contains cross-project task")
                if task_key in keys:
                    raise ValueError(f"{field} cannot reference the task itself")
                return [found[key]["id"] for key in keys]

            scalar_columns = {
                "title": "title", "description": "description", "task_type": "task_type",
                "is_runnable": "is_runnable", "task_metadata": "task_metadata",
            }
            assignments: list[str] = []
            values: list[Any] = []
            for field, column in scalar_columns.items():
                if field in patch:
                    value = patch[field]
                    if field == "task_metadata":
                        value = json.dumps(value, sort_keys=True, separators=(",", ":"))
                        assignments.append(f"{column}=${len(values)+1}::jsonb")
                    else:
                        assignments.append(f"{column}=${len(values)+1}")
                    values.append(value)

            for field, column in (("parent_task_key", "parent_task_id"),
                                  ("feature_task_key", "feature_task_id")):
                if field in patch:
                    key = patch[field]
                    resolved = None if key is None else (await task_ids([key], field))[0]
                    assignments.append(f"{column}=${len(values)+1}")
                    values.append(resolved)
            if assignments:
                values.append(task_id)
                await conn.execute(
                    f"UPDATE planning.tasks SET {', '.join(assignments)}, updated_utc=NOW() "
                    f"WHERE id=${len(values)}",
                    *values,
                )

            current = {}
            for field in ("depends_on_task_keys", "blocked_by_task_keys", "coordination_task_keys"):
                if field in patch:
                    current[field] = await task_ids(list(patch[field]), field)
            repo_ids: list[int] | None = None
            if "related_repository_keys" in patch:
                keys = list(patch["related_repository_keys"])
                rows = await conn.fetch(
                    "SELECT id, repository_key FROM catalog.repositories WHERE repository_key=ANY($1::text[])",
                    keys,
                )
                found = {r["repository_key"]: r["id"] for r in rows}
                missing = sorted(set(keys) - set(found))
                if missing:
                    raise ValueError(f"related_repository_keys not found: {', '.join(missing)}")
                repo_ids = [found[key] for key in keys]
                ownership = await conn.fetch(
                    "SELECT repository_id FROM planning.project_repositories "
                    "WHERE project_id=$1 AND repository_id=ANY($2::bigint[])",
                    project_id, repo_ids,
                )
                if len(ownership) != len(set(repo_ids)):
                    raise ValueError("related repository is not linked to the project")
                if feature_id is not None:
                    feature_ownership = await conn.fetch(
                        "SELECT repository_id FROM planning.feature_repositories "
                        "WHERE feature_id=$1 AND repository_id=ANY($2::bigint[])",
                        feature_id, repo_ids,
                    )
                    if len(feature_ownership) != len(set(repo_ids)):
                        raise ValueError("related repository is not linked to the project")

            relation_specs = (
                ("depends_on_task_keys", "planning.task_dependencies", "depends_on_task_id"),
                ("blocked_by_task_keys", "planning.task_blockers", "blocked_by_task_id"),
                ("coordination_task_keys", "planning.task_coordination", "coordination_task_id"),
            )
            for field, table, column in relation_specs:
                if field in current:
                    await conn.execute(f"DELETE FROM {table} WHERE task_id=$1", task_id)
                    if current[field]:
                        await conn.executemany(
                            f"INSERT INTO {table}(task_id,{column}) VALUES($1,$2)",
                            [(task_id, value) for value in current[field]],
                        )
            if repo_ids is not None:
                await conn.execute("DELETE FROM planning.task_related_repositories WHERE task_id=$1", task_id)
                if repo_ids:
                    await conn.executemany(
                        "INSERT INTO planning.task_related_repositories(task_id,repository_id) VALUES($1,$2)",
                        [(task_id, value) for value in repo_ids],
                    )
            return task_id


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
        WHERE {" AND ".join(feature_conditions)}
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
        WHERE {" AND ".join(task_conditions)}
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
