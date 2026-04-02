"""Remote write and rebuild safety guards.

Invocation-time blocking: the server starts in remote mode but
write operations are rejected unless explicitly allowed.
"""
from __future__ import annotations

from memory_knowledge.config import Settings
from memory_knowledge.workflows.base import WorkflowResult


def check_remote_write_guard(
    settings: Settings,
    tool_name: str,
    *,
    is_destructive: bool = False,
) -> WorkflowResult | None:
    """Return WorkflowResult error if remote writes are blocked, else None.

    Called at the top of write-path MCP tool handlers.
    - If no DB is remote, returns None (always allowed).
    - If remote and ALLOW_REMOTE_WRITES is False, returns error.
    - If is_destructive and ALLOW_REMOTE_REBUILDS is False, returns error.
    """
    if not settings.is_any_remote():
        return None

    if not settings.allow_remote_writes:
        return WorkflowResult(
            run_id="",
            tool_name=tool_name,
            status="error",
            error=(
                f"Write operation '{tool_name}' blocked: DATA_MODE includes remote "
                "databases but ALLOW_REMOTE_WRITES is not set to true"
            ),
        )

    if is_destructive and not settings.allow_remote_rebuilds:
        return WorkflowResult(
            run_id="",
            tool_name=tool_name,
            status="error",
            error=(
                f"Destructive operation '{tool_name}' blocked: "
                "ALLOW_REMOTE_REBUILDS is not set to true"
            ),
        )

    return None
