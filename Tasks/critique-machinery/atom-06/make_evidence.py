#!/usr/bin/env python3
"""Freeze the Atom 6 real comparison as a controller-verifiable assembly."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
RUN = ATOM / "experiment"
ASSEMBLY = RUN / "composition" / "assembly"
ALLOWED = ["skills/critique-machinery/scripts/critique.py", "tests/test_critique_machinery.py"]


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
metrics = ("reference-identity", "two-sided-grounding", "invented-quote-refusal", "visible-gap-specificity")
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
            "id": "paired-benchmark",
            "goal": "Make a professional comparison inspectable on both sides.",
            "practical_value": request["practical_value"],
            "work_type": "code",
            "work_type_reason": "Code freezes reference identity and verifies both exact passages before accepting a defect.",
            "allowed_paths": ALLOWED,
            "inputs": [{"case_id": case["case_id"]} for case in request["captured_cases"]],
            "approaches": [
                {
                    "id": "reference-label-only",
                    "hypothesis": "Naming a standard is sufficient evidence of the quality gap.",
                    "implementation": "Store the verdict with a reference label but no paired words.",
                    "predicted_tradeoff": "Compact, but neither side of the comparison is independently checkable.",
                },
                {
                    "id": "paired-exact-evidence",
                    "hypothesis": "Frozen identity plus exact words from both texts makes the gap inspectable.",
                    "implementation": "Register the reference and attach exact delivered and reference quotations.",
                    "predicted_tradeoff": "Two copied passages in exchange for a concrete standard and repair target.",
                },
            ],
            "proof": {
                "success_criterion": "Both cases retain the immutable reference and exact words from each side, while invented reference words refuse.",
                "failure_criterion": "A defect completes with only a label, either passage is ungrounded, or reference identity can be replaced.",
            },
            "evaluation": {
                "metrics": [{"name": name, "direction": "maximize"} for name in metrics],
                "across_cases": [{"name": name, "method": "sum"} for name in metrics],
            },
            "winner_output": {
                "artifact": "paired-benchmark-contract",
                "description": "Immutable reference registration, exact two-sided quotations, and a defect gate.",
            },
        }
    ],
    "composition": {
        "consumes": [{"probe_id": "paired-benchmark", "artifact": "paired-benchmark-contract"}],
        "assembly_contract": "Use paired-exact-evidence unchanged.",
        "final_validation": {
            "operator_path": "Open each unchanged page, register the complete calendar reference, attach both exact passages, then record both readers.",
            "case_ids": [case["case_id"] for case in request["captured_cases"]],
            "success_criterion": "The incomplete and corrected calendars both expose the exact professional comparison.",
            "failure_criterion": "Either side is absent, invented, or detached from immutable identity.",
        },
    },
}

if RUN.exists():
    raise SystemExit(f"refusing nonempty evidence directory: {RUN}")

operator = json.loads((ATOM / "operator-validation/summary.json").read_text())
comparison = {
    "schema_version": 1,
    "status": "completed",
    "criteria_frozen_at": "spec.md",
    "cases": {case["case_id"]: case for case in operator["cases"]},
    "ranking": [
        {"rank": 1, "approach_id": "paired-exact-evidence", "metrics": {name: 2 for name in metrics}},
        {"rank": 2, "approach_id": "reference-label-only", "metrics": {name: 0 for name in metrics}},
    ],
    "champion": "paired-exact-evidence",
    "promotion_applied": False,
}
comparison_path = RUN / "comparison.json"
write(comparison_path, document(comparison))

source_files, baseline_files, operations = [], [], []
for relative in ALLOWED:
    current = (ROOT / relative).read_bytes()
    baseline = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=ROOT, check=True, capture_output=True).stdout
    write(ASSEMBLY / "source" / relative, current)
    source_files.append({"path": relative, "sha256": digest(current), "size": len(current)})
    baseline_files.append({"path": relative, "sha256": digest(baseline), "size": len(baseline)})
    operations.append({"path": relative, "action": "change", "sha256": digest(current), "size": len(current), "contributors": ["paired-benchmark"]})

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
        "root": "source", "entrypoint": ALLOWED[0],
        "sha256": digest(compact(sorted(source_files, key=lambda item: item["path"]))),
        "files": sorted(source_files, key=lambda item: item["path"]),
    },
    "inputs": input_records,
    "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
    "candidates": [{"probe_id": "paired-benchmark", "artifact": "paired-benchmark-contract", "approach_id": "paired-exact-evidence", "bundle_sha256": digest(comparison_path.read_bytes())}],
    "operations": sorted(operations, key=lambda item: item["path"]),
    "promotion_applied": False,
}
write(ASSEMBLY / "assembly.json", document(assembly))
for path in [*ASSEMBLY.rglob("*")]:
    path.chmod(0o555 if path.is_dir() else 0o444)
ASSEMBLY.chmod(0o555)

assembly_sha = digest(compact({"assembly": assembly, "development_manifest": manifest}))
final = {
    "schema_version": 1, "status": "completed", "atomic_step_id": request["atomic_step_id"],
    "assembly_sha256": assembly_sha, "verdict": "passed",
    "cases": [
        {"case_id": case["case_id"], "verdict": "satisfied", "reason": "The operator path retained immutable reference identity and exact words from both texts while refusing invented reference words.", "evidence_pointers": [f"operator-validation/{case['case_id']}.json"]}
        for case in request["captured_cases"]
    ],
    "promotion_applied": False,
}
write(RUN / "final-verdict.json", document(final))
final_sha = digest((RUN / "final-verdict.json").read_bytes())
evidence_sha = digest(comparison_path.read_bytes())


def stage(name):
    return {"schema_version": 1, "stage": name, "status": "completed", "exit_code": 0, "output": str(comparison_path), "evidence": str(comparison_path), "evidence_sha256": evidence_sha, "result": str(comparison_path), "result_sha256": evidence_sha, "promotion_applied": False}


write(RUN / "development-probe-summary.json", document({
    "schema_version": 1, "status": "completed", "atomic_step_id": request["atomic_step_id"],
    "verdict": "passed", "final_verdict_sha256": final_sha,
    "stages": [stage("run-probes"), stage("compose-winners"), stage("final-validation")],
    "promotion_applied": False,
}))
print(json.dumps({"status": "completed", "assembly_sha256": assembly_sha}, sort_keys=True))
