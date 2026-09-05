#!/usr/bin/env python3
"""Measure one Atom 19 candidate critique machinery against one frozen real case.

A case names frozen compact copies (matrix, unit manifest, owner queue and rulings, sources) of real
critique runs — the five completed B Team S12 roadmap critiques (pages v1, v2, v3, v5, v6), the
partial version 7 run, the partial version 6 consistency-only run, and a Strategy One-Pager run —
plus the declared expectation. The candidate is driven through its own command line: `trend` with
every run the case lists, in the order the case lists them, and `report` on each comparable run to
cross-check the count against the route the machinery already trusts.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

WORKTREE = Path("/Users/kamenkamenov/.codex/worktrees/critique-machinery-publish-20260903")


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


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", ""), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(argv, cwd=WORKTREE, capture_output=True, text=True, env=env)


def main() -> int:
    frozen_input, result_path, telemetry_path = map(Path, sys.argv[1:4])
    tree = Path(__file__).resolve().parent
    script = tree / "skills/critique-machinery/scripts/critique.py"
    before = hashlib.sha256(frozen_input.read_bytes()).hexdigest()
    case = json.loads(frozen_input.read_text())
    expect = case["expect"]
    variant = os.environ.get("EXPERIMENT_VARIANT_ID", "control")
    works = [str(WORKTREE / work) for work in case["works"]]
    argv = [sys.executable, str(script), "trend"]
    for work in works:
        argv += ["--work", work]
    trend = run(argv)
    payload = {}
    if trend.returncode == 0:
        try:
            payload = json.loads(trend.stdout)
        except ValueError:
            payload = {}
    runs = payload.get("runs", []) if isinstance(payload, dict) else []
    metrics = {}
    metrics["exit-correct"] = int(trend.returncode == expect["exit"])
    if expect["exit"] == 0:
        metrics["order-correct"] = int([entry.get("version") for entry in runs] == expect["versions"])
        metrics["counts-correct"] = int([entry.get("located_defects") for entry in runs] == expect["located"])
        cross = []
        for entry in runs:
            if entry.get("comparable"):
                report = run([sys.executable, str(script), "report", "--work", entry["work"]])
                try:
                    cross.append(json.loads(report.stdout).get("located_defects") == entry.get("located_defects"))
                except ValueError:
                    cross.append(False)
        metrics["counts-match-report-route"] = int(bool(cross) and all(cross))
        metrics["deltas-correct"] = int(payload.get("deltas") == expect["deltas"] and payload.get("direction") == expect["direction"])
        metrics["comparability-correct"] = int(
            [entry.get("comparable") for entry in runs] == expect["comparable"]
            and [entry.get("not_comparable_because") for entry in runs] == expect["not_comparable_because"]
            and payload.get("deliverable") == expect["deliverable"]
        )
        metrics["refusal-names-items"] = int(trend.returncode == 0 and trend.stderr == "")
    else:
        refused = trend.returncode == 2 and trend.stdout == ""
        metrics["order-correct"] = int(refused)
        metrics["counts-correct"] = int(refused)
        metrics["counts-match-report-route"] = int(refused)
        metrics["deltas-correct"] = int(refused)
        metrics["comparability-correct"] = int(refused)
        metrics["refusal-names-items"] = int(refused and all(name in trend.stderr for name in expect["refusal_names"]))
    metrics["frozen-input-unchanged"] = int(hashlib.sha256(frozen_input.read_bytes()).hexdigest() == before)
    outcome = {
        "case_id": case["case_id"], "case_sha256": before, "trend_exit": trend.returncode,
        "trend_stderr": trend.stderr.strip()[:400],
        "versions": [entry.get("version") for entry in runs], "located": [entry.get("located_defects") for entry in runs],
        "deltas": payload.get("deltas") if isinstance(payload, dict) else None,
        "direction": payload.get("direction") if isinstance(payload, dict) else None,
        "metrics": dict(metrics),
    }
    emit(telemetry_path, "work_completed", f"drove the candidate critique machinery on case {case['case_id']}",
         json.dumps(outcome, sort_keys=True).encode(), **metrics)
    emit(telemetry_path, "decision_recorded", "metrics recorded against the declared expectation",
         json.dumps(metrics, sort_keys=True).encode(), case_id=case["case_id"])
    result_path.write_text(json.dumps({"schema_version": 1, "variant_id": variant, "status": "completed",
                                       "outcome": outcome, "metrics": metrics, "error": None}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
