#!/usr/bin/env python3
"""Replay real Atom 7 seat evidence through Atom 8's no-reference public operator path."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
ATOM = Path(__file__).resolve().parent
SOURCE = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap"
LIVE = ROOT / "Tasks/critique-machinery/atom-07/live-probe"
OUT = ATOM / "operator-validation"
WORK = OUT / "run"
REASON = "UP supplies no roadmap-shaped benchmark"


def call(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["python3", str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)
    if ok and result.returncode != 0:
        raise SystemExit(result.stderr)
    if not ok and result.returncode == 0:
        raise SystemExit(f"expected refusal: {args}")
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if OUT.exists():
    raise SystemExit(f"refusing to replace existing operator evidence: {OUT}")
OUT.mkdir(parents=True)

red_before = {
    "matrix_sha256": digest(ATOM / "frozen-red/matrix.json"),
    "unit_manifest_sha256": digest(ATOM / "frozen-red/unit-manifest.json"),
    "read_run_log_sha256": digest(ATOM / "frozen-red/read-run.log"),
}

opened = json.loads(call(
    "open", "--page", str(SOURCE / "page.md"),
    "--payload", f"{SOURCE / 'state.json'}#context.up.cd_s_002.tactical_roadmap",
    "--work", str(WORK), "--no-reference", REASON,
).stdout)
opening_status = json.loads(call("status", "--work", str(WORK)).stdout)
if opening_status["benchmark_no_reference_count"] != 25 or opening_status["unjudged_count"] != 150:
    raise SystemExit(f"unexpected opening state: {opening_status}")

live_matrix = json.loads((LIVE / "matrix.json").read_text())
submitted_cells = []
for cell in live_matrix["cells"]:
    if cell["lens"] == "benchmark-vs-reference":
        continue
    submitted_cells.append(cell["cell_id"])
    for seat in ("reader-1", "reader-2"):
        reader = cell["readers"][seat]
        call(
            "judge", "--work", str(WORK), "--id", cell["cell_id"], "--seat", seat,
            "--verdict", reader["verdict"], "--quote", reader["quote"],
        )

rulings = json.loads((LIVE / "owner-rulings.json").read_text())["rulings"]
by_cell = {ruling["cell_id"]: ruling for ruling in rulings}
used_rulings = []
while True:
    queue = json.loads(call("ask-owner", "--work", str(WORK)).stdout)
    if queue["status"] == "empty":
        break
    question = queue["question"]
    ruling = by_cell[question["cell_id"]]
    used_rulings.append(ruling)
    call(
        "answer-owner", "--work", str(WORK), "--id", question["decision_id"],
        "--choice", ruling["choice"], "--because", ruling["because"],
    )

benchmark_cell = next(
    cell for cell in json.loads((WORK / "matrix.json").read_text())["cells"]
    if cell["lens"] == "benchmark-vs-reference"
)
read_cell = json.loads(call("read-cell", "--work", str(WORK), "--id", benchmark_cell["cell_id"]).stdout)
benchmark_refusal = call(
    "judge", "--work", str(WORK), "--id", benchmark_cell["cell_id"],
    "--seat", "reader-1", "--verdict", "clear", "--quote", "unused",
    ok=False,
).stderr.strip()

document_path = OUT / "located-defects.md"
document = json.loads(call("document", "--work", str(WORK), "--out", str(document_path)).stdout)
final_status = json.loads(call("status", "--work", str(WORK)).stdout)
document_text = document_path.read_text()
source_text = SCRIPT.read_text()
red_after = {
    "matrix_sha256": digest(ATOM / "frozen-red/matrix.json"),
    "unit_manifest_sha256": digest(ATOM / "frozen-red/unit-manifest.json"),
    "read_run_log_sha256": digest(ATOM / "frozen-red/read-run.log"),
}

checks = {
    "all_175_cells_visible": final_status["cell_count"] == 175,
    "all_150_applicable_cells_judged": final_status["judged_count"] == 150,
    "all_25_benchmark_cells_not_applicable": final_status["benchmark_no_reference_count"] == 25,
    "benchmark_reason_visible_in_status": final_status["benchmark_no_reference_reason"] == REASON,
    "benchmark_reason_visible_in_document": f"Not applicable — {REASON}" in document_text,
    "benchmark_cells_never_submitted": len(submitted_cells) == 150 and all(
        "::benchmark-vs-reference" not in cell_id for cell_id in submitted_cells
    ),
    "explicit_read_cell_launches_no_reader": read_cell["status"] == "not-applicable" and not (WORK / "reader-evidence").exists(),
    "direct_benchmark_judgment_refuses": "No reader judgment can be recorded" in benchmark_refusal,
    "no_prompt_instruction_to_clear_benchmark": "For benchmark-vs-reference and upstream-trace, return clear" not in source_text,
    "run_completed_past_unit_one": any(not cell_id.startswith("u-001-") for cell_id in submitted_cells),
    "frozen_red_unchanged": red_before == red_after,
}
if not all(checks.values()) or final_status["status"] != "complete":
    raise SystemExit(json.dumps({"checks": checks, "status": final_status}, sort_keys=True))

summary = {
    "status": "passed",
    "source_page_sha256": digest(SOURCE / "page.md"),
    "source_state_sha256": digest(SOURCE / "state.json"),
    "opening": opened,
    "opening_status": opening_status,
    "final_status": final_status,
    "submitted_nonbenchmark_cell_count": len(submitted_cells),
    "replayed_real_reader_records": len(submitted_cells) * 2,
    "owner_rulings_replayed": len(used_rulings),
    "model_calls": 0,
    "checks": checks,
    "document": document,
    "benchmark_judgment_refusal": benchmark_refusal,
    "red_evidence": red_after,
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": "passed", "cells": 175, "judged": 150, "not_applicable": 25}, sort_keys=True))
