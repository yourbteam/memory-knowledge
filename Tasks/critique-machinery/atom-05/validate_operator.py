#!/usr/bin/env python3
"""Exercise Atom 5 through the public critique CLI on both frozen calendar cases."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
ATOM = Path(__file__).resolve().parent
CASES = ROOT / "Tasks/critique-machinery/atom-03/cases"
OUT = ATOM / "operator-validation"
QUOTES = {
    "calendar-red": "Twelve-month corporate calendar showing major moments (results announcements, investor days, AGM, sustainability report publication, executive appearances, signature events, anticipated regulatory milestones), plus always-on activity.",
    "calendar-green": "The 12-month content calendar balanced Hero/Hub/Hygiene, showing the white space.",
}


def call(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["python3", str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)
    if ok and result.returncode != 0:
        raise SystemExit(result.stderr)
    if not ok and result.returncode == 0:
        raise SystemExit(f"expected refusal: {args}")
    return result


OUT.mkdir(parents=True, exist_ok=True)
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
    cell_id = f"{unit['unit_id']}::upstream-trace"
    call(
        "register-source", "--work", str(work), "--source", "execution-guide",
        "--payload", f"{source / 'state.json'}#context.up.cd_s_002.source_document_packet",
    )
    refused = call(
        "trace", "--work", str(work), "--id", cell_id, "--source", "execution-guide",
        "--quote", "invented upstream requirement words", ok=False,
    )
    trace = json.loads(call(
        "trace", "--work", str(work), "--id", cell_id, "--source", "execution-guide",
        "--quote", QUOTES[case],
    ).stdout)
    unit_quote = " ".join(unit["text"].split())[:120]
    verdict = "revise" if case == "calendar-red" else "clear"
    for seat in ("reader-1", "reader-2"):
        call(
            "judge", "--work", str(work), "--id", cell_id, "--seat", seat,
            "--verdict", verdict, "--quote", unit_quote,
        )
    matrix = json.loads((work / "matrix.json").read_text())
    cell = next(item for item in matrix["cells"] if item["cell_id"] == cell_id)
    summary = {
        "case_id": case,
        "status": "satisfied",
        "cell_id": cell_id,
        "outcome": cell["outcome"],
        "trace": trace,
        "invalid_trace_refusal": refused.stderr.strip(),
    }
    (OUT / f"{case}.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    summaries.append(summary)
(OUT / "summary.json").write_text(json.dumps({"cases": summaries}, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": "passed", "cases": len(summaries)}, sort_keys=True))
