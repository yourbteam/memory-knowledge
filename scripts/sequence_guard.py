#!/usr/bin/env python3
"""Guard operational commands with classification, selection, and bundle receipts."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts.directive_guard import (
        DEFAULT_DIRECTIVES_PATH, DEFAULT_MAX_AGE_MINUTES,
        DEFAULT_STATE_PATH as DEFAULT_DIRECTIVE_STATE_PATH, check_directive_read_state,
    )
    from scripts import work_memory
except ModuleNotFoundError:
    from directive_guard import (  # type: ignore
        DEFAULT_DIRECTIVES_PATH, DEFAULT_MAX_AGE_MINUTES,
        DEFAULT_STATE_PATH as DEFAULT_DIRECTIVE_STATE_PATH, check_directive_read_state,
    )
    import work_memory  # type: ignore


ALLOWED_SOURCES = {"sequence_doc", "discovery_log", "script", "tool_help"}


def _root(value: str | None) -> Path:
    return Path(value or ".").resolve()


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def _state_path(task_id: str, value: str | None) -> Path:
    return Path(value).resolve() if value else work_memory.receipt_path(task_id, "active")


def _require_directives(args: argparse.Namespace) -> None:
    check_directive_read_state(
        directives_path=Path(args.directives_path).resolve() if args.directives_path else DEFAULT_DIRECTIVES_PATH,
        state_path=Path(args.directive_state).resolve() if args.directive_state else DEFAULT_DIRECTIVE_STATE_PATH,
        max_age_minutes=int(args.directive_max_age_minutes),
    )


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = work_memory.canonical_bytes(value)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise work_memory.WorkMemoryError("active-state-not-found", 4)
    try:
        state = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise work_memory.WorkMemoryError("invalid-active-state", 4) from exc
    if not isinstance(state, dict):
        raise work_memory.WorkMemoryError("invalid-active-state", 4)
    return state


def verify_receipts(task_id: str, state_path: Path | None = None) -> dict[str, Any]:
    classification, class_hash, _ = work_memory.load_receipt(task_id, "classification")
    selection, selection_hash, _ = work_memory.load_receipt(task_id, "selection")
    if classification["verdict"] != "operational":
        raise work_memory.WorkMemoryError("classification-is-not-operational", 4)
    if selection["classification_receipt_hash"] != class_hash:
        raise work_memory.WorkMemoryError("receipt-chain-mismatch", 4)
    rows, registry_hash = work_memory.registry_rows()
    if selection["registry_hash"] != registry_hash:
        raise work_memory.WorkMemoryError("stale-registry-receipt", 4)
    bundle, bundle_hash, lineage = work_memory.resolve_bundle(
        mode=selection["mode"], subject_id=selection["subject_id"],
        document=Path(selection["document"]), manifest=Path(selection["manifest"]),
        repo_roots_file=selection.get("repository_roots_file"),
    )
    if bundle_hash != selection["source_bundle_hash"] or bundle != selection["source_bundle"]:
        raise work_memory.WorkMemoryError("stale-source-bundle", 4)
    if lineage != selection["lineage_id"]:
        raise work_memory.WorkMemoryError("stale-lineage", 4)
    if selection["mode"] == "registered":
        row = next((item for item in rows if item["sequence_id"] == selection["subject_id"]), None)
        if row is None or row["lineage_id"] != lineage:
            raise work_memory.WorkMemoryError("registry-lineage-mismatch", 4)
    if state_path is not None:
        state = _load_state(state_path)
        expected = {
            "task_id": task_id, "classification_receipt_hash": class_hash,
            "selection_receipt_hash": selection_hash, "source_bundle_hash": bundle_hash,
        }
        if any(state.get(key) != value for key, value in expected.items()):
            raise work_memory.WorkMemoryError("active-state-receipt-mismatch", 4)
    return {
        "ok": True, "task_id": task_id, "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash, "source_bundle_hash": bundle_hash,
        "mode": selection["mode"], "subject_id": selection["subject_id"],
        "lineage_id": lineage, "selection": selection,
    }


def cmd_activate(args: argparse.Namespace) -> dict[str, Any]:
    _require_directives(args)
    if args.sequence_id:
        raise work_memory.WorkMemoryError(
            "activation-sequence-id-retired:run-work_memory-select-then-pass-selected-document", 2
        )
    root = _root(args.root)
    chosen = args.sequence_doc or args.discovery_log
    if bool(args.sequence_doc) == bool(args.discovery_log):
        raise work_memory.WorkMemoryError("exactly-one-selected-document-required", 2)
    selected_path = _resolve(root, chosen)
    verified = verify_receipts(args.task_id)
    selection = verified.pop("selection")
    expected_mode = "registered" if args.sequence_doc else "discovery"
    if selection["mode"] != expected_mode or Path(selection["document"]).resolve() != selected_path:
        raise work_memory.WorkMemoryError("selected-document-receipt-mismatch", 4)
    state = {
        "schema_version": 1, "task_id": args.task_id, "activated_at_utc": work_memory.utc_now(),
        "mode": selection["mode"], "subject_id": selection["subject_id"],
        "lineage_id": selection["lineage_id"], "document": str(selected_path),
        "classification_receipt_hash": verified["classification_receipt_hash"],
        "selection_receipt_hash": verified["selection_receipt_hash"],
        "source_bundle_hash": verified["source_bundle_hash"],
    }
    path = _state_path(args.task_id, args.state)
    _atomic_json(path, state)
    return {"ok": True, "state_path": str(path), "state": state}


def _shape_match(command: str, text: str) -> bool:
    if command in text:
        return True
    try:
        command_tokens = shlex.split(command)
    except ValueError:
        return False
    for line in text.splitlines():
        try:
            shape = shlex.split(line.strip())
        except ValueError:
            continue
        if len(shape) < len(command_tokens):
            continue
        for start in range(len(shape) - len(command_tokens) + 1):
            window = shape[start:start + len(command_tokens)]
            if all(
                actual == declared
                or (declared.startswith("<") and declared.endswith(">"))
                for actual, declared in zip(command_tokens, window)
            ):
                return True
    return False


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    _require_directives(args)
    result = verify_receipts(args.task_id)
    result.pop("selection")
    return result


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    _require_directives(args)
    path = _state_path(args.task_id, args.state)
    state = _load_state(path)
    result = verify_receipts(args.task_id, path)
    result.pop("selection")
    return {**result, "state_path": str(path), "active_state": state}


def cmd_guard(args: argparse.Namespace) -> dict[str, Any]:
    _require_directives(args)
    if args.source not in ALLOWED_SOURCES:
        raise work_memory.WorkMemoryError("invalid-command-source", 2)
    root = _root(args.root)
    path = _state_path(args.task_id, args.state)
    verified = verify_receipts(args.task_id, path)
    selection = verified.pop("selection")
    roots = work_memory._repo_roots(selection.get("repository_roots_file"))
    bundle_paths = {
        (roots[item["repository_key"]] / item["path"]).resolve()
        for item in selection["source_bundle"] if item["repository_key"] in roots
    }
    raw_source = Path(args.source_ref)
    if raw_source.is_absolute():
        source_ref = raw_source.resolve()
    else:
        matches = [
            (roots[item["repository_key"]] / item["path"]).resolve()
            for item in selection["source_bundle"]
            if item["repository_key"] in roots and item["path"] == args.source_ref
        ]
        source_ref = matches[0] if len(matches) == 1 else _resolve(root, args.source_ref)
    if source_ref not in bundle_paths:
        raise work_memory.WorkMemoryError("source-ref-outside-selected-bundle", 4)
    if not source_ref.is_file():
        raise work_memory.WorkMemoryError("source-ref-not-found", 4)
    command = args.command.strip()
    if not command or not args.step.strip():
        raise work_memory.WorkMemoryError("step-and-command-required", 2)
    document_text = Path(selection["document"]).read_text()
    grounded = _shape_match(command, document_text)
    if not grounded:
        if args.source != "tool_help" or not (args.evidence_text or "").strip():
            raise work_memory.WorkMemoryError("command-not-grounded-in-selected-document", 4)
    if args.source == "script" and source_ref.name not in command and str(source_ref) not in command:
        raise work_memory.WorkMemoryError("command-does-not-invoke-source-script", 4)
    return {**verified, "ok": True, "step": args.step, "command_source": args.source,
            "source_ref": str(source_ref)}


def _shared(parser: argparse.ArgumentParser, *, state: bool = True) -> None:
    parser.add_argument("--task-id", required=True); parser.add_argument("--root")
    if state:
        parser.add_argument("--state")
    parser.add_argument("--directives-path"); parser.add_argument("--directive-state")
    parser.add_argument("--directive-max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command_name", required=True)
    activate = sub.add_parser("activate")
    activate.add_argument("--sequence-doc"); activate.add_argument("--discovery-log"); activate.add_argument("--sequence-id")
    _shared(activate); activate.set_defaults(func=cmd_activate)
    verify = sub.add_parser("verify-receipts"); _shared(verify, state=False); verify.set_defaults(func=cmd_verify)
    status = sub.add_parser("status"); _shared(status); status.set_defaults(func=cmd_status)
    guard = sub.add_parser("guard")
    guard.add_argument("--step", required=True); guard.add_argument("--command", required=True)
    guard.add_argument("--source", required=True); guard.add_argument("--source-ref", required=True)
    guard.add_argument("--evidence-text"); _shared(guard); guard.set_defaults(func=cmd_guard)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        print(json.dumps(args.func(args), sort_keys=True))
        return 0
    except work_memory.WorkMemoryError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
