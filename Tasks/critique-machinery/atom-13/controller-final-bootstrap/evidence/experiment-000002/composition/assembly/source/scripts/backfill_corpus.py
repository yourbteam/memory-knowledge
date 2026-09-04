#!/usr/bin/env python3
"""Backfill the Tier-2 corpus with the working-agreement directives via the deployed MCP.

Parses working-agreement/DIRECTIVES.md, and for each directive (G0, G1, ...) ingests one
`directive_rationale` corpus entry by calling the deployed `run_corpus_upsert_workflow`
MCP tool (server-side embedding; no local fastembed needed).

Usage:
    python scripts/backfill_corpus.py [--url URL] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

DEFAULT_URL = "https://memory-knowledge.azurewebsites.net/mcp/"
DIRECTIVES = Path(__file__).resolve().parent.parent / "working-agreement" / "DIRECTIVES.md"

# Match "## G0 · Title" headings; capture the GN id and the full heading title.
_HEADING = re.compile(r"^##\s+(G\d+)\s+·\s+(.*)$")


def parse_directives(text: str) -> list[dict]:
    """Return one entry per directive section: kind/title/body_text/link_slug/tags."""
    lines = text.splitlines()
    entries: list[dict] = []
    cur: dict | None = None
    body: list[str] = []

    def flush():
        if cur is not None:
            # body_text = everything up to the **Set:** footer line.
            kept = []
            for ln in body:
                if ln.strip().startswith("**Set:**"):
                    break
                kept.append(ln)
            cur["body_text"] = "\n".join(kept).strip()
            entries.append(cur)

    for ln in lines:
        m = _HEADING.match(ln)
        if m:
            flush()
            gid, title = m.group(1), m.group(2).strip()
            cur = {
                "kind": "directive_rationale",
                "title": f"{gid} · {title}",
                "link_slug": gid.lower(),
                "tags": ["directive", gid.lower()],
            }
            body = []
        elif cur is not None:
            body.append(ln)
    flush()
    return entries


def _tool_text(result) -> str:
    for block in result.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


async def run(url: str, entries: list[dict], dry_run: bool) -> int:
    if dry_run:
        for e in entries:
            print(f"[dry-run] would upsert {e['link_slug']}: {e['title']}  ({len(e['body_text'])} chars)")
        return 0

    failures = 0
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for e in entries:
                res = await session.call_tool("run_corpus_upsert_workflow", {
                    "kind": e["kind"],
                    "title": e["title"],
                    "body_text": e["body_text"],
                    "link_slug": e["link_slug"],
                    "tags": e["tags"],
                })
                raw = _tool_text(res)
                try:
                    data = json.loads(raw)
                    status = data.get("status")
                    key = (data.get("data") or {}).get("entry_key")
                    err = data.get("error")
                except Exception:
                    status, key, err = "unparseable", None, raw[:200]
                ok = status == "success"
                failures += 0 if ok else 1
                print(f"{'OK ' if ok else 'ERR'} {e['link_slug']:4} status={status} entry_key={key}" + (f" error={err}" if err else ""))
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    entries = parse_directives(DIRECTIVES.read_text())
    if not entries:
        print("No directive sections found in DIRECTIVES.md", file=sys.stderr)
        return 1
    print(f"Parsed {len(entries)} directive entries: {', '.join(e['link_slug'] for e in entries)}")
    return asyncio.run(run(args.url, entries, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
