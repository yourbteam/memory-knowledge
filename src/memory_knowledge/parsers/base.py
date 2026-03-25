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
class FileParseOutput:
    file_path: str
    language: str
    symbols: list[SymbolInfo] = field(default_factory=list)
    parse_error: str | None = None
