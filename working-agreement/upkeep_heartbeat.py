#!/usr/bin/env python3
"""WS5 dead-man's-switch — fail (non-zero exit) if the upkeep cadence has stalled.

Detects the original failure mode (a schedule that silently never fires) by checking BOTH halves:
  (a) repo half — the `DIRECTIVES.md` "Last reviewed" stamp, which the weekly CI cron bumps;
  (b) server half — the in-server maintenance scheduler, via the `get_scheduler_heartbeat` MCP tool
      (age of the latest integrity_audit/compaction job).

A non-zero exit makes the GitHub Actions run red → GitHub emails the failure. Run it on a schedule
independent of the upkeep job so a dead upkeep cron is what trips it.

Env: CLAUDE_CORPUS_MCP_URL, MK_HEARTBEAT_STAMP_MAX_DAYS (default 9 = 7d cadence + 2d grace),
MK_HEARTBEAT_SERVER_FACTOR (default 1.5 × maintenance interval).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

URL = os.environ.get("CLAUDE_CORPUS_MCP_URL", "https://memory-knowledge.azurewebsites.net/mcp/")
DIRECTIVES = Path(__file__).resolve().parent / "DIRECTIVES.md"
STAMP_MAX_DAYS = int(os.environ.get("MK_HEARTBEAT_STAMP_MAX_DAYS", "9"))
SERVER_FACTOR = float(os.environ.get("MK_HEARTBEAT_SERVER_FACTOR", "1.5"))
_STAMP_RE = re.compile(r"Last reviewed: (\d{4}-\d{2}-\d{2})")


def stamp_age_days(text: str, today: dt.date | None = None) -> int | None:
    """Days since the DIRECTIVES 'Last reviewed' stamp; None if the stamp is absent."""
    m = _STAMP_RE.search(text)
    if not m:
        return None
    today = today or dt.date.today()
    return (today - dt.date.fromisoformat(m.group(1))).days


async def _server_heartbeat() -> tuple[float | None, int | None]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(URL) as (rd, wr, _):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            res = await s.call_tool("get_scheduler_heartbeat", {})
            txt = next((b.text for b in res.content if getattr(b, "type", None) == "text"), "")
            d = json.loads(txt)
            if isinstance(d, dict) and isinstance(d.get("result"), str):
                d = json.loads(d["result"])
            data = d.get("data") or {}
            return data.get("age_seconds"), data.get("maintenance_interval_seconds")


def main() -> int:
    failures: list[str] = []

    # (a) repo half — DIRECTIVES stamp
    try:
        age = stamp_age_days(DIRECTIVES.read_text())
    except Exception as exc:  # noqa: BLE001
        age = None
        failures.append(f"could not read DIRECTIVES stamp: {exc!r}")
    if age is None or age > STAMP_MAX_DAYS:
        failures.append(f"DIRECTIVES 'Last reviewed' stale: age={age}d > {STAMP_MAX_DAYS}d (weekly CI cron not committing)")

    # (b) server half — maintenance scheduler heartbeat
    try:
        srv_age, interval = asyncio.run(_server_heartbeat())
        threshold = (interval or 604800) * SERVER_FACTOR
        if srv_age is None or srv_age > threshold:
            failures.append(f"maintenance scheduler stale: age={srv_age}s > {threshold:.0f}s (server scheduler not ticking)")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"server heartbeat unreachable: {exc!r}")

    if failures:
        print("UPKEEP HEARTBEAT FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("upkeep heartbeat OK (stamp + server scheduler fresh)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
