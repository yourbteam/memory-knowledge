from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import minimal_git_publish as publish


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def publish_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
    )
    repo = tmp_path / "repo"
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)],
        check=True,
        capture_output=True,
    )
    git(repo, "config", "user.email", "publish-test@example.invalid")
    git(repo, "config", "user.name", "Publish Test")
    git(repo, "remote", "add", "origin", str(remote))
    (repo / "approved.txt").write_text("before\n", encoding="utf-8")
    (repo / "removed.txt").write_text("before\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("before\n", encoding="utf-8")
    git(repo, "add", "--", "approved.txt", "removed.txt", "unrelated.txt")
    git(repo, "commit", "-m", "baseline")
    git(repo, "push", "-u", "origin", "main")

    (repo / "approved.txt").write_text("approved change\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("unrelated change\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(["approved.txt"]), encoding="utf-8")
    return repo, remote, manifest


def verification(*paths: str) -> list[str]:
    return ["git", "diff", "--check", "--cached", "--", *paths]


def remote_head(remote: Path) -> str:
    return subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def real_object_files(repo: Path) -> set[str]:
    common_dir = Path(git(repo, "rev-parse", "--git-common-dir").stdout.strip())
    if not common_dir.is_absolute():
        common_dir = repo / common_dir
    object_dir = common_dir.resolve() / "objects"
    return {
        path.relative_to(object_dir).as_posix()
        for path in object_dir.rglob("*")
        if path.is_file()
    }


def test_dry_run_exercises_exact_scope_without_mutating_real_index(
    publish_repo: tuple[Path, Path, Path],
) -> None:
    repo, remote, manifest = publish_repo
    head_before = git(repo, "rev-parse", "HEAD").stdout.strip()

    result = publish.publish(
        repo=repo,
        manifest=manifest,
        verification=verification("approved.txt"),
        message="",
        branch="main",
        remote="origin",
        execute=False,
    )

    assert result["ok"] is True
    assert result["mode"] == "dry-run"
    assert result["paths"] == ["approved.txt"]
    assert result["verification"]["exit"] == 0
    assert git(repo, "diff", "--cached", "--name-only").stdout == ""
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == head_before
    assert remote_head(remote) == head_before


def test_dry_run_does_not_write_real_git_object_database(
    publish_repo: tuple[Path, Path, Path],
) -> None:
    repo, _remote, manifest = publish_repo
    (repo / "new-approved.txt").write_text(
        "content not already stored by Git\n", encoding="utf-8"
    )
    manifest.write_text(json.dumps(["new-approved.txt"]), encoding="utf-8")
    objects_before = real_object_files(repo)

    publish.publish(
        repo=repo,
        manifest=manifest,
        verification=verification("new-approved.txt"),
        message="",
        branch="main",
        remote="origin",
        execute=False,
    )

    assert real_object_files(repo) == objects_before


def test_dry_run_does_not_leak_temporary_git_environment_to_verification(
    publish_repo: tuple[Path, Path, Path],
) -> None:
    repo, _remote, manifest = publish_repo
    command = [
        sys.executable,
        "-c",
        (
            "import os, sys; "
            "sys.exit(any(name in os.environ for name in "
            "('GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY')))"
        ),
    ]

    result = publish.publish(
        repo=repo,
        manifest=manifest,
        verification=command,
        message="",
        branch="main",
        remote="origin",
        execute=False,
    )

    assert result["verification"]["exit"] == 0


def test_publish_commits_exact_scope_pushes_and_confirms_fresh_remote(
    publish_repo: tuple[Path, Path, Path],
) -> None:
    repo, remote, manifest = publish_repo

    result = publish.publish(
        repo=repo,
        manifest=manifest,
        verification=verification("approved.txt"),
        message="publish exact scope",
        branch="main",
        remote="origin",
        execute=True,
    )

    assert result["ok"] is True
    assert result["commit"] == result["remote_commit"] == remote_head(remote)
    assert git(
        repo, "show", "--format=", "--name-only", result["commit"]
    ).stdout.strip() == "approved.txt"
    assert git(repo, "diff", "--name-only").stdout.strip() == "unrelated.txt"
    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_nonzero_relevant_verification_blocks_before_commit(
    publish_repo: tuple[Path, Path, Path],
) -> None:
    repo, _remote, manifest = publish_repo
    head_before = git(repo, "rev-parse", "HEAD").stdout.strip()

    with pytest.raises(publish.PublishError, match="exited 7"):
        publish.publish(
            repo=repo,
            manifest=manifest,
            verification=[sys.executable, "-c", "raise SystemExit(7)"],
            message="must not exist",
            branch="main",
            remote="origin",
            execute=True,
        )

    assert git(repo, "rev-parse", "HEAD").stdout.strip() == head_before
    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_verification_cannot_expand_the_commit_scope(
    publish_repo: tuple[Path, Path, Path],
) -> None:
    repo, _remote, manifest = publish_repo
    head_before = git(repo, "rev-parse", "HEAD").stdout.strip()
    command = [
        sys.executable,
        "-c",
        "import subprocess; subprocess.run(['git', 'add', 'unrelated.txt'], check=True)",
    ]

    with pytest.raises(publish.PublishError, match="staged paths differ after verification"):
        publish.publish(
            repo=repo,
            manifest=manifest,
            verification=command,
            message="must not include unrelated",
            branch="main",
            remote="origin",
            execute=True,
        )

    assert git(repo, "rev-parse", "HEAD").stdout.strip() == head_before
    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_verification_cannot_change_selected_content_after_staging(
    publish_repo: tuple[Path, Path, Path],
) -> None:
    repo, _remote, manifest = publish_repo
    head_before = git(repo, "rev-parse", "HEAD").stdout.strip()
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; Path('approved.txt').write_text('changed by verification\\n')",
    ]

    with pytest.raises(
        publish.PublishError, match="verification changed selected files after staging"
    ):
        publish.publish(
            repo=repo,
            manifest=manifest,
            verification=command,
            message="must not commit unverified content",
            branch="main",
            remote="origin",
            execute=True,
        )

    assert git(repo, "rev-parse", "HEAD").stdout.strip() == head_before
    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_tracked_deletion_is_a_valid_exact_manifest_change(
    publish_repo: tuple[Path, Path, Path],
) -> None:
    repo, remote, manifest = publish_repo
    (repo / "removed.txt").unlink()
    manifest.write_text(json.dumps(["removed.txt"]), encoding="utf-8")

    result = publish.publish(
        repo=repo,
        manifest=manifest,
        verification=verification("removed.txt"),
        message="remove tracked file",
        branch="main",
        remote="origin",
        execute=True,
    )

    assert result["paths"] == ["removed.txt"]
    assert result["commit"] == remote_head(remote)
    assert git(
        repo, "show", "--format=", "--name-only", result["commit"]
    ).stdout.strip() == "removed.txt"


