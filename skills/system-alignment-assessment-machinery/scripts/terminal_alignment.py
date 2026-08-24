#!/usr/bin/env python3
"""Create or freshly verify the terminal System Alignment Assessment package."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from terminal_input_binding import InputBindingError, bind
from terminal_package_builder import TerminalPackageError, build, canonical


class TerminalAlignmentError(RuntimeError):
    pass


def load(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_bytes())
    except Exception as exc:
        raise TerminalAlignmentError(f"{label} is unavailable or invalid: {exc}") from None
    if type(value) is not dict:
        raise TerminalAlignmentError(f"{label} must be one object")
    return value


def create(spec_path: Path) -> dict:
    return build(bind(load(spec_path, "terminal specification")))


def write_once(value: dict, output: Path) -> None:
    if output.exists():
        raise TerminalAlignmentError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def verify(artifact_path: Path) -> dict:
    observed = load(artifact_path, "terminal package")
    if observed.get("artifact_type") != "system-alignment-assessment-package":
        raise TerminalAlignmentError("terminal package artifact type changed")
    expected = build(bind({"schema_version": 1, "inputs": observed.get("inputs")}))
    if canonical(observed) != canonical(expected):
        raise TerminalAlignmentError("terminal package does not match freshly rebuilt evidence")
    return observed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--spec", type=Path, required=True)
    create_parser.add_argument("--output", type=Path, required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = create(args.spec)
            write_once(value, args.output)
        else:
            value = verify(args.artifact)
    except (TerminalAlignmentError, InputBindingError, TerminalPackageError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"artifact_sha256": value["artifact_sha256"], "overall_verdict": value["overall_verdict"], "status": value["status"], "summary": value["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
