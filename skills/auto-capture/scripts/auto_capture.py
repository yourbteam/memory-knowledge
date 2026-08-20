#!/usr/bin/env python3
"""#2 option-1: automatic session-close auto-capture (Claude Code `Stop` hook).

Reads the Stop-hook payload (transcript_path + cwd) from stdin, LLM-extracts the session's
durable lessons, and writes each as a **candidate** note (verification_status='unverified')
via the `author_repo_note` MCP tool — so knowledge accrues automatically, for later promotion.

Design guarantees:
- **Opt-in:** does nothing unless env `MK_AUTOCAPTURE=1` (avoids per-session LLM cost by default).
- **Fail-open:** ANY error, missing transcript, non-ingested repo, or empty extraction → exit 0,
  capture nothing. Never blocks or breaks the session end.
- **Code-controlled choices:** the model receives numbered menus and code maps the selected
  numbers to canonical values. Prose labels are rejected with one bounded correction attempt.
- **Candidate tier:** writes verification_status='unverified', low confidence — never a directive.

Env: MK_AUTOCAPTURE (gate), MK_CLIENT_KIND (codex or claude subscription client),
CLAUDE_CORPUS_MCP_URL (brain), and MK_AUTOCAPTURE_DRY_RUN (extract without writing).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from auto_capture_interview import (
    CONTENT_KIND_OPTIONS,
    EVIDENCE_KIND_OPTIONS,
    INTERVIEW_OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    InterviewError,
    collect_interactive,
    parse_interview,
    user_prompt,
)
from auto_capture_interview import MAX_LESSONS as INTERVIEW_MAX_LESSONS
from auto_capture_subscription import complete as complete_via_subscription

URL = os.environ.get("CLAUDE_CORPUS_MCP_URL", "https://memory-knowledge.azurewebsites.net/mcp/")
MAX_LESSONS = min(
    max(int(os.environ.get("MK_AUTOCAPTURE_MAX", "3")), 0),
    INTERVIEW_MAX_LESSONS,
)
MAX_TRANSCRIPT_CHARS = 24000
MAX_INTERVIEW_ATTEMPTS = 2

_CONTENT_KINDS = frozenset(CONTENT_KIND_OPTIONS.values())
_EVIDENCE_KINDS = frozenset(EVIDENCE_KIND_OPTIONS.values())


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


def parse_model_answer(content: object) -> list[dict]:
    """Parse one model answer through the proven numbered interview boundary."""
    if not isinstance(content, str):
        raise InterviewError("model answer was not text; return one JSON object")
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise InterviewError(
            f"model answer was not valid JSON at character {exc.pos}; return one JSON object"
        ) from exc
    return parse_interview(raw)[:MAX_LESSONS]


async def conduct_interview(client, transcript_text: str) -> list[dict]:
    """Run the numbered interview with one bounded correction for invalid selections."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(transcript_text)},
    ]
    for attempt in range(MAX_INTERVIEW_ATTEMPTS):
        response = await client.chat.completions.create(
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = response.choices[0].message.content
        try:
            return parse_model_answer(content)
        except InterviewError as exc:
            if attempt + 1 == MAX_INTERVIEW_ATTEMPTS:
                raise
            messages.extend([
                {"role": "assistant", "content": content or ""},
                {
                    "role": "user",
                    "content": (
                        f"Your interview answer was rejected: {exc}. "
                        "Return the complete corrected JSON answer. Choose only numbers from "
                        "the displayed menus for every selection field."
                    ),
                },
            ])
    raise AssertionError("unreachable interview attempt state")


class SubscriptionCompletions:
    """Adapt the installed-client subscription boundary to the interview contract."""

    async def create(self, *, messages: list[dict], **_ignored) -> SimpleNamespace:
        content = await asyncio.to_thread(
            complete_via_subscription,
            messages,
            INTERVIEW_OUTPUT_SCHEMA,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


async def extract_lessons(transcript_text: str) -> list[dict]:
    """LLM-extract durable lessons; the outer hook owns fail-open behavior."""
    if not transcript_text.strip() or MAX_LESSONS == 0:
        return []
    completions = SubscriptionCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return await conduct_interview(client, transcript_text)


async def write_candidates(repo_key: str, lessons: list[dict]) -> int:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    written = 0
    async with streamable_http_client(URL) as (rd, wr, _):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            for ls in lessons:
                title, body = (ls.get("title") or "").strip(), (ls.get("body") or "").strip()
                content_kind = ls.get("content_kind")
                refs = ls.get("evidence_refs")
                if (
                    not title or not body or len(title) > 80
                    or content_kind not in _CONTENT_KINDS
                    or not isinstance(refs, list) or not refs
                ):
                    continue
                normalized_refs = []
                for ref in refs:
                    if not isinstance(ref, dict) or ref.get("kind") not in _EVIDENCE_KINDS:
                        normalized_refs = []
                        break
                    normalized_refs.append({**ref, "repository_key": repo_key})
                if not normalized_refs:
                    continue
                res = await s.call_tool("author_repo_note", {
                    "repository_key": repo_key, "title": title, "body_text": body,
                    "verification_status": "unverified", "confidence": 0.4,
                    "content_kind": content_kind, "evidence_refs": normalized_refs})
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
        if os.environ.get("MK_AUTOCAPTURE_DRY_RUN") == "1":
            print(json.dumps({"repository_key": repo_key, "lessons": lessons}, sort_keys=True))
        elif lessons:
            n = await write_candidates(repo_key, lessons)
            print(f"[auto-capture] {n} candidate note(s) -> {repo_key}", file=sys.stderr)
    except Exception as exc:
        if os.environ.get("MK_AUTOCAPTURE_DRY_RUN") == "1":
            print(
                f"[auto-capture] dry-run failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        return 0  # fail-open
    return 0


async def _interactive_main() -> int:
    """Explicit skill-driven path; default no-argument Stop-hook behavior is unchanged."""
    try:
        repo_key, lessons = collect_interactive()
        if os.environ.get("MK_AUTOCAPTURE_DRY_RUN") == "1":
            print(json.dumps({"repository_key": repo_key, "lessons": lessons}, sort_keys=True))
        elif lessons:
            written = await write_candidates(repo_key, lessons)
            print(f"[auto-capture] {written} candidate note(s) -> {repo_key}")
        else:
            print("[auto-capture] nothing durable to capture")
    except (EOFError, KeyboardInterrupt, InterviewError) as exc:
        print(f"[auto-capture] interview rejected: {exc}", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    try:
        if sys.argv[1:] == ["--interview"]:
            return asyncio.run(_interactive_main())
        if sys.argv[1:]:
            print("usage: auto_capture.py [--interview]", file=sys.stderr)
            return 2
        return asyncio.run(_main())
    except Exception as exc:
        if sys.argv[1:]:
            print(f"[auto-capture] failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
