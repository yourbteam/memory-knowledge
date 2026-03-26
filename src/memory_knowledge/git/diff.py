from __future__ import annotations

import structlog
from git import Repo

logger = structlog.get_logger()


def changed_files(
    repo: Repo,
    old_sha: str | None,
    new_sha: str,
    extensions: set[str] | None = None,
) -> list[str] | None:
    """Return list of changed source files between two commits.

    If extensions is provided, only include files matching those extensions.
    Returns None if old_sha is None (signals full ingestion needed).
    """
    if old_sha is None:
        return None
    old_commit = repo.commit(old_sha)
    new_commit = repo.commit(new_sha)
    diff_index = old_commit.diff(new_commit)
    paths: set[str] = set()
    for d in diff_index:
        for path in (d.a_path, d.b_path):
            if path and (
                extensions is None
                or any(path.endswith(ext) for ext in extensions)
            ):
                paths.add(path)
    logger.info(
        "diff_computed",
        old_sha=old_sha,
        new_sha=new_sha,
        changed_count=len(paths),
    )
    return list(paths)
