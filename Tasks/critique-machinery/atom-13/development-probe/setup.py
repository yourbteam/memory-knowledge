#!/usr/bin/env python3
"""Prepare the official Atom C Development-Probe from frozen real inputs."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SPEC = Path(__file__).resolve().parent
OUT = SPEC / "run-inputs-7"
ATOM = ROOT / "Tasks/critique-machinery/atom-13"
ATOM_B = ROOT / "Tasks/critique-machinery/atom-12/controller-v3/evidence/experiment-000002/composition/assembly/source"
PATHS = [
    "skills/atom-building-machinery/SKILL.md",
    "skills/atom-building-machinery/scripts/atom_controller.py",
    "tests/test_atom_building_machinery.py",
    "working-agreement/client-skill-projections.json",
]
sys.path.insert(0, str(ROOT / "skills/experiment-machinery/scripts"))

from development_probe_candidate import _snapshot_source  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"run inputs must be new: {OUT}")
    baseline = OUT / "baseline"
    baseline.mkdir(parents=True)
    for relative in PATHS:
        target = baseline / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ATOM_B / relative, target)
    shutil.copytree(ROOT / "scripts", baseline / "scripts", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(SPEC / "probe_entry.py", baseline / "probe_entry.py")
    write(baseline / "operator-context.json", {"repository_root": "/Users/kamenkamenov/united-partners"})
    for source_name, target_name in (("proof-order-final-waive", "proof-order"), ("countable-kpis-final", "countable-kpis")):
        shutil.copytree(ATOM / "waiver-interviews" / source_name, baseline / "owner-evidence" / target_name)

    enforced = OUT / "candidates/enforced"
    remembered = OUT / "candidates/author-remembers"
    shutil.copytree(baseline, enforced)
    shutil.copytree(baseline, remembered)
    for copied_tree in (enforced, remembered):
        for path in [copied_tree, *copied_tree.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
    for relative in PATHS:
        shutil.copy2(ROOT / relative, enforced / relative)

    request = json.loads((ATOM / "atom-request-final.json").read_text())
    manifest = {
        "schema_version": 2,
        "case_source_root": str(ROOT),
        "atomic_step": {
            "id": request["atomic_step_id"],
            "outcome": request["outcome"],
            "practical_value": request["practical_value"],
            "stopping_condition": request["stopping_condition"],
            "captured_cases": [
                {"id": case["case_id"], "source_ref": case["source_ref"], "sha256": case["sha256"], "kind": case["kind"], "expected_outcome": case["expected_outcome"]}
                for case in request["captured_cases"]
            ],
        },
        "mini_probes": [{
            "id": "validation-contract-surface",
            "goal": "Choose whether the atom controller enforces a repository-backed validation surface at start.",
            "practical_value": request["practical_value"],
            "work_type": "code",
            "work_type_reason": "The boundary is deterministic start, status, and receipt behavior.",
            "allowed_paths": PATHS,
            "inputs": [{"case_id": case["case_id"]} for case in request["captured_cases"]],
            "approaches": [
                {"id": "enforced-surface", "hypothesis": "A code-enforced field and shape declaration prevents prose-parser validation from starting silently.", "implementation": "Resolve contract_surface against the repository and bind prose exceptions to the owner's code-interview receipt.", "predicted_tradeoff": "New atoms declare their surface; prose atoms need one owner choice."},
                {"id": "author-remembers", "hypothesis": "Documenting the lesson is enough.", "implementation": "Keep the pre-Atom C controller.", "predicted_tradeoff": "No request change, but no executable protection."},
            ],
            "proof": {"success_criterion": request["stopping_condition"], "failure_criterion": "A prose validator starts without its exact waiver, a structured request cannot start, or the declaration is absent from status."},
            "evaluation": {
                "metrics": [{"name": name, "direction": "maximize"} for name in ("direct-contract-correct", "refusal-actionable", "owner-waiver-request-bound", "contract-surface-visible", "frozen-input-unchanged")],
                "across_cases": [{"name": name, "method": "worst"} for name in ("direct-contract-correct", "refusal-actionable", "owner-waiver-request-bound", "contract-surface-visible", "frozen-input-unchanged")],
            },
            "winner_output": {"artifact": "validation-contract-surface-winner", "description": "The measured controller approach."},
        }],
        "composition": {
            "consumes": [{"probe_id": "validation-contract-surface", "artifact": "validation-contract-surface-winner"}],
            "assembly_contract": "Use only the measured winner; preserve every other controller lifecycle boundary.",
            "final_validation": {
                "operator_path": "probe_entry.py invokes start and status on every frozen declared request and both owner receipts.",
                "case_ids": [case["case_id"] for case in request["captured_cases"]],
                "success_criterion": request["stopping_condition"],
                "failure_criterion": "Any measured contract, waiver, visibility, or immutability metric is not one.",
            },
        },
    }
    manifest_path = OUT / "development-manifest.json"
    write(manifest_path, manifest)
    build_requests = []
    for approach, candidate in (("enforced-surface", enforced), ("author-remembers", remembered)):
        path = OUT / "requests" / f"build-{approach}.json"
        write(path, {
            "schema_version": 1,
            "development_manifest": str(manifest_path),
            "probe_id": "validation-contract-surface",
            "approach_id": approach,
            "source": {"baseline": str(baseline), "candidate": str(candidate), "entrypoint": "probe_entry.py"},
            "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}", "{frozen-input}", "{result-path}", "{telemetry-path}"]},
        })
        build_requests.append({"approach_id": approach, "request": str(path)})
    evaluator = SPEC / "evaluator_adapter.py"
    cross = OUT / "requests/cross-case.json"
    write(cross, {
        "schema_version": 1,
        "development_manifest": str(manifest_path),
        "probe_id": "validation-contract-surface",
        "approach_build_requests": build_requests,
        "evaluator": {"adapter": {"path": str(evaluator), "sha256": sha(evaluator)}, "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]},
    })
    assessor = SPEC / "assessment_adapter.py"
    development_request = OUT / "development-probe-request.json"
    _, _, baseline_sha256 = _snapshot_source(baseline, "Atom C baseline")
    write(development_request, {
        "schema_version": 1,
        "development_manifest": {"path": str(manifest_path), "sha256": sha(manifest_path)},
        "baseline": {"path": str(baseline), "sha256": baseline_sha256},
        "probe_requests": [{"probe_id": "validation-contract-surface", "request": str(cross), "request_sha256": sha(cross)}],
        "assessment": {"adapter": {"path": str(assessor), "sha256": sha(assessor)}, "command": ["{python}", "{assessment-adapter}", "{assessment-request}", "{assessment-response}"]},
    })
    print(development_request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
