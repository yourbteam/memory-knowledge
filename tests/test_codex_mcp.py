"""Tests for Codex MCP client (codex_mcp.py)."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory_knowledge.llm.codex_mcp import CodexMcpClient


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton between tests."""
    CodexMcpClient._instance = None
    yield
    CodexMcpClient._instance = None


@pytest.fixture
def mock_process():
    """Create a mock subprocess with stdin/stdout."""
    process = MagicMock()
    process.returncode = None  # process is running
    process.stdin = MagicMock()
    process.stdin.write = MagicMock()
    process.stdin.drain = AsyncMock()
    process.stdout = MagicMock()
    process.stderr = MagicMock()
    process.terminate = MagicMock()
    process.kill = MagicMock()
    process.wait = AsyncMock()
    return process


def _make_response(request_id, result):
    """Create a JSON-RPC response line."""
    return (json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n").encode()


def _make_error(request_id, code, message):
    """Create a JSON-RPC error response line."""
    return (json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}) + "\n").encode()


class TestCodexMcpClientSingleton:
    def test_get_returns_same_instance(self):
        a = CodexMcpClient.get()
        b = CodexMcpClient.get()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = CodexMcpClient.get()
        CodexMcpClient._instance = None
        b = CodexMcpClient.get()
        assert a is not b


class TestCodexMcpClientStartup:
    @pytest.mark.asyncio
    async def test_start_spawns_codex_mcp_server(self, mock_process):
        client = CodexMcpClient.get()

        # Initialize response (id=1) then initialized notification is fire-and-forget
        init_response = _make_response(1, {"protocolVersion": "2024-11-05"})
        mock_process.stdout.readline = AsyncMock(return_value=init_response)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec, \
             patch("shutil.which", return_value="/usr/local/bin/codex"):
            await client._ensure_started()

            mock_exec.assert_called_once()
            args = mock_exec.call_args
            assert args[0][0] == "/usr/local/bin/codex"
            assert args[0][1] == "mcp-server"
            assert client._initialized is True

    @pytest.mark.asyncio
    async def test_start_raises_if_codex_not_found(self):
        client = CodexMcpClient.get()

        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="codex CLI not found"):
                await client._ensure_started()


class TestCodexMcpClientComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_text(self, mock_process):
        client = CodexMcpClient.get()

        # Sequence: init response, then tool call response
        init_resp = _make_response(1, {"protocolVersion": "2024-11-05"})
        tool_resp = _make_response(2, {
            "content": [{"type": "text", "text": "This is a summary of the code."}]
        })
        mock_process.stdout.readline = AsyncMock(side_effect=[init_resp, tool_resp])

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process), \
             patch("shutil.which", return_value="/usr/local/bin/codex"):
            result = await client.complete("Summarize this function")

        assert result == "This is a summary of the code."

    @pytest.mark.asyncio
    async def test_complete_sends_correct_tool_call(self, mock_process):
        client = CodexMcpClient.get()

        init_resp = _make_response(1, {"protocolVersion": "2024-11-05"})
        tool_resp = _make_response(2, {"content": [{"type": "text", "text": "ok"}]})
        mock_process.stdout.readline = AsyncMock(side_effect=[init_resp, tool_resp])

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process), \
             patch("shutil.which", return_value="/usr/local/bin/codex"):
            await client.complete("test prompt")

        # Check the tool call written to stdin (second write, after init + notification)
        writes = mock_process.stdin.write.call_args_list
        # Find the tools/call request
        tool_call = None
        for w in writes:
            data = json.loads(w[0][0].decode())
            if data.get("method") == "tools/call":
                tool_call = data
                break

        assert tool_call is not None
        assert tool_call["params"]["name"] == "codex"
        assert tool_call["params"]["arguments"]["approval-policy"] == "never"
        assert tool_call["params"]["arguments"]["sandbox"] == "read-only"
        assert tool_call["params"]["arguments"]["prompt"] == "test prompt"

    @pytest.mark.asyncio
    async def test_complete_skips_notifications(self, mock_process):
        client = CodexMcpClient.get()

        init_resp = _make_response(1, {"protocolVersion": "2024-11-05"})
        notification = (json.dumps({"jsonrpc": "2.0", "method": "log", "params": {"msg": "hi"}}) + "\n").encode()
        tool_resp = _make_response(2, {"content": [{"type": "text", "text": "result"}]})
        mock_process.stdout.readline = AsyncMock(side_effect=[init_resp, notification, tool_resp])

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process), \
             patch("shutil.which", return_value="/usr/local/bin/codex"):
            result = await client.complete("test")

        assert result == "result"

    @pytest.mark.asyncio
    async def test_complete_handles_empty_content(self, mock_process):
        client = CodexMcpClient.get()

        init_resp = _make_response(1, {"protocolVersion": "2024-11-05"})
        tool_resp = _make_response(2, {"content": []})
        mock_process.stdout.readline = AsyncMock(side_effect=[init_resp, tool_resp])

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process), \
             patch("shutil.which", return_value="/usr/local/bin/codex"):
            result = await client.complete("test")

        assert result == "[]"


class TestCodexMcpClientErrors:
    @pytest.mark.asyncio
    async def test_error_response_raises(self, mock_process):
        client = CodexMcpClient.get()

        init_resp = _make_response(1, {"protocolVersion": "2024-11-05"})
        error_resp = _make_error(2, -32600, "Something went wrong")
        mock_process.stdout.readline = AsyncMock(side_effect=[init_resp, error_resp])

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process), \
             patch("shutil.which", return_value="/usr/local/bin/codex"):
            with pytest.raises(RuntimeError, match="Something went wrong"):
                await client.complete("test")

    @pytest.mark.asyncio
    async def test_closed_connection_raises(self, mock_process):
        client = CodexMcpClient.get()

        init_resp = _make_response(1, {"protocolVersion": "2024-11-05"})
        mock_process.stdout.readline = AsyncMock(side_effect=[init_resp, b""])

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process), \
             patch("shutil.which", return_value="/usr/local/bin/codex"):
            with pytest.raises(RuntimeError, match="closed connection"):
                await client.complete("test")


class TestCodexMcpClientShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_terminates_process(self, mock_process):
        client = CodexMcpClient.get()

        init_resp = _make_response(1, {"protocolVersion": "2024-11-05"})
        mock_process.stdout.readline = AsyncMock(return_value=init_resp)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process), \
             patch("shutil.which", return_value="/usr/local/bin/codex"):
            await client._ensure_started()

        await client.shutdown()
        mock_process.terminate.assert_called_once()
        assert client._initialized is False
