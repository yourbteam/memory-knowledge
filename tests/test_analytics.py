from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memory_knowledge.admin import analytics


class AnalyticsPool:
    async def fetch(self, query, *args):
        if "FROM ops.workflow_runs wr" in query and "wr.id AS workflow_run_id" in query:
            return [
                {
                    "workflow_run_id": 1,
                    "run_id": "00000000-0000-0000-0000-000000000001",
                    "repository_key": "repo-a",
                    "workflow_name": "wf-a",
                    "actor_email": None,
                    "status_code": "RUN_SUCCESS",
                    "is_terminal": True,
                    "started_utc": datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
                    "completed_utc": datetime(2026, 4, 9, 10, 5, tzinfo=timezone.utc),
                    "iteration_count": 2,
                },
                {
                    "workflow_run_id": 2,
                    "run_id": "00000000-0000-0000-0000-000000000002",
                    "repository_key": "repo-a",
                    "workflow_name": "wf-a",
                    "actor_email": None,
                    "status_code": "RUN_ERROR",
                    "is_terminal": True,
                    "started_utc": datetime(2026, 4, 9, 11, 0, tzinfo=timezone.utc),
                    "completed_utc": None,
                    "iteration_count": 4,
                },
            ]
        if "FROM ops.workflow_phase_states wps" in query:
            return [
                {
                    "workflow_run_id": 1,
                    "run_id": "00000000-0000-0000-0000-000000000001",
                    "repository_key": "repo-a",
                    "workflow_name": "wf-a",
                    "phase_id": "validate",
                    "status": "success",
                    "status_bucket": "success",
                    "decision": "approve",
                    "attempts": 1,
                    "started_utc": datetime(2026, 4, 9, 10, 1, tzinfo=timezone.utc),
                    "completed_utc": datetime(2026, 4, 9, 10, 2, tzinfo=timezone.utc),
                    "error_text": None,
                },
                {
                    "workflow_run_id": 2,
                    "run_id": "00000000-0000-0000-0000-000000000002",
                    "repository_key": "repo-a",
                    "workflow_name": "wf-a",
                    "phase_id": "validate",
                    "status": "error",
                    "status_bucket": "error",
                    "decision": None,
                    "attempts": 3,
                    "started_utc": datetime(2026, 4, 9, 11, 1, tzinfo=timezone.utc),
                    "completed_utc": datetime(2026, 4, 9, 11, 2, tzinfo=timezone.utc),
                    "error_text": "bad output",
                },
            ]
        if "FROM ops.workflow_validator_results wvr" in query:
            return [
                {
                    "workflow_run_id": 1,
                    "run_id": "00000000-0000-0000-0000-000000000001",
                    "repository_key": "repo-a",
                    "workflow_name": "wf-a",
                    "phase_id": "validate",
                    "validator_code": "OUTPUT_CONTRACT",
                    "validator_name": "Output Contract",
                    "attempt_number": 1,
                    "status_code": "VAL_PASSED",
                    "failure_reason_code": None,
                    "failure_reason": None,
                    "created_utc": datetime(2026, 4, 9, 10, 2, tzinfo=timezone.utc),
                    "started_utc": datetime(2026, 4, 9, 10, 1, tzinfo=timezone.utc),
                    "completed_utc": datetime(2026, 4, 9, 10, 2, tzinfo=timezone.utc),
                },
                {
                    "workflow_run_id": 2,
                    "run_id": "00000000-0000-0000-0000-000000000002",
                    "repository_key": "repo-a",
                    "workflow_name": "wf-a",
                    "phase_id": "validate",
                    "validator_code": "OUTPUT_CONTRACT",
                    "validator_name": "Output Contract",
                    "attempt_number": 1,
                    "status_code": "VAL_FAILED",
                    "failure_reason_code": "FORMAT",
                    "failure_reason": "bad",
                    "created_utc": datetime(2026, 4, 9, 11, 2, tzinfo=timezone.utc),
                    "started_utc": datetime(2026, 4, 9, 11, 1, tzinfo=timezone.utc),
                    "completed_utc": datetime(2026, 4, 9, 11, 2, tzinfo=timezone.utc),
                },
            ]
        if "FROM ops.workflow_artifacts wa" in query:
            return [
                {
                    "workflow_run_id": 1,
                    "run_id": "00000000-0000-0000-0000-000000000001",
                    "repository_key": "repo-a",
                    "workflow_name": "wf-a",
                    "artifact_name": "analysis.md",
                    "iteration": 1,
                },
                {
                    "workflow_run_id": 2,
                    "run_id": "00000000-0000-0000-0000-000000000002",
                    "repository_key": "repo-a",
                    "workflow_name": "wf-a",
                    "artifact_name": "analysis.md",
                    "iteration": 2,
                },
            ]
        if "FROM planning.task_workflow_runs twr" in query:
            return [
                {
                    "workflow_run_id": 1,
                    "task_key": "task-1",
                    "task_title": "Task 1",
                    "feature_key": "feature-1",
                    "feature_title": "Feature 1",
                    "project_key": "project-1",
                    "project_name": "Project 1",
                }
            ]
        return []


@pytest.mark.asyncio
async def test_agent_performance_summary_uses_duration_denominator_and_unknown_actor_bucket():
    data = await analytics.get_agent_performance_summary(
        AnalyticsPool(),
        include_planning_context=True,
    )
    row = data["summary"][0]
    assert row["actor_email"] == "unknown"
    assert row["run_count"] == 2
    assert row["avg_duration_ms"] == 300000.0
    assert row["planning_context"]["tasks"][0]["task_key"] == "task-1"


@pytest.mark.asyncio
async def test_quality_grade_summary_uses_latest_run_grade_tiebreak_by_started_utc():
    data = await analytics.get_quality_grade_summary(AnalyticsPool())
    row = data["summary"][0]
    assert row["run_count"] == 2
    assert row["latest_run_grade"] == "F"
    assert row["grade_distribution"]["A"] == 1
    assert row["grade_distribution"]["F"] == 1


@pytest.mark.asyncio
async def test_entropy_targets_are_ordered_and_limited_after_bucketing():
    data = await analytics.list_entropy_sweep_targets(AnalyticsPool(), limit=1)
    assert len(data["targets"]) == 1
    row = data["targets"][0]
    assert row["score"] == 120
    assert row["reason_codes"] == [
        "LOW_GRADE",
        "RUN_ERROR",
        "HIGH_ITERATION_COUNT",
        "PHASE_RETRY_PRESSURE",
        "VALIDATOR_FAILED",
    ]


@pytest.mark.asyncio
async def test_loop_pattern_summary_normalizes_thresholds_and_phase_retry_counts():
    data = await analytics.get_loop_pattern_summary(
        AnalyticsPool(),
        loop_thresholds=[5, 3, 3],
    )
    row = data["summary"][0]
    assert row["threshold_counts"] == [
        {"threshold": 3, "run_count": 1},
        {"threshold": 5, "run_count": 0},
    ]
    assert row["phase_retry_counts"][0]["phase_id"] == "validate"
    assert row["phase_retry_counts"][0]["runs_with_attempts_ge_2"] == 1
    assert row["phase_retry_counts"][0]["max_attempts"] == 3
