from __future__ import annotations

from typing import Any

import asyncpg

from memory_knowledge.admin import analytics
from memory_knowledge.admin import findings
from memory_knowledge import triage_memory


def _confidence(case_count: int, severity_signal: float) -> float:
    evidence_factor = min(max(case_count, 0) / 5.0, 1.0)
    return round(min(1.0, 0.45 * evidence_factor + 0.55 * max(min(severity_signal, 1.0), 0.0)), 4)


def _append_playbook(
    items: list[dict[str, Any]],
    *,
    playbook_code: str,
    source_type: str,
    source_key: str,
    confidence: float,
    recommendation: str,
    suggested_actions: list[str],
    evidence: dict[str, Any],
) -> None:
    items.append(
        {
            "playbook_code": playbook_code,
            "source_type": source_type,
            "source_key": source_key,
            "confidence": round(confidence, 4),
            "recommendation": recommendation,
            "suggested_actions": suggested_actions,
            "evidence": evidence,
        }
    )


def _playbook_sort_key(item: dict[str, Any]) -> tuple[float, str, str]:
    return (
        float(item["confidence"]),
        str(item["playbook_code"]),
        str(item["source_key"]),
    )


async def get_failure_mode_playbooks(
    pool: asyncpg.Pool,
    *,
    repository_key: str,
    workflow_name: str | None = None,
    phase_id: str | None = None,
    agent_name: str | None = None,
    request_kind: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    convergence = await analytics.get_convergence_recommendation_summary(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        since_utc=since_utc,
        until_utc=until_utc,
        include_planning_context=False,
    )
    finding_patterns = await findings.get_finding_pattern_summary(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        phase_id=phase_id,
        agent_name=agent_name,
        since_utc=since_utc,
        until_utc=until_utc,
        limit=limit,
    )
    failure_modes = await findings.get_agent_failure_mode_summary(
        pool,
        repository_key=repository_key,
        workflow_name=workflow_name,
        phase_id=phase_id,
        agent_name=agent_name,
        since_utc=since_utc,
        until_utc=until_utc,
        limit=limit,
    )
    confusion = await triage_memory.get_triage_confusion_clusters(
        pool,
        repository_key=repository_key,
        request_kind=request_kind,
        selected_workflow_name=selected_workflow_name,
        selected_run_action=selected_run_action,
        lookback_days=30,
        limit=limit,
    )

    playbooks: list[dict[str, Any]] = []

    action_map = {
        "ADD_PRE_RETRY_GROUNDING": (
            "RERUN_RETRIEVAL_CONTEXT",
            "Add a grounding or retrieval refresh step before another retry.",
            ["rerun retrieval/context assembly", "tighten evidence requirements before retry"],
        ),
        "MOVE_VALIDATOR_EARLIER": (
            "MOVE_VALIDATOR_EARLIER",
            "Run the dominant failed validator earlier to catch bad output before additional churn.",
            ["move validator earlier in the workflow", "gate retry on validator pass"],
        ),
        "ADD_REPAIR_OR_CLARIFICATION_PHASE": (
            "INSERT_REPAIR_OR_CLARIFICATION_PHASE",
            "Insert an explicit repair or clarification phase before another retry.",
            ["add repair phase", "ask clarification questions before reroute"],
        ),
        "INSERT_CONVERGENCE_CHECKPOINT": (
            "INSERT_CONVERGENCE_CHECKPOINT",
            "Pause after the retry threshold and reassess the route or evidence set.",
            ["insert convergence checkpoint", "require intervention after retry threshold"],
        ),
        "STRENGTHEN_PHASE_ENTRY_CRITERIA": (
            "STRENGTHEN_PHASE_ENTRY_CRITERIA",
            "Strengthen phase-entry checks to avoid entering a high-churn phase under weak inputs.",
            ["add stronger preconditions", "block phase entry on missing context"],
        ),
        "ADD_PHASE_SPEC_OR_GUARDRAIL": (
            "ADD_PHASE_GUARDRAIL",
            "Add a stricter phase spec or guardrail for this repeated failure mode.",
            ["add phase spec", "add guardrail or template checks"],
        ),
        "ESCALATE_AFTER_THRESHOLD": (
            "ESCALATE_TO_OPERATOR_REVIEW",
            "Escalate to operator review after repeated failed attempts.",
            ["escalate to operator review", "stop automatic retries after threshold"],
        ),
        "RUN_ENTROPY_SWEEP": (
            "RUN_ENTROPY_SWEEP",
            "Run a broad entropy sweep to inspect low-grade repeated failures.",
            ["inspect low-grade runs", "cluster recurring failure reasons"],
        ),
        "HARDEN_VALIDATOR_EXECUTION": (
            "HARDEN_VALIDATOR_EXECUTION",
            "Harden validator execution reliability before depending on its output.",
            ["stabilize validator runtime", "improve validator error handling"],
        ),
    }

    for row in convergence["summary"]:
        primary = str(row.get("primary_recommendation") or "MONITOR")
        mapped = action_map.get(primary)
        if mapped is None:
            continue
        playbook_code, recommendation, suggested_actions = mapped
        reason_count = sum(int(item["count"]) for item in row.get("reason_counts", []))
        severity_signal = 0.0
        if row.get("latest_run_grade") in {"D", "F"}:
            severity_signal += 0.4
        if row.get("max_iteration_count", 0) >= 3:
            severity_signal += 0.3
        if row.get("dominant_failed_validator"):
            severity_signal += 0.2
        if row.get("dominant_retry_phase"):
            severity_signal += 0.1
        _append_playbook(
            playbooks,
            playbook_code=playbook_code,
            source_type="convergence",
            source_key="|".join([str(row.get("workflow_name") or ""), str(row.get("actor_email") or "")]),
            confidence=_confidence(int(row.get("run_count") or 0), severity_signal),
            recommendation=recommendation,
            suggested_actions=suggested_actions,
            evidence={
                "workflow_name": row.get("workflow_name"),
                "actor_email": row.get("actor_email"),
                "run_count": row.get("run_count"),
                "dominant_retry_phase": row.get("dominant_retry_phase"),
                "dominant_failed_validator": row.get("dominant_failed_validator"),
                "reason_count": reason_count,
            },
        )

    for row in confusion["clusters"]:
        if row.get("clarification_count", 0) <= 0:
            continue
        corrected_request_kind = row.get("corrected_request_kind")
        recommendation = "Ask for clarification before routing this request."
        suggested_actions = ["request clarification", "collect missing workflow inputs"]
        playbook_code = "REQUEST_CLARIFICATION"
        if corrected_request_kind and corrected_request_kind != row.get("request_kind"):
            recommendation = "Escalate to planning-first triage before selecting a workflow."
            suggested_actions = ["escalate to planning-first", "reclassify request kind before routing"]
            playbook_code = "ESCALATE_TO_PLANNING_FIRST"
        _append_playbook(
            playbooks,
            playbook_code=playbook_code,
            source_type="triage_confusion",
            source_key=row.get("cluster_key") or "",
            confidence=_confidence(
                int(row.get("case_count") or 0),
                min(1.0, float(row.get("clarification_count") or 0) / max(int(row.get("case_count") or 1), 1)),
            ),
            recommendation=recommendation,
            suggested_actions=suggested_actions,
            evidence={
                "request_kind": row.get("request_kind"),
                "selected_workflow_name": row.get("selected_workflow_name"),
                "selected_run_action": row.get("selected_run_action"),
                "corrected_request_kind": corrected_request_kind,
                "case_count": row.get("case_count"),
                "clarification_count": row.get("clarification_count"),
            },
        )

    for row in finding_patterns["summary"]:
        occurrence_count = int(row.get("occurrence_count") or 0)
        dismiss_count = int(row.get("dismiss_count") or 0)
        actionable_count = int(row.get("actionable_count") or 0)
        if occurrence_count <= 0:
            continue
        dismiss_rate = dismiss_count / occurrence_count
        actionable_rate = actionable_count / occurrence_count
        if dismiss_rate >= 0.5:
            _append_playbook(
                playbooks,
                playbook_code="SUPPRESS_LOW_VALUE_NOISE",
                source_type="finding_pattern",
                source_key="|".join([str(row.get("workflow_name") or ""), str(row.get("finding_kind") or ""), str(row.get("phase_id") or "")]),
                confidence=_confidence(occurrence_count, dismiss_rate),
                recommendation="Suppress or filter repeated low-value findings for this pattern.",
                suggested_actions=["suppress low-value noise", "tighten critic filtering for this pattern"],
                evidence={
                    "workflow_name": row.get("workflow_name"),
                    "finding_kind": row.get("finding_kind"),
                    "phase_id": row.get("phase_id"),
                    "occurrence_count": occurrence_count,
                    "dismiss_count": dismiss_count,
                    "actionable_count": actionable_count,
                },
            )
        elif actionable_rate >= 0.5:
            _append_playbook(
                playbooks,
                playbook_code="ESCALATE_TO_OPERATOR_REVIEW",
                source_type="finding_pattern",
                source_key="|".join([str(row.get("workflow_name") or ""), str(row.get("finding_kind") or ""), str(row.get("phase_id") or "")]),
                confidence=_confidence(occurrence_count, actionable_rate),
                recommendation="Escalate this repeated actionable finding pattern for direct operator or workflow-owner review.",
                suggested_actions=["escalate to operator review", "promote to workflow hardening task"],
                evidence={
                    "workflow_name": row.get("workflow_name"),
                    "finding_kind": row.get("finding_kind"),
                    "phase_id": row.get("phase_id"),
                    "occurrence_count": occurrence_count,
                    "actionable_count": actionable_count,
                },
            )

    for row in failure_modes["summary"]:
        repeat_rate = float(row.get("repeat_rate") or 0.0)
        actionable_rate = float(row.get("critic_actionable_rate") or 0.0)
        finding_count = int(row.get("finding_count") or 0)
        if repeat_rate >= 0.3 and actionable_rate >= 0.4:
            _append_playbook(
                playbooks,
                playbook_code="ADD_PHASE_GUARDRAIL",
                source_type="agent_failure_mode",
                source_key="|".join(
                    [
                        str(row.get("workflow_name") or ""),
                        str(row.get("agent_name") or ""),
                        str(row.get("finding_kind") or ""),
                        str(row.get("phase_id") or ""),
                    ]
                ),
                confidence=_confidence(finding_count, min(1.0, (repeat_rate + actionable_rate) / 2.0)),
                recommendation="Add a reusable guardrail or template for this repeated agent failure mode.",
                suggested_actions=["add agent guardrail", "add reusable prompt/spec template"],
                evidence={
                    "workflow_name": row.get("workflow_name"),
                    "agent_name": row.get("agent_name"),
                    "finding_kind": row.get("finding_kind"),
                    "phase_id": row.get("phase_id"),
                    "finding_count": finding_count,
                    "repeat_rate": repeat_rate,
                    "critic_actionable_rate": actionable_rate,
                },
            )

    playbooks.sort(key=_playbook_sort_key, reverse=True)
    return {
        "playbooks": playbooks[:limit],
        "ordering": ["confidence DESC", "playbook_code ASC", "source_key ASC"],
        "filters": {
            "repository_key": repository_key,
            "workflow_name": workflow_name,
            "phase_id": phase_id,
            "agent_name": agent_name,
            "request_kind": request_kind,
            "selected_workflow_name": selected_workflow_name,
            "selected_run_action": selected_run_action,
            "since_utc": since_utc,
            "until_utc": until_utc,
            "limit": limit,
        },
        "source_counts": {
            "convergence": len(convergence["summary"]),
            "finding_patterns": len(finding_patterns["summary"]),
            "agent_failure_modes": len(failure_modes["summary"]),
            "triage_confusion_clusters": len(confusion["clusters"]),
        },
        "count": len(playbooks[:limit]),
    }
