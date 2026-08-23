#!/usr/bin/env python3
"""Drive grounded assessment verdicts through structured Codex responses."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONTROLLER = SCRIPT_DIR / "assessment_verdicts.py"


class AssessmentVerdictLaunchError(RuntimeError):
    """Raised when the controlled verdict run fails to advance exactly."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssessmentVerdictLaunchError(f"{name} is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _journal_module():
    return _load_module("assessment_verdict_runner_journal", SCRIPT_DIR / "projection_interview.py")


def _controller_module():
    return _load_module("assessment_verdict_runner_controller", CONTROLLER)


def _progress(work: Path) -> tuple[int, int, bool]:
    path = work / "interview.jsonl"
    if not path.exists():
        return 0, 0, False
    try:
        entries = _journal_module()._read_journal(path)
    except Exception as error:
        raise AssessmentVerdictLaunchError(f"assessment verdict journal is invalid: {error}") from error
    deterministic = sum(entry.get("event") == "incomplete_verdict_recorded" for entry in entries)
    model = sum(entry.get("event") == "unit_answer_recorded" and entry.get("accepted") is True for entry in entries)
    completed = any(entry.get("event") == "assessment_verdicts_completed" for entry in entries)
    return deterministic + model, model, completed


def _prompt(question: dict[str, object]) -> str:
    return (
        "Assess only this one evidence-complete unit. Compare the criterion with the observation "
        "in their supplied context. Return exactly one JSON object matching the output schema. "
        "Choose only aligned or misaligned. State the concrete comparison in measure, explain the "
        "verdict in reason, and cite at least one supplied evidence id from criterion, observation, "
        "and context. Use only the supplied evidence. Do not run commands or edit files.\n\n"
        "Code-bound question:\n" + json.dumps(question, indent=2, sort_keys=True)
    )


