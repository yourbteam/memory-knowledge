"""Resolve a Reporting V3 writer expression to one calculation root."""

from __future__ import annotations

import re


_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_ROW_ROOT = re.compile(rf"^row\.({_IDENTIFIER})$")
_LOCAL_ROOT = re.compile(
    rf"^(?:\([A-Za-z_][A-Za-z0-9_.<>]*\)\s*)?({_IDENTIFIER})$"
)
_HELPER_ROOT = re.compile(
    rf"^[A-Za-z_][A-Za-z0-9_.]*\(\s*({_IDENTIFIER})\s*\)$"
)


def extract_root(expression: str) -> str:
    """Return the only supported calculation root or fail closed."""

    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("writer expression must be a nonempty string")
    value = expression.strip()
    match = _ROW_ROOT.fullmatch(value)
    if match:
        return f"row.{match.group(1)}"
    match = _LOCAL_ROOT.fullmatch(value)
    if match:
        return match.group(1)
    match = _HELPER_ROOT.fullmatch(value)
    if match:
        return match.group(1)
    raise ValueError(
        f"writer expression {expression!r} does not identify one supported calculation root"
    )
