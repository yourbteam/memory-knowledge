from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import uuid
from contextlib import asynccontextmanager

import structlog
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP

from memory_knowledge.config import Settings, init_settings, get_settings
from memory_knowledge.db.health import health_check, readiness_check
from memory_knowledge.db.neo4j import apply_constraints, close_neo4j, init_neo4j
from memory_knowledge.db.postgres import close_postgres, init_postgres
from memory_knowledge.db.qdrant import close_qdrant, ensure_collections, init_qdrant
from memory_knowledge.observability.logging import configure_logging
from memory_knowledge.observability.metrics import track_tool_metrics
from memory_knowledge.guards import check_remote_write_guard
from memory_knowledge.workflows.base import WorkflowResult
from memory_knowledge.admin import analytics as _analytics
from memory_knowledge.admin import actor_adaptation as _actor_adaptation
from memory_knowledge.admin import findings as _findings
from memory_knowledge.admin import intake as _intake
from memory_knowledge.admin import playbooks as _playbooks
from memory_knowledge.admin import planning as _planning
from memory_knowledge import triage_memory as _triage_memory
from memory_knowledge import triage_policy as _triage_policy
from memory_knowledge.observability.run_context import (
    bind_run_context,
    clear_run_context,
    new_run_id,
)
from memory_knowledge.db.postgres import get_pg_pool
from memory_knowledge.db.qdrant import get_qdrant_client
from memory_knowledge.db.neo4j import get_neo4j_driver
from memory_knowledge.workflows import retrieval as _retrieval
from memory_knowledge.workflows import context_assembly as _context_assembly
from memory_knowledge.workflows import impact_analysis as _impact_analysis
from memory_knowledge.workflows import learned_memory as _learned_memory
from memory_knowledge.workflows import blueprint_refinement as _blueprint_refinement
from memory_knowledge.workflows import ingestion as _ingestion
from memory_knowledge.workflows import integrity_audit as _integrity_audit
from memory_knowledge.workflows import repair_rebuild as _repair_rebuild
from memory_knowledge.workflows import route_intelligence as _route_intelligence

logger = structlog.get_logger()

WORKFLOW_RUN_STATUS_TYPE = "WORKFLOW_RUN_STATUS"
WORKFLOW_VALIDATOR_STATUS_TYPE = "WORKFLOW_VALIDATOR_STATUS"
WORKFLOW_FINDING_KIND_TYPE = "WORKFLOW_FINDING_KIND"
WORKFLOW_FINDING_DECISION_BUCKET_TYPE = "WORKFLOW_FINDING_DECISION_BUCKET"
WORKFLOW_FINDING_SUPPRESSION_SCOPE_TYPE = "WORKFLOW_FINDING_SUPPRESSION_SCOPE"
WORKFLOW_FINDING_STATUS_TYPE = "WORKFLOW_FINDING_STATUS"
DEFAULT_WORKFLOW_RUN_STATUS = "RUN_PENDING"
DEFAULT_WORKFLOW_FINDING_KIND = "UNKNOWN"
DEFAULT_WORKFLOW_FINDING_STATUS = "OPEN"
DEFAULT_WORKFLOW_FINDING_SUPPRESSION_SCOPE = "RUN_LOCAL"
VALIDATOR_CODE_SET = {
    "OUTPUT_CONTRACT",
    "EVIDENCE_GROUNDING",
    "MEMORY_PROPOSAL",
}
PHASE_STATUS_SET = {
    "pending",
    "running",
    "success",
    "error",
    "cancelled",
}
LEGACY_WORKFLOW_RUN_STATUS_MAP = {
    "pending": "RUN_PENDING",
    "submitted": "RUN_SUBMITTED",
    "running": "RUN_RUNNING",
    "success": "RUN_SUCCESS",
    "completed": "RUN_SUCCESS",
    "partial": "RUN_PARTIAL",
    "error": "RUN_ERROR",
    "failed": "RUN_ERROR",
    "cancelled": "RUN_CANCELLED",
}
WORKFLOW_RUN_STATUS_LEGACY_NAMES = {
    "RUN_PENDING": "pending",
    "RUN_SUBMITTED": "submitted",
    "RUN_RUNNING": "running",
    "RUN_SUCCESS": "success",
    "RUN_PARTIAL": "partial",
    "RUN_ERROR": "error",
    "RUN_CANCELLED": "cancelled",
}

# MCP server instance — tools are registered on this via @mcp.tool()
# streamable_http_path="/" so the endpoint is at /mcp/ (not /mcp/mcp)
# transport_security disabled to allow non-localhost hosts (Azure, etc.)
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "memory-knowledge",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _intake_result_json(run_id: uuid.UUID, tool_name: str, data: dict) -> str:
    if data.get("ok") is False:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=tool_name,
            status="error",
            error=data.get("error"),
            data=data,
        ).model_dump_json()
    return WorkflowResult(
        run_id=str(run_id),
        tool_name=tool_name,
        status="success",
        data=data,
    ).model_dump_json()


# ---------------------------------------------------------------------------
# MCP Tool registrations
# ---------------------------------------------------------------------------


@mcp.tool()
@track_tool_metrics("run_retrieval_workflow")
async def run_retrieval_workflow(
    repository_key: str, query: str, correlation_id: str | None = None
) -> str:
    """Retrieve evidence from the memory architecture for a given query."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_retrieval_workflow")
    try:
        result = await _retrieval.run(
            repository_key, query, run_id,
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            settings=get_settings(),
        )
        return result.model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("run_context_assembly_workflow")
async def run_context_assembly_workflow(
    repository_key: str, query: str, correlation_id: str | None = None
) -> str:
    """Build a normalized evidence package from retrieved results."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_context_assembly_workflow")
    try:
        result = await _context_assembly.run(
            repository_key, query, run_id,
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            settings=get_settings(),
        )
        return result.model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("run_impact_analysis_workflow")
async def run_impact_analysis_workflow(
    repository_key: str, query: str, correlation_id: str | None = None
) -> str:
    """Determine what a proposed change affects via graph traversal."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_impact_analysis_workflow")
    try:
        result = await _impact_analysis.run(
            repository_key, query, run_id,
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            settings=get_settings(),
        )
        return result.model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("run_learned_memory_proposal_workflow")
async def run_learned_memory_proposal_workflow(
    repository_key: str,
    memory_type: str,
    title: str,
    body_text: str,
    evidence_entity_key: str,
    scope_entity_key: str,
    confidence: float = 0.5,
    applicability_mode: str = "repository",
    correlation_id: str | None = None,
) -> str:
    """Propose a learned-memory candidate backed by evidence."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_learned_memory_proposal_workflow")
    guard = check_remote_write_guard(get_settings(), "run_learned_memory_proposal_workflow")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        result = await _learned_memory.run_proposal(
            repository_key=repository_key,
            memory_type=memory_type,
            title=title,
            body_text=body_text,
            evidence_entity_key=evidence_entity_key,
            scope_entity_key=scope_entity_key,
            confidence=confidence,
            applicability_mode=applicability_mode,
            run_id=run_id,
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            settings=get_settings(),
        )
        return result.model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("run_learned_memory_commit_workflow")
async def run_learned_memory_commit_workflow(
    repository_key: str,
    proposal_id: str,
    approval_status: str,
    verification_notes: str | None = None,
    supersedes_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Approve, reject, or supersede a learned-memory proposal."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_learned_memory_commit_workflow")
    guard = check_remote_write_guard(get_settings(), "run_learned_memory_commit_workflow")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        result = await _learned_memory.run_commit(
            repository_key=repository_key,
            proposal_id=proposal_id,
            approval_status=approval_status,
            verification_notes=verification_notes,
            supersedes_id=supersedes_id,
            run_id=run_id,
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            settings=get_settings(),
        )
        return result.model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("run_blueprint_refinement_workflow")
async def run_blueprint_refinement_workflow(
    repository_key: str, query: str, correlation_id: str | None = None
) -> str:
    """Support iterative refinement of blueprint artifacts."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_blueprint_refinement_workflow")
    try:
        result = await _blueprint_refinement.run(
            repository_key, query, run_id,
            settings=get_settings(),
        )
        return result.model_dump_json()
    finally:
        clear_run_context()


# Background task tracking for graceful shutdown
_background_tasks: set[asyncio.Task] = set()


def _get_optional_neo4j_driver():
    """Return the Neo4j driver when available, otherwise degrade gracefully."""
    try:
        return get_neo4j_driver()
    except RuntimeError as exc:
        logger.warning("neo4j_driver_unavailable", error=str(exc))
        return None


async def _run_ingestion_background(
    job_id: uuid.UUID, run_id: uuid.UUID,
    repository_key: str, commit_sha: str, branch_name: str,
    checkpoint: dict | None = None,
) -> None:
    """Background task for ingestion job execution."""
    from memory_knowledge.jobs.job_worker import execute_job

    # execute_job uses its own pool/settings for manifest writes.
    # The workflow's pool/qdrant/neo4j/settings are passed via **kwargs.
    pool = get_pg_pool()
    settings = get_settings()
    await execute_job(
        manifest_pool=pool,
        job_id=job_id,
        job_fn=_ingestion.run,
        worker_settings=settings,
        # These kwargs are forwarded to _ingestion.run()
        repository_key=repository_key,
        commit_sha=commit_sha,
        branch_name=branch_name,
        run_id=run_id,
        manifest_job_id=job_id,
        checkpoint=checkpoint,
        pool=pool,
        qdrant_client=get_qdrant_client(),
        neo4j_driver=_get_optional_neo4j_driver(),
        settings=settings,
    )


async def _run_repair_background(
    job_id: uuid.UUID, run_id: uuid.UUID,
    repository_key: str, repair_scope: str,
) -> None:
    """Background task for repair job execution."""
    from memory_knowledge.jobs.job_worker import execute_job

    pool = get_pg_pool()
    settings = get_settings()
    await execute_job(
        manifest_pool=pool,
        job_id=job_id,
        job_fn=_repair_rebuild.run,
        worker_settings=settings,
        repository_key=repository_key,
        run_id=run_id,
        repair_scope=repair_scope,
        pool=pool,
        qdrant_client=get_qdrant_client(),
        neo4j_driver=_get_optional_neo4j_driver(),
        settings=settings,
    )


async def _run_integrity_background(
    job_id: uuid.UUID, run_id: uuid.UUID,
    repository_key: str,
) -> None:
    """Background task for integrity audit job execution."""
    from memory_knowledge.jobs.job_worker import execute_job

    pool = get_pg_pool()
    settings = get_settings()
    await execute_job(
        manifest_pool=pool,
        job_id=job_id,
        job_fn=_integrity_audit.run,
        worker_settings=settings,
        repository_key=repository_key,
        run_id=run_id,
        pool=pool,
        qdrant_client=get_qdrant_client(),
        neo4j_driver=_get_optional_neo4j_driver(),
        settings=settings,
    )


def _on_task_done(task: asyncio.Task) -> None:
    """Remove task from tracking set and log any unhandled exceptions."""
    from memory_knowledge.observability.error_detail import format_exception_detail

    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        logger.error("background_task_failed", error=format_exception_detail(task.exception()))


def _track_task(task: asyncio.Task) -> None:
    """Add task to tracking set, remove on completion."""
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)


@mcp.tool()
@track_tool_metrics("run_repo_ingestion_workflow")
async def run_repo_ingestion_workflow(
    repository_key: str,
    commit_sha: str,
    branch_name: str,
    correlation_id: str | None = None,
) -> str:
    """Seed or refresh repository knowledge from a commit. Returns job_id for polling."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_repo_ingestion_workflow")
    guard = check_remote_write_guard(get_settings(), "run_repo_ingestion_workflow")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        from memory_knowledge.jobs.manifest_writer import create_job
        from memory_knowledge.jobs.manifest_reader import (
            get_active_job_for_shape,
            get_latest_resume_checkpoint,
        )

        pool = get_pg_pool()
        active_job = await get_active_job_for_shape(
            pool,
            repository_key=repository_key,
            commit_sha=commit_sha,
            branch_name=branch_name,
            tool_name="run_repo_ingestion_workflow",
        )
        if active_job is not None:
            active_job_id = str(active_job["job_id"])
            logger.info(
                "ingestion_job_already_active",
                repository_key=repository_key,
                commit_sha=commit_sha,
                branch_name=branch_name,
                job_id=active_job_id,
            )
            return WorkflowResult(
                run_id=str(run_id),
                tool_name="run_repo_ingestion_workflow",
                status="submitted",
                data={
                    "job_id": active_job_id,
                    "existing": True,
                    "state_code": active_job.get("state_code"),
                },
            ).model_dump_json()

        resume_checkpoint = await get_latest_resume_checkpoint(
            pool,
            repository_key=repository_key,
            commit_sha=commit_sha,
            branch_name=branch_name,
            tool_name="run_repo_ingestion_workflow",
        )
        job_id = await create_job(
            pool, run_id, "ingestion", "run_repo_ingestion_workflow",
            repository_key,
            commit_sha,
            branch_name,
            str(correlation_id) if correlation_id else None,
            job_params={"checkpoint": resume_checkpoint} if resume_checkpoint else None,
        )
        task = asyncio.create_task(
            _run_ingestion_background(
                job_id,
                run_id,
                repository_key,
                commit_sha,
                branch_name,
                checkpoint=resume_checkpoint,
            )
        )
        _track_task(task)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_repo_ingestion_workflow",
            status="submitted",
            data={"job_id": str(job_id)},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("run_integrity_audit_workflow")
async def run_integrity_audit_workflow(
    repository_key: str, correlation_id: str | None = None
) -> str:
    """Check mechanical layer trustworthiness across stores. Returns job_id for polling."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_integrity_audit_workflow")
    guard = check_remote_write_guard(get_settings(), "run_integrity_audit_workflow")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        from memory_knowledge.jobs.manifest_writer import create_job

        pool = get_pg_pool()
        job_id = await create_job(
            pool, run_id, "integrity_audit", "run_integrity_audit_workflow",
            repository_key, correlation_id=str(correlation_id) if correlation_id else None,
        )
        task = asyncio.create_task(
            _run_integrity_background(job_id, run_id, repository_key)
        )
        _track_task(task)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_integrity_audit_workflow",
            status="submitted",
            data={"job_id": str(job_id)},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("run_repair_rebuild_workflow")
async def run_repair_rebuild_workflow(
    repository_key: str,
    repair_scope: str = "full",
    correlation_id: str | None = None,
) -> str:
    """Repair drift or rebuild a memory slice. Returns job_id for polling. Scope: full, qdrant, or neo4j."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_repair_rebuild_workflow")
    guard = check_remote_write_guard(get_settings(), "run_repair_rebuild_workflow", is_destructive=True)
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        from memory_knowledge.jobs.manifest_writer import create_job

        pool = get_pg_pool()
        job_id = await create_job(
            pool, run_id, "repair", "run_repair_rebuild_workflow",
            repository_key, correlation_id=str(correlation_id) if correlation_id else None,
        )
        task = asyncio.create_task(
            _run_repair_background(job_id, run_id, repository_key, repair_scope)
        )
        _track_task(task)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_repair_rebuild_workflow",
            status="submitted",
            data={"job_id": str(job_id)},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("check_job_status")
