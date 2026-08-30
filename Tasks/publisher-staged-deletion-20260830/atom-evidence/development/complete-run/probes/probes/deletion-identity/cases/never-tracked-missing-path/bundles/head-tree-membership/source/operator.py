from __future__ import annotations

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
