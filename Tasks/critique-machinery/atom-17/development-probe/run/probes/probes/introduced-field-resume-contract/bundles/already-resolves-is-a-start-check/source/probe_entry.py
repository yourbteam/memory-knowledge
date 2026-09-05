#!/usr/bin/env python3
"""Measure one Atom 17 candidate controller against one frozen real case (start cases as Atom 16; a load case runs
`status` on a byte copy of a real started run whose introduced field has since landed in the canonical module).

The case is a real atom request (the round-5 request refused at start on 2026-09-05, the real
misspelled request from Atom 13, the real structured-KPI request) plus the declared expectation.
The candidate controller is run through its real `start` command against the real United Partners
repository the request targets; the promotion-time gate is exercised through the same module's
request validation at the record-promotion stage.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPOSITORY = Path("/Users/kamenkamenov/united-partners")


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


def main() -> int:
    frozen_input, result_path, telemetry_path = map(Path, sys.argv[1:4])
    tree = Path(__file__).resolve().parent
    controller = tree / "skills/atom-building-machinery/scripts/atom_controller.py"
    before = hashlib.sha256(frozen_input.read_bytes()).hexdigest()
    case = json.loads(frozen_input.read_text())
    expect = case["expect"]
    work = Path(tempfile.mkdtemp(prefix="atom17-probe-", dir=str(result_path.parent)))
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", ""), "PYTHONDONTWRITEBYTECODE": "1"}
    metrics = {"start-verdict-correct": 1, "refusal-actionable": 1, "promotion-gate-correct": 1, "load-verdict-correct": 1}
    outcome = {"case_id": case["case_id"], "case_sha256": before}
    if case.get("kind") == "load":
        run = work / "run"
        shutil.copytree(case["run_copy"], run)
        loaded = subprocess.run([sys.executable, str(controller), "status", str(run)], cwd=REPOSITORY, capture_output=True, text=True, env=env)
        verdict = "loads" if loaded.returncode == 0 else "refused"
        stage = None
        if verdict == "loads":
            try:
                stage = json.loads(loaded.stdout).get("stage")
            except ValueError:
                stage = None
        metrics["load-verdict-correct"] = int(verdict == expect["load"] and (verdict != "loads" or stage == expect.get("stage")))
        outcome.update({"load_verdict": verdict, "stage": stage, "load_stderr": loaded.stderr.strip()[:600]})
    else:
        request = case["request"]
        request_path = work / "atom-request.json"
        request_path.write_text(json.dumps(request, indent=1))
        started = subprocess.run([sys.executable, str(controller), "start", str(request_path), str(work / "run")], cwd=REPOSITORY, capture_output=True, text=True, env=env)
        start_verdict = "started" if started.returncode == 0 else "refused"
        refusal = started.stderr.strip()
        metrics["start-verdict-correct"] = int(start_verdict == expect["start"])
        if expect["start"] == "refused":
            metrics["refusal-actionable"] = int(start_verdict == "refused" and all(s in refusal for s in expect.get("refusal_contains", [])))
        else:
            metrics["refusal-actionable"] = int(start_verdict == "started")
        spec = importlib.util.spec_from_file_location("atom17_candidate_controller", controller)
        module = importlib.util.module_from_spec(spec)
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        promotion_expect = expect.get("promotion", "not-applicable")
        promotion_observed = "not-applicable"
        promotion_message = ""
        if promotion_expect != "not-applicable":
            try:
                module._validate_request(request, repository_root=REPOSITORY, stage="record-promotion", require_introduced_resolved=True)
                promotion_observed = "resolves"
            except module.AtomError as error:  # type: ignore[attr-defined]
                promotion_message = str(error)
                field = request["contract_surface"]["fields"][0]["field"]
                promotion_observed = "refused-naming-field" if field in promotion_message else "refused-unnamed"
        metrics["promotion-gate-correct"] = int(promotion_observed == promotion_expect)
        outcome.update({"start_verdict": start_verdict, "start_refusal": refusal[:600], "promotion_observed": promotion_observed, "promotion_message": promotion_message[:600]})
    metrics["frozen-input-unchanged"] = int(hashlib.sha256(frozen_input.read_bytes()).hexdigest() == before)
    outcome["metrics"] = dict(metrics)
    emit(telemetry_path, "work_completed", f"exercised the candidate controller on case {case['case_id']}", json.dumps(outcome, sort_keys=True).encode(), **metrics)
    emit(telemetry_path, "decision_recorded", "metrics recorded against the declared expectation", json.dumps(metrics, sort_keys=True).encode(), case_id=case["case_id"])
    result_path.write_text(json.dumps({"schema_version": 1, "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID", "control"), "status": "completed", "outcome": outcome, "metrics": metrics, "error": None}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
