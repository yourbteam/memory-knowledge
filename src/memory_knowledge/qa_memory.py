from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

import asyncpg
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.db.qdrant import semantic_query_points
from memory_knowledge.identity.entity_key import NAMESPACE_MK
from memory_knowledge.llm.openai_client import embed_single

logger = structlog.get_logger()

QA_PAIRS_COLLECTION = "qa_pairs"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalized_tokens(text: str) -> set[str]:
    """Lowercased alphanumeric token set for lexical-overlap comparison."""
    return set(_TOKEN_RE.findall((text or "").lower()))


def _question_overlap(asked: set[str], candidate: str) -> float:
    """Jaccard overlap between the asked question's tokens and a candidate question's tokens."""
    other = _normalized_tokens(candidate)
    if not asked or not other:
        return 0.0
    union = len(asked | other)
    return (len(asked & other) / union) if union else 0.0


async def _resolve_repository_id(pool: asyncpg.Pool, repository_key: str) -> int | None:
    row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1",
        repository_key,
    )
    return row["id"] if row else None


def _normalize_question(q: str) -> str:
    return " ".join(q.strip().lower().split())


def _question_hash(q: str) -> str:
    # Same sha256 pattern as triage's _prompt_hash, but over the NORMALIZED question.
    return hashlib.sha256(_normalize_question(q).encode("utf-8")).hexdigest()


def _qa_pair_id(repository_key: str, question_hash: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE_MK, f"qa:{repository_key}:{question_hash}")


def _qa_payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "qa_pair_id": str(row["qa_pair_id"]),
        "repository_key": row["repository_key"],
        "feature_key": row.get("feature_key"),
        "is_active": True,
        "content_kind": "qa_pair",
    }


def _qa_point_from_row(row: dict[str, Any], embedding: list[float]) -> models.PointStruct:
    return models.PointStruct(
        id=str(row["qa_pair_id"]),
        vector=embedding,
        payload=_qa_payload_from_row(row),
    )


def _qdrant_filter(*, repository_key: str, feature_key: str | None = None) -> models.Filter:
    conditions: list[models.FieldCondition] = [
        models.FieldCondition(key="repository_key", match=models.MatchValue(value=repository_key)),
        models.FieldCondition(key="is_active", match=models.MatchValue(value=True)),
    ]
    if feature_key:
        conditions.append(models.FieldCondition(key="feature_key", match=models.MatchValue(value=feature_key)))
    return models.Filter(must=conditions)


async def ingest_qa_pairs(
    pool: asyncpg.Pool,
    settings: Settings,
    *,
    repository_key: str,
    pairs: list[dict[str, Any]],
    source: dict[str, Any] | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
) -> dict[str, Any]:
    logger.info("qa_ingest_start", repository_key=repository_key, pairs=len(pairs))
    repository_id = await _resolve_repository_id(pool, repository_key)
    if repository_id is None:
        raise ValueError(f"Repository '{repository_key}' not found")

    qa_pair_ids: list[uuid.UUID] = []
    skipped: list[dict[str, Any]] = []

    for pair in pairs:
        q = (pair.get("question") or "").strip()
        a = (pair.get("answer") or "").strip()
        if not q or not a:
            skipped.append({"question": pair.get("question"), "reason": "empty question/answer"})
            continue

        eff_source = {**(source or {}), **(pair.get("source") or {})}
        qh = _question_hash(q)
        qid = _qa_pair_id(repository_key, qh)
        feature_key = eff_source.get("feature_key")
        task_key = eff_source.get("task_key")

        await pool.execute(
            """
            INSERT INTO memory.qa_pairs (
                qa_pair_id, repository_id, feature_key, task_key,
                question, answer, question_hash, question_tsv, source, confidence
            )
            VALUES (
                $1::uuid, $2, $3, $4,
                $5, $6, $7, to_tsvector('english', $5), $8::jsonb, 0.80
            )
            ON CONFLICT (repository_id, question_hash) DO UPDATE SET
                answer = EXCLUDED.answer,
                feature_key = EXCLUDED.feature_key,
                task_key = EXCLUDED.task_key,
                source = EXCLUDED.source,
                updated_utc = NOW()
            """,
            str(qid),
            repository_id,
            feature_key,
            task_key,
            q,
            a,
            qh,
            json.dumps(eff_source),
        )

        if qdrant_client is not None:
            try:
                embedding = await embed_single(q, settings)
                await qdrant_client.upsert(
                    collection_name=QA_PAIRS_COLLECTION,
                    points=[
                        _qa_point_from_row(
                            {
                                "qa_pair_id": qid,
                                "repository_key": repository_key,
                                "feature_key": feature_key,
                            },
                            embedding,
                        )
                    ],
                )
            except Exception:
                logger.warning("qa_pair_embedding_upsert_failed", qa_pair_id=str(qid), exc_info=True)

        qa_pair_ids.append(qid)

    logger.info(
        "qa_ingest_done",
        repository_key=repository_key,
        ingested=len(qa_pair_ids),
        skipped=len(skipped),
    )
    return {
        "ingested": len(qa_pair_ids),
        "qa_pair_ids": [str(x) for x in qa_pair_ids],
        "skipped": skipped,
    }


