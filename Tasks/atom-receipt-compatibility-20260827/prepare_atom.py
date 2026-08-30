#!/usr/bin/env python3
"""Prepare the receipt-compatibility corrective atom."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else Path("/private/tmp/atom-receipt-compatibility")
ATOM_ID = "accept-current-experiment-stage-receipts"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def tracked(path: str, target: Path) -> None:
    data = subprocess.run(
        ["git", "show", f"HEAD:{path}"], cwd=REPO, check=True, capture_output=True
    ).stdout
    destination = target / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def tracked_tree(path: str, target: Path) -> None:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", path],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    for relative in result.stdout.splitlines():
        tracked(relative, target)


LEGACY_FIELDS = '''STAGE_FIELDS = {
    "schema_version",
    "stage",
    "status",
    "exit_code",
    "output",
    "evidence",
    "evidence_sha256",
    "result",
    "result_sha256",
    "promotion_applied",
}
'''

CURRENT_FIELDS = '''LEGACY_STAGE_FIELDS = {
    "schema_version",
    "stage",
    "status",
    "exit_code",
    "output",
    "evidence",
    "evidence_sha256",
    "result",
    "result_sha256",
    "promotion_applied",
}
CURRENT_STAGE_FIELDS = LEGACY_STAGE_FIELDS | {
    "duration_ms",
    "timeout_ms",
    "timed_out",
    "stdout_sha256",
    "stderr_sha256",
    "timeout",
    "timeout_sha256",
}
'''

OLD_VALIDATION = '''    for index, raw in enumerate(value):
        receipt = _exact(raw, f"stages[{index}]", STAGE_FIELDS, stage)
        expected_stage = EXPERIMENT_STAGES[index]
'''

STRICT_VALIDATION = '''    for index, raw in enumerate(value):
        receipt = _exact(raw, f"stages[{index}]", CURRENT_STAGE_FIELDS, stage)
        expected_stage = EXPERIMENT_STAGES[index]
'''

DUAL_VALIDATION = '''    for index, raw in enumerate(value):
        if type(raw) is not dict:
            raise AtomError(stage, f"stages[{index}] is {type(raw).__name__}; provide one object")
        fields = CURRENT_STAGE_FIELDS if "duration_ms" in raw else LEGACY_STAGE_FIELDS
        receipt = _exact(raw, f"stages[{index}]", fields, stage)
        expected_stage = EXPERIMENT_STAGES[index]
'''

POST_SUCCESS = '''        if receipt["promotion_applied"] is not False:
            raise AtomError(stage, f"stage {expected_stage!r} applied promotion; experiments must remain isolated")
        for field in ("output", "evidence", "evidence_sha256", "result", "result_sha256"):
'''

CURRENT_CHECKS = '''        if receipt["promotion_applied"] is not False:
            raise AtomError(stage, f"stage {expected_stage!r} applied promotion; experiments must remain isolated")
        if fields is CURRENT_STAGE_FIELDS:
            if type(receipt["duration_ms"]) is not int or receipt["duration_ms"] < 0:
                raise AtomError(stage, f"stages[{index}].duration_ms must be one nonnegative integer")
            if type(receipt["timeout_ms"]) is not int or receipt["timeout_ms"] <= 0:
                raise AtomError(stage, f"stages[{index}].timeout_ms must be one positive integer")
            if receipt["timed_out"] is not False:
                raise AtomError(stage, f"successful stage {expected_stage!r} cannot be timed out")
            _sha(receipt["stdout_sha256"], f"stages[{index}].stdout_sha256", stage)
            _sha(receipt["stderr_sha256"], f"stages[{index}].stderr_sha256", stage)
            if receipt["timeout"] is not None or receipt["timeout_sha256"] is not None:
                raise AtomError(stage, f"successful stage {expected_stage!r} cannot carry timeout evidence")
        for field in ("output", "evidence", "evidence_sha256", "result", "result_sha256"):
'''

TEST = r'''

def test_current_experiment_stage_receipts_advance(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "current-experiment"
    experiment(experiment_path, assembly_fixture)
    summary_path = experiment_path / "development-probe-summary.json"
    summary = json.loads(summary_path.read_text())
    for receipt in summary["stages"]:
        receipt.update({
            "duration_ms": 1,
            "timeout_ms": 2700000,
            "timed_out": False,
            "stdout_sha256": "2" * 64,
            "stderr_sha256": "3" * 64,
            "timeout": None,
            "timeout_sha256": None,
        })
    write_json(summary_path, summary)

    result = invoke("record-experiment", run, experiment_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["stage"] == "promotion"
'''

OPERATOR = r'''from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("atom_controller_candidate", root / "skills/atom-building-machinery/scripts/atom_controller.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
case = json.loads(Path(os.environ["EXPERIMENT_INPUT_PATH"]).read_text())
accepted = True
error = None
try:
    module._validate_stage_receipts(case["stages"])
except Exception as exc:
    accepted = False
    error = str(exc)
result = {
    "schema_version": 1,
    "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
    "status": "completed",
    "outcome": {"case_id": case["case_id"], "accepted": accepted, "error": error},
    "metrics": {
        "receipt-correctness": int(accepted),
        "compatibility-breadth": int(accepted),
    },
    "error": None,
}
Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps(result, sort_keys=True) + "\n")
'''

EVALUATOR = r'''import json, sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text())
scores = []
for candidate in request["candidates"]:
    accepted = bool(candidate["outcome"].get("accepted"))
    scores.append({
        "variant_id": candidate["variant_id"],
        "metrics": {
            "receipt-correctness": int(accepted),
            "compatibility-breadth": int(accepted),
        },
    })
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n")
'''

ASSESSMENT = r'''import json, sys
from pathlib import Path
question = json.loads(Path(sys.argv[1]).read_text())
accepted = bool(question["execution_result"]["outcome"].get("accepted"))
response = {
    "case_id": question["case_id"],
    "verdict": "satisfied" if accepted else "not-satisfied",
    "reason": "The assembled controller accepts the declared legitimate Experiment Machinery receipt." if accepted else "The assembled controller rejects the declared legitimate Experiment Machinery receipt.",
    "evidence_pointers": ["execution-result"],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\n")
'''


def patch_candidate(root: Path, *, dual: bool) -> None:
    controller = root / "skills/atom-building-machinery/scripts/atom_controller.py"
    text = controller.read_text()
    if LEGACY_FIELDS not in text or OLD_VALIDATION not in text or POST_SUCCESS not in text:
        raise RuntimeError("controller source boundary changed")
    text = text.replace(LEGACY_FIELDS, CURRENT_FIELDS)
    text = text.replace(OLD_VALIDATION, DUAL_VALIDATION if dual else STRICT_VALIDATION)
    if dual:
        text = text.replace(POST_SUCCESS, CURRENT_CHECKS)
    controller.write_text(text)
    tests = root / "tests/test_atom_building_machinery.py"
    tests.write_text(tests.read_text() + TEST)


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing existing output: {OUT}")
    baseline = OUT / "development/baseline"
    for path in (
        "skills/atom-building-machinery/scripts/atom_controller.py",
        "tests/test_atom_building_machinery.py",
    ):
        tracked(path, baseline)
    tracked_tree("skills/experiment-machinery", baseline)
    (baseline / "operator.py").write_text(OPERATOR)

    strict = OUT / "development/strict-current"
    dual = OUT / "development/dual-schema-exact"
    shutil.copytree(baseline, strict)
    shutil.copytree(baseline, dual)
    patch_candidate(strict, dual=False)
    patch_candidate(dual, dual=True)

    actual = json.loads(Path("/private/tmp/requirements-machinery-promotion-atom-r3/development/complete-run/development-probe-summary.json").read_text())["stages"]
    legacy = [{key: value for key, value in item.items() if key not in {"duration_ms", "timeout_ms", "timed_out", "stdout_sha256", "stderr_sha256", "timeout", "timeout_sha256"}} for item in actual]
    cases = []
    for case_id, stages, kind in (
        ("current-receipt", actual, "failure"),
        ("legacy-receipt", legacy, "success"),
    ):
        path = OUT / f"cases/{case_id}.json"
        write(path, {"case_id": case_id, "stages": stages})
        cases.append({
            "id": case_id,
            "source": str(path),
            "sha256": sha(path),
            "kind": kind,
            "expected_outcome": "Atom Building Machinery accepts and validates this legitimate Experiment Machinery stage receipt schema.",
        })

    allowed = [
        "skills/atom-building-machinery/scripts/atom_controller.py",
        "tests/test_atom_building_machinery.py",
    ]
    atom = {
        "schema_version": 1,
        "atomic_step_id": ATOM_ID,
        "outcome": "Atom Building Machinery accepts current Experiment Machinery stage receipts while preserving legacy receipt compatibility.",
        "practical_value": "Passing Development-Probe runs can advance to promotion without weakening exact receipt validation or stranding older evidence.",
        "stopping_condition": "The exact current rejected receipt and the legacy receipt both advance, while malformed telemetry remains rejected.",
        "allowed_paths": allowed,
        "captured_cases": [{
            "case_id": case["id"], "source_ref": case["source"], "sha256": case["sha256"],
            "kind": case["kind"], "expected_outcome": case["expected_outcome"],
        } for case in cases],
    }
    write(OUT / "atom-request.json", atom)
    manifest = {
        "schema_version": 1,
        "atomic_step": {
            "id": ATOM_ID, "outcome": atom["outcome"], "practical_value": atom["practical_value"],
            "stopping_condition": atom["stopping_condition"], "captured_cases": cases,
        },
        "mini_probes": [{
            "id": "receipt-consumer",
            "goal": "Consume current stage telemetry without weakening exact validation or breaking legacy receipts.",
            "practical_value": atom["practical_value"],
            "work_type": "code",
            "work_type_reason": "Receipt fields and telemetry invariants are deterministic schema enforcement.",
            "allowed_paths": allowed,
            "inputs": [{"case_id": "current-receipt"}, {"case_id": "legacy-receipt"}],
            "approaches": [
                {"id": "strict-current", "hypothesis": "Replacing the legacy field set with the current schema is sufficient.", "implementation": "Require exactly the current telemetry-bearing receipt fields.", "predicted_tradeoff": "Accepts new runs but strands legitimate legacy evidence."},
                {"id": "dual-schema-exact", "hypothesis": "Two explicit exact schemas preserve history while validating current telemetry.", "implementation": "Dispatch by the current duration marker, enforce one exact field set, then validate current telemetry semantics.", "predicted_tradeoff": "Maintains two bounded schema versions without accepting arbitrary supersets."},
            ],
            "proof": {"success_criterion": "Current and legacy legitimate receipts are accepted.", "failure_criterion": "Either legitimate schema is rejected."},
            "evaluation": {
                "metrics": [{"name": "receipt-correctness", "direction": "maximize"}, {"name": "compatibility-breadth", "direction": "maximize"}],
                "across_cases": [{"name": "receipt-correctness", "method": "sum"}, {"name": "compatibility-breadth", "method": "sum"}],
            },
            "winner_output": {"artifact": "receipt-consumer-contract", "description": "The exact versioned stage receipt consumer."},
        }],
        "composition": {
            "consumes": [{"probe_id": "receipt-consumer", "artifact": "receipt-consumer-contract"}],
            "assembly_contract": "Use the single selected receipt consumer and its focused regression test.",
            "final_validation": {
                "operator_path": "invoke Atom Building Machinery stage receipt validation against both captured schemas",
                "case_ids": ["current-receipt", "legacy-receipt"],
                "success_criterion": "Both legitimate schema versions are accepted.",
                "failure_criterion": "Either legitimate schema version is rejected.",
            },
        },
    }
    development = OUT / "development"
    write(development / "manifest.json", manifest)
    (development / "evaluator.py").write_text(EVALUATOR)
    (development / "assessment.py").write_text(ASSESSMENT)

    approaches = []
    for approach_id, source in (("strict-current", strict), ("dual-schema-exact", dual)):
        request = development / f"build-{approach_id}.json"
        write(request, {
            "schema_version": 1, "development_manifest": str(development / "manifest.json"),
            "probe_id": "receipt-consumer", "approach_id": approach_id,
            "source": {"baseline": str(baseline), "candidate": str(source), "entrypoint": "operator.py"},
            "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
        })
        approaches.append({"approach_id": approach_id, "request": str(request)})
    cross = development / "cross-receipt-consumer.json"
    write(cross, {
        "schema_version": 1, "development_manifest": str(development / "manifest.json"),
        "probe_id": "receipt-consumer", "approach_build_requests": approaches,
        "evaluator": {"adapter": {"path": str(development / "evaluator.py"), "sha256": sha(development / "evaluator.py")},
                      "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]},
    })
    all_probes = development / "all-probes.json"
    write(all_probes, {"schema_version": 1, "development_manifest": str(development / "manifest.json"),
                       "probe_requests": [{"probe_id": "receipt-consumer", "request": str(cross)}]})
    full = development / "full-run.json"
    write(full, {
        "schema_version": 1,
        "development_manifest": {"path": str(development / "manifest.json"), "sha256": sha(development / "manifest.json")},
        "probe_requests": [{
            "probe_id": "receipt-consumer",
            "request": str(cross),
            "request_sha256": sha(cross),
        }],
        "baseline": {"path": str(baseline), "sha256": subprocess.run([sys.executable, str(REPO / "skills/experiment-machinery/scripts/run_experiment.py"), "--hash-source", str(baseline)], check=True, capture_output=True, text=True).stdout.strip()},
        "assessment": {"adapter": {"path": str(development / "assessment.py"), "sha256": sha(development / "assessment.py")},
                       "command": ["{python}", "{assessment-adapter}", "{assessment-request}", "{assessment-response}"]},
    })
    print(json.dumps({"root": str(OUT), "atom_request": str(OUT / "atom-request.json"), "full_run": str(full)}, sort_keys=True))


if __name__ == "__main__":
    main()
