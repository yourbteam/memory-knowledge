#!/usr/bin/env python3
"""Correct rejected first-projection relationships and verify proposals independently."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable


def _enter_managed_python() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    managed_environment = repo_root / ".venv"
    if Path(sys.prefix).resolve() == managed_environment.resolve():
        return
    managed_python = managed_environment / "bin" / "python"
    if managed_python.is_file() and os.access(managed_python, os.X_OK):
        os.execv(str(managed_python), [str(managed_python), *sys.argv])
    uv = shutil.which("uv")
    if uv is not None:
        os.execv(
            uv,
            [uv, "run", "python", str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    raise RuntimeError(
        "the repository-managed Python environment is unavailable; create .venv or install uv"
    )


_enter_managed_python()


def _load_sibling(name: str, filename: str) -> object:
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().with_name(filename)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{filename} is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CODEX_RUNNER = _load_sibling(
    "info_intake_projection_runner_for_correction_stage",
    "run_projection_with_codex.py",
)
START_INTAKE = _load_sibling(
    "info_intake_start_for_correction_stage",
    "start_intake.py",
)

CORRECT_FLAG = "--run-relationship-correction"
VERIFY_FLAG = "--run-correction-verification"


def _resume(work: Path) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(
            encoding="utf-8"
        )
        purpose = (work / "sources" / "source-000002.txt").read_text(
            encoding="utf-8"
        )
    except OSError as error:
        raise CODEX_RUNNER.LaunchError(
            "the intake opening or purpose is unavailable"
        ) from error
    result = START_INTAKE.drive(work, opening, purpose)
    if not isinstance(result, dict):
        raise CODEX_RUNNER.LaunchError("the intake resume result must be an object")
    return result


def _durable_control_bytes(work: Path) -> tuple[bytes, bytes]:
    try:
        return (
            (work / "ledger.jsonl").read_bytes(),
            (work / "intake-state.json").read_bytes(),
        )
    except OSError as error:
        raise CODEX_RUNNER.LaunchError(
            "the intake ledger or state is unavailable"
        ) from error


def _request_for(
    work: Path,
    expected_flag: str,
    expected_stopped: str,
    expected_stage: str,
) -> tuple[Path | tuple[Path, ...], list[str]]:
    boundary = _resume(work)
    if (
        boundary.get("status") != "waiting_for_model"
        or boundary.get("stopped") != expected_stopped
    ):
        raise CODEX_RUNNER.LaunchError(
            f"the intake is not waiting for {expected_stage}"
        )
    attachment, command = CODEX_RUNNER.load_request(work)
    if not command or command[-1] != expected_flag:
        raise CODEX_RUNNER.LaunchError(
            f"the intake is not waiting for {expected_stage}"
        )
    return attachment, command


def _run_model_stage(
    work: Path,
    attachment: Path | tuple[Path, ...],
    command: list[str],
    *,
    model_runner: Callable[..., object],
) -> int:
    model_client = CODEX_RUNNER.active_model_client()
    executable = CODEX_RUNNER.resolve_model_executable(model_client)
    argv = CODEX_RUNNER.build_model_argv(
        model_client, executable, work, attachment, command
    )
    completed = model_runner(argv, check=False)
    returncode = getattr(completed, "returncode", None)
    return returncode if isinstance(returncode, int) else 3


def _projection_payload(
    work: Path, result: dict[str, object]
) -> dict[str, object]:
    if (
        result.get("status") != "ready_for_projection_assessment"
        or result.get("stopped") != "first_projection_recorded"
        or not isinstance(result.get("projection"), dict)
    ):
        if result.get("status") == "blocked":
            return {"ok": False, "boundary": "blocked", **result, "work": str(work)}
        raise CODEX_RUNNER.LaunchError(
            "relationship correction did not reach canonical projection recording"
        )
    return {
        "ok": True,
        "boundary": "projection_recorded",
        "status": result["status"],
        "stopped": result["stopped"],
        "projection": result["projection"],
        "work": str(work),
    }


def _idempotent_projection_result(
    work: Path, first: dict[str, object]
) -> dict[str, object]:
    control_before = _durable_control_bytes(work)
    second = _resume(work)
    control_after = _durable_control_bytes(work)
    if first != second or control_before != control_after:
        raise CODEX_RUNNER.LaunchError(
            "relationship correction resume is not idempotent"
        )
    return _projection_payload(work, first)


def run_one_stage(
    work: Path,
    *,
    model_runner: Callable[..., object] = subprocess.run,
) -> tuple[int, dict[str, object]]:
    work = work.expanduser().resolve()
    try:
        attachment, correction_command = _request_for(
            work,
            CORRECT_FLAG,
            "correcting_rejected_relationships",
            "relationship correction",
        )
        correction_returncode = _run_model_stage(
            work,
            attachment,
            correction_command,
            model_runner=model_runner,
        )
        if correction_returncode != 0:
            return 3, {
                "ok": False,
                "boundary": "model_stage_failed",
                "stage": "relationship_correction",
                "returncode": correction_returncode,
                "work": str(work),
            }

        after_correction = _resume(work)
        if after_correction.get("status") == "ready_for_projection_assessment":
            payload = _idempotent_projection_result(work, after_correction)
            return (0 if payload.get("ok") is True else 3), payload
        if (
            after_correction.get("status") != "waiting_for_model"
            or after_correction.get("stopped")
            != "verifying_relationship_corrections"
        ):
            payload = _projection_payload(work, after_correction)
            return (0 if payload.get("ok") is True else 3), payload

        verification_attachment, verification_command = _request_for(
            work,
            VERIFY_FLAG,
            "verifying_relationship_corrections",
            "relationship correction verification",
        )
        verification_returncode = _run_model_stage(
            work,
            verification_attachment,
            verification_command,
            model_runner=model_runner,
        )
        if verification_returncode != 0:
            return 3, {
                "ok": False,
                "boundary": "model_stage_failed",
                "stage": "relationship_correction_verification",
                "returncode": verification_returncode,
                "work": str(work),
            }

        payload = _idempotent_projection_result(work, _resume(work))
        return (0 if payload.get("ok") is True else 3), payload
    except (CODEX_RUNNER.LaunchError, OSError, ValueError) as error:
        return 3, {"ok": False, "error": str(error), "work": str(work)}


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps({"ok": False, "error": "this launcher accepts no arguments"}))
        return 2
    print("Question: Intake work directory")
    print("Response format: One absolute directory path.")
    print("Example: /private/tmp/example-intake")
    print("Constraints: Use an image intake waiting for relationship correction.")
    try:
        work = Path(input("Answer: ").strip())
    except EOFError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    code, payload = run_one_stage(work)
    print(json.dumps(payload, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
