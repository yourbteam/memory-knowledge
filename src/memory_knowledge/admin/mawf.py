from __future__ import annotations

import uuid
import json
from typing import Any

import asyncpg


DEFAULT_PROJECT_STATUS = "active"
DEFAULT_REPOSITORY_STATUS = "active"
DEFAULT_TASK_STATUS = "active"
DEFAULT_PRIORITY = "PRIO_MEDIUM"
DEFAULT_USER_ROLE = "employee"
DEFAULT_USER_STATUS = "active"
DEFAULT_ARTIFACT_PERSIST_STATUS = "local_only"

MAWF_WORKFLOW_RUN_NAMESPACE = uuid.UUID("c9134234-7022-4f5d-96fd-65f5eaa4ddf6")
MAWF_TO_WORKFLOW_RUN_STATUS = {
    "queued": "RUN_PENDING",
    "pending": "RUN_PENDING",
    "submitted": "RUN_SUBMITTED",
    "running": "RUN_RUNNING",
    "completed": "RUN_SUCCESS",
    "success": "RUN_SUCCESS",
    "partial": "RUN_PARTIAL",
    "failed": "RUN_ERROR",
    "error": "RUN_ERROR",
    "cancelled": "RUN_CANCELLED",
    "canceled": "RUN_CANCELLED",
}
WORKFLOW_RUN_TO_MAWF_STATUS = {
    "RUN_PENDING": "queued",
    "RUN_SUBMITTED": "submitted",
    "RUN_RUNNING": "running",
    "RUN_SUCCESS": "completed",
    "RUN_PARTIAL": "partial",
    "RUN_ERROR": "failed",
    "RUN_CANCELLED": "cancelled",
}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _dict(row: Any | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _workflow_run_uuid(workflow_run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(workflow_run_id)
    except ValueError:
        return uuid.uuid5(MAWF_WORKFLOW_RUN_NAMESPACE, workflow_run_id)


def _workflow_status_code(status_code: str | None) -> str:
    if not status_code:
        return "RUN_PENDING"
    return MAWF_TO_WORKFLOW_RUN_STATUS.get(status_code.lower(), status_code)


def _mawf_workflow_status(internal_code: str) -> str:
    return WORKFLOW_RUN_TO_MAWF_STATUS.get(internal_code, internal_code.lower())


async def resolve_reference_value(
    pool: asyncpg.Pool, type_code: str, value_code: str
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT rv.id, rv.internal_code, rv.mawf_code, rv.display_name,
               rv.description, rv.sort_order, rv.is_active, rv.is_terminal
        FROM core.reference_values rv
        JOIN core.reference_types rt ON rt.id = rv.reference_type_id
        WHERE rt.internal_code = $1
          AND (rv.mawf_code = $2 OR rv.internal_code = $2)
        ORDER BY CASE WHEN rv.mawf_code = $2 THEN 0 ELSE 1 END
        LIMIT 1
        """,
        type_code,
        value_code,
    )
    if row is None:
        raise ValueError(f"Invalid {type_code} value: {value_code}")
    return dict(row)


async def _reference_id(pool: asyncpg.Pool, type_code: str, value_code: str) -> int:
    return (await resolve_reference_value(pool, type_code, value_code))["id"]


def _catalog_value(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "catalog_type_id": row["reference_type_id"],
        "catalog_type_code": row["type_code"],
        "code": row["mawf_code"] or row["internal_code"],
        "internal_code": row["internal_code"],
        "description": row["description"],
        "sort_order": row["sort_order"],
        "is_active": row["is_active"],
    }


async def list_catalog_types(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT id, internal_code AS code, description
        FROM core.reference_types
        WHERE internal_code IN (
            'USER_ROLE', 'USER_STATUS', 'PROJECT_STATUS', 'REPOSITORY_STATUS',
            'TASK_STATUS', 'ARTIFACT_ROLE', 'ARTIFACT_PERSIST_STATUS'
        )
        ORDER BY id
        """
    )
    return [dict(row) for row in rows]


async def list_catalog_values(
    pool: asyncpg.Pool, catalog_type_code: str | None = None, include_inactive: bool = False
) -> list[dict[str, Any]]:
    clauses: list[str] = [
        """
        rt.internal_code IN (
            'USER_ROLE', 'USER_STATUS', 'PROJECT_STATUS', 'REPOSITORY_STATUS',
            'TASK_STATUS', 'ARTIFACT_ROLE', 'ARTIFACT_PERSIST_STATUS'
        )
        """
    ]
    args: list[Any] = []
    if catalog_type_code:
        args.append(catalog_type_code)
        clauses.append(f"rt.internal_code = ${len(args)}")
    if not include_inactive:
        clauses.append("rv.is_active = TRUE")
    rows = await pool.fetch(
        f"""
        SELECT rv.id, rv.reference_type_id, rt.internal_code AS type_code,
               rv.internal_code, rv.mawf_code, rv.description,
               rv.sort_order, rv.is_active
        FROM core.reference_values rv
        JOIN core.reference_types rt ON rt.id = rv.reference_type_id
        WHERE {' AND '.join(clauses)}
        ORDER BY rt.id, rv.sort_order, rv.id
        """,
        *args,
    )
    return [_catalog_value(row) for row in rows]


async def upsert_catalog_value(
    pool: asyncpg.Pool,
    catalog_type_code: str,
    code: str,
    description: str | None = None,
    sort_order: int = 0,
    is_active: bool = True,
) -> dict[str, Any]:
    type_row = await pool.fetchrow(
        "SELECT id FROM core.reference_types WHERE internal_code = $1",
        catalog_type_code,
    )
    if type_row is None:
        raise ValueError(f"Catalog type not found: {catalog_type_code}")
    internal_code = f"{catalog_type_code}_{code.upper()}"
    row = await pool.fetchrow(
        """
        INSERT INTO core.reference_values (
            reference_type_id, internal_code, mawf_code, display_name,
            description, sort_order, is_active
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (reference_type_id, mawf_code) WHERE mawf_code IS NOT NULL
        DO UPDATE SET
            description = EXCLUDED.description,
            sort_order = EXCLUDED.sort_order,
            is_active = EXCLUDED.is_active,
            updated_utc = NOW()
        RETURNING id, reference_type_id, internal_code, mawf_code, description,
                  sort_order, is_active
        """,
        type_row["id"],
        internal_code,
        code,
        code.replace("_", " ").title(),
        description,
        sort_order,
        is_active,
    )
    data = dict(row)
    data["type_code"] = catalog_type_code
    return _catalog_value(data)


async def deactivate_catalog_value(
    pool: asyncpg.Pool, catalog_type_code: str, code: str
) -> dict[str, Any]:
    value = await resolve_reference_value(pool, catalog_type_code, code)
    type_row = await pool.fetchrow(
        "SELECT id FROM core.reference_types WHERE internal_code = $1",
        catalog_type_code,
    )
    await pool.execute(
        "UPDATE core.reference_values SET is_active = FALSE, updated_utc = NOW() WHERE id = $1",
        value["id"],
    )
    value["is_active"] = False
    value["reference_type_id"] = type_row["id"] if type_row else None
    value["type_code"] = catalog_type_code
    return _catalog_value(value)


def _user(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "role_catalog_value_id": row["role_id"],
        "role_code": row["role_code"],
        "status_catalog_value_id": row["status_id"],
        "status_code": row["status_code"],
        "created_at": _iso(row["created_utc"]),
        "updated_at": _iso(row["updated_utc"]),
    }


async def upsert_user(
    pool: asyncpg.Pool,
    email: str,
    user_id: str | None = None,
    display_name: str | None = None,
    role_code: str = DEFAULT_USER_ROLE,
    status_code: str = DEFAULT_USER_STATUS,
) -> dict[str, Any]:
    role_id = await _reference_id(pool, "USER_ROLE", role_code)
    status_id = await _reference_id(pool, "USER_STATUS", status_code)
    row = await pool.fetchrow(
        """
        INSERT INTO core.users (id, email, display_name, role_id, status_id)
        VALUES (COALESCE($1::uuid, gen_random_uuid()), $2, $3, $4, $5)
        ON CONFLICT (email) DO UPDATE SET
            display_name = COALESCE(EXCLUDED.display_name, core.users.display_name),
            role_id = EXCLUDED.role_id,
            status_id = EXCLUDED.status_id,
            updated_utc = NOW()
        RETURNING id, email, display_name, role_id, status_id, created_utc, updated_utc,
            (SELECT COALESCE(mawf_code, internal_code) FROM core.reference_values WHERE id = role_id) AS role_code,
            (SELECT COALESCE(mawf_code, internal_code) FROM core.reference_values WHERE id = status_id) AS status_code
        """,
        uuid.UUID(user_id) if user_id else None,
        email,
        display_name,
        role_id,
        status_id,
    )
    return _user(row)


async def get_user(pool: asyncpg.Pool, user_id: str | None = None, email: str | None = None) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT u.id, u.email, u.display_name, u.role_id, u.status_id,
               u.created_utc, u.updated_utc,
               COALESCE(role.mawf_code, role.internal_code) AS role_code,
               COALESCE(status.mawf_code, status.internal_code) AS status_code
        FROM core.users u
        JOIN core.reference_values role ON role.id = u.role_id
        JOIN core.reference_values status ON status.id = u.status_id
        WHERE ($1::uuid IS NULL OR u.id = $1::uuid)
          AND ($2::text IS NULL OR u.email = $2)
        """,
        uuid.UUID(user_id) if user_id else None,
        email,
    )
    if row is None:
        raise ValueError("User not found")
    return _user(row)


async def list_users(pool: asyncpg.Pool, status_code: str | None = None) -> list[dict[str, Any]]:
    status_id = await _reference_id(pool, "USER_STATUS", status_code) if status_code else None
    rows = await pool.fetch(
        """
        SELECT u.id, u.email, u.display_name, u.role_id, u.status_id,
               u.created_utc, u.updated_utc,
               COALESCE(role.mawf_code, role.internal_code) AS role_code,
               COALESCE(status.mawf_code, status.internal_code) AS status_code
        FROM core.users u
        JOIN core.reference_values role ON role.id = u.role_id
        JOIN core.reference_values status ON status.id = u.status_id
        WHERE ($1::bigint IS NULL OR u.status_id = $1)
        ORDER BY u.updated_utc DESC, u.email
        """,
        status_id,
    )
    return [_user(row) for row in rows]


async def deactivate_user(pool: asyncpg.Pool, user_id: str) -> dict[str, Any]:
    status_id = await _reference_id(pool, "USER_STATUS", "inactive")
    row = await pool.fetchrow(
        """
        UPDATE core.users
        SET status_id = $2, updated_utc = NOW()
        WHERE id = $1
        RETURNING id, email, display_name, role_id, status_id, created_utc, updated_utc,
            (SELECT COALESCE(mawf_code, internal_code) FROM core.reference_values WHERE id = role_id) AS role_code,
            (SELECT COALESCE(mawf_code, internal_code) FROM core.reference_values WHERE id = status_id) AS status_code
        """,
        uuid.UUID(user_id),
        status_id,
    )
    if row is None:
        raise ValueError("User not found")
    return _user(row)


def _project(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["project_key"]),
        "project_key": row["mawf_project_key"],
        "display_name": row["name"],
        "status_catalog_value_id": row["project_status_id"],
        "status_code": row["status_code"],
        "created_at": _iso(row["created_utc"]),
        "updated_at": _iso(row["updated_utc"]),
    }


async def upsert_project(
    pool: asyncpg.Pool,
    project_key: str,
    display_name: str,
    project_id: str | None = None,
    status_code: str = DEFAULT_PROJECT_STATUS,
) -> dict[str, Any]:
    status_id = await _reference_id(pool, "PROJECT_STATUS", status_code)
    row = await pool.fetchrow(
        """
        INSERT INTO planning.projects (project_key, mawf_project_key, name, project_status_id)
        VALUES (COALESCE($1::uuid, gen_random_uuid()), $2, $3, $4)
        ON CONFLICT (mawf_project_key) DO UPDATE SET
            name = EXCLUDED.name,
            project_status_id = EXCLUDED.project_status_id,
            updated_utc = NOW()
        RETURNING project_key, mawf_project_key, name, project_status_id, created_utc, updated_utc,
            (SELECT COALESCE(mawf_code, internal_code) FROM core.reference_values WHERE id = project_status_id) AS status_code
        """,
        uuid.UUID(project_id) if project_id else None,
        project_key,
        display_name,
        status_id,
    )
    return _project(row)


async def _project_row(pool: asyncpg.Pool, project_id: str | None = None, project_key: str | None = None) -> Any:
    return await pool.fetchrow(
        """
        SELECT p.id, p.project_key, p.mawf_project_key, p.name, p.project_status_id,
               p.created_utc, p.updated_utc,
               COALESCE(rv.mawf_code, rv.internal_code) AS status_code
        FROM planning.projects p
        JOIN core.reference_values rv ON rv.id = p.project_status_id
        WHERE ($1::uuid IS NULL OR p.project_key = $1::uuid)
          AND ($2::text IS NULL OR p.mawf_project_key = $2)
        """,
        uuid.UUID(project_id) if project_id else None,
        project_key,
    )


async def get_project(pool: asyncpg.Pool, project_id: str | None = None, project_key: str | None = None) -> dict[str, Any]:
    row = await _project_row(pool, project_id, project_key)
    if row is None:
        raise ValueError("Project not found")
    return _project(row)


async def list_projects(pool: asyncpg.Pool, status_code: str | None = None) -> list[dict[str, Any]]:
    status_id = await _reference_id(pool, "PROJECT_STATUS", status_code) if status_code else None
    rows = await pool.fetch(
        """
        SELECT p.project_key, p.mawf_project_key, p.name, p.project_status_id,
               p.created_utc, p.updated_utc,
               COALESCE(rv.mawf_code, rv.internal_code) AS status_code
        FROM planning.projects p
        JOIN core.reference_values rv ON rv.id = p.project_status_id
        WHERE p.mawf_project_key IS NOT NULL
          AND ($1::bigint IS NULL OR p.project_status_id = $1)
        ORDER BY p.updated_utc DESC
        """,
        status_id,
    )
    return [_project(row) for row in rows]


async def archive_project(pool: asyncpg.Pool, project_id: str) -> dict[str, Any]:
    status_id = await _reference_id(pool, "PROJECT_STATUS", "inactive")
    row = await pool.fetchrow(
        """
        UPDATE planning.projects
        SET project_status_id = $2, updated_utc = NOW()
        WHERE project_key = $1::uuid
        RETURNING project_key, mawf_project_key, name, project_status_id, created_utc, updated_utc,
            (SELECT COALESCE(mawf_code, internal_code) FROM core.reference_values WHERE id = project_status_id) AS status_code
        """,
        uuid.UUID(project_id),
        status_id,
    )
    if row is None:
        raise ValueError("Project not found")
    return _project(row)


def _repository(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["mawf_repository_id"]),
        "project_id": str(row["project_key"]) if row["project_key"] else None,
        "repository_key": row["repository_key"],
        "provider": row["provider"],
        "owner": row["owner"],
        "repo_name": row["repo_name"],
        "remote_url": row["origin_url"],
        "status_catalog_value_id": row["status_id"],
        "status_code": row["status_code"],
        "created_at": _iso(row["created_utc"]),
        "updated_at": _iso(row["updated_utc"]),
    }


async def upsert_repository(
    pool: asyncpg.Pool,
    repository_key: str,
    repository_id: str | None = None,
    project_id: str | None = None,
    provider: str | None = None,
    owner: str | None = None,
    repo_name: str | None = None,
    remote_url: str | None = None,
    status_code: str = DEFAULT_REPOSITORY_STATUS,
) -> dict[str, Any]:
    status_id = await _reference_id(pool, "REPOSITORY_STATUS", status_code)
    display_name = repo_name or repository_key
    row = await pool.fetchrow(
        """
        INSERT INTO catalog.repositories (
            mawf_repository_id, repository_key, name, origin_url,
            provider, owner, repo_name, status_id
        )
        VALUES (COALESCE($1::uuid, gen_random_uuid()), $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (repository_key) DO UPDATE SET
            name = EXCLUDED.name,
            origin_url = EXCLUDED.origin_url,
            provider = EXCLUDED.provider,
            owner = EXCLUDED.owner,
            repo_name = EXCLUDED.repo_name,
            status_id = EXCLUDED.status_id,
            updated_utc = NOW()
        RETURNING id, mawf_repository_id
        """,
        uuid.UUID(repository_id) if repository_id else None,
        repository_key,
        display_name,
        remote_url,
        provider,
        owner,
        repo_name,
        status_id,
    )
    if project_id:
        project_row = await _project_row(pool, project_id=project_id)
        if project_row is None:
            raise ValueError("Project not found")
        await pool.execute(
            """
            INSERT INTO planning.project_repositories (project_id, repository_id)
            VALUES ($1, $2)
            ON CONFLICT (project_id, repository_id) DO NOTHING
            """,
            project_row["id"],
            row["id"],
        )
    return await get_repository(pool, repository_id=str(row["mawf_repository_id"]))


async def get_repository(
    pool: asyncpg.Pool,
    repository_id: str | None = None,
    repository_key: str | None = None,
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT r.mawf_repository_id, p.project_key, r.repository_key, r.provider,
               r.owner, r.repo_name, r.origin_url, r.status_id,
               r.created_utc, r.updated_utc,
               COALESCE(rv.mawf_code, rv.internal_code) AS status_code
        FROM catalog.repositories r
        JOIN core.reference_values rv ON rv.id = r.status_id
        LEFT JOIN planning.project_repositories pr ON pr.repository_id = r.id
        LEFT JOIN planning.projects p ON p.id = pr.project_id
        WHERE ($1::uuid IS NULL OR r.mawf_repository_id = $1::uuid)
          AND ($2::text IS NULL OR r.repository_key = $2)
        ORDER BY p.created_utc NULLS LAST
        LIMIT 1
        """,
        uuid.UUID(repository_id) if repository_id else None,
        repository_key,
    )
    if row is None:
        raise ValueError("Repository not found")
    return _repository(row)


async def list_repositories(pool: asyncpg.Pool, status_code: str | None = None) -> list[dict[str, Any]]:
    status_id = await _reference_id(pool, "REPOSITORY_STATUS", status_code) if status_code else None
    rows = await pool.fetch(
        """
        SELECT r.mawf_repository_id, p.project_key, r.repository_key, r.provider,
               r.owner, r.repo_name, r.origin_url, r.status_id,
               r.created_utc, r.updated_utc,
               COALESCE(rv.mawf_code, rv.internal_code) AS status_code
        FROM catalog.repositories r
        JOIN core.reference_values rv ON rv.id = r.status_id
        LEFT JOIN planning.project_repositories pr ON pr.repository_id = r.id
        LEFT JOIN planning.projects p ON p.id = pr.project_id
        WHERE ($1::bigint IS NULL OR r.status_id = $1)
        ORDER BY r.updated_utc DESC
        """,
        status_id,
    )
    return [_repository(row) for row in rows]


async def deactivate_repository(pool: asyncpg.Pool, repository_id: str) -> dict[str, Any]:
    status_id = await _reference_id(pool, "REPOSITORY_STATUS", "inactive")
    row = await pool.fetchrow(
        """
        UPDATE catalog.repositories
        SET status_id = $2, updated_utc = NOW()
        WHERE mawf_repository_id = $1::uuid
        RETURNING mawf_repository_id
        """,
        uuid.UUID(repository_id),
        status_id,
    )
    if row is None:
        raise ValueError("Repository not found")
    return await get_repository(pool, repository_id=repository_id)


def _prompt(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "normalized_hash": row["normalized_hash"],
        "original_prompt_ref": row["original_prompt_ref"],
        "normalized_prompt_ref": row["normalized_prompt_ref"],
        "created_by_user_id": str(row["created_by_user_id"]),
        "supersedes_prompt_id": str(row["supersedes_prompt_id"]) if row["supersedes_prompt_id"] else None,
        "correction_note": row["correction_note"],
        "created_at": _iso(row["created_utc"]),
    }


async def create_prompt(
    pool: asyncpg.Pool,
    normalized_hash: str,
    original_prompt_ref: str,
    normalized_prompt_ref: str,
    created_by_user_id: str,
    prompt_id: str | None = None,
    supersedes_prompt_id: str | None = None,
    correction_note: str | None = None,
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO ops.mawf_prompts (
            id, normalized_hash, original_prompt_ref, normalized_prompt_ref,
            created_by_user_id, supersedes_prompt_id, correction_note
        )
        VALUES (
            COALESCE($1::uuid, gen_random_uuid()), $2, $3, $4,
            $5::uuid, $6::uuid, $7
        )
        ON CONFLICT (normalized_hash) DO UPDATE SET
            normalized_hash = EXCLUDED.normalized_hash
        RETURNING id, normalized_hash, original_prompt_ref, normalized_prompt_ref,
                  created_by_user_id, supersedes_prompt_id, correction_note, created_utc
        """,
        uuid.UUID(prompt_id) if prompt_id else None,
        normalized_hash,
        original_prompt_ref,
        normalized_prompt_ref,
        uuid.UUID(created_by_user_id),
        uuid.UUID(supersedes_prompt_id) if supersedes_prompt_id else None,
        correction_note,
    )
    return _prompt(row)


async def get_prompt(pool: asyncpg.Pool, prompt_id: str) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT id, normalized_hash, original_prompt_ref, normalized_prompt_ref,
               created_by_user_id, supersedes_prompt_id, correction_note, created_utc
        FROM ops.mawf_prompts
        WHERE id = $1::uuid
        """,
        uuid.UUID(prompt_id),
    )
    if row is None:
        raise ValueError("Prompt not found")
    return _prompt(row)


async def get_prompt_by_hash(pool: asyncpg.Pool, normalized_hash: str) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT id, normalized_hash, original_prompt_ref, normalized_prompt_ref,
               created_by_user_id, supersedes_prompt_id, correction_note, created_utc
        FROM ops.mawf_prompts
        WHERE normalized_hash = $1
        """,
        normalized_hash,
    )
    if row is None:
        raise ValueError("Prompt not found")
    return _prompt(row)


async def list_prompts_by_user(pool: asyncpg.Pool, user_id: str) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT id, normalized_hash, original_prompt_ref, normalized_prompt_ref,
               created_by_user_id, supersedes_prompt_id, correction_note, created_utc
        FROM ops.mawf_prompts
        WHERE created_by_user_id = $1::uuid
        ORDER BY created_utc DESC
        """,
        uuid.UUID(user_id),
    )
    return [_prompt(row) for row in rows]


async def supersede_prompt_ref(
    pool: asyncpg.Pool,
    prompt_id: str,
    normalized_hash: str,
    original_prompt_ref: str,
    normalized_prompt_ref: str,
    correction_note: str | None = None,
) -> dict[str, Any]:
    existing = await get_prompt(pool, prompt_id)
    return await create_prompt(
        pool,
        normalized_hash=normalized_hash,
        original_prompt_ref=original_prompt_ref,
        normalized_prompt_ref=normalized_prompt_ref,
        created_by_user_id=existing["created_by_user_id"],
        supersedes_prompt_id=prompt_id,
        correction_note=correction_note,
    )


def _task(row: Any) -> dict[str, Any]:
    return {
        "id": row["mawf_task_id"],
        "owner_user_id": str(row["owner_user_id"]) if row["owner_user_id"] else None,
        "project_id": str(row["project_key"]) if row["project_key"] else None,
        "repository_id": str(row["mawf_repository_id"]) if row["mawf_repository_id"] else None,
        "prompt_id": str(row["prompt_id"]) if row["prompt_id"] else None,
        "title": row["title"],
        "status_catalog_value_id": row["task_status_id"],
        "status_code": row["status_code"],
        "task_ledger_ref": row["task_ledger_ref"],
        "created_at": _iso(row["created_utc"]),
        "updated_at": _iso(row["updated_utc"]),
    }


async def _priority_id(pool: asyncpg.Pool) -> int:
    return await _reference_id(pool, "PRIORITY", DEFAULT_PRIORITY)


async def _internal_project_id(pool: asyncpg.Pool, project_id: str) -> int:
    row = await _project_row(pool, project_id=project_id)
    if row is None:
        raise ValueError("Project not found")
    return row["id"]


async def _internal_repository_id(pool: asyncpg.Pool, repository_id: str) -> int:
    row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE mawf_repository_id = $1::uuid",
        uuid.UUID(repository_id),
    )
    if row is None:
        raise ValueError("Repository not found")
    return row["id"]


