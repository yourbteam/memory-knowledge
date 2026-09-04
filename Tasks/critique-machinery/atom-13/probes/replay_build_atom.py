#!/usr/bin/env python3
"""Run the real Step 12 launcher against a new relocated copy of its repository surface."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_repository", type=Path)
    parser.add_argument("launcher", type=Path)
    parser.add_argument("controller", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("specs", nargs="+", type=Path)
    args = parser.parse_args()
    source = args.source_repository.resolve()
    launcher = args.launcher.resolve()
    controller = args.controller.resolve()
    workspace = args.workspace.resolve()
    if workspace.exists():
        raise SystemExit(f"workspace must be new: {workspace}")
    task = workspace / "Tasks" / "step6-feedback-closure"
    shutil.copytree(source / "Tasks" / "step6-feedback-closure" / "scaffold", task / "scaffold")
    module = workspace / "src" / "up_harness" / "tactical_roadmap.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "src" / "up_harness" / "tactical_roadmap.py", module)
    shutil.copytree(source / "tests" / "unit", workspace / "tests" / "unit")

    module_spec = importlib.util.spec_from_file_location("real_step12_build_atom", launcher)
    if module_spec is None or module_spec.loader is None:
        raise SystemExit(f"cannot import launcher: {launcher}")
    build_atom = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(build_atom)
    build_atom.ROOT = workspace
    build_atom.TASK = task
    build_atom.SCAFFOLD = task / "scaffold"
    build_atom.CONTROLLER = controller

    results = []
    for supplied in args.specs:
        spec = supplied.resolve()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            returncode = build_atom.main(str(spec))
        atom_id = json.loads(spec.read_text())["atom_id"]
        run = task / "runs" / f"atom-{atom_id}"
        evidence = workspace / "operator-evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / f"{atom_id}.stdout.txt").write_text(stdout.getvalue())
        (evidence / f"{atom_id}.stderr.txt").write_text(stderr.getvalue())
        results.append({
            "atom_id": atom_id,
            "spec": str(spec),
            "spec_sha256": sha(spec),
            "returncode": returncode,
            "run": str(run),
            "request_sha256": sha(run / "atom-request.json"),
            "controller_run_created": (run / "controller-run" / "ledger.jsonl").is_file(),
            "development_probe_completed": (run / "dp-run" / "final-verdict.json").is_file(),
        })
    receipt = {
        "launcher": str(launcher),
        "launcher_sha256": sha(launcher),
        "controller": str(controller),
        "controller_sha256": sha(controller),
        "source_repository": str(source),
        "relocated_repository": str(workspace),
        "model_calls": 0,
        "results": results,
    }
    (workspace / "operator-evidence" / "summary.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
