from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

import asyncpg
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.llm.openai_client import embed, embed_single

logger = structlog.get_logger()

TRIAGE_CASES_COLLECTION = "triage_cases"
DEFAULT_LOOKBACK_DAYS = 30
TRIAGE_REPROJECTION_BATCH_SIZE = 50
TRIAGE_OUTCOME_STATUS_TYPE = "TRIAGE_OUTCOME_STATUS"
TRIAGE_OUTCOME_PENDING = "TRIAGE_OUTCOME_PENDING"
TRIAGE_OUTCOME_CONFIRMED_CORRECT = "TRIAGE_OUTCOME_CONFIRMED_CORRECT"
TRIAGE_OUTCOME_EXECUTION_FAILED_AFTER_ROUTE = "TRIAGE_OUTCOME_EXECUTION_FAILED_AFTER_ROUTE"
TRIAGE_OUTCOME_INSUFFICIENT_CONTEXT = "TRIAGE_OUTCOME_INSUFFICIENT_CONTEXT"
TRIAGE_OUTCOME_CORRECTED = "TRIAGE_OUTCOME_CORRECTED"
TRIAGE_OUTCOME_OVERRIDDEN_BY_HUMAN = "TRIAGE_OUTCOME_OVERRIDDEN_BY_HUMAN"

_OUTCOME_CONFIDENCE = {
    "pending": None,
    "confirmed_correct": 1.0,
    "execution_failed_after_route": 0.75,
    "insufficient_context": 0.5,
    "corrected": 0.25,
    "overridden_by_human": 0.0,
}

_LEGACY_OUTCOME_TO_REFERENCE_CODE = {
    "pending": TRIAGE_OUTCOME_PENDING,
    "confirmed_correct": TRIAGE_OUTCOME_CONFIRMED_CORRECT,
    "execution_failed_after_route": TRIAGE_OUTCOME_EXECUTION_FAILED_AFTER_ROUTE,
    "insufficient_context": TRIAGE_OUTCOME_INSUFFICIENT_CONTEXT,
    "corrected": TRIAGE_OUTCOME_CORRECTED,
    "overridden_by_human": TRIAGE_OUTCOME_OVERRIDDEN_BY_HUMAN,
}

LEXICAL_FALLBACK_BASELINE = 0.65
PROJECT_PREFERENCE_BOOST = 0.03
OUTCOME_CONFIDENCE_WEIGHT = 0.08
CLARIFICATION_PENALTY = 0.04
RECENCY_WEIGHT = 0.04


def _prompt_hash(prompt_text: str) -> str:
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def _outcome_confidence(status: str | None) -> float | None:
    return _OUTCOME_CONFIDENCE.get((status or "pending").strip().lower(), None)


def _canonicalize_outcome_status(status: str | None) -> str | None:
    normalized = (status or "").strip().lower()
    if not normalized:
        return None
    return normalized


def _recency_score(created_utc: dt.datetime | None, max_age_days: int) -> float:
    if created_utc is None or max_age_days <= 0:
        return 0.0
    now = dt.datetime.now(dt.timezone.utc)
    if created_utc.tzinfo is None:
        created_utc = created_utc.replace(tzinfo=dt.timezone.utc)
    age_seconds = max((now - created_utc).total_seconds(), 0.0)
    horizon_seconds = max(float(max_age_days) * 86400.0, 1.0)
    freshness = max(0.0, 1.0 - min(age_seconds / horizon_seconds, 1.0))
    return round(freshness, 4)


def _hybrid_similarity_score(
    row: dict[str, Any],
    *,
    candidate_scores: dict[str, float],
    project_key: str | None,
    max_age_days: int,
    lexical_fallback: bool,
) -> float:
    triage_case_id = str(row["triage_case_id"])
    baseline = candidate_scores.get(triage_case_id, LEXICAL_FALLBACK_BASELINE if lexical_fallback else 0.0)
    score = float(baseline)
    if project_key and row["project_key"] == project_key:
        score += PROJECT_PREFERENCE_BOOST
    outcome_confidence = _outcome_confidence(str(row.get("outcome_status") or "pending"))
    if outcome_confidence is not None:
        score += (float(outcome_confidence) - 0.5) * OUTCOME_CONFIDENCE_WEIGHT
    if row.get("requires_clarification"):
        score -= CLARIFICATION_PENALTY
    score += _recency_score(row.get("created_utc"), max_age_days) * RECENCY_WEIGHT
    return round(max(score, 0.0), 4)


