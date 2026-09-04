#!/usr/bin/env python3
"""Atomically recover an active discovery run after its selected bundle changed."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts import sequence_guard, work_memory, work_memory_bootstrap as bootstrap
except ImportError:
    import sequence_guard  # type: ignore
    import work_memory  # type: ignore
    import work_memory_bootstrap as bootstrap  # type: ignore


SCRIPT_PATH = "scripts/active_discovery_recovery_v1.py"
COMMAND_PREFIX = f"python3 {SCRIPT_PATH} correct"
CORRECTION_NAMESPACE = uuid.NAMESPACE_URL
CANONICAL_CORRECTION_EXAMPLE = (
    "python3 scripts/work_memory_bootstrap.py correct "
    "--task-id canonical-task --run-id 11111111-1111-4111-8111-111111111111 "
    "--blocker-id blk-111111111111111111111111 "
    "--occurrence-id 22222222-2222-4222-8222-222222222222 "
    "--step-id canonical-step --changed-artifact scripts/example.py "
    "--solution canonical-solution --reusable-behavior-changed yes"
)


class ActiveDiscoveryRecoveryError(Exception):
    def __init__(self, code: str, exit_code: int = 4):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def _bundle_map(bundle: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    return {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in bundle
    }


def _authorize_recovery(task_id: str, run_id: str) -> dict[str, Any]:
    active = work_memory.RECEIPT_ROOT / task_id / "active.json"
    try:
        verified = sequence_guard.verify_receipts(task_id, active)
        owner = work_memory.require_task_writer(task_id)
    except work_memory.WorkMemoryError as exc:
        raise ActiveDiscoveryRecoveryError("recovery-authorization-invalid") from exc
    selection = verified["selection"]
    document = Path(selection["document"])
    if COMMAND_PREFIX not in document.read_text(encoding="utf-8"):
        raise ActiveDiscoveryRecoveryError("recovery-command-not-grounded")

    roots = work_memory._repo_roots(
        selection.get("repository_roots_file"),
        snapshot=selection.get("repository_roots"),
    )
    script = Path(__file__).resolve()
    entries = [
        item for item in selection["source_bundle"]
        if item["repository_key"] in roots
        and (roots[item["repository_key"]] / item["path"]).resolve() == script
    ]
    if (
        len(entries) != 1
        or entries[0]["repository_key"] != "memory-knowledge"
        or entries[0]["path"] != SCRIPT_PATH
        or entries[0]["sha256"] != work_memory.sha256_bytes(script.read_bytes())
    ):
        raise ActiveDiscoveryRecoveryError("recovery-controller-not-selected")

    events, _ = work_memory.load_ledger()
    try:
        start, related = work_memory._run_state(events, run_id)
    except work_memory.WorkMemoryError as exc:
        raise ActiveDiscoveryRecoveryError("recovery-authorization-run-invalid") from exc
    expected = {
        "task_id": task_id,
        "subject_id": selection["subject_id"],
        "lineage_id": selection["lineage_id"],
        "mode": selection["mode"],
        "source_bundle_hash": selection["source_bundle_hash"],
        "classification_receipt_hash": selection["classification_receipt_hash"],
        "selection_receipt_hash": verified["selection_receipt_hash"],
        "writer_thread_id": owner["writer_thread_id"],
        "ownership_generation": owner["ownership_generation"],
    }
    if (
        any(start.get(key) != value for key, value in expected.items())
        or any(event["event_type"] in {"run_closed", "run_abandoned"} for event in related)
    ):
        raise ActiveDiscoveryRecoveryError("recovery-authorization-run-invalid")
    return verified


def _subject_paths(start: dict[str, Any]) -> tuple[Path, Path]:
    bundle_paths = {
        item["path"] for item in start["source_bundle"]
        if item["repository_key"] == "memory-knowledge"
    }
    if start["mode"] == "registered":
        document_relative = f"operations/sequences/{start['subject_id']}/sequence.md"
        manifest_relative = f"operations/sequences/{start['subject_id']}/dependencies.json"
    else:
        document_relative = manifest_relative = None
        for relative in sorted(bundle_paths):
            if not relative.endswith(".dependencies.json"):
                continue
            candidate = work_memory.ROOT / relative
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("lineage_id") == start["lineage_id"]:
                manifest_relative = relative
                document_relative = relative.removesuffix(".dependencies.json") + ".md"
                break
        if document_relative is None or manifest_relative is None:
            raise ActiveDiscoveryRecoveryError("recovery-subject-not-found")
    if document_relative not in bundle_paths or manifest_relative not in bundle_paths:
        raise ActiveDiscoveryRecoveryError("recovery-subject-not-found")
    return work_memory.ROOT / document_relative, work_memory.ROOT / manifest_relative


def _load_target_run(
    *, task_id: str, run_id: str, authorization: dict[str, Any], correction_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    try:
        target_owner = work_memory.require_task_writer(task_id)
    except work_memory.WorkMemoryError as exc:
        raise ActiveDiscoveryRecoveryError("recovery-target-owner-invalid") from exc
    if target_owner["writer_thread_id"] != authorization["writer_thread_id"]:
        raise ActiveDiscoveryRecoveryError("recovery-owner-mismatch")
    events, _ = work_memory.load_ledger()
    try:
        start, related = work_memory._run_state(events, run_id)
    except work_memory.WorkMemoryError as exc:
        raise ActiveDiscoveryRecoveryError("recovery-target-run-invalid") from exc
    expected = {
        "task_id": task_id,
        "writer_thread_id": target_owner["writer_thread_id"],
        "ownership_generation": target_owner["ownership_generation"],
    }
    terminal = [
        event for event in related
        if event["event_type"] in {"run_closed", "run_abandoned"}
    ]
    existing = next((
        event for event in related
        if event["event_type"] == "correction_recorded"
        and event["correction_id"] == correction_id
    ), None)
    retry_terminal = (
        existing is not None
        and len(terminal) == 1
        and terminal[0]["event_type"] == "run_closed"
        and terminal[0]["result"] == "failed"
    )
    if (
        start.get("mode") != "discovery"
        or any(start.get(key) != value for key, value in expected.items())
        or (terminal and not retry_terminal)
    ):
        raise ActiveDiscoveryRecoveryError("recovery-target-run-invalid")
    return events, start, related


def _resolve_target_transition(
    start: dict[str, Any],
) -> tuple[list[dict[str, Any]], str, dict[str, str], Path]:
    document, manifest = _subject_paths(start)
    if not sequence_guard._shape_match(
        CANONICAL_CORRECTION_EXAMPLE, document.read_text(encoding="utf-8")
    ):
        raise ActiveDiscoveryRecoveryError("recovery-correction-command-not-grounded")
    repository_roots = start.get("repository_roots") or {
        key: str(path) for key, path in work_memory._repo_roots().items()
    }
    try:
        bundle, digest, lineage = work_memory.resolve_bundle(
            mode=start["mode"], subject_id=start["subject_id"],
            document=document, manifest=manifest,
            repository_roots=repository_roots,
            include_bootstrap_trust_anchors=True,
        )
    except work_memory.WorkMemoryError as exc:
        raise ActiveDiscoveryRecoveryError("recovery-target-bundle-invalid") from exc
    if lineage != start["lineage_id"]:
        raise ActiveDiscoveryRecoveryError("recovery-target-lineage-mismatch")
    old_map, new_map = _bundle_map(start["source_bundle"]), _bundle_map(bundle)
    for relative in work_memory.BOOTSTRAP_TRUST_ANCHORS:
        key = ("memory-knowledge", relative)
        if old_map.get(key) is None or old_map.get(key) != new_map.get(key):
            raise ActiveDiscoveryRecoveryError("recovery-trust-anchor-drift")
    return bundle, digest, repository_roots, document


def _changed_artifact_values(args: argparse.Namespace) -> list[str]:
    values = list(args.changed_artifact or [])
    if args.changed_artifacts_file:
        values.extend(
            line.strip()
            for line in Path(args.changed_artifacts_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return list(dict.fromkeys(values))


def _validate_exact_drift(
    *, start: dict[str, Any], current_bundle: list[dict[str, Any]],
    changed_values: list[str], repository_roots: dict[str, str],
) -> tuple[list[Any], list[str]]:
    if not changed_values:
        raise ActiveDiscoveryRecoveryError("recovery-changed-artifacts-required", 2)
    try:
        artifacts, hashes = work_memory._artifact_hashes(
            changed_values, repository_roots=repository_roots,
        )
    except work_memory.WorkMemoryError as exc:
        raise ActiveDiscoveryRecoveryError("recovery-artifact-invalid", 2) from exc
    old_map, new_map = _bundle_map(start["source_bundle"]), _bundle_map(current_bundle)
    drifted = {
        key for key in old_map.keys() | new_map.keys()
        if old_map.get(key) != new_map.get(key)
    }
    artifact_keys = {bootstrap._artifact_identity(item) for item in artifacts}
    if artifact_keys != drifted:
        raise ActiveDiscoveryRecoveryError("recovery-artifact-drift-mismatch")
    return artifacts, hashes


def _validate_blockers(
    *, events: list[dict[str, Any]], start: dict[str, Any], args: argparse.Namespace,
    correction_id: str,
) -> None:
    blocker_ids = [args.blocker_id, *(args.co_blocker_id or [])]
    if len(blocker_ids) != len(set(blocker_ids)):
        raise ActiveDiscoveryRecoveryError("recovery-duplicate-blocker", 2)
    existing = any(
        event["event_type"] == "correction_recorded"
        and event["correction_id"] == correction_id
        for event in events
    )
    expected_status = "fixed-awaiting-verification" if existing else "open"
    for index, blocker_id in enumerate(blocker_ids):
        opened, status, occurrence_id, occurrence_run = bootstrap._current_blocker(
            events, blocker_id,
        )
        expected_occurrence = args.occurrence_id if index == 0 else occurrence_id
        if (
            opened is None or status != expected_status or occurrence_run != args.run_id
            or occurrence_id != expected_occurrence
            or opened["subject_id"] != start["subject_id"]
            or opened["lineage_id"] != start["lineage_id"]
        ):
            raise ActiveDiscoveryRecoveryError("recovery-blocker-mismatch")
    primary, _, _, _ = bootstrap._current_blocker(events, args.blocker_id)
    if primary is None or primary["step_id"] != args.step_id:
        raise ActiveDiscoveryRecoveryError("recovery-blocker-mismatch")


def cmd_correct(args: argparse.Namespace) -> dict[str, Any]:
    bootstrap._require_directives(args)
    if args.correction_id is None:
        args.correction_id = str(uuid.uuid5(
            CORRECTION_NAMESPACE,
            f"active-discovery-recovery:{args.run_id}:{args.blocker_id}:{args.occurrence_id}",
        ))
    if args.event_id is None:
        args.event_id = str(uuid.uuid5(uuid.UUID(args.correction_id), "correction-event"))
    if args.transition_event_id is None:
        args.transition_event_id = str(uuid.uuid5(
            uuid.UUID(args.correction_id), "bundle-transition-event",
        ))
    authorization = _authorize_recovery(
        args.authorization_task_id, args.authorization_run_id,
    )
    events, start, _ = _load_target_run(
        task_id=args.task_id, run_id=args.run_id, authorization=authorization,
        correction_id=args.correction_id,
    )
    _validate_blockers(
        events=events, start=start, args=args, correction_id=args.correction_id,
    )
    current_bundle, current_hash, repository_roots, _ = _resolve_target_transition(start)
    artifacts, hashes = _validate_exact_drift(
        start=start, current_bundle=current_bundle,
        changed_values=_changed_artifact_values(args),
        repository_roots=repository_roots,
    )

    args.changed_artifact = _changed_artifact_values(args)
    args.repo_roots_file = None
    args.finalize_failed_run = True

    original_hashes = work_memory._artifact_hashes
    original_resolve = work_memory.resolve_bundle
    work_memory._artifact_hashes = bootstrap._sealed_artifact_hashes(
        work_memory, artifacts, hashes, None, repository_roots,
    )
    work_memory.resolve_bundle = lambda **kwargs: (
        current_bundle, current_hash, start["lineage_id"],
    )
    try:
        result = work_memory.cmd_correct(args)
    finally:
        work_memory._artifact_hashes = original_hashes
        work_memory.resolve_bundle = original_resolve
    if (
        result.get("changed_artifact_hashes") != hashes
        or result.get("new_bundle_hash") != current_hash
    ):
        raise ActiveDiscoveryRecoveryError("recovery-result-mismatch", 5)
    return {
        **result,
        "active_discovery_recovery_version": 1,
        "authorization_task_id": args.authorization_task_id,
        "authorization_run_id": args.authorization_run_id,
        "target_task_id": args.task_id,
        "target_run_id": args.run_id,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    correct = sub.add_parser("correct")
    correct.add_argument("--authorization-task-id", required=True)
    correct.add_argument("--authorization-run-id", required=True)
    correct.add_argument("--task-id", required=True)
    correct.add_argument("--run-id", required=True)
    correct.add_argument("--blocker-id", required=True)
    correct.add_argument("--occurrence-id", required=True)
    correct.add_argument("--co-blocker-id", action="append")
    correct.add_argument("--step-id", required=True)
    correct.add_argument("--changed-artifact", action="append")
    correct.add_argument("--changed-artifacts-file")
    correct.add_argument("--solution", required=True)
    correct.add_argument("--reusable-behavior-changed", choices=["yes", "no"], required=True)
    correct.add_argument("--supersedes-correction-id", action="append")
    correct.add_argument("--correction-id")
    correct.add_argument("--event-id")
    correct.add_argument("--transition-event-id")
    correct.add_argument("--directives-path")
    correct.add_argument("--directive-state")
    correct.add_argument(
        "--directive-max-age-minutes", type=int, default=bootstrap.DEFAULT_MAX_AGE_MINUTES,
    )
    correct.set_defaults(func=cmd_correct)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        print(json.dumps(args.func(args), sort_keys=True))
        return 0
    except (ActiveDiscoveryRecoveryError, work_memory.WorkMemoryError) as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
