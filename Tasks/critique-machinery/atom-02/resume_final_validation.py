#!/usr/bin/env python3
"""Resume only Atom 2 final validation after an assessment-adapter correction."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
SOURCE = ATOM / "run-04"
OUTPUT = ATOM / "run-04-finalized"
RUNNER_PATH = ROOT / "skills/experiment-machinery/scripts/development_probe_run.py"


def load_runner():
    sys.path.insert(0, str(RUNNER_PATH.parent))
    spec = importlib.util.spec_from_file_location("development_probe_run", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit(f"refusing to replace existing {OUTPUT}")
    runner = load_runner()
    OUTPUT.mkdir(parents=True)
    for name in ("development-probe-request.json",):
        shutil.copy2(SOURCE / name, OUTPUT / name)
    shutil.copytree(SOURCE / "probes", OUTPUT / "probes")
    shutil.copytree(SOURCE / "composition", OUTPUT / "composition")
    for stage in ("run-probes", "compose-winners"):
        target = OUTPUT / "stage-receipts" / stage
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SOURCE / "stage-receipts" / stage, target)
    normalized = json.loads((SOURCE / "development-probe-request.json").read_text(encoding="utf-8"))
    final_request = json.loads((SOURCE / "stage-requests/final-validation.json").read_text(encoding="utf-8"))
    final_request["assembly"] = str(OUTPUT / "composition/assembly")
    request_path = OUTPUT / "stage-requests/final-validation.json"
    runner._write_json(request_path, final_request)
    telemetry_path = OUTPUT / "telemetry.jsonl"
    identity = {
        "atomic_step_id": normalized["atomic_step_id"],
        "probe_id": None,
        "case_id": None,
        "approach_id": None,
        "variant_id": None,
    }
    child_environment = os.environ.copy()
    child_environment["DEVELOPMENT_PROBE_TELEMETRY_PATH"] = str(telemetry_path)
    child_environment["DEVELOPMENT_PROBE_ATOMIC_STEP_ID"] = normalized["atomic_step_id"]
    final_receipt = runner._run_stage(
        OUTPUT,
        "final-validation",
        [
            sys.executable,
            str(ROOT / "skills/experiment-machinery/scripts/development_probe_final_validation.py"),
            "run",
            str(request_path),
            str(OUTPUT / "validation"),
        ],
        timeout_ms=2_700_000,
        telemetry_path=telemetry_path,
        telemetry_identity=identity,
        child_environment=child_environment,
    )
    verdict = runner._bind_final_result(OUTPUT, normalized, final_receipt)
    runner._write_json(
        OUTPUT / "development-probe-summary.json",
        {
            "schema_version": 1,
            "status": "completed",
            "atomic_step_id": normalized["atomic_step_id"],
            "verdict": verdict["verdict"],
            "final_verdict_sha256": final_receipt["result_sha256"],
            "stages": runner._receipts(OUTPUT),
            "promotion_applied": False,
        },
    )
    print(json.dumps({"status": "completed", "verdict": verdict["verdict"], "output": str(OUTPUT)}))


if __name__ == "__main__":
    main()
