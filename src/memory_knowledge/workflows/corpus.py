from __future__ import annotations

import time
import uuid

import asyncpg
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.db.qdrant import semantic_query_points
from memory_knowledge.identity.entity_key import corpus_entry_key
from memory_knowledge.llm.openai_client import embed_single
from memory_knowledge.projections.corpus_qdrant import (
    COLLECTION,
    deactivate_corpus_point,
    embed_and_upsert_corpus_entry,
)
from memory_knowledge.projections.corpus_writer import (
    deactivate_corpus_entry,
    supersede_corpus_entry,
    upsert_corpus_entry,
)
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

VALID_CORPUS_KINDS = {"directive_rationale", "playbook_detail", "example", "reference"}


async def run_upsert(
    *,
    kind: str,
    title: str,
    body_text: str,
    run_id: uuid.UUID,
    tags: list[str] | None = None,
    link_slug: str | None = None,
    confidence: float | None = None,
    supersedes_id: str | None = None,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    """Upsert a Tier-2 corpus entry: PG (source of truth) then embed->Qdrant.

    PG is authoritative. If the Qdrant embed/upsert fails, the entry remains in PG but the
    workflow returns an error (the entry is not yet searchable) — drift reconciliation is left
    to the service-wide integrity tooling, per the plan's R14.

    Identity (F1): entry_key is derived from (kind, link_slug, title). Editing the *body* of an
    entry upserts it in place; changing its *title* yields a NEW entry (the corpus intentionally
    holds many entries per link_slug). To replace an entry whose title changed, pass
    supersedes_id so the old one is retired — otherwise both remain active.

    Ordering (F2): the old entry is retired only AFTER the new one is durably embedded. An embed
    failure therefore leaves the old entry fully intact and searchable; the new (PG-only) row is
    reconciled by the integrity tooling. Do not move the supersede ahead of the embed.
    """
    start = time.monotonic()
    tool = "run_corpus_upsert_workflow"
    try:
        if pool is None or settings is None:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error", error="Missing required dependency: pool/settings."
            )
        if kind not in VALID_CORPUS_KINDS:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=tool,
                status="error",
                error=f"Invalid kind: {kind}. Must be one of: {', '.join(sorted(VALID_CORPUS_KINDS))}",
            )
        if not title or not body_text:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error", error="title and body_text are required."
            )

        entry_key = corpus_entry_key(kind, link_slug, title)
        supersedes_key = uuid.UUID(supersedes_id) if supersedes_id else None

        corpus_entry_id = await upsert_corpus_entry(
            pool,
            entry_key=entry_key,
            kind=kind,
            title=title,
            body_text=body_text,
            tags=tags,
            link_slug=link_slug,
            confidence=confidence,
            supersedes_key=supersedes_key,
        )

        if qdrant_client is not None:
            await embed_and_upsert_corpus_entry(
                client=qdrant_client,
                entry_key=str(entry_key),
                body_text=body_text,
                kind=kind,
                link_slug=link_slug,
                confidence=confidence,
                settings=settings,
            )

        if supersedes_key is not None:
            await supersede_corpus_entry(pool, supersedes_key)
            if qdrant_client is not None:
                await deactivate_corpus_point(qdrant_client, str(supersedes_key))

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("corpus_upsert_done", entry_key=str(entry_key), kind=kind)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=tool,
            status="success",
            data={"entry_key": str(entry_key), "corpus_entry_id": corpus_entry_id},
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("corpus_upsert_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id), tool_name=tool, status="error", error=str(exc), duration_ms=duration_ms
        )


