from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import commit_push_main_launch as launch


def answers(*values: str):
    remaining = iter(values)
    return lambda _prompt: next(remaining)


def test_no_argument_dry_run_collects_numbered_choices_and_calls_minimal_publisher(
    monkeypatch,
) -> None:
    calls = []
    output = []
    repo = Path("/repo").resolve()
    monkeypatch.setattr(
        launch, "_repository_choices", lambda: [("memory-knowledge", repo)]
    )
    monkeypatch.setattr(
        launch.minimal_git_publish,
        "changed_paths",
        lambda _repo: ["approved.txt", "unrelated.txt"],
    )
    monkeypatch.setattr(launch, "_current_branch", lambda _repo: "feature")
    monkeypatch.setattr(
        launch.minimal_git_publish,
        "publish",
        lambda **kwargs: calls.append(kwargs) or {"ok": True, "mode": "dry-run"},
    )

    result = launch.main(
        [],
        input_fn=answers(
            "1", "1", "1", "git diff --check --cached -- approved.txt", "", ""
        ),
        output_fn=output.append,
    )

    assert result == 0
    assert len(calls) == 1
    assert calls[0]["repo"] == repo
    assert calls[0]["verification"] == [
        "git", "diff", "--check", "--cached", "--", "approved.txt"
    ]
    assert calls[0]["branch"] == "feature"
    assert calls[0]["remote"] == "origin"
    assert calls[0]["execute"] is False
    assert json.loads(output[-1]) == {"ok": True, "mode": "dry-run"}
    assert "1. Dry run" in output
    assert "2. Commit and push" in output
    assert "1. approved.txt" in output
    assert "2. unrelated.txt" in output


def test_publish_decline_never_calls_publisher(monkeypatch, capsys) -> None:
    repo = Path("/repo").resolve()
    monkeypatch.setattr(launch, "_repository_choices", lambda: [("repo", repo)])
    monkeypatch.setattr(
        launch.minimal_git_publish, "changed_paths", lambda _repo: ["approved.txt"]
    )
    monkeypatch.setattr(launch, "_current_branch", lambda _repo: "main")
    monkeypatch.setattr(
        launch.minimal_git_publish,
        "publish",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("published")),
    )

    result = launch.main(
        [],
        input_fn=answers(
            "2", "1", "1", "git diff --check --cached -- approved.txt",
            "", "", "approved message", "1",
        ),
        output_fn=lambda _message: None,
    )

    assert result == 130
    assert json.loads(capsys.readouterr().err) == {
        "ok": False,
        "error": "commit and push declined",
    }


def test_arguments_are_rejected_before_interview(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        launch,
        "_run_interview",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("interview ran")),
    )

    assert launch.main(["--task-id", "hand-written"]) == 2
    assert json.loads(capsys.readouterr().err) == {
        "ok": False,
        "error": "no-argument-entrypoint-required",
    }


def test_launcher_has_no_lifecycle_or_ingestion_dependency() -> None:
    source = Path(launch.__file__).read_text(encoding="utf-8")

    assert "work_memory" not in source
    assert "sequence_guard" not in source
    assert "sequence_intake" not in source
    assert "published_commit_ingestion" not in source
    assert "prevention_" not in source


def test_authoritative_routes_use_only_the_minimal_launcher() -> None:
    root = Path(launch.__file__).resolve().parents[1]
    runner = (root / "skills/sequence-runner/SKILL.md").read_text(encoding="utf-8")
    registry = (root / "operations/sequences/SEQUENCES.md").read_text(
        encoding="utf-8"
    )
    exception = runner.split("Exception for every commit/push task:", 1)[1].split(
        "\n\n", 1
    )[0]
    registry_row = next(
        line for line in registry.splitlines() if line.startswith("| `commit-push-main`")
    )

    assert "python3 scripts/commit_push_main_launch.py" in exception
    assert "sequence_intake_launch.py" in exception
    assert "Do not classify, select, activate" in exception
    assert "Git common directory" in runner
    assert "reach the configured Git" in runner
    assert "index.lock" in runner
    assert "scripts/commit_push_main_launch.py" in registry_row
    assert "scripts/scoped_git_publish.py" not in registry_row


def test_default_interview_publishes_end_to_end_to_disposable_remote(
    tmp_path: Path, monkeypatch,
) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    repo = tmp_path / "repo"
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "launch@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Launch Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", str(remote)],
        check=True,
    )
    (repo / "approved.txt").write_text("before\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("before\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "approved.txt", "unrelated.txt"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "baseline"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "push", "-u", "origin", "main"],
        check=True,
        capture_output=True,
    )
    (repo / "approved.txt").write_text("published\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("still local\n", encoding="utf-8")
    monkeypatch.setattr(launch, "_repository_choices", lambda: [("fixture", repo)])

    result = launch.main(
        [],
        input_fn=answers(
            "2", "1", "1", "git diff --check --cached -- approved.txt",
            "", "", "publish through default interview", "2",
        ),
        output_fn=lambda _message: None,
    )

    local_head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    committed = subprocess.run(
        ["git", "-C", str(repo), "show", "--format=", "--name-only", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    remaining = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert result == 0
    assert local_head == remote_head
    assert committed == "approved.txt"
    assert remaining == "unrelated.txt"
