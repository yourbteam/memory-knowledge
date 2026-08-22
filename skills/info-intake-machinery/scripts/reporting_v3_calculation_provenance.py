"""Trace one Reporting V3 calculation root to exact source spans."""

from __future__ import annotations

import re


def _statement(lines: list[str], start: int) -> tuple[int, str]:
    parts: list[str] = []
    for index in range(start, len(lines)):
        parts.append(lines[index].strip())
        if ";" in lines[index]:
            return index + 1, " ".join(parts)
    raise ValueError(f"unterminated calculation beginning on line {start + 1}")


def trace_root(source: str, root: str, writer_line: int) -> list[dict[str, object]]:
    """Return exact prior definitions or mutations for ``root``."""

    if not isinstance(source, str):
        raise ValueError("source must be text")
    if not isinstance(root, str) or not root:
        raise ValueError("calculation root must be a nonempty string")
    if not isinstance(writer_line, int) or writer_line < 1:
        raise ValueError("writer line must be a positive integer")
    lines = source.splitlines()
    if writer_line > len(lines):
        raise ValueError(
            f"writer line {writer_line} exceeds source length {len(lines)}"
        )
    if root.startswith("row."):
        name = re.escape(root)
        mutation = re.compile(rf"\b{name}\s*(\+\+|--|\+=|-=|\*=|/=|=)")
        matches: list[dict[str, object]] = []
        for index, line in enumerate(lines):
            if index + 1 >= writer_line:
                break
            matched = mutation.search(line)
            if not matched:
                continue
            if matched.group(1) == "=":
                end_line, statement = _statement(lines, index)
            else:
                end_line, statement = index + 1, line.strip()
            matches.append(
                {
                    "kind": "row_mutation",
                    "start_line": index + 1,
                    "end_line": end_line,
                    "source": statement,
                }
            )
        return matches
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", root):
        raise ValueError(f"unsupported calculation root {root!r}")
    declaration = re.compile(rf"^\s*var\s+{re.escape(root)}\s*=")
    matches: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        if index + 1 >= writer_line or not declaration.search(line):
            continue
        end_line, statement = _statement(lines, index)
        matches.append(
            {
                "kind": "local_definition",
                "start_line": index + 1,
                "end_line": end_line,
                "source": statement,
            }
        )
    if len(matches) > 1:
        raise ValueError(
            f"calculation root {root!r} has multiple local definitions before its writer"
        )
    return matches
