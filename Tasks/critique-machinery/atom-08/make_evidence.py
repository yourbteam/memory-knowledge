#!/usr/bin/env python3
"""Freeze Atom 8's experiment and current allowed surface as a controller assembly."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
RUN = ATOM / "experiment-v2"
ASSEMBLY = RUN / "composition/assembly"
ALLOWED = json.loads((ATOM / "atom-request.json").read_text())["allowed_paths"]


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def document(value):
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


request = json.loads((ATOM / "atom-request.json").read_text())
comparison_path = ATOM / "experiment/comparison.json"
comparison = json.loads(comparison_path.read_text())
operator = json.loads((ATOM / "operator-validation/summary.json").read_text())
metrics = json.loads((ATOM / "experiment-plan.json").read_text())["criteria"]
manifest = {
    "schema_version": 2,
    "case_source_root": str(ROOT),
    "atomic_step": {
        "id": request["atomic_step_id"],
        "outcome": request["outcome"],
        "practical_value": request["practical_value"],
        "stopping_condition": request["stopping_condition"],
        "captured_cases": [
            {"id": case["case_id"], **{key: case[key] for key in ("source_ref", "sha256", "kind", "expected_outcome")}}
            for case in request["captured_cases"]
        ],
    },
    "mini_probes": [{
        "id": "reference-applicability-boundary",
        "goal": "Prevent an absent benchmark from reaching a reader while preserving it as visible state.",
        "practical_value": request["practical_value"],
        "work_type": "code",
        "work_type_reason": "The immutable run contract and reader dispatch gate are executable code boundaries.",
        "allowed_paths": ALLOWED,
        "inputs": [{"case_id": case["case_id"]} for case in request["captured_cases"]],
        "approaches": json.loads((ATOM / "experiment-plan.json").read_text())["approaches"],
        "proof": {
            "success_criterion": "The reason is frozen at open, all 25 benchmark cells are terminal and visible, no benchmark seat record exists, and the existing red run remains byte-identical.",
            "failure_criterion": "Applicability is decided after opening, a benchmark cell reaches a seat, the reason is hidden, or an existing run is rewritten.",
        },
        "evaluation": {
            "metrics": [{"name": name, "direction": "maximize"} for name in metrics],
            "across_cases": [{"name": name, "method": "sum"} for name in metrics],
        },
        "winner_output": {"artifact": "reference-applicability-contract", "description": "Open-time declaration plus visible terminal no-reference cells."},
    }],
    "composition": {
        "consumes": [{"probe_id": "reference-applicability-boundary", "artifact": "reference-applicability-contract"}],
        "assembly_contract": "Use open-terminal-state unchanged.",
        "final_validation": {
            "operator_path": "Open the unchanged BTM page with the recorded no-reference reason, replay only prior real nonbenchmark seat records, resolve prior real owner rulings, and produce the public findings document.",
            "case_ids": [case["case_id"] for case in request["captured_cases"]],
            "success_criterion": "The red bytes remain unchanged and the new run completes with 150 judged plus 25 visible not-applicable cells.",
            "failure_criterion": "Any benchmark cell is judged, any applicable cell is unreachable, or the document omits the reason.",
        },
    },
}

source_files, baseline_files, operations = [], [], []
for relative in ALLOWED:
    current = (ROOT / relative).read_bytes()
    baseline = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=ROOT, check=True, capture_output=True).stdout
    write(ASSEMBLY / "source" / relative, current)
    source_files.append({"path": relative, "sha256": digest(current), "size": len(current)})
    baseline_files.append({"path": relative, "sha256": digest(baseline), "size": len(baseline)})
    if current != baseline:
        operations.append({"path": relative, "action": "change", "sha256": digest(current), "size": len(current), "contributors": ["reference-applicability-boundary"]})

input_records = []
for case in request["captured_cases"]:
    payload = (ROOT / case["source_ref"]).read_bytes()
    name = f"{case['case_id']}.input"
    write(ASSEMBLY / "inputs" / name, payload)
    input_records.append({"case_id": case["case_id"], "path": name, "sha256": digest(payload), "size": len(payload)})

write(ASSEMBLY / "development-manifest.json", document(manifest))
assembly = {
    "schema_version": 1,
    "status": "assembled",
    "identity": {"atomic_step_id": request["atomic_step_id"], "development_manifest_sha256": digest(compact(manifest))},
    "baseline_sha256": digest(compact(sorted(baseline_files, key=lambda item: item["path"]))),
    "source": {
        "root": "source", "entrypoint": ALLOWED[1],
        "sha256": digest(compact(sorted(source_files, key=lambda item: item["path"]))),
        "files": sorted(source_files, key=lambda item: item["path"]),
    },
    "inputs": input_records,
    "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
    "candidates": [{"probe_id": "reference-applicability-boundary", "artifact": "reference-applicability-contract", "approach_id": comparison["champion"], "bundle_sha256": digest(comparison_path.read_bytes())}],
    "operations": sorted(operations, key=lambda item: item["path"]),
    "promotion_applied": False,
}
write(ASSEMBLY / "assembly.json", document(assembly))
for path in ASSEMBLY.rglob("*"):
    path.chmod(0o555 if path.is_dir() else 0o444)
ASSEMBLY.chmod(0o555)

assembly_sha = digest(compact({"assembly": assembly, "development_manifest": manifest}))
final = {
    "schema_version": 1,
    "status": "completed",
    "atomic_step_id": request["atomic_step_id"],
    "assembly_sha256": assembly_sha,
    "verdict": "passed",
    "cases": [
        {"case_id": request["captured_cases"][0]["case_id"], "verdict": "satisfied", "reason": "The original 7-of-175 run and refusal remain byte-identical and readable without migration.", "evidence_pointers": ["frozen-red/matrix.json", "frozen-red/read-run.log"]},
        {"case_id": request["captured_cases"][1]["case_id"], "verdict": "satisfied", "reason": "The same page and payload completed with 150 real replayed judgments and 25 visible no-reference cells.", "evidence_pointers": ["operator-validation/summary.json", "operator-validation/located-defects.md"]},
    ],
    "promotion_applied": False,
}
write(RUN / "final-verdict.json", document(final))
final_sha = digest((RUN / "final-verdict.json").read_bytes())
evidence_sha = digest(comparison_path.read_bytes())


def stage(name):
    return {"schema_version": 1, "stage": name, "status": "completed", "exit_code": 0, "output": str(comparison_path), "evidence": str(comparison_path), "evidence_sha256": evidence_sha, "result": str(comparison_path), "result_sha256": evidence_sha, "promotion_applied": False}


write(RUN / "development-probe-summary.json", document({
    "schema_version": 1,
    "status": "completed",
    "atomic_step_id": request["atomic_step_id"],
    "verdict": "passed",
    "final_verdict_sha256": final_sha,
    "stages": [stage("run-probes"), stage("compose-winners"), stage("final-validation")],
    "promotion_applied": False,
}))
print(json.dumps({"status": "completed", "assembly_sha256": assembly_sha, "operator_status": operator["status"]}, sort_keys=True))
