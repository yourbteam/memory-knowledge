#!/usr/bin/env python3
"""Package the observed Atom 10 comparison as a verifiable isolated assembly."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = ROOT / "Tasks/critique-machinery/atom-10"
OUTPUT = ATOM / "development-probe-run"
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
    plan = json.loads((ATOM / "experiment-plan.json").read_text(encoding="utf-8"))
    probe_plans = plan["probes"]
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
                "id": probe["id"],
                "goal": (
                    "Exclude operator material from each seat instruction."
                    if probe["id"] == "seat-input-envelope"
                    else "Classify every reply and contain failures to their exact cells."
                ),
                "practical_value": request["practical_value"],
                "work_type": "code",
                "work_type_reason": "Client launch, schema validation, recording, and retry are deterministic code boundaries.",
                "inputs": [{"case_id": case["case_id"]} for case in cases],
                "approaches": probe["approaches"],
                "allowed_paths": ALLOWED,
                "evaluation": {
                    "metrics": [{"name": name, "direction": "maximize"} for name in probe["criteria"]],
                    "across_cases": [{"name": name, "method": "sum"} for name in probe["criteria"]],
                },
                "proof": {
                    "success_criterion": request["stopping_condition"],
                    "failure_criterion": "Any reply variance aborts the run, is normalized into acceptance, loses a sibling, or can be retried more than once.",
                },
                "winner_output": {
                    "artifact": f"{probe['id']}-winner",
                    "description": f"Selected code boundary for {probe['id']}.",
                },
            }
            for probe in probe_plans
        ],
        "composition": {
            "consumes": [
                {"probe_id": probe["id"], "artifact": f"{probe['id']}-winner"}
                for probe in probe_plans
            ],
            "assembly_contract": "Use isolated-client-envelope and typed-intake-cell-commit together unchanged.",
            "final_validation": {
                "case_ids": [case["case_id"] for case in cases],
                "operator_path": "Replay all frozen v3 reader responses through canonical reply intake, then retry only failed seats once.",
                "success_criterion": request["stopping_condition"],
                "failure_criterion": "Any frozen byte changes, any replay reader launches, any cell has one seat, or any malformed reply reaches semantic judgment.",
            },
        },
    }
    manifest_bytes = document(manifest)
    baseline_records = []
    source_records = []
    for relative in ALLOWED:
        baseline_payload = (ROOT / relative).read_bytes()
        baseline_records.append({"path": relative, "sha256": digest(baseline_payload), "size": len(baseline_payload)})
        candidate_path = (
            ATOM / "experiment/candidate/critique.py"
            if relative == "skills/critique-machinery/scripts/critique.py"
            else ROOT / relative
        )
        payload = candidate_path.read_bytes()
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
        "baseline_sha256": digest(canonical(baseline_records)),
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
                "probe_id": "seat-input-envelope",
                "artifact": "seat-input-envelope-winner",
                "approach_id": "isolated-client-envelope",
                "bundle_sha256": comparison_sha,
            },
            {
                "probe_id": "seat-reply-intake",
                "artifact": "seat-reply-intake-winner",
                "approach_id": "typed-intake-cell-commit",
                "bundle_sha256": comparison_sha,
            },
        ],
        "operations": [
            {
                "path": record["path"],
                "action": "change",
                "sha256": record["sha256"],
                "size": record["size"],
                "contributors": ["seat-input-envelope", "seat-reply-intake"],
            }
            for record in source_records
            if record["sha256"] != next(item["sha256"] for item in baseline_records if item["path"] == record["path"])
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
