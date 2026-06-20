#!/usr/bin/env python3
"""#3: proactive "directive Spark".

Mines the brain's own telemetry across the active repos for recurring patterns that may warrant
a NEW working-agreement directive — and writes them to a review file for Kamen. It NEVER edits
DIRECTIVES.md: promotion stays human-gated ("lock it"). This turns our reactive directive habit
(a rule only after a lapse hurts) into a forward-looking proposal stream.

Signals (per repo, best-effort — a tool returning nothing is skipped):
  - get_finding_pattern_summary       (recurring review findings)
  - get_agent_failure_mode_summary    (recurring agent failure modes)
  - get_clarification_policy          (recurring clarification needs)
  - get_triage_confusion_clusters     (recurring triage confusion)

Output: working-agreement/spark-candidates.md — a review queue. Fail-open per tool.

Env: CLAUDE_CORPUS_MCP_URL (brain), MK_SPARK_REPOS (comma-sep repo keys), MK_SPARK_MIN (freq floor).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

URL = os.environ.get("CLAUDE_CORPUS_MCP_URL", "https://memory-knowledge.azurewebsites.net/mcp/")
DEFAULT_REPOS = ["taggable-api", "fcsapi", "taggable-server"]
REPOS = [r.strip() for r in os.environ.get("MK_SPARK_REPOS", ",".join(DEFAULT_REPOS)).split(",") if r.strip()]
MIN_FREQ = int(os.environ.get("MK_SPARK_MIN", "2"))
OUT = Path(__file__).resolve().parent / "spark-candidates.md"

SIGNALS = [
    "get_finding_pattern_summary",
    "get_agent_failure_mode_summary",
    "get_clarification_policy",
    "get_triage_confusion_clusters",
]


def _text(result) -> str:
    for b in result.content:
        if getattr(b, "type", None) == "text":
            return b.text
    return ""


def _items(parsed) -> list:
    """Best-effort: pull a list of pattern rows out of whatever shape the tool returned."""
    if not isinstance(parsed, dict):
        return []
    data = parsed.get("data", parsed)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
    return []


async def gather(session, repo: str) -> list[dict]:
    out = []
    for tool in SIGNALS:
        try:
            res = await session.call_tool(tool, {"repository_key": repo})
            parsed = json.loads(_text(res))
            if parsed.get("status") not in (None, "success"):
                continue
            for it in _items(parsed):
                # frequency floor: only surface patterns seen >= MIN_FREQ times when a count exists
                cnt = it.get("count") or it.get("frequency") or it.get("n") if isinstance(it, dict) else None
                if cnt is not None and cnt < MIN_FREQ:
                    continue
                out.append({"repo": repo, "signal": tool, "item": it})
        except Exception:
            continue  # fail-open per tool
    return out


def render(rows: list[dict]) -> str:
    lines = [
        "# Directive Spark — candidates for review",
        "",
        "Proactively surfaced from the brain's telemetry. **Not directives** — review each and, if",
        'it warrants a rule, promote it via the normal "lock it" flow into DIRECTIVES.md.',
        f"\nRepos scanned: {', '.join(REPOS)} · frequency floor: {MIN_FREQ}\n",
    ]
    if not rows:
        lines.append("_No recurring patterns above the floor this run._")
        return "\n".join(lines) + "\n"
    by_signal: dict[str, list[dict]] = {}
    for r in rows:
        by_signal.setdefault(r["signal"], []).append(r)
    for signal, items in by_signal.items():
        lines.append(f"## {signal} ({len(items)})")
        for r in items:
            summary = json.dumps(r["item"], default=str)[:300]
            lines.append(f"- **[{r['repo']}]** {summary}")
        lines.append("")
    return "\n".join(lines) + "\n"


async def _run() -> int:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    rows: list[dict] = []
    async with streamable_http_client(URL) as (rd, wr, _):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            for repo in REPOS:
                rows.extend(await gather(s, repo))
    OUT.write_text(render(rows))
    print(f"[spark] {len(rows)} candidate pattern(s) -> {OUT}", file=sys.stderr)
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
