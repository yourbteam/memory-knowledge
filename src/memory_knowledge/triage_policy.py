from __future__ import annotations

import datetime as dt
import json
from typing import Any

import asyncpg

from memory_knowledge import triage_memory

DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_POLICY_VERSION = "triage-policy-v1"
DEFAULT_ROLLOUT_STAGE = "advisory"
DEFAULT_DRIFT_STATE = "stable"

_OUTCOME_QUALITY = {
    "confirmed_correct": 1.0,
    "pending": 0.5,
    "insufficient_context": 0.35,
    "execution_failed_after_route": 0.2,
    "corrected": 0.0,
    "overridden_by_human": 0.0,
}

_LIFECYCLE_QUALITY = {
    "validated": 1.0,
    "feedback_recorded": 0.6,
    "proposed": 0.4,
    "needs_retriage": 0.1,
    "human_rejected": 0.0,
    "superseded": 0.0,
}


def _normalize_json_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return [stripped]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _safe_iso(value: Any) -> str | None:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return None


def _outcome_quality(status: str | None) -> float:
    return _OUTCOME_QUALITY.get(str(status or "pending"), 0.25)


def _lifecycle_quality(state: str | None) -> float:
    return _LIFECYCLE_QUALITY.get(str(state or "proposed"), 0.25)


def _policy_source_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("request_kind") or ""),
        str(row.get("selected_workflow_name") or ""),
        str(row.get("selected_run_action") or ""),
        str(row.get("prompt_text") or ""),
    )


