#!/usr/bin/env python3
"""Launch every Requirements Machinery reading packet without weakening blind independence."""
from __future__ import annotations

import concurrent.futures
import subprocess
from pathlib import Path

from client_model_policy import validate_reader_command


def _answers_in(directory: Path) -> int:
    return len(list(directory.glob("*.json"))) if directory.is_dir() else 0


def launch(jobs: list[dict[str, object]], command: str, cwd: Path,
           work: Path, tag: str) -> list[dict[str, object]]:
    """Validate once, then run the independent jobs concurrently with private logs."""

    parts = validate_reader_command(command)

    def run(number: int, job: dict[str, object]) -> dict[str, object]:
        log = work / f"launch-{tag}-{number}.log"
        done = subprocess.run(
            parts, input=str(job["instruction"]), cwd=str(cwd),
            capture_output=True, text=True, check=False,
        )
        log.write_text(
            done.stdout + ("\n--- stderr ---\n" + done.stderr if done.stderr else ""),
            encoding="utf-8",
        )
        return {
            "exit_code": done.returncode,
            "log": str(log),
            "wrote": _answers_in(Path(str(job["waiting_for"]))),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(lambda item: run(*item), enumerate(jobs, start=1)))
