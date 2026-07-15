#!/usr/bin/env python3
"""Guard operational commands with classification, selection, and bundle receipts."""

from __future__ import annotations

import argparse
import base64
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
CORRECTION_BOOTSTRAP_PREFIX = ("python3", "scripts/work_memory.py", "correct")
POST_CORRECTION_TRANSITION_PREFIX = ("python3", "scripts/blocker_catalog.py", "transition")
POST_CORRECTION_CLOSE_PREFIX = ("python3", "scripts/work_memory.py", "run-close")
CORRECTION_REQUIRED_OPTIONS = {
    "--run-id", "--blocker-id", "--occurrence-id", "--step-id",
    "--changed-artifact", "--solution", "--reusable-behavior-changed",
}
CORRECTION_OPTIONAL_OPTIONS = {
    "--supersedes-correction-id", "--correction-id", "--event-id", "--transition-event-id",
}


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


def _load_receipt_chain(
    task_id: str,
) -> tuple[dict[str, Any], str, dict[str, Any], str, list[dict[str, Any]]]:
    classification, class_hash, _ = work_memory.load_receipt(task_id, "classification")
    selection, selection_hash, _ = work_memory.load_receipt(task_id, "selection")
    if classification["verdict"] != "operational":
        raise work_memory.WorkMemoryError("classification-is-not-operational", 4)
    if selection["classification_receipt_hash"] != class_hash:
        raise work_memory.WorkMemoryError("receipt-chain-mismatch", 4)
    rows: list[dict[str, str]] = []
    if selection["mode"] == "registered":
        rows, registry_hash = work_memory.registry_rows()
        if selection["registry_hash"] != registry_hash:
            raise work_memory.WorkMemoryError("stale-registry-receipt", 4)
    return classification, class_hash, selection, selection_hash, rows


