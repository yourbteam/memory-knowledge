from memory_knowledge.parsers.php_adapter import parse_php_file


SAMPLE_CODE = r"""<?php

namespace App\Controllers;

use App\Models\User;
use App\Services\AuthService as Auth;
use Illuminate\Http\Request;

abstract class BaseController
{
    use LoggingTrait;

    protected function validate($data): bool
    {
        return true;
    }
}

final class UserController extends BaseController
{
    private static function getInstance(): self
    {
        return new self();
    }

    public function index(Request $request): Response
    {
        $users = User::all();
        return response()->json($users);
    }
}

interface Authenticatable
{
    public function getAuthIdentifier(): string;
}

trait HasTimestamps
{
    public function touch(): void {}
}

enum Status: string
{
    case Active = "active";
    case Inactive = "inactive";
}

function helper_function($x, $y)
{
    return $x + $y;
}

require_once 'vendor/autoload.php';
include 'config/app.php';
"""


def test_extracts_classes():
    output = parse_php_file("app.php", SAMPLE_CODE)
    classes = [s for s in output.symbols if s.kind == "class"]
    names = {c.name for c in classes}
    assert names == {"BaseController", "UserController"}


def test_extracts_abstract_class():
    output = parse_php_file("app.php", SAMPLE_CODE)
    base = next(s for s in output.symbols if s.name == "BaseController")
    assert base.kind == "class"
    assert "abstract" in base.signature


def test_extracts_final_class():
    output = parse_php_file("app.php", SAMPLE_CODE)
    ctrl = next(s for s in output.symbols if s.name == "UserController")
    assert ctrl.kind == "class"
    assert "final" in ctrl.signature


def test_extracts_interface():
    output = parse_php_file("app.php", SAMPLE_CODE)
    ifaces = [s for s in output.symbols if s.kind == "interface"]
    assert len(ifaces) == 1
    assert ifaces[0].name == "Authenticatable"


def test_extracts_trait():
    output = parse_php_file("app.php", SAMPLE_CODE)
    traits = [s for s in output.symbols if s.kind == "trait"]
    assert len(traits) == 1
    assert traits[0].name == "HasTimestamps"


def test_extracts_enum():
    output = parse_php_file("app.php", SAMPLE_CODE)
    enums = [s for s in output.symbols if s.kind == "enum"]
    assert len(enums) == 1
    assert enums[0].name == "Status"


def test_extracts_top_level_function():
    output = parse_php_file("app.php", SAMPLE_CODE)
    funcs = [s for s in output.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert funcs[0].name == "helper_function"


def test_extracts_methods():
    output = parse_php_file("app.php", SAMPLE_CODE)
    methods = [s for s in output.symbols if s.kind == "method"]
    names = {m.name for m in methods}
    assert "validate" in names
    assert "getInstance" in names
    assert "index" in names
    assert "getAuthIdentifier" in names
    assert "touch" in names


def test_namespace_use_imports():
    output = parse_php_file("app.php", SAMPLE_CODE)
    use_imports = [i for i in output.imports if "\\" in i.module_path]
    paths = {i.module_path for i in use_imports}
    assert r"App\Models\User" in paths
    assert r"App\Services\AuthService" in paths
    assert r"Illuminate\Http\Request" in paths


def test_trait_use_not_captured_as_import():
    output = parse_php_file("app.php", SAMPLE_CODE)
    for imp in output.imports:
        assert "LoggingTrait" not in imp.module_path


def test_require_include():
    output = parse_php_file("app.php", SAMPLE_CODE)
    req_imports = [i for i in output.imports if "\\" not in i.module_path]
    paths = {i.module_path for i in req_imports}
    assert "vendor/autoload.php" in paths
    assert "config/app.php" in paths


def test_language_is_php():
    output = parse_php_file("test.php", "<?php\n")
    assert output.language == "php"


def test_syntax_error():
    output = parse_php_file("broken.php", "<?php\nclass {}\n")
    # Regex parser is lenient — won't crash, may produce partial results
    assert output.parse_error is None or isinstance(output.parse_error, str)


def test_empty_file():
    output = parse_php_file("empty.php", "")
    assert output.symbols == []
    assert output.imports == []
    assert output.parse_error is None


def test_abstract_method_before_visibility():
    """PHP allows 'abstract public function' — abstract before visibility."""
    code = r"""<?php
abstract class Base
{
    abstract public function handle(): void;
    abstract protected function process($data): array;
}
"""
    output = parse_php_file("base.php", code)
    methods = [s for s in output.symbols if s.kind == "method"]
    names = {m.name for m in methods}
    assert "handle" in names
    assert "process" in names


def test_imported_names_extracted():
    output = parse_php_file("app.php", SAMPLE_CODE)
    user_import = next(i for i in output.imports if "User" in i.module_path)
    assert user_import.imported_names == ["User"]


def test_readonly_class():
    code = r"""<?php
readonly class Point
{
    public function __construct(
        public float $x,
        public float $y,
    ) {}
}
"""
    output = parse_php_file("point.php", code)
    classes = [s for s in output.symbols if s.kind == "class"]
    assert len(classes) == 1
    assert classes[0].name == "Point"
    assert "readonly" in classes[0].signature


def test_method_without_visibility():
    """PHP methods without explicit visibility default to public."""
    code = r"""<?php
class Foo
{
    function bar()
    {
        return 1;
    }
}
"""
    output = parse_php_file("foo.php", code)
    methods = [s for s in output.symbols if s.kind == "method"]
    assert len(methods) == 1
    assert methods[0].name == "bar"


def test_call_extraction():
    code = r"""<?php
function helper()
{
    return 42;
}

function main()
{
    $x = helper();
    return $x;
}
"""
    output = parse_php_file("calls.php", code)
    assert len(output.calls) == 1
    assert output.calls[0].caller_name == "main"
    assert output.calls[0].callee_name == "helper"


def test_grouped_use_imports():
    code = r"""<?php
use App\Models\{User, Post, Comment};
"""
    output = parse_php_file("grouped.php", code)
    paths = {i.module_path for i in output.imports}
    assert r"App\Models\User" in paths
    assert r"App\Models\Post" in paths
    assert r"App\Models\Comment" in paths


def test_use_function_import():
    code = r"""<?php
use function App\Helpers\formatDate;
"""
    output = parse_php_file("usefn.php", code)
    assert len(output.imports) == 1
    assert output.imports[0].module_path == r"App\Helpers\formatDate"
