#!/usr/bin/env python3
"""#7: scheduled review / consolidation cadence (run weekly via launchd).

One routine that keeps the memory trustworthy on a schedule instead of by memory:
  1. Directive Spark (#3) — refresh spark-candidates.md from telemetry.
  2. Consolidation/integrity — run_integrity_audit_workflow + run_compaction_workflow per
     active repo (best-effort; reports problems, never blocks).
  3. Bump the DIRECTIVES.md "Last reviewed:" stamp to today's date.

Stamp bump is committed by the wrapper (weekly-review.sh) so sync_corpus mirrors it.
Env: CLAUDE_CORPUS_MCP_URL, MK_SPARK_REPOS (active repos), --date YYYY-MM-DD (wrapper passes today).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

URL = os.environ.get("CLAUDE_CORPUS_MCP_URL", "https://memory-knowledge.azurewebsites.net/mcp/")
REPOS = [r.strip() for r in os.environ.get(
    "MK_SPARK_REPOS", "taggable-api,fcsapi,taggable-server").split(",") if r.strip()]
DIRECTIVES = Path(__file__).resolve().parent / "DIRECTIVES.md"
_STAMP_RE = re.compile(r"(<!-- Last reviewed: )\d{4}-\d{2}-\d{2}( -->)")


def bump_review_stamp(text: str, date: str) -> str:
    """Replace the 'Last reviewed: YYYY-MM-DD' header stamp with `date`. Idempotent."""
    return _STAMP_RE.sub(rf"\g<1>{date}\g<2>", text, count=1)


def _text(result) -> str:
    for b in result.content:
        if getattr(b, "type", None) == "text":
            return b.text
    return ""


async def consolidate(session, repos: list[str]) -> list[str]:
    """Best-effort integrity audit + compaction per repo. Returns one status line each."""
    notes = []
    for repo in repos:
        for tool in ("run_integrity_audit_workflow", "run_compaction_workflow"):
            try:
                res = await session.call_tool(tool, {"repository_key": repo})
                status = json.loads(_text(res)).get("status", "?")
                notes.append(f"{tool}[{repo}]={status}")
            except Exception as exc:  # noqa: BLE001 — best-effort
                notes.append(f"{tool}[{repo}]=error:{str(exc)[:50]}")
    return notes


async def _run(date: str) -> int:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    # 1. Spark (reuse the module so logic stays in one place)
    try:
        import importlib.util
        spark_path = Path(__file__).resolve().parent / "directive_spark.py"
        spec = importlib.util.spec_from_file_location("directive_spark", spark_path)
        spark = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(spark)
        await spark._run()
    except Exception as exc:  # noqa: BLE001
        print(f"[weekly-review] spark failed (continuing): {exc}", file=sys.stderr)

    # 2. Consolidation/integrity (best-effort)
    try:
        async with streamable_http_client(URL) as (rd, wr, _):
            async with ClientSession(rd, wr) as s:
                await s.initialize()
                for line in await consolidate(s, REPOS):
                    print(f"[weekly-review] {line}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"[weekly-review] consolidation failed (continuing): {exc}", file=sys.stderr)

    # 3. Bump the review stamp (wrapper commits it)
    if DIRECTIVES.exists():
        DIRECTIVES.write_text(bump_review_stamp(DIRECTIVES.read_text(), date))
        print(f"[weekly-review] stamped Last reviewed: {date}", file=sys.stderr)
    return 0


def main() -> int:
    date = "1970-01-01"
    if "--date" in sys.argv:
        date = sys.argv[sys.argv.index("--date") + 1]
    return asyncio.run(_run(date))


if __name__ == "__main__":
    raise SystemExit(main())
