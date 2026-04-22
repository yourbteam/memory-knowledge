from __future__ import annotations

import traceback


def format_exception_detail(exc: BaseException, *, max_length: int = 2000) -> str:
    """Return a non-empty diagnostic string for exceptions with blank messages."""
    exc_type = type(exc).__name__
    message = str(exc).strip()
    detail = f"{exc_type}: {message}" if message else f"{exc_type}: <no message>"

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    if tb:
        detail = f"{detail}\n{tb}"

    if len(detail) > max_length:
        return detail[: max_length - 3] + "..."
    return detail
