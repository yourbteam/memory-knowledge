#!/usr/bin/env python3
"""Drive one pending image-intake model stage through Codex."""

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
    projection_phase = (
        state.get("status") == "waiting_for_model"
        and state.get("phase") == "interviewing_first_projection"
        and state.get("waiting_for") == "projection-interviews/attempt-000001/interview.jsonl"
    )
    gap_phase = (
        state.get("status") == "waiting_for_model"
        and state.get("phase") == "formulating_gap_question"
        and state.get("waiting_for") == "gap-clarifications/attempt-000001/interview.jsonl"
    )
    gap_round_phase = (
        state.get("status") == "waiting_for_model"
        and (
            (
                state.get("phase") == "formulating_gap_question_round"
                and state.get("waiting_for")
                == "gap-question-rounds/round-000001/interview.jsonl"
            )
            or (
                state.get("phase") == "formulating_follow_up_gap_question_round"
                and state.get("waiting_for")
                == "gap-question-rounds/round-000002/interview.jsonl"
            )
        )
    )
    gap_answer_assessment_phase = (
        state.get("status") == "waiting_for_model"
        and state.get("phase") == "assessing_gap_answers"
        and state.get("waiting_for")
        == "gap-answer-assessments/round-000001/interview.jsonl"
    )
    resolution_phase = (
        state.get("status") == "waiting_for_model"
        and state.get("phase") == "resolving_gap_answer"
        and isinstance(state.get("gap_resolution"), dict)
        and isinstance(state["gap_resolution"].get("attempt"), int)
        and state.get("waiting_for")
        == f"gap-resolutions/attempt-{state['gap_resolution']['attempt']:06d}/interview.jsonl"
    )
    resolution_verification_phase = (
        state.get("status") == "waiting_for_model"
        and state.get("phase") == "verifying_gap_resolution"
        and isinstance(state.get("gap_resolution"), dict)
        and isinstance(state["gap_resolution"].get("attempt"), int)
        and state.get("waiting_for")
        == f"gap-resolution-verifications/attempt-{state['gap_resolution']['attempt']:06d}/interview.jsonl"
    )
    if not any(
        (
            projection_phase,
            gap_phase,
            gap_round_phase,
            gap_answer_assessment_phase,
            resolution_phase,
            resolution_verification_phase,
        )
    ):
        raise LaunchError("the intake is not waiting for a supported visual model stage")
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
    if gap_phase or gap_round_phase:
        return attachment, [
            sys.executable,
            str(START_INTAKE),
            "--work",
            str(work),
            "--run-gap-clarification",
        ]
    if gap_answer_assessment_phase:
        return attachment, [
            sys.executable,
            str(START_INTAKE),
            "--work",
            str(work),
            "--run-gap-answer-assessment",
        ]
    if resolution_phase or resolution_verification_phase:
        return attachment, [
            sys.executable,
            str(START_INTAKE),
            "--work",
            str(work),
            (
                "--run-gap-resolution-verification"
                if resolution_verification_phase
                else "--run-gap-resolution"
            ),
        ]
    candidate = work / "projection-interviews" / "attempt-000001" / "projection.json"
    verification = work / "projection-verifications" / "attempt-000001" / "verification.json"
    corrections = work / "relationship-corrections" / "attempt-000001" / "corrections.json"
    correction_verification = (
        work / "relationship-correction-verifications" / "attempt-000001" / "verification.json"
    )
    flag = "--run-projection-interview"
    if candidate.exists() and int(state.get("projection_interview_contract", 0)) >= 7:
        flag = "--run-projection-verification"
    if verification.exists():
        try:
            verification_value = json.loads(verification.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LaunchError("the relationship verification result is invalid") from error
        rejected = any(
            item.get("verdict") != "supported"
            for item in verification_value.get("verdicts", [])
        )
        if rejected:
            flag = "--run-relationship-correction"
    if corrections.exists():
        try:
            correction_value = json.loads(corrections.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LaunchError("the relationship correction result is invalid") from error
        proposed = any(
            item.get("action") == "propose_replacement_endpoint"
            for item in correction_value.get("corrections", [])
        )
        if proposed and not correction_verification.exists():
            flag = "--run-correction-verification"
    command = [
        sys.executable,
        str(START_INTAKE),
        "--work",
        str(work),
        flag,
    ]
    return attachment, command


def build_codex_argv(
    executable: str,
    work: Path,
    attachment: Path,
    interview_command: list[str],
) -> list[str]:
    command_text = " ".join(json.dumps(part) for part in interview_command)
    flag = interview_command[-1]
    independently = flag in {
        "--run-projection-verification",
        "--run-correction-verification",
        "--run-gap-resolution-verification",
    }
    correction = flag == "--run-relationship-correction"
    gap_clarification = flag == "--run-gap-clarification"
    gap_answer_assessment = flag == "--run-gap-answer-assessment"
    gap_resolution = flag == "--run-gap-resolution"
    evidence_instruction = (
        "the code-bound preserved answer and visible source context"
        if gap_answer_assessment or gap_resolution
        else "visible source evidence"
    )
    prompt = (
        (
            "Inspect the attached frozen source and formulate one focused operator question for each code-bound gap presented. "
            if gap_clarification else
            "Inspect the attached frozen source and judge each code-bound preserved answer only against its exact gap. "
            if gap_answer_assessment else
            "Inspect the attached frozen source and complete only the code-controlled gap-resolution interview. When an accepted assessment is bound, do not reassess it; supply only the requested relationship facts. "
            if gap_resolution else
            "Independently inspect the attached frozen source without relying on the producer's "
            "relationship conclusions. "
            if independently else
            "Inspect the attached frozen source and address only independently rejected relationships. "
            if correction else
            "Inspect the attached frozen source. "
        )
        + "The command is a self-contained local controller that owns its ordering, journaling, "
        + "validation, and stopping. Run it immediately; do not invoke task intake, sequence "
        + "selection, discovery, repository workflows, or repository instruction reads. "
        + "Run this exact interactive command in a PTY: "
        + f"{command_text}. Answer every displayed question one at a time using {evidence_instruction}. "
        + "Do not create or edit the projection, interview journal, ledger, or "
        + "state directly. Do not assess projection completeness. Continue until the command "
        + "prints its terminal JSON result, then report that result."
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
    print("Constraints: Use an intake currently waiting for a supported image-intake model stage.")
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
    seen: set[tuple[str, ...]] = set()
    while True:
        command_key = tuple(interview_command)
        if command_key in seen:
            print(json.dumps({"ok": False, "error": "the intake did not advance after a model stage"}, sort_keys=True))
            return 3
        seen.add(command_key)
        argv = build_codex_argv(executable, work, attachment, interview_command)
        completed = subprocess.run(argv, check=False)
        if completed.returncode != 0:
            return completed.returncode
        try:
            attachment, interview_command = load_request(work)
        except LaunchError:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
