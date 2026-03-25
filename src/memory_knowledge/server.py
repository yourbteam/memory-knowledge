from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP

from memory_knowledge.config import Settings, init_settings, get_settings
from memory_knowledge.db.health import health_check, readiness_check
from memory_knowledge.db.neo4j import apply_constraints, close_neo4j, init_neo4j
from memory_knowledge.db.postgres import close_postgres, init_postgres
from memory_knowledge.db.qdrant import close_qdrant, ensure_collections, init_qdrant
from memory_knowledge.observability.logging import configure_logging
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
        result = await _impact_analysis.run(repository_key, query, run_id)
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
        result = await _blueprint_refinement.run(repository_key, query, run_id)
        return result.model_dump_json()
    finally:
        clear_run_context()


@mcp.tool()
async def run_repo_ingestion_workflow(
    repository_key: str,
    commit_sha: str,
    branch_name: str,
    correlation_id: str | None = None,
) -> str:
    """Seed or refresh repository knowledge from a commit."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_repo_ingestion_workflow")
    try:
        result = await _ingestion.run(
            repository_key, commit_sha, branch_name, run_id,
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            settings=get_settings(),
        )
        return result.model_dump_json()
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
    """Repair drift or rebuild a memory slice. Scope: full, qdrant, or neo4j."""
    run_id = new_run_id()
    bind_run_context(run_id, correlation_id, "run_repair_rebuild_workflow")
    try:
        result = await _repair_rebuild.run(
            repository_key, run_id,
            repair_scope=repair_scope,
            pool=get_pg_pool(),
            qdrant_client=get_qdrant_client(),
            neo4j_driver=get_neo4j_driver(),
            settings=get_settings(),
        )
        return result.model_dump_json()
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

    logger.info("startup_complete")

    # MCP session manager must run in outer lifespan because Starlette
    # Mount does not propagate lifespan events to mounted sub-apps
    async with mcp.session_manager.run():
        yield

    # SHUTDOWN (reverse of startup order)
    logger.info("shutdown_begin")
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


# Starlette app with health routes + mounted MCP sub-app
app = Starlette(
    routes=[
        Route("/health", health_endpoint),
        Route("/ready", readiness_endpoint),
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
