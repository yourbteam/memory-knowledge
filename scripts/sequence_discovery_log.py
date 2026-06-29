#!/usr/bin/env python3
"""Create and update repeatable-sequence discovery logs."""

from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence


DISCOVERY_DIR = Path("operations/sequences/discovery")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unnamed-sequence"


def _repo_root(path: str | None) -> Path:
    return Path(path or ".").resolve()


def _discovery_path(root: Path, name: str, date_value: str | None) -> Path:
    date_text = date_value or datetime.now(UTC).strftime("%Y-%m-%d")
    return root / DISCOVERY_DIR / f"{date_text}-{_slug(name)}.md"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cmd_start(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    path = _discovery_path(root, args.sequence_name, args.date)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not args.force:
        raise SystemExit(f"discovery log already exists: {path}")
    text = f"""# Sequence Discovery Log: {args.sequence_name}

Status: discovery
CreatedAtUtc: {_utc_now()}
RegisteredSequenceMatch: none

## Intended Outcome

{args.outcome.strip()}

## Why This Looks Repeatable

{args.why_repeatable.strip()}

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
"""
    path.write_text(text, encoding="utf-8")
    print(path)
    return 0


def cmd_append_step(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    if not path.is_file():
        raise SystemExit(f"discovery log not found: {path}")
    text = path.read_text(encoding="utf-8")
    marker = "| step | command or action | result | correction or note |\n| --- | --- | --- | --- |\n"
    if marker not in text:
        raise SystemExit("discovery log is missing the commands table")
    row = f"| {args.step.strip()} | {args.command.strip()} | {args.result.strip()} | {args.note.strip()} |\n"
    text = text.replace(marker, marker + row, 1)
    path.write_text(text, encoding="utf-8")
    print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--sequence-name", required=True)
    start.add_argument("--outcome", required=True)
    start.add_argument("--why-repeatable", required=True)
    start.add_argument("--root")
    start.add_argument("--date")
    start.add_argument("--force", action="store_true")
    start.set_defaults(func=cmd_start)

    append_step = sub.add_parser("append-step")
    append_step.add_argument("--file", required=True)
    append_step.add_argument("--step", required=True)
    append_step.add_argument("--command", required=True)
    append_step.add_argument("--result", required=True)
    append_step.add_argument("--note", default="")
    append_step.set_defaults(func=cmd_append_step)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
