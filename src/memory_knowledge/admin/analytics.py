from __future__ import annotations

from collections import defaultdict
from typing import Any

import asyncpg


def _isoformat(value) -> str | None:
    return value.isoformat() if value else None


def _bucket_unknown(value: str | None) -> str:
    return value if value is not None else "unknown"


def _append_clause(
    clauses: list[str],
    args: list[Any],
    sql_template: str,
    value: Any,
) -> None:
    args.append(value)
    clauses.append(sql_template.format(len(args)))


def _distinct_sorted(items: list[dict[str, str]], key_name: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in sorted(items, key=lambda x: x[key_name]):
        if item[key_name] in seen:
            continue
        seen.add(item[key_name])
        result.append(item)
    return result


async def fetch_run_fact(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    actor_email: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if repository_key is not None:
        _append_clause(clauses, args, "r.repository_key = ${}", repository_key)
    if workflow_name is not None:
        _append_clause(clauses, args, "wr.workflow_name = ${}", workflow_name)
    if actor_email is not None:
        if actor_email == "unknown":
            clauses.append("wr.actor_email IS NULL")
        else:
            _append_clause(clauses, args, "wr.actor_email = ${}", actor_email)
    if since_utc is not None:
        _append_clause(clauses, args, "wr.started_utc >= ${}::timestamptz", since_utc)
    if until_utc is not None:
        _append_clause(clauses, args, "wr.started_utc <= ${}::timestamptz", until_utc)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = await pool.fetch(
        f"""
        SELECT
            wr.id AS workflow_run_id,
            wr.run_id,
            r.repository_key,
            wr.workflow_name,
            wr.actor_email,
            rv.internal_code AS status_code,
            rv.is_terminal,
            wr.started_utc,
            wr.completed_utc,
            wr.iteration_count
        FROM ops.workflow_runs wr
        JOIN catalog.repositories r ON r.id = wr.repository_id
        JOIN core.reference_values rv ON rv.id = wr.status_id
        {where_sql}
        ORDER BY wr.started_utc DESC NULLS LAST, wr.run_id DESC
        """,
        *args,
    )
    facts = []
    for row in rows:
        duration_ms = None
        if row["started_utc"] and row["completed_utc"]:
            duration_ms = (row["completed_utc"] - row["started_utc"]).total_seconds() * 1000.0
        facts.append(
            {
                "workflow_run_id": row["workflow_run_id"],
                "run_id": str(row["run_id"]),
                "repository_key": row["repository_key"],
                "workflow_name": row["workflow_name"],
                "actor_email": _bucket_unknown(row["actor_email"]),
                "status_code": row["status_code"],
                "is_terminal": row["is_terminal"],
                "started_utc": row["started_utc"],
                "completed_utc": row["completed_utc"],
                "duration_ms": duration_ms,
                "iteration_count": row["iteration_count"],
            }
        )
    return facts


async def fetch_phase_fact(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    phase_id: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if repository_key is not None:
        _append_clause(clauses, args, "r.repository_key = ${}", repository_key)
    if workflow_name is not None:
        _append_clause(clauses, args, "wr.workflow_name = ${}", workflow_name)
    if phase_id is not None:
        _append_clause(clauses, args, "wps.phase_id = ${}", phase_id)
    if since_utc is not None:
        _append_clause(
            clauses,
            args,
            "COALESCE(wps.started_utc, wps.completed_utc) >= ${}::timestamptz",
            since_utc,
        )
    if until_utc is not None:
        _append_clause(
            clauses,
            args,
            "COALESCE(wps.started_utc, wps.completed_utc) <= ${}::timestamptz",
            until_utc,
        )
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = await pool.fetch(
        f"""
        SELECT
            wps.workflow_run_id,
            wr.run_id,
            r.repository_key,
            wr.workflow_name,
            wps.phase_id,
            wps.status,
            CASE
                WHEN wps.status = 'success' THEN 'success'
                WHEN wps.status = 'error' THEN 'error'
                WHEN wps.status = 'cancelled' THEN 'cancelled'
                ELSE 'other'
            END AS status_bucket,
            wps.decision,
            wps.attempts,
            wps.started_utc,
            wps.completed_utc,
            wps.error_text
        FROM ops.workflow_phase_states wps
        JOIN ops.workflow_runs wr ON wr.id = wps.workflow_run_id
        JOIN catalog.repositories r ON r.id = wr.repository_id
        {where_sql}
        ORDER BY wps.phase_id ASC, wr.run_id DESC
        """,
        *args,
    )
    facts = []
    for row in rows:
        duration_ms = None
        if row["started_utc"] and row["completed_utc"]:
            duration_ms = (row["completed_utc"] - row["started_utc"]).total_seconds() * 1000.0
        facts.append(
            {
                "workflow_run_id": row["workflow_run_id"],
                "run_id": str(row["run_id"]),
                "repository_key": row["repository_key"],
                "workflow_name": row["workflow_name"],
                "phase_id": row["phase_id"],
                "status": row["status"],
                "status_bucket": row["status_bucket"],
                "decision": _bucket_unknown(row["decision"]),
                "attempts": row["attempts"],
                "started_utc": row["started_utc"],
                "completed_utc": row["completed_utc"],
                "duration_ms": duration_ms,
                "error_text": row["error_text"],
            }
        )
    return facts


async def fetch_validator_fact(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    validator_code: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if repository_key is not None:
        _append_clause(clauses, args, "r.repository_key = ${}", repository_key)
    if workflow_name is not None:
        _append_clause(clauses, args, "wr.workflow_name = ${}", workflow_name)
    if validator_code is not None:
        _append_clause(clauses, args, "wvr.validator_code = ${}", validator_code)
    if since_utc is not None:
        _append_clause(
            clauses,
            args,
            "COALESCE(wvr.started_utc, wvr.completed_utc, wvr.created_utc) >= ${}::timestamptz",
            since_utc,
        )
    if until_utc is not None:
        _append_clause(
            clauses,
            args,
            "COALESCE(wvr.started_utc, wvr.completed_utc, wvr.created_utc) <= ${}::timestamptz",
            until_utc,
        )
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = await pool.fetch(
        f"""
        SELECT
            wvr.workflow_run_id,
            wr.run_id,
            r.repository_key,
            wr.workflow_name,
            wvr.phase_id,
            wvr.validator_code,
            wvr.validator_name,
            wvr.attempt_number,
            rv.internal_code AS status_code,
            wvr.failure_reason_code,
            wvr.failure_reason,
            wvr.created_utc,
            wvr.started_utc,
            wvr.completed_utc
        FROM ops.workflow_validator_results wvr
        JOIN ops.workflow_runs wr ON wr.id = wvr.workflow_run_id
        JOIN catalog.repositories r ON r.id = wr.repository_id
        JOIN core.reference_values rv ON rv.id = wvr.status_id
        {where_sql}
        ORDER BY wvr.validator_code ASC, wvr.attempt_number ASC
        """,
        *args,
    )
    return [dict(row) for row in rows]


async def fetch_artifact_latest_fact(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if repository_key is not None:
        _append_clause(clauses, args, "r.repository_key = ${}", repository_key)
    if workflow_name is not None:
        _append_clause(clauses, args, "wr.workflow_name = ${}", workflow_name)
    if since_utc is not None:
        _append_clause(clauses, args, "wr.started_utc >= ${}::timestamptz", since_utc)
    if until_utc is not None:
        _append_clause(clauses, args, "wr.started_utc <= ${}::timestamptz", until_utc)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = await pool.fetch(
        f"""
        SELECT
            wa.workflow_run_id,
            wr.run_id,
            r.repository_key,
            wr.workflow_name,
            wa.artifact_name,
            wa.iteration
        FROM ops.workflow_artifacts wa
        JOIN ops.workflow_runs wr ON wr.id = wa.workflow_run_id
        JOIN catalog.repositories r ON r.id = wr.repository_id
        {where_sql}
        """,
        *args,
    )
    return [dict(row) for row in rows]


async def fetch_planning_context_for_runs(
    pool: asyncpg.Pool,
    run_ids: list[int],
) -> dict[int, dict[str, list[dict[str, str]]]]:
    if not run_ids:
        return {}
    rows = await pool.fetch(
        """
        SELECT
            twr.workflow_run_id,
            t.task_key,
            t.title AS task_title,
            f.feature_key,
            f.title AS feature_title,
            p.project_key,
            p.name AS project_name
        FROM planning.task_workflow_runs twr
        JOIN planning.tasks t ON t.id = twr.task_id
        LEFT JOIN planning.features f ON f.id = t.feature_id
        LEFT JOIN planning.projects p ON p.id = t.project_id
        JOIN ops.workflow_runs wr ON wr.id = twr.workflow_run_id
        WHERE twr.workflow_run_id = ANY($1::bigint[])
          AND wr.repository_id = t.repository_id
        ORDER BY twr.workflow_run_id, p.project_key, f.feature_key, t.task_key
        """,
        run_ids,
    )
    context_by_run: dict[int, dict[str, list[dict[str, str]]]] = {}
    for row in rows:
        run_id = row["workflow_run_id"]
        ctx = context_by_run.setdefault(run_id, {"projects": [], "features": [], "tasks": []})
        if row["project_key"]:
            ctx["projects"].append(
                {"project_key": str(row["project_key"]), "project_name": row["project_name"]}
            )
        if row["feature_key"]:
            ctx["features"].append(
                {"feature_key": str(row["feature_key"]), "feature_title": row["feature_title"]}
            )
        if row["task_key"]:
            ctx["tasks"].append(
                {"task_key": str(row["task_key"]), "task_title": row["task_title"]}
            )
    for run_id, ctx in context_by_run.items():
        ctx["projects"] = _distinct_sorted(ctx["projects"], "project_key")
        ctx["features"] = _distinct_sorted(ctx["features"], "feature_key")
        ctx["tasks"] = _distinct_sorted(ctx["tasks"], "task_key")
    return context_by_run


def _bucket_planning_context(
    bucket_run_ids: list[int],
    run_planning_context: dict[int, dict[str, list[dict[str, str]]]],
) -> dict[str, list[dict[str, str]]]:
    projects: list[dict[str, str]] = []
    features: list[dict[str, str]] = []
    tasks: list[dict[str, str]] = []
    for run_id in bucket_run_ids:
        ctx = run_planning_context.get(run_id, {"projects": [], "features": [], "tasks": []})
        projects.extend(ctx["projects"])
        features.extend(ctx["features"])
        tasks.extend(ctx["tasks"])
    return {
        "projects": _distinct_sorted(projects, "project_key"),
        "features": _distinct_sorted(features, "feature_key"),
        "tasks": _distinct_sorted(tasks, "task_key"),
    }


def _empty_planning_context() -> dict[str, list[dict[str, str]]]:
    return {"projects": [], "features": [], "tasks": []}


def _reason_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    return (int(item["count"]), str(item["reason_code"]))


_ACTION_PRIORITY = {
    "ADD_PRE_RETRY_GROUNDING": 0,
    "MOVE_VALIDATOR_EARLIER": 1,
    "ADD_REPAIR_OR_CLARIFICATION_PHASE": 2,
    "INSERT_CONVERGENCE_CHECKPOINT": 3,
    "STRENGTHEN_PHASE_ENTRY_CRITERIA": 4,
    "ADD_PHASE_SPEC_OR_GUARDRAIL": 5,
    "ESCALATE_AFTER_THRESHOLD": 6,
    "RUN_ENTROPY_SWEEP": 7,
    "HARDEN_VALIDATOR_EXECUTION": 8,
    "MONITOR": 99,
}


def _action_sort_key(item: tuple[str, int]) -> tuple[int, int, str]:
    action_code, count = item
    return (-count, _ACTION_PRIORITY.get(action_code, 50), action_code)


async def get_agent_performance_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    actor_email: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    include_planning_context: bool = False,
) -> dict[str, Any]:
    run_fact = await fetch_run_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        actor_email=actor_email,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in run_fact:
        key = (row["repository_key"], row["workflow_name"], row["actor_email"])
        bucket = buckets.setdefault(
            key,
            {
                "repository_key": key[0],
                "workflow_name": key[1],
                "actor_email": key[2],
                "run_count": 0,
                "terminal_count": 0,
                "non_terminal_count": 0,
                "pending_count": 0,
                "submitted_count": 0,
                "running_count": 0,
                "success_count": 0,
                "partial_count": 0,
                "error_count": 0,
                "cancelled_count": 0,
                "_duration_total": 0.0,
                "_duration_count": 0,
                "_iteration_total": 0,
                "_run_ids": [],
            },
        )
        bucket["run_count"] += 1
        bucket["terminal_count"] += 1 if row["is_terminal"] else 0
        bucket["non_terminal_count"] += 0 if row["is_terminal"] else 1
        bucket["_iteration_total"] += row["iteration_count"] or 0
        bucket["_run_ids"].append(row["workflow_run_id"])
        if row["duration_ms"] is not None:
            bucket["_duration_total"] += row["duration_ms"]
            bucket["_duration_count"] += 1
        status_key = row["status_code"].replace("RUN_", "").lower() + "_count"
        bucket[status_key] += 1
    run_planning_context = (
        await fetch_planning_context_for_runs(pool, [r["workflow_run_id"] for r in run_fact])
        if include_planning_context
        else {}
    )
    summary = []
    for key in sorted(buckets):
        bucket = buckets[key]
        summary.append(
            {
                "repository_key": bucket["repository_key"],
                "workflow_name": bucket["workflow_name"],
                "actor_email": bucket["actor_email"],
                "run_count": bucket["run_count"],
                "terminal_count": bucket["terminal_count"],
                "non_terminal_count": bucket["non_terminal_count"],
                "pending_count": bucket["pending_count"],
                "submitted_count": bucket["submitted_count"],
                "running_count": bucket["running_count"],
                "success_count": bucket["success_count"],
                "partial_count": bucket["partial_count"],
                "error_count": bucket["error_count"],
                "cancelled_count": bucket["cancelled_count"],
                "avg_duration_ms": (
                    bucket["_duration_total"] / bucket["_duration_count"]
                    if bucket["_duration_count"]
                    else 0.0
                ),
                "avg_iteration_count": bucket["_iteration_total"] / bucket["run_count"]
                if bucket["run_count"]
                else 0.0,
                "planning_context": _bucket_planning_context(bucket["_run_ids"], run_planning_context)
                if include_planning_context
                else _empty_planning_context(),
            }
        )
    return {
        "summary": summary,
        "ordering": ["repository_key", "workflow_name", "actor_email"],
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "actor_email": actor_email,
            "since_utc": since_utc,
            "until_utc": until_utc,
            "include_planning_context": include_planning_context,
        },
        "eligible_run_count": len(run_fact),
        "excluded_run_count": 0,
    }


async def get_phase_quality_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    phase_id: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
) -> dict[str, Any]:
    run_fact = await fetch_run_fact(pool, repository_key=repository_key, workflow_name=workflow_name)
    phase_fact = await fetch_phase_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        phase_id=phase_id,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    eligible_run_ids = {row["workflow_run_id"] for row in phase_fact}
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in phase_fact:
        key = (row["repository_key"], row["workflow_name"], row["phase_id"])
        bucket = buckets.setdefault(
            key,
            {
                "repository_key": key[0],
                "workflow_name": key[1],
                "phase_id": key[2],
                "_run_ids": set(),
                "execution_count": 0,
                "success_count": 0,
                "error_count": 0,
                "cancelled_count": 0,
                "other_count": 0,
                "_decision_counts": defaultdict(int),
                "_attempt_total": 0,
                "_duration_total": 0.0,
                "_duration_count": 0,
            },
        )
        bucket["_run_ids"].add(row["workflow_run_id"])
        bucket["execution_count"] += row["attempts"]
        bucket[f"{row['status_bucket']}_count"] += 1
        bucket["_decision_counts"][row["decision"]] += 1
        bucket["_attempt_total"] += row["attempts"]
        if row["duration_ms"] is not None:
            bucket["_duration_total"] += row["duration_ms"]
            bucket["_duration_count"] += 1
    summary = []
    for key in sorted(buckets):
        bucket = buckets[key]
        decision_counts = [
            {"decision": decision, "count": count}
            for decision, count in sorted(
                bucket["_decision_counts"].items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        summary.append(
            {
                "repository_key": bucket["repository_key"],
                "workflow_name": bucket["workflow_name"],
                "phase_id": bucket["phase_id"],
                "run_count": len(bucket["_run_ids"]),
                "execution_count": bucket["execution_count"],
                "success_count": bucket["success_count"],
                "error_count": bucket["error_count"],
                "cancelled_count": bucket["cancelled_count"],
                "other_count": bucket["other_count"],
                "decision_counts": decision_counts,
                "avg_attempts": bucket["_attempt_total"] / len(bucket["_run_ids"])
                if bucket["_run_ids"]
                else 0.0,
                "avg_duration_ms": (
                    bucket["_duration_total"] / bucket["_duration_count"]
                    if bucket["_duration_count"]
                    else 0.0
                ),
            }
        )
    return {
        "summary": summary,
        "ordering": ["repository_key", "workflow_name", "phase_id"],
        "coverage": {"historical_complete": False, "basis": "post_adoption_only"},
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "phase_id": phase_id,
            "since_utc": since_utc,
            "until_utc": until_utc,
        },
        "eligible_run_count": len(eligible_run_ids),
        "excluded_run_count": max(len(run_fact) - len(eligible_run_ids), 0),
    }


async def get_validator_failure_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    validator_code: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
) -> dict[str, Any]:
    run_fact = await fetch_run_fact(pool, repository_key=repository_key, workflow_name=workflow_name)
    validator_fact = await fetch_validator_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        validator_code=validator_code,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    eligible_run_ids = {row["workflow_run_id"] for row in validator_fact}
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in validator_fact:
        key = (row["repository_key"], row["workflow_name"], row["validator_code"])
        bucket = buckets.setdefault(
            key,
            {
                "repository_key": key[0],
                "workflow_name": key[1],
                "validator_code": key[2],
                "validator_name": row["validator_name"],
                "pending_count": 0,
                "pass_count": 0,
                "fail_count": 0,
                "error_count": 0,
                "skipped_count": 0,
                "_reasons": defaultdict(int),
            },
        )
        status_map = {
            "VAL_PENDING": "pending_count",
            "VAL_PASSED": "pass_count",
            "VAL_FAILED": "fail_count",
            "VAL_ERROR": "error_count",
            "VAL_SKIPPED": "skipped_count",
        }
        bucket[status_map[row["status_code"]]] += 1
        bucket["_reasons"][_bucket_unknown(row["failure_reason_code"])] += 1
    summary = []
    for key in sorted(buckets):
        bucket = buckets[key]
        summary.append(
            {
                "repository_key": bucket["repository_key"],
                "workflow_name": bucket["workflow_name"],
                "validator_code": bucket["validator_code"],
                "validator_name": bucket["validator_name"],
                "pending_count": bucket["pending_count"],
                "pass_count": bucket["pass_count"],
                "fail_count": bucket["fail_count"],
                "error_count": bucket["error_count"],
                "skipped_count": bucket["skipped_count"],
                "failure_reason_counts": [
                    {"failure_reason_code": code, "count": count}
                    for code, count in sorted(bucket["_reasons"].items(), key=lambda item: (-item[1], item[0]))
                ],
            }
        )
    return {
        "summary": summary,
        "ordering": ["repository_key", "workflow_name", "validator_code"],
        "coverage": {"historical_complete": False, "basis": "post_adoption_only"},
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "validator_code": validator_code,
            "since_utc": since_utc,
            "until_utc": until_utc,
        },
        "eligible_run_count": len(eligible_run_ids),
        "excluded_run_count": max(len(run_fact) - len(eligible_run_ids), 0),
    }


async def get_loop_pattern_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    loop_thresholds: list[int] | None = None,
    include_planning_context: bool = False,
) -> dict[str, Any]:
    thresholds = sorted({int(value) for value in (loop_thresholds or [3, 5])})
    if not thresholds or any(value <= 0 for value in thresholds):
        raise ValueError("loop_thresholds must contain only positive integers")
    run_fact = await fetch_run_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    phase_fact = await fetch_phase_fact(pool, repository_key=repository_key, workflow_name=workflow_name)
    artifact_latest_fact = await fetch_artifact_latest_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    phase_by_run = defaultdict(list)
    for row in phase_fact:
        phase_by_run[row["workflow_run_id"]].append(row)
    artifact_max_by_run = defaultdict(int)
    for row in artifact_latest_fact:
        artifact_max_by_run[row["workflow_run_id"]] = max(artifact_max_by_run[row["workflow_run_id"]], row["iteration"])
    run_planning_context = (
        await fetch_planning_context_for_runs(pool, [r["workflow_run_id"] for r in run_fact])
        if include_planning_context
        else {}
    )
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in run_fact:
        key = (row["repository_key"], row["workflow_name"])
        bucket = buckets.setdefault(
            key,
            {
                "repository_key": key[0],
                "workflow_name": key[1],
                "run_count": 0,
                "_iteration_total": 0,
                "_threshold_counts": {threshold: 0 for threshold in thresholds},
                "_phase_retry": defaultdict(lambda: {"runs_with_attempts_ge_2": 0, "max_attempts": 0}),
                "_max_latest_artifact_iteration": 0,
                "_run_ids": [],
            },
        )
        bucket["run_count"] += 1
        bucket["_iteration_total"] += row["iteration_count"] or 0
        bucket["_run_ids"].append(row["workflow_run_id"])
        for threshold in thresholds:
            if (row["iteration_count"] or 0) >= threshold:
                bucket["_threshold_counts"][threshold] += 1
        for phase in phase_by_run.get(row["workflow_run_id"], []):
            phase_bucket = bucket["_phase_retry"][phase["phase_id"]]
            if phase["attempts"] >= 2:
                phase_bucket["runs_with_attempts_ge_2"] += 1
            phase_bucket["max_attempts"] = max(phase_bucket["max_attempts"], phase["attempts"])
        bucket["_max_latest_artifact_iteration"] = max(
            bucket["_max_latest_artifact_iteration"],
            artifact_max_by_run.get(row["workflow_run_id"], 0),
        )
    summary = []
    for key in sorted(buckets):
        bucket = buckets[key]
        phase_retry_counts = [
            {
                "phase_id": phase_id,
                "runs_with_attempts_ge_2": values["runs_with_attempts_ge_2"],
                "max_attempts": values["max_attempts"],
            }
            for phase_id, values in sorted(
                bucket["_phase_retry"].items(),
                key=lambda item: (-item[1]["max_attempts"], item[0]),
            )
        ]
        summary.append(
            {
                "repository_key": bucket["repository_key"],
                "workflow_name": bucket["workflow_name"],
                "run_count": bucket["run_count"],
                "avg_iteration_count": bucket["_iteration_total"] / bucket["run_count"]
                if bucket["run_count"]
                else 0.0,
                "threshold_counts": [
                    {"threshold": threshold, "run_count": bucket["_threshold_counts"][threshold]}
                    for threshold in thresholds
                ],
                "phase_retry_counts": phase_retry_counts,
                "max_latest_artifact_iteration": bucket["_max_latest_artifact_iteration"],
                "planning_context": _bucket_planning_context(bucket["_run_ids"], run_planning_context)
                if include_planning_context
                else _empty_planning_context(),
            }
        )
    return {
        "summary": summary,
        "ordering": ["repository_key", "workflow_name"],
        "coverage": {
            "historical_complete": False,
            "basis": "run_metrics_complete__phase_retry_post_adoption_only",
        },
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "since_utc": since_utc,
            "until_utc": until_utc,
            "loop_thresholds": thresholds,
            "include_planning_context": include_planning_context,
        },
        "eligible_run_count": len(run_fact),
        "excluded_run_count": 0,
    }


