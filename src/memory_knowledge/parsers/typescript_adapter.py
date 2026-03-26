from __future__ import annotations

import os
import re

import structlog

from memory_knowledge.parsers.base import (
    CallInfo,
    FileParseOutput,
    ImportInfo,
    SymbolInfo,
)

logger = structlog.get_logger()

# Regex-based extraction for TypeScript/JavaScript
# Falls back to regex if tree-sitter is not available

_FUNC_PATTERN = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)
_CLASS_PATTERN = re.compile(
    r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)",
    re.MULTILINE,
)
_INTERFACE_PATTERN = re.compile(
    r"^(?:export\s+)?interface\s+(\w+)",
    re.MULTILINE,
)
_ARROW_PATTERN = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
    re.MULTILINE,
)
_IMPORT_PATTERN = re.compile(
    r"""import\s+(?:{[^}]+}|\w+|\*\s+as\s+\w+)\s+from\s+['"]([^'"]+)['"]""",
    re.MULTILINE,
)
_REQUIRE_PATTERN = re.compile(
    r"""(?:const|let|var)\s+(?:{[^}]+}|\w+)\s*=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)


def parse_typescript_file(file_path: str, source: str) -> FileParseOutput:
    """Parse TypeScript/JavaScript source using regex patterns."""
    ext = os.path.splitext(file_path)[1].lower()
    language = "javascript" if ext in (".js", ".jsx") else "typescript"

    try:
        lines = source.splitlines()
        symbols = _extract_symbols(source, lines)
        imports = _extract_imports(source)
        calls = _extract_calls(source, symbols)

        return FileParseOutput(
            file_path=file_path,
            language=language,
            symbols=symbols,
            imports=imports,
            calls=calls,
        )
    except Exception as e:
        logger.warning("ts_parse_error", file_path=file_path, error=str(e))
        return FileParseOutput(
            file_path=file_path, language=language, parse_error=str(e)
        )


def _extract_symbols(source: str, lines: list[str]) -> list[SymbolInfo]:
    symbols: list[SymbolInfo] = []

    for match in _FUNC_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        symbols.append(
            SymbolInfo(
                name=match.group(1),
                kind="function",
                line_start=line_no,
                line_end=_find_block_end(lines, line_no),
                signature=f"function {match.group(1)}(...)",
            )
        )

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

    for match in _ARROW_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        symbols.append(
            SymbolInfo(
                name=match.group(1),
                kind="function",
                line_start=line_no,
                line_end=_find_block_end(lines, line_no),
                signature=f"const {match.group(1)} = (...) =>",
            )
        )

    return symbols


def _find_block_end(lines: list[str], start_line: int) -> int:
    """Estimate the end of a code block by tracking brace depth."""
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
    for match in _IMPORT_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        imports.append(
            ImportInfo(
                module_path=match.group(1),
                imported_names=[],
                line_start=line_no,
            )
        )
    for match in _REQUIRE_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        imports.append(
            ImportInfo(
                module_path=match.group(1),
                imported_names=[],
                line_start=line_no,
            )
        )
    return imports


def _extract_calls(source: str, symbols: list[SymbolInfo]) -> list[CallInfo]:
    """Extract simple function calls matching known symbol names."""
    known = {s.name for s in symbols}
    calls: list[CallInfo] = []
    call_pattern = re.compile(r"\b(\w+)\s*\(")
    for match in call_pattern.finditer(source):
        name = match.group(1)
        if name in known and name not in ("if", "for", "while", "switch", "catch"):
            line_no = source[: match.start()].count("\n") + 1
            # Find enclosing symbol
            enclosing = None
            for sym in symbols:
                if sym.line_start <= line_no <= sym.line_end and sym.name != name:
                    enclosing = sym.name
            if enclosing:
                calls.append(CallInfo(caller_name=enclosing, callee_name=name, line_no=line_no))
    return calls
