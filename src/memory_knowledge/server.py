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
mcp = FastMCP(
    "memory-knowledge",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


# ---------------------------------------------------------------------------
# MCP Tool registrations
# ---------------------------------------------------------------------------


@mcp.tool()
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
async def run_repo_ingestion_workflow(
    repository_key: str,
    commit_sha: str,
    branch_name: str,
    correlation_id: str | None = None,
) -> str:
    """Seed or refresh repository knowledge from a commit. Returns job_id for polling."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_repo_ingestion_workflow")
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
async def run_integrity_audit_workflow(
    repository_key: str, correlation_id: str | None = None
) -> str:
    """Check mechanical layer trustworthiness across stores."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_integrity_audit_workflow")
    try:
        result = await _integrity_audit.run(
            repository_key, run_id,
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            settings=get_settings(),
        )
        return result.model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
async def run_repair_rebuild_workflow(
    repository_key: str,
    repair_scope: str = "full",
    correlation_id: str | None = None,
) -> str:
    """Repair drift or rebuild a memory slice. Returns job_id for polling. Scope: full, qdrant, or neo4j."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_repair_rebuild_workflow")
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
async def create_working_session(
    repository_key: str, correlation_id: str | None = None
) -> str:
    """Create a new working session for tracking investigation state."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "create_working_session")
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
async def register_repository(
    repository_key: str,
    name: str,
    origin_url: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """Register or update a repository in the catalog. Must be called before ingestion."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "register_repository")
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
async def end_working_session(
    session_key: str, correlation_id: str | None = None
) -> str:
    """End a working session, marking it as completed."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "end_working_session")
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

        await pool.execute(
            """
            INSERT INTO routing.route_feedback
                (route_execution_id, usefulness_score, precision_score,
                 expansion_needed, notes)
            VALUES ($1, $2, $3, $4, $5)
            """,
            route_execution_id,
            usefulness_score,
            precision_score,
            expansion_needed,
            notes,
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
async def import_repo_memory_tool(
    data: str, correlation_id: str | None = None
) -> str:
    """Import repository memory from JSONL data."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "import_repo_memory")
    try:
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
async def rebuild_revision_workflow(
    repository_key: str,
    commit_sha: str,
    repair_scope: str = "full",
    correlation_id: str | None = None,
) -> str:
    """Re-project PG canonical data for a specific revision to Qdrant and/or Neo4j."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "rebuild_revision_workflow")
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


# ---------------------------------------------------------------------------
# Starlette lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def app_lifespan(app: Starlette):
    # STARTUP — DB pools owned by Starlette, not MCP
    settings = Settings()
    configure_logging(settings.log_level)
    init_settings(settings)

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

    await init_postgres(settings)
    logger.info("postgres_connected")

    neo4j_driver = await init_neo4j(settings)
    await apply_constraints(neo4j_driver)
    logger.info("neo4j_connected")

    qdrant_client = await init_qdrant(settings)
    await ensure_collections(qdrant_client, settings)
    logger.info("qdrant_connected")

    # Load routing archetypes into Qdrant (requires OpenAI — skip on failure)
    try:
        from memory_knowledge.routing.archetype_loader import load_archetypes

        count = await load_archetypes(get_pg_pool(), qdrant_client, settings)
        logger.info("routing_archetypes_loaded", count=count)
    except Exception as e:
        logger.warning("archetype_loading_skipped", error=str(e))

    logger.info("startup_complete")

    # MCP session manager must run in outer lifespan because Starlette
    # Mount does not propagate lifespan events to mounted sub-apps
    async with mcp.session_manager.run():
        yield

    # SHUTDOWN — drain background tasks before closing connections
    logger.info("shutdown_begin")
    if _background_tasks:
        tasks = list(_background_tasks)
        logger.info("draining_background_tasks", count=len(tasks))
        await asyncio.gather(*tasks, return_exceptions=True)
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


# Starlette app with health routes + mounted MCP sub-app
app = Starlette(
    routes=[
        Route("/health", health_endpoint),
        Route("/ready", readiness_endpoint),
        Route("/metrics", metrics_endpoint),
        Mount("/mcp", app=mcp.streamable_http_app()),
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
