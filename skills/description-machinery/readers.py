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
import json
import re
import subprocess
import threading
import time
from pathlib import Path

from client_model_policy import validate_reader_command


def _answers_in(directory: Path) -> int:
    return len(list(directory.glob("*.json"))) if directory.is_dir() else 0


_FEED_LOCK = threading.Lock()


def _say(work: Path, what: str, **facts: object) -> None:
    """Append and flush one monitoring event without exposing the reader instruction."""

    line = {"at": time.strftime("%H:%M:%S"), "what": what, **facts}
    with _FEED_LOCK:
        with (work / "feed.jsonl").open("a", encoding="utf-8") as feed:
            feed.write(json.dumps(line, default=str) + "\n")
            feed.flush()


def _safe_activity(event: dict[str, object]) -> str | None:
    """Reduce a client event to an operation kind, never prompt or repository content."""

    if str(event.get("type")) in {"item.started", "item.completed"}:
        item = event.get("item") or {}
        if not isinstance(item, dict):
            return None
        kind = str(item.get("type") or "item")
        command = str(item.get("command") or "").strip()
        if command:
            return f"{kind} {Path(command.split()[0]).name}"
        tool = str(item.get("tool") or item.get("name") or "").strip()
        if tool:
            return f"{kind} {tool}"
        path = str(item.get("path") or "").strip()
        return f"{kind} {Path(path).name}" if path else kind
    if str(event.get("type")) != "assistant":
        return None
    message = event.get("message") or {}
    if not isinstance(message, dict):
        return None
    for block in message.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = str(block.get("name") or "tool")
        used = block.get("input") or {}
        if not isinstance(used, dict):
            return name
        command = str(used.get("command") or "").strip()
        if command:
            return f"{name} {Path(command.split()[0]).name}"
        path = str(used.get("file_path") or used.get("path") or "").strip()
        return f"{name} {Path(path).name}" if path else name
    return None


def _failure_kind(event: dict[str, object]) -> str | None:
    """Return only a structured failure kind; detailed client prose stays in the raw log."""

    event_type = str(event.get("type") or "")
    if event_type not in {"turn.failed", "error"}:
        return None
    error = event.get("error")
    code = str(error.get("code") or "").strip() if isinstance(error, dict) else ""
    return f"{event_type}:{code}" if code else event_type


def _watch(stream, work: Path, facts: dict[str, object], captured: list[str],
           failures: list[str]) -> None:
    """Losslessly retain stdout while projecting only safe structured activity to the feed."""

    for raw_line in stream:
        captured.append(raw_line)
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        activity = _safe_activity(event)
        if activity:
            _say(work, "agent", **facts, doing=activity)
        failure = _failure_kind(event)
        if failure:
            failures.append(failure)
            _say(work, "agent failure", **facts, error=failure)


def _drain(stream, captured: list[str]) -> None:
    for raw_line in stream:
        captured.append(raw_line)


def _reader_identity(scratch: Path) -> tuple[str | None, str | None]:
    try:
        record = json.loads((scratch / "reader.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None, None
    if not isinstance(record, dict):
        return None, None
    model = str(record.get("model") or "").strip() or None
    harness = str(record.get("harness") or "").strip() or None
    return model, harness


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

    parts = validate_reader_command(command)
    started = []

    def run(number: int, job: dict[str, object]) -> dict[str, object]:
        waiting_for = Path(str(job["waiting_for"]))
        scratch = Path(str(job.get("scratch") or work / f"launch-{tag}-{number}-scratch"))
        stage = str(job.get("stage") or tag)
        job_id = f"{stage}-{number}"
        began = time.monotonic()
        try:
            process = subprocess.Popen(
                parts, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=str(built), text=True,
            )
        except Exception as error:
            _say(work, "agent failure", machinery="description", job=job_id, stage=stage,
                 seat=number, waiting_for=waiting_for.name, error=type(error).__name__)
            raise
        identity = re.sub(r"[^A-Za-z0-9_.-]+", "-", waiting_for.name).strip("-") or "work"
        log = work / f"launch-{tag}-{number}-{identity}-{process.pid}.log"
        facts = {
            "machinery": "description", "job": job_id, "stage": stage, "seat": number,
            "waiting_for": waiting_for.name, "pid": process.pid,
        }
        _say(work, "agent started", **facts, log=log.name)
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        process.stdin.write(str(job["instruction"]))
        process.stdin.close()
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        failures: list[str] = []
        watching = threading.Thread(
            target=_watch, args=(process.stdout, work, facts, stdout_lines, failures), daemon=True,
        )
        draining = threading.Thread(target=_drain, args=(process.stderr, stderr_lines), daemon=True)
        watching.start()
        draining.start()
        process.wait()
        watching.join()
        draining.join()
        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
        log.write_text(
            stdout + ("\n--- stderr ---\n" + stderr if stderr else ""), encoding="utf-8",
        )
        wrote = _answers_in(waiting_for)
        model, harness = _reader_identity(scratch)
        failure = failures[-1] if failures else ("nonzero_exit" if process.returncode else None)
        if failure == "nonzero_exit":
            _say(work, "agent failure", **facts, error=failure)
        delivery = "delivered" if wrote else "missing"
        _say(
            work, "agent finished", **facts, wrote=wrote, delivery=delivery,
            seconds=round(time.monotonic() - began, 3), exit_code=process.returncode,
            failure=failure, model=model, harness=harness, log=log.name,
        )
        return {
            "exit_code": process.returncode, "log": str(log), "wrote": wrote,
            "delivery": delivery, "failure": failure, "model": model, "harness": harness,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(run, number, job) for number, job in enumerate(jobs, start=1)]
        for future in futures:
            started.append(future.result())
    return started
