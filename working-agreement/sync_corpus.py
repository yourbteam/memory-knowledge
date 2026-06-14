#!/usr/bin/env python3
"""Sync the Tier-2 corpus to DIRECTIVES.md (full mirror) via the deployed MCP.

Run from a git post-commit hook (see sync-corpus.sh). It makes the corpus mirror the file:

  1. Parse the CURRENT DIRECTIVES.md and upsert every directive (idempotent).
  2. Parse the PREVIOUS version (``git show HEAD~1:working-agreement/DIRECTIVES.md``) and
     deactivate any entry whose (kind, link_slug, title) identity is no longer present — i.e.
     a rule that was renamed (old title gone) or deleted. This is the prune the additive
     backfill cannot do; it calls the ``corpus_deactivate`` MCP tool.

Identity matches the write path exactly (entry_key = f(kind, link_slug, title)), so comparing
the (kind, link_slug, title) triple is equivalent to comparing entry_keys.

Fail-soft: prune is skipped when there is no previous revision (first commit / shallow clone).

Usage:
    python working-agreement/sync_corpus.py [--url URL] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

REPO_ROOT = Path(__file__).resolve().parent.parent
DIRECTIVES_REL = "working-agreement/DIRECTIVES.md"
DIRECTIVES = REPO_ROOT / DIRECTIVES_REL
DEFAULT_URL = "https://memory-knowledge.azurewebsites.net/mcp/"

# Reuse the single, tested directives parser from the backfill script.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from backfill_corpus import parse_directives  # noqa: E402


def _identity(entry: dict) -> tuple[str, str | None, str]:
    return (entry["kind"], entry.get("link_slug"), entry["title"])


def _previous_directives() -> str | None:
    """Return DIRECTIVES.md content at HEAD~1, or None if unavailable (first commit, etc.)."""
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD~1:{DIRECTIVES_REL}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    return out.stdout if out.returncode == 0 else None


def _tool_text(result) -> str:
    for block in result.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


async def run(url: str, upserts: list[dict], orphans: list[dict], dry_run: bool) -> int:
    if dry_run:
        for e in upserts:
            print(f"[dry-run] upsert {e['link_slug']}: {e['title']}  ({len(e['body_text'])} chars)")
        for e in orphans:
            print(f"[dry-run] deactivate {e['link_slug']}: {e['title']}")
        return 0

    failures = 0
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for e in upserts:
                res = await session.call_tool("run_corpus_upsert_workflow", {
                    "kind": e["kind"],
                    "title": e["title"],
                    "body_text": e["body_text"],
                    "link_slug": e["link_slug"],
                    "tags": e["tags"],
                })
                ok = _report("upsert", e, _tool_text(res))
                failures += 0 if ok else 1

            for e in orphans:
                res = await session.call_tool("corpus_deactivate", {
                    "kind": e["kind"],
                    "title": e["title"],
                    "link_slug": e["link_slug"],
                })
                ok = _report("deactivate", e, _tool_text(res))
                failures += 0 if ok else 1
    return failures


def _report(op: str, entry: dict, raw: str) -> bool:
    try:
        data = json.loads(raw)
        status = data.get("status")
        key = (data.get("data") or {}).get("entry_key")
        err = data.get("error")
    except Exception:
        status, key, err = "unparseable", None, raw[:200]
    ok = status == "success"
    print(f"{'OK ' if ok else 'ERR'} {op:10} {entry['link_slug']:4} status={status} entry_key={key}"
          + (f" error={err}" if err else ""))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    current = parse_directives(DIRECTIVES.read_text())
    if not current:
        print("No directive sections found in DIRECTIVES.md", file=sys.stderr)
        return 1

    prev_text = _previous_directives()
    if prev_text is None:
        orphans: list[dict] = []
        print("No previous DIRECTIVES.md revision found; skipping prune (upsert only).")
    else:
        current_ids = {_identity(e) for e in current}
        orphans = [e for e in parse_directives(prev_text) if _identity(e) not in current_ids]

    print(f"Sync: {len(current)} upsert, {len(orphans)} deactivate "
          f"({', '.join(e['link_slug'] for e in current)})")
    return asyncio.run(run(args.url, current, orphans, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
