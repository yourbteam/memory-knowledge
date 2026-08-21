#!/usr/bin/env python3
"""Run only the pending first-projection relationship verification stage."""

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
        os.execv(uv, [uv, "run", "python", str(Path(__file__).resolve()), *sys.argv[1:]])
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
    "info_intake_projection_runner_for_verification_stage",
    "run_projection_with_codex.py",
)
START_INTAKE = _load_sibling(
    "info_intake_start_for_verification_stage",
    "start_intake.py",
)

VERIFY_FLAG = "--run-projection-verification"
CORRECT_FLAG = "--run-relationship-correction"


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


def _terminal_payload(work: Path, result: dict[str, object]) -> dict[str, object]:
    if (
        result.get("status") == "ready_for_projection_assessment"
        and result.get("stopped") == "first_projection_recorded"
        and isinstance(result.get("projection"), dict)
    ):
        return {
            "ok": True,
            "boundary": "projection_recorded",
            "status": result["status"],
            "stopped": result["stopped"],
            "projection": result["projection"],
            "work": str(work),
        }

    if (
        result.get("status") == "waiting_for_model"
        and result.get("stopped") == "correcting_rejected_relationships"
    ):
        work_items = result.get("work")
        if (
            not isinstance(work_items, list)
            or len(work_items) != 1
            or not isinstance(work_items[0], dict)
            or not isinstance(work_items[0].get("command"), list)
            or not work_items[0]["command"]
            or work_items[0]["command"][-1] != CORRECT_FLAG
        ):
            raise CODEX_RUNNER.LaunchError(
                "the rejected relationship boundary lost its exact correction command"
            )
        attachment, saved_command = CODEX_RUNNER.load_request(work)
        saved_attachments = attachment if isinstance(attachment, tuple) else (attachment,)
        if saved_command != work_items[0]["command"] or work_items[0].get(
            "attachments"
        ) != [str(path) for path in saved_attachments]:
            raise CODEX_RUNNER.LaunchError(
                "the rejected relationship boundary changed after verification"
            )
        return {
            "ok": True,
            "boundary": "relationship_correction_required",
            "status": result["status"],
            "stopped": result["stopped"],
            "work": str(work),
        }

    if result.get("status") == "blocked":
        return {"ok": False, "boundary": "blocked", **result, "work": str(work)}
    raise CODEX_RUNNER.LaunchError(
        "relationship verification did not reach projection completion or correction"
    )


def run_one_stage(
    work: Path,
    *,
    model_runner: Callable[..., object] = subprocess.run,
) -> tuple[int, dict[str, object]]:
    work = work.expanduser().resolve()
    try:
        attachment, interview_command = CODEX_RUNNER.load_request(work)
        if not interview_command or interview_command[-1] != VERIFY_FLAG:
            raise CODEX_RUNNER.LaunchError(
                "the intake is not waiting for relationship verification"
            )
        model_client = CODEX_RUNNER.active_model_client()
        executable = CODEX_RUNNER.resolve_model_executable(model_client)
        argv = CODEX_RUNNER.build_model_argv(
            model_client, executable, work, attachment, interview_command
        )
        completed = model_runner(argv, check=False)
        returncode = getattr(completed, "returncode", None)
        if returncode != 0:
            return 3, {
                "ok": False,
                "boundary": "model_stage_failed",
                "returncode": returncode,
                "work": str(work),
            }

        first = _resume(work)
        control_before = _durable_control_bytes(work)
        second = _resume(work)
        control_after = _durable_control_bytes(work)
        if first != second or control_before != control_after:
            raise CODEX_RUNNER.LaunchError(
                "relationship verification resume is not idempotent"
            )
        payload = _terminal_payload(work, first)
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
    print("Constraints: Use an image intake waiting for relationship verification.")
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
