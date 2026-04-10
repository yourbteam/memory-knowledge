from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import asyncpg


def _isoformat(value) -> str | None:
    return value.isoformat() if value else None


def _append_clause(
    clauses: list[str],
    args: list[Any],
    sql_template: str,
    value: Any,
) -> None:
    args.append(value)
    clauses.append(sql_template.format(len(args)))


def _top_counts(
    values: list[str | None],
    *,
    label_key: str,
    count_key: str = "count",
    limit: int = 5,
) -> list[dict[str, Any]]:
    counts = Counter(v for v in values if v)
    items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return [{label_key: value, count_key: count} for value, count in items[:limit]]


async def save_workflow_finding(
    pool: asyncpg.Pool,
    *,
    repository_id: int,
    workflow_run_id: int,
    workflow_name: str,
    phase_id: str,
    agent_name: str,
    attempt_number: int,
    artifact_name: str | None,
    artifact_iteration: int | None,
    artifact_hash: str | None,
    finding_fingerprint: str,
    finding_title: str,
    finding_message: str,
    location: str | None,
    evidence_text: str | None,
    finding_kind_id: int,
    severity: str | None,
    source_kind: str | None,
    status_id: int,
    actor_email: str | None,
    context_json: str | None,
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO ops.workflow_findings (
            repository_id, workflow_run_id, workflow_name, phase_id, agent_name,
            attempt_number, artifact_name, artifact_iteration, artifact_hash,
            finding_fingerprint, finding_title, finding_message, location,
            evidence_text, finding_kind_id, severity, source_kind, status_id,
            actor_email, context_json
        )
        VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12, $13,
            $14, $15, $16, $17, $18,
            $19, $20::jsonb
        )
        ON CONFLICT (workflow_run_id, phase_id, attempt_number, finding_fingerprint) DO UPDATE SET
            workflow_name = EXCLUDED.workflow_name,
            agent_name = EXCLUDED.agent_name,
            artifact_name = COALESCE(EXCLUDED.artifact_name, ops.workflow_findings.artifact_name),
            artifact_iteration = COALESCE(EXCLUDED.artifact_iteration, ops.workflow_findings.artifact_iteration),
            artifact_hash = COALESCE(EXCLUDED.artifact_hash, ops.workflow_findings.artifact_hash),
            finding_title = EXCLUDED.finding_title,
            finding_message = EXCLUDED.finding_message,
            location = COALESCE(EXCLUDED.location, ops.workflow_findings.location),
            evidence_text = COALESCE(EXCLUDED.evidence_text, ops.workflow_findings.evidence_text),
            finding_kind_id = EXCLUDED.finding_kind_id,
            severity = COALESCE(EXCLUDED.severity, ops.workflow_findings.severity),
            source_kind = COALESCE(EXCLUDED.source_kind, ops.workflow_findings.source_kind),
            status_id = EXCLUDED.status_id,
            actor_email = COALESCE(EXCLUDED.actor_email, ops.workflow_findings.actor_email),
            context_json = COALESCE(EXCLUDED.context_json, ops.workflow_findings.context_json),
            updated_utc = NOW()
        RETURNING id, phase_id, attempt_number, finding_fingerprint
        """,
        repository_id,
        workflow_run_id,
        workflow_name,
        phase_id,
        agent_name,
        attempt_number,
        artifact_name,
        artifact_iteration,
        artifact_hash,
        finding_fingerprint,
        finding_title,
        finding_message,
        location,
        evidence_text,
        finding_kind_id,
        severity,
        source_kind,
        status_id,
        actor_email,
        context_json,
    )
    return dict(row)


async def resolve_workflow_finding_id(
    pool: asyncpg.Pool,
    *,
    workflow_run_id: int,
    attempt_number: int,
    finding_fingerprint: str,
    finding_phase_id: str | None,
) -> int | None | str:
    rows = await pool.fetch(
        """
        SELECT id, phase_id
        FROM ops.workflow_findings
        WHERE workflow_run_id = $1
          AND attempt_number = $2
          AND finding_fingerprint = $3
          AND ($4::text IS NULL OR phase_id = $4)
        ORDER BY id ASC
        """,
        workflow_run_id,
        attempt_number,
        finding_fingerprint,
        finding_phase_id,
    )
    if not rows:
        return None
    if len(rows) > 1:
        return "ambiguous"
    return rows[0]["id"]


async def save_workflow_finding_decision(
    pool: asyncpg.Pool,
    *,
    repository_id: int,
    workflow_run_id: int,
    workflow_finding_id: int,
    workflow_name: str,
    critic_phase_id: str,
    critic_agent_name: str,
    attempt_number: int,
    finding_fingerprint: str,
    decision_bucket_id: int,
    actionable: bool,
    reason_text: str | None,
    evidence_text: str | None,
    suppression_scope_id: int,
    suppress_on_rerun: bool,
    artifact_name: str | None,
    artifact_iteration: int | None,
    artifact_hash: str | None,
    actor_email: str | None,
    context_json: str | None,
    created_utc: str | None,
) -> dict[str, Any] | None:
    return await pool.fetchrow(
        """
        INSERT INTO ops.workflow_finding_decisions (
            repository_id, workflow_run_id, workflow_finding_id, workflow_name,
            critic_phase_id, critic_agent_name, attempt_number, finding_fingerprint,
            decision_bucket_id, actionable, reason_text, evidence_text,
            suppression_scope_id, suppress_on_rerun, artifact_name, artifact_iteration,
            artifact_hash, actor_email, context_json, created_utc
        )
        VALUES (
            $1, $2, $3, $4,
            $5, $6, $7, $8,
            $9, $10, $11, $12,
            $13, $14, $15, $16,
            $17, $18, $19::jsonb, COALESCE($20::timestamptz, NOW())
        )
        ON CONFLICT (
            workflow_finding_id, critic_phase_id, critic_agent_name, attempt_number,
            decision_bucket_id, created_utc
        ) DO NOTHING
        RETURNING id, workflow_finding_id
        """,
        repository_id,
        workflow_run_id,
        workflow_finding_id,
        workflow_name,
        critic_phase_id,
        critic_agent_name,
        attempt_number,
        finding_fingerprint,
        decision_bucket_id,
        actionable,
        reason_text,
        evidence_text,
        suppression_scope_id,
        suppress_on_rerun,
        artifact_name,
        artifact_iteration,
        artifact_hash,
        actor_email,
        context_json,
        created_utc,
    )


async def list_workflow_finding_suppressions(
    pool: asyncpg.Pool,
    *,
    repository_id: int,
    workflow_run_id: int,
    workflow_name: str,
    phase_id: str,
    artifact_name: str | None,
    artifact_iteration: int | None,
    artifact_hash: str | None,
    limit: int,
) -> dict[str, Any]:
    rows = await pool.fetch(
        """
        WITH latest_decisions AS (
            SELECT DISTINCT ON (wf.finding_fingerprint)
                wf.finding_fingerprint,
                wfd.workflow_finding_id,
                rv.internal_code AS decision_bucket,
                wf.finding_title,
                wf.location,
                wfd.reason_text,
                wfd.suppress_on_rerun,
                wfd.artifact_name,
                wfd.artifact_iteration,
                wfd.artifact_hash,
                wfd.created_utc
            FROM ops.workflow_finding_decisions wfd
            JOIN ops.workflow_findings wf ON wf.id = wfd.workflow_finding_id
            JOIN core.reference_values rv ON rv.id = wfd.decision_bucket_id
            WHERE wfd.repository_id = $1
              AND wfd.workflow_run_id = $2
              AND wfd.workflow_name = $3
              AND wf.phase_id = $4
              AND ($5::text IS NULL OR wfd.artifact_name = $5)
              AND ($6::int IS NULL OR wfd.artifact_iteration = $6)
              AND ($7::text IS NULL OR wfd.artifact_hash = $7)
            ORDER BY wf.finding_fingerprint, wfd.created_utc DESC, wfd.id DESC
        )
        SELECT
            ld.finding_fingerprint,
            ld.finding_title,
            ld.location,
            ld.decision_bucket,
            ld.reason_text,
            ld.suppress_on_rerun,
            ld.artifact_name,
            ld.artifact_iteration,
            ld.artifact_hash,
            ld.created_utc
        FROM latest_decisions ld
        WHERE ld.suppress_on_rerun = TRUE
          AND ld.decision_bucket IN ('ACKNOWLEDGE_OK', 'DISMISS', 'FILTERED')
        ORDER BY ld.created_utc DESC NULLS LAST, ld.finding_fingerprint ASC
        LIMIT $8
        """,
        repository_id,
        workflow_run_id,
        workflow_name,
        phase_id,
        artifact_name,
        artifact_iteration,
        artifact_hash,
        limit,
    )
    items = [
        {
            "finding_fingerprint": row["finding_fingerprint"],
            "finding_title": row["finding_title"],
            "location": row["location"],
            "decision_bucket": row["decision_bucket"],
            "reason_text": row["reason_text"],
            "suppress_on_rerun": row["suppress_on_rerun"],
            "artifact_name": row["artifact_name"],
            "artifact_iteration": row["artifact_iteration"],
            "artifact_hash": row["artifact_hash"],
            "created_utc": _isoformat(row["created_utc"]),
        }
        for row in rows
    ]
    return {
        "items": items,
        "ordering": ["created_utc DESC", "finding_fingerprint ASC"],
        "filters": {
            "workflow_name": workflow_name,
            "phase_id": phase_id,
            "artifact_name": artifact_name,
            "artifact_iteration": artifact_iteration,
            "artifact_hash": artifact_hash,
        },
        "count": len(items),
    }


async def _fetch_finding_rows(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    workflow_name: str | None = None,
    phase_id: str | None = None,
    agent_name: str | None = None,
    finding_kind_code: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["r.repository_key = $1"]
    args: list[Any] = [repository_key]
    if workflow_name is not None:
        _append_clause(clauses, args, "wf.workflow_name = ${}", workflow_name)
    if phase_id is not None:
        _append_clause(clauses, args, "wf.phase_id = ${}", phase_id)
    if agent_name is not None:
        _append_clause(clauses, args, "wf.agent_name = ${}", agent_name)
    if finding_kind_code is not None:
        _append_clause(clauses, args, "fkind.internal_code = ${}", finding_kind_code)
    if since_utc is not None:
        _append_clause(clauses, args, "wf.created_utc >= ${}::timestamptz", since_utc)
    if until_utc is not None:
        _append_clause(clauses, args, "wf.created_utc <= ${}::timestamptz", until_utc)
    where_sql = " AND ".join(clauses)
    rows = await pool.fetch(
        f"""
        SELECT
            wf.id,
            wf.workflow_run_id,
            r.repository_key,
            wf.workflow_name,
            wf.phase_id,
            wf.agent_name,
            fkind.internal_code AS finding_kind,
            wf.finding_fingerprint,
            wf.finding_title,
            wf.location,
            wf.attempt_number,
            wf.created_utc,
            latest_decision.decision_bucket,
            latest_decision.actionable,
            latest_decision.reason_text
        FROM ops.workflow_findings wf
        JOIN catalog.repositories r ON r.id = wf.repository_id
        JOIN core.reference_values fkind ON fkind.id = wf.finding_kind_id
        LEFT JOIN LATERAL (
            SELECT
                rv.internal_code AS decision_bucket,
                wfd.actionable,
                wfd.reason_text
            FROM ops.workflow_finding_decisions wfd
            JOIN core.reference_values rv ON rv.id = wfd.decision_bucket_id
            WHERE wfd.workflow_finding_id = wf.id
            ORDER BY wfd.created_utc DESC, wfd.id DESC
            LIMIT 1
        ) latest_decision ON TRUE
        WHERE {where_sql}
        ORDER BY wf.created_utc DESC, wf.id DESC
        """,
        *args,
    )
    return [dict(row) for row in rows]


async def get_finding_pattern_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    workflow_name: str | None = None,
    phase_id: str | None = None,
    agent_name: str | None = None,
    finding_kind_code: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    rows = await _fetch_finding_rows(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        phase_id=phase_id,
        agent_name=agent_name,
        finding_kind_code=finding_kind_code,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    grouped: dict[tuple[str, str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["repository_key"], row["workflow_name"], row["finding_kind"], row["phase_id"])].append(row)

    summary: list[dict[str, Any]] = []
    for (repo_key, wf_name, kind, phase), items in grouped.items():
        summary.append(
            {
                "repository_key": repo_key,
                "workflow_name": wf_name,
                "finding_kind": kind,
                "agent_name": items[0]["agent_name"] if len({i["agent_name"] for i in items}) == 1 else "multiple",
                "phase_id": phase,
                "occurrence_count": len(items),
                "dismiss_count": sum(1 for i in items if i["decision_bucket"] == "DISMISS"),
                "acknowledge_count": sum(1 for i in items if i["decision_bucket"] == "ACKNOWLEDGE_OK"),
                "actionable_count": sum(1 for i in items if i["actionable"] is True),
                "top_fingerprints": _top_counts([i["finding_fingerprint"] for i in items], label_key="finding_fingerprint"),
                "top_locations": _top_counts([i["location"] for i in items], label_key="location"),
                "top_reason_texts": _top_counts([i["reason_text"] for i in items], label_key="reason_text"),
            }
        )
    summary.sort(key=lambda x: (x["repository_key"], x["workflow_name"], x["finding_kind"], x["phase_id"]))
    summary = summary[:limit]
    eligible = len({row["workflow_run_id"] for row in rows})
    return {
        "summary": summary,
        "ordering": ["repository_key", "workflow_name", "finding_kind", "phase_id"],
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "phase_id": phase_id,
            "agent_name": agent_name,
            "finding_kind_code": finding_kind_code,
            "since_utc": since_utc,
            "until_utc": until_utc,
            "limit": limit,
        },
        "coverage": {"historical_complete": False, "basis": "finding_persistence_adoption_only"},
        "eligible_run_count": eligible,
        "excluded_run_count": 0,
    }


async def get_agent_failure_mode_summary(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    workflow_name: str | None = None,
    phase_id: str | None = None,
    agent_name: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    rows = await _fetch_finding_rows(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        phase_id=phase_id,
        agent_name=agent_name,
        since_utc=since_utc,
        until_utc=until_utc,
    )
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["repository_key"],
                row["workflow_name"],
                row["agent_name"],
                row["finding_kind"],
                row["phase_id"],
            )
        ].append(row)

    summary: list[dict[str, Any]] = []
    for (repo_key, wf_name, agent, kind, phase), items in grouped.items():
        finding_count = len(items)
        distinct_fingerprint_count = len({i["finding_fingerprint"] for i in items})
        dismiss_count = sum(1 for i in items if i["decision_bucket"] == "DISMISS")
        actionable_count = sum(1 for i in items if i["actionable"] is True)
        latest_seen = max((i["created_utc"] for i in items if i["created_utc"] is not None), default=None)
        summary.append(
            {
                "repository_key": repo_key,
                "workflow_name": wf_name,
                "agent_name": agent,
                "finding_kind": kind,
                "phase_id": phase,
                "finding_count": finding_count,
                "distinct_fingerprint_count": distinct_fingerprint_count,
                "latest_seen_utc": _isoformat(latest_seen),
                "dismiss_count": dismiss_count,
                "acknowledge_count": sum(1 for i in items if i["decision_bucket"] == "ACKNOWLEDGE_OK"),
                "fix_now_count": sum(1 for i in items if i["decision_bucket"] in {"FIX_NOW", "FIX_NOW_PROMOTED"}),
                "critic_dismiss_rate": dismiss_count / finding_count if finding_count else 0.0,
                "critic_actionable_rate": actionable_count / finding_count if finding_count else 0.0,
                "repeat_rate": (finding_count - distinct_fingerprint_count) / finding_count if finding_count else 0.0,
                "top_examples": [
                    {"finding_fingerprint": item["finding_fingerprint"], "finding_title": item["finding_title"], "count": count}
                    for item, count in []
                ],
            }
        )
        examples = Counter((i["finding_fingerprint"], i["finding_title"]) for i in items)
        summary[-1]["top_examples"] = [
            {
                "finding_fingerprint": fingerprint,
                "finding_title": title,
                "count": count,
            }
            for (fingerprint, title), count in sorted(examples.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))[:5]
        ]

    summary.sort(key=lambda x: (x["repository_key"], x["workflow_name"], x["agent_name"], x["finding_kind"], x["phase_id"]))
    summary = summary[:limit]
    eligible = len({row["workflow_run_id"] for row in rows})
    return {
        "summary": summary,
        "ordering": ["repository_key", "workflow_name", "agent_name", "finding_kind", "phase_id"],
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "phase_id": phase_id,
            "agent_name": agent_name,
            "since_utc": since_utc,
            "until_utc": until_utc,
            "limit": limit,
        },
        "coverage": {"historical_complete": False, "basis": "finding_persistence_adoption_only"},
        "eligible_run_count": eligible,
        "excluded_run_count": 0,
    }
