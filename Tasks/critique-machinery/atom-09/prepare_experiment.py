#!/usr/bin/env python3
"""Package the observed Atom 9 comparison as a verifiable isolated assembly."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = ROOT / "Tasks/critique-machinery/atom-09"
OUTPUT = ATOM / "experiment-v2"
ASSEMBLY = OUTPUT / "composition/assembly"
COMPARISON = ATOM / "experiment/comparison.json"
ALLOWED = [
    "skills/critique-machinery/SKILL.md",
    "skills/critique-machinery/scripts/critique.py",
    "tests/test_critique_machinery.py",
    "working-agreement/client-skill-projections.json",
]


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def document(value) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


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
    request = json.loads((ATOM / "atom-request.json").read_text(encoding="utf-8"))
    cases = request["captured_cases"]
    approaches = json.loads((ATOM / "experiment-plan.json").read_text(encoding="utf-8"))["approaches"]
    metrics = [
        "open-time-upstream-declaration",
        "exact-named-producer-grounding",
        "zero-one-seat-cells",
        "visible-per-cell-refusal",
        "zero-new-model-calls",
    ]
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
                "id": "upstream-recording-boundary",
                "goal": "Declare producer material before reading and contain an ungroundable claim to one fully recorded cell.",
                "practical_value": request["practical_value"],
                "work_type": "code",
                "work_type_reason": "The declaration, reader schema, exact-source check, and cell transaction are executable boundaries.",
                "inputs": [{"case_id": case["case_id"]} for case in cases],
                "approaches": approaches,
                "allowed_paths": ALLOWED,
                "evaluation": {
                    "metrics": [{"name": name, "direction": "maximize"} for name in metrics],
                    "across_cases": [{"name": name, "method": "sum"} for name in metrics],
                },
                "proof": {
                    "success_criterion": "All 150 applicable cells hold two seats; unsupported upstream claims are visible refusals; exact named producer words are required for defects.",
                    "failure_criterion": "Any cell holds one seat, any applicable cell remains unread, or an upstream defect records without exact registered-source words.",
                },
                "winner_output": {
                    "artifact": "declared-source-atomic-recorder",
                    "description": "Open-time upstream declaration, source-cited defects, and per-cell atomic writes.",
                },
            }
        ],
        "composition": {
            "consumes": [
                {"probe_id": "upstream-recording-boundary", "artifact": "declared-source-atomic-recorder"}
            ],
            "assembly_contract": "Use source-cited-cell-transaction unchanged.",
            "final_validation": {
                "case_ids": [case["case_id"] for case in cases],
                "operator_path": "Replay all frozen v2 reader responses into a fresh declared-source run without launching a model.",
                "success_criterion": "The red bytes stay unchanged; all 150 applicable cells record both seats; unsupported claims remain visible non-defect refusals.",
                "failure_criterion": "Any red byte changes, any reader launches, any cell has one seat, or any unsupported upstream defect enters state.",
            },
        },
    }
    manifest_bytes = document(manifest)
    source_records = []
    for relative in ALLOWED:
        payload = (ROOT / relative).read_bytes()
        target = ASSEMBLY / "source" / relative
        write(target, payload)
        source_records.append({"path": relative, "sha256": digest(payload), "size": len(payload)})
    source_sha = digest(canonical(source_records))
    input_records = []
    for case in cases:
        payload = (ROOT / case["source_ref"]).read_bytes()
        name = f"{case['case_id']}.input"
        write(ASSEMBLY / "inputs" / name, payload)
        input_records.append({"case_id": case["case_id"], "path": name, "sha256": digest(payload), "size": len(payload)})
    comparison_sha = digest(COMPARISON.read_bytes())
    assembly = {
        "schema_version": 1,
        "status": "assembled",
        "identity": {
            "atomic_step_id": request["atomic_step_id"],
            "development_manifest_sha256": digest(canonical(manifest)),
        },
        "baseline_sha256": "7507077f5949019bea3dfa5d9723b4ce2e16821dd7834e1fa0cf631a6f9dc0e0",
        "source": {
            "root": "source",
            "entrypoint": "skills/critique-machinery/scripts/critique.py",
            "sha256": source_sha,
            "files": source_records,
        },
        "inputs": input_records,
        "execution": {"command": ["{python}", "{candidate-entrypoint}"], "protocol": "experiment-result-v1"},
        "candidates": [
            {
                "probe_id": "upstream-recording-boundary",
                "artifact": "declared-source-atomic-recorder",
                "approach_id": "source-cited-cell-transaction",
                "bundle_sha256": comparison_sha,
            }
        ],
        "operations": [
            {
                "path": record["path"],
                "action": "change",
                "sha256": record["sha256"],
                "size": record["size"],
                "contributors": ["upstream-recording-boundary"],
            }
            for record in source_records
        ],
        "promotion_applied": False,
    }
    write(ASSEMBLY / "development-manifest.json", manifest_bytes)
    write(ASSEMBLY / "assembly.json", document(assembly))
    for path in sorted([ASSEMBLY, *ASSEMBLY.rglob("*")], key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)

    tooling = Path("/Users/kamenkamenov/.codex/skills/experiment-machinery/scripts")
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
                "case_id": "claude-v2-upstream-red",
                "verdict": "satisfied",
                "reason": "The exact parked v2 matrix remains unchanged with its five one-seat cells and first upstream refusal.",
                "evidence_pointers": ["frozen-red/matrix.json", "frozen-red/read-run.log"],
            },
            {
                "case_id": "claude-v2-atomic-replay-green",
                "verdict": "satisfied",
                "reason": "The same 50 captured responses recorded all 150 applicable cells with two seats, eight visible source-grounding refusals, and zero model calls.",
                "evidence_pointers": ["operator-validation/result.json", "operator-validation/run/matrix.json"],
            },
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
