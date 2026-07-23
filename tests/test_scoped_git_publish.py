from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import (
    prevention_source_receipt,
    scoped_git_publish,
    sequence_intake_adapters,
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _prepared_intake(
    *,
    artifact_path: str,
    operation: str,
) -> dict[str, object]:
    effectful = operation == "publish"
    argv = [
        "python3", "scripts/scoped_git_publish.py",
        "--repo", "/repo",
        "--manifest", artifact_path,
        "--message", "Publish approved scope",
        "--branch", "main",
        "--remote", "origin",
    ]
    if effectful:
        argv.append("--execute")
    return {
        "schema_version": 1,
        "sequence_id": "commit-push-main",
        "profile": operation,
        "artifacts": {
            "approved_paths": {
                "content": "included.txt\n",
                "path": artifact_path,
            },
        },
        "argv": argv,
        "authorization": {
            "effectful": effectful,
            "required": effectful,
            "operation": operation,
        },
    }


def test_sequence_uses_git_push_not_github_cli_as_authentication_boundary() -> None:
    sequence = (
        Path(__file__).resolve().parents[1]
        / "operations/sequences/commit-push-main/sequence.md"
    ).read_text(encoding="utf-8")

    assert "GitHub CLI authentication is not a prerequisite" in sequence
    assert "`gh auth status` must not gate this sequence" in sequence
    assert "Only the actual `git push` result" in sequence


def test_no_argument_main_materializes_semantic_intake_and_runs_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []

    def collect_and_prepare(sequence_id, *, artifact_paths, **kwargs):
        calls.append(("collect", sequence_id))
        return _prepared_intake(
            artifact_path=artifact_paths["approved_paths"],
            operation="dry-run",
        )

    monkeypatch.setattr(
        sequence_intake_adapters, "collect_and_prepare", collect_and_prepare,
    )
    monkeypatch.setattr(
        scoped_git_publish,
        "publish",
        lambda **kwargs: calls.append((
            "publish",
            kwargs["manifest"].read_text(encoding="utf-8"),
            kwargs["execute"],
        )) or {"ok": True, "mode": "dry-run"},
    )

    assert scoped_git_publish.main([]) == 0
    assert calls == [
        ("collect", "commit-push-main"),
        ("publish", "included.txt\n", False),
    ]
    captured = capsys.readouterr()
    assert '"event": "intake-prepared"' in captured.err
    assert json.loads(captured.out) == {"mode": "dry-run", "ok": True}


def test_no_argument_publish_requires_authorization_after_review(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def collect_and_prepare(sequence_id, *, artifact_paths, **kwargs):
        return _prepared_intake(
            artifact_path=artifact_paths["approved_paths"],
            operation="publish",
        )

    monkeypatch.setattr(
        sequence_intake_adapters, "collect_and_prepare", collect_and_prepare,
    )
    monkeypatch.setattr(
        scoped_git_publish.script_intake,
        "collect",
        lambda spec: {"authorize": False},
    )
    monkeypatch.setattr(
        scoped_git_publish,
        "publish",
        lambda **kwargs: pytest.fail("declined publication must not run"),
    )

    assert scoped_git_publish.main([]) == 130
    captured = capsys.readouterr()
    assert '"event": "intake-prepared"' in captured.err
    assert '"error": "effect-authorization-declined"' in captured.err


def test_no_argument_publish_dispatches_only_after_authorization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []

    def collect_and_prepare(sequence_id, *, artifact_paths, **kwargs):
        return _prepared_intake(
            artifact_path=artifact_paths["approved_paths"],
            operation="publish",
        )

    monkeypatch.setattr(
        sequence_intake_adapters, "collect_and_prepare", collect_and_prepare,
    )
    monkeypatch.setattr(
        scoped_git_publish.script_intake,
        "collect",
        lambda spec: calls.append(("authorize", spec)) or {"authorize": True},
    )
    monkeypatch.setattr(
        scoped_git_publish,
        "publish",
        lambda **kwargs: calls.append((
            "publish",
            kwargs["manifest"].read_text(encoding="utf-8"),
            kwargs["execute"],
        )) or {"ok": True, "mode": "execute"},
    )

    assert scoped_git_publish.main([]) == 0
    assert calls == [
        ("authorize", scoped_git_publish.EFFECT_AUTHORIZATION_SPEC),
        ("publish", "included.txt\n", True),
    ]
    assert json.loads(capsys.readouterr().out) == {
        "mode": "execute",
        "ok": True,
    }


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


def test_dry_run_accepts_the_contract_without_a_commit_message(
    publish_repo: tuple[Path, Path],
) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("changed\n")

    result = scoped_git_publish.publish(
        repo=repo, manifest=manifest, message="", branch="main",
        remote="origin", execute=False,
    )

    assert result["mode"] == "dry-run"
    assert git(repo, "diff", "--cached", "--name-only") == ""


def test_manifest_accepts_the_materialized_contract_json_list(
    publish_repo: tuple[Path, Path],
) -> None:
    repo, manifest = publish_repo
    manifest.write_text(json.dumps(["included.txt"]), encoding="utf-8")
    (repo / "included.txt").write_text("changed\n")

    result = scoped_git_publish.publish(
        repo=repo, manifest=manifest, message="", branch="main",
        remote="origin", execute=False,
    )

    assert result["paths"] == ["included.txt"]


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


def test_prevention_publish_binds_commit_and_source_receipt_before_remote_effect(
    publish_repo: tuple[Path, Path], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    repo, manifest = publish_repo
    (repo / "included.txt").write_text("prevention change\n")
    monkeypatch.setattr(prevention_source_receipt, "ROOT", tmp_path / "receipts")

    returncode = scoped_git_publish.main([
        "--repo", str(repo), "--manifest", str(manifest),
        "--message", "fix: prevention", "--branch", "main",
        "--remote", "origin", "--execute",
        "--prevention-effect-id", "e" * 64,
        "--prevention-preparation-sha256", "f" * 64,
    ])

    result = json.loads(capsys.readouterr().out)
    message = git(repo, "show", "-s", "--format=%B", "HEAD")
    receipt = json.loads(
        prevention_source_receipt.receipt_path("e" * 64).read_text(encoding="utf-8")
    )
    assert returncode == 0
    assert "Prevention-Effect-ID: " + "e" * 64 in message
    assert "Prevention-Preparation-SHA256: " + "f" * 64 in message
    assert receipt["status"] == "APPLIED"
    assert receipt["result_identity"]["commit"] == result["commit"]
    assert result["preventionSourceReceiptSha256"] == (
        prevention_source_receipt.receipt_sha256(receipt)
    )


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


def test_isolated_reconcile_ignores_older_local_commits_outside_overlay_scope(
    publish_repo: tuple[Path, Path], tmp_path: Path,
) -> None:
    repo, manifest = publish_repo
    (repo / "excluded.txt").write_text("older unrelated local commit\n")
    git(repo, "add", "excluded.txt")
    git(repo, "commit", "-m", "test: unrelated local history")
    (repo / "included.txt").write_text("approved committed version\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "fix: approved local change")
    source_commit = git(repo, "rev-parse", "HEAD")

    writer = remote_writer(repo, tmp_path)
    (writer / "remote.txt").write_text("remote change\n")
    git(writer, "add", "remote.txt")
    git(writer, "commit", "-m", "fix: remote")
    git(writer, "push", "origin", "main")

    (repo / "included.txt").write_text("approved overlay version\n")
    overlay_manifest = tmp_path / "overlay-scope.txt"
    overlay_manifest.write_text("included.txt\n")
    source_status = git(repo, "status", "--short")

    result = scoped_git_publish.isolated_reconcile_and_resume(
        repo=repo,
        manifest=manifest,
        overlay_manifest=overlay_manifest,
        message="fix: publish narrow overlay",
        branch="main",
        remote="origin",
        commit_sha=source_commit,
    )

    assert git(repo, "rev-parse", "HEAD") == source_commit
    assert git(repo, "status", "--short") == source_status
    published = remote_writer(repo, tmp_path / "published")
    assert (published / "included.txt").read_text() == "approved overlay version\n"
    assert (published / "excluded.txt").read_text() == "before\n"
    assert (published / "remote.txt").read_text() == "remote change\n"
    assert result["paths"] == ["included.txt"]


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


def test_merge_commit_path_treats_multiple_conflicts_as_content_conflict(
    publish_repo: tuple[Path, Path], tmp_path: Path, monkeypatch,
) -> None:
    repo, _ = publish_repo
    (repo / "included.txt").write_text("base\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "test: establish merge base")
    merge_base = git(repo, "rev-parse", "HEAD")
    (repo / "included.txt").write_text("local\n")
    git(repo, "add", "included.txt")
    git(repo, "commit", "-m", "test: establish local change")
    local_commit = git(repo, "rev-parse", "HEAD")

    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "included.txt").write_text("remote\n")
    real_run = scoped_git_publish.subprocess.run

    def conflict_run(args, **kwargs):
        if len(args) > 1 and args[0:2] == ["git", "merge-file"]:
            return subprocess.CompletedProcess(args, 10, stdout=b"", stderr=b"")
        return real_run(args, **kwargs)

    monkeypatch.setattr(scoped_git_publish.subprocess, "run", conflict_run)

    assert not scoped_git_publish._merge_commit_path(
        repo, merge_base, local_commit, "included.txt", destination,
    )
