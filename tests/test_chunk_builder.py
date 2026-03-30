from memory_knowledge.parsers.base import FileParseOutput, SymbolInfo
from memory_knowledge.structure.chunk_builder import (
    MAX_CHUNK_CHARS,
    ChunkSpec,
    build_chunks,
)


def _make_parse_output(symbols=None):
    return FileParseOutput(
        file_path="test.py",
        language="python",
        symbols=symbols or [],
    )


def test_symbol_chunks():
    symbols = [
        SymbolInfo("foo", "function", 1, 3, "def foo()"),
        SymbolInfo("bar", "function", 5, 7, "def bar()"),
    ]
    source = ["def foo():", "    pass", "", "def bar():", "    pass", "", ""]
    chunks = build_chunks(_make_parse_output(symbols), source)
    assert len(chunks) == 2
    assert chunks[0].chunk_type == "symbol"
    assert chunks[0].symbol_name == "foo"
    assert chunks[1].symbol_name == "bar"
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1


def test_file_level_fallback():
    source = ["x = 1", "y = 2"]
    chunks = build_chunks(_make_parse_output(), source)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "file"
    assert chunks[0].title == "test.py"
    assert chunks[0].symbol_name is None


def test_oversized_symbol_splits():
    big_body = "x = 1\n" * 2000  # well over 8000 chars
    lines = big_body.splitlines()
    symbols = [SymbolInfo("big_func", "function", 1, len(lines), "def big_func()")]
    chunks = build_chunks(_make_parse_output(symbols), lines)
    assert len(chunks) > 1
    assert all(c.chunk_type == "symbol" for c in chunks)
    assert all(c.symbol_name == "big_func" for c in chunks)
    # Each chunk should be <= MAX_CHUNK_CHARS
    for c in chunks:
        assert len(c.content_text) <= MAX_CHUNK_CHARS


def test_oversized_file_splits():
    big_content = "x = 1\n" * 2000
    lines = big_content.splitlines()
    chunks = build_chunks(_make_parse_output(), lines)
    assert len(chunks) > 1
    assert all(c.chunk_type == "file" for c in chunks)


def test_chunk_titles():
    symbols = [SymbolInfo("MyClass", "class", 1, 5, "class MyClass")]
    source = ["class MyClass:", "    pass", "", "", ""]
    chunks = build_chunks(_make_parse_output(symbols), source)
    assert chunks[0].title == "class:MyClass"


def test_empty_file():
    chunks = build_chunks(_make_parse_output(), [])
    assert len(chunks) == 0  # empty files produce no chunks
