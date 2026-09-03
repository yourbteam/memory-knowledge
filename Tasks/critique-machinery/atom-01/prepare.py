#!/usr/bin/env python3
"""Bind Atom 1's frozen cases and candidate trees into canonical run requests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
DEV = ATOM / "development"
EXPERIMENT = ROOT / "skills/experiment-machinery/scripts/run_experiment.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    cases = []
    declarations = (
        ("btm-roadmap", "success", "opened", "The authentic BTM Step 12 page opens."),
        ("viv-scorecard", "success", "opened", "The authentic Vivacom Step 10 scorecard opens."),
        (
            "btm-roadmap-wrong-payload",
            "failure",
            "refused-page-payload-mismatch",
            "The BTM roadmap paired with the real measurement payload refuses by name.",
        ),
    )
    for case_id, kind, expected, description in declarations:
        source = ROOT / f"Tasks/critique-machinery/evidence/cases/atom-01/{case_id}.tar"
        cases.append(
            {
                "id": case_id,
                "source": str(source),
                "sha256": sha(source),
                "kind": kind,
                "expected_outcome": description,
            }
        )
    outcome = (
        "The open CLI freezes a complete, payload-grounded unit manifest for authentic page/payload "
        "pairs and refuses wrong pairings, non-repository work roots, and incompatible reopens."
    )
    practical = "A critic cannot silently omit page territory or judge a page against unrelated stored material."
    stopping = "All frozen cases pass through the assembled candidate and the promoted open CLI repeats them."
    allowed = ["skills/critique-machinery/scripts/critique.py"]
    write(
        ATOM / "atom-request.json",
        {
            "schema_version": 1,
            "atomic_step_id": "critique-unit-enumeration",
            "outcome": outcome,
            "practical_value": practical,
            "stopping_condition": stopping,
            "allowed_paths": allowed,
            "captured_cases": [
                {
                    "case_id": case["id"],
                    "source_ref": case["source"],
                    "sha256": case["sha256"],
                    "kind": case["kind"],
                    "expected_outcome": case["expected_outcome"],
                }
                for case in cases
            ],
        },
    )
    manifest = {
        "schema_version": 1,
        "atomic_step": {
            "id": "critique-unit-enumeration",
            "outcome": outcome,
            "practical_value": practical,
            "stopping_condition": stopping,
            "captured_cases": cases,
        },
        "mini_probes": [
            {
                "id": "unit-cut",
                "goal": "Cut authentic delivered pages into complete, judgeable territories bound to stored payload records.",
                "practical_value": practical,
                "work_type": "code",
                "work_type_reason": "Payload traversal, identity evidence, and exact territory accounting are deterministic code boundaries.",
                "allowed_paths": allowed,
                "inputs": [{"case_id": case["id"]} for case in cases],
                "approaches": [
                    {
                        "id": "payload-records",
                        "hypothesis": "Stored record boundaries produce units closest to the objects a person can judge alone.",
                        "implementation": "Enumerate top-level stored objects and list records, then assign rendered blocks by word overlap.",
                        "predicted_tradeoff": "Strong payload identity with possible empty units when a stored record is omitted from this rendered page.",
                    },
                    {
                        "id": "rendered-sections",
                        "hypothesis": "Rendered heading boundaries preserve the page's visible reading structure while payload binding supplies provenance.",
                        "implementation": "Enumerate heading sections, then bind each section to its strongest stored record by word overlap.",
                        "predicted_tradeoff": "Complete visible sections, but a long table under one heading may be too coarse to judge alone.",
                    },
                ],
                "proof": {
                    "success_criterion": "Both authentic pairs open, the mismatched pair refuses, and every rendered block is assigned exactly once.",
                    "failure_criterion": "Any expected outcome differs or any rendered block is omitted or multiply assigned.",
                },
                "evaluation": {
                    "metrics": [
                        {"name": "boundary-correctness", "direction": "maximize"},
                        {"name": "territory-completeness", "direction": "maximize"},
                        {"name": "judgeability", "direction": "maximize"},
                        {"name": "payload-grounding", "direction": "maximize"},
                    ],
                    "across_cases": [
                        {"name": "boundary-correctness", "method": "sum"},
                        {"name": "territory-completeness", "method": "sum"},
                        {"name": "judgeability", "method": "mean"},
                        {"name": "payload-grounding", "method": "mean"},
                    ],
                },
                "winner_output": {
                    "artifact": "unit-enumerator",
                    "description": "The tested page/payload identity guard and complete unit-cut implementation.",
                },
            }
        ],
        "composition": {
            "consumes": [{"probe_id": "unit-cut", "artifact": "unit-enumerator"}],
            "assembly_contract": "Use the selected unit enumerator unchanged as the critique open boundary.",
            "final_validation": {
                "operator_path": "execute the selected critique.py against each frozen page/state archive",
                "case_ids": [case["id"] for case in cases],
                "success_criterion": "Every real case reports its declared outcome with exact territory coverage on opened pages.",
                "failure_criterion": "Any case reports a different outcome or incomplete territory.",
            },
        },
    }
    manifest_path = DEV / "manifest.json"
    write(manifest_path, manifest)
    approaches = []
    for approach_id in ("payload-records", "rendered-sections"):
        request = DEV / f"build-{approach_id}.json"
        write(
            request,
            {
                "schema_version": 1,
                "development_manifest": str(manifest_path),
                "probe_id": "unit-cut",
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
    cross = DEV / "cross-unit-cut.json"
    write(
        cross,
        {
            "schema_version": 1,
            "development_manifest": str(manifest_path),
            "probe_id": "unit-cut",
            "approach_build_requests": approaches,
            "evaluator": {
                "adapter": {"path": str(DEV / "evaluator.py"), "sha256": sha(DEV / "evaluator.py")},
                "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"],
            },
        },
    )
    baseline_hash = subprocess.run(
        [sys.executable, str(EXPERIMENT), "--hash-source", str(DEV / "baseline")],
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
            "probe_requests": [{"probe_id": "unit-cut", "request": str(cross), "request_sha256": sha(cross)}],
            "assessment": {
                "adapter": {"path": str(DEV / "assessment.py"), "sha256": sha(DEV / "assessment.py")},
                "command": ["{python}", "{assessment-adapter}", "{assessment-request}", "{assessment-response}"],
            },
        },
    )


if __name__ == "__main__":
    main()
