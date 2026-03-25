from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class WorkflowResult(BaseModel):
    run_id: str
    tool_name: str
    status: Literal["success", "error", "not_implemented"]
    data: dict[str, Any] = {}
    error: str | None = None
    duration_ms: int | None = None
