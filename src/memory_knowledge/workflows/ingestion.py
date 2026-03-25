from __future__ import annotations

import uuid

from memory_knowledge.workflows.base import WorkflowResult

TOOL_NAME = "run_repo_ingestion_workflow"


async def run(
    repository_key: str,
    commit_sha: str,
    branch_name: str,
    run_id: uuid.UUID,
    **kwargs,
) -> WorkflowResult:
    return WorkflowResult(
        run_id=str(run_id),
        tool_name=TOOL_NAME,
        status="not_implemented",
        error="This workflow is not yet implemented.",
    )