async def _ensure_project_repository_link(
    pool: asyncpg.Pool, project_id: int, repository_id: int
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


async def upsert_task(
    pool: asyncpg.Pool,
    task_id: str,
    owner_user_id: str,
    project_id: str,
    repository_id: str,
    prompt_id: str,
    title: str,
    task_ledger_ref: str,
    status_code: str = DEFAULT_TASK_STATUS,
) -> dict[str, Any]:
    status_id = await _reference_id(pool, "TASK_STATUS", status_code)
    priority_id = await _priority_id(pool)
    internal_project_id = await _internal_project_id(pool, project_id)
    internal_repository_id = await _internal_repository_id(pool, repository_id)
    await _ensure_project_repository_link(pool, internal_project_id, internal_repository_id)
    row = await pool.fetchrow(
        """
        UPDATE planning.tasks
        SET owner_user_id = $2::uuid,
            project_id = $3,
            repository_id = $4,
            prompt_id = $5::uuid,
            title = $6,
            task_status_id = $7,
            priority_id = $8,
            task_ledger_ref = $9,
            updated_utc = NOW()
        WHERE mawf_task_id = $1
        RETURNING id
        """,
        task_id,
        uuid.UUID(owner_user_id),
        internal_project_id,
        internal_repository_id,
        uuid.UUID(prompt_id),
        title,
        status_id,
        priority_id,
        task_ledger_ref,
    )
    if row is None:
        await pool.fetchrow(
            """
            INSERT INTO planning.tasks (
                task_key, project_id, repository_id, feature_id, title,
                description, task_status_id, priority_id, mawf_task_id,
                owner_user_id, prompt_id, task_ledger_ref
            )
            VALUES (
                gen_random_uuid(), $1, $2, NULL, $3, NULL, $4, $5,
                $6, $7::uuid, $8::uuid, $9
            )
            RETURNING id
            """,
            internal_project_id,
            internal_repository_id,
            title,
            status_id,
            priority_id,
            task_id,
            uuid.UUID(owner_user_id),
            uuid.UUID(prompt_id),
            task_ledger_ref,
        )
    return await get_task(pool, task_id)


async def get_task(pool: asyncpg.Pool, task_id: str) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT t.mawf_task_id, t.owner_user_id, p.project_key,
               r.mawf_repository_id, t.prompt_id, t.title, t.task_status_id,
               t.task_ledger_ref, t.created_utc, t.updated_utc,
               COALESCE(rv.mawf_code, rv.internal_code) AS status_code
        FROM planning.tasks t
        JOIN planning.projects p ON p.id = t.project_id
        JOIN catalog.repositories r ON r.id = t.repository_id
        JOIN core.reference_values rv ON rv.id = t.task_status_id
        WHERE t.mawf_task_id = $1
        """,
        task_id,
    )
    if row is None:
        raise ValueError("Task not found")
    return _task(row)


async def list_tasks(
    pool: asyncpg.Pool,
    owner_user_id: str | None = None,
    project_id: str | None = None,
    repository_id: str | None = None,
    status_code: str | None = None,
) -> list[dict[str, Any]]:
    status_id = await _reference_id(pool, "TASK_STATUS", status_code) if status_code else None
    rows = await pool.fetch(
        """
        SELECT t.mawf_task_id, t.owner_user_id, p.project_key,
               r.mawf_repository_id, t.prompt_id, t.title, t.task_status_id,
               t.task_ledger_ref, t.created_utc, t.updated_utc,
               COALESCE(rv.mawf_code, rv.internal_code) AS status_code
        FROM planning.tasks t
        JOIN planning.projects p ON p.id = t.project_id
        JOIN catalog.repositories r ON r.id = t.repository_id
        JOIN core.reference_values rv ON rv.id = t.task_status_id
        WHERE t.mawf_task_id IS NOT NULL
          AND ($1::uuid IS NULL OR t.owner_user_id = $1::uuid)
          AND ($2::uuid IS NULL OR p.project_key = $2::uuid)
          AND ($3::uuid IS NULL OR r.mawf_repository_id = $3::uuid)
          AND ($4::bigint IS NULL OR t.task_status_id = $4)
        ORDER BY t.updated_utc DESC
        """,
        uuid.UUID(owner_user_id) if owner_user_id else None,
        uuid.UUID(project_id) if project_id else None,
        uuid.UUID(repository_id) if repository_id else None,
        status_id,
    )
    return [_task(row) for row in rows]


async def set_task_status(pool: asyncpg.Pool, task_id: str, status_code: str) -> dict[str, Any]:
    status_id = await _reference_id(pool, "TASK_STATUS", status_code)
    row = await pool.fetchrow(
        """
        UPDATE planning.tasks
        SET task_status_id = $2, updated_utc = NOW()
        WHERE mawf_task_id = $1
        RETURNING id
        """,
        task_id,
        status_id,
    )
    if row is None:
        raise ValueError("Task not found")
    return await get_task(pool, task_id)


def _workflow_run(row: Any) -> dict[str, Any]:
    context = row["context_json"] or {}
    if isinstance(context, str):
        context = json.loads(context)
    workflow_run_id = context.get("mawf_workflow_run_id") or str(row["run_id"])
    relation_type = row.get("relation_type", "implements") if hasattr(row, "get") else row["relation_type"]
    relation_type = relation_type or "implements"
    return {
        "workflow_run_id": workflow_run_id,
        "canonical_run_id": str(row["run_id"]),
        "task_id": row["mawf_task_id"],
        "workflow_name": row["workflow_name"],
        "attempt": context.get("mawf_attempt"),
        "status_code": _mawf_workflow_status(row["status_code"]),
        "internal_status_code": row["status_code"],
        "status_display_name": row["status_display_name"],
        "is_terminal": row["is_terminal"],
        "workflow_ledger_ref": context.get("workflow_ledger_ref"),
        "workflow_state_ref": context.get("workflow_state_ref"),
        "actor_email": row["actor_email"],
        "current_phase": row["current_phase"],
        "iteration_count": row["iteration_count"],
        "started_at": _iso(row["started_utc"]),
        "completed_at": _iso(row["completed_utc"]),
        "error_text": row["error_text"],
        "relation_type": relation_type,
    }


async def upsert_workflow_run(
    pool: asyncpg.Pool,
    workflow_run_id: str,
    task_id: str,
    workflow_name: str,
    attempt: int = 1,
    status_code: str = "queued",
    workflow_ledger_ref: str | None = None,
    workflow_state_ref: str | None = None,
    current_phase: str | None = None,
    iteration_count: int | None = None,
    error_text: str | None = None,
    relation_type: str = "implements",
) -> dict[str, Any]:
    task_row = await pool.fetchrow(
        """
        SELECT t.id, t.mawf_task_id, t.repository_id, t.title, u.email AS actor_email
        FROM planning.tasks t
        LEFT JOIN core.users u ON u.id = t.owner_user_id
        WHERE t.mawf_task_id = $1
        """,
        task_id,
    )
    if task_row is None:
        raise ValueError(f"Task not found: {task_id}")

    status = await resolve_reference_value(
        pool, "WORKFLOW_RUN_STATUS", _workflow_status_code(status_code)
    )
    context_json = {
        "mawf_workflow_run_id": workflow_run_id,
        "mawf_attempt": attempt,
        "workflow_ledger_ref": workflow_ledger_ref,
        "workflow_state_ref": workflow_state_ref,
    }
    run_uuid = _workflow_run_uuid(workflow_run_id)
    row = await pool.fetchrow(
        """
        INSERT INTO ops.workflow_runs (
            run_id, repository_id, workflow_name, task_description, status,
            status_id, actor_email, current_phase, iteration_count, context_json,
            error_text, completed_utc
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, COALESCE($9, 0), $10::jsonb,
            $11, CASE WHEN $12 THEN NOW() ELSE NULL END
        )
        ON CONFLICT (run_id) DO UPDATE SET
            repository_id = EXCLUDED.repository_id,
            workflow_name = EXCLUDED.workflow_name,
            task_description = COALESCE(EXCLUDED.task_description, ops.workflow_runs.task_description),
            status = EXCLUDED.status,
            status_id = EXCLUDED.status_id,
            actor_email = COALESCE(EXCLUDED.actor_email, ops.workflow_runs.actor_email),
            current_phase = COALESCE(EXCLUDED.current_phase, ops.workflow_runs.current_phase),
            iteration_count = COALESCE(EXCLUDED.iteration_count, ops.workflow_runs.iteration_count),
            context_json = COALESCE(ops.workflow_runs.context_json, '{}'::jsonb) || EXCLUDED.context_json,
            error_text = COALESCE(EXCLUDED.error_text, ops.workflow_runs.error_text),
            completed_utc = CASE
                WHEN $12 THEN COALESCE(ops.workflow_runs.completed_utc, NOW())
                ELSE ops.workflow_runs.completed_utc
            END
        RETURNING id
        """,
        run_uuid,
        task_row["repository_id"],
        workflow_name,
        task_row["title"],
        _mawf_workflow_status(status["internal_code"]),
        status["id"],
        task_row["actor_email"],
        current_phase,
        iteration_count,
        json.dumps(context_json),
        error_text,
        status["is_terminal"],
    )
    await pool.execute(
        """
        INSERT INTO planning.task_workflow_runs (task_id, workflow_run_id, relation_type)
        VALUES ($1, $2, $3)
        ON CONFLICT (task_id, workflow_run_id, relation_type) DO NOTHING
        """,
        task_row["id"],
        row["id"],
        relation_type,
    )
    return await get_workflow_run(pool, workflow_run_id)


async def get_workflow_run(pool: asyncpg.Pool, workflow_run_id: str) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT wr.run_id, t.mawf_task_id, wr.workflow_name, wr.context_json,
               rv.internal_code AS status_code, rv.display_name AS status_display_name,
               rv.is_terminal, wr.actor_email, wr.current_phase, wr.iteration_count,
               wr.started_utc, wr.completed_utc, wr.error_text, twr.relation_type
        FROM ops.workflow_runs wr
        JOIN core.reference_values rv ON rv.id = wr.status_id
        LEFT JOIN planning.task_workflow_runs twr ON twr.workflow_run_id = wr.id
        LEFT JOIN planning.tasks t ON t.id = twr.task_id
        WHERE wr.run_id = $1
        ORDER BY twr.created_utc DESC NULLS LAST
        LIMIT 1
        """,
        _workflow_run_uuid(workflow_run_id),
    )
    if row is None:
        raise ValueError(f"Workflow run not found: {workflow_run_id}")
    return _workflow_run(row)


