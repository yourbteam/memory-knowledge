from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SymbolInfo:
    name: str
    kind: str  # "function", "async_function", "class"
    line_start: int
    line_end: int
    signature: str


@dataclass
class ImportInfo:
    module_path: str
    imported_names: list[str]
    line_start: int


@dataclass
class CallInfo:
    caller_name: str
    callee_name: str
    line_no: int


@dataclass
class FileParseOutput:
    file_path: str
    language: str
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    parse_error: str | None = None
