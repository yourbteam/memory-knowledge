#!/usr/bin/env python3
"""Commit and push an explicitly listed Git path scope without staging other work."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

try:
    from scripts import (
        prevention_source_receipt,
        script_intake,
        sequence_intake_adapters,
        work_memory,
    )
except ModuleNotFoundError:  # direct script execution
    import prevention_source_receipt
    import script_intake
    import sequence_intake_adapters
    import work_memory


class PublishError(RuntimeError):
    """A safe, operator-actionable publish failure."""


EFFECT_AUTHORIZATION_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        {
            "id": "authorize",
            "prompt": "Authorize the reviewed commit or push operation now",
            "response_format": "One yes or no answer.",
            "example": "no",
            "constraints": (
                "Answer yes only after reviewing the prepared operation, "
                "repository, branch, remote, and file scope shown above."
            ),
            "type": "boolean",
            "required": True,
        },
    ],
}


def _bind_prevention_trailers(
    message: str, effect_id: str | None, preparation_sha256: str | None,
) -> str:
    if not effect_id and not preparation_sha256:
        return message
    if not effect_id or not preparation_sha256:
        raise PublishError("incomplete prevention effect identity")
    trailers = {
        "Prevention-Effect-ID": effect_id,
        "Prevention-Preparation-SHA256": preparation_sha256,
    }
    existing = {}
    for line in message.splitlines():
        for name in trailers:
            prefix = f"{name}:"
            if line.startswith(prefix):
                existing[name] = line[len(prefix):].strip()
    if existing and existing != trailers:
        raise PublishError("conflicting prevention commit identity")
    if existing == trailers:
        return message
    return message.rstrip() + "\n\n" + "\n".join(
        f"{name}: {value}" for name, value in trailers.items()
    )


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise PublishError(f"git {' '.join(args)} failed: {detail}")
    return result


def _manifest_paths(repo: Path, manifest: Path) -> list[str]:
    if not manifest.is_file():
        raise PublishError(f"manifest not found: {manifest}")
    text = manifest.read_text(encoding="utf-8")
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        decoded = None
    if decoded is not None:
        if (
            not isinstance(decoded, list) or not decoded
            or any(not isinstance(item, str) or not item for item in decoded)
        ):
            raise PublishError("manifest JSON must be a non-empty string list")
        rows = [(number, value) for number, value in enumerate(decoded, start=1)]
    else:
        # Bounded compatibility for existing checked sequence manifests. New
        # controller materialization is the canonical JSON-list producer.
        rows = list(enumerate(text.splitlines(), start=1))
    paths: list[str] = []
    for number, raw in rows:
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise PublishError(f"manifest line {number} escapes the repository: {value}")
        resolved = (repo / candidate).resolve()
        try:
            resolved.relative_to(repo)
        except ValueError as exc:
            raise PublishError(f"manifest line {number} escapes the repository: {value}") from exc
        normalized = candidate.as_posix()
        if normalized in paths:
            raise PublishError(f"duplicate manifest path: {normalized}")
        if resolved.is_dir():
            raise PublishError(f"manifest paths must name files, not directories: {normalized}")
        if not resolved.exists() and _git(repo, "ls-files", "--error-unmatch", "--", normalized, check=False).returncode:
            raise PublishError(f"manifest path is neither present nor tracked: {normalized}")
        paths.append(normalized)
    if not paths:
        raise PublishError("manifest contains no publish paths")
    return paths


def _nul_names(result: subprocess.CompletedProcess[str]) -> set[str]:
    return {value for value in result.stdout.split("\0") if value}


#: A repository declares its own suite here, one command on the first non-comment line. The
#: publisher never guesses a command: a guessed one that happens to exit 0 is worse than none,
#: because it reports a gate that ran nothing.
TEST_DECLARATION = ".publish-tests"


def _repo_test_command(repo: Path) -> list[str] | None:
    """The command this repository says proves itself, or None if it declares none."""

    declaration = repo / TEST_DECLARATION
    if not declaration.is_file():
        return None
    for line in declaration.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return ["bash", "-lc", stripped]
    return None


def _run_repo_tests(repo: Path) -> dict[str, object]:
    """Run the repository's declared suite and refuse the publish if it fails.

    Why this is here rather than in a git hook: on 2026-08-05 a check was added that fails the
    suite when a refusal carries no detail -- the defect that had killed two live runs that day.
    It was in the standard discovery path and would run whenever the suite ran, and nothing made
    the suite run: this repository has no git hooks and no continuous integration. A rule whose
    enforcement depends on somebody remembering to run it is the rule that was already broken.
    A local hook was the other candidate; it is skippable with --no-verify and absent from a
    fresh clone, and this publisher is the path every commit here actually takes.

    A repository with no `.publish-tests` publishes as before, and the result says so, so an
    ungated repository is visible rather than assumed safe.
    """

    command = _repo_test_command(repo)
    if command is None:
        return {"ran": False, "reason": f"no {TEST_DECLARATION} in {repo}"}
    completed = subprocess.run(
        command, cwd=repo, capture_output=True, text=True, check=False
    )
    if completed.returncode == 0:
        return {"ran": True, "command": command[-1], "passed": True}
    tail = "\n".join(
        (completed.stdout + completed.stderr).strip().splitlines()[-15:]
    )
    raise PublishError(
        f"the repository's own tests failed, so nothing was committed.\n"
        f"  command: {command[-1]}\n"
        f"  exit:    {completed.returncode}\n"
        f"  last lines:\n{tail}\n"
        "Fix the failures and publish again, or remove the command from "
        f"{TEST_DECLARATION} if it is no longer the suite that proves this repository."
    )


def _preflight(repo: Path, branch: str, remote: str, manifest: Path) -> list[str]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise PublishError(f"repository not found: {repo}")
    root = Path(_git(repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if root != repo:
        raise PublishError(f"--repo must be the worktree root: {root}")
    current = _git(repo, "branch", "--show-current").stdout.strip()
    if current != branch:
        raise PublishError(f"branch mismatch: expected {branch}, found {current or '<detached>'}")
    _git(repo, "remote", "get-url", remote)
    if _git(repo, "diff", "--cached", "--quiet", check=False).returncode:
        raise PublishError("index is not empty; commit or unstage existing staged work first")
    paths = _manifest_paths(repo, manifest.resolve())
    unchanged = [
        path for path in paths
        if not _git(repo, "status", "--porcelain=v1", "--untracked-files=all", "--", path).stdout.strip()
    ]
    if unchanged:
        raise PublishError("manifest includes unchanged paths: " + ", ".join(unchanged))
    return paths


def _push_and_verify(repo: Path, branch: str, remote: str, commit_sha: str) -> str:
    _git(repo, "push", remote, branch)
    remote_line = _git(repo, "ls-remote", "--heads", remote, branch).stdout.strip()
    remote_sha = remote_line.split()[0] if remote_line else ""
    if remote_sha != commit_sha:
        raise PublishError(f"remote verification mismatch: local={commit_sha}; remote={remote_sha or '<missing>'}")
    return remote_sha


def _changed_paths(repo: Path, older: str, newer: str) -> set[str]:
    return _nul_names(_git(repo, "diff", "--name-only", "-z", f"{older}..{newer}"))


def _copy_commit_path(source: Path, commit: str, relative: str, destination: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(source), "show", f"{commit}:{relative}"],
        check=False,
        capture_output=True,
    )
    target = destination / relative
    if result.returncode:
        if _git(source, "cat-file", "-e", f"{commit}:{relative}", check=False).returncode:
            if target.exists():
                target.unlink()
            return
        detail = result.stderr.decode(errors="replace").strip() or f"exit {result.returncode}"
        raise PublishError(f"cannot read {relative} from {commit}: {detail}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result.stdout)


def _commit_path_bytes(source: Path, commit: str, relative: str) -> bytes | None:
    result = subprocess.run(
        ["git", "-C", str(source), "show", f"{commit}:{relative}"],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        if _git(source, "cat-file", "-e", f"{commit}:{relative}", check=False).returncode:
            return None
        detail = result.stderr.decode(errors="replace").strip() or f"exit {result.returncode}"
        raise PublishError(f"cannot read {relative} from {commit}: {detail}")
    return result.stdout


def _merge_commit_path(
    source: Path, merge_base: str, commit: str, relative: str, destination: Path,
) -> bool:
    """Apply a clean three-way file merge; return False for a real content conflict."""
    base = _commit_path_bytes(source, merge_base, relative)
    local = _commit_path_bytes(source, commit, relative)
    target = destination / relative
    remote = target.read_bytes() if target.is_file() else None
    if local == base or local == remote:
        return True
    if remote == base:
        if local is None:
            if target.exists():
                target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(local)
        return True
    if base is None or local is None or remote is None or any(
        b"\0" in value for value in (base, local, remote)
    ):
        return False
    with tempfile.TemporaryDirectory(prefix="scoped-file-merge-") as merge_dir:
        merge_root = Path(merge_dir)
        local_file = merge_root / "local"
        base_file = merge_root / "base"
        remote_file = merge_root / "remote"
        local_file.write_bytes(local)
        base_file.write_bytes(base)
        remote_file.write_bytes(remote)
        result = subprocess.run(
            ["git", "merge-file", "-p", str(local_file), str(base_file), str(remote_file)],
            check=False,
            capture_output=True,
        )
    if 0 < result.returncode <= 127:
        return False
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip() or f"exit {result.returncode}"
        raise PublishError(f"three-way merge failed for {relative}: {detail}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result.stdout)
    return True


def _copy_worktree_path(source: Path, relative: str, destination: Path) -> None:
    origin = source / relative
    target = destination / relative
    if origin.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
    elif target.exists():
        target.unlink()


def _source_state(repo: Path, paths: Sequence[str]) -> tuple[str, str, dict[str, str | None]]:
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    status = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    hashes = {
        relative: hashlib.sha256((repo / relative).read_bytes()).hexdigest()
        if (repo / relative).is_file() else None
        for relative in paths
    }
    return head, status, hashes


def integrate_remote_and_resume(
    *, repo: Path, manifest: Path, branch: str, remote: str, commit_sha: str,
) -> dict[str, object]:
    """Rebase the exact manifest-bounded local commit stack, then push and verify it.

    The operation is intentionally fail-closed: it aborts and restores the original HEAD on a
    rebase conflict, never force-pushes, and refuses any pre/post-rebase scope mismatch.
    """
    repo = repo.resolve()
    root = Path(_git(repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if root != repo:
        raise PublishError(f"--repo must be the worktree root: {root}")
    current = _git(repo, "branch", "--show-current").stdout.strip()
    if current != branch:
        raise PublishError(f"branch mismatch: expected {branch}, found {current or '<detached>'}")
    _git(repo, "remote", "get-url", remote)
    if _git(repo, "diff", "--cached", "--quiet", check=False).returncode:
        raise PublishError("index is not empty; commit or unstage existing staged work first")
    if _git(repo, "diff", "--quiet", check=False).returncode:
        raise PublishError("tracked worktree is not clean; commit the approved scope before integration")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != commit_sha:
        raise PublishError(f"resume commit is not HEAD: expected {commit_sha}, found {head}")
    paths = _manifest_paths(repo, manifest.resolve())

    _git(repo, "fetch", remote, branch)
    remote_ref = f"refs/remotes/{remote}/{branch}"
    remote_sha = _git(repo, "rev-parse", remote_ref).stdout.strip()
    merge_base = _git(repo, "merge-base", head, remote_sha).stdout.strip()
    expected = set(paths)
    before = _changed_paths(repo, merge_base, head)
    if before != expected:
        raise PublishError(
            "local commit-stack scope mismatch before integration; "
            f"missing={sorted(expected - before)}; extra={sorted(before - expected)}"
        )

    if _git(repo, "merge-base", "--is-ancestor", remote_sha, head, check=False).returncode:
        result = _git(repo, "rebase", "--onto", remote_sha, merge_base, branch, check=False)
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            conflict_paths = sorted(_nul_names(
                _git(repo, "diff", "--name-only", "--diff-filter=U", "-z", check=False)
            ))
            _git(repo, "rebase", "--abort", check=False)
            restored = _git(repo, "rev-parse", "HEAD").stdout.strip()
            if restored != head:
                raise PublishError(
                    "remote integration failed and rebase abort did not restore HEAD; "
                    f"expected={head}; found={restored}; original-error={detail}"
                )
            raise PublishError(
                "remote integration conflict; rebase aborted and HEAD restored to "
                f"{head}; conflict_paths={conflict_paths}: {detail}"
            )

    integrated_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    integrated_remote = _git(repo, "rev-parse", remote_ref).stdout.strip()
    after = _changed_paths(repo, integrated_remote, integrated_head)
    if after != expected:
        raise PublishError(
            "local commit-stack scope mismatch after integration; "
            f"missing={sorted(expected - after)}; extra={sorted(after - expected)}"
        )
    verified_remote = _push_and_verify(repo, branch, remote, integrated_head)
    return {
        "ok": True,
        "mode": "integrate-remote-and-resume",
        "repo": str(repo),
        "branch": branch,
        "remote": remote,
        "original_commit": commit_sha,
        "commit": integrated_head,
        "remote_commit": verified_remote,
        "merge_base": merge_base,
        "paths": paths,
    }


def isolated_integrate_and_resume(
    *,
    repo: Path,
    manifest: Path,
    overlay_manifest: Path,
    message: str,
    branch: str,
    remote: str,
    commit_sha: str,
) -> dict[str, object]:
    """Publish through a temporary clone while leaving a dirty source worktree untouched."""
    repo = repo.resolve()
    root = Path(_git(repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if root != repo:
        raise PublishError(f"--repo must be the worktree root: {root}")
    current = _git(repo, "branch", "--show-current").stdout.strip()
    if current != branch:
        raise PublishError(f"branch mismatch: expected {branch}, found {current or '<detached>'}")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != commit_sha:
        raise PublishError(f"resume commit is not HEAD: expected {commit_sha}, found {head}")
    if not message.strip():
        raise PublishError("overlay commit message must not be empty")
    remote_url = _git(repo, "remote", "get-url", remote).stdout.strip()
    scope_paths = _manifest_paths(repo, manifest.resolve())
    overlay_paths = _manifest_paths(repo, overlay_manifest.resolve())
    if not set(overlay_paths).issubset(scope_paths):
        raise PublishError(
            "overlay manifest escapes publish scope: "
            + ", ".join(sorted(set(overlay_paths) - set(scope_paths)))
        )

    with tempfile.TemporaryDirectory(prefix="scoped-git-publish-") as temp_dir:
        isolated = Path(temp_dir) / "repo"
        subprocess.run(
            ["git", "clone", "--no-hardlinks", "--branch", branch, str(repo), str(isolated)],
            check=True,
            capture_output=True,
            text=True,
        )
        _git(isolated, "remote", "set-url", remote, remote_url)
        isolated_head = _git(isolated, "rev-parse", "HEAD").stdout.strip()
        if isolated_head != commit_sha:
            raise PublishError(
                f"isolated clone HEAD mismatch: expected {commit_sha}, found {isolated_head}"
            )
        for relative in overlay_paths:
            source = repo / relative
            destination = isolated / relative
            if source.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            elif destination.exists():
                destination.unlink()
        _git(isolated, "add", "--", *overlay_paths)
        staged = _nul_names(_git(isolated, "diff", "--cached", "--name-only", "-z"))
        if staged != set(overlay_paths):
            raise PublishError(
                "isolated overlay scope mismatch; "
                f"missing={sorted(set(overlay_paths) - staged)}; "
                f"extra={sorted(staged - set(overlay_paths))}"
            )
        _git(isolated, "diff", "--cached", "--check")
        _git(isolated, "commit", "-m", message)
        overlay_commit = _git(isolated, "rev-parse", "HEAD").stdout.strip()
        result = integrate_remote_and_resume(
            repo=isolated,
            manifest=manifest,
            branch=branch,
            remote=remote,
            commit_sha=overlay_commit,
        )
        return {
            **result,
            "mode": "isolated-integrate-remote-and-resume",
            "source_repo": str(repo),
            "source_commit": commit_sha,
            "overlay_commit": overlay_commit,
        }


def isolated_reconcile_and_resume(
    *,
    repo: Path,
    manifest: Path,
    overlay_manifest: Path,
    message: str,
    branch: str,
    remote: str,
    commit_sha: str,
    ledger_path: str | None = None,
    generated_view_path: str | None = None,
) -> dict[str, object]:
    """Squash an approved scope onto remote HEAD with bounded semantic conflict rules.

    Ordinary files retain the preserved local commit. Explicit overlay files use the verified
    source-worktree version. The append-only work ledger is unioned by immutable event identity,
    and its derived blocker view is regenerated. Every other remote/local overlap fails closed.
    """
    repo = repo.resolve()
    root = Path(_git(repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if root != repo:
        raise PublishError(f"--repo must be the worktree root: {root}")
    current = _git(repo, "branch", "--show-current").stdout.strip()
    if current != branch:
        raise PublishError(f"branch mismatch: expected {branch}, found {current or '<detached>'}")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != commit_sha:
        raise PublishError(f"resume commit is not HEAD: expected {commit_sha}, found {head}")
    if not message.strip():
        raise PublishError("reconciled commit message must not be empty")
    remote_url = _git(repo, "remote", "get-url", remote).stdout.strip()
    scope_paths = _manifest_paths(repo, manifest.resolve())
    overlay_paths = _manifest_paths(repo, overlay_manifest.resolve())
    scope = set(scope_paths)
    overlay = set(overlay_paths)
    if not overlay <= scope:
        raise PublishError(
            "overlay manifest escapes publish scope: " + ", ".join(sorted(overlay - scope))
        )
    before_state = _source_state(repo, sorted(scope | overlay))

    _git(repo, "fetch", remote, branch)
    remote_sha = _git(repo, "rev-parse", f"refs/remotes/{remote}/{branch}").stdout.strip()
    merge_base = _git(repo, "merge-base", commit_sha, remote_sha).stdout.strip()
    local_paths = _changed_paths(repo, merge_base, commit_sha)
    remote_paths = _changed_paths(repo, merge_base, remote_sha)
    preserved_local_paths = (local_paths & scope) - overlay
    if scope != preserved_local_paths | overlay:
        raise PublishError(
            "publish scope is not fully sourced by commit or overlay; "
            f"missing={sorted(scope - (preserved_local_paths | overlay))}"
        )
    overlaps = (local_paths & scope) & remote_paths
    if bool(ledger_path) != bool(generated_view_path):
        raise PublishError("ledger path and generated view path must be provided together")
    semantic_paths = overlay | ({ledger_path, generated_view_path} if ledger_path else set())
    if ledger_path and ledger_path in scope and generated_view_path not in scope:
        raise PublishError("ledger reconciliation requires the generated blocker view in scope")

    with tempfile.TemporaryDirectory(prefix="scoped-git-reconcile-") as temp_dir:
        isolated = Path(temp_dir) / "repo"
        clone = subprocess.run(
            ["git", "clone", "--branch", branch, remote_url, str(isolated)],
            check=False,
            capture_output=True,
            text=True,
        )
        if clone.returncode:
            detail = clone.stderr.strip() or clone.stdout.strip() or f"exit {clone.returncode}"
            raise PublishError(f"isolated remote clone failed: {detail}")
        if remote != "origin":
            _git(isolated, "remote", "rename", "origin", remote)
        if _git(isolated, "rev-parse", "HEAD").stdout.strip() != remote_sha:
            raise PublishError("remote advanced during isolated clone; rerun reconciliation")
        for key in ("user.name", "user.email"):
            value = _git(repo, "config", "--get", key, check=False).stdout.strip()
            if value:
                _git(isolated, "config", key, value)

        generated_paths = {ledger_path, generated_view_path} if ledger_path else set()
        auto_merged: list[str] = []
        unsupported: list[str] = []
        for relative in sorted(preserved_local_paths - generated_paths):
            if relative in remote_paths:
                if _merge_commit_path(repo, merge_base, commit_sha, relative, isolated):
                    auto_merged.append(relative)
                else:
                    unsupported.append(relative)
            else:
                _copy_commit_path(repo, commit_sha, relative, isolated)
        if unsupported:
            raise PublishError(
                "remote content conflict has no approved reconciliation rule: "
                + ", ".join(unsupported)
            )
        for relative in sorted(overlay - generated_paths):
            _copy_worktree_path(repo, relative, isolated)
        if ledger_path and ledger_path in scope:
            canonical_write = subprocess.run(
                [
                    sys.executable, str(isolated / "scripts/work_memory.py"), "merge-ledger",
                    "--source-ledger", str(repo / ledger_path),
                    "--ledger", str(isolated / ledger_path),
                    "--view", str(isolated / generated_view_path),
                    "--reconcile-persisted-source",
                ],
                cwd=isolated,
                check=False,
                capture_output=True,
                text=True,
            )
            if canonical_write.returncode:
                detail = (
                    canonical_write.stderr.strip() or canonical_write.stdout.strip()
                    or f"exit {canonical_write.returncode}"
                )
                raise PublishError(f"merged ledger failed canonical validation: {detail}")

        _git(isolated, "add", "--", *scope_paths)
        staged = _nul_names(_git(isolated, "diff", "--cached", "--name-only", "-z"))
        if not staged or not staged <= scope:
            raise PublishError(
                "reconciled staged scope mismatch; "
                f"missing-change={sorted(scope - staged)}; extra={sorted(staged - scope)}"
            )
        _git(isolated, "diff", "--cached", "--check")
        _git(isolated, "commit", "-m", message)
        reconciled = _git(isolated, "rev-parse", "HEAD").stdout.strip()
        if _changed_paths(isolated, remote_sha, reconciled) != staged:
            raise PublishError("reconciled commit differs from its validated staged scope")
        verified_remote = _push_and_verify(isolated, branch, remote, reconciled)

    after_state = _source_state(repo, sorted(scope | overlay))
    if after_state != before_state:
        raise PublishError("source worktree changed during isolated reconciliation")
    return {
        "ok": True,
        "mode": "isolated-reconcile-remote-and-resume",
        "source_repo": str(repo),
        "source_commit": commit_sha,
        "remote_base": remote_sha,
        "merge_base": merge_base,
        "commit": reconciled,
        "remote_commit": verified_remote,
        "paths": sorted(staged),
        "conflict_paths": sorted(overlaps & semantic_paths),
        "auto_merged_paths": auto_merged,
        "ledger_strategy": "remote-order-plus-local-unseen-event-id",
    }


def resume_push(*, repo: Path, branch: str, remote: str, commit_sha: str) -> dict[str, object]:
    repo = repo.resolve()
    root = Path(_git(repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if root != repo:
        raise PublishError(f"--repo must be the worktree root: {root}")
    current = _git(repo, "branch", "--show-current").stdout.strip()
    if current != branch:
        raise PublishError(f"branch mismatch: expected {branch}, found {current or '<detached>'}")
    _git(repo, "remote", "get-url", remote)
    if _git(repo, "diff", "--cached", "--quiet", check=False).returncode:
        raise PublishError("index is not empty; commit or unstage existing staged work first")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != commit_sha:
        raise PublishError(f"resume commit is not HEAD: expected {commit_sha}, found {head}")
    remote_sha = _push_and_verify(repo, branch, remote, commit_sha)
    return {
        "ok": True,
        "mode": "resume-push",
        "repo": str(repo),
        "branch": branch,
        "remote": remote,
        "commit": commit_sha,
        "remote_commit": remote_sha,
    }


def publish(
    *, repo: Path, manifest: Path, message: str, branch: str, remote: str, execute: bool,
) -> dict[str, object]:
    repo = repo.resolve()
    if execute and not message.strip():
        raise PublishError("commit message must not be empty")
    paths = _preflight(repo, branch, remote, manifest)
    if not execute:
        return {
            "ok": True,
            "mode": "dry-run",
            "repo": str(repo),
            "branch": branch,
            "remote": remote,
            "paths": paths,
            "tests": (
                {"would_run": _repo_test_command(repo)[-1]}
                if _repo_test_command(repo)
                else {"would_run": None, "reason": f"no {TEST_DECLARATION}"}
            ),
        }
    tests = _run_repo_tests(repo)

    committed = False
    commit_sha = ""
    try:
        _git(repo, "add", "--", *paths)
        staged = _nul_names(_git(repo, "diff", "--cached", "--name-only", "-z"))
        expected = set(paths)
        if staged != expected:
            missing = sorted(expected - staged)
            extra = sorted(staged - expected)
            raise PublishError(f"staged scope mismatch; missing={missing}; extra={extra}")
        _git(repo, "diff", "--cached", "--check")
        _git(repo, "commit", "-m", message)
        committed = True
        commit_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
        remote_sha = _push_and_verify(repo, branch, remote, commit_sha)
        if _git(repo, "diff", "--cached", "--quiet", check=False).returncode:
            raise PublishError("index is not empty after publish")
        return {
            "ok": True,
            "mode": "execute",
            "repo": str(repo),
            "branch": branch,
            "remote": remote,
            "paths": paths,
            "commit": commit_sha,
            "remote_commit": remote_sha,
            "tests": tests,
        }
    except Exception:
        if not committed:
            _git(repo, "reset", "--quiet", "--", *paths, check=False)
        elif commit_sha:
            print(
                "containment: commit "
                f"{commit_sha} remains local; repair auth/network and rerun with --resume-commit {commit_sha}",
                file=sys.stderr,
            )
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--message")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--execute", action="store_true", help="Commit and push; otherwise perform a dry-run.")
    parser.add_argument("--resume-commit", help="Push and verify an already-created local HEAD commit.")
    parser.add_argument(
        "--integrate-remote",
        action="store_true",
        help="With --resume-commit and --manifest, fetch and transactionally rebase before push.",
    )
    parser.add_argument(
        "--isolated-integrate-remote",
        action="store_true",
        help="Commit --overlay-manifest in a temporary clone, integrate, push, and preserve source state.",
    )
    parser.add_argument(
        "--isolated-reconcile-remote",
        action="store_true",
        help="Reconcile approved conflicts in a temporary remote-based clone, then push.",
    )
    parser.add_argument("--overlay-manifest", type=Path)
    parser.add_argument("--ledger-path")
    parser.add_argument("--generated-view-path")
    parser.add_argument("--prevention-effect-id")
    parser.add_argument("--prevention-preparation-sha256")
    return parser


def _run_semantic_intake() -> int:
    try:
        roots = {
            key: str(path)
            for key, path in work_memory._repo_roots().items()
        }
        with tempfile.TemporaryDirectory(prefix="commit-push-intake-") as raw_root:
            root = Path(raw_root).resolve()
            prepared = sequence_intake_adapters.collect_and_prepare(
                "commit-push-main",
                artifact_paths={
                    "approved_paths": str(root / "approved-paths.txt"),
                    "overlay_paths": str(root / "overlay-paths.txt"),
                },
                repository_roots=roots,
            )
            print(json.dumps({
                "event": "intake-prepared",
                "prepared": prepared,
            }, sort_keys=True), file=sys.stderr)
            if prepared["authorization"]["required"]:
                confirmation = script_intake.collect(EFFECT_AUTHORIZATION_SPEC)
                if not confirmation["authorize"]:
                    print(json.dumps({
                        "ok": False,
                        "error": "effect-authorization-declined",
                    }, sort_keys=True), file=sys.stderr)
                    return 130
            for artifact in prepared["artifacts"].values():
                path = Path(artifact["path"]).resolve()
                try:
                    path.relative_to(root)
                except ValueError as exc:
                    raise PublishError(
                        "intake-artifact-path-outside-temporary-root"
                    ) from exc
                path.write_text(artifact["content"], encoding="utf-8")
            return main(prepared["argv"][2:])
    except script_intake.IntakeCancelled:
        print(json.dumps({
            "ok": False,
            "error": "intake-cancelled",
        }, sort_keys=True), file=sys.stderr)
        return 130
    except (
        sequence_intake_adapters.AdapterError,
        work_memory.WorkMemoryError,
    ) as exc:
        error = exc.code if isinstance(exc, work_memory.WorkMemoryError) else str(exc)
        print(json.dumps({
            "ok": False,
            "error": error,
        }, sort_keys=True), file=sys.stderr)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    try:
        values = list(sys.argv[1:] if argv is None else argv)
        if not values:
            return _run_semantic_intake()
        args = build_parser().parse_args(values)
        if args.resume_commit:
            profile = (
                "isolated-reconcile-and-resume" if args.isolated_reconcile_remote
                else "isolated-integrate-and-resume" if args.isolated_integrate_remote
                else "integrate-remote-and-resume" if args.integrate_remote
                else "resume-push"
            )
        else:
            profile = "publish" if args.execute else "dry-run"
        source_identity = {
            "repository_path_sha256": hashlib.sha256(
                str(args.repo.expanduser().resolve()).encode("utf-8")
            ).hexdigest(),
            "profile": profile,
            "branch": args.branch,
            "remote_key": args.remote,
            "manifest_sha256": (
                hashlib.sha256(args.manifest.read_bytes()).hexdigest()
                if args.manifest is not None and args.manifest.is_file() else None
            ),
            "overlay_manifest_sha256": (
                hashlib.sha256(args.overlay_manifest.read_bytes()).hexdigest()
                if args.overlay_manifest is not None and args.overlay_manifest.is_file()
                else None
            ),
            "resume_commit": args.resume_commit,
        }
        source_receipt = None
        if profile != "dry-run" and (
            args.prevention_effect_id or args.prevention_preparation_sha256
        ):
            source_receipt = prevention_source_receipt.prepare(
                owner_sequence_id="commit-push-main",
                profile_id=profile,
                effect_id=args.prevention_effect_id,
                preparation_artifact_sha256=args.prevention_preparation_sha256,
                source_identity=source_identity,
            )
        if args.resume_commit:
            if args.execute:
                raise PublishError("--resume-commit cannot be combined with --execute")
            integration_modes = sum((
                args.integrate_remote,
                args.isolated_integrate_remote,
                args.isolated_reconcile_remote,
            ))
            if integration_modes > 1:
                raise PublishError("choose only one remote-integration mode")
            if args.isolated_reconcile_remote:
                if args.manifest is None or args.overlay_manifest is None or args.message is None:
                    raise PublishError(
                        "--manifest, --overlay-manifest, and --message are required with "
                        "--isolated-reconcile-remote"
                    )
                result = isolated_reconcile_and_resume(
                    repo=args.repo,
                    manifest=args.manifest,
                    overlay_manifest=args.overlay_manifest,
                    message=_bind_prevention_trailers(
                        args.message, args.prevention_effect_id,
                        args.prevention_preparation_sha256,
                    ),
                    branch=args.branch,
                    remote=args.remote,
                    commit_sha=args.resume_commit,
                    ledger_path=args.ledger_path,
                    generated_view_path=args.generated_view_path,
                )
            elif args.isolated_integrate_remote:
                if args.manifest is None or args.overlay_manifest is None or args.message is None:
                    raise PublishError(
                        "--manifest, --overlay-manifest, and --message are required with "
                        "--isolated-integrate-remote"
                    )
                result = isolated_integrate_and_resume(
                    repo=args.repo,
                    manifest=args.manifest,
                    overlay_manifest=args.overlay_manifest,
                    message=_bind_prevention_trailers(
                        args.message, args.prevention_effect_id,
                        args.prevention_preparation_sha256,
                    ),
                    branch=args.branch,
                    remote=args.remote,
                    commit_sha=args.resume_commit,
                )
            elif args.integrate_remote:
                if args.message or args.overlay_manifest:
                    raise PublishError(
                        "--integrate-remote cannot be combined with --message or --overlay-manifest"
                    )
                if args.manifest is None:
                    raise PublishError("--manifest is required with --integrate-remote")
                result = integrate_remote_and_resume(
                    repo=args.repo,
                    manifest=args.manifest,
                    branch=args.branch,
                    remote=args.remote,
                    commit_sha=args.resume_commit,
                )
            else:
                if args.manifest or args.message or args.overlay_manifest:
                    raise PublishError(
                        "--manifest, --message, or --overlay-manifest require a remote-integration "
                        "mode with --resume-commit"
                    )
                result = resume_push(
                    repo=args.repo, branch=args.branch, remote=args.remote, commit_sha=args.resume_commit
                )
        else:
            if (
                args.integrate_remote or args.isolated_integrate_remote
                or args.isolated_reconcile_remote or args.overlay_manifest
            ):
                raise PublishError("remote-integration options require --resume-commit")
            if args.manifest is None or (args.execute and args.message is None):
                raise PublishError(
                    "--manifest is required; --message is additionally required for publish"
                )
            result = publish(
                repo=args.repo,
                manifest=args.manifest,
                message=_bind_prevention_trailers(
                    args.message or "", args.prevention_effect_id,
                    args.prevention_preparation_sha256,
                ),
                branch=args.branch,
                remote=args.remote,
                execute=args.execute,
            )
        if source_receipt is not None:
            source_receipt = prevention_source_receipt.complete(
                owner_sequence_id="commit-push-main",
                profile_id=profile,
                effect_id=args.prevention_effect_id,
                preparation_artifact_sha256=args.prevention_preparation_sha256,
                source_identity=source_identity,
                result_identity={
                    "profile": profile,
                    "commit": result.get("commit"),
                    "remote_commit": result.get("remote_commit"),
                    "ok": result.get("ok"),
                },
            )
        if args.prevention_effect_id:
            result = {
                **result,
                "preventionEffectId": args.prevention_effect_id,
                "preventionPreparationSha256": args.prevention_preparation_sha256,
            }
            if source_receipt is not None:
                result["preventionSourceReceiptSha256"] = (
                    prevention_source_receipt.receipt_sha256(source_receipt)
                )
        print(json.dumps(result, sort_keys=True))
        return 0
    except PublishError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
