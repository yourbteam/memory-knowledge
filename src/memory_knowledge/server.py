from __future__ import annotations

import asyncio
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


async def _run_ingestion_background(
    job_id: uuid.UUID, run_id: uuid.UUID,
    repository_key: str, commit_sha: str, branch_name: str,
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
        pool=pool,
        qdrant_client=get_qdrant_client(),
        neo4j_driver=get_neo4j_driver(),
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
        neo4j_driver=get_neo4j_driver(),
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
        neo4j_driver=get_neo4j_driver(),
        settings=settings,
    )


def _on_task_done(task: asyncio.Task) -> None:
    """Remove task from tracking set and log any unhandled exceptions."""
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        logger.error("background_task_failed", error=str(task.exception()))


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

        pool = get_pg_pool()
        job_id = await create_job(
            pool, run_id, "ingestion", "run_repo_ingestion_workflow",
            repository_key, commit_sha, branch_name, str(correlation_id) if correlation_id else None,
        )
        task = asyncio.create_task(
            _run_ingestion_background(job_id, run_id, repository_key, commit_sha, branch_name)
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

    neo4j_driver = await init_neo4j(settings)
    await apply_constraints(neo4j_driver)
    logger.info("neo4j_connected")

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
        neo4j_result = await neo4j_driver.execute_query(
            "CALL dbms.components() YIELD versions RETURN versions[0] AS v"
        )
        logger.info("db_fingerprint_neo4j",
                     version=neo4j_result.records[0]["v"] if neo4j_result.records else "?")
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
