from __future__ import annotations

import os
from pathlib import Path

import structlog
from git import Repo

logger = structlog.get_logger()


def ensure_repo(
    repository_key: str,
    origin_url: str | None,
    clone_base_path: str,
) -> Repo:
    """Clone if missing, fetch if present. Returns a gitpython Repo."""
    repo_dir = Path(clone_base_path) / repository_key
    if repo_dir.exists() and (repo_dir / ".git").exists():
        logger.info("git_fetch", repository_key=repository_key, path=str(repo_dir))
        repo = Repo(repo_dir)
        repo.remotes.origin.fetch()
        return repo
    if origin_url is None:
        raise ValueError(
            f"No origin_url for {repository_key} and no local clone exists"
        )
    logger.info(
        "git_clone", repository_key=repository_key, origin_url=origin_url
    )
    os.makedirs(repo_dir.parent, exist_ok=True)
    return Repo.clone_from(origin_url, str(repo_dir))


def checkout_commit(repo: Repo, commit_sha: str) -> None:
    """Detached HEAD checkout of a specific commit."""
    repo.git.checkout(commit_sha, force=True)
    logger.info("git_checkout", commit_sha=commit_sha)


def list_source_files(
    repo: Repo, extensions: set[str] | None = None
) -> list[str]:
    """Return repo-relative paths of source files tracked at HEAD.

    If extensions is None, returns all blob files.
    Otherwise filters by file extension (e.g., {".py", ".ts"}).
    """
    return [
        item.path
        for item in repo.head.commit.tree.traverse()
        if item.type == "blob"
        and (extensions is None or any(item.path.endswith(ext) for ext in extensions))
    ]


def list_python_files(repo: Repo) -> list[str]:
    """Deprecated: use list_source_files(repo, {".py"}) instead."""
    return list_source_files(repo, {".py"})