def _model_client(environ: dict[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    configured = values.get("MK_CLIENT_KIND", "codex")
    if configured != "codex":
        raise AssessmentVerdictLaunchError("structured assessment verdicts currently require MK_CLIENT_KIND=codex")
    return configured


def _executable(client: str) -> str:
    executable = shutil.which(client)
    if executable is None:
        raise AssessmentVerdictLaunchError(f"model executable is unavailable for client {client}")
    return executable


def build_structured_codex_argv(executable: str, work: Path, question: dict[str, object], schema_path: Path, response_path: Path) -> list[str]:
    return [
        executable,
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        str(work.resolve()),
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(response_path),
        "--color",
        "never",
        "--",
        _prompt(question),
    ]


def _write_exact(path: Path, value: object, label: str) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    if path.exists() and path.read_bytes() != payload:
        raise AssessmentVerdictLaunchError(f"{label} already exists with different bytes")
    if not path.exists():
        path.write_bytes(payload)


def _write_process_output(path: Path, value: object) -> None:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode()
    elif value is None:
        payload = b""
    else:
        payload = str(value).encode()
    path.write_bytes(payload)


def _next_attempt_dir(work: Path, unit_id: str) -> Path:
    root = work / "model-runs" / unit_id
    root.mkdir(parents=True, exist_ok=True)
    numbers = []
    for path in root.iterdir():
        if path.is_dir() and path.name.startswith("attempt-"):
            try:
                numbers.append(int(path.name.removeprefix("attempt-")))
            except ValueError:
                pass
    attempt = root / f"attempt-{max(numbers, default=0) + 1:06d}"
    attempt.mkdir()
    return attempt


def run(evidence: Path, sufficiency: Path, work: Path, *, max_model_units: int | None = None, model_run_fn: Callable[..., object] | None = None, environ: dict[str, str] | None = None) -> dict[str, object]:
    if max_model_units is not None and (not isinstance(max_model_units, int) or isinstance(max_model_units, bool) or max_model_units < 1):
        raise AssessmentVerdictLaunchError("max_model_units must be one positive integer")
    if not evidence.is_file() or not sufficiency.is_file():
        raise AssessmentVerdictLaunchError("assessment evidence and sufficiency artifacts must both exist")
    work.mkdir(parents=True, exist_ok=True)
    before, model_before, completed_before = _progress(work)
    if completed_before:
        artifact = work / "verdicts.json"
        if not artifact.is_file():
            raise AssessmentVerdictLaunchError("completed verdict journal lost its artifact")
        return {"ok": True, "status": "already-complete", "recorded_unit_count": before, "artifact": str(artifact.resolve())}
    client = _model_client(environ)
    executable = _executable(client)
    controller = _controller_module()
    accepted_model = 0
    completed_after = False
    while max_model_units is None or accepted_model < max_model_units:
        try:
            prepared = controller.prepare_question(evidence, sufficiency, work)
        except controller.AssessmentVerdictError as error:
            raise AssessmentVerdictLaunchError(str(error)) from error
        if prepared["status"] == "complete":
            completed_after = True
            break
        question = prepared["question"]
        schema = prepared["response_schema"]
        unit_id = question["unit"]["unit_id"]
        accepted = False
        for _attempt in range(3):
            attempt_dir = _next_attempt_dir(work, unit_id)
            question_path = attempt_dir / "question.json"
            schema_path = attempt_dir / "response-schema.json"
            response_path = attempt_dir / "response.json"
            _write_exact(question_path, question, "model question")
            _write_exact(schema_path, schema, "model response schema")
            completed = (model_run_fn or subprocess.run)(
                build_structured_codex_argv(executable, work, question, schema_path, response_path),
                check=False,
                capture_output=True,
                text=True,
            )
            _write_process_output(attempt_dir / "stdout.txt", getattr(completed, "stdout", None))
            _write_process_output(attempt_dir / "stderr.txt", getattr(completed, "stderr", None))
            returncode = getattr(completed, "returncode", None)
            _write_exact(attempt_dir / "receipt.json", {
                "schema_version": 1,
                "unit_id": unit_id,
                "returncode": returncode,
                "question_sha256": hashlib.sha256(question_path.read_bytes()).hexdigest(),
                "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
                "response_exists": response_path.is_file(),
            }, "model attempt receipt")
            if returncode != 0:
                raise AssessmentVerdictLaunchError(f"Codex verdict response for {unit_id} exited with {returncode!r}; evidence: {attempt_dir}")
            if not response_path.is_file():
                raise AssessmentVerdictLaunchError(f"Codex verdict response for {unit_id} is missing; evidence: {attempt_dir}")
            try:
                submitted = controller.submit_response(evidence, sufficiency, work, response_path.read_text())
            except controller.AssessmentVerdictError as error:
                raise AssessmentVerdictLaunchError(str(error)) from error
            _write_exact(attempt_dir / "submission.json", submitted, "model submission result")
            if submitted["status"] != "rejected":
                accepted = True
                accepted_model += 1
                completed_after = submitted["status"] == "complete"
                break
            prepared = controller.prepare_question(evidence, sufficiency, work)
            question = prepared["question"]
            schema = prepared["response_schema"]
        if not accepted:
            raise AssessmentVerdictLaunchError(f"Codex produced three rejected responses for {unit_id}")
        if completed_after:
            break
    after, model_after, journal_completed = _progress(work)
    if model_after != model_before + accepted_model or after < before + accepted_model:
        raise AssessmentVerdictLaunchError("verdict journal progress does not match accepted structured responses")
    completed_after = completed_after or journal_completed
    artifact = work / "verdicts.json"
    if completed_after and not artifact.is_file():
        raise AssessmentVerdictLaunchError("model run completed without the verdict artifact")
    return {
        "ok": True,
        "status": "complete" if completed_after else "paused",
        "model_client": client,
        "recorded_before": before,
        "recorded_after": after,
        "model_answers_this_run": accepted_model,
        "deterministic_verdicts_this_run": after - before - accepted_model,
        "artifact": str(artifact.resolve()) if completed_after else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--sufficiency", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--max-model-units", type=int)
    args = parser.parse_args()
    try:
        result = run(args.evidence, args.sufficiency, args.work, max_model_units=args.max_model_units)
    except AssessmentVerdictLaunchError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
