from memory_knowledge.parsers.python_adapter import parse_python_file


SAMPLE_CODE = '''\
class MyClass:
    """A sample class."""

    def method(self, x: int) -> str:
        return str(x)


def standalone(a, b):
    return a + b


async def async_handler(request: Request) -> Response:
    return Response()
'''


def test_extracts_class():
    output = parse_python_file("sample.py", SAMPLE_CODE)
    classes = [s for s in output.symbols if s.kind == "class"]
    assert len(classes) == 1
    assert classes[0].name == "MyClass"
    assert classes[0].line_start == 1
    assert classes[0].signature == "class MyClass"


def test_extracts_top_level_function():
    output = parse_python_file("sample.py", SAMPLE_CODE)
    funcs = [s for s in output.symbols if s.kind == "function"]
    names = {f.name for f in funcs}
    assert "standalone" in names
    # method is inside MyClass — should NOT be extracted as separate symbol
    assert "method" not in names


def test_extracts_async_function():
    output = parse_python_file("sample.py", SAMPLE_CODE)
    async_funcs = [s for s in output.symbols if s.kind == "async_function"]
    assert len(async_funcs) == 1
    assert async_funcs[0].name == "async_handler"


def test_signature_includes_annotations():
    output = parse_python_file("sample.py", SAMPLE_CODE)
    handler = next(s for s in output.symbols if s.name == "async_handler")
    assert "request: Request" in handler.signature
    assert "-> Response" in handler.signature


def test_async_signature_prefix():
    output = parse_python_file("sample.py", SAMPLE_CODE)
    handler = next(s for s in output.symbols if s.name == "async_handler")
    assert handler.signature.startswith("async def")


def test_line_ranges():
    output = parse_python_file("sample.py", SAMPLE_CODE)
    standalone = next(s for s in output.symbols if s.name == "standalone")
    assert standalone.line_start > 0
    assert standalone.line_end >= standalone.line_start


def test_syntax_error_returns_parse_error():
    output = parse_python_file("broken.py", "def broken(\n")
    assert output.parse_error is not None
    assert output.symbols == []


def test_language_is_python():
    output = parse_python_file("test.py", "x = 1\n")
    assert output.language == "python"


def test_empty_file():
    output = parse_python_file("empty.py", "")
    assert output.symbols == []
    assert output.parse_error is None


def test_only_top_level_symbols():
    """Verify nested methods inside classes are NOT extracted as separate symbols."""
    output = parse_python_file("sample.py", SAMPLE_CODE)
    # Should have exactly 3 top-level symbols: MyClass, standalone, async_handler
    assert len(output.symbols) == 3
    names = {s.name for s in output.symbols}
    assert names == {"MyClass", "standalone", "async_handler"}