async def run_deactivate(
    *,
    kind: str,
    title: str,
    run_id: uuid.UUID,
    link_slug: str | None = None,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
) -> WorkflowResult:
    """Soft-delete a Tier-2 corpus entry by identity (kind, link_slug, title).

    Used by the directives sync to prune orphans — entries whose rule was renamed or deleted
    from DIRECTIVES.md. Identity (F1): entry_key is derived the same way as the write path, so
    the caller passes the same fields it would pass to run_upsert.

    PG is authoritative: deactivate the PG row first, then the Qdrant point — but only if the PG
    row existed (they are written together, so a missing PG row means no Qdrant point either, and
    real Qdrant set_payload 404s on a missing point). Idempotent — a missing or already-inactive
    key is a no-op that still returns success, so re-running the sync never errors.
    """
    start = time.monotonic()
    tool = "corpus_deactivate"
    try:
        if pool is None:
            return WorkflowResult(
                run_id=str(run_id), tool_name=tool, status="error", error="Missing required dependency: pool."
            )
        if kind not in VALID_CORPUS_KINDS:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=tool,
                status="error",
                error=f"Invalid kind: {kind}. Must be one of: {', '.join(sorted(VALID_CORPUS_KINDS))}",
            )
        if not title:
            return WorkflowResult(run_id=str(run_id), tool_name=tool, status="error", error="title is required.")

        entry_key = corpus_entry_key(kind, link_slug, title)
        existed = await deactivate_corpus_entry(pool, entry_key)
        if existed and qdrant_client is not None:
            await deactivate_corpus_point(qdrant_client, str(entry_key))

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("corpus_deactivate_done", entry_key=str(entry_key), kind=kind)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=tool,
            status="success",
            data={"entry_key": str(entry_key)},
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("corpus_deactivate_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id), tool_name=tool, status="error", error=str(exc), duration_ms=duration_ms
        )


async def run_query(
    *,
    query_text: str,
    run_id: uuid.UUID,
    kind: str | None = None,
    link_slug: str | None = None,
    limit: int = 5,
    min_score: float | None = None,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    """Semantic search over the corpus. Embeds the query with the same model as the write
    path, filters is_active=true (+ optional kind/link_slug), and returns ranked entries.

    Ranking: vector similarity is primary; ``updated_utc`` recency is a tiebreaker so that,
    among entries of equal similarity, the freshest ranks first (conservative — recency never
    overrides a stronger similarity match). ``min_score`` (optional) drops hits below that
    cosine-similarity floor so weakly-related entries are not returned. Both are additive and
    default to the prior behaviour (no floor; Qdrant score order) when unset.
    """
    start = time.monotonic()
    tool = "corpus_query"
    try:
        if qdrant_client is None or settings is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=tool,
                status="error",
                error="Missing required dependency: qdrant_client/settings.",
            )
        if not query_text:
            return WorkflowResult(run_id=str(run_id), tool_name=tool, status="error", error="query_text is required.")

        query_vector = await embed_single(query_text, settings)

        must: list[models.Condition] = [models.FieldCondition(key="is_active", match=models.MatchValue(value=True))]
        if kind is not None:
            must.append(models.FieldCondition(key="kind", match=models.MatchValue(value=kind)))
        if link_slug is not None:
            must.append(models.FieldCondition(key="link_slug", match=models.MatchValue(value=link_slug)))

        points = await semantic_query_points(
            qdrant_client,
            collection_name=COLLECTION,
            query_vector=query_vector,
            limit=max(1, min(int(limit or 5), 50)),
            query_filter=models.Filter(must=must),
            with_payload=True,
        )

        results = [
            {
                "entry_key": p.payload.get("entry_key"),
                "kind": p.payload.get("kind"),
                "link_slug": p.payload.get("link_slug"),
                "score": p.score,
            }
            for p in points
        ]

        # Relevance floor: drop hits below the requested cosine-similarity threshold.
        if min_score is not None:
            results = [r for r in results if (r.get("score") or 0.0) >= min_score]

        # Enrich with title/body/recency from PG (authoritative), still excluding inactive rows.
        if pool is not None and results:
            keys = [uuid.UUID(r["entry_key"]) for r in results if r["entry_key"]]
            rows = await pool.fetch(
                "SELECT entry_key, title, body_text, updated_utc FROM memory.corpus_entries "
                "WHERE entry_key = ANY($1::uuid[]) AND is_active = TRUE",
                keys,
            )
            by_key = {str(r["entry_key"]): r for r in rows}
            for r in results:
                row = by_key.get(r["entry_key"])
                if row is not None:
                    r["title"] = row["title"]
                    r["body_text"] = row["body_text"]
                    r["updated_utc"] = row["updated_utc"].isoformat() if row["updated_utc"] else None
                    r["_recency"] = row["updated_utc"].timestamp() if row["updated_utc"] else 0.0

        # Rank: similarity primary, recency (updated_utc) as a tiebreaker. Two stable sorts —
        # recency first, then score — so equal-similarity entries keep newest-first order.
        results.sort(key=lambda r: r.pop("_recency", 0.0), reverse=True)
        results.sort(key=lambda r: r.get("score") or 0.0, reverse=True)

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=tool,
            status="success",
            data={"results": results, "count": len(results)},
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("corpus_query_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id), tool_name=tool, status="error", error=str(exc), duration_ms=duration_ms
        )
