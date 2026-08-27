#!/usr/bin/env python3
"""Fail closed when the published command inventory drifts from cover.py."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path


BEGIN = "<!-- BEGIN PUBLIC COMMAND SURFACE -->"
END = "<!-- END PUBLIC COMMAND SURFACE -->"
ALLOWED_CATEGORIES = {"coverage", "extraction", "owner decision", "document assembly"}
ROW = re.compile(r"^\| `([a-z][a-z-]*)` \| ([^|]+?) \| ([^|]+?) \|$")


def documented(skill_path: Path) -> dict[str, dict[str, str]]:
    text = skill_path.read_text(encoding="utf-8")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError("public-command-surface-markers")
    body = text.split(BEGIN, 1)[1].split(END, 1)[0]
    rows: dict[str, dict[str, str]] = {}
    for line in body.splitlines():
        match = ROW.fullmatch(line.strip())
        if not match:
            continue
        command, category, boundary = (part.strip() for part in match.groups())
        if command in rows:
            raise ValueError(f"duplicate-documented-command:{command}")
        if category not in ALLOWED_CATEGORIES:
            raise ValueError(f"invalid-command-category:{command}:{category}")
        if not boundary:
            raise ValueError(f"missing-command-boundary:{command}")
        rows[command] = {"category": category, "boundary": boundary}
    return rows


def executable(cover_path: Path) -> set[str]:
    spec = importlib.util.spec_from_file_location("requirements_machinery_cover", cover_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    parser = module.build_parser()
    action = next(
        item for item in parser._actions
        if isinstance(item, argparse._SubParsersAction)
    )
    return set(action.choices)


def check(skill_path: Path, cover_path: Path) -> dict[str, object]:
    docs = documented(skill_path)
    cli = executable(cover_path)
    missing = sorted(cli - set(docs))
    extra = sorted(set(docs) - cli)
    result = {
        "documented": len(docs),
        "executable": len(cli),
        "missing_from_contract": missing,
        "not_executable": extra,
        "categories": {name: docs[name]["category"] for name in sorted(docs)},
        "parity": not missing and not extra,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--cover", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(args.skill, args.cover)
    except (OSError, ValueError) as exc:
        print(json.dumps({"parity": False, "error": str(exc)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["parity"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
