#!/usr/bin/env python3
"""Drive code-controlled assessment sufficiency through structured Codex responses."""

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
CONTROLLER = SCRIPT_DIR / "assessment_sufficiency.py"


class AssessmentSufficiencyLaunchError(RuntimeError):
    """Raised when a model run does not advance the controlled interview exactly."""


def _journal_module():
    path = SCRIPT_DIR / "projection_interview.py"
    spec = importlib.util.spec_from_file_location(
        "assessment_sufficiency_runner_journal", path
    )
    if spec is None or spec.loader is None:
        raise AssessmentSufficiencyLaunchError(
            "assessment sufficiency journal contract is unavailable"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _controller_module():
    spec = importlib.util.spec_from_file_location(
        "assessment_sufficiency_runner_controller", CONTROLLER
    )
    if spec is None or spec.loader is None:
        raise AssessmentSufficiencyLaunchError(
            "assessment sufficiency controller is unavailable"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _progress(work: Path) -> tuple[int, bool]:
    journal_path = work / "interview.jsonl"
    if not journal_path.exists():
        return 0, False
    try:
        entries = _journal_module()._read_journal(journal_path)
    except Exception as error:
        raise AssessmentSufficiencyLaunchError(
            f"assessment sufficiency journal is invalid: {error}"
        ) from error
    accepted = sum(
        entry.get("event") == "unit_answer_recorded"
        and entry.get("accepted") is True
        for entry in entries
    )
    completed = any(
        entry.get("event") == "assessment_sufficiency_completed"
        for entry in entries
    )
    return accepted, completed


def _prompt(question: dict[str, object]) -> str:
    return (
        "Assess only this one code-bound evidence-sufficiency unit. Return exactly one JSON "
        "object matching the supplied output schema. Choose only sufficient, insufficient, or "
        "cannot-assess. Use only evidence ids listed for the matching obligation. A sufficient "
        "verdict requires selected evidence and null missing_evidence. Every other verdict requires "
        "one concrete missing_evidence string. Do not run commands or edit files.\n\n"
        "Code-bound question:\n"
        + json.dumps(question, indent=2, sort_keys=True)
    )


def _model_client(environ: dict[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    configured = values.get("MK_CLIENT_KIND")
    if configured is not None:
        if configured != "codex":
            raise AssessmentSufficiencyLaunchError(
                "structured assessment sufficiency currently requires MK_CLIENT_KIND=codex"
            )
        return configured
    return "codex"


def _executable(client: str) -> str:
    executable = shutil.which(client)
    if executable is None:
        raise AssessmentSufficiencyLaunchError(
            f"model executable is unavailable for client {client}"
        )
    return executable


def build_structured_codex_argv(
    executable: str,
    work: Path,
    question: dict[str, object],
    schema_path: Path,
    response_path: Path,
) -> list[str]:
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
    payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if path.exists() and path.read_bytes() != payload:
        raise AssessmentSufficiencyLaunchError(
            f"{label} already exists with different bytes"
        )
    if not path.exists():
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
                continue
    attempt = root / f"attempt-{max(numbers, default=0) + 1:06d}"
    attempt.mkdir()
    return attempt


def _write_process_output(path: Path, value: object) -> None:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    elif value is None:
        payload = b""
    else:
        payload = str(value).encode("utf-8")
    path.write_bytes(payload)


def run(
    charter: Path,
    evidence: Path,
    work: Path,
    *,
    max_units: int | None = None,
    model_run_fn: Callable[..., object] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, object]:
    if max_units is not None and (
        not isinstance(max_units, int)
        or isinstance(max_units, bool)
        or max_units < 1
    ):
        raise AssessmentSufficiencyLaunchError(
            "max_units must be one positive integer"
        )
    if not charter.is_file() or not evidence.is_file():
        raise AssessmentSufficiencyLaunchError(
            "assessment charter and evidence artifacts must both exist"
        )
    work.mkdir(parents=True, exist_ok=True)
    before, completed_before = _progress(work)
    if completed_before:
        artifact = work / "sufficiency.json"
        if not artifact.is_file():
            raise AssessmentSufficiencyLaunchError(
                "completed sufficiency journal lost its artifact"
            )
        return {
            "ok": True,
            "status": "already-complete",
            "accepted_unit_count": before,
            "artifact": str(artifact.resolve()),
        }
    client = _model_client(environ)
    executable = _executable(client)
    controller = _controller_module()
    accepted_this_run = 0
    completed_after = False
    while max_units is None or accepted_this_run < max_units:
        try:
            prepared = controller.prepare_question(charter, evidence, work)
        except controller.AssessmentSufficiencyError as error:
            raise AssessmentSufficiencyLaunchError(str(error)) from error
        if prepared["status"] == "complete":
            completed_after = True
            break
        question = prepared["question"]
        schema = prepared["response_schema"]
        unit_id = question["unit"]["unit_id"]
        accepted = False
        for _attempt_number in range(3):
            attempt_dir = _next_attempt_dir(work, unit_id)
            question_path = attempt_dir / "question.json"
            schema_path = attempt_dir / "response-schema.json"
            response_path = attempt_dir / "response.json"
            _write_exact(question_path, question, "model question")
            _write_exact(schema_path, schema, "model response schema")
            argv = build_structured_codex_argv(
                executable, work, question, schema_path, response_path
            )
            completed = (model_run_fn or subprocess.run)(
                argv,
                check=False,
                capture_output=True,
                text=True,
            )
            _write_process_output(attempt_dir / "stdout.txt", getattr(completed, "stdout", None))
            _write_process_output(attempt_dir / "stderr.txt", getattr(completed, "stderr", None))
            returncode = getattr(completed, "returncode", None)
            receipt = {
                "schema_version": 1,
                "unit_id": unit_id,
                "returncode": returncode,
                "question_sha256": hashlib.sha256(question_path.read_bytes()).hexdigest(),
                "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
                "response_exists": response_path.is_file(),
            }
            _write_exact(attempt_dir / "receipt.json", receipt, "model attempt receipt")
            if returncode != 0:
                raise AssessmentSufficiencyLaunchError(
                    f"Codex sufficiency response for {unit_id} exited with {returncode!r}; evidence: {attempt_dir}"
                )
            if not response_path.is_file():
                raise AssessmentSufficiencyLaunchError(
                    f"Codex sufficiency response for {unit_id} is missing; evidence: {attempt_dir}"
                )
            raw = response_path.read_text(encoding="utf-8")
            try:
                submitted = controller.submit_response(
                    charter, evidence, work, raw
                )
            except controller.AssessmentSufficiencyError as error:
                raise AssessmentSufficiencyLaunchError(str(error)) from error
            _write_exact(
                attempt_dir / "submission.json",
                submitted,
                "model submission result",
            )
            if submitted["status"] != "rejected":
                accepted = True
                accepted_this_run += 1
                completed_after = submitted["status"] == "complete"
                break
            prepared = controller.prepare_question(charter, evidence, work)
            question = prepared["question"]
            schema = prepared["response_schema"]
        if not accepted:
            raise AssessmentSufficiencyLaunchError(
                f"Codex produced three rejected responses for {unit_id}"
            )
        if completed_after:
            break
    after, journal_completed = _progress(work)
    completed_after = completed_after or journal_completed
    if after != before + accepted_this_run:
        raise AssessmentSufficiencyLaunchError(
            "journal progress does not equal the accepted structured responses"
        )
    artifact = work / "sufficiency.json"
    if completed_after and not artifact.is_file():
        raise AssessmentSufficiencyLaunchError(
            "model run completed without the sufficiency artifact"
        )
    return {
        "ok": True,
        "status": "complete" if completed_after else "paused",
        "model_client": client,
        "accepted_before": before,
        "accepted_after": after,
        "accepted_this_run": after - before,
        "artifact": str(artifact.resolve()) if completed_after else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--charter", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--max-units", type=int)
    args = parser.parse_args()
    try:
        result = run(
            args.charter, args.evidence, args.work, max_units=args.max_units
        )
    except AssessmentSufficiencyLaunchError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