async def list_workflow_runs(pool: asyncpg.Pool, task_id: str) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT wr.run_id, t.mawf_task_id, wr.workflow_name, wr.context_json,
               rv.internal_code AS status_code, rv.display_name AS status_display_name,
               rv.is_terminal, wr.actor_email, wr.current_phase, wr.iteration_count,
               wr.started_utc, wr.completed_utc, wr.error_text, twr.relation_type
        FROM planning.tasks t
        JOIN planning.task_workflow_runs twr ON twr.task_id = t.id
        JOIN ops.workflow_runs wr ON wr.id = twr.workflow_run_id
        JOIN core.reference_values rv ON rv.id = wr.status_id
        WHERE t.mawf_task_id = $1
        ORDER BY wr.started_utc DESC
        """,
        task_id,
    )
    return [_workflow_run(row) for row in rows]


def _artifact_ref(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "task_id": row["mawf_task_id"],
        "role_catalog_value_id": row["role_id"],
        "role_code": row["role_code"],
        "artifact_path": row["artifact_path"],
        "content_hash": row["content_hash"],
        "persist_status_catalog_value_id": row["persist_status_id"],
        "persist_status_code": row["persist_status_code"],
        "created_at": _iso(row["created_utc"]),
        "updated_at": _iso(row["updated_utc"]),
    }


async def upsert_artifact_ref(
    pool: asyncpg.Pool,
    task_id: str,
    role_code: str,
    artifact_path: str,
    content_hash: str | None = None,
    persist_status_code: str = DEFAULT_ARTIFACT_PERSIST_STATUS,
    artifact_ref_id: str | None = None,
) -> dict[str, Any]:
    role_id = await _reference_id(pool, "ARTIFACT_ROLE", role_code)
    persist_status_id = await _reference_id(pool, "ARTIFACT_PERSIST_STATUS", persist_status_code)
    row = await pool.fetchrow(
        """
        INSERT INTO planning.mawf_artifact_refs (
            id, mawf_task_id, role_id, artifact_path, content_hash, persist_status_id
        )
        VALUES (COALESCE($1::uuid, gen_random_uuid()), $2, $3, $4, $5, $6)
        ON CONFLICT (mawf_task_id, role_id) DO UPDATE SET
            artifact_path = EXCLUDED.artifact_path,
            content_hash = EXCLUDED.content_hash,
            persist_status_id = EXCLUDED.persist_status_id,
            updated_utc = NOW()
        RETURNING id
        """,
        uuid.UUID(artifact_ref_id) if artifact_ref_id else None,
        task_id,
        role_id,
        artifact_path,
        content_hash,
        persist_status_id,
    )
    return await get_artifact_ref(pool, artifact_ref_id=str(row["id"]))


async def get_artifact_ref(
    pool: asyncpg.Pool,
    artifact_ref_id: str | None = None,
    task_id: str | None = None,
    role_code: str | None = None,
) -> dict[str, Any]:
    role_id = await _reference_id(pool, "ARTIFACT_ROLE", role_code) if role_code else None
    row = await pool.fetchrow(
        """
        SELECT ar.id, ar.mawf_task_id, ar.role_id, ar.artifact_path,
               ar.content_hash, ar.persist_status_id, ar.created_utc, ar.updated_utc,
               COALESCE(role.mawf_code, role.internal_code) AS role_code,
               COALESCE(ps.mawf_code, ps.internal_code) AS persist_status_code
        FROM planning.mawf_artifact_refs ar
        JOIN core.reference_values role ON role.id = ar.role_id
        JOIN core.reference_values ps ON ps.id = ar.persist_status_id
        WHERE ($1::uuid IS NULL OR ar.id = $1::uuid)
          AND ($2::text IS NULL OR ar.mawf_task_id = $2)
          AND ($3::bigint IS NULL OR ar.role_id = $3)
        """,
        uuid.UUID(artifact_ref_id) if artifact_ref_id else None,
        task_id,
        role_id,
    )
    if row is None:
        raise ValueError("Artifact ref not found")
    return _artifact_ref(row)


async def list_artifact_refs(pool: asyncpg.Pool, task_id: str) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT ar.id, ar.mawf_task_id, ar.role_id, ar.artifact_path,
               ar.content_hash, ar.persist_status_id, ar.created_utc, ar.updated_utc,
               COALESCE(role.mawf_code, role.internal_code) AS role_code,
               COALESCE(ps.mawf_code, ps.internal_code) AS persist_status_code
        FROM planning.mawf_artifact_refs ar
        JOIN core.reference_values role ON role.id = ar.role_id
        JOIN core.reference_values ps ON ps.id = ar.persist_status_id
        WHERE ar.mawf_task_id = $1
        ORDER BY role.sort_order, ar.created_utc
        """,
        task_id,
    )
    return [_artifact_ref(row) for row in rows]


