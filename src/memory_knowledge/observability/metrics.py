from __future__ import annotations

import functools
import time
from typing import Any, Callable

import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger()

tool_calls_total = Counter(
    "mk_tool_calls_total", "MCP tool call count", ["tool_name", "status"]
)
tool_duration_seconds = Histogram(
    "mk_tool_duration_seconds", "MCP tool call duration", ["tool_name"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
embedding_calls_total = Counter(
    "mk_embedding_calls_total", "Embedding API call count", ["model"]
)
ingestion_files_total = Counter(
    "mk_ingestion_files_total", "Files processed during ingestion", ["language", "status"]
)
job_transitions_total = Counter(
    "mk_job_transitions_total", "Job state transitions", ["from_state", "to_state"]
)


def track_tool_metrics(tool_name: str) -> Callable:
    """Decorator that tracks duration and status for MCP tool functions."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            status = "success"
            try:
                result = await fn(*args, **kwargs)
                return result
            except Exception:
                status = "error"
                raise
            finally:
                duration = time.monotonic() - start
                tool_calls_total.labels(tool_name=tool_name, status=status).inc()
                tool_duration_seconds.labels(tool_name=tool_name).observe(duration)
        return wrapper
    return decorator
