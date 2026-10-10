#!/usr/bin/env python3
"""Interactive zero-argument entry point for the bounded Atlas route batch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import route_batch


def _ask(label: str) -> str:
    value = input(label).strip()
    if not value:
        raise route_batch.BatchError(f"{label.rstrip(': ')} is required")
    return value


def main() -> int:
    try:
        print("Atlas route batch")
        print("1. Prepare or resume batch")
        print("2. Read status")
        print("3. Show next native-worker relay")
        choice = _ask("Choose 1, 2, or 3: ")
        if choice == "1":
            repo = _ask("Read-only target repository path: ")
            db = _ask("Atlas database path: ")
            run = _ask("Batch run directory (outside the target repository): ")
            ids = [item.strip() for item in input("Route IDs (comma-separated, at most 3): ").split(",") if item.strip()]
            result = route_batch.prepare(repo, db, ids, run)
        elif choice == "2":
            result = route_batch.status(_ask("Batch run directory: "))
        elif choice == "3":
            result = route_batch.next_job(_ask("Batch run directory: "))
        else:
            raise route_batch.BatchError("choice must be 1, 2, or 3")
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
        relay = result.get("relay_path") if isinstance(result, dict) else None
        if choice == "1" and "run" in locals():
            relay = str(Path(run).expanduser().absolute() / "batch-relay.md")
        if isinstance(relay, str):
            print(f"\nNative relay instructions: {relay}")
            print(Path(relay).read_text(encoding="utf-8"))
        return 0
    except (route_batch.BatchError, OSError, EOFError) as exc:
        print(f"route-batch-launch: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
