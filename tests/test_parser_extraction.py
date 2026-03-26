"""Tests for route, SQL ref, and doc block extraction across parsers."""
from memory_knowledge.parsers.python_adapter import parse_python_file
from memory_knowledge.parsers.typescript_adapter import parse_typescript_file
from memory_knowledge.parsers.csharp_adapter import parse_csharp_file
from memory_knowledge.parsers.php_adapter import parse_php_file
from memory_knowledge.parsers.sql_adapter import parse_sql_file


# --- Python route extraction ---

PYTHON_FLASK = '''\
from flask import Flask
app = Flask(__name__)

@app.route('/users')
def list_users():
    return []

@app.get('/users/<int:id>')
async def get_user(id: int):
    return {}
'''


def test_python_flask_routes():
    output = parse_python_file("app.py", PYTHON_FLASK)
    assert len(output.routes) == 2
    assert output.routes[0].path == "/users"
    assert output.routes[0].method == "GET"
    assert output.routes[1].path == "/users/<int:id>"
    assert output.routes[1].method == "GET"


PYTHON_FASTAPI = '''\
from fastapi import APIRouter
router = APIRouter()

@router.get('/items')
async def list_items():
    return []

@router.post('/items')
async def create_item():
    return {}
'''


def test_python_fastapi_routes():
    output = parse_python_file("api.py", PYTHON_FASTAPI)
    assert len(output.routes) == 2
    methods = {r.method for r in output.routes}
    assert methods == {"GET", "POST"}


# --- Python docblock extraction ---

PYTHON_DOC = '''\
"""Module-level docstring."""

def foo():
    """Foo does something."""
    pass

class Bar:
    """Bar class documentation."""
    pass
'''


def test_python_doc_blocks():
    output = parse_python_file("doc.py", PYTHON_DOC)
    assert len(output.doc_blocks) >= 2
    module_doc = next((d for d in output.doc_blocks if d.symbol_name is None), None)
    assert module_doc is not None
    assert "Module-level" in module_doc.text
    foo_doc = next((d for d in output.doc_blocks if d.symbol_name == "foo"), None)
    assert foo_doc is not None
    assert "Foo does something" in foo_doc.text


# --- TypeScript route extraction ---

TS_EXPRESS = '''\
import express from 'express';
const app = express();

app.get('/api/users', (req, res) => {
    res.json([]);
});

app.post('/api/users', (req, res) => {
    res.json({});
});
'''


def test_ts_express_routes():
    output = parse_typescript_file("server.ts", TS_EXPRESS)
    assert len(output.routes) == 2
    paths = {r.path for r in output.routes}
    assert "/api/users" in paths


# --- TypeScript JSDoc extraction ---

TS_JSDOC = '''\
/**
 * Creates a new user
 * @param name - the user name
 */
function createUser(name) {
    return { name };
}
'''


def test_ts_jsdoc():
    output = parse_typescript_file("user.ts", TS_JSDOC)
    assert len(output.doc_blocks) >= 1
    assert "Creates a new user" in output.doc_blocks[0].text


# --- C# route extraction ---

CS_ROUTES = '''\
[HttpGet("api/users")]
public IActionResult GetUsers() { }

[HttpPost("api/users")]
public IActionResult CreateUser() { }

[Route("api/[controller]")]
public class UsersController { }
'''


def test_csharp_routes():
    output = parse_csharp_file("UsersController.cs", CS_ROUTES)
    assert len(output.routes) >= 2
    methods = {r.method for r in output.routes}
    assert "GET" in methods
    assert "POST" in methods


# --- C# XML doc extraction ---

CS_DOC = '''\
/// <summary>
/// Represents a user entity
/// </summary>
public class User { }
'''


def test_csharp_xml_doc():
    output = parse_csharp_file("User.cs", CS_DOC)
    assert len(output.doc_blocks) >= 1
    assert "Represents a user entity" in output.doc_blocks[0].text


# --- PHP route extraction ---

PHP_LARAVEL = r"""<?php
Route::get('/users', 'UserController@index');
Route::post('/users', 'UserController@store');
"""


def test_php_laravel_routes():
    output = parse_php_file("routes.php", PHP_LARAVEL)
    assert len(output.routes) == 2
    paths = {r.path for r in output.routes}
    assert "/users" in paths


# --- SQL DML extraction ---

SQL_DML = """\
CREATE TABLE users (id INT, name VARCHAR(100));

SELECT u.name, o.total
FROM users u
JOIN orders o ON o.user_id = u.id;

INSERT INTO audit_log (action, user_id) VALUES ('login', 1);

UPDATE users SET name = 'foo' WHERE id = 1;

DELETE FROM sessions WHERE expired = true;
"""


def test_sql_dml_refs():
    output = parse_sql_file("queries.sql", SQL_DML)
    assert len(output.sql_refs) >= 4
    names = {r.object_name.lower() for r in output.sql_refs}
    assert "users" in names
    assert "orders" in names
    assert "audit_log" in names
    assert "sessions" in names


def test_sql_dml_operations():
    output = parse_sql_file("queries.sql", SQL_DML)
    ops = {(r.object_name.lower(), r.operation) for r in output.sql_refs}
    assert ("users", "select") in ops
    assert ("audit_log", "insert") in ops
    assert ("users", "update") in ops
    assert ("sessions", "delete") in ops


# --- Default fields ---

def test_new_fields_have_defaults():
    output = parse_sql_file("empty.sql", "")
    assert output.routes == []
    assert output.sql_refs == []
    assert output.doc_blocks == []
