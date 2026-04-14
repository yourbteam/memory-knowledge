from __future__ import annotations

from typing import Any

import asyncpg

from memory_knowledge.admin import analytics


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _team_key(actor_email: str | None, planning_context: dict[str, list[dict[str, str]]]) -> str:
    projects = planning_context.get("projects", [])
    if projects:
        return f"project:{projects[0]['project_key']}"
    normalized = str(actor_email or "").strip().lower()
    if "@" in normalized:
        return f"domain:{normalized.split('@', 1)[1]}"
    return "team:unknown"


async def get_actor_adaptation_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    actor_email: str,
    workflow_name: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
) -> dict[str, Any]:
    quality = await analytics.get_quality_grade_summary(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        actor_email=actor_email,
        since_utc=since_utc,
        until_utc=until_utc,
        include_planning_context=True,
    )
    convergence = await analytics.get_convergence_recommendation_summary(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        actor_email=actor_email,
        since_utc=since_utc,
        until_utc=until_utc,
        include_planning_context=True,
    )
    entropy = await analytics.list_entropy_sweep_targets(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        actor_email=actor_email,
        since_utc=since_utc,
        until_utc=until_utc,
        limit=5,
        include_planning_context=True,
    )

    quality_rows = quality["summary"]
    convergence_rows = convergence["summary"]
    entropy_rows = entropy["targets"]

    if not quality_rows and not convergence_rows and not entropy_rows:
        return {
            "repository_key": repository_key,
            "actor_email": actor_email,
            "workflow_name": workflow_name,
            "match_found": False,
            "adaptation_mode": "balanced",
            "confidence_delta": 0.0,
            "requires_stronger_clarification": False,
            "preferred_route_posture": "standard",
            "team_key": "team:unknown",
            "evidence": {
                "run_count": 0,
                "avg_score": 0.0,
                "entropy_target_count": 0,
                "primary_recommendation": None,
            },
            "planning_context": {"projects": [], "features": [], "tasks": []},
        }

    planning_context = next(
        (
            row["planning_context"]
            for row in quality_rows + convergence_rows + entropy_rows
            if row.get("planning_context")
        ),
        {"projects": [], "features": [], "tasks": []},
    )
    avg_score = _avg([float(row.get("avg_score") or 0.0) for row in quality_rows if row.get("avg_score") is not None])
    run_count = sum(int(row.get("run_count") or 0) for row in quality_rows) or sum(
        int(row.get("run_count") or 0) for row in convergence_rows
    )
    entropy_target_count = len(entropy_rows)
    primary_recommendation = next(
        (row.get("primary_recommendation") for row in convergence_rows if row.get("primary_recommendation")),
        None,
    )

    adaptation_mode = "balanced"
    confidence_delta = 0.0
    requires_stronger_clarification = False
    preferred_route_posture = "standard"

    if run_count >= 2:
        if avg_score >= 85.0 and entropy_target_count == 0:
            adaptation_mode = "streamlined"
            confidence_delta = 0.05
            preferred_route_posture = "lean_forward"
        elif avg_score <= 60.0 or entropy_target_count >= 1:
            adaptation_mode = "cautious"
            confidence_delta = -0.1
            requires_stronger_clarification = True
            preferred_route_posture = "safer_default"

    if primary_recommendation in {"ADD_PRE_RETRY_GROUNDING", "INSERT_CONVERGENCE_CHECKPOINT", "ESCALATE_AFTER_THRESHOLD"}:
        adaptation_mode = "cautious"
        confidence_delta = min(confidence_delta, -0.1)
        requires_stronger_clarification = True
        preferred_route_posture = "safer_default"

    return {
        "repository_key": repository_key,
        "actor_email": actor_email,
        "workflow_name": workflow_name,
        "match_found": True,
        "adaptation_mode": adaptation_mode,
        "confidence_delta": round(confidence_delta, 4),
        "requires_stronger_clarification": requires_stronger_clarification,
        "preferred_route_posture": preferred_route_posture,
        "team_key": _team_key(actor_email, planning_context),
        "evidence": {
            "run_count": run_count,
            "avg_score": avg_score,
            "entropy_target_count": entropy_target_count,
            "primary_recommendation": primary_recommendation,
        },
        "planning_context": planning_context,
    }
