from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import scoped_git_publish


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def publish_repo(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    git(repo, "remote", "add", "origin", str(remote))
    (repo / "included.txt").write_text("before\n")
    (repo / "excluded.txt").write_text("before\n")
    git(repo, "add", "included.txt", "excluded.txt")
    git(repo, "commit", "-m", "initial")
    git(repo, "push", "-u", "origin", "main")
    manifest = tmp_path / "scope.txt"
    manifest.write_text("included.txt\n")
    return repo, manifest


def test_dry_run_reports_scope_without_mutating_index(publish_repo: tuple[Path, Path]) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("changed\n")
    result = scoped_git_publish.publish(
        repo=repo, manifest=manifest, message="fix: included", branch="main", remote="origin", execute=False
    )
    assert result["mode"] == "dry-run"
    assert result["paths"] == ["included.txt"]
    assert git(repo, "diff", "--cached", "--name-only") == ""


def test_execute_pushes_exact_scope_and_leaves_unrelated_worktree_change(
    publish_repo: tuple[Path, Path],
) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("included change\n")
    (repo / "excluded.txt").write_text("excluded change\n")
    result = scoped_git_publish.publish(
        repo=repo, manifest=manifest, message="fix: included", branch="main", remote="origin", execute=True
    )
    assert result["commit"] == git(repo, "rev-parse", "refs/remotes/origin/main")
    assert git(repo, "show", "--format=", "--name-only", "HEAD") == "included.txt"
    assert git(repo, "status", "--short") == "M excluded.txt"
    assert git(repo, "diff", "--cached", "--name-only") == ""


def test_preflight_rejects_existing_staged_work(publish_repo: tuple[Path, Path]) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("included change\n")
    (repo / "excluded.txt").write_text("staged elsewhere\n")
    git(repo, "add", "excluded.txt")
    with pytest.raises(scoped_git_publish.PublishError, match="index is not empty"):
        scoped_git_publish.publish(
            repo=repo, manifest=manifest, message="fix: included", branch="main", remote="origin", execute=False
        )


def test_manifest_rejects_repository_escape(publish_repo: tuple[Path, Path]) -> None:
    repo, manifest = publish_repo
    manifest.write_text("../outside.txt\n")
    with pytest.raises(scoped_git_publish.PublishError, match="escapes the repository"):
        scoped_git_publish.publish(
            repo=repo, manifest=manifest, message="fix: included", branch="main", remote="origin", execute=False
        )


def test_resume_push_publishes_existing_head(publish_repo: tuple[Path, Path]) -> None:
    repo, _ = publish_repo
    (repo / "included.txt").write_text("local commit\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "fix: local")
    commit_sha = git(repo, "rev-parse", "HEAD")
    assert git(repo, "rev-parse", "refs/remotes/origin/main") != commit_sha
    result = scoped_git_publish.resume_push(
        repo=repo, branch="main", remote="origin", commit_sha=commit_sha
    )
    assert result["mode"] == "resume-push"
    assert git(repo, "rev-parse", "refs/remotes/origin/main") == commit_sha


def remote_writer(repo: Path, tmp_path: Path) -> Path:
    writer = tmp_path / "writer"
    subprocess.run(
        ["git", "clone", git(repo, "remote", "get-url", "origin"), str(writer)],
        check=True,
        capture_output=True,
    )
    git(writer, "config", "user.email", "writer@example.com")
    git(writer, "config", "user.name", "Remote Writer")
    return writer


def test_integrate_remote_rebases_exact_scope_and_pushes(
    publish_repo: tuple[Path, Path], tmp_path: Path,
) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("local change\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "fix: local")
    original = git(repo, "rev-parse", "HEAD")
    (repo / "unrelated.tmp").write_text("preserve me\n")

    writer = remote_writer(repo, tmp_path)
    (writer / "remote.txt").write_text("remote change\n")
    git(writer, "add", "remote.txt")
    git(writer, "commit", "-m", "fix: remote")
    git(writer, "push", "origin", "main")
    remote_advance = git(writer, "rev-parse", "HEAD")

    result = scoped_git_publish.integrate_remote_and_resume(
        repo=repo, manifest=manifest, branch="main", remote="origin", commit_sha=original
    )

    assert result["mode"] == "integrate-remote-and-resume"
    assert result["original_commit"] == original
    assert result["commit"] != original
    assert git(repo, "rev-parse", "HEAD^") == remote_advance
    assert git(repo, "rev-parse", "refs/remotes/origin/main") == result["commit"]
    assert (repo / "unrelated.tmp").read_text() == "preserve me\n"


def test_integrate_remote_aborts_conflict_and_restores_head(
    publish_repo: tuple[Path, Path], tmp_path: Path,
) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("local change\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "fix: local")
    original = git(repo, "rev-parse", "HEAD")

    writer = remote_writer(repo, tmp_path)
    (writer / "included.txt").write_text("remote change\n")
    git(writer, "add", "included.txt")
    git(writer, "commit", "-m", "fix: remote")
    git(writer, "push", "origin", "main")
    remote_advance = git(writer, "rev-parse", "HEAD")

    with pytest.raises(
        scoped_git_publish.PublishError,
        match=r"rebase aborted and HEAD restored.*conflict_paths=\['included.txt'\]",
    ):
        scoped_git_publish.integrate_remote_and_resume(
            repo=repo, manifest=manifest, branch="main", remote="origin", commit_sha=original
        )

    assert git(repo, "rev-parse", "HEAD") == original
    assert git(repo, "rev-parse", "refs/remotes/origin/main") == remote_advance
    assert git(repo, "status", "--short") == ""


def test_integrate_remote_rejects_tracked_worktree_changes(
    publish_repo: tuple[Path, Path],
) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("local change\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "fix: local")
    original = git(repo, "rev-parse", "HEAD")
    (repo / "excluded.txt").write_text("dirty\n")

    with pytest.raises(scoped_git_publish.PublishError, match="tracked worktree is not clean"):
        scoped_git_publish.integrate_remote_and_resume(
            repo=repo, manifest=manifest, branch="main", remote="origin", commit_sha=original
        )


def test_isolated_integration_preserves_dirty_source_and_pushes_overlay(
    publish_repo: tuple[Path, Path], tmp_path: Path,
) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("local committed change\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "fix: local")
    source_commit = git(repo, "rev-parse", "HEAD")
    (repo / "overlay.txt").write_text("overlay change\n")
    (repo / "excluded.txt").write_text("unrelated dirty change\n")
    manifest.write_text("included.txt\noverlay.txt\n")
    overlay_manifest = tmp_path / "overlay-scope.txt"
    overlay_manifest.write_text("overlay.txt\n")

    writer = remote_writer(repo, tmp_path)
    (writer / "remote.txt").write_text("remote change\n")
    git(writer, "add", "remote.txt")
    git(writer, "commit", "-m", "fix: remote")
    git(writer, "push", "origin", "main")

    result = scoped_git_publish.isolated_integrate_and_resume(
        repo=repo,
        manifest=manifest,
        overlay_manifest=overlay_manifest,
        message="fix: overlay",
        branch="main",
        remote="origin",
        commit_sha=source_commit,
    )

    assert result["mode"] == "isolated-integrate-remote-and-resume"
    assert result["source_commit"] == source_commit
    assert git(repo, "rev-parse", "HEAD") == source_commit
    assert git(repo, "status", "--short") == "M excluded.txt\n?? overlay.txt"
    assert git(repo, "ls-remote", "--heads", "origin", "main").split()[0] == result["commit"]


def test_isolated_reconcile_uses_verified_overlay_for_approved_conflict(
    publish_repo: tuple[Path, Path], tmp_path: Path,
) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("local committed change\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "fix: local")
    source_commit = git(repo, "rev-parse", "HEAD")

    writer = remote_writer(repo, tmp_path)
    (writer / "included.txt").write_text("remote change\n")
    git(writer, "add", "included.txt")
    git(writer, "commit", "-m", "fix: remote")
    git(writer, "push", "origin", "main")

    (repo / "included.txt").write_text("remote change\nlocal committed change\n")
    overlay_manifest = tmp_path / "overlay-scope.txt"
    overlay_manifest.write_text("included.txt\n")
    source_status = git(repo, "status", "--short")

    result = scoped_git_publish.isolated_reconcile_and_resume(
        repo=repo,
        manifest=manifest,
        overlay_manifest=overlay_manifest,
        message="fix: reconcile conflict",
        branch="main",
        remote="origin",
        commit_sha=source_commit,
    )

    assert result["mode"] == "isolated-reconcile-remote-and-resume"
    assert result["conflict_paths"] == ["included.txt"]
    assert git(repo, "rev-parse", "HEAD") == source_commit
    assert git(repo, "status", "--short") == source_status
    assert (repo / "included.txt").read_text() == "remote change\nlocal committed change\n"
    published = git(repo, "ls-remote", "--heads", "origin", "main").split()[0]
    assert published == result["commit"]


def test_isolated_reconcile_auto_merges_clean_same_path_edits(
    publish_repo: tuple[Path, Path], tmp_path: Path,
) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("one\ntwo\nthree\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "test: establish merge base")
    git(repo, "push", "origin", "main")
    (repo / "included.txt").write_text("LOCAL\ntwo\nthree\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "fix: local first line")
    source_commit = git(repo, "rev-parse", "HEAD")

    writer = remote_writer(repo, tmp_path)
    (writer / "included.txt").write_text("one\ntwo\nREMOTE\n")
    git(writer, "add", "included.txt")
    git(writer, "commit", "-m", "fix: remote third line")
    git(writer, "push", "origin", "main")

    (repo / "overlay.txt").write_text("reviewed overlay\n")
    manifest.write_text("included.txt\noverlay.txt\n")
    overlay_manifest = tmp_path / "overlay-scope.txt"
    overlay_manifest.write_text("overlay.txt\n")
    source_status = git(repo, "status", "--short")

    result = scoped_git_publish.isolated_reconcile_and_resume(
        repo=repo,
        manifest=manifest,
        overlay_manifest=overlay_manifest,
        message="fix: merge clean overlap",
        branch="main",
        remote="origin",
        commit_sha=source_commit,
    )

    assert result["auto_merged_paths"] == ["included.txt"]
    assert result["conflict_paths"] == []
    assert git(repo, "rev-parse", "HEAD") == source_commit
    assert git(repo, "status", "--short") == source_status
