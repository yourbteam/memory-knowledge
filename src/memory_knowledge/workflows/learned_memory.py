from __future__ import annotations

import uuid

from memory_knowledge.workflows.base import WorkflowResult


async def run_proposal(
    repository_key: str, query: str, run_id: uuid.UUID, **kwargs
) -> WorkflowResult:
    return WorkflowResult(
        run_id=str(run_id),
        tool_name="run_learned_memory_proposal_workflow",
        status="not_implemented",
        error="This workflow is not yet implemented.",
    )


async def run_commit(
    repository_key: str, proposal_id: str, run_id: uuid.UUID, **kwargs
) -> WorkflowResult:
    return WorkflowResult(
        run_id=str(run_id),
        tool_name="run_learned_memory_commit_workflow",
        status="not_implemented",
        error="This workflow is not yet implemented.",
    )
