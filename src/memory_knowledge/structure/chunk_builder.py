from __future__ import annotations

from dataclasses import dataclass

from memory_knowledge.parsers.base import FileParseOutput, SymbolInfo

MAX_CHUNK_CHARS = 8000
OVERLAP_CHARS = 500


@dataclass
class ChunkSpec:
    chunk_index: int
    chunk_type: str  # "symbol" or "file"
    title: str
    content_text: str
    line_start: int | None
    line_end: int | None
    symbol_name: str | None


def build_chunks(
    parse_output: FileParseOutput, source_lines: list[str]
) -> list[ChunkSpec]:
    """Build chunks from parsed symbols. Falls back to file-level if no symbols."""
    if not source_lines or not any(line.strip() for line in source_lines):
        return []  # skip empty files

    if not parse_output.symbols:
        return _file_level_chunks(parse_output.file_path, source_lines)

    chunks: list[ChunkSpec] = []
    for sym in parse_output.symbols:
        text = "\n".join(source_lines[sym.line_start - 1 : sym.line_end])
        if len(text) <= MAX_CHUNK_CHARS:
            chunks.append(
                ChunkSpec(
                    chunk_index=len(chunks),
                    chunk_type="symbol",
                    title=f"{sym.kind}:{sym.name}",
                    content_text=text,
                    line_start=sym.line_start,
                    line_end=sym.line_end,
                    symbol_name=sym.name,
                )
            )
        else:
            chunks.extend(_split_oversized(text, sym, len(chunks)))
    return chunks


def _file_level_chunks(
    file_path: str, source_lines: list[str]
) -> list[ChunkSpec]:
    full_text = "\n".join(source_lines)
    if len(full_text) <= MAX_CHUNK_CHARS:
        return [
            ChunkSpec(
                chunk_index=0,
                chunk_type="file",
                title=file_path,
                content_text=full_text,
                line_start=1,
                line_end=len(source_lines),
                symbol_name=None,
            )
        ]
    parts = _split_with_overlap(full_text)
    return [
        ChunkSpec(
            chunk_index=i,
            chunk_type="file",
            title=f"{file_path}[{i}]",
            content_text=part,
            line_start=1,
            line_end=len(source_lines),
            symbol_name=None,
        )
        for i, part in enumerate(parts)
    ]


def _split_oversized(
    text: str, sym: SymbolInfo, start_idx: int
) -> list[ChunkSpec]:
    parts = _split_with_overlap(text)
    return [
        ChunkSpec(
            chunk_index=start_idx + i,
            chunk_type="symbol",
            title=f"{sym.kind}:{sym.name}[{i}]",
            content_text=part,
            line_start=sym.line_start,
            line_end=sym.line_end,
            symbol_name=sym.name,
        )
        for i, part in enumerate(parts)
    ]


def _split_with_overlap(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = start + MAX_CHUNK_CHARS
        parts.append(text[start:end])
        start = end - OVERLAP_CHARS
    return parts
