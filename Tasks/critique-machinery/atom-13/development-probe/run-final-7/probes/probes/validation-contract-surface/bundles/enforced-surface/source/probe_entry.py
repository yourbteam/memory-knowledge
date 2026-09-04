#!/usr/bin/env python3
"""Measure one Atom C candidate against one frozen declared request."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def emit(path: Path, event: str, message: str, evidence: bytes, **observations: object) -> None:
    record = {
        "schema_version": 1,
        "sequence": emit.sequence,
        "event": event,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID", "control"),
        "message": message,
        "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        "observations": observations,
    }
    emit.sequence += 1
    with path.open("a") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


emit.sequence = int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1"))


def invoke(controller: Path, repository: Path, request: Path, run: Path, interview: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(controller), "start", str(request), str(run)]
    if interview is not None:
        command.extend(["--prose-waiver-interview", str(interview)])
    return subprocess.run(command, cwd=repository, text=True, capture_output=True, check=False)


def main() -> int:
    frozen_input, result_path, telemetry_path = map(Path, sys.argv[1:4])
    tree = Path(__file__).resolve().parent
    variant = os.environ.get("EXPERIMENT_VARIANT_ID", "control")
    controller = tree / "skills/atom-building-machinery/scripts/atom_controller.py"
    context = json.loads((tree / "operator-context.json").read_text())
    repository = Path(context["repository_root"])
    request = json.loads(frozen_input.read_text())
    before = hashlib.sha256(frozen_input.read_bytes()).hexdigest()
    surface = request["contract_surface"]
    prose_fields = [item["field"] for item in surface.get("fields", []) if item["shape"] == "prose"]
    workspace = Path(tempfile.mkdtemp(prefix="atom-c-probe-"))
    direct = invoke(controller, repository, frozen_input, workspace / "direct")
    accepted_run = workspace / "direct"
    waiver_result = None
    wrong_result = None
    if prose_fields:
        waiver_name = "proof-order" if prose_fields == ["proof_building_order"] else "countable-kpis"
        wrong_name = "countable-kpis" if waiver_name == "proof-order" else "proof-order"
        waiver_result = invoke(controller, repository, frozen_input, workspace / "waived", tree / "owner-evidence" / waiver_name)
        wrong_result = invoke(controller, repository, frozen_input, workspace / "wrong-waiver", tree / "owner-evidence" / wrong_name)
        accepted_run = workspace / "waived"

    expected_direct = direct.returncode == (2 if prose_fields else 0)
    refusal = direct.stderr
    actionable = not prose_fields or (
        all(field in refusal for field in prose_fields)
        and "structured field" in refusal
        and "prose-waiver-interview" in refusal
    )
    waiver_bound = not prose_fields or (
        waiver_result is not None and waiver_result.returncode == 0
        and wrong_result is not None and wrong_result.returncode == 2
    )
    visible = False
    if accepted_run.is_dir():
        status = subprocess.run(
            [sys.executable, str(controller), "status", str(accepted_run)],
            cwd=repository,
            text=True,
            capture_output=True,
            check=False,
        )
        if status.returncode == 0:
            visible = json.loads(status.stdout).get("contract_surface") == surface
    metrics = {
        "direct-contract-correct": int(expected_direct),
        "refusal-actionable": int(actionable),
        "owner-waiver-request-bound": int(waiver_bound),
        "contract-surface-visible": int(visible),
        "frozen-input-unchanged": int(hashlib.sha256(frozen_input.read_bytes()).hexdigest() == before),
    }
    outcome = {
        "direct_returncode": direct.returncode,
        "direct_stderr": direct.stderr[:500],
        "prose_fields": prose_fields,
        "waived_returncode": None if waiver_result is None else waiver_result.returncode,
        "wrong_waiver_returncode": None if wrong_result is None else wrong_result.returncode,
    }
    evidence = json.dumps(outcome, sort_keys=True).encode()
    emit(telemetry_path, "work_completed", "measured Atom C start contract", evidence, **metrics)
    emit(telemetry_path, "decision_recorded", "recorded candidate metrics", json.dumps(metrics, sort_keys=True).encode(), **metrics)
    Path(result_path).write_text(json.dumps({
        "schema_version": 1,
        "variant_id": variant,
        "status": "completed",
        "outcome": outcome,
        "metrics": metrics,
        "error": None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
