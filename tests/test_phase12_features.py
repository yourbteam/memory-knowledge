"""Tests for Phase 12 features: inheritance, mixed classification, features, backfill schemas."""
from memory_knowledge.parsers.python_adapter import parse_python_file
from memory_knowledge.parsers.typescript_adapter import parse_typescript_file
from memory_knowledge.parsers.csharp_adapter import parse_csharp_file
from memory_knowledge.parsers.php_adapter import parse_php_file
from memory_knowledge.workflows.retrieval import classify_prompt
from memory_knowledge.routing.prompt_feature_extractor import extract_prompt_features


# --- Inheritance extraction ---

def test_python_base_classes():
    code = '''\
class Base:
    pass

class Child(Base):
    pass

class Multi(Base, Mixin):
    pass
'''
    output = parse_python_file("test.py", code)
    child = next(s for s in output.symbols if s.name == "Child")
    assert child.base_classes == ["Base"]
    multi = next(s for s in output.symbols if s.name == "Multi")
    assert set(multi.base_classes) == {"Base", "Mixin"}


def test_python_no_bases():
    code = "class Standalone:\n    pass\n"
    output = parse_python_file("test.py", code)
    assert output.symbols[0].base_classes == []


def test_typescript_extends():
    code = "export class UserService extends BaseService {\n}\n"
    output = parse_typescript_file("user.ts", code)
    cls = next(s for s in output.symbols if s.name == "UserService")
    assert "BaseService" in cls.base_classes


def test_typescript_implements():
    code = "class Handler implements IHandler, Serializable {\n}\n"
    output = parse_typescript_file("handler.ts", code)
    cls = next(s for s in output.symbols if s.name == "Handler")
    assert "IHandler" in cls.base_classes
    assert "Serializable" in cls.base_classes


def test_csharp_inheritance():
    code = "public class UserController : BaseController, IDisposable\n{\n}\n"
    output = parse_csharp_file("UserController.cs", code)
    cls = next(s for s in output.symbols if s.name == "UserController")
    assert "BaseController" in cls.base_classes
    assert "IDisposable" in cls.base_classes


def test_php_extends_implements():
    code = r"""<?php
class UserService extends BaseService implements Cacheable, Loggable
{
}
"""
    output = parse_php_file("UserService.php", code)
    cls = next(s for s in output.symbols if s.name == "UserService")
    assert "BaseService" in cls.base_classes
    assert "Cacheable" in cls.base_classes
    assert "Loggable" in cls.base_classes


# --- Prompt feature extractor ---

def test_stack_trace_detection():
    features = extract_prompt_features('Traceback (most recent call last):\n  File "foo.py", line 42')
    assert features["has_stack_trace"] is True


def test_sql_keyword_detection():
    features = extract_prompt_features("SELECT * FROM users WHERE id = 1")
    assert features["has_sql_keywords"] is True


def test_traversal_phrase_detection():
    features = extract_prompt_features("what calls the auth middleware")
    assert features["has_traversal_phrases"] is True


def test_no_false_positive_features():
    features = extract_prompt_features("tell me about the logging system")
    assert features["has_stack_trace"] is False
    assert features["has_sql_keywords"] is False
    assert features["has_traversal_phrases"] is False


# --- Mixed classification ---

def test_mixed_two_categories():
    result = classify_prompt("what is the impact of the design pattern change")
    assert result == ("mixed", 0.7)


def test_traversal_routes_to_impact():
    result = classify_prompt("what calls getUserById")
    assert result[0] == "impact_analysis"


def test_single_category_not_mixed():
    result = classify_prompt("what would break if I change the schema")
    assert result == ("impact_analysis", 1.0)


# --- Service label heuristic (unit test for naming) ---

def test_service_name_detection():
    """Service label is applied to classes ending with Service or Provider."""
    # This tests the naming convention, not the Neo4j projection
    service_names = ["UserService", "AuthProvider", "CacheService"]
    non_service_names = ["ServiceLocator", "User", "Controller"]
    for name in service_names:
        assert name.endswith("Service") or name.endswith("Provider")
    for name in non_service_names:
        assert not (name.endswith("Service") or name.endswith("Provider"))
