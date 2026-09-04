#!/usr/bin/env python3
"""Run isolated probes for the minimal commit-and-push boundary."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Sequence


class ProbeFailure(RuntimeError):
    """The boundary under test did not preserve its declared invariant."""


def _run(argv: Sequence[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = _run(["git", "-C", str(repo), *args])
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise ProbeFailure(f"git {' '.join(args)} failed: {detail}")
    return result


def _bootstrap(root: Path) -> tuple[Path, Path]:
    remote = root / "remote.git"
    repo = root / "repo"
    remote.parent.mkdir(parents=True, exist_ok=True)
    bare = _run(["git", "init", "--bare", str(remote)])
    if bare.returncode:
        raise ProbeFailure(bare.stderr.strip() or "bare repository initialization failed")
    initialized = _run(["git", "init", "-b", "main", str(repo)])
    if initialized.returncode:
        raise ProbeFailure(initialized.stderr.strip() or "repository initialization failed")
    _git(repo, "config", "user.email", "publish-probe@example.invalid")
    _git(repo, "config", "user.name", "Publish Boundary Probe")
    (repo / "approved.txt").write_text("before\n", encoding="utf-8")
    (repo / "removed.txt").write_text("before\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("before\n", encoding="utf-8")
    _git(repo, "add", "--", "approved.txt", "removed.txt", "unrelated.txt")
    _git(repo, "commit", "-m", "probe baseline")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")
    return repo, remote


def _manifest_paths(repo: Path, manifest: Path) -> list[str]:
    try:
        values = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeFailure(f"manifest is not readable JSON: {exc}") from exc
    if not isinstance(values, list) or not values:
        raise ProbeFailure("manifest must be a non-empty JSON list")
    paths: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ProbeFailure("every manifest entry must be a non-empty string")
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ProbeFailure(f"manifest entry escapes repository: {value}")
        normalized = candidate.as_posix()
        resolved = (repo / candidate).resolve()
        try:
            resolved.relative_to(repo.resolve())
        except ValueError as exc:
            raise ProbeFailure(f"manifest entry escapes repository: {value}") from exc
        if normalized in paths:
            raise ProbeFailure(f"duplicate manifest entry: {normalized}")
        tracked = _git(
            repo, "ls-files", "--error-unmatch", "--", normalized, check=False
        ).returncode == 0
        if not resolved.is_file() and not tracked:
            raise ProbeFailure(f"manifest entry is neither present nor tracked: {normalized}")
        paths.append(normalized)
    return paths


def _cached_paths(repo: Path) -> list[str]:
    output = _git(repo, "diff", "--cached", "--name-only", "-z").stdout
    return sorted(item for item in output.split("\0") if item)


def _stage_exact(repo: Path, paths: Sequence[str]) -> None:
    if _cached_paths(repo):
        raise ProbeFailure("index was not empty before exact staging")
    _git(repo, "add", "--", *paths)
    staged = _cached_paths(repo)
    if staged != sorted(paths):
        raise ProbeFailure(f"staged paths differ from manifest: {staged!r}")


def probe_manifest(root: Path) -> dict[str, object]:
    repo, _remote = _bootstrap(root)
    (repo / "approved.txt").write_text("approved change\n", encoding="utf-8")
    (repo / "removed.txt").unlink()
    (repo / "unrelated.txt").write_text("unrelated change\n", encoding="utf-8")
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(["approved.txt", "removed.txt"]), encoding="utf-8"
    )
    paths = _manifest_paths(repo, manifest)
    _stage_exact(repo, paths)
    success_case = _cached_paths(repo) == ["approved.txt", "removed.txt"]
    unrelated_remained_unstaged = "unrelated.txt" in _git(
        repo, "diff", "--name-only"
    ).stdout.splitlines()

    rejected = root / "rejected-manifest.json"
    rejected.write_text(json.dumps(["../outside.txt"]), encoding="utf-8")
    try:
        _manifest_paths(repo, rejected)
    except ProbeFailure as exc:
        rejection_case = "escapes repository" in str(exc)
    else:
        rejection_case = False

    if not success_case or not unrelated_remained_unstaged or not rejection_case:
        raise ProbeFailure("manifest boundary did not preserve exact scope")
    return {
        "success_case": True,
        "rejection_case": True,
        "evidence": {
            "manifest_paths": paths,
            "staged_paths": _cached_paths(repo),
            "tracked_deletion_included": True,
            "unrelated_remained_unstaged": True,
            "path_escape_rejected": True,
        },
    }


def _run_relevant_verification(repo: Path, paths: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return _git(repo, "diff", "--check", "--cached", "--", *paths, check=False)


def probe_verification(root: Path) -> dict[str, object]:
    repo, _remote = _bootstrap(root)
    (repo / "approved.txt").write_text("approved change\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text(
        "unrelated trailing whitespace \n", encoding="utf-8"
    )
    _stage_exact(repo, ["approved.txt"])
    passing = _run_relevant_verification(repo, ["approved.txt"])

    (repo / "approved.txt").write_text(
        "approved trailing whitespace \n", encoding="utf-8"
    )
    _git(repo, "add", "--", "approved.txt")
    failing = _run_relevant_verification(repo, ["approved.txt"])

    success_case = passing.returncode == 0
    rejection_case = failing.returncode != 0
    if not success_case or not rejection_case:
        raise ProbeFailure("verification boundary did not obey the selected command exit code")
    return {
        "success_case": True,
        "rejection_case": True,
        "evidence": {
            "selected_paths": ["approved.txt"],
            "unrelated_failure_ignored": True,
            "selected_success_exit": passing.returncode,
            "selected_failure_exit": failing.returncode,
            "nonzero_blocked": True,
        },
    }


def _commit_exact(repo: Path, paths: Sequence[str], message: str) -> str:
    staged = _cached_paths(repo)
    if staged != sorted(paths):
        raise ProbeFailure(f"staged paths differ from manifest before commit: {staged!r}")
    _git(repo, "commit", "-m", message)
    commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
    committed = sorted(
        item
        for item in _git(
            repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", commit
        ).stdout.split("\0")
        if item
    )
    if committed != sorted(paths):
        raise ProbeFailure(f"committed paths differ from manifest: {committed!r}")
    return commit


def probe_commit(root: Path) -> dict[str, object]:
    success_repo, _remote = _bootstrap(root / "success")
    (success_repo / "approved.txt").write_text("approved change\n", encoding="utf-8")
    (success_repo / "unrelated.txt").write_text("unrelated change\n", encoding="utf-8")
    _stage_exact(success_repo, ["approved.txt"])
    commit = _commit_exact(success_repo, ["approved.txt"], "probe exact commit")
    committed_paths = [
        item
        for item in _git(
            success_repo,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit,
        ).stdout.splitlines()
        if item
    ]
    unrelated_remained_unstaged = "unrelated.txt" in _git(
        success_repo, "diff", "--name-only"
    ).stdout.splitlines()

    rejection_repo, _remote = _bootstrap(root / "rejection")
    (rejection_repo / "approved.txt").write_text("approved change\n", encoding="utf-8")
    (rejection_repo / "unrelated.txt").write_text("unrelated change\n", encoding="utf-8")
    _git(rejection_repo, "add", "--", "approved.txt", "unrelated.txt")
    head_before = _git(rejection_repo, "rev-parse", "HEAD").stdout.strip()
    try:
        _commit_exact(rejection_repo, ["approved.txt"], "must not exist")
    except ProbeFailure as exc:
        rejected_mismatch = "staged paths differ" in str(exc)
    else:
        rejected_mismatch = False
    head_after = _git(rejection_repo, "rev-parse", "HEAD").stdout.strip()

    success_case = committed_paths == ["approved.txt"] and unrelated_remained_unstaged
    rejection_case = rejected_mismatch and head_after == head_before
    if not success_case or not rejection_case:
        raise ProbeFailure("commit boundary did not preserve exact manifest identity")
    return {
        "success_case": True,
        "rejection_case": True,
        "evidence": {
            "commit_created": bool(commit),
            "committed_paths": committed_paths,
            "unrelated_remained_unstaged": True,
            "staging_mismatch_rejected_before_commit": True,
        },
    }


def _remote_head(remote: Path, branch: str) -> str:
    result = _run(
        ["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{branch}"]
    )
    if result.returncode:
        raise ProbeFailure(result.stderr.strip() or "remote branch is missing")
    return result.stdout.strip()


def probe_push(root: Path) -> dict[str, object]:
    success_repo, success_remote = _bootstrap(root / "success")
    (success_repo / "approved.txt").write_text("approved change\n", encoding="utf-8")
    _stage_exact(success_repo, ["approved.txt"])
    commit = _commit_exact(success_repo, ["approved.txt"], "probe push")
    pushed = _git(
        success_repo,
        "push",
        "origin",
        "HEAD:refs/heads/main",
        check=False,
    )
    remote_after_success = _remote_head(success_remote, "main")

    rejection_repo, rejection_remote = _bootstrap(root / "rejection")
    remote_before_failure = _remote_head(rejection_remote, "main")
    (rejection_repo / "approved.txt").write_text("approved change\n", encoding="utf-8")
    _stage_exact(rejection_repo, ["approved.txt"])
    rejected_commit = _commit_exact(
        rejection_repo, ["approved.txt"], "probe rejected push"
    )
    rejected_push = _git(
        rejection_repo,
        "push",
        "missing-remote",
        "HEAD:refs/heads/main",
        check=False,
    )
    remote_after_failure = _remote_head(rejection_remote, "main")

    success_case = pushed.returncode == 0 and remote_after_success == commit
    rejection_case = (
        rejected_push.returncode != 0
        and remote_after_failure == remote_before_failure
        and remote_after_failure != rejected_commit
    )
    if not success_case or not rejection_case:
        raise ProbeFailure("push boundary did not preserve remote effect identity")
    return {
        "success_case": True,
        "rejection_case": True,
        "evidence": {
            "push_exit": pushed.returncode,
            "remote_advanced_to_commit": True,
            "failed_push_exit": rejected_push.returncode,
            "failed_push_left_remote_unchanged": True,
        },
    }


def _fresh_checkout_head(remote: Path, destination: Path, branch: str) -> str:
    cloned = _run(
        [
            "git",
            "clone",
            "--quiet",
            "--branch",
            branch,
            "--single-branch",
            str(remote),
            str(destination),
        ]
    )
    if cloned.returncode:
        raise ProbeFailure(cloned.stderr.strip() or "independent checkout failed")
    return _git(destination, "rev-parse", "HEAD").stdout.strip()


def probe_confirmation(root: Path) -> dict[str, object]:
    repo, remote = _bootstrap(root / "source")
    (repo / "approved.txt").write_text("published change\n", encoding="utf-8")
    _stage_exact(repo, ["approved.txt"])
    published_commit = _commit_exact(repo, ["approved.txt"], "probe confirmation")
    pushed = _git(
        repo, "push", "origin", "HEAD:refs/heads/main", check=False
    )
    confirmed_commit = _fresh_checkout_head(
        remote, root / "confirmed-reader", "main"
    )

    (repo / "approved.txt").write_text("not published\n", encoding="utf-8")
    _stage_exact(repo, ["approved.txt"])
    unpublished_commit = _commit_exact(
        repo, ["approved.txt"], "probe unpublished confirmation"
    )
    independently_observed = _fresh_checkout_head(
        remote, root / "rejection-reader", "main"
    )

    success_case = pushed.returncode == 0 and confirmed_commit == published_commit
    rejection_case = independently_observed != unpublished_commit
    if not success_case or not rejection_case:
        raise ProbeFailure("confirmation boundary trusted local state instead of the remote")
    return {
        "success_case": True,
        "rejection_case": True,
        "evidence": {
            "independent_checkout_matched_published_commit": True,
            "unpublished_local_commit_rejected": True,
            "confirmation_source": "fresh-checkout",
        },
    }


PROBES: dict[str, Callable[[Path], dict[str, object]]] = {
    "commit": probe_commit,
    "confirmation": probe_confirmation,
    "manifest": probe_manifest,
    "push": probe_push,
    "verification": probe_verification,
}


def run_probe(name: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"publish-{name}-probe-") as temporary:
        result = PROBES[name](Path(temporary))
    return {"ok": True, "probe": name, **result}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, choices=sorted(PROBES))
    args = parser.parse_args(argv)
    try:
        result = run_probe(args.probe)
    except ProbeFailure as exc:
        print(json.dumps({"ok": False, "probe": args.probe, "error": str(exc)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
