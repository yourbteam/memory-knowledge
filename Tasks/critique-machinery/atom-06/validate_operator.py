#!/usr/bin/env python3
"""Exercise Atom 6 through the public critique CLI on both frozen calendar cases."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
ATOM = Path(__file__).resolve().parent
CASES = ROOT / "Tasks/critique-machinery/atom-03/cases"
OUT = ATOM / "operator-validation"
REFERENCE = CASES / "calendar-green/page.md"


def call(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["python3", str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)
    if ok and result.returncode != 0:
        raise SystemExit(result.stderr)
    if not ok and result.returncode == 0:
        raise SystemExit(f"expected refusal: {args}")
    return result


OUT.mkdir(parents=True, exist_ok=True)
reference_quote = next(line for line in REFERENCE.read_text().splitlines() if line.startswith("| Month 11 |"))
summaries = []
for case in ("calendar-red", "calendar-green"):
    source = CASES / case
    work = OUT / "runs" / case
    call(
        "open", "--page", str(source / "page.md"),
        "--payload", f"{source / 'state.json'}#context.up.cd_s_002.execution_toolkit",
        "--work", str(work),
    )
    manifest = json.loads((work / "unit-manifest.json").read_text())
    unit = next(item for item in manifest["units"] if "editorial calendar" in item["text"].casefold())
    cell_id = f"{unit['unit_id']}::benchmark-vs-reference"
    delivered_quote = next(line for line in unit["text"].splitlines() if line.startswith("| Month 12 |"))
    call(
        "register-reference", "--work", str(work), "--reference", "complete-calendar",
        "--page", str(REFERENCE),
    )
    refused = call(
        "benchmark", "--work", str(work), "--id", cell_id, "--reference", "complete-calendar",
        "--delivered-quote", delivered_quote, "--reference-quote", "invented professional reference words",
        ok=False,
    )
    benchmark = json.loads(call(
        "benchmark", "--work", str(work), "--id", cell_id, "--reference", "complete-calendar",
        "--delivered-quote", delivered_quote, "--reference-quote", reference_quote,
    ).stdout)
    verdict = "revise" if case == "calendar-red" else "clear"
    for seat in ("reader-1", "reader-2"):
        call(
            "judge", "--work", str(work), "--id", cell_id, "--seat", seat,
            "--verdict", verdict, "--quote", delivered_quote,
        )
    matrix = json.loads((work / "matrix.json").read_text())
    cell = next(item for item in matrix["cells"] if item["cell_id"] == cell_id)
    summary = {
        "case_id": case,
        "status": "satisfied",
        "cell_id": cell_id,
        "outcome": cell["outcome"],
        "benchmark": benchmark,
        "invalid_reference_refusal": refused.stderr.strip(),
    }
    (OUT / f"{case}.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    summaries.append(summary)
(OUT / "summary.json").write_text(json.dumps({"cases": summaries}, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": "passed", "cases": len(summaries)}, sort_keys=True))