def _search_sort_key(
    item: dict[str, Any],
) -> tuple[float, float, int, int, str, str, str]:
    created_utc = str(item.get("created_utc") or "")
    return (
        float(item["similarity_score"]),
        float(item.get("outcome_confidence") or -1.0),
        1 if item.get("requires_clarification") is False else 0,
        1 if created_utc else 0,
        created_utc,
        str(item.get("repository_key") or ""),
        str(item.get("triage_case_id") or ""),
    )


async def _resolve_triage_outcome_status_id(
    pool: asyncpg.Pool,
    outcome_status: str,
) -> int | None:
    canonical_status = _canonicalize_outcome_status(outcome_status)
    if canonical_status is None:
        return None
    reference_code = _LEGACY_OUTCOME_TO_REFERENCE_CODE.get(canonical_status)
    if reference_code is None:
        return None
    row = await pool.fetchrow(
        """
        SELECT rv.id
        FROM core.reference_values rv
        JOIN core.reference_types rt ON rt.id = rv.reference_type_id
        WHERE rt.internal_code = $1 AND rv.internal_code = $2
        """,
        TRIAGE_OUTCOME_STATUS_TYPE,
        reference_code,
    )
    if row is None:
        logger.warning(
            "triage_outcome_reference_value_missing",
            outcome_status=canonical_status,
            reference_code=reference_code,
        )
        return None
    return int(row["id"])


async def _resolve_repository_id(pool: asyncpg.Pool, repository_key: str) -> int | None:
    row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1",
        repository_key,
    )
    return row["id"] if row else None


def _triage_case_payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    created_utc = row.get("created_utc")
    if isinstance(created_utc, dt.datetime):
        created_utc_value = created_utc.isoformat()
    else:
        created_utc_value = str(created_utc) if created_utc is not None else None
    return {
        "triage_case_id": str(row["triage_case_id"]),
        "repository_key": row["repository_key"],
        "project_key": row.get("project_key"),
        "feature_key": row.get("feature_key"),
        "request_kind": row.get("request_kind"),
        "selected_workflow_name": row.get("selected_workflow_name"),
        "policy_version": row.get("policy_version"),
        "created_utc": created_utc_value,
    }


def _triage_case_point_from_row(
    row: dict[str, Any],
    embedding: list[float],
) -> models.PointStruct:
    return models.PointStruct(
        id=str(row["triage_case_id"]),
        vector=embedding,
        payload=_triage_case_payload_from_row(row),
    )


