from __future__ import annotations

import ast
import re
import sys

import structlog

from memory_knowledge.parsers.base import (
    CallInfo,
    DocBlock,
    FileParseOutput,
    ImportInfo,
    RouteInfo,
    SymbolInfo,
)

logger = structlog.get_logger()

# Stdlib module names for filtering (Python 3.10+)
_STDLIB_NAMES: set[str] = getattr(sys, "stdlib_module_names", set())


def parse_python_file(file_path: str, source: str) -> FileParseOutput:
    """Parse Python source using ast. Returns symbols, imports, and calls."""
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        logger.warning("python_parse_error", file_path=file_path, error=str(e))
        return FileParseOutput(
            file_path=file_path, language="python", parse_error=str(e)
        )

    # Extract top-level symbols (module-level functions and classes)
    symbols: list[SymbolInfo] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = (
                "async_function"
                if isinstance(node, ast.AsyncFunctionDef)
                else "function"
            )
            sig = _extract_signature(node)
            symbols.append(
                SymbolInfo(
                    name=node.name,
                    kind=kind,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    signature=sig,
                )
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                SymbolInfo(
                    name=node.name,
                    kind="class",
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    signature=f"class {node.name}",
                )
            )

    # Extract imports (walk full tree — imports can be inside functions)
    imports = _extract_imports(tree)

    # Extract intra-file calls (only calls to known top-level symbols)
    calls = _extract_calls(tree, symbols)

    # Extract routes and doc blocks
    routes = _extract_routes(source)
    doc_blocks = _extract_doc_blocks(tree, symbols)

    return FileParseOutput(
        file_path=file_path,
        language="python",
        symbols=symbols,
        imports=imports,
        calls=calls,
        routes=routes,
        doc_blocks=doc_blocks,
    )


def _extract_imports(tree: ast.Module) -> list[ImportInfo]:
    """Extract import statements, filtering stdlib and relative imports."""
    imports: list[ImportInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_module = alias.name.split(".")[0]
                if top_module in _STDLIB_NAMES:
                    continue
                imports.append(
                    ImportInfo(
                        module_path=alias.name,
                        imported_names=[alias.asname or alias.name],
                        line_start=node.lineno,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            # Skip relative imports
            if node.level and node.level > 0:
                continue
            module = node.module or ""
            if not module:
                continue
            top_module = module.split(".")[0]
            if top_module in _STDLIB_NAMES:
                continue
            imports.append(
                ImportInfo(
                    module_path=module,
                    imported_names=[a.name for a in (node.names or [])],
                    line_start=node.lineno,
                )
            )
    return imports


def _extract_calls(
    tree: ast.Module, symbols: list[SymbolInfo]
) -> list[CallInfo]:
    """Extract intra-file function calls (only ast.Name calls to known symbols)."""
    known_names = {s.name for s in symbols}
    calls: list[CallInfo] = []

    for top_node in ast.iter_child_nodes(tree):
        if not isinstance(
            top_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        caller_name = top_node.name
        for child in ast.walk(top_node):
            if not isinstance(child, ast.Call):
                continue
            if not isinstance(child.func, ast.Name):
                continue  # skip attribute calls (self.foo(), obj.bar())
            callee = child.func.id
            if callee in known_names and callee != caller_name:
                calls.append(
                    CallInfo(
                        caller_name=caller_name,
                        callee_name=callee,
                        line_no=child.lineno,
                    )
                )
    return calls


_ROUTE_PATTERN = re.compile(
    r"@\w+\.(get|post|put|delete|patch|route|head|options)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


def _extract_routes(source: str) -> list[RouteInfo]:
    """Extract Flask/FastAPI route decorators."""
    routes: list[RouteInfo] = []
    lines = source.splitlines()
    for i, line in enumerate(lines):
        match = _ROUTE_PATTERN.search(line)
        if match:
            method = match.group(1).upper()
            if method == "ROUTE":
                method = "GET"  # Flask @app.route defaults to GET
            path = match.group(2)
            # Find the function name on the next non-decorator line
            handler = ""
            for j in range(i + 1, min(i + 5, len(lines))):
                func_match = re.match(r"\s*(?:async\s+)?def\s+(\w+)", lines[j])
                if func_match:
                    handler = func_match.group(1)
                    break
            routes.append(RouteInfo(method=method, path=path, handler_name=handler, line_start=i + 1))
    return routes


def _extract_doc_blocks(tree: ast.Module, symbols: list[SymbolInfo]) -> list[DocBlock]:
    """Extract docstrings from module and top-level symbols."""
    doc_blocks: list[DocBlock] = []
    # Module-level docstring
    module_doc = ast.get_docstring(tree)
    if module_doc:
        doc_blocks.append(DocBlock(symbol_name=None, text=module_doc, line_start=1))
    # Symbol docstrings
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                doc_blocks.append(DocBlock(symbol_name=node.name, text=doc, line_start=node.lineno))
    return doc_blocks


def _extract_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    """Build a signature string from the AST node."""
    args = []
    for arg in node.args.args:
        annotation = ""
        if arg.annotation:
            annotation = f": {ast.unparse(arg.annotation)}"
        args.append(f"{arg.arg}{annotation}")
    prefix = (
        "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    )
    ret = ""
    if node.returns:
        ret = f" -> {ast.unparse(node.returns)}"
    return f"{prefix} {node.name}({', '.join(args)}){ret}"
