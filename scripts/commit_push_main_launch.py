#!/usr/bin/env python3
"""Open the minimal commit-and-push interview with no caller arguments."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

try:
    from scripts import minimal_git_publish
except ModuleNotFoundError:  # direct script execution
    import minimal_git_publish  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_REGISTRY_ENV = "MK_REPO_ROOTS_FILE"
PYTEST_WRAPPER = Path("scripts/run_pytest.sh")


class InterviewError(ValueError):
    """The operator response did not satisfy the displayed contract."""


class InterviewCancelled(InterviewError):
    """The operator declined the reviewed remote effect."""


def _repository_choices() -> list[tuple[str, Path]]:
    choices: dict[str, Path] = {"memory-knowledge": ROOT.resolve()}
    source = Path(
        os.environ.get(
            REPOSITORY_REGISTRY_ENV,
            "~/.config/memory-knowledge/repositories.json",
        )
    ).expanduser()
    if source.is_file():
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise InterviewError("repository registry must be a JSON object")
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise InterviewError("repository registry entries must be string pairs")
            if key == "memory-knowledge":
                continue
            candidate = Path(value).expanduser().resolve()
            if candidate.is_dir() and not minimal_git_publish._git(
                candidate, "rev-parse", "--is-inside-work-tree", check=False
            ).returncode:
                choices[key] = candidate
    return sorted(choices.items())


def _select_one(
    title: str,
    options: Sequence[str],
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> int:
    output_fn(title)
    for index, option in enumerate(options, start=1):
        output_fn(f"{index}. {option}")
    raw = input_fn(f"Choose 1-{len(options)}: ").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(options):
        raise InterviewError(f"choose one number from 1 to {len(options)}")
    return int(raw) - 1


def _select_many(
    title: str,
    options: Sequence[str],
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> list[str]:
    output_fn(title)
    for index, option in enumerate(options, start=1):
        output_fn(f"{index}. {option}")
    raw = input_fn("Choose comma-separated numbers: ").strip()
    pieces = [piece.strip() for piece in raw.split(",") if piece.strip()]
    if not pieces or any(not piece.isdigit() for piece in pieces):
        raise InterviewError("choose one or more comma-separated numbers")
    indexes = [int(piece) for piece in pieces]
    if len(set(indexes)) != len(indexes) or any(
        index < 1 or index > len(options) for index in indexes
    ):
        raise InterviewError(
            f"choose unique numbers between 1 and {len(options)}"
        )
    return [options[index - 1] for index in indexes]


def _required(
    prompt: str, *, input_fn: Callable[[str], str]
) -> str:
    value = input_fn(prompt).strip()
    if not value:
        raise InterviewError(f"{prompt.rstrip(': ')} is required")
    return value


def _defaulted(
    prompt: str, default: str, *, input_fn: Callable[[str], str]
) -> str:
    return input_fn(f"{prompt} [{default}]: ").strip() or default


def _current_branch(repo: Path) -> str:
    branch = minimal_git_publish._git(repo, "branch", "--show-current").stdout.strip()
    if not branch:
        raise InterviewError("selected repository has a detached HEAD")
    return branch


def _verification_command(repo: Path, text: str) -> list[str]:
    """Bind pytest verification to the selected repository's managed runtime."""

    command = shlex.split(text)
    if not command:
        raise InterviewError("focused verification command is empty")

    executable = Path(command[0]).name
    pytest_arguments: list[str] | None = None
    if (
        re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable)
        and command[1:3] == ["-m", "pytest"]
    ):
        pytest_arguments = command[3:]
    elif executable == "pytest":
        pytest_arguments = command[1:]
    elif command[:3] == ["uv", "run", "pytest"]:
        pytest_arguments = command[3:]

    if pytest_arguments is None:
        return command

    wrapper = repo / PYTEST_WRAPPER
    if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
        raise InterviewError(
            "pytest verification requires the selected repository's executable "
            f"{PYTEST_WRAPPER.as_posix()} wrapper"
        )
    return [PYTEST_WRAPPER.as_posix(), *pytest_arguments]


def _run_interview(
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> dict[str, object]:
    operation_index = _select_one(
        "Operation",
        ["Dry run", "Commit and push"],
        input_fn=input_fn,
        output_fn=output_fn,
    )
    execute = operation_index == 1

    repositories = _repository_choices()
    repository_index = _select_one(
        "Repository",
        [f"{key} — {path}" for key, path in repositories],
        input_fn=input_fn,
        output_fn=output_fn,
    )
    repository_key, repo = repositories[repository_index]

    changes = minimal_git_publish.changed_paths(repo)
    if not changes:
        raise InterviewError("selected repository has no changes to publish")
    paths = _select_many(
        "Changed paths",
        changes,
        input_fn=input_fn,
        output_fn=output_fn,
    )

    verification_text = _required(
        "Focused verification command: ", input_fn=input_fn
    )
    verification = _verification_command(repo, verification_text)
    branch = _defaulted(
        "Branch", _current_branch(repo), input_fn=input_fn
    )
    remote = _defaulted("Remote", "origin", input_fn=input_fn)
    message = (
        _required("Commit message: ", input_fn=input_fn)
        if execute
        else ""
    )

    output_fn("Prepared operation")
    output_fn(f"Operation: {'commit and push' if execute else 'dry run'}")
    output_fn(f"Repository: {repository_key} — {repo}")
    output_fn(f"Branch: {branch}")
    output_fn(f"Remote: {remote}")
    output_fn("Paths:")
    for path in paths:
        output_fn(f"- {path}")
    output_fn(f"Verification: {shlex.join(verification)}")
    if execute:
        output_fn(f"Commit message: {message}")
        authorization = _select_one(
            "Authorize the prepared remote effect",
            ["No", "Yes"],
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if authorization != 1:
            raise InterviewCancelled("commit and push declined")

    with tempfile.TemporaryDirectory(prefix="commit-push-manifest-") as temporary:
        manifest = Path(temporary) / "manifest.json"
        manifest.write_text(json.dumps(paths), encoding="utf-8")
        return minimal_git_publish.publish(
            repo=repo,
            manifest=manifest,
            verification=verification,
            message=message,
            branch=branch,
            remote=remote,
            execute=execute,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values:
        print(json.dumps({
            "ok": False,
            "error": "no-argument-entrypoint-required",
        }, sort_keys=True), file=sys.stderr)
        return 2
    read = input_fn or input
    write = output_fn or print
    try:
        result = _run_interview(input_fn=read, output_fn=write)
        write(json.dumps(result, sort_keys=True))
        return 0
    except InterviewCancelled as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 130
    except (
        InterviewError,
        minimal_git_publish.PublishError,
        OSError,
        json.JSONDecodeError,
        EOFError,
        KeyboardInterrupt,
    ) as exc:
        print(json.dumps({
            "ok": False,
            "error": str(exc) or type(exc).__name__,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
