from __future__ import annotations

import re

import structlog

from memory_knowledge.parsers.base import FileParseOutput, SqlObjectRef, SymbolInfo

logger = structlog.get_logger()

_CREATE_PATTERN = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?"
    r"(TABLE|PROCEDURE|FUNCTION|VIEW|TRIGGER|INDEX|TYPE)"
    r"\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:(?:`[\w.]+`|\[?[\w.]+\]?)\.)?(`[\w]+`|\[?[\w]+\]?)",
    re.IGNORECASE | re.MULTILINE,
)


def parse_sql_file(file_path: str, source: str) -> FileParseOutput:
    """Parse SQL source using regex patterns. Extracts CREATE statements."""
    try:
        lines = source.splitlines()
        symbols = _extract_symbols(source, lines)
        sql_refs = _extract_sql_refs(source)

        return FileParseOutput(
            file_path=file_path,
            language="sql",
            symbols=symbols,
            imports=[],
            calls=[],
            sql_refs=sql_refs,
        )
    except Exception as e:
        logger.warning("sql_parse_error", file_path=file_path, error=str(e))
        return FileParseOutput(
            file_path=file_path, language="sql", parse_error=str(e)
        )


def _extract_symbols(source: str, lines: list[str]) -> list[SymbolInfo]:
    symbols: list[SymbolInfo] = []

    for match in _CREATE_PATTERN.finditer(source):
        obj_type = match.group(1).lower()
        obj_name = match.group(2).strip("[]`")
        line_no = source[: match.start()].count("\n") + 1

        # Estimate end: next CREATE or EOF
        end_line = len(lines)
        rest = source[match.end() :]
        next_create = _CREATE_PATTERN.search(rest)
        if next_create:
            end_line = source[: match.end() + next_create.start()].count("\n") + 1

        symbols.append(
            SymbolInfo(
                name=obj_name,
                kind=obj_type,
                line_start=line_no,
                line_end=end_line,
                signature=f"CREATE {obj_type.upper()} {obj_name}",
            )
        )

    return symbols


_DML_PATTERN = re.compile(
    r"\b(SELECT\s+[^;]*?\s+FROM|JOIN|INSERT\s+INTO|UPDATE|DELETE\s+FROM)"
    r"\s+(?:(?:`[\w.]+`|\[?[\w.]+\]?)\.)?(`[\w]+`|\[?\w+\]?)",
    re.IGNORECASE,
)


def _extract_sql_refs(source: str) -> list[SqlObjectRef]:
    """Extract table references from DML statements."""
    refs: list[SqlObjectRef] = []
    seen: set[tuple[str, str]] = set()
    for match in _DML_PATTERN.finditer(source):
        operation_raw = match.group(1).strip().split()[0].lower()
        obj_name = match.group(2).strip("[]`")
        if obj_name.upper() in ("SET", "VALUES", "AS", "ON", "WHERE", "AND", "OR"):
            continue
        op_map = {"select": "select", "join": "select", "insert": "insert", "update": "update", "delete": "delete"}
        operation = op_map.get(operation_raw, operation_raw)
        key = (obj_name.lower(), operation)
        if key in seen:
            continue
        seen.add(key)
        line_no = source[: match.start()].count("\n") + 1
        refs.append(SqlObjectRef(
            object_name=obj_name,
            object_type="table",
            operation=operation,
            line_start=line_no,
        ))
    return refs
