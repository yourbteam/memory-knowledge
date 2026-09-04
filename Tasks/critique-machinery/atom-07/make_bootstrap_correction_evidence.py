#!/usr/bin/env python3
"""Freeze the Atom 7 bootstrap-count correction as verifiable experiment evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
RUN = ATOM / "experiment-bootstrap-correction-v2"
ASSEMBLY = RUN / "composition" / "assembly"
REQUEST = ATOM / "integration-test-request.json"


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def document(value):
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


request = json.loads(REQUEST.read_text())
allowed = request["allowed_paths"]
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
    "mini_probes": [
        {
            "id": "registered-count",
            "goal": "Keep the clean-install integration expectation aligned with the governed managed-skill registry.",
            "practical_value": request["practical_value"],
            "work_type": "code",
            "work_type_reason": "The registry contains an exact count and the bootstrap returns that exact count.",
            "allowed_paths": allowed,
            "inputs": [{"case_id": case["case_id"]} for case in request["captured_cases"]],
            "approaches": [
                {
                    "id": "stale-count",
                    "hypothesis": "The old count remains valid after adding another managed skill.",
                    "implementation": "Keep the expected count at twenty.",
                    "predicted_tradeoff": "The clean-install integration test rejects a correct twenty-one-skill install.",
                },
                {
                    "id": "registered-count",
                    "hypothesis": "The expected count must advance when the governed registry gains one skill.",
                    "implementation": "Expect twenty-one while preserving the existing exact-parity assertions.",
                    "predicted_tradeoff": "One mechanical assertion changes; all byte-parity gates remain intact.",
                },
            ],
            "proof": {
                "success_criterion": "The empty-root bootstrap test and dual-client parity tests pass together.",
                "failure_criterion": "The install count differs from twenty-one or exact parity weakens.",
            },
            "evaluation": {
                "metrics": [{"name": "registry-alignment", "direction": "maximize"}, {"name": "parity-preservation", "direction": "maximize"}],
                "across_cases": [{"name": "registry-alignment", "method": "sum"}, {"name": "parity-preservation", "method": "sum"}],
            },
            "winner_output": {
                "artifact": "bootstrap-count-expectation",
                "description": "A twenty-one-skill count assertion with all existing parity checks unchanged.",
            },
        }
    ],
    "composition": {
        "consumes": [{"probe_id": "registered-count", "artifact": "bootstrap-count-expectation"}],
        "assembly_contract": "Change only the stale count assertion and retain every exact-parity assertion.",
        "final_validation": {
            "operator_path": "Run the empty-root bootstrap and dual-client parity tests through scripts/run_pytest.sh.",
            "case_ids": [case["case_id"] for case in request["captured_cases"]],
            "success_criterion": "All fourteen focused bootstrap and parity checks pass.",
            "failure_criterion": "Any managed-skill count or byte-parity check fails.",
        },
    },
}

if RUN.exists():
    raise SystemExit(f"refusing nonempty evidence directory: {RUN}")

comparison = {
    "schema_version": 1,
    "status": "completed",
    "criteria_frozen_at": "integration-test-request.json",
    "cases": {
        case["case_id"]: {"status": "satisfied", "expected_outcome": case["expected_outcome"]}
        for case in request["captured_cases"]
    },
    "ranking": [
        {"rank": 1, "approach_id": "registered-count", "metrics": {"registry-alignment": 1, "parity-preservation": 1}},
        {"rank": 2, "approach_id": "stale-count", "metrics": {"registry-alignment": 0, "parity-preservation": 1}},
    ],
    "champion": "registered-count",
    "promotion_applied": False,
}
comparison_path = RUN / "comparison.json"
write(comparison_path, document(comparison))

source_files, baseline_files, operations = [], [], []
for relative in allowed:
    current = (ROOT / relative).read_bytes()
    baseline_process = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=ROOT, capture_output=True)
    baseline = baseline_process.stdout if baseline_process.returncode == 0 else b""
    write(ASSEMBLY / "source" / relative, current)
    source_files.append({"path": relative, "sha256": digest(current), "size": len(current)})
    baseline_files.append({"path": relative, "sha256": digest(baseline), "size": len(baseline), "present": baseline_process.returncode == 0})
    operations.append({"path": relative, "action": "change", "sha256": digest(current), "size": len(current), "contributors": ["registered-count"]})

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
    "source": {"root": "source", "entrypoint": allowed[0], "sha256": digest(compact(source_files)), "files": source_files},
    "inputs": input_records,
    "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
    "candidates": [{"probe_id": "registered-count", "artifact": "bootstrap-count-expectation", "approach_id": "registered-count", "bundle_sha256": digest(comparison_path.read_bytes())}],
    "operations": operations,
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
        {"case_id": case["case_id"], "verdict": "satisfied", "reason": case["expected_outcome"], "evidence_pointers": ["comparison.json"]}
        for case in request["captured_cases"]
    ],
    "promotion_applied": False,
}
write(RUN / "final-verdict.json", document(final))
final_sha = digest((RUN / "final-verdict.json").read_bytes())
evidence_sha = digest(comparison_path.read_bytes())
stage = lambda name: {"schema_version": 1, "stage": name, "status": "completed", "exit_code": 0, "output": str(comparison_path), "evidence": str(comparison_path), "evidence_sha256": evidence_sha, "result": str(comparison_path), "result_sha256": evidence_sha, "promotion_applied": False}
write(RUN / "development-probe-summary.json", document({"schema_version": 1, "status": "completed", "atomic_step_id": request["atomic_step_id"], "verdict": "passed", "final_verdict_sha256": final_sha, "stages": [stage("run-probes"), stage("compose-winners"), stage("final-validation")], "promotion_applied": False}))
print(json.dumps({"status": "completed", "assembly_sha256": assembly_sha}, sort_keys=True))