async def check_job_status(
    job_id: str, correlation_id: str | None = None
) -> str:
    """Check the current status of a background job. Returns manifest state + result data."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "check_job_status")
    try:
        from memory_knowledge.jobs.manifest_reader import get_job_by_id

        job = await get_job_by_id(get_pg_pool(), uuid.UUID(job_id))
        if job is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name="check_job_status",
                status="error",
                error=f"Job not found: {job_id}",
            ).model_dump_json()
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="check_job_status",
            status="success",
            data=job,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_memory_stats")
async def get_memory_stats(
    repository_key: str, correlation_id: str | None = None
) -> str:
    """Get comprehensive statistics about the memory architecture for a repository."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "get_memory_stats")
    try:
        from memory_knowledge.admin.memory_stats import collect_memory_stats

        stats = await collect_memory_stats(
            get_pg_pool(), get_qdrant_client(), get_neo4j_driver(), repository_key
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="get_memory_stats",
            status="success",
            data=stats,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_repositories")
async def list_repositories(correlation_id: str | None = None) -> str:
    """List all registered repositories with their latest ingestion state."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "list_repositories")
    try:
        pool = get_pg_pool()
        rows = await pool.fetch(
            """
            SELECT
                r.repository_key,
                r.name,
                r.origin_url,
                r.created_utc,
                r.updated_utc,
                bh.branch_name   AS latest_branch,
                rv.commit_sha    AS latest_commit,
                rv.committed_utc AS latest_commit_utc,
                COALESCE(ec.file_count, 0)    AS file_count,
                COALESCE(ec.symbol_count, 0)  AS symbol_count,
                COALESCE(ec.chunk_count, 0)   AS chunk_count,
                ir.status         AS last_ingestion_status,
                ir.completed_utc  AS last_ingestion_utc
            FROM catalog.repositories r
            LEFT JOIN LATERAL (
                SELECT bh2.branch_name, bh2.repo_revision_id
                FROM catalog.branch_heads bh2
                WHERE bh2.repository_id = r.id
                ORDER BY bh2.updated_utc DESC LIMIT 1
            ) bh ON TRUE
            LEFT JOIN catalog.repo_revisions rv ON rv.id = bh.repo_revision_id
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE e2.entity_type = 'file')   AS file_count,
                    COUNT(*) FILTER (WHERE e2.entity_type = 'symbol') AS symbol_count,
                    COUNT(*) FILTER (WHERE e2.entity_type = 'chunk')  AS chunk_count
                FROM catalog.entities e2
                WHERE e2.repository_id = r.id
            ) ec ON TRUE
            LEFT JOIN LATERAL (
                SELECT ir2.status, ir2.completed_utc
                FROM ops.ingestion_runs ir2
                WHERE ir2.repository_id = r.id
                ORDER BY ir2.id DESC LIMIT 1
            ) ir ON TRUE
            ORDER BY r.name
            """
        )
        repos = []
        for row in rows:
            repos.append({
                "repository_key": row["repository_key"],
                "name": row["name"],
                "origin_url": row["origin_url"],
                "latest_branch": row["latest_branch"],
                "latest_commit": row["latest_commit"],
                "latest_commit_utc": row["latest_commit_utc"].isoformat() if row["latest_commit_utc"] else None,
                "file_count": row["file_count"],
                "symbol_count": row["symbol_count"],
                "chunk_count": row["chunk_count"],
                "last_ingestion_status": row["last_ingestion_status"],
                "last_ingestion_utc": row["last_ingestion_utc"].isoformat() if row["last_ingestion_utc"] else None,
            })
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_repositories",
            status="success",
            data={"repositories": repos, "count": len(repos)},
        ).model_dump_json()
    finally:
        clear_run_context()


# ---------------------------------------------------------------------------
# Workflow tracking tools
# ---------------------------------------------------------------------------


async def _resolve_reference_type_id(pool, internal_code: str) -> int | None:
    row = await pool.fetchrow(
        "SELECT id FROM core.reference_types WHERE internal_code = $1",
        internal_code,
    )
    return row["id"] if row else None


async def _resolve_reference_value(pool, type_code: str, value_code: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT rv.id, rv.internal_code, rv.display_name, rv.is_terminal
        FROM core.reference_values rv
        JOIN core.reference_types rt ON rt.id = rv.reference_type_id
        WHERE rt.internal_code = $1 AND rv.internal_code = $2
        """,
        type_code,
        value_code,
    )
    return dict(row) if row else None


async def _resolve_workflow_run_status(pool, status_code: str | None) -> dict | None:
    if status_code is None:
        return None
    code = LEGACY_WORKFLOW_RUN_STATUS_MAP.get(status_code, status_code)
    return await _resolve_reference_value(pool, WORKFLOW_RUN_STATUS_TYPE, code)


async def _require_reference_value(
    pool,
    type_code: str,
    value_code: str,
    tool_name: str,
    run_id: uuid.UUID,
) -> dict | str:
    row = await _resolve_reference_value(pool, type_code, value_code)
    if row is None:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=tool_name,
            status="error",
            error=f"Invalid {type_code} value: {value_code}",
        ).model_dump_json()
    return row


def _legacy_workflow_run_status_name(status_code: str) -> str:
    return WORKFLOW_RUN_STATUS_LEGACY_NAMES.get(status_code, status_code.lower())


def _isoformat(value) -> str | None:
    return value.isoformat() if value else None


def _is_valid_timestamp(value: str | None) -> bool:
    if value is None:
        return True
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


