#!/usr/bin/env python3
"""Make a remotely published commit visible in memory before publish closeout."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx


DEFAULT_MCP_URL = "https://memory-knowledge.azurewebsites.net/mcp/"
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 21600.0
TERMINAL_JOB_STATES = frozenset({"completed", "failed", "dead_letter", "cancelled"})


class IngestionVerificationError(RuntimeError):
    """The published commit could not be proven present in memory."""


ToolCaller = Callable[[str, dict[str, object]], Awaitable[dict[str, object]]]


def _required_data(payload: dict[str, object], operation: str) -> dict[str, object]:
    if payload.get("status") not in {"success", "submitted"}:
        raise IngestionVerificationError(f"{operation}-failed:{payload.get('status') or 'unknown'}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise IngestionVerificationError(f"{operation}-missing-data")
    return data


def _memory_row(
    payload: dict[str, object], *, repository_key: str,
) -> dict[str, object] | None:
    data = _required_data(payload, "list-repositories")
    rows = data.get("repositories")
    if not isinstance(rows, list):
        raise IngestionVerificationError("list-repositories-missing-rows")
    matches = [
        row for row in rows
        if isinstance(row, dict) and row.get("repository_key") == repository_key
    ]
    if len(matches) > 1:
        raise IngestionVerificationError("repository-memory-identity-ambiguous")
    return matches[0] if matches else None


def _is_ready(
    row: dict[str, object] | None, *, branch_name: str, commit_sha: str,
) -> bool:
    return bool(
        row
        and row.get("latest_branch") == branch_name
        and row.get("latest_commit") == commit_sha
        and row.get("last_ingestion_status") == "success"
    )


def _verify_job_shape(
    job: dict[str, object], *, repository_key: str, branch_name: str, commit_sha: str,
) -> None:
    if (
        job.get("repository_key") != repository_key
        or job.get("branch_name") != branch_name
        or job.get("commit_sha") != commit_sha
    ):
        raise IngestionVerificationError("ingestion-job-shape-mismatch")


async def verify(
    call_tool: ToolCaller,
    *,
    repository_key: str,
    branch_name: str,
    commit_sha: str,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Submit once, wait for exact job success, and prove the memory head advanced."""

    if not repository_key.strip() or not branch_name.strip() or not commit_sha.strip():
        raise IngestionVerificationError("incomplete-published-commit-identity")
    if poll_interval_seconds < 0 or timeout_seconds <= 0:
        raise IngestionVerificationError("invalid-ingestion-wait-bound")

    current = _memory_row(
        await call_tool("list_repositories", {"include_inactive": True}),
        repository_key=repository_key,
    )
    if _is_ready(current, branch_name=branch_name, commit_sha=commit_sha):
        return {
            "verified": True,
            "alreadyReady": True,
            "repositoryKey": repository_key,
            "branch": branch_name,
            "memoryCommit": commit_sha,
        }

    submission = await call_tool("run_repo_ingestion_workflow", {
        "repository_key": repository_key,
        "branch_name": branch_name,
        "commit_sha": commit_sha,
    })
    submission_data = _required_data(submission, "ingestion-submission")
    job_id = submission_data.get("job_id")
    if not isinstance(job_id, str) or not job_id.strip():
        raise IngestionVerificationError("ingestion-submission-missing-job-id")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    polls = 0
    job: dict[str, object] | None = None
    while loop.time() <= deadline:
        polls += 1
        job = _required_data(
            await call_tool("check_job_status", {"job_id": job_id}),
            "ingestion-job-status",
        )
        state = job.get("state_code")
        if state in TERMINAL_JOB_STATES:
            break
        if not isinstance(state, str) or not state:
            raise IngestionVerificationError("ingestion-job-missing-state")
        if poll_interval_seconds:
            await asyncio.sleep(min(poll_interval_seconds, max(0.0, deadline - loop.time())))
    else:
        raise IngestionVerificationError(f"ingestion-job-timeout:{job_id}")

    assert job is not None
    _verify_job_shape(
        job,
        repository_key=repository_key,
        branch_name=branch_name,
        commit_sha=commit_sha,
    )
    state = str(job.get("state_code"))
    if state != "completed":
        raise IngestionVerificationError(f"ingestion-job-state:{state}")
    checkpoint = job.get("checkpoint_data")
    if not isinstance(checkpoint, dict):
        raise IngestionVerificationError("ingestion-job-missing-workflow-result")
    workflow_status = checkpoint.get("status")
    if workflow_status != "success":
        raise IngestionVerificationError(
            f"ingestion-workflow-status:{workflow_status or 'unknown'}"
        )

    visible = _memory_row(
        await call_tool("list_repositories", {"include_inactive": True}),
        repository_key=repository_key,
    )
    if not _is_ready(visible, branch_name=branch_name, commit_sha=commit_sha):
        observed = visible.get("latest_commit") if visible else "missing"
        raise IngestionVerificationError(
            f"published-commit-not-memory-visible:expected={commit_sha};observed={observed}"
        )
    return {
        "verified": True,
        "alreadyReady": False,
        "repositoryKey": repository_key,
        "branch": branch_name,
        "memoryCommit": commit_sha,
        "jobId": job_id,
        "polls": polls,
    }


