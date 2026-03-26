from __future__ import annotations

import re

import structlog

from memory_knowledge.parsers.base import (
    CallInfo,
    FileParseOutput,
    ImportInfo,
    SymbolInfo,
)

logger = structlog.get_logger()

_CLASS_PATTERN = re.compile(
    r"^\s*(?:public|private|internal|protected)?\s*(?:static\s+)?(?:abstract\s+)?(?:partial\s+)?class\s+(\w+)",
    re.MULTILINE,
)
_INTERFACE_PATTERN = re.compile(
    r"^\s*(?:public|private|internal|protected)?\s*interface\s+(\w+)",
    re.MULTILINE,
)
_METHOD_PATTERN = re.compile(
    r"^\s*(?:public|private|internal|protected)\s+(?:static\s+)?(?:async\s+)?(?:virtual\s+)?(?:override\s+)?\w+(?:<[^>]+>)?\s+(\w+)\s*\(",
    re.MULTILINE,
)
_USING_PATTERN = re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE)


def parse_csharp_file(file_path: str, source: str) -> FileParseOutput:
    """Parse C# source using regex patterns."""
    try:
        lines = source.splitlines()
        symbols = _extract_symbols(source, lines)
        imports = _extract_imports(source)
        calls = _extract_calls(source, symbols)

        return FileParseOutput(
            file_path=file_path,
            language="csharp",
            symbols=symbols,
            imports=imports,
            calls=calls,
        )
    except Exception as e:
        logger.warning("csharp_parse_error", file_path=file_path, error=str(e))
        return FileParseOutput(
            file_path=file_path, language="csharp", parse_error=str(e)
        )


def _extract_symbols(source: str, lines: list[str]) -> list[SymbolInfo]:
    symbols: list[SymbolInfo] = []

    for match in _CLASS_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        symbols.append(
            SymbolInfo(
                name=match.group(1),
                kind="class",
                line_start=line_no,
                line_end=_find_block_end(lines, line_no),
                signature=f"class {match.group(1)}",
            )
        )

    for match in _INTERFACE_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        symbols.append(
            SymbolInfo(
                name=match.group(1),
                kind="interface",
                line_start=line_no,
                line_end=_find_block_end(lines, line_no),
                signature=f"interface {match.group(1)}",
            )
        )

    for match in _METHOD_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        name = match.group(1)
        if name not in ("if", "for", "while", "switch", "catch", "using"):
            symbols.append(
                SymbolInfo(
                    name=name,
                    kind="method",
                    line_start=line_no,
                    line_end=_find_block_end(lines, line_no),
                    signature=match.group(0).strip(),
                )
            )

    return symbols


def _find_block_end(lines: list[str], start_line: int) -> int:
    depth = 0
    started = False
    for i in range(start_line - 1, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth <= 0:
                    return i + 1
    return len(lines)


def _extract_imports(source: str) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for match in _USING_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        imports.append(
            ImportInfo(
                module_path=match.group(1),
                imported_names=[match.group(1).split(".")[-1]],
                line_start=line_no,
            )
        )
    return imports


def _extract_calls(source: str, symbols: list[SymbolInfo]) -> list[CallInfo]:
    known = {s.name for s in symbols}
    calls: list[CallInfo] = []
    call_pattern = re.compile(r"\b(\w+)\s*\(")
    for match in call_pattern.finditer(source):
        name = match.group(1)
        if name in known and name not in ("if", "for", "while", "switch", "catch", "using", "class"):
            line_no = source[: match.start()].count("\n") + 1
            enclosing = None
            for sym in symbols:
                if sym.line_start <= line_no <= sym.line_end and sym.name != name:
                    enclosing = sym.name
            if enclosing:
                calls.append(CallInfo(caller_name=enclosing, callee_name=name, line_no=line_no))
    return calls
