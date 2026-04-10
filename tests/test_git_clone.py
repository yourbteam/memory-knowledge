import os
from types import SimpleNamespace

import pytest
from git import Repo

from memory_knowledge.git.clone import (
    _inject_github_token,
    checkout_commit,
    ensure_repo,
    list_python_files,
)
from memory_knowledge.git.diff import changed_files


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temp git repo with 2 commits and Python files."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    repo = Repo.init(repo_dir)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()

    # Commit 1: add main.py
    main_py = repo_dir / "main.py"
    main_py.write_text("def hello():\n    return 'hello'\n")
    repo.index.add(["main.py"])
    commit1 = repo.index.commit("Add main.py")

    # Commit 2: add utils.py, modify main.py
    utils_py = repo_dir / "utils.py"
    utils_py.write_text("def helper():\n    pass\n")
    main_py.write_text("def hello():\n    return 'hello world'\n")
    repo.index.add(["utils.py", "main.py"])
    commit2 = repo.index.commit("Add utils.py, modify main.py")

    return repo, str(commit1), str(commit2)


def test_ensure_repo_clone(tmp_path, temp_git_repo):
    source_repo, _, _ = temp_git_repo
    clone_base = tmp_path / "clones"
    clone_base.mkdir()

    repo = ensure_repo("my-repo", str(source_repo.working_dir), str(clone_base))
    assert (clone_base / "my-repo" / ".git").exists()
    assert isinstance(repo, Repo)


def test_ensure_repo_fetch_existing(tmp_path, temp_git_repo):
    source_repo, _, _ = temp_git_repo
    clone_base = tmp_path / "clones"
    clone_base.mkdir()

    # Clone first
    repo1 = ensure_repo("my-repo", str(source_repo.working_dir), str(clone_base))
    # Fetch again — should not fail
    repo2 = ensure_repo("my-repo", str(source_repo.working_dir), str(clone_base))
    assert isinstance(repo2, Repo)


def test_ensure_repo_no_url_raises(tmp_path):
    with pytest.raises(ValueError, match="No origin_url"):
        ensure_repo("missing-repo", None, str(tmp_path))


def test_inject_github_token_preserves_non_github_urls():
    url = "https://gitlab.example.com/team/repo.git"
    assert _inject_github_token(url, "token") == url


def test_inject_github_token_uses_existing_username():
    url = "https://yourbteam@github.com/thebteambg/FCSAPI.git"
    assert _inject_github_token(url, "secret") == "https://yourbteam:secret@github.com/thebteambg/FCSAPI.git"


def test_inject_github_token_uses_default_username_when_missing():
    url = "https://github.com/thebteambg/FCSAPI.git"
    assert _inject_github_token(url, "secret") == "https://x-access-token:secret@github.com/thebteambg/FCSAPI.git"


def test_ensure_repo_clone_uses_temp_authenticated_url_and_restores_origin(monkeypatch, tmp_path):
    clone_base = tmp_path / "clones"
    clone_base.mkdir()
    captured: dict[str, str] = {}

    class FakeOrigin:
        def __init__(self):
            self.url = ""

        def set_url(self, url):
            self.url = url

    fake_origin = FakeOrigin()
    fake_repo = SimpleNamespace(remotes=SimpleNamespace(origin=fake_origin))

    def fake_clone_from(url, dest):
        captured["url"] = url
        captured["dest"] = dest
        return fake_repo

    monkeypatch.setattr("memory_knowledge.git.clone.Repo.clone_from", fake_clone_from)

    ensure_repo(
        "fcsapi",
        "https://yourbteam@github.com/thebteambg/FCSAPI.git",
        str(clone_base),
        github_token="secret",
    )

    assert captured["url"] == "https://yourbteam:secret@github.com/thebteambg/FCSAPI.git"
    assert fake_origin.url == "https://yourbteam@github.com/thebteambg/FCSAPI.git"


def test_ensure_repo_fetch_uses_temp_authenticated_url_and_restores_origin(monkeypatch, tmp_path):
    repo_dir = tmp_path / "clones" / "fcsapi" / ".git"
    repo_dir.mkdir(parents=True)
    fetch_calls: list[str] = []
    set_urls: list[str] = []

    class FakeOrigin:
        def __init__(self):
            self.url = "https://yourbteam@github.com/thebteambg/FCSAPI.git"

        def set_url(self, url):
            self.url = url
            set_urls.append(url)

        def fetch(self):
            fetch_calls.append(self.url)

    fake_repo = SimpleNamespace(remotes=SimpleNamespace(origin=FakeOrigin()))
    monkeypatch.setattr("memory_knowledge.git.clone.Repo", lambda path: fake_repo)

    ensure_repo(
        "fcsapi",
        "https://yourbteam@github.com/thebteambg/FCSAPI.git",
        str(tmp_path / "clones"),
        github_token="secret",
    )

    assert fetch_calls == ["https://yourbteam:secret@github.com/thebteambg/FCSAPI.git"]
    assert set_urls[-1] == "https://yourbteam@github.com/thebteambg/FCSAPI.git"


def test_list_python_files(temp_git_repo):
    repo, _, _ = temp_git_repo
    files = list_python_files(repo)
    assert sorted(files) == ["main.py", "utils.py"]


def test_checkout_commit(temp_git_repo):
    repo, commit1_sha, commit2_sha = temp_git_repo
    # At HEAD (commit2), both files exist
    files_head = list_python_files(repo)
    assert "utils.py" in files_head

    # Checkout commit1 — only main.py
    checkout_commit(repo, commit1_sha)
    files_c1 = list_python_files(repo)
    assert "main.py" in files_c1
    assert "utils.py" not in files_c1


def test_changed_files(temp_git_repo):
    repo, commit1_sha, commit2_sha = temp_git_repo
    changes = changed_files(repo, commit1_sha, commit2_sha)
    assert changes is not None
    assert sorted(changes) == ["main.py", "utils.py"]


def test_changed_files_none_old_sha(temp_git_repo):
    repo, _, commit2_sha = temp_git_repo
    result = changed_files(repo, None, commit2_sha)
    assert result is None  # signals full ingestion
