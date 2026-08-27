#!/usr/bin/env python3
"""Prepare the standalone-and-composed Experiment Machinery projection atom."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else Path("/private/tmp/experiment-projection-dual-path")
ATOM_ID = "promote-experiment-machinery-standalone-and-composed"
FULL_REQUEST = Path("/private/tmp/atom-receipt-compatibility-r4/development/full-run.json")
COMPLETE_RUN = Path("/private/tmp/atom-receipt-compatibility-r4/development/complete-run")
ATOM_REQUEST = Path("/private/tmp/atom-receipt-compatibility-r4/atom-request.json")
RUN_TEMPLATES = {
    "codex": Path("/private/tmp/atom-building-live-codex-run"),
    "claude": Path("/private/tmp/atom-building-live-claude-run"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("projection_tool", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def copy_tracked(boundary: str, target: Path) -> None:
    result = subprocess.run(
        ["git", "ls-files", boundary], cwd=REPO, check=True, capture_output=True, text=True
    )
    for relative in result.stdout.splitlines():
        source = REPO / relative
        if not source.is_file():
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


OPERATOR = r'''from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def load(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_projection", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


root = Path(__file__).resolve().parent
case = json.loads(Path(os.environ["EXPERIMENT_INPUT_PATH"]).read_text())
work = Path(os.environ["EXPERIMENT_WORK_DIR"])
module = load(root / "working-agreement/project_client_skills.py")
entries = module.load_projections(root / "working-agreement/client-skill-projections.json")["entries"]
baseline_entries = json.loads((root / "baseline-projections.json").read_text())["entries"]
client = case["client"]
staging = work / "installed"


def writable_source(name: str) -> Path:
    destination = work / "writable-source" / name
    shutil.copytree(root / "skills" / name, destination)
    destination.chmod(0o755)
    for path in destination.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    return destination


result = None
error = None
try:
    for name in ("atom-building-machinery", "experiment-machinery"):
        module.project_skill(writable_source(name), staging / name, client, entries[name])
    if case["mode"] == "standalone":
        output = work / "standalone-run"
        command = [
            sys.executable,
            str(staging / "experiment-machinery/scripts/development_probe_run.py"),
            "run",
            case["full_request"],
            str(output),
        ]
    else:
        atom_run = work / "atom-run"
        shutil.copytree(case["run_template"], atom_run)
        command = [
            sys.executable,
            str(staging / "atom-building-machinery/scripts/atom_controller.py"),
            "record-experiment",
            str(atom_run),
            case["complete_run"],
        ]
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if completed.returncode == 0:
        result = json.loads(completed.stdout)
    else:
        error = completed.stderr.strip() or completed.stdout.strip()
    returncode = completed.returncode
except Exception as exc:
    returncode = 1
    error = str(exc)

experiment_row = entries["experiment-machinery"]
canonical_hash = module.tree_hash(root / "skills/experiment-machinery")
row_current = (
    experiment_row["canonical_tree_sha256"] == canonical_hash
    and experiment_row["projected_tree_sha256"] == canonical_hash
)
unrelated_churn = sum(
    entries.get(name) != row
    for name, row in baseline_entries.items()
    if name != "experiment-machinery"
)
path_succeeded = returncode == 0 and (
    (case["mode"] == "standalone" and result.get("verdict") == "passed")
    or (case["mode"] == "composed" and result.get("stage") == "promotion")
)
payload = {
    "schema_version": 1,
    "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
    "status": "completed",
    "outcome": {
        "case_id": case["case_id"],
        "client": client,
        "mode": case["mode"],
        "path_succeeded": path_succeeded,
        "row_current": row_current,
        "unrelated_row_churn": unrelated_churn,
        "returncode": returncode,
        "result": result,
        "error": error,
    },
    "metrics": {
        "operator-path-correctness": int(path_succeeded and row_current),
        "unrelated-row-churn": unrelated_churn,
    },
    "error": None,
}
Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps(payload, sort_keys=True) + "\n")
'''

EVALUATOR = r'''import json, sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text())
scores = []
for candidate in request["candidates"]:
    outcome = candidate["outcome"]
    scores.append({
        "variant_id": candidate["variant_id"],
        "metrics": {
            "operator-path-correctness": int(outcome.get("path_succeeded") is True and outcome.get("row_current") is True),
            "unrelated-row-churn": int(outcome.get("unrelated_row_churn", 999)),
        },
    })
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n")
'''

ASSESSMENT = r'''import json, sys
from pathlib import Path
question = json.loads(Path(sys.argv[1]).read_text())
outcome = question["execution_result"]["outcome"]
satisfied = outcome.get("path_succeeded") is True and outcome.get("row_current") is True
response = {
    "case_id": question["case_id"],
    "verdict": "satisfied" if satisfied else "not-satisfied",
    "reason": "The promoted Experiment Machinery projection completed the declared standalone or composed client path." if satisfied else "The promoted Experiment Machinery projection did not complete the declared standalone or composed client path.",
    "evidence_pointers": ["execution-result"],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\n")
'''


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing existing output: {OUT}")
    development = OUT / "development"
    baseline = development / "baseline"
    copy_tracked("skills", baseline)
    for path in (
        "working-agreement/client-skill-projections.json",
        "working-agreement/machinery-client-model-v1.json",
        "working-agreement/project_client_skills.py",
    ):
        copy_tracked(path, baseline)
    shutil.copy2(REPO / "working-agreement/client-skill-projections.json", baseline / "baseline-projections.json")
    (baseline / "operator.py").write_text(OPERATOR)

    global_refresh = development / "global-refresh"
    scoped_refresh = development / "scoped-refresh"
    shutil.copytree(baseline, global_refresh)
    shutil.copytree(baseline, scoped_refresh)
    for candidate in (global_refresh, scoped_refresh):
        shutil.copy2(REPO / "skills/managed-skills.txt", candidate / "skills/managed-skills.txt")

    tool = global_refresh / "working-agreement/project_client_skills.py"
    completed = subprocess.run(
        [sys.executable, str(tool), "generate", "--skills-root", str(global_refresh / "skills"),
         "--manifest", str(global_refresh / "skills/managed-skills.txt"), "--projections",
         str(global_refresh / "working-agreement/client-skill-projections.json")],
        capture_output=True, text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    generated = json.loads((global_refresh / "working-agreement/client-skill-projections.json").read_text())
    scoped = json.loads((scoped_refresh / "working-agreement/client-skill-projections.json").read_text())
    scoped["entries"]["experiment-machinery"] = generated["entries"]["experiment-machinery"]
    write_json(scoped_refresh / "working-agreement/client-skill-projections.json", scoped)

    cases = []
    for client in ("codex", "claude"):
        for mode in ("standalone", "composed"):
            case_id = f"{client}-{mode}"
            payload = {
                "case_id": case_id,
                "client": client,
                "mode": mode,
                "full_request": str(FULL_REQUEST),
                "full_request_sha256": digest(FULL_REQUEST),
                "complete_run": str(COMPLETE_RUN),
                "run_template": str(RUN_TEMPLATES[client]),
                "atom_request": str(ATOM_REQUEST),
            }
            path = OUT / f"cases/{case_id}.json"
            write_json(path, payload)
            cases.append({
                "id": case_id,
                "source": str(path),
                "sha256": digest(path),
                "kind": "success" if mode == "standalone" else "failure",
                "expected_outcome": (
                    f"The {client} Experiment Machinery projection completes its own Development-Probe run."
                    if mode == "standalone" else
                    f"Atom Building Machinery consumes the same {client} Experiment Machinery projection and advances record-experiment to promotion."
                ),
            })

    allowed = ["working-agreement/client-skill-projections.json"]
    atom_request = {
        "schema_version": 1,
        "atomic_step_id": ATOM_ID,
        "outcome": "The same current Experiment Machinery projection works standalone and through Atom Building Machinery for Codex and Claude.",
        "practical_value": "Experiment Machinery remains independently usable while Atom Building Machinery composes it without a private or stale copy.",
        "stopping_condition": "Both clients complete one standalone Development-Probe run and one composed record-experiment transition using hash-matched managed installations.",
        "allowed_paths": allowed,
        "captured_cases": [{"case_id": c["id"], "source_ref": c["source"], "sha256": c["sha256"], "kind": c["kind"], "expected_outcome": c["expected_outcome"]} for c in cases],
    }
    write_json(OUT / "atom-request.json", atom_request)
    manifest = {
        "schema_version": 1,
        "atomic_step": {"id": ATOM_ID, "outcome": atom_request["outcome"], "practical_value": atom_request["practical_value"], "stopping_condition": atom_request["stopping_condition"], "captured_cases": cases},
        "mini_probes": [{
            "id": "projection-currency",
            "goal": "Publish the current Experiment Machinery bytes without coupling its standalone and composed entrypoints.",
            "practical_value": atom_request["practical_value"],
            "work_type": "code",
            "work_type_reason": "Projection hashes, installation identity, entrypoints, and exit states are deterministic boundaries.",
            "allowed_paths": allowed,
            "inputs": [{"case_id": c["id"]} for c in cases],
            "approaches": [
                {"id": "global-refresh", "hypothesis": "Refreshing every stale projection is the safest way to publish Experiment Machinery.", "implementation": "Regenerate the complete projection manifest.", "predicted_tradeoff": "Makes the target work but silently changes unrelated projection identities."},
                {"id": "scoped-refresh", "hypothesis": "Refreshing only Experiment Machinery preserves standalone and composed behavior with no unrelated projection churn.", "implementation": "Regenerate all identities in isolation, then promote only the Experiment Machinery row.", "predicted_tradeoff": "Leaves unrelated stale rows visible for their own separately approved atoms."},
            ],
            "proof": {"success_criterion": "All four standalone/composed client paths complete with a current row.", "failure_criterion": "Any path fails or the row remains stale."},
            "evaluation": {
                "metrics": [{"name": "operator-path-correctness", "direction": "maximize"}, {"name": "unrelated-row-churn", "direction": "minimize"}],
                "across_cases": [{"name": "operator-path-correctness", "method": "sum"}, {"name": "unrelated-row-churn", "method": "sum"}],
            },
            "winner_output": {"artifact": "experiment-projection-row", "description": "The smallest managed projection update supporting both execution modes."},
        }],
        "composition": {
            "consumes": [{"probe_id": "projection-currency", "artifact": "experiment-projection-row"}],
            "assembly_contract": "Use the single selected managed projection row without modifying Experiment Machinery behavior.",
            "final_validation": {"operator_path": "run Experiment Machinery standalone and through Atom Building Machinery in both client projections", "case_ids": [c["id"] for c in cases], "success_criterion": "All four paths complete from the same current projection bytes.", "failure_criterion": "Any standalone or composed client path fails."},
        },
    }
    write_json(development / "manifest.json", manifest)
    (development / "evaluator.py").write_text(EVALUATOR)
    (development / "assessment.py").write_text(ASSESSMENT)

    approaches = []
    for approach_id, source in (("global-refresh", global_refresh), ("scoped-refresh", scoped_refresh)):
        path = development / f"build-{approach_id}.json"
        write_json(path, {"schema_version": 1, "development_manifest": str(development / "manifest.json"), "probe_id": "projection-currency", "approach_id": approach_id, "source": {"baseline": str(baseline), "candidate": str(source), "entrypoint": "operator.py"}, "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]}})
        approaches.append({"approach_id": approach_id, "request": str(path)})
    cross = development / "cross-projection-currency.json"
    write_json(cross, {"schema_version": 1, "development_manifest": str(development / "manifest.json"), "probe_id": "projection-currency", "approach_build_requests": approaches, "evaluator": {"adapter": {"path": str(development / "evaluator.py"), "sha256": digest(development / "evaluator.py")}, "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]}})
    full = development / "full-run.json"
    tree_hash = subprocess.run([sys.executable, str(REPO / "skills/experiment-machinery/scripts/run_experiment.py"), "--hash-source", str(baseline)], check=True, capture_output=True, text=True).stdout.strip()
    write_json(full, {"schema_version": 1, "development_manifest": {"path": str(development / "manifest.json"), "sha256": digest(development / "manifest.json")}, "baseline": {"path": str(baseline), "sha256": tree_hash}, "probe_requests": [{"probe_id": "projection-currency", "request": str(cross), "request_sha256": digest(cross)}], "assessment": {"adapter": {"path": str(development / "assessment.py"), "sha256": digest(development / "assessment.py")}, "command": ["{python}", "{assessment-adapter}", "{assessment-request}", "{assessment-response}"]}})
    print(json.dumps({"root": str(OUT), "atom_request": str(OUT / "atom-request.json"), "full_run": str(full)}, sort_keys=True))


if __name__ == "__main__":
    main()
