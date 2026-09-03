#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
DEV = ATOM / "development"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    declarations = (
        ("btm-roadmap", "failure", "A controlled partial real roadmap refuses every result-bearing route."),
        ("viv-scorecard", "success", "A real scorecard produces units times seven cells and exposes partial status."),
    )
    cases = []
    for case_id, kind, expected in declarations:
        source = ROOT / f"Tasks/critique-machinery/evidence/cases/atom-01/{case_id}.tar"
        cases.append({"id": case_id, "source": str(source), "sha256": sha(source), "kind": kind, "expected_outcome": expected})
    outcome = "Every opened unit is crossed with seven fixed lenses and no result route leaks before all cells are judged."
    practical = "A partial critique is visibly partial and cannot be mistaken for a complete assessment."
    stopping = "Both real pages produce exact matrices and all result routes refuse the controlled partial state."
    allowed = ["skills/critique-machinery/scripts/critique.py", "tests/test_critique_machinery.py"]
    write(ATOM / "atom-request.json", {
        "schema_version": 1, "atomic_step_id": "critique-lens-matrix", "outcome": outcome,
        "practical_value": practical, "stopping_condition": stopping, "allowed_paths": allowed,
        "captured_cases": [{"case_id": case["id"], "source_ref": case["source"], "sha256": case["sha256"], "kind": case["kind"], "expected_outcome": case["expected_outcome"]} for case in cases],
    })
    manifest = {
        "schema_version": 1,
        "atomic_step": {"id": "critique-lens-matrix", "outcome": outcome, "practical_value": practical, "stopping_condition": stopping, "captured_cases": cases},
        "mini_probes": [{
            "id": "completion-boundary", "goal": "Close every result-bearing route over the same exact unit-by-lens matrix.",
            "practical_value": practical, "work_type": "code",
            "work_type_reason": "Matrix enumeration and route admission are deterministic state boundaries.",
            "allowed_paths": allowed, "inputs": [{"case_id": case["id"]} for case in cases],
            "approaches": [
                {"id": "terminal-only-gates", "hypothesis": "Protecting only assembled outputs is enough because individual cells are not final reports.", "implementation": "Gate report and document, but return any addressed judged cell.", "predicted_tradeoff": "Less restrictive inspection, but a partial run can leak a completed-looking result."},
                {"id": "universal-gate", "hypothesis": "Every result-bearing route must share one completeness gate to make partial work unmistakable.", "implementation": "Gate cell, report, and document through one missing-cell check; keep status diagnostic-only.", "predicted_tradeoff": "Operators cannot inspect one completed cell until the whole matrix closes."},
            ],
            "proof": {"success_criterion": "Exact matrix shape, partial status, and three actionable route refusals on both real pages.", "failure_criterion": "Wrong dimensions, completed status, or any result-bearing route returns while a cell is unjudged."},
            "evaluation": {
                "metrics": [
                    {"name": "open-correctness", "direction": "maximize"},
                    {"name": "matrix-shape", "direction": "maximize"},
                    {"name": "partial-visibility", "direction": "maximize"},
                    {"name": "closed-result-routes", "direction": "maximize"},
                    {"name": "actionable-refusals", "direction": "maximize"},
                ],
                "across_cases": [
                    {"name": "open-correctness", "method": "sum"},
                    {"name": "matrix-shape", "method": "sum"},
                    {"name": "partial-visibility", "method": "sum"},
                    {"name": "closed-result-routes", "method": "sum"},
                    {"name": "actionable-refusals", "method": "sum"},
                ],
            },
            "winner_output": {"artifact": "matrix-completion-boundary", "description": "The exact fixed-lens matrix and shared result-route gate."},
        }],
        "composition": {
            "consumes": [{"probe_id": "completion-boundary", "artifact": "matrix-completion-boundary"}],
            "assembly_contract": "Use the selected matrix construction and route gate unchanged.",
            "final_validation": {"operator_path": "open each frozen real archive, create controlled partial state, and invoke status/cell/report/document", "case_ids": [case["id"] for case in cases], "success_criterion": "Both cases show exact partial matrices and all three result routes refuse.", "failure_criterion": "Any matrix is malformed or any result route leaks."},
        },
    }
    manifest_path = DEV / "manifest.json"
    write(manifest_path, manifest)
    approaches = []
    for approach_id in ("terminal-only-gates", "universal-gate"):
        request = DEV / f"build-{approach_id}.json"
        write(request, {
            "schema_version": 1, "development_manifest": str(manifest_path), "probe_id": "completion-boundary", "approach_id": approach_id,
            "source": {"baseline": str(DEV / "baseline"), "candidate": str(DEV / approach_id), "entrypoint": "skills/critique-machinery/scripts/critique.py"},
            "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
        })
        approaches.append({"approach_id": approach_id, "request": str(request)})
    cross = DEV / "cross-completion-boundary.json"
    write(cross, {
        "schema_version": 1, "development_manifest": str(manifest_path), "probe_id": "completion-boundary", "approach_build_requests": approaches,
        "evaluator": {"adapter": {"path": str(DEV / "evaluator.py"), "sha256": sha(DEV / "evaluator.py")}, "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]},
    })
    hasher = ROOT / "skills/experiment-machinery/scripts/run_experiment.py"
    baseline_hash = subprocess.run([sys.executable, str(hasher), "--hash-source", str(DEV / "baseline")], check=True, capture_output=True, text=True).stdout.strip()
    write(DEV / "full-run.json", {
        "schema_version": 1,
        "development_manifest": {"path": str(manifest_path), "sha256": sha(manifest_path)},
        "baseline": {"path": str(DEV / "baseline"), "sha256": baseline_hash},
        "probe_requests": [{"probe_id": "completion-boundary", "request": str(cross), "request_sha256": sha(cross)}],
        "assessment": {"adapter": {"path": str(DEV / "assessment.py"), "sha256": sha(DEV / "assessment.py")}, "command": ["{python}", "{assessment-adapter}", "{assessment-request}", "{assessment-response}"]},
    })


if __name__ == "__main__":
    main()
