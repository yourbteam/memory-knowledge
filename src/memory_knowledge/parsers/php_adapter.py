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
    r"^\s*(?:abstract\s+|final\s+|readonly\s+)*class\s+(\w+)",
    re.MULTILINE,
)
_INTERFACE_PATTERN = re.compile(
    r"^\s*interface\s+(\w+)",
    re.MULTILINE,
)
_TRAIT_PATTERN = re.compile(
    r"^\s*trait\s+(\w+)",
    re.MULTILINE,
)
_ENUM_PATTERN = re.compile(
    r"^\s*enum\s+(\w+)",
    re.MULTILINE,
)
_FUNCTION_PATTERN = re.compile(
    r"^function\s+(\w+)\s*\(",
    re.MULTILINE,
)
_METHOD_PATTERN = re.compile(
    r"^\s+(?:abstract\s+)?(?:(?:public|protected|private)\s+)?(?:static\s+)?(?:abstract\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)
_USE_PATTERN = re.compile(
    r"^use\s+(?:function\s+|const\s+)?([\w\\]+)(?:\s+as\s+\w+)?\s*;",
    re.MULTILINE,
)
_USE_GROUP_PATTERN = re.compile(
    r"^use\s+(?:function\s+|const\s+)?([\w\\]+)\\\{([^}]+)\}\s*;",
    re.MULTILINE,
)
_REQUIRE_PATTERN = re.compile(
    r"(?:require_once|include_once|require|include)\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)


def parse_php_file(file_path: str, source: str) -> FileParseOutput:
    """Parse PHP source using regex patterns."""
    try:
        lines = source.splitlines()
        symbols = _extract_symbols(source, lines)
        imports = _extract_imports(source)
        calls = _extract_calls(source, symbols)

        return FileParseOutput(
            file_path=file_path,
            language="php",
            symbols=symbols,
            imports=imports,
            calls=calls,
        )
    except Exception as e:
        logger.warning("php_parse_error", file_path=file_path, error=str(e))
        return FileParseOutput(
            file_path=file_path, language="php", parse_error=str(e)
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
                signature=match.group(0).strip(),
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

    for match in _TRAIT_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        symbols.append(
            SymbolInfo(
                name=match.group(1),
                kind="trait",
                line_start=line_no,
                line_end=_find_block_end(lines, line_no),
                signature=f"trait {match.group(1)}",
            )
        )

    for match in _ENUM_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        symbols.append(
            SymbolInfo(
                name=match.group(1),
                kind="enum",
                line_start=line_no,
                line_end=_find_block_end(lines, line_no),
                signature=match.group(0).strip(),
            )
        )

    for match in _FUNCTION_PATTERN.finditer(source):
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

    for match in _METHOD_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        name = match.group(1)
        if name not in ("if", "for", "while", "switch", "catch", "foreach"):
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
    for match in _USE_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        module_path = match.group(1)
        imports.append(
            ImportInfo(
                module_path=module_path,
                imported_names=[module_path.rsplit("\\", 1)[-1]],
                line_start=line_no,
            )
        )
    for match in _USE_GROUP_PATTERN.finditer(source):
        line_no = source[: match.start()].count("\n") + 1
        prefix = match.group(1)
        names = [n.strip() for n in match.group(2).split(",") if n.strip()]
        for name in names:
            full_path = f"{prefix}\\{name}"
            imports.append(
                ImportInfo(
                    module_path=full_path,
                    imported_names=[name.rsplit("\\", 1)[-1]],
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
    known = {s.name for s in symbols}
    calls: list[CallInfo] = []
    call_pattern = re.compile(r"\b(\w+)\s*\(")
    for match in call_pattern.finditer(source):
        name = match.group(1)
        if name in known and name not in (
            "if", "for", "while", "switch", "catch", "foreach",
            "class", "function", "use", "require", "include",
            "require_once", "include_once", "array", "list",
        ):
            line_no = source[: match.start()].count("\n") + 1
            enclosing = None
            for sym in symbols:
                if sym.line_start <= line_no <= sym.line_end and sym.name != name:
                    enclosing = sym.name
            if enclosing:
                calls.append(
                    CallInfo(caller_name=enclosing, callee_name=name, line_no=line_no)
                )
    return calls
