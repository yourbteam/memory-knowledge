from __future__ import annotations

import json
import uuid
from typing import Any


SESSION_STATUSES = {"active", "finalized", "cancelled", "expired"}
SESSION_MODES = {"full", "quick"}
EVENT_ROLES = {"user", "assistant", "system", "tool"}
DRAFT_STATUSES = {"draft", "verified", "final", "rejected"}
TERMINAL_SESSION_STATUSES = {"finalized", "cancelled", "expired"}


def _key(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _json_arg(value: Any, default: Any) -> str:
    return json.dumps(default if value is None else value)


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _record_to_dict(row: Any | None, json_fields: set[str] | None = None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for field in json_fields or set():
        if field in data:
            data[field] = _json_value(data[field])
    return data


def _validate(value: str, allowed: set[str], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(f"Invalid {field_name}: {value}")


async def create_session(
    pool,
    *,
    mode: str,
    title: str | None,
    actor_email: str | None = None,
    actor_id: str | None = None,
    repository_key: str | None = None,
    project_key: str | None = None,
    feature_key: str | None = None,
    task_key: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    _validate(mode, SESSION_MODES, "mode")
    session_key = _key("intake")
    row = await pool.fetchrow(
        """
        INSERT INTO ops.intake_sessions
            (session_key, status, mode, title, actor_email, actor_id,
             repository_key, project_key, feature_key, task_key, metadata)
        VALUES ($1, 'active', $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
        RETURNING session_key, status, created_utc
        """,
        session_key,
        mode,
        title,
        actor_email,
        actor_id,
        repository_key,
        project_key,
        feature_key,
        task_key,
        _json_arg(metadata, {}),
    )
    return _record_to_dict(row) or {}


async def append_event(
    pool,
    *,
    session_key: str,
    role: str,
    event_type: str,
    content_text: str | None = None,
    content_json: dict | list | None = None,
    attachment_refs: list | None = None,
    source: str | None = "mcp",
    model_provider: str | None = None,
    model_name: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    _validate(role, EVENT_ROLES, "role")
    async with pool.acquire() as conn:
        async with conn.transaction():
            session = await conn.fetchrow(
                """
                SELECT session_key, status
                FROM ops.intake_sessions
                WHERE session_key = $1
                FOR UPDATE
                """,
                session_key,
            )
            if not session:
                raise ValueError(f"Intake session not found: {session_key}")
            if idempotency_key:
                existing = await conn.fetchrow(
                    """
                    SELECT event_key, sequence, session_key
                    FROM ops.intake_events
                    WHERE session_key = $1 AND idempotency_key = $2
                    """,
                    session_key,
                    idempotency_key,
                )
                if existing:
                    data = _record_to_dict(existing) or {}
                    data["idempotent"] = True
                    return data
            if session["status"] != "active":
                raise ValueError(f"Cannot append event to {session['status']} intake session")
            sequence_row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
                FROM ops.intake_events
                WHERE session_key = $1
                """,
                session_key,
            )
            sequence = sequence_row["next_sequence"]
            event_key = _key("evt")
            row = await conn.fetchrow(
                """
                INSERT INTO ops.intake_events
                    (event_key, session_key, sequence, role, event_type, content_text,
                     content_json, attachment_refs, source, model_provider, model_name,
                     idempotency_key, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10, $11, $12, $13::jsonb)
                RETURNING event_key, sequence, session_key
                """,
                event_key,
                session_key,
                sequence,
                role,
                event_type,
                content_text,
                _json_arg(content_json, None),
                _json_arg(attachment_refs, []),
                source,
                model_provider,
                model_name,
                idempotency_key,
                _json_arg(metadata, {}),
            )
            await conn.execute(
                "UPDATE ops.intake_sessions SET updated_utc = NOW() WHERE session_key = $1",
                session_key,
            )
            return _record_to_dict(row) or {}


async def get_session_state(
    pool,
    *,
    session_key: str,
    include_recent_events: bool = True,
    recent_event_limit: int = 10,
    include_latest_draft: bool = True,
    include_asset_refs: bool = True,
) -> dict[str, Any]:
    session = _record_to_dict(
        await pool.fetchrow(
            """
            SELECT session_key, status, mode, title, actor_email, actor_id,
                   repository_key, project_key, feature_key, task_key,
                   final_draft_revision, created_utc, updated_utc, finalized_utc, metadata
            FROM ops.intake_sessions
            WHERE session_key = $1
            """,
            session_key,
        ),
        {"metadata"},
    )
    if session is None:
        raise ValueError(f"Intake session not found: {session_key}")

    distilled_context = _record_to_dict(
        await pool.fetchrow(
            """
            SELECT session_key, revision, updated_from_sequence, distilled_context,
                   source_event_range, updated_utc, metadata
            FROM ops.intake_distilled_context
            WHERE session_key = $1
            """,
            session_key,
        ),
        {"distilled_context", "source_event_range", "metadata"},
    )
    latest_draft = None
    if include_latest_draft:
        latest_draft = _record_to_dict(
            await pool.fetchrow(
                """
                SELECT draft_revision_key, session_key, revision, status, draft_json,
                       draft_markdown, source_distilled_revision, source_event_range,
                       created_utc, metadata
                FROM ops.intake_draft_revisions
                WHERE session_key = $1
                ORDER BY revision DESC
                LIMIT 1
                """,
                session_key,
            ),
            {"draft_json", "source_event_range", "metadata"},
        )

    recent_events: list[dict[str, Any]] = []
    if include_recent_events:
        limit = max(0, min(int(recent_event_limit or 10), 100))
        rows = await pool.fetch(
            """
            SELECT event_key, session_key, sequence, role, event_type, content_text,
                   content_json, attachment_refs, source, model_provider, model_name,
                   created_utc, metadata
            FROM (
                SELECT *
                FROM ops.intake_events
                WHERE session_key = $1
                ORDER BY sequence DESC
                LIMIT $2
            ) recent
            ORDER BY sequence ASC
            """,
            session_key,
            limit,
        )
        recent_events = [
            _record_to_dict(row, {"content_json", "attachment_refs", "metadata"}) or {}
            for row in rows
        ]

    asset_refs: list[dict[str, Any]] = []
    if include_asset_refs:
        rows = await pool.fetch(
            """
            SELECT asset_ref_key, session_key, event_key, asset_type, display_name,
                   uri, mime_type, description, created_utc, metadata
            FROM ops.intake_asset_refs
            WHERE session_key = $1
            ORDER BY created_utc ASC, id ASC
            """,
            session_key,
        )
        asset_refs = [_record_to_dict(row, {"metadata"}) or {} for row in rows]

    link_rows = await pool.fetch(
        """
        SELECT link_key, session_key, run_id, workflow_name, link_type, repository_key,
               project_key, feature_key, task_key, created_utc, metadata
        FROM ops.intake_workflow_links
        WHERE session_key = $1
        ORDER BY created_utc ASC, id ASC
        """,
        session_key,
    )
    workflow_links = [_record_to_dict(row, {"metadata"}) or {} for row in link_rows]
    return {
        "session": session,
        "distilled_context": distilled_context,
        "latest_draft": latest_draft,
        "recent_events": recent_events,
        "asset_refs": asset_refs,
        "workflow_links": workflow_links,
    }


async def update_distilled_context(
    pool,
    *,
    session_key: str,
    expected_revision: int,
    updated_from_sequence: int,
    distilled_context: dict,
    metadata: dict | None = None,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            session = await conn.fetchrow(
                "SELECT session_key FROM ops.intake_sessions WHERE session_key = $1 FOR UPDATE",
                session_key,
            )
            if not session:
                raise ValueError(f"Intake session not found: {session_key}")
            current = await conn.fetchrow(
                """
                SELECT revision, updated_from_sequence
                FROM ops.intake_distilled_context
                WHERE session_key = $1
                FOR UPDATE
                """,
                session_key,
            )
            current_revision = current["revision"] if current else 0
            current_sequence = current["updated_from_sequence"] if current else 0
            if expected_revision != current_revision:
                return {
                    "ok": False,
                    "errorCode": "REVISION_CONFLICT",
                    "error": f"Expected revision {expected_revision} but current revision is {current_revision}",
                    "current_revision": current_revision,
                }
            if updated_from_sequence < current_sequence:
                return {
                    "ok": False,
                    "errorCode": "SEQUENCE_REGRESSION",
                    "error": (
                        f"updated_from_sequence {updated_from_sequence} is older than "
                        f"current sequence {current_sequence}"
                    ),
                    "current_updated_from_sequence": current_sequence,
                }
            next_revision = current_revision + 1
            source_event_range = {"from_sequence": 1, "to_sequence": updated_from_sequence}
            row = await conn.fetchrow(
                """
                INSERT INTO ops.intake_distilled_context
                    (session_key, revision, updated_from_sequence, distilled_context,
                     source_event_range, metadata)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb)
                ON CONFLICT (session_key) DO UPDATE SET
                    revision = EXCLUDED.revision,
                    updated_from_sequence = EXCLUDED.updated_from_sequence,
                    distilled_context = EXCLUDED.distilled_context,
                    source_event_range = EXCLUDED.source_event_range,
                    updated_utc = NOW(),
                    metadata = EXCLUDED.metadata
                RETURNING session_key, revision, updated_from_sequence
                """,
                session_key,
                next_revision,
                updated_from_sequence,
                _json_arg(distilled_context, {}),
                _json_arg(source_event_range, {}),
                _json_arg(metadata, {}),
            )
            await conn.execute(
                "UPDATE ops.intake_sessions SET updated_utc = NOW() WHERE session_key = $1",
                session_key,
            )
            return _record_to_dict(row) or {}


async def save_draft_revision(
    pool,
    *,
    session_key: str,
    status: str,
    draft_json: dict,
    draft_markdown: str | None = None,
    source_distilled_revision: int | None = None,
    source_event_range: dict | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    _validate(status, DRAFT_STATUSES, "draft status")
    async with pool.acquire() as conn:
        async with conn.transaction():
            session = await conn.fetchrow(
                "SELECT session_key FROM ops.intake_sessions WHERE session_key = $1 FOR UPDATE",
                session_key,
            )
            if not session:
                raise ValueError(f"Intake session not found: {session_key}")
            revision_row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(revision), 0) + 1 AS next_revision
                FROM ops.intake_draft_revisions
                WHERE session_key = $1
                """,
                session_key,
            )
            revision = revision_row["next_revision"]
            draft_revision_key = _key("draft_rev")
            row = await conn.fetchrow(
                """
                INSERT INTO ops.intake_draft_revisions
                    (draft_revision_key, session_key, revision, status, draft_json,
                     draft_markdown, source_distilled_revision, source_event_range, metadata)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8::jsonb, $9::jsonb)
                RETURNING draft_revision_key, revision, session_key
                """,
                draft_revision_key,
                session_key,
                revision,
                status,
                _json_arg(draft_json, {}),
                draft_markdown,
                source_distilled_revision,
                _json_arg(source_event_range, {}),
                _json_arg(metadata, {}),
            )
            await conn.execute(
                "UPDATE ops.intake_sessions SET updated_utc = NOW() WHERE session_key = $1",
                session_key,
            )
            return _record_to_dict(row) or {}


async def list_events(
    pool,
    *,
    session_key: str,
    from_sequence: int = 1,
    to_sequence: int | None = None,
    limit: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    row = await pool.fetchrow(
        "SELECT session_key FROM ops.intake_sessions WHERE session_key = $1",
        session_key,
    )
    if not row:
        raise ValueError(f"Intake session not found: {session_key}")
    capped_limit = max(1, min(int(limit or 100), 500))
    rows = await pool.fetch(
        """
        SELECT event_key, session_key, sequence, role, event_type, content_text,
               content_json, attachment_refs, source, model_provider, model_name,
               created_utc, metadata
        FROM ops.intake_events
        WHERE session_key = $1
          AND sequence >= $2
          AND ($3::integer IS NULL OR sequence <= $3::integer)
        ORDER BY sequence ASC
        LIMIT $4
        """,
        session_key,
        from_sequence,
        to_sequence,
        capped_limit,
    )
    return {
        "events": [
            _record_to_dict(row, {"content_json", "attachment_refs", "metadata"}) or {}
            for row in rows
        ]
    }


async def add_asset_ref(
    pool,
    *,
    session_key: str,
    event_key: str,
    asset_type: str,
    display_name: str,
    uri: str,
    mime_type: str | None = None,
    description: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            event = await conn.fetchrow(
                """
                SELECT event_key
                FROM ops.intake_events
                WHERE session_key = $1 AND event_key = $2
                """,
                session_key,
                event_key,
            )
            if not event:
                raise ValueError(f"Intake event not found for session: {event_key}")
            asset_ref_key = _key("asset")
            row = await conn.fetchrow(
                """
                INSERT INTO ops.intake_asset_refs
                    (asset_ref_key, session_key, event_key, asset_type, display_name,
                     uri, mime_type, description, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                RETURNING asset_ref_key
                """,
                asset_ref_key,
                session_key,
                event_key,
                asset_type,
                display_name,
                uri,
                mime_type,
                description,
                _json_arg(metadata, {}),
            )
            await conn.execute(
                "UPDATE ops.intake_sessions SET updated_utc = NOW() WHERE session_key = $1",
                session_key,
            )
            return _record_to_dict(row) or {}


async def finalize_session(
    pool,
    *,
    session_key: str,
    final_draft_revision: int,
    repository_key: str | None = None,
    project_key: str | None = None,
    feature_key: str | None = None,
    task_key: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            session = await conn.fetchrow(
                """
                SELECT session_key, status, final_draft_revision
                FROM ops.intake_sessions
                WHERE session_key = $1
                FOR UPDATE
                """,
                session_key,
            )
            if not session:
                raise ValueError(f"Intake session not found: {session_key}")
            if session["status"] == "finalized":
                if session["final_draft_revision"] == final_draft_revision:
                    row = await conn.fetchrow(
                        """
                        SELECT session_key, status, finalized_utc
                        FROM ops.intake_sessions
                        WHERE session_key = $1
                        """,
                        session_key,
                    )
                    data = _record_to_dict(row) or {}
                    data["idempotent"] = True
                    return data
                return {
                    "ok": False,
                    "errorCode": "FINALIZATION_CONFLICT",
                    "error": (
                        f"Session already finalized with draft revision "
                        f"{session['final_draft_revision']}"
                    ),
                    "final_draft_revision": session["final_draft_revision"],
                }
            if session["status"] != "active":
                raise ValueError(f"Cannot finalize {session['status']} intake session")
            draft = await conn.fetchrow(
                """
                SELECT revision
                FROM ops.intake_draft_revisions
                WHERE session_key = $1 AND revision = $2
                """,
                session_key,
                final_draft_revision,
            )
            if not draft:
                raise ValueError(f"Draft revision not found for session: {final_draft_revision}")
            row = await conn.fetchrow(
                """
                UPDATE ops.intake_sessions
                SET status = 'finalized',
                    repository_key = COALESCE($2, repository_key),
                    project_key = COALESCE($3, project_key),
                    feature_key = COALESCE($4, feature_key),
                    task_key = COALESCE($5, task_key),
                    final_draft_revision = $6,
                    finalized_utc = NOW(),
                    updated_utc = NOW(),
                    metadata = metadata || $7::jsonb
                WHERE session_key = $1
                RETURNING session_key, status, finalized_utc
                """,
                session_key,
                repository_key,
                project_key,
                feature_key,
                task_key,
                final_draft_revision,
                _json_arg(metadata, {}),
            )
            return _record_to_dict(row) or {}


async def link_workflow_run(
    pool,
    *,
    session_key: str,
    run_id: str,
    workflow_name: str,
    link_type: str,
    repository_key: str | None = None,
    project_key: str | None = None,
    feature_key: str | None = None,
    task_key: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            session = await conn.fetchrow(
                "SELECT session_key FROM ops.intake_sessions WHERE session_key = $1 FOR UPDATE",
                session_key,
            )
            if not session:
                raise ValueError(f"Intake session not found: {session_key}")
            link_key = _key("link")
            row = await conn.fetchrow(
                """
                INSERT INTO ops.intake_workflow_links
                    (link_key, session_key, run_id, workflow_name, link_type,
                     repository_key, project_key, feature_key, task_key, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                RETURNING link_key
                """,
                link_key,
                session_key,
                uuid.UUID(run_id),
                workflow_name,
                link_type,
                repository_key,
                project_key,
                feature_key,
                task_key,
                _json_arg(metadata, {}),
            )
            await conn.execute(
                "UPDATE ops.intake_sessions SET updated_utc = NOW() WHERE session_key = $1",
                session_key,
            )
            return _record_to_dict(row) or {}


async def list_sessions_by_actor(
    pool,
    *,
    actor_email: str,
    include_terminal: bool = False,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    if status is not None:
        _validate(status, SESSION_STATUSES, "status")
    capped_limit = max(1, min(int(limit or 50), 200))
    rows = await pool.fetch(
        """
        SELECT session_key, status, mode, title, updated_utc, project_key,
               feature_key, repository_key, task_key
        FROM ops.intake_sessions
        WHERE actor_email = $1
          AND ($2::varchar IS NULL OR status = $2::varchar)
          AND ($3::boolean OR $2::varchar IS NOT NULL OR status NOT IN ('finalized', 'cancelled', 'expired'))
        ORDER BY updated_utc DESC
        LIMIT $4
        """,
        actor_email,
        status,
        include_terminal,
        capped_limit,
    )
    return {"sessions": [_record_to_dict(row) or {} for row in rows]}
