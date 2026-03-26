from __future__ import annotations

import re

import structlog

from memory_knowledge.parsers.base import FileParseOutput, SymbolInfo

logger = structlog.get_logger()

_CREATE_PATTERN = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?"
    r"(TABLE|PROCEDURE|FUNCTION|VIEW|TRIGGER|INDEX|TYPE)"
    r"\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:\[?[\w.]+\]?\.)?(\[?[\w]+\]?)",
    re.IGNORECASE | re.MULTILINE,
)


def parse_sql_file(file_path: str, source: str) -> FileParseOutput:
    """Parse SQL source using regex patterns. Extracts CREATE statements."""
    try:
        lines = source.splitlines()
        symbols = _extract_symbols(source, lines)

        return FileParseOutput(
            file_path=file_path,
            language="sql",
            symbols=symbols,
            imports=[],
            calls=[],
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
        obj_name = match.group(2).strip("[]")
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