def _count_mix(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get(field) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


async def _fetch_policy_source_rows(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    project_key: str | None,
    request_kind: str | None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    lookback_days: int,
) -> list[dict[str, Any]]:
    lifecycle_select = triage_memory._triage_lifecycle_projection_select("tc", "lifecycle_rv")
    rows = await pool.fetch(
        f"""
        /* triage_policy_source_rows */
        SELECT
            r.repository_key,
            tc.project_key,
            tc.prompt_text,
            tc.request_kind,
            tc.selected_workflow_name,
            tc.selected_run_action,
            tc.requires_clarification,
            tc.clarifying_questions,
            tc.created_utc,
            {lifecycle_select},
            COALESCE(fb.effective_outcome_status, 'pending') AS outcome_status,
            fb.corrected_request_kind,
            fb.successful_execution
        FROM ops.triage_cases tc
        JOIN catalog.repositories r ON r.id = tc.repository_id
        LEFT JOIN core.reference_values lifecycle_rv ON lifecycle_rv.id = tc.lifecycle_state_id
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
                fb.corrected_request_kind,
                fb.successful_execution
            FROM ops.triage_case_feedback fb
            LEFT JOIN core.reference_values rv ON rv.id = fb.status_id
            WHERE fb.triage_case_id = tc.triage_case_id
            ORDER BY fb.created_utc DESC, fb.id DESC
            LIMIT 1
        ) fb ON TRUE
        WHERE r.repository_key = $1
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
    normalized = [dict(row) for row in rows]
    normalized.sort(key=_policy_source_sort_key)
    return normalized


async def _resolve_repository_id(pool: asyncpg.Pool, repository_key: str) -> int | None:
    row = await pool.fetchrow(
        "SELECT id FROM catalog.repositories WHERE repository_key = $1",
        repository_key,
    )
    if row is None:
        return None
    return int(row["id"])


def _routing_sort_key(item: dict[str, Any]) -> tuple[float, int, str, str, str]:
    return (
        float(item["confidence"]),
        int(item["case_count"]),
        str(item.get("latest_seen_utc") or ""),
        str(item.get("request_kind") or ""),
        str(item.get("recommended_workflow_name") or ""),
    )


async def get_routing_policy_recommendations(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    project_key: str | None = None,
    request_kind: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    limit: int = 10,
    min_case_count: int = 3,
    min_confidence: float = 0.6,
) -> dict[str, Any]:
    rows = await _fetch_policy_source_rows(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        request_kind=request_kind,
        lookback_days=lookback_days,
        selected_workflow_name=None,
        selected_run_action=None,
    )
    base = {
        "advisory_only": True,
        "policy_version": DEFAULT_POLICY_VERSION,
        "filters": {
            "repository_key": repository_key,
            "project_key": project_key,
            "request_kind": request_kind,
            "lookback_days": lookback_days,
            "limit": limit,
            "min_case_count": min_case_count,
            "min_confidence": min_confidence,
        },
        "analyzed_case_count": len(rows),
        "recommendation_count": 0,
        "recommendations": [],
    }
    if not rows:
        return base

    grouped: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]] = {}
    for row in rows:
        workflow_name = row.get("selected_workflow_name")
        if not workflow_name:
            continue
        run_action = row.get("selected_run_action") if row.get("request_kind") == "run_operation" else None
        key = (row.get("request_kind"), workflow_name, run_action)
        grouped.setdefault(key, []).append(row)

    recommendations: list[dict[str, Any]] = []
    for (request_kind_value, workflow_name, run_action), bucket in grouped.items():
        case_count = len(bucket)
        if case_count < min_case_count:
            continue
        confidence = round(
            sum((_outcome_quality(row.get("outcome_status")) + _lifecycle_quality(row.get("lifecycle_state"))) / 2.0 for row in bucket)
            / case_count,
            4,
        )
        if confidence < min_confidence:
            continue
        latest_seen_utc = max((_safe_iso(row.get("created_utc")) or "" for row in bucket), default=None)
        clarification_count = sum(1 for row in bucket if row.get("requires_clarification"))
        corrected_count = sum(1 for row in bucket if row.get("outcome_status") == "corrected")
        sample_prompts: list[str] = []
        for row in bucket:
            prompt = str(row.get("prompt_text") or "")
            if prompt and prompt not in sample_prompts and len(sample_prompts) < 3:
                sample_prompts.append(prompt)
        recommendations.append(
            {
                "policy_key": "|".join([str(request_kind_value or ""), str(workflow_name or ""), str(run_action or "")]),
                "repository_key": repository_key,
                "project_key": project_key,
                "request_kind": request_kind_value,
                "recommended_workflow_name": workflow_name,
                "recommended_run_action": run_action,
                "confidence": confidence,
                "case_count": case_count,
                "clarification_rate": round(clarification_count / case_count, 4),
                "correction_rate": round(corrected_count / case_count, 4),
                "latest_seen_utc": latest_seen_utc,
                "sample_prompts": sample_prompts,
                "outcome_mix": _count_mix(bucket, "outcome_status"),
                "lifecycle_mix": _count_mix(bucket, "lifecycle_state"),
                "inclusion_reasons": [
                    f"case_count>={min_case_count}",
                    f"confidence>={min_confidence}",
                ],
                "evidence_summary": (
                    f"{case_count} cases for {request_kind_value or 'unknown'} "
                    f"routed to {workflow_name}"
                ),
            }
        )

    recommendations.sort(key=_routing_sort_key, reverse=True)
    return {
        **base,
        "recommendation_count": len(recommendations),
        "recommendations": recommendations[:limit],
    }


def _clarification_sort_key(item: dict[str, Any]) -> tuple[float, int, str, str, str]:
    return (
        float(item["confidence"]),
        int(item["case_count"]),
        str(item.get("latest_seen_utc") or ""),
        str(item.get("request_kind") or ""),
        str(item.get("selected_workflow_name") or ""),
    )


async def get_clarification_policy(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    project_key: str | None = None,
    request_kind: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    limit: int = 10,
    min_case_count: int = 2,
) -> dict[str, Any]:
    rows = await _fetch_policy_source_rows(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        request_kind=request_kind,
        selected_workflow_name=selected_workflow_name,
        selected_run_action=selected_run_action,
        lookback_days=lookback_days,
    )
    base = {
        "advisory_only": True,
        "policy_version": DEFAULT_POLICY_VERSION,
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
        "policy_count": 0,
        "policies": [],
    }
    if not rows:
        return base

    grouped: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]] = {}
    for row in rows:
        conditional_run_action = row.get("selected_run_action") if row.get("request_kind") == "run_operation" else None
        key = (row.get("request_kind"), row.get("selected_workflow_name"), conditional_run_action)
        grouped.setdefault(key, []).append(row)

    policies: list[dict[str, Any]] = []
    for (request_kind_value, workflow_name, run_action), bucket in grouped.items():
        case_count = len(bucket)
        if case_count < min_case_count:
            continue
        clarification_count = sum(1 for row in bucket if row.get("requires_clarification"))
        if clarification_count == 0:
            continue
        sample_questions: list[str] = []
        sample_prompts: list[str] = []
        problem_case_count = 0
        for row in bucket:
            if row.get("outcome_status") in {"corrected", "overridden_by_human", "insufficient_context"}:
                problem_case_count += 1
            prompt = str(row.get("prompt_text") or "")
            if row.get("requires_clarification") and prompt and prompt not in sample_prompts and len(sample_prompts) < 3:
                sample_prompts.append(prompt)
            for question in _normalize_json_text_list(row.get("clarifying_questions")):
                if question not in sample_questions and len(sample_questions) < 5:
                    sample_questions.append(question)
        clarification_rate = clarification_count / case_count
        problem_rate = problem_case_count / case_count
        confidence = round(min(1.0, clarification_rate * 0.7 + problem_rate * 0.3), 4)
        policies.append(
            {
                "policy_key": "|".join([str(request_kind_value or ""), str(workflow_name or ""), str(run_action or "")]),
                "repository_key": repository_key,
                "project_key": project_key,
                "request_kind": request_kind_value,
                "selected_workflow_name": workflow_name,
                "selected_run_action": run_action,
                "confidence": confidence,
                "case_count": case_count,
                "clarification_rate": round(clarification_rate, 4),
                "problem_rate": round(problem_rate, 4),
                "latest_seen_utc": max((_safe_iso(row.get("created_utc")) or "" for row in bucket), default=None),
                "suggested_questions": sample_questions,
                "sample_prompts": sample_prompts,
                "outcome_mix": _count_mix(bucket, "outcome_status"),
                "lifecycle_mix": _count_mix(bucket, "lifecycle_state"),
                "recommendation": (
                    f"Prompt for clarification before routing {request_kind_value or 'unknown'} "
                    f"requests to {workflow_name or 'the default workflow'}"
                ),
            }
        )

    policies.sort(key=_clarification_sort_key, reverse=True)
    return {
        **base,
        "policy_count": len(policies),
        "policies": policies[:limit],
    }


def _profile_sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
    return (
        int(item["case_count"]),
        float(item["validated_rate"]),
        str(item.get("request_kind") or ""),
    )


async def list_triage_behavior_profiles(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    project_key: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    limit: int = 10,
) -> dict[str, Any]:
    rows = await _fetch_policy_source_rows(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        request_kind=None,
        lookback_days=lookback_days,
        selected_workflow_name=None,
        selected_run_action=None,
    )
    base = {
        "advisory_only": True,
        "policy_version": DEFAULT_POLICY_VERSION,
        "filters": {
            "repository_key": repository_key,
            "project_key": project_key,
            "lookback_days": lookback_days,
            "limit": limit,
        },
        "analyzed_case_count": len(rows),
        "profile_count": 0,
        "profiles": [],
    }
    if not rows:
        return base

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("request_kind") or "unknown"), []).append(row)

    profiles: list[dict[str, Any]] = []
    for request_kind_value, bucket in grouped.items():
        case_count = len(bucket)
        workflow_counts: dict[tuple[str | None, str | None], int] = {}
        validated_count = 0
        clarification_count = 0
        corrected_count = 0
        for row in bucket:
            workflow_key = (
                row.get("selected_workflow_name"),
                row.get("selected_run_action") if row.get("request_kind") == "run_operation" else None,
            )
            workflow_counts[workflow_key] = workflow_counts.get(workflow_key, 0) + 1
            if row.get("lifecycle_state") == "validated":
                validated_count += 1
            if row.get("requires_clarification"):
                clarification_count += 1
            if row.get("outcome_status") == "corrected":
                corrected_count += 1
        top_workflow_name, top_run_action = sorted(
            workflow_counts.items(),
            key=lambda item: (-item[1], str(item[0][0] or ""), str(item[0][1] or "")),
        )[0][0]
        profiles.append(
            {
                "profile_key": request_kind_value,
                "repository_key": repository_key,
                "project_key": project_key,
                "request_kind": request_kind_value,
                "case_count": case_count,
                "top_workflow_name": top_workflow_name,
                "top_run_action": top_run_action,
                "validated_rate": round(validated_count / case_count, 4),
                "clarification_rate": round(clarification_count / case_count, 4),
                "correction_rate": round(corrected_count / case_count, 4),
                "latest_seen_utc": max((_safe_iso(row.get("created_utc")) or "" for row in bucket), default=None),
                "outcome_mix": _count_mix(bucket, "outcome_status"),
                "lifecycle_mix": _count_mix(bucket, "lifecycle_state"),
            }
        )

    profiles.sort(key=_profile_sort_key, reverse=True)
    return {
        **base,
        "profile_count": len(profiles),
        "profiles": profiles[:limit],
    }


async def refresh_triage_policy_artifacts(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    project_key: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    routing_min_case_count: int = 3,
    routing_min_confidence: float = 0.6,
    clarification_min_case_count: int = 2,
    limit: int = 50,
) -> dict[str, Any]:
    repository_id = await _resolve_repository_id(pool, repository_key)
    if repository_id is None:
        raise ValueError(f"Repository '{repository_key}' not found")

    routing = await get_routing_policy_recommendations(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        lookback_days=lookback_days,
        limit=limit,
        min_case_count=routing_min_case_count,
        min_confidence=routing_min_confidence,
    )
    clarification = await get_clarification_policy(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        lookback_days=lookback_days,
        limit=limit,
        min_case_count=clarification_min_case_count,
    )
    profiles = await list_triage_behavior_profiles(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        lookback_days=lookback_days,
        limit=limit,
    )

    await pool.execute(
        """
        DELETE FROM ops.triage_policy_artifacts
        WHERE repository_id = $1
          AND ($2::text IS NULL OR project_key = $2)
          AND version = $3
        """,
        repository_id,
        project_key,
        DEFAULT_POLICY_VERSION,
    )

    inserted = 0
    for policy_kind, items in [
        ("routing_recommendation", routing["recommendations"]),
        ("clarification_policy", clarification["policies"]),
        ("behavior_profile", profiles["profiles"]),
    ]:
        for item in items:
            policy_key = str(
                item.get("policy_key")
                or item.get("profile_key")
                or f"{policy_kind}:{inserted + 1}"
            )
            await pool.execute(
                """
                INSERT INTO ops.triage_policy_artifacts (
                    repository_id, project_key, policy_kind, policy_key, version,
                    confidence, case_count, evidence_summary_json, policy_json,
                    rollout_stage, confidence_threshold, minimum_evidence_threshold,
                    drift_state, is_suppressed, last_reviewed_utc
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11, $12, $13, FALSE, NOW())
                """,
                repository_id,
                project_key,
                policy_kind,
                policy_key,
                DEFAULT_POLICY_VERSION,
                item.get("confidence"),
                int(item.get("case_count") or 0),
                json.dumps({"repository_key": repository_key, "project_key": project_key, "policy_kind": policy_kind}),
                json.dumps(item),
                DEFAULT_ROLLOUT_STAGE,
                item.get("confidence"),
                int(item.get("case_count") or 0),
                DEFAULT_DRIFT_STATE,
            )
            inserted += 1

    return {
        "repository_key": repository_key,
        "project_key": project_key,
        "policy_version": DEFAULT_POLICY_VERSION,
        "routing_recommendation_count": routing["recommendation_count"],
        "clarification_policy_count": clarification["policy_count"],
        "behavior_profile_count": profiles["profile_count"],
        "persisted_artifact_count": inserted,
    }


async def get_behavior_policy_status(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    project_key: str | None = None,
) -> dict[str, Any]:
    rows = await pool.fetch(
        """
        SELECT
            tpa.policy_kind,
            tpa.policy_key,
            tpa.version,
            tpa.confidence,
            tpa.case_count,
            tpa.rollout_stage,
            tpa.confidence_threshold,
            tpa.minimum_evidence_threshold,
            tpa.drift_state,
            tpa.is_suppressed,
            tpa.last_reviewed_utc,
            tpa.governance_notes
        FROM ops.triage_policy_artifacts tpa
        JOIN catalog.repositories r ON r.id = tpa.repository_id
        WHERE r.repository_key = $1
          AND ($2::text IS NULL OR tpa.project_key = $2)
        ORDER BY tpa.policy_kind, tpa.policy_key, tpa.id
        """,
        repository_key,
        project_key,
    )
    data_rows = [
        {
            "policy_kind": row["policy_kind"],
            "policy_key": row["policy_key"],
            "version": row["version"],
            "confidence": row["confidence"],
            "case_count": row["case_count"],
            "rollout_stage": row["rollout_stage"],
            "confidence_threshold": row["confidence_threshold"],
            "minimum_evidence_threshold": row["minimum_evidence_threshold"],
            "drift_state": row["drift_state"],
            "is_suppressed": row["is_suppressed"],
            "last_reviewed_utc": _safe_iso(row.get("last_reviewed_utc")),
            "governance_notes": row["governance_notes"],
        }
        for row in rows
    ]
    return {
        "repository_key": repository_key,
        "project_key": project_key,
        "artifact_count": len(data_rows),
        "artifacts": data_rows,
    }


async def triage_request_with_memory(
    pool: asyncpg.Pool,
    settings: Any,
    *,
    prompt_text: str,
    repository_key: str,
    project_key: str | None = None,
    feature_key: str | None = None,
    request_kind: str | None = None,
    execution_mode: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    search = await triage_memory.search_triage_cases(
        pool,
        settings,
        prompt_text=prompt_text,
        repository_key=repository_key,
        project_key=project_key,
        feature_key=feature_key,
        request_kind=request_kind,
        execution_mode=execution_mode,
        selected_workflow_name=selected_workflow_name,
        selected_run_action=selected_run_action,
        limit=limit,
        qdrant_client=None,
    )
    routing = await get_routing_policy_recommendations(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        request_kind=request_kind,
        limit=3,
        min_case_count=1,
        min_confidence=0.0,
    )
    clarification = await get_clarification_policy(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        request_kind=request_kind,
        selected_workflow_name=selected_workflow_name,
        selected_run_action=selected_run_action,
        limit=3,
        min_case_count=1,
    )
    behavior = await list_triage_behavior_profiles(
        pool,
        repository_key=repository_key,
        project_key=project_key,
        limit=3,
    )
    governance = await get_behavior_policy_status(
        pool,
        repository_key=repository_key,
        project_key=project_key,
    )

    top_search = search["rows"][0] if search["rows"] else None
    top_policy = routing["recommendations"][0] if routing["recommendations"] else None
    top_stage = next(
        (
            artifact["rollout_stage"]
            for artifact in governance["artifacts"]
            if artifact["policy_kind"] == "routing_recommendation"
        ),
        DEFAULT_ROLLOUT_STAGE,
    )
    no_recommendation_reasons: list[str] = []
    if top_search is None:
        no_recommendation_reasons.append("no similar cases found")
    if top_policy is None:
        no_recommendation_reasons.append("no routing policy recommendation met thresholds")

    return {
        "advisory_only": top_stage != "trusted",
        "repository_key": repository_key,
        "project_key": project_key,
        "prompt_text": prompt_text,
        "recommended_request_kind": (
            top_policy.get("request_kind")
            if top_policy is not None
            else top_search.get("request_kind") if top_search is not None else request_kind
        ),
        "recommended_workflow_name": (
            top_policy.get("recommended_workflow_name")
            if top_policy is not None
            else top_search.get("selected_workflow_name") if top_search is not None else None
        ),
        "recommended_run_action": (
            top_policy.get("recommended_run_action")
            if top_policy is not None
            else top_search.get("selected_run_action") if top_search is not None else None
        ),
        "recommendation_confidence": (
            top_policy.get("confidence")
            if top_policy is not None
            else top_search.get("similarity_score") if top_search is not None else None
        ),
        "rollout_stage": top_stage,
        "supporting_cases": search["rows"][:3],
        "routing_recommendations": routing["recommendations"][:3],
        "clarification_policies": clarification["policies"][:3],
        "behavior_profiles": behavior["profiles"][:3],
        "policy_status": governance["artifacts"],
        "ranking_features": top_search.get("ranking_features") if top_search is not None else None,
        "no_recommendation_reasons": no_recommendation_reasons,
    }


async def finalize_triage_outcome(
    pool: asyncpg.Pool,
    *,
    triage_case_id: str,
    outcome_status: str,
    repository_key: str,
    project_key: str | None = None,
    successful_execution: bool | None = None,
    human_override: bool | None = None,
    correction_reason: str | None = None,
    corrected_request_kind: str | None = None,
    corrected_execution_mode: str | None = None,
    corrected_selected_workflow_name: str | None = None,
    feedback_notes: str | None = None,
    refresh_policy_artifacts: bool = True,
) -> dict[str, Any]:
    updated = await triage_memory.record_triage_case_feedback(
        pool,
        triage_case_id=triage_case_id,
        outcome_status=outcome_status,
        successful_execution=successful_execution,
        human_override=human_override,
        correction_reason=correction_reason,
        corrected_request_kind=corrected_request_kind,
        corrected_execution_mode=corrected_execution_mode,
        corrected_selected_workflow_name=corrected_selected_workflow_name,
        feedback_notes=feedback_notes,
    )
    if not updated:
        raise ValueError(f"Triage case '{triage_case_id}' not found")

    refresh_result = None
    if refresh_policy_artifacts:
        refresh_result = await refresh_triage_policy_artifacts(
            pool,
            repository_key=repository_key,
            project_key=project_key,
        )
    policy_status = await get_behavior_policy_status(
        pool,
        repository_key=repository_key,
        project_key=project_key,
    )
    return {
        "triage_case_id": triage_case_id,
        "updated": True,
        "policy_artifacts_refreshed": refresh_policy_artifacts,
        "refresh_result": refresh_result,
        "policy_status": policy_status,
    }
