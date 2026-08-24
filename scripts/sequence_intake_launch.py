#!/usr/bin/env python3
"""Prepare the active registered sequence through zero-argument semantic intake."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

try:
    from scripts import (
        script_intake,
        sequence_guard,
        sequence_intake_adapters,
        work_memory,
    )
except ModuleNotFoundError:  # direct script execution
    import script_intake
    import sequence_guard
    import sequence_intake_adapters
    import work_memory


TASK_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [{
        "id": "task_id",
        "prompt": "Active governed task identity",
        "response_format": "One exact task identity.",
        "example": "sequence-intake-example",
        "constraints": (
            "Use the task whose registered sequence has already been selected "
            "and activated."
        ),
        "type": "string",
        "required": True,
    }],
}

DISPATCH_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [{
        "id": "authorize",
        "prompt": "Authorize this exact prepared operation now",
        "response_format": "Answer yes or no.",
        "example": "no",
        "constraints": (
            "Answer yes only when the displayed sequence, operation, "
            "repository, artifacts, and effect are explicitly authorized."
        ),
        "type": "boolean",
        "required": True,
    }],
}

DISPATCH_MARKER = "SEQUENCE_INTAKE_DISPATCHED"
DISPATCH_RECEIPT = "SEQUENCE_INTAKE_DISPATCH_RECEIPT"
HOST_CAPABILITIES_ENV = "MK_HOST_CAPABILITIES"
PREPARED_RECEIPT_NAME = "prepared-intake"
SEQUENCE_RUN_ID_ENV = "MK_SEQUENCE_RUN_ID"
WORKFLOW_RESUME_SEQUENCE = "workflow-resume-from-phase-live-confirmation"
DIRECTIVES_PATH = Path(__file__).resolve().parents[1] / "working-agreement/DIRECTIVES.md"


class SequenceLaunchError(ValueError):
    """The active sequence cannot be prepared safely."""


def _require_host_capabilities(prepared: Mapping[str, Any]) -> None:
    """Fail before effects when the host has not attested required access."""
    required = prepared.get("host_capabilities", [])
    if (
        not isinstance(required, list)
        or not all(isinstance(item, str) and item for item in required)
        or len(required) != len(set(required))
    ):
        raise SequenceLaunchError("prepared-host-capabilities-invalid")
    supplied = {
        item.strip()
        for item in os.environ.get(HOST_CAPABILITIES_ENV, "").split(",")
        if item.strip()
    }
    missing = sorted(set(required) - supplied)
    if missing:
        raise SequenceLaunchError(
            "host-capability-required:" + ",".join(missing)
        )


def _active_publication_run_id(
    task_id: str, prepared: Mapping[str, Any],
) -> str | None:
    if (
        prepared.get("sequence_id") != "commit-push-main"
        or prepared.get("profile") == "dry-run"
    ):
        return None
    events, _ = work_memory.load_ledger()
    terminal = {
        event["run_id"] for event in events
        if event.get("event_type") in {"run_closed", "run_abandoned"}
    }
    active = [
        event for event in events
        if event.get("event_type") == "run_started"
        and event.get("task_id") == task_id
        and event.get("subject_id") == "commit-push-main"
        and event.get("run_id") not in terminal
    ]
    if len(active) != 1:
        raise SequenceLaunchError("publication-active-run-required")
    return active[0]["run_id"]


def _repository_roots(selection: Mapping[str, Any]) -> dict[str, str]:
    snapshot = selection.get("repository_roots")
    if snapshot is None:
        roots = work_memory._repo_roots(selection.get("repository_roots_file"))
    else:
        roots = work_memory._repo_roots(snapshot=snapshot)
    return {key: str(path.resolve()) for key, path in roots.items()}


def _sequence_name(selection: Mapping[str, Any], sequence_id: str) -> str:
    """Read the operator-facing name while retaining the stable ledger identity."""
    document = selection.get("document")
    if not isinstance(document, str):
        return sequence_id
    try:
        first_line = Path(document).read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError, UnicodeError):
        return sequence_id
    match = re.fullmatch(r"#\s+(.+?)\s*", first_line)
    return match.group(1) if match else sequence_id


def _artifact_paths(task_id: str, sequence_id: str) -> dict[str, str]:
    root = Path("/private/tmp/sequence-intake", task_id, sequence_id)
    suffixes = {
        "approved_paths": ".txt",
        "overlay_paths": ".txt",
        "changed_artifacts": ".json",
        "request": ".json",
        "spec": ".json",
        "benchmark_spec": ".json",
        "goal_answers": ".json",
    }
    return {
        artifact_id: str(root / f"{artifact_id}{suffixes[artifact_id]}")
        for artifact_id in sequence_intake_adapters.artifact_ids(sequence_id)
    }


def _active_selection_for_intake(
    task_id: str, active_path: Path,
) -> dict[str, Any]:
    try:
        return sequence_guard.verify_receipts(task_id, active_path)
    except work_memory.WorkMemoryError as exc:
        if exc.code != "stale-registry-receipt":
            raise
    selection, selection_hash, _ = work_memory.load_receipt(
        task_id, "selection",
    )
    active = json.loads(active_path.read_text(encoding="utf-8"))
    required = {
        "task_id": task_id,
        "mode": selection["mode"],
        "subject_id": selection["subject_id"],
        "lineage_id": selection["lineage_id"],
        "document": str(Path(selection["document"]).resolve()),
        "source_bundle_hash": selection["source_bundle_hash"],
        "selection_receipt_hash": selection_hash,
    }
    if (
        selection["mode"] != "registered"
        or not isinstance(active, Mapping)
        or any(active.get(key) != value for key, value in required.items())
    ):
        raise SequenceLaunchError("stale-registry-selection-mismatch")
    return {
        "mode": selection["mode"],
        "subject_id": selection["subject_id"],
        "selection": selection,
        "selection_receipt_hash": selection_hash,
        "source_bundle_hash": selection["source_bundle_hash"],
        "stale_registry_receipt": True,
    }


def prepare_active_sequence(
    task_id: str,
    *,
    expected_sequence_id: str | None = None,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    active_path = work_memory.receipt_path(task_id, "active")
    verified = _active_selection_for_intake(task_id, active_path)
    if verified["mode"] != "registered":
        raise SequenceLaunchError("active-selection-is-not-registered")
    sequence_id = verified["subject_id"]
    if (
        expected_sequence_id is not None
        and sequence_id != expected_sequence_id
    ):
        raise SequenceLaunchError(
            "active-sequence-does-not-match-entrypoint:"
            f"{expected_sequence_id}:{sequence_id}"
        )
    selection = verified["selection"]
    repository_roots = _repository_roots(selection)
    prepared = sequence_intake_adapters.collect_and_prepare(
        sequence_id,
        artifact_paths=_artifact_paths(task_id, sequence_id),
        repository_roots=repository_roots,
        input_fn=input_fn,
        output_fn=output_fn,
    )
    prepared = _with_controller_preflight(
        task_id, sequence_id, prepared, repository_roots,
    )
    if prepared.get("profile") in {"correct", "correct-registered"}:
        prepared = _prepare_correction_bootstrap(
            task_id, prepared, selection, repository_roots,
        )
    return {
        "schema_version": 1,
        "task_id": task_id,
        "sequence_id": sequence_id,
        "sequence_name": _sequence_name(selection, sequence_id),
        "dispatch_status": "PREPARED_NOT_AUTHORIZED",
        "prepared": prepared,
    }


def _prepared_receipt_binding(
    verified: Mapping[str, Any],
) -> dict[str, Any] | None:
    selection = verified.get("selection")
    if not isinstance(selection, Mapping):
        return None
    keys = (
        "writer_thread_id", "writer_id", "writer_client_kind",
        "writer_session_id", "ownership_generation", "ownership_event_id",
        "ownership_sha256",
    )
    ownership = {key: selection[key] for key in keys if key in selection}
    binding = {
        "selection_receipt_hash": verified.get("selection_receipt_hash"),
        "source_bundle_hash": verified.get("source_bundle_hash"),
        "expires_at_utc": selection.get("expires_at_utc"),
        **ownership,
    }
    if any(not binding.get(key) for key in (
        "selection_receipt_hash", "source_bundle_hash", "expires_at_utc",
        "ownership_generation", "ownership_event_id", "ownership_sha256",
    )) or not ({"writer_thread_id"} <= ownership.keys() or {
        "writer_id", "writer_client_kind", "writer_session_id",
    } <= ownership.keys()):
        return None
    return binding


def _persist_prepared_result(
    result: Mapping[str, Any], verified: Mapping[str, Any], *,
    dispatch_stage: str, intake_reused: bool,
) -> dict[str, Any]:
    binding = _prepared_receipt_binding(verified)
    output = dict(result)
    output["intake_reused"] = intake_reused
    if binding is None:
        return output
    payload = {
        "schema_version": 1,
        "task_id": result["task_id"],
        "sequence_id": result["sequence_id"],
        "dispatch_stage": dispatch_stage,
        "prepared": result["prepared"],
        **binding,
    }
    path, digest = work_memory.write_receipt(
        result["task_id"], PREPARED_RECEIPT_NAME, payload,
    )
    output["prepared_receipt"] = {
        "path": str(path),
        "sha256": digest,
        "dispatch_stage": dispatch_stage,
    }
    return output


def _load_or_prepare_active_sequence(
    task_id: str,
    *,
    expected_sequence_id: str | None = None,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    active_path = work_memory.receipt_path(task_id, "active")
    verified = _active_selection_for_intake(task_id, active_path)
    sequence_id = verified["subject_id"]
    if expected_sequence_id is not None and sequence_id != expected_sequence_id:
        raise SequenceLaunchError(
            "active-sequence-does-not-match-entrypoint:"
            f"{expected_sequence_id}:{sequence_id}"
        )
    binding = _prepared_receipt_binding(verified)
    receipt = None
    receipt_hash = None
    prepared_path = None
    if binding is not None:
        try:
            receipt, receipt_hash, prepared_path = work_memory.load_receipt(
                task_id, PREPARED_RECEIPT_NAME,
            )
        except work_memory.WorkMemoryError as exc:
            if exc.code != f"missing-{PREPARED_RECEIPT_NAME}-receipt":
                raise
    if receipt is not None:
        expected = {
            "schema_version": 1,
            "task_id": task_id,
            "sequence_id": sequence_id,
            **binding,
        }
        if any(receipt.get(key) != value for key, value in expected.items()):
            receipt = None
        elif receipt.get("dispatch_stage") == "completed":
            receipt = None
        elif not isinstance(receipt.get("prepared"), Mapping):
            raise SequenceLaunchError("prepared-intake-receipt-invalid")
    if receipt is not None:
        prepared = dict(receipt["prepared"])
        stage = receipt["dispatch_stage"]
        result = {
            "schema_version": 1,
            "task_id": task_id,
            "sequence_id": sequence_id,
            "sequence_name": _sequence_name(verified["selection"], sequence_id),
            "dispatch_status": "PREPARED_NOT_AUTHORIZED",
            "prepared": prepared,
            "intake_reused": True,
            "prepared_receipt": {
                "path": str(prepared_path),
                "sha256": receipt_hash,
                "dispatch_stage": stage,
            },
        }
        if stage == "dry-run-passed":
            result["prepared"] = (
                sequence_intake_adapters.promote_commit_push_dry_run(prepared)
            )
            return _persist_prepared_result(
                result, verified,
                dispatch_stage="effect-pending",
                intake_reused=True,
            )
        if stage not in {"prepared", "effect-pending"}:
            raise SequenceLaunchError("prepared-intake-stage-invalid")
        return result
    fresh = prepare_active_sequence(
        task_id,
        expected_sequence_id=expected_sequence_id,
        input_fn=input_fn,
        output_fn=output_fn,
    )
    current = _active_selection_for_intake(task_id, active_path)
    if current["subject_id"] != fresh["sequence_id"]:
        raise SequenceLaunchError("active-selection-changed-during-intake")
    return _persist_prepared_result(
        fresh, current,
        dispatch_stage="prepared",
        intake_reused=False,
    )


def _record_prepared_dispatch(
    result: Mapping[str, Any], returncode: int,
) -> None:
    metadata = result.get("prepared_receipt")
    if returncode != 0 or not isinstance(metadata, Mapping):
        return
    task_id = result["task_id"]
    receipt, digest, _ = work_memory.load_receipt(
        task_id, PREPARED_RECEIPT_NAME,
    )
    if digest != metadata.get("sha256"):
        raise SequenceLaunchError("prepared-intake-receipt-changed")
    prepared = result.get("prepared")
    if receipt.get("prepared") != prepared:
        raise SequenceLaunchError("prepared-intake-payload-changed")
    stage = (
        "dry-run-passed"
        if result.get("sequence_id") == "commit-push-main"
        and isinstance(prepared, Mapping)
        and prepared.get("profile") == "dry-run"
        else "completed"
    )
    work_memory.write_receipt(
        task_id, PREPARED_RECEIPT_NAME,
        {**receipt, "dispatch_stage": stage},
    )


def _with_controller_preflight(
    task_id: str,
    sequence_id: str,
    prepared: Mapping[str, Any],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    result = dict(prepared)
    if sequence_id != "workflow-resume-from-phase-live-confirmation":
        return result
    repository = prepared.get("repository")
    if (
        not isinstance(repository, Mapping)
        or not isinstance(repository.get("key"), str)
        or not isinstance(repository.get("root"), str)
        or repository.get("key") not in repository_roots
        or repository_roots[repository["key"]] != repository["root"]
        or not Path(repository["root"]).is_absolute()
    ):
        raise SequenceLaunchError("workflow-resume-repository-required")
    python = (
        "/Users/kamenkamenov/.cache/codex-runtimes/"
        "codex-primary-runtime/dependencies/python/bin/python3"
    )
    result["preflight"] = {
        "argv": [
            "env",
            "-C",
            repository["root"],
            "PYTHONPATH=src",
            python,
            "-m",
            "unittest",
            "tests.unit.test_workflow_resume",
            "tests.unit.test_client_regeneration_resume",
            "tests.unit.test_vivacom_phase20_reproduction",
            "tests.unit.test_codex_role_command",
            "tests.unit.test_role_executor_retry",
            "-v",
        ],
        "step": "verify-automation",
        "proof_kind": "same-public-entrypoint",
    }
    result["controller_context"] = {
        "task_id": task_id,
        "repository_roots": dict(repository_roots),
        "guard_source": "sequence_doc",
        "guard_step": "verify-automation",
    }
    return result


def _required_argv_value(argv: Sequence[str], option: str) -> str:
    if argv.count(option) != 1:
        raise SequenceLaunchError(f"prepared-correction-option-invalid:{option}")
    index = argv.index(option)
    if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
        raise SequenceLaunchError(f"prepared-correction-option-invalid:{option}")
    return argv[index + 1]


def _prepare_correction_bootstrap(
    task_id: str,
    prepared: Mapping[str, Any],
    selection: Mapping[str, Any],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    argv = prepared.get("argv")
    artifacts = prepared.get("artifacts")
    if (
        not isinstance(argv, list)
        or not all(isinstance(token, str) for token in argv)
        or not isinstance(artifacts, Mapping)
        or not isinstance(artifacts.get("changed_artifacts"), Mapping)
    ):
        raise SequenceLaunchError("prepared-correction-invalid")
    target_task_id = _required_argv_value(argv, "--task-id")
    target_subject_id = (
        _required_argv_value(argv, "--subject-id")
        if prepared.get("profile") == "correct-registered"
        else None
    )
    events, _ = work_memory.load_ledger()
    terminal_run_ids = {
        event["run_id"]
        for event in events
        if event.get("event_type") in {"run_closed", "run_abandoned"}
    }
    starts = [
        event for event in events
        if (
            event.get("event_type") == "run_started"
            and event.get("task_id") == target_task_id
            and (
                target_subject_id is None
                or event.get("subject_id") == target_subject_id
            )
            and event["run_id"] not in terminal_run_ids
        )
    ]
    if len(starts) != 1:
        raise SequenceLaunchError("active-correction-run-ambiguous")
    run_id = starts[0]["run_id"]
    target_subject_id = starts[0]["subject_id"]
    target_lineage_id = starts[0]["lineage_id"]
    blockers: dict[str, dict[str, Any]] = {}
    for event in events:
        blocker_id = event.get("blocker_id")
        kind = event.get("event_type")
        if kind == "blocker_opened":
            if (
                event.get("subject_id") != target_subject_id
                or event.get("lineage_id") != target_lineage_id
            ):
                continue
            blockers[blocker_id] = {
                "opened": event,
                "status": "open",
                "occurrence_id": event["occurrence_id"],
                "run_id": event["run_id"],
            }
        elif kind == "blocker_recurred" and blocker_id in blockers:
            blockers[blocker_id].update(
                status="open",
                occurrence_id=event["occurrence_id"],
                run_id=event["run_id"],
            )
        elif kind == "blocker_transitioned" and blocker_id in blockers:
            blockers[blocker_id]["status"] = event["to_status"]
    open_blockers = [
        (blocker_id, state)
        for blocker_id, state in blockers.items()
        if state["status"] == "open" and state["run_id"] == run_id
    ]
    if not open_blockers:
        raise SequenceLaunchError("active-correction-blocker-missing")
    primary_id, primary = open_blockers[0]
    descriptor = artifacts["changed_artifacts"]
    try:
        changed = json.loads(descriptor["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SequenceLaunchError("prepared-correction-artifacts-invalid") from exc
    if not isinstance(changed, list) or not changed:
        raise SequenceLaunchError("prepared-correction-artifacts-invalid")
    changed_paths: list[str] = []
    for item in changed:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"repository_key", "path"}
            or item["repository_key"] not in repository_roots
        ):
            raise SequenceLaunchError("prepared-correction-artifacts-invalid")
        changed_paths.append(str(
            (Path(repository_roots[item["repository_key"]]) / item["path"]).resolve()
        ))
    solution = _required_argv_value(argv, "--solution")
    reusable = _required_argv_value(argv, "--reusable-behavior-changed")
    if reusable not in {"yes", "no"}:
        raise SequenceLaunchError("prepared-correction-context-mismatch")
    supersedes = [
        argv[index + 1]
        for index, token in enumerate(argv[:-1])
        if token == "--supersedes-correction-id"
    ]
    repository_root = Path(repository_roots["memory-knowledge"])
    directive_state = Path(os.environ.get(
        "MK_DIRECTIVE_STATE_PATH",
        str(sequence_guard.default_state_path(
            repository_root / "working-agreement" / "DIRECTIVES.md"
        )),
    )).resolve()
    bootstrap_argv = [
        "python3",
        str(repository_root / "scripts/work_memory_bootstrap_launcher.py"),
        "correct",
        "--task-id", target_task_id,
        "--directives-path", str(
            repository_root / "working-agreement/DIRECTIVES.md"
        ),
        "--directive-state", str(directive_state),
        "--run-id", run_id,
        "--blocker-id", primary_id,
    ]
    for blocker_id, _ in open_blockers[1:]:
        bootstrap_argv.extend(["--co-blocker-id", blocker_id])
    bootstrap_argv.extend([
        "--occurrence-id", primary["occurrence_id"],
        "--step-id", primary["opened"]["step_id"],
        "--solution", solution,
        "--reusable-behavior-changed", reusable,
        "--correction-id", str(uuid5(
            NAMESPACE_URL,
            f"memory-knowledge:{run_id}:{primary_id}:{primary['occurrence_id']}",
        )),
    ])
    for path in changed_paths:
        bootstrap_argv.extend(["--changed-artifact", path])
    for correction_id in supersedes:
        bootstrap_argv.extend(["--supersedes-correction-id", correction_id])
    result = dict(prepared)
    result["argv"] = bootstrap_argv
    return result


def _materialize_artifacts(prepared: Mapping[str, Any]) -> None:
    artifacts = prepared.get("artifacts", {})
    if not isinstance(artifacts, Mapping):
        raise SequenceLaunchError("prepared-artifacts-invalid")
    for artifact_id, artifact in artifacts.items():
        if (
            not isinstance(artifact_id, str)
            or not isinstance(artifact, Mapping)
            or set(artifact) != {"content", "path"}
            or not isinstance(artifact["content"], str)
            or not isinstance(artifact["path"], str)
        ):
            raise SequenceLaunchError("prepared-artifact-invalid")
        path = Path(artifact["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(artifact["content"])
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def _invoked_script(prepared: Mapping[str, Any]) -> Path:
    argv = prepared.get("argv")
    repository = prepared.get("repository")
    if (
        not isinstance(argv, list)
        or not isinstance(repository, Mapping)
        or not isinstance(repository.get("root"), str)
    ):
        raise SequenceLaunchError("prepared-argv-invalid")
    repository_root = Path(repository["root"])
    executable = Path(argv[0]).name if argv and isinstance(argv[0], str) else ""
    # A registered command may be invoked through a project runner: "uv run python <script> ...".
    # Strip that prefix first, then resolve exactly as a direct invocation. Live 2026-07-29 the
    # un-stripped form inspected only argv[:1] -- the runner itself -- so it found ZERO script
    # candidates and every uv-run sequence was undispatchable (blk-af452065311f7f6c0b7ebc6e).
    if (
        executable in {"uv", "poetry", "pipenv", "hatch", "rye", "pdm"}
        and len(argv) > 2
        and isinstance(argv[1], str)
        and argv[1] == "run"
    ):
        argv = argv[2:]
        executable = Path(argv[0]).name if isinstance(argv[0], str) else ""
    script_tokens = (
        argv[1:2]
        if executable in {"python", "python3", "bash", "sh", "zsh"}
        else argv[:1]
    )
    candidates = []
    for token in script_tokens:
        if not isinstance(token, str) or Path(token).suffix not in {".py", ".sh"}:
            continue
        path = Path(token)
        candidates.append(
            path.resolve()
            if path.is_absolute()
            else (repository_root / path).resolve()
        )
    if len(candidates) != 1:
        raise SequenceLaunchError("prepared-script-source-ambiguous")
    return candidates[0]


def _guard_prepared(task_id: str, prepared: Mapping[str, Any]) -> None:
    argv = prepared.get("argv")
    profile = prepared.get("profile")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(token, str) for token in argv)
        or not isinstance(profile, str)
        or not profile
    ):
        raise SequenceLaunchError("prepared-command-invalid")
    source = _invoked_script(prepared)
    if profile in {"correct", "correct-registered"}:
        selection, _, _ = work_memory.load_receipt(task_id, "selection")
        roots = _repository_roots(selection)
        current_source = source.resolve()
        matches = [
            item for item in selection["source_bundle"]
            if item["repository_key"] in roots
            and (Path(roots[item["repository_key"]]) / item["path"]).resolve()
            == current_source
        ]
        artifacts = prepared.get("artifacts")
        artifact = (
            artifacts.get("changed_artifacts")
            if isinstance(artifacts, Mapping)
            else None
        )
        if (
            len(matches) != 1
            or work_memory.sha256_bytes(current_source.read_bytes())
            != matches[0]["sha256"]
            or len(argv) < 3
            or Path(argv[1]).name != "work_memory_bootstrap_launcher.py"
            or argv[2] != "correct"
            or not _required_argv_value(argv, "--task-id")
            or "--changed-artifacts-file" in argv
            or "--changed-artifact" not in argv
            or not isinstance(artifact, Mapping)
            or not isinstance(artifact.get("path"), str)
            or not Path(artifact["path"]).resolve().is_relative_to(
                Path("/private/tmp/sequence-intake", task_id).resolve()
            )
        ):
            raise SequenceLaunchError("correction-orchestrator-not-sealed")
        return
    sequence_guard.cmd_guard(SimpleNamespace(
        task_id=task_id,
        root=None,
        state=None,
        directives_path=str(DIRECTIVES_PATH),
        directive_state=None,
        directive_max_age_minutes=sequence_guard.DEFAULT_MAX_AGE_MINUTES,
        step=f"semantic-intake:{profile}",
        command=shlex.join(argv),
        command_argv=argv,
        source="script",
        source_ref=str(source),
        correction_bootstrap=False,
        post_correction_bootstrap=False,
        evidence_text=None,
    ))


def _guard_preflight(task_id: str, prepared: Mapping[str, Any]) -> None:
    preflight = prepared.get("preflight")
    repository = prepared.get("repository")
    context = prepared.get("controller_context")
    if (
        prepared.get("sequence_id")
        != "workflow-resume-from-phase-live-confirmation"
        or not isinstance(preflight, Mapping)
        or set(preflight) != {"argv", "step", "proof_kind"}
        or not isinstance(repository, Mapping)
        or not isinstance(repository.get("key"), str)
        or not isinstance(repository.get("root"), str)
        or not isinstance(context, Mapping)
        or set(context) != {
            "task_id", "repository_roots", "guard_source", "guard_step",
        }
    ):
        raise SequenceLaunchError("workflow-resume-preflight-required")
    roots = context["repository_roots"]
    if (
        context["task_id"] != task_id
        or context["guard_source"] != "sequence_doc"
        or context["guard_step"] != "verify-automation"
        or not isinstance(roots, Mapping)
        or roots.get(repository["key"]) != repository["root"]
        or not Path(repository["root"]).is_absolute()
    ):
        raise SequenceLaunchError("workflow-resume-controller-context-invalid")
    python = (
        "/Users/kamenkamenov/.cache/codex-runtimes/"
        "codex-primary-runtime/dependencies/python/bin/python3"
    )
    expected_argv = [
        "env",
        "-C",
        repository["root"],
        "PYTHONPATH=src",
        python,
        "-m",
        "unittest",
        "tests.unit.test_workflow_resume",
        "tests.unit.test_client_regeneration_resume",
        "tests.unit.test_vivacom_phase20_reproduction",
        "tests.unit.test_codex_role_command",
        "tests.unit.test_role_executor_retry",
        "-v",
    ]
    if (
        preflight.get("argv") != expected_argv
        or preflight.get("step") != "verify-automation"
        or preflight.get("proof_kind") != "same-public-entrypoint"
    ):
        raise SequenceLaunchError("workflow-resume-preflight-invalid")
    selection, _, _ = work_memory.load_receipt(task_id, "selection")
    if (
        selection.get("subject_id")
        != "workflow-resume-from-phase-live-confirmation"
        or dict(roots) != _repository_roots(selection)
    ):
        raise SequenceLaunchError(
            "workflow-resume-selection-context-mismatch",
        )
    sequence_guard.cmd_guard(SimpleNamespace(
        task_id=task_id,
        root=None,
        state=None,
        directives_path=str(DIRECTIVES_PATH),
        directive_state=None,
        directive_max_age_minutes=sequence_guard.DEFAULT_MAX_AGE_MINUTES,
        step=preflight["step"],
        command=shlex.join(expected_argv),
        command_argv=expected_argv,
        source="sequence_doc",
        source_ref=selection["document"],
        correction_bootstrap=False,
        post_correction_bootstrap=False,
        evidence_text=None,
    ))


def _workflow_resume_dispatch_receipt(
    task_id: str,
    prepared: Mapping[str, Any],
) -> tuple[Path, str]:
    argv = prepared["argv"]
    repository = prepared["repository"]
    if len(argv) < 2:
        raise SequenceLaunchError("workflow-resume-dispatch-receipt-invalid")
    script = Path(argv[1]).resolve()
    root = Path(repository["root"]).resolve()
    if (
        prepared.get("sequence_id") != WORKFLOW_RESUME_SEQUENCE
        or script != (root / "scripts/run_client_regeneration.py").resolve()
    ):
        raise SequenceLaunchError("workflow-resume-dispatch-receipt-invalid")
    payload = {
        "schema_version": 1,
        "sequence_id": WORKFLOW_RESUME_SEQUENCE,
        "task_id": task_id,
        "repository_root": str(root),
        "script": str(script),
        "arguments": argv[2:],
    }
    content = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    directory = Path("/private/tmp/sequence-intake", task_id)
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(
        prefix=".workflow-resume-dispatch-",
        suffix=".json",
        dir=directory,
    )
    path = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path, hashlib.sha256(content).hexdigest()


def _dispatch_prepared(task_id: str, prepared: Mapping[str, Any]) -> int:
    argv = prepared.get("argv")
    repository = prepared.get("repository")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(token, str) for token in argv)
        or not isinstance(repository, Mapping)
        or not isinstance(repository.get("root"), str)
    ):
        raise SequenceLaunchError("prepared-dispatch-invalid")
    _require_host_capabilities(prepared)
    publication_run_id = _active_publication_run_id(task_id, prepared)
    if (
        prepared.get("sequence_id")
        == WORKFLOW_RESUME_SEQUENCE
    ):
        _guard_preflight(task_id, prepared)
    _guard_prepared(task_id, prepared)
    _materialize_artifacts(prepared)
    environment = os.environ.copy()
    environment[DISPATCH_MARKER] = "1"
    additions = prepared.get("environment", {})
    if not isinstance(additions, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in additions.items()
    ):
        raise SequenceLaunchError("prepared-environment-invalid")
    if {
        DISPATCH_MARKER, DISPATCH_RECEIPT, HOST_CAPABILITIES_ENV,
        SEQUENCE_RUN_ID_ENV,
    } & set(additions):
        raise SequenceLaunchError("prepared-environment-reserved")
    environment.update(additions)
    if publication_run_id is not None:
        environment[SEQUENCE_RUN_ID_ENV] = publication_run_id
    if (
        prepared.get("sequence_id")
        == WORKFLOW_RESUME_SEQUENCE
    ):
        preflight = prepared["preflight"]
        result = subprocess.run(
            preflight["argv"],
            cwd=repository["root"],
            env=environment,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            return result.returncode
        receipt_path, receipt_hash = _workflow_resume_dispatch_receipt(
            task_id, prepared,
        )
        environment[DISPATCH_MARKER] = receipt_hash
        environment[DISPATCH_RECEIPT] = str(receipt_path)
        try:
            return subprocess.run(
                argv,
                cwd=repository["root"],
                env=environment,
                check=False,
                shell=False,
            ).returncode
        finally:
            receipt_path.unlink(missing_ok=True)
    return subprocess.run(
        argv,
        cwd=repository["root"],
        env=environment,
        check=False,
        shell=False,
    ).returncode


def _task_and_preparation(
    *,
    expected_sequence_id: str | None,
    input_fn: Callable[[str], str] | None,
    output_fn: Callable[[str], None] | None,
) -> dict[str, Any]:
    task = script_intake.collect(
        TASK_SPEC, input_fn=input_fn, output_fn=output_fn,
    )
    active_path = work_memory.receipt_path(task["task_id"], "active")
    verified = _active_selection_for_intake(task["task_id"], active_path)
    sequence_id = verified["subject_id"]
    if expected_sequence_id is not None and sequence_id != expected_sequence_id:
        raise SequenceLaunchError(
            "active-sequence-does-not-match-entrypoint:"
            f"{expected_sequence_id}:{sequence_id}"
        )
    _require_current_intake_contract(sequence_id)
    return _load_or_prepare_active_sequence(
        task["task_id"],
        expected_sequence_id=expected_sequence_id,
        input_fn=input_fn,
        output_fn=output_fn,
    )


def _require_current_intake_contract(sequence_id: str) -> None:
    contract_drift = sequence_intake_adapters.check_intake_contracts(work_memory.ROOT)
    selected_drift = [
        error for error in contract_drift
        if error == f"intake-contract-drift:{sequence_id}"
        or error.startswith("intake-contracts-missing:")
        or error.startswith("intake-contracts-unreadable:")
        or error == "intake-contract-drift:document-level"
    ]
    if selected_drift:
        raise SequenceLaunchError(
            "intake-contracts-stale:" + ";".join(selected_drift[:5])
        )


def _main(
    values: Sequence[str],
    *,
    expected_sequence_id: str | None = None,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> int:
    if values:
        print(json.dumps({
            "ok": False,
            "error": "no-argument-entrypoint-required",
        }, sort_keys=True), file=sys.stderr)
        return 2
    try:
        result = _task_and_preparation(
            expected_sequence_id=expected_sequence_id,
            input_fn=input_fn,
            output_fn=output_fn,
        )
        print(json.dumps(
            {"ok": True, **result},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ))
        return 0
    except (
        SequenceLaunchError,
        script_intake.IntakeCancelled,
        script_intake.IntakeSpecError,
        sequence_intake_adapters.AdapterError,
        work_memory.WorkMemoryError,
    ) as exc:
        error = exc.code if isinstance(
            exc, work_memory.WorkMemoryError,
        ) else str(exc)
        print(json.dumps({
            "ok": False,
            "error": error or type(exc).__name__,
        }, sort_keys=True), file=sys.stderr)
        return getattr(exc, "exit_code", 2)


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values:
        return _main(
            values,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    return _interactive_dispatch(
        expected_sequence_id=None,
        input_fn=input_fn,
        output_fn=output_fn,
    )


def _interactive_dispatch(
    *,
    expected_sequence_id: str | None,
    task_id: str | None = None,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> int:
    try:
        if task_id is None:
            result = _task_and_preparation(
                expected_sequence_id=expected_sequence_id,
                input_fn=input_fn,
                output_fn=output_fn,
            )
        else:
            if expected_sequence_id is None:
                active_path = work_memory.receipt_path(task_id, "active")
                expected_sequence_id = _active_selection_for_intake(
                    task_id, active_path,
                )["subject_id"]
            _require_current_intake_contract(expected_sequence_id)
            result = _load_or_prepare_active_sequence(
                task_id,
                expected_sequence_id=expected_sequence_id,
                input_fn=input_fn,
                output_fn=output_fn,
            )
        print(json.dumps({
            "ok": True,
            **result,
        }, sort_keys=True, ensure_ascii=False), file=sys.stderr)
        authorization = script_intake.collect(
            DISPATCH_SPEC, input_fn=input_fn, output_fn=output_fn,
        )
        if not authorization["authorize"]:
            print(json.dumps({
                "ok": True,
                "task_id": result["task_id"],
                "sequence_id": result["sequence_id"],
                "dispatch_status": "DECLINED",
            }, sort_keys=True))
            return 0
        returncode = _dispatch_prepared(
            result["task_id"], result["prepared"],
        )
        _record_prepared_dispatch(result, returncode)
        return returncode
    except (
        SequenceLaunchError,
        script_intake.IntakeCancelled,
        script_intake.IntakeSpecError,
        sequence_intake_adapters.AdapterError,
        work_memory.WorkMemoryError,
    ) as exc:
        error = exc.code if isinstance(
            exc, work_memory.WorkMemoryError,
        ) else str(exc)
        print(json.dumps({
            "ok": False,
            "error": error or type(exc).__name__,
        }, sort_keys=True), file=sys.stderr)
        return getattr(exc, "exit_code", 2)


def main_for_sequence(
    sequence_id: str,
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> int:
    if sequence_id not in sequence_intake_adapters.ADAPTER_REGISTRY:
        raise SequenceLaunchError(f"sequence-not-registered:{sequence_id}")
    values = list(sys.argv[1:] if argv is None else argv)
    if values:
        return _main(
            values,
            expected_sequence_id=sequence_id,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    return _interactive_dispatch(
        expected_sequence_id=sequence_id,
        input_fn=input_fn,
        output_fn=output_fn,
    )


def main_for_active_task(
    sequence_id: str,
    task_id: str,
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> int:
    """Enter a registered interview using the controller-owned task identity."""
    if sequence_id not in sequence_intake_adapters.ADAPTER_REGISTRY:
        raise SequenceLaunchError(f"sequence-not-registered:{sequence_id}")
    if not task_id:
        raise SequenceLaunchError("active-task-id-required")
    return _interactive_dispatch(
        expected_sequence_id=sequence_id,
        task_id=task_id,
        input_fn=input_fn,
        output_fn=output_fn,
    )


if __name__ == "__main__":
    raise SystemExit(main())
