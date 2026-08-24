#!/usr/bin/env python3
"""Subscription-native structured completion for auto-capture.

This boundary deliberately invokes the installed Codex or Claude client. It never imports or
calls the public OpenAI or Anthropic API SDKs, so the user's existing client subscription remains
the only model-authentication path.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

CLIENTS = {"codex", "claude"}
DEFAULT_TIMEOUT_SECONDS = 180
_ANSI_CONTROL = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class SubscriptionCompletionError(RuntimeError):
    """The selected installed client did not return one structured answer."""


def active_client(environ: Mapping[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    configured = values.get("MK_CLIENT_KIND")
    if configured is not None:
        if configured not in CLIENTS:
            raise SubscriptionCompletionError("MK_CLIENT_KIND must be codex or claude")
        return configured
    return "claude" if values.get("CLAUDECODE") else "codex"


def _messages_prompt(messages: list[dict[str, str]]) -> str:
    sections = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant"} or not isinstance(content, str):
            raise SubscriptionCompletionError("completion messages must contain text roles")
        sections.append(f"<{role}>\n{content}\n</{role}>")
    return "\n\n".join(sections)


def build_codex_argv(
    executable: str, work: Path, schema_path: Path, result_path: Path,
) -> list[str]:
    return [
        executable,
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--cd",
        str(work),
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(result_path),
        "-",
    ]


def build_claude_argv(executable: str, schema: dict[str, Any]) -> list[str]:
    return [
        executable,
        "-p",
        "--input-format",
        "text",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema, sort_keys=True, separators=(",", ":")),
        "--max-budget-usd",
        "0.25",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--setting-sources",
        "",
        "--tools",
        "",
    ]


def _claude_structured_output(stdout: str) -> dict[str, Any]:
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SubscriptionCompletionError("Claude returned a non-JSON result envelope") from exc
    if not isinstance(envelope, dict) or envelope.get("type") != "result" or envelope.get("is_error"):
        raise SubscriptionCompletionError("Claude did not return a successful terminal result")
    candidate = envelope.get("structured_output", envelope.get("result"))
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise SubscriptionCompletionError("Claude result contained non-JSON text") from exc
    if not isinstance(candidate, dict):
        raise SubscriptionCompletionError("Claude result omitted structured output")
    return candidate


def complete(
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    client: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    selected = active_client() if client is None else client
    if selected not in CLIENTS:
        raise SubscriptionCompletionError("client must be codex or claude")
    executable = which(selected)
    if not executable:
        raise SubscriptionCompletionError(f"{selected} subscription client is unavailable")
    prompt = _messages_prompt(messages)
    child_environment = dict(os.environ)
    child_environment.update({"MK_AUTOCAPTURE": "0", "MK_AUTOCAPTURE_NESTED": "1"})

    with tempfile.TemporaryDirectory(prefix="auto-capture-subscription-") as raw:
        work = Path(raw)
        schema_path = work / "schema.json"
        result_path = work / "result.json"
        schema_path.write_text(json.dumps(schema, sort_keys=True), encoding="utf-8")
        argv = (
            build_codex_argv(executable, work, schema_path, result_path)
            if selected == "codex"
            else build_claude_argv(executable, schema)
        )
        try:
            completed = runner(
                argv,
                cwd=work,
                env=child_environment,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise SubscriptionCompletionError(
                f"{selected} subscription completion timed out after {timeout_seconds}s"
            ) from exc
        if completed.returncode:
            detail = [
                cleaned
                for line in (completed.stderr or "").splitlines()
                if (cleaned := _ANSI_CONTROL.sub("", line).strip())
            ]
            suffix = f": {detail[-1][-500:]}" if detail else ": no stderr returned"
            if os.environ.get("MK_AUTOCAPTURE_DEBUG") == "1":
                suffix += (
                    f"; stderr_tail={(completed.stderr or '')[-1000:]!r}"
                    f"; stdout_tail={(completed.stdout or '')[-1000:]!r}"
                )
            raise SubscriptionCompletionError(
                f"{selected} subscription client exited {completed.returncode}{suffix}"
            )
        if selected == "codex":
            if not result_path.is_file():
                raise SubscriptionCompletionError("Codex omitted its structured result file")
            try:
                answer = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SubscriptionCompletionError("Codex result file was not JSON") from exc
        else:
            answer = _claude_structured_output(completed.stdout)
    return json.dumps(answer, sort_keys=True)