async def search_qa_knowledge(
    pool: asyncpg.Pool,
    settings: Settings,
    *,
    repository_key: str,
    question: str,
    limit: int = 5,
    min_similarity: float = 0.45,
    qdrant_client: AsyncQdrantClient | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    repository_id = await _resolve_repository_id(pool, repository_key)
    if repository_id is None:
        logger.info("qa_search_done", repository_key=repository_key, returned=0, reason="unknown_repository")
        return {"advisory_only": True, "rows": [], "warnings": ["unknown repository"]}

    candidates: list[tuple[str, float]] = []
    fallback_to_lexical = qdrant_client is None

    if qdrant_client is not None:
        try:
            qe = await embed_single(question, settings)
            results = await semantic_query_points(
                qdrant_client,
                collection_name=QA_PAIRS_COLLECTION,
                query_vector=qe,
                limit=max(limit * 5, limit),
                score_threshold=min_similarity,
                query_filter=_qdrant_filter(repository_key=repository_key),
            )
            candidates = [(str(r.id), float(r.score)) for r in results]
        except Exception:
            warnings.append("Semantic retrieval unavailable; using lexical fallback.")
            logger.warning("qa_search_semantic_failed", exc_info=True)
            fallback_to_lexical = True
    else:
        warnings.append("Semantic retrieval unavailable; using lexical fallback.")

    # Semantic ran but nothing cleared the threshold → try lexical before giving up.
    # An exact/overlapping question still matches via full-text even when the embedding
    # similarity is below min_similarity.
    semantic_hits = len(candidates)
    if qdrant_client is not None and not fallback_to_lexical and not candidates:
        fallback_to_lexical = True
        warnings.append("No semantic matches above threshold; using lexical fallback.")

    if fallback_to_lexical:
        lex = await pool.fetch(
            """
            SELECT qa_pair_id,
                   ts_rank(question_tsv, plainto_tsquery('english', $2)) AS score
            FROM memory.qa_pairs
            WHERE repository_id = $1 AND is_active
              AND question_tsv @@ plainto_tsquery('english', $2)
            ORDER BY score DESC
            LIMIT $3
            """,
            repository_id,
            question,
            limit,
        )
        candidates = [(str(r["qa_pair_id"]), float(r["score"])) for r in lex]

    if not candidates:
        logger.info(
            "qa_search_done",
            repository_key=repository_key,
            question_len=len(question),
            semantic_hits=semantic_hits,
            lexical_used=fallback_to_lexical,
            returned=0,
        )
        return {"advisory_only": True, "rows": [], "warnings": warnings}

    score_by_id = {cid: score for cid, score in candidates}
    hydrated = await pool.fetch(
        """
        SELECT qa_pair_id, question, answer, confidence, source
        FROM memory.qa_pairs
        WHERE qa_pair_id = ANY($1::uuid[]) AND is_active
        """,
        [cid for cid, _ in candidates],
    )

    # Lexical fallback has no relevance floor (ts_rank matches any shared token), so it surfaces
    # junk when little Q&A is ingested. Keep only near-exact re-asks: candidates whose question
    # clears a token-overlap (Jaccard) threshold. The semantic path is already floored at
    # min_similarity, so this filter applies to the lexical fallback only.
    lexical_min_overlap = float(getattr(settings, "qa_lexical_min_overlap", 0.6))
    asked_tokens = _normalized_tokens(question) if fallback_to_lexical else set()

    rows: list[dict[str, Any]] = []
    dropped_low_overlap = 0
    for r in hydrated:
        if fallback_to_lexical and _question_overlap(asked_tokens, r["question"]) < lexical_min_overlap:
            dropped_low_overlap += 1
            continue
        raw_source = r["source"]
        src = raw_source if isinstance(raw_source, dict) else json.loads(raw_source or "{}")
        rows.append(
            {
                "qa_pair_id": str(r["qa_pair_id"]),
                "question": r["question"],
                "answer": r["answer"],
                "confidence": float(r["confidence"]),
                "source": src,
                "score": score_by_id.get(str(r["qa_pair_id"]), 0.0),
            }
        )
    rows.sort(key=lambda x: x["score"], reverse=True)  # PG = ANY() does not preserve order
    result_rows = rows[:limit]
    logger.info(
        "qa_search_done",
        repository_key=repository_key,
        question_len=len(question),
        semantic_hits=semantic_hits,
        lexical_used=fallback_to_lexical,
        lexical_dropped_low_overlap=dropped_low_overlap,
        returned=len(result_rows),
    )
    return {"advisory_only": True, "rows": result_rows, "warnings": warnings}
