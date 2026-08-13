#!/usr/bin/env python3
"""Create or resume the first interview stages of an information intake."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid


CONTRACT = 1
OPENING_QUESTION = {
    "id": "intake-purpose",
    "asks": "What information should this intake make AI-readable?",
}
FIRST_SOURCE_QUESTION = {
    "id": "first-source",
    "asks": "Please provide the first source for this intake.",
}
ASSESSMENT_SCHEMA = 1
LOCAL_FILE_ADAPTER_VERSION = 1

_INTERVIEW_SPEC = importlib.util.spec_from_file_location(
    "info_intake_projection_interview",
    Path(__file__).resolve().with_name("projection_interview.py"),
)
if _INTERVIEW_SPEC is None or _INTERVIEW_SPEC.loader is None:
    raise RuntimeError("projection interview engine is unavailable")
projection_interview = importlib.util.module_from_spec(_INTERVIEW_SPEC)
_INTERVIEW_SPEC.loader.exec_module(projection_interview)
PROJECTION_INTERVIEW_CONTRACT = projection_interview.CONTRACT
_PURPOSE_SPEC = importlib.util.spec_from_file_location(
    "info_intake_purpose_interview",
    Path(__file__).resolve().with_name("purpose_interview.py"),
)
if _PURPOSE_SPEC is None or _PURPOSE_SPEC.loader is None:
    raise RuntimeError("purpose interview engine is unavailable")
purpose_interview = importlib.util.module_from_spec(_PURPOSE_SPEC)
_PURPOSE_SPEC.loader.exec_module(purpose_interview)
_VERIFICATION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_relationship_verification",
    Path(__file__).resolve().with_name("relationship_verification.py"),
)
if _VERIFICATION_SPEC is None or _VERIFICATION_SPEC.loader is None:
    raise RuntimeError("relationship verification engine is unavailable")
relationship_verification = importlib.util.module_from_spec(_VERIFICATION_SPEC)
_VERIFICATION_SPEC.loader.exec_module(relationship_verification)
_CORRECTION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_relationship_correction",
    Path(__file__).resolve().with_name("relationship_correction.py"),
)
if _CORRECTION_SPEC is None or _CORRECTION_SPEC.loader is None:
    raise RuntimeError("relationship correction engine is unavailable")
relationship_correction = importlib.util.module_from_spec(_CORRECTION_SPEC)
_CORRECTION_SPEC.loader.exec_module(relationship_correction)
_GAP_CLARIFICATION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_gap_clarification",
    Path(__file__).resolve().with_name("gap_clarification.py"),
)
if _GAP_CLARIFICATION_SPEC is None or _GAP_CLARIFICATION_SPEC.loader is None:
    raise RuntimeError("gap clarification engine is unavailable")
gap_clarification = importlib.util.module_from_spec(_GAP_CLARIFICATION_SPEC)
_GAP_CLARIFICATION_SPEC.loader.exec_module(gap_clarification)
_GAP_ANSWER_ASSESSMENT_SPEC = importlib.util.spec_from_file_location(
    "info_intake_gap_answer_assessment",
    Path(__file__).resolve().with_name("gap_answer_assessment.py"),
)
if (
    _GAP_ANSWER_ASSESSMENT_SPEC is None
    or _GAP_ANSWER_ASSESSMENT_SPEC.loader is None
):
    raise RuntimeError("gap answer assessment engine is unavailable")
gap_answer_assessment = importlib.util.module_from_spec(
    _GAP_ANSWER_ASSESSMENT_SPEC
)
_GAP_ANSWER_ASSESSMENT_SPEC.loader.exec_module(gap_answer_assessment)
_GAP_RESOLUTION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_gap_resolution",
    Path(__file__).resolve().with_name("gap_resolution.py"),
)
if _GAP_RESOLUTION_SPEC is None or _GAP_RESOLUTION_SPEC.loader is None:
    raise RuntimeError("gap resolution engine is unavailable")
gap_resolution = importlib.util.module_from_spec(_GAP_RESOLUTION_SPEC)
_GAP_RESOLUTION_SPEC.loader.exec_module(gap_resolution)
_GAP_RESOLUTION_VERIFICATION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_gap_resolution_verification",
    Path(__file__).resolve().with_name("gap_resolution_verification.py"),
)
if (
    _GAP_RESOLUTION_VERIFICATION_SPEC is None
    or _GAP_RESOLUTION_VERIFICATION_SPEC.loader is None
):
    raise RuntimeError("gap resolution verification engine is unavailable")
gap_resolution_verification = importlib.util.module_from_spec(
    _GAP_RESOLUTION_VERIFICATION_SPEC
)
_GAP_RESOLUTION_VERIFICATION_SPEC.loader.exec_module(
    gap_resolution_verification
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _ledger_entry(
    sequence: int, event: str, payload: dict[str, object], previous: str | None
) -> dict[str, object]:
    entry: dict[str, object] = {
        "sequence": sequence,
        "event": event,
        "previous_entry_sha256": previous,
        **payload,
    }
    entry["entry_sha256"] = _digest_bytes(_canonical(entry))
    return entry


def _validate_ledger(path: Path) -> tuple[list[dict[str, object]], str | None]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], "ledger unavailable"
    entries: list[dict[str, object]] = []
    previous: str | None = None
    for sequence, line in enumerate(lines, start=1):
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return [], f"ledger entry {sequence} is not valid JSON"
        if not isinstance(entry, dict):
            return [], f"ledger entry {sequence} is not an object"
        claimed = entry.pop("entry_sha256", None)
        actual = _digest_bytes(_canonical(entry))
        entry["entry_sha256"] = claimed
        if entry.get("sequence") != sequence:
            return [], f"ledger entry {sequence} has the wrong sequence"
        if entry.get("previous_entry_sha256") != previous:
            return [], f"ledger entry {sequence} breaks the hash chain"
        if claimed != actual:
            return [], f"ledger entry {sequence} has changed"
        previous = str(claimed)
        entries.append(entry)
    return entries, None


def _blocked(stopped: str, why: str) -> dict[str, object]:
    return {"status": "blocked", "stopped": stopped, "why": why}


def _operator_result(state: dict[str, object], work: Path) -> dict[str, object]:
    return {
        "status": "needs_operator",
        "stopped": str(state["phase"]),
        "intake_id": state["intake_id"],
        "question": state["question"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _model_result(state: dict[str, object], work: Path) -> dict[str, object]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--work",
        str(work.resolve()),
        "--run-purpose-interview",
    ]
    return {
        "status": "waiting_for_model",
        "stopped": "assessing_intake_purpose",
        "intake_id": state["intake_id"],
        "work": [{
            "stage": "assess_intake_purpose",
            "instruction": (
                "Run the command and answer only the typed question currently displayed. "
                "Code controls allowed choices and assembles the assessment."
            ),
            "command": command,
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _source_ready_result(state: dict[str, object], work: Path) -> dict[str, object]:
    return {
        "status": "ready_for_projection",
        "stopped": "first_source_frozen",
        "intake_id": state["intake_id"],
        "source": state["first_source"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _projection_waiting_result(
    state: dict[str, object], work: Path, stage: str | None = None,
) -> dict[str, object]:
    if stage is None:
        candidate_path = work / "projection-interviews" / "attempt-000001" / "projection.json"
        stage = (
            "verify_first_projection"
            if candidate_path.exists() and int(state.get("projection_interview_contract", 0)) >= 7
            else "project_first_source"
        )
    stages = {
        "project_first_source": {
            "flag": "--run-projection-interview",
            "stopped": "interviewing_first_projection",
            "instruction": (
                "Inspect the attached frozen source, run the command, and answer only the "
                "typed question currently displayed. Code controls allowed choices and assembly."
            ),
        },
        "verify_first_projection": {
            "flag": "--run-projection-verification",
            "stopped": "verifying_first_projection",
            "instruction": (
                "Independently inspect the attached frozen source, run the command, and answer "
                "only the typed question currently displayed. Code controls allowed choices and assembly."
            ),
        },
        "correct_rejected_relationships": {
            "flag": "--run-relationship-correction",
            "stopped": "correcting_rejected_relationships",
            "instruction": (
                "Inspect the attached frozen source, run the command, and address only the independently "
                "rejected relationships. Code controls replacement choices, coordinate binding, and gaps."
            ),
        },
        "verify_relationship_corrections": {
            "flag": "--run-correction-verification",
            "stopped": "verifying_relationship_corrections",
            "instruction": (
                "Independently inspect the attached frozen source, run the command, and verify only the "
                "proposed corrected relationships. Code controls allowed verdicts and final assembly."
            ),
        },
    }
    selected = stages[stage]
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--work",
        str(work.resolve()),
        selected["flag"],
    ]
    return {
        "status": "waiting_for_model",
        "stopped": selected["stopped"],
        "intake_id": state["intake_id"],
        "work": [{
            "stage": stage,
            "instruction": selected["instruction"],
            "attachments": [str((work / "sources" / "source-000003").resolve())],
            "command": command,
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _projection_ready_result(state: dict[str, object], work: Path) -> dict[str, object]:
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "first_projection_recorded",
        "intake_id": state["intake_id"],
        "projection": state["first_projection"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _gap_clarification_model_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--work",
        str(work.resolve()),
        "--run-gap-clarification",
    ]
    return {
        "status": "waiting_for_model",
        "stopped": "formulating_gap_question",
        "intake_id": state["intake_id"],
        "work": [{
            "stage": "formulate_gap_question",
            "instruction": (
                "Inspect the frozen source and the code-bound gap, then answer only the typed "
                "question. Code controls the gap identity and assembles the operator question."
            ),
            "attachments": [str((work / "sources" / "source-000003").resolve())],
            "command": command,
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _gap_question_round_model_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    return {
        "status": "waiting_for_model",
        "stopped": "formulating_gap_question_round",
        "intake_id": state["intake_id"],
        "work": [{
            "stage": "formulate_gap_question_round",
            "instruction": (
                "Inspect the frozen source and answer only each typed question displayed. "
                "Code fixes every current gap, their order, and the final question round."
            ),
            "attachments": [str((work / "sources" / "source-000003").resolve())],
            "command": [
                sys.executable,
                str(Path(__file__).resolve()),
                "--work",
                str(work.resolve()),
                "--run-gap-clarification",
            ],
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _follow_up_gap_question_round_model_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    return {
        "status": "waiting_for_model",
        "stopped": "formulating_follow_up_gap_question_round",
        "intake_id": state["intake_id"],
        "work": [{
            "stage": "formulate_follow_up_gap_question_round",
            "instruction": (
                "Inspect the frozen source and each code-bound failed clarification. "
                "Answer only the typed questions. Code fixes the complete eligible "
                "gap set, prior evidence, order, and persisted follow-up round."
            ),
            "attachments": [str((work / "sources" / "source-000003").resolve())],
            "command": [
                sys.executable,
                str(Path(__file__).resolve()),
                "--work",
                str(work.resolve()),
                "--run-gap-clarification",
            ],
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _follow_up_gap_question_round_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    saved = state["follow_up_gap_question_round"]
    assert isinstance(saved, dict)
    return {
        "status": "ready_for_operator_interview",
        "stopped": "follow_up_gap_question_round_recorded",
        "intake_id": state["intake_id"],
        "round": saved["round"],
        "question_count": saved["question_count"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _prepared_question_round_operator_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    interview = state["prepared_question_round_interview"]
    saved = state["follow_up_gap_question_round"]
    assert isinstance(interview, dict) and isinstance(saved, dict)
    answers = interview["answers"]
    questions = saved["questions"]
    assert isinstance(answers, list) and isinstance(questions, list)
    return {
        "status": "needs_operator",
        "stopped": "awaiting_prepared_question_round_answer",
        "intake_id": state["intake_id"],
        "round": interview["round"],
        "question": state["question"],
        "answered_question_count": len(answers),
        "question_count": len(questions),
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _prepared_question_round_answered_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    interview = state["prepared_question_round_interview"]
    saved = state["follow_up_gap_question_round"]
    assert isinstance(interview, dict) and isinstance(saved, dict)
    answers = interview["answers"]
    questions = saved["questions"]
    assert isinstance(answers, list) and isinstance(questions, list)
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "prepared_question_round_answered",
        "intake_id": state["intake_id"],
        "round": interview["round"],
        "answered_question_count": len(answers),
        "question_count": len(questions),
        "projection": state.get("current_projection", state["first_projection"]),
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _gap_question_round_operator_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    answers = state.get("gap_question_answers", [])
    questions = state.get("questions", [])
    return {
        "status": "needs_operator",
        "stopped": "awaiting_gap_answers",
        "intake_id": state["intake_id"],
        "question": state["question"],
        "answered_question_count": len(answers) if isinstance(answers, list) else 0,
        "question_count": len(questions) if isinstance(questions, list) else 0,
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _gap_question_round_answered_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    answers = state.get("gap_question_answers", [])
    questions = state.get("questions", [])
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "gap_question_round_answered",
        "intake_id": state["intake_id"],
        "projection": state["first_projection"],
        "answered_question_count": len(answers) if isinstance(answers, list) else 0,
        "question_count": len(questions) if isinstance(questions, list) else 0,
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _gap_answer_assessment_model_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    return {
        "status": "waiting_for_model",
        "stopped": "assessing_gap_answers",
        "intake_id": state["intake_id"],
        "work": [{
            "stage": "assess_gap_answers",
            "instruction": (
                "Inspect each code-bound preserved answer and judge only whether it "
                "resolves its exact gap. Code fixes every pair, order, and verdict choice."
            ),
            "attachments": [str((work / "sources" / "source-000003").resolve())],
            "command": [
                sys.executable,
                str(Path(__file__).resolve()),
                "--work",
                str(work.resolve()),
                "--run-gap-answer-assessment",
            ],
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _gap_answer_assessment_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    assessment = state["gap_answer_assessment"]
    assert isinstance(assessment, dict)
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "gap_answer_assessment_recorded",
        "intake_id": state["intake_id"],
        "projection": state["first_projection"],
        "assessment_count": assessment["assessment_count"],
        "assessments": assessment["assessments"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _gap_source_ready_result(state: dict[str, object], work: Path) -> dict[str, object]:
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "gap_operator_source_recorded",
        "intake_id": state["intake_id"],
        "projection": state["first_projection"],
        "operator_source": state["gap_operator_source"],
        "operator_projection": state["gap_operator_projection"],
        "answers_gap": state["gap_clarification"]["gap"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _gap_resolution_model_result(
    state: dict[str, object], work: Path, *, verification: bool = False
) -> dict[str, object]:
    resolution = state.get("gap_resolution")
    assessed_answer = (
        isinstance(resolution, dict)
        and resolution.get("mode") == "assessed_answer"
    )
    flag = (
        "--run-gap-resolution-verification"
        if verification
        else "--run-gap-resolution"
    )
    return {
        "status": "waiting_for_model",
        "stopped": (
            "verifying_gap_resolution" if verification else "resolving_gap_answer"
        ),
        "intake_id": state["intake_id"],
        "work": [{
            "stage": (
                "verify_gap_resolution" if verification else "resolve_gap_answer"
            ),
            "instruction": (
                "Independently inspect the frozen source and verify the code-bound proposed relationship."
                if verification
                else "Inspect the frozen source and supply only the missing relationship facts for the code-bound resolving answer."
                if assessed_answer
                else "Inspect the frozen source and assess whether the preserved operator answer resolves the code-bound gap."
            ),
            "attachments": [str((work / "sources" / "source-000003").resolve())],
            "command": [
                sys.executable,
                str(Path(__file__).resolve()),
                "--work",
                str(work.resolve()),
                flag,
            ],
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _gap_resolution_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    return {
        "status": "ready_for_projection_assessment",
        "stopped": str(state["phase"]),
        "intake_id": state["intake_id"],
        "projection": state.get("current_projection", state["first_projection"]),
        "original_projection": state["first_projection"],
        "gap_resolution": state["gap_resolution"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _write_state(path: Path, state: dict[str, object]) -> None:
    temporary = path.with_suffix(".json.next")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _append_ledger(path: Path, entries: list[dict[str, object]]) -> None:
    with path.open("a", encoding="utf-8") as ledger:
        for entry in entries:
            ledger.write(json.dumps(entry, sort_keys=True) + "\n")


def _source_record(number: int, sha256: str) -> dict[str, object]:
    return {
        "id": f"source-{number:06d}",
        "kind": "human_operator_prompt",
        "path": f"sources/source-{number:06d}.txt",
        "sha256": sha256,
    }


def _projection_record(number: int, sha256: str) -> dict[str, object]:
    return {
        "id": f"projection-{number:06d}",
        "version": 1,
        "path": f"projections/projection-{number:06d}.txt",
        "sha256": sha256,
        "coverage": {
            "status": "complete",
            "source_units": 1,
            "represented_units": 1,
            "gaps": [],
        },
    }


def _gap_answer_source_record(
    sha256: str, question_id: str, gap: dict[str, object]
) -> dict[str, object]:
    return {
        "id": "source-000004",
        "kind": "human_operator_answer",
        "path": "sources/source-000004.txt",
        "sha256": sha256,
        "answers_question": question_id,
        "answers_gap": {
            key: gap[key]
            for key in ("projection_sha256", "collection", "kind", "id", "record_sha256")
        },
    }


def _gap_answer_projection_record(sha256: str) -> dict[str, object]:
    return {
        "id": "projection-source-000004-v1",
        "source_id": "source-000004",
        "version": 1,
        "path": "projections/source-000004-v1.txt",
        "sha256": sha256,
        "method": "verbatim_utf8",
        "coverage": {
            "status": "complete",
            "source_units": 1,
            "represented_units": 1,
            "gaps": [],
        },
    }


def _round_answer_source_record(
    number: int, sha256: str, question: dict[str, object]
) -> dict[str, object]:
    return {
        "id": f"source-{number:06d}",
        "kind": "human_operator_answer",
        "path": f"sources/source-{number:06d}.txt",
        "sha256": sha256,
        "answers_question": question["id"],
        "answers_gap": question["answers_gap"],
    }


def _round_answer_projection_record(number: int, sha256: str) -> dict[str, object]:
    return {
        "id": f"projection-source-{number:06d}-v1",
        "source_id": f"source-{number:06d}",
        "version": 1,
        "path": f"projections/source-{number:06d}-v1.txt",
        "sha256": sha256,
        "method": "verbatim_utf8",
        "coverage": {
            "status": "complete",
            "source_units": 1,
            "represented_units": 1,
            "gaps": [],
        },
    }


def _detect_media_type(path: Path) -> tuple[str, str]:
    try:
        completed = subprocess.run(
            ["file", "--brief", "--mime-type", "--", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "application/octet-stream", "undetermined"
    media_type = completed.stdout.strip()
    if completed.returncode == 0 and "/" in media_type and "\n" not in media_type:
        return media_type, "file --brief --mime-type"
    return "application/octet-stream", "undetermined"


def _local_file_record(
    supplied: Path,
    resolved: Path,
    stored_path: str,
    content: bytes,
    media_type: str,
    media_type_basis: str,
) -> dict[str, object]:
    return {
        "id": "source-000003",
        "kind": "local_file",
        "adapter": {"name": "local_file", "version": LOCAL_FILE_ADAPTER_VERSION},
        "provided_path": str(supplied),
        "resolved_path": str(resolved),
        "filename": supplied.name,
        "stored_path": stored_path,
        "size_bytes": len(content),
        "sha256": _digest_bytes(content),
        "media_type": media_type,
        "media_type_basis": media_type_basis,
    }


def _validate_source_projection(
    work: Path,
    entry: dict[str, object],
    number: int,
    expected_bytes: bytes,
) -> str | None:
    sha256 = _digest_bytes(expected_bytes)
    if entry.get("source") != _source_record(number, sha256):
        return f"source {number} does not match its ledger record"
    if entry.get("projection") != _projection_record(number, sha256):
        return f"projection {number} does not match its ledger record"
    source_path = work / str(_source_record(number, sha256)["path"])
    projection_path = work / str(_projection_record(number, sha256)["path"])
    try:
        source_bytes = source_path.read_bytes()
        projection_bytes = projection_path.read_bytes()
    except OSError:
        return f"source or projection {number} is unavailable"
    if source_bytes != expected_bytes:
        return f"immutable source {number} has changed"
    if projection_bytes != source_bytes:
        return f"immutable projection {number} has changed"
    return None


def _load_bound(
    work: Path, opening_bytes: bytes
) -> tuple[dict[str, object] | None, list[dict[str, object]], dict[str, object] | None]:
    state_path = work / "intake-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None, [], _blocked("invalid intake state", "intake-state.json cannot be read")
    if not isinstance(state, dict) or state.get("contract") != CONTRACT:
        return None, [], _blocked("invalid intake state", "the intake contract is missing or unsupported")
    intake_id = state.get("intake_id")
    if not isinstance(intake_id, str) or not intake_id.startswith("intake-"):
        return None, [], _blocked("invalid intake state", "the intake identity is missing or invalid")
    opening_sha256 = _digest_bytes(opening_bytes)
    if state.get("opening_sha256") != opening_sha256:
        return None, [], _blocked("input changed", "this work directory is bound to a different opening")

    entries, ledger_error = _validate_ledger(work / "ledger.jsonl")
    if ledger_error:
        return None, [], _blocked("invalid ledger", ledger_error)
    if state.get("ledger_entries") != len(entries):
        return None, [], _blocked("invalid ledger", "saved state and ledger length differ")
    if not entries or entries[-1].get("entry_sha256") != state.get("ledger_tail_sha256"):
        return None, [], _blocked("invalid ledger", "the saved ledger tail does not match the history")
    if any(entry.get("intake_id") != intake_id for entry in entries):
        return None, [], _blocked("invalid ledger", "a ledger entry belongs to a different intake")
    if len(entries) < 2 or entries[0].get("event") != "source_projected":
        return None, [], _blocked("invalid ledger", "the opening source projection is missing")
    if entries[1].get("event") != "operator_question_asked" or entries[1].get("question") != OPENING_QUESTION:
        return None, [], _blocked("invalid ledger", "the opening question is missing or changed")
    artifact_error = _validate_source_projection(work, entries[0], 1, opening_bytes)
    if artifact_error:
        return None, [], _blocked("immutable opening changed", artifact_error)
    return state, entries, None


def _accept_purpose(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    if not purpose.strip():
        return _blocked("purpose required", "preserve the operator's purpose answer before assessing it")
    if len(entries) != 2 or state.get("phase") != "awaiting_intake_purpose":
        return _blocked("invalid intake stage", "the purpose answer cannot be added at this stage")
    purpose_bytes = purpose.encode("utf-8")
    purpose_sha256 = _digest_bytes(purpose_bytes)
    source_path = work / "sources" / "source-000002.txt"
    projection_path = work / "projections" / "projection-000002.txt"
    assessment_dir = work / "purpose-interview"
    if source_path.exists() or projection_path.exists() or assessment_dir.exists():
        return _blocked("unbound purpose artifacts", "purpose artifacts already exist outside the ledger")
    assessment_dir.mkdir()
    source_path.write_bytes(purpose_bytes)
    projection_path.write_bytes(purpose_bytes)
    timestamp = datetime.now(timezone.utc).isoformat()
    third = _ledger_entry(
        3,
        "source_projected",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "answers_question": OPENING_QUESTION["id"],
            "source": _source_record(2, purpose_sha256),
            "projection": _projection_record(2, purpose_sha256),
        },
        str(entries[-1]["entry_sha256"]),
    )
    fourth = _ledger_entry(
        4,
        "model_assessment_requested",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "assessment": "intake_purpose_sufficiency",
            "interview_contract": ASSESSMENT_SCHEMA,
            "interview_path": "purpose-interview/interview.jsonl",
            "input_source_id": "source-000002",
        },
        str(third["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [third, fourth])
    state.update({
        "status": "waiting_for_model",
        "phase": "assessing_intake_purpose",
        "waiting_for": "purpose-interview/interview.jsonl",
        "question": None,
        "purpose_sha256": purpose_sha256,
        "ledger_entries": 4,
        "ledger_tail_sha256": fourth["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _model_result(state, work)


def _validate_purpose_stage(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    supplied_purpose: str | None,
) -> tuple[bytes | None, dict[str, object] | None]:
    if len(entries) < 4 or entries[2].get("event") != "source_projected":
        return None, _blocked("invalid ledger", "the purpose source projection is missing")
    purpose_path = work / "sources" / "source-000002.txt"
    try:
        purpose_bytes = purpose_path.read_bytes()
    except OSError:
        return None, _blocked("immutable purpose unavailable", str(purpose_path))
    if state.get("purpose_sha256") != _digest_bytes(purpose_bytes):
        return None, _blocked("immutable purpose changed", "the purpose no longer matches saved state")
    if supplied_purpose is not None and supplied_purpose.encode("utf-8") != purpose_bytes:
        return None, _blocked("purpose changed", "this intake is bound to the preserved purpose answer")
    artifact_error = _validate_source_projection(work, entries[2], 2, purpose_bytes)
    if artifact_error:
        return None, _blocked("immutable purpose changed", artifact_error)
    if entries[3].get("event") != "model_assessment_requested":
        return None, _blocked("invalid ledger", "the purpose assessment request is missing")
    expected_request = {
        "assessment": "intake_purpose_sufficiency",
        "interview_contract": ASSESSMENT_SCHEMA,
        "interview_path": "purpose-interview/interview.jsonl",
        "input_source_id": "source-000002",
    }
    if any(entries[3].get(key) != value for key, value in expected_request.items()):
        return None, _blocked("invalid ledger", "the purpose assessment request does not match its artifacts")
    return purpose_bytes, None


def _read_assessment(path: Path, purpose: str) -> tuple[dict[str, object] | None, str | None]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None, "the model result is unavailable or invalid JSON"
    expected = {
        "schema_version", "sufficient", "quote", "reason", "clarifying_question", "reader"
    }
    if not isinstance(result, dict) or set(result) != expected:
        return None, "the model result does not match the fixed assessment schema"
    reader = result.get("reader")
    if not isinstance(reader, dict) or set(reader) != {"model", "harness"}:
        return None, "the model result does not identify its reader"
    if any(not isinstance(reader.get(key), str) or not str(reader[key]).strip() for key in reader):
        return None, "the model and harness identities must be non-empty"
    if result.get("schema_version") != ASSESSMENT_SCHEMA:
        return None, "the model result uses an unsupported schema"
    sufficient = result.get("sufficient")
    quote = result.get("quote")
    reason = result.get("reason")
    question = result.get("clarifying_question")
    if sufficient not in {"yes", "no"}:
        return None, "sufficient must be 'yes' or 'no'"
    if not isinstance(reason, str) or not reason.strip():
        return None, "the assessment reason is empty"
    if not isinstance(quote, str) or not isinstance(question, str):
        return None, "quote and clarifying_question must be strings"
    if sufficient == "yes":
        if not quote.strip() or quote not in purpose:
            return None, "a sufficient assessment must quote the exact purpose answer"
        if question:
            return None, "a sufficient assessment cannot also ask a clarification"
    else:
        if quote:
            return None, "an insufficient assessment cannot claim supporting words"
        if (
            not question.strip()
            or len(question) > 240
            or "\n" in question
            or question.count("?") != 1
            or not question.endswith("?")
        ):
            return None, "an insufficient assessment must contain exactly one short question"
    return result, None


def _consume_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose_bytes: bytes,
) -> dict[str, object]:
    attempt_dir = work / "purpose-interview"
    try:
        assembled, interview_sha256, result_sha256 = purpose_interview.validate(
            attempt_dir,
            purpose=purpose_bytes.decode("utf-8"),
        )
        interview_entries = purpose_interview.journal._read_journal(
            attempt_dir / "interview.jsonl"
        )
    except purpose_interview.InterviewError as error:
        return _blocked("invalid purpose interview", str(error))
    result_path = attempt_dir / "assessment.json"
    assessment, assessment_error = _read_assessment(result_path, purpose_bytes.decode("utf-8"))
    if assessment_error:
        return _blocked("invalid purpose assessment", assessment_error)
    assert assessment is not None
    if assessment != assembled:
        return _blocked("invalid purpose interview", "the assembled assessment differs from its interview")
    if assessment["sufficient"] == "yes":
        phase = "awaiting_first_source"
        question = FIRST_SOURCE_QUESTION
    else:
        phase = "clarifying_intake_purpose"
        question = {
            "id": "intake-purpose-clarification",
            "asks": assessment["clarifying_question"],
        }
    timestamp = datetime.now(timezone.utc).isoformat()
    fifth = _ledger_entry(
        5,
        "model_assessment_completed",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "assessment": "intake_purpose_sufficiency",
            "interview_path": "purpose-interview/interview.jsonl",
            "interview_sha256": interview_sha256,
            "result_path": "purpose-interview/assessment.json",
            "result_sha256": result_sha256,
            "question_count": sum(
                entry["event"] == "question_asked" for entry in interview_entries
            ),
            "answer_count": sum(
                entry["event"] == "answer_recorded" for entry in interview_entries
            ),
            "rejected_answer_count": sum(
                entry["event"] == "answer_recorded" and entry["accepted"] is False
                for entry in interview_entries
            ),
            "result": assessment,
        },
        str(entries[-1]["entry_sha256"]),
    )
    sixth = _ledger_entry(
        6,
        "operator_question_asked",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "question": question,
        },
        str(fifth["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [fifth, sixth])
    state.update({
        "status": "needs_operator",
        "phase": phase,
        "waiting_for": question["id"],
        "question": question,
        "assessment_interview_sha256": interview_sha256,
        "assessment_result_sha256": result_sha256,
        "ledger_entries": 6,
        "ledger_tail_sha256": sixth["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _operator_result(state, work)


def _read_local_source(path: Path) -> tuple[Path | None, bytes | None, dict[str, object] | None]:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as error:
        return None, None, _blocked("source unavailable", str(error))
    if not resolved.is_file():
        return None, None, _blocked("source is not a file", str(resolved))
    try:
        content = resolved.read_bytes()
    except OSError as error:
        return None, None, _blocked("source unavailable", str(error))
    return resolved, content, None


def _acquire_first_source(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    supplied: Path,
) -> dict[str, object]:
    resolved, content, source_error = _read_local_source(supplied)
    if source_error:
        return source_error
    assert resolved is not None and content is not None
    stored_relative = "sources/source-000003"
    stored_path = work / stored_relative
    if stored_path.exists():
        return _blocked("unbound source artifact", "the first local-file artifact already exists")
    stored_path.write_bytes(content)
    media_type, media_type_basis = _detect_media_type(stored_path)
    source = _local_file_record(
        supplied, resolved, stored_relative, content, media_type, media_type_basis
    )
    seventh = _ledger_entry(
        7,
        "source_acquired",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "answers_question": FIRST_SOURCE_QUESTION["id"],
            "source": source,
            "projection": {
                "status": "pending",
                "why": "the source has been frozen but not yet converted",
            },
            "next_phase": "first_source_frozen",
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [seventh])
    state.update({
        "status": "ready_for_projection",
        "phase": "first_source_frozen",
        "waiting_for": None,
        "question": None,
        "first_source": source,
        "ledger_entries": 7,
        "ledger_tail_sha256": seventh["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _source_ready_result(state, work)


def _validate_frozen_first_source(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    supplied: Path | None,
) -> dict[str, object] | None:
    if len(entries) < 7 or entries[6].get("event") != "source_acquired":
        return _blocked("invalid ledger", "the first local-file acquisition is missing")
    source = entries[6].get("source")
    if not isinstance(source, dict) or state.get("first_source") != source:
        return _blocked("invalid ledger", "the saved first source does not match its acquisition entry")
    if entries[6].get("projection") != {
        "status": "pending",
        "why": "the source has been frozen but not yet converted",
    } or entries[6].get("next_phase") != "first_source_frozen":
        return _blocked("invalid ledger", "the acquisition entry does not preserve the pending projection state")
    expected_keys = {
        "id", "kind", "adapter", "provided_path", "resolved_path", "filename",
        "stored_path", "size_bytes", "sha256", "media_type", "media_type_basis",
    }
    if (
        set(source) != expected_keys
        or source.get("id") != "source-000003"
        or source.get("kind") != "local_file"
        or source.get("adapter") != {"name": "local_file", "version": LOCAL_FILE_ADAPTER_VERSION}
        or source.get("stored_path") != "sources/source-000003"
        or not all(
            isinstance(source.get(key), str) and bool(str(source[key]).strip())
            for key in (
                "provided_path", "resolved_path", "filename", "sha256",
                "media_type", "media_type_basis",
            )
        )
        or not isinstance(source.get("size_bytes"), int)
        or int(source["size_bytes"]) < 0
        or len(str(source["sha256"])) != 64
        or "/" not in str(source["media_type"])
    ):
        return _blocked("invalid ledger", "the first local-file source record has an invalid shape")
    if entries[6].get("answers_question") != FIRST_SOURCE_QUESTION["id"]:
        return _blocked("invalid ledger", "the acquisition is not linked to the first-source question")
    stored_path = work / str(source["stored_path"])
    try:
        frozen = stored_path.read_bytes()
    except OSError:
        return _blocked("immutable source unavailable", str(stored_path))
    if len(frozen) != source.get("size_bytes") or _digest_bytes(frozen) != source.get("sha256"):
        return _blocked("immutable source changed", "the frozen first source no longer matches its ledger record")
    if supplied is not None:
        resolved, current, source_error = _read_local_source(supplied)
        if source_error:
            return source_error
        assert resolved is not None and current is not None
        if str(supplied) != source.get("provided_path") or str(resolved) != source.get("resolved_path"):
            return _blocked("source origin changed", "this intake is bound to a different local-file origin")
        if current != frozen:
            return _blocked("source changed", "the supplied local file no longer matches the frozen source")
    return None


def _request_first_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    source = state["first_source"]
    assert isinstance(source, dict)
    if not str(source["media_type"]).startswith("image/"):
        return _blocked(
            "projection adapter unavailable",
            f"visual projection requires image/*; source-000003 is {source['media_type']}",
        )
    attempt_dir = work / "projection-interviews" / "attempt-000001"
    if attempt_dir.exists():
        return _blocked("unbound projection artifacts", "projection attempt 1 already exists outside the ledger")
    attempt_dir.mkdir(parents=True)
    eighth = _ledger_entry(
        8,
        "model_projection_interview_started",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": 1,
            "source_id": "source-000003",
            "source_sha256": source["sha256"],
            "interview_contract": PROJECTION_INTERVIEW_CONTRACT,
            "interview_path": "projection-interviews/attempt-000001/interview.jsonl",
            "attachment_path": "sources/source-000003",
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [eighth])
    state.update({
        "status": "waiting_for_model",
        "phase": "interviewing_first_projection",
        "waiting_for": "projection-interviews/attempt-000001/interview.jsonl",
        "projection_interview_contract": PROJECTION_INTERVIEW_CONTRACT,
        "ledger_entries": 8,
        "ledger_tail_sha256": eighth["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _projection_waiting_result(state, work)


def _apply_independent_verification(
    projection: dict[str, object],
    verification: dict[str, object],
    corrections: dict[str, object] | None = None,
    correction_verification: dict[str, object] | None = None,
) -> dict[str, object] | None:
    relationships = projection["relationships"]
    verdicts = verification["verdicts"]
    assert isinstance(relationships, list) and isinstance(verdicts, list)
    readable_relationship_count = sum(
        relationship["status"] == "readable" for relationship in relationships
    )
    if len(verdicts) != readable_relationship_count:
        return _blocked(
            "invalid relationship verification",
            "every readable proposed relationship requires one verdict",
        )
    correction_items = corrections["corrections"] if corrections is not None else []
    assert isinstance(correction_items, list)
    correction_by_original = {
        item["original_relationship_id"]: item for item in correction_items
    }
    corrected_verdicts = (
        correction_verification["verdicts"] if correction_verification is not None else []
    )
    assert isinstance(corrected_verdicts, list)
    corrected_verdict_by_id = {
        item["relationship_id"]: item for item in corrected_verdicts
    }
    final_relationships: list[dict[str, object]] = []
    verdict_index = 0
    for relationship in relationships:
        if relationship["status"] == "gap":
            relationship["verification_eligibility"] = {
                "status": "not_applicable_existing_gap",
                "reason": relationship["gap_reason"],
            }
            final_relationships.append(relationship)
            continue
        verdict = verdicts[verdict_index]
        verdict_index += 1
        if verdict["relationship_id"] != relationship["id"]:
            return _blocked("invalid relationship verification", "relationship verdict order changed")
        original_verification = {
            "verdict": verdict["verdict"],
            "reason": verdict["reason"],
            "reader": verification["reader"],
        }
        relationship["independent_visual_verification"] = original_verification
        if verdict["verdict"] == "supported":
            final_relationships.append(relationship)
            continue
        correction = correction_by_original.get(relationship["id"])
        if correction is None:
            return _blocked(
                "invalid relationship correction",
                f"rejected relationship {relationship['id']} has no correction outcome",
            )
        if correction["action"] == "preserve_gap":
            relationship.update({
                "status": "gap",
                "description": "",
                "gap_reason": correction["gap_reason"],
                "correction_outcome": {
                    "action": "preserve_gap",
                    "reason": correction["gap_reason"],
                },
            })
            final_relationships.append(relationship)
            continue
        corrected = dict(correction["corrected_relationship"])
        corrected_verdict = corrected_verdict_by_id.get(corrected["id"])
        if corrected_verdict is None:
            return _blocked(
                "invalid relationship correction verification",
                f"corrected relationship {corrected['id']} has no independent verdict",
            )
        correction_evidence = {
            "action": "propose_replacement_endpoint",
            "candidate_relationship_id": corrected["id"],
            "replacement_role": correction["replacement_role"],
            "replacement_source": correction["replacement_source"],
            "replacement_element": correction["replacement_element"],
            "independent_visual_verification": {
                "verdict": corrected_verdict["verdict"],
                "reason": corrected_verdict["reason"],
                "reader": correction_verification["reader"],
            },
        }
        if corrected_verdict["verdict"] == "supported":
            if correction["replacement_element"].get("created_by_correction") is True:
                replacement = {
                    key: value for key, value in correction["replacement_element"].items()
                    if key != "created_by_correction"
                }
                projection["elements"].append(replacement)
            corrected["id"] = relationship["id"]
            corrected["independent_visual_verification"] = original_verification
            corrected["correction_outcome"] = correction_evidence
            final_relationships.append(corrected)
        else:
            relationship.update({
                "status": "gap",
                "description": "",
                "gap_reason": corrected_verdict["reason"],
                "correction_outcome": correction_evidence,
            })
            final_relationships.append(relationship)
    if len(correction_by_original) != sum(
        verdict["verdict"] != "supported" for verdict in verdicts
    ):
        return _blocked("invalid relationship correction", "correction outcome coverage changed")
    if len(corrected_verdict_by_id) != sum(
        item["action"] == "propose_replacement_endpoint" for item in correction_items
    ):
        return _blocked(
            "invalid relationship correction verification",
            "corrected relationship verdict coverage changed",
        )
    projection["relationships"] = final_relationships
    return None


def _consume_first_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    attempt_dir = work / "projection-interviews" / "attempt-000001"
    source = state["first_source"]
    assert isinstance(source, dict)
    try:
        projection, journal_sha256, attempt_projection_sha256 = projection_interview.validate(
            attempt_dir,
            source_sha256=str(source["sha256"]),
            purpose=purpose,
            contract=int(entries[7]["interview_contract"]),
        )
        journal_entries = projection_interview._read_journal(attempt_dir / "interview.jsonl")
    except projection_interview.InterviewError as error:
        return _blocked("invalid projection interview", str(error))
    verification: dict[str, object] | None = None
    verification_journal_sha256: str | None = None
    verification_result_sha256: str | None = None
    corrections: dict[str, object] | None = None
    correction_journal_sha256: str | None = None
    correction_result_sha256: str | None = None
    correction_candidate_sha256: str | None = None
    correction_verification: dict[str, object] | None = None
    correction_verification_journal_sha256: str | None = None
    correction_verification_result_sha256: str | None = None
    if int(entries[7]["interview_contract"]) >= 7:
        verification_dir = work / "projection-verifications" / "attempt-000001"
        if not (verification_dir / "verification.json").exists():
            return _projection_waiting_result(state, work, "verify_first_projection")
        try:
            verification, verification_journal_sha256, verification_result_sha256 = (
                relationship_verification.validate(
                    verification_dir,
                    candidate_path=attempt_dir / "projection.json",
                    candidate_sha256=attempt_projection_sha256,
                    purpose=purpose,
                )
            )
        except relationship_verification.VerificationError as error:
            return _blocked("invalid relationship verification", str(error))
        rejected_count = sum(
            verdict["verdict"] != "supported" for verdict in verification["verdicts"]
        )
        if rejected_count:
            correction_dir = work / "relationship-corrections" / "attempt-000001"
            if not (correction_dir / "corrections.json").exists():
                return _projection_waiting_result(
                    state, work, "correct_rejected_relationships"
                )
            try:
                (
                    corrections,
                    correction_journal_sha256,
                    correction_result_sha256,
                    correction_candidate_sha256,
                ) = relationship_correction.validate(
                    correction_dir,
                    candidate_path=attempt_dir / "projection.json",
                    candidate_sha256=attempt_projection_sha256,
                    verification_path=verification_dir / "verification.json",
                    verification_sha256=str(verification_result_sha256),
                    purpose=purpose,
                )
            except relationship_correction.CorrectionError as error:
                return _blocked("invalid relationship correction", str(error))
            proposed_count = sum(
                item["action"] == "propose_replacement_endpoint"
                for item in corrections["corrections"]
            )
            if proposed_count:
                correction_verification_dir = (
                    work / "relationship-correction-verifications" / "attempt-000001"
                )
                if not (correction_verification_dir / "verification.json").exists():
                    return _projection_waiting_result(
                        state, work, "verify_relationship_corrections"
                    )
                try:
                    (
                        correction_verification,
                        correction_verification_journal_sha256,
                        correction_verification_result_sha256,
                    ) = relationship_verification.validate(
                        correction_verification_dir,
                        candidate_path=correction_dir / "verification-candidate.json",
                        candidate_sha256=str(correction_candidate_sha256),
                        purpose=purpose,
                    )
                except relationship_verification.VerificationError as error:
                    return _blocked(
                        "invalid relationship correction verification", str(error)
                    )
        verification_error = _apply_independent_verification(
            projection, verification, corrections, correction_verification
        )
        if verification_error:
            return verification_error
    projection_path = work / "projections" / "source-000003-v1.json"
    if projection_path.exists():
        return _blocked("unbound projection artifact", "projection version 1 already exists outside the ledger")
    projection_bytes = json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    projection_path.write_bytes(projection_bytes)
    gap_count = sum(item["status"] == "gap" for item in projection["elements"])
    gap_count += sum(item["status"] == "gap" for item in projection["relationships"])
    gap_count += sum(item["status"] == "gap" for item in projection.get("scan_regions", []))
    projection_record = {
        "id": "projection-source-000003-v1",
        "source_id": "source-000003",
        "version": 1,
        "path": "projections/source-000003-v1.json",
        "sha256": _digest_bytes(projection_bytes),
        "element_count": len(projection["elements"]),
        "relationship_count": len(projection["relationships"]),
        "gap_count": gap_count,
        "coverage": "unassessed",
    }
    ninth = _ledger_entry(
        9,
        "model_projection_interview_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": 1,
            "interview_path": "projection-interviews/attempt-000001/interview.jsonl",
            "interview_sha256": journal_sha256,
            "attempt_projection_path": "projection-interviews/attempt-000001/projection.json",
            "attempt_projection_sha256": attempt_projection_sha256,
            "question_count": sum(entry["event"] == "question_asked" for entry in journal_entries),
            "answer_count": sum(entry["event"] == "answer_recorded" for entry in journal_entries),
            "rejected_answer_count": sum(
                entry["event"] == "answer_recorded" and entry["accepted"] is False
                for entry in journal_entries
            ),
            "verification_path": (
                "projection-verifications/attempt-000001/interview.jsonl"
                if verification is not None else None
            ),
            "verification_journal_sha256": verification_journal_sha256,
            "verification_result_sha256": verification_result_sha256,
            "correction_path": (
                "relationship-corrections/attempt-000001/interview.jsonl"
                if corrections is not None else None
            ),
            "correction_journal_sha256": correction_journal_sha256,
            "correction_result_sha256": correction_result_sha256,
            "correction_candidate_sha256": correction_candidate_sha256,
            "correction_verification_path": (
                "relationship-correction-verifications/attempt-000001/interview.jsonl"
                if correction_verification is not None else None
            ),
            "correction_verification_journal_sha256": (
                correction_verification_journal_sha256
            ),
            "correction_verification_result_sha256": (
                correction_verification_result_sha256
            ),
        },
        str(entries[-1]["entry_sha256"]),
    )
    tenth = _ledger_entry(
        10,
        "projection_version_created",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": 1,
            "projection": projection_record,
        },
        str(ninth["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [ninth, tenth])
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "first_projection_recorded",
        "waiting_for": None,
        "projection_interview_sha256": journal_sha256,
        "projection_attempt_sha256": attempt_projection_sha256,
        "relationship_verification_journal_sha256": verification_journal_sha256,
        "relationship_verification_result_sha256": verification_result_sha256,
        "relationship_correction_journal_sha256": correction_journal_sha256,
        "relationship_correction_result_sha256": correction_result_sha256,
        "relationship_correction_candidate_sha256": correction_candidate_sha256,
        "relationship_correction_verification_journal_sha256": (
            correction_verification_journal_sha256
        ),
        "relationship_correction_verification_result_sha256": (
            correction_verification_result_sha256
        ),
        "first_projection": projection_record,
        "ledger_entries": 10,
        "ledger_tail_sha256": tenth["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _projection_ready_result(state, work)


def _validate_projection_request(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object] | None:
    if len(entries) < 8 or entries[7].get("event") != "model_projection_interview_started":
        return _blocked("invalid ledger", "the first projection interview start is missing")
    source = state["first_source"]
    assert isinstance(source, dict)
    expected = {
        "attempt": 1,
        "source_id": "source-000003",
        "source_sha256": source["sha256"],
        "interview_path": "projection-interviews/attempt-000001/interview.jsonl",
        "attachment_path": "sources/source-000003",
    }
    if (
        entries[7].get("interview_contract")
        not in projection_interview.SUPPORTED_CONTRACTS
        or any(entries[7].get(key) != value for key, value in expected.items())
    ):
        return _blocked("invalid ledger", "the first projection interview does not match its source")
    return None


def _validate_recorded_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    if (
        len(entries) < 10
        or (not allow_later_phase and len(entries) != 10)
        or entries[8].get("event") != "model_projection_interview_completed"
    ):
        return _blocked("invalid ledger", "the completed first projection interview is missing")
    source = state["first_source"]
    assert isinstance(source, dict)
    try:
        projection, journal_sha256, attempt_projection_sha256 = projection_interview.validate(
            work / "projection-interviews" / "attempt-000001",
            source_sha256=str(source["sha256"]),
            purpose=purpose,
            contract=int(entries[7]["interview_contract"]),
        )
        journal_entries = projection_interview._read_journal(
            work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
        )
    except projection_interview.InterviewError as error:
        return _blocked("invalid projection interview", str(error))
    verification: dict[str, object] | None = None
    verification_journal_sha256: str | None = None
    verification_result_sha256: str | None = None
    corrections: dict[str, object] | None = None
    correction_journal_sha256: str | None = None
    correction_result_sha256: str | None = None
    correction_candidate_sha256: str | None = None
    correction_verification: dict[str, object] | None = None
    correction_verification_journal_sha256: str | None = None
    correction_verification_result_sha256: str | None = None
    if int(entries[7]["interview_contract"]) >= 7:
        verification_dir = work / "projection-verifications" / "attempt-000001"
        try:
            verification, verification_journal_sha256, verification_result_sha256 = (
                relationship_verification.validate(
                    verification_dir,
                    candidate_path=work / "projection-interviews" / "attempt-000001" / "projection.json",
                    candidate_sha256=attempt_projection_sha256,
                    purpose=purpose,
                )
            )
        except relationship_verification.VerificationError as error:
            return _blocked("invalid relationship verification", str(error))
        rejected_count = sum(
            verdict["verdict"] != "supported" for verdict in verification["verdicts"]
        )
        if rejected_count:
            correction_dir = work / "relationship-corrections" / "attempt-000001"
            try:
                (
                    corrections,
                    correction_journal_sha256,
                    correction_result_sha256,
                    correction_candidate_sha256,
                ) = relationship_correction.validate(
                    correction_dir,
                    candidate_path=work / "projection-interviews" / "attempt-000001" / "projection.json",
                    candidate_sha256=attempt_projection_sha256,
                    verification_path=verification_dir / "verification.json",
                    verification_sha256=str(verification_result_sha256),
                    purpose=purpose,
                )
            except relationship_correction.CorrectionError as error:
                return _blocked("invalid relationship correction", str(error))
            proposed_count = sum(
                item["action"] == "propose_replacement_endpoint"
                for item in corrections["corrections"]
            )
            if proposed_count:
                try:
                    (
                        correction_verification,
                        correction_verification_journal_sha256,
                        correction_verification_result_sha256,
                    ) = relationship_verification.validate(
                        work / "relationship-correction-verifications" / "attempt-000001",
                        candidate_path=correction_dir / "verification-candidate.json",
                        candidate_sha256=str(correction_candidate_sha256),
                        purpose=purpose,
                    )
                except relationship_verification.VerificationError as error:
                    return _blocked(
                        "invalid relationship correction verification", str(error)
                    )
        verification_error = _apply_independent_verification(
            projection, verification, corrections, correction_verification
        )
        if verification_error:
            return verification_error
    if (
        state.get("projection_interview_sha256") != journal_sha256
        or state.get("projection_attempt_sha256") != attempt_projection_sha256
        or entries[8].get("attempt") != 1
        or entries[8].get("interview_path") != "projection-interviews/attempt-000001/interview.jsonl"
        or entries[8].get("interview_sha256") != journal_sha256
        or entries[8].get("attempt_projection_path") != "projection-interviews/attempt-000001/projection.json"
        or entries[8].get("attempt_projection_sha256") != attempt_projection_sha256
        or entries[8].get("question_count") != sum(
            entry["event"] == "question_asked" for entry in journal_entries
        )
        or entries[8].get("answer_count") != sum(
            entry["event"] == "answer_recorded" for entry in journal_entries
        )
        or entries[8].get("rejected_answer_count") != sum(
            entry["event"] == "answer_recorded" and entry["accepted"] is False
            for entry in journal_entries
        )
        or state.get("relationship_verification_journal_sha256") != verification_journal_sha256
        or state.get("relationship_verification_result_sha256") != verification_result_sha256
        or entries[8].get("verification_path") != (
            "projection-verifications/attempt-000001/interview.jsonl"
            if verification is not None else None
        )
        or entries[8].get("verification_journal_sha256") != verification_journal_sha256
        or entries[8].get("verification_result_sha256") != verification_result_sha256
        or state.get("relationship_correction_journal_sha256") != correction_journal_sha256
        or state.get("relationship_correction_result_sha256") != correction_result_sha256
        or state.get("relationship_correction_candidate_sha256") != correction_candidate_sha256
        or state.get("relationship_correction_verification_journal_sha256")
        != correction_verification_journal_sha256
        or state.get("relationship_correction_verification_result_sha256")
        != correction_verification_result_sha256
        or entries[8].get("correction_path") != (
            "relationship-corrections/attempt-000001/interview.jsonl"
            if corrections is not None else None
        )
        or entries[8].get("correction_journal_sha256") != correction_journal_sha256
        or entries[8].get("correction_result_sha256") != correction_result_sha256
        or entries[8].get("correction_candidate_sha256") != correction_candidate_sha256
        or entries[8].get("correction_verification_path") != (
            "relationship-correction-verifications/attempt-000001/interview.jsonl"
            if correction_verification is not None else None
        )
        or entries[8].get("correction_verification_journal_sha256")
        != correction_verification_journal_sha256
        or entries[8].get("correction_verification_result_sha256")
        != correction_verification_result_sha256
    ):
        return _blocked("invalid ledger", "the completed projection interview does not match its artifacts")
    if entries[9].get("event") != "projection_version_created":
        return _blocked("invalid ledger", "the projection interview has an invalid terminal state")
    if not allow_later_phase and (
        state.get("phase") != "first_projection_recorded"
        or state.get("status") != "ready_for_projection_assessment"
        or state.get("waiting_for") is not None
    ):
        return _blocked("invalid ledger", "the projection interview has an invalid terminal state")
    projection_path = work / "projections" / "source-000003-v1.json"
    try:
        projection_bytes = projection_path.read_bytes()
    except OSError:
        return _blocked("immutable projection unavailable", str(projection_path))
    canonical = (
        json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        if verification is not None else
        (work / "projection-interviews" / "attempt-000001" / "projection.json").read_bytes()
    )
    if projection_bytes != canonical:
        return _blocked("immutable projection changed", "projection version 1 no longer matches its accepted model result")
    gap_count = sum(item["status"] == "gap" for item in projection["elements"])
    gap_count += sum(item["status"] == "gap" for item in projection["relationships"])
    gap_count += sum(item["status"] == "gap" for item in projection.get("scan_regions", []))
    expected_record = {
        "id": "projection-source-000003-v1",
        "source_id": "source-000003",
        "version": 1,
        "path": "projections/source-000003-v1.json",
        "sha256": _digest_bytes(projection_bytes),
        "element_count": len(projection["elements"]),
        "relationship_count": len(projection["relationships"]),
        "gap_count": gap_count,
        "coverage": "unassessed",
    }
    if entries[9].get("attempt") != 1 or entries[9].get("projection") != expected_record:
        return _blocked("invalid ledger", "projection version 1 does not match its ledger record")
    if state.get("first_projection") != expected_record:
        return _blocked("invalid intake state", "the saved first projection does not match its ledger record")
    return None


def run_purpose_interview(
    work: Path,
    *,
    input_fn: object | None = None,
    output_fn: object | None = None,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(encoding="utf-8")
        purpose = (work / "sources" / "source-000002.txt").read_text(encoding="utf-8")
    except OSError as error:
        return _blocked("purpose interview context unavailable", str(error))
    current = drive(work, opening, purpose)
    if current.get("status") != "waiting_for_model" or current.get("stopped") != "assessing_intake_purpose":
        if current.get("status") == "needs_operator":
            return current
        return _blocked("purpose interview unavailable", json.dumps(current, sort_keys=True))
    try:
        purpose_interview.run(
            work / "purpose-interview",
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except purpose_interview.InterviewError as error:
        return _blocked("purpose interview failed", str(error))
    return drive(work, opening, purpose)


def run_first_projection_interview(
    work: Path,
    *,
    input_fn: object | None = None,
    output_fn: object | None = None,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(encoding="utf-8")
        purpose = (work / "sources" / "source-000002.txt").read_text(encoding="utf-8")
    except OSError as error:
        return _blocked("interview context unavailable", str(error))
    current = drive(work, opening, purpose)
    if current.get("status") == "ready_for_projection_assessment":
        return current
    if current.get("status") != "waiting_for_model" or current.get("stopped") != "interviewing_first_projection":
        return _blocked("projection interview unavailable", json.dumps(current, sort_keys=True))
    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    entries, ledger_error = _validate_ledger(work / "ledger.jsonl")
    if ledger_error:
        return _blocked("invalid ledger", ledger_error)
    source = state["first_source"]
    assert isinstance(source, dict)
    try:
        projection_interview.run(
            work / "projection-interviews" / "attempt-000001",
            source_sha256=str(source["sha256"]),
            purpose=purpose,
            contract=int(entries[7]["interview_contract"]),
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except projection_interview.InterviewError as error:
        return _blocked("projection interview failed", str(error))
    return drive(work, opening, purpose)


def run_first_projection_verification(
    work: Path,
    *,
    input_fn: object | None = None,
    output_fn: object | None = None,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(encoding="utf-8")
        purpose = (work / "sources" / "source-000002.txt").read_text(encoding="utf-8")
        candidate_path = work / "projection-interviews" / "attempt-000001" / "projection.json"
        candidate_bytes = candidate_path.read_bytes()
    except OSError as error:
        return _blocked("verification context unavailable", str(error))
    current = drive(work, opening, purpose)
    if current.get("status") == "ready_for_projection_assessment":
        return current
    if current.get("status") != "waiting_for_model" or current.get("stopped") != "verifying_first_projection":
        return _blocked("relationship verification unavailable", json.dumps(current, sort_keys=True))
    try:
        relationship_verification.run(
            work / "projection-verifications" / "attempt-000001",
            candidate_path=candidate_path,
            candidate_sha256=_digest_bytes(candidate_bytes),
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except relationship_verification.VerificationError as error:
        return _blocked("relationship verification failed", str(error))
    return drive(work, opening, purpose)


def run_relationship_correction(
    work: Path,
    *,
    input_fn: object | None = None,
    output_fn: object | None = None,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(encoding="utf-8")
        purpose = (work / "sources" / "source-000002.txt").read_text(encoding="utf-8")
        candidate_path = work / "projection-interviews" / "attempt-000001" / "projection.json"
        candidate_bytes = candidate_path.read_bytes()
        verification_path = work / "projection-verifications" / "attempt-000001" / "verification.json"
        verification_bytes = verification_path.read_bytes()
    except OSError as error:
        return _blocked("correction context unavailable", str(error))
    current = drive(work, opening, purpose)
    if current.get("status") == "ready_for_projection_assessment":
        return current
    if current.get("status") != "waiting_for_model" or current.get("stopped") != "correcting_rejected_relationships":
        return _blocked("relationship correction unavailable", json.dumps(current, sort_keys=True))
    try:
        relationship_correction.run(
            work / "relationship-corrections" / "attempt-000001",
            candidate_path=candidate_path,
            candidate_sha256=_digest_bytes(candidate_bytes),
            verification_path=verification_path,
            verification_sha256=_digest_bytes(verification_bytes),
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except relationship_correction.CorrectionError as error:
        return _blocked("relationship correction failed", str(error))
    return drive(work, opening, purpose)


def run_relationship_correction_verification(
    work: Path,
    *,
    input_fn: object | None = None,
    output_fn: object | None = None,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(encoding="utf-8")
        purpose = (work / "sources" / "source-000002.txt").read_text(encoding="utf-8")
        candidate_path = work / "relationship-corrections" / "attempt-000001" / "verification-candidate.json"
        candidate_bytes = candidate_path.read_bytes()
    except OSError as error:
        return _blocked("correction verification context unavailable", str(error))
    current = drive(work, opening, purpose)
    if current.get("status") == "ready_for_projection_assessment":
        return current
    if current.get("status") != "waiting_for_model" or current.get("stopped") != "verifying_relationship_corrections":
        return _blocked(
            "relationship correction verification unavailable",
            json.dumps(current, sort_keys=True),
        )
    try:
        relationship_verification.run(
            work / "relationship-correction-verifications" / "attempt-000001",
            candidate_path=candidate_path,
            candidate_sha256=_digest_bytes(candidate_bytes),
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except relationship_verification.VerificationError as error:
        return _blocked("relationship correction verification failed", str(error))
    return drive(work, opening, purpose)


def _projection_for_gap(
    work: Path, state: dict[str, object]
) -> tuple[Path | None, str | None, dict[str, object] | None]:
    record = state.get("first_projection")
    if not isinstance(record, dict):
        return None, None, _blocked("gap clarification unavailable", "the first projection record is missing")
    path_value = record.get("path")
    expected_sha256 = record.get("sha256")
    if not isinstance(path_value, str) or not isinstance(expected_sha256, str):
        return None, None, _blocked("gap clarification unavailable", "the first projection identity is incomplete")
    path = work / path_value
    try:
        content = path.read_bytes()
    except OSError:
        return None, None, _blocked("gap clarification unavailable", "the first projection is unavailable")
    if _digest_bytes(content) != expected_sha256:
        return None, None, _blocked("immutable projection changed", "the first projection no longer matches its record")
    return path, expected_sha256, None


def _request_gap_question_round(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    projection_path, projection_sha256, projection_error = _projection_for_gap(
        work, state
    )
    if projection_error:
        return projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        gaps = gap_clarification.select_gaps(projection, projection_sha256)
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return _blocked("gap question round unavailable", str(error))
    round_dir = work / "gap-question-rounds" / "round-000001"
    if round_dir.exists():
        return _blocked(
            "unbound gap question round",
            "gap question round artifacts already exist outside the ledger",
        )
    request = _ledger_entry(
        11,
        "model_gap_question_round_requested",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "round": 1,
            "contract": gap_clarification.ROUND_CONTRACT,
            "projection_path": str(state["first_projection"]["path"]),
            "projection_sha256": projection_sha256,
            "gap_count": len(gaps),
            "gaps": gaps,
            "interview_path": "gap-question-rounds/round-000001/interview.jsonl",
            "result_path": "gap-question-rounds/round-000001/clarification-round.json",
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [request])
    state.update({
        "status": "waiting_for_model",
        "phase": "formulating_gap_question_round",
        "waiting_for": "gap-question-rounds/round-000001/interview.jsonl",
        "question": None,
        "questions": [],
        "gap_question_round": {
            "round": 1,
            "projection_sha256": projection_sha256,
            "gap_count": len(gaps),
            "gaps": gaps,
        },
        "ledger_entries": 11,
        "ledger_tail_sha256": request["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_question_round_model_result(state, work)


def _validate_gap_question_round_request(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> tuple[Path | None, str | None, dict[str, object] | None]:
    if len(entries) < 11 or entries[10].get("event") != "model_gap_question_round_requested":
        return None, None, _blocked(
            "invalid ledger", "the gap question round request is missing"
        )
    projection_path, projection_sha256, projection_error = _projection_for_gap(
        work, state
    )
    if projection_error:
        return None, None, projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        gaps = gap_clarification.select_gaps(projection, projection_sha256)
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return None, None, _blocked("invalid gap question round", str(error))
    expected = {
        "round": 1,
        "contract": gap_clarification.ROUND_CONTRACT,
        "projection_path": str(state["first_projection"]["path"]),
        "projection_sha256": projection_sha256,
        "gap_count": len(gaps),
        "gaps": gaps,
        "interview_path": "gap-question-rounds/round-000001/interview.jsonl",
        "result_path": "gap-question-rounds/round-000001/clarification-round.json",
    }
    saved = state.get("gap_question_round")
    if (
        any(entries[10].get(key) != value for key, value in expected.items())
        or not isinstance(saved, dict)
        or any(saved.get(key) != value for key, value in {
            "round": 1,
            "projection_sha256": projection_sha256,
            "gap_count": len(gaps),
            "gaps": gaps,
        }.items())
    ):
        return None, None, _blocked(
            "invalid ledger", "the gap question round request changed"
        )
    return projection_path, projection_sha256, None


def _validate_question_round_shape(
    result: dict[str, object],
    gaps: list[dict[str, object]],
    *,
    round_number: int = 1,
) -> str | None:
    questions = result.get("questions")
    if not isinstance(questions, list) or len(questions) != len(gaps):
        return "the question round does not contain exactly one question per known gap"
    expected_ids = [
        (
            f"gap-clarification-answer-{index:06d}"
            if round_number == 1
            else f"gap-clarification-round-{round_number:06d}-question-{index:06d}"
        )
        for index in range(1, len(gaps) + 1)
    ]
    actual_ids = [item.get("id") if isinstance(item, dict) else None for item in questions]
    if actual_ids != expected_ids or len(set(actual_ids)) != len(actual_ids):
        return "the question round identities are missing, duplicated, or reordered"
    for question, gap in zip(questions, gaps, strict=True):
        expected_gap = {
            key: gap[key]
            for key in (
                "projection_sha256", "collection", "kind", "id", "record_sha256"
            )
        }
        if not isinstance(question, dict) or question.get("answers_gap") != expected_gap:
            return "a question is not bound to its code-selected gap"
    return None


def _consume_gap_question_round(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    projection_path, projection_sha256, request_error = (
        _validate_gap_question_round_request(work, state, entries)
    )
    if request_error:
        return request_error
    assert projection_path is not None and projection_sha256 is not None
    round_dir = work / "gap-question-rounds" / "round-000001"
    try:
        result, journal_sha256, result_sha256 = gap_clarification.validate_round(
            round_dir,
            projection_path=projection_path,
            projection_sha256=projection_sha256,
            purpose=purpose,
        )
        journal_entries = gap_clarification._read_journal(
            round_dir / "interview.jsonl"
        )
    except gap_clarification.ClarificationError as error:
        return _blocked("invalid gap question round", str(error))
    saved = state["gap_question_round"]
    assert isinstance(saved, dict)
    gaps = saved["gaps"]
    assert isinstance(gaps, list)
    shape_error = _validate_question_round_shape(result, gaps)
    if shape_error:
        return _blocked("invalid gap question round", shape_error)
    timestamp = datetime.now(timezone.utc).isoformat()
    completed = _ledger_entry(
        12,
        "model_gap_question_round_completed",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "round": 1,
            "interview_path": "gap-question-rounds/round-000001/interview.jsonl",
            "interview_sha256": journal_sha256,
            "result_path": "gap-question-rounds/round-000001/clarification-round.json",
            "result_sha256": result_sha256,
            "question_count": len(result["questions"]),
            "interview_question_count": sum(
                item["event"] == "question_asked" for item in journal_entries
            ),
            "answer_count": sum(
                item["event"] == "answer_recorded" for item in journal_entries
            ),
            "rejected_answer_count": sum(
                item["event"] == "answer_recorded" and item["accepted"] is False
                for item in journal_entries
            ),
            "questioner": result["questioner"],
            "gaps": result["gaps"],
            "questions": result["questions"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    prepared = _ledger_entry(
        13,
        "operator_question_round_prepared",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "round": 1,
            "question_count": len(result["questions"]),
            "questions": result["questions"],
        },
        str(completed["entry_sha256"]),
    )
    first_question = result["questions"][0]
    first_asked = _ledger_entry(
        14,
        "operator_question_asked",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "round": 1,
            "question_position": 1,
            "question": first_question,
        },
        str(prepared["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed, prepared, first_asked])
    state["gap_question_round"].update({
        "interview_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "questioner": result["questioner"],
    })
    state.update({
        "status": "needs_operator",
        "phase": "awaiting_gap_answers",
        "waiting_for": first_question["id"],
        "question": first_question,
        "questions": result["questions"],
        "gap_question_answers": [],
        "ledger_entries": 14,
        "ledger_tail_sha256": first_asked["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_question_round_operator_result(state, work)


def _used_assessment_positions(state: dict[str, object]) -> set[int]:
    used: set[int] = set()
    history = state.get("gap_resolution_history", [])
    candidates = history if isinstance(history, list) else []
    current = state.get("gap_resolution")
    if isinstance(current, dict) and current.get("result_sha256"):
        candidates = [*candidates, current]
    for item in candidates:
        if isinstance(item, dict) and isinstance(
            item.get("selected_assessment_position"), int
        ):
            used.add(item["selected_assessment_position"])
    return used


def _follow_up_gap_bindings(
    work: Path, state: dict[str, object]
) -> tuple[
    list[dict[str, object]] | None,
    Path | None,
    str | None,
    dict[str, object] | None,
]:
    bindings, binding_error = _gap_answer_assessment_bindings(work, state)
    if binding_error:
        return None, None, None, binding_error
    assert bindings is not None
    saved_assessment = state.get("gap_answer_assessment")
    assessments = (
        saved_assessment.get("assessments")
        if isinstance(saved_assessment, dict)
        else None
    )
    if not isinstance(assessments, list) or len(assessments) != len(bindings):
        return None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "the preserved assessment set is incomplete",
        )
    used = _used_assessment_positions(state)
    unused_resolving = [
        item.get("position")
        for item in assessments
        if isinstance(item, dict)
        and item.get("verdict") == "resolves_gap"
        and item.get("position") not in used
    ]
    if unused_resolving:
        return None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "apply every already-resolving assessment before asking follow-up questions",
        )
    parent = state.get("current_projection", state.get("first_projection"))
    if not isinstance(parent, dict):
        return None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "the current projection record is missing",
        )
    projection_path, projection_sha256, projection_error = (
        _validated_projection_record(work, parent)
    )
    if projection_error:
        return None, None, None, projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        current_gaps = gap_clarification.select_gaps(projection, projection_sha256)
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return None, None, None, _blocked(
            "follow-up gap clarification unavailable", str(error)
        )
    current_by_identity = {
        (item["collection"], item["id"]): item for item in current_gaps
    }
    follow_ups: list[dict[str, object]] = []
    for assessment, binding in zip(assessments, bindings, strict=True):
        if (
            not isinstance(assessment, dict)
            or assessment.get("verdict") != "does_not_resolve_gap"
        ):
            continue
        original_gap = binding.get("gap")
        if not isinstance(original_gap, dict):
            return None, None, None, _blocked(
                "follow-up gap clarification unavailable",
                "a non-resolving assessment lost its bound gap",
            )
        key = (original_gap.get("collection"), original_gap.get("id"))
        current_gap = current_by_identity.get(key)
        if current_gap is None:
            continue
        if current_gap.get("record_sha256") != original_gap.get("record_sha256"):
            return None, None, None, _blocked(
                "follow-up gap clarification unavailable",
                f"gap {original_gap.get('id')} changed after its failed clarification",
            )
        follow_up = json.loads(json.dumps(current_gap))
        follow_up["follow_up_of"] = {
            "question_round": 1,
            "assessment_position": assessment.get("position"),
            "question": binding.get("question"),
            "answer": binding.get("answer"),
            "answer_source": binding.get("answer_source"),
            "answer_projection": binding.get("answer_projection"),
            "assessment": {
                "verdict": assessment.get("verdict"),
                "reason": assessment.get("reason"),
                "question_id": assessment.get("question_id"),
            },
        }
        follow_ups.append(follow_up)
    if not follow_ups:
        return None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "no still-current gap has a non-resolving preserved answer",
        )
    return follow_ups, projection_path, projection_sha256, None


def _request_follow_up_gap_question_round(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    if isinstance(state.get("follow_up_gap_question_round"), dict):
        return _blocked(
            "follow-up gap clarification unavailable",
            "the follow-up question round is already recorded or in progress",
        )
    gaps, projection_path, projection_sha256, binding_error = (
        _follow_up_gap_bindings(work, state)
    )
    if binding_error:
        return binding_error
    assert gaps is not None and projection_path is not None and projection_sha256 is not None
    round_number = 2
    relative_dir = f"gap-question-rounds/round-{round_number:06d}"
    round_dir = work / relative_dir
    if round_dir.exists():
        return _blocked(
            "unbound follow-up gap question round",
            "follow-up question artifacts already exist outside the ledger",
        )
    current_resolution = state.get("gap_resolution")
    history = state.get("gap_resolution_history", [])
    if not isinstance(history, list):
        return _blocked(
            "follow-up gap clarification unavailable",
            "gap resolution history must remain append-only",
        )
    archived_resolution: dict[str, object] | None = None
    if isinstance(current_resolution, dict):
        archived_resolution = json.loads(json.dumps(current_resolution))
        archived_resolution["terminal_phase"] = state.get("phase")
        archived_resolution["output_projection"] = state.get("current_projection")
    request_sequence = len(entries) + 1
    parent_path = projection_path.relative_to(work)
    request = _ledger_entry(
        request_sequence,
        "model_follow_up_gap_question_round_requested",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "round": round_number,
            "contract": gap_clarification.ROUND_CONTRACT,
            "projection_path": str(parent_path),
            "projection_sha256": projection_sha256,
            "gap_count": len(gaps),
            "gaps": gaps,
            "prior_assessment_sha256": state["gap_answer_assessment"]["result_sha256"],
            "interview_path": f"{relative_dir}/interview.jsonl",
            "result_path": f"{relative_dir}/clarification-round.json",
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [request])
    if archived_resolution is not None:
        state["gap_resolution_history"] = [*history, archived_resolution]
        state.pop("gap_resolution", None)
    state.update({
        "status": "waiting_for_model",
        "phase": "formulating_follow_up_gap_question_round",
        "waiting_for": f"{relative_dir}/interview.jsonl",
        "question": None,
        "follow_up_gap_question_round": {
            "round": round_number,
            "contract": gap_clarification.ROUND_CONTRACT,
            "request_ledger_sequence": request_sequence,
            "projection_path": str(parent_path),
            "projection_sha256": projection_sha256,
            "gap_count": len(gaps),
            "gaps": gaps,
            "prior_assessment_sha256": state["gap_answer_assessment"]["result_sha256"],
        },
        "ledger_entries": request_sequence,
        "ledger_tail_sha256": request["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _follow_up_gap_question_round_model_result(state, work)


def _validate_follow_up_question_round_shape(
    result: dict[str, object],
    gaps: list[dict[str, object]],
    round_number: int,
) -> str | None:
    shape_error = _validate_question_round_shape(
        result, gaps, round_number=round_number
    )
    if shape_error:
        return shape_error
    if result.get("round") != round_number or result.get("gaps") != gaps:
        return "the follow-up question round identity or bindings changed"
    questions = result["questions"]
    assert isinstance(questions, list)
    for question, gap in zip(questions, gaps, strict=True):
        follow_up = gap.get("follow_up_of")
        prior = follow_up.get("question") if isinstance(follow_up, dict) else None
        prior_asks = prior.get("asks") if isinstance(prior, dict) else None
        if (
            not isinstance(question, dict)
            or not isinstance(question.get("asks"), str)
            or not isinstance(prior_asks, str)
            or question["asks"].strip().casefold() == prior_asks.strip().casefold()
        ):
            return "a follow-up question exactly repeats its failed prior question"
    return None


def _consume_follow_up_gap_question_round(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    saved = state.get("follow_up_gap_question_round")
    if not isinstance(saved, dict):
        return _blocked("invalid intake state", "the follow-up question round is missing")
    gaps, projection_path, projection_sha256, binding_error = (
        _follow_up_gap_bindings(work, state)
    )
    if binding_error:
        return binding_error
    assert gaps is not None and projection_path is not None and projection_sha256 is not None
    request_sequence = saved.get("request_ledger_sequence")
    request_index = request_sequence - 1 if isinstance(request_sequence, int) else -1
    expected_request = {
        "round": 2,
        "contract": gap_clarification.ROUND_CONTRACT,
        "projection_path": str(projection_path.relative_to(work)),
        "projection_sha256": projection_sha256,
        "gap_count": len(gaps),
        "gaps": gaps,
        "prior_assessment_sha256": state["gap_answer_assessment"]["result_sha256"],
        "interview_path": "gap-question-rounds/round-000002/interview.jsonl",
        "result_path": "gap-question-rounds/round-000002/clarification-round.json",
    }
    if (
        request_index < 0
        or request_index >= len(entries)
        or entries[request_index].get("event")
        != "model_follow_up_gap_question_round_requested"
        or any(entries[request_index].get(key) != value for key, value in expected_request.items())
        or any(saved.get(key) != value for key, value in {
            key: value for key, value in expected_request.items()
            if key not in {"interview_path", "result_path"}
        }.items())
    ):
        return _blocked("invalid ledger", "the follow-up question request changed")
    round_dir = work / "gap-question-rounds" / "round-000002"
    try:
        result, journal_sha256, result_sha256 = gap_clarification.validate_round(
            round_dir,
            projection_path=projection_path,
            projection_sha256=projection_sha256,
            purpose=purpose,
            gaps=gaps,
            round_number=2,
        )
        journal_entries = gap_clarification._read_journal(
            round_dir / "interview.jsonl"
        )
    except gap_clarification.ClarificationError as error:
        return _blocked("invalid follow-up gap question round", str(error))
    shape_error = _validate_follow_up_question_round_shape(result, gaps, 2)
    if shape_error:
        return _blocked("invalid follow-up gap question round", shape_error)
    timestamp = datetime.now(timezone.utc).isoformat()
    completed_sequence = len(entries) + 1
    completed = _ledger_entry(
        completed_sequence,
        "model_follow_up_gap_question_round_completed",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "round": 2,
            "interview_path": "gap-question-rounds/round-000002/interview.jsonl",
            "interview_sha256": journal_sha256,
            "result_path": "gap-question-rounds/round-000002/clarification-round.json",
            "result_sha256": result_sha256,
            "question_count": len(result["questions"]),
            "interview_question_count": sum(
                item["event"] == "question_asked" for item in journal_entries
            ),
            "answer_count": sum(
                item["event"] == "answer_recorded" for item in journal_entries
            ),
            "rejected_answer_count": sum(
                item["event"] == "answer_recorded" and item["accepted"] is False
                for item in journal_entries
            ),
            "questioner": result["questioner"],
            "gaps": result["gaps"],
            "questions": result["questions"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    prepared = _ledger_entry(
        completed_sequence + 1,
        "operator_follow_up_question_round_prepared",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "round": 2,
            "question_count": len(result["questions"]),
            "questions": result["questions"],
        },
        str(completed["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed, prepared])
    state["follow_up_gap_question_round"].update({
        "interview_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "questioner": result["questioner"],
        "question_count": len(result["questions"]),
        "questions": result["questions"],
    })
    state.update({
        "status": "ready_for_operator_interview",
        "phase": "follow_up_gap_question_round_recorded",
        "waiting_for": None,
        "question": None,
        "ledger_entries": completed_sequence + 1,
        "ledger_tail_sha256": prepared["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _follow_up_gap_question_round_ready_result(state, work)


def _validate_follow_up_gap_question_round(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    *,
    allow_interview: bool = False,
) -> dict[str, object] | None:
    saved = state.get("follow_up_gap_question_round")
    if not isinstance(saved, dict):
        return _blocked(
            "invalid intake state", "the follow-up question round is missing"
        )
    round_number = saved.get("round")
    projection_value = saved.get("projection_path")
    projection_sha256 = saved.get("projection_sha256")
    gaps = saved.get("gaps")
    prior_assessment_sha256 = saved.get("prior_assessment_sha256")
    if (
        not isinstance(round_number, int)
        or round_number < 2
        or not isinstance(projection_value, str)
        or not isinstance(projection_sha256, str)
        or not isinstance(gaps, list)
        or not gaps
        or not isinstance(prior_assessment_sha256, str)
    ):
        return _blocked(
            "invalid intake state", "the prepared question round identity is incomplete"
        )
    projection_path, validated_sha256, projection_error = _validated_projection_record(
        work, {"path": projection_value, "sha256": projection_sha256}
    )
    if projection_error:
        return projection_error
    assert projection_path is not None and validated_sha256 == projection_sha256
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        gap_clarification._validate_bound_gaps(
            projection, projection_sha256, gaps
        )
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return _blocked("invalid follow-up gap question round", str(error))
    request_sequence = saved.get("request_ledger_sequence")
    request_index = request_sequence - 1 if isinstance(request_sequence, int) else -1
    round_dir_value = f"gap-question-rounds/round-{round_number:06d}"
    expected_request = {
        "round": round_number,
        "contract": gap_clarification.ROUND_CONTRACT,
        "projection_path": str(projection_path.relative_to(work)),
        "projection_sha256": projection_sha256,
        "gap_count": len(gaps),
        "gaps": gaps,
        "prior_assessment_sha256": prior_assessment_sha256,
        "interview_path": f"{round_dir_value}/interview.jsonl",
        "result_path": f"{round_dir_value}/clarification-round.json",
    }
    if (
        request_index < 0
        or request_index + 2 >= len(entries)
        or (not allow_interview and len(entries) != request_index + 3)
        or entries[request_index].get("event")
        != "model_follow_up_gap_question_round_requested"
        or any(
            entries[request_index].get(key) != value
            for key, value in expected_request.items()
        )
        or any(
            saved.get(key) != value
            for key, value in {
                key: value
                for key, value in expected_request.items()
                if key not in {"interview_path", "result_path"}
            }.items()
        )
    ):
        return _blocked("invalid ledger", "the follow-up question request changed")
    round_dir = work / round_dir_value
    try:
        result, journal_sha256, result_sha256 = gap_clarification.validate_round(
            round_dir,
            projection_path=projection_path,
            projection_sha256=projection_sha256,
            purpose=purpose,
            gaps=gaps,
            round_number=round_number,
        )
        journal_entries = gap_clarification._read_journal(
            round_dir / "interview.jsonl"
        )
    except gap_clarification.ClarificationError as error:
        return _blocked("invalid follow-up gap question round", str(error))
    shape_error = _validate_follow_up_question_round_shape(
        result, gaps, round_number
    )
    completed = entries[request_index + 1]
    prepared = entries[request_index + 2]
    expected_completed = {
        "round": round_number,
        "interview_path": f"{round_dir_value}/interview.jsonl",
        "interview_sha256": journal_sha256,
        "result_path": f"{round_dir_value}/clarification-round.json",
        "result_sha256": result_sha256,
        "question_count": len(result["questions"]),
        "interview_question_count": sum(
            item["event"] == "question_asked" for item in journal_entries
        ),
        "answer_count": sum(
            item["event"] == "answer_recorded" for item in journal_entries
        ),
        "rejected_answer_count": sum(
            item["event"] == "answer_recorded" and item["accepted"] is False
            for item in journal_entries
        ),
        "questioner": result["questioner"],
        "gaps": result["gaps"],
        "questions": result["questions"],
    }
    expected_saved = {
        **{
            key: value
            for key, value in expected_request.items()
            if key not in {"interview_path", "result_path"}
        },
        "interview_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "questioner": result["questioner"],
        "question_count": len(result["questions"]),
        "questions": result["questions"],
    }
    if (
        shape_error
        or completed.get("event")
        != "model_follow_up_gap_question_round_completed"
        or any(completed.get(key) != value for key, value in expected_completed.items())
        or prepared.get("event") != "operator_follow_up_question_round_prepared"
        or prepared.get("round") != round_number
        or prepared.get("question_count") != len(result["questions"])
        or prepared.get("questions") != result["questions"]
        or any(saved.get(key) != value for key, value in expected_saved.items())
        or (
            not allow_interview
            and (
                state.get("status") != "ready_for_operator_interview"
                or state.get("phase") != "follow_up_gap_question_round_recorded"
                or state.get("waiting_for") is not None
                or state.get("question") is not None
                or state.get("ledger_entries") != len(entries)
                or state.get("ledger_tail_sha256") != prepared.get("entry_sha256")
            )
        )
    ):
        return _blocked(
            "invalid ledger",
            shape_error or "the preserved follow-up question round changed",
        )
    return None


def _known_source_numbers(entries: list[dict[str, object]]) -> set[int]:
    numbers: set[int] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            source_id = value.get("id")
            path = value.get("path")
            if (
                isinstance(source_id, str)
                and source_id.startswith("source-")
                and isinstance(path, str)
                and path.startswith("sources/source-")
            ):
                suffix = source_id.removeprefix("source-")
                if len(suffix) == 6 and suffix.isdigit():
                    numbers.add(int(suffix))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(entries)
    return numbers


def _start_prepared_question_round_interview(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    round_error = _validate_follow_up_gap_question_round(
        work, state, entries, purpose
    )
    if round_error:
        return round_error
    saved = state["follow_up_gap_question_round"]
    assert isinstance(saved, dict)
    round_number = saved["round"]
    questions = saved["questions"]
    result_sha256 = saved["result_sha256"]
    assert isinstance(round_number, int)
    assert isinstance(questions, list) and questions
    assert isinstance(result_sha256, str)
    current_projection = state.get("current_projection", state.get("first_projection"))
    if (
        not isinstance(current_projection, dict)
        or current_projection.get("sha256") != saved.get("projection_sha256")
        or not isinstance(current_projection.get("id"), str)
        or not isinstance(current_projection.get("source_id"), str)
    ):
        return _blocked(
            "prepared question round unavailable",
            "the prepared round is not bound to the current projection",
        )
    first_question = questions[0]
    assert isinstance(first_question, dict)
    timestamp = datetime.now(timezone.utc).isoformat()
    first_sequence = len(entries) + 1
    asked = _ledger_entry(
        first_sequence,
        "operator_question_asked",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "round": round_number,
            "question_position": 1,
            "question": first_question,
            "prepared_round_result_sha256": result_sha256,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [asked])
    state.update({
        "status": "needs_operator",
        "phase": "awaiting_prepared_question_round_answers",
        "waiting_for": first_question["id"],
        "question": first_question,
        "prepared_question_round_interview": {
            "round": round_number,
            "prepared_round_result_sha256": result_sha256,
            "first_question_ledger_sequence": first_sequence,
            "original_source_id": current_projection["source_id"],
            "original_projection_id": current_projection["id"],
            "answers": [],
        },
        "ledger_entries": first_sequence,
        "ledger_tail_sha256": asked["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _prepared_question_round_operator_result(state, work)


def _validate_prepared_question_round_interview(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    round_error = _validate_follow_up_gap_question_round(
        work, state, entries, purpose, allow_interview=True
    )
    if round_error:
        return round_error
    saved = state.get("follow_up_gap_question_round")
    interview = state.get("prepared_question_round_interview")
    if not isinstance(saved, dict) or not isinstance(interview, dict):
        return _blocked(
            "invalid intake state", "the prepared-round interview record is missing"
        )
    round_number = saved.get("round")
    questions = saved.get("questions")
    answers = interview.get("answers")
    first_sequence = interview.get("first_question_ledger_sequence")
    result_sha256 = saved.get("result_sha256")
    if (
        not isinstance(round_number, int)
        or not isinstance(questions, list)
        or not questions
        or not isinstance(answers, list)
        or len(answers) > len(questions)
        or not isinstance(first_sequence, int)
        or not isinstance(result_sha256, str)
        or interview.get("round") != round_number
        or interview.get("prepared_round_result_sha256") != result_sha256
    ):
        return _blocked(
            "invalid intake state", "the prepared-round interview identity changed"
        )
    current_projection = state.get("current_projection", state.get("first_projection"))
    if (
        not isinstance(current_projection, dict)
        or interview.get("original_source_id") != current_projection.get("source_id")
        or interview.get("original_projection_id") != current_projection.get("id")
        or current_projection.get("sha256") != saved.get("projection_sha256")
    ):
        return _blocked(
            "invalid intake state", "the prepared-round source lineage changed"
        )
    expected_ledger_length = first_sequence + (2 * len(answers))
    if (
        len(entries) < expected_ledger_length
        or (not allow_later_phase and len(entries) != expected_ledger_length)
    ):
        return _blocked(
            "invalid ledger", "the prepared-round answer ledger length changed"
        )
    first_question = questions[0]
    if (
        not isinstance(first_question, dict)
        or entries[first_sequence - 1].get("event") != "operator_question_asked"
        or entries[first_sequence - 1].get("round") != round_number
        or entries[first_sequence - 1].get("question_position") != 1
        or entries[first_sequence - 1].get("question") != first_question
        or entries[first_sequence - 1].get("prepared_round_result_sha256")
        != result_sha256
    ):
        return _blocked(
            "invalid ledger", "question 1 was not presented from the prepared round"
        )
    prior_source_numbers = _known_source_numbers(entries[: first_sequence - 1])
    answer_source_ids: list[str] = []
    for index, saved_answer in enumerate(answers):
        question = questions[index]
        if not isinstance(question, dict) or not isinstance(saved_answer, dict):
            return _blocked(
                "invalid ledger", f"prepared-round answer {index + 1} changed"
            )
        source = saved_answer.get("source")
        projection = saved_answer.get("projection")
        if not isinstance(source, dict) or not isinstance(projection, dict):
            return _blocked(
                "invalid ledger", f"prepared-round answer {index + 1} lost its artifacts"
            )
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id.startswith("source-"):
            return _blocked(
                "invalid ledger", f"prepared-round answer {index + 1} has no source identity"
            )
        suffix = source_id.removeprefix("source-")
        if len(suffix) != 6 or not suffix.isdigit():
            return _blocked(
                "invalid ledger", f"prepared-round answer {index + 1} has an invalid source identity"
            )
        number = int(suffix)
        if number in prior_source_numbers or source_id in answer_source_ids:
            return _blocked(
                "invalid ledger", f"prepared-round answer {index + 1} reused a source identity"
            )
        source_path = work / f"sources/source-{number:06d}.txt"
        projection_path = work / f"projections/source-{number:06d}-v1.txt"
        try:
            source_bytes = source_path.read_bytes()
            projection_bytes = projection_path.read_bytes()
        except OSError:
            return _blocked(
                "invalid ledger", f"prepared-round answer {index + 1} is unavailable"
            )
        sha256 = _digest_bytes(source_bytes)
        expected_source = _round_answer_source_record(number, sha256, question)
        expected_projection = _round_answer_projection_record(number, sha256)
        question_sequence = first_sequence + (2 * index)
        lineage = {
            "question_ledger_sequence": question_sequence,
            "question_round": round_number,
            "question_position": index + 1,
            "original_source_id": interview.get("original_source_id"),
            "original_projection_id": interview.get("original_projection_id"),
            "prepared_round_result_sha256": result_sha256,
        }
        answer_entry = entries[question_sequence]
        following_entry = entries[question_sequence + 1]
        if (
            not source_bytes.strip()
            or projection_bytes != source_bytes
            or source != expected_source
            or projection != expected_projection
            or saved_answer
            != {"question": question, "source": source, "projection": projection}
            or answer_entry.get("event") != "source_projected"
            or answer_entry.get("round") != round_number
            or answer_entry.get("question_position") != index + 1
            or answer_entry.get("answers_question") != question.get("id")
            or answer_entry.get("answers_gap") != question.get("answers_gap")
            or answer_entry.get("source") != source
            or answer_entry.get("projection") != projection
            or answer_entry.get("lineage") != lineage
        ):
            return _blocked(
                "invalid ledger", f"prepared-round answer {index + 1} changed"
            )
        answer_source_ids.append(source_id)
        if index + 1 < len(questions):
            next_question = questions[index + 1]
            if (
                following_entry.get("event") != "operator_question_asked"
                or following_entry.get("round") != round_number
                or following_entry.get("question_position") != index + 2
                or following_entry.get("question") != next_question
                or following_entry.get("prepared_round_result_sha256")
                != result_sha256
            ):
                return _blocked(
                    "invalid ledger", f"prepared question {index + 2} changed"
                )
        elif (
            following_entry.get("event") != "operator_question_round_answered"
            or following_entry.get("round") != round_number
            or following_entry.get("question_count") != len(questions)
            or following_entry.get("answered_question_count") != len(answers)
            or following_entry.get("answer_source_ids") != answer_source_ids
            or following_entry.get("prepared_round_result_sha256")
            != result_sha256
        ):
            return _blocked(
                "invalid ledger", "the prepared question round completion changed"
            )
    if len(answers) < len(questions):
        active = questions[len(answers)]
        expected_state = (
            "needs_operator",
            "awaiting_prepared_question_round_answers",
            active.get("id") if isinstance(active, dict) else None,
            active,
        )
    else:
        expected_states = {
            (
                "ready_for_projection_assessment",
                "prepared_question_round_answered",
                None,
                None,
            )
        }
        if allow_later_phase:
            paths = _answer_assessment_paths(round_number)
            expected_states.update({
                (
                    "waiting_for_model",
                    "assessing_prepared_question_round_answers",
                    paths["interview_path"],
                    None,
                ),
                (
                    "ready_for_projection_assessment",
                    "prepared_question_round_assessment_recorded",
                    None,
                    None,
                ),
            })
        expected_state = (
            state.get("status"),
            state.get("phase"),
            state.get("waiting_for"),
            state.get("question"),
        )
        if expected_state not in expected_states:
            return _blocked(
                "invalid intake state", "the prepared-round interview state changed"
            )
    if (
        len(answers) < len(questions)
        and (
            state.get("status"), state.get("phase"), state.get("waiting_for"),
            state.get("question"),
        ) != expected_state
        or state.get("ledger_entries") != len(entries)
        or state.get("ledger_tail_sha256") != entries[-1].get("entry_sha256")
    ):
        return _blocked(
            "invalid intake state", "the prepared-round interview state changed"
        )
    return None


def _accept_prepared_question_round_answer(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    answer: str,
) -> dict[str, object]:
    interview_error = _validate_prepared_question_round_interview(
        work, state, entries, purpose
    )
    if interview_error:
        return interview_error
    if not answer.strip():
        return _blocked(
            "gap answer required",
            "answer the current operator question with non-whitespace text",
        )
    saved = state["follow_up_gap_question_round"]
    interview = state["prepared_question_round_interview"]
    assert isinstance(saved, dict) and isinstance(interview, dict)
    questions = saved["questions"]
    answers = interview["answers"]
    round_number = interview["round"]
    result_sha256 = interview["prepared_round_result_sha256"]
    assert isinstance(questions, list) and isinstance(answers, list)
    assert isinstance(round_number, int) and isinstance(result_sha256, str)
    index = len(answers)
    if index >= len(questions):
        return _blocked("gap answer not requested", "the question round is already answered")
    question = questions[index]
    assert isinstance(question, dict)
    known_numbers = _known_source_numbers(entries)
    number = max(known_numbers, default=0) + 1
    source_path = work / f"sources/source-{number:06d}.txt"
    projection_path = work / f"projections/source-{number:06d}-v1.txt"
    if source_path.exists() or projection_path.exists():
        return _blocked(
            "unbound gap answer artifacts",
            f"answer {index + 1} artifacts already exist outside the ledger",
        )
    answer_bytes = answer.encode("utf-8")
    answer_sha256 = _digest_bytes(answer_bytes)
    source = _round_answer_source_record(number, answer_sha256, question)
    projection = _round_answer_projection_record(number, answer_sha256)
    source_path.write_bytes(answer_bytes)
    projection_path.write_bytes(answer_bytes)
    timestamp = datetime.now(timezone.utc).isoformat()
    first_sequence = interview["first_question_ledger_sequence"]
    assert isinstance(first_sequence, int)
    answer_entry = _ledger_entry(
        len(entries) + 1,
        "source_projected",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "round": round_number,
            "question_position": index + 1,
            "answers_question": question["id"],
            "answers_gap": question["answers_gap"],
            "source": source,
            "projection": projection,
            "lineage": {
                "question_ledger_sequence": first_sequence + (2 * index),
                "question_round": round_number,
                "question_position": index + 1,
                "original_source_id": interview["original_source_id"],
                "original_projection_id": interview["original_projection_id"],
                "prepared_round_result_sha256": result_sha256,
            },
        },
        str(entries[-1]["entry_sha256"]),
    )
    saved_answer = {"question": question, "source": source, "projection": projection}
    answers.append(saved_answer)
    if len(answers) < len(questions):
        next_question = questions[len(answers)]
        assert isinstance(next_question, dict)
        following_entry = _ledger_entry(
            len(entries) + 2,
            "operator_question_asked",
            {
                "recorded_at": timestamp,
                "intake_id": state["intake_id"],
                "round": round_number,
                "question_position": len(answers) + 1,
                "question": next_question,
                "prepared_round_result_sha256": result_sha256,
            },
            str(answer_entry["entry_sha256"]),
        )
        state.update({
            "status": "needs_operator",
            "phase": "awaiting_prepared_question_round_answers",
            "waiting_for": next_question["id"],
            "question": next_question,
        })
    else:
        following_entry = _ledger_entry(
            len(entries) + 2,
            "operator_question_round_answered",
            {
                "recorded_at": timestamp,
                "intake_id": state["intake_id"],
                "round": round_number,
                "question_count": len(questions),
                "answered_question_count": len(answers),
                "answer_source_ids": [item["source"]["id"] for item in answers],
                "prepared_round_result_sha256": result_sha256,
            },
            str(answer_entry["entry_sha256"]),
        )
        state.update({
            "status": "ready_for_projection_assessment",
            "phase": "prepared_question_round_answered",
            "waiting_for": None,
            "question": None,
        })
    _append_ledger(work / "ledger.jsonl", [answer_entry, following_entry])
    interview["answers"] = answers
    state.update({
        "ledger_entries": len(entries) + 2,
        "ledger_tail_sha256": following_entry["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    if state["phase"] == "prepared_question_round_answered":
        return _prepared_question_round_answered_result(state, work)
    return _prepared_question_round_operator_result(state, work)


def _validate_gap_question_answer_records(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    questions: list[dict[str, object]],
    *,
    allow_later_phase: bool = False,
) -> str | None:
    answers = state.get("gap_question_answers")
    if not isinstance(answers, list) or len(answers) > len(questions):
        return "the preserved answer sequence is invalid"
    answer_ledger_length = 14 + (2 * len(answers))
    if (
        len(entries) < answer_ledger_length
        or (not allow_later_phase and len(entries) != answer_ledger_length)
    ):
        return "the answer ledger length does not match the preserved answers"
    if (
        entries[13].get("event") != "operator_question_asked"
        or entries[13].get("round") != 1
        or entries[13].get("question_position") != 1
        or entries[13].get("question") != questions[0]
    ):
        return "question 1 was not presented from the prepared round"
    for index, saved in enumerate(answers):
        question = questions[index]
        number = 4 + index
        source_path = work / f"sources/source-{number:06d}.txt"
        projection_path = work / f"projections/source-{number:06d}-v1.txt"
        try:
            source_bytes = source_path.read_bytes()
            projection_bytes = projection_path.read_bytes()
        except OSError:
            return f"answer {index + 1} source or projection is unavailable"
        sha256 = _digest_bytes(source_bytes)
        source = _round_answer_source_record(number, sha256, question)
        projection = _round_answer_projection_record(number, sha256)
        question_sequence = 14 + (2 * index)
        lineage = {
            "question_ledger_sequence": question_sequence,
            "question_round": 1,
            "question_position": index + 1,
            "original_source_id": "source-000003",
            "original_projection_id": state["first_projection"]["id"],
        }
        answer_entry = entries[14 + (2 * index)]
        following_entry = entries[15 + (2 * index)]
        if (
            not source_bytes.strip()
            or projection_bytes != source_bytes
            or saved != {"question": question, "source": source, "projection": projection}
            or answer_entry.get("event") != "source_projected"
            or answer_entry.get("round") != 1
            or answer_entry.get("question_position") != index + 1
            or answer_entry.get("answers_question") != question["id"]
            or answer_entry.get("answers_gap") != question["answers_gap"]
            or answer_entry.get("source") != source
            or answer_entry.get("projection") != projection
            or answer_entry.get("lineage") != lineage
        ):
            return f"answer {index + 1} no longer matches its immutable lineage"
        if index + 1 < len(questions):
            next_question = questions[index + 1]
            if (
                following_entry.get("event") != "operator_question_asked"
                or following_entry.get("round") != 1
                or following_entry.get("question_position") != index + 2
                or following_entry.get("question") != next_question
            ):
                return f"question {index + 2} was not presented after answer {index + 1}"
        elif (
            following_entry.get("event") != "operator_question_round_answered"
            or following_entry.get("round") != 1
            or following_entry.get("question_count") != len(questions)
            or following_entry.get("answered_question_count") != len(answers)
            or following_entry.get("answer_source_ids")
            != [f"source-{4 + answer_index:06d}" for answer_index in range(len(answers))]
        ):
            return "the completed answer round does not match its preserved sources"
    if len(answers) < len(questions):
        active = questions[len(answers)]
        if (
            state.get("status") != "needs_operator"
            or state.get("phase") != "awaiting_gap_answers"
            or state.get("waiting_for") != active["id"]
            or state.get("question") != active
        ):
            return f"question {len(answers) + 1} is not the only active operator question"
    else:
        expected_states = {
            (
                "ready_for_projection_assessment",
                "gap_question_round_answered",
                None,
            )
        }
        if allow_later_phase:
            active_resolution = state.get("gap_resolution")
            active_attempt = (
                active_resolution.get("attempt")
                if isinstance(active_resolution, dict)
                else 1
            )
            active_paths = _resolution_paths(
                active_attempt if isinstance(active_attempt, int) else 1
            )
            expected_states.update({
                (
                    "waiting_for_model",
                    "assessing_gap_answers",
                    "gap-answer-assessments/round-000001/interview.jsonl",
                ),
                (
                    "ready_for_projection_assessment",
                    "gap_answer_assessment_recorded",
                    None,
                ),
                (
                    "waiting_for_model",
                    "resolving_gap_answer",
                    active_paths["interview_path"],
                ),
                (
                    "waiting_for_model",
                    "verifying_gap_resolution",
                    active_paths["verification_interview_path"],
                ),
                (
                    "ready_for_projection_assessment",
                    "gap_resolution_applied",
                    None,
                ),
                (
                    "ready_for_projection_assessment",
                    "gap_resolution_rejected",
                    None,
                ),
                (
                    "waiting_for_model",
                    "formulating_follow_up_gap_question_round",
                    "gap-question-rounds/round-000002/interview.jsonl",
                ),
                (
                    "ready_for_operator_interview",
                    "follow_up_gap_question_round_recorded",
                    None,
                ),
                (
                    "needs_operator",
                    "awaiting_prepared_question_round_answers",
                    state.get("waiting_for"),
                ),
                (
                    "ready_for_projection_assessment",
                    "prepared_question_round_answered",
                    None,
                ),
                (
                    "waiting_for_model",
                    "assessing_prepared_question_round_answers",
                    state.get("waiting_for"),
                ),
                (
                    "ready_for_projection_assessment",
                    "prepared_question_round_assessment_recorded",
                    None,
                ),
            })
        if (
            (state.get("status"), state.get("phase"), state.get("waiting_for"))
            not in expected_states
            or (
                state.get("question") is not None
                and state.get("phase")
                != "awaiting_prepared_question_round_answers"
            )
        ):
            return "the completed answer round has an invalid terminal state"
    return None


def _validate_gap_question_round(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    projection_path, projection_sha256, request_error = (
        _validate_gap_question_round_request(work, state, entries)
    )
    if request_error:
        return request_error
    assert projection_path is not None and projection_sha256 is not None
    round_dir = work / "gap-question-rounds" / "round-000001"
    try:
        result, journal_sha256, result_sha256 = gap_clarification.validate_round(
            round_dir,
            projection_path=projection_path,
            projection_sha256=projection_sha256,
            purpose=purpose,
        )
        journal_entries = gap_clarification._read_journal(
            round_dir / "interview.jsonl"
        )
    except gap_clarification.ClarificationError as error:
        return _blocked("invalid gap question round", str(error))
    saved = state.get("gap_question_round")
    if not isinstance(saved, dict) or not isinstance(saved.get("gaps"), list):
        return _blocked("invalid intake state", "the gap question round is missing")
    shape_error = _validate_question_round_shape(result, saved["gaps"])
    expected_completed = {
        "round": 1,
        "interview_path": "gap-question-rounds/round-000001/interview.jsonl",
        "interview_sha256": journal_sha256,
        "result_path": "gap-question-rounds/round-000001/clarification-round.json",
        "result_sha256": result_sha256,
        "question_count": len(result["questions"]),
        "interview_question_count": sum(
            item["event"] == "question_asked" for item in journal_entries
        ),
        "answer_count": sum(
            item["event"] == "answer_recorded" for item in journal_entries
        ),
        "rejected_answer_count": sum(
            item["event"] == "answer_recorded" and item["accepted"] is False
            for item in journal_entries
        ),
        "questioner": result["questioner"],
        "gaps": result["gaps"],
        "questions": result["questions"],
    }
    questions = result["questions"]
    assert isinstance(questions, list)
    answer_error = _validate_gap_question_answer_records(
        work,
        state,
        entries,
        questions,
        allow_later_phase=allow_later_phase,
    )
    if (
        shape_error
        or entries[11].get("event") != "model_gap_question_round_completed"
        or any(entries[11].get(key) != value for key, value in expected_completed.items())
        or entries[12].get("event") != "operator_question_round_prepared"
        or entries[12].get("questions") != result["questions"]
        or entries[12].get("question_count") != len(result["questions"])
        or saved.get("interview_sha256") != journal_sha256
        or saved.get("result_sha256") != result_sha256
        or saved.get("questioner") != result["questioner"]
        or state.get("questions") != result["questions"]
        or answer_error
    ):
        return _blocked(
            "invalid ledger",
            shape_error or answer_error or "the preserved gap question round changed",
        )
    return None


def _accept_gap_question_round_answer(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    answer: str,
) -> dict[str, object]:
    if not answer.strip():
        return _blocked(
            "gap answer required",
            "answer the current operator question with non-whitespace text",
        )
    questions = state["questions"]
    answers = state["gap_question_answers"]
    assert isinstance(questions, list) and isinstance(answers, list)
    index = len(answers)
    if index >= len(questions):
        return _blocked("gap answer not requested", "the question round is already answered")
    question = questions[index]
    assert isinstance(question, dict)
    number = 4 + index
    source_path = work / f"sources/source-{number:06d}.txt"
    projection_path = work / f"projections/source-{number:06d}-v1.txt"
    if source_path.exists() or projection_path.exists():
        return _blocked(
            "unbound gap answer artifacts",
            f"answer {index + 1} artifacts already exist outside the ledger",
        )
    answer_bytes = answer.encode("utf-8")
    answer_sha256 = _digest_bytes(answer_bytes)
    source = _round_answer_source_record(number, answer_sha256, question)
    projection = _round_answer_projection_record(number, answer_sha256)
    source_path.write_bytes(answer_bytes)
    projection_path.write_bytes(answer_bytes)
    timestamp = datetime.now(timezone.utc).isoformat()
    answer_entry = _ledger_entry(
        len(entries) + 1,
        "source_projected",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "round": 1,
            "question_position": index + 1,
            "answers_question": question["id"],
            "answers_gap": question["answers_gap"],
            "source": source,
            "projection": projection,
            "lineage": {
                "question_ledger_sequence": 14 + (2 * index),
                "question_round": 1,
                "question_position": index + 1,
                "original_source_id": "source-000003",
                "original_projection_id": state["first_projection"]["id"],
            },
        },
        str(entries[-1]["entry_sha256"]),
    )
    saved_answer = {"question": question, "source": source, "projection": projection}
    answers.append(saved_answer)
    if len(answers) < len(questions):
        next_question = questions[len(answers)]
        assert isinstance(next_question, dict)
        following_entry = _ledger_entry(
            len(entries) + 2,
            "operator_question_asked",
            {
                "recorded_at": timestamp,
                "intake_id": state["intake_id"],
                "round": 1,
                "question_position": len(answers) + 1,
                "question": next_question,
            },
            str(answer_entry["entry_sha256"]),
        )
        state.update({
            "status": "needs_operator",
            "phase": "awaiting_gap_answers",
            "waiting_for": next_question["id"],
            "question": next_question,
        })
    else:
        following_entry = _ledger_entry(
            len(entries) + 2,
            "operator_question_round_answered",
            {
                "recorded_at": timestamp,
                "intake_id": state["intake_id"],
                "round": 1,
                "question_count": len(questions),
                "answered_question_count": len(answers),
                "answer_source_ids": [item["source"]["id"] for item in answers],
            },
            str(answer_entry["entry_sha256"]),
        )
        state.update({
            "status": "ready_for_projection_assessment",
            "phase": "gap_question_round_answered",
            "waiting_for": None,
            "question": None,
        })
    _append_ledger(work / "ledger.jsonl", [answer_entry, following_entry])
    state.update({
        "gap_question_answers": answers,
        "ledger_entries": len(entries) + 2,
        "ledger_tail_sha256": following_entry["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    if state["phase"] == "gap_question_round_answered":
        return _gap_question_round_answered_result(state, work)
    return _gap_question_round_operator_result(state, work)


def _answer_assessment_bindings(
    work: Path,
    questions: object,
    answers: object,
    gaps: object,
) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    if (
        not isinstance(questions, list)
        or not isinstance(answers, list)
        or not isinstance(gaps, list)
        or not questions
        or len(questions) != len(answers)
        or len(questions) != len(gaps)
    ):
        return None, _blocked(
            "gap answer assessment unavailable",
            "the complete question, answer, and gap sets are not aligned",
        )
    bindings: list[dict[str, object]] = []
    for index, (question, answer_record, gap) in enumerate(
        zip(questions, answers, gaps, strict=True), 1
    ):
        if (
            not isinstance(question, dict)
            or not isinstance(answer_record, dict)
            or not isinstance(gap, dict)
            or not isinstance(answer_record.get("source"), dict)
            or not isinstance(answer_record.get("projection"), dict)
        ):
            return None, _blocked(
                "gap answer assessment unavailable",
                f"answer {index} is missing its bound source, projection, question, or gap",
            )
        source = answer_record["source"]
        projection = answer_record["projection"]
        assert isinstance(source, dict) and isinstance(projection, dict)
        try:
            source_bytes = (work / str(source["path"])).read_bytes()
            projection_bytes = (work / str(projection["path"])).read_bytes()
            answer = source_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError, KeyError) as error:
            return None, _blocked(
                "gap answer assessment unavailable",
                f"answer {index} source or projection cannot be read: {error}",
            )
        if (
            projection_bytes != source_bytes
            or _digest_bytes(source_bytes) != source.get("sha256")
            or projection.get("sha256") != source.get("sha256")
        ):
            return None, _blocked(
                "gap answer assessment unavailable",
                f"answer {index} no longer matches its immutable source and projection",
            )
        bindings.append({
            "position": index,
            "question": question,
            "gap": gap,
            "answer_source": source,
            "answer_projection": projection,
            "answer": answer,
        })
    try:
        gap_answer_assessment.identities(bindings)
    except gap_answer_assessment.AssessmentError as error:
        return None, _blocked("gap answer assessment unavailable", str(error))
    return bindings, None


def _gap_answer_assessment_bindings(
    work: Path, state: dict[str, object]
) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    round_record = state.get("gap_question_round")
    gaps = round_record.get("gaps") if isinstance(round_record, dict) else None
    return _answer_assessment_bindings(
        work,
        state.get("questions"),
        state.get("gap_question_answers"),
        gaps,
    )


def _prepared_question_round_assessment_bindings(
    work: Path, state: dict[str, object]
) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    prepared = state.get("follow_up_gap_question_round")
    interview = state.get("prepared_question_round_interview")
    if not isinstance(prepared, dict) or not isinstance(interview, dict):
        return None, _blocked(
            "prepared answer assessment unavailable",
            "the completed prepared question round is missing",
        )
    if prepared.get("round") != interview.get("round"):
        return None, _blocked(
            "prepared answer assessment unavailable",
            "the prepared question round and its answers have different round identities",
        )
    return _answer_assessment_bindings(
        work,
        prepared.get("questions"),
        interview.get("answers"),
        prepared.get("gaps"),
    )


def _answer_assessment_paths(round_number: int) -> dict[str, str]:
    directory = f"gap-answer-assessments/round-{round_number:06d}"
    return {
        "directory": directory,
        "interview_path": f"{directory}/interview.jsonl",
        "result_path": f"{directory}/assessment.json",
    }


def _request_gap_answer_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    bindings, binding_error = _gap_answer_assessment_bindings(work, state)
    if binding_error:
        return binding_error
    assert bindings is not None
    assessment_dir = work / "gap-answer-assessments" / "round-000001"
    if assessment_dir.exists():
        return _blocked(
            "unbound gap answer assessment",
            "assessment artifacts already exist outside the ledger",
        )
    identities = gap_answer_assessment.identities(bindings)
    request_sequence = len(entries) + 1
    request = _ledger_entry(
        request_sequence,
        "model_gap_answer_assessment_requested",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "round": 1,
            "contract": gap_answer_assessment.CONTRACT,
            "assessment_count": len(bindings),
            "bindings": identities,
            "interview_path": "gap-answer-assessments/round-000001/interview.jsonl",
            "result_path": "gap-answer-assessments/round-000001/assessment.json",
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [request])
    state.update({
        "status": "waiting_for_model",
        "phase": "assessing_gap_answers",
        "waiting_for": "gap-answer-assessments/round-000001/interview.jsonl",
        "question": None,
        "gap_answer_assessment": {
            "round": 1,
            "contract": gap_answer_assessment.CONTRACT,
            "request_ledger_sequence": request_sequence,
            "assessment_count": len(bindings),
            "bindings": identities,
        },
        "ledger_entries": request_sequence,
        "ledger_tail_sha256": request["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_answer_assessment_model_result(state, work)


def _validate_gap_answer_assessment_request(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    bindings, binding_error = _gap_answer_assessment_bindings(work, state)
    if binding_error:
        return None, binding_error
    assert bindings is not None
    identities = gap_answer_assessment.identities(bindings)
    saved = state.get("gap_answer_assessment")
    if not isinstance(saved, dict):
        return None, _blocked(
            "invalid intake state", "the gap answer assessment request is missing"
        )
    request_sequence = saved.get("request_ledger_sequence")
    if not isinstance(request_sequence, int) or not 1 <= request_sequence <= len(entries):
        return None, _blocked(
            "invalid ledger", "the gap answer assessment request sequence is invalid"
        )
    request = entries[request_sequence - 1]
    expected = {
        "round": 1,
        "contract": gap_answer_assessment.CONTRACT,
        "assessment_count": len(bindings),
        "bindings": identities,
        "interview_path": "gap-answer-assessments/round-000001/interview.jsonl",
        "result_path": "gap-answer-assessments/round-000001/assessment.json",
    }
    expected_saved = {
        "round": 1,
        "contract": gap_answer_assessment.CONTRACT,
        "request_ledger_sequence": request_sequence,
        "assessment_count": len(bindings),
        "bindings": identities,
    }
    if (
        request.get("event") != "model_gap_answer_assessment_requested"
        or any(request.get(key) != value for key, value in expected.items())
        or any(saved.get(key) != value for key, value in expected_saved.items())
    ):
        return None, _blocked(
            "invalid ledger", "the gap answer assessment request changed"
        )
    return bindings, None


def _validate_gap_answer_assessment_shape(
    result: dict[str, object], bindings: list[dict[str, object]]
) -> str | None:
    assessments = result.get("assessments")
    if not isinstance(assessments, list) or len(assessments) != len(bindings):
        return "the assessment does not contain exactly one outcome per preserved answer"
    for index, (assessment, binding) in enumerate(
        zip(assessments, bindings, strict=True), 1
    ):
        identity = gap_answer_assessment._assessment_identity(binding)
        if not isinstance(assessment, dict):
            return f"assessment {index} is not a record"
        actual_identity = {
            key: assessment.get(key)
            for key in (
                "position", "question_id", "gap", "answer_source", "answer_projection"
            )
        }
        if actual_identity != identity:
            return f"assessment {index} is not bound to answer {index} and its exact gap"
        if assessment.get("verdict") not in gap_answer_assessment.VERDICTS:
            return f"assessment {index} has unsupported verdict {assessment.get('verdict')!r}"
        if not isinstance(assessment.get("reason"), str) or not assessment["reason"].strip():
            return f"assessment {index} has no reason for its verdict"
    return None


def _consume_gap_answer_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    bindings, request_error = _validate_gap_answer_assessment_request(
        work, state, entries
    )
    if request_error:
        return request_error
    assert bindings is not None
    assessment_dir = work / "gap-answer-assessments" / "round-000001"
    try:
        result, journal_sha256, result_sha256 = gap_answer_assessment.validate(
            assessment_dir, bindings=bindings, purpose=purpose
        )
        journal_entries = gap_answer_assessment._read_journal(
            assessment_dir / "interview.jsonl"
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("invalid gap answer assessment", str(error))
    shape_error = _validate_gap_answer_assessment_shape(result, bindings)
    if shape_error:
        return _blocked("invalid gap answer assessment", shape_error)
    completed = _ledger_entry(
        len(entries) + 1,
        "model_gap_answer_assessment_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "round": 1,
            "interview_path": "gap-answer-assessments/round-000001/interview.jsonl",
            "interview_sha256": journal_sha256,
            "result_path": "gap-answer-assessments/round-000001/assessment.json",
            "result_sha256": result_sha256,
            "assessment_count": len(result["assessments"]),
            "question_count": sum(
                item["event"] == "question_asked" for item in journal_entries
            ),
            "answer_count": sum(
                item["event"] == "answer_recorded" for item in journal_entries
            ),
            "rejected_answer_count": sum(
                item["event"] == "answer_recorded" and item["accepted"] is False
                for item in journal_entries
            ),
            "assessor": result["assessor"],
            "assessments": result["assessments"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed])
    state["gap_answer_assessment"].update({
        "interview_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "assessor": result["assessor"],
        "assessments": result["assessments"],
    })
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "gap_answer_assessment_recorded",
        "waiting_for": None,
        "question": None,
        "ledger_entries": len(entries) + 1,
        "ledger_tail_sha256": completed["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_answer_assessment_ready_result(state, work)


def _validate_gap_answer_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    bindings, request_error = _validate_gap_answer_assessment_request(
        work, state, entries
    )
    if request_error:
        return request_error
    assert bindings is not None
    assessment_dir = work / "gap-answer-assessments" / "round-000001"
    try:
        result, journal_sha256, result_sha256 = gap_answer_assessment.validate(
            assessment_dir, bindings=bindings, purpose=purpose
        )
        journal_entries = gap_answer_assessment._read_journal(
            assessment_dir / "interview.jsonl"
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("invalid gap answer assessment", str(error))
    shape_error = _validate_gap_answer_assessment_shape(result, bindings)
    expected = {
        "round": 1,
        "interview_path": "gap-answer-assessments/round-000001/interview.jsonl",
        "interview_sha256": journal_sha256,
        "result_path": "gap-answer-assessments/round-000001/assessment.json",
        "result_sha256": result_sha256,
        "assessment_count": len(result["assessments"]),
        "question_count": sum(
            item["event"] == "question_asked" for item in journal_entries
        ),
        "answer_count": sum(
            item["event"] == "answer_recorded" for item in journal_entries
        ),
        "rejected_answer_count": sum(
            item["event"] == "answer_recorded" and item["accepted"] is False
            for item in journal_entries
        ),
        "assessor": result["assessor"],
        "assessments": result["assessments"],
    }
    saved = state.get("gap_answer_assessment")
    request_sequence = (
        saved.get("request_ledger_sequence") if isinstance(saved, dict) else None
    )
    completed_index = request_sequence if isinstance(request_sequence, int) else -1
    expected_states = {
        ("ready_for_projection_assessment", "gap_answer_assessment_recorded", None)
    }
    if allow_later_phase:
        active_resolution = state.get("gap_resolution")
        active_attempt = (
            active_resolution.get("attempt")
            if isinstance(active_resolution, dict)
            else 1
        )
        active_paths = _resolution_paths(
            active_attempt if isinstance(active_attempt, int) else 1
        )
        expected_states.update({
            (
                "waiting_for_model",
                "resolving_gap_answer",
                active_paths["interview_path"],
            ),
            (
                "waiting_for_model",
                "verifying_gap_resolution",
                active_paths["verification_interview_path"],
            ),
            ("ready_for_projection_assessment", "gap_resolution_applied", None),
            ("ready_for_projection_assessment", "gap_resolution_rejected", None),
            (
                "waiting_for_model",
                "formulating_follow_up_gap_question_round",
                "gap-question-rounds/round-000002/interview.jsonl",
            ),
            (
                "ready_for_operator_interview",
                "follow_up_gap_question_round_recorded",
                None,
            ),
            (
                "needs_operator",
                "awaiting_prepared_question_round_answers",
                state.get("waiting_for"),
            ),
            (
                "ready_for_projection_assessment",
                "prepared_question_round_answered",
                None,
            ),
            (
                "waiting_for_model",
                "assessing_prepared_question_round_answers",
                state.get("waiting_for"),
            ),
            (
                "ready_for_projection_assessment",
                "prepared_question_round_assessment_recorded",
                None,
            ),
        })
    if (
        shape_error
        or completed_index < 0
        or completed_index >= len(entries)
        or entries[completed_index].get("event")
        != "model_gap_answer_assessment_completed"
        or any(
            entries[completed_index].get(key) != value
            for key, value in expected.items()
        )
        or not isinstance(saved, dict)
        or saved.get("interview_sha256") != journal_sha256
        or saved.get("result_sha256") != result_sha256
        or saved.get("assessor") != result["assessor"]
        or saved.get("assessments") != result["assessments"]
        or (
            state.get("status"), state.get("phase"), state.get("waiting_for")
        ) not in expected_states
        or (
            state.get("question") is not None
            and state.get("phase") != "awaiting_prepared_question_round_answers"
        )
    ):
        return _blocked(
            "invalid ledger",
            shape_error or "the preserved gap answer assessment changed",
        )
    return None


def _prepared_question_round_assessment_record(
    state: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    prepared = state.get("follow_up_gap_question_round")
    records = state.get("prepared_question_round_assessments")
    if not isinstance(prepared, dict) or not isinstance(prepared.get("round"), int):
        return None, _blocked(
            "invalid intake state", "the prepared question round identity is missing"
        )
    if not isinstance(records, list):
        return None, _blocked(
            "invalid intake state", "the prepared-round assessment history is missing"
        )
    matching = [
        record
        for record in records
        if isinstance(record, dict) and record.get("round") == prepared["round"]
    ]
    if len(matching) != 1:
        return None, _blocked(
            "invalid intake state",
            "the current prepared round must have exactly one assessment record",
        )
    return matching[0], None


def _prepared_question_round_assessment_model_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    record, record_error = _prepared_question_round_assessment_record(state)
    assert record_error is None and record is not None
    return {
        "status": "waiting_for_model",
        "stopped": "assessing_prepared_question_round_answers",
        "intake_id": state["intake_id"],
        "round": record["round"],
        "work": [{
            "stage": "assess_prepared_question_round_answers",
            "instruction": (
                "Inspect each code-bound preserved answer and judge only whether it "
                "resolves its exact gap. Code fixes every pair, order, and verdict choice."
            ),
            "attachments": [str((work / "sources" / "source-000003").resolve())],
            "command": [
                sys.executable,
                str(Path(__file__).resolve()),
                "--work",
                str(work.resolve()),
                "--run-gap-answer-assessment",
            ],
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _prepared_question_round_assessment_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    record, record_error = _prepared_question_round_assessment_record(state)
    assert record_error is None and record is not None
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "prepared_question_round_assessment_recorded",
        "intake_id": state["intake_id"],
        "round": record["round"],
        "projection": state.get("current_projection", state["first_projection"]),
        "assessment_count": record["assessment_count"],
        "assessments": record["assessments"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _request_prepared_question_round_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    bindings, binding_error = _prepared_question_round_assessment_bindings(
        work, state
    )
    if binding_error:
        return binding_error
    assert bindings is not None
    prepared = state.get("follow_up_gap_question_round")
    assert isinstance(prepared, dict)
    round_number = prepared.get("round")
    result_sha256 = prepared.get("result_sha256")
    if (
        not isinstance(round_number, int)
        or round_number < 1
        or not isinstance(result_sha256, str)
    ):
        return _blocked(
            "prepared answer assessment unavailable",
            "the prepared round identity or immutable result is missing",
        )
    records = state.get("prepared_question_round_assessments", [])
    if not isinstance(records, list) or any(
        not isinstance(record, dict) for record in records
    ):
        return _blocked(
            "prepared answer assessment unavailable",
            "the prepared-round assessment history must remain an ordered list",
        )
    if any(record.get("round") == round_number for record in records):
        return _blocked(
            "prepared answer assessment unavailable",
            f"round {round_number} already has an assessment request",
        )
    paths = _answer_assessment_paths(round_number)
    assessment_dir = work / paths["directory"]
    if assessment_dir.exists():
        return _blocked(
            "unbound prepared answer assessment",
            f"round {round_number} assessment artifacts already exist outside the ledger",
        )
    identities = gap_answer_assessment.identities(bindings)
    request_sequence = len(entries) + 1
    answer_round_tail = entries[-1].get("entry_sha256")
    if not isinstance(answer_round_tail, str):
        return _blocked(
            "invalid ledger", "the completed answer round has no ledger identity"
        )
    request = _ledger_entry(
        request_sequence,
        "model_gap_answer_assessment_requested",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "round": round_number,
            "contract": gap_answer_assessment.CONTRACT,
            "assessment_count": len(bindings),
            "bindings": identities,
            "prepared_round_result_sha256": result_sha256,
            "answer_round_ledger_tail_sha256": answer_round_tail,
            "interview_path": paths["interview_path"],
            "result_path": paths["result_path"],
        },
        str(answer_round_tail),
    )
    _append_ledger(work / "ledger.jsonl", [request])
    record = {
        "round": round_number,
        "contract": gap_answer_assessment.CONTRACT,
        "request_ledger_sequence": request_sequence,
        "assessment_count": len(bindings),
        "bindings": identities,
        "prepared_round_result_sha256": result_sha256,
        "answer_round_ledger_tail_sha256": answer_round_tail,
    }
    state.update({
        "status": "waiting_for_model",
        "phase": "assessing_prepared_question_round_answers",
        "waiting_for": paths["interview_path"],
        "question": None,
        "prepared_question_round_assessments": [*records, record],
        "ledger_entries": request_sequence,
        "ledger_tail_sha256": request["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _prepared_question_round_assessment_model_result(state, work)


def _validate_prepared_question_round_assessment_request(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> tuple[
    list[dict[str, object]] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    bindings, binding_error = _prepared_question_round_assessment_bindings(
        work, state
    )
    if binding_error:
        return None, None, binding_error
    assert bindings is not None
    saved, saved_error = _prepared_question_round_assessment_record(state)
    if saved_error:
        return None, None, saved_error
    assert saved is not None
    round_number = saved.get("round")
    request_sequence = saved.get("request_ledger_sequence")
    if (
        not isinstance(round_number, int)
        or not isinstance(request_sequence, int)
        or not 1 <= request_sequence <= len(entries)
    ):
        return None, None, _blocked(
            "invalid ledger", "the prepared-round assessment request sequence is invalid"
        )
    paths = _answer_assessment_paths(round_number)
    identities = gap_answer_assessment.identities(bindings)
    prepared = state.get("follow_up_gap_question_round")
    assert isinstance(prepared, dict)
    expected = {
        "round": round_number,
        "contract": gap_answer_assessment.CONTRACT,
        "assessment_count": len(bindings),
        "bindings": identities,
        "prepared_round_result_sha256": prepared.get("result_sha256"),
        "answer_round_ledger_tail_sha256": saved.get(
            "answer_round_ledger_tail_sha256"
        ),
        "interview_path": paths["interview_path"],
        "result_path": paths["result_path"],
    }
    expected_saved = {
        key: value
        for key, value in expected.items()
        if key not in {"interview_path", "result_path"}
    }
    expected_saved["request_ledger_sequence"] = request_sequence
    request = entries[request_sequence - 1]
    answer_tail = saved.get("answer_round_ledger_tail_sha256")
    if (
        request.get("event") != "model_gap_answer_assessment_requested"
        or request.get("previous_entry_sha256") != answer_tail
        or any(request.get(key) != value for key, value in expected.items())
        or any(saved.get(key) != value for key, value in expected_saved.items())
    ):
        return None, None, _blocked(
            "invalid ledger", "the prepared-round assessment request changed"
        )
    if state.get("phase") == "assessing_prepared_question_round_answers" and (
        state.get("status") != "waiting_for_model"
        or state.get("waiting_for") != paths["interview_path"]
        or state.get("question") is not None
        or len(entries) != request_sequence
        or state.get("ledger_entries") != request_sequence
        or state.get("ledger_tail_sha256") != request.get("entry_sha256")
    ):
        return None, None, _blocked(
            "invalid intake state",
            "the prepared-round assessment request is not the only active ledger event",
        )
    return bindings, saved, None


def _consume_prepared_question_round_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    bindings, saved, request_error = (
        _validate_prepared_question_round_assessment_request(work, state, entries)
    )
    if request_error:
        return request_error
    assert bindings is not None and saved is not None
    round_number = saved["round"]
    assert isinstance(round_number, int)
    paths = _answer_assessment_paths(round_number)
    assessment_dir = work / paths["directory"]
    try:
        result, journal_sha256, result_sha256 = gap_answer_assessment.validate(
            assessment_dir, bindings=bindings, purpose=purpose
        )
        journal_entries = gap_answer_assessment._read_journal(
            assessment_dir / "interview.jsonl"
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("invalid prepared answer assessment", str(error))
    shape_error = _validate_gap_answer_assessment_shape(result, bindings)
    if shape_error:
        return _blocked("invalid prepared answer assessment", shape_error)
    completed = _ledger_entry(
        len(entries) + 1,
        "model_gap_answer_assessment_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "round": round_number,
            "interview_path": paths["interview_path"],
            "interview_sha256": journal_sha256,
            "result_path": paths["result_path"],
            "result_sha256": result_sha256,
            "assessment_count": len(result["assessments"]),
            "question_count": sum(
                item["event"] == "question_asked" for item in journal_entries
            ),
            "answer_count": sum(
                item["event"] == "answer_recorded" for item in journal_entries
            ),
            "rejected_answer_count": sum(
                item["event"] == "answer_recorded" and item["accepted"] is False
                for item in journal_entries
            ),
            "assessor": result["assessor"],
            "assessments": result["assessments"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed])
    saved.update({
        "interview_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "assessor": result["assessor"],
        "assessments": result["assessments"],
    })
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "prepared_question_round_assessment_recorded",
        "waiting_for": None,
        "question": None,
        "ledger_entries": len(entries) + 1,
        "ledger_tail_sha256": completed["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _prepared_question_round_assessment_ready_result(state, work)


def _validate_prepared_question_round_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object] | None:
    bindings, saved, request_error = (
        _validate_prepared_question_round_assessment_request(work, state, entries)
    )
    if request_error:
        return request_error
    assert bindings is not None and saved is not None
    round_number = saved["round"]
    request_sequence = saved["request_ledger_sequence"]
    assert isinstance(round_number, int) and isinstance(request_sequence, int)
    paths = _answer_assessment_paths(round_number)
    assessment_dir = work / paths["directory"]
    try:
        result, journal_sha256, result_sha256 = gap_answer_assessment.validate(
            assessment_dir, bindings=bindings, purpose=purpose
        )
        journal_entries = gap_answer_assessment._read_journal(
            assessment_dir / "interview.jsonl"
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("invalid prepared answer assessment", str(error))
    shape_error = _validate_gap_answer_assessment_shape(result, bindings)
    expected = {
        "round": round_number,
        "interview_path": paths["interview_path"],
        "interview_sha256": journal_sha256,
        "result_path": paths["result_path"],
        "result_sha256": result_sha256,
        "assessment_count": len(result["assessments"]),
        "question_count": sum(
            item["event"] == "question_asked" for item in journal_entries
        ),
        "answer_count": sum(
            item["event"] == "answer_recorded" for item in journal_entries
        ),
        "rejected_answer_count": sum(
            item["event"] == "answer_recorded" and item["accepted"] is False
            for item in journal_entries
        ),
        "assessor": result["assessor"],
        "assessments": result["assessments"],
    }
    completed_index = request_sequence
    if (
        shape_error
        or len(entries) != request_sequence + 1
        or completed_index >= len(entries)
        or entries[completed_index].get("event")
        != "model_gap_answer_assessment_completed"
        or any(
            entries[completed_index].get(key) != value
            for key, value in expected.items()
        )
        or any(
            saved.get(key) != value
            for key, value in {
                "interview_sha256": journal_sha256,
                "result_sha256": result_sha256,
                "assessor": result["assessor"],
                "assessments": result["assessments"],
            }.items()
        )
        or state.get("status") != "ready_for_projection_assessment"
        or state.get("phase") != "prepared_question_round_assessment_recorded"
        or state.get("waiting_for") is not None
        or state.get("question") is not None
        or state.get("ledger_entries") != len(entries)
        or state.get("ledger_tail_sha256") != entries[-1].get("entry_sha256")
    ):
        return _blocked(
            "invalid ledger",
            shape_error or "the preserved prepared-round assessment changed",
        )
    return None


def _request_gap_clarification(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    projection_path, projection_sha256, projection_error = _projection_for_gap(work, state)
    if projection_error:
        return projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        gap = gap_clarification.select_gap(projection, projection_sha256)
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return _blocked("gap clarification unavailable", str(error))
    attempt_dir = work / "gap-clarifications" / "attempt-000001"
    if attempt_dir.exists():
        return _blocked("unbound gap clarification", "gap clarification artifacts already exist")
    eleventh = _ledger_entry(
        11,
        "model_gap_clarification_requested",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": 1,
            "contract": gap_clarification.CONTRACT,
            "projection_path": str(state["first_projection"]["path"]),
            "projection_sha256": projection_sha256,
            "interview_path": "gap-clarifications/attempt-000001/interview.jsonl",
            "result_path": "gap-clarifications/attempt-000001/clarification.json",
            "gap": gap,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [eleventh])
    state.update({
        "status": "waiting_for_model",
        "phase": "formulating_gap_question",
        "waiting_for": "gap-clarifications/attempt-000001/interview.jsonl",
        "question": None,
        "gap_clarification": {
            "attempt": 1,
            "projection_sha256": projection_sha256,
            "gap": gap,
        },
        "ledger_entries": 11,
        "ledger_tail_sha256": eleventh["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_clarification_model_result(state, work)


def _validate_gap_request(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> tuple[Path | None, str | None, dict[str, object] | None]:
    if len(entries) < 11 or entries[10].get("event") != "model_gap_clarification_requested":
        return None, None, _blocked("invalid ledger", "the gap clarification request is missing")
    projection_path, projection_sha256, projection_error = _projection_for_gap(work, state)
    if projection_error:
        return None, None, projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        gap = gap_clarification.select_gap(projection, projection_sha256)
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return None, None, _blocked("invalid gap clarification", str(error))
    expected = {
        "attempt": 1,
        "contract": gap_clarification.CONTRACT,
        "projection_path": str(state["first_projection"]["path"]),
        "projection_sha256": projection_sha256,
        "interview_path": "gap-clarifications/attempt-000001/interview.jsonl",
        "result_path": "gap-clarifications/attempt-000001/clarification.json",
        "gap": gap,
    }
    saved = state.get("gap_clarification")
    if (
        any(entries[10].get(key) != value for key, value in expected.items())
        or not isinstance(saved, dict)
        or saved.get("attempt") != 1
        or saved.get("projection_sha256") != projection_sha256
        or saved.get("gap") != gap
    ):
        return None, None, _blocked("invalid ledger", "the gap clarification request changed")
    return projection_path, projection_sha256, None


def _consume_gap_clarification(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    projection_path, projection_sha256, request_error = _validate_gap_request(work, state, entries)
    if request_error:
        return request_error
    assert projection_path is not None and projection_sha256 is not None
    attempt_dir = work / "gap-clarifications" / "attempt-000001"
    try:
        result, journal_sha256, result_sha256 = gap_clarification.validate(
            attempt_dir,
            projection_path=projection_path,
            projection_sha256=projection_sha256,
            purpose=purpose,
        )
        journal_entries = gap_clarification._read_journal(attempt_dir / "interview.jsonl")
    except gap_clarification.ClarificationError as error:
        return _blocked("invalid gap clarification", str(error))
    question = result["question"]
    timestamp = datetime.now(timezone.utc).isoformat()
    twelfth = _ledger_entry(
        12,
        "model_gap_clarification_completed",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "attempt": 1,
            "interview_path": "gap-clarifications/attempt-000001/interview.jsonl",
            "interview_sha256": journal_sha256,
            "result_path": "gap-clarifications/attempt-000001/clarification.json",
            "result_sha256": result_sha256,
            "question_count": sum(item["event"] == "question_asked" for item in journal_entries),
            "answer_count": sum(item["event"] == "answer_recorded" for item in journal_entries),
            "rejected_answer_count": sum(
                item["event"] == "answer_recorded" and item["accepted"] is False
                for item in journal_entries
            ),
            "questioner": result["questioner"],
            "gap": result["gap"],
            "question": question,
        },
        str(entries[-1]["entry_sha256"]),
    )
    thirteenth = _ledger_entry(
        13,
        "operator_question_asked",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "question": question,
        },
        str(twelfth["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [twelfth, thirteenth])
    state["gap_clarification"].update({
        "interview_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "questioner": result["questioner"],
    })
    state.update({
        "status": "needs_operator",
        "phase": "awaiting_gap_answer",
        "waiting_for": question["id"],
        "question": question,
        "ledger_entries": 13,
        "ledger_tail_sha256": thirteenth["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _operator_result(state, work)


def _validate_gap_question(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if len(entries) < 13:
        return None, _blocked("invalid ledger", "the operator gap question is incomplete")
    projection_path, projection_sha256, request_error = _validate_gap_request(work, state, entries)
    if request_error:
        return None, request_error
    assert projection_path is not None and projection_sha256 is not None
    attempt_dir = work / "gap-clarifications" / "attempt-000001"
    try:
        result, journal_sha256, result_sha256 = gap_clarification.validate(
            attempt_dir,
            projection_path=projection_path,
            projection_sha256=projection_sha256,
            purpose=purpose,
        )
        journal_entries = gap_clarification._read_journal(attempt_dir / "interview.jsonl")
    except gap_clarification.ClarificationError as error:
        return None, _blocked("invalid gap clarification", str(error))
    expected_completed = {
        "attempt": 1,
        "interview_path": "gap-clarifications/attempt-000001/interview.jsonl",
        "interview_sha256": journal_sha256,
        "result_path": "gap-clarifications/attempt-000001/clarification.json",
        "result_sha256": result_sha256,
        "question_count": sum(item["event"] == "question_asked" for item in journal_entries),
        "answer_count": sum(item["event"] == "answer_recorded" for item in journal_entries),
        "rejected_answer_count": sum(
            item["event"] == "answer_recorded" and item["accepted"] is False
            for item in journal_entries
        ),
        "questioner": result["questioner"],
        "gap": result["gap"],
        "question": result["question"],
    }
    saved = state.get("gap_clarification")
    if (
        entries[11].get("event") != "model_gap_clarification_completed"
        or any(entries[11].get(key) != value for key, value in expected_completed.items())
        or entries[12].get("event") != "operator_question_asked"
        or entries[12].get("question") != result["question"]
        or not isinstance(saved, dict)
        or saved.get("interview_sha256") != journal_sha256
        or saved.get("result_sha256") != result_sha256
        or saved.get("questioner") != result["questioner"]
    ):
        return None, _blocked("invalid ledger", "the operator gap question changed")
    if state.get("phase") == "awaiting_gap_answer" and (
        state.get("status") != "needs_operator"
        or state.get("waiting_for") != result["question"]["id"]
        or state.get("question") != result["question"]
    ):
        return None, _blocked("invalid intake state", "the machinery is not waiting on its preserved gap question")
    if state.get("phase") not in {
        "awaiting_gap_answer",
        "gap_operator_source_recorded",
        "resolving_gap_answer",
        "verifying_gap_resolution",
        "gap_resolution_not_applied",
        "gap_resolution_applied",
        "gap_resolution_rejected",
    }:
        return None, _blocked("invalid intake state", "the preserved gap question has an unsupported phase")
    return result, None


def _accept_gap_answer(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    result: dict[str, object],
    answer: str,
) -> dict[str, object]:
    if not answer.strip():
        return _blocked("gap answer required", "answer the operator clarification with non-whitespace text")
    source_path = work / "sources" / "source-000004.txt"
    projection_path = work / "projections" / "source-000004-v1.txt"
    if source_path.exists() or projection_path.exists():
        return _blocked("unbound gap answer artifacts", "gap answer artifacts already exist outside the ledger")
    answer_bytes = answer.encode("utf-8")
    answer_sha256 = _digest_bytes(answer_bytes)
    question = result["question"]
    gap = result["gap"]
    source_record = _gap_answer_source_record(answer_sha256, question["id"], gap)
    projection_record = _gap_answer_projection_record(answer_sha256)
    source_path.write_bytes(answer_bytes)
    projection_path.write_bytes(answer_bytes)
    fourteenth = _ledger_entry(
        14,
        "source_projected",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "answers_question": question["id"],
            "answers_gap": source_record["answers_gap"],
            "source": source_record,
            "projection": projection_record,
            "lineage": {
                "question_ledger_sequence": 13,
                "original_source_id": "source-000003",
                "original_projection_id": state["first_projection"]["id"],
            },
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [fourteenth])
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "gap_operator_source_recorded",
        "waiting_for": None,
        "question": None,
        "gap_operator_source": source_record,
        "gap_operator_projection": projection_record,
        "ledger_entries": 14,
        "ledger_tail_sha256": fourteenth["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_source_ready_result(state, work)


def _validate_gap_source(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    result: dict[str, object],
) -> dict[str, object] | None:
    if len(entries) < 14 or entries[13].get("event") != "source_projected":
        return _blocked("invalid ledger", "the operator gap answer source is missing")
    source = state.get("gap_operator_source")
    projection = state.get("gap_operator_projection")
    if not isinstance(source, dict) or not isinstance(projection, dict):
        return _blocked("invalid intake state", "the operator gap source records are missing")
    try:
        source_bytes = (work / "sources" / "source-000004.txt").read_bytes()
        projection_bytes = (work / "projections" / "source-000004-v1.txt").read_bytes()
    except OSError:
        return _blocked("immutable gap answer unavailable", "the operator gap answer artifacts are missing")
    sha256 = _digest_bytes(source_bytes)
    expected_source = _gap_answer_source_record(sha256, result["question"]["id"], result["gap"])
    expected_projection = _gap_answer_projection_record(sha256)
    expected_lineage = {
        "question_ledger_sequence": 13,
        "original_source_id": "source-000003",
        "original_projection_id": state["first_projection"]["id"],
    }
    if (
        not source_bytes
        or not source_bytes.strip()
        or projection_bytes != source_bytes
        or source != expected_source
        or projection != expected_projection
        or entries[13].get("answers_question") != result["question"]["id"]
        or entries[13].get("answers_gap") != expected_source["answers_gap"]
        or entries[13].get("source") != expected_source
        or entries[13].get("projection") != expected_projection
        or entries[13].get("lineage") != expected_lineage
    ):
        return _blocked("immutable gap answer changed", "the operator gap answer no longer matches its ledger")
    if state.get("question") is not None:
        return _blocked("immutable gap answer changed", "the operator gap answer no longer matches its ledger")
    if state.get("phase") == "gap_operator_source_recorded" and state.get(
        "status"
    ) != "ready_for_projection_assessment":
        return _blocked("invalid intake state", "the recorded gap answer has an invalid status")
    return None


def _resolution_paths(attempt: int) -> dict[str, str]:
    suffix = f"attempt-{attempt:06d}"
    return {
        "attempt_dir": f"gap-resolutions/{suffix}",
        "interview_path": f"gap-resolutions/{suffix}/interview.jsonl",
        "clarification_path": f"gap-resolutions/{suffix}/clarification.json",
        "result_path": f"gap-resolutions/{suffix}/resolution.json",
        "candidate_path": f"gap-resolutions/{suffix}/verification-candidate.json",
        "verification_dir": f"gap-resolution-verifications/{suffix}",
        "verification_interview_path": f"gap-resolution-verifications/{suffix}/interview.jsonl",
        "verification_result_path": f"gap-resolution-verifications/{suffix}/verification.json",
    }


def _resolution_parent_record(
    state: dict[str, object], saved_resolution: dict[str, object]
) -> dict[str, object] | None:
    parent = saved_resolution.get("parent_projection")
    if isinstance(parent, dict):
        return parent
    first = state.get("first_projection")
    return first if isinstance(first, dict) else None


def _validated_projection_record(
    work: Path, record: dict[str, object] | None
) -> tuple[Path | None, str | None, dict[str, object] | None]:
    if not isinstance(record, dict):
        return None, None, _blocked(
            "gap resolution unavailable", "parent projection record is missing"
        )
    path_value = record.get("path")
    expected_sha256 = record.get("sha256")
    if not isinstance(path_value, str) or not isinstance(expected_sha256, str):
        return None, None, _blocked(
            "gap resolution unavailable", "parent projection identity is incomplete"
        )
    path = work / path_value
    try:
        content = path.read_bytes()
    except OSError:
        return None, None, _blocked(
            "gap resolution unavailable", f"parent projection is unavailable: {path_value}"
        )
    received_sha256 = _digest_bytes(content)
    if received_sha256 != expected_sha256:
        return None, None, _blocked(
            "immutable projection changed",
            f"parent projection {path_value} has sha256 {received_sha256}; expected {expected_sha256}",
        )
    return path, expected_sha256, None


def _assessed_binding_at_position(
    work: Path,
    state: dict[str, object],
    position: int,
    parent: dict[str, object],
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    bindings, binding_error = _gap_answer_assessment_bindings(work, state)
    if binding_error:
        return None, None, binding_error
    assert bindings is not None
    saved = state.get("gap_answer_assessment")
    assessments = saved.get("assessments") if isinstance(saved, dict) else None
    if not isinstance(assessments, list):
        return None, None, _blocked(
            "gap resolution unavailable", "the assessed answer outcomes are missing"
        )
    shape_error = _validate_gap_answer_assessment_shape(
        {"assessments": assessments}, bindings
    )
    if shape_error:
        return None, None, _blocked("gap resolution unavailable", shape_error)
    if not 1 <= position <= len(bindings):
        return None, None, _blocked(
            "gap resolution unavailable",
            f"assessment position {position} is outside 1..{len(bindings)}",
        )
    assessment = assessments[position - 1]
    binding = bindings[position - 1]
    assert isinstance(assessment, dict) and isinstance(binding, dict)
    gap = binding.get("gap")
    original_record = gap.get("record") if isinstance(gap, dict) else None
    binding_issue = (
        original_record.get("binding_issue")
        if isinstance(original_record, dict)
        else None
    )
    missing_endpoint_count = (
        sum(original_record.get(key) is None for key in ("from_id", "to_id"))
        if isinstance(original_record, dict)
        else 0
    )
    if (
        assessment.get("verdict") != "resolves_gap"
        or not isinstance(gap, dict)
        or gap.get("collection") != "relationships"
        or (
            not isinstance(binding_issue, dict)
            and missing_endpoint_count != 1
        )
    ):
        return None, None, _blocked(
            "gap resolution unavailable",
            f"assessment position {position} is not a resolving relationship gap with either an identity ambiguity or exactly one missing endpoint",
        )
    projection_path, projection_sha256, projection_error = (
        _validated_projection_record(work, parent)
    )
    if projection_error:
        return None, None, projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        relationships = projection["relationships"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None, None, _blocked(
            "gap resolution unavailable", "parent projection relationships are invalid"
        )
    matches = [
        item
        for item in relationships
        if isinstance(item, dict) and item.get("id") == gap.get("id")
    ]
    if len(matches) != 1:
        return None, None, _blocked(
            "gap resolution unavailable",
            f"gap {gap.get('id')} appears {len(matches)} times in the parent projection; expected 1",
        )
    received_record_sha256 = _digest_bytes(
        json.dumps(matches[0], sort_keys=True, separators=(",", ":")).encode()
    )
    if received_record_sha256 != gap.get("record_sha256") or matches[0] != original_record:
        return None, None, _blocked(
            "gap resolution unavailable",
            f"gap {gap.get('id')} changed in parent projection {parent.get('id')}; expected unchanged record {gap.get('record_sha256')}, received {received_record_sha256}",
        )
    try:
        gap_resolution._participant_contract(projection, matches[0])
    except gap_resolution.ResolutionError as contract_error:
        return None, None, _blocked(
            "gap resolution unavailable",
            f"gap {gap.get('id')} participant contract is invalid: {contract_error}",
        )
    active_binding = json.loads(json.dumps(binding))
    active_binding["gap"]["projection_sha256"] = projection_sha256
    active_binding["question"]["answers_gap"]["projection_sha256"] = (
        projection_sha256
    )
    return active_binding, assessment, None


def _next_resolving_assessed_binding(
    work: Path, state: dict[str, object], parent: dict[str, object]
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    used: set[int] = set()
    history = state.get("gap_resolution_history", [])
    if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
        return None, None, _blocked(
            "gap resolution unavailable", "gap resolution history must be a list of records"
        )
    candidates = list(history)
    current = state.get("gap_resolution")
    if isinstance(current, dict) and current.get("result_sha256"):
        candidates.append(current)
    for item in candidates:
        position = item.get("selected_assessment_position")
        if isinstance(position, int):
            used.add(position)
    saved = state.get("gap_answer_assessment")
    assessments = saved.get("assessments") if isinstance(saved, dict) else None
    if not isinstance(assessments, list):
        return None, None, _blocked(
            "gap resolution unavailable", "the assessed answer outcomes are missing"
        )
    for assessment in assessments:
        if not isinstance(assessment, dict) or assessment.get("verdict") != "resolves_gap":
            continue
        position = assessment.get("position")
        if isinstance(position, int) and position not in used:
            return _assessed_binding_at_position(work, state, position, parent)
    return None, None, _blocked(
        "gap resolution unavailable", "no unused assessed answer resolves an exact remaining gap"
    )


def _gap_resolution_inputs(
    work: Path,
    state: dict[str, object],
    saved_resolution: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    saved_resolution = saved_resolution or state.get("gap_resolution")
    if isinstance(saved_resolution, dict) and saved_resolution.get("mode") == "assessed_answer":
        attempt = saved_resolution.get("attempt")
        position = saved_resolution.get("selected_assessment_position")
        parent = _resolution_parent_record(state, saved_resolution)
        if not isinstance(attempt, int) or not isinstance(position, int) or not isinstance(parent, dict):
            return None, _blocked(
                "gap resolution unavailable", "the assessed answer resolution identity is incomplete"
            )
        paths = _resolution_paths(attempt)
        binding, assessment, selection_error = _assessed_binding_at_position(
            work, state, position, parent
        )
        if selection_error:
            return None, selection_error
        assert binding is not None and assessment is not None
        clarification_path = work / paths["clarification_path"]
        try:
            clarification_bytes = clarification_path.read_bytes()
            clarification = json.loads(clarification_bytes)
        except (OSError, json.JSONDecodeError):
            return None, _blocked(
                "gap resolution unavailable",
                f"clarification is unavailable or invalid: {paths['clarification_path']}",
            )
        original_binding, _, original_error = _assessed_binding_at_position(
            work, state, position, state["first_projection"]
        )
        if original_error:
            return None, original_error
        assert original_binding is not None
        expected_assessment_sha256 = _digest_bytes(
            json.dumps(assessment, sort_keys=True, separators=(",", ":")).encode()
        )
        source = binding["answer_source"]
        answer_projection = binding["answer_projection"]
        assert isinstance(source, dict) and isinstance(answer_projection, dict)
        expected = {
            "projection_sha256": parent.get("sha256"),
            "clarification_path": paths["clarification_path"],
            "clarification_sha256": _digest_bytes(clarification_bytes),
            "answer_source_path": str(source["path"]),
            "operator_answer_source_sha256": source["sha256"],
            "answer_projection_path": str(answer_projection["path"]),
            "operator_answer_projection_sha256": answer_projection["sha256"],
            "selected_assessment_position": position,
            "accepted_assessment_sha256": expected_assessment_sha256,
        }
        if any(saved_resolution.get(key) != value for key, value in expected.items()):
            return None, _blocked(
                "gap resolution unavailable",
                f"attempt {attempt} binding differs from its preserved request",
            )
        if (
            clarification.get("schema_version") != gap_resolution.CONTRACT
            or clarification.get("gap") != binding["gap"]
            or clarification.get("question") != binding["question"]
            or clarification.get("accepted_assessment") != assessment
            or (
                "assessment_gap" in clarification
                and clarification.get("assessment_gap") != original_binding["gap"]
            )
        ):
            return None, _blocked(
                "gap resolution unavailable",
                f"attempt {attempt} clarification no longer matches assessment position {position}",
            )
        projection_path, projection_sha256, projection_error = (
            _validated_projection_record(work, parent)
        )
        if projection_error:
            return None, projection_error
        values = {
            "projection_path": projection_path,
            "projection_sha256": projection_sha256,
            "clarification_path": clarification_path,
            "clarification_sha256": expected["clarification_sha256"],
            "answer_source_path": work / expected["answer_source_path"],
            "answer_source_sha256": expected["operator_answer_source_sha256"],
            "answer_projection_path": work / expected["answer_projection_path"],
            "answer_projection_sha256": expected["operator_answer_projection_sha256"],
        }
        return values, None
    projection_path, projection_sha256, projection_error = _projection_for_gap(
        work, state
    )
    if projection_error:
        return None, projection_error
    clarification = state.get("gap_clarification")
    source = state.get("gap_operator_source")
    projection = state.get("gap_operator_projection")
    if not all(isinstance(item, dict) for item in (clarification, source, projection)):
        return None, _blocked(
            "gap resolution unavailable", "the bound clarification answer is incomplete"
        )
    assert projection_path is not None and projection_sha256 is not None
    values = {
        "projection_path": projection_path,
        "projection_sha256": projection_sha256,
        "clarification_path": work
        / "gap-clarifications"
        / "attempt-000001"
        / "clarification.json",
        "clarification_sha256": clarification.get("result_sha256"),
        "answer_source_path": work / str(source.get("path")),
        "answer_source_sha256": source.get("sha256"),
        "answer_projection_path": work / str(projection.get("path")),
        "answer_projection_sha256": projection.get("sha256"),
    }
    if not all(
        isinstance(values[key], str)
        for key in (
            "clarification_sha256",
            "answer_source_sha256",
            "answer_projection_sha256",
        )
    ):
        return None, _blocked(
            "gap resolution unavailable", "the bound clarification hashes are incomplete"
        )
    return values, None


def _first_resolving_assessed_binding(
    work: Path, state: dict[str, object]
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    first = state.get("first_projection")
    if not isinstance(first, dict):
        return None, None, _blocked(
            "gap resolution unavailable", "the first projection record is missing"
        )
    shadow = dict(state)
    shadow["gap_resolution_history"] = []
    shadow.pop("gap_resolution", None)
    return _next_resolving_assessed_binding(work, shadow, first)


def _request_gap_resolution(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    prior_phase = state.get("phase")
    prior_projection = state.get("current_projection")
    mode = (
        "legacy_answer"
        if state.get("phase") == "gap_operator_source_recorded"
        else "assessed_answer"
    )
    current = state.get("gap_resolution")
    history = state.get("gap_resolution_history", [])
    if not isinstance(history, list):
        return _blocked(
            "gap resolution unavailable", "gap resolution history must be a list"
        )
    previous_attempts = [
        item.get("attempt")
        for item in history
        if isinstance(item, dict) and isinstance(item.get("attempt"), int)
    ]
    if isinstance(current, dict) and isinstance(current.get("attempt"), int):
        previous_attempts.append(current["attempt"])
    attempt = max(previous_attempts, default=0) + 1 if mode == "assessed_answer" else 1
    paths = _resolution_paths(attempt)
    attempt_dir = work / paths["attempt_dir"]
    verification_dir = work / paths["verification_dir"]
    if attempt_dir.exists() or verification_dir.exists():
        return _blocked(
            "unbound gap resolution", "gap resolution artifacts already exist"
        )
    selected_position: int | None = None
    accepted_assessment_sha256: str | None = None
    if mode == "assessed_answer":
        parent = state.get("current_projection", state.get("first_projection"))
        if not isinstance(parent, dict):
            return _blocked(
                "gap resolution unavailable", "the current projection record is missing"
            )
        binding, assessment, selection_error = _next_resolving_assessed_binding(
            work, state, parent
        )
        if selection_error:
            return selection_error
        assert binding is not None and assessment is not None
        assessment_gap = json.loads(json.dumps(binding["gap"]))
        assessment_gap["projection_sha256"] = assessment["gap"][
            "projection_sha256"
        ]
        clarification = {
            "schema_version": gap_resolution.CONTRACT,
            "gap": binding["gap"],
            "assessment_gap": assessment_gap,
            "question": binding["question"],
            "accepted_assessment": assessment,
        }
        clarification_bytes = (
            json.dumps(clarification, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        attempt_dir.mkdir(parents=True)
        clarification_path = attempt_dir / "clarification.json"
        clarification_path.write_bytes(clarification_bytes)
        source = binding["answer_source"]
        projection = binding["answer_projection"]
        assert isinstance(source, dict) and isinstance(projection, dict)
        selected_position = int(assessment["position"])
        accepted_assessment_sha256 = _digest_bytes(
            json.dumps(assessment, sort_keys=True, separators=(",", ":")).encode()
        )
        inputs = {
            "projection_path": work / str(parent["path"]),
            "projection_sha256": parent["sha256"],
            "clarification_path": clarification_path,
            "clarification_sha256": _digest_bytes(clarification_bytes),
            "answer_source_path": work / str(source["path"]),
            "answer_source_sha256": source["sha256"],
            "answer_projection_path": work / str(projection["path"]),
            "answer_projection_sha256": projection["sha256"],
        }
    else:
        inputs, error = _gap_resolution_inputs(work, state)
        if error:
            return error
        assert inputs is not None
    request_sequence = len(entries) + 1
    request = _ledger_entry(
        request_sequence,
        "model_gap_resolution_requested",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": attempt,
            "mode": mode,
            "contract": gap_resolution.CONTRACT,
            "projection_sha256": inputs["projection_sha256"],
            "clarification_path": str(
                Path(inputs["clarification_path"]).relative_to(work)
            ),
            "clarification_sha256": inputs["clarification_sha256"],
            "operator_answer_source_sha256": inputs["answer_source_sha256"],
            "operator_answer_projection_sha256": inputs[
                "answer_projection_sha256"
            ],
            "selected_assessment_position": selected_position,
            "accepted_assessment_sha256": accepted_assessment_sha256,
            "interview_path": paths["interview_path"],
            "result_path": paths["result_path"],
            "candidate_path": paths["candidate_path"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [request])
    archived: dict[str, object] | None = None
    if mode == "assessed_answer" and isinstance(current, dict):
        archived = json.loads(json.dumps(current))
        archived["terminal_phase"] = prior_phase
        archived["output_projection"] = prior_projection
    state.update({
        "status": "waiting_for_model",
        "phase": "resolving_gap_answer",
        "waiting_for": paths["interview_path"],
        "question": None,
        "gap_resolution": {
            "attempt": attempt,
            "mode": mode,
            "contract": gap_resolution.CONTRACT,
            "request_ledger_sequence": request_sequence,
            "projection_sha256": inputs["projection_sha256"],
            "clarification_path": str(
                Path(inputs["clarification_path"]).relative_to(work)
            ),
            "clarification_sha256": inputs["clarification_sha256"],
            "answer_source_path": str(
                Path(inputs["answer_source_path"]).relative_to(work)
            ),
            "operator_answer_source_sha256": inputs["answer_source_sha256"],
            "answer_projection_path": str(
                Path(inputs["answer_projection_path"]).relative_to(work)
            ),
            "operator_answer_projection_sha256": inputs[
                "answer_projection_sha256"
            ],
            "selected_assessment_position": selected_position,
            "accepted_assessment_sha256": accepted_assessment_sha256,
            "parent_projection": (
                parent if mode == "assessed_answer" else state["first_projection"]
            ),
        },
        "ledger_entries": request_sequence,
        "ledger_tail_sha256": request["entry_sha256"],
    })
    if archived is not None:
        state["gap_resolution_history"] = [*history, archived]
    _write_state(work / "intake-state.json", state)
    return _gap_resolution_model_result(state, work)


def _validated_gap_resolution(
    work: Path,
    state: dict[str, object],
    purpose: str,
    saved_resolution: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    saved_resolution = saved_resolution or state.get("gap_resolution")
    if not isinstance(saved_resolution, dict) or not isinstance(
        saved_resolution.get("attempt"), int
    ):
        return None, _blocked(
            "gap resolution unavailable", "gap resolution attempt is missing"
        )
    inputs, error = _gap_resolution_inputs(work, state, saved_resolution)
    if error:
        return None, error
    assert inputs is not None
    try:
        result, journal_sha256, result_sha256, candidate_sha256 = (
            gap_resolution.validate(
                work / _resolution_paths(saved_resolution["attempt"])["attempt_dir"],
                **inputs,
                purpose=purpose,
            )
        )
    except gap_resolution.ResolutionError as resolution_error:
        return None, _blocked("invalid gap resolution", str(resolution_error))
    return {
        "result": result,
        "journal_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "candidate_sha256": candidate_sha256,
    }, None


def _consume_gap_resolution(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    validated, error = _validated_gap_resolution(work, state, purpose)
    if error:
        return error
    assert validated is not None
    result = validated["result"]
    assert isinstance(result, dict)
    resolution = state["gap_resolution"]
    assert isinstance(resolution, dict)
    attempt = int(resolution["attempt"])
    paths = _resolution_paths(attempt)
    journal_entries = gap_resolution._read_journal(
        work / paths["interview_path"]
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    completed_sequence = len(entries) + 1
    completed_entry = _ledger_entry(
        completed_sequence,
        "model_gap_resolution_completed",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "attempt": attempt,
            "interview_sha256": validated["journal_sha256"],
            "result_sha256": validated["result_sha256"],
            "candidate_sha256": validated["candidate_sha256"],
            "question_count": sum(
                item["event"] == "question_asked" for item in journal_entries
            ),
            "answer_count": sum(
                item["event"] == "answer_recorded" for item in journal_entries
            ),
            "rejected_answer_count": sum(
                item["event"] == "answer_recorded" and item["accepted"] is False
                for item in journal_entries
            ),
            "result": result,
        },
        str(entries[-1]["entry_sha256"]),
    )
    state["gap_resolution"].update({
        "interview_sha256": validated["journal_sha256"],
        "result_sha256": validated["result_sha256"],
        "candidate_sha256": validated["candidate_sha256"],
        "gap_id": result["gap_id"],
        "verdict": result["verdict"],
        "reason": result["reason"],
    })
    if result["verdict"] == "does_not_resolve_gap":
        outcome_entry = _ledger_entry(
            completed_sequence + 1,
            "gap_resolution_not_applied",
            {
                "recorded_at": timestamp,
                "intake_id": state["intake_id"],
                "gap_id": result["gap_id"],
                "reason": result["reason"],
                "preserved_projection": resolution["parent_projection"],
            },
            str(completed_entry["entry_sha256"]),
        )
        _append_ledger(work / "ledger.jsonl", [completed_entry, outcome_entry])
        state.update({
            "status": "ready_for_projection_assessment",
            "phase": "gap_resolution_not_applied",
            "waiting_for": None,
            "current_projection": resolution["parent_projection"],
            "ledger_entries": completed_sequence + 1,
            "ledger_tail_sha256": outcome_entry["entry_sha256"],
        })
        _write_state(work / "intake-state.json", state)
        return _gap_resolution_ready_result(state, work)
    verification_request = _ledger_entry(
        completed_sequence + 1,
        "model_gap_resolution_verification_requested",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "attempt": attempt,
            "contract": gap_resolution_verification.CONTRACT,
            "candidate_sha256": validated["candidate_sha256"],
            "resolution_sha256": validated["result_sha256"],
            "interview_path": paths["verification_interview_path"],
            "result_path": paths["verification_result_path"],
        },
        str(completed_entry["entry_sha256"]),
    )
    _append_ledger(
        work / "ledger.jsonl", [completed_entry, verification_request]
    )
    state.update({
        "status": "waiting_for_model",
        "phase": "verifying_gap_resolution",
        "waiting_for": paths["verification_interview_path"],
        "ledger_entries": completed_sequence + 1,
        "ledger_tail_sha256": verification_request["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_resolution_model_result(state, work, verification=True)


def _validated_gap_resolution_verification(
    work: Path,
    state: dict[str, object],
    purpose: str,
    saved_resolution: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    resolution = saved_resolution or state.get("gap_resolution")
    inputs, input_error = _gap_resolution_inputs(work, state, resolution if isinstance(resolution, dict) else None)
    if input_error:
        return None, input_error
    if not isinstance(resolution, dict) or inputs is None:
        return None, _blocked(
            "gap resolution verification unavailable",
            "the proposed resolution inputs are incomplete",
        )
    attempt = resolution.get("attempt")
    if not isinstance(attempt, int):
        return None, _blocked(
            "gap resolution verification unavailable", "gap resolution attempt is missing"
        )
    paths = _resolution_paths(attempt)
    try:
        result, journal_sha256, result_sha256 = (
            gap_resolution_verification.validate(
                work / paths["verification_dir"],
                candidate_path=work / paths["candidate_path"],
                candidate_sha256=str(resolution["candidate_sha256"]),
                resolution_path=work / paths["result_path"],
                resolution_sha256=str(resolution["result_sha256"]),
                clarification_path=Path(inputs["clarification_path"]),
                clarification_sha256=str(inputs["clarification_sha256"]),
                answer_path=Path(inputs["answer_source_path"]),
                answer_sha256=str(inputs["answer_source_sha256"]),
                purpose=purpose,
            )
        )
    except gap_resolution_verification.ResolutionVerificationError as verification_error:
        return None, _blocked(
            "invalid gap resolution verification", str(verification_error)
        )
    return {
        "result": result,
        "journal_sha256": journal_sha256,
        "result_sha256": result_sha256,
    }, None


def _build_resolved_projection(
    work: Path,
    state: dict[str, object],
    verification: dict[str, object],
    saved_resolution: dict[str, object] | None = None,
) -> tuple[bytes, dict[str, object]]:
    resolution = saved_resolution or state["gap_resolution"]
    assert isinstance(resolution, dict)
    parent = _resolution_parent_record(state, resolution)
    assert isinstance(parent, dict)
    attempt = int(resolution["attempt"])
    original = json.loads((work / str(parent["path"])).read_text(encoding="utf-8"))
    candidate = json.loads(
        (work / _resolution_paths(attempt)["candidate_path"]).read_text(encoding="utf-8")
    )
    proposed = dict(candidate["relationships"][0])
    gap_id = str(proposed["resolution_of"])
    proposed["id"] = gap_id
    proposed["resolution_audit"] = {
        "parent_projection_sha256": parent["sha256"],
        "operator_answer_source_sha256": resolution[
            "operator_answer_source_sha256"
        ],
        "accepted_assessment_sha256": resolution.get(
            "accepted_assessment_sha256"
        ),
        "resolution_result_sha256": resolution["result_sha256"],
        "independent_verification_sha256": verification["result_sha256"],
    }
    replaced = False
    relationships: list[object] = []
    for relationship in original["relationships"]:
        if relationship.get("id") == gap_id:
            relationships.append(proposed)
            replaced = True
        else:
            relationships.append(relationship)
    if not replaced:
        raise ValueError(
            f"resolved relationship gap {gap_id} is absent from parent projection {parent.get('id')}"
        )
    original["relationships"] = relationships
    existing_ids = {item["id"] for item in original["elements"]}
    original["elements"].extend(
        item for item in candidate["elements"] if item["id"] not in existing_ids
    )
    original["projection_lineage"] = {
        "parent_projection_id": parent["id"],
        "parent_projection_sha256": parent["sha256"],
        "resolved_gap_id": gap_id,
        "accepted_assessment_position": resolution.get(
            "selected_assessment_position"
        ),
    }
    content = json.dumps(original, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    gap_count = sum(item["status"] == "gap" for item in original["elements"])
    gap_count += sum(
        item["status"] == "gap" for item in original["relationships"]
    )
    gap_count += sum(
        item["status"] == "gap" for item in original.get("scan_regions", [])
    )
    parent_version = parent.get("version")
    if not isinstance(parent_version, int) or parent_version < 1:
        raise ValueError("parent projection version must be a positive integer")
    version = parent_version + 1
    record = {
        "id": f"projection-source-000003-v{version}",
        "source_id": "source-000003",
        "version": version,
        "parent_projection_id": parent["id"],
        "path": f"projections/source-000003-v{version}.json",
        "sha256": _digest_bytes(content),
        "element_count": len(original["elements"]),
        "relationship_count": len(original["relationships"]),
        "gap_count": gap_count,
        "coverage": "unassessed",
    }
    return content, record


def _consume_gap_resolution_verification(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    verification, error = _validated_gap_resolution_verification(
        work, state, purpose
    )
    if error:
        return error
    assert verification is not None
    result = verification["result"]
    assert isinstance(result, dict)
    resolution = state["gap_resolution"]
    assert isinstance(resolution, dict)
    attempt = int(resolution["attempt"])
    paths = _resolution_paths(attempt)
    journal_entries = gap_resolution_verification._read_journal(
        work / paths["verification_interview_path"]
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    verification_sequence = len(entries) + 1
    verification_entry = _ledger_entry(
        verification_sequence,
        "model_gap_resolution_verification_completed",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "attempt": attempt,
            "interview_sha256": verification["journal_sha256"],
            "result_sha256": verification["result_sha256"],
            "question_count": sum(
                item["event"] == "question_asked" for item in journal_entries
            ),
            "answer_count": sum(
                item["event"] == "answer_recorded" for item in journal_entries
            ),
            "rejected_answer_count": sum(
                item["event"] == "answer_recorded" and item["accepted"] is False
                for item in journal_entries
            ),
            "result": result,
        },
        str(entries[-1]["entry_sha256"]),
    )
    state["gap_resolution"].update({
        "verification_interview_sha256": verification["journal_sha256"],
        "verification_result_sha256": verification["result_sha256"],
        "verification_verdict": result["verdict"],
        "verification_reason": result["reason"],
    })
    if result["verdict"] == "supported":
        try:
            projection_bytes, projection_record = _build_resolved_projection(
                work, state, verification
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as build_error:
            return _blocked("gap resolution projection invalid", str(build_error))
        projection_path = work / str(projection_record["path"])
        if projection_path.exists():
            return _blocked(
                "unbound projection version",
                f"projection path already exists: {projection_record['path']}",
            )
        projection_path.write_bytes(projection_bytes)
        outcome_entry = _ledger_entry(
            verification_sequence + 1,
            "projection_version_created",
            {
                "recorded_at": timestamp,
                "intake_id": state["intake_id"],
                "resolution_of_gap": state["gap_resolution"]["gap_id"],
                "verification_result_sha256": verification["result_sha256"],
                "projection": projection_record,
            },
            str(verification_entry["entry_sha256"]),
        )
        phase = "gap_resolution_applied"
        current_projection = projection_record
    else:
        outcome_entry = _ledger_entry(
            verification_sequence + 1,
            "gap_resolution_not_applied",
            {
                "recorded_at": timestamp,
                "intake_id": state["intake_id"],
                "gap_id": state["gap_resolution"]["gap_id"],
                "reason": result["reason"],
                "verification_verdict": result["verdict"],
                "preserved_projection": resolution["parent_projection"],
            },
            str(verification_entry["entry_sha256"]),
        )
        phase = "gap_resolution_rejected"
        current_projection = resolution["parent_projection"]
    _append_ledger(work / "ledger.jsonl", [verification_entry, outcome_entry])
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": phase,
        "waiting_for": None,
        "current_projection": current_projection,
        "ledger_entries": verification_sequence + 1,
        "ledger_tail_sha256": outcome_entry["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_resolution_ready_result(state, work)


def run_gap_resolution(
    work: Path,
    *,
    input_fn: object | None = None,
    output_fn: object | None = None,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(
            encoding="utf-8"
        )
        purpose = (work / "sources" / "source-000002.txt").read_text(
            encoding="utf-8"
        )
        state = json.loads(
            (work / "intake-state.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as context_error:
        return _blocked("gap resolution context unavailable", str(context_error))
    current = drive(work, opening, purpose)
    if current.get("status") != "waiting_for_model" or current.get(
        "stopped"
    ) != "resolving_gap_answer":
        return _blocked("gap resolution unavailable", json.dumps(current, sort_keys=True))
    inputs, error = _gap_resolution_inputs(work, state)
    if error:
        return error
    assert inputs is not None
    resolution = state.get("gap_resolution")
    if not isinstance(resolution, dict) or not isinstance(resolution.get("attempt"), int):
        return _blocked("gap resolution unavailable", "gap resolution attempt is missing")
    paths = _resolution_paths(resolution["attempt"])
    try:
        gap_resolution.run(
            work / paths["attempt_dir"],
            **inputs,
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except gap_resolution.ResolutionError as resolution_error:
        return _blocked("gap resolution failed", str(resolution_error))
    return drive(work, opening, purpose)


def run_gap_resolution_verification(
    work: Path,
    *,
    input_fn: object | None = None,
    output_fn: object | None = None,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(
            encoding="utf-8"
        )
        purpose = (work / "sources" / "source-000002.txt").read_text(
            encoding="utf-8"
        )
        state = json.loads(
            (work / "intake-state.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as context_error:
        return _blocked(
            "gap resolution verification context unavailable", str(context_error)
        )
    current = drive(work, opening, purpose)
    if current.get("status") != "waiting_for_model" or current.get(
        "stopped"
    ) != "verifying_gap_resolution":
        return _blocked(
            "gap resolution verification unavailable",
            json.dumps(current, sort_keys=True),
        )
    resolution = state["gap_resolution"]
    if not isinstance(resolution, dict) or not isinstance(resolution.get("attempt"), int):
        return _blocked(
            "gap resolution verification unavailable", "gap resolution attempt is missing"
        )
    paths = _resolution_paths(resolution["attempt"])
    inputs, input_error = _gap_resolution_inputs(work, state)
    if input_error:
        return input_error
    assert inputs is not None
    try:
        gap_resolution_verification.run(
            work / paths["verification_dir"],
            candidate_path=work / paths["candidate_path"],
            candidate_sha256=str(resolution["candidate_sha256"]),
            resolution_path=work / paths["result_path"],
            resolution_sha256=str(resolution["result_sha256"]),
            clarification_path=Path(inputs["clarification_path"]),
            clarification_sha256=str(inputs["clarification_sha256"]),
            answer_path=Path(inputs["answer_source_path"]),
            answer_sha256=str(inputs["answer_source_sha256"]),
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except gap_resolution_verification.ResolutionVerificationError as verification_error:
        return _blocked("gap resolution verification failed", str(verification_error))
    return drive(work, opening, purpose)


def _validate_gap_resolution_terminal(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    saved_resolution: dict[str, object] | None = None,
    *,
    archived: bool = False,
) -> dict[str, object] | None:
    saved = saved_resolution or state.get("gap_resolution")
    if not isinstance(saved, dict) or not isinstance(saved.get("attempt"), int):
        return _blocked(
            "invalid gap resolution ledger", "gap resolution attempt is missing"
        )
    attempt = saved["attempt"]
    paths = _resolution_paths(attempt)
    resolution, error = _validated_gap_resolution(
        work, state, purpose, saved
    )
    if error:
        return error
    assert resolution is not None
    result = resolution["result"]
    request_sequence = saved.get("request_ledger_sequence")
    request_index = request_sequence - 1 if isinstance(request_sequence, int) else -1
    if (
        not isinstance(result, dict)
        or not isinstance(request_sequence, int)
        or request_index < 0
        or len(entries) < request_sequence + 2
        or entries[request_index].get("event") != "model_gap_resolution_requested"
        or entries[request_index].get("attempt") != attempt
        or entries[request_index].get("mode") != saved.get("mode")
        or entries[request_index].get("clarification_path")
        != saved.get("clarification_path")
        or entries[request_index].get("clarification_sha256")
        != saved.get("clarification_sha256")
        or entries[request_index].get("selected_assessment_position")
        != saved.get("selected_assessment_position")
        or entries[request_index].get("accepted_assessment_sha256")
        != saved.get("accepted_assessment_sha256")
        or entries[request_index].get("contract") != saved.get("contract")
        or entries[request_index].get("projection_sha256")
        != saved.get("projection_sha256")
        or entries[request_index].get("operator_answer_source_sha256")
        != saved.get("operator_answer_source_sha256")
        or entries[request_index].get("operator_answer_projection_sha256")
        != saved.get("operator_answer_projection_sha256")
        or entries[request_index].get("interview_path")
        != paths["interview_path"]
        or entries[request_index].get("result_path")
        != paths["result_path"]
        or entries[request_index].get("candidate_path")
        != paths["candidate_path"]
        or entries[request_index + 1].get("event")
        != "model_gap_resolution_completed"
        or entries[request_index + 1].get("attempt") != attempt
        or entries[request_index + 1].get("interview_sha256")
        != resolution["journal_sha256"]
        or entries[request_index + 1].get("result_sha256")
        != resolution["result_sha256"]
        or entries[request_index + 1].get("candidate_sha256")
        != resolution["candidate_sha256"]
        or saved.get("result_sha256") != resolution["result_sha256"]
        or saved.get("candidate_sha256") != resolution["candidate_sha256"]
        or saved.get("verdict") != result.get("verdict")
    ):
        return _blocked(
            "invalid gap resolution ledger",
            f"attempt {attempt} no longer matches its request and result records",
        )
    terminal_phase = saved.get("terminal_phase") if archived else state.get("phase")
    output_projection = (
        saved.get("output_projection")
        if archived
        else state.get("current_projection")
    )
    expected_total = request_sequence + 2
    if result["verdict"] == "does_not_resolve_gap":
        if (
            len(entries) < expected_total
            or entries[request_index + 2].get("event")
            != "gap_resolution_not_applied"
            or terminal_phase != "gap_resolution_not_applied"
            or output_projection != saved.get("parent_projection")
            or (not archived and len(entries) != expected_total)
        ):
            return _blocked(
                "invalid gap resolution ledger",
                f"attempt {attempt} non-resolving outcome changed",
            )
        return None
    verification, verification_error = _validated_gap_resolution_verification(
        work, state, purpose, saved
    )
    if verification_error:
        return verification_error
    assert verification is not None
    verification_result = verification["result"]
    if (
        not isinstance(verification_result, dict)
        or len(entries) < request_sequence + 4
        or entries[request_index + 2].get("event")
        != "model_gap_resolution_verification_requested"
        or entries[request_index + 2].get("attempt") != attempt
        or entries[request_index + 2].get("interview_path")
        != paths["verification_interview_path"]
        or entries[request_index + 2].get("result_path")
        != paths["verification_result_path"]
        or entries[request_index + 3].get("event")
        != "model_gap_resolution_verification_completed"
        or entries[request_index + 3].get("attempt") != attempt
        or entries[request_index + 3].get("interview_sha256")
        != verification["journal_sha256"]
        or entries[request_index + 3].get("result_sha256")
        != verification["result_sha256"]
        or saved.get("verification_result_sha256")
        != verification["result_sha256"]
        or saved.get("verification_verdict")
        != verification_result.get("verdict")
    ):
        return _blocked(
            "invalid gap resolution ledger",
            f"attempt {attempt} independent verification changed",
        )
    expected_total = request_sequence + 4
    if verification_result["verdict"] == "supported":
        if entries[request_index + 4].get("event") != "projection_version_created":
            return _blocked(
                "invalid gap resolution ledger",
                f"attempt {attempt} projection outcome is not recorded",
            )
        try:
            expected_bytes, expected_record = _build_resolved_projection(
                work, state, verification, saved
            )
            actual_bytes = (work / str(expected_record["path"])).read_bytes()
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as build_error:
            return _blocked(
                "invalid resolved projection", f"attempt {attempt}: {build_error}"
            )
        if (
            actual_bytes != expected_bytes
            or entries[request_index + 4].get("projection") != expected_record
            or terminal_phase != "gap_resolution_applied"
            or output_projection != expected_record
            or (not archived and len(entries) != expected_total)
        ):
            return _blocked(
                "immutable projection changed",
                f"attempt {attempt} output projection no longer matches its verified resolution",
            )
    elif (
        entries[request_index + 4].get("event") != "gap_resolution_not_applied"
        or terminal_phase != "gap_resolution_rejected"
        or output_projection != saved.get("parent_projection")
        or (not archived and len(entries) != expected_total)
    ):
        return _blocked(
            "invalid gap resolution ledger",
            f"attempt {attempt} rejected outcome changed",
        )
    return None


def _validate_gap_resolution_history(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object] | None:
    history = state.get("gap_resolution_history", [])
    if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
        return _blocked(
            "invalid gap resolution ledger", "gap resolution history must be a list of records"
        )
    expected_attempt = 1
    previous_output: dict[str, object] | None = None
    for saved in history:
        if saved.get("attempt") != expected_attempt:
            return _blocked(
                "invalid gap resolution ledger",
                f"history attempt received {saved.get('attempt')}; expected {expected_attempt}",
            )
        if previous_output is not None and saved.get("parent_projection") != previous_output:
            return _blocked(
                "invalid gap resolution ledger",
                f"attempt {expected_attempt} parent does not match attempt {expected_attempt - 1} output",
            )
        terminal_error = _validate_gap_resolution_terminal(
            work, state, entries, purpose, saved, archived=True
        )
        if terminal_error:
            return terminal_error
        output = saved.get("output_projection")
        previous_output = output if isinstance(output, dict) else None
        expected_attempt += 1
    current = state.get("gap_resolution")
    if isinstance(current, dict) and current.get("mode") == "assessed_answer":
        if current.get("attempt") != expected_attempt:
            return _blocked(
                "invalid gap resolution ledger",
                f"active attempt received {current.get('attempt')}; expected {expected_attempt}",
            )
        if history and current.get("parent_projection") != previous_output:
            return _blocked(
                "invalid gap resolution ledger",
                f"active attempt {expected_attempt} parent does not match prior output",
            )
    return None


def run_gap_clarification(
    work: Path,
    *,
    input_fn: object | None = None,
    output_fn: object | None = None,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(encoding="utf-8")
        purpose = (work / "sources" / "source-000002.txt").read_text(encoding="utf-8")
        state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return _blocked("gap clarification context unavailable", str(error))
    current = drive(work, opening, purpose)
    stopped = current.get("stopped")
    if current.get("status") != "waiting_for_model" or stopped not in {
        "formulating_gap_question", "formulating_gap_question_round",
        "formulating_follow_up_gap_question_round",
    }:
        return _blocked("gap clarification unavailable", json.dumps(current, sort_keys=True))
    try:
        if stopped == "formulating_follow_up_gap_question_round":
            gaps, projection_path, projection_sha256, binding_error = (
                _follow_up_gap_bindings(work, state)
            )
            if binding_error:
                return binding_error
            assert gaps is not None and projection_path is not None and projection_sha256 is not None
            gap_clarification.run_round(
                work / "gap-question-rounds" / "round-000002",
                projection_path=projection_path,
                projection_sha256=projection_sha256,
                purpose=purpose,
                gaps=gaps,
                round_number=2,
                input_fn=input_fn,
                output_fn=output_fn,
            )
        else:
            projection_path, projection_sha256, projection_error = _projection_for_gap(
                work, state
            )
            if projection_error:
                return projection_error
            assert projection_path is not None and projection_sha256 is not None
        if stopped == "formulating_gap_question_round":
            gap_clarification.run_round(
                work / "gap-question-rounds" / "round-000001",
                projection_path=projection_path,
                projection_sha256=projection_sha256,
                purpose=purpose,
                input_fn=input_fn,
                output_fn=output_fn,
            )
        elif stopped == "formulating_gap_question":
            gap_clarification.run(
                work / "gap-clarifications" / "attempt-000001",
                projection_path=projection_path,
                projection_sha256=projection_sha256,
                purpose=purpose,
                input_fn=input_fn,
                output_fn=output_fn,
            )
    except gap_clarification.ClarificationError as error:
        return _blocked("gap clarification failed", str(error))
    return drive(work, opening, purpose)


def run_gap_answer_assessment(
    work: Path,
    *,
    input_fn: object | None = None,
    output_fn: object | None = None,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(
            encoding="utf-8"
        )
        purpose = (work / "sources" / "source-000002.txt").read_text(
            encoding="utf-8"
        )
        state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return _blocked("gap answer assessment context unavailable", str(error))
    current = drive(work, opening, purpose)
    stopped = current.get("stopped")
    if (
        current.get("status") != "waiting_for_model"
        or stopped not in {
            "assessing_gap_answers",
            "assessing_prepared_question_round_answers",
        }
    ):
        return _blocked(
            "gap answer assessment unavailable", json.dumps(current, sort_keys=True)
        )
    if stopped == "assessing_prepared_question_round_answers":
        bindings, binding_error = _prepared_question_round_assessment_bindings(
            work, state
        )
        prepared = state.get("follow_up_gap_question_round")
        round_number = prepared.get("round") if isinstance(prepared, dict) else None
    else:
        bindings, binding_error = _gap_answer_assessment_bindings(work, state)
        round_number = 1
    if binding_error:
        return binding_error
    if bindings is None or not isinstance(round_number, int):
        return _blocked(
            "gap answer assessment unavailable",
            "the answer bindings or their round identity are missing",
        )
    paths = _answer_assessment_paths(round_number)
    try:
        gap_answer_assessment.run(
            work / paths["directory"],
            bindings=bindings,
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("gap answer assessment failed", str(error))
    return drive(work, opening, purpose)


def _resume(
    work: Path,
    opening_bytes: bytes,
    purpose: str | None,
    source: Path | None,
    project_source: bool,
    clarify_gap: bool,
    gap_answer: str | None,
    resolve_gap: bool,
    assess_gap_answers: bool,
    conduct_question_round: bool,
) -> dict[str, object]:
    state, entries, error = _load_bound(work, opening_bytes)
    if error:
        return error
    assert state is not None
    phase = state.get("phase")
    if conduct_question_round and (
        source is not None
        or project_source
        or clarify_gap
        or gap_answer is not None
        or resolve_gap
        or assess_gap_answers
    ):
        return _blocked(
            "prepared question round invocation invalid",
            "start or resume the prepared question round without another intake action",
        )
    gap_input_phases = {
        "first_projection_recorded", "awaiting_gap_answer",
        "formulating_gap_question_round", "awaiting_gap_answers",
        "gap_question_round_answered",
        "gap_answer_assessment_recorded", "gap_resolution_applied",
        "gap_resolution_rejected", "formulating_follow_up_gap_question_round",
        "follow_up_gap_question_round_recorded",
    }
    if clarify_gap and phase not in gap_input_phases:
        return _blocked(
            "gap clarification unavailable",
            "gap clarification input is only accepted after the first projection or at its operator question",
        )
    if gap_answer is not None and phase not in {
        *gap_input_phases,
        "awaiting_prepared_question_round_answers",
        "prepared_question_round_answered",
    }:
        return _blocked(
            "gap clarification unavailable",
            "gap clarification input is only accepted after the first projection or at its operator question",
        )
    if conduct_question_round and phase not in {
        "follow_up_gap_question_round_recorded",
        "awaiting_prepared_question_round_answers",
        "prepared_question_round_answered",
    }:
        return _blocked(
            "prepared question round unavailable",
            "conduct a question round only after that round has been prepared",
        )
    if resolve_gap and phase not in {
        "gap_operator_source_recorded", "gap_answer_assessment_recorded",
        "gap_resolution_applied", "gap_resolution_rejected",
    }:
        return _blocked(
            "gap resolution unavailable",
            "resolve a preserved answer only after its source and required assessment are recorded",
        )
    if assess_gap_answers and phase in {
        "gap_answer_assessment_recorded",
        "prepared_question_round_assessment_recorded",
    }:
        return _blocked(
            "gap answer assessment already recorded",
            "this completed question round already has its immutable assessment",
        )
    if assess_gap_answers and phase not in {
        "gap_question_round_answered",
        "prepared_question_round_answered",
    }:
        return _blocked(
            "gap answer assessment unavailable",
            "complete the current question round before assessing its preserved answers",
        )
    if phase == "awaiting_intake_purpose":
        if (
            len(entries) != 2
            or state.get("status") != "needs_operator"
            or state.get("waiting_for") != OPENING_QUESTION["id"]
            or state.get("question") != OPENING_QUESTION
        ):
            return _blocked("invalid intake state", "the opening stage does not match its ledger")
        if purpose is None:
            if source is not None or project_source:
                return _blocked("purpose required", "answer the intake-purpose question before supplying a source")
            return _operator_result(state, work)
        if source is not None or project_source:
            return _blocked("source not requested", "preserve and assess the purpose before supplying a source")
        return _accept_purpose(work, state, entries, purpose)

    purpose_bytes, purpose_error = _validate_purpose_stage(work, state, entries, purpose)
    if purpose_error:
        return purpose_error
    assert purpose_bytes is not None
    if phase == "assessing_intake_purpose":
        if (
            len(entries) != 4
            or state.get("status") != "waiting_for_model"
            or state.get("waiting_for") != "purpose-interview/interview.jsonl"
            or state.get("question") is not None
        ):
            return _blocked("invalid intake state", "the assessment stage does not match its ledger")
        if source is not None or project_source:
            return _blocked("purpose assessment pending", "finish the purpose assessment before supplying a source")
        result_path = work / "purpose-interview" / "assessment.json"
        if not result_path.exists():
            return _model_result(state, work)
        return _consume_assessment(work, state, entries, purpose_bytes)

    supported_ledger_length = len(entries) in {6, 7, 8, 10, 11, 13, 14, 15, 17, 19}
    assessed_resolution_phase = (
        phase in {
            "resolving_gap_answer",
            "verifying_gap_resolution",
            "gap_resolution_applied",
            "gap_resolution_rejected",
        }
        and isinstance(state.get("gap_resolution"), dict)
        and state["gap_resolution"].get("mode") == "assessed_answer"
    )
    if phase in {
        "awaiting_gap_answers",
        "gap_question_round_answered",
        "assessing_gap_answers",
        "gap_answer_assessment_recorded",
        "formulating_follow_up_gap_question_round",
        "follow_up_gap_question_round_recorded",
        "awaiting_prepared_question_round_answers",
        "prepared_question_round_answered",
        "assessing_prepared_question_round_answers",
        "prepared_question_round_assessment_recorded",
    } or assessed_resolution_phase:
        supported_ledger_length = len(entries) >= 14
    if phase not in {
        "awaiting_first_source", "clarifying_intake_purpose", "first_source_frozen",
        "interviewing_first_projection", "first_projection_recorded",
        "formulating_gap_question", "awaiting_gap_answer", "gap_operator_source_recorded",
        "formulating_gap_question_round", "awaiting_gap_answers",
        "gap_question_round_answered",
        "assessing_gap_answers", "gap_answer_assessment_recorded",
        "resolving_gap_answer", "verifying_gap_resolution",
        "gap_resolution_not_applied", "gap_resolution_applied",
        "gap_resolution_rejected",
        "formulating_follow_up_gap_question_round",
        "follow_up_gap_question_round_recorded",
        "awaiting_prepared_question_round_answers",
        "prepared_question_round_answered",
        "assessing_prepared_question_round_answers",
        "prepared_question_round_assessment_recorded",
    } or not supported_ledger_length:
        return _blocked("invalid intake state", "the saved purpose stage is unsupported")
    result_path = work / "purpose-interview" / "assessment.json"
    try:
        result_bytes = result_path.read_bytes()
    except OSError:
        return _blocked("assessment result unavailable", str(result_path))
    result_sha256 = _digest_bytes(result_bytes)
    if result_sha256 != state.get("assessment_result_sha256"):
        return _blocked("assessment result changed", "the preserved model result has changed")
    if entries[4].get("event") != "model_assessment_completed":
        return _blocked("invalid ledger", "the completed purpose assessment is missing")
    assessment, assessment_error = _read_assessment(result_path, purpose_bytes.decode("utf-8"))
    if assessment_error:
        return _blocked("invalid purpose assessment", assessment_error)
    try:
        assembled, interview_sha256, _ = purpose_interview.validate(
            work / "purpose-interview",
            purpose=purpose_bytes.decode("utf-8"),
        )
        interview_entries = purpose_interview.journal._read_journal(
            work / "purpose-interview" / "interview.jsonl"
        )
    except purpose_interview.InterviewError as error:
        return _blocked("invalid purpose interview", str(error))
    if (
        assessment != assembled
        or state.get("assessment_interview_sha256") != interview_sha256
        or entries[4].get("assessment") != "intake_purpose_sufficiency"
        or entries[4].get("interview_path") != "purpose-interview/interview.jsonl"
        or entries[4].get("interview_sha256") != interview_sha256
        or entries[4].get("result_path") != "purpose-interview/assessment.json"
        or entries[4].get("result_sha256") != result_sha256
        or entries[4].get("question_count") != sum(
            entry["event"] == "question_asked" for entry in interview_entries
        )
        or entries[4].get("answer_count") != sum(
            entry["event"] == "answer_recorded" for entry in interview_entries
        )
        or entries[4].get("rejected_answer_count") != sum(
            entry["event"] == "answer_recorded" and entry["accepted"] is False
            for entry in interview_entries
        )
        or entries[4].get("result") != assessment
    ):
        return _blocked("invalid ledger", "the completed assessment does not match its preserved result")
    expected_question = (
        FIRST_SOURCE_QUESTION
        if assessment["sufficient"] == "yes"
        else {"id": "intake-purpose-clarification", "asks": assessment["clarifying_question"]}
    )
    if entries[5].get("event") != "operator_question_asked" or entries[5].get("question") != expected_question:
        return _blocked("invalid ledger", "the current operator question is missing or changed")
    if assessment["sufficient"] == "no":
        if source is not None or project_source:
            return _blocked("purpose clarification required", "answer the current clarification before supplying a source")
        if (
            len(entries) != 6
            or state.get("status") != "needs_operator"
            or phase != "clarifying_intake_purpose"
            or state.get("waiting_for") != expected_question["id"]
            or state.get("question") != expected_question
        ):
            return _blocked("invalid intake state", "the current clarification does not follow from the assessment")
        return _operator_result(state, work)

    if phase == "clarifying_intake_purpose":
        return _blocked(
            "invalid intake state",
            "a sufficient purpose assessment cannot lead to a clarification stage",
        )

    if phase == "awaiting_first_source":
        if (
            len(entries) != 6
            or state.get("status") != "needs_operator"
            or state.get("waiting_for") != FIRST_SOURCE_QUESTION["id"]
            or state.get("question") != FIRST_SOURCE_QUESTION
        ):
            return _blocked("invalid intake state", "the first-source request does not follow from the assessment")
        if source is None:
            if project_source:
                return _blocked("source required", "freeze the first source before requesting its projection")
            return _operator_result(state, work)
        if project_source:
            return _blocked(
                "source not yet frozen",
                "freeze the supplied source before requesting its projection",
            )
        return _acquire_first_source(work, state, entries, source)

    frozen_error = _validate_frozen_first_source(work, state, entries, source)
    if frozen_error:
        return frozen_error
    if phase == "first_source_frozen":
        if (
            len(entries) != 7
            or state.get("status") != "ready_for_projection"
            or state.get("waiting_for") is not None
            or state.get("question") is not None
        ):
            return _blocked("invalid intake state", "the frozen first-source stage is invalid")
        if project_source:
            return _request_first_projection(work, state, entries)
        return _source_ready_result(state, work)

    request_error = _validate_projection_request(work, state, entries)
    if request_error:
        return request_error
    if phase == "interviewing_first_projection":
        if (
            len(entries) != 8
            or state.get("status") != "waiting_for_model"
            or state.get("waiting_for") != "projection-interviews/attempt-000001/interview.jsonl"
        ):
            return _blocked("invalid intake state", "the first projection interview has an invalid state")
        projection_path = work / "projection-interviews" / "attempt-000001" / "projection.json"
        if not projection_path.exists():
            return _projection_waiting_result(state, work)
        return _consume_first_projection(work, state, entries, purpose_bytes.decode("utf-8"))

    later_phase = phase in {
        "formulating_gap_question", "awaiting_gap_answer", "gap_operator_source_recorded",
        "formulating_gap_question_round", "awaiting_gap_answers",
        "gap_question_round_answered",
        "assessing_gap_answers", "gap_answer_assessment_recorded",
        "resolving_gap_answer", "verifying_gap_resolution",
        "gap_resolution_not_applied", "gap_resolution_applied",
        "gap_resolution_rejected",
        "formulating_follow_up_gap_question_round",
        "follow_up_gap_question_round_recorded",
        "awaiting_prepared_question_round_answers",
        "prepared_question_round_answered",
        "assessing_prepared_question_round_answers",
        "prepared_question_round_assessment_recorded",
    }
    recorded_error = _validate_recorded_projection(
        work,
        state,
        entries,
        purpose_bytes.decode("utf-8"),
        allow_later_phase=later_phase,
    )
    if recorded_error:
        return recorded_error
    if phase == "first_projection_recorded":
        if gap_answer is not None:
            return _blocked("gap answer not requested", "start a gap question round before answering it")
        if clarify_gap:
            return _request_gap_question_round(work, state, entries)
        return _projection_ready_result(state, work)
    if phase == "formulating_gap_question_round":
        result_path = (
            work
            / "gap-question-rounds"
            / "round-000001"
            / "clarification-round.json"
        )
        if not result_path.exists():
            return _gap_question_round_model_result(state, work)
        return _consume_gap_question_round(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
    if phase in {
        "awaiting_gap_answers",
        "gap_question_round_answered",
        "assessing_gap_answers",
        "gap_answer_assessment_recorded",
    }:
        round_error = _validate_gap_question_round(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
            allow_later_phase=phase in {
                "assessing_gap_answers", "gap_answer_assessment_recorded"
            },
        )
        if round_error:
            return round_error
        if phase == "gap_question_round_answered":
            if gap_answer is not None:
                return _blocked(
                    "gap answer not requested", "the question round is already answered"
                )
            if assess_gap_answers:
                return _request_gap_answer_assessment(work, state, entries)
            return _gap_question_round_answered_result(state, work)
        if phase == "assessing_gap_answers":
            result_path = (
                work
                / "gap-answer-assessments"
                / "round-000001"
                / "assessment.json"
            )
            if not result_path.exists():
                return _gap_answer_assessment_model_result(state, work)
            return _consume_gap_answer_assessment(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
        if phase == "gap_answer_assessment_recorded":
            assessment_error = _validate_gap_answer_assessment(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
            if assessment_error:
                return assessment_error
            if clarify_gap:
                return _request_follow_up_gap_question_round(work, state, entries)
            if resolve_gap:
                return _request_gap_resolution(work, state, entries)
            return _gap_answer_assessment_ready_result(state, work)
        if gap_answer is None:
            return _gap_question_round_operator_result(state, work)
        return _accept_gap_question_round_answer(
            work, state, entries, gap_answer
        )
    resolution_state = state.get("gap_resolution")
    assessed_resolution = (
        isinstance(resolution_state, dict)
        and resolution_state.get("mode") == "assessed_answer"
        and phase in {
            "resolving_gap_answer",
            "verifying_gap_resolution",
            "gap_resolution_applied",
            "gap_resolution_rejected",
        }
    )
    follow_up_phase = phase in {
        "formulating_follow_up_gap_question_round",
        "follow_up_gap_question_round_recorded",
        "awaiting_prepared_question_round_answers",
        "prepared_question_round_answered",
        "assessing_prepared_question_round_answers",
        "prepared_question_round_assessment_recorded",
    }
    if follow_up_phase:
        round_error = _validate_gap_question_round(
            work, state, entries, purpose_bytes.decode("utf-8"), allow_later_phase=True
        )
        if round_error:
            return round_error
        assessment_error = _validate_gap_answer_assessment(
            work, state, entries, purpose_bytes.decode("utf-8"), allow_later_phase=True
        )
        if assessment_error:
            return assessment_error
        history_error = _validate_gap_resolution_history(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
        if history_error:
            return history_error
        if phase == "formulating_follow_up_gap_question_round":
            result_path = (
                work / "gap-question-rounds" / "round-000002" / "clarification-round.json"
            )
            if not result_path.exists():
                return _follow_up_gap_question_round_model_result(state, work)
            return _consume_follow_up_gap_question_round(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
        if phase == "follow_up_gap_question_round_recorded":
            follow_up_error = _validate_follow_up_gap_question_round(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
            if follow_up_error:
                return follow_up_error
            if gap_answer is not None:
                return _blocked(
                    "gap answer not requested",
                    "start the prepared question round before answering it",
                )
            if conduct_question_round:
                return _start_prepared_question_round_interview(
                    work, state, entries, purpose_bytes.decode("utf-8")
                )
            return _follow_up_gap_question_round_ready_result(state, work)
        follow_up_error = _validate_follow_up_gap_question_round(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
            allow_interview=True,
        )
        if follow_up_error:
            return follow_up_error
        interview_error = _validate_prepared_question_round_interview(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
            allow_later_phase=phase in {
                "assessing_prepared_question_round_answers",
                "prepared_question_round_assessment_recorded",
            },
        )
        if interview_error:
            return interview_error
        if phase == "awaiting_prepared_question_round_answers":
            if gap_answer is not None:
                return _accept_prepared_question_round_answer(
                    work,
                    state,
                    entries,
                    purpose_bytes.decode("utf-8"),
                    gap_answer,
                )
            return _prepared_question_round_operator_result(state, work)
        if phase == "prepared_question_round_answered":
            if gap_answer is not None:
                return _blocked(
                    "gap answer not requested", "the question round is already answered"
                )
            if assess_gap_answers:
                return _request_prepared_question_round_assessment(
                    work, state, entries
                )
            return _prepared_question_round_answered_result(state, work)
        if phase == "assessing_prepared_question_round_answers":
            _, record, request_error = (
                _validate_prepared_question_round_assessment_request(
                    work, state, entries
                )
            )
            if request_error:
                return request_error
            assert record is not None and isinstance(record.get("round"), int)
            paths = _answer_assessment_paths(record["round"])
            if not (work / paths["result_path"]).exists():
                return _prepared_question_round_assessment_model_result(state, work)
            return _consume_prepared_question_round_assessment(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
        assessment_error = _validate_prepared_question_round_assessment(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
        if assessment_error:
            return assessment_error
        return _prepared_question_round_assessment_ready_result(state, work)
    if assessed_resolution:
        round_error = _validate_gap_question_round(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
            allow_later_phase=True,
        )
        if round_error:
            return round_error
        assessment_error = _validate_gap_answer_assessment(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
            allow_later_phase=True,
        )
        if assessment_error:
            return assessment_error
        history_error = _validate_gap_resolution_history(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
        if history_error:
            return history_error
        active_attempt = resolution_state.get("attempt")
        if not isinstance(active_attempt, int):
            return _blocked(
                "invalid gap resolution ledger", "active gap resolution attempt is missing"
            )
        active_paths = _resolution_paths(active_attempt)
        if phase == "resolving_gap_answer":
            result_path = work / active_paths["result_path"]
            if not result_path.exists():
                return _gap_resolution_model_result(state, work)
            return _consume_gap_resolution(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
        if phase == "verifying_gap_resolution":
            result_path = work / active_paths["verification_result_path"]
            if not result_path.exists():
                return _gap_resolution_model_result(state, work, verification=True)
            return _consume_gap_resolution_verification(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
        terminal_error = _validate_gap_resolution_terminal(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
        if terminal_error:
            return terminal_error
        if clarify_gap:
            return _request_follow_up_gap_question_round(work, state, entries)
        if resolve_gap:
            return _request_gap_resolution(work, state, entries)
        return _gap_resolution_ready_result(state, work)
    if phase == "formulating_gap_question":
        result_path = work / "gap-clarifications" / "attempt-000001" / "clarification.json"
        if not result_path.exists():
            return _gap_clarification_model_result(state, work)
        return _consume_gap_clarification(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
    clarification_result, clarification_error = _validate_gap_question(
        work, state, entries, purpose_bytes.decode("utf-8")
    )
    if clarification_error:
        return clarification_error
    assert clarification_result is not None
    if phase == "awaiting_gap_answer":
        if gap_answer is None:
            return _operator_result(state, work)
        return _accept_gap_answer(
            work, state, entries, clarification_result, gap_answer
        )
    source_error = _validate_gap_source(
        work, state, entries, clarification_result
    )
    if source_error:
        return source_error
    if phase == "gap_operator_source_recorded":
        if resolve_gap:
            return _request_gap_resolution(work, state, entries)
        return _gap_source_ready_result(state, work)
    if phase == "resolving_gap_answer":
        result_path = work / "gap-resolutions" / "attempt-000001" / "resolution.json"
        if not result_path.exists():
            return _gap_resolution_model_result(state, work)
        return _consume_gap_resolution(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
    if phase == "verifying_gap_resolution":
        result_path = (
            work
            / "gap-resolution-verifications"
            / "attempt-000001"
            / "verification.json"
        )
        if not result_path.exists():
            return _gap_resolution_model_result(state, work, verification=True)
        return _consume_gap_resolution_verification(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
    terminal_error = _validate_gap_resolution_terminal(
        work, state, entries, purpose_bytes.decode("utf-8")
    )
    if terminal_error:
        return terminal_error
    return _gap_resolution_ready_result(state, work)


def drive(
    work: Path,
    opening: str,
    purpose: str | None = None,
    source: Path | None = None,
    project_source: bool = False,
    clarify_gap: bool = False,
    gap_answer: str | None = None,
    resolve_gap: bool = False,
    assess_gap_answers: bool = False,
    conduct_question_round: bool = False,
) -> dict[str, object]:
    opening_bytes = opening.encode("utf-8")
    if not opening.strip():
        return _blocked("opening required", "preserve the operator's opening words before starting")
    state_path = work / "intake-state.json"
    if state_path.exists():
        return _resume(
            work,
            opening_bytes,
            purpose,
            source,
            project_source,
            clarify_gap,
            gap_answer,
            resolve_gap,
            assess_gap_answers,
            conduct_question_round,
        )
    if (
        purpose is not None
        or source is not None
        or project_source
        or clarify_gap
        or gap_answer is not None
        or resolve_gap
        or assess_gap_answers
        or conduct_question_round
    ):
        return _blocked("intake not started", "start the intake before supplying its purpose or source")
    if work.exists() and not work.is_dir():
        return _blocked("invalid work path", "the work path exists and is not a directory")
    if work.exists() and any(work.iterdir()):
        return _blocked("unbound existing state", "use a fresh work directory")

    work.mkdir(parents=True, exist_ok=True)
    source_dir = work / "sources"
    projection_dir = work / "projections"
    source_dir.mkdir()
    projection_dir.mkdir()
    source_path = source_dir / "source-000001.txt"
    projection_path = projection_dir / "projection-000001.txt"
    source_path.write_bytes(opening_bytes)
    projection_path.write_bytes(opening_bytes)

    intake_id = f"intake-{uuid.uuid4().hex}"
    timestamp = datetime.now(timezone.utc).isoformat()
    opening_sha256 = _digest_bytes(opening_bytes)
    first = _ledger_entry(
        1,
        "source_projected",
        {
            "recorded_at": timestamp,
            "intake_id": intake_id,
            "trigger": "new_intake",
            "source": _source_record(1, opening_sha256),
            "projection": _projection_record(1, opening_sha256),
        },
        None,
    )
    second = _ledger_entry(
        2,
        "operator_question_asked",
        {
            "recorded_at": timestamp,
            "intake_id": intake_id,
            "question": OPENING_QUESTION,
        },
        str(first["entry_sha256"]),
    )
    ledger_path = work / "ledger.jsonl"
    ledger_path.write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in (first, second)),
        encoding="utf-8",
    )
    state: dict[str, object] = {
        "contract": CONTRACT,
        "intake_id": intake_id,
        "status": "needs_operator",
        "phase": "awaiting_intake_purpose",
        "waiting_for": OPENING_QUESTION["id"],
        "question": OPENING_QUESTION,
        "opening_sha256": opening_sha256,
        "ledger_entries": 2,
        "ledger_tail_sha256": second["entry_sha256"],
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _operator_result(state, work)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--opening", help="the operator's exact opening statement")
    parser.add_argument("--purpose", help="the operator's exact answer to the purpose question")
    parser.add_argument("--source", type=Path, help="the first local file supplied by the operator")
    parser.add_argument(
        "--project-source",
        action="store_true",
        help="request the first AI-readable projection attempt for the frozen source",
    )
    parser.add_argument(
        "--run-projection-interview",
        action="store_true",
        help="answer the code-controlled projection questions for the frozen image",
    )
    parser.add_argument(
        "--run-projection-verification",
        action="store_true",
        help="independently verify proposed visual relationships for the frozen image",
    )
    parser.add_argument(
        "--run-relationship-correction",
        action="store_true",
        help="propose bounded corrections for independently rejected relationships",
    )
    parser.add_argument(
        "--run-correction-verification",
        action="store_true",
        help="independently verify proposed relationship corrections",
    )
    parser.add_argument(
        "--clarify-gap",
        action="store_true",
        help="prepare one operator question for every current projection gap",
    )
    parser.add_argument(
        "--gap-answer",
        help="the operator's exact answer to the current gap clarification",
    )
    parser.add_argument(
        "--conduct-question-round",
        action="store_true",
        help="present the next question from a prepared operator round",
    )
    parser.add_argument(
        "--run-gap-clarification",
        action="store_true",
        help="formulate the code-bound operator question round for current gaps",
    )
    parser.add_argument(
        "--assess-gap-answers",
        action="store_true",
        help="request assessment of every preserved question-round answer",
    )
    parser.add_argument(
        "--run-gap-answer-assessment",
        action="store_true",
        help="run the code-controlled assessment of all preserved round answers",
    )
    parser.add_argument(
        "--resolve-gap",
        action="store_true",
        help="request assessment of the preserved answer against its exact gap",
    )
    parser.add_argument(
        "--run-gap-resolution",
        action="store_true",
        help="run the code-controlled assessment of one preserved gap answer",
    )
    parser.add_argument(
        "--run-gap-resolution-verification",
        action="store_true",
        help="independently verify one proposed gap resolution",
    )
    parser.add_argument(
        "--run-purpose-interview",
        action="store_true",
        help="answer the code-controlled purpose-assessment questions",
    )
    args = parser.parse_args()
    interview_flags = sum((
        args.run_projection_interview,
        args.run_projection_verification,
        args.run_relationship_correction,
        args.run_correction_verification,
        args.run_gap_clarification,
        args.run_gap_answer_assessment,
        args.run_gap_resolution,
        args.run_gap_resolution_verification,
        args.run_purpose_interview,
    ))
    if args.conduct_question_round and interview_flags:
        result = _blocked(
            "interview invocation invalid",
            "conduct the prepared operator round separately from model interviews",
        )
    elif interview_flags and (args.resolve_gap or args.assess_gap_answers):
        result = _blocked(
            "interview invocation invalid",
            "request or run one gap-resolution stage at a time",
        )
    elif interview_flags > 1:
        result = _blocked("interview invocation invalid", "run exactly one interview at a time")
    elif args.run_purpose_interview:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.gap_answer))
            or args.project_source or args.clarify_gap or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run the purpose interview with only --work and --run-purpose-interview",
            )
        else:
            result = run_purpose_interview(args.work)
    elif args.run_projection_interview:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.gap_answer))
            or args.project_source or args.clarify_gap or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run the projection interview with only --work and --run-projection-interview",
            )
        else:
            result = run_first_projection_interview(args.work)
    elif args.run_projection_verification:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.gap_answer))
            or args.project_source or args.clarify_gap or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run relationship verification with only --work and --run-projection-verification",
            )
        else:
            result = run_first_projection_verification(args.work)
    elif args.run_relationship_correction:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.gap_answer))
            or args.project_source or args.clarify_gap or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run relationship correction with only --work and --run-relationship-correction",
            )
        else:
            result = run_relationship_correction(args.work)
    elif args.run_correction_verification:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.gap_answer))
            or args.project_source or args.clarify_gap or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run correction verification with only --work and --run-correction-verification",
            )
        else:
            result = run_relationship_correction_verification(args.work)
    elif args.run_gap_clarification:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.gap_answer))
            or args.project_source or args.clarify_gap or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run gap clarification with only --work and --run-gap-clarification",
            )
        else:
            result = run_gap_clarification(args.work)
    elif args.run_gap_answer_assessment:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.gap_answer))
            or args.project_source or args.clarify_gap or args.resolve_gap
            or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run gap answer assessment with only --work and --run-gap-answer-assessment",
            )
        else:
            result = run_gap_answer_assessment(args.work)
    elif args.run_gap_resolution:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.gap_answer))
            or args.project_source or args.clarify_gap or args.resolve_gap
            or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run gap resolution with only --work and --run-gap-resolution",
            )
        else:
            result = run_gap_resolution(args.work)
    elif args.run_gap_resolution_verification:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.gap_answer))
            or args.project_source or args.clarify_gap or args.resolve_gap
            or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run gap resolution verification with only --work and --run-gap-resolution-verification",
            )
        else:
            result = run_gap_resolution_verification(args.work)
    elif args.opening is None:
        result = _blocked("opening required", "preserve the operator's opening words before starting")
    else:
        result = drive(
            args.work,
            args.opening,
            args.purpose,
            args.source,
            args.project_source,
            args.clarify_gap,
            args.gap_answer,
            args.resolve_gap,
            args.assess_gap_answers,
            args.conduct_question_round,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return {
        "ready_for_projection": 0,
        "ready_for_projection_assessment": 0,
        "ready_for_operator_interview": 0,
        "waiting_for_model": 2,
        "blocked": 3,
        "needs_operator": 4,
    }[str(result["status"])]


if __name__ == "__main__":
    raise SystemExit(main())
