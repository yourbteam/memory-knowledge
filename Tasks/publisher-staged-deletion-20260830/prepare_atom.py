#!/usr/bin/env python3
"""Prepare the staged-deletion publisher atom and its Development-Probe run."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else Path("/private/tmp/publisher-staged-deletion-atom")
ATOM_ID = "publisher-accepts-staged-deletions"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


CURRENT = '''        tracked = _git(
            repo, "ls-files", "--error-unmatch", "--", normalized, check=False
        ).returncode == 0
        if not resolved.is_file() and not tracked:
'''

HEAD_MEMBERSHIP = '''        tracked = _git(
            repo, "ls-files", "--error-unmatch", "--", normalized, check=False
        ).returncode == 0
        tracked_in_head = _git(
            repo, "cat-file", "-e", f"HEAD:{normalized}", check=False
        ).returncode == 0
        if not resolved.is_file() and not tracked and not tracked_in_head:
'''

DIFF_DELETION = '''        tracked = _git(
            repo, "ls-files", "--error-unmatch", "--", normalized, check=False
        ).returncode == 0
        deleted = normalized in {
            item
            for item in _git(
                repo,
                "diff",
                "--name-only",
                "--diff-filter=D",
                "-z",
                "HEAD",
                "--",
                normalized,
            ).stdout.split("\\0")
            if item
        }
        if not resolved.is_file() and not tracked and not deleted:
'''

OPERATOR = r'''from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
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
    tracked = repo / "retired.py"
    tracked.write_text("legacy\n")
    subprocess.run(["git", "-C", str(repo), "add", "retired.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "baseline"], check=True, capture_output=True)
    selected = case["selected_path"]
    if case["setup"] == "staged-deletion":
        tracked.unlink()
        subprocess.run(["git", "-C", str(repo), "add", "--", "retired.py"], check=True)
    manifest = Path(temporary) / "manifest.json"
    manifest.write_text(json.dumps([selected]))
    accepted = True
    error = None
    paths = None
    try:
        paths = module.manifest_paths(repo, manifest)
    except Exception as exc:
        accepted = False
        error = str(exc)

expected = bool(case["expected_accepted"])
correct = accepted is expected
result = {
    "schema_version": 1,
    "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
    "status": "completed",
    "outcome": {
        "case_id": case["case_id"],
        "accepted": accepted,
        "expected_accepted": expected,
        "correct": correct,
        "paths": paths,
        "error": error,
    },
    "metrics": {"boundary-correctness": int(correct)},
    "error": None,
}
Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps(result, sort_keys=True) + "\n")
'''

EVALUATOR = r'''import json, sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text())
scores = []
for candidate in request["candidates"]:
    correct = bool(candidate["outcome"].get("correct"))
    scores.append({
        "variant_id": candidate["variant_id"],
        "metrics": {
            "boundary-correctness": int(correct),
            "deletion-specificity": int(correct and candidate["variant_id"] == "diff-deletion-membership"),
        },
    })
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n")
'''

ASSESSMENT = r'''import json, sys
from pathlib import Path

question = json.loads(Path(sys.argv[1]).read_text())
outcome = question["execution_result"]["outcome"]
correct = bool(outcome.get("correct"))
response = {
    "case_id": question["case_id"],
    "verdict": "satisfied" if correct else "not-satisfied",
    "reason": "The assembled publisher classified the captured manifest path correctly." if correct else "The assembled publisher misclassified the captured manifest path.",
    "evidence_pointers": ["execution-result"],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\n")
'''


def candidate(source: Path, replacement: str) -> None:
    shutil.copytree(OUT / "development/baseline", source)
    target = source / "scripts/minimal_git_publish.py"
    text = target.read_text(encoding="utf-8")
    if CURRENT not in text:
        raise RuntimeError("publisher manifest boundary changed")
    target.write_text(text.replace(CURRENT, replacement), encoding="utf-8")


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing existing output: {OUT}")
    baseline = OUT / "development/baseline"
    (baseline / "scripts").mkdir(parents=True)
    shutil.copy2(REPO / "scripts/minimal_git_publish.py", baseline / "scripts/minimal_git_publish.py")
    (baseline / "operator.py").write_text(OPERATOR, encoding="utf-8")
    approaches = {
        "head-tree-membership": HEAD_MEMBERSHIP,
        "diff-deletion-membership": DIFF_DELETION,
    }
    for approach_id, replacement in approaches.items():
        candidate(OUT / f"development/{approach_id}", replacement)

    cases = []
    for case_id, setup, selected, expected, kind in (
        ("staged-tracked-deletion", "staged-deletion", "retired.py", True, "failure"),
        ("never-tracked-missing-path", "none", "missing.py", False, "success"),
    ):
        path = OUT / f"cases/{case_id}.json"
        write(path, {"case_id": case_id, "setup": setup, "selected_path": selected, "expected_accepted": expected})
        cases.append({
            "id": case_id,
            "source": str(path),
            "sha256": sha(path),
            "kind": kind,
            "expected_outcome": "Accept the staged tracked deletion." if expected else "Reject a path that never existed.",
        })

    allowed = ["scripts/minimal_git_publish.py", "tests/test_minimal_git_publish.py"]
    atom = {
        "schema_version": 1,
        "atomic_step_id": ATOM_ID,
        "outcome": "The registered publisher accepts exact manifest paths already staged as deletions while still rejecting nonexistent paths.",
        "practical_value": "Approved retirements can be committed and pushed through the normal publisher without weakening manifest scope.",
        "stopping_condition": "A staged tracked deletion publishes through the boundary and a never-tracked missing path remains rejected.",
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
            "id": "deletion-identity",
            "goal": "Recognize a missing manifest path as an exact tracked deletion without admitting an invented path.",
            "practical_value": atom["practical_value"],
            "work_type": "code",
            "work_type_reason": "Git path identity and deletion status are deterministic repository facts.",
            "allowed_paths": allowed,
            "inputs": [{"case_id": case["id"]} for case in cases],
            "approaches": [
                {"id": "head-tree-membership", "hypothesis": "HEAD tree membership proves a staged deletion was previously tracked.", "implementation": "Accept a missing index path when its exact blob exists in HEAD.", "predicted_tradeoff": "Simple, but recognizes history rather than the current deletion state."},
                {"id": "diff-deletion-membership", "hypothesis": "The HEAD diff can prove the exact path is currently deleted.", "implementation": "Accept only an exact path reported by Git with deletion status.", "predicted_tradeoff": "One bounded Git diff per missing manifest entry, with semantics local to this boundary."},
            ],
            "proof": {"success_criterion": "The staged deletion is accepted and the invented path is rejected.", "failure_criterion": "Either case is misclassified."},
            "evaluation": {
                "metrics": [{"name": "boundary-correctness", "direction": "maximize"}, {"name": "deletion-specificity", "direction": "maximize"}],
                "across_cases": [{"name": "boundary-correctness", "method": "sum"}, {"name": "deletion-specificity", "method": "sum"}],
            },
            "winner_output": {"artifact": "deletion-identity-boundary", "description": "The exact missing-path deletion classifier."},
        }],
        "composition": {
            "consumes": [{"probe_id": "deletion-identity", "artifact": "deletion-identity-boundary"}],
            "assembly_contract": "Use the selected deletion identity boundary unchanged.",
            "final_validation": {
                "operator_path": "invoke manifest_paths on disposable Git repositories matching the captured cases",
                "case_ids": [case["id"] for case in cases],
                "success_criterion": "Both path classifications match their declared outcomes.",
                "failure_criterion": "Either captured path is misclassified.",
            },
        },
    }
    development = OUT / "development"
    write(development / "manifest.json", manifest)
    (development / "evaluator.py").write_text(EVALUATOR, encoding="utf-8")
    (development / "assessment.py").write_text(ASSESSMENT, encoding="utf-8")

    built = []
    for approach_id in approaches:
        request = development / f"build-{approach_id}.json"
        write(request, {
            "schema_version": 1, "development_manifest": str(development / "manifest.json"),
            "probe_id": "deletion-identity", "approach_id": approach_id,
            "source": {"baseline": str(baseline), "candidate": str(development / approach_id), "entrypoint": "operator.py"},
            "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
        })
        built.append({"approach_id": approach_id, "request": str(request)})
    cross = development / "cross-deletion-identity.json"
    write(cross, {
        "schema_version": 1, "development_manifest": str(development / "manifest.json"),
        "probe_id": "deletion-identity", "approach_build_requests": built,
        "evaluator": {"adapter": {"path": str(development / "evaluator.py"), "sha256": sha(development / "evaluator.py")},
                      "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]},
    })
    full = development / "full-run.json"
    baseline_hash = subprocess.run(
        [sys.executable, str(REPO / "skills/experiment-machinery/scripts/run_experiment.py"), "--hash-source", str(baseline)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    write(full, {
        "schema_version": 1,
        "development_manifest": {"path": str(development / "manifest.json"), "sha256": sha(development / "manifest.json")},
        "probe_requests": [{"probe_id": "deletion-identity", "request": str(cross), "request_sha256": sha(cross)}],
        "baseline": {"path": str(baseline), "sha256": baseline_hash},
        "assessment": {"adapter": {"path": str(development / "assessment.py"), "sha256": sha(development / "assessment.py")},
                       "command": ["{python}", "{assessment-adapter}", "{assessment-request}", "{assessment-response}"]},
    })
    print(json.dumps({"root": str(OUT), "atom_request": str(OUT / "atom-request.json"), "full_run": str(full)}, sort_keys=True))


if __name__ == "__main__":
    main()