class McpToolClient:
    """Small Streamable-HTTP client for the two existing ingestion tools."""

    def __init__(self, url: str, *, request_timeout_seconds: float = 60.0) -> None:
        self.url = url.rstrip("/") + "/"
        self.http = httpx.AsyncClient(timeout=request_timeout_seconds)
        self.session_id: str | None = None
        self.request_id = 0

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        token = os.environ.get("MEMORY_KNOWLEDGE_MCP_API_KEY", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        if "text/event-stream" in response.headers.get("content-type", ""):
            data = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
            if not data:
                raise IngestionVerificationError("mcp-sse-response-missing-data")
            decoded = json.loads(data[-1])
        else:
            decoded = response.json()
        if not isinstance(decoded, dict):
            raise IngestionVerificationError("mcp-response-not-object")
        return decoded

    async def _post(self, payload: dict[str, object]) -> dict[str, Any]:
        response = await self.http.post(self.url, json=payload, headers=self._headers())
        response.raise_for_status()
        if session_id := response.headers.get("mcp-session-id"):
            self.session_id = session_id
        return self._decode_response(response)

    async def initialize(self) -> None:
        self.request_id += 1
        response = await self._post({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "scoped-git-publish", "version": "1"},
            },
        })
        if "result" not in response:
            raise IngestionVerificationError("mcp-initialize-failed")
        notification = await self.http.post(
            self.url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=self._headers(),
        )
        if notification.status_code not in {200, 202, 204}:
            raise IngestionVerificationError(
                f"mcp-initialized-notification-http:{notification.status_code}"
            )

    async def call_tool(
        self, name: str, arguments: dict[str, object],
    ) -> dict[str, object]:
        self.request_id += 1
        response = await self._post({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if "error" in response:
            raise IngestionVerificationError(f"mcp-tool-rpc-error:{name}")
        result = response.get("result")
        if not isinstance(result, dict) or result.get("isError") is True:
            raise IngestionVerificationError(f"mcp-tool-failed:{name}")
        content = result.get("content")
        text = [
            item.get("text") for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ] if isinstance(content, list) else []
        if not text or not isinstance(text[0], str):
            raise IngestionVerificationError(f"mcp-tool-missing-text:{name}")
        decoded = json.loads(text[0])
        if not isinstance(decoded, dict):
            raise IngestionVerificationError(f"mcp-tool-result-not-object:{name}")
        return decoded

    async def close(self) -> None:
        await self.http.aclose()


async def _run(
    *, repository_key: str, branch_name: str, commit_sha: str,
) -> dict[str, object]:
    url = os.environ.get("WORKFLOW_ORCH_MEMORY_KNOWLEDGE_URL", DEFAULT_MCP_URL)
    poll_interval = float(os.environ.get(
        "MK_PUBLISH_INGESTION_POLL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS,
    ))
    timeout = float(os.environ.get(
        "MK_PUBLISH_INGESTION_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS,
    ))
    client = McpToolClient(url)
    try:
        await client.initialize()
        return await verify(
            client.call_tool,
            repository_key=repository_key,
            branch_name=branch_name,
            commit_sha=commit_sha,
            poll_interval_seconds=poll_interval,
            timeout_seconds=timeout,
        )
    finally:
        await client.close()


def run(
    *, repository_key: str, branch_name: str, commit_sha: str,
) -> dict[str, object]:
    """Synchronous publisher boundary."""

    try:
        return asyncio.run(_run(
            repository_key=repository_key,
            branch_name=branch_name,
            commit_sha=commit_sha,
        ))
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        raise IngestionVerificationError(
            f"memory-ingestion-transport:{type(exc).__name__}"
        ) from exc
