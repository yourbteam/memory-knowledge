from __future__ import annotations

import structlog
from git import Repo

logger = structlog.get_logger()


def changed_files(
    repo: Repo, old_sha: str | None, new_sha: str
) -> list[str] | None:
    """Return list of changed .py files between two commits.

    Returns None if old_sha is None (signals full ingestion needed).
    """
    if old_sha is None:
        return None
    old_commit = repo.commit(old_sha)
    new_commit = repo.commit(new_sha)
    diff_index = old_commit.diff(new_commit)
    paths: set[str] = set()
    for d in diff_index:
        if d.a_path and d.a_path.endswith(".py"):
            paths.add(d.a_path)
        if d.b_path and d.b_path.endswith(".py"):
            paths.add(d.b_path)
    logger.info(
        "diff_computed",
        old_sha=old_sha,
        new_sha=new_sha,
        changed_count=len(paths),
    )
    return list(paths)
