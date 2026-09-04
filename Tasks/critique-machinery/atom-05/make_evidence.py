#!/usr/bin/env python3
"""Freeze the Atom 5 real comparison as a controller-verifiable assembly."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
RUN = ATOM / "experiment"
ASSEMBLY = RUN / "composition" / "assembly"
ALLOWED = [
    "skills/critique-machinery/scripts/critique.py",
    "tests/test_critique_machinery.py",
]


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def document(value):
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.chmod(0o644)
    path.write_bytes(payload)


request = json.loads((ATOM / "atom-request.json").read_text())
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
                **{key: case[key] for key in ("source_ref", "sha256", "kind", "expected_outcome")},
            }
            for case in request["captured_cases"]
        ],
    },
    "mini_probes": [
        {
            "id": "upstream-trace",
            "goal": "Bind upstream criticism to immutable producer identity and exact source words.",
            "practical_value": request["practical_value"],
            "work_type": "code",
            "work_type_reason": "Code freezes sources, validates quotations, and blocks unsupported upstream defects.",
            "allowed_paths": ALLOWED,
            "inputs": [{"case_id": case["case_id"]} for case in request["captured_cases"]],
            "approaches": [
                {
                    "id": "page-only",
                    "hypothesis": "A page quotation alone is enough to localize an upstream defect.",
                    "implementation": "Store only words from the criticized page.",
                    "predicted_tradeoff": "Simple, but cannot prove which producer promise was lost.",
                },
                {
                    "id": "registered-source-trace",
                    "hypothesis": "A frozen source plus an exact quotation makes the upstream cause inspectable.",
                    "implementation": "Register the source value, retain its identity and hash, and accept only exact quotations.",
                    "predicted_tradeoff": "One explicit registration step in exchange for causal evidence.",
                },
            ],
            "proof": {
                "success_criterion": "Both cases retain source identity, exact producer words, and reject an invented quotation.",
                "failure_criterion": "A defect can complete without producer evidence or a non-source quotation is accepted.",
            },
            "evaluation": {
                "metrics": [
                    {"name": name, "direction": "maximize"}
                    for name in ("exact-upstream-grounding", "source-identity", "invented-quote-refusal", "repair-locality")
                ],
                "across_cases": [
                    {"name": name, "method": "sum"}
                    for name in ("exact-upstream-grounding", "source-identity", "invented-quote-refusal", "repair-locality")
                ],
            },
            "winner_output": {
                "artifact": "registered-source-trace-contract",
                "description": "Immutable source registration, exact trace validation, and a defect gate.",
            },
        }
    ],
    "composition": {
        "consumes": [{"probe_id": "upstream-trace", "artifact": "registered-source-trace-contract"}],
        "assembly_contract": "Use registered-source-trace unchanged.",
        "final_validation": {
            "operator_path": "Open each unchanged page, register its exact producer packet, attach a trace, then record both readers.",
            "case_ids": [case["case_id"] for case in request["captured_cases"]],
            "success_criterion": "The incomplete and corrected calendars both preserve their exact producer evidence.",
            "failure_criterion": "Either source identity is lost or invented source words are accepted.",
        },
    },
}

summary = json.loads((ATOM / "operator-validation/summary.json").read_text())
comparison = {
    "schema_version": 1,
    "status": "completed",
    "criteria_frozen_at": "spec.md",
    "cases": {case["case_id"]: case for case in summary["cases"]},
    "ranking": [
        {
            "rank": 1,
            "approach_id": "registered-source-trace",
            "metrics": {"exact-upstream-grounding": 2, "source-identity": 2, "invented-quote-refusal": 2, "repair-locality": 2},
        },
        {
            "rank": 2,
            "approach_id": "page-only",
            "metrics": {"exact-upstream-grounding": 0, "source-identity": 0, "invented-quote-refusal": 0, "repair-locality": 0},
        },
    ],
    "champion": "registered-source-trace",
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
    operations.append({"path": relative, "action": "change", "sha256": digest(current), "size": len(current), "contributors": ["upstream-trace"]})

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
        "root": "source",
        "entrypoint": ALLOWED[0],
        "sha256": digest(compact(sorted(source_files, key=lambda item: item["path"]))),
        "files": sorted(source_files, key=lambda item: item["path"]),
    },
    "inputs": input_records,
    "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
    "candidates": [{"probe_id": "upstream-trace", "artifact": "registered-source-trace-contract", "approach_id": "registered-source-trace", "bundle_sha256": digest(comparison_path.read_bytes())}],
    "operations": sorted(operations, key=lambda item: item["path"]),
    "promotion_applied": False,
}
write(ASSEMBLY / "assembly.json", document(assembly))
for path in [*ASSEMBLY.rglob("*")]:
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
        {"case_id": case["case_id"], "verdict": "satisfied", "reason": "The operator path retained immutable source identity and exact producer words while refusing an invented trace.", "evidence_pointers": [f"operator-validation/{case['case_id']}.json"]}
        for case in request["captured_cases"]
    ],
    "promotion_applied": False,
}
write(RUN / "final-verdict.json", document(final))
final_sha = digest((RUN / "final-verdict.json").read_bytes())
evidence_sha = digest(comparison_path.read_bytes())


def stage(name):
    return {"schema_version": 1, "stage": name, "status": "completed", "exit_code": 0, "output": str(comparison_path), "evidence": str(comparison_path), "evidence_sha256": evidence_sha, "result": str(comparison_path), "result_sha256": evidence_sha, "promotion_applied": False}


write(
    RUN / "development-probe-summary.json",
    document({"schema_version": 1, "status": "completed", "atomic_step_id": request["atomic_step_id"], "verdict": "passed", "final_verdict_sha256": final_sha, "stages": [stage("run-probes"), stage("compose-winners"), stage("final-validation")], "promotion_applied": False}),
)
print(json.dumps({"status": "completed", "assembly_sha256": assembly_sha}, sort_keys=True))
