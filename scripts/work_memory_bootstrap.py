#!/usr/bin/env python3
"""Atomically execute correction lifecycle operations with the activated controller snapshot."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import types
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts.directive_guard import (
        DEFAULT_DIRECTIVES_PATH,
        DEFAULT_MAX_AGE_MINUTES,
        DEFAULT_STATE_PATH as DEFAULT_DIRECTIVE_STATE_PATH,
        check_directive_read_state,
    )
except ModuleNotFoundError:
    from directive_guard import (  # type: ignore
        DEFAULT_DIRECTIVES_PATH,
        DEFAULT_MAX_AGE_MINUTES,
        DEFAULT_STATE_PATH as DEFAULT_DIRECTIVE_STATE_PATH,
        check_directive_read_state,
    )


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = Path(__file__).resolve()
RECEIPT_ROOT = Path("/private/tmp/work-memory")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CONTROLLER_PATH = "scripts/work_memory.py"
BOOTSTRAP_LOGICAL_PATH = "scripts/work_memory_bootstrap.py"


class BootstrapError(Exception):
    def __init__(self, code: str, exit_code: int = 4):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path, error: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError(error) from exc
    if not isinstance(value, dict):
        raise BootstrapError(error)
    return value


def _receipt_path(task_id: str, kind: str) -> Path:
    if not TASK_ID_RE.fullmatch(task_id):
        raise BootstrapError("invalid-task-id", 2)
    return RECEIPT_ROOT / task_id / f"{kind}.json"


def _require_directives(args: argparse.Namespace) -> None:
    check_directive_read_state(
        directives_path=Path(args.directives_path).resolve() if args.directives_path else DEFAULT_DIRECTIVES_PATH,
        state_path=Path(args.directive_state).resolve() if args.directive_state else DEFAULT_DIRECTIVE_STATE_PATH,
        max_age_minutes=int(args.directive_max_age_minutes),
    )


def _bundle_map(bundle: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    return {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in bundle
    }


def _artifact_identity(value: Any) -> tuple[str, str]:
    if isinstance(value, str):
        return "memory-knowledge", value
    if (
        isinstance(value, dict)
        and set(value) == {"repository_key", "path"}
        and isinstance(value["repository_key"], str)
        and isinstance(value["path"], str)
        and value["repository_key"]
        and value["path"]
    ):
        return value["repository_key"], value["path"]
    raise BootstrapError("bootstrap-artifact-identity-invalid", 2)


def _sealed_artifact_hashes(
    module: Any, artifacts: list[Any], hashes: list[str], expected_repo_roots_file: str | None,
    expected_repository_roots: dict[str, str] | None = None,
):
    def sealed(
        values: Sequence[str], repo_roots_file: str | None = None,
        repository_roots: dict[str, str] | None = None,
    ):
        if repository_roots is None:
            matches_expected_roots = (
                expected_repository_roots is None
                and repo_roots_file == expected_repo_roots_file
            )
        else:
            matches_expected_roots = (
                repo_roots_file is None
                and repository_roots == expected_repository_roots
            )
        if not matches_expected_roots:
            raise module.WorkMemoryError("bootstrap-repository-roots-mismatch", 4)
        return list(artifacts), list(hashes)

    return sealed


def _load_context(args: argparse.Namespace) -> dict[str, Any]:
    _require_directives(args)
    state_path = Path(args.state).resolve() if args.state else _receipt_path(args.task_id, "active")
    state = _read_json(state_path, "invalid-active-state")
    classification = _read_json(_receipt_path(args.task_id, "classification"), "invalid-classification-receipt")
    selection = _read_json(_receipt_path(args.task_id, "selection"), "invalid-selection-receipt")
    class_hash = _sha256(_canonical_bytes(classification))
    selection_hash = _sha256(_canonical_bytes(selection))
    expected_state = {
        "task_id": args.task_id,
        "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash,
        "source_bundle_hash": selection.get("source_bundle_hash"),
        "mode": selection.get("mode"),
        "subject_id": selection.get("subject_id"),
        "lineage_id": selection.get("lineage_id"),
        "document": str(Path(selection.get("document", "")).resolve()),
        "sealed_controller_path": CONTROLLER_PATH,
        "bootstrap_path": BOOTSTRAP_LOGICAL_PATH,
    }
    if any(state.get(key) != value for key, value in expected_state.items()):
        raise BootstrapError("active-state-receipt-mismatch")
    if selection.get("classification_receipt_hash") != class_hash:
        raise BootstrapError("receipt-chain-mismatch")

    selected = _bundle_map(selection.get("source_bundle", []))
    controller_hash = selected.get(("memory-knowledge", CONTROLLER_PATH))
    bootstrap_hash = selected.get(("memory-knowledge", BOOTSTRAP_LOGICAL_PATH))
    try:
        controller_bytes = base64.b64decode(state["sealed_controller_b64"], validate=True)
    except (KeyError, ValueError) as exc:
        raise BootstrapError("invalid-sealed-controller") from exc
    if (
        controller_hash is None
        or bootstrap_hash is None
        or state.get("sealed_controller_sha256") != controller_hash
        or state.get("bootstrap_sha256") != bootstrap_hash
        or _sha256(controller_bytes) != controller_hash
        or _sha256(BOOTSTRAP_PATH.read_bytes()) != bootstrap_hash
    ):
        raise BootstrapError("bootstrap-trust-mismatch")

    module = types.ModuleType("_sealed_work_memory")
    module.__file__ = str(ROOT / CONTROLLER_PATH)
    module.__package__ = ""
    try:
        exec(compile(controller_bytes, module.__file__, "exec"), module.__dict__)
    except Exception as exc:
        raise BootstrapError("sealed-controller-load-failed") from exc
    bundle, bundle_hash, lineage = module.resolve_bundle(
        mode=selection["mode"], subject_id=selection["subject_id"],
        document=Path(selection["document"]), manifest=Path(selection["manifest"]),
        repo_roots_file=selection.get("repository_roots_file"),
        include_bootstrap_trust_anchors=True,
    )
    if lineage != selection["lineage_id"]:
        raise BootstrapError("bootstrap-lineage-mismatch")
    return {
        "module": module,
        "state": state,
        "selection": selection,
        "classification": classification,
        "current_bundle": bundle,
        "current_bundle_hash": bundle_hash,
    }


def _run_matches_selection(
    module: Any, events: list[dict[str, Any]], run_id: str,
    selection: dict[str, Any], state: dict[str, Any], classification: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        start, related = module._run_state(events, run_id)
    except module.WorkMemoryError as exc:
        raise BootstrapError("bootstrap-run-mismatch") from exc
    expected = {
        "subject_id": selection["subject_id"],
        "lineage_id": selection["lineage_id"],
        "mode": selection["mode"],
        "source_bundle": selection["source_bundle"],
        "source_bundle_hash": selection["source_bundle_hash"],
        "classification_receipt_hash": selection["classification_receipt_hash"],
        "selection_receipt_hash": state["selection_receipt_hash"],
        "operation_kind": classification["operation_kind"],
    }
    if any(start.get(key) != value for key, value in expected.items()):
        raise BootstrapError("bootstrap-run-mismatch")
    return start, related


def _current_blocker(events: list[dict[str, Any]], blocker_id: str) -> tuple[dict[str, Any] | None, str | None, str | None, str | None]:
    opened = None
    status = occurrence_id = run_id = None
    for event in events:
        if event.get("blocker_id") != blocker_id:
            continue
        if event["event_type"] == "blocker_opened":
            opened, status = event, "open"
            occurrence_id, run_id = event["occurrence_id"], event["run_id"]
        elif event["event_type"] == "blocker_recurred":
            status = "open"
            occurrence_id, run_id = event["occurrence_id"], event["run_id"]
        elif event["event_type"] == "blocker_transitioned":
            status = event["to_status"]
    return opened, status, occurrence_id, run_id


def cmd_correct(args: argparse.Namespace) -> dict[str, Any]:
    context = _load_context(args)
    if "python3 scripts/work_memory_bootstrap_launcher.py correct" not in Path(context["selection"]["document"]).read_text():
        raise BootstrapError("bootstrap-command-not-grounded")
    module = context["module"]
    events, _ = module.load_ledger()
    start, related = _run_matches_selection(
        module, events, args.run_id, context["selection"],
        context["state"], context["classification"],
    )
    existing = next((
        event for event in related
        if event["event_type"] == "correction_recorded"
        and args.correction_id
        and event["correction_id"] == args.correction_id
    ), None)
    if (
        existing is None
        and any(event["event_type"] in {"run_closed", "run_abandoned"} for event in related)
    ):
        raise BootstrapError("bootstrap-run-is-terminal")
    opened, status, occurrence_id, occurrence_run = _current_blocker(events, args.blocker_id)
    if (
        opened is None or (existing is None and status != "open")
        or occurrence_id != args.occurrence_id
        or occurrence_run != args.run_id or opened["step_id"] != args.step_id
        or opened["lineage_id"] != context["selection"]["lineage_id"]
    ):
        raise BootstrapError("bootstrap-blocker-mismatch")

    repo_roots_file = context["selection"].get("repository_roots_file")
    args.repo_roots_file = repo_roots_file
    args.finalize_failed_run = True
    try:
        artifacts, hashes = module._artifact_hashes(args.changed_artifact, repo_roots_file)
    except module.WorkMemoryError as exc:
        raise BootstrapError("bootstrap-artifact-invalid", 2) from exc
    old_map = _bundle_map(context["selection"]["source_bundle"])
    current_map = _bundle_map(context["current_bundle"])
    drifted = {key for key in old_map.keys() | current_map.keys() if old_map.get(key) != current_map.get(key)}
    artifact_keys = {_artifact_identity(artifact) for artifact in artifacts}
    if artifact_keys != drifted:
        raise BootstrapError("bootstrap-artifact-drift-mismatch")
    if (
        old_map.get(("memory-knowledge", CONTROLLER_PATH))
        != current_map.get(("memory-knowledge", CONTROLLER_PATH))
        and ("memory-knowledge", CONTROLLER_PATH) not in artifact_keys
    ):
        raise BootstrapError("bootstrap-controller-artifact-required")

    original_hashes = module._artifact_hashes
    original_resolve = module.resolve_bundle
    module._artifact_hashes = _sealed_artifact_hashes(
        module, artifacts, hashes, repo_roots_file, start.get("repository_roots"),
    )
    module.resolve_bundle = lambda **kwargs: (
        context["current_bundle"], context["current_bundle_hash"], context["selection"]["lineage_id"]
    )
    try:
        result = module.cmd_correct(args)
    finally:
        module._artifact_hashes = original_hashes
        module.resolve_bundle = original_resolve
    if result.get("changed_artifact_hashes") != hashes or result.get("new_bundle_hash") != context["current_bundle_hash"]:
        raise BootstrapError("bootstrap-execution-result-mismatch", 5)
    return {**result, "bootstrap_atomic": True, "sealed_controller_sha256": context["state"]["sealed_controller_sha256"]}


def cmd_run_close(args: argparse.Namespace) -> dict[str, Any]:
    context = _load_context(args)
    if "python3 scripts/work_memory_bootstrap_launcher.py run-close" not in Path(context["selection"]["document"]).read_text():
        raise BootstrapError("bootstrap-command-not-grounded")
    module = context["module"]
    events, _ = module.load_ledger()
    _, related = _run_matches_selection(
        module, events, args.run_id, context["selection"],
        context["state"], context["classification"],
    )
    if not any(event["event_type"] == "correction_recorded" for event in related):
        raise BootstrapError("bootstrap-correction-required")
    if args.result != "failed":
        raise BootstrapError("bootstrap-close-must-fail", 2)
    result = module.cmd_run_close(args)
    return {**result, "bootstrap_atomic": True, "sealed_controller_sha256": context["state"]["sealed_controller_sha256"]}


def _shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--state")
    parser.add_argument("--directives-path")
    parser.add_argument("--directive-state")
    parser.add_argument("--directive-max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    correct = sub.add_parser("correct")
    _shared(correct)
    correct.add_argument("--run-id", required=True)
    correct.add_argument("--blocker-id", required=True)
    correct.add_argument("--occurrence-id", required=True)
    correct.add_argument("--step-id", required=True)
    correct.add_argument("--changed-artifact", action="append", required=True)
    correct.add_argument("--solution", required=True)
    correct.add_argument("--reusable-behavior-changed", choices=["yes", "no"], required=True)
    correct.add_argument("--supersedes-correction-id", action="append")
    correct.add_argument("--correction-id")
    correct.add_argument("--event-id")
    correct.add_argument("--transition-event-id")
    correct.set_defaults(func=cmd_correct)
    close = sub.add_parser("run-close")
    _shared(close)
    close.add_argument("--run-id", required=True)
    close.add_argument("--result", choices=["failed"], required=True)
    close.add_argument("--event-id")
    close.set_defaults(func=cmd_run_close)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = args.func(args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except BootstrapError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
