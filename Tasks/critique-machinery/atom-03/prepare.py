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
    definitions = (
        ("stale-door-red", "failure", "Every assigned lens identifies the recorded decision contradiction."),
        ("stale-door-green", "success", "The same lenses clear the corrected recorded decision."),
        ("calendar-red", "failure", "Every assigned lens identifies the recorded incomplete annual calendar."),
        ("calendar-green", "success", "The same lenses clear the corrected twelve-month calendar."),
    )
    cases = []
    for case_id, kind, expected in definitions:
        source_ref = f"Tasks/critique-machinery/atom-03/cases/{case_id}.tar"
        source = ROOT / source_ref
        cases.append(
            {
                "id": case_id,
                "source_ref": source_ref,
                "sha256": sha(source),
                "kind": kind,
                "expected_outcome": expected,
            }
        )
    outcome = "One matrix cell records a discriminating fixed verdict plus an exact unit quote, and refuses invented evidence."
    practical = "Each criticism names the delivered words that caused it, while corrected real pages receive different verdicts."
    stopping = "All seven lenses discriminate their assigned real red/green pair, every accepted verdict is grounded, and invalid quotes refuse."
    allowed = ["skills/critique-machinery/scripts/critique.py", "tests/test_critique_machinery.py"]
    write(
        ATOM / "atom-request.json",
        {
            "schema_version": 1,
            "atomic_step_id": "critique-grounded-verdict",
            "outcome": outcome,
            "practical_value": practical,
            "stopping_condition": stopping,
            "allowed_paths": allowed,
            "captured_cases": [
                {
                    "case_id": case["id"],
                    "source_ref": case["source_ref"],
                    "sha256": case["sha256"],
                    "kind": case["kind"],
                    "expected_outcome": case["expected_outcome"],
                }
                for case in cases
            ],
        },
    )
    metrics = [
        {"name": "lens-discrimination", "direction": "maximize"},
        {"name": "grounded-verdicts", "direction": "maximize"},
        {"name": "actionable-handoffs", "direction": "maximize"},
        {"name": "invalid-quote-refusal", "direction": "maximize"},
    ]
    manifest = {
        "schema_version": 2,
        "case_source_root": str(ROOT),
        "atomic_step": {
            "id": "critique-grounded-verdict",
            "outcome": outcome,
            "practical_value": practical,
            "stopping_condition": stopping,
            "captured_cases": cases,
        },
        "mini_probes": [
            {
                "id": "verdict-contract",
                "goal": "Select a fixed verdict and grounding contract that discriminates recorded real defects from their corrections.",
                "practical_value": practical,
                "work_type": "hybrid",
                "work_type_reason": "Code owns accepted words and exact-quote admission; a model applies each semantic lens to the frozen unit.",
                "allowed_paths": allowed,
                "inputs": [{"case_id": case["id"]} for case in cases],
                "approaches": [
                    {
                        "id": "binary-groundless",
                        "hypothesis": "A weak-or-fine verdict alone discriminates defects with less response burden.",
                        "implementation": "Accept weak/fine without a quote and run the reader with a verdict-only schema.",
                        "predicted_tradeoff": "Cheap classification, but no page words are handed to the operator and invented evidence cannot be rejected.",
                    },
                    {
                        "id": "action-grounded",
                        "hypothesis": "Reject/revise/clear plus an exact unit quote preserves discrimination and yields actionable evidence.",
                        "implementation": "Require an allowed action verdict and an exact whitespace-collapsed quote of at least 25 characters or the whole short unit.",
                        "predicted_tradeoff": "Stricter responses and more model tokens, but every call is located in immutable page language.",
                    },
                ],
                "proof": {
                    "success_criterion": "All assigned lens verdicts match the recorded red/green status, accepted quotes are exact and actionable, and a fabricated quote refuses.",
                    "failure_criterion": "Any lens gives the same defect state to both twins, any accepted judgment lacks unit words, or an invented quote is stored.",
                },
                "evaluation": {
                    "metrics": metrics,
                    "across_cases": [{"name": item["name"], "method": "sum"} for item in metrics],
                },
                "winner_output": {
                    "artifact": "grounded-verdict-contract",
                    "description": "The fixed verdict vocabulary, exact quote admission boundary, reader prompt, and judge command.",
                },
            }
        ],
        "composition": {
            "consumes": [{"probe_id": "verdict-contract", "artifact": "grounded-verdict-contract"}],
            "assembly_contract": "Use the selected verdict vocabulary, quote admission, and model-backed experiment path unchanged.",
            "final_validation": {
                "operator_path": "open each frozen page, select its recorded-defect unit, run each assigned lens through codex exec, and record each cell through judge",
                "case_ids": [case["id"] for case in cases],
                "success_criterion": "Every real case is classified correctly with an exact actionable quote, and an invented quote refuses.",
                "failure_criterion": "Any case is misclassified, ungrounded, non-actionable, or admits invented words.",
            },
        },
    }
    manifest_path = DEV / "manifest.json"
    write(manifest_path, manifest)
    approaches = []
    for approach_id in ("binary-groundless", "action-grounded"):
        request = DEV / f"build-{approach_id}.json"
        write(
            request,
            {
                "schema_version": 1,
                "development_manifest": str(manifest_path),
                "probe_id": "verdict-contract",
                "approach_id": approach_id,
                "source": {
                    "baseline": str(DEV / "baseline"),
                    "candidate": str(DEV / approach_id),
                    "entrypoint": "skills/critique-machinery/scripts/critique.py",
                },
                "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
            },
        )
        approaches.append({"approach_id": approach_id, "request": str(request)})
    cross = DEV / "cross-verdict-contract.json"
    write(
        cross,
        {
            "schema_version": 1,
            "development_manifest": str(manifest_path),
            "probe_id": "verdict-contract",
            "approach_build_requests": approaches,
            "evaluator": {
                "adapter": {"path": str(DEV / "evaluator.py"), "sha256": sha(DEV / "evaluator.py")},
                "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"],
            },
        },
    )
    hasher = ROOT / "skills/experiment-machinery/scripts/run_experiment.py"
    baseline_hash = subprocess.run(
        [sys.executable, str(hasher), "--hash-source", str(DEV / "baseline")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    write(
        DEV / "full-run.json",
        {
            "schema_version": 1,
            "development_manifest": {"path": str(manifest_path), "sha256": sha(manifest_path)},
            "baseline": {"path": str(DEV / "baseline"), "sha256": baseline_hash},
            "probe_requests": [
                {"probe_id": "verdict-contract", "request": str(cross), "request_sha256": sha(cross)}
            ],
            "assessment": {
                "adapter": {"path": str(DEV / "assessment.py"), "sha256": sha(DEV / "assessment.py")},
                "command": ["{python}", "{assessment-adapter}", "{assessment-request}", "{assessment-response}"],
            },
        },
    )


if __name__ == "__main__":
    main()
