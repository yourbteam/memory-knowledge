#!/usr/bin/env python3
"""Resume the canonical prepared build without reconstructing loop arguments."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


BASE = Path(__file__).resolve().parent
CONFIG = BASE / "prepared_build_launch.json"


def read(path):
    with Path(path).open() as stream:
        return json.load(stream)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve(base, value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def attempt_path(cycle_dir, attempt):
    suffix = "" if attempt == 1 else "-attempt" + str(attempt)
    return cycle_dir / ("prepared-execution" + suffix)


def next_attempt(cycle_dir):
    attempt = 1
    while attempt_path(cycle_dir, attempt).exists():
        attempt += 1
    return attempt


def resumable_attempt(cycle_dir):
    """Reuse a completed execution whose only unfinished stage is review."""
    candidates = []
    for attempt in range(1, next_attempt(cycle_dir)):
        path = attempt_path(cycle_dir, attempt)
        if (path / "receipts" / "generation.json").is_file() and \
                (path / "execution" / "result.json").is_file() and \
                not (path / "handoff.json").exists():
            candidates.append(attempt)
    return candidates[-1] if candidates else None


def attached_handoff_attempt(state, cycle_dir):
    """Return the exact completed attempt attached before an interrupted loop transition."""
    pending = state.get("pending") or {}
    references = [value for value in
                  [state.get("prepared_execution"), pending.get("prepared_execution")]
                  if value is not None]
    if not references:
        return None
    if any(reference != references[0] for reference in references[1:]):
        raise ValueError("Loop state points to different prepared executions")
    root = Path(state["root"]).resolve()
    handoff = resolve(root, references[0]["path"])
    if not handoff.is_file() or sha256(handoff) != references[0]["sha256"]:
        raise ValueError("The attached prepared-execution handoff changed")
    for attempt in range(1, next_attempt(cycle_dir)):
        if handoff == (attempt_path(cycle_dir, attempt) / "handoff.json").resolve():
            return attempt
    raise ValueError("The attached prepared execution is outside the current cycle attempts")


def plan(base=BASE, config_path=CONFIG):
    config = read(config_path)
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported prepared-build launcher configuration")

    run = resolve(base, config["run"])
    state_path = run / "state.json"
    state = read(state_path)
    pending = state.get("pending") or {}
    if state.get("stage") != "build" or pending.get("action") != "prepare_build":
        raise ValueError("The bound loop is not waiting for a prepared build")
    if not pending.get("selection_preparation"):
        raise ValueError("The current selection has no prepared build input")
    cycle = Path(state["cycle"]).resolve()
    cycle_dir = cycle.parent
    if cycle_dir.parent.parent != run.resolve():
        raise ValueError("The current cycle is outside the bound loop run")

    runtime_config = resolve(base, config["runtime_config"])
    if sha256(runtime_config) != config["runtime_config_sha256"]:
        raise ValueError("The bound runtime configuration changed")

    model_io = Path(state["skills"]) / "atom-building-machinery" / "scripts" / "model_io.py"
    if sha256(model_io) != config["builder_model_io_sha256"]:
        raise ValueError("The bound builder model-call implementation changed")

    prepared_execution = base / "prepared_execution.py"
    if sha256(prepared_execution) != config["prepared_execution_sha256"]:
        raise ValueError("The bound prepared-execution implementation changed")

    model_timeout = config.get("model_timeout_seconds", 300)
    if type(model_timeout) is not int or not 60 <= model_timeout <= 1800:
        raise ValueError("The model timeout must be between 60 and 1800 seconds")

    completed_attempt = attached_handoff_attempt(state, cycle_dir)
    review_attempt = None if completed_attempt else resumable_attempt(cycle_dir)
    attempt = completed_attempt or review_attempt or next_attempt(cycle_dir)
    resumed = completed_attempt is not None or review_attempt == attempt
    argv = [
        sys.executable,
        "-B",
        str(base / "loop.py"),
        "execute-prepared",
        "--run",
        str(run),
        "--runtime-config",
        str(runtime_config),
        "--attempt",
        str(attempt),
    ]
    return {
        "action": "execute_prepared_build",
        "run": str(run),
        "cycle": str(cycle),
        "cycle_number": state.get("cycle_number"),
        "selection": pending["selection"],
        "selection_preparation": pending["selection_preparation"],
        "runtime_config": {
            "path": str(runtime_config),
            "sha256": config["runtime_config_sha256"],
        },
        "builder_model_io": {
            "path": str(model_io),
            "sha256": config["builder_model_io_sha256"],
        },
        "prepared_execution": {
            "path": str(prepared_execution),
            "sha256": config["prepared_execution_sha256"],
        },
        "attempt": attempt,
        "resumed": resumed,
        "output": str(attempt_path(cycle_dir, attempt)),
        "model_calls": 0 if completed_attempt else (1 if resumed else 2),
        "completed_handoff": completed_attempt is not None,
        "model_timeout_seconds": model_timeout,
        "argv": argv,
    }


def main():
    prepared = plan()
    print(json.dumps(prepared, indent=2), flush=True)
    answer = input("Run this prepared build? Type yes to continue: ").strip().lower()
    if answer != "yes":
        print(json.dumps({"ok": False, "error": "launch-cancelled"}))
        return 2
    completed = subprocess.run(
        prepared["argv"],
        env={**os.environ, "ATOM_BUILDER_MODEL_TIMEOUT_SECONDS": str(prepared["model_timeout_seconds"])},
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
