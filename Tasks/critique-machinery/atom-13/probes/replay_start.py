#!/usr/bin/env python3
"""Replay frozen atom requests through Atom Controller start without model calls."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("controller", type=Path)
    parser.add_argument("repository", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("cases", nargs="+", help="label=request=run")
    args = parser.parse_args()
    controller = args.controller.resolve()
    repository = args.repository.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    summary = []
    for raw in args.cases:
        label, request, run = raw.split("=", 2)
        completed = subprocess.run(
            [sys.executable, str(controller), "start", request, run],
            cwd=repository,
            text=True,
            capture_output=True,
            check=False,
        )
        (args.output / f"{label}.stdout.txt").write_text(completed.stdout)
        (args.output / f"{label}.stderr.txt").write_text(completed.stderr)
        summary.append({
            "label": label,
            "request": request,
            "run": run,
            "returncode": completed.returncode,
        })
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
