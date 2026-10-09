#!/usr/bin/env python3
"""Prompt for a bounded Atlas compiler index operation, then dispatch its existing CLI."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from typing import Callable, Sequence


class LaunchError(ValueError):
    pass


class LaunchCancelled(Exception):
    pass


def _prompt(label: str, input_fn: Callable[[str], str]) -> str:
    try:
        value = input_fn(label)
    except (EOFError, KeyboardInterrupt) as exc:
        raise LaunchCancelled from exc
    value = value.strip()
    if not value:
        raise LaunchCancelled
    return value


def _existing_checkout(value: str) -> Path:
    path = Path(value).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LaunchError(f"checkout path does not exist: {value!r}") from exc
    if not resolved.is_dir() or not (resolved / ".git").exists():
        raise LaunchError(f"checkout must be an existing Git worktree: {value!r}")
    return resolved


def _existing_database(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink():
        raise LaunchError("database path must not be a symbolic link")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LaunchError(f"database file does not exist: {value!r}") from exc
    if not resolved.is_file():
        raise LaunchError(f"database path must name an existing regular file: {value!r}")
    return resolved


def _project_path(checkout: Path, value: str) -> str:
    if "\\" in value or value.startswith("/"):
        raise LaunchError("project must be a safe repository-relative .csproj path")
    parts = value.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts) or PurePosixPath(value).is_absolute():
        raise LaunchError("project must be a safe repository-relative .csproj path")
    if not value.endswith(".csproj"):
        raise LaunchError("project must end in .csproj")
    lexical = checkout.joinpath(*parts)
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise LaunchError(f"project file does not exist in checkout: {value!r}") from exc
    try:
        relative = resolved.relative_to(checkout)
    except ValueError as exc:
        raise LaunchError(f"project resolves outside checkout: {value!r}") from exc
    if not resolved.is_file() or relative.as_posix() != value:
        raise LaunchError(f"project must be a regular in-checkout file at its supplied path: {value!r}")
    return value


def _framework(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", value):
        raise LaunchError("framework must be a target-framework moniker such as net8.0")
    return value


def _usable_dotnet(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return None
    if resolved.is_file() and os.access(resolved, os.X_OK):
        return resolved
    return None


def _default_dotnet(environment: dict[str, str]) -> Path | None:
    configured = _usable_dotnet(environment.get("ATLAS_DOTNET"))
    if configured is not None:
        return configured
    return _usable_dotnet(shutil.which("dotnet", path=environment.get("PATH")))


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    environment: dict[str, str] | None = None,
    atlas_script: Path | None = None,
) -> int:
    """Collect inputs in order; invalid input or cancellation never starts Atlas."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("compiler_index_launch.py accepts no command-line arguments", file=sys.stderr)
        return 2
    env = dict(os.environ if environment is None else environment)
    try:
        checkout = _existing_checkout(_prompt("Repository checkout path: ", input_fn))
        database = _existing_database(_prompt("Atlas database path: ", input_fn))
        project = _project_path(checkout, _prompt("Repository-relative project path: ", input_fn))
        framework = _framework(_prompt("Target framework moniker: ", input_fn))
        dotnet = _default_dotnet(env)
        if dotnet is None:
            dotnet = _usable_dotnet(_prompt("Path to executable dotnet SDK host: ", input_fn))
            if dotnet is None:
                raise LaunchError("SDK host must be an existing executable file")
        script = (atlas_script or Path(__file__).resolve().with_name("atlas.py")).resolve(strict=True)
        if not script.is_file():
            raise LaunchError("Atlas CLI script is missing")
        env["ATLAS_DOTNET"] = dotnet.as_posix()
        command = [sys.executable, script.as_posix(), "compiler-index", "--repo", checkout.as_posix(),
                   "--db", database.as_posix(), "--project", project, "--framework", framework]
        result = runner(command, env=env, check=False)
        return int(result.returncode)
    except LaunchCancelled:
        print("Cancelled; compiler indexing was not started.", file=sys.stderr)
        return 130
    except LaunchError as exc:
        print(f"compiler-index launch refused: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"compiler-index launch failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
