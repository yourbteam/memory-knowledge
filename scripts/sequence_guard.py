#!/usr/bin/env python3
"""Guard repeatable operational commands against memory-only execution."""

from __future__ import annotations

import argparse
import json
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts.directive_guard import (
        DEFAULT_DIRECTIVES_PATH,
        DEFAULT_MAX_AGE_MINUTES,
        DEFAULT_STATE_PATH as DEFAULT_DIRECTIVE_STATE_PATH,
        check_directive_read_state,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from directive_guard import (
        DEFAULT_DIRECTIVES_PATH,
        DEFAULT_MAX_AGE_MINUTES,
        DEFAULT_STATE_PATH as DEFAULT_DIRECTIVE_STATE_PATH,
        check_directive_read_state,
    )


DEFAULT_STATE_PATH = Path("/private/tmp/workflow-orch-active-sequence.json")
ALLOWED_SOURCES = {"sequence_doc", "discovery_log", "script", "tool_help"}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repo_root(path: str | None) -> Path:
    return Path(path or ".").resolve()


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _state_path(value: str | None) -> Path:
    return Path(value).resolve() if value else DEFAULT_STATE_PATH


def _directive_path(value: str | None) -> Path:
    return Path(value).resolve() if value else DEFAULT_DIRECTIVES_PATH


def _directive_state_path(value: str | None) -> Path:
    return Path(value).resolve() if value else DEFAULT_DIRECTIVE_STATE_PATH


def _require_directives(args: argparse.Namespace) -> None:
    check_directive_read_state(
        directives_path=_directive_path(args.directives_path),
        state_path=_directive_state_path(args.directive_state),
        max_age_minutes=int(args.directive_max_age_minutes),
    )


def _write_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"active sequence state not found: {path}")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"active sequence state is invalid JSON: {path}: {exc}") from exc
    if not isinstance(state, dict):
        raise SystemExit(f"active sequence state must be a JSON object: {path}")
    return state