def test_manifest_escape_is_rejected_before_staging(
    publish_repo: tuple[Path, Path, Path],
) -> None:
    repo, _remote, manifest = publish_repo
    manifest.write_text(json.dumps(["../outside.txt"]), encoding="utf-8")

    with pytest.raises(publish.PublishError, match="escapes repository"):
        publish.publish(
            repo=repo,
            manifest=manifest,
            verification=verification("approved.txt"),
            message="",
            branch="main",
            remote="origin",
            execute=False,
        )

    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_failed_push_preserves_one_local_commit_and_remote_state(
    publish_repo: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    repo, remote, manifest = publish_repo
    remote_before = remote_head(remote)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "missing.git"))

    with pytest.raises(publish.PublishError, match="local commit .* remains at HEAD"):
        publish.publish(
            repo=repo,
            manifest=manifest,
            verification=verification("approved.txt"),
            message="local after failed push",
            branch="main",
            remote="origin",
            execute=True,
        )

    assert git(repo, "rev-parse", "HEAD").stdout.strip() != remote_before
    assert remote_head(remote) == remote_before
    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_confirmation_mismatch_refuses_success(
    publish_repo: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _remote, manifest = publish_repo
    monkeypatch.setattr(
        publish, "_fresh_remote_confirmation", lambda _url, _branch: "0" * 40
    )

    with pytest.raises(publish.PublishError, match="remote confirmation mismatch"):
        publish.publish(
            repo=repo,
            manifest=manifest,
            verification=verification("approved.txt"),
            message="confirmation mismatch",
            branch="main",
            remote="origin",
            execute=True,
        )


def test_publish_pending_merge_preserves_two_parents_and_advances_target(
    tmp_path: Path,
) -> None:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.email", "publish-test@example.invalid")
    git(repo, "config", "user.name", "Publish Test")
    git(repo, "remote", "add", "origin", str(remote))
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-m", "base")
    git(repo, "push", "-u", "origin", "main")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "switch", "-c", "codex/topic")
    (repo / "source.txt").write_text("source\n", encoding="utf-8")
    git(repo, "add", "source.txt")
    git(repo, "commit", "-m", "source")
    source = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "switch", "-c", "codex/integrate-topic", base)
    git(repo, "merge", "--no-ff", "--no-commit", source)
    (repo / "resolution.txt").write_text("resolved\n", encoding="utf-8")
    manifest = tmp_path / "merge-manifest.json"
    manifest.write_text(json.dumps(["resolution.txt", "source.txt"]), encoding="utf-8")

    result = publish.publish(
        repo=repo,
        manifest=manifest,
        verification=verification("resolution.txt", "source.txt"),
        message="merge topic",
        branch="codex/integrate-topic",
        target_branch="main",
        remote="origin",
        execute=True,
    )

    assert result["commit"] == result["remote_commit"] == remote_head(remote)
    parents = git(repo, "show", "-s", "--format=%P", result["commit"]).stdout.split()
    assert parents == [base, source]
    assert result["target_branch"] == "main"