async def set_artifact_persist_status(
    pool: asyncpg.Pool, artifact_ref_id: str, persist_status_code: str
) -> dict[str, Any]:
    persist_status_id = await _reference_id(pool, "ARTIFACT_PERSIST_STATUS", persist_status_code)
    row = await pool.fetchrow(
        """
        UPDATE planning.mawf_artifact_refs
        SET persist_status_id = $2, updated_utc = NOW()
        WHERE id = $1::uuid
        RETURNING id
        """,
        uuid.UUID(artifact_ref_id),
        persist_status_id,
    )
    if row is None:
        raise ValueError("Artifact ref not found")
    return await get_artifact_ref(pool, artifact_ref_id=artifact_ref_id)


async def get_task_memory_bundle(pool: asyncpg.Pool, task_id: str) -> dict[str, Any]:
    task = await get_task(pool, task_id)
    owner = await get_user(pool, user_id=task["owner_user_id"]) if task["owner_user_id"] else None
    project = await get_project(pool, project_id=task["project_id"]) if task["project_id"] else None
    repository = await get_repository(pool, repository_id=task["repository_id"]) if task["repository_id"] else None
    prompt = await get_prompt(pool, task["prompt_id"]) if task["prompt_id"] else None
    artifact_refs = await list_artifact_refs(pool, task_id)
    workflow_runs = await list_workflow_runs(pool, task_id)
    return {
        "task": task,
        "owner": owner,
        "project": project,
        "repository": repository,
        "prompt": prompt,
        "artifact_refs": artifact_refs,
        "workflow_runs": workflow_runs,
        "available_memory_surfaces": [
            "workflow_runs",
            "workflow_artifacts",
            "workflow_phase_states",
            "workflow_validator_results",
            "workflow_findings",
            "triage_memory",
            "actor_adaptation",
        ],
    }
