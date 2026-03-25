from __future__ import annotations

import ast

import structlog

from memory_knowledge.parsers.base import FileParseOutput, SymbolInfo

logger = structlog.get_logger()


def parse_python_file(file_path: str, source: str) -> FileParseOutput:
    """Parse Python source using ast. Returns symbols or records parse_error."""
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        logger.warning("python_parse_error", file_path=file_path, error=str(e))
        return FileParseOutput(
            file_path=file_path, language="python", parse_error=str(e)
        )

    symbols: list[SymbolInfo] = []
    for node in ast.walk(tree):
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
    return FileParseOutput(
        file_path=file_path, language="python", symbols=symbols
    )


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
