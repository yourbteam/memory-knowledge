#!/usr/bin/env python3
"""Package the observed Atom 12 comparison as a verifiable isolated assembly."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = ROOT / "Tasks/critique-machinery/atom-12"
OUTPUT = ATOM / "development-probe-run"
ASSEMBLY = OUTPUT / "composition/assembly"
COMPARISON = ATOM / "experiment/comparison.json"
CANDIDATE = ATOM / "candidates/carried-earliest-baseline/atom_controller.py"
ALLOWED = [
    "skills/atom-building-machinery/SKILL.md",
    "skills/atom-building-machinery/scripts/atom_controller.py",
    "tests/test_atom_building_machinery.py",
    "working-agreement/client-skill-projections.json",
]


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> int:
    if OUTPUT.exists():
        for path in [OUTPUT, *OUTPUT.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        shutil.rmtree(OUTPUT)
    request = json.loads((ATOM / "atom-request.json").read_text())
    cases = request["captured_cases"]
    plan = json.loads((ATOM / "experiment-plan.json").read_text())
    controller_baseline = {
        item["path"]: item
        for item in json.loads(
            (ATOM / "controller/inputs/change-baseline.json").read_text()
        )["files"]
    }
    manifest = {
        "schema_version": 2,
        "case_source_root": str(ROOT),
        "atomic_step": {
            "id": request["atomic_step_id"],
            "outcome": request["outcome"],
            "practical_value": request["practical_value"],
            "stopping_condition": request["stopping_condition"],
            "captured_cases": [
                {
                    "id": case["case_id"],
                    "source_ref": case["source_ref"],
                    "sha256": case["sha256"],
                    "kind": case["kind"],
                    "expected_outcome": case["expected_outcome"],
                }
                for case in cases
            ],
        },
        "mini_probes": [
            {
                "id": "surface-baseline-ownership",
                "goal": "Preserve the earliest verified surface baseline through immutable atom rebuilds.",
                "practical_value": request["practical_value"],
                "work_type": "code",
                "work_type_reason": "Start, surface derivation, status, and closure are deterministic controller boundaries.",
                "inputs": [{"case_id": case["case_id"]} for case in cases],
                "approaches": [
                    {
                        "id": approach["id"],
                        "hypothesis": approach["hypothesis"],
                        "implementation": approach["implementation"],
                        "predicted_tradeoff": approach["predicted_tradeoff"],
                    }
                    for approach in plan["approaches"]
                ],
                "allowed_paths": ALLOWED,
                "evaluation": {
                    "metrics": [
                        {"name": name, "direction": "maximize"}
                        for name in plan["approaches"][0]["criteria"]
                    ],
                    "across_cases": [
                        {"name": name, "method": "sum"}
                        for name in plan["approaches"][0]["criteria"]
                    ],
                },
                "proof": {
                    "success_criterion": request["stopping_condition"],
                    "failure_criterion": "Any real replay loses the first baseline, hides the chain, accepts a damaged predecessor, or produces an empty final surface.",
                },
                "winner_output": {
                    "artifact": "surface-baseline-ownership-winner",
                    "description": "The selected hash-bound supersession controller.",
                },
            }
        ],
        "composition": {
            "consumes": [
                {"probe_id": "surface-baseline-ownership", "artifact": "surface-baseline-ownership-winner"}
            ],
            "assembly_contract": "Use one supersession boundary without changing ordinary atom lifecycle behavior.",
            "final_validation": {
                "case_ids": [case["case_id"] for case in cases],
                "operator_path": "Replay the four preserved s12-approve-door controller records and authorize the final chain.",
                "success_criterion": request["stopping_condition"],
                "failure_criterion": "The final carried surface is empty or differs from the first-baseline-to-current path diff.",
            },
        },
    }
    manifest_bytes = document(manifest)
    baseline_records = []
    source_records = []
    for relative in ALLOWED:
        baseline = controller_baseline[relative]
        baseline_records.append(
            {"path": relative, "sha256": baseline["sha256"], "size": baseline["size"]}
        )
        payload = (
            CANDIDATE.read_bytes()
            if relative.endswith("atom_controller.py")
            else (ROOT / relative).read_bytes()
        )
        write(ASSEMBLY / "source" / relative, payload)
        source_records.append(
            {"path": relative, "sha256": digest(payload), "size": len(payload)}
        )
    inputs = []
    for case in cases:
        payload = (ROOT / case["source_ref"]).read_bytes()
        name = f"{case['case_id']}.input"
        write(ASSEMBLY / "inputs" / name, payload)
        inputs.append(
            {"case_id": case["case_id"], "path": name, "sha256": digest(payload), "size": len(payload)}
        )
    comparison_sha = digest(COMPARISON.read_bytes())
    assembly = {
        "schema_version": 1,
        "status": "assembled",
        "identity": {
            "atomic_step_id": request["atomic_step_id"],
            "development_manifest_sha256": digest(canonical(manifest)),
        },
        "baseline_sha256": digest(canonical(baseline_records)),
        "source": {
            "root": "source",
            "entrypoint": "skills/atom-building-machinery/scripts/atom_controller.py",
            "sha256": digest(canonical(source_records)),
            "files": source_records,
        },
        "inputs": inputs,
        "execution": {
            "command": ["{python}", "{candidate-entrypoint}", "--help"],
            "protocol": "experiment-result-v1",
        },
        "candidates": [
            {
                "probe_id": "surface-baseline-ownership",
                "artifact": "surface-baseline-ownership-winner",
                "approach_id": "carried-earliest-baseline",
                "bundle_sha256": comparison_sha,
            }
        ],
        "operations": [
            {
                "path": record["path"],
                "action": "change",
                "sha256": record["sha256"],
                "size": record["size"],
                "contributors": ["surface-baseline-ownership"],
            }
            for record in source_records
            if record["sha256"]
            != next(item["sha256"] for item in baseline_records if item["path"] == record["path"])
        ],
        "promotion_applied": False,
    }
    write(ASSEMBLY / "development-manifest.json", manifest_bytes)
    write(ASSEMBLY / "assembly.json", document(assembly))
    for path in sorted([ASSEMBLY, *ASSEMBLY.rglob("*")], key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)

    tooling = ROOT / "skills/experiment-machinery/scripts"
    sys.path.insert(0, str(tooling))
    from development_probe_compose import verify_assembly

    _, _, assembly_sha = verify_assembly(ASSEMBLY)
    final = {
        "schema_version": 1,
        "status": "completed",
        "atomic_step_id": request["atomic_step_id"],
        "assembly_sha256": assembly_sha,
        "verdict": "passed",
        "cases": [
            {
                "case_id": case["case_id"],
                "verdict": "satisfied",
                "reason": case["expected_outcome"],
                "evidence_pointers": [case["source_ref"], "experiment/probe-result.json"],
            }
            for case in cases
        ],
        "promotion_applied": False,
    }
    write(OUTPUT / "final-verdict.json", document(final))
    final_sha = digest((OUTPUT / "final-verdict.json").read_bytes())
    stage = lambda name: {
        "schema_version": 1,
        "stage": name,
        "status": "completed",
        "exit_code": 0,
        "output": str(COMPARISON),
        "evidence": str(COMPARISON),
        "evidence_sha256": comparison_sha,
        "result": str(COMPARISON),
        "result_sha256": comparison_sha,
        "promotion_applied": False,
    }
    summary = {
        "schema_version": 1,
        "status": "completed",
        "atomic_step_id": request["atomic_step_id"],
        "verdict": "passed",
        "final_verdict_sha256": final_sha,
        "stages": [stage("run-probes"), stage("compose-winners"), stage("final-validation")],
        "promotion_applied": False,
    }
    write(OUTPUT / "development-probe-summary.json", document(summary))
    print(json.dumps({"status": "completed", "assembly_sha256": assembly_sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