async def _fetch_triage_case_projection_rows(
    pool: asyncpg.Pool,
    repository_key: str,
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT
            tc.triage_case_id,
            r.repository_key,
            tc.prompt_text,
            tc.request_kind,
            tc.selected_workflow_name,
            tc.project_key,
            tc.feature_key,
            tc.policy_version,
            tc.created_utc
        FROM ops.triage_cases tc
        JOIN catalog.repositories r ON r.id = tc.repository_id
        WHERE r.repository_key = $1
        ORDER BY tc.created_utc, tc.id
        """,
        repository_key,
    )
    return [dict(row) for row in rows]


async def reproject_triage_cases(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    settings: Settings,
    repository_key: str,
) -> dict[str, Any]:
    rows = await _fetch_triage_case_projection_rows(pool, repository_key)
    if not rows:
        return {"repaired": 0, "skipped": 0, "errors": []}

    repaired = 0
    skipped = 0
    errors: list[str] = []

    for index in range(0, len(rows), TRIAGE_REPROJECTION_BATCH_SIZE):
        batch = rows[index : index + TRIAGE_REPROJECTION_BATCH_SIZE]
        texts = [str(row["prompt_text"]) for row in batch]
        try:
            embeddings = await embed(texts, settings)
        except Exception as exc:
            message = f"Triage reprojection batch failed for {len(batch)} rows: {exc}"
            logger.warning("triage_case_reprojection_batch_failed", error=message)
            skipped += len(batch)
            errors.append(message)
            continue

        if len(embeddings) != len(batch):
            for row in batch[len(embeddings):]:
                skipped += 1
                message = f"Triage case {row.get('triage_case_id')} projection skipped: embedding missing"
                logger.warning("triage_case_projection_embedding_missing", error=message)
                errors.append(message)

        points: list[models.PointStruct] = []
        for row, embedding in zip(batch, embeddings):
            try:
                points.append(_triage_case_point_from_row(row, embedding))
            except Exception as exc:
                skipped += 1
                message = f"Triage case {row.get('triage_case_id')} projection skipped: {exc}"
                logger.warning("triage_case_projection_skipped", error=message)
                errors.append(message)

        if not points:
            continue

        try:
            await qdrant_client.upsert(collection_name=TRIAGE_CASES_COLLECTION, points=points)
            repaired += len(points)
        except Exception as exc:
            skipped += len(points)
            message = f"Triage reprojection upsert failed for {len(points)} rows: {exc}"
            logger.warning("triage_case_reprojection_upsert_failed", error=message)
            errors.append(message)

    return {"repaired": repaired, "skipped": skipped, "errors": errors}


async def save_triage_case(
    pool: asyncpg.Pool,
    settings: Settings,
    *,
    repository_key: str,
    prompt_text: str,
    request_kind: str,
    execution_mode: str,
    knowledge_mode: str,
    suggested_workflows: list[str],
    requires_clarification: bool,
    clarifying_questions: list[str],
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    fallback_route: str | None = None,
    confidence: float | None = None,
    reasoning_summary: str | None = None,
    project_key: str | None = None,
    feature_key: str | None = None,
    task_key: str | None = None,
    actor_email: str | None = None,
    policy_version: str | None = None,
    workflow_catalog_version: str | None = None,
    decision_source: str | None = None,
    matched_case_ids: list[str] | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
) -> str:
    repository_id = await _resolve_repository_id(pool, repository_key)
    if repository_id is None:
        raise ValueError(f"Repository '{repository_key}' not found")

    triage_case_id = str(uuid.uuid4())
    inserted = await pool.fetchrow(
        """
        INSERT INTO ops.triage_cases (
            triage_case_id, repository_id, prompt_text, prompt_hash,
            request_kind, execution_mode, knowledge_mode, selected_workflow_name,
            suggested_workflows, selected_run_action, requires_clarification,
            clarifying_questions, fallback_route, confidence, reasoning_summary,
            project_key, feature_key, task_key, actor_email, policy_version,
            workflow_catalog_version, decision_source, matched_case_ids
        )
        VALUES (
            $1::uuid, $2, $3, $4, $5, $6, $7, $8,
            $9::jsonb, $10, $11, $12::jsonb, $13, $14, $15,
            $16, $17, $18, $19, $20, $21, $22, $23::jsonb
        )
        RETURNING
            triage_case_id,
            request_kind,
            selected_workflow_name,
            project_key,
            feature_key,
            policy_version,
            created_utc
        """,
        triage_case_id,
        repository_id,
        prompt_text,
        _prompt_hash(prompt_text),
        request_kind,
        execution_mode,
        knowledge_mode,
        selected_workflow_name,
        json.dumps(suggested_workflows),
        selected_run_action,
        requires_clarification,
        json.dumps(clarifying_questions),
        fallback_route,
        confidence,
        reasoning_summary,
        project_key,
        feature_key,
        task_key,
        actor_email,
        policy_version,
        workflow_catalog_version,
        decision_source,
        json.dumps(matched_case_ids or []),
    )

    if qdrant_client is not None and inserted is not None:
        try:
            projection_row = dict(inserted)
            projection_row["repository_key"] = repository_key
            projection_row["prompt_text"] = prompt_text
            embedding = await embed_single(prompt_text, settings)
            await qdrant_client.upsert(
                collection_name=TRIAGE_CASES_COLLECTION,
                points=[_triage_case_point_from_row(projection_row, embedding)],
            )
        except Exception:
            logger.warning("triage_case_embedding_upsert_failed", triage_case_id=triage_case_id, exc_info=True)

    return triage_case_id


async def record_triage_case_feedback(
    pool: asyncpg.Pool,
    *,
    triage_case_id: str,
    outcome_status: str,
    successful_execution: bool | None = None,
    human_override: bool | None = None,
    correction_reason: str | None = None,
    corrected_request_kind: str | None = None,
    corrected_execution_mode: str | None = None,
    corrected_selected_workflow_name: str | None = None,
    feedback_notes: str | None = None,
) -> bool:
    existing = await pool.fetchrow(
        "SELECT triage_case_id FROM ops.triage_cases WHERE triage_case_id = $1::uuid",
        triage_case_id,
    )
    if existing is None:
        return False
    status_id = await _resolve_triage_outcome_status_id(pool, outcome_status)
    await pool.fetchrow(
        """
        INSERT INTO ops.triage_case_feedback (
            triage_case_id, outcome_status, status_id, successful_execution, human_override,
            correction_reason, corrected_request_kind, corrected_execution_mode,
            corrected_selected_workflow_name, feedback_notes
        )
        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id
        """,
        triage_case_id,
        outcome_status,
        status_id,
        successful_execution,
        human_override,
        correction_reason,
        corrected_request_kind,
        corrected_execution_mode,
        corrected_selected_workflow_name,
        feedback_notes,
    )
    return True


def _qdrant_filter(
    *,
    repository_key: str | None = None,
    project_key: str | None = None,
    feature_key: str | None = None,
    request_kind: str | None = None,
    selected_workflow_name: str | None = None,
    policy_version: str | None = None,
) -> models.Filter | None:
    conditions: list[models.FieldCondition] = []
    for field, value in [
        ("repository_key", repository_key),
        ("project_key", project_key),
        ("feature_key", feature_key),
        ("request_kind", request_kind),
        ("selected_workflow_name", selected_workflow_name),
        ("policy_version", policy_version),
    ]:
        if value:
            conditions.append(
                models.FieldCondition(key=field, match=models.MatchValue(value=value))
            )
    if not conditions:
        return None
    return models.Filter(must=conditions)


async def search_triage_cases(
    pool: asyncpg.Pool,
    settings: Settings,
    *,
    prompt_text: str,
    repository_key: str | None = None,
    project_key: str | None = None,
    feature_key: str | None = None,
    request_kind: str | None = None,
    execution_mode: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    policy_version: str | None = None,
    limit: int = 5,
    min_similarity: float = 0.65,
    prefer_same_repository: bool = True,
    include_corrected: bool = True,
    max_age_days: int = 180,
    qdrant_client: AsyncQdrantClient | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    candidates: list[tuple[str, float]] = []
    fallback_to_lexical = qdrant_client is None

    if prefer_same_repository is False:
        warnings.append("prefer_same_repository is retained for compatibility and does not change ranking under the current search contract.")

    if qdrant_client is not None:
        try:
            query_embedding = await embed_single(prompt_text, settings)
            results = await qdrant_client.search(
                collection_name=TRIAGE_CASES_COLLECTION,
                query_vector=query_embedding,
                limit=max(limit * 5, limit),
                score_threshold=min_similarity,
                query_filter=_qdrant_filter(
                    repository_key=repository_key,
                    project_key=project_key,
                    feature_key=feature_key,
                    request_kind=request_kind,
                    selected_workflow_name=selected_workflow_name,
                    policy_version=policy_version,
                ),
            )
            candidates = [(str(r.id), float(r.score)) for r in results]
        except Exception:
            warnings.append("Semantic retrieval unavailable; using lexical fallback.")
            logger.warning("triage_case_search_semantic_failed", exc_info=True)
            fallback_to_lexical = True
    else:
        warnings.append("Semantic retrieval unavailable; using lexical fallback.")
        fallback_to_lexical = True

    if qdrant_client is not None and not fallback_to_lexical and not candidates:
        return {
            "advisory_only": True,
            "retrieval_summary": _build_retrieval_summary([]),
            "rows": [],
            "warnings": warnings,
        }

    rows = await _fetch_search_rows(
        pool,
        candidate_ids=[row[0] for row in candidates],
        candidate_scores={row[0]: row[1] for row in candidates},
        prompt_text=prompt_text,
        repository_key=repository_key,
        project_key=project_key,
        feature_key=feature_key,
        request_kind=request_kind,
        execution_mode=execution_mode,
        selected_workflow_name=selected_workflow_name,
        selected_run_action=selected_run_action,
        policy_version=policy_version,
        include_corrected=include_corrected,
        max_age_days=max_age_days,
        limit=limit,
        lexical_fallback=fallback_to_lexical,
    )

    summary = _build_retrieval_summary(rows)
    return {
        "advisory_only": True,
        "retrieval_summary": summary,
        "rows": rows,
        "warnings": warnings,
    }


async def _fetch_search_rows(
    pool: asyncpg.Pool,
    *,
    candidate_ids: list[str],
    candidate_scores: dict[str, float],
    prompt_text: str,
    repository_key: str | None,
    project_key: str | None,
    feature_key: str | None,
    request_kind: str | None,
    execution_mode: str | None,
    selected_workflow_name: str | None,
    selected_run_action: str | None,
    policy_version: str | None,
    include_corrected: bool,
    max_age_days: int,
    limit: int,
    lexical_fallback: bool,
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT
            tc.triage_case_id,
            tc.prompt_text,
            tc.request_kind,
            tc.execution_mode,
            tc.knowledge_mode,
            tc.selected_workflow_name,
            tc.selected_run_action,
            tc.requires_clarification,
            tc.confidence,
            tc.project_key,
            tc.feature_key,
            r.repository_key,
            tc.policy_version,
            tc.created_utc,
            COALESCE(fb.effective_outcome_status, 'pending') AS outcome_status,
            fb.corrected_request_kind
        FROM ops.triage_cases tc
        JOIN catalog.repositories r ON r.id = tc.repository_id
        LEFT JOIN LATERAL (
            SELECT
                CASE
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_PENDING' THEN 'pending'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_CONFIRMED_CORRECT' THEN 'confirmed_correct'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_EXECUTION_FAILED_AFTER_ROUTE' THEN 'execution_failed_after_route'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_INSUFFICIENT_CONTEXT' THEN 'insufficient_context'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_CORRECTED' THEN 'corrected'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_OVERRIDDEN_BY_HUMAN' THEN 'overridden_by_human'
                    WHEN fb.outcome_status IS NOT NULL THEN lower(btrim(fb.outcome_status))
                    ELSE NULL
                END AS effective_outcome_status,
                fb.corrected_request_kind
            FROM ops.triage_case_feedback fb
            LEFT JOIN core.reference_values rv ON rv.id = fb.status_id
            WHERE fb.triage_case_id = tc.triage_case_id
            ORDER BY fb.created_utc DESC, fb.id DESC
            LIMIT 1
        ) fb ON TRUE
        WHERE ($1::boolean = FALSE OR tc.triage_case_id::text = ANY($2::text[]))
          AND ($3::text IS NULL OR r.repository_key = $3)
          AND ($4::text IS NULL OR tc.project_key = $4)
          AND ($5::text IS NULL OR tc.feature_key = $5)
          AND ($6::text IS NULL OR tc.request_kind = $6)
          AND ($7::text IS NULL OR tc.execution_mode = $7)
          AND ($8::text IS NULL OR tc.selected_workflow_name = $8)
          AND ($9::text IS NULL OR tc.selected_run_action = $9)
          AND ($10::text IS NULL OR tc.policy_version = $10)
          AND tc.created_utc >= NOW() - make_interval(days => $11)
          AND ($12::boolean = TRUE OR COALESCE(fb.effective_outcome_status, 'pending') NOT IN ('corrected', 'overridden_by_human'))
          AND ($13::boolean = FALSE OR tc.prompt_text ILIKE $14)
        """,
        bool(candidate_ids),
        candidate_ids,
        repository_key,
        project_key,
        feature_key,
        request_kind,
        execution_mode,
        selected_workflow_name,
        selected_run_action,
        policy_version,
        max_age_days,
        include_corrected,
        lexical_fallback,
        f"%{prompt_text[:64]}%",
    )

    enriched: list[dict[str, Any]] = []
    for row in rows:
        triage_case_id = str(row["triage_case_id"])
        outcome_status = str(row["outcome_status"] or "pending")
        score = _hybrid_similarity_score(
            row,
            candidate_scores=candidate_scores,
            project_key=project_key,
            max_age_days=max_age_days,
            lexical_fallback=lexical_fallback,
        )
        enriched.append(
            {
                "triage_case_id": triage_case_id,
                "prompt_text": row["prompt_text"],
                "similarity_score": score,
                "request_kind": row["request_kind"],
                "execution_mode": row["execution_mode"],
                "knowledge_mode": row["knowledge_mode"],
                "selected_workflow_name": row["selected_workflow_name"],
                "selected_run_action": row["selected_run_action"],
                "requires_clarification": row["requires_clarification"],
                "confidence": row["confidence"],
                "project_key": row["project_key"],
                "feature_key": row["feature_key"],
                "repository_key": row["repository_key"],
                "policy_version": row["policy_version"],
                "created_utc": row["created_utc"].isoformat() if row["created_utc"] else None,
                "outcome_status": outcome_status,
                "outcome_confidence": _outcome_confidence(outcome_status),
            }
        )

    enriched.sort(key=_search_sort_key, reverse=True)
    return enriched[:limit]


