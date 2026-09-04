#!/usr/bin/env python3
"""Replay Atom 7's real BTM reader evidence through the public CLI."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
ATOM = Path(__file__).resolve().parent
SOURCE = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap"
LIVE = ATOM / "live-probe"
OUT = ATOM / "operator-validation"
WORK = OUT / "run"


def call(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["python3", str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)
    if ok and result.returncode != 0:
        raise SystemExit(result.stderr)
    if not ok and result.returncode == 0:
        raise SystemExit(f"expected refusal: {args}")
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


OUT.mkdir(parents=True, exist_ok=True)
call(
    "open", "--page", str(SOURCE / "page.md"),
    "--payload", f"{SOURCE / 'state.json'}#context.up.cd_s_002.tactical_roadmap",
    "--work", str(WORK),
)
live_matrix = json.loads((LIVE / "matrix.json").read_text())
for cell in live_matrix["cells"]:
    for seat in ("reader-1", "reader-2"):
        reader = cell["readers"][seat]
        call(
            "judge", "--work", str(WORK), "--id", cell["cell_id"], "--seat", seat,
            "--verdict", reader["verdict"], "--quote", reader["quote"],
        )

before_status = json.loads(call("status", "--work", str(WORK)).stdout)
before_queue = json.loads(call("ask-owner", "--work", str(WORK)).stdout)
blocked = call("document", "--work", str(WORK), ok=False)
open_evidence = {
    "case_id": "btm-roadmap-open-queue",
    "status": "satisfied",
    "matrix_status": before_status,
    "owner_queue_count": before_queue["open_count"],
    "first_question": before_queue["question"],
    "document_refusal": blocked.stderr.strip(),
    "matrix_sha256": digest(WORK / "matrix.json"),
}
(OUT / "open-queue.json").write_text(json.dumps(open_evidence, indent=2, sort_keys=True) + "\n")

rulings = json.loads((LIVE / "owner-rulings.json").read_text())["rulings"]
by_cell = {ruling["cell_id"]: ruling for ruling in rulings}
while True:
    queue = json.loads(call("ask-owner", "--work", str(WORK)).stdout)
    if queue["status"] == "empty":
        break
    ruling = by_cell[queue["question"]["cell_id"]]
    call(
        "answer-owner", "--work", str(WORK), "--id", queue["question"]["decision_id"],
        "--choice", ruling["choice"], "--because", ruling["because"],
    )

document_path = OUT / "located-defects.md"
document = json.loads(call("document", "--work", str(WORK), "--out", str(document_path)).stdout)
after_status = json.loads(call("status", "--work", str(WORK)).stdout)
resolved_evidence = {
    "case_id": "btm-roadmap-resolved-queue",
    "status": "satisfied",
    "matrix_status": after_status,
    "owner_rulings": rulings,
    "document": document,
    "matrix_sha256": digest(WORK / "matrix.json"),
    "owner_rulings_sha256": digest(WORK / "owner-rulings.json"),
}
(OUT / "resolved-queue.json").write_text(json.dumps(resolved_evidence, indent=2, sort_keys=True) + "\n")
(OUT / "summary.json").write_text(json.dumps({
    "status": "passed",
    "cases": [open_evidence, resolved_evidence],
    "real_reader_source": str((LIVE / "reader-evidence").relative_to(ROOT)),
}, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": "passed", "cells": after_status["cell_count"], "owner_rulings": len(rulings)}, sort_keys=True))
