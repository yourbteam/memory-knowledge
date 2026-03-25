from __future__ import annotations

import asyncpg
import structlog
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient, models

logger = structlog.get_logger()


class FreshnessReport(BaseModel):
    latest_pg_commit: str | None = None
    qdrant_commit_shas: list[str] = []
    is_stale: bool = False
    stale_point_count: int = 0


async def check_freshness(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    repository_key: str,
) -> FreshnessReport:
    """Check if Qdrant projections are up-to-date with the latest PG revision."""
    report = FreshnessReport()

    # Get latest PG revision
    row = await pool.fetchrow(
        """
        SELECT rr.commit_sha
        FROM catalog.repo_revisions rr
        JOIN catalog.repositories r ON rr.repository_id = r.id
        WHERE r.repository_key = $1
        ORDER BY rr.created_utc DESC
        LIMIT 1
        """,
        repository_key,
    )
    if row is None:
        return report  # no revisions ingested yet

    report.latest_pg_commit = row["commit_sha"]

    # Scroll Qdrant active points and collect commit_shas
    commit_shas: set[str] = set()
    stale_count = 0
    scroll_offset = None

    while True:
        results, next_offset = await qdrant_client.scroll(
            collection_name="code_chunks",
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="repository_key",
                        match=models.MatchValue(value=repository_key),
                    ),
                    models.FieldCondition(
                        key="is_active",
                        match=models.MatchValue(value=True),
                    ),
                ]
            ),
            limit=100,
            offset=scroll_offset,
            with_payload=True,
        )

        for p in results:
            sha = p.payload.get("commit_sha") if p.payload else None
            if sha:
                commit_shas.add(sha)
                if sha != report.latest_pg_commit:
                    stale_count += 1

        if next_offset is None:
            break
        scroll_offset = next_offset

    report.qdrant_commit_shas = list(commit_shas)
    report.stale_point_count = stale_count
    report.is_stale = stale_count > 0

    logger.info(
        "freshness_check_complete",
        latest_pg=report.latest_pg_commit,
        qdrant_shas=len(commit_shas),
        is_stale=report.is_stale,
        stale_points=stale_count,
    )
    return report
