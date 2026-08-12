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


def _projection_waiting_result(state: dict[str, object], work: Path) -> dict[str, object]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--work",
        str(work.resolve()),
        "--run-projection-interview",
    ]
    return {
        "status": "waiting_for_model",
        "stopped": "interviewing_first_projection",
        "intake_id": state["intake_id"],
        "work": [{
            "stage": "project_first_source",
            "instruction": (
                "Inspect the attached frozen source, run the command, and answer only the "
                "typed question currently displayed. Code controls allowed choices and assembly."
            ),
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
        "ledger_entries": 8,
        "ledger_tail_sha256": eighth["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _projection_waiting_result(state, work)


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
    projection_path = work / "projections" / "source-000003-v1.json"
    if projection_path.exists():
        return _blocked("unbound projection artifact", "projection version 1 already exists outside the ledger")
    projection_bytes = (attempt_dir / "projection.json").read_bytes()
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
) -> dict[str, object] | None:
    if len(entries) != 10 or entries[8].get("event") != "model_projection_interview_completed":
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
    ):
        return _blocked("invalid ledger", "the completed projection interview does not match its artifacts")
    if (
        state.get("phase") != "first_projection_recorded"
        or state.get("status") != "ready_for_projection_assessment"
        or state.get("waiting_for") is not None
        or entries[9].get("event") != "projection_version_created"
    ):
        return _blocked("invalid ledger", "the projection interview has an invalid terminal state")
    projection_path = work / "projections" / "source-000003-v1.json"
    try:
        projection_bytes = projection_path.read_bytes()
    except OSError:
        return _blocked("immutable projection unavailable", str(projection_path))
    canonical = (work / "projection-interviews" / "attempt-000001" / "projection.json").read_bytes()
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


def _resume(
    work: Path,
    opening_bytes: bytes,
    purpose: str | None,
    source: Path | None,
    project_source: bool,
) -> dict[str, object]:
    state, entries, error = _load_bound(work, opening_bytes)
    if error:
        return error
    assert state is not None
    phase = state.get("phase")
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

    if phase not in {
        "awaiting_first_source", "clarifying_intake_purpose", "first_source_frozen",
        "interviewing_first_projection", "first_projection_recorded",
    } or len(entries) not in {6, 7, 8, 10}:
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

    recorded_error = _validate_recorded_projection(
        work, state, entries, purpose_bytes.decode("utf-8")
    )
    if recorded_error:
        return recorded_error
    return _projection_ready_result(state, work)


def drive(
    work: Path,
    opening: str,
    purpose: str | None = None,
    source: Path | None = None,
    project_source: bool = False,
) -> dict[str, object]:
    opening_bytes = opening.encode("utf-8")
    if not opening.strip():
        return _blocked("opening required", "preserve the operator's opening words before starting")
    state_path = work / "intake-state.json"
    if state_path.exists():
        return _resume(work, opening_bytes, purpose, source, project_source)
    if purpose is not None or source is not None or project_source:
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
        "--run-purpose-interview",
        action="store_true",
        help="answer the code-controlled purpose-assessment questions",
    )
    args = parser.parse_args()
    if args.run_projection_interview and args.run_purpose_interview:
        result = _blocked("interview invocation invalid", "run exactly one interview at a time")
    elif args.run_purpose_interview:
        if any(value is not None for value in (args.opening, args.purpose, args.source)) or args.project_source:
            result = _blocked(
                "interview invocation invalid",
                "run the purpose interview with only --work and --run-purpose-interview",
            )
        else:
            result = run_purpose_interview(args.work)
    elif args.run_projection_interview:
        if any(value is not None for value in (args.opening, args.purpose, args.source)) or args.project_source:
            result = _blocked(
                "interview invocation invalid",
                "run the projection interview with only --work and --run-projection-interview",
            )
        else:
            result = run_first_projection_interview(args.work)
    elif args.opening is None:
        result = _blocked("opening required", "preserve the operator's opening words before starting")
    else:
        result = drive(args.work, args.opening, args.purpose, args.source, args.project_source)
    print(json.dumps(result, indent=2, sort_keys=True))
    return {
        "ready_for_projection": 0,
        "ready_for_projection_assessment": 0,
        "waiting_for_model": 2,
        "blocked": 3,
        "needs_operator": 4,
    }[str(result["status"])]


if __name__ == "__main__":
    raise SystemExit(main())
