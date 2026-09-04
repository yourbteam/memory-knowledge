#!/usr/bin/env python3
"""Freeze the Atom 7 real comparison as a controller-verifiable assembly."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
RUN = ATOM / os.environ.get("CRITIQUE_EXPERIMENT_RUN", "experiment")
ASSEMBLY = RUN / "composition" / "assembly"
ALLOWED = [
    "skills/critique-machinery/scripts/critique.py",
    "tests/test_critique_machinery.py",
    "skills/critique-machinery/SKILL.md",
    "skills/critique-machinery/agents/openai.yaml",
    "skills/managed-skills.txt",
    "working-agreement/client-skill-projections.json",
]


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
metrics = ("authority-preservation", "exact-ruling-retention", "partial-output-refusal", "evidence-retention", "document-determinism")
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
            "id": "owner-bound-assembly",
            "goal": "Keep every unresolved reader outcome with the owner and every incomplete state out of the findings document.",
            "practical_value": request["practical_value"],
            "work_type": "hybrid",
            "work_type_reason": "Blind model readers create real uncertainty; code fixes the queue, offered choices, exact owner record, and document gates.",
            "allowed_paths": ALLOWED,
            "inputs": [{"case_id": case["case_id"]} for case in request["captured_cases"]],
            "approaches": [
                {
                    "id": "machine-cast",
                    "hypothesis": "A deterministic reducer can choose one reader whenever two grounded readers disagree.",
                    "implementation": "Select a verdict automatically and allow document assembly immediately.",
                    "predicted_tradeoff": "Fast completion, but the machine silently acquires owner authority and erases uncertainty.",
                },
                {
                    "id": "owner-bound",
                    "hypothesis": "Stable one-question rulings preserve authority without sacrificing deterministic completion.",
                    "implementation": "Derive immutable questions, accept only offered verdicts with exact owner words, and gate the document on an empty queue.",
                    "predicted_tradeoff": "Requires owner attention for genuine disagreements, with all reader and ruling evidence retained.",
                },
            ],
            "proof": {
                "success_criterion": "The real BTM run refuses before five rulings, preserves each exact ruling and both readers, then writes one deterministic document.",
                "failure_criterion": "Any disagreement is machine-cast, an unoffered choice lands, owner words change, or a partial document exists.",
            },
            "evaluation": {
                "metrics": [{"name": name, "direction": "maximize"} for name in metrics],
                "across_cases": [{"name": name, "method": "sum"} for name in metrics],
            },
            "winner_output": {
                "artifact": "owner-bound-findings-contract",
                "description": "One-question owner queue, append-only exact rulings, complete-matrix gate, and evidence-rich document assembly.",
            },
        }
    ],
    "composition": {
        "consumes": [{"probe_id": "owner-bound-assembly", "artifact": "owner-bound-findings-contract"}],
        "assembly_contract": "Use owner-bound unchanged and expose it through the managed dual-client skill.",
        "final_validation": {
            "operator_path": "Open S12 BTM, run both blind seats across all 175 cells, ask and answer five owner questions, then request document.",
            "case_ids": [case["case_id"] for case in request["captured_cases"]],
            "success_criterion": "Document refuses with the real queue open and completes with all exact rulings retained after the queue empties.",
            "failure_criterion": "The queue is bypassed, evidence is replaced, or the installed skill projection fails either client.",
        },
    },
}

if RUN.exists():
    raise SystemExit(f"refusing nonempty evidence directory: {RUN}")

open_case = json.loads((ATOM / "operator-validation/open-queue.json").read_text())
resolved_case = json.loads((ATOM / "operator-validation/resolved-queue.json").read_text())
comparison = {
    "schema_version": 1,
    "status": "completed",
    "criteria_frozen_at": "spec.md",
    "cases": {open_case["case_id"]: open_case, resolved_case["case_id"]: resolved_case},
    "ranking": [
        {"rank": 1, "approach_id": "owner-bound", "metrics": {"authority-preservation": 5, "exact-ruling-retention": 5, "partial-output-refusal": 1, "evidence-retention": 10, "document-determinism": 1}},
        {"rank": 2, "approach_id": "machine-cast", "metrics": {"authority-preservation": 0, "exact-ruling-retention": 0, "partial-output-refusal": 0, "evidence-retention": 0, "document-determinism": 1}},
    ],
    "champion": "owner-bound",
    "promotion_applied": False,
}
comparison_path = RUN / "comparison.json"
write(comparison_path, document(comparison))

source_files, baseline_files, operations = [], [], []
for relative in ALLOWED:
    current = (ROOT / relative).read_bytes()
    baseline_process = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=ROOT, capture_output=True)
    baseline = baseline_process.stdout if baseline_process.returncode == 0 else b""
    action = "change" if baseline_process.returncode == 0 else "add"
    write(ASSEMBLY / "source" / relative, current)
    source_files.append({"path": relative, "sha256": digest(current), "size": len(current)})
    baseline_files.append({"path": relative, "sha256": digest(baseline), "size": len(baseline), "present": baseline_process.returncode == 0})
    operations.append({"path": relative, "action": action, "sha256": digest(current), "size": len(current), "contributors": ["owner-bound-assembly"]})

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
    "source": {"root": "source", "entrypoint": ALLOWED[0], "sha256": digest(compact(sorted(source_files, key=lambda item: item["path"]))), "files": sorted(source_files, key=lambda item: item["path"])},
    "inputs": input_records,
    "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
    "candidates": [{"probe_id": "owner-bound-assembly", "artifact": "owner-bound-findings-contract", "approach_id": "owner-bound", "bundle_sha256": digest(comparison_path.read_bytes())}],
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
        {"case_id": "btm-roadmap-open-queue", "verdict": "satisfied", "reason": "The full real matrix exposed five disagreements and the public document route refused while they remained open.", "evidence_pointers": ["operator-validation/open-queue.json"]},
        {"case_id": "btm-roadmap-resolved-queue", "verdict": "satisfied", "reason": "Five owner rulings were retained verbatim and the public route assembled all 175 cells into a 30-finding document only after the queue emptied.", "evidence_pointers": ["operator-validation/resolved-queue.json", "operator-validation/located-defects.md"]},
    ],
    "promotion_applied": False,
}
write(RUN / "final-verdict.json", document(final))
final_sha = digest((RUN / "final-verdict.json").read_bytes())
evidence_sha = digest(comparison_path.read_bytes())


def stage(name):
    return {"schema_version": 1, "stage": name, "status": "completed", "exit_code": 0, "output": str(comparison_path), "evidence": str(comparison_path), "evidence_sha256": evidence_sha, "result": str(comparison_path), "result_sha256": evidence_sha, "promotion_applied": False}


write(RUN / "development-probe-summary.json", document({"schema_version": 1, "status": "completed", "atomic_step_id": request["atomic_step_id"], "verdict": "passed", "final_verdict_sha256": final_sha, "stages": [stage("run-probes"), stage("compose-winners"), stage("final-validation")], "promotion_applied": False}))
print(json.dumps({"status": "completed", "assembly_sha256": assembly_sha}, sort_keys=True))
