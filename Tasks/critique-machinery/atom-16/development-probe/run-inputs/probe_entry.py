#!/usr/bin/env python3
"""Measure one Atom 16 candidate controller against one frozen real case.

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
    request = case["request"]
    expect = case["expect"]
    work = Path(tempfile.mkdtemp(prefix="atom16-probe-", dir=str(result_path.parent)))
    request_path = work / "atom-request.json"
    request_path.write_text(json.dumps(request, indent=1))
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", ""), "PYTHONDONTWRITEBYTECODE": "1"}
    started = subprocess.run(
        [sys.executable, str(controller), "start", str(request_path), str(work / "run")],
        cwd=REPOSITORY, capture_output=True, text=True, env=env,
    )
    start_verdict = "started" if started.returncode == 0 else "refused"
    refusal = started.stderr.strip()
    start_correct = int(start_verdict == expect["start"])
    if expect["start"] == "refused":
        refusal_actionable = int(start_verdict == "refused" and all(s in refusal for s in expect.get("refusal_contains", [])))
    else:
        refusal_actionable = int(start_verdict == "started")
    # promotion-time gate through the candidate module's own request validation
    spec = importlib.util.spec_from_file_location("atom16_candidate_controller", controller)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    promotion_expect = expect.get("promotion", "not-applicable")
    promotion_observed = "not-applicable"
    promotion_message = ""
    if promotion_expect != "not-applicable":
        kwargs = {"repository_root": REPOSITORY, "stage": "record-promotion"}
        try:
            if "require_introduced_resolved" in module._validate_request.__code__.co_varnames:
                kwargs["require_introduced_resolved"] = True
            module._validate_request(request, **kwargs)
            promotion_observed = "resolves"
        except module.AtomError as error:  # type: ignore[attr-defined]
            promotion_message = str(error)
            field = request["contract_surface"]["fields"][0]["field"]
            promotion_observed = "refused-naming-field" if field in promotion_message else "refused-unnamed"
    promotion_correct = int(promotion_observed == promotion_expect)
    metrics = {
        "start-verdict-correct": start_correct,
        "refusal-actionable": refusal_actionable,
        "promotion-gate-correct": promotion_correct,
        "frozen-input-unchanged": int(hashlib.sha256(frozen_input.read_bytes()).hexdigest() == before),
    }
    outcome = {
        "case_id": case["case_id"], "case_sha256": before, "start_verdict": start_verdict,
        "start_refusal": refusal[:600], "promotion_observed": promotion_observed,
        "promotion_message": promotion_message[:600], "metrics": metrics,
    }
    evidence = json.dumps(outcome, sort_keys=True).encode()
    emit(telemetry_path, "work_completed", f"ran candidate start on {case['case_id']}", evidence, **metrics)
    emit(telemetry_path, "decision_recorded", "recorded Atom 16 candidate metrics", evidence, **metrics)
    result_path.write_text(json.dumps({
        "schema_version": 1,
        "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID", "control"),
        "status": "completed",
        "outcome": outcome,
        "metrics": metrics,
        "error": None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
