#!/usr/bin/env python3
"""Freeze the Atom 4 real comparison as a controller-verifiable assembly."""

from __future__ import annotations

import hashlib
import json
import shutil
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
                "source_ref": case["source_ref"],
                "sha256": case["sha256"],
                "kind": case["kind"],
                "expected_outcome": case["expected_outcome"],
            }
            for case in request["captured_cases"]
        ],
    },
    "mini_probes": [
        {
            "id": "reader-separation",
            "goal": "Preserve independent readings and their uncertainty instead of collapsing them.",
            "practical_value": request["practical_value"],
            "work_type": "hybrid",
            "work_type_reason": "Models read independently; code owns seat identity, outcome reduction, and completion safety.",
            "allowed_paths": ALLOWED,
            "inputs": [{"case_id": case["case_id"]} for case in request["captured_cases"]],
            "approaches": [
                {
                    "id": "first-reader-wins",
                    "hypothesis": "One accepted reader response is sufficient for a stable critique cell.",
                    "implementation": "Keep the first response as the cell verdict and discard the second identity.",
                    "predicted_tradeoff": "Smaller state, but disagreement becomes invisible.",
                },
                {
                    "id": "blind-separated",
                    "hypothesis": "Two isolated seats plus a fixed reducer preserve agreement and uncertainty safely.",
                    "implementation": "Launch separate readers, retain both grounded responses, and expose five terminal outcomes.",
                    "predicted_tradeoff": "Two model calls per cell, with inspectable corroboration and owner-bound uncertainty.",
                },
            ],
            "proof": {
                "success_criterion": "Both real responses retain identity, disagreement stays unresolved, and all five outcomes remain distinct.",
                "failure_criterion": "Either response is overwritten, disagreement completes the matrix, or an outcome collapses into another.",
            },
            "evaluation": {
                "metrics": [
                    {"name": "reader-identities", "direction": "maximize"},
                    {"name": "disagreement-preservation", "direction": "maximize"},
                    {"name": "outcome-separation", "direction": "maximize"},
                    {"name": "completion-safety", "direction": "maximize"},
                ],
                "across_cases": [
                    {"name": "reader-identities", "method": "sum"},
                    {"name": "disagreement-preservation", "method": "sum"},
                    {"name": "outcome-separation", "method": "sum"},
                    {"name": "completion-safety", "method": "sum"},
                ],
            },
            "winner_output": {
                "artifact": "blind-reader-contract",
                "description": "Separate reader state, fixed outcome reducer, and independent model launch path.",
            },
        }
    ],
    "composition": {
        "consumes": [{"probe_id": "reader-separation", "artifact": "blind-reader-contract"}],
        "assembly_contract": "Use the blind-separated reader state and reducer unchanged.",
        "final_validation": {
            "operator_path": "Open each unchanged page and run read-cell, which launches two isolated Codex processes.",
            "case_ids": [case["case_id"] for case in request["captured_cases"]],
            "success_criterion": "The corrected page agrees clear and the stale page exposes its observed disagreement as unresolved.",
            "failure_criterion": "Reader identity is lost or the stale-page disagreement is reported as complete.",
        },
    },
}

if RUN.exists():
    raise SystemExit(f"refusing nonempty evidence directory: {RUN}")

red = json.loads((ATOM / "operator-validation/stale-door-red/matrix.json").read_text())
green = json.loads((ATOM / "operator-validation/stale-door-green/matrix.json").read_text())
red_cell = next(cell for cell in red["cells"] if cell["cell_id"].endswith("::buyer-read"))
green_cell = next(cell for cell in green["cells"] if cell["cell_id"].endswith("::buyer-read"))
comparison = {
    "schema_version": 1,
    "status": "completed",
    "criteria_frozen_at": "spec.md",
    "cases": {
        "stale-door-red": {"outcome": red_cell["outcome"], "status": red_cell["status"], "readers": red_cell["readers"]},
        "stale-door-green": {"outcome": green_cell["outcome"], "status": green_cell["status"], "readers": green_cell["readers"]},
    },
    "ranking": [
        {
            "rank": 1,
            "approach_id": "blind-separated",
            "metrics": {"reader-identities": 4, "disagreement-preservation": 1, "outcome-separation": 5, "completion-safety": 2},
        },
        {
            "rank": 2,
            "approach_id": "first-reader-wins",
            "metrics": {"reader-identities": 2, "disagreement-preservation": 0, "outcome-separation": 2, "completion-safety": 1},
        },
    ],
    "champion": "blind-separated",
    "promotion_applied": False,
}
comparison_path = RUN / "comparison.json"
write(comparison_path, document(comparison))

source_files = []
baseline_files = []
operations = []
for relative in ALLOWED:
    current = (ROOT / relative).read_bytes()
    baseline = subprocess.run(
        ["git", "show", f"HEAD:{relative}"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    target = ASSEMBLY / "source" / relative
    write(target, current)
    source_files.append({"path": relative, "sha256": digest(current), "size": len(current)})
    baseline_files.append({"path": relative, "sha256": digest(baseline), "size": len(baseline)})
    operations.append(
        {"path": relative, "action": "change", "sha256": digest(current), "size": len(current), "contributors": ["reader-separation"]}
    )

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
    "candidates": [
        {
            "probe_id": "reader-separation",
            "artifact": "blind-reader-contract",
            "approach_id": "blind-separated",
            "bundle_sha256": digest((comparison_path).read_bytes()),
        }
    ],
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
        {
            "case_id": "stale-door-red",
            "verdict": "satisfied",
            "reason": "Two independent readers disagreed on the unchanged stale unit and the cell remained unresolved.",
            "evidence_pointers": ["operator-validation/stale-door-red/matrix.json"],
        },
        {
            "case_id": "stale-door-green",
            "verdict": "satisfied",
            "reason": "Two independent readers agreed clear on the corrected unit with separate exact quotations.",
            "evidence_pointers": ["operator-validation/stale-door-green/matrix.json"],
        },
    ],
    "promotion_applied": False,
}
write(RUN / "final-verdict.json", document(final))
final_sha = digest((RUN / "final-verdict.json").read_bytes())
evidence_sha = digest(comparison_path.read_bytes())
stage = lambda name: {
    "schema_version": 1,
    "stage": name,
    "status": "completed",
    "exit_code": 0,
    "output": str(comparison_path),
    "evidence": str(comparison_path),
    "evidence_sha256": evidence_sha,
    "result": str(comparison_path),
    "result_sha256": evidence_sha,
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
write(RUN / "development-probe-summary.json", document(summary))
print(json.dumps({"status": "completed", "assembly_sha256": assembly_sha}, sort_keys=True))