def _build_retrieval_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    request_kinds: dict[str, int] = {}
    workflows: dict[str, int] = {}
    total_score = 0.0
    for row in rows:
        if row.get("request_kind"):
            request_kinds[row["request_kind"]] = request_kinds.get(row["request_kind"], 0) + 1
        if row.get("selected_workflow_name"):
            workflows[row["selected_workflow_name"]] = workflows.get(row["selected_workflow_name"], 0) + 1
        total_score += float(row.get("similarity_score") or 0.0)
    return {
        "returned": len(rows),
        "consensus_request_kind": max(request_kinds, key=request_kinds.get) if request_kinds else None,
        "consensus_workflow": max(workflows, key=workflows.get) if workflows else None,
        "consensus_strength": round(total_score / len(rows), 4) if rows else 0.0,
    }


async def _fetch_triage_analysis_rows(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None,
    project_key: str | None,
    request_kind: str | None,
    selected_workflow_name: str | None,
    selected_run_action: str | None,
    lookback_days: int,
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        /* triage_analysis_rows */
        SELECT
            tc.prompt_text,
            tc.request_kind,
            tc.selected_workflow_name,
            tc.selected_run_action,
            tc.requires_clarification,
            tc.created_utc,
            COALESCE(fb.effective_outcome_status, 'pending') AS outcome_status,
            fb.corrected_request_kind
        FROM ops.triage_cases tc
        JOIN catalog.repositories r ON r.id = tc.repository_id
        LEFT JOIN LATERAL (
            SELECT
                CASE
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_PENDING' THEN 'pending'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_CONFIRMED_CORRECT' THEN 'confirmed_correct'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_EXECUTION_FAILED_AFTER_ROUTE' THEN 'execution_failed_after_route'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_INSUFFICIENT_CONTEXT' THEN 'insufficient_context'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_CORRECTED' THEN 'corrected'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_OVERRIDDEN_BY_HUMAN' THEN 'overridden_by_human'
                    WHEN fb.outcome_status IS NOT NULL THEN lower(btrim(fb.outcome_status))
                    ELSE NULL
                END AS effective_outcome_status,
                fb.corrected_request_kind
            FROM ops.triage_case_feedback fb
            LEFT JOIN core.reference_values rv ON rv.id = fb.status_id
            WHERE fb.triage_case_id = tc.triage_case_id
            ORDER BY fb.created_utc DESC, fb.id DESC
            LIMIT 1
        ) fb ON TRUE
        WHERE ($1::text IS NULL OR r.repository_key = $1)
          AND ($2::text IS NULL OR tc.project_key = $2)
          AND ($3::text IS NULL OR tc.request_kind = $3)
          AND ($4::text IS NULL OR tc.selected_workflow_name = $4)
          AND ($5::text IS NULL OR tc.selected_run_action = $5)
          AND tc.created_utc >= NOW() - make_interval(days => $6)
        ORDER BY tc.created_utc DESC, tc.triage_case_id DESC
        """,
        repository_key,
        project_key,
        request_kind,
        selected_workflow_name,
        selected_run_action,
        lookback_days,
    )
    return [dict(row) for row in rows]


def _triage_cluster_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str, str, str, str, str]:
    return (
        int(item["case_count"]),
        int(item["clarification_count"]),
        str(item.get("latest_seen_utc") or ""),
        str(item.get("request_kind") or ""),
        str(item.get("selected_workflow_name") or ""),
        str(item.get("selected_run_action") or ""),
        str(item.get("corrected_request_kind") or ""),
        str(item.get("outcome_status") or ""),
    )


async def get_triage_confusion_clusters(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    project_key: str | None = None,
    request_kind: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    limit: int = 10,
) -> dict[str, Any]:
    rows = await _fetch_triage_analysis_rows(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        request_kind=request_kind,
        selected_workflow_name=selected_workflow_name,
        selected_run_action=selected_run_action,
        lookback_days=lookback_days,
    )
    filtered_rows = [
        row
        for row in rows
        if row.get("corrected_request_kind")
        or row.get("outcome_status") in {"corrected", "overridden_by_human", "execution_failed_after_route", "insufficient_context"}
        or row.get("requires_clarification")
    ]
    base_data = {
        "filters": {
            "repository_key": repository_key,
            "project_key": project_key,
            "request_kind": request_kind,
            "selected_workflow_name": selected_workflow_name,
            "selected_run_action": selected_run_action,
            "lookback_days": lookback_days,
            "limit": limit,
        },
        "analyzed_case_count": len(rows),
        "cluster_count": 0,
        "clusters": [],
    }
    if not filtered_rows:
        return base_data

    grouped: dict[tuple[str | None, str | None, str | None, str | None, str], dict[str, Any]] = {}
    for row in filtered_rows:
        conditional_run_action = row.get("selected_run_action") if row.get("request_kind") == "run_operation" else None
        outcome_status = str(row.get("outcome_status") or "pending")
        corrected_request_kind = row.get("corrected_request_kind")
        key = (
            row.get("request_kind"),
            row.get("selected_workflow_name"),
            conditional_run_action,
            corrected_request_kind,
            outcome_status,
        )
        bucket = grouped.setdefault(
            key,
            {
                "request_kind": row.get("request_kind"),
                "selected_workflow_name": row.get("selected_workflow_name"),
                "selected_run_action": conditional_run_action,
                "outcome_status": outcome_status,
                "corrected_request_kind": corrected_request_kind,
                "case_count": 0,
                "clarification_count": 0,
                "latest_seen_utc": None,
                "example_prompts": [],
            },
        )
        bucket["case_count"] += 1
        if row.get("requires_clarification"):
            bucket["clarification_count"] += 1
        created = row.get("created_utc")
        latest_seen = bucket.get("latest_seen_utc")
        if isinstance(created, dt.datetime):
            created_iso = created.isoformat()
            if latest_seen is None or created_iso > latest_seen:
                bucket["latest_seen_utc"] = created_iso
        prompt = str(row.get("prompt_text") or "")
        if prompt and prompt not in bucket["example_prompts"] and len(bucket["example_prompts"]) < 3:
            bucket["example_prompts"].append(prompt)

    clusters = []
    for bucket in grouped.values():
        cluster_key = "|".join(
            [
                str(bucket.get("request_kind") or ""),
                str(bucket.get("selected_workflow_name") or ""),
                str(bucket.get("selected_run_action") or ""),
                str(bucket.get("corrected_request_kind") or ""),
                str(bucket.get("outcome_status") or ""),
            ]
        )
        bucket["cluster_key"] = cluster_key
        clusters.append(bucket)

    clusters.sort(key=_triage_cluster_sort_key, reverse=True)
    return {
        **base_data,
        "cluster_count": len(clusters),
        "clusters": clusters[:limit],
    }


def _triage_recommendation_sort_key(item: dict[str, Any]) -> tuple[float, int, int, str, str, str, str]:
    return (
        float(item["clarification_rate"]),
        int(item["clarification_count"]),
        int(item["case_count"]),
        str(item.get("latest_seen_utc") or ""),
        str(item.get("request_kind") or ""),
        str(item.get("selected_workflow_name") or ""),
        str(item.get("selected_run_action") or ""),
    )


async def get_triage_clarification_recommendations(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    project_key: str | None = None,
    request_kind: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    limit: int = 10,
    min_case_count: int = 2,
) -> dict[str, Any]:
    rows = await _fetch_triage_analysis_rows(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        request_kind=request_kind,
        selected_workflow_name=selected_workflow_name,
        selected_run_action=selected_run_action,
        lookback_days=lookback_days,
    )
    base_data = {
        "filters": {
            "repository_key": repository_key,
            "project_key": project_key,
            "request_kind": request_kind,
            "selected_workflow_name": selected_workflow_name,
            "selected_run_action": selected_run_action,
            "lookback_days": lookback_days,
            "limit": limit,
            "min_case_count": min_case_count,
        },
        "analyzed_case_count": len(rows),
        "recommendation_count": 0,
        "recommendations": [],
    }
    if not rows:
        return base_data

    grouped: dict[tuple[str | None, str | None, str | None], dict[str, Any]] = {}
    for row in rows:
        conditional_run_action = row.get("selected_run_action") if row.get("request_kind") == "run_operation" else None
        key = (
            row.get("request_kind"),
            row.get("selected_workflow_name"),
            conditional_run_action,
        )
        bucket = grouped.setdefault(
            key,
            {
                "request_kind": row.get("request_kind"),
                "selected_workflow_name": row.get("selected_workflow_name"),
                "selected_run_action": conditional_run_action,
                "case_count": 0,
                "clarification_count": 0,
                "latest_seen_utc": None,
                "sample_prompts": [],
            },
        )
        bucket["case_count"] += 1
        if row.get("requires_clarification"):
            bucket["clarification_count"] += 1
        created = row.get("created_utc")
        if isinstance(created, dt.datetime):
            created_iso = created.isoformat()
            latest_seen = bucket.get("latest_seen_utc")
            if latest_seen is None or created_iso > latest_seen:
                bucket["latest_seen_utc"] = created_iso
        if row.get("requires_clarification"):
            prompt = str(row.get("prompt_text") or "")
            if prompt and prompt not in bucket["sample_prompts"] and len(bucket["sample_prompts"]) < 3:
                bucket["sample_prompts"].append(prompt)

    recommendations = []
    for bucket in grouped.values():
        case_count = int(bucket["case_count"])
        clarification_count = int(bucket["clarification_count"])
        if case_count < min_case_count or clarification_count == 0:
            continue
        clarification_rate = round(clarification_count / case_count, 4)
        workflow_name = bucket.get("selected_workflow_name")
        run_action = bucket.get("selected_run_action")
        request_kind_value = bucket.get("request_kind")
        recommendation_parts = [f"Add clarification guidance for {request_kind_value or 'unknown'} requests"]
        if workflow_name:
            recommendation_parts.append(f"before routing to {workflow_name}")
        if run_action:
            recommendation_parts.append(f"with run action {run_action}")
        recommendation = " ".join(recommendation_parts)
        recommendation_key = "|".join(
            [
                str(request_kind_value or ""),
                str(workflow_name or ""),
                str(run_action or ""),
            ]
        )
        recommendations.append(
            {
                "recommendation_key": recommendation_key,
                "request_kind": request_kind_value,
                "selected_workflow_name": workflow_name,
                "selected_run_action": run_action,
                "case_count": case_count,
                "clarification_count": clarification_count,
                "clarification_rate": clarification_rate,
                "latest_seen_utc": bucket.get("latest_seen_utc"),
                "sample_prompts": bucket["sample_prompts"],
                "recommendation": recommendation,
            }
        )

    recommendations.sort(key=_triage_recommendation_sort_key, reverse=True)
    return {
        **base_data,
        "recommendation_count": len(recommendations),
        "recommendations": recommendations[:limit],
    }


async def get_triage_feedback_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    project_key: str | None = None,
    request_kind: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    rows = await pool.fetch(
        """
        SELECT
            tc.prompt_text,
            tc.request_kind,
            tc.requires_clarification,
            tc.created_utc,
            COALESCE(fb.effective_outcome_status, 'pending') AS outcome_status,
            fb.corrected_request_kind
        FROM ops.triage_cases tc
        JOIN catalog.repositories r ON r.id = tc.repository_id
        LEFT JOIN LATERAL (
            SELECT
                CASE
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_PENDING' THEN 'pending'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_CONFIRMED_CORRECT' THEN 'confirmed_correct'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_EXECUTION_FAILED_AFTER_ROUTE' THEN 'execution_failed_after_route'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_INSUFFICIENT_CONTEXT' THEN 'insufficient_context'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_CORRECTED' THEN 'corrected'
                    WHEN rv.internal_code = 'TRIAGE_OUTCOME_OVERRIDDEN_BY_HUMAN' THEN 'overridden_by_human'
                    WHEN fb.outcome_status IS NOT NULL THEN lower(btrim(fb.outcome_status))
                    ELSE NULL
                END AS effective_outcome_status,
                fb.corrected_request_kind
            FROM ops.triage_case_feedback fb
            LEFT JOIN core.reference_values rv ON rv.id = fb.status_id
            WHERE fb.triage_case_id = tc.triage_case_id
            ORDER BY fb.created_utc DESC, fb.id DESC
            LIMIT 1
        ) fb ON TRUE
        WHERE ($1::text IS NULL OR r.repository_key = $1)
          AND ($2::text IS NULL OR tc.project_key = $2)
          AND ($3::text IS NULL OR tc.request_kind = $3)
          AND tc.created_utc >= NOW() - make_interval(days => $4)
        """,
        repository_key,
        project_key,
        request_kind,
        lookback_days,
    )
    case_count = len(rows)
    if case_count == 0:
        return {
            "case_count": 0,
            "confirmed_correct_rate": 0.0,
            "corrected_rate": 0.0,
            "human_override_rate": 0.0,
            "clarification_rate": 0.0,
            "top_misroutes": [],
            "top_problem_prompts": [],
        }

    def _rate(status: str) -> float:
        return sum(1 for row in rows if row["outcome_status"] == status) / case_count

    misroutes: dict[tuple[str, str], int] = {}
    prompts: dict[str, int] = {}
    clarification_count = 0
    for row in rows:
        if row["requires_clarification"]:
            clarification_count += 1
        if row["corrected_request_kind"]:
            key = (str(row["request_kind"]), str(row["corrected_request_kind"]))
            misroutes[key] = misroutes.get(key, 0) + 1
        if row["outcome_status"] in {"corrected", "overridden_by_human"}:
            prompts[str(row["prompt_text"])] = prompts.get(str(row["prompt_text"]), 0) + 1

    top_misroutes = [
        {"from": from_kind, "to": to_kind, "count": count}
        for (from_kind, to_kind), count in sorted(misroutes.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))[:10]
    ]
    latest_prompt_ts: dict[str, float] = {}
    for row in rows:
        if row["outcome_status"] not in {"corrected", "overridden_by_human"}:
            continue
        prompt = str(row["prompt_text"])
        created = row.get("created_utc")
        ts = created.timestamp() if created else 0.0
        latest_prompt_ts[prompt] = max(latest_prompt_ts.get(prompt, 0.0), ts)
    top_problem_prompts = [
        prompt
        for prompt, _count in sorted(
            prompts.items(),
            key=lambda item: (-item[1], -latest_prompt_ts.get(item[0], 0.0), item[0]),
        )[:10]
    ]

    return {
        "case_count": case_count,
        "confirmed_correct_rate": round(_rate("confirmed_correct"), 4),
        "corrected_rate": round(_rate("corrected"), 4),
        "human_override_rate": round(_rate("overridden_by_human"), 4),
        "clarification_rate": round(clarification_count / case_count, 4),
        "top_misroutes": top_misroutes,
        "top_problem_prompts": top_problem_prompts,
    }
