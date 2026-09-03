#!/usr/bin/env python3
"""Exercise Atom 2 through the promoted critique CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
CASES = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01"
OUT = Path(__file__).resolve().parent / "operator-validation"


def invoke(*args: str) -> dict[str, object]:
    command = [sys.executable, str(SCRIPT), *args]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return {"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing existing validation directory: {OUT}")
    OUT.mkdir(parents=True)
    declarations = (
        ("btm-roadmap", "context.up.cd_s_002.tactical_roadmap", 25),
        ("viv-scorecard", "context.up.cd_s_002.measurement_framework", 12),
    )
    for case_id, key, unit_count in declarations:
        source = CASES / case_id
        work = OUT / "runs" / case_id
        opening = invoke(
            "open", "--page", str(source / "page.md"), "--payload", str(source / "state.json"),
            "--key", key, "--work", str(work),
        )
        matrix_path = work / "matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        matrix["cells"][0]["status"] = "judged"
        matrix_path.write_text(json.dumps(matrix, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        status_call = invoke("status", "--work", str(work))
        status = json.loads(str(status_call["stdout"]))
        routes = {
            "cell": invoke("cell", "--work", str(work), "--id", matrix["cells"][0]["cell_id"]),
            "report": invoke("report", "--work", str(work)),
            "document": invoke("document", "--work", str(work)),
        }
        missing_count = unit_count * 7 - 1
        route_passes = all(
            call["returncode"] == 2
            and f"{missing_count} matrix cells are unjudged" in str(call["stderr"])
            and matrix["cells"][1]["cell_id"] in str(call["stderr"])
            and "Judge every named unit/lens cell" in str(call["stderr"])
            for call in routes.values()
        )
        record = {
            "case_id": case_id,
            "opening": opening,
            "controlled_partial_cell": matrix["cells"][0]["cell_id"],
            "status_call": status_call,
            "status": status,
            "routes": routes,
            "satisfied": (
                opening["returncode"] == 0
                and status_call["returncode"] == 0
                and status["status"] == "partial"
                and status["unit_count"] == unit_count
                and status["lens_count"] == 7
                and status["cell_count"] == unit_count * 7
                and status["unjudged_count"] == missing_count
                and route_passes
            ),
        }
        (OUT / f"{case_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not record["satisfied"]:
            raise SystemExit(f"operator validation failed for {case_id}; inspect {OUT / (case_id + '.json')}")
    print(json.dumps({"status": "passed", "cases": 2, "protected_routes": 3}, sort_keys=True))


if __name__ == "__main__":
    main()
