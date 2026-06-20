#!/usr/bin/env python3
"""#2 option-1: automatic session-close auto-capture (Claude Code `Stop` hook).

Reads the Stop-hook payload (transcript_path + cwd) from stdin, LLM-extracts the session's
durable lessons, and writes each as a **candidate** note (verification_status='unverified')
via the `author_repo_note` MCP tool — so knowledge accrues automatically, for later promotion.

Design guarantees:
- **Opt-in:** does nothing unless env `MK_AUTOCAPTURE=1` (avoids per-session LLM cost by default).
- **Fail-open:** ANY error, missing transcript, non-ingested repo, or empty extraction → exit 0,
  capture nothing. Never blocks or breaks the session end. (A wrong model just yields no capture.)
- **Candidate tier:** writes verification_status='unverified', low confidence — never a directive.

Env: MK_AUTOCAPTURE (gate), MK_AUTOCAPTURE_MODEL (chat model), CLAUDE_CORPUS_MCP_URL (brain),
plus the repo's normal AUTH_MODE/CODEX_AUTH_PATH for the LLM key.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

URL = os.environ.get("CLAUDE_CORPUS_MCP_URL", "https://memory-knowledge.azurewebsites.net/mcp/")
MODEL = os.environ.get("MK_AUTOCAPTURE_MODEL", "gpt-5.4-mini")
MAX_LESSONS = int(os.environ.get("MK_AUTOCAPTURE_MAX", "3"))
MAX_TRANSCRIPT_CHARS = 24000

_PROMPT = (
    "You review an AI coding session and extract ONLY durable, reusable lessons worth remembering: "
    "a confirmed gotcha/root-cause, a corrected approach, or a decision with lasting rationale. "
    "Skip task chatter, transient state, secrets, and large code. Return STRICT JSON: "
    '{"lessons":[{"title":"<=80 chars","body":"the lesson + why"}]} with 0 to %d items.' % MAX_LESSONS
)


def read_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def repo_key_from_cwd(cwd: str | None) -> str | None:
    if not cwd:
        return None
    return Path(cwd).name or None


def load_transcript_text(transcript_path: str | None) -> str:
    if not transcript_path or not Path(transcript_path).exists():
        return ""
    parts: list[str] = []
    for line in Path(transcript_path).read_text(errors="ignore").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        msg = ev.get("message") or ev
        role = msg.get("role") or ev.get("type")
        content = msg.get("content")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if role in ("user", "assistant") and content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts)[-MAX_TRANSCRIPT_CHARS:]


async def extract_lessons(transcript_text: str) -> list[dict]:
    """LLM-extract durable lessons. Returns [] on any failure (fail-open)."""
    if not transcript_text.strip():
        return []
    from memory_knowledge.config import Settings
    from memory_knowledge.llm.openai_client import _get_api_key
    from openai import AsyncOpenAI

    settings = Settings()
    api_key = await _get_api_key(settings)
    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": _PROMPT},
                  {"role": "user", "content": transcript_text}],
    )
    data = json.loads(resp.choices[0].message.content)
    return (data.get("lessons") or [])[:MAX_LESSONS]


async def write_candidates(repo_key: str, lessons: list[dict]) -> int:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    written = 0
    async with streamable_http_client(URL) as (rd, wr, _):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            for ls in lessons:
                title, body = (ls.get("title") or "").strip(), (ls.get("body") or "").strip()
                if not title or not body:
                    continue
                res = await s.call_tool("author_repo_note", {
                    "repository_key": repo_key, "title": title, "body_text": body,
                    "verification_status": "unverified", "confidence": 0.4})
                txt = next((b.text for b in res.content if getattr(b, "type", None) == "text"), "")
                try:
                    if json.loads(txt).get("status") == "success":
                        written += 1
                except Exception:
                    pass
    return written


async def _main() -> int:
    if os.environ.get("MK_AUTOCAPTURE") != "1":
        return 0  # opt-in
    payload = read_payload()
    repo_key = repo_key_from_cwd(payload.get("cwd"))
    if not repo_key:
        return 0
    try:
        lessons = await extract_lessons(load_transcript_text(payload.get("transcript_path")))
        if lessons:
            n = await write_candidates(repo_key, lessons)
            print(f"[auto-capture] {n} candidate note(s) -> {repo_key}", file=sys.stderr)
    except Exception:
        return 0  # fail-open
    return 0


def main() -> int:
    try:
        return asyncio.run(_main())
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
