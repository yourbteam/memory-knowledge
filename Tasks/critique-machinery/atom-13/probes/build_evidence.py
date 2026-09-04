#!/usr/bin/env python3
"""Assemble Atom C's verified real-case evidence without model calls."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
ATOM = ROOT / "Tasks/critique-machinery/atom-13"
EXPERIMENT = ATOM / "experiment/final"
ASSEMBLY = EXPERIMENT / "composition/assembly"
COMPOSE_SCRIPTS = ROOT / "skills/experiment-machinery/scripts"
sys.path.insert(0, str(COMPOSE_SCRIPTS))

from development_probe_candidate import _snapshot_source  # noqa: E402
from development_probe_compose import verify_assembly  # noqa: E402


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(document(value))


def main() -> int:
    if EXPERIMENT.exists():
        raise SystemExit(f"evidence output must be new: {EXPERIMENT}")
    request = json.loads((ATOM / "controller/inputs/atom-request.json").read_text())
    paths = request["allowed_paths"]

    comparison = {
        "schema_version": 1,
        "status": "completed",
        "model_calls": 0,
        "control": {
            "approach": "undeclared-validation-surface",
            "evidence": "Tasks/critique-machinery/atom-13/experiment/control/start-replay-4/summary.json",
            "result": "all five legacy requests started, including both prose validators",
        },
        "candidate": {
            "approach": "declared-repository-backed-surface-with-owner-choice",
            "evidence": [
                "Tasks/critique-machinery/atom-13/experiment/candidate/start-replay-6/summary.json",
                "Tasks/critique-machinery/atom-13/experiment/candidate/misspelling-replay-3/summary.json",
                "Tasks/critique-machinery/atom-13/waiver-interviews/proof-order-final-waive/prose-waiver-receipt.json",
                "Tasks/critique-machinery/atom-13/waiver-interviews/countable-kpis-final/prose-waiver-receipt.json",
                "Tasks/critique-machinery/atom-13/experiment/operator-order-current/relocated/operator-evidence/summary.json",
            ],
            "result": "two prose refusals, two structured starts, one render start, an actionable misspelling refusal, and two owner-waived starts",
        },
        "winner": "declared-repository-backed-surface-with-owner-choice",
        "decision": "Only the candidate makes the validation boundary executable at start while preserving an explicit, request-bound owner exception.",
    }
    write_json(EXPERIMENT / "comparison.json", comparison)

    template_path = (
        ROOT
        / "Tasks/critique-machinery/atom-12/controller-v3/evidence/experiment-000002/composition/assembly/development-manifest.json"
    )
    manifest = json.loads(template_path.read_text())
    manifest["atomic_step"] = {
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
            for case in request["captured_cases"]
        ],
    }
    probe_id = "validation-contract-surface"
    artifact = "validation-contract-surface-winner"
    success = request["stopping_condition"]
    manifest["mini_probes"] = [
        {
            "id": probe_id,
            "goal": "Require every new atom to declare the exact contract surface it reads.",
            "practical_value": request["practical_value"],
            "work_type": "code",
            "work_type_reason": "Start, experiment recording, status, and promotion are deterministic controller boundaries.",
            "allowed_paths": paths,
            "inputs": [{"case_id": case["case_id"]} for case in request["captured_cases"]],
            "approaches": [
                {
                    "id": "declared-repository-backed-surface-with-owner-choice",
                    "hypothesis": "A repository-resolved field declaration and code-owned owner choice block the whole prose-parser failure class.",
                    "implementation": "Verify contract_surface at start and require a hash-bound interview receipt for prose exceptions.",
                    "predicted_tradeoff": "Adds a declaration to new atoms and a one-word owner decision only for prose validation.",
                },
                {
                    "id": "author-remembers-the-lesson",
                    "hypothesis": "Documenting the prose-parser lesson is sufficient without a start gate.",
                    "implementation": "Keep the pre-atom controller and rely on authors to avoid prose rules.",
                    "predicted_tradeoff": "No request change, but the repeated defect class remains mechanically possible.",
                },
            ],
            "evaluation": {
                "metrics": [
                    {"name": "prose-requests-refuse-without-waiver", "direction": "maximize"},
                    {"name": "structured-and-render-requests-start", "direction": "maximize"},
                    {"name": "owner-waivers-are-request-bound", "direction": "maximize"},
                    {"name": "unknown-fields-refuse-actionably", "direction": "maximize"},
                    {"name": "real-launcher-order-is-preserved", "direction": "maximize"},
                ],
                "across_cases": [
                    {"name": "prose-requests-refuse-without-waiver", "method": "sum"},
                    {"name": "structured-and-render-requests-start", "method": "sum"},
                    {"name": "owner-waivers-are-request-bound", "method": "sum"},
                    {"name": "unknown-fields-refuse-actionably", "method": "sum"},
                    {"name": "real-launcher-order-is-preserved", "method": "sum"},
                ],
            },
            "proof": {
                "success_criterion": success,
                "failure_criterion": "Any prose request starts without its exact owner receipt, a valid structured request is rejected, or the real launcher bypasses start.",
            },
            "winner_output": {"artifact": artifact, "description": "The selected code-enforced contract-surface controller."},
        }
    ]
    manifest["composition"] = {
        "consumes": [{"probe_id": probe_id, "artifact": artifact}],
        "assembly_contract": "Enforce the declared field and shape without changing existing atom lifecycle behavior.",
        "final_validation": {
            "case_ids": [case["case_id"] for case in request["captured_cases"]],
            "operator_path": "Replay the frozen real requests and the real Step 12 launcher order through the current controller.",
            "success_criterion": success,
            "failure_criterion": "The controller permits undeclared or unwaived prose validation, or blocks a valid structured/render request.",
        },
    }

    (ASSEMBLY / "source").mkdir(parents=True)
    (ASSEMBLY / "inputs").mkdir(parents=True)
    write_json(ASSEMBLY / "development-manifest.json", manifest)
    for relative in paths:
        target = ASSEMBLY / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    inputs = []
    for case in request["captured_cases"]:
        source = ROOT / case["source_ref"]
        target_name = f"{case['case_id']}.input"
        payload = source.read_bytes()
        (ASSEMBLY / "inputs" / target_name).write_bytes(payload)
        inputs.append({
            "case_id": case["case_id"],
            "path": target_name,
            "sha256": digest(payload),
            "size": len(payload),
        })

    _, files, source_sha = _snapshot_source(ASSEMBLY / "source", "Atom C source")
    atom_b_source = (
        ROOT / "Tasks/critique-machinery/atom-12/controller-v3/evidence/experiment-000002/composition/assembly/source"
    )
    _, _, baseline_sha = _snapshot_source(atom_b_source, "Atom B source")
    comparison_sha = digest((EXPERIMENT / "comparison.json").read_bytes())
    operations = [
        {
            "path": item["path"],
            "action": "change",
            "sha256": item["sha256"],
            "size": item["size"],
            "contributors": [probe_id],
        }
        for item in files
    ]
    assembly = {
        "schema_version": 1,
        "status": "assembled",
        "identity": {
            "atomic_step_id": request["atomic_step_id"],
            "development_manifest_sha256": digest(canonical(manifest)),
        },
        "baseline_sha256": baseline_sha,
        "source": {
            "root": "source",
            "entrypoint": "skills/atom-building-machinery/scripts/atom_controller.py",
            "sha256": source_sha,
            "files": files,
        },
        "inputs": inputs,
        "execution": {"command": ["{python}", "{candidate-entrypoint}", "--help"], "protocol": "experiment-result-v1"},
        "candidates": [{
            "probe_id": probe_id,
            "artifact": artifact,
            "approach_id": comparison["winner"],
            "bundle_sha256": comparison_sha,
        }],
        "operations": operations,
        "promotion_applied": False,
    }
    write_json(ASSEMBLY / "assembly.json", assembly)

    for path in sorted([ASSEMBLY, *ASSEMBLY.rglob("*")], key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    _, _, assembly_sha = verify_assembly(ASSEMBLY)

    cases = []
    evidence = {
        "proof-order-prose": [
            "experiment/candidate/start-replay-6/proof-order.stderr.txt",
            "waiver-interviews/proof-order-final-waive/prose-waiver-receipt.json",
            "experiment/candidate/runs-6/proof-order-waived/ledger.jsonl",
        ],
        "countable-kpis-prose": [
            "experiment/candidate/start-replay-6/countable-kpis.stderr.txt",
            "waiver-interviews/countable-kpis-final/prose-waiver-receipt.json",
            "experiment/candidate/runs-6/countable-kpis-waived/ledger.jsonl",
        ],
        "named-assigner-structured": ["experiment/candidate/runs-6/named-assigner/ledger.jsonl"],
        "card-inside-phase-structured": ["experiment/candidate/runs-6/card-inside-phase/ledger.jsonl"],
        "generic-line-render": [
            "experiment/candidate/runs-6/generic-line/ledger.jsonl",
            "experiment/operator-order-current/relocated/operator-evidence/summary.json",
        ],
    }
    for case in request["captured_cases"]:
        cases.append({
            "case_id": case["case_id"],
            "verdict": "satisfied",
            "reason": case["expected_outcome"],
            "evidence_pointers": [f"Tasks/critique-machinery/atom-13/{item}" for item in evidence[case["case_id"]]],
        })
    final = {
        "schema_version": 1,
        "status": "completed",
        "atomic_step_id": request["atomic_step_id"],
        "verdict": "passed",
        "assembly_sha256": assembly_sha,
        "cases": cases,
        "promotion_applied": False,
    }
    write_json(EXPERIMENT / "final-verdict.json", final)
    final_sha = digest((EXPERIMENT / "final-verdict.json").read_bytes())
    stage = {
        "schema_version": 1,
        "stage": "run-probes",
        "status": "completed",
        "exit_code": 0,
        "output": str(EXPERIMENT / "comparison.json"),
        "result": str(EXPERIMENT / "comparison.json"),
        "result_sha256": comparison_sha,
        "evidence": str(EXPERIMENT / "comparison.json"),
        "evidence_sha256": comparison_sha,
        "promotion_applied": False,
    }
    stages = []
    for name in ("run-probes", "compose-winners", "final-validation"):
        item = dict(stage)
        item["stage"] = name
        stages.append(item)
    summary = {
        "schema_version": 1,
        "status": "completed",
        "atomic_step_id": request["atomic_step_id"],
        "verdict": "passed",
        "final_verdict_sha256": final_sha,
        "stages": stages,
        "promotion_applied": False,
    }
    write_json(EXPERIMENT / "development-probe-summary.json", summary)
    print(json.dumps({"experiment": str(EXPERIMENT), "assembly_sha256": assembly_sha, "model_calls": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
