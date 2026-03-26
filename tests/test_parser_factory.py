from memory_knowledge.parsers.factory import (
    detect_language,
    get_import_resolver,
    get_parser,
)
from memory_knowledge.parsers.php_adapter import parse_php_file


def test_get_parser_php():
    parser = get_parser("src/controllers/UserController.php")
    assert parser is parse_php_file


def test_detect_language_php():
    assert detect_language("test.php") == "php"


def test_import_resolver_php_is_none():
    assert get_import_resolver("php") is None


def test_detect_language_case_insensitive():
    assert detect_language("test.PHP") == "php"


def test_get_parser_unsupported():
    parser = get_parser("test.rb")
    output = parser("test.rb", "class Foo; end")
    assert output.parse_error is not None
    assert output.language == "unknown"
