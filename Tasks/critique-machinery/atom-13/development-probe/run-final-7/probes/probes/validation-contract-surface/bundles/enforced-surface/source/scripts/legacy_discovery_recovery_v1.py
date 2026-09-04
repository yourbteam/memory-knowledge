#!/usr/bin/env python3
"""Recover a pre-contract discovery whose generated document omitted correction rows."""

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


SCRIPT_PATH = "scripts/legacy_discovery_recovery_v1.py"
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


class LegacyRecoveryError(Exception):
    def __init__(self, code: str, exit_code: int = 4):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def _has_canonical_correction_shape(document_text: str) -> bool:
    """Return true only when the complete guarded correction shape is recorded."""
    return sequence_guard._shape_match(CANONICAL_CORRECTION_EXAMPLE, document_text)


def _authorize_recovery(task_id: str, run_id: str) -> dict[str, Any]:
    try:
        verified = sequence_guard.verify_receipts(task_id)
    except work_memory.WorkMemoryError as exc:
        raise LegacyRecoveryError("legacy-recovery-authorization-invalid") from exc
    selection = verified["selection"]
    document = Path(selection["document"])
    if COMMAND_PREFIX not in document.read_text(encoding="utf-8"):
        raise LegacyRecoveryError("legacy-recovery-command-not-grounded")

    roots = work_memory._repo_roots(selection.get("repository_roots_file"))
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
        raise LegacyRecoveryError("legacy-recovery-controller-not-selected")

    events, _ = work_memory.load_ledger()
    try:
        start, related = work_memory._run_state(events, run_id)
    except work_memory.WorkMemoryError as exc:
        raise LegacyRecoveryError("legacy-recovery-authorization-run-invalid") from exc
    expected = {
        "subject_id": selection["subject_id"],
        "lineage_id": selection["lineage_id"],
        "mode": selection["mode"],
        "source_bundle_hash": selection["source_bundle_hash"],
        "classification_receipt_hash": selection["classification_receipt_hash"],
        "selection_receipt_hash": verified["selection_receipt_hash"],
    }
    if (
        any(start.get(key) != value for key, value in expected.items())
        or any(event["event_type"] in {"run_closed", "run_abandoned"} for event in related)
    ):
        raise LegacyRecoveryError("legacy-recovery-authorization-run-invalid")
    return verified


def _execute_correction(args: argparse.Namespace) -> dict[str, Any]:
    _authorize_recovery(args.authorization_task_id, args.authorization_run_id)
    context = bootstrap._load_context(args)
    document_text = Path(context["selection"]["document"]).read_text(encoding="utf-8")
    if _has_canonical_correction_shape(document_text):
        raise LegacyRecoveryError("legacy-recovery-not-required")

    module = context["module"]
    events, _ = module.load_ledger()
    start, related = bootstrap._run_matches_selection(
        module, events, args.run_id, context["selection"],
        context["state"], context["classification"],
    )
    if args.correction_id is None:
        args.correction_id = str(uuid.uuid5(
            CORRECTION_NAMESPACE,
            f"memory-knowledge:{args.run_id}:{args.blocker_id}:{args.occurrence_id}",
        ))
    existing = next((
        event for event in related
        if event["event_type"] == "correction_recorded"
        and event["correction_id"] == args.correction_id
    ), None)
    if existing is None and any(
        event["event_type"] in {"run_closed", "run_abandoned"} for event in related
    ):
        raise LegacyRecoveryError("legacy-recovery-run-is-terminal")
    opened, status, occurrence_id, occurrence_run = bootstrap._current_blocker(
        events, args.blocker_id,
    )
    if (
        opened is None or (existing is None and status != "open")
        or occurrence_id != args.occurrence_id or occurrence_run != args.run_id
        or opened["step_id"] != args.step_id
        or opened["lineage_id"] != context["selection"]["lineage_id"]
    ):
        raise LegacyRecoveryError("legacy-recovery-blocker-mismatch")

    repo_roots_file = context["selection"].get("repository_roots_file")
    repository_roots = start.get("repository_roots")
    args.repo_roots_file = repo_roots_file
    args.finalize_failed_run = True
    changed_artifacts = list(args.changed_artifact or [])
    if args.changed_artifacts_file:
        changed_artifacts.extend(
            line.strip()
            for line in Path(args.changed_artifacts_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    args.changed_artifact = list(dict.fromkeys(changed_artifacts))
    if not args.changed_artifact:
        raise LegacyRecoveryError("legacy-recovery-changed-artifacts-required", 2)
    try:
        if repository_roots is None:
            artifacts, hashes = module._artifact_hashes(args.changed_artifact, repo_roots_file)
        else:
            artifacts, hashes = module._artifact_hashes(
                args.changed_artifact, repository_roots=repository_roots,
            )
    except module.WorkMemoryError as exc:
        raise LegacyRecoveryError("legacy-recovery-artifact-invalid", 2) from exc
    old_map = bootstrap._bundle_map(context["selection"]["source_bundle"])
    current_map = bootstrap._bundle_map(context["current_bundle"])
    drifted = {
        key for key in old_map.keys() | current_map.keys()
        if old_map.get(key) != current_map.get(key)
    }
    artifact_keys = {bootstrap._artifact_identity(artifact) for artifact in artifacts}
    if artifact_keys != drifted:
        raise LegacyRecoveryError("legacy-recovery-artifact-drift-mismatch")

    original_hashes = module._artifact_hashes
    original_resolve = module.resolve_bundle
    module._artifact_hashes = bootstrap._sealed_artifact_hashes(
        module, artifacts, hashes, repo_roots_file, repository_roots,
    )
    module.resolve_bundle = lambda **kwargs: (
        context["current_bundle"], context["current_bundle_hash"],
        context["selection"]["lineage_id"],
    )
    try:
        result = module.cmd_correct(args)
    finally:
        module._artifact_hashes = original_hashes
        module.resolve_bundle = original_resolve
    if (
        result.get("changed_artifact_hashes") != hashes
        or result.get("new_bundle_hash") != context["current_bundle_hash"]
    ):
        raise LegacyRecoveryError("legacy-recovery-result-mismatch", 5)
    return {
        **result,
        "legacy_recovery_version": 1,
        "authorization_task_id": args.authorization_task_id,
        "authorization_run_id": args.authorization_run_id,
        "sealed_controller_sha256": context["state"]["sealed_controller_sha256"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    correct = sub.add_parser("correct")
    correct.add_argument("--authorization-task-id", required=True)
    correct.add_argument("--authorization-run-id", required=True)
    correct.add_argument("--task-id", required=True)
    correct.add_argument("--state")
    correct.add_argument("--run-id", required=True)
    correct.add_argument("--blocker-id", required=True)
    correct.add_argument("--occurrence-id", required=True)
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
    correct.set_defaults(func=_execute_correction)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        print(json.dumps(args.func(args), sort_keys=True))
        return 0
    except (LegacyRecoveryError, bootstrap.BootstrapError) as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
