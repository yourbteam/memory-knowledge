from __future__ import annotations

import uuid

import structlog


def new_run_id() -> uuid.UUID:
    return uuid.uuid4()


def bind_run_context(
    run_id: uuid.UUID,
    correlation_id: str | None = None,
    tool_name: str | None = None,
) -> None:
    structlog.contextvars.bind_contextvars(
        run_id=str(run_id),
        correlation_id=correlation_id,
        tool_name=tool_name,
    )


def clear_run_context() -> None:
    structlog.contextvars.clear_contextvars()
