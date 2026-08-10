#!/usr/bin/env python3
"""Start the readers a step asks for, instead of handing the packets to a person.

Nothing about a person's hand improves the answer — the gates decide, and they do not know who
pressed start. What the hand sets is the pace, and a rule kept in prose ("launch two, never one,
never tell either what the other found") is a rule the code does not hold. Here it does.

Who reads is still supplied from outside. This machinery never chooses a reader; whoever runs it
gives the command, and every reader writes down what it is.
"""

from __future__ import annotations

import concurrent.futures
import shlex
import subprocess
from pathlib import Path


def _answers_in(directory: Path) -> int:
    return len(list(directory.glob("*.json"))) if directory.is_dir() else 0


def _launch(jobs: list[dict[str, object]], command: str, built: Path,
            work: Path, tag: str) -> list[dict[str, object]]:
    """Run the packets this step just wrote, instead of handing them to whoever is driving.

    Until now the step wrote the instruction and a person passed it to a reader. Nothing about
    that hand improved the answer — the gates decide the verdict and they do not know whose hand
    pressed start — but it set the pace: the loop moved as fast as somebody was watching it, and
    stopped when they stopped.

    What does not change is who reads. The command is supplied from outside, exactly as the reader
    was before; this machinery still never chooses one, and every reader still writes down what it
    is. The instruction goes in on standard input so nothing about it can be reshaped by a shell.
    """

    parts = shlex.split(command)
    started = []

    def run(number: int, job: dict[str, object]) -> dict[str, object]:
        log = work / f"launch-{tag}-{number}.log"
        done = subprocess.run(
            parts, input=str(job["instruction"]), cwd=str(built),
            capture_output=True, text=True,
        )
        log.write_text(done.stdout + ("\n--- stderr ---\n" + done.stderr if done.stderr else ""),
                       encoding="utf-8")
        return {"exit_code": done.returncode, "log": str(log),
                "wrote": _answers_in(Path(str(job["waiting_for"])))}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(run, number, job) for number, job in enumerate(jobs, start=1)]
        for future in futures:
            started.append(future.result())
    return started