def _require_text(value: str, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise SystemExit(f"{label} is required")
    return stripped


def _path_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _source_ref_text(source_ref: Path) -> str:
    if not source_ref.is_file():
        raise SystemExit(f"source ref file not found: {source_ref}")
    return source_ref.read_text(encoding="utf-8")


def _is_placeholder_token(token: str) -> bool:
    return token.startswith("<") and token.endswith(">") and len(token) > 2 and token != "<command>"


def _tokens_match_shape(command_tokens: list[str], shape_tokens: list[str]) -> bool:
    if len(command_tokens) != len(shape_tokens):
        return False
    for command_token, shape_token in zip(command_tokens, shape_tokens):
        if _is_placeholder_token(shape_token):
            continue
        if command_token != shape_token:
            return False
    return True


def _command_matches_documented_shape(command: str, text: str) -> bool:
    try:
        command_tokens = shlex.split(command)
    except ValueError:
        return False
    for line in text.splitlines():
        shape = line.strip()
        if not shape or "<" not in shape or ">" not in shape or "<command>" in shape:
            continue
        try:
            shape_tokens = shlex.split(shape)
        except ValueError:
            continue
        if any(_is_placeholder_token(token) for token in shape_tokens) and _tokens_match_shape(
            command_tokens, shape_tokens
        ):
            return True
    return False


def _command_in_text(command: str, text: str, source_ref: Path) -> None:
    if command not in text and not _command_matches_documented_shape(command, text):
        raise SystemExit(f"command is not recorded in source ref: {source_ref}")


def _script_command_mentions(command: str, script_ref: Path) -> None:
    candidates = {str(script_ref), script_ref.name}
    try:
        candidates.add(str(script_ref.relative_to(Path.cwd())))
    except ValueError:
        pass
    if not any(candidate in command for candidate in candidates):
        raise SystemExit(f"command does not invoke source script: {script_ref}")


def cmd_activate(args: argparse.Namespace) -> int:
    _require_directives(args)
    root = _repo_root(args.root)
    sequence_doc = _resolve(root, args.sequence_doc) if args.sequence_doc else None
    discovery_log = _resolve(root, args.discovery_log) if args.discovery_log else None
    if bool(sequence_doc) == bool(discovery_log):
        raise SystemExit("activate requires exactly one of --sequence-doc or --discovery-log")
    if sequence_doc and not sequence_doc.is_file():
        raise SystemExit(f"sequence doc not found: {sequence_doc}")
    if discovery_log and not discovery_log.is_file():
        raise SystemExit(f"discovery log not found: {discovery_log}")

    state = {
        "activeSequence": _require_text(args.sequence_id, "sequence id"),
        "activatedAtUtc": _utc_now(),
        "mode": "registered" if sequence_doc else "discovery",
        "sequenceDoc": str(sequence_doc) if sequence_doc else None,
        "discoveryLog": str(discovery_log) if discovery_log else None,
    }
    path = _state_path(args.state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_json({"ok": True, "statePath": str(path), "state": state})
    return 0


def _validate_source_against_state(
    *,
    root: Path,
    state: dict[str, Any],
    source: str,
    source_ref: Path,
    command: str,
    evidence_text: str | None,
) -> None:
    if source not in ALLOWED_SOURCES:
        raise SystemExit(
            f"command source must be one of {sorted(ALLOWED_SOURCES)}; got {source!r}"
        )
    if source == "sequence_doc":
        active_doc = state.get("sequenceDoc")
        if not active_doc:
            raise SystemExit("active sequence is not backed by a sequence document")
        if source_ref != Path(str(active_doc)).resolve():
            raise SystemExit("sequence_doc source ref does not match active sequence document")
        _command_in_text(command, _source_ref_text(source_ref), source_ref)
        return
    if source == "discovery_log":
        active_log = state.get("discoveryLog")
        if not active_log:
            raise SystemExit("active sequence is not backed by a discovery log")
        if source_ref != Path(str(active_log)).resolve():
            raise SystemExit("discovery_log source ref does not match active discovery log")
        _command_in_text(command, _source_ref_text(source_ref), source_ref)
        return
    if source == "script":
        if not _path_under(source_ref, root / "scripts"):
            raise SystemExit(f"script source ref must be under scripts/: {source_ref}")
        if not source_ref.is_file():
            raise SystemExit(f"script source ref not found: {source_ref}")
        _script_command_mentions(command, source_ref)
        return
    if source == "tool_help":
        _require_text(evidence_text or "", "tool_help evidence text")
        return


def cmd_guard(args: argparse.Namespace) -> int:
    _require_directives(args)
    root = _repo_root(args.root)
    state_path = _state_path(args.state)
    state = _load_state(state_path)
    step = _require_text(args.step, "step")
    command = _require_text(args.command, "command")
    source = _require_text(args.source, "source")
    source_ref = _resolve(root, _require_text(args.source_ref, "source ref"))
    _validate_source_against_state(
        root=root,
        state=state,
        source=source,
        source_ref=source_ref,
        command=command,
        evidence_text=args.evidence_text,
    )
    _write_json(
        {
            "ok": True,
            "activeSequence": state.get("activeSequence"),
            "step": step,
            "commandSource": source,
            "sourceRef": str(source_ref),
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command_name", required=True)

    activate = sub.add_parser("activate", help="Record the active operational sequence.")
    activate.add_argument("--sequence-id", required=True)
    activate.add_argument("--sequence-doc")
    activate.add_argument("--discovery-log")
    activate.add_argument("--root")
    activate.add_argument("--state")
    activate.add_argument("--directives-path")
    activate.add_argument("--directive-state")
    activate.add_argument("--directive-max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES)
    activate.set_defaults(func=cmd_activate)

    guard = sub.add_parser("guard", help="Verify a command has an allowed sequence source.")
    guard.add_argument("--step", required=True)
    guard.add_argument("--command", required=True)
    guard.add_argument("--source", required=True)
    guard.add_argument("--source-ref", required=True)
    guard.add_argument("--evidence-text")
    guard.add_argument("--root")
    guard.add_argument("--state")
    guard.add_argument("--directives-path")
    guard.add_argument("--directive-state")
    guard.add_argument("--directive-max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES)
    guard.set_defaults(func=cmd_guard)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
