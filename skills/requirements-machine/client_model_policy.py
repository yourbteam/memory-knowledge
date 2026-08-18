#!/usr/bin/env python3
"""Apply an installed client model policy to a Requirements Machinery reader command."""
from __future__ import annotations

import json
import shlex
from pathlib import Path


def validate_reader_command(command: str, policy_path: Path | None = None) -> list[str]:
    """Return argv only when it belongs to this installed client projection."""

    parts = shlex.split(command)
    if not parts:
        raise ValueError("reader command is empty")
    path = policy_path or Path(__file__).with_name("client-model-policy.json")
    if not path.exists():
        return parts
    try:
        policy = json.loads(path.read_text())
        required = shlex.split(policy["required_runtime"])
        forbidden = policy["forbidden_runtime"]
        client = policy["client"]
        fail_closed = policy["fail_closed"]
        if (policy["schema_version"] != 1 or fail_closed is not True or not required
                or not isinstance(forbidden, str) or not isinstance(client, str)):
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid client model policy: {path}") from error
    if parts[:len(required)] != required:
        raise ValueError(
            f"{client} projection refuses reader command {command!r}; "
            f"it must begin with {policy['required_runtime']!r}"
        )
    # Embedded readers do not need session persistence, skills, hooks, or MCP. Isolate those
    # surfaces in the invoking client's own syntax without changing which client/model it runs.
    if client == "codex":
        forbidden_flags = {"--dangerously-bypass-approvals-and-sandbox"}
        if forbidden_flags.intersection(parts):
            raise ValueError("codex machinery readers refuse unrestricted host access")
        for flag in ("--ignore-user-config", "--ephemeral"):
            if flag not in parts:
                parts.append(flag)
    elif client == "claude":
        forbidden_flags = {"--dangerously-skip-permissions", "--allow-dangerously-skip-permissions"}
        if forbidden_flags.intersection(parts):
            raise ValueError("claude machinery readers refuse unrestricted host access")
        additions = (
            "--disable-slash-commands", "--strict-mcp-config", "--mcp-config",
            '{"mcpServers":{}}', "--no-session-persistence",
        )
        for item in additions:
            if item not in parts:
                parts.append(item)
    return parts