def build_run_grade_fact(
    run_fact: list[dict[str, Any]],
    phase_fact: list[dict[str, Any]],
    validator_fact: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    phase_by_run = defaultdict(list)
    validator_by_run = defaultdict(list)
    for row in phase_fact:
        phase_by_run[row["workflow_run_id"]].append(row)
    for row in validator_fact:
        validator_by_run[row["workflow_run_id"]].append(row)
    grades = []
    for row in run_fact:
        if row["status_code"] not in {"RUN_SUCCESS", "RUN_PARTIAL", "RUN_ERROR", "RUN_CANCELLED"}:
            continue
        phases = phase_by_run.get(row["workflow_run_id"], [])
        validators = validator_by_run.get(row["workflow_run_id"], [])
        if not phases or not validators:
            continue
        terminal_penalty = 0
        if row["status_code"] in {"RUN_ERROR", "RUN_CANCELLED"}:
            terminal_penalty = 40
        elif row["status_code"] == "RUN_PARTIAL":
            terminal_penalty = 20
        validator_failure_penalty = 25 if any(v["status_code"] == "VAL_FAILED" for v in validators) else 0
        validator_error_penalty = 15 if any(v["status_code"] == "VAL_ERROR" for v in validators) else 0
        iteration_penalty = 10 if (row["iteration_count"] or 0) >= 3 else 0
        phase_retry_penalty = 10 if any(p["attempts"] >= 3 for p in phases) else 0
        phase_error_penalty = 10 if any(p["error_text"] is not None for p in phases) else 0
        score = 100 - (
            terminal_penalty
            + validator_failure_penalty
            + validator_error_penalty
            + iteration_penalty
            + phase_retry_penalty
            + phase_error_penalty
        )
        if score >= 90:
            grade = "A"
        elif score >= 75:
            grade = "B"
        elif score >= 60:
            grade = "C"
        elif score >= 45:
            grade = "D"
        else:
            grade = "F"
        grades.append(
            {
                **row,
                "score": score,
                "grade": grade,
                "terminal_penalty": float(terminal_penalty),
                "validator_failure_penalty": float(validator_failure_penalty),
                "validator_error_penalty": float(validator_error_penalty),
                "iteration_penalty": float(iteration_penalty),
                "phase_retry_penalty": float(phase_retry_penalty),
                "phase_error_penalty": float(phase_error_penalty),
            }
        )
    return grades


async def get_quality_grade_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    actor_email: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    include_planning_context: bool = False,
) -> dict[str, Any]:
    run_fact = await fetch_run_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        actor_email=actor_email,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    phase_fact = await fetch_phase_fact(pool, repository_key=repository_key, workflow_name=workflow_name)
    validator_fact = await fetch_validator_fact(pool, repository_key=repository_key, workflow_name=workflow_name)
    run_grade_fact = build_run_grade_fact(run_fact, phase_fact, validator_fact)
    run_planning_context = (
        await fetch_planning_context_for_runs(pool, [r["workflow_run_id"] for r in run_grade_fact])
        if include_planning_context
        else {}
    )
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in run_grade_fact:
        key = (row["repository_key"], row["workflow_name"], row["actor_email"])
        bucket = buckets.setdefault(
            key,
            {
                "repository_key": key[0],
                "workflow_name": key[1],
                "actor_email": key[2],
                "run_count": 0,
                "_score_total": 0.0,
                "_grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
                "_rows": [],
                "_run_ids": [],
                "_component_totals": defaultdict(float),
            },
        )
        bucket["run_count"] += 1
        bucket["_score_total"] += row["score"]
        bucket["_grade_distribution"][row["grade"]] += 1
        bucket["_rows"].append(row)
        bucket["_run_ids"].append(row["workflow_run_id"])
        for component in (
            "terminal_penalty",
            "validator_failure_penalty",
            "validator_error_penalty",
            "iteration_penalty",
            "phase_retry_penalty",
            "phase_error_penalty",
        ):
            bucket["_component_totals"][component] += row[component]
    summary = []
    for key in sorted(buckets):
        bucket = buckets[key]
        latest_row = sorted(
            bucket["_rows"],
            key=lambda row: (_isoformat(row["started_utc"]) or "", row["run_id"]),
            reverse=True,
        )[0]
        summary.append(
            {
                "repository_key": bucket["repository_key"],
                "workflow_name": bucket["workflow_name"],
                "actor_email": bucket["actor_email"],
                "run_count": bucket["run_count"],
                "avg_score": bucket["_score_total"] / bucket["run_count"] if bucket["run_count"] else 0.0,
                "grade_distribution": bucket["_grade_distribution"],
                "latest_run_grade": latest_row["grade"],
                "component_averages": {
                    key_name: bucket["_component_totals"][key_name] / bucket["run_count"]
                    if bucket["run_count"]
                    else 0.0
                    for key_name in (
                        "terminal_penalty",
                        "validator_failure_penalty",
                        "validator_error_penalty",
                        "iteration_penalty",
                        "phase_retry_penalty",
                        "phase_error_penalty",
                    )
                },
                "planning_context": _bucket_planning_context(bucket["_run_ids"], run_planning_context)
                if include_planning_context
                else _empty_planning_context(),
            }
        )
    return {
        "summary": summary,
        "ordering": ["repository_key", "workflow_name", "actor_email"],
        "coverage": {"historical_complete": False, "basis": "post_adoption_only"},
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "actor_email": actor_email,
            "since_utc": since_utc,
            "until_utc": until_utc,
            "include_planning_context": include_planning_context,
        },
        "eligible_run_count": len(run_grade_fact),
        "excluded_run_count": max(len(run_fact) - len(run_grade_fact), 0),
    }


