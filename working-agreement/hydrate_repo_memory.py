#!/usr/bin/env python3
"""Repo-scoped memory hydration helper for the UserPromptSubmit hook (A3).

Sibling of `hydrate_corpus.py`: reads the hook's stdin JSON (prompt + cwd), derives the repo key
from the cwd basename (the brain canonicalizes it — A1), queries the deployed `run_retrieval_workflow`
MCP tool, and prints a UserPromptSubmit additionalContext payload with the repo's scoped notes so
captured knowledge resurfaces automatically (closes the capture→recall loop).

Opt-in: does nothing unless MK_REPO_HYDRATE=1. Fail-open by contract: on ANY error, missing
prompt/cwd, timeout, unknown repo, or no notes, it prints nothing and exits 0 — never blocks the prompt.

Tunables (env): CLAUDE_CORPUS_MCP_URL, CLAUDE_REPO_HYDRATE_TIMEOUT, CLAUDE_REPO_HYDRATE_LIMIT.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

URL = os.environ.get("CLAUDE_CORPUS_MCP_URL", "https://memory-knowledge.azurewebsites.net/mcp/")
TIMEOUT = float(os.environ.get("CLAUDE_REPO_HYDRATE_TIMEOUT", "6"))
LIMIT = int(os.environ.get("CLAUDE_REPO_HYDRATE_LIMIT", "3"))
ALLOWED_CONTENT_KINDS = {
    "root-cause", "corrected-approach", "repository-decision", "repository-fact",
}


def _eligible(note: dict) -> bool:
    operator_note = note.get("source_kind") == "operator_note" or note.get("memory_type") in {
        "note", "operator_note",
    }
    if not note.get("is_active", True):
        return False
    if not operator_note:
        return note.get("verification_status") == "verified"
    return (
        note.get("verification_status") in {"human_asserted", "verified"}
        and note.get("content_kind") in ALLOWED_CONTENT_KINDS
        and isinstance(note.get("evidence_refs"), list)
        and bool(note["evidence_refs"])
        and not note.get("evidence_resolution_errors")
    )


def _read_payload() -> tuple[str, str]:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return "", ""
    return (data.get("prompt") or "").strip(), (data.get("cwd") or "").strip()


async def _query(repo_key: str, prompt: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(
                "run_retrieval_workflow", {"repository_key": repo_key, "query": prompt}
            )
            for block in res.content:
                txt = getattr(block, "text", None)
                if txt:
                    parsed = json.loads(txt)
                    # the tool layer may wrap the WorkflowResult JSON under "result"
                    if isinstance(parsed, dict) and isinstance(parsed.get("result"), str):
                        parsed = json.loads(parsed["result"])
                    return parsed
    return None


def main() -> int:
    if os.environ.get("MK_REPO_HYDRATE") != "1":
        return 0  # opt-in
    prompt, cwd = _read_payload()
    if not prompt or not cwd:
        return 0
    repo_key = Path(cwd).name  # the brain canonicalizes case (A1)
    if not repo_key:
        return 0
    try:
        data = asyncio.run(asyncio.wait_for(_query(repo_key, prompt), TIMEOUT))
    except Exception:
        return 0  # fail-open: never block the prompt
    if not data or data.get("status") != "success":
        return 0
    notes = [
        n for n in ((data.get("data") or {}).get("repo_scoped_memory") or [])
        if n.get("body_text") and _eligible(n)
    ][:LIMIT]
    if not notes:
        return 0

    lines = [
        "# Repo memory — retrieved for this prompt",
        "(Repo-scoped notes for this repository, retrieved on demand. Context only — the Tier-1 "
        "directives above remain authoritative.)",
    ]
    for n in notes:
        label = n.get("title") or "note"
        tier = n.get("verification_status") or "—"
        lines.append(f"\n## {label}  ({tier})\n{n['body_text'].strip()}")
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