async def _resolve_workflow_run_row(pool, run_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT wr.id, wr.repository_id, wr.run_id
        FROM ops.workflow_runs wr
        WHERE wr.run_id = $1
        """,
        uuid.UUID(run_id),
    )
    return dict(row) if row else None


async def _resolve_project_identifier(
    pool,
    *,
    project_key: str | None,
    project_external_system: str | None,
    project_external_id: str | None,
) -> int:
    if project_key is not None:
        project_id = await _planning.resolve_project_id(pool, project_key)
        if project_external_system and project_external_id:
            ext_id = await _planning.resolve_project_id_by_external(pool, project_external_system, project_external_id)
            if ext_id != project_id:
                raise ValueError("project_key and external project reference resolve to different projects")
        return project_id
    if project_external_system and project_external_id:
        return await _planning.resolve_project_id_by_external(pool, project_external_system, project_external_id)
    raise ValueError("project_key or project external reference is required")


async def _resolve_feature_identifier(
    pool,
    *,
    feature_key: str | None,
    feature_external_system: str | None,
    feature_external_id: str | None,
) -> dict[str, int] | None:
    if feature_key is None and not (feature_external_system and feature_external_id):
        return None
    if feature_key is not None:
        ctx = await _planning.resolve_feature_context(pool, feature_key)
        if feature_external_system and feature_external_id:
            ext_ctx = await _planning.resolve_feature_context_by_external(pool, feature_external_system, feature_external_id)
            if ext_ctx != ctx:
                raise ValueError("feature_key and external feature reference resolve to different features")
        return ctx
    return await _planning.resolve_feature_context_by_external(pool, feature_external_system, feature_external_id)


@mcp.tool()
@track_tool_metrics("save_workflow_run")
async def save_workflow_run(
    repository_key: str,
    run_id: str,
    workflow_name: str | None = None,
    task_description: str | None = None,
    status: str | None = None,
    status_code: str | None = None,
    actor_email: str | None = None,
    current_phase: str | None = None,
    iteration_count: int | None = None,
    context_json: dict | None = None,
    error_text: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Create or update a workflow run record. Upserts on run_id."""
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "save_workflow_run")
    guard = check_remote_write_guard(get_settings(), "save_workflow_run")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        import json as _json
        pool = get_pg_pool()
        # Resolve repository_key → repository_id
        repo_row = await pool.fetchrow(
            "SELECT id FROM catalog.repositories WHERE repository_key = $1",
            repository_key,
        )
        if not repo_row:
            return WorkflowResult(
                run_id=str(rid), tool_name="save_workflow_run",
                status="error", error=f"Repository '{repository_key}' not found",
            ).model_dump_json()
        repo_id = repo_row["id"]
        if isinstance(context_json, str):
            ctx = _json.loads(context_json) if context_json else None
        else:
            ctx = context_json
        existing_run_row = await pool.fetchrow(
            "SELECT workflow_name FROM ops.workflow_runs WHERE run_id = $1",
            uuid.UUID(run_id),
        )
        effective_workflow_name = workflow_name or (
            existing_run_row["workflow_name"] if existing_run_row else None
        )
        if effective_workflow_name is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_run",
                status="error",
                error="workflow_name is required on first workflow-run write",
            ).model_dump_json()
        effective_status_code = status_code or status
        status_row = await _resolve_workflow_run_status(pool, effective_status_code)
        if effective_status_code is not None and status_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_run",
                status="error",
                error=f"Invalid workflow run status or status_code: {effective_status_code}",
            ).model_dump_json()
        default_status_row = await _resolve_workflow_run_status(pool, DEFAULT_WORKFLOW_RUN_STATUS)
        if default_status_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_run",
                status="error",
                error=f"Default workflow run status not found: {DEFAULT_WORKFLOW_RUN_STATUS}",
            ).model_dump_json()

        row = await pool.fetchrow(
            """
            INSERT INTO ops.workflow_runs
                (run_id, repository_id, workflow_name, task_description,
                 status_id, actor_email, current_phase, iteration_count,
                 context_json, error_text, correlation_id)
            VALUES ($1, $2, $3, $4, COALESCE($5::bigint, $13::bigint), $6, $7,
                    COALESCE($8, 0), $9, $10, $11::uuid)
            ON CONFLICT (run_id) DO UPDATE SET
                workflow_name   = COALESCE(EXCLUDED.workflow_name, ops.workflow_runs.workflow_name),
                task_description = COALESCE(EXCLUDED.task_description, ops.workflow_runs.task_description),
                status_id       = COALESCE(EXCLUDED.status_id, ops.workflow_runs.status_id),
                actor_email     = COALESCE(EXCLUDED.actor_email, ops.workflow_runs.actor_email),
                current_phase   = COALESCE(EXCLUDED.current_phase, ops.workflow_runs.current_phase),
                iteration_count = COALESCE(EXCLUDED.iteration_count, ops.workflow_runs.iteration_count),
                context_json    = COALESCE(EXCLUDED.context_json, ops.workflow_runs.context_json),
                error_text      = COALESCE(EXCLUDED.error_text, ops.workflow_runs.error_text),
                completed_utc   = CASE
                    WHEN $5 IS NULL THEN ops.workflow_runs.completed_utc
                    WHEN $12 THEN NOW()
                    ELSE ops.workflow_runs.completed_utc
                END
            RETURNING id, (xmax = 0) AS is_insert, status_id
            """,
            uuid.UUID(run_id), repo_id, effective_workflow_name, task_description,
            status_row["id"] if status_row else None,
            actor_email, current_phase, iteration_count,
            _json.dumps(ctx) if ctx else None,
            error_text,
            correlation_id,
            status_row["is_terminal"] if status_row else False,
            default_status_row["id"],
        )
        persisted_status = status_row or default_status_row
        return WorkflowResult(
            run_id=str(rid), tool_name="save_workflow_run", status="success",
            data={
                "run_id": run_id,
                "status": _legacy_workflow_run_status_name(persisted_status["internal_code"]),
                "status_code": persisted_status["internal_code"],
                "status_display_name": persisted_status["display_name"],
                "is_terminal": persisted_status["is_terminal"],
                "created": row["is_insert"],
            },
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("save_workflow_artifact")
async def save_workflow_artifact(
    run_id: str,
    artifact_name: str,
    artifact_type: str,
    content_text: str,
    phase_id: str | None = None,
    iteration: int = 1,
    is_final: bool = False,
    correlation_id: str | None = None,
) -> str:
    """Upsert an artifact for a workflow run. Updates in place on (run_id, artifact_name)."""
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "save_workflow_artifact")
    guard = check_remote_write_guard(get_settings(), "save_workflow_artifact")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        # Resolve run_id → workflow_run_id
        wr = await pool.fetchrow(
            "SELECT id FROM ops.workflow_runs WHERE run_id = $1",
            uuid.UUID(run_id),
        )
        if not wr:
            return WorkflowResult(
                run_id=str(rid), tool_name="save_workflow_artifact",
                status="error", error=f"Workflow run '{run_id}' not found",
            ).model_dump_json()
        wf_id = wr["id"]

        row = await pool.fetchrow(
            """
            INSERT INTO ops.workflow_artifacts
                (workflow_run_id, artifact_name, artifact_type, content_text,
                 phase_id, iteration, is_final)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (workflow_run_id, artifact_name) DO UPDATE SET
                artifact_type = EXCLUDED.artifact_type,
                content_text  = EXCLUDED.content_text,
                phase_id      = COALESCE(EXCLUDED.phase_id, ops.workflow_artifacts.phase_id),
                iteration     = EXCLUDED.iteration,
                is_final      = EXCLUDED.is_final,
                updated_utc   = NOW()
            RETURNING id, (xmax = 0) AS is_insert, iteration, is_final
            """,
            wf_id, artifact_name, artifact_type, content_text,
            phase_id, iteration, is_final,
        )
        return WorkflowResult(
            run_id=str(rid), tool_name="save_workflow_artifact", status="success",
            data={
                "artifact_id": row["id"],
                "artifact_name": artifact_name,
                "iteration": row["iteration"],
                "is_final": row["is_final"],
                "created_or_updated": "created" if row["is_insert"] else "updated",
            },
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("save_workflow_phase_state")
async def save_workflow_phase_state(
    run_id: str,
    phase_id: str,
    status: str | None = None,
    decision: str | None = None,
    handoff_text: str | None = None,
    attempts: int | None = None,
    started_utc: str | None = None,
    completed_utc: str | None = None,
    error_text: str | None = None,
    clear_error_text: bool = False,
    metrics_json: dict | None = None,
    correlation_id: str | None = None,
) -> str:
    """Create or update workflow phase state by (run_id, phase_id)."""
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "save_workflow_phase_state")
    guard = check_remote_write_guard(get_settings(), "save_workflow_phase_state")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        run_row = await _resolve_workflow_run_row(pool, run_id)
        if run_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_phase_state",
                status="error",
                error=f"Workflow run '{run_id}' not found",
            ).model_dump_json()
        if status is not None and status not in PHASE_STATUS_SET:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_phase_state",
                status="error",
                error=f"Invalid phase status: {status}",
            ).model_dump_json()
        if attempts is not None and attempts < 1:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_phase_state",
                status="error",
                error="attempts must be >= 1",
            ).model_dump_json()
        if clear_error_text and error_text is not None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_phase_state",
                status="error",
                error="error_text and clear_error_text cannot both be set",
            ).model_dump_json()
        if status is None:
            existing = await pool.fetchrow(
                """
                SELECT 1
                FROM ops.workflow_phase_states
                WHERE workflow_run_id = $1 AND phase_id = $2
                """,
                run_row["id"],
                phase_id,
            )
            if existing is None:
                return WorkflowResult(
                    run_id=str(rid),
                    tool_name="save_workflow_phase_state",
                    status="error",
                    error="status is required on first phase-state write",
                ).model_dump_json()

        row = await pool.fetchrow(
            """
            INSERT INTO ops.workflow_phase_states (
                workflow_run_id, phase_id, status, decision, handoff_text, attempts,
                started_utc, completed_utc, error_text, metrics_json
            )
            VALUES (
                $1, $2, $3, $4, $5, COALESCE($6, 1),
                $7::timestamptz, $8::timestamptz, $9, $10::jsonb
            )
            ON CONFLICT (workflow_run_id, phase_id) DO UPDATE SET
                status = COALESCE(EXCLUDED.status, ops.workflow_phase_states.status),
                decision = COALESCE(EXCLUDED.decision, ops.workflow_phase_states.decision),
                handoff_text = COALESCE(EXCLUDED.handoff_text, ops.workflow_phase_states.handoff_text),
                attempts = COALESCE(EXCLUDED.attempts, ops.workflow_phase_states.attempts),
                started_utc = COALESCE(EXCLUDED.started_utc, ops.workflow_phase_states.started_utc),
                completed_utc = COALESCE(EXCLUDED.completed_utc, ops.workflow_phase_states.completed_utc),
                error_text = CASE
                    WHEN $11 THEN NULL
                    WHEN $9 IS NOT NULL THEN EXCLUDED.error_text
                    ELSE ops.workflow_phase_states.error_text
                END,
                metrics_json = COALESCE(EXCLUDED.metrics_json, ops.workflow_phase_states.metrics_json),
                updated_utc = NOW()
            RETURNING phase_id
            """,
            run_row["id"],
            phase_id,
            status,
            decision,
            handoff_text,
            attempts,
            started_utc,
            completed_utc,
            error_text,
            json.dumps(metrics_json) if metrics_json is not None else None,
            clear_error_text,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="save_workflow_phase_state",
            status="success",
            data={"run_id": run_id, "phase_id": row["phase_id"], "saved": True},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("save_workflow_validator_result")
async def save_workflow_validator_result(
    run_id: str,
    phase_id: str,
    validator_code: str,
    validator_name: str,
    attempt_number: int,
    status_code: str,
    failure_reason_code: str | None = None,
    failure_reason: str | None = None,
    clear_failure_reason_code: bool = False,
    clear_failure_reason: bool = False,
    details_json: dict | None = None,
    clear_details_json: bool = False,
    started_utc: str | None = None,
    completed_utc: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Create or update workflow validator result by run/phase/code/attempt."""
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "save_workflow_validator_result")
    guard = check_remote_write_guard(get_settings(), "save_workflow_validator_result")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        run_row = await _resolve_workflow_run_row(pool, run_id)
        if run_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_validator_result",
                status="error",
                error=f"Workflow run '{run_id}' not found",
            ).model_dump_json()
        if validator_code not in VALIDATOR_CODE_SET:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_validator_result",
                status="error",
                error=f"Invalid validator_code: {validator_code}",
            ).model_dump_json()
        if attempt_number < 1:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_validator_result",
                status="error",
                error="attempt_number must be >= 1",
            ).model_dump_json()
        if failure_reason_code is not None and clear_failure_reason_code:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_validator_result",
                status="error",
                error="failure_reason_code and clear_failure_reason_code cannot both be set",
            ).model_dump_json()
        if failure_reason is not None and clear_failure_reason:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_validator_result",
                status="error",
                error="failure_reason and clear_failure_reason cannot both be set",
            ).model_dump_json()
        if details_json is not None and clear_details_json:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_validator_result",
                status="error",
                error="details_json and clear_details_json cannot both be set",
            ).model_dump_json()
        status_row = await _resolve_reference_value(pool, WORKFLOW_VALIDATOR_STATUS_TYPE, status_code)
        if status_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_validator_result",
                status="error",
                error=f"Invalid {WORKFLOW_VALIDATOR_STATUS_TYPE} value: {status_code}",
            ).model_dump_json()

        row = await pool.fetchrow(
            """
            INSERT INTO ops.workflow_validator_results (
                workflow_run_id, phase_id, validator_code, validator_name, attempt_number,
                status_id, failure_reason_code, failure_reason, details_json,
                correlation_id, started_utc, completed_utc
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9::jsonb, $10::uuid, $11::timestamptz, $12::timestamptz
            )
            ON CONFLICT (workflow_run_id, phase_id, validator_code, attempt_number) DO UPDATE SET
                validator_name = EXCLUDED.validator_name,
                status_id = EXCLUDED.status_id,
                failure_reason_code = CASE
                    WHEN $13 THEN NULL
                    WHEN $7 IS NOT NULL THEN EXCLUDED.failure_reason_code
                    ELSE ops.workflow_validator_results.failure_reason_code
                END,
                failure_reason = CASE
                    WHEN $14 THEN NULL
                    WHEN $8 IS NOT NULL THEN EXCLUDED.failure_reason
                    ELSE ops.workflow_validator_results.failure_reason
                END,
                details_json = CASE
                    WHEN $15 THEN NULL
                    WHEN $9::jsonb IS NOT NULL THEN EXCLUDED.details_json
                    ELSE ops.workflow_validator_results.details_json
                END,
                started_utc = COALESCE(EXCLUDED.started_utc, ops.workflow_validator_results.started_utc),
                completed_utc = COALESCE(EXCLUDED.completed_utc, ops.workflow_validator_results.completed_utc),
                updated_utc = NOW()
            RETURNING phase_id, validator_code, attempt_number
            """,
            run_row["id"],
            phase_id,
            validator_code,
            validator_name,
            attempt_number,
            status_row["id"],
            failure_reason_code,
            failure_reason,
            json.dumps(details_json) if details_json is not None else None,
            correlation_id,
            started_utc,
            completed_utc,
            clear_failure_reason_code,
            clear_failure_reason,
            clear_details_json,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="save_workflow_validator_result",
            status="success",
            data={
                "run_id": run_id,
                "phase_id": row["phase_id"],
                "validator_code": row["validator_code"],
                "attempt_number": row["attempt_number"],
                "saved": True,
            },
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("save_triage_case")
async def save_triage_case(
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
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "save_triage_case")
    guard = check_remote_write_guard(get_settings(), "save_triage_case")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        required_map = {
            "prompt_text": prompt_text,
            "request_kind": request_kind,
            "execution_mode": execution_mode,
            "knowledge_mode": knowledge_mode,
            "repository_key": repository_key,
        }
        for name, value in required_map.items():
            if not str(value or "").strip():
                return WorkflowResult(
                    run_id=str(rid),
                    tool_name="save_triage_case",
                    status="error",
                    error=f"{name} is required",
                ).model_dump_json()
        if not isinstance(suggested_workflows, list):
            return WorkflowResult(run_id=str(rid), tool_name="save_triage_case", status="error", error="suggested_workflows must be a list").model_dump_json()
        if not isinstance(clarifying_questions, list):
            return WorkflowResult(run_id=str(rid), tool_name="save_triage_case", status="error", error="clarifying_questions must be a list").model_dump_json()
        if matched_case_ids is not None and not isinstance(matched_case_ids, list):
            return WorkflowResult(run_id=str(rid), tool_name="save_triage_case", status="error", error="matched_case_ids must be a list").model_dump_json()

        triage_case_id = await _triage_memory.save_triage_case(
            get_pg_pool(),
            get_settings(),
            repository_key=repository_key,
            prompt_text=prompt_text,
            request_kind=request_kind,
            execution_mode=execution_mode,
            knowledge_mode=knowledge_mode,
            selected_workflow_name=selected_workflow_name,
            suggested_workflows=suggested_workflows,
            selected_run_action=selected_run_action if request_kind == "run_operation" else None,
            requires_clarification=requires_clarification,
            clarifying_questions=clarifying_questions,
            fallback_route=fallback_route,
            confidence=confidence,
            reasoning_summary=reasoning_summary,
            project_key=project_key,
            feature_key=feature_key,
            task_key=task_key,
            actor_email=actor_email,
            policy_version=policy_version,
            workflow_catalog_version=workflow_catalog_version,
            decision_source=decision_source,
            matched_case_ids=matched_case_ids or [],
            qdrant_client=get_qdrant_client(),
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="save_triage_case",
            status="success",
            data={"triage_case_id": triage_case_id, "saved": True},
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(rid), tool_name="save_triage_case", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("search_triage_cases")
async def search_triage_cases(
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
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "search_triage_cases")
    try:
        if not str(prompt_text or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="search_triage_cases", status="error", error="prompt_text is required").model_dump_json()
        data = await _triage_memory.search_triage_cases(
            get_pg_pool(),
            get_settings(),
            prompt_text=prompt_text,
            repository_key=repository_key,
            project_key=project_key,
            feature_key=feature_key,
            request_kind=request_kind,
            execution_mode=execution_mode,
            selected_workflow_name=selected_workflow_name,
            selected_run_action=selected_run_action,
            policy_version=policy_version,
            limit=limit,
            min_similarity=min_similarity,
            prefer_same_repository=prefer_same_repository,
            include_corrected=include_corrected,
            max_age_days=max_age_days,
            qdrant_client=get_qdrant_client(),
        )
        return WorkflowResult(run_id=str(rid), tool_name="search_triage_cases", status="success", data=data).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("record_triage_case_feedback")
async def record_triage_case_feedback(
    triage_case_id: str,
    outcome_status: str,
    successful_execution: bool | None = None,
    human_override: bool | None = None,
    correction_reason: str | None = None,
    corrected_request_kind: str | None = None,
    corrected_execution_mode: str | None = None,
    corrected_selected_workflow_name: str | None = None,
    feedback_notes: str | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "record_triage_case_feedback")
    guard = check_remote_write_guard(get_settings(), "record_triage_case_feedback")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        if not str(triage_case_id or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="record_triage_case_feedback", status="error", error="triage_case_id is required").model_dump_json()
        if not str(outcome_status or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="record_triage_case_feedback", status="error", error="outcome_status is required").model_dump_json()
        try:
            uuid.UUID(str(triage_case_id))
        except ValueError:
            return WorkflowResult(run_id=str(rid), tool_name="record_triage_case_feedback", status="error", error="triage_case_id must be a valid UUID").model_dump_json()
        updated = await _triage_memory.record_triage_case_feedback(
            get_pg_pool(),
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
            return WorkflowResult(run_id=str(rid), tool_name="record_triage_case_feedback", status="error", error=f"Triage case '{triage_case_id}' not found").model_dump_json()
        return WorkflowResult(run_id=str(rid), tool_name="record_triage_case_feedback", status="success", data={"triage_case_id": triage_case_id, "updated": True}).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_triage_feedback_summary")
async def get_triage_feedback_summary(
    repository_key: str | None = None,
    project_key: str | None = None,
    lookback_days: int = 30,
    request_kind: str | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_triage_feedback_summary")
    try:
        data = await _triage_memory.get_triage_feedback_summary(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
            request_kind=request_kind,
            lookback_days=lookback_days,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_triage_feedback_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_triage_confusion_clusters")
async def get_triage_confusion_clusters(
    repository_key: str | None = None,
    project_key: str | None = None,
    request_kind: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    lookback_days: int = 30,
    limit: int = 10,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_triage_confusion_clusters")
    try:
        if lookback_days < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_triage_confusion_clusters", status="error", error="lookback_days must be >= 1").model_dump_json()
        if limit < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_triage_confusion_clusters", status="error", error="limit must be >= 1").model_dump_json()
        data = await _triage_memory.get_triage_confusion_clusters(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
            request_kind=request_kind,
            selected_workflow_name=selected_workflow_name,
            selected_run_action=selected_run_action,
            lookback_days=lookback_days,
            limit=limit,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_triage_confusion_clusters",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_triage_clarification_recommendations")
async def get_triage_clarification_recommendations(
    repository_key: str | None = None,
    project_key: str | None = None,
    request_kind: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    lookback_days: int = 30,
    limit: int = 10,
    min_case_count: int = 2,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_triage_clarification_recommendations")
    try:
        if lookback_days < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_triage_clarification_recommendations", status="error", error="lookback_days must be >= 1").model_dump_json()
        if limit < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_triage_clarification_recommendations", status="error", error="limit must be >= 1").model_dump_json()
        if min_case_count < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_triage_clarification_recommendations", status="error", error="min_case_count must be >= 1").model_dump_json()
        data = await _triage_memory.get_triage_clarification_recommendations(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
            request_kind=request_kind,
            selected_workflow_name=selected_workflow_name,
            selected_run_action=selected_run_action,
            lookback_days=lookback_days,
            limit=limit,
            min_case_count=min_case_count,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_triage_clarification_recommendations",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_routing_policy_recommendations")
async def get_routing_policy_recommendations(
    repository_key: str,
    project_key: str | None = None,
    request_kind: str | None = None,
    lookback_days: int = 90,
    limit: int = 10,
    min_case_count: int = 3,
    min_confidence: float = 0.6,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_routing_policy_recommendations")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="get_routing_policy_recommendations", status="error", error="repository_key is required").model_dump_json()
        if lookback_days < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_routing_policy_recommendations", status="error", error="lookback_days must be >= 1").model_dump_json()
        if limit < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_routing_policy_recommendations", status="error", error="limit must be >= 1").model_dump_json()
        if min_case_count < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_routing_policy_recommendations", status="error", error="min_case_count must be >= 1").model_dump_json()
        try:
            min_confidence_value = float(min_confidence)
        except (TypeError, ValueError):
            return WorkflowResult(run_id=str(rid), tool_name="get_routing_policy_recommendations", status="error", error="min_confidence must be between 0 and 1").model_dump_json()
        if not 0.0 <= min_confidence_value <= 1.0:
            return WorkflowResult(run_id=str(rid), tool_name="get_routing_policy_recommendations", status="error", error="min_confidence must be between 0 and 1").model_dump_json()
        data = await _triage_policy.get_routing_policy_recommendations(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
            request_kind=request_kind,
            lookback_days=lookback_days,
            limit=limit,
            min_case_count=min_case_count,
            min_confidence=min_confidence_value,
        )
        return WorkflowResult(run_id=str(rid), tool_name="get_routing_policy_recommendations", status="success", data=data).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_clarification_policy")
async def get_clarification_policy(
    repository_key: str,
    project_key: str | None = None,
    request_kind: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    lookback_days: int = 90,
    limit: int = 10,
    min_case_count: int = 2,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_clarification_policy")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="get_clarification_policy", status="error", error="repository_key is required").model_dump_json()
        if lookback_days < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_clarification_policy", status="error", error="lookback_days must be >= 1").model_dump_json()
        if limit < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_clarification_policy", status="error", error="limit must be >= 1").model_dump_json()
        if min_case_count < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_clarification_policy", status="error", error="min_case_count must be >= 1").model_dump_json()
        data = await _triage_policy.get_clarification_policy(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
            request_kind=request_kind,
            selected_workflow_name=selected_workflow_name,
            selected_run_action=selected_run_action,
            lookback_days=lookback_days,
            limit=limit,
            min_case_count=min_case_count,
        )
        return WorkflowResult(run_id=str(rid), tool_name="get_clarification_policy", status="success", data=data).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_required_clarification_policy")
async def get_required_clarification_policy(
    repository_key: str,
    project_key: str | None = None,
    request_kind: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    lookback_days: int = 90,
    min_case_count: int = 2,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_required_clarification_policy")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="get_required_clarification_policy", status="error", error="repository_key is required").model_dump_json()
        if lookback_days < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_required_clarification_policy", status="error", error="lookback_days must be >= 1").model_dump_json()
        if min_case_count < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_required_clarification_policy", status="error", error="min_case_count must be >= 1").model_dump_json()
        data = await _triage_policy.get_required_clarification_policy(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
            request_kind=request_kind,
            selected_workflow_name=selected_workflow_name,
            selected_run_action=selected_run_action,
            lookback_days=lookback_days,
            min_case_count=min_case_count,
        )
        return WorkflowResult(run_id=str(rid), tool_name="get_required_clarification_policy", status="success", data=data).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_triage_behavior_profiles")
async def list_triage_behavior_profiles(
    repository_key: str,
    project_key: str | None = None,
    lookback_days: int = 90,
    limit: int = 10,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "list_triage_behavior_profiles")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="list_triage_behavior_profiles", status="error", error="repository_key is required").model_dump_json()
        if lookback_days < 1:
            return WorkflowResult(run_id=str(rid), tool_name="list_triage_behavior_profiles", status="error", error="lookback_days must be >= 1").model_dump_json()
        if limit < 1:
            return WorkflowResult(run_id=str(rid), tool_name="list_triage_behavior_profiles", status="error", error="limit must be >= 1").model_dump_json()
        data = await _triage_policy.list_triage_behavior_profiles(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
            lookback_days=lookback_days,
            limit=limit,
        )
        return WorkflowResult(run_id=str(rid), tool_name="list_triage_behavior_profiles", status="success", data=data).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("refresh_triage_policy_artifacts")
async def refresh_triage_policy_artifacts(
    repository_key: str,
    project_key: str | None = None,
    lookback_days: int = 90,
    routing_min_case_count: int = 3,
    routing_min_confidence: float = 0.6,
    clarification_min_case_count: int = 2,
    limit: int = 50,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "refresh_triage_policy_artifacts")
    guard = check_remote_write_guard(get_settings(), "refresh_triage_policy_artifacts")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="refresh_triage_policy_artifacts", status="error", error="repository_key is required").model_dump_json()
        if lookback_days < 1:
            return WorkflowResult(run_id=str(rid), tool_name="refresh_triage_policy_artifacts", status="error", error="lookback_days must be >= 1").model_dump_json()
        if routing_min_case_count < 1:
            return WorkflowResult(run_id=str(rid), tool_name="refresh_triage_policy_artifacts", status="error", error="routing_min_case_count must be >= 1").model_dump_json()
        if clarification_min_case_count < 1:
            return WorkflowResult(run_id=str(rid), tool_name="refresh_triage_policy_artifacts", status="error", error="clarification_min_case_count must be >= 1").model_dump_json()
        if limit < 1:
            return WorkflowResult(run_id=str(rid), tool_name="refresh_triage_policy_artifacts", status="error", error="limit must be >= 1").model_dump_json()
        try:
            routing_min_confidence_value = float(routing_min_confidence)
        except (TypeError, ValueError):
            return WorkflowResult(run_id=str(rid), tool_name="refresh_triage_policy_artifacts", status="error", error="routing_min_confidence must be between 0 and 1").model_dump_json()
        if not 0.0 <= routing_min_confidence_value <= 1.0:
            return WorkflowResult(run_id=str(rid), tool_name="refresh_triage_policy_artifacts", status="error", error="routing_min_confidence must be between 0 and 1").model_dump_json()
        data = await _triage_policy.refresh_triage_policy_artifacts(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
            lookback_days=lookback_days,
            routing_min_case_count=routing_min_case_count,
            routing_min_confidence=routing_min_confidence_value,
            clarification_min_case_count=clarification_min_case_count,
            limit=limit,
        )
        return WorkflowResult(run_id=str(rid), tool_name="refresh_triage_policy_artifacts", status="success", data=data).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(rid), tool_name="refresh_triage_policy_artifacts", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_behavior_policy_status")
async def get_behavior_policy_status(
    repository_key: str,
    project_key: str | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_behavior_policy_status")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="get_behavior_policy_status", status="error", error="repository_key is required").model_dump_json()
        data = await _triage_policy.get_behavior_policy_status(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
        )
        return WorkflowResult(run_id=str(rid), tool_name="get_behavior_policy_status", status="success", data=data).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_policy_governance_rollout_summary")
async def get_policy_governance_rollout_summary(
    repository_key: str,
    project_key: str | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_policy_governance_rollout_summary")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_policy_governance_rollout_summary",
                status="error",
                error="repository_key is required",
            ).model_dump_json()
        data = await _triage_policy.get_policy_governance_rollout_summary(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_policy_governance_rollout_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_outcome_weighted_routing_summary")
async def get_outcome_weighted_routing_summary(
    repository_key: str,
    project_key: str | None = None,
    request_kind: str | None = None,
    lookback_days: int = 90,
    limit: int = 10,
    min_case_count: int = 2,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_outcome_weighted_routing_summary")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="get_outcome_weighted_routing_summary", status="error", error="repository_key is required").model_dump_json()
        if lookback_days < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_outcome_weighted_routing_summary", status="error", error="lookback_days must be >= 1").model_dump_json()
        if limit < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_outcome_weighted_routing_summary", status="error", error="limit must be >= 1").model_dump_json()
        if min_case_count < 1:
            return WorkflowResult(run_id=str(rid), tool_name="get_outcome_weighted_routing_summary", status="error", error="min_case_count must be >= 1").model_dump_json()
        data = await _triage_policy.get_outcome_weighted_routing_summary(
            get_pg_pool(),
            repository_key=repository_key,
            project_key=project_key,
            request_kind=request_kind,
            lookback_days=lookback_days,
            limit=limit,
            min_case_count=min_case_count,
        )
        return WorkflowResult(run_id=str(rid), tool_name="get_outcome_weighted_routing_summary", status="success", data=data).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("triage_request_with_memory")
async def triage_request_with_memory(
    repository_key: str,
    prompt_text: str,
    project_key: str | None = None,
    feature_key: str | None = None,
    actor_email: str | None = None,
    request_kind: str | None = None,
    execution_mode: str | None = None,
    selected_workflow_name: str | None = None,
    selected_run_action: str | None = None,
    limit: int = 5,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "triage_request_with_memory")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="triage_request_with_memory", status="error", error="repository_key is required").model_dump_json()
        if not str(prompt_text or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="triage_request_with_memory", status="error", error="prompt_text is required").model_dump_json()
        if limit < 1:
            return WorkflowResult(run_id=str(rid), tool_name="triage_request_with_memory", status="error", error="limit must be >= 1").model_dump_json()
        data = await _triage_policy.triage_request_with_memory(
            get_pg_pool(),
            get_settings(),
            prompt_text=prompt_text,
            repository_key=repository_key,
            project_key=project_key,
            feature_key=feature_key,
            actor_email=actor_email,
            request_kind=request_kind,
            execution_mode=execution_mode,
            selected_workflow_name=selected_workflow_name,
            selected_run_action=selected_run_action,
            limit=limit,
        )
        return WorkflowResult(run_id=str(rid), tool_name="triage_request_with_memory", status="success", data=data).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("finalize_triage_outcome")
async def finalize_triage_outcome(
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
    refresh_policy_artifacts_after_write: bool = True,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "finalize_triage_outcome")
    guard = check_remote_write_guard(get_settings(), "finalize_triage_outcome")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        if not str(triage_case_id or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="finalize_triage_outcome", status="error", error="triage_case_id is required").model_dump_json()
        if not str(repository_key or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="finalize_triage_outcome", status="error", error="repository_key is required").model_dump_json()
        if not str(outcome_status or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="finalize_triage_outcome", status="error", error="outcome_status is required").model_dump_json()
        try:
            uuid.UUID(str(triage_case_id))
        except ValueError:
            return WorkflowResult(run_id=str(rid), tool_name="finalize_triage_outcome", status="error", error="triage_case_id must be a valid UUID").model_dump_json()
        data = await _triage_policy.finalize_triage_outcome(
            get_pg_pool(),
            triage_case_id=triage_case_id,
            outcome_status=outcome_status,
            repository_key=repository_key,
            project_key=project_key,
            successful_execution=successful_execution,
            human_override=human_override,
            correction_reason=correction_reason,
            corrected_request_kind=corrected_request_kind,
            corrected_execution_mode=corrected_execution_mode,
            corrected_selected_workflow_name=corrected_selected_workflow_name,
            feedback_notes=feedback_notes,
            refresh_policy_artifacts=refresh_policy_artifacts_after_write,
        )
        return WorkflowResult(run_id=str(rid), tool_name="finalize_triage_outcome", status="success", data=data).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(rid), tool_name="finalize_triage_outcome", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("save_workflow_finding")
async def save_workflow_finding(
    repository_key: str,
    run_id: str,
    workflow_name: str,
    phase_id: str,
    agent_name: str,
    attempt_number: int,
    finding_fingerprint: str,
    finding_title: str,
    finding_message: str,
    artifact_name: str | None = None,
    artifact_iteration: int | None = None,
    artifact_hash: str | None = None,
    location: str | None = None,
    evidence_text: str | None = None,
    finding_kind_code: str | None = None,
    severity: str | None = None,
    source_kind: str | None = None,
    status_code: str | None = None,
    actor_email: str | None = None,
    context_json: dict | str | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "save_workflow_finding")
    guard = check_remote_write_guard(get_settings(), "save_workflow_finding")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        import json as _json
        if attempt_number < 1:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding",
                status="error",
                error="attempt_number must be >= 1",
            ).model_dump_json()
        if not finding_fingerprint or not finding_fingerprint.strip():
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding",
                status="error",
                error="finding_fingerprint must be non-empty",
            ).model_dump_json()
        if not phase_id or not phase_id.strip():
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding",
                status="error",
                error="phase_id must be non-empty",
            ).model_dump_json()
        pool = get_pg_pool()
        repo_row = await pool.fetchrow(
            "SELECT id FROM catalog.repositories WHERE repository_key = $1",
            repository_key,
        )
        if repo_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding",
                status="error",
                error=f"Repository '{repository_key}' not found",
            ).model_dump_json()
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding",
                status="error",
                error=f"Invalid run_id: {run_id}",
            ).model_dump_json()
        run_row = await pool.fetchrow(
            """
            SELECT wr.id, wr.repository_id, wr.workflow_name
            FROM ops.workflow_runs wr
            WHERE wr.run_id = $1
            """,
            run_uuid,
        )
        if run_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding",
                status="error",
                error=f"Workflow run '{run_id}' not found",
            ).model_dump_json()
        if run_row["repository_id"] != repo_row["id"]:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding",
                status="error",
                error="repository_key does not match the workflow run repository",
            ).model_dump_json()
        if workflow_name != run_row["workflow_name"]:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding",
                status="error",
                error="workflow_name does not match the workflow run",
            ).model_dump_json()
        finding_kind = await _require_reference_value(
            pool,
            WORKFLOW_FINDING_KIND_TYPE,
            finding_kind_code or DEFAULT_WORKFLOW_FINDING_KIND,
            "save_workflow_finding",
            rid,
        )
        if isinstance(finding_kind, str):
            return finding_kind
        status_row = await _require_reference_value(
            pool,
            WORKFLOW_FINDING_STATUS_TYPE,
            status_code or DEFAULT_WORKFLOW_FINDING_STATUS,
            "save_workflow_finding",
            rid,
        )
        if isinstance(status_row, str):
            return status_row
        if isinstance(context_json, str):
            try:
                normalized_context = _json.dumps(_json.loads(context_json)) if context_json else None
            except json.JSONDecodeError:
                return WorkflowResult(
                    run_id=str(rid),
                    tool_name="save_workflow_finding",
                    status="error",
                    error="context_json must be valid JSON",
                ).model_dump_json()
        elif context_json is not None:
            normalized_context = _json.dumps(context_json)
        else:
            normalized_context = None
        row = await _findings.save_workflow_finding(
            pool,
            repository_id=repo_row["id"],
            workflow_run_id=run_row["id"],
            workflow_name=workflow_name,
            phase_id=phase_id,
            agent_name=agent_name,
            attempt_number=attempt_number,
            artifact_name=artifact_name,
            artifact_iteration=artifact_iteration,
            artifact_hash=artifact_hash,
            finding_fingerprint=finding_fingerprint.strip(),
            finding_title=finding_title,
            finding_message=finding_message,
            location=location,
            evidence_text=evidence_text,
            finding_kind_id=finding_kind["id"],
            severity=severity,
            source_kind=source_kind,
            status_id=status_row["id"],
            actor_email=actor_email,
            context_json=normalized_context,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="save_workflow_finding",
            status="success",
            data={
                "finding_id": row["id"],
                "run_id": run_id,
                "phase_id": row["phase_id"],
                "attempt_number": row["attempt_number"],
                "finding_fingerprint": row["finding_fingerprint"],
                "saved": True,
            },
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("save_workflow_finding_decision")
async def save_workflow_finding_decision(
    repository_key: str,
    run_id: str,
    workflow_name: str,
    critic_phase_id: str,
    critic_agent_name: str,
    attempt_number: int,
    finding_fingerprint: str,
    decision_bucket_code: str,
    actionable: bool,
    suppress_on_rerun: bool,
    reason_text: str | None = None,
    evidence_text: str | None = None,
    suppression_scope_code: str | None = None,
    finding_phase_id: str | None = None,
    artifact_name: str | None = None,
    artifact_iteration: int | None = None,
    artifact_hash: str | None = None,
    actor_email: str | None = None,
    context_json: dict | str | None = None,
    created_utc: str | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "save_workflow_finding_decision")
    guard = check_remote_write_guard(get_settings(), "save_workflow_finding_decision")
    if guard is not None:
        guard.run_id = str(rid)
        return guard.model_dump_json()
    try:
        import json as _json
        if attempt_number < 1:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error="attempt_number must be >= 1",
            ).model_dump_json()
        if not finding_fingerprint or not finding_fingerprint.strip():
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error="finding_fingerprint must be non-empty",
            ).model_dump_json()
        pool = get_pg_pool()
        repo_row = await pool.fetchrow(
            "SELECT id FROM catalog.repositories WHERE repository_key = $1",
            repository_key,
        )
        if repo_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error=f"Repository '{repository_key}' not found",
            ).model_dump_json()
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error=f"Invalid run_id: {run_id}",
            ).model_dump_json()
        run_row = await pool.fetchrow(
            """
            SELECT wr.id, wr.repository_id, wr.workflow_name
            FROM ops.workflow_runs wr
            WHERE wr.run_id = $1
            """,
            run_uuid,
        )
        if run_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error=f"Workflow run '{run_id}' not found",
            ).model_dump_json()
        if run_row["repository_id"] != repo_row["id"]:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error="repository_key does not match the workflow run repository",
            ).model_dump_json()
        if workflow_name != run_row["workflow_name"]:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error="workflow_name does not match the workflow run",
            ).model_dump_json()
        if not _is_valid_timestamp(created_utc):
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error="created_utc must be a valid ISO-8601 timestamp",
            ).model_dump_json()
        decision_bucket = await _require_reference_value(
            pool,
            WORKFLOW_FINDING_DECISION_BUCKET_TYPE,
            decision_bucket_code,
            "save_workflow_finding_decision",
            rid,
        )
        if isinstance(decision_bucket, str):
            return decision_bucket
        suppression_scope = await _require_reference_value(
            pool,
            WORKFLOW_FINDING_SUPPRESSION_SCOPE_TYPE,
            suppression_scope_code or DEFAULT_WORKFLOW_FINDING_SUPPRESSION_SCOPE,
            "save_workflow_finding_decision",
            rid,
        )
        if isinstance(suppression_scope, str):
            return suppression_scope
        finding_id = await _findings.resolve_workflow_finding_id(
            pool,
            workflow_run_id=run_row["id"],
            attempt_number=attempt_number,
            finding_fingerprint=finding_fingerprint.strip(),
            finding_phase_id=finding_phase_id,
        )
        if finding_id is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error="No matching workflow finding found for this decision",
            ).model_dump_json()
        if finding_id == "ambiguous":
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error="Multiple findings match this run/attempt/fingerprint; provide finding_phase_id",
            ).model_dump_json()
        if isinstance(context_json, str):
            try:
                normalized_context = _json.dumps(_json.loads(context_json)) if context_json else None
            except json.JSONDecodeError:
                return WorkflowResult(
                    run_id=str(rid),
                    tool_name="save_workflow_finding_decision",
                    status="error",
                    error="context_json must be valid JSON",
                ).model_dump_json()
        elif context_json is not None:
            normalized_context = _json.dumps(context_json)
        else:
            normalized_context = None
        row = await _findings.save_workflow_finding_decision(
            pool,
            repository_id=repo_row["id"],
            workflow_run_id=run_row["id"],
            workflow_finding_id=finding_id,
            workflow_name=workflow_name,
            critic_phase_id=critic_phase_id,
            critic_agent_name=critic_agent_name,
            attempt_number=attempt_number,
            finding_fingerprint=finding_fingerprint.strip(),
            decision_bucket_id=decision_bucket["id"],
            actionable=actionable,
            reason_text=reason_text,
            evidence_text=evidence_text,
            suppression_scope_id=suppression_scope["id"],
            suppress_on_rerun=suppress_on_rerun,
            artifact_name=artifact_name,
            artifact_iteration=artifact_iteration,
            artifact_hash=artifact_hash,
            actor_email=actor_email,
            context_json=normalized_context,
            created_utc=created_utc,
        )
        if row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="save_workflow_finding_decision",
                status="error",
                error="Duplicate workflow finding decision",
            ).model_dump_json()
        return WorkflowResult(
            run_id=str(rid),
            tool_name="save_workflow_finding_decision",
            status="success",
            data={
                "decision_id": row["id"],
                "workflow_finding_id": row["workflow_finding_id"],
                "saved": True,
            },
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_workflow_finding_suppressions")
async def list_workflow_finding_suppressions(
    repository_key: str,
    run_id: str,
    workflow_name: str,
    phase_id: str,
    artifact_name: str | None = None,
    artifact_iteration: int | None = None,
    artifact_hash: str | None = None,
    limit: int = 50,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "list_workflow_finding_suppressions")
    try:
        if limit < 0:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="list_workflow_finding_suppressions",
                status="error",
                error="limit must be >= 0",
            ).model_dump_json()
        pool = get_pg_pool()
        repo_row = await pool.fetchrow(
            "SELECT id FROM catalog.repositories WHERE repository_key = $1",
            repository_key,
        )
        if repo_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="list_workflow_finding_suppressions",
                status="error",
                error=f"Repository '{repository_key}' not found",
            ).model_dump_json()
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="list_workflow_finding_suppressions",
                status="error",
                error=f"Invalid run_id: {run_id}",
            ).model_dump_json()
        run_row = await pool.fetchrow(
            """
            SELECT wr.id, wr.repository_id, wr.workflow_name
            FROM ops.workflow_runs wr
            WHERE wr.run_id = $1
            """,
            run_uuid,
        )
        if run_row is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="list_workflow_finding_suppressions",
                status="error",
                error=f"Workflow run '{run_id}' not found",
            ).model_dump_json()
        if run_row["repository_id"] != repo_row["id"]:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="list_workflow_finding_suppressions",
                status="error",
                error="repository_key does not match the workflow run repository",
            ).model_dump_json()
        if workflow_name != run_row["workflow_name"]:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="list_workflow_finding_suppressions",
                status="error",
                error="workflow_name does not match the workflow run",
            ).model_dump_json()
        data = await _findings.list_workflow_finding_suppressions(
            pool,
            repository_id=repo_row["id"],
            workflow_run_id=run_row["id"],
            workflow_name=workflow_name,
            phase_id=phase_id,
            artifact_name=artifact_name,
            artifact_iteration=artifact_iteration,
            artifact_hash=artifact_hash,
            limit=limit,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="list_workflow_finding_suppressions",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_workflow_run")
async def get_workflow_run(
    run_id: str, correlation_id: str | None = None
) -> str:
    """Retrieve a workflow run by run_id, including phase states and artifact metadata."""
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_workflow_run")
    try:
        pool = get_pg_pool()
        row = await pool.fetchrow(
            """
            SELECT wr.run_id, r.repository_key, wr.workflow_name,
                   wr.task_description, rv.internal_code AS status_code,
                   rv.display_name AS status_display_name, rv.is_terminal,
                   wr.actor_email, wr.current_phase,
                   wr.iteration_count, wr.context_json,
                   wr.started_utc, wr.completed_utc, wr.error_text
            FROM ops.workflow_runs wr
            JOIN catalog.repositories r ON r.id = wr.repository_id
            JOIN core.reference_values rv ON rv.id = wr.status_id
            WHERE wr.run_id = $1
            """,
            uuid.UUID(run_id),
        )
        if not row:
            return WorkflowResult(
                run_id=str(rid), tool_name="get_workflow_run",
                status="error", error=f"Workflow run '{run_id}' not found",
            ).model_dump_json()

        phases = await pool.fetch(
            """
            SELECT phase_id, status, decision, attempts,
                   started_utc, completed_utc, error_text, metrics_json
            FROM ops.workflow_phase_states
            WHERE workflow_run_id = (SELECT id FROM ops.workflow_runs WHERE run_id = $1)
            ORDER BY id
            """,
            uuid.UUID(run_id),
        )
        artifacts = await pool.fetch(
            """
            SELECT artifact_name, artifact_type, iteration, is_final, updated_utc
            FROM ops.workflow_artifacts
            WHERE workflow_run_id = (SELECT id FROM ops.workflow_runs WHERE run_id = $1)
            ORDER BY id
            """,
            uuid.UUID(run_id),
        )
        validator_results = await pool.fetch(
            """
            SELECT wvr.phase_id,
                   wvr.validator_code,
                   wvr.validator_name,
                   wvr.attempt_number,
                   rv.internal_code AS status_code,
                   wvr.failure_reason_code,
                   wvr.failure_reason,
                   wvr.details_json,
                   wvr.started_utc,
                   wvr.completed_utc,
                   wvr.created_utc
            FROM ops.workflow_validator_results wvr
            JOIN core.reference_values rv ON rv.id = wvr.status_id
            WHERE wvr.workflow_run_id = (SELECT id FROM ops.workflow_runs WHERE run_id = $1)
            ORDER BY wvr.phase_id, wvr.validator_code, wvr.attempt_number, wvr.created_utc
            """,
            uuid.UUID(run_id),
        )
        ctx = json.loads(row["context_json"]) if row["context_json"] else None
        return WorkflowResult(
            run_id=str(rid), tool_name="get_workflow_run", status="success",
            data={
                "run_id": str(row["run_id"]),
                "repository_key": row["repository_key"],
                "workflow_name": row["workflow_name"],
                "task_description": row["task_description"],
                "status": _legacy_workflow_run_status_name(row["status_code"]),
                "status_code": row["status_code"],
                "status_display_name": row["status_display_name"],
                "is_terminal": row["is_terminal"],
                "actor_email": row["actor_email"],
                "current_phase": row["current_phase"],
                "iteration_count": row["iteration_count"],
                "context_json": ctx,
                "started_utc": _isoformat(row["started_utc"]),
                "completed_utc": _isoformat(row["completed_utc"]),
                "error_text": row["error_text"],
                "phases": [
                    {
                        "phase_id": p["phase_id"],
                        "status": p["status"],
                        "decision": p["decision"],
                        "attempts": p["attempts"],
                        "started_utc": _isoformat(p["started_utc"]),
                        "completed_utc": _isoformat(p["completed_utc"]),
                        "error_text": p["error_text"],
                        "metrics_json": p["metrics_json"],
                    }
                    for p in phases
                ],
                "validator_results": [
                    {
                        "phase_id": v["phase_id"],
                        "validator_code": v["validator_code"],
                        "validator_name": v["validator_name"],
                        "attempt_number": v["attempt_number"],
                        "status_code": v["status_code"],
                        "failure_reason_code": v["failure_reason_code"],
                        "failure_reason": v["failure_reason"],
                        "details_json": v["details_json"],
                        "started_utc": _isoformat(v["started_utc"]),
                        "completed_utc": _isoformat(v["completed_utc"]),
                        "created_utc": _isoformat(v["created_utc"]),
                    }
                    for v in validator_results
                ],
                "artifacts": [
                    {
                        "artifact_name": a["artifact_name"],
                        "artifact_type": a["artifact_type"],
                        "iteration": a["iteration"],
                        "is_final": a["is_final"],
                        "updated_utc": _isoformat(a["updated_utc"]),
                    }
                    for a in artifacts
                ],
            },
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_workflow_artifact")
async def get_workflow_artifact(
    run_id: str,
    artifact_name: str,
    correlation_id: str | None = None,
) -> str:
    """Retrieve the full content of a specific workflow artifact."""
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_workflow_artifact")
    try:
        pool = get_pg_pool()
        row = await pool.fetchrow(
            """
            SELECT a.artifact_name, a.artifact_type, a.content_text,
                   a.phase_id, a.iteration, a.is_final, a.updated_utc
            FROM ops.workflow_artifacts a
            JOIN ops.workflow_runs wr ON wr.id = a.workflow_run_id
            WHERE wr.run_id = $1 AND a.artifact_name = $2
            """,
            uuid.UUID(run_id), artifact_name,
        )
        if not row:
            return WorkflowResult(
                run_id=str(rid), tool_name="get_workflow_artifact",
                status="error",
                error=f"Artifact '{artifact_name}' not found for run '{run_id}'",
            ).model_dump_json()

        return WorkflowResult(
            run_id=str(rid), tool_name="get_workflow_artifact", status="success",
            data={
                "artifact_name": row["artifact_name"],
                "artifact_type": row["artifact_type"],
                "content_text": row["content_text"],
                "phase_id": row["phase_id"],
                "iteration": row["iteration"],
                "is_final": row["is_final"],
                "updated_utc": row["updated_utc"].isoformat() if row["updated_utc"] else None,
            },
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_workflow_runs")
async def list_workflow_runs(
    repository_key: str,
    status: str | None = None,
    status_code: str | None = None,
    limit: int = 20,
    correlation_id: str | None = None,
) -> str:
    """List workflow runs for a repository, with optional status_code filter."""
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "list_workflow_runs")
    try:
        pool = get_pg_pool()
        effective_status_code = status_code or status
        if effective_status_code:
            status_row = await _resolve_workflow_run_status(pool, effective_status_code)
            if status_row is None:
                return WorkflowResult(
                    run_id=str(rid),
                    tool_name="list_workflow_runs",
                    status="error",
                    error=f"Invalid workflow run status or status_code: {effective_status_code}",
                ).model_dump_json()
            rows = await pool.fetch(
                """
                SELECT wr.run_id, wr.workflow_name,
                       rv.internal_code AS status_code, rv.display_name AS status_display_name,
                       rv.is_terminal,
                       wr.iteration_count, wr.started_utc, wr.completed_utc,
                       (SELECT COUNT(*) FROM ops.workflow_artifacts wa
                        WHERE wa.workflow_run_id = wr.id) AS artifact_count
                FROM ops.workflow_runs wr
                JOIN catalog.repositories r ON r.id = wr.repository_id
                JOIN core.reference_values rv ON rv.id = wr.status_id
                WHERE r.repository_key = $1 AND wr.status_id = $2
                ORDER BY wr.started_utc DESC
                LIMIT $3
                """,
                repository_key, status_row["id"], limit,
            )
        else:
            rows = await pool.fetch(
                """
                SELECT wr.run_id, wr.workflow_name,
                       rv.internal_code AS status_code, rv.display_name AS status_display_name,
                       rv.is_terminal,
                       wr.iteration_count, wr.started_utc, wr.completed_utc,
                       (SELECT COUNT(*) FROM ops.workflow_artifacts wa
                        WHERE wa.workflow_run_id = wr.id) AS artifact_count
                FROM ops.workflow_runs wr
                JOIN catalog.repositories r ON r.id = wr.repository_id
                JOIN core.reference_values rv ON rv.id = wr.status_id
                WHERE r.repository_key = $1
                ORDER BY wr.started_utc DESC
                LIMIT $2
                """,
                repository_key, limit,
            )
        runs = [
            {
                "run_id": str(r["run_id"]),
                "workflow_name": r["workflow_name"],
                "status": _legacy_workflow_run_status_name(r["status_code"]),
                "status_code": r["status_code"],
                "status_display_name": r["status_display_name"],
                "is_terminal": r["is_terminal"],
                "iteration_count": r["iteration_count"],
                "started_utc": r["started_utc"].isoformat() if r["started_utc"] else None,
                "completed_utc": r["completed_utc"].isoformat() if r["completed_utc"] else None,
                "artifact_count": r["artifact_count"],
            }
            for r in rows
        ]
        return WorkflowResult(
            run_id=str(rid), tool_name="list_workflow_runs", status="success",
            data={"runs": runs, "count": len(runs)},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_reference_values")
async def list_reference_values(
    reference_type_code: str, correlation_id: str | None = None
) -> str:
    """List values for a reference type by internal_code."""
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "list_reference_values")
    try:
        pool = get_pg_pool()
        type_id = await _resolve_reference_type_id(pool, reference_type_code)
        if type_id is None:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="list_reference_values",
                status="error",
                error=f"Reference type not found: {reference_type_code}",
            ).model_dump_json()
        rows = await pool.fetch(
            """
            SELECT rv.id, rv.internal_code, rv.display_name, rv.description,
                   rv.sort_order, rv.is_active, rv.is_terminal
            FROM core.reference_values rv
            WHERE rv.reference_type_id = $1
            ORDER BY rv.sort_order, rv.id
            """,
            type_id,
        )
        values = [
            {
                "id": r["id"],
                "internal_code": r["internal_code"],
                "display_name": r["display_name"],
                "description": r["description"],
                "sort_order": r["sort_order"],
                "is_active": r["is_active"],
                "is_terminal": r["is_terminal"],
            }
            for r in rows
        ]
        return WorkflowResult(
            run_id=str(rid),
            tool_name="list_reference_values",
            status="success",
            data={"reference_type_code": reference_type_code, "values": values, "count": len(values)},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_workflow_runs_by_actor")
async def list_workflow_runs_by_actor(
    actor_email: str,
    include_terminal: bool = False,
    limit: int = 20,
    correlation_id: str | None = None,
) -> str:
    """List workflow runs for an actor email, optionally excluding terminal runs."""
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "list_workflow_runs_by_actor")
    try:
        pool = get_pg_pool()
        base_rows = await pool.fetch(
            """
            SELECT
                wr.id AS workflow_run_id,
                wr.run_id,
                r.repository_key,
                wr.workflow_name,
                wr.task_description,
                rv.id AS status_id,
                rv.internal_code AS status_code,
                rv.display_name AS status_display_name,
                rv.is_terminal,
                wr.current_phase,
                wr.iteration_count,
                wr.started_utc,
                wr.completed_utc,
                (
                    SELECT COUNT(*)
                    FROM ops.workflow_artifacts wa
                    WHERE wa.workflow_run_id = wr.id
                ) AS artifact_count
            FROM ops.workflow_runs wr
            JOIN catalog.repositories r ON r.id = wr.repository_id
            JOIN core.reference_values rv ON rv.id = wr.status_id
            WHERE wr.actor_email = $1
              AND ($2::boolean = TRUE OR rv.is_terminal = FALSE)
            ORDER BY wr.started_utc DESC
            LIMIT $3
            """,
            actor_email,
            include_terminal,
            limit,
        )
        run_ids = [row["workflow_run_id"] for row in base_rows]
        planning_rows = []
        if run_ids:
            planning_rows = await pool.fetch(
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

        planning_context_by_run: dict[int, dict[str, list[dict[str, str]]]] = {}
        seen_keys_by_run: dict[int, dict[str, set[str]]] = {}
        for row in planning_rows:
            workflow_run_id = row["workflow_run_id"]
            if workflow_run_id not in planning_context_by_run:
                planning_context_by_run[workflow_run_id] = {
                    "projects": [],
                    "features": [],
                    "tasks": [],
                }
                seen_keys_by_run[workflow_run_id] = {
                    "projects": set(),
                    "features": set(),
                    "tasks": set(),
                }
            ctx = planning_context_by_run[workflow_run_id]
            seen = seen_keys_by_run[workflow_run_id]
            if row["project_key"] and str(row["project_key"]) not in seen["projects"]:
                seen["projects"].add(str(row["project_key"]))
                ctx["projects"].append(
                    {
                        "project_key": str(row["project_key"]),
                        "project_name": row["project_name"],
                    }
                )
            if row["feature_key"] and str(row["feature_key"]) not in seen["features"]:
                seen["features"].add(str(row["feature_key"]))
                ctx["features"].append(
                    {
                        "feature_key": str(row["feature_key"]),
                        "feature_title": row["feature_title"],
                    }
                )
            if row["task_key"] and str(row["task_key"]) not in seen["tasks"]:
                seen["tasks"].add(str(row["task_key"]))
                ctx["tasks"].append(
                    {
                        "task_key": str(row["task_key"]),
                        "task_title": row["task_title"],
                    }
                )

        runs = [
            {
                "run_id": str(r["run_id"]),
                "repository_key": r["repository_key"],
                "workflow_name": r["workflow_name"],
                "task_description": r["task_description"],
                "status_id": r["status_id"],
                "status_code": r["status_code"],
                "status_display_name": r["status_display_name"],
                "is_terminal": r["is_terminal"],
                "current_phase": r["current_phase"],
                "iteration_count": r["iteration_count"],
                "started_utc": _isoformat(r["started_utc"]),
                "completed_utc": _isoformat(r["completed_utc"]),
                "artifact_count": r["artifact_count"],
                "planning_context": planning_context_by_run.get(
                    r["workflow_run_id"],
                    {"projects": [], "features": [], "tasks": []},
                ),
            }
            for r in base_rows
        ]
        return WorkflowResult(
            run_id=str(rid),
            tool_name="list_workflow_runs_by_actor",
            status="success",
            data={"actor_email": actor_email, "runs": runs, "count": len(runs)},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_agent_performance_summary")
async def get_agent_performance_summary(
    repository_key: str | None = None,
    workflow_name: str | None = None,
    actor_email: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    include_planning_context: bool = False,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_agent_performance_summary")
    try:
        data = await _analytics.get_agent_performance_summary(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            actor_email=actor_email,
            since_utc=since_utc,
            until_utc=until_utc,
            include_planning_context=include_planning_context,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_agent_performance_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_phase_quality_summary")
async def get_phase_quality_summary(
    repository_key: str | None = None,
    workflow_name: str | None = None,
    phase_id: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_phase_quality_summary")
    try:
        data = await _analytics.get_phase_quality_summary(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            phase_id=phase_id,
            since_utc=since_utc,
            until_utc=until_utc,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_phase_quality_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_validator_failure_summary")
async def get_validator_failure_summary(
    repository_key: str | None = None,
    workflow_name: str | None = None,
    validator_code: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_validator_failure_summary")
    try:
        data = await _analytics.get_validator_failure_summary(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            validator_code=validator_code,
            since_utc=since_utc,
            until_utc=until_utc,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_validator_failure_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_loop_pattern_summary")
async def get_loop_pattern_summary(
    repository_key: str | None = None,
    workflow_name: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    loop_thresholds: list[int] | None = None,
    include_planning_context: bool = False,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_loop_pattern_summary")
    try:
        data = await _analytics.get_loop_pattern_summary(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            since_utc=since_utc,
            until_utc=until_utc,
            loop_thresholds=loop_thresholds,
            include_planning_context=include_planning_context,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_loop_pattern_summary",
            status="success",
            data=data,
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_loop_pattern_summary",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_quality_grade_summary")
async def get_quality_grade_summary(
    repository_key: str | None = None,
    workflow_name: str | None = None,
    actor_email: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    include_planning_context: bool = False,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_quality_grade_summary")
    try:
        data = await _analytics.get_quality_grade_summary(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            actor_email=actor_email,
            since_utc=since_utc,
            until_utc=until_utc,
            include_planning_context=include_planning_context,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_quality_grade_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_entropy_sweep_targets")
async def list_entropy_sweep_targets(
    repository_key: str | None = None,
    workflow_name: str | None = None,
    actor_email: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    limit: int = 20,
    include_planning_context: bool = False,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "list_entropy_sweep_targets")
    try:
        data = await _analytics.list_entropy_sweep_targets(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            actor_email=actor_email,
            since_utc=since_utc,
            until_utc=until_utc,
            limit=limit,
            include_planning_context=include_planning_context,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="list_entropy_sweep_targets",
            status="success",
            data=data,
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(rid),
            tool_name="list_entropy_sweep_targets",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_convergence_recommendation_summary")
async def get_convergence_recommendation_summary(
    repository_key: str | None = None,
    workflow_name: str | None = None,
    actor_email: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    include_planning_context: bool = False,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_convergence_recommendation_summary")
    try:
        data = await _analytics.get_convergence_recommendation_summary(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            actor_email=actor_email,
            since_utc=since_utc,
            until_utc=until_utc,
            include_planning_context=include_planning_context,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_convergence_recommendation_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_failure_mode_playbooks")
async def get_failure_mode_playbooks(
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
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_failure_mode_playbooks")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_failure_mode_playbooks",
                status="error",
                error="repository_key is required",
            ).model_dump_json()
        if limit < 1:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_failure_mode_playbooks",
                status="error",
                error="limit must be >= 1",
            ).model_dump_json()
        if not _is_valid_timestamp(since_utc) or not _is_valid_timestamp(until_utc):
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_failure_mode_playbooks",
                status="error",
                error="since_utc and until_utc must be valid ISO-8601 timestamps",
            ).model_dump_json()
        data = await _playbooks.get_failure_mode_playbooks(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            phase_id=phase_id,
            agent_name=agent_name,
            request_kind=request_kind,
            selected_workflow_name=selected_workflow_name,
            selected_run_action=selected_run_action,
            since_utc=since_utc,
            until_utc=until_utc,
            limit=limit,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_failure_mode_playbooks",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_actor_adaptation_summary")
async def get_actor_adaptation_summary(
    repository_key: str,
    actor_email: str,
    workflow_name: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_actor_adaptation_summary")
    try:
        if not str(repository_key or "").strip():
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_actor_adaptation_summary",
                status="error",
                error="repository_key is required",
            ).model_dump_json()
        if not str(actor_email or "").strip():
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_actor_adaptation_summary",
                status="error",
                error="actor_email is required",
            ).model_dump_json()
        if not _is_valid_timestamp(since_utc) or not _is_valid_timestamp(until_utc):
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_actor_adaptation_summary",
                status="error",
                error="since_utc and until_utc must be valid ISO-8601 timestamps",
            ).model_dump_json()
        data = await _actor_adaptation.get_actor_adaptation_summary(
            get_pg_pool(),
            repository_key=repository_key,
            actor_email=actor_email,
            workflow_name=workflow_name,
            since_utc=since_utc,
            until_utc=until_utc,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_actor_adaptation_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_finding_pattern_summary")
async def get_finding_pattern_summary(
    repository_key: str,
    workflow_name: str | None = None,
    phase_id: str | None = None,
    agent_name: str | None = None,
    finding_kind_code: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    limit: int = 50,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_finding_pattern_summary")
    try:
        if limit < 0:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_finding_pattern_summary",
                status="error",
                error="limit must be >= 0",
            ).model_dump_json()
        if not _is_valid_timestamp(since_utc) or not _is_valid_timestamp(until_utc):
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_finding_pattern_summary",
                status="error",
                error="since_utc and until_utc must be valid ISO-8601 timestamps",
            ).model_dump_json()
        data = await _findings.get_finding_pattern_summary(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            phase_id=phase_id,
            agent_name=agent_name,
            finding_kind_code=finding_kind_code,
            since_utc=since_utc,
            until_utc=until_utc,
            limit=limit,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_finding_pattern_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_agent_failure_mode_summary")
async def get_agent_failure_mode_summary(
    repository_key: str,
    workflow_name: str | None = None,
    phase_id: str | None = None,
    agent_name: str | None = None,
    since_utc: str | None = None,
    until_utc: str | None = None,
    limit: int = 50,
    correlation_id: str | None = None,
) -> str:
    rid = new_run_id()
    bind_run_context(rid, correlation_id, "get_agent_failure_mode_summary")
    try:
        if limit < 0:
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_agent_failure_mode_summary",
                status="error",
                error="limit must be >= 0",
            ).model_dump_json()
        if not _is_valid_timestamp(since_utc) or not _is_valid_timestamp(until_utc):
            return WorkflowResult(
                run_id=str(rid),
                tool_name="get_agent_failure_mode_summary",
                status="error",
                error="since_utc and until_utc must be valid ISO-8601 timestamps",
            ).model_dump_json()
        data = await _findings.get_agent_failure_mode_summary(
            get_pg_pool(),
            repository_key=repository_key,
            workflow_name=workflow_name,
            phase_id=phase_id,
            agent_name=agent_name,
            since_utc=since_utc,
            until_utc=until_utc,
            limit=limit,
        )
        return WorkflowResult(
            run_id=str(rid),
            tool_name="get_agent_failure_mode_summary",
            status="success",
            data=data,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("create_project")
async def create_project(
    name: str,
    description: str | None = None,
    project_status_code: str = "PROJ_ACTIVE",
    repository_keys: list[str] | None = None,
    correlation_id: str | None = None,
) -> str:
    """Create a project and optionally link it to repositories."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "create_project")
    guard = check_remote_write_guard(get_settings(), "create_project")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        status_row = await _require_reference_value(pool, "PROJECT_STATUS", project_status_code, "create_project", run_id)
        if isinstance(status_row, str):
            return status_row
        result = await _planning.create_project(
            pool,
            project_status_id=status_row["id"],
            name=name,
            description=description,
            repository_keys=repository_keys,
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="create_project",
            status="success",
            data=result,
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="create_project",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("link_project_external_ref")
async def link_project_external_ref(
    project_key: str,
    external_system: str,
    external_object_type: str,
    external_id: str,
    external_parent_id: str | None = None,
    external_url: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Link a project to an external PM entity."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "link_project_external_ref")
    guard = check_remote_write_guard(get_settings(), "link_project_external_ref")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        project_id = await _planning.resolve_project_id(pool, project_key)
        result = await _planning.create_external_link(
            pool,
            "planning.project_external_links",
            "project_id",
            project_id,
            external_system,
            external_object_type,
            external_id,
            external_parent_id,
            external_url,
        )
        return WorkflowResult(run_id=str(run_id), tool_name="link_project_external_ref", status="success", data=result).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="link_project_external_ref", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_projects")
async def list_projects(
    project_status_code: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """List projects with optional status filter."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "list_projects")
    try:
        pool = get_pg_pool()
        status_id = None
        if project_status_code is not None:
            status_row = await _require_reference_value(pool, "PROJECT_STATUS", project_status_code, "list_projects", run_id)
            if isinstance(status_row, str):
                return status_row
            status_id = status_row["id"]
        projects = await _planning.list_projects(pool, status_id)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_projects",
            status="success",
            data={"projects": projects, "count": len(projects)},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("add_repository_to_project")
async def add_repository_to_project(
    repository_key: str,
    project_key: str | None = None,
    project_external_system: str | None = None,
    project_external_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Add a repository to a project's scope."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "add_repository_to_project")
    guard = check_remote_write_guard(get_settings(), "add_repository_to_project")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        resolved_project_id = await _resolve_project_identifier(
            pool,
            project_key=project_key,
            project_external_system=project_external_system,
            project_external_id=project_external_id,
        )
        repository_id = await _planning.resolve_repository_id(pool, repository_key)
        await _planning.add_repository_to_project(pool, resolved_project_id, repository_id)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="add_repository_to_project",
            status="success",
            data={"repository_key": repository_key},
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="add_repository_to_project", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_project_repositories")
async def list_project_repositories(
    project_key: str | None = None,
    project_external_system: str | None = None,
    project_external_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """List repositories linked to a project."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "list_project_repositories")
    try:
        pool = get_pg_pool()
        resolved_project_id = await _resolve_project_identifier(
            pool,
            project_key=project_key,
            project_external_system=project_external_system,
            project_external_id=project_external_id,
        )
        repos = await _planning.list_project_repositories(pool, resolved_project_id)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_project_repositories",
            status="success",
            data={"repositories": repos, "count": len(repos)},
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="list_project_repositories", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("remove_repository_from_project")
async def remove_repository_from_project(
    repository_key: str,
    project_key: str | None = None,
    project_external_system: str | None = None,
    project_external_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Remove a repository from a project's scope if no planning items still use it."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "remove_repository_from_project")
    guard = check_remote_write_guard(get_settings(), "remove_repository_from_project")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        resolved_project_id = await _resolve_project_identifier(
            pool,
            project_key=project_key,
            project_external_system=project_external_system,
            project_external_id=project_external_id,
        )
        repository_id = await _planning.resolve_repository_id(pool, repository_key)
        result = await _planning.remove_repository_from_project(pool, resolved_project_id, repository_id)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="remove_repository_from_project",
            status="success",
            data={"repository_key": repository_key, **result},
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="remove_repository_from_project", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("create_feature")
async def create_feature(
    title: str,
    *,
    project_key: str | None = None,
    description: str | None = None,
    feature_status_code: str = "FEAT_IDEA",
    priority_code: str = "PRIO_MEDIUM",
    project_external_system: str | None = None,
    project_external_id: str | None = None,
    repository_keys: list[str] | None = None,
    correlation_id: str | None = None,
) -> str:
    """Create a feature within a project."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "create_feature")
    guard = check_remote_write_guard(get_settings(), "create_feature")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        project_id = await _resolve_project_identifier(
            pool,
            project_key=project_key,
            project_external_system=project_external_system,
            project_external_id=project_external_id,
        )
        status_row = await _require_reference_value(pool, "FEATURE_STATUS", feature_status_code, "create_feature", run_id)
        if isinstance(status_row, str):
            return status_row
        priority_row = await _require_reference_value(pool, "PRIORITY", priority_code, "create_feature", run_id)
        if isinstance(priority_row, str):
            return priority_row
        result = await _planning.create_feature(
            pool,
            project_id=project_id,
            feature_status_id=status_row["id"],
            priority_id=priority_row["id"],
            title=title,
            description=description,
            repository_keys=repository_keys,
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="create_feature",
            status="success",
            data=result,
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="create_feature",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("link_feature_external_ref")
async def link_feature_external_ref(
    feature_key: str,
    external_system: str,
    external_object_type: str,
    external_id: str,
    external_parent_id: str | None = None,
    external_url: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Link a feature to an external PM entity."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "link_feature_external_ref")
    guard = check_remote_write_guard(get_settings(), "link_feature_external_ref")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        feature_id = await _planning.resolve_feature_id(pool, feature_key)
        result = await _planning.create_external_link(
            pool,
            "planning.feature_external_links",
            "feature_id",
            feature_id,
            external_system,
            external_object_type,
            external_id,
            external_parent_id,
            external_url,
        )
        return WorkflowResult(run_id=str(run_id), tool_name="link_feature_external_ref", status="success", data=result).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="link_feature_external_ref", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_features")
async def list_features(
    project_key: str | None = None,
    repository_key: str | None = None,
    feature_status_code: str | None = None,
    project_external_system: str | None = None,
    project_external_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """List features with optional project, repository, and status filters."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "list_features")
    try:
        pool = get_pg_pool()
        project_id = None
        if project_key or (project_external_system and project_external_id):
            project_id = await _resolve_project_identifier(
                pool,
                project_key=project_key,
                project_external_system=project_external_system,
                project_external_id=project_external_id,
            )
        status_id = None
        if feature_status_code is not None:
            status_row = await _require_reference_value(pool, "FEATURE_STATUS", feature_status_code, "list_features", run_id)
            if isinstance(status_row, str):
                return status_row
            status_id = status_row["id"]
        features = await _planning.list_features(pool, project_id, repository_key, status_id)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_features",
            status="success",
            data={"features": features, "count": len(features)},
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_features",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("add_repository_to_feature")
async def add_repository_to_feature(
    repository_key: str,
    feature_key: str | None = None,
    feature_external_system: str | None = None,
    feature_external_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Add a repository to a feature's scope."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "add_repository_to_feature")
    guard = check_remote_write_guard(get_settings(), "add_repository_to_feature")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        feature_ctx = await _resolve_feature_identifier(
            pool,
            feature_key=feature_key,
            feature_external_system=feature_external_system,
            feature_external_id=feature_external_id,
        )
        if feature_ctx is None:
            raise ValueError("feature_key or feature external reference is required")
        repository_id = await _planning.resolve_repository_id(pool, repository_key)
        await _planning.ensure_project_has_repository(pool, feature_ctx["project_id"], repository_id)
        await _planning.add_repository_to_feature(pool, feature_ctx["feature_id"], repository_id)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="add_repository_to_feature",
            status="success",
            data={"repository_key": repository_key},
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="add_repository_to_feature", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_feature_repositories")
async def list_feature_repositories(
    feature_key: str | None = None,
    feature_external_system: str | None = None,
    feature_external_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """List repositories linked to a feature."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "list_feature_repositories")
    try:
        pool = get_pg_pool()
        feature_ctx = await _resolve_feature_identifier(
            pool,
            feature_key=feature_key,
            feature_external_system=feature_external_system,
            feature_external_id=feature_external_id,
        )
        if feature_ctx is None:
            raise ValueError("feature_key or feature external reference is required")
        repos = await _planning.list_feature_repositories(pool, feature_ctx["feature_id"])
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_feature_repositories",
            status="success",
            data={"repositories": repos, "count": len(repos)},
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="list_feature_repositories", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("remove_repository_from_feature")
async def remove_repository_from_feature(
    repository_key: str,
    feature_key: str | None = None,
    feature_external_system: str | None = None,
    feature_external_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Remove a repository from a feature's scope if no tasks still use it."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "remove_repository_from_feature")
    guard = check_remote_write_guard(get_settings(), "remove_repository_from_feature")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        feature_ctx = await _resolve_feature_identifier(
            pool,
            feature_key=feature_key,
            feature_external_system=feature_external_system,
            feature_external_id=feature_external_id,
        )
        if feature_ctx is None:
            raise ValueError("feature_key or feature external reference is required")
        repository_id = await _planning.resolve_repository_id(pool, repository_key)
        result = await _planning.remove_repository_from_feature(pool, feature_ctx["feature_id"], repository_id)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="remove_repository_from_feature",
            status="success",
            data={"repository_key": repository_key, **result},
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="remove_repository_from_feature", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("create_task")
async def create_task(
    title: str,
    *,
    project_key: str | None = None,
    repository_key: str,
    description: str | None = None,
    feature_key: str | None = None,
    task_status_code: str = "TASK_TODO",
    priority_code: str = "PRIO_MEDIUM",
    project_external_system: str | None = None,
    project_external_id: str | None = None,
    feature_external_system: str | None = None,
    feature_external_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Create a task within a feature."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "create_task")
    guard = check_remote_write_guard(get_settings(), "create_task")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        project_id = await _resolve_project_identifier(
            pool,
            project_key=project_key,
            project_external_system=project_external_system,
            project_external_id=project_external_id,
        )
        repository_id = await _planning.resolve_repository_id(pool, repository_key)
        feature_id = None
        feature_ctx = await _resolve_feature_identifier(
            pool,
            feature_key=feature_key,
            feature_external_system=feature_external_system,
            feature_external_id=feature_external_id,
        )
        if feature_ctx is not None:
            if feature_ctx["project_id"] != project_id:
                return WorkflowResult(
                    run_id=str(run_id),
                    tool_name="create_task",
                    status="error",
                    error="feature_key does not belong to the given project_key",
                ).model_dump_json()
            feature_id = feature_ctx["feature_id"]
        status_row = await _require_reference_value(pool, "TASK_STATUS", task_status_code, "create_task", run_id)
        if isinstance(status_row, str):
            return status_row
        priority_row = await _require_reference_value(pool, "PRIORITY", priority_code, "create_task", run_id)
        if isinstance(priority_row, str):
            return priority_row
        result = await _planning.create_task(
            pool,
            project_id=project_id,
            repository_id=repository_id,
            feature_id=feature_id,
            task_status_id=status_row["id"],
            priority_id=priority_row["id"],
            title=title,
            description=description,
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="create_task",
            status="success",
            data=result,
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="create_task",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("link_task_external_ref")
async def link_task_external_ref(
    task_key: str,
    external_system: str,
    external_object_type: str,
    external_id: str,
    external_parent_id: str | None = None,
    external_url: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Link a task to an external PM entity."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "link_task_external_ref")
    guard = check_remote_write_guard(get_settings(), "link_task_external_ref")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        task_id = await _planning.resolve_task_id(pool, task_key)
        result = await _planning.create_external_link(
            pool,
            "planning.task_external_links",
            "task_id",
            task_id,
            external_system,
            external_object_type,
            external_id,
            external_parent_id,
            external_url,
        )
        return WorkflowResult(run_id=str(run_id), tool_name="link_task_external_ref", status="success", data=result).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="link_task_external_ref", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_tasks")
async def list_tasks(
    project_key: str | None = None,
    feature_key: str | None = None,
    repository_key: str | None = None,
    task_status_code: str | None = None,
    project_external_system: str | None = None,
    project_external_id: str | None = None,
    feature_external_system: str | None = None,
    feature_external_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """List tasks with optional feature, repository, and status filters."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "list_tasks")
    try:
        pool = get_pg_pool()
        project_id = None
        if project_key or (project_external_system and project_external_id):
            project_id = await _resolve_project_identifier(
                pool,
                project_key=project_key,
                project_external_system=project_external_system,
                project_external_id=project_external_id,
            )
        feature_ctx = await _resolve_feature_identifier(
            pool,
            feature_key=feature_key,
            feature_external_system=feature_external_system,
            feature_external_id=feature_external_id,
        )
        feature_id = feature_ctx["feature_id"] if feature_ctx else None
        status_id = None
        if task_status_code is not None:
            status_row = await _require_reference_value(pool, "TASK_STATUS", task_status_code, "list_tasks", run_id)
            if isinstance(status_row, str):
                return status_row
            status_id = status_row["id"]
        tasks = await _planning.list_tasks(pool, project_id, feature_id, repository_key, status_id)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_tasks",
            status="success",
            data={"tasks": tasks, "count": len(tasks)},
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_tasks",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("link_repository_external_ref")
async def link_repository_external_ref(
    repository_key: str,
    external_system: str,
    external_object_type: str,
    external_id: str,
    external_parent_id: str | None = None,
    external_url: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Link a repository to an external PM entity."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "link_repository_external_ref")
    guard = check_remote_write_guard(get_settings(), "link_repository_external_ref")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        repository_id = await _planning.resolve_repository_id(pool, repository_key)
        result = await _planning.create_external_link(
            pool,
            "catalog.repository_external_links",
            "repository_id",
            repository_id,
            external_system,
            external_object_type,
            external_id,
            external_parent_id,
            external_url,
        )
        return WorkflowResult(run_id=str(run_id), tool_name="link_repository_external_ref", status="success", data=result).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(run_id=str(run_id), tool_name="link_repository_external_ref", status="error", error=str(exc)).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("link_task_to_workflow_run")
async def link_task_to_workflow_run(
    task_key: str,
    workflow_run_id: str,
    relation_type: str = "implements",
    correlation_id: str | None = None,
) -> str:
    """Link a planning task to a workflow run."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "link_task_to_workflow_run")
    guard = check_remote_write_guard(get_settings(), "link_task_to_workflow_run")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        task_id = await _planning.resolve_task_id(pool, task_key)
        result = await _planning.link_task_to_workflow_run(pool, task_id, workflow_run_id, relation_type)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="link_task_to_workflow_run",
            status="success",
            data=result,
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="link_task_to_workflow_run",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_backlog")
async def get_backlog(
    project_key: str | None = None,
    repository_key: str | None = None,
    limit: int = 100,
    correlation_id: str | None = None,
) -> str:
    """Return backlog-shaped features and tasks for a project or repository."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "get_backlog")
    try:
        pool = get_pg_pool()
        project_id = await _planning.resolve_project_id(pool, project_key) if project_key else None
        backlog = await _planning.get_backlog(pool, project_id=project_id, repository_key=repository_key, limit=limit)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="get_backlog",
            status="success",
            data=backlog,
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="get_backlog",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("create_working_session")
async def create_working_session(
    repository_key: str, correlation_id: str | None = None
) -> str:
    """Create a new working session for tracking investigation state."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "create_working_session")
    guard = check_remote_write_guard(get_settings(), "create_working_session")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        from memory_knowledge.admin.working_memory import create_session

        session_key = await create_session(get_pg_pool(), repository_key)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="create_working_session",
            status="success",
            data={"session_key": str(session_key)},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("record_working_observation")
async def record_working_observation(
    session_key: str,
    entity_key: str,
    observation_type: str,
    observation_text: str,
    correlation_id: str | None = None,
) -> str:
    """Record an observation (inspection, hypothesis, plan note) in a working session."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "record_working_observation")
    guard = check_remote_write_guard(get_settings(), "record_working_observation")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        from memory_knowledge.admin.working_memory import record_observation

        obs_id = await record_observation(
            get_pg_pool(), uuid.UUID(session_key),
            entity_key, observation_type, observation_text,
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="record_working_observation",
            status="success",
            data={"observation_id": obs_id},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_working_session_context")
async def get_working_session_context(
    session_key: str, correlation_id: str | None = None
) -> str:
    """Get all observations from a working session."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "get_working_session_context")
    try:
        from memory_knowledge.admin.working_memory import get_session_observations

        observations = await get_session_observations(
            get_pg_pool(), uuid.UUID(session_key)
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="get_working_session_context",
            status="success",
            data={"session_key": session_key, "observations": observations},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("run_route_intelligence_workflow")
async def run_route_intelligence_workflow(
    repository_key: str, query: str, correlation_id: str | None = None
) -> str:
    """Provide routing history and support for route decisions."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_route_intelligence_workflow")
    try:
        result = await _route_intelligence.run(
            repository_key, query, run_id,
            pool=get_pg_pool(),
        )
        return result.model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("create_intake_session")
async def create_intake_session(
    mode: str = "full",
    title: str | None = None,
    actor_email: str | None = None,
    actor_id: str | None = None,
    repository_key: str | None = None,
    project_key: str | None = None,
    feature_key: str | None = None,
    task_key: str | None = None,
    metadata: dict | None = None,
    correlation_id: str | None = None,
) -> str:
    """Create a durable brainstorm intake session."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "create_intake_session")
    guard = check_remote_write_guard(get_settings(), "create_intake_session")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        data = await _intake.create_session(
            get_pg_pool(),
            mode=mode,
            title=title,
            actor_email=actor_email,
            actor_id=actor_id,
            repository_key=repository_key,
            project_key=project_key,
            feature_key=feature_key,
            task_key=task_key,
            metadata=metadata,
        )
        return _intake_result_json(run_id, "create_intake_session", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="create_intake_session",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("append_intake_event")
async def append_intake_event(
    session_key: str,
    role: str,
    event_type: str,
    content_text: str | None = None,
    content_json: dict | None = None,
    attachment_refs: list | None = None,
    source: str | None = "mcp",
    model_provider: str | None = None,
    model_name: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict | None = None,
    correlation_id: str | None = None,
) -> str:
    """Append one immutable intake transcript or system event."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "append_intake_event")
    guard = check_remote_write_guard(get_settings(), "append_intake_event")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        data = await _intake.append_event(
            get_pg_pool(),
            session_key=session_key,
            role=role,
            event_type=event_type,
            content_text=content_text,
            content_json=content_json,
            attachment_refs=attachment_refs,
            source=source,
            model_provider=model_provider,
            model_name=model_name,
            idempotency_key=idempotency_key,
            metadata=metadata,
        )
        return _intake_result_json(run_id, "append_intake_event", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="append_intake_event",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("get_intake_session_state")
async def get_intake_session_state(
    session_key: str,
    include_recent_events: bool = True,
    recent_event_limit: int = 10,
    include_latest_draft: bool = True,
    include_asset_refs: bool = True,
    correlation_id: str | None = None,
) -> str:
    """Return compact intake state for stateless prompt reconstruction."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "get_intake_session_state")
    try:
        data = await _intake.get_session_state(
            get_pg_pool(),
            session_key=session_key,
            include_recent_events=include_recent_events,
            recent_event_limit=recent_event_limit,
            include_latest_draft=include_latest_draft,
            include_asset_refs=include_asset_refs,
        )
        return _intake_result_json(run_id, "get_intake_session_state", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="get_intake_session_state",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("update_intake_distilled_context")
async def update_intake_distilled_context(
    session_key: str,
    expected_revision: int,
    updated_from_sequence: int,
    distilled_context: dict,
    metadata: dict | None = None,
    correlation_id: str | None = None,
) -> str:
    """Overwrite current distilled intake context with revision protection."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "update_intake_distilled_context")
    guard = check_remote_write_guard(get_settings(), "update_intake_distilled_context")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        data = await _intake.update_distilled_context(
            get_pg_pool(),
            session_key=session_key,
            expected_revision=expected_revision,
            updated_from_sequence=updated_from_sequence,
            distilled_context=distilled_context,
            metadata=metadata,
        )
        return _intake_result_json(run_id, "update_intake_distilled_context", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="update_intake_distilled_context",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("save_intake_draft_revision")
async def save_intake_draft_revision(
    session_key: str,
    status: str = "draft",
    draft_json: dict | None = None,
    draft_markdown: str | None = None,
    source_distilled_revision: int | None = None,
    source_event_range: dict | None = None,
    metadata: dict | None = None,
    correlation_id: str | None = None,
) -> str:
    """Persist a versioned intake draft snapshot."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "save_intake_draft_revision")
    guard = check_remote_write_guard(get_settings(), "save_intake_draft_revision")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        data = await _intake.save_draft_revision(
            get_pg_pool(),
            session_key=session_key,
            status=status,
            draft_json=draft_json or {},
            draft_markdown=draft_markdown,
            source_distilled_revision=source_distilled_revision,
            source_event_range=source_event_range,
            metadata=metadata,
        )
        return _intake_result_json(run_id, "save_intake_draft_revision", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="save_intake_draft_revision",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_intake_events")
async def list_intake_events(
    session_key: str,
    from_sequence: int = 1,
    to_sequence: int | None = None,
    limit: int = 100,
    correlation_id: str | None = None,
) -> str:
    """Return exact intake events for replay, review, or re-distillation."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "list_intake_events")
    try:
        data = await _intake.list_events(
            get_pg_pool(),
            session_key=session_key,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            limit=limit,
        )
        return _intake_result_json(run_id, "list_intake_events", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_intake_events",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("add_intake_asset_ref")
async def add_intake_asset_ref(
    session_key: str,
    event_key: str,
    asset_type: str,
    display_name: str,
    uri: str,
    mime_type: str | None = None,
    description: str | None = None,
    metadata: dict | None = None,
    correlation_id: str | None = None,
) -> str:
    """Attach metadata for an external intake asset."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "add_intake_asset_ref")
    guard = check_remote_write_guard(get_settings(), "add_intake_asset_ref")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        data = await _intake.add_asset_ref(
            get_pg_pool(),
            session_key=session_key,
            event_key=event_key,
            asset_type=asset_type,
            display_name=display_name,
            uri=uri,
            mime_type=mime_type,
            description=description,
            metadata=metadata,
        )
        return _intake_result_json(run_id, "add_intake_asset_ref", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="add_intake_asset_ref",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("finalize_intake_session")
async def finalize_intake_session(
    session_key: str,
    final_draft_revision: int,
    repository_key: str | None = None,
    project_key: str | None = None,
    feature_key: str | None = None,
    task_key: str | None = None,
    metadata: dict | None = None,
    correlation_id: str | None = None,
) -> str:
    """Finalize an intake session and pin its final draft revision."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "finalize_intake_session")
    guard = check_remote_write_guard(get_settings(), "finalize_intake_session")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        data = await _intake.finalize_session(
            get_pg_pool(),
            session_key=session_key,
            final_draft_revision=final_draft_revision,
            repository_key=repository_key,
            project_key=project_key,
            feature_key=feature_key,
            task_key=task_key,
            metadata=metadata,
        )
        return _intake_result_json(run_id, "finalize_intake_session", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="finalize_intake_session",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("link_intake_workflow_run")
async def link_intake_workflow_run(
    session_key: str,
    run_id: str,
    workflow_name: str,
    link_type: str,
    repository_key: str | None = None,
    project_key: str | None = None,
    feature_key: str | None = None,
    task_key: str | None = None,
    metadata: dict | None = None,
    correlation_id: str | None = None,
) -> str:
    """Link an intake session to a downstream workflow run."""
    tool_run_id = new_run_id()
    bind_run_context(tool_run_id, correlation_id, "link_intake_workflow_run")
    guard = check_remote_write_guard(get_settings(), "link_intake_workflow_run")
    if guard is not None:
        guard.run_id = str(tool_run_id)
        return guard.model_dump_json()
    try:
        data = await _intake.link_workflow_run(
            get_pg_pool(),
            session_key=session_key,
            run_id=run_id,
            workflow_name=workflow_name,
            link_type=link_type,
            repository_key=repository_key,
            project_key=project_key,
            feature_key=feature_key,
            task_key=task_key,
            metadata=metadata,
        )
        return _intake_result_json(tool_run_id, "link_intake_workflow_run", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(tool_run_id),
            tool_name="link_intake_workflow_run",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("list_intake_sessions_by_actor")
async def list_intake_sessions_by_actor(
    actor_email: str,
    include_terminal: bool = False,
    status: str | None = None,
    limit: int = 50,
    correlation_id: str | None = None,
) -> str:
    """Recover active or historical intake sessions by actor email."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "list_intake_sessions_by_actor")
    try:
        data = await _intake.list_sessions_by_actor(
            get_pg_pool(),
            actor_email=actor_email,
            include_terminal=include_terminal,
            status=status,
            limit=limit,
        )
        return _intake_result_json(run_id, "list_intake_sessions_by_actor", data)
    except Exception as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="list_intake_sessions_by_actor",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("register_repository")
async def register_repository(
    repository_key: str,
    name: str,
    origin_url: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Register or update a repository in the catalog. Must be called before ingestion."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "register_repository")
    guard = check_remote_write_guard(get_settings(), "register_repository")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        pool = get_pg_pool()
        row = await pool.fetchrow(
            """
            INSERT INTO catalog.repositories (repository_key, name, origin_url)
            VALUES ($1, $2, $3)
            ON CONFLICT (repository_key) DO UPDATE
                SET name = EXCLUDED.name,
                    origin_url = EXCLUDED.origin_url,
                    updated_utc = NOW()
            RETURNING id, (xmax = 0) AS is_insert
            """,
            repository_key,
            name,
            origin_url,
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="register_repository",
            status="success",
            data={
                "repository_key": repository_key,
                "repository_id": row["id"],
                "created": row["is_insert"],
            },
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("end_working_session")
async def end_working_session(
    session_key: str, correlation_id: str | None = None
) -> str:
    """End a working session, marking it as completed."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "end_working_session")
    guard = check_remote_write_guard(get_settings(), "end_working_session")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        from memory_knowledge.admin.working_memory import end_session

        await end_session(
            get_pg_pool(),
            uuid.UUID(session_key),
            neo4j_driver=get_neo4j_driver(),
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="end_working_session",
            status="success",
            data={"session_key": session_key},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("submit_route_feedback")
async def submit_route_feedback(
    route_execution_id: int,
    usefulness_score: float | None = None,
    precision_score: float | None = None,
    expansion_needed: bool | None = None,
    notes: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Submit feedback on a retrieval route execution to improve routing."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "submit_route_feedback")
    guard = check_remote_write_guard(get_settings(), "submit_route_feedback")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        # Validate score ranges
        for name, val in [("usefulness_score", usefulness_score), ("precision_score", precision_score)]:
            if val is not None and not (0.0 <= val <= 1.0):
                return WorkflowResult(
                    run_id=str(run_id),
                    tool_name="submit_route_feedback",
                    status="error",
                    error=f"{name} must be between 0.0 and 1.0, got {val}",
                ).model_dump_json()

        pool = get_pg_pool()
        # Validate execution exists
        row = await pool.fetchrow(
            "SELECT id FROM routing.route_executions WHERE id = $1",
            route_execution_id,
        )
        if row is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name="submit_route_feedback",
                status="error",
                error=f"Route execution not found: {route_execution_id}",
            ).model_dump_json()

        from memory_knowledge.projections.pg_writer import record_route_feedback
        await record_route_feedback(
            pool, route_execution_id,
            usefulness_score=usefulness_score,
            precision_score=precision_score,
            expansion_needed=expansion_needed,
            notes=notes,
            is_auto=False,
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="submit_route_feedback",
            status="success",
            data={"route_execution_id": route_execution_id},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("export_repo_memory_tool")
async def export_repo_memory_tool(
    repository_key: str, correlation_id: str | None = None
) -> str:
    """Export repository memory as JSONL for backup or migration."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "export_repo_memory")
    try:
        from memory_knowledge.admin.export_import import export_repo_memory

        lines = await export_repo_memory(get_pg_pool(), repository_key)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="export_repo_memory",
            status="success",
            data={"repository_key": repository_key, "lines": lines, "line_count": len(lines)},
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("import_repo_memory_tool")
async def import_repo_memory_tool(
    data: str, correlation_id: str | None = None
) -> str:
    """Import repository memory from JSONL data."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "import_repo_memory")
    guard = check_remote_write_guard(get_settings(), "import_repo_memory")
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        max_bytes = get_settings().max_import_size_mb * 1024 * 1024
        if len(data.encode("utf-8")) > max_bytes:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name="import_repo_memory",
                status="error",
                error=f"Import data exceeds {get_settings().max_import_size_mb}MB limit",
            ).model_dump_json()

        from memory_knowledge.admin.export_import import import_repo_memory

        lines = [line for line in data.strip().split("\n") if line.strip()]
        result = await import_repo_memory(get_pg_pool(), lines)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="import_repo_memory",
            status="success",
            data=result,
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("purge_repository")
async def purge_repository(
    repository_key: str, correlation_id: str | None = None
) -> str:
    """Purge all repo-owned data across PostgreSQL, Qdrant, and Neo4j."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "purge_repository")
    guard = check_remote_write_guard(get_settings(), "purge_repository", is_destructive=True)
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        from memory_knowledge.admin.purge import purge_repository as _purge_repository

        result = await _purge_repository(
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            repository_key=repository_key,
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="purge_repository",
            status="success",
            data=result,
        ).model_dump_json()
    except ValueError as exc:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="purge_repository",
            status="error",
            error=str(exc),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("rebuild_revision_workflow")
async def rebuild_revision_workflow(
    repository_key: str,
    commit_sha: str,
    repair_scope: str = "full",
    correlation_id: str | None = None,
) -> str:
    """Re-project PG canonical data for a specific revision to Qdrant and/or Neo4j."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "rebuild_revision_workflow")
    guard = check_remote_write_guard(get_settings(), "rebuild_revision_workflow", is_destructive=True)
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        from memory_knowledge.integrity.repair_drift import rebuild_revision

        report = await rebuild_revision(
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            settings=get_settings(),
            repository_key=repository_key,
            commit_sha=commit_sha,
            repair_scope=repair_scope,
        )
        status = "success" if not report.errors else "partial"
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="rebuild_revision_workflow",
            status=status,
            data=report.model_dump(),
        ).model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
@track_tool_metrics("run_embedding_backfill")
async def run_embedding_backfill(
    repository_key: str, correlation_id: str | None = None
) -> str:
    """Backfill missing Qdrant embeddings from PG canonical data."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_embedding_backfill")
    guard = check_remote_write_guard(get_settings(), "run_embedding_backfill", is_destructive=True)
    if guard is not None:
        guard.run_id = str(run_id)
        return guard.model_dump_json()
    try:
        from memory_knowledge.integrity.embedding_backfill import backfill_embeddings

        stats = await backfill_embeddings(
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            settings=get_settings(),
            repository_key=repository_key,
        )
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_embedding_backfill",
            status="success",
            data=stats,
        ).model_dump_json()
    finally:
        clear_run_context()


# ---------------------------------------------------------------------------
# Starlette lifecycle
# ---------------------------------------------------------------------------


def _mask_url(url: str) -> str:
    """Show host:port but mask credentials in URLs."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.password:
        masked = parsed._replace(
            netloc=f"***:***@{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")
        )
        return masked.geturl()
    return url


@asynccontextmanager
async def app_lifespan(app: Starlette):
    # STARTUP — DB pools owned by Starlette, not MCP
    settings = Settings()
    configure_logging(settings.log_level)
    init_settings(settings)

    # Seed Codex auth from Key Vault before validation (required for Azure deployment)
    if settings.auth_mode == "codex" and settings.azure_keyvault_name:
        from memory_knowledge.auth.credential_refresh import seed_from_keyvault

        seed_status = await seed_from_keyvault(
            settings.azure_keyvault_name, settings.codex_auth_path
        )
        logger.info("codex_kv_seed_result", status=seed_status)

    if settings.azure_keyvault_name:
        from memory_knowledge.auth.credential_refresh import (
            seed_github_app_secrets_from_keyvault,
        )

        github_seed_status = await seed_github_app_secrets_from_keyvault(
            settings.azure_keyvault_name,
            settings.github_app_config_path,
            config_secret_name=settings.kv_github_app_config_secret_name,
        )
        logger.info("github_app_kv_seed_result", status=github_seed_status)

    # Validate auth configuration — fail fast
    if settings.auth_mode == "codex":
        from memory_knowledge.auth.codex import codex_token_provider

        try:
            await codex_token_provider(settings.codex_auth_path)
            logger.info("codex_auth_validated", auth_path=settings.codex_auth_path)
        except RuntimeError as e:
            logger.error("codex_auth_failed", error=str(e))
            raise
    elif not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required when AUTH_MODE=api_key"
        )

    logger.info("startup_begin")

    from memory_knowledge.auth.github_auth import init_github_auth_registry

    github_registry = init_github_auth_registry(settings)
    logger.info(
        "github_auth_registry_initialized",
        configured=github_registry.is_configured(),
        org_count=len(github_registry.orgs) if hasattr(github_registry, "orgs") else 0,
    )

    # Seed DB secrets from Azure Key Vault if configured
    if settings.azure_keyvault_name and settings.data_mode == "remote":
        from memory_knowledge.auth.credential_refresh import fetch_kv_secret
        for env_var, secret_name in [
            ("DATABASE_URL", settings.kv_pg_secret_name),
            ("QDRANT_API_KEY", settings.kv_qdrant_secret_name),
            ("NEO4J_PASSWORD", settings.kv_neo4j_secret_name),
        ]:
            if not os.environ.get(env_var):
                value = await fetch_kv_secret(settings.azure_keyvault_name, secret_name)
                if value:
                    os.environ[env_var] = value
                    logger.info("kv_secret_seeded", env_var=env_var)
        # Re-create settings to pick up seeded values
        settings = Settings()
        init_settings(settings)

    await init_postgres(settings)
    logger.info("postgres_connected")

    neo4j_driver = None
    try:
        neo4j_driver = await init_neo4j(settings)
        await apply_constraints(neo4j_driver)
        logger.info("neo4j_connected")
    except Exception as exc:
        logger.warning("neo4j_startup_degraded", error=str(exc))

    qdrant_client = await init_qdrant(settings)
    await ensure_collections(qdrant_client, settings)
    logger.info("qdrant_connected")

    # Startup mode summary
    logger.info(
        "startup_mode_summary",
        data_mode=settings.data_mode,
        pg_mode=settings.effective_mode("pg"),
        pg_url=_mask_url(settings.database_url),
        pg_ssl=settings.pg_ssl,
        qdrant_mode=settings.effective_mode("qdrant"),
        qdrant_url=settings.qdrant_url,
        qdrant_api_key_set=settings.qdrant_api_key is not None,
        neo4j_mode=settings.effective_mode("neo4j"),
        neo4j_uri=settings.neo4j_uri,
        allow_remote_writes=settings.allow_remote_writes,
        allow_remote_rebuilds=settings.allow_remote_rebuilds,
    )

    # Environment fingerprinting
    try:
        pg_ver = await get_pg_pool().fetchval("SELECT version()")
        logger.info("db_fingerprint_pg", version=pg_ver[:60])
    except Exception:
        pass
    try:
        if neo4j_driver is not None:
            neo4j_result = await neo4j_driver.execute_query(
                "CALL dbms.components() YIELD versions RETURN versions[0] AS v"
            )
            logger.info(
                "db_fingerprint_neo4j",
                version=neo4j_result.records[0]["v"] if neo4j_result.records else "?",
            )
    except Exception:
        pass

    # Load routing archetypes into Qdrant (requires OpenAI — skip on failure)
    try:
        from memory_knowledge.routing.archetype_loader import load_archetypes

        count = await load_archetypes(get_pg_pool(), qdrant_client, settings)
        logger.info("routing_archetypes_loaded", count=count)
    except Exception as e:
        logger.warning("archetype_loading_skipped", error=str(e))

    # Start job dispatcher
    from memory_knowledge.jobs.dispatcher import JobDispatcher, register_job_type

    register_job_type("ingestion", _ingestion.run)
    register_job_type("repair", _repair_rebuild.run)
    register_job_type("integrity_audit", _integrity_audit.run)

    _dispatcher = JobDispatcher(poll_interval=15.0, max_concurrent=3)
    await _dispatcher.start(get_pg_pool(), settings)

    # Start Codex token refresh manager
    _token_manager = None
    if settings.auth_mode == "codex" and settings.codex_refresh_enabled:
        from memory_knowledge.auth.credential_refresh import CodexTokenManager

        _token_manager = CodexTokenManager(
            codex_auth_path=settings.codex_auth_path,
            keyvault_name=settings.azure_keyvault_name or None,
            check_interval=settings.codex_check_interval,
            refresh_after_days=settings.codex_refresh_after_days,
            daily_refresh_utc_hour=settings.codex_daily_refresh_hour,
            writeback_enabled=settings.codex_kv_writeback_enabled,
        )
        await _token_manager.start()

    logger.info("startup_complete")

    # MCP session manager must run in outer lifespan because Starlette
    # Mount does not propagate lifespan events to mounted sub-apps
    async with mcp.session_manager.run():
        yield

    # SHUTDOWN — stop Codex MCP client, token manager, dispatcher, drain tasks, close connections
    logger.info("shutdown_begin")
    from memory_knowledge.llm.codex_mcp import CodexMcpClient
    await CodexMcpClient.get().shutdown()
    if _token_manager:
        await _token_manager.stop()
    await _dispatcher.stop()
    if _background_tasks:
        tasks = list(_background_tasks)
        logger.info("draining_background_tasks", count=len(tasks))
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.warning("shutdown_drain_timeout", remaining=len(tasks))
    await close_qdrant()
    await close_neo4j()
    await close_postgres()
    logger.info("shutdown_complete")


async def health_endpoint(request: Request) -> JSONResponse:
    result = await health_check()
    return JSONResponse(result)


async def readiness_endpoint(request: Request) -> JSONResponse:
    result = await readiness_check()
    status_code = 200 if result["status"] == "ready" else 503
    return JSONResponse(result, status_code=status_code)


async def metrics_endpoint(request: Request) -> Response:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from memory_knowledge.middleware.auth import ApiKeyAuthMiddleware

_cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "*").split(",")

# Starlette app with health routes + mounted MCP sub-app
app = Starlette(
    routes=[
        Route("/health", health_endpoint),
        Route("/ready", readiness_endpoint),
        Route("/metrics", metrics_endpoint),
        Route("/.well-known/oauth-authorization-server",
              lambda r: JSONResponse({"error": "oauth_not_supported"}, status_code=404)),
        Route("/.well-known/openid-configuration",
              lambda r: JSONResponse({"error": "not_supported"}, status_code=404)),
        Route("/.well-known/oauth-protected-resource",
              lambda r: JSONResponse({"error": "not_supported"}, status_code=404)),
        Route("/.well-known/oauth-protected-resource/{path:path}",
              lambda r: JSONResponse({"error": "not_supported"}, status_code=404)),
        Route("/register",
              lambda r: JSONResponse({"error": "registration_not_supported"}, status_code=404),
              methods=["POST"]),
        Mount("/mcp", app=mcp.streamable_http_app()),
    ],
    middleware=[
        Middleware(ApiKeyAuthMiddleware),
        Middleware(CORSMiddleware, allow_origins=_cors_origins,
                  allow_methods=["*"], allow_headers=["*"]),
    ],
    lifespan=app_lifespan,
)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("SERVER_PORT", "8000"))
    uvicorn.run(
        "memory_knowledge.server:app",
        host="0.0.0.0",
        port=port,
    )
