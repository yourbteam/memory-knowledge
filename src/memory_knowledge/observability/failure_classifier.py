from __future__ import annotations

from pydantic import BaseModel

# Error code constants
STORE_UNREACHABLE = "STORE_UNREACHABLE"
ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
PROJECTION_DRIFT = "PROJECTION_DRIFT"
EMBEDDING_FAILED = "EMBEDDING_FAILED"
REPAIR_PARTIAL = "REPAIR_PARTIAL"
UNKNOWN = "UNKNOWN"


class FailureReport(BaseModel):
    error_code: str
    message: str
    store: str | None = None
    recoverable: bool = True


def classify_error(exc: Exception) -> str:
    """Map an exception to a structured error code."""
    exc_type = type(exc).__name__
    exc_module = type(exc).__module__ or ""

    # Connection / unreachable errors
    if any(
        kw in exc_type.lower()
        for kw in ("connection", "timeout", "refused", "unreachable")
    ):
        return STORE_UNREACHABLE
    if "asyncpg" in exc_module and exc_type in (
        "InterfaceError", "InternalClientError", "ConnectionDoesNotExistError",
    ):
        return STORE_UNREACHABLE
    if "qdrant" in exc_module.lower() and any(
        kw in exc_type for kw in ("Connection", "Timeout", "Unreachable")
    ):
        return STORE_UNREACHABLE
    if "neo4j" in exc_module.lower() and exc_type in ("ServiceUnavailable",):
        return STORE_UNREACHABLE

    # OpenAI / embedding errors
    if "openai" in exc_module.lower():
        return EMBEDDING_FAILED

    # Not found
    if isinstance(exc, (KeyError, ValueError)):
        msg = str(exc).lower()
        if "not found" in msg:
            return ENTITY_NOT_FOUND

    return UNKNOWN