def verify_receipts(task_id: str, state_path: Path | None = None) -> dict[str, Any]:
    _, class_hash, selection, selection_hash, rows = _load_receipt_chain(task_id)
    bundle, bundle_hash, lineage = work_memory.resolve_bundle(
        mode=selection["mode"], subject_id=selection["subject_id"],
        document=Path(selection["document"]), manifest=Path(selection["manifest"]),
        repo_roots_file=selection.get("repository_roots_file"),
        include_bootstrap_trust_anchors=True,
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


def _control_plane_tokens(command: str, error_code: str) -> list[str]:
    if not command.strip() or any(character in command for character in "\r\n`$"):
        raise work_memory.WorkMemoryError(error_code, 4)
    try:
        shell_lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
        shell_lexer.whitespace_split = True
        shell_tokens = list(shell_lexer)
        tokens = shlex.split(command)
    except ValueError as exc:
        raise work_memory.WorkMemoryError(error_code, 4) from exc
    shell_controls = set(";&|<>()")
    if any(token and set(token) <= shell_controls for token in shell_tokens):
        raise work_memory.WorkMemoryError(error_code, 4)
    return tokens


def _parse_correction_command(command: str) -> dict[str, Any]:
    tokens = _control_plane_tokens(command, "invalid-correction-bootstrap-command")
    if tuple(tokens[:3]) != CORRECTION_BOOTSTRAP_PREFIX:
        raise work_memory.WorkMemoryError("invalid-correction-bootstrap-command", 4)

    allowed = CORRECTION_REQUIRED_OPTIONS | CORRECTION_OPTIONAL_OPTIONS
    parsed: dict[str, Any] = {
        "--changed-artifact": [],
        "--supersedes-correction-id": [],
    }
    index = 3
    while index < len(tokens):
        option = tokens[index]
        if option not in allowed or index + 1 >= len(tokens):
            raise work_memory.WorkMemoryError("invalid-correction-bootstrap-command", 4)
        value = tokens[index + 1]
        if value.startswith("--"):
            raise work_memory.WorkMemoryError("invalid-correction-bootstrap-command", 4)
        if option in {"--changed-artifact", "--supersedes-correction-id"}:
            parsed[option].append(value)
        elif option in parsed:
            raise work_memory.WorkMemoryError("invalid-correction-bootstrap-command", 4)
        else:
            parsed[option] = value
        index += 2

    if not CORRECTION_REQUIRED_OPTIONS <= set(parsed):
        raise work_memory.WorkMemoryError("invalid-correction-bootstrap-command", 4)
    if parsed["--reusable-behavior-changed"] not in {"yes", "no"} or not parsed["--solution"].strip():
        raise work_memory.WorkMemoryError("invalid-correction-bootstrap-command", 4)
    try:
        for option in (
            "--run-id", "--occurrence-id", "--correction-id", "--event-id",
            "--transition-event-id",
        ):
            if option in parsed:
                work_memory.require_uuid(parsed[option], option.removeprefix("--"))
        for correction_id in parsed["--supersedes-correction-id"]:
            work_memory.require_uuid(correction_id, "supersedes-correction-id")
        work_memory.require_id(parsed["--blocker-id"], "blocker-id")
        work_memory.require_id(parsed["--step-id"], "step-id")
    except work_memory.WorkMemoryError as exc:
        raise work_memory.WorkMemoryError("invalid-correction-bootstrap-command", 4) from exc
    if not parsed["--blocker-id"].startswith("blk-"):
        raise work_memory.WorkMemoryError("invalid-correction-bootstrap-command", 4)
    return parsed


def _parse_exact_options(
    tokens: list[str], prefix: tuple[str, ...], required: set[str], optional: set[str],
) -> dict[str, str]:
    if tuple(tokens[:len(prefix)]) != prefix:
        raise work_memory.WorkMemoryError("invalid-post-correction-bootstrap-command", 4)
    parsed: dict[str, str] = {}
    index = len(prefix)
    allowed = required | optional
    while index < len(tokens):
        option = tokens[index]
        if option not in allowed or option in parsed or index + 1 >= len(tokens):
            raise work_memory.WorkMemoryError("invalid-post-correction-bootstrap-command", 4)
        value = tokens[index + 1]
        if value.startswith("--"):
            raise work_memory.WorkMemoryError("invalid-post-correction-bootstrap-command", 4)
        parsed[option] = value
        index += 2
    if not required <= set(parsed):
        raise work_memory.WorkMemoryError("invalid-post-correction-bootstrap-command", 4)
    return parsed


def _parse_post_correction_command(command: str) -> dict[str, str]:
    tokens = _control_plane_tokens(command, "invalid-post-correction-bootstrap-command")
    if tuple(tokens[:3]) == POST_CORRECTION_TRANSITION_PREFIX:
        parsed = _parse_exact_options(
            tokens, POST_CORRECTION_TRANSITION_PREFIX,
            {"--run-id", "--blocker-id", "--to-status"}, {"--event-id"},
        )
        if parsed["--to-status"] != "fixed-awaiting-verification":
            raise work_memory.WorkMemoryError("invalid-post-correction-bootstrap-command", 4)
        operation = "transition-fixed"
    elif tuple(tokens[:3]) == POST_CORRECTION_CLOSE_PREFIX:
        parsed = _parse_exact_options(
            tokens, POST_CORRECTION_CLOSE_PREFIX,
            {"--run-id", "--result"}, {"--event-id"},
        )
        if parsed["--result"] != "failed":
            raise work_memory.WorkMemoryError("invalid-post-correction-bootstrap-command", 4)
        operation = "close-failed-run"
    else:
        raise work_memory.WorkMemoryError("invalid-post-correction-bootstrap-command", 4)
    try:
        work_memory.require_uuid(parsed["--run-id"], "run-id")
        if "--event-id" in parsed:
            work_memory.require_uuid(parsed["--event-id"], "event-id")
        if "--blocker-id" in parsed:
            work_memory.require_id(parsed["--blocker-id"], "blocker-id")
    except work_memory.WorkMemoryError as exc:
        raise work_memory.WorkMemoryError("invalid-post-correction-bootstrap-command", 4) from exc
    if "--blocker-id" in parsed and not parsed["--blocker-id"].startswith("blk-"):
        raise work_memory.WorkMemoryError("invalid-post-correction-bootstrap-command", 4)
    return {**parsed, "operation": operation}


def _canonical_changed_artifacts(values: list[str]) -> list[str]:
    root = work_memory.ROOT.resolve()
    relative_paths: list[str] = []
    for raw in values:
        raw_path = Path(raw)
        if raw_path.is_absolute():
            raise work_memory.WorkMemoryError("invalid-correction-bootstrap-artifact", 4)
        resolved = (root / raw_path).resolve()
        try:
            relative = str(resolved.relative_to(root))
        except ValueError as exc:
            raise work_memory.WorkMemoryError("invalid-correction-bootstrap-artifact", 4) from exc
        if raw != relative or relative in relative_paths:
            raise work_memory.WorkMemoryError("invalid-correction-bootstrap-artifact", 4)
        relative_paths.append(relative)
    try:
        artifacts, _ = work_memory._artifact_hashes(str(root / path) for path in relative_paths)
    except work_memory.WorkMemoryError as exc:
        raise work_memory.WorkMemoryError("invalid-correction-bootstrap-artifact", 4) from exc
    if artifacts != relative_paths:
        raise work_memory.WorkMemoryError("invalid-correction-bootstrap-artifact", 4)
    return relative_paths


def _bundle_keys(bundle: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    return {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in bundle
    }


def _bundle_key_for_path(
    bundle: list[dict[str, Any]], roots: dict[str, Path], path: Path,
) -> tuple[str, str] | None:
    matches = [
        (item["repository_key"], item["path"])
        for item in bundle
        if item["repository_key"] in roots
        and (roots[item["repository_key"]] / item["path"]).resolve() == path
    ]
    return matches[0] if len(matches) == 1 else None


def _current_blocker_state(
    events: list[dict[str, Any]], blocker_id: str,
) -> tuple[dict[str, Any] | None, str | None, str | None, str | None]:
    opened = None
    status = occurrence_id = occurrence_run_id = None
    for event in events:
        if event.get("blocker_id") != blocker_id:
            continue
        if event["event_type"] == "blocker_opened":
            opened = event
            status = "open"
            occurrence_id = event["occurrence_id"]
            occurrence_run_id = event["run_id"]
        elif event["event_type"] == "blocker_recurred":
            status = "open"
            occurrence_id = event["occurrence_id"]
            occurrence_run_id = event["run_id"]
        elif event["event_type"] == "blocker_transitioned":
            status = event["to_status"]
            if status == "open":
                occurrence_run_id = event["run_id"]
    return opened, status, occurrence_id, occurrence_run_id


def _stale_bootstrap_context(
    args: argparse.Namespace, run_id: str, script_relative: str,
) -> dict[str, Any]:
    if args.source != "script":
        raise work_memory.WorkMemoryError("correction-bootstrap-requires-script-source", 4)
    classification, class_hash, selection, selection_hash, rows = _load_receipt_chain(args.task_id)
    state_path = _state_path(args.task_id, args.state)
    state = _load_state(state_path)
    old_expected = {
        "task_id": args.task_id,
        "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash,
        "source_bundle_hash": selection["source_bundle_hash"],
        "mode": selection["mode"],
        "subject_id": selection["subject_id"],
        "lineage_id": selection["lineage_id"],
        "document": str(Path(selection["document"]).resolve()),
    }
    if any(state.get(key) != value for key, value in old_expected.items()):
        raise work_memory.WorkMemoryError("correction-bootstrap-active-state-mismatch", 4)

    current_bundle, current_hash, current_lineage = work_memory.resolve_bundle(
        mode=selection["mode"], subject_id=selection["subject_id"],
        document=Path(selection["document"]), manifest=Path(selection["manifest"]),
        repo_roots_file=selection.get("repository_roots_file"),
        include_bootstrap_trust_anchors=True,
    )
    if current_lineage != selection["lineage_id"]:
        raise work_memory.WorkMemoryError("correction-bootstrap-lineage-mismatch", 4)
    if (
        current_hash == selection["source_bundle_hash"]
        and current_bundle == selection["source_bundle"]
    ):
        raise work_memory.WorkMemoryError("correction-bootstrap-requires-source-bundle-drift", 4)
    if selection["mode"] == "registered":
        row = next((item for item in rows if item["sequence_id"] == selection["subject_id"]), None)
        if row is None or row["lineage_id"] != current_lineage:
            raise work_memory.WorkMemoryError("registry-lineage-mismatch", 4)

    roots = work_memory._repo_roots(selection.get("repository_roots_file"))
    document_path = Path(selection["document"]).resolve()
    old_document_key = _bundle_key_for_path(selection["source_bundle"], roots, document_path)
    document_key = _bundle_key_for_path(current_bundle, roots, document_path)
    canonical_script = (work_memory.ROOT / script_relative).resolve()
    source_ref = _resolve(_root(args.root), args.source_ref)
    old_script_key = _bundle_key_for_path(selection["source_bundle"], roots, canonical_script)
    current_script_key = _bundle_key_for_path(current_bundle, roots, canonical_script)
    if old_document_key is None or document_key != old_document_key:
        raise work_memory.WorkMemoryError("correction-bootstrap-document-mismatch", 4)
    old_keys = _bundle_keys(selection["source_bundle"])
    current_keys = _bundle_keys(current_bundle)
    if (
        source_ref != canonical_script or old_script_key is None or current_script_key != old_script_key
        or old_keys[old_script_key] != current_keys[current_script_key]
    ):
        raise work_memory.WorkMemoryError("invalid-correction-bootstrap-source", 4)
    if not _shape_match(args.command.strip(), document_path.read_text()):
        raise work_memory.WorkMemoryError("command-not-grounded-in-selected-document", 4)

    events, _ = work_memory.load_ledger()
    try:
        start, related = work_memory._run_state(events, run_id)
    except work_memory.WorkMemoryError as exc:
        raise work_memory.WorkMemoryError("correction-bootstrap-run-mismatch", 4) from exc
    if any(event["event_type"] in {"run_closed", "run_abandoned"} for event in related):
        raise work_memory.WorkMemoryError("correction-bootstrap-run-is-terminal", 4)
    run_expected = {
        "subject_id": selection["subject_id"], "lineage_id": selection["lineage_id"],
        "mode": selection["mode"], "operation_kind": classification["operation_kind"],
        "source_bundle": selection["source_bundle"],
        "source_bundle_hash": selection["source_bundle_hash"],
        "classification_receipt_hash": class_hash, "selection_receipt_hash": selection_hash,
    }
    if any(start.get(key) != value for key, value in run_expected.items()):
        raise work_memory.WorkMemoryError("correction-bootstrap-run-mismatch", 4)

    return {
        "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash,
        "selection": selection,
        "current_bundle": current_bundle,
        "current_source_bundle_hash": current_hash,
        "current_lineage": current_lineage,
        "source_ref": source_ref,
        "events": events,
        "start": start,
        "related": related,
        "old_keys": old_keys,
        "current_keys": current_keys,
    }


def _verify_correction_bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    parsed = _parse_correction_command(args.command.strip())
    context = _stale_bootstrap_context(
        args, parsed["--run-id"], "scripts/work_memory.py",
    )
    class_hash = context["classification_receipt_hash"]
    selection_hash = context["selection_receipt_hash"]
    selection = context["selection"]
    current_hash = context["current_source_bundle_hash"]
    current_lineage = context["current_lineage"]
    source_ref = context["source_ref"]
    events = context["events"]
    old_keys = context["old_keys"]
    current_keys = context["current_keys"]

    opened, status, occurrence_id, occurrence_run_id = _current_blocker_state(
        events, parsed["--blocker-id"],
    )
    if (
        opened is None or status != "open"
        or occurrence_id != parsed["--occurrence-id"]
        or occurrence_run_id != parsed["--run-id"]
        or opened["subject_id"] != selection["subject_id"]
        or opened["lineage_id"] != selection["lineage_id"]
        or opened["step_id"] != parsed["--step-id"]
        or args.step != parsed["--step-id"]
    ):
        raise work_memory.WorkMemoryError("correction-bootstrap-blocker-mismatch", 4)

    artifacts = _canonical_changed_artifacts(parsed["--changed-artifact"])
    drifted_keys = {
        key for key in old_keys.keys() | current_keys.keys()
        if old_keys.get(key) != current_keys.get(key)
    }
    artifact_keys = {("memory-knowledge", path) for path in artifacts}
    if not artifact_keys & drifted_keys:
        raise work_memory.WorkMemoryError("correction-bootstrap-artifact-not-in-bundle-drift", 4)

    return {
        "ok": True, "task_id": args.task_id, "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash,
        "source_bundle_hash": selection["source_bundle_hash"],
        "current_source_bundle_hash": current_hash,
        "mode": selection["mode"], "subject_id": selection["subject_id"],
        "lineage_id": current_lineage, "correction_bootstrap": True,
        "run_id": parsed["--run-id"], "blocker_id": parsed["--blocker-id"],
        "occurrence_id": parsed["--occurrence-id"], "changed_artifacts": artifacts,
        "step": args.step, "command_source": args.source, "source_ref": str(source_ref),
    }


def _verify_post_correction_bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    parsed = _parse_post_correction_command(args.command.strip())
    if args.step != parsed["operation"]:
        raise work_memory.WorkMemoryError("post-correction-bootstrap-step-mismatch", 4)
    script_relative = (
        "scripts/blocker_catalog.py"
        if parsed["operation"] == "transition-fixed"
        else "scripts/work_memory.py"
    )
    context = _stale_bootstrap_context(args, parsed["--run-id"], script_relative)
    selection = context["selection"]
    events = context["events"]

    if parsed["operation"] == "transition-fixed":
        opened, status, occurrence_id, occurrence_run_id = _current_blocker_state(
            events, parsed["--blocker-id"],
        )
        corrections = [
            event for event in events
            if event["event_type"] == "correction_recorded"
            and event["run_id"] == parsed["--run-id"]
            and event["blocker_id"] == parsed["--blocker-id"]
            and event["occurrence_id"] == occurrence_id
        ]
        if (
            opened is None or status != "open"
            or occurrence_run_id != parsed["--run-id"]
            or not corrections
            or opened["subject_id"] != selection["subject_id"]
            or opened["lineage_id"] != selection["lineage_id"]
            or any(
                correction["subject_id"] != selection["subject_id"]
                or correction["lineage_id"] != selection["lineage_id"]
                or correction["step_id"] != opened["step_id"]
                for correction in corrections
            )
        ):
            raise work_memory.WorkMemoryError("post-correction-bootstrap-transition-mismatch", 4)
        blocker_ids = [parsed["--blocker-id"]]
        occurrence_ids = [occurrence_id]
    else:
        corrections = [
            event for event in context["related"]
            if event["event_type"] == "correction_recorded"
        ]
        if not corrections:
            raise work_memory.WorkMemoryError("post-correction-bootstrap-correction-required", 4)
        blocker_ids = sorted({correction["blocker_id"] for correction in corrections})
        occurrence_ids = []
        for correction in corrections:
            opened, status, occurrence_id, _ = _current_blocker_state(
                events, correction["blocker_id"],
            )
            if (
                opened is None or status != "fixed-awaiting-verification"
                or occurrence_id != correction["occurrence_id"]
                or opened["subject_id"] != selection["subject_id"]
                or opened["lineage_id"] != selection["lineage_id"]
                or correction["subject_id"] != selection["subject_id"]
                or correction["lineage_id"] != selection["lineage_id"]
                or correction["step_id"] != opened["step_id"]
            ):
                raise work_memory.WorkMemoryError("post-correction-bootstrap-blockers-not-fixed", 4)
            occurrence_ids.append(occurrence_id)

    return {
        "ok": True, "task_id": args.task_id,
        "classification_receipt_hash": context["classification_receipt_hash"],
        "selection_receipt_hash": context["selection_receipt_hash"],
        "source_bundle_hash": selection["source_bundle_hash"],
        "current_source_bundle_hash": context["current_source_bundle_hash"],
        "mode": selection["mode"], "subject_id": selection["subject_id"],
        "lineage_id": context["current_lineage"], "post_correction_bootstrap": True,
        "operation": parsed["operation"], "run_id": parsed["--run-id"],
        "blocker_ids": blocker_ids, "occurrence_ids": occurrence_ids,
        "step": args.step, "command_source": args.source,
        "source_ref": str(context["source_ref"]),
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
    bundle_by_path = {
        item["path"]: item for item in selection["source_bundle"]
        if item["repository_key"] == "memory-knowledge"
    }
    controller_path = work_memory.ROOT / "scripts/work_memory.py"
    bootstrap_path = work_memory.ROOT / "scripts/work_memory_bootstrap.py"
    launcher_path = work_memory.ROOT / "scripts/work_memory_bootstrap_launcher.py"
    controller_entry = bundle_by_path.get("scripts/work_memory.py")
    bootstrap_entry = bundle_by_path.get("scripts/work_memory_bootstrap.py")
    launcher_entry = bundle_by_path.get("scripts/work_memory_bootstrap_launcher.py")
    if (
        controller_entry is None or bootstrap_entry is None or launcher_entry is None
        or not bootstrap_path.is_file() or not launcher_path.is_file()
    ):
        raise work_memory.WorkMemoryError("bootstrap-sources-not-selected", 4)
    controller_bytes = controller_path.read_bytes()
    bootstrap_bytes = bootstrap_path.read_bytes()
    launcher_bytes = launcher_path.read_bytes()
    if (
        work_memory.sha256_bytes(controller_bytes) != controller_entry["sha256"]
        or work_memory.sha256_bytes(bootstrap_bytes) != bootstrap_entry["sha256"]
        or work_memory.sha256_bytes(launcher_bytes) != launcher_entry["sha256"]
    ):
        raise work_memory.WorkMemoryError("bootstrap-source-hash-mismatch", 4)
    state = {
        "schema_version": 1, "task_id": args.task_id, "activated_at_utc": work_memory.utc_now(),
        "mode": selection["mode"], "subject_id": selection["subject_id"],
        "lineage_id": selection["lineage_id"], "document": str(selected_path),
        "classification_receipt_hash": verified["classification_receipt_hash"],
        "selection_receipt_hash": verified["selection_receipt_hash"],
        "source_bundle_hash": verified["source_bundle_hash"],
        "sealed_controller_path": "scripts/work_memory.py",
        "sealed_controller_sha256": controller_entry["sha256"],
        "sealed_controller_b64": base64.b64encode(controller_bytes).decode("ascii"),
        "bootstrap_path": "scripts/work_memory_bootstrap.py",
        "bootstrap_sha256": bootstrap_entry["sha256"],
        "sealed_bootstrap_b64": base64.b64encode(bootstrap_bytes).decode("ascii"),
        "bootstrap_launcher_path": "scripts/work_memory_bootstrap_launcher.py",
        "bootstrap_launcher_sha256": launcher_entry["sha256"],
    }
    path = _state_path(args.task_id, args.state)
    _atomic_json(path, state)
    public_state = {
        key: value for key, value in state.items()
        if key not in {"sealed_controller_b64", "sealed_bootstrap_b64"}
    }
    return {"ok": True, "state_path": str(path), "state": public_state}


def _shape_match(command: str, text: str) -> bool:
    if command in text:
        return True
    try:
        command_tokens = shlex.split(command)
    except ValueError:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = stripped.split("|")
            if len(cells) >= 4:
                stripped = cells[2].strip()
        try:
            shape = shlex.split(stripped)
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
    if args.correction_bootstrap and args.post_correction_bootstrap:
        raise work_memory.WorkMemoryError("multiple-bootstrap-modes", 2)
    if args.correction_bootstrap:
        return _verify_correction_bootstrap(args)
    if args.post_correction_bootstrap:
        return _verify_post_correction_bootstrap(args)
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
    guard.add_argument("--correction-bootstrap", action="store_true")
    guard.add_argument("--post-correction-bootstrap", action="store_true")
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
