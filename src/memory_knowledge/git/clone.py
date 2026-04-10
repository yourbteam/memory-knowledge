from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import structlog
from git import Repo

logger = structlog.get_logger()


def _inject_github_token(
    origin_url: str,
    github_token: str | None,
    *,
    default_username: str = "x-access-token",
) -> str:
    """Return a temporary authenticated GitHub HTTPS URL without mutating the stored origin."""
    if not github_token:
        return origin_url

    parts = urlsplit(origin_url)
    if parts.scheme != "https" or parts.hostname != "github.com":
        return origin_url

    username = parts.username or default_username
    auth_netloc = f"{username}:{github_token}@{parts.hostname}"
    if parts.port:
        auth_netloc = f"{auth_netloc}:{parts.port}"
    return urlunsplit((parts.scheme, auth_netloc, parts.path, parts.query, parts.fragment))


def ensure_repo(
    repository_key: str,
    origin_url: str | None,
    clone_base_path: str,
    *,
    github_token: str | None = None,
    github_https_username: str = "x-access-token",
) -> Repo:
    """Clone if missing, fetch if present. Returns a gitpython Repo."""
    repo_dir = Path(clone_base_path) / repository_key
    if repo_dir.exists() and (repo_dir / ".git").exists():
        logger.info("git_repo_found", repository_key=repository_key, path=str(repo_dir))
        repo = Repo(repo_dir)
        original_remote_url = repo.remotes.origin.url
        fetch_url = _inject_github_token(
            origin_url or original_remote_url,
            github_token,
            default_username=github_https_username,
        )
        try:
            if fetch_url != original_remote_url:
                repo.remotes.origin.set_url(fetch_url)
            repo.remotes.origin.fetch()
            logger.info("git_fetch_complete", repository_key=repository_key)
        except Exception as e:
            logger.warning("git_fetch_skipped", repository_key=repository_key, error=str(e))
        finally:
            if fetch_url != original_remote_url:
                repo.remotes.origin.set_url(origin_url or original_remote_url)
        return repo
    if origin_url is None:
        raise ValueError(
            f"No origin_url for {repository_key} and no local clone exists"
        )
    logger.info(
        "git_clone", repository_key=repository_key, origin_url=origin_url
    )
    os.makedirs(repo_dir.parent, exist_ok=True)
    clone_url = _inject_github_token(
        origin_url,
        github_token,
        default_username=github_https_username,
    )
    repo = Repo.clone_from(clone_url, str(repo_dir))
    if clone_url != origin_url:
        repo.remotes.origin.set_url(origin_url)
    return repo


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