async def list_entropy_sweep_targets(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    actor_email: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    limit: int = 20,
    include_planning_context: bool = False,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    run_fact = await fetch_run_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        actor_email=actor_email,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    phase_fact = await fetch_phase_fact(pool, repository_key=repository_key, workflow_name=workflow_name)
    validator_fact = await fetch_validator_fact(pool, repository_key=repository_key, workflow_name=workflow_name)
    run_grade_fact = build_run_grade_fact(run_fact, phase_fact, validator_fact)
    grade_by_run = {row["workflow_run_id"]: row for row in run_grade_fact}
    validator_by_run = defaultdict(list)
    phase_by_run = defaultdict(list)
    for row in validator_fact:
        validator_by_run[row["workflow_run_id"]].append(row)
    for row in phase_fact:
        phase_by_run[row["workflow_run_id"]].append(row)
    eligible_rows = []
    for row in run_grade_fact:
        score = 0
        reason_codes: list[str] = []
        if row["grade"] in {"D", "F"}:
            score += 40
            reason_codes.append("LOW_GRADE")
        if row["status_code"] == "RUN_ERROR":
            score += 25
            reason_codes.append("RUN_ERROR")
        if (row["iteration_count"] or 0) >= 3:
            score += 20
            reason_codes.append("HIGH_ITERATION_COUNT")
        if any(p["attempts"] >= 3 for p in phase_by_run[row["workflow_run_id"]]):
            score += 15
            reason_codes.append("PHASE_RETRY_PRESSURE")
        failed_count = sum(1 for v in validator_by_run[row["workflow_run_id"]] if v["status_code"] == "VAL_FAILED")
        error_count = sum(1 for v in validator_by_run[row["workflow_run_id"]] if v["status_code"] == "VAL_ERROR")
        if failed_count:
            score += 20
            reason_codes.append("VALIDATOR_FAILED")
        if error_count:
            score += 10
            reason_codes.append("VALIDATOR_ERROR")
        eligible_rows.append(
            {
                **row,
                "entropy_score": score,
                "reason_codes": reason_codes,
                "max_score_run_validator_failed_count": failed_count,
                "max_score_run_validator_error_count": error_count,
                "max_score_run_phase_attempts": max(
                    [p["attempts"] for p in phase_by_run[row["workflow_run_id"]]],
                    default=0,
                ),
            }
        )
    run_planning_context = (
        await fetch_planning_context_for_runs(pool, [r["workflow_run_id"] for r in eligible_rows])
        if include_planning_context
        else {}
    )
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in eligible_rows:
        key = (row["repository_key"], row["workflow_name"], row["actor_email"])
        bucket = buckets.setdefault(
            key,
            {
                "repository_key": key[0],
                "workflow_name": key[1],
                "actor_email": key[2],
                "_rows": [],
                "_run_ids": [],
                "_latest_started_utc": None,
            },
        )
        bucket["_rows"].append(row)
        bucket["_run_ids"].append(row["workflow_run_id"])
        if bucket["_latest_started_utc"] is None or (
            row["started_utc"] and row["started_utc"] > bucket["_latest_started_utc"]
        ):
            bucket["_latest_started_utc"] = row["started_utc"]
    targets = []
    for bucket in buckets.values():
        representative = sorted(
            bucket["_rows"],
            key=lambda row: (row["entropy_score"], _isoformat(row["started_utc"]) or "", row["run_id"]),
            reverse=True,
        )[0]
        reason_order = {
            "LOW_GRADE": 0,
            "RUN_ERROR": 1,
            "HIGH_ITERATION_COUNT": 2,
            "PHASE_RETRY_PRESSURE": 3,
            "VALIDATOR_FAILED": 4,
            "VALIDATOR_ERROR": 5,
        }
        targets.append(
            {
                "repository_key": representative["repository_key"],
                "workflow_name": representative["workflow_name"],
                "actor_email": representative["actor_email"],
                "score": representative["entropy_score"],
                "reason_codes": sorted(representative["reason_codes"], key=lambda code: reason_order[code]),
                "supporting_metrics": {
                    "max_score_run_grade": representative["grade"],
                    "max_score_run_status": representative["status_code"],
                    "max_score_run_iteration_count": representative["iteration_count"],
                    "max_score_run_phase_attempts": representative["max_score_run_phase_attempts"],
                    "max_score_run_validator_failed_count": representative["max_score_run_validator_failed_count"],
                    "max_score_run_validator_error_count": representative["max_score_run_validator_error_count"],
                },
                "latest_started_utc": _isoformat(bucket["_latest_started_utc"]),
                "planning_context": _bucket_planning_context(bucket["_run_ids"], run_planning_context)
                if include_planning_context
                else _empty_planning_context(),
            }
        )
    targets = sorted(
        targets,
        key=lambda row: (row["score"], row["latest_started_utc"] or ""),
        reverse=True,
    )[:limit]
    return {
        "targets": targets,
        "ordering": ["score DESC", "latest_started_utc DESC"],
        "coverage": {"historical_complete": False, "basis": "post_adoption_only"},
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "actor_email": actor_email,
            "since_utc": since_utc,
            "until_utc": until_utc,
            "limit": limit,
            "include_planning_context": include_planning_context,
        },
        "eligible_run_count": len(eligible_rows),
        "excluded_run_count": max(len(run_fact) - len(eligible_rows), 0),
    }


