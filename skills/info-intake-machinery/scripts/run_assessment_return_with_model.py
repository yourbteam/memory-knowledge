#!/usr/bin/env python3
"""Drive returned-source gap assessment through one code-controlled model answer at a time."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONTROLLER = SCRIPT_DIR / "assessment_return.py"


class AssessmentReturnLaunchError(RuntimeError):
    """The model did not advance the exact returned-evidence question."""


def _controller():
    spec = importlib.util.spec_from_file_location("assessment_return_model_controller", CONTROLLER)
    if spec is None or spec.loader is None:
        raise AssessmentReturnLaunchError("assessment return controller is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _prompt(question: dict[str, object]) -> str:
    return (
        "Assess only the one returned-evidence gap in this code-bound question. Inspect only the "
        "immutable projection files listed in obligations[].evidence[].path. Choose exactly one "
        "of sufficient, insufficient, or cannot-assess. A sufficient answer must cite at least "
        "one listed evidence_id and use null missing_evidence. Otherwise state the concrete evidence "
        "still missing. Return exactly one JSON object matching the supplied schema. Do not edit files.\n\n"
        + json.dumps(question, indent=2, sort_keys=True)
    )


def build_argv(executable: str, work: Path, question: dict[str, object], schema: Path, response: Path) -> list[str]:
    return [
        executable, "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
        "--sandbox", "read-only", "--cd", str(work.resolve()), "--output-schema", str(schema),
        "--output-last-message", str(response), "--color", "never", "--", _prompt(question),
    ]


def _write_exact(path: Path, value: object) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    if path.exists() and path.read_bytes() != payload:
        raise AssessmentReturnLaunchError(f"{path.name} already exists with different bytes")
    if not path.exists():
        path.write_bytes(payload)


def _attempt(work: Path, gap_id: str) -> Path:
    root = work / "model-runs" / gap_id
    root.mkdir(parents=True, exist_ok=True)
    numbers = [int(path.name.removeprefix("attempt-")) for path in root.glob("attempt-*") if path.name.removeprefix("attempt-").isdigit()]
    path = root / f"attempt-{max(numbers, default=0) + 1:06d}"
    path.mkdir()
    return path


def run(
    work: Path,
    *,
    max_gaps: int | None = None,
    model_run_fn: Callable[..., object] | None = None,
) -> dict[str, object]:
    if max_gaps is not None and (not isinstance(max_gaps, int) or isinstance(max_gaps, bool) or max_gaps < 1):
        raise AssessmentReturnLaunchError("max_gaps must be one positive integer")
    executable = shutil.which("codex")
    if executable is None:
        raise AssessmentReturnLaunchError("codex model executable is unavailable")
    controller = _controller()
    accepted = 0
    while max_gaps is None or accepted < max_gaps:
        try:
            prepared = controller.prepare_gap_question(work)
        except controller.AssessmentReturnError as error:
            raise AssessmentReturnLaunchError(str(error)) from error
        if prepared["status"] == "complete":
            return {"ok": True, "status": "complete", "accepted_this_run": accepted, "artifact": prepared["artifact"]}
        question = prepared["question"]
        gap_id = question["unit"]["unit_id"]
        attempt = _attempt(work, gap_id)
        question_path = attempt / "question.json"
        schema_path = attempt / "response-schema.json"
        response_path = attempt / "response.json"
        _write_exact(question_path, question)
        _write_exact(schema_path, prepared["response_schema"])
        completed = (model_run_fn or subprocess.run)(
            build_argv(executable, work, question, schema_path, response_path),
            check=False, capture_output=True, text=True,
        )
        (attempt / "stdout.txt").write_text(str(getattr(completed, "stdout", "") or ""))
        (attempt / "stderr.txt").write_text(str(getattr(completed, "stderr", "") or ""))
        receipt = {
            "schema_version": 1,
            "gap_id": gap_id,
            "returncode": getattr(completed, "returncode", None),
            "question_sha256": hashlib.sha256(question_path.read_bytes()).hexdigest(),
            "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
            "response_exists": response_path.is_file(),
        }
        _write_exact(attempt / "receipt.json", receipt)
        if receipt["returncode"] != 0 or not response_path.is_file():
            raise AssessmentReturnLaunchError(f"Codex return-gap response failed for {gap_id}; evidence: {attempt}")
        submitted = controller.submit_gap_response(work, response_path.read_text())
        _write_exact(attempt / "submission.json", submitted)
        if submitted["status"] == "rejected":
            raise AssessmentReturnLaunchError(f"Codex return-gap response was rejected for {gap_id}: {submitted['error']}")
        accepted += 1
        if submitted["status"] == "complete":
            return {"ok": True, "status": "complete", "accepted_this_run": accepted, "artifact": submitted["artifact"]}
    return {"ok": True, "status": "paused", "accepted_this_run": accepted, "artifact": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--max-gaps", type=int)
    args = parser.parse_args()
    try:
        result = run(args.work, max_gaps=args.max_gaps)
    except AssessmentReturnLaunchError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
