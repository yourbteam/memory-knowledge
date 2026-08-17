#!/usr/bin/env python3
"""Record and verify that the canonical working-agreement directives were read."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts import script_intake
except ModuleNotFoundError:  # direct script execution
    import script_intake


DEFAULT_DIRECTIVES_PATH = Path("/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md")
STATE_PATH_PREFIX = "/private/tmp/workflow-orch-directive-guard"


def default_state_path(directives_path: Path) -> Path:
    """Where the read state for one directives file lives.

    One file per directives checkout, not one file for the machine. Until 2026-08-17 every
    session on this host shared /private/tmp/workflow-orch-directive-guard.json, so a session
    working from a second checkout -- a git worktree, a codex sandbox -- overwrote the state
    the first session had recorded, and the next activation refused with "directive read state
    was recorded for <other path>, expected <this path>". The ledger carries nine blockers on
    this receipt and seven of them are still open, because each occurrence was cleared by
    re-recording the read rather than by removing the contention.
    """
    digest = hashlib.sha256(str(directives_path.resolve()).encode("utf-8")).hexdigest()[:12]
    return Path(f"{STATE_PATH_PREFIX}-{digest}.json")


#: The canonical checkout's state file, kept as a module constant for callers that have no
#: directives path in hand. A caller that does have one derives its own with
#: ``default_state_path`` instead, so two checkouts never write the same file.
DEFAULT_STATE_PATH = default_state_path(DEFAULT_DIRECTIVES_PATH)
DEFAULT_MAX_AGE_MINUTES = 1440
SCHEMA_VERSION = 1
INTAKE_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        {
            "id": "command_name",
            "prompt": "Directive guard action",
            "response_format": "One action name as plain text.",
            "example": "read",
            "constraints": "Use exactly one allowed value; do not add quotes or JSON.",
            "type": "choice",
            "choices": ["read", "check"],
            "required": True,
        },
        {
            "id": "mode",
            "prompt": "Sequence or task mode",
            "response_format": "One non-empty mode identifier as plain text.",
            "example": "greenfield-full-drive",
            "constraints": "Do not add quotes, flags, or JSON.",
            "type": "string",
            "required": True,
            "when": {"field": "command_name", "equals": "read"},
        },
        {
            "id": "directives_path",
            "prompt": "Canonical directives path",
            "response_format": "One filesystem path as plain text.",
            "example": "/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md",
            "constraints": "Press Enter for the displayed default; do not add quotes.",
            "type": "path",
            "default": str(DEFAULT_DIRECTIVES_PATH),
        },
        {
            "id": "state",
            "prompt": "Directive-read state path",
            "response_format": "One filesystem path as plain text.",
            "example": "/private/tmp/workflow-orch-directive-guard.json",
            "constraints": "Press Enter for the displayed default; do not add quotes.",
            "type": "path",
            "default": str(DEFAULT_STATE_PATH),
        },
        {
            "id": "max_age_minutes",
            "prompt": "Maximum directive-read age in minutes",
            "response_format": "One positive whole number written with digits.",
            "example": "60",
            "constraints": "Value must be at least 1; do not add units or JSON.",
            "type": "integer",
            "default": DEFAULT_MAX_AGE_MINUTES,
            "minimum": 1,
            "when": {"field": "command_name", "equals": "check"},
        },
    ],
}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _utc_now_text() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _write_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _path(value: str | None, default: Path) -> Path:
    return Path(value).expanduser().resolve() if value else default


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"directives file not found: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_utc(value: str, *, label: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SystemExit(f"{label} is not a valid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise SystemExit(f"{label} must include UTC timezone: {value!r}")
    return parsed.astimezone(UTC)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"directive read state not found: {path}")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"directive read state is invalid JSON: {path}: {exc}") from exc
    if not isinstance(state, dict):
        raise SystemExit(f"directive read state must be a JSON object: {path}")
    return state


def write_directive_read_state(
    *,
    directives_path: Path,
    state_path: Path,
    mode: str,
) -> dict[str, Any]:
    mode_text = mode.strip()
    if not mode_text:
        raise SystemExit("mode is required")
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "directivesPath": str(directives_path),
        "directivesSha256": _sha256(directives_path),
        "readAtUtc": _utc_now_text(),
        "mode": mode_text,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state


def check_directive_read_state(
    *,
    directives_path: Path,
    state_path: Path,
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
) -> dict[str, Any]:
    if max_age_minutes <= 0:
        raise SystemExit("directive max age minutes must be greater than zero")
    state = _load_state(state_path)
    if state.get("schemaVersion") != SCHEMA_VERSION:
        raise SystemExit("directive read state schemaVersion is unsupported")
    stored_path = str(state.get("directivesPath") or "").strip()
    if Path(stored_path).resolve() != directives_path.resolve():
        raise SystemExit(
            f"directive read state was recorded for {stored_path or '<missing>'}, expected {directives_path}"
        )
    stored_sha = str(state.get("directivesSha256") or "").strip()
    current_sha = _sha256(directives_path)
    if stored_sha != current_sha:
        raise SystemExit("directive read state is stale because directives SHA changed")
    read_at = _parse_utc(str(state.get("readAtUtc") or ""), label="readAtUtc")
    if read_at + timedelta(minutes=max_age_minutes) < _utc_now():
        raise SystemExit("directive read state is stale because it exceeded max age")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "directivesPath": str(directives_path),
        "directivesSha256": current_sha,
        "readAtUtc": state.get("readAtUtc"),
        "mode": state.get("mode"),
        "statePath": str(state_path),
        "maxAgeMinutes": max_age_minutes,
    }


def cmd_read(args: argparse.Namespace) -> int:
    directives_path = _path(args.directives_path, DEFAULT_DIRECTIVES_PATH)
    state_path = _path(args.state, default_state_path(directives_path))
    state = write_directive_read_state(
        directives_path=directives_path,
        state_path=state_path,
        mode=args.mode,
    )
    _write_json({"ok": True, "statePath": str(state_path), "state": state})
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    directives_path = _path(args.directives_path, DEFAULT_DIRECTIVES_PATH)
    state_path = _path(args.state, default_state_path(directives_path))
    state = check_directive_read_state(
        directives_path=directives_path,
        state_path=state_path,
        max_age_minutes=int(args.max_age_minutes),
    )
    _write_json({"ok": True, "state": state})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command_name", required=True)

    read = sub.add_parser("read", help="Record that the canonical directives were read.")
    read.add_argument("--mode", required=True)
    read.add_argument("--directives-path")
    read.add_argument("--state")
    read.set_defaults(func=cmd_read)

    check = sub.add_parser("check", help="Verify a fresh directive-read state exists.")
    check.add_argument("--directives-path")
    check.add_argument("--state")
    check.add_argument("--max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES)
    check.set_defaults(func=cmd_check)

    return parser


def run_intake(answers: dict[str, Any]) -> int:
    command_name = answers["command_name"]
    if command_name == "read":
        args = argparse.Namespace(
            mode=answers["mode"],
            directives_path=answers["directives_path"],
            state=answers["state"],
        )
        return cmd_read(args)
    args = argparse.Namespace(
        directives_path=answers["directives_path"],
        state=answers["state"],
        max_age_minutes=answers["max_age_minutes"],
    )
    return cmd_check(args)


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        try:
            return run_intake(script_intake.collect(INTAKE_SPEC))
        except script_intake.IntakeCancelled as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 130
    parser = build_parser()
    args = parser.parse_args(values)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