async def get_convergence_recommendation_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str | None = None,
    workflow_name: str | None = None,
    actor_email: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    include_planning_context: bool = False,
) -> dict[str, Any]:
    run_fact = await fetch_run_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        actor_email=actor_email,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    phase_fact = await fetch_phase_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    validator_fact = await fetch_validator_fact(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    run_grade_fact = build_run_grade_fact(run_fact, phase_fact, validator_fact)
    phase_by_run = defaultdict(list)
    validator_by_run = defaultdict(list)
    for row in phase_fact:
        phase_by_run[row["workflow_run_id"]].append(row)
    for row in validator_fact:
        validator_by_run[row["workflow_run_id"]].append(row)
    run_planning_context = (
        await fetch_planning_context_for_runs(pool, [r["workflow_run_id"] for r in run_grade_fact])
        if include_planning_context
        else {}
    )

    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in run_grade_fact:
        key = (row["repository_key"], row["workflow_name"], row["actor_email"])
        bucket = buckets.setdefault(
            key,
            {
                "repository_key": key[0],
                "workflow_name": key[1],
                "actor_email": key[2],
                "run_count": 0,
                "_rows": [],
                "_run_ids": [],
                "_latest_started_utc": None,
                "_reason_counts": defaultdict(int),
                "_action_counts": defaultdict(int),
                "_phase_retry_counts": defaultdict(int),
                "_validator_failure_counts": defaultdict(int),
                "_max_iteration_count": 0,
            },
        )
        bucket["run_count"] += 1
        bucket["_rows"].append(row)
        bucket["_run_ids"].append(row["workflow_run_id"])
        bucket["_max_iteration_count"] = max(bucket["_max_iteration_count"], row["iteration_count"] or 0)
        if bucket["_latest_started_utc"] is None or (
            row["started_utc"] and row["started_utc"] > bucket["_latest_started_utc"]
        ):
            bucket["_latest_started_utc"] = row["started_utc"]

        reasons: set[str] = set()
        actions: set[str] = set()
        if row["grade"] in {"D", "F"}:
            reasons.add("LOW_GRADE")
            actions.add("RUN_ENTROPY_SWEEP")
        if row["status_code"] == "RUN_ERROR":
            reasons.add("RUN_ERROR")
            actions.add("ADD_PRE_RETRY_GROUNDING")
        if (row["iteration_count"] or 0) >= 3:
            reasons.add("HIGH_ITERATION_COUNT")
            actions.add("INSERT_CONVERGENCE_CHECKPOINT")

        for phase in phase_by_run[row["workflow_run_id"]]:
            if phase["attempts"] >= 2:
                bucket["_phase_retry_counts"][phase["phase_id"]] += 1
            if phase["attempts"] >= 3:
                reasons.add("PHASE_RETRY_PRESSURE")
                actions.add("STRENGTHEN_PHASE_ENTRY_CRITERIA")
            if phase["error_text"] is not None:
                reasons.add("PHASE_ERROR")
                actions.add("ADD_PHASE_SPEC_OR_GUARDRAIL")

        for validator in validator_by_run[row["workflow_run_id"]]:
            if validator["status_code"] == "VAL_FAILED":
                reasons.add("VALIDATOR_FAILED")
                bucket["_validator_failure_counts"][validator["validator_code"]] += 1
                actions.add("MOVE_VALIDATOR_EARLIER")
            if validator["status_code"] == "VAL_ERROR":
                reasons.add("VALIDATOR_ERROR")
                actions.add("HARDEN_VALIDATOR_EXECUTION")

        if "VALIDATOR_FAILED" in reasons and "PHASE_RETRY_PRESSURE" in reasons:
            actions.add("ADD_REPAIR_OR_CLARIFICATION_PHASE")
        if "RUN_ERROR" in reasons and "HIGH_ITERATION_COUNT" in reasons:
            actions.add("ESCALATE_AFTER_THRESHOLD")

        for reason in reasons:
            bucket["_reason_counts"][reason] += 1
        for action in actions:
            bucket["_action_counts"][action] += 1

    summary = []
    for key in sorted(buckets):
        bucket = buckets[key]
        dominant_retry_phase = None
        if bucket["_phase_retry_counts"]:
            dominant_retry_phase = sorted(
                bucket["_phase_retry_counts"].items(),
                key=lambda item: (-item[1], item[0]),
            )[0][0]
        dominant_failed_validator = None
        if bucket["_validator_failure_counts"]:
            dominant_failed_validator = sorted(
                bucket["_validator_failure_counts"].items(),
                key=lambda item: (-item[1], item[0]),
            )[0][0]
        latest_row = sorted(
            bucket["_rows"],
            key=lambda row: (_isoformat(row["started_utc"]) or "", row["run_id"]),
            reverse=True,
        )[0]
        primary_recommendation = sorted(
            bucket["_action_counts"].items(),
            key=_action_sort_key,
        )[0][0] if bucket["_action_counts"] else "MONITOR"
        summary.append(
            {
                "repository_key": bucket["repository_key"],
                "workflow_name": bucket["workflow_name"],
                "actor_email": bucket["actor_email"],
                "run_count": bucket["run_count"],
                "latest_started_utc": _isoformat(bucket["_latest_started_utc"]),
                "max_iteration_count": bucket["_max_iteration_count"],
                "avg_score": sum(row["score"] for row in bucket["_rows"]) / bucket["run_count"]
                if bucket["run_count"]
                else 0.0,
                "latest_run_grade": latest_row["grade"],
                "dominant_retry_phase": dominant_retry_phase,
                "dominant_failed_validator": dominant_failed_validator,
                "reason_counts": [
                    {"reason_code": reason_code, "count": count}
                    for reason_code, count in sorted(
                        bucket["_reason_counts"].items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                ],
                "recommended_actions": [
                    {"action_code": action_code, "count": count}
                    for action_code, count in sorted(
                        bucket["_action_counts"].items(),
                        key=_action_sort_key,
                    )
                ],
                "primary_recommendation": primary_recommendation,
                "planning_context": _bucket_planning_context(bucket["_run_ids"], run_planning_context)
                if include_planning_context
                else _empty_planning_context(),
            }
        )
    return {
        "summary": summary,
        "ordering": ["repository_key", "workflow_name", "actor_email"],
        "coverage": {"historical_complete": False, "basis": "post_adoption_only"},
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "actor_email": actor_email,
            "since_utc": since_utc,
            "until_utc": until_utc,
            "include_planning_context": include_planning_context,
        },
        "eligible_run_count": len(run_grade_fact),
        "excluded_run_count": max(len(run_fact) - len(run_grade_fact), 0),
    }
