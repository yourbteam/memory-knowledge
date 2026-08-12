#!/usr/bin/env python3
"""Drive one pending image projection interview through Codex."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


START_INTAKE = Path(__file__).resolve().with_name("start_intake.py")


class LaunchError(ValueError):
    """The saved intake cannot be launched through this adapter."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_request(work: Path) -> tuple[Path, list[str]]:
    work = work.expanduser().resolve()
    try:
        state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LaunchError("the intake state is unavailable or invalid") from error
    if not isinstance(state, dict):
        raise LaunchError("the intake state must be an object")
    if (
        state.get("status") != "waiting_for_model"
        or state.get("phase") != "interviewing_first_projection"
        or state.get("waiting_for") != "projection-interviews/attempt-000001/interview.jsonl"
    ):
        raise LaunchError("the intake is not waiting for its first projection interview")
    source = state.get("first_source")
    if not isinstance(source, dict):
        raise LaunchError("the frozen first-source record is missing")
    media_type = source.get("media_type")
    if not isinstance(media_type, str) or not media_type.startswith("image/"):
        raise LaunchError("the pending source is not supported by the image projection adapter")
    stored_path = source.get("stored_path")
    expected_sha256 = source.get("sha256")
    if not isinstance(stored_path, str) or not isinstance(expected_sha256, str):
        raise LaunchError("the frozen first-source identity is incomplete")
    attachment = (work / stored_path).resolve()
    try:
        attachment.relative_to(work)
    except ValueError as error:
        raise LaunchError("the frozen first source escapes the intake directory") from error
    if not attachment.is_file() or _sha256(attachment) != expected_sha256:
        raise LaunchError("the frozen first source is unavailable or has changed")
    command = [
        sys.executable,
        str(START_INTAKE),
        "--work",
        str(work),
        "--run-projection-interview",
    ]
    return attachment, command


def build_codex_argv(
    executable: str,
    work: Path,
    attachment: Path,
    interview_command: list[str],
) -> list[str]:
    command_text = " ".join(json.dumps(part) for part in interview_command)
    prompt = (
        "Inspect the attached frozen source, then run this exact interactive command in a PTY: "
        f"{command_text}. Answer every displayed question one at a time using only visible "
        "source evidence. Do not create or edit the projection, interview journal, ledger, or "
        "state directly. Do not assess projection completeness. Continue until the command "
        "prints its terminal JSON result, then report that result."
    )
    return [
        executable,
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(work),
        "--image",
        str(attachment),
        "--",
        prompt,
    ]


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps({"ok": False, "error": "this launcher accepts no arguments"}))
        return 2
    print("Question: Intake work directory")
    print("Response format: One absolute directory path.")
    print("Example: /private/tmp/example-intake")
    print("Constraints: Use an intake currently waiting for its first projection interview.")
    try:
        work = Path(input("Answer: ").strip()).expanduser().resolve()
        attachment, interview_command = load_request(work)
    except (EOFError, LaunchError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    executable = shutil.which("codex")
    if executable is None:
        print(json.dumps({"ok": False, "error": "codex executable is unavailable"}, sort_keys=True))
        return 3
    argv = build_codex_argv(executable, work, attachment, interview_command)
    completed = subprocess.run(argv, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
