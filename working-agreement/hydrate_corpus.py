#!/usr/bin/env python3
"""Tier-2 corpus hydration helper for the UserPromptSubmit hook.

Reads the hook's stdin JSON, takes the user prompt, queries the deployed corpus_query MCP
tool, and prints a UserPromptSubmit additionalContext payload with the top relevant entries.

Fail-open by contract: on ANY error, missing prompt, timeout, or no above-threshold hit, it
prints nothing and exits 0 — it must never block or delay the prompt beyond the timeout.

Tunables (env): CLAUDE_CORPUS_MCP_URL, CLAUDE_CORPUS_TIMEOUT, CLAUDE_CORPUS_MIN_SCORE,
CLAUDE_CORPUS_LIMIT.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

URL = os.environ.get("CLAUDE_CORPUS_MCP_URL", "https://memory-knowledge.azurewebsites.net/mcp/")
TIMEOUT = float(os.environ.get("CLAUDE_CORPUS_TIMEOUT", "6"))
MIN_SCORE = float(os.environ.get("CLAUDE_CORPUS_MIN_SCORE", "0.5"))
LIMIT = int(os.environ.get("CLAUDE_CORPUS_LIMIT", "3"))


def _read_prompt() -> str:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return ""
    return (data.get("prompt") or "").strip()


async def _query(prompt: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool("corpus_query", {"query_text": prompt, "limit": LIMIT})
            for block in res.content:
                txt = getattr(block, "text", None)
                if txt:
                    return json.loads(txt)
    return None


def main() -> int:
    prompt = _read_prompt()
    if not prompt:
        return 0
    try:
        data = asyncio.run(asyncio.wait_for(_query(prompt), TIMEOUT))
    except Exception:
        return 0  # fail-open: never block the prompt
    if not data or data.get("status") != "success":
        return 0
    hits = [
        h for h in (data.get("data") or {}).get("results", [])
        if (h.get("score") or 0) >= MIN_SCORE and h.get("body_text")
    ]
    if not hits:
        return 0

    lines = [
        "# Tier-2 corpus — retrieved for this prompt",
        "(Relevance-ranked background, retrieved on demand. Context only — the Tier-1 "
        "directives above remain authoritative.)",
    ]
    for h in hits:
        label = h.get("title") or h.get("link_slug") or "entry"
        score = round(float(h.get("score") or 0), 2)
        lines.append(f"\n## {label}  (score {score})\n{h['body_text'].strip()}")
    ctx = "\n".join(lines)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
