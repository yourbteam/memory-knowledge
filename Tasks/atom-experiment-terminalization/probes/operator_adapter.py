#!/usr/bin/env python3
"""Exercise generic experiment terminalization through the real runner CLI."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def terminal_events(path: Path) -> list[str]:
    records = [json.loads(line) for line in path.read_text().splitlines()]
    return [row["event"] for row in records if row["event"] in {"evaluation_completed", "experiment_failed"}]


def run_mode(root: Path, work: Path, mode: str) -> bool:
    work.mkdir(parents=True)
    runner = root / "skills/experiment-machinery/scripts/run_experiment.py"
    target = work / "target"
    target.mkdir()
    (target / "entry.py").write_text("VALUE = 1\n")
    frozen = work / "input.json"
    frozen.write_text('{"value":1}\n')
    evaluator = work / "evaluator.py"
    evaluator.write_text(
        """import json, os, sys, time
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text())
mode = os.environ.get("TERMINAL_MODE", "success")
if mode == "timeout": time.sleep(1)
if mode == "nonzero": raise SystemExit(7)
if mode == "malformed": Path(sys.argv[2]).write_text("{")
elif mode == "wrong-shape": Path(sys.argv[2]).write_text(json.dumps({"schema_version":1,"scores":[]}))
else:
    scores = [{"variant_id": item["variant_id"], "metrics":{"quality":1}} for item in request["candidates"]]
    Path(sys.argv[2]).write_text(json.dumps({"schema_version":1,"scores":scores}))
"""
    )
    candidate = work / "candidate.py"
    candidate.write_text(
        """import json, os
from pathlib import Path
configuration = json.loads(Path(os.environ["EXPERIMENT_VARIANT_PATH"]).read_text())["configuration"]
if configuration.get("drift"):
    evaluator = Path(configuration["evaluator_path"])
    evaluator.write_text(evaluator.read_text() + "\\n# drift\\n")
Path(os.environ["EXPERIMENT_TELEMETRY_PATH"]).write_text(json.dumps({"event":"observed"}) + "\\n")
Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps({"schema_version":1,"variant_id":os.environ["EXPERIMENT_VARIANT_ID"],"status":"completed","outcome":{},"metrics":{"quality":0},"error":None}) + "\\n")
"""
    )
    source_hash = subprocess.run(
        [sys.executable, str(runner), "--hash-source", str(target)],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    spec = work / "experiment.json"
    variants = []
    for variant_id in ("control", "variation"):
        variants.append(
            {
                "id": variant_id,
                "command": [sys.executable, str(candidate)],
                "adapter": {"path": str(candidate), "sha256": digest(candidate)},
                "configuration": {
                    "drift": mode == "digest-drift" and variant_id == "control",
                    "evaluator_path": str(evaluator),
                },
            }
        )
    write(
        spec,
        {
            "schema_version": 4,
            "experiment_id": f"terminal-{mode}",
            "hypothesis": "Every started experiment reaches one terminal record.",
            "target": {
                "machinery": "experiment-machinery",
                "phase": "terminalization",
                "source": {"path": str(target), "sha256": source_hash},
                "entrypoint": "entry.py",
            },
            "frozen_input": {"path": str(frozen), "sha256": digest(frozen)},
            "execution_limits": {
                "variant_timeout_ms": 5000,
                "evaluator_timeout_ms": 100 if mode == "timeout" else 5000,
            },
            "variants": variants,
            "evaluation": {
                "metrics": [{"name": "quality", "direction": "maximize"}],
                "evaluator": {
                    "adapter": {"path": str(evaluator), "sha256": digest(evaluator)},
                    "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"],
                },
            },
        },
    )
    environment = os.environ.copy()
    environment["TERMINAL_MODE"] = mode
    output = work / "output"
    completed = subprocess.run(
        [sys.executable, str(runner), "--spec", str(spec), "--output", str(output)],
        env=environment,
        text=True,
        capture_output=True,
    )
    summary_path = output / "summary.json"
    if not summary_path.is_file() or not (output / "ledger.jsonl").is_file():
        return False
    summary = json.loads(summary_path.read_text())
    events = terminal_events(output / "ledger.jsonl")
    if mode == "success":
        return completed.returncode == 0 and summary["champion"] is not None and events == ["evaluation_completed"]
    return (
        completed.returncode != 0
        and summary["champion"] is None
        and summary["promotion_applied"] is False
        and isinstance(summary["evaluation_error"], dict)
        and events == ["experiment_failed"]
    )


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    work = Path(os.environ["EXPERIMENT_WORK_DIR"])
    case = json.loads(Path(os.environ["EXPERIMENT_INPUT_PATH"]).read_text())["case"]
    modes = ["success", "timeout", "nonzero", "malformed", "wrong-shape", "digest-drift"]
    metrics = {f"{mode}-terminalized": int(run_mode(root, work / mode, mode)) for mode in modes}
    Path(os.environ["EXPERIMENT_TELEMETRY_PATH"]).write_text(
        json.dumps({"event": "terminalization-observed", "metrics": metrics}, sort_keys=True) + "\n"
    )
    write(
        Path(os.environ["EXPERIMENT_RESULT_PATH"]),
        {
            "schema_version": 1,
            "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
            "status": "completed",
            "outcome": {"case": case},
            "metrics": metrics,
            "error": None,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
