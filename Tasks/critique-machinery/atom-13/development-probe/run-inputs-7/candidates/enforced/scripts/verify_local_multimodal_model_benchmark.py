#!/usr/bin/env python3
"""Run the bounded same-path contract checks for the local benchmark sequence."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_pytest.sh"
COMMANDS = (
    [
        str(RUNNER),
        "tests/test_local_multimodal_model_benchmark.py",
        "-q",
    ],
    [
        str(RUNNER),
        "tests/test_sequence_intake_adapters.py",
        "-k",
        "test_local_multimodal_benchmark",
        "-q",
    ],
)


def main() -> int:
    for command in COMMANDS:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            print(json.dumps({
                "ok": False,
                "failed_command": command,
                "exit_code": completed.returncode,
            }, sort_keys=True))
            return completed.returncode
    print(json.dumps({
        "ok": True,
        "runner_tests": 9,
        "intake_tests": 3,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
