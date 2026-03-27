from __future__ import annotations

import os
from collections.abc import Callable

from memory_knowledge.parsers.base import FileParseOutput

# Extension → (module, function_name) mapping
# Lazy imports avoid loading tree-sitter until needed
_EXTENSION_MAP: dict[str, tuple[str, str]] = {
    ".py": ("memory_knowledge.parsers.python_adapter", "parse_python_file"),
    ".ts": ("memory_knowledge.parsers.typescript_adapter", "parse_typescript_file"),
    ".tsx": ("memory_knowledge.parsers.typescript_adapter", "parse_typescript_file"),
    ".js": ("memory_knowledge.parsers.typescript_adapter", "parse_typescript_file"),
    ".jsx": ("memory_knowledge.parsers.typescript_adapter", "parse_typescript_file"),
    ".cs": ("memory_knowledge.parsers.csharp_adapter", "parse_csharp_file"),
    ".php": ("memory_knowledge.parsers.php_adapter", "parse_php_file"),
    ".sql": ("memory_knowledge.parsers.sql_adapter", "parse_sql_file"),
}

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".cs": "csharp",
    ".php": "php",
    ".sql": "sql",
}


def _unsupported_parser(file_path: str, source: str) -> FileParseOutput:
    """Fallback parser for unsupported file types."""
    return FileParseOutput(
        file_path=file_path,
        language="unknown",
        parse_error=f"Unsupported file type: {os.path.splitext(file_path)[1]}",
    )


def get_parser(file_path: str) -> Callable[[str, str], FileParseOutput]:
    """Get the appropriate parser function for a file based on its extension."""
    ext = os.path.splitext(file_path)[1].lower()
    entry = _EXTENSION_MAP.get(ext)
    if entry is None:
        return _unsupported_parser

    module_path, func_name = entry
    try:
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ImportError, AttributeError):
        return _unsupported_parser


def detect_language(file_path: str) -> str:
    """Detect the language from a file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return _EXTENSION_TO_LANGUAGE.get(ext, "unknown")


def get_import_resolver(
    language: str,
) -> Callable[[str, dict[str, int], dict[str, str]], tuple[int, str] | None] | None:
    """Get the import resolver for a language. Returns None if no file-based imports."""
    if language == "python":
        return _resolve_python_import
    if language in ("typescript", "javascript"):
        return _resolve_ts_import
    return None  # C#, SQL have no file-based import resolution


def _resolve_python_import(
    module_path: str,
    file_path_to_file_id: dict[str, int],
    file_path_to_entity_key: dict[str, str],
) -> tuple[int, str] | None:
    """Resolve a Python import module path to a file_id + entity_key."""
    candidates = [
        module_path.replace(".", "/") + ".py",
        module_path.replace(".", "/") + "/__init__.py",
    ]
    for candidate in candidates:
        for known_path in file_path_to_file_id:
            if known_path.endswith(candidate):
                return (
                    file_path_to_file_id[known_path],
                    file_path_to_entity_key[known_path],
                )
    return None


def _resolve_ts_import(
    import_path: str,
    file_path_to_file_id: dict[str, int],
    file_path_to_entity_key: dict[str, str],
) -> tuple[int, str] | None:
    """Resolve a TypeScript/JS import path to a file_id + entity_key."""
    # Only resolve relative imports (./foo, ../bar)
    if not import_path.startswith("."):
        return None  # npm package — skip

    # Strip leading ./ or ../ prefixes properly (not character-based lstrip)
    clean = import_path
    while clean.startswith("../"):
        clean = clean[3:]
    if clean.startswith("./"):
        clean = clean[2:]

    # Try with various extensions
    suffixes = [".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"]
    for suffix in suffixes:
        candidate = clean + suffix
        for known_path in file_path_to_file_id:
            if known_path.endswith(candidate):
                return (
                    file_path_to_file_id[known_path],
                    file_path_to_entity_key[known_path],
                )
    return None
