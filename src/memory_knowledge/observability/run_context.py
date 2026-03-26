from __future__ import annotations

import uuid

import structlog


def new_run_id() -> uuid.UUID:
    return uuid.uuid4()


def bind_run_context(
    run_id: uuid.UUID,
    correlation_id: str | None = None,
    tool_name: str | None = None,
    job_id: str | None = None,
    repository_key: str | None = None,
    commit_sha: str | None = None,
    branch_name: str | None = None,
) -> None:
    ctx: dict[str, str | None] = {
        "run_id": str(run_id),
        "correlation_id": correlation_id,
        "tool_name": tool_name,
    }
    if job_id:
        ctx["job_id"] = job_id
    if repository_key:
        ctx["repository_key"] = repository_key
    if commit_sha:
        ctx["commit_sha"] = commit_sha
    if branch_name:
        ctx["branch_name"] = branch_name
    structlog.contextvars.bind_contextvars(**ctx)


def clear_run_context() -> None:
    structlog.contextvars.clear_contextvars()
