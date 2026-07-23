#!/usr/bin/env python3
"""Prepare the active registered sequence through zero-argument semantic intake."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


class SequenceLaunchError(ValueError):
    """The active sequence cannot be prepared safely."""


def _repository_roots(selection: Mapping[str, Any]) -> dict[str, str]:
    snapshot = selection.get("repository_roots")
    if snapshot is None:
        roots = work_memory._repo_roots(selection.get("repository_roots_file"))
    else:
        roots = work_memory._repo_roots(snapshot=snapshot)
    return {key: str(path.resolve()) for key, path in roots.items()}


def _artifact_paths(task_id: str, sequence_id: str) -> dict[str, str]:
    root = Path("/private/tmp/sequence-intake", task_id, sequence_id)
    suffixes = {
        "approved_paths": ".txt",
        "overlay_paths": ".txt",
        "changed_artifacts": ".json",
        "request": ".json",
        "spec": ".json",
    }
    return {
        artifact_id: str(root / f"{artifact_id}{suffixes[artifact_id]}")
        for artifact_id in sequence_intake_adapters.artifact_ids(sequence_id)
    }


def prepare_active_sequence(
    task_id: str,
    *,
    expected_sequence_id: str | None = None,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    active_path = work_memory.receipt_path(task_id, "active")
    verified = sequence_guard.verify_receipts(task_id, active_path)
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
    return {
        "schema_version": 1,
        "task_id": task_id,
        "sequence_id": sequence_id,
        "dispatch_status": "PREPARED_NOT_AUTHORIZED",
        "prepared": prepared,
    }


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
    candidates = []
    for token in argv:
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
    sequence_guard.cmd_guard(SimpleNamespace(
        task_id=task_id,
        root=None,
        state=None,
        directives_path=None,
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
    environment.update(additions)
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
    return prepare_active_sequence(
        task["task_id"],
        expected_sequence_id=expected_sequence_id,
        input_fn=input_fn,
        output_fn=output_fn,
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
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> int:
    try:
        result = _task_and_preparation(
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
        return _dispatch_prepared(
            result["task_id"], result["prepared"],
        )
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


if __name__ == "__main__":
    raise SystemExit(main())
