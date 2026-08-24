#!/usr/bin/env python3
"""Prepare an isolated, conflict-visible merge of one branch into another."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

try:
    from scripts import commit_push_main_launch, script_intake
except ModuleNotFoundError:  # direct script execution
    import commit_push_main_launch  # type: ignore
    import script_intake  # type: ignore


class IntegrationError(RuntimeError):
    """The requested integration preparation is unsafe or incomplete."""


def _git(
    repo: Path, *args: str, check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise IntegrationError(
            f"git {' '.join(args)} failed: {detail or completed.returncode}"
        )
    return completed


def _choice_field(
    field_id: str, prompt: str, choices: list[str], example: str,
) -> dict[str, object]:
    if not choices:
        raise IntegrationError(f"no choices available for {field_id}")
    return {
        "id": field_id,
        "prompt": prompt,
        "response_format": "One numbered selection.",
        "example": example,
        "constraints": "Choose exactly one displayed option.",
        "type": "choice",
        "choices": choices,
        "numbered_selection": True,
        "required": True,
    }


def _collect_one(
    field: dict[str, object], *, input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> str:
    value = script_intake.collect(
        {"schema_version": script_intake.SCHEMA_VERSION, "fields": [field]},
        input_fn=input_fn,
        output_fn=output_fn,
    )[str(field["id"])]
    if not isinstance(value, str):
        raise IntegrationError(f"invalid selection for {field['id']}")
    return value


def _branches(repo: Path) -> list[str]:
    return sorted(filter(None, _git(
        repo, "for-each-ref", "--format=%(refname:short)", "refs/heads",
    ).stdout.splitlines()))


def _remotes(repo: Path) -> list[str]:
    return sorted(filter(None, _git(repo, "remote").stdout.splitlines()))


def _remote_branches(repo: Path, remote: str) -> list[str]:
    prefix = f"{remote}/"
    values = []
    for ref in _git(
        repo,
        "for-each-ref",
        "--format=%(refname:short)",
        f"refs/remotes/{remote}",
    ).stdout.splitlines():
        if ref.startswith(prefix) and ref != f"{remote}/HEAD":
            values.append(ref[len(prefix):])
    return sorted(set(values))


def integration_branch_name(source: str, target: str) -> str:
    source_name = source.removeprefix("codex/")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", source_name).strip("-.")
    target_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", target).strip("-.")
    if not slug or not target_slug:
        raise IntegrationError("source or target branch cannot produce a safe integration name")
    suffix = "" if target == "main" else f"-into-{target_slug}"
    return f"codex/integrate-{slug}{suffix}"


def integration_worktree_path(
    repo: Path, source_sha: str, target_sha: str,
) -> Path:
    identity = hashlib.sha256(
        f"{repo.resolve()}\0{source_sha}\0{target_sha}".encode("utf-8")
    ).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"{repo.name}-integration-{identity}"


def prepare_integration(
    *, repo: Path, source: str, remote: str, target: str,
) -> dict[str, object]:
    repo = repo.resolve()
    if source not in _branches(repo):
        raise IntegrationError(f"source branch does not exist locally: {source}")
    if remote not in _remotes(repo):
        raise IntegrationError(f"remote does not exist: {remote}")

    _git(repo, "fetch", "--prune", remote)
    source_sha = _git(repo, "rev-parse", f"refs/heads/{source}").stdout.strip()
    remote_source = _git(
        repo, "rev-parse", f"refs/remotes/{remote}/{source}", check=False,
    )
    if remote_source.returncode or remote_source.stdout.strip() != source_sha:
        raise IntegrationError(
            f"source branch must be pushed unchanged to {remote}/{source}"
        )
    target_sha = _git(
        repo, "rev-parse", f"refs/remotes/{remote}/{target}",
    ).stdout.strip()

    integration_branch = integration_branch_name(source, target)
    if not _git(
        repo, "show-ref", "--verify", "--quiet",
        f"refs/heads/{integration_branch}", check=False,
    ).returncode:
        raise IntegrationError(f"integration branch already exists: {integration_branch}")
    if not _git(
        repo, "show-ref", "--verify", "--quiet",
        f"refs/remotes/{remote}/{integration_branch}", check=False,
    ).returncode:
        raise IntegrationError(
            f"remote integration branch already exists: {remote}/{integration_branch}"
        )

    worktree = integration_worktree_path(repo, source_sha, target_sha)
    if worktree.exists():
        raise IntegrationError(f"integration worktree path already exists: {worktree}")
    _git(
        repo, "worktree", "add", "-b", integration_branch,
        str(worktree), target_sha,
    )
    merged = _git(
        worktree, "merge", "--no-ff", "--no-commit", source_sha,
        check=False,
    )
    conflicts = sorted(filter(None, _git(
        worktree, "diff", "--name-only", "--diff-filter=U",
    ).stdout.splitlines()))
    if merged.returncode not in {0, 1} or (merged.returncode == 1 and not conflicts):
        detail = merged.stderr.strip() or merged.stdout.strip() or merged.returncode
        raise IntegrationError(f"merge preparation failed without conflicts: {detail}")
    return {
        "ok": True,
        "status": "conflicts-ready" if conflicts else "clean-merge-ready",
        "repository": str(repo),
        "source_branch": source,
        "source_sha": source_sha,
        "target_branch": target,
        "target_sha": target_sha,
        "remote": remote,
        "integration_branch": integration_branch,
        "integration_worktree": str(worktree),
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


def _run_interview(
    *, input_fn: Callable[[str], str], output_fn: Callable[[str], None],
) -> dict[str, object]:
    repositories = commit_push_main_launch._repository_choices()
    repository_labels = [f"{key} — {path}" for key, path in repositories]
    selected_repository = _collect_one(
        _choice_field("repository", "Repository to integrate", repository_labels, "1"),
        input_fn=input_fn,
        output_fn=output_fn,
    )
    repository_key, repo = repositories[repository_labels.index(selected_repository)]
    source = _collect_one(
        _choice_field("source", "Committed source branch", _branches(repo), "1"),
        input_fn=input_fn,
        output_fn=output_fn,
    )
    remote = _collect_one(
        _choice_field("remote", "Target remote", _remotes(repo), "1"),
        input_fn=input_fn,
        output_fn=output_fn,
    )
    target = _collect_one(
        _choice_field(
            "target", "Target branch", _remote_branches(repo, remote), "1",
        ),
        input_fn=input_fn,
        output_fn=output_fn,
    )
    integration_branch = integration_branch_name(source, target)
    output_fn("Prepared operation")
    output_fn(f"Repository: {repository_key} — {repo}")
    output_fn(f"Source: {source}")
    output_fn(f"Target: {remote}/{target}")
    output_fn(f"Integration branch: {integration_branch}")
    authorization = script_intake.collect(
        {
            "schema_version": script_intake.SCHEMA_VERSION,
            "fields": [{
                "id": "authorize",
                "prompt": "Create this isolated integration worktree now",
                "response_format": "One yes or no answer.",
                "example": "no",
                "constraints": "Answer yes only after reviewing the displayed operation.",
                "type": "boolean",
                "required": True,
            }],
        },
        input_fn=input_fn,
        output_fn=output_fn,
    )["authorize"]
    if authorization is not True:
        raise script_intake.IntakeCancelled("integration preparation declined")
    return prepare_integration(
        repo=repo, source=source, remote=remote, target=target,
    )


def main(
    argv: Sequence[str] | None = None,
    *, input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> int:
    if list(sys.argv[1:] if argv is None else argv):
        print(json.dumps({
            "ok": False, "error": "no-argument-entrypoint-required",
        }, sort_keys=True), file=sys.stderr)
        return 2
    try:
        result = _run_interview(
            input_fn=input_fn or input,
            output_fn=output_fn or print,
        )
        (output_fn or print)(json.dumps(result, sort_keys=True))
        return 0
    except (
        IntegrationError,
        commit_push_main_launch.InterviewError,
        script_intake.IntakeCancelled,
        OSError,
        EOFError,
        KeyboardInterrupt,
    ) as exc:
        print(json.dumps({
            "ok": False, "error": str(exc) or type(exc).__name__,
        }, sort_keys=True), file=sys.stderr)
        return 130 if isinstance(exc, script_intake.IntakeCancelled) else 2


if __name__ == "__main__":
    raise SystemExit(main())
