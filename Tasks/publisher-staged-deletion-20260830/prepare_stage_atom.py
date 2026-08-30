#!/usr/bin/env python3
"""Prepare the publisher already-staged-path corrective atom."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]).resolve()
ATOM_ID = "publisher-preserves-already-staged-paths"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


CURRENT = '''    _git(repo, "add", "--", *paths, env=env)
    staged = _staged_paths(repo, env=env)
'''

SELECTIVE = '''    already_staged = set(_staged_paths(repo, env=env))
    paths_to_stage = [path for path in paths if path not in already_staged]
    if paths_to_stage:
        _git(repo, "add", "--", *paths_to_stage, env=env)
    staged = _staged_paths(repo, env=env)
'''

OPERATOR = r'''from __future__ import annotations
import importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("candidate_publish", root / "scripts/minimal_git_publish.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
case = json.loads(Path(os.environ["EXPERIMENT_INPUT_PATH"]).read_text())

with tempfile.TemporaryDirectory() as temporary:
    repo = Path(temporary) / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "probe@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Probe"], check=True)
    (repo / "retired.py").write_text("legacy\n")
    (repo / "kept.py").write_text("before\n")
    subprocess.run(["git", "-C", str(repo), "add", "retired.py", "kept.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "baseline"], check=True, capture_output=True)
    (repo / "retired.py").unlink()
    subprocess.run(["git", "-C", str(repo), "add", "--", "retired.py"], check=True)
    (repo / "kept.py").write_text("after\n")
    if case["setup"] == "verification-mutates-selected":
        verification = [sys.executable, "-c", "from pathlib import Path; Path('kept.py').write_text('mutated\\n')"]
    else:
        verification = ["git", "diff", "--cached", "--check", "--", "retired.py", "kept.py"]
    accepted = True
    error = None
    try:
        module._stage_and_verify(repo, ["retired.py", "kept.py"], verification)
    except Exception as exc:
        accepted = False
        error = str(exc)

expected = bool(case["expected_accepted"])
correct = accepted is expected
result = {
    "schema_version": 1,
    "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
    "status": "completed",
    "outcome": {"case_id": case["case_id"], "accepted": accepted, "expected_accepted": expected, "correct": correct, "error": error},
    "metrics": {"staging-correctness": int(correct)},
    "error": None,
}
Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps(result, sort_keys=True) + "\n")
'''

EVALUATOR = r'''import json, sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text())
scores = [{"variant_id": c["variant_id"], "metrics": {"staging-correctness": int(bool(c["outcome"].get("correct")))}} for c in request["candidates"]]
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n")
'''

ASSESSMENT = r'''import json, sys
from pathlib import Path
q = json.loads(Path(sys.argv[1]).read_text())
correct = bool(q["execution_result"]["outcome"].get("correct"))
Path(sys.argv[2]).write_text(json.dumps({"case_id": q["case_id"], "verdict": "satisfied" if correct else "not-satisfied", "reason": "The assembled staging boundary produced the declared outcome.", "evidence_pointers": ["execution-result"]}, sort_keys=True) + "\n")
'''


def make_candidate(source: Path, selective: bool) -> None:
    shutil.copytree(OUT / "development/baseline", source)
    if selective:
        target = source / "scripts/minimal_git_publish.py"
        text = target.read_text()
        if CURRENT not in text:
            raise RuntimeError("staging boundary changed")
        target.write_text(text.replace(CURRENT, SELECTIVE))


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing existing output: {OUT}")
    baseline = OUT / "development/baseline"
    (baseline / "scripts").mkdir(parents=True)
    shutil.copy2(REPO / "scripts/minimal_git_publish.py", baseline / "scripts/minimal_git_publish.py")
    (baseline / "operator.py").write_text(OPERATOR)
    make_candidate(OUT / "development/readd-entire-manifest", False)
    make_candidate(OUT / "development/stage-only-unstaged", True)

    cases = []
    for case_id, setup, expected, kind in (
        ("merge-has-staged-deletion", "normal", True, "failure"),
        ("verification-mutation-still-refused", "verification-mutates-selected", False, "success"),
    ):
        path = OUT / f"cases/{case_id}.json"
        write(path, {"case_id": case_id, "setup": setup, "expected_accepted": expected})
        cases.append({"id": case_id, "source": str(path), "sha256": sha(path), "kind": kind,
                      "expected_outcome": "Stage remaining paths while preserving the already-staged deletion." if expected else "Reject verification-time mutation of a selected path."})

    allowed = ["scripts/minimal_git_publish.py", "tests/test_minimal_git_publish.py"]
    atom = {"schema_version": 1, "atomic_step_id": ATOM_ID,
            "outcome": "The publisher preserves already-staged exact paths and stages only remaining manifest paths.",
            "practical_value": "A pending merge containing staged retirements can reach commit without weakening exact-scope or mutation checks.",
            "stopping_condition": "Mixed staged and unstaged manifest paths pass, while verification mutation remains blocked.",
            "allowed_paths": allowed,
            "captured_cases": [{"case_id": c["id"], "source_ref": c["source"], "sha256": c["sha256"], "kind": c["kind"], "expected_outcome": c["expected_outcome"]} for c in cases]}
    write(OUT / "atom-request.json", atom)
    manifest = {"schema_version": 1,
        "atomic_step": {"id": ATOM_ID, "outcome": atom["outcome"], "practical_value": atom["practical_value"], "stopping_condition": atom["stopping_condition"], "captured_cases": cases},
        "mini_probes": [{"id": "staging-selection", "goal": "Stage a mixed manifest without re-adding paths already staged as deletions.", "practical_value": atom["practical_value"],
            "work_type": "code", "work_type_reason": "Index membership and selected path staging are deterministic Git facts.", "allowed_paths": allowed,
            "inputs": [{"case_id": c["id"]} for c in cases],
            "approaches": [
                {"id": "readd-entire-manifest", "hypothesis": "Git can safely re-add every selected path.", "implementation": "Run git add over the complete manifest.", "predicted_tradeoff": "Simple but rejects a deletion already absent from the index."},
                {"id": "stage-only-unstaged", "hypothesis": "Already-staged exact paths should be preserved while only missing index changes are added.", "implementation": "Subtract staged paths from the manifest before git add, then validate the complete staged set.", "predicted_tradeoff": "One deterministic staged-set read before adding remaining paths."}],
            "proof": {"success_criterion": "Mixed staged and unstaged paths pass and the mutation guard remains active.", "failure_criterion": "The merge deletion is re-added or the mutation guard is weakened."},
            "evaluation": {"metrics": [{"name": "staging-correctness", "direction": "maximize"}], "across_cases": [{"name": "staging-correctness", "method": "sum"}]},
            "winner_output": {"artifact": "staging-selection-boundary", "description": "The exact mixed-index staging behavior."}}],
        "composition": {"consumes": [{"probe_id": "staging-selection", "artifact": "staging-selection-boundary"}], "assembly_contract": "Use the selected staging boundary unchanged.",
            "final_validation": {"operator_path": "invoke _stage_and_verify in disposable Git repositories matching both cases", "case_ids": [c["id"] for c in cases], "success_criterion": "Both captured cases match their outcomes.", "failure_criterion": "Either case differs."}}}
    development = OUT / "development"
    write(development / "manifest.json", manifest)
    (development / "evaluator.py").write_text(EVALUATOR)
    (development / "assessment.py").write_text(ASSESSMENT)
    built = []
    for approach_id in ("readd-entire-manifest", "stage-only-unstaged"):
        request = development / f"build-{approach_id}.json"
        write(request, {"schema_version": 1, "development_manifest": str(development / "manifest.json"), "probe_id": "staging-selection", "approach_id": approach_id,
                        "source": {"baseline": str(baseline), "candidate": str(development / approach_id), "entrypoint": "operator.py"},
                        "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]}})
        built.append({"approach_id": approach_id, "request": str(request)})
    cross = development / "cross-staging-selection.json"
    write(cross, {"schema_version": 1, "development_manifest": str(development / "manifest.json"), "probe_id": "staging-selection", "approach_build_requests": built,
                  "evaluator": {"adapter": {"path": str(development / "evaluator.py"), "sha256": sha(development / "evaluator.py")}, "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]}})
    baseline_hash = subprocess.run([sys.executable, str(REPO / "skills/experiment-machinery/scripts/run_experiment.py"), "--hash-source", str(baseline)], check=True, capture_output=True, text=True).stdout.strip()
    full = development / "full-run.json"
    write(full, {"schema_version": 1, "development_manifest": {"path": str(development / "manifest.json"), "sha256": sha(development / "manifest.json")},
                 "probe_requests": [{"probe_id": "staging-selection", "request": str(cross), "request_sha256": sha(cross)}],
                 "baseline": {"path": str(baseline), "sha256": baseline_hash},
                 "assessment": {"adapter": {"path": str(development / "assessment.py"), "sha256": sha(development / "assessment.py")}, "command": ["{python}", "{assessment-adapter}", "{assessment-request}", "{assessment-response}"]}})
    print(json.dumps({"atom_request": str(OUT / "atom-request.json"), "full_run": str(full)}, sort_keys=True))


if __name__ == "__main__":
    main()
