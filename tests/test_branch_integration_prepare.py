from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import branch_integration_prepare as prepare


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(tmp_path, "clone", str(remote), str(repo))
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "switch", "-c", "main")
    (repo / "shared.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "shared.txt")
    _git(repo, "commit", "-m", "base")
    _git(repo, "push", "-u", "origin", "main")
    _git(repo, "switch", "-c", "codex/topic")
    (repo / "shared.txt").write_text("source\n", encoding="utf-8")
    _git(repo, "commit", "-am", "source")
    _git(repo, "push", "-u", "origin", "codex/topic")
    _git(repo, "switch", "main")
    (repo / "shared.txt").write_text("target\n", encoding="utf-8")
    _git(repo, "commit", "-am", "target")
    _git(repo, "push")
    _git(repo, "switch", "codex/topic")
    return repo, remote


def test_prepare_integration_preserves_source_and_exposes_conflicts(
    tmp_path: Path,
) -> None:
    repo, _remote = _repository(tmp_path)
    (repo / "unrelated-untracked.txt").write_text("preserve me\n", encoding="utf-8")
    before_status = _git(repo, "status", "--porcelain")

    result = prepare.prepare_integration(
        repo=repo,
        source="codex/topic",
        remote="origin",
        target="main",
    )

    assert result["status"] == "conflicts-ready"
    assert result["conflicts"] == ["shared.txt"]
    assert _git(repo, "branch", "--show-current") == "codex/topic"
    assert _git(repo, "status", "--porcelain") == before_status
    assert (repo / "unrelated-untracked.txt").read_text(encoding="utf-8") == "preserve me\n"
    worktree = Path(str(result["integration_worktree"]))
    assert _git(worktree, "branch", "--show-current") == "codex/integrate-topic"
    assert "UU shared.txt" in _git(worktree, "status", "--short")


def test_prepare_integration_rejects_unpublished_source(tmp_path: Path) -> None:
    repo, _remote = _repository(tmp_path)
    (repo / "only-local.txt").write_text("local\n", encoding="utf-8")
    _git(repo, "add", "only-local.txt")
    _git(repo, "commit", "-m", "not pushed")

    with pytest.raises(
        prepare.IntegrationError,
        match="source branch must be pushed unchanged",
    ):
        prepare.prepare_integration(
            repo=repo,
            source="codex/topic",
            remote="origin",
            target="main",
        )


def test_zero_argument_boundary_rejects_arguments() -> None:
    assert prepare.main(["--repo", "/tmp/example"]) == 2
