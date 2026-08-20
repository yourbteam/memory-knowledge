#!/usr/bin/env python3
"""Publish an exact Git manifest through five explicit boundaries."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping, Sequence


class PublishError(RuntimeError):
    """The publish stopped before its next unsafe effect."""


def _run(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    try:
        return subprocess.run(
            list(argv),
            cwd=cwd,
            env=process_env,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise PublishError(f"cannot run {argv[0]}: {exc}") from exc


def _git(
    repo: Path,
    *args: str,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = _run(["git", "-C", str(repo), *args], env=env)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise PublishError(f"git {' '.join(args)} failed: {detail}")
    return result


def changed_paths(repo: Path) -> list[str]:
    tracked = _git(repo, "diff", "--name-only", "-z", "HEAD", "--").stdout
    untracked = _git(
        repo, "ls-files", "--others", "--exclude-standard", "-z"
    ).stdout
    return sorted({
        item
        for item in (*tracked.split("\0"), *untracked.split("\0"))
        if item
    })


def manifest_paths(repo: Path, manifest: Path) -> list[str]:
    try:
        values = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"manifest is not readable JSON: {exc}") from exc
    if not isinstance(values, list) or not values:
        raise PublishError("manifest must be a non-empty JSON list")

    paths: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise PublishError("every manifest entry must be a non-empty string")
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise PublishError(f"manifest entry escapes repository: {value}")
        normalized = candidate.as_posix()
        resolved = (repo / candidate).resolve()
        try:
            resolved.relative_to(repo.resolve())
        except ValueError as exc:
            raise PublishError(f"manifest entry escapes repository: {value}") from exc
        if normalized in paths:
            raise PublishError(f"duplicate manifest entry: {normalized}")
        tracked = _git(
            repo, "ls-files", "--error-unmatch", "--", normalized, check=False
        ).returncode == 0
        if not resolved.is_file() and not tracked:
            raise PublishError(
                f"manifest entry is neither present nor tracked: {normalized}"
            )
        paths.append(normalized)
    return paths


def _staged_paths(
    repo: Path, *, env: Mapping[str, str] | None = None
) -> list[str]:
    output = _git(
        repo, "diff", "--cached", "--name-only", "-z", env=env
    ).stdout
    return sorted(item for item in output.split("\0") if item)


def _validate_repo(repo: Path, branch: str, remote: str) -> str:
    if not repo.is_dir():
        raise PublishError(f"repository does not exist: {repo}")
    top = Path(_git(repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top != repo:
        raise PublishError(f"repository path must be its worktree root: {repo}")
    current = _git(repo, "branch", "--show-current").stdout.strip()
    if current != branch:
        raise PublishError(
            f"branch mismatch: expected {branch}, found {current or '<detached>'}"
        )
    remote_url = _git(repo, "remote", "get-url", remote).stdout.strip()
    if _staged_paths(repo):
        raise PublishError("index is not empty before publish")
    return remote_url


def _validate_changed_scope(repo: Path, paths: Sequence[str]) -> None:
    changed = set(changed_paths(repo))
    unchanged = sorted(set(paths) - changed)
    if unchanged:
        raise PublishError(f"manifest paths have no change to publish: {unchanged}")


def _run_verification(
    repo: Path,
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    if not command:
        raise PublishError("verification command must not be empty")
    result = _run(command, cwd=repo, env=env)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise PublishError(
            f"verification command exited {result.returncode}: {detail}"
        )
    return {
        "command": list(command),
        "exit": result.returncode,
        "passed": True,
    }


def _stage_and_verify(
    repo: Path,
    paths: Sequence[str],
    verification: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    _git(repo, "add", "--", *paths, env=env)
    staged = _staged_paths(repo, env=env)
    if staged != sorted(paths):
        raise PublishError(f"staged paths differ from manifest: {staged}")
    _git(repo, "diff", "--cached", "--check", "--", *paths, env=env)
    # The temporary Git environment is only for mechanical staging. Passing it
    # into a test runner would redirect every nested Git command, including Git
    # commands run in disposable repositories created by the tests.
    verified = _run_verification(repo, verification)
    staged_after = _staged_paths(repo, env=env)
    if staged_after != sorted(paths):
        raise PublishError(
            f"staged paths differ after verification: {staged_after}"
        )
    selected_worktree_changes = _git(
        repo, "diff", "--name-only", "-z", "--", *paths, env=env
    ).stdout
    if any(selected_worktree_changes.split("\0")):
        raise PublishError("verification changed selected files after staging")
    _git(repo, "diff", "--cached", "--check", "--", *paths, env=env)
    return verified


@contextmanager
def _temporary_index(repo: Path) -> Iterator[dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="publish-index-") as temporary:
        temporary_root = Path(temporary)
        index = temporary_root / "index"
        object_directory = temporary_root / "objects"
        object_directory.mkdir()

        real_objects = Path(
            _git(repo, "rev-parse", "--git-path", "objects").stdout.strip()
        )
        if not real_objects.is_absolute():
            real_objects = repo / real_objects
        alternates = [str(real_objects.resolve())]
        inherited_alternates = os.environ.get("GIT_ALTERNATE_OBJECT_DIRECTORIES")
        if inherited_alternates:
            alternates.append(inherited_alternates)

        env = {
            "GIT_INDEX_FILE": str(index),
            "GIT_OBJECT_DIRECTORY": str(object_directory),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.pathsep.join(alternates),
        }
        _git(repo, "read-tree", "HEAD", env=env)
        yield env


def _committed_paths(repo: Path, commit: str) -> list[str]:
    output = _git(
        repo,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-z",
        commit,
    ).stdout
    return sorted(item for item in output.split("\0") if item)


def _fresh_remote_confirmation(remote_url: str, branch: str) -> str:
    with tempfile.TemporaryDirectory(prefix="publish-confirm-") as temporary:
        reader = Path(temporary) / "reader"
        cloned = _run([
            "git",
            "clone",
            "--quiet",
            "--no-checkout",
            "--single-branch",
            "--branch",
            branch,
            "--depth",
            "1",
            remote_url,
            str(reader),
        ])
        if cloned.returncode:
            detail = cloned.stderr.strip() or cloned.stdout.strip() or "no output"
            raise PublishError(f"fresh remote confirmation failed: {detail}")
        return _git(reader, "rev-parse", "HEAD").stdout.strip()


def publish(
    *,
    repo: Path,
    manifest: Path,
    verification: Sequence[str],
    message: str,
    branch: str,
    remote: str,
    execute: bool,
) -> dict[str, object]:
    repo = repo.expanduser().resolve()
    if execute and not message.strip():
        raise PublishError("commit message must not be empty")
    remote_url = _validate_repo(repo, branch, remote)
    paths = manifest_paths(repo, manifest)
    _validate_changed_scope(repo, paths)

    if not execute:
        with _temporary_index(repo) as env:
            verified = _stage_and_verify(
                repo, paths, verification, env=env
            )
        if _staged_paths(repo):
            raise PublishError("dry run changed the real index")
        return {
            "ok": True,
            "mode": "dry-run",
            "repo": str(repo),
            "branch": branch,
            "remote": remote,
            "paths": list(paths),
            "verification": verified,
        }

    committed = False
    commit = ""
    try:
        verified = _stage_and_verify(repo, paths, verification)
        _git(repo, "commit", "-m", message)
        committed = True
        commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
        committed_scope = _committed_paths(repo, commit)
        if committed_scope != sorted(paths):
            raise PublishError(
                f"committed paths differ from manifest: {committed_scope}"
            )

        pushed = _git(
            repo,
            "push",
            remote,
            f"HEAD:refs/heads/{branch}",
            check=False,
        )
        if pushed.returncode:
            detail = pushed.stderr.strip() or pushed.stdout.strip() or "no output"
            raise PublishError(f"git push failed: {detail}")

        remote_commit = _fresh_remote_confirmation(remote_url, branch)
        if remote_commit != commit:
            raise PublishError(
                f"remote confirmation mismatch: local {commit}, remote {remote_commit}"
            )
        if _staged_paths(repo):
            raise PublishError("index is not empty after publish")
        return {
            "ok": True,
            "mode": "publish",
            "repo": str(repo),
            "branch": branch,
            "remote": remote,
            "paths": list(paths),
            "commit": commit,
            "remote_commit": remote_commit,
            "verification": verified,
        }
    except PublishError as exc:
        if not committed:
            # Preflight proved the real index was empty. Reset the complete index
            # so a verification command cannot leave an out-of-manifest stage.
            _git(repo, "reset", "--quiet", check=False)
            raise
        raise PublishError(f"{exc}; local commit {commit} remains at HEAD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--verification-command", required=True)
    parser.add_argument("--message", default="")
    parser.add_argument("--branch", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(
            list(sys.argv[1:] if argv is None else argv)
        )
        verification = shlex.split(args.verification_command)
        result = publish(
            repo=args.repo,
            manifest=args.manifest,
            verification=verification,
            message=args.message,
            branch=args.branch,
            remote=args.remote,
            execute=args.execute,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except PublishError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
