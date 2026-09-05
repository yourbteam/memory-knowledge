#!/usr/bin/env python3
"""Measure one Atom 18 candidate critique machinery against one frozen real case.

A case is a real delivered page and the real run state that produced it (B Team version 6, Vivacom
version 6, B Team version 5 rendered from its state) plus the declared expectation. The candidate
is driven through its own command line: `open` (derived or explicit, as the case says), then
`consistency`, then `located --only defects`; the matrix it wrote is read back.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORKTREE = Path("/Users/kamenkamenov/.codex/worktrees/critique-machinery-publish-20260903")
PROBE_WORK = WORKTREE / "Tasks/critique-machinery/atom-18/probe-work"
NO_REFERENCE = "UP supplies no roadmap-shaped benchmark"
NO_UPSTREAM = "the explicit-mode case declares no producer material"


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
    work = PROBE_WORK / variant / case["case_id"]
    shutil.rmtree(work, ignore_errors=True)
    page = WORKTREE / case["page"]
    state = WORKTREE / case["state"]
    if case["mode"] == "derived":
        opened = run([sys.executable, str(script), "open", "--page", str(page), "--from-run", str(state),
                      "--deliverable", case["deliverable"], "--work", str(work), "--no-reference", NO_REFERENCE])
    else:
        opened = run([sys.executable, str(script), "open", "--page", str(page), "--payload", f"{state}#{case['payload_key']}",
                      "--work", str(work), "--no-reference", NO_REFERENCE, "--no-upstream", NO_UPSTREAM])
    consistency = run([sys.executable, str(script), "consistency", "--work", str(work)])
    located = run([sys.executable, str(script), "located", "--work", str(work), "--only", "defects"])
    matrix = json.loads((work / "matrix.json").read_text()) if (work / "matrix.json").is_file() else {"cells": []}
    manifest = json.loads((work / "unit-manifest.json").read_text()) if (work / "unit-manifest.json").is_file() else {"units": []}
    labels = {unit["unit_id"]: unit["label"] for unit in manifest.get("units", [])}
    code_cells = [cell for cell in matrix.get("cells", []) if cell.get("lens") == "payload-consistency"]
    by_label = {labels.get(cell["unit_id"]): cell for cell in code_cells}
    checked_labels = {"The activation map", "The proof-building order", "The twelve-month calendar", "The always-on loop", "The rollout"}

    metrics = {}
    map_cell = by_label.get("The activation map")
    if expect.get("all_lens_cells_not_applicable"):
        metrics["map-cell-correct"] = int(bool(code_cells) and all(c.get("status") == "not-applicable" for c in code_cells))
    else:
        metrics["map-cell-correct"] = int(map_cell is not None and map_cell.get("outcome") == expect["map_cell"])
    defects = sorted(f["subject"] for f in (map_cell or {}).get("consistency_facts", []) if f.get("verdict") == "defect")
    metrics["defect-subjects-correct"] = int(bool(code_cells) and defects == sorted(expect.get("map_defect_cards", [])))
    clear_units = expect.get("clear_units", [])
    metrics["clear-units-correct"] = int(bool(code_cells) and all(by_label.get(label, {}).get("outcome") == "agreement-clear" for label in clear_units))
    reason = expect.get("not_applicable_reason")
    if expect.get("all_lens_cells_not_applicable"):
        na_ok = bool(code_cells) and all(c.get("status") == "not-applicable" and (c.get("consistency_state") or {}).get("state") == reason for c in code_cells)
    else:
        others = [c for label, c in by_label.items() if label not in checked_labels]
        na_ok = bool(others) and all(c.get("status") == "not-applicable" and (c.get("consistency_state") or {}).get("state") == reason for c in others)
    metrics["not-applicable-correct"] = int(na_ok)
    queue = run([sys.executable, str(script), "ask-owner", "--work", str(work)])
    open_count = None
    try:
        open_count = json.loads(queue.stdout).get("open_count")
    except ValueError:
        pass
    metrics["no-owner-question"] = int(open_count == expect.get("owner_queue_from_lens", 0) and bool(code_cells))
    if expect.get("located_names_first_defect_row"):
        metrics["located-correct"] = int(located.returncode == 0 and "payload-consistency" in located.stdout and "| Senior craft story series |" in located.stdout)
    else:
        metrics["located-correct"] = int(located.returncode == 0 and "payload-consistency" not in located.stdout)
    metrics["frozen-input-unchanged"] = int(hashlib.sha256(frozen_input.read_bytes()).hexdigest() == before)
    outcome = {
        "case_id": case["case_id"], "case_sha256": before, "open_exit": opened.returncode, "open_stderr": opened.stderr.strip()[:300],
        "consistency_exit": consistency.returncode, "consistency_stdout": consistency.stdout.strip()[:400], "consistency_stderr": consistency.stderr.strip()[:300],
        "code_cells": len(code_cells), "map_outcome": (map_cell or {}).get("outcome"), "defect_subjects": defects,
        "owner_open_count": open_count, "located_head": located.stdout[:300], "metrics": dict(metrics),
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
