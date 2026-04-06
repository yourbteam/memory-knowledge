"""Codex MCP server client for LLM completions.

Spawns `codex mcp-server` as a subprocess and communicates via JSON-RPC
over stdin/stdout. This is the only way to use ChatGPT OAuth tokens for
completions — the standard OpenAI API rejects them.

Adapted from mcp-agents-workflow's McpStdioClient pattern.
"""
from __future__ import annotations

import asyncio
import json

import structlog

logger = structlog.get_logger()

_REQUEST_TIMEOUT = 120.0  # seconds per request
_STARTUP_TIMEOUT = 30.0


class CodexMcpClient:
    """Singleton MCP client that manages a long-lived codex mcp-server subprocess."""

    _instance: CodexMcpClient | None = None

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._initialized = False
        self._lock = asyncio.Lock()       # guards subprocess startup
        self._req_lock = asyncio.Lock()   # serializes requests — one in-flight at a time

    @classmethod
    def get(cls) -> CodexMcpClient:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _ensure_started(self) -> None:
        """Start the subprocess if not already running."""
        if self._process and self._process.returncode is None and self._initialized:
            return

        async with self._lock:
            # Double-check after acquiring lock
            if self._process and self._process.returncode is None and self._initialized:
                return

            # Kill stale process
            if self._process and self._process.returncode is None:
                self._process.kill()
                await self._process.wait()

            import os
            import shutil

            command = shutil.which("codex")
            if not command:
                raise RuntimeError(
                    "codex CLI not found in PATH — install it or add to PATH"
                )

            logger.info("codex_mcp_starting", command=command)

            self._process = await asyncio.create_subprocess_exec(
                command, "mcp-server",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ},
                limit=10 * 1024 * 1024,
            )

            self._request_id = 0
            self._initialized = False
            await self._initialize()

    async def _initialize(self) -> None:
        """Perform MCP protocol handshake."""
        await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "memory-knowledge",
                    "version": "0.1.0",
                },
            },
            timeout=_STARTUP_TIMEOUT,
        )
        await self._send_notification("notifications/initialized", {})
        self._initialized = True
        logger.info("codex_mcp_initialized")

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("Codex MCP subprocess not started")

        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self._process.stdin.write((json.dumps(msg) + "\n").encode())
        await self._process.stdin.drain()

    async def _send_request(
        self, method: str, params: dict, timeout: float = _REQUEST_TIMEOUT
    ) -> dict:
        """Send a JSON-RPC request and wait for the matching response.

        Serialized via _req_lock — only one request in-flight at a time
        to prevent concurrent readline() on the same stdout pipe.
        """
        async with self._req_lock:
            return await self._send_request_inner(method, params, timeout)

    async def _send_request_inner(
        self, method: str, params: dict, timeout: float
    ) -> dict:
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("Codex MCP subprocess not started")

        self._request_id += 1
        rid = self._request_id

        request = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        self._process.stdin.write((json.dumps(request) + "\n").encode())
        await self._process.stdin.drain()

        # Read lines until we get our response
        while True:
            try:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(), timeout=timeout
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Codex MCP request timed out after {timeout}s: {method}"
                )

            if not line:
                self._initialized = False
                raise RuntimeError("Codex MCP server closed connection")

            decoded = line.decode().strip()
            if not decoded:
                continue

            response = json.loads(decoded)

            # Skip notifications
            if "id" not in response:
                continue

            if response.get("id") == rid:
                if "error" in response:
                    err = response["error"]
                    raise RuntimeError(
                        f"Codex MCP error: {err.get('message', 'unknown')}"
                    )
                return response.get("result", {})

    async def complete(self, prompt: str, timeout: float = _REQUEST_TIMEOUT) -> str:
        """Send a prompt to Codex and return the text response."""
        await self._ensure_started()

        result = await self._send_request(
            "tools/call",
            {
                "name": "codex",
                "arguments": {
                    "prompt": prompt,
                    "approval-policy": "never",
                    "sandbox": "read-only",
                },
            },
            timeout=timeout,
        )

        # Parse MCP tool result: {"content": [{"type": "text", "text": "..."}]}
        content = result.get("content", [])
        if content and len(content) > 0:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                return first.get("text", "")
        return str(content)

    async def shutdown(self) -> None:
        """Shut down the subprocess."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            self._initialized = False
            logger.info("codex_mcp_stopped")
