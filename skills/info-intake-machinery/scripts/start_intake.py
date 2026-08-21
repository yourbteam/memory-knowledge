#!/usr/bin/env python3
"""Create or resume the first interview stages of an information intake."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
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
URL_ADAPTER_VERSION = 1
URL_MAX_BYTES = 20 * 1024 * 1024
URL_MAX_REDIRECTS = 5
URL_TIMEOUT_SECONDS = 20
URL_REDIRECT_STATUSES = {301, 302, 303, 307, 308}

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
_ADDITIONAL_SOURCE_GAP_ASSESSMENT_SPEC = importlib.util.spec_from_file_location(
    "info_intake_additional_source_gap_assessment",
    Path(__file__).resolve().with_name("additional_source_gap_assessment.py"),
)
if (
    _ADDITIONAL_SOURCE_GAP_ASSESSMENT_SPEC is None
    or _ADDITIONAL_SOURCE_GAP_ASSESSMENT_SPEC.loader is None
):
    raise RuntimeError("additional source gap assessment engine is unavailable")
additional_source_gap_assessment = importlib.util.module_from_spec(
    _ADDITIONAL_SOURCE_GAP_ASSESSMENT_SPEC
)
_ADDITIONAL_SOURCE_GAP_ASSESSMENT_SPEC.loader.exec_module(
    additional_source_gap_assessment
)
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
_PDF_PROJECTION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_pdf_projection",
    Path(__file__).resolve().with_name("pdf_projection.py"),
)
if _PDF_PROJECTION_SPEC is None or _PDF_PROJECTION_SPEC.loader is None:
    raise RuntimeError("PDF projection adapter is unavailable")
pdf_projection = importlib.util.module_from_spec(_PDF_PROJECTION_SPEC)
_PDF_PROJECTION_SPEC.loader.exec_module(pdf_projection)
_SPREADSHEET_PROJECTION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_spreadsheet_projection",
    Path(__file__).resolve().with_name("spreadsheet_projection.py"),
)
if (
    _SPREADSHEET_PROJECTION_SPEC is None
    or _SPREADSHEET_PROJECTION_SPEC.loader is None
):
    raise RuntimeError("spreadsheet projection adapter is unavailable")
spreadsheet_projection = importlib.util.module_from_spec(
    _SPREADSHEET_PROJECTION_SPEC
)
_SPREADSHEET_PROJECTION_SPEC.loader.exec_module(spreadsheet_projection)
_SOURCE_COLLECTION_DECISION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_source_collection_decision",
    Path(__file__).resolve().with_name("source_collection_decision.py"),
)
if (
    _SOURCE_COLLECTION_DECISION_SPEC is None
    or _SOURCE_COLLECTION_DECISION_SPEC.loader is None
):
    raise RuntimeError("source collection decision probe is unavailable")
source_collection_decision = importlib.util.module_from_spec(
    _SOURCE_COLLECTION_DECISION_SPEC
)
_SOURCE_COLLECTION_DECISION_SPEC.loader.exec_module(source_collection_decision)
_SOURCE_COLLECTION_RESERVATION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_source_collection_reservation",
    Path(__file__).resolve().with_name("source_collection_reservation.py"),
)
if (
    _SOURCE_COLLECTION_RESERVATION_SPEC is None
    or _SOURCE_COLLECTION_RESERVATION_SPEC.loader is None
):
    raise RuntimeError("source collection reservation probe is unavailable")
source_collection_reservation = importlib.util.module_from_spec(
    _SOURCE_COLLECTION_RESERVATION_SPEC
)
_SOURCE_COLLECTION_RESERVATION_SPEC.loader.exec_module(
    source_collection_reservation
)
_SOURCE_COLLECTION_CLOSURE_SPEC = importlib.util.spec_from_file_location(
    "info_intake_source_collection_closure",
    Path(__file__).resolve().with_name("source_collection_closure.py"),
)
if (
    _SOURCE_COLLECTION_CLOSURE_SPEC is None
    or _SOURCE_COLLECTION_CLOSURE_SPEC.loader is None
):
    raise RuntimeError("source collection closure probe is unavailable")
source_collection_closure = importlib.util.module_from_spec(
    _SOURCE_COLLECTION_CLOSURE_SPEC
)
_SOURCE_COLLECTION_CLOSURE_SPEC.loader.exec_module(source_collection_closure)
_SOURCE_QUALIFICATION_BINDING_SPEC = importlib.util.spec_from_file_location(
    "info_intake_source_qualification_binding",
    Path(__file__).resolve().with_name("source_qualification_binding.py"),
)
if (
    _SOURCE_QUALIFICATION_BINDING_SPEC is None
    or _SOURCE_QUALIFICATION_BINDING_SPEC.loader is None
):
    raise RuntimeError("source qualification binding probe is unavailable")
source_qualification_binding = importlib.util.module_from_spec(
    _SOURCE_QUALIFICATION_BINDING_SPEC
)
_SOURCE_QUALIFICATION_BINDING_SPEC.loader.exec_module(
    source_qualification_binding
)
_SOURCE_PROJECTION_QUALIFICATION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_source_projection_qualification",
    Path(__file__).resolve().with_name("source_projection_qualification.py"),
)
if (
    _SOURCE_PROJECTION_QUALIFICATION_SPEC is None
    or _SOURCE_PROJECTION_QUALIFICATION_SPEC.loader is None
):
    raise RuntimeError("source projection qualification probe is unavailable")
source_projection_qualification = importlib.util.module_from_spec(
    _SOURCE_PROJECTION_QUALIFICATION_SPEC
)
_SOURCE_PROJECTION_QUALIFICATION_SPEC.loader.exec_module(
    source_projection_qualification
)
_SOURCE_QUALIFICATION_RECONCILIATION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_source_qualification_reconciliation",
    Path(__file__).resolve().with_name("source_qualification_reconciliation.py"),
)
if (
    _SOURCE_QUALIFICATION_RECONCILIATION_SPEC is None
    or _SOURCE_QUALIFICATION_RECONCILIATION_SPEC.loader is None
):
    raise RuntimeError("source qualification reconciliation probe is unavailable")
source_qualification_reconciliation = importlib.util.module_from_spec(
    _SOURCE_QUALIFICATION_RECONCILIATION_SPEC
)
_SOURCE_QUALIFICATION_RECONCILIATION_SPEC.loader.exec_module(
    source_qualification_reconciliation
)
_QUALIFICATION_TERMINAL_DISPOSITION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_qualification_terminal_disposition",
    Path(__file__).resolve().with_name("qualification_terminal_disposition.py"),
)
if (
    _QUALIFICATION_TERMINAL_DISPOSITION_SPEC is None
    or _QUALIFICATION_TERMINAL_DISPOSITION_SPEC.loader is None
):
    raise RuntimeError("qualification terminal disposition probe is unavailable")
qualification_terminal_disposition = importlib.util.module_from_spec(
    _QUALIFICATION_TERMINAL_DISPOSITION_SPEC
)
_QUALIFICATION_TERMINAL_DISPOSITION_SPEC.loader.exec_module(
    qualification_terminal_disposition
)
_CLARIFICATION_OBLIGATION_BINDING_SPEC = importlib.util.spec_from_file_location(
    "info_intake_clarification_obligation_binding",
    Path(__file__).resolve().with_name("clarification_obligation_binding.py"),
)
if (
    _CLARIFICATION_OBLIGATION_BINDING_SPEC is None
    or _CLARIFICATION_OBLIGATION_BINDING_SPEC.loader is None
):
    raise RuntimeError("clarification obligation binding probe is unavailable")
clarification_obligation_binding = importlib.util.module_from_spec(
    _CLARIFICATION_OBLIGATION_BINDING_SPEC
)
_CLARIFICATION_OBLIGATION_BINDING_SPEC.loader.exec_module(
    clarification_obligation_binding
)
_QUALIFICATION_ADMISSION_PUBLICATION_SPEC = importlib.util.spec_from_file_location(
    "info_intake_qualification_admission_publication",
    Path(__file__).resolve().with_name("qualification_admission_publication.py"),
)
if (
    _QUALIFICATION_ADMISSION_PUBLICATION_SPEC is None
    or _QUALIFICATION_ADMISSION_PUBLICATION_SPEC.loader is None
):
    raise RuntimeError("qualification admission publication probe is unavailable")
qualification_admission_publication = importlib.util.module_from_spec(
    _QUALIFICATION_ADMISSION_PUBLICATION_SPEC
)
_QUALIFICATION_ADMISSION_PUBLICATION_SPEC.loader.exec_module(
    qualification_admission_publication
)
_QUALIFICATION_QUESTION_ROUND_SPEC = importlib.util.spec_from_file_location(
    "info_intake_qualification_question_round",
    Path(__file__).resolve().with_name("qualification_question_round.py"),
)
if (
    _QUALIFICATION_QUESTION_ROUND_SPEC is None
    or _QUALIFICATION_QUESTION_ROUND_SPEC.loader is None
):
    raise RuntimeError("qualification question-round controller is unavailable")
qualification_question_round = importlib.util.module_from_spec(
    _QUALIFICATION_QUESTION_ROUND_SPEC
)
_QUALIFICATION_QUESTION_ROUND_SPEC.loader.exec_module(
    qualification_question_round
)

SOURCE_COLLECTION_DECISION_QUESTION = {
    "id": "source-collection-decision",
    "asks": "Do you want to add another independent source or finish source collection?",
    "answer_type": "enum",
    "allowed_values": list(source_collection_decision.ALLOWED_ACTIONS),
}
SOURCE_COLLECTION_KIND_QUESTION = {
    "id": "source-collection-kind",
    "asks": "How will you provide the next independent source?",
    "answer_type": "enum",
    "allowed_values": ["local_file", "url"],
}


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


def _projection_model_attachment(
    work: Path,
    *,
    source_path: Path,
    source_sha256: str,
    attempt_dir: Path,
    contract: int,
) -> tuple[
    Path | tuple[Path, Path] | None,
    str | None,
    str | None,
    str | None,
    dict[str, object] | None,
]:
    try:
        purpose = (work / "sources" / "source-000002.txt").read_text(
            encoding="utf-8"
        )
        projection_interview.enable_endpoint_crop_verification(
            attempt_dir, purpose=purpose, contract=contract,
        )
        projection_interview.enable_existing_participant_crop_verification(
            attempt_dir, purpose=purpose, contract=contract,
        )
        projection_interview.enable_contextual_endpoint_verification(
            attempt_dir, purpose=purpose, contract=contract,
        )
        projection_interview.enable_endpoint_context_evidence(
            attempt_dir, purpose=purpose, contract=contract,
        )
        projection_interview.enable_rejected_endpoint_reuse_block(
            attempt_dir, purpose=purpose, contract=contract,
        )
        projection_interview.enable_rejected_endpoint_collision_exclusion(
            attempt_dir, purpose=purpose, contract=contract,
        )
        endpoint_evidence = projection_interview.prepare_endpoint_evidence(
            attempt_dir,
            source_path=source_path,
            source_sha256=source_sha256,
            purpose=purpose,
            contract=contract,
        )
        crop = projection_interview.prepare_region_evidence(
            attempt_dir,
            source_path=source_path,
            source_sha256=source_sha256,
            purpose=purpose,
            contract=contract,
        )
        interview_state, _pending, _completed = (
            projection_interview.prepare_resume(
                attempt_dir,
                purpose=purpose,
                contract=contract,
            )
        )
        replacement_attachments = (
            projection_interview.required_participant_replacement_attachments(
                attempt_dir,
                interview_state,
                source_path=source_path,
                source_sha256=source_sha256,
            )
        )
    except (OSError, projection_interview.InterviewError) as error:
        return None, None, None, None, _blocked(
            "projection region evidence failed", str(error)
        )
    region_id: str | None = None
    obligation_id: str | None = None
    endpoint_evidence_sha256: str | None = None
    if contract >= 4:
        try:
            active_region = projection_interview._active_scan_region(
                interview_state
            )
        except projection_interview.InterviewError as error:
            return None, None, None, _blocked(
                "projection region evidence failed", str(error)
            )
        if isinstance(active_region, dict) and isinstance(
            active_region.get("id"), str
        ):
            region_id = str(active_region["id"])
        else:
            obligation = projection_interview._pending_obligation(
                interview_state
            )
            if not isinstance(obligation, dict) or not isinstance(
                obligation.get("id"), str
            ):
                return None, None, None, _blocked(
                    "projection relationship binding failed",
                    "no active region or pending relationship obligation is available",
                )
            obligation_id = str(obligation["id"])
    if endpoint_evidence is not None:
        crop, endpoint_evidence_sha256 = endpoint_evidence
    elif replacement_attachments is not None:
        crop = replacement_attachments
    return (
        crop or source_path,
        region_id,
        obligation_id,
        endpoint_evidence_sha256,
        None,
    )


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
    attachment: Path | tuple[Path, Path] = work / "sources" / "source-000003"
    if stage == "project_first_source":
        source = state.get("first_source")
        if not isinstance(source, dict) or not isinstance(source.get("sha256"), str):
            return _blocked(
                "projection region evidence failed", "the frozen source identity is missing"
            )
        (
            attachment,
            region_id,
            obligation_id,
            endpoint_evidence_sha256,
            attachment_error,
        ) = _projection_model_attachment(
            work,
            source_path=attachment,
            source_sha256=str(source["sha256"]),
            attempt_dir=work / "projection-interviews" / "attempt-000001",
            contract=int(state.get("projection_interview_contract", 0)),
        )
        if attachment_error:
            return attachment_error
        assert attachment is not None
    attachments = attachment if isinstance(attachment, tuple) else (attachment,)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--work",
        str(work.resolve()),
    ]
    if stage == "project_first_source" and region_id is not None:
        command.extend(["--projection-region-id", region_id])
    elif stage == "project_first_source" and obligation_id is not None:
        command.extend(["--projection-obligation-id", obligation_id])
    if (
        stage == "project_first_source"
        and endpoint_evidence_sha256 is not None
    ):
        command.extend([
            "--projection-endpoint-evidence-sha256",
            endpoint_evidence_sha256,
        ])
    command.append(selected["flag"])
    return {
        "status": "waiting_for_model",
        "stopped": selected["stopped"],
        "intake_id": state["intake_id"],
        "work": [{
            "stage": stage,
            "instruction": selected["instruction"],
            "attachments": [str(path.resolve()) for path in attachments],
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


def _pdf_projection_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "first_pdf_projection_recorded",
        "intake_id": state["intake_id"],
        "source": state["first_source"],
        "projection": state["first_projection"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _pdf_projection_failed_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    return {
        "status": "ready_for_projection",
        "stopped": "first_pdf_projection_failed",
        "intake_id": state["intake_id"],
        "source": state["first_source"],
        "projection": state["first_projection"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _pdf_page_paths(source_id: str, page: int) -> dict[str, str]:
    root = f"pdf-projections/{source_id}-v1/page-projections/page-{page:06d}"
    return {
        "root": root,
        "interview_dir": f"{root}/projection-interview",
        "interview_path": f"{root}/projection-interview/interview.jsonl",
        "candidate_path": f"{root}/projection-interview/projection.json",
        "verification_dir": f"{root}/relationship-verification",
        "verification_path": f"{root}/relationship-verification/verification.json",
        "correction_dir": f"{root}/relationship-correction",
        "correction_path": f"{root}/relationship-correction/corrections.json",
        "correction_candidate_path": f"{root}/relationship-correction/verification-candidate.json",
        "correction_verification_dir": f"{root}/relationship-correction-verification",
        "correction_verification_path": f"{root}/relationship-correction-verification/verification.json",
        "projection_path": f"{root}/projection.json",
    }


def _active_pdf_page(state: dict[str, object]) -> dict[str, object] | None:
    saved = state.get("pdf_projection")
    if not isinstance(saved, dict):
        return None
    prepared = saved.get("prepared")
    page = saved.get("active_page")
    pages = prepared.get("pages") if isinstance(prepared, dict) else None
    if (
        not isinstance(page, int)
        or not isinstance(pages, list)
        or page < 1
        or page > len(pages)
        or not isinstance(pages[page - 1], dict)
    ):
        return None
    return pages[page - 1]


def _pdf_page_gap_inventory(
    projection: dict[str, object],
    *,
    page: int,
    page_projection_path: str,
    page_projection_sha256: str,
    render_path: str,
    render_sha256: str,
) -> list[dict[str, object]]:
    """Freeze every page gap with a globally unique, source-unit identity."""
    inventory: list[dict[str, object]] = []
    elements = projection.get("elements", [])
    for collection, kind in (
        ("scan_regions", "scan_region"),
        ("elements", "element"),
        ("relationships", "relationship"),
    ):
        items = projection.get(collection, [])
        assert isinstance(items, list)
        for item in items:
            assert isinstance(item, dict)
            if item.get("status") != "gap":
                continue
            item_id = str(item["id"])
            context: list[dict[str, object]] = []
            if collection == "relationships":
                participant_ids = {item.get("from_id"), item.get("to_id")}
                context = [
                    element
                    for element in elements
                    if isinstance(element, dict)
                    and element.get("id") in participant_ids
                ]
            inventory.append({
                "page": page,
                "collection": collection,
                "kind": kind,
                "id": f"pdf-page-{page:06d}:{collection}:{item_id}",
                "item_id": item_id,
                "page_projection_path": page_projection_path,
                "page_projection_sha256": page_projection_sha256,
                "render_path": render_path,
                "render_sha256": render_sha256,
                "record_sha256": _digest_bytes(_canonical(item)),
                "record": item,
                "recorded_context": context,
            })
    return inventory


def _pdf_projection_waiting_result(
    state: dict[str, object], work: Path, stage: str
) -> dict[str, object]:
    page = _active_pdf_page(state)
    if page is None:
        return _blocked("invalid PDF projection state", "the active PDF page is missing")
    stages = {
        "project": ("--run-projection-interview", "interviewing_first_projection"),
        "verify": ("--run-projection-verification", "verifying_first_projection"),
        "correct": ("--run-relationship-correction", "correcting_rejected_relationships"),
        "verify_correction": ("--run-correction-verification", "verifying_relationship_corrections"),
    }
    flag, stopped = stages[stage]
    attachment: Path | tuple[Path, Path] = work / str(page["render_path"])
    if stage == "project":
        saved = state.get("pdf_projection")
        prepared = saved.get("prepared") if isinstance(saved, dict) else None
        if not isinstance(prepared, dict) or not isinstance(
            prepared.get("source_id"), str
        ):
            return _blocked(
                "projection region evidence failed", "the PDF projection identity is missing"
            )
        paths = _pdf_page_paths(str(prepared["source_id"]), int(page["page"]))
        (
            attachment,
            region_id,
            obligation_id,
            endpoint_evidence_sha256,
            attachment_error,
        ) = _projection_model_attachment(
            work,
            source_path=attachment,
            source_sha256=str(page["render_sha256"]),
            attempt_dir=work / paths["interview_dir"],
            contract=PROJECTION_INTERVIEW_CONTRACT,
        )
        if attachment_error:
            return attachment_error
        assert attachment is not None
    attachments = attachment if isinstance(attachment, tuple) else (attachment,)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--work",
        str(work.resolve()),
    ]
    if stage == "project" and region_id is not None:
        command.extend(["--projection-region-id", region_id])
    elif stage == "project" and obligation_id is not None:
        command.extend(["--projection-obligation-id", obligation_id])
    if stage == "project" and endpoint_evidence_sha256 is not None:
        command.extend([
            "--projection-endpoint-evidence-sha256",
            endpoint_evidence_sha256,
        ])
    command.append(flag)
    return {
        "status": "waiting_for_model",
        "stopped": stopped,
        "intake_id": state["intake_id"],
        "pdf_page": page["page"],
        "pdf_page_count": state["pdf_projection"]["prepared"]["page_count"],
        "work": [{
            "stage": f"{stage}_pdf_page",
            "instruction": (
                "Inspect the attached rendered PDF page, run the command, and answer only "
                "the typed question currently displayed. Code controls page order, allowed "
                "choices, spatial coverage, and assembly."
            ),
            "attachments": [str(path.resolve()) for path in attachments],
            "command": command,
        }],
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
    saved_round = state.get("gap_question_round")
    gaps = saved_round.get("gaps") if isinstance(saved_round, dict) else None
    attachments: list[str]
    if (
        isinstance(state.get("first_projection"), dict)
        and state["first_projection"].get("method") == "pdf_visible_pages"
        and isinstance(gaps, list)
    ):
        ordered_paths: list[str] = []
        for gap in gaps:
            if not isinstance(gap, dict) or not isinstance(gap.get("render_path"), str):
                return _blocked(
                    "invalid PDF gap inventory",
                    "a PDF gap lost its exact rendered-page identity",
                )
            if gap["render_path"] not in ordered_paths:
                ordered_paths.append(str(gap["render_path"]))
        attachments = [str((work / path).resolve()) for path in ordered_paths]
    else:
        attachments = [str((work / "sources" / "source-000003").resolve())]
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
            "attachments": attachments,
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
    prepared = state["follow_up_gap_question_round"]
    assert isinstance(prepared, dict) and isinstance(prepared.get("round"), int)
    return {
        "status": "waiting_for_model",
        "stopped": "formulating_follow_up_gap_question_round",
        "intake_id": state["intake_id"],
        "round": prepared["round"],
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
    result = {
        "status": "ready_for_projection_assessment",
        "stopped": "gap_answer_assessment_recorded",
        "intake_id": state["intake_id"],
        "projection": state["first_projection"],
        "assessment_count": assessment["assessment_count"],
        "assessments": assessment["assessments"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }
    return _with_clarification_continuation(work, state, result)


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
    result = {
        "status": "ready_for_projection_assessment",
        "stopped": str(state["phase"]),
        "intake_id": state["intake_id"],
        "projection": state.get("current_projection", state["first_projection"]),
        "original_projection": state["first_projection"],
        "gap_resolution": state["gap_resolution"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }
    resolution = state.get("gap_resolution")
    if isinstance(resolution, dict) and resolution.get("mode") == "assessed_answer":
        return _with_clarification_continuation(work, state, result)
    return result


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


def _verbatim_utf8_projection_record(
    source_id: str, source_sha256: str
) -> dict[str, object]:
    return {
        "id": f"projection-{source_id}-v1",
        "source_id": source_id,
        "version": 1,
        "path": f"projections/{source_id}-v1.txt",
        "sha256": source_sha256,
        "method": "verbatim_utf8",
        "coverage": {
            "status": "complete",
            "source_units": 1,
            "represented_units": 1,
            "gaps": [],
        },
    }


def _verbatim_utf8_bytes(
    frozen: bytes,
) -> tuple[bytes | None, dict[str, object] | None]:
    try:
        text = frozen.decode("utf-8")
    except UnicodeDecodeError as error:
        return None, _blocked(
            "projection adapter unavailable",
            f"the complete frozen source is not valid UTF-8: {error}",
        )
    if text.encode("utf-8") != frozen:
        return None, _blocked(
            "invalid UTF-8 projection",
            "the decoded source does not round-trip to its exact frozen bytes",
        )
    return frozen, None


def _pending_additional_projection_record(number: int) -> dict[str, object]:
    return {
        "id": f"projection-source-{number:06d}-v1",
        "source_id": f"source-{number:06d}",
        "version": 1,
        "status": "pending",
        "path": None,
        "sha256": None,
        "method": None,
        "coverage": {
            "status": "pending",
            "source_units": 1,
            "represented_units": 0,
            "gaps": ["the frozen source has not yet been converted"],
        },
    }


def _bind_local_file_to_question(
    source: dict[str, object], question: dict[str, object]
) -> dict[str, object]:
    return {
        **source,
        "answers_question": question["id"],
        "answers_gap": question["answers_gap"],
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
    number: int,
    supplied: Path,
    resolved: Path,
    stored_path: str,
    content: bytes,
    media_type: str,
    media_type_basis: str,
) -> dict[str, object]:
    return {
        "id": f"source-{number:06d}",
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


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, server_hostname: str, address: str, port: int) -> None:
        self._server_hostname = server_hostname
        super().__init__(
            address,
            port=port,
            timeout=URL_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )

    def connect(self) -> None:
        http.client.HTTPConnection.connect(self)
        assert self.sock is not None
        self.sock = self._context.wrap_socket(
            self.sock, server_hostname=self._server_hostname
        )


def _url_connection(
    scheme: str, hostname: str, address: str, port: int
) -> http.client.HTTPConnection:
    if scheme == "https":
        return _PinnedHTTPSConnection(hostname, address, port)
    return http.client.HTTPConnection(
        address, port=port, timeout=URL_TIMEOUT_SECONDS
    )


def _without_url_fragment(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
    )


def _requestable_public_url(
    supplied: str,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if not supplied or any(ord(character) < 32 for character in supplied):
        return None, _blocked(
            "URL unavailable", "supply one non-empty HTTP(S) URL without control characters"
        )
    try:
        parsed = urlsplit(supplied)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as error:
        return None, _blocked("URL unavailable", f"the URL authority is invalid: {error}")
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return None, _blocked(
            "URL scheme unsupported",
            f"the supplied URL uses {parsed.scheme or 'no scheme'}; use http or https",
        )
    if parsed.username is not None or parsed.password is not None:
        return None, _blocked(
            "URL credentials prohibited",
            "remove the username and password from the URL before intake",
        )
    if not hostname:
        return None, _blocked(
            "URL unavailable", "the supplied HTTP(S) URL has no hostname"
        )
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as error:
        return None, _blocked("URL unavailable", f"the hostname is invalid: {error}")
    port = port or (443 if scheme == "https" else 80)
    try:
        resolved = socket.getaddrinfo(
            ascii_hostname, port, type=socket.SOCK_STREAM
        )
    except OSError as error:
        return None, _blocked(
            "URL resolution failed",
            f"the hostname {ascii_hostname!r} could not be resolved: {error}",
        )
    addresses = sorted({str(item[4][0]) for item in resolved})
    unsafe = []
    for address in addresses:
        try:
            candidate = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            unsafe.append(address)
            continue
        if not candidate.is_global:
            unsafe.append(address)
    if not addresses or unsafe:
        return None, _blocked(
            "unsafe URL destination",
            "the hostname must resolve only to public internet addresses; "
            f"rejected: {', '.join(unsafe) if unsafe else 'no addresses'}",
        )
    request_url = _without_url_fragment(supplied)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    default_port = 443 if scheme == "https" else 80
    display_hostname = (
        f"[{ascii_hostname}]" if ":" in ascii_hostname else ascii_hostname
    )
    host_header = (
        display_hostname if port == default_port else f"{display_hostname}:{port}"
    )
    return {
        "scheme": scheme,
        "hostname": ascii_hostname,
        "port": port,
        "request_url": request_url,
        "target": target,
        "host_header": host_header,
        "resolved_addresses": addresses,
    }, None


def _response_headers(response: http.client.HTTPResponse) -> list[dict[str, str]]:
    return [
        {"name": str(name), "value": str(value)}
        for name, value in response.getheaders()
    ]


def _fetch_public_url(
    supplied: str,
) -> tuple[dict[str, object] | None, bytes | None, dict[str, object] | None]:
    current = supplied
    initial_request_url: str | None = None
    redirects: list[dict[str, object]] = []
    for redirect_count in range(URL_MAX_REDIRECTS + 1):
        request, request_error = _requestable_public_url(current)
        if request_error:
            return None, None, request_error
        assert request is not None
        request_url = str(request["request_url"])
        if initial_request_url is None:
            initial_request_url = request_url
        response: http.client.HTTPResponse | None = None
        connection: http.client.HTTPConnection | None = None
        connected_address: str | None = None
        connection_errors: list[str] = []
        for address in request["resolved_addresses"]:
            assert isinstance(address, str)
            try:
                connection = _url_connection(
                    str(request["scheme"]),
                    str(request["hostname"]),
                    address,
                    int(request["port"]),
                )
                connection.request(
                    "GET",
                    str(request["target"]),
                    headers={
                        "Host": str(request["host_header"]),
                        "User-Agent": "info-intake-machinery/1",
                        "Accept": "*/*",
                        "Connection": "close",
                    },
                )
                response = connection.getresponse()
                connected_address = address
                break
            except (OSError, ssl.SSLError, http.client.HTTPException) as error:
                connection_errors.append(f"{address}: {error}")
                if connection is not None:
                    connection.close()
                connection = None
        if response is None or connection is None or connected_address is None:
            return None, None, _blocked(
                "URL retrieval failed",
                f"the public URL {request_url!r} could not be retrieved: "
                + "; ".join(connection_errors),
            )
        try:
            headers = _response_headers(response)
            status = int(response.status)
            reason = str(response.reason or "")
            if status in URL_REDIRECT_STATUSES:
                locations = [
                    item["value"]
                    for item in headers
                    if item["name"].lower() == "location"
                ]
                if len(locations) != 1 or not locations[0]:
                    return None, None, _blocked(
                        "URL redirect invalid",
                        f"redirect response {status} from {request_url!r} must contain exactly one Location header",
                    )
                if redirect_count >= URL_MAX_REDIRECTS:
                    return None, None, _blocked(
                        "URL redirect limit exceeded",
                        f"the retrieval exceeded {URL_MAX_REDIRECTS} redirects",
                    )
                next_url = _without_url_fragment(
                    urljoin(request_url, locations[0])
                )
                redirects.append({
                    "request_url": request_url,
                    "status": status,
                    "reason": reason,
                    "location": locations[0],
                    "next_url": next_url,
                    "headers": headers,
                    "resolved_addresses": request["resolved_addresses"],
                    "connected_address": connected_address,
                })
                current = next_url
                continue
            if status < 200 or status >= 300:
                return None, None, _blocked(
                    "URL response unsuccessful",
                    f"the final response from {request_url!r} was {status} {reason}".strip(),
                )
            lengths = [
                item["value"]
                for item in headers
                if item["name"].lower() == "content-length"
            ]
            if lengths:
                try:
                    declared_length = int(lengths[-1])
                except ValueError:
                    declared_length = -1
                if declared_length > URL_MAX_BYTES:
                    return None, None, _blocked(
                        "URL response too large",
                        f"the response declares {declared_length} bytes; the limit is {URL_MAX_BYTES}",
                    )
            chunks: list[bytes] = []
            received = 0
            while True:
                chunk = response.read(min(65536, URL_MAX_BYTES + 1 - received))
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
                if received > URL_MAX_BYTES:
                    return None, None, _blocked(
                        "URL response too large",
                        f"the response exceeded the {URL_MAX_BYTES}-byte limit",
                    )
            content = b"".join(chunks)
            return {
                "provided_url": supplied,
                "request_url": initial_request_url,
                "final_url": request_url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "redirect_chain": redirects,
                "response": {
                    "status": status,
                    "reason": reason,
                    "headers": headers,
                    "resolved_addresses": request["resolved_addresses"],
                    "connected_address": connected_address,
                },
            }, content, None
        except (OSError, ssl.SSLError, http.client.HTTPException) as error:
            return None, None, _blocked(
                "URL retrieval failed",
                f"the response from {request_url!r} could not be read: {error}",
            )
        finally:
            connection.close()
    return None, None, _blocked(
        "URL redirect limit exceeded",
        f"the retrieval exceeded {URL_MAX_REDIRECTS} redirects",
    )


def _url_media_type(
    retrieval: dict[str, object], stored_path: Path
) -> tuple[str, str]:
    response = retrieval.get("response")
    headers = response.get("headers") if isinstance(response, dict) else None
    if isinstance(headers, list):
        for item in reversed(headers):
            if (
                isinstance(item, dict)
                and str(item.get("name", "")).lower() == "content-type"
            ):
                media_type = str(item.get("value", "")).split(";", 1)[0].strip().lower()
                if "/" in media_type and "\n" not in media_type:
                    return media_type, "HTTP Content-Type"
    return _detect_media_type(stored_path)


def _url_source_record(
    number: int,
    stored_path: str,
    content: bytes,
    retrieval: dict[str, object],
    media_type: str,
    media_type_basis: str,
) -> dict[str, object]:
    final = urlsplit(str(retrieval["final_url"]))
    final_segment = unquote(final.path.rsplit("/", 1)[-1])
    filename = final_segment.replace("/", "_") or str(final.hostname or "download")
    return {
        "id": f"source-{number:06d}",
        "kind": "url",
        "adapter": {"name": "url", "version": URL_ADAPTER_VERSION},
        "provided_url": retrieval["provided_url"],
        "request_url": retrieval["request_url"],
        "final_url": retrieval["final_url"],
        "retrieved_at": retrieval["retrieved_at"],
        "redirect_chain": retrieval["redirect_chain"],
        "response": retrieval["response"],
        "filename": filename,
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


def _closure_artifact(
    work: Path,
    relative: object,
    expected_sha256: object,
    label: str,
) -> tuple[bytes | None, dict[str, object] | None]:
    if (
        not isinstance(relative, str)
        or not relative
        or not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
    ):
        return None, _blocked(
            "invalid source projection ledger",
            f"{label} lost its immutable path or SHA-256",
        )
    artifact = (work / relative).resolve()
    try:
        artifact.relative_to(work.resolve())
        content = artifact.read_bytes()
    except ValueError:
        return None, _blocked(
            "invalid source projection ledger", f"{label} escapes the intake directory"
        )
    except OSError:
        return None, _blocked(
            "immutable source projection unavailable", f"{label}: {relative}"
        )
    if _digest_bytes(content) != expected_sha256:
        return None, _blocked(
            "immutable source projection changed", f"{label}: {relative}"
        )
    return content, None


def _source_projection_closure_inventory(
    work: Path, entries: list[dict[str, object]]
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    sources: dict[str, dict[str, object]] = {}
    projections: dict[str, list[dict[str, object]]] = {}
    failures: dict[str, dict[str, object]] = {}
    pdf_progress: dict[str, dict[str, int]] = {}
    projection_ids: set[str] = set()
    source_paths: set[str] = set()
    projection_paths: set[str] = set()

    def register_source(
        entry: dict[str, object], *, directly_projected: bool
    ) -> dict[str, object] | None:
        source = entry.get("source")
        if not isinstance(source, dict):
            return _blocked(
                "invalid source projection ledger",
                f"ledger entry {entry.get('sequence')} lost its source record",
            )
        source_id = source.get("id")
        if (
            not isinstance(source_id, str)
            or not source_id.startswith("source-")
            or source_id in sources
        ):
            return _blocked(
                "invalid source projection ledger",
                f"ledger entry {entry.get('sequence')} has a missing or duplicate source identity",
            )
        relative = source.get("path", source.get("stored_path"))
        if (
            not isinstance(relative, str)
            or relative in source_paths
            or relative in projection_paths
        ):
            return _blocked(
                "invalid source projection ledger",
                f"source {source_id} has a missing or duplicate artifact path",
            )
        source_bytes, artifact_error = _closure_artifact(
            work, relative, source.get("sha256"), f"source {source_id}"
        )
        if artifact_error:
            return artifact_error
        reservation = None if directly_projected else entry.get("projection")
        if not directly_projected:
            if not isinstance(reservation, dict) or reservation.get("status") != "pending":
                return _blocked(
                    "invalid source projection ledger",
                    f"source {source_id} lost its pending projection reservation",
                )
            reservation_id = reservation.get("id")
            if reservation_id is not None and (
                reservation_id != f"projection-{source_id}-v1"
                or reservation.get("source_id") != source_id
                or reservation.get("version") != 1
                or reservation.get("path") is not None
                or reservation.get("sha256") is not None
            ):
                return _blocked(
                    "invalid source projection ledger",
                    f"source {source_id} has a malformed projection reservation",
                )
        source_paths.add(relative)
        sources[source_id] = {
            "source": source,
            "source_ledger_sequence": entry["sequence"],
            "reservation": reservation,
            "source_bytes": source_bytes,
            "directly_projected": directly_projected,
        }
        projections[source_id] = []
        return None

    def register_projection(
        source_id: object,
        projection: object,
        entry: dict[str, object],
        *,
        direct_source_bytes: bytes | None = None,
    ) -> dict[str, object] | None:
        if not isinstance(source_id, str) or source_id not in sources:
            return _blocked(
                "invalid source projection ledger",
                f"ledger entry {entry.get('sequence')} projects an unknown source",
            )
        if not isinstance(projection, dict):
            return _blocked(
                "invalid source projection ledger",
                f"ledger entry {entry.get('sequence')} lost its projection record",
            )
        projection_id = projection.get("id")
        version = projection.get("version")
        path = projection.get("path")
        if (
            not isinstance(projection_id, str)
            or not projection_id
            or projection_id in projection_ids
            or not isinstance(version, int)
            or version < 1
            or not isinstance(path, str)
            or path in projection_paths
            or path in source_paths
            or any(item["version"] == version for item in projections[source_id])
        ):
            return _blocked(
                "invalid source projection ledger",
                f"ledger entry {entry.get('sequence')} has a duplicate or malformed projection identity",
            )
        projection_bytes, artifact_error = _closure_artifact(
            work, path, projection.get("sha256"), f"projection {projection_id}"
        )
        if artifact_error:
            return artifact_error
        if direct_source_bytes is not None and projection_bytes != direct_source_bytes:
            return _blocked(
                "immutable source projection changed",
                f"projection {projection_id} is not the complete verbatim source representation",
            )
        declared_source_id = projection.get("source_id")
        if declared_source_id is not None and declared_source_id != source_id:
            return _blocked(
                "invalid source projection ledger",
                f"projection {projection_id} is bound to a different source",
            )
        projection_ids.add(projection_id)
        projection_paths.add(path)
        projections[source_id].append(
            {
                "ledger_sequence": entry["sequence"],
                "id": projection_id,
                "version": version,
                "path": path,
                "sha256": projection["sha256"],
            }
        )
        return None

    for entry in entries:
        event = entry.get("event")
        if event == "source_projected":
            source_error = register_source(entry, directly_projected=True)
            if source_error:
                return None, source_error
            source = entry["source"]
            assert isinstance(source, dict)
            source_id = source["id"]
            source_bytes = sources[str(source_id)]["source_bytes"]
            assert isinstance(source_bytes, bytes)
            projection_error = register_projection(
                source_id,
                entry.get("projection"),
                entry,
                direct_source_bytes=source_bytes,
            )
            if projection_error:
                return None, projection_error
        elif event == "source_acquired":
            source_error = register_source(entry, directly_projected=False)
            if source_error:
                return None, source_error
        elif event == "projection_version_created":
            projection = entry.get("projection")
            source_id = projection.get("source_id") if isinstance(projection, dict) else None
            projection_error = register_projection(source_id, projection, entry)
            if projection_error:
                return None, projection_error
        elif event == "projection_conversion_failed":
            source_id = entry.get("source_id")
            failure = entry.get("failure")
            if (
                not isinstance(source_id, str)
                or source_id not in sources
                or source_id in failures
                or not isinstance(failure, dict)
                or failure.get("id") != f"projection-{source_id}-v1"
                or failure.get("source_id") != source_id
                or failure.get("version") != 1
                or failure.get("status") != "failed"
                or failure.get("path") is not None
                or failure.get("sha256") is not None
                or not isinstance(failure.get("coverage"), dict)
                or failure["coverage"].get("status") != "failed"
            ):
                return None, _blocked(
                    "invalid source projection ledger",
                    f"ledger entry {entry.get('sequence')} has an invalid conversion failure",
                )
            failures[source_id] = {
                "ledger_sequence": entry["sequence"],
                "failure": failure,
            }
        elif event == "pdf_projection_started":
            source_id = entry.get("source_id")
            prepared = entry.get("prepared")
            page_count = prepared.get("page_count") if isinstance(prepared, dict) else None
            if (
                not isinstance(source_id, str)
                or source_id not in sources
                or source_id in pdf_progress
                or not isinstance(page_count, int)
                or page_count < 1
            ):
                return None, _blocked(
                    "invalid source projection ledger",
                    f"ledger entry {entry.get('sequence')} has invalid PDF progress",
                )
            pdf_progress[source_id] = {"page_count": page_count, "completed": 0}
        elif event == "pdf_page_projection_completed":
            source_id = entry.get("source_id")
            progress = pdf_progress.get(str(source_id))
            if (
                progress is None
                or entry.get("page") != progress["completed"] + 1
                or progress["completed"] >= progress["page_count"]
            ):
                return None, _blocked(
                    "invalid source projection ledger",
                    f"ledger entry {entry.get('sequence')} reordered PDF pages",
                )
            progress["completed"] += 1

    if not sources:
        return None, _blocked(
            "source projection closure unavailable", "the intake has no immutable sources"
        )

    outcomes: list[dict[str, object]] = []
    for source_id, saved in sources.items():
        source = saved["source"]
        reservation = saved["reservation"]
        versions = sorted(projections[source_id], key=lambda item: int(item["version"]))
        if versions:
            if source_id in failures:
                return None, _blocked(
                    "invalid source projection ledger",
                    f"source {source_id} has both failed and completed projection outcomes",
                )
            progress = pdf_progress.get(source_id)
            if progress is not None and progress["completed"] != progress["page_count"]:
                return None, _blocked(
                    "invalid source projection ledger",
                    f"source {source_id} completed before every PDF page was projected",
                )
            expected_versions = list(range(1, len(versions) + 1))
            actual_versions = [item["version"] for item in versions]
            if actual_versions != expected_versions:
                return None, _blocked(
                    "invalid source projection ledger",
                    f"source {source_id} has a missing or reordered projection version",
                )
            if isinstance(reservation, dict) and isinstance(reservation.get("id"), str):
                if reservation["id"] != versions[0]["id"]:
                    return None, _blocked(
                        "invalid source projection ledger",
                        f"source {source_id} did not fill its reserved projection identity",
                    )
            outcome = "projected"
            reason = None
            current_projection = versions[-1]
        else:
            if saved["directly_projected"]:
                return None, _blocked(
                    "invalid source projection ledger",
                    f"source {source_id} lost its atomic readable projection",
                )
            recorded_failure = failures.get(source_id)
            progress = pdf_progress.get(source_id)
            media_type = source.get("media_type") if isinstance(source, dict) else None
            source_bytes = saved.get("source_bytes")
            assert isinstance(source_bytes, bytes)
            _, utf8_error = _verbatim_utf8_bytes(source_bytes)
            if recorded_failure is not None:
                failure = recorded_failure["failure"]
                assert isinstance(failure, dict)
                coverage = failure.get("coverage")
                gaps = coverage.get("gaps") if isinstance(coverage, dict) else None
                outcome = "failed"
                reason = gaps[0] if isinstance(gaps, list) and gaps else "source conversion failed"
                current_projection = {
                    "ledger_sequence": recorded_failure["ledger_sequence"],
                    **failure,
                }
            elif progress is not None:
                outcome = "pending"
                reason = (
                    f"PDF visible-page projection completed {progress['completed']} "
                    f"of {progress['page_count']} pages"
                )
                current_projection = None
            elif (
                isinstance(media_type, str)
                and not media_type.startswith("image/")
                and utf8_error is not None
            ):
                outcome = "failed"
                reason = str(utf8_error["why"])
                current_projection = None
            else:
                outcome = "pending"
                if isinstance(reservation, dict):
                    reason = reservation.get("why")
                    coverage = reservation.get("coverage")
                    if reason is None and isinstance(coverage, dict):
                        gaps = coverage.get("gaps")
                        if isinstance(gaps, list) and gaps and isinstance(gaps[0], str):
                            reason = gaps[0]
                if not isinstance(reason, str) or not reason:
                    reason = "the frozen source has not yet been converted"
                current_projection = None
        outcomes.append(
            {
                "source_id": source_id,
                "source_kind": source.get("kind") if isinstance(source, dict) else None,
                "source_sha256": source.get("sha256") if isinstance(source, dict) else None,
                "source_ledger_sequence": saved["source_ledger_sequence"],
                "outcome": outcome,
                "reason": reason,
                "reserved_projection": reservation,
                "projection": current_projection,
                "projection_version_count": len(versions),
            }
        )

    outcome_counts = {
        name: sum(item["outcome"] == name for item in outcomes)
        for name in ("projected", "pending", "failed")
    }
    return {
        "verdict": (
            "all_projected"
            if outcome_counts == {
                "projected": len(outcomes),
                "pending": 0,
                "failed": 0,
            }
            else "conversion_incomplete"
        ),
        "source_count": len(outcomes),
        "outcome_counts": outcome_counts,
        "outcomes": outcomes,
    }, None


def run_source_projection_closure(work: Path) -> dict[str, object]:
    try:
        opening_bytes = (work / "sources" / "source-000001.txt").read_bytes()
    except OSError as error:
        return _blocked("source projection closure unavailable", str(error))
    state, entries, load_error = _load_bound(work, opening_bytes)
    if load_error:
        return load_error
    assert state is not None
    inventory, inventory_error = _source_projection_closure_inventory(work, entries)
    if inventory_error:
        return inventory_error
    assert inventory is not None
    return {
        "status": "source_projection_closure",
        "stopped": "source_projection_closure",
        "intake_id": state["intake_id"],
        **inventory,
        "ledger_entries": len(entries),
        "ledger_tail_sha256": entries[-1]["entry_sha256"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _source_set_qualification_evidence(
    work: Path,
    entries: list[dict[str, object]],
    closure: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    bound = source_qualification_binding.bind(closure, entries)
    if bound.get("complete") is not True:
        return None, _blocked(
            "source-set qualification invalid", str(bound.get("why"))
        )
    records = bound.get("records")
    if not isinstance(records, list):
        return None, _blocked(
            "source-set qualification invalid",
            "the binding probe lost its ordered source records",
        )
    qualifications: list[dict[str, object]] = []
    for item in records:
        if not isinstance(item, dict):
            return None, _blocked(
                "source-set qualification invalid",
                "the binding probe returned a malformed source record",
            )
        record = item.get("record")
        artifact_bytes: bytes | None = None
        artifact_sha256: str | None = None
        visual_qualification: dict[str, object] | None = None
        if item.get("outcome") == "projected":
            if not isinstance(record, dict):
                return None, _blocked(
                    "source-set qualification invalid",
                    f"projected source {item.get('source_id')} lost its record",
                )
            artifact_bytes, artifact_error = _closure_artifact(
                work,
                record.get("path"),
                record.get("sha256"),
                f"qualification projection {record.get('id')}",
            )
            if artifact_error:
                return None, artifact_error
            artifact_sha256 = str(record["sha256"])
            if record.get("method") == "visual_spatial_v1":
                visual_qualification, visual_error = (
                    _visual_projection_qualification(work, record)
                )
                if visual_error:
                    return None, visual_error
                assert visual_qualification is not None
        qualified = source_projection_qualification.qualify(
            item,
            artifact_bytes,
            artifact_sha256,
            visual_qualification=visual_qualification,
        )
        if qualified.get("complete") is not True:
            return None, _blocked(
                "source-set qualification invalid", str(qualified.get("why"))
            )
        qualification = qualified.get("qualification")
        if not isinstance(qualification, dict):
            return None, _blocked(
                "source-set qualification invalid",
                "an adapter probe lost its source qualification",
            )
        qualifications.append(qualification)
    reconciled = source_qualification_reconciliation.reconcile(
        closure, qualifications
    )
    if reconciled.get("complete") is not True:
        return None, _blocked(
            "source-set qualification invalid", str(reconciled.get("why"))
        )
    result = reconciled.get("qualification")
    if not isinstance(result, dict):
        return None, _blocked(
            "source-set qualification invalid",
            "the reconciliation probe lost its intake-wide outcome",
        )
    return result, None


def _source_set_qualification_result(
    state: dict[str, object],
    work: Path,
    closure: dict[str, object],
    qualification: dict[str, object],
) -> dict[str, object]:
    return {
        "status": "source_set_qualification_complete",
        "stopped": "source_set_qualification_complete",
        "intake_id": state["intake_id"],
        "source_projection_closure": closure,
        "source_set_qualification": qualification,
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def run_source_set_qualification(work: Path) -> dict[str, object]:
    try:
        opening_bytes = (work / "sources" / "source-000001.txt").read_bytes()
    except OSError as error:
        return _blocked("source-set qualification unavailable", str(error))
    state, entries, load_error = _load_bound(work, opening_bytes)
    if load_error:
        return load_error
    assert state is not None
    if state.get("phase") not in {
        "source_collection_complete",
        "source_set_qualification_complete",
    }:
        return _blocked(
            "source-set qualification unavailable",
            "qualify the complete collected source set before clarification",
        )
    closure, closure_error = _source_projection_closure_inventory(work, entries)
    if closure_error:
        return closure_error
    assert closure is not None
    collection = state.get("source_collection")
    completion_sequence = (
        collection.get("completion_ledger_sequence")
        if isinstance(collection, dict)
        else None
    )
    if (
        not isinstance(completion_sequence, int)
        or completion_sequence < 1
        or completion_sequence > len(entries)
        or entries[completion_sequence - 1].get("event")
        != "source_collection_completed"
        or entries[completion_sequence - 1].get("source_ids")
        != collection.get("source_ids")
        or entries[completion_sequence - 1].get("source_projection_closure")
        != closure
    ):
        return _blocked(
            "invalid source collection ledger",
            "the completed source set changed before qualification",
        )
    qualification, qualification_error = _source_set_qualification_evidence(
        work, entries, closure
    )
    if qualification_error:
        return qualification_error
    assert qualification is not None
    if state.get("phase") == "source_set_qualification_complete":
        saved = state.get("source_set_qualification")
        sequence = (
            saved.get("ledger_sequence") if isinstance(saved, dict) else None
        )
        if (
            not isinstance(sequence, int)
            or sequence != len(entries)
            or entries[-1].get("event") != "source_set_qualification_completed"
            or entries[-1].get("source_collection_completion_ledger_sequence")
            != completion_sequence
            or entries[-1].get("source_projection_closure") != closure
            or entries[-1].get("source_set_qualification") != qualification
            or saved.get("qualification") != qualification
            or state.get("status") != "source_set_qualification_complete"
            or state.get("waiting_for") is not None
            or state.get("question") is not None
        ):
            return _blocked(
                "invalid source-set qualification ledger",
                "the preserved intake-wide qualification changed",
            )
        return _source_set_qualification_result(
            state, work, closure, qualification
        )

    completed = _ledger_entry(
        len(entries) + 1,
        "source_set_qualification_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "source_collection_completion_ledger_sequence": completion_sequence,
            "source_projection_closure": closure,
            "source_set_qualification": qualification,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed])
    state.update({
        "status": "source_set_qualification_complete",
        "phase": "source_set_qualification_complete",
        "waiting_for": None,
        "question": None,
        "source_set_qualification": {
            "ledger_sequence": completed["sequence"],
            "qualification": qualification,
        },
        "ledger_entries": completed["sequence"],
        "ledger_tail_sha256": completed["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _source_set_qualification_result(state, work, closure, qualification)


def _qualification_admission_result(
    state: dict[str, object],
    work: Path,
    closure: dict[str, object],
    qualification: dict[str, object],
    route: str,
    obligations: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "status": "qualification_admission_complete",
        "stopped": "qualification_admission_complete",
        "intake_id": state["intake_id"],
        "route": route,
        "clarification_obligations": obligations,
        "source_projection_closure": closure,
        "source_set_qualification": qualification,
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def run_qualification_admission(work: Path) -> dict[str, object]:
    try:
        opening_bytes = (work / "sources" / "source-000001.txt").read_bytes()
    except OSError as error:
        return _blocked("qualification admission unavailable", str(error))
    state, entries, load_error = _load_bound(work, opening_bytes)
    if load_error:
        return load_error
    assert state is not None
    if state.get("phase") not in {
        "source_set_qualification_complete",
        "qualification_admission_complete",
    }:
        return _blocked(
            "qualification admission unavailable",
            "admit only a completed intake-wide source qualification",
        )
    closure, closure_error = _source_projection_closure_inventory(work, entries)
    if closure_error:
        return closure_error
    assert closure is not None
    qualification, qualification_error = _source_set_qualification_evidence(
        work, entries, closure
    )
    if qualification_error:
        return qualification_error
    assert qualification is not None
    saved = state.get("source_set_qualification")
    qualification_sequence = (
        saved.get("ledger_sequence") if isinstance(saved, dict) else None
    )
    qualification_index = (
        qualification_sequence - 1
        if isinstance(qualification_sequence, int)
        else -1
    )
    if (
        qualification_index < 0
        or qualification_index >= len(entries)
        or entries[qualification_index].get("event")
        != "source_set_qualification_completed"
        or entries[qualification_index].get("source_set_qualification")
        != qualification
        or saved.get("qualification") != qualification
    ):
        return _blocked(
            "invalid qualification admission ledger",
            "the admission lost its exact source-set qualification event",
        )
    qualification_event_sha256 = entries[qualification_index].get(
        "entry_sha256"
    )
    disposition = qualification_terminal_disposition.decide(qualification)
    if disposition.get("complete") is not True:
        return _blocked(
            "qualification admission invalid", str(disposition.get("why"))
        )
    route = disposition.get("route")
    obligations: list[dict[str, object]] = []
    if route == "clarification_required":
        bound = clarification_obligation_binding.bind(
            qualification, str(qualification_event_sha256)
        )
        if bound.get("complete") is not True:
            return _blocked(
                "qualification admission invalid", str(bound.get("why"))
            )
        exact = bound.get("obligations")
        if not isinstance(exact, list) or any(
            not isinstance(item, dict) for item in exact
        ):
            return _blocked(
                "qualification admission invalid",
                "the obligation binding probe lost its exact ordered results",
            )
        obligations = exact
    prepared = qualification_admission_publication.prepare(
        route, obligations, qualification_event_sha256
    )
    if prepared.get("complete") is not True:
        return _blocked(
            "qualification admission invalid", str(prepared.get("why"))
        )
    publication = prepared.get("publication")
    if not isinstance(publication, dict):
        return _blocked(
            "qualification admission invalid",
            "the publication probe lost its exact event payload",
        )
    if state.get("phase") == "qualification_admission_complete":
        admission = state.get("qualification_admission")
        sequence = (
            admission.get("ledger_sequence")
            if isinstance(admission, dict)
            else None
        )
        entry = (
            entries[sequence - 1]
            if isinstance(sequence, int) and 1 <= sequence <= len(entries)
            else None
        )
        if (
            sequence != len(entries)
            or not isinstance(entry, dict)
            or entry.get("event") != "qualification_admission_completed"
            or entry.get("source_set_qualification_ledger_sequence")
            != qualification_sequence
            or any(entry.get(key) != value for key, value in publication.items())
            or admission.get("qualification_event_sha256")
            != qualification_event_sha256
            or admission.get("route") != route
            or admission.get("clarification_obligations") != obligations
            or state.get("status") != "qualification_admission_complete"
            or state.get("waiting_for") is not None
            or state.get("question") is not None
        ):
            return _blocked(
                "invalid qualification admission ledger",
                "the preserved qualification admission changed",
            )
        return _qualification_admission_result(
            state, work, closure, qualification, str(route), obligations
        )

    if qualification_sequence != len(entries):
        return _blocked(
            "invalid qualification admission ledger",
            "the qualification event is not the current immutable ledger tail",
        )
    completed = _ledger_entry(
        len(entries) + 1,
        "qualification_admission_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "source_set_qualification_ledger_sequence": qualification_sequence,
            **publication,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed])
    state.update({
        "status": "qualification_admission_complete",
        "phase": "qualification_admission_complete",
        "waiting_for": None,
        "question": None,
        "qualification_admission": {
            "ledger_sequence": completed["sequence"],
            "qualification_event_sha256": qualification_event_sha256,
            "route": route,
            "clarification_obligations": obligations,
        },
        "ledger_entries": completed["sequence"],
        "ledger_tail_sha256": completed["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _qualification_admission_result(
        state, work, closure, qualification, str(route), obligations
    )


def _qualification_question_round_model_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    return {
        "status": "waiting_for_model",
        "stopped": "formulating_qualification_question_round",
        "intake_id": state["intake_id"],
        "work": [{
            "stage": "formulate_qualification_question_round",
            "instruction": (
                "Answer only each typed question displayed. Code fixes every "
                "clarification obligation, allowed answer type, order, and final round."
            ),
            "attachments": [],
            "command": [
                sys.executable,
                str(Path(__file__).resolve()),
                "--work",
                str(work.resolve()),
                "--run-qualification-question-round",
            ],
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _qualification_question_round_operator_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    questions = state.get("questions")
    assert isinstance(questions, list) and questions
    return {
        "status": "needs_operator",
        "stopped": "awaiting_qualification_clarification_answers",
        "intake_id": state["intake_id"],
        "question": questions[0],
        "questions": questions,
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _qualification_question_round_request_context(
    state: dict[str, object], entries: list[dict[str, object]]
) -> tuple[
    dict[str, object] | None,
    list[dict[str, object]] | None,
    dict[str, object] | None,
]:
    saved = state.get("qualification_question_round")
    request_sequence = (
        saved.get("request_ledger_sequence") if isinstance(saved, dict) else None
    )
    admission_sequence = (
        saved.get("admission_ledger_sequence") if isinstance(saved, dict) else None
    )
    if (
        not isinstance(request_sequence, int)
        or not isinstance(admission_sequence, int)
        or admission_sequence < 1
        or request_sequence != admission_sequence + 1
        or len(entries) < request_sequence
    ):
        return None, None, _blocked(
            "invalid qualification question round",
            (
                f"saved request {request_sequence!r} and admission {admission_sequence!r} "
                "are not adjacent ledger positions; restore their exact recorded positions"
            ),
        )
    admission = entries[admission_sequence - 1]
    request = entries[request_sequence - 1]
    try:
        contexts = qualification_question_round.bind_contexts(admission)
    except qualification_question_round.QuestionRoundError as error:
        return None, None, _blocked(
            "invalid qualification question round", str(error)
        )
    context_digests = [str(item["evidence_sha256"]) for item in contexts]
    obligation_ids = [str(item["obligation_id"]) for item in contexts]
    expected_request = {
        "contract": qualification_question_round.CONTRACT,
        "qualification_admission_ledger_sequence": admission_sequence,
        "qualification_admission_sha256": admission.get("entry_sha256"),
        "obligation_count": len(contexts),
        "obligation_ids": obligation_ids,
        "evidence_sha256s": context_digests,
        "interview_path": "qualification-question-round/interview.jsonl",
        "result_path": "qualification-question-round/question-round.json",
    }
    if (
        request.get("event") != "qualification_question_round_requested"
        or any(request.get(key) != value for key, value in expected_request.items())
        or not isinstance(saved, dict)
        or any(saved.get(key) != value for key, value in {
            "contract": qualification_question_round.CONTRACT,
            "admission_ledger_sequence": admission_sequence,
            "admission_sha256": admission.get("entry_sha256"),
            "obligation_ids": obligation_ids,
            "evidence_sha256s": context_digests,
            "request_ledger_sequence": request_sequence,
        }.items())
    ):
        return None, None, _blocked(
            "invalid qualification question round",
            (
                f"request at ledger position {request_sequence} changed; restore the "
                "recorded admission identity, obligation identities, evidence digests, and paths"
            ),
        )
    return admission, contexts, None


def request_qualification_question_round(work: Path) -> dict[str, object]:
    admitted = run_qualification_admission(work)
    if admitted.get("status") == "blocked":
        return admitted
    if admitted.get("route") != "clarification_required":
        return _blocked(
            "qualification question round unavailable",
            (
                f"qualification route {admitted.get('route')!r} needs no operator "
                "clarification; preserve first-layer completion"
            ),
        )
    try:
        opening_bytes = (work / "sources" / "source-000001.txt").read_bytes()
    except OSError as error:
        return _blocked("qualification question round unavailable", str(error))
    state, entries, load_error = _load_bound(work, opening_bytes)
    if load_error:
        return load_error
    assert state is not None
    if state.get("phase") == "formulating_qualification_question_round":
        admission, _contexts, request_error = (
            _qualification_question_round_request_context(state, entries)
        )
        if request_error:
            return request_error
        assert admission is not None
        return _qualification_question_round_model_result(state, work)
    if state.get("phase") != "qualification_admission_complete":
        return _blocked(
            "qualification question round unavailable",
            (
                f"intake phase {state.get('phase')!r} is not an admitted clarification; "
                "resume the preserved current boundary"
            ),
        )
    admission = entries[-1]
    try:
        contexts = qualification_question_round.bind_contexts(admission)
    except qualification_question_round.QuestionRoundError as error:
        return _blocked("qualification question round unavailable", str(error))
    round_dir = work / "qualification-question-round"
    if round_dir.exists():
        return _blocked(
            "unbound qualification question round",
            (
                f"artifact directory {round_dir} already exists without a request event; "
                "remove only that unbound directory before retrying"
            ),
        )
    round_dir.mkdir(parents=True)
    (round_dir / "interview.jsonl").touch()
    request_sequence = len(entries) + 1
    request = _ledger_entry(
        request_sequence,
        "qualification_question_round_requested",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "contract": qualification_question_round.CONTRACT,
            "qualification_admission_ledger_sequence": admission["sequence"],
            "qualification_admission_sha256": admission["entry_sha256"],
            "obligation_count": len(contexts),
            "obligation_ids": [item["obligation_id"] for item in contexts],
            "evidence_sha256s": [item["evidence_sha256"] for item in contexts],
            "interview_path": "qualification-question-round/interview.jsonl",
            "result_path": "qualification-question-round/question-round.json",
        },
        str(admission["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [request])
    state.update({
        "status": "waiting_for_model",
        "phase": "formulating_qualification_question_round",
        "waiting_for": "qualification-question-round/interview.jsonl",
        "question": None,
        "questions": [],
        "qualification_question_round": {
            "contract": qualification_question_round.CONTRACT,
            "admission_ledger_sequence": admission["sequence"],
            "admission_sha256": admission["entry_sha256"],
            "obligation_ids": [item["obligation_id"] for item in contexts],
            "evidence_sha256s": [item["evidence_sha256"] for item in contexts],
            "request_ledger_sequence": request_sequence,
        },
        "ledger_entries": request_sequence,
        "ledger_tail_sha256": request["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _qualification_question_round_model_result(state, work)


def _validate_qualification_question_round(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object] | None:
    admission, contexts, request_error = (
        _qualification_question_round_request_context(state, entries)
    )
    if request_error:
        return request_error
    assert admission is not None and contexts is not None
    saved = state["qualification_question_round"]
    assert isinstance(saved, dict)
    request_sequence = saved["request_ledger_sequence"]
    assert isinstance(request_sequence, int)
    try:
        result, interview_sha256, result_sha256 = (
            qualification_question_round.validate(
                work / "qualification-question-round",
                admission=admission,
                purpose=purpose,
            )
        )
        interview_entries = qualification_question_round._read_journal(
            work / "qualification-question-round" / "interview.jsonl"
        )
    except qualification_question_round.QuestionRoundError as error:
        return _blocked("invalid qualification question round", str(error))
    questions = result.get("questions")
    if not isinstance(questions, list) or len(questions) != len(contexts):
        return _blocked(
            "invalid qualification question round",
            (
                f"prepared questions {questions!r} do not cover all {len(contexts)} "
                "admitted obligations; preserve exactly one question per obligation"
            ),
        )
    for position, (question, context) in enumerate(
        zip(questions, contexts, strict=True), 1
    ):
        if (
            not isinstance(question, dict)
            or question.get("id")
            != f"qualification-clarification-answer-{position:06d}"
            or question.get("answers_obligation") != context["evidence"]
            or question.get("evidence_sha256") != context["evidence_sha256"]
            or question.get("answer_type")
            not in qualification_question_round.ANSWER_TYPES
            or not isinstance(question.get("asks"), str)
            or not str(question["asks"]).strip()
        ):
            return _blocked(
                "invalid qualification question round",
                (
                    f"question {position} value {question!r} is not the exact "
                    f"evidence-bound question for obligation {context['obligation_id']!r}; "
                    "restore its generated identity, enum answer type, wording, obligation, and evidence digest"
                ),
            )
    expected_completed = {
        "interview_path": "qualification-question-round/interview.jsonl",
        "interview_sha256": interview_sha256,
        "result_path": "qualification-question-round/question-round.json",
        "result_sha256": result_sha256,
        "question_count": len(questions),
        "interview_question_count": sum(
            entry["event"] == "question_asked" for entry in interview_entries
        ),
        "answer_count": sum(
            entry["event"] == "answer_recorded" for entry in interview_entries
        ),
        "rejected_answer_count": sum(
            entry["event"] == "answer_recorded" and entry["accepted"] is False
            for entry in interview_entries
        ),
        "questions": questions,
    }
    completed = entries[request_sequence] if len(entries) > request_sequence else None
    prepared = entries[request_sequence + 1] if len(entries) > request_sequence + 1 else None
    asked = entries[request_sequence + 2] if len(entries) > request_sequence + 2 else None
    if (
        len(entries) != request_sequence + 3
        or not isinstance(completed, dict)
        or completed.get("event") != "qualification_question_round_completed"
        or any(completed.get(key) != value for key, value in expected_completed.items())
        or not isinstance(prepared, dict)
        or prepared.get("event")
        != "operator_qualification_question_round_prepared"
        or prepared.get("question_count") != len(questions)
        or prepared.get("questions") != questions
        or not isinstance(asked, dict)
        or asked.get("event") != "operator_qualification_question_asked"
        or asked.get("question_position") != 1
        or asked.get("question") != questions[0]
        or saved.get("interview_sha256") != interview_sha256
        or saved.get("result_sha256") != result_sha256
        or state.get("status") != "needs_operator"
        or state.get("phase") != "awaiting_qualification_clarification_answers"
        or state.get("waiting_for") != questions[0]["id"]
        or state.get("question") != questions[0]
        or state.get("questions") != questions
        or state.get("ledger_entries") != len(entries)
        or state.get("ledger_tail_sha256") != entries[-1].get("entry_sha256")
    ):
        return _blocked(
            "invalid qualification question round",
            (
                "the completed question round, prepared full list, first active question, "
                "or ledger binding changed; restore the exact append-only recorded values"
            ),
        )
    return None


def _consume_qualification_question_round(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    admission, contexts, request_error = (
        _qualification_question_round_request_context(state, entries)
    )
    if request_error:
        return request_error
    assert admission is not None and contexts is not None
    saved = state["qualification_question_round"]
    assert isinstance(saved, dict)
    request_sequence = saved["request_ledger_sequence"]
    assert isinstance(request_sequence, int)
    if len(entries) != request_sequence:
        return _blocked(
            "invalid qualification question round",
            (
                f"request ledger position {request_sequence} is no longer the current tail "
                f"of {len(entries)} entries; preserve the exact append-only request"
            ),
        )
    try:
        result, interview_sha256, result_sha256 = (
            qualification_question_round.validate(
                work / "qualification-question-round",
                admission=admission,
                purpose=purpose,
            )
        )
        interview_entries = qualification_question_round._read_journal(
            work / "qualification-question-round" / "interview.jsonl"
        )
    except qualification_question_round.QuestionRoundError as error:
        return _blocked("invalid qualification question round", str(error))
    questions = result.get("questions")
    if not isinstance(questions, list) or not questions:
        return _blocked(
            "invalid qualification question round",
            (
                f"model result questions {questions!r} are invalid; preserve one "
                "evidence-bound question for every admitted obligation"
            ),
        )
    for position, (question, context) in enumerate(
        zip(questions, contexts, strict=True), 1
    ):
        if (
            not isinstance(question, dict)
            or question.get("id")
            != f"qualification-clarification-answer-{position:06d}"
            or question.get("answers_obligation") != context["evidence"]
            or question.get("evidence_sha256") != context["evidence_sha256"]
            or question.get("answer_type")
            not in qualification_question_round.ANSWER_TYPES
        ):
            return _blocked(
                "invalid qualification question round",
                (
                    f"question {position} value {question!r} changed; preserve the exact "
                    f"question for obligation {context['obligation_id']!r} and one allowed answer type"
                ),
            )
    timestamp = datetime.now(timezone.utc).isoformat()
    completed = _ledger_entry(
        request_sequence + 1,
        "qualification_question_round_completed",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "interview_path": "qualification-question-round/interview.jsonl",
            "interview_sha256": interview_sha256,
            "result_path": "qualification-question-round/question-round.json",
            "result_sha256": result_sha256,
            "question_count": len(questions),
            "interview_question_count": sum(
                entry["event"] == "question_asked" for entry in interview_entries
            ),
            "answer_count": sum(
                entry["event"] == "answer_recorded" for entry in interview_entries
            ),
            "rejected_answer_count": sum(
                entry["event"] == "answer_recorded" and entry["accepted"] is False
                for entry in interview_entries
            ),
            "questions": questions,
        },
        str(entries[-1]["entry_sha256"]),
    )
    prepared = _ledger_entry(
        request_sequence + 2,
        "operator_qualification_question_round_prepared",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "question_count": len(questions),
            "questions": questions,
        },
        str(completed["entry_sha256"]),
    )
    asked = _ledger_entry(
        request_sequence + 3,
        "operator_qualification_question_asked",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "question_position": 1,
            "question": questions[0],
        },
        str(prepared["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed, prepared, asked])
    state["qualification_question_round"].update({
        "interview_sha256": interview_sha256,
        "result_sha256": result_sha256,
    })
    state.update({
        "status": "needs_operator",
        "phase": "awaiting_qualification_clarification_answers",
        "waiting_for": questions[0]["id"],
        "question": questions[0],
        "questions": questions,
        "qualification_question_answers": [],
        "ledger_entries": request_sequence + 3,
        "ledger_tail_sha256": asked["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _qualification_question_round_operator_result(state, work)


def run_qualification_question_round(
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
        opening_bytes = opening.encode("utf-8")
    except OSError as error:
        return _blocked("qualification question round unavailable", str(error))
    state, entries, load_error = _load_bound(work, opening_bytes)
    if load_error:
        return load_error
    assert state is not None
    if state.get("phase") != "formulating_qualification_question_round":
        return _blocked(
            "qualification question round unavailable",
            (
                f"intake phase {state.get('phase')!r} is not waiting for question "
                "formulation; resume its preserved current boundary"
            ),
        )
    admission, _contexts, request_error = (
        _qualification_question_round_request_context(state, entries)
    )
    if request_error:
        return request_error
    assert admission is not None
    try:
        qualification_question_round.run(
            work / "qualification-question-round",
            admission=admission,
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except qualification_question_round.QuestionRoundError as error:
        return _blocked("qualification question round failed", str(error))
    state, entries, load_error = _load_bound(work, opening_bytes)
    if load_error:
        return load_error
    assert state is not None
    return _consume_qualification_question_round(
        work, state, entries, purpose
    )


SOURCE_COLLECTION_TERMINAL_PHASES = {
    "first_projection_recorded",
    "first_verbatim_projection_recorded",
    "first_pdf_projection_recorded",
    "first_pdf_projection_failed",
    "first_spreadsheet_projection_recorded",
    "first_spreadsheet_projection_failed",
    "additional_source_projection_recorded",
    "additional_spreadsheet_projection_failed",
}
SOURCE_COLLECTION_PHASES = {
    "awaiting_source_collection_decision",
    "awaiting_source_collection_kind",
    "awaiting_independent_source",
    "additional_source_frozen",
    "interviewing_additional_source_projection",
    "additional_source_projection_recorded",
    "additional_spreadsheet_projection_failed",
    "source_collection_complete",
    "source_set_qualification_complete",
    "qualification_admission_complete",
}


def _numbered_collection_question(
    template: dict[str, object], position: int
) -> dict[str, object]:
    return {**template, "id": f"{template['id']}-{position:06d}"}


def _source_collection_result(
    state: dict[str, object], work: Path, inventory: dict[str, object]
) -> dict[str, object]:
    return {
        "status": "source_collection_complete",
        "stopped": "source_collection_complete",
        "intake_id": state["intake_id"],
        "source_collection": state["source_collection"],
        "source_projection_closure": inventory,
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _source_collection_inventory(
    work: Path, entries: list[dict[str, object]]
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    inventory, error = _source_projection_closure_inventory(work, entries)
    if error:
        return None, error
    assert inventory is not None
    outcomes = inventory.get("outcomes")
    if not isinstance(outcomes, list):
        return None, _blocked(
            "source collection unavailable",
            "the source projection closure lost its ordered outcomes",
        )
    return inventory, None


def _offer_source_collection_decision(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    inventory, inventory_error = _source_collection_inventory(work, entries)
    if inventory_error:
        return inventory_error
    assert inventory is not None
    outcomes = inventory["outcomes"]
    assert isinstance(outcomes, list)
    pending = [
        str(item.get("source_id"))
        for item in outcomes
        if isinstance(item, dict) and item.get("outcome") not in {"projected", "failed"}
    ]
    if pending:
        return _blocked(
            "source collection decision unavailable",
            "complete or explicitly fail the pending projection for: "
            + ", ".join(pending),
        )
    collection = state.get("source_collection")
    position = (
        int(collection.get("decision_count", 0)) + 1
        if isinstance(collection, dict)
        else 1
    )
    question = _numbered_collection_question(
        SOURCE_COLLECTION_DECISION_QUESTION, position
    )
    asked = _ledger_entry(
        len(entries) + 1,
        "operator_question_asked",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "role": "source_collection_decision",
            "question": question,
            "source_projection_closure": inventory,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [asked])
    source_collection = {
        **(collection if isinstance(collection, dict) else {}),
        "mode": "independent_multi_source",
        "decision_count": position,
        "decision_question_ledger_sequence": asked["sequence"],
    }
    state.update({
        "status": "needs_operator",
        "phase": "awaiting_source_collection_decision",
        "waiting_for": question["id"],
        "question": question,
        "source_collection": source_collection,
        "ledger_entries": asked["sequence"],
        "ledger_tail_sha256": asked["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _operator_result(state, work)


def _validate_collection_question(
    state: dict[str, object],
    entries: list[dict[str, object]],
    *,
    phase: str,
    role: str,
    sequence_key: str,
) -> dict[str, object] | None:
    collection = state.get("source_collection")
    question = state.get("question")
    sequence = collection.get(sequence_key) if isinstance(collection, dict) else None
    if (
        state.get("status") != "needs_operator"
        or state.get("phase") != phase
        or not isinstance(question, dict)
        or state.get("waiting_for") != question.get("id")
        or not isinstance(sequence, int)
        or sequence < 1
        or sequence > len(entries)
    ):
        return _blocked(
            "invalid source collection state",
            "the active code-controlled source question changed",
        )
    asked = entries[sequence - 1]
    if (
        sequence != len(entries)
        or asked.get("event") != "operator_question_asked"
        or asked.get("role") != role
        or asked.get("question") != question
    ):
        return _blocked(
            "invalid source collection ledger",
            "the active source question lost its immutable ledger entry",
        )
    return None


def _answer_source_collection_decision(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    action: object,
) -> dict[str, object]:
    question_error = _validate_collection_question(
        state,
        entries,
        phase="awaiting_source_collection_decision",
        role="source_collection_decision",
        sequence_key="decision_question_ledger_sequence",
    )
    if question_error:
        return question_error
    inventory, inventory_error = _source_collection_inventory(work, entries)
    if inventory_error:
        return inventory_error
    assert inventory is not None and isinstance(inventory["outcomes"], list)
    decision = source_collection_decision.decide(action, inventory["outcomes"])
    if decision.get("accepted") is not True:
        return _blocked("invalid source collection decision", str(decision["why"]))
    question = state["question"]
    assert isinstance(question, dict)
    answered = _ledger_entry(
        len(entries) + 1,
        "operator_answer_recorded",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "role": "source_collection_decision",
            "answers_question": question["id"],
            "answer": action,
        },
        str(entries[-1]["entry_sha256"]),
    )
    if action == "finish_sources":
        declared = [
            item.get("source_id")
            for item in inventory["outcomes"]
            if isinstance(item, dict)
        ]
        closure = source_collection_closure.reconcile(
            declared, inventory["outcomes"]
        )
        if closure.get("complete") is not True:
            return _blocked("source collection incomplete", str(closure["why"]))
        completed = _ledger_entry(
            len(entries) + 2,
            "source_collection_completed",
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "intake_id": state["intake_id"],
                "decision_ledger_sequence": answered["sequence"],
                "source_ids": closure["source_ids"],
                "source_projection_closure": inventory,
            },
            str(answered["entry_sha256"]),
        )
        _append_ledger(work / "ledger.jsonl", [answered, completed])
        collection = state["source_collection"]
        assert isinstance(collection, dict)
        collection = {
            **collection,
            "status": "complete",
            "source_ids": closure["source_ids"],
            "completion_ledger_sequence": completed["sequence"],
        }
        state.update({
            "status": "source_collection_complete",
            "phase": "source_collection_complete",
            "waiting_for": None,
            "question": None,
            "source_collection": collection,
            "ledger_entries": completed["sequence"],
            "ledger_tail_sha256": completed["entry_sha256"],
        })
        _write_state(work / "intake-state.json", state)
        return _source_collection_result(state, work, inventory)

    collection = state["source_collection"]
    assert isinstance(collection, dict)
    position = int(collection["decision_count"])
    kind_question = _numbered_collection_question(
        SOURCE_COLLECTION_KIND_QUESTION, position
    )
    asked = _ledger_entry(
        len(entries) + 2,
        "operator_question_asked",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "role": "source_collection_kind",
            "question": kind_question,
        },
        str(answered["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [answered, asked])
    collection = {
        **collection,
        "kind_question_ledger_sequence": asked["sequence"],
    }
    state.update({
        "status": "needs_operator",
        "phase": "awaiting_source_collection_kind",
        "waiting_for": kind_question["id"],
        "question": kind_question,
        "source_collection": collection,
        "ledger_entries": asked["sequence"],
        "ledger_tail_sha256": asked["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _operator_result(state, work)


def _answer_source_collection_kind(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    kind: object,
) -> dict[str, object]:
    question_error = _validate_collection_question(
        state,
        entries,
        phase="awaiting_source_collection_kind",
        role="source_collection_kind",
        sequence_key="kind_question_ledger_sequence",
    )
    if question_error:
        return question_error
    if kind not in {"local_file", "url"}:
        return _blocked(
            "invalid source collection kind",
            "source kind must be exactly one of: local_file, url",
        )
    collection = state["source_collection"]
    assert isinstance(collection, dict)
    reservation = source_collection_reservation.reserve(
        [f"source-{number:06d}" for number in sorted(_known_source_numbers(entries))]
    )
    source_id = str(reservation["source_id"])
    question = state["question"]
    assert isinstance(question, dict)
    answered = _ledger_entry(
        len(entries) + 1,
        "operator_answer_recorded",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "role": "source_collection_kind",
            "answers_question": question["id"],
            "answer": kind,
        },
        str(entries[-1]["entry_sha256"]),
    )
    source_question = {
        "id": f"independent-{source_id}",
        "asks": "Please provide the next independent source for this intake.",
        "answer_type": kind,
        "answers_gap": {
            "kind": "independent_source_collection",
            "source_id": source_id,
        },
    }
    asked = _ledger_entry(
        len(entries) + 2,
        "operator_question_asked",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "role": "independent_source_collection",
            "question": source_question,
            "reservation": reservation,
        },
        str(answered["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [answered, asked])
    collection = {
        **collection,
        "source_kind": kind,
        "source_question_ledger_sequence": asked["sequence"],
        "reservation": reservation,
    }
    state.update({
        "status": "needs_operator",
        "phase": "awaiting_independent_source",
        "waiting_for": source_question["id"],
        "question": source_question,
        "source_collection": collection,
        "ledger_entries": asked["sequence"],
        "ledger_tail_sha256": asked["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _operator_result(state, work)


def _resume_source_collection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    source: Path | None,
    source_url: str | None,
    project_source: bool,
    begin: bool,
    action: str | None,
    kind: str | None,
) -> dict[str, object]:
    phase = str(state.get("phase"))
    if phase in SOURCE_COLLECTION_TERMINAL_PHASES and begin:
        if any(value is not None for value in (source, source_url, action, kind)) or project_source:
            return _blocked(
                "source collection invocation invalid",
                "begin source collection without answering its first question in the same call",
            )
        return _offer_source_collection_decision(work, state, entries)
    if phase == "awaiting_source_collection_decision":
        if begin or source is not None or source_url is not None or kind is not None or project_source:
            return _blocked(
                "source collection decision required",
                "answer only the current add_source or finish_sources question",
            )
        if action is None:
            error = _validate_collection_question(
                state,
                entries,
                phase=phase,
                role="source_collection_decision",
                sequence_key="decision_question_ledger_sequence",
            )
            return error or _operator_result(state, work)
        return _answer_source_collection_decision(work, state, entries, action)
    if phase == "awaiting_source_collection_kind":
        if begin or source is not None or source_url is not None or action is not None or project_source:
            return _blocked(
                "source collection kind required",
                "answer only the current local_file or url question",
            )
        if kind is None:
            error = _validate_collection_question(
                state,
                entries,
                phase=phase,
                role="source_collection_kind",
                sequence_key="kind_question_ledger_sequence",
            )
            return error or _operator_result(state, work)
        return _answer_source_collection_kind(work, state, entries, kind)
    if phase == "awaiting_independent_source":
        if begin or action is not None or kind is not None or project_source:
            return _blocked(
                "independent source required",
                "supply only the source requested by the current question",
            )
        collection = state.get("source_collection")
        question = state.get("question")
        sequence = (
            collection.get("source_question_ledger_sequence")
            if isinstance(collection, dict)
            else None
        )
        if (
            not isinstance(question, dict)
            or not isinstance(sequence, int)
            or sequence != len(entries)
            or entries[-1].get("event") != "operator_question_asked"
            or entries[-1].get("role") != "independent_source_collection"
            or entries[-1].get("question") != question
        ):
            return _blocked(
                "invalid source collection state",
                "the independent source request changed",
            )
        if source is None and source_url is None:
            return _operator_result(state, work)
        if source is not None and source_url is not None:
            return _blocked(
                "operator input type mismatch",
                "supply either one local file or one URL, not both",
            )
        lineage = {
            "mode": "independent_source_collection",
            "decision_question_ledger_sequence": collection["decision_question_ledger_sequence"],
            "source_kind_question_ledger_sequence": collection["kind_question_ledger_sequence"],
            "question_ledger_sequence": sequence,
        }
        if source_url is not None:
            return _acquire_additional_url(
                work, state, entries, source_url, question=question, lineage=lineage
            )
        assert source is not None
        return _acquire_additional_local_file(
            work, state, entries, source, question=question, lineage=lineage
        )
    if phase in {
        "additional_source_frozen",
        "interviewing_additional_source_projection",
        "additional_source_projection_recorded",
        "additional_spreadsheet_projection_failed",
    }:
        pending = state.get("pending_additional_source")
        lineage = pending.get("lineage") if isinstance(pending, dict) else None
        if not isinstance(lineage, dict) or lineage.get("mode") != "independent_source_collection":
            return _blocked(
                "invalid source collection state",
                "the pending source is not bound to independent source collection",
            )
        pending_error = _validate_pending_additional_source(
            work,
            state,
            entries,
            source,
            source_url,
            allow_projection=phase != "additional_source_frozen",
        )
        if pending_error:
            return pending_error
        if any(value is not None for value in (action, kind)) or begin:
            return _blocked(
                "source projection pending",
                "finish the current source projection before another collection decision",
            )
        if phase == "additional_source_frozen":
            if project_source:
                return _request_additional_projection(work, state, entries)
            return _additional_source_ready_result(state, work)
        if phase == "interviewing_additional_source_projection":
            request_error = _validate_additional_projection_request(work, state, entries)
            if request_error:
                return request_error
            if project_source or source is not None or source_url is not None:
                return _blocked(
                    "additional projection interview active",
                    "finish the current code-controlled projection interview",
                )
            active = state.get("active_additional_projection")
            paths = active.get("paths") if isinstance(active, dict) else None
            if not isinstance(paths, dict):
                return _blocked(
                    "invalid intake state", "the active projection paths are missing"
                )
            if not (work / str(paths["candidate_path"])).exists():
                return _additional_projection_waiting_result(state, work)
            return _consume_additional_projection(work, state, entries, purpose)
        if phase == "additional_source_projection_recorded":
            recorded_error = _validate_recorded_additional_projection(
                work, state, entries, purpose
            )
            if recorded_error:
                return recorded_error
        else:
            failure_error = _validate_spreadsheet_failure(
                work, state, entries, additional=True
            )
            if failure_error:
                return failure_error
        if project_source or source is not None or source_url is not None:
            return _blocked(
                "source projection complete",
                "resume once to receive the next source-collection decision",
            )
        return _offer_source_collection_decision(work, state, entries)
    if phase in {
        "source_collection_complete",
        "source_set_qualification_complete",
        "qualification_admission_complete",
    }:
        if any(
            value is not None for value in (source, source_url, action, kind)
        ) or project_source or begin:
            return _blocked(
                "source collection already complete",
                "the append-only source collection has already reached its terminal result",
            )
        if phase == "qualification_admission_complete":
            return run_qualification_admission(work)
        if phase == "source_set_qualification_complete":
            return run_source_set_qualification(work)
        inventory, inventory_error = _source_collection_inventory(work, entries)
        if inventory_error:
            return inventory_error
        assert inventory is not None
        collection = state.get("source_collection")
        sequence = (
            collection.get("completion_ledger_sequence")
            if isinstance(collection, dict)
            else None
        )
        if (
            not isinstance(sequence, int)
            or sequence != len(entries)
            or entries[-1].get("event") != "source_collection_completed"
            or entries[-1].get("source_ids") != collection.get("source_ids")
            or entries[-1].get("source_projection_closure") != inventory
        ):
            return _blocked(
                "invalid source collection ledger",
                "the completed source set changed",
            )
        return _source_collection_result(state, work, inventory)
    return _blocked(
        "source collection unavailable",
        "begin source collection only after a source has a terminal projection outcome",
    )


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
        3, supplied, resolved, stored_relative, content, media_type, media_type_basis
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


def _acquire_first_url(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    supplied_url: str,
) -> dict[str, object]:
    stored_relative = "sources/source-000003"
    stored_path = work / stored_relative
    if stored_path.exists():
        return _blocked(
            "unbound source artifact", "the first URL artifact already exists"
        )
    retrieval, content, retrieval_error = _fetch_public_url(supplied_url)
    if retrieval_error:
        return retrieval_error
    assert retrieval is not None and content is not None
    stored_path.write_bytes(content)
    media_type, media_type_basis = _url_media_type(retrieval, stored_path)
    source = _url_source_record(
        3,
        stored_relative,
        content,
        retrieval,
        media_type,
        media_type_basis,
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


def _headers_have_valid_shape(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, dict)
        and set(item) == {"name", "value"}
        and isinstance(item["name"], str)
        and isinstance(item["value"], str)
        for item in value
    )


def _public_address_evidence(value: object, connected: object) -> bool:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) for item in value)
        or not isinstance(connected, str)
        or connected not in value
    ):
        return False
    try:
        return all(
            ipaddress.ip_address(item.split("%", 1)[0]).is_global for item in value
        )
    except ValueError:
        return False


def _validate_url_source_record(
    source: dict[str, object],
    number: int,
    frozen: bytes,
    supplied_url: str | None,
) -> dict[str, object] | None:
    expected_keys = {
        "id", "kind", "adapter", "provided_url", "request_url", "final_url",
        "retrieved_at", "redirect_chain", "response", "filename", "stored_path",
        "size_bytes", "sha256", "media_type", "media_type_basis",
    }
    if (
        set(source) != expected_keys
        or source.get("id") != f"source-{number:06d}"
        or source.get("kind") != "url"
        or source.get("adapter") != {"name": "url", "version": URL_ADAPTER_VERSION}
        or source.get("stored_path") != f"sources/source-{number:06d}"
        or not all(
            isinstance(source.get(key), str) and bool(str(source[key]).strip())
            for key in (
                "provided_url", "request_url", "final_url", "retrieved_at",
                "filename", "sha256", "media_type", "media_type_basis",
            )
        )
        or source.get("size_bytes") != len(frozen)
        or source.get("sha256") != _digest_bytes(frozen)
        or len(str(source.get("sha256"))) != 64
        or "/" not in str(source.get("media_type"))
    ):
        return _blocked("invalid ledger", "the URL source record has an invalid shape")
    if supplied_url is not None and supplied_url != source.get("provided_url"):
        return _blocked(
            "source origin changed", "this intake is bound to a different supplied URL"
        )
    try:
        provided = urlsplit(str(source["provided_url"]))
        request = urlsplit(str(source["request_url"]))
        final = urlsplit(str(source["final_url"]))
        retrieved_at = datetime.fromisoformat(str(source["retrieved_at"]))
    except (ValueError, TypeError) as error:
        return _blocked("invalid ledger", f"the URL retrieval identity is invalid: {error}")
    if (
        provided.scheme.lower() not in {"http", "https"}
        or request.scheme.lower() not in {"http", "https"}
        or final.scheme.lower() not in {"http", "https"}
        or provided.hostname is None
        or request.hostname is None
        or final.hostname is None
        or provided.username is not None
        or provided.password is not None
        or request.username is not None
        or request.password is not None
        or final.username is not None
        or final.password is not None
        or request.fragment
        or final.fragment
        or str(source["request_url"])
        != _without_url_fragment(str(source["provided_url"]))
        or retrieved_at.tzinfo is None
    ):
        return _blocked("invalid ledger", "the URL retrieval identity changed")
    redirects = source.get("redirect_chain")
    if not isinstance(redirects, list) or len(redirects) > URL_MAX_REDIRECTS:
        return _blocked("invalid ledger", "the URL redirect trail changed")
    expected_request = str(source["request_url"])
    for redirect in redirects:
        if (
            not isinstance(redirect, dict)
            or set(redirect) != {
                "request_url", "status", "reason", "location", "next_url",
                "headers", "resolved_addresses", "connected_address",
            }
            or redirect.get("request_url") != expected_request
            or redirect.get("status") not in URL_REDIRECT_STATUSES
            or not isinstance(redirect.get("reason"), str)
            or not isinstance(redirect.get("location"), str)
            or not redirect.get("location")
            or redirect.get("next_url")
            != _without_url_fragment(
                urljoin(expected_request, str(redirect["location"]))
            )
            or not _headers_have_valid_shape(redirect.get("headers"))
            or not _public_address_evidence(
                redirect.get("resolved_addresses"),
                redirect.get("connected_address"),
            )
        ):
            return _blocked("invalid ledger", "the URL redirect trail changed")
        expected_request = str(redirect["next_url"])
    response = source.get("response")
    if (
        expected_request != source.get("final_url")
        or not isinstance(response, dict)
        or set(response) != {
            "status", "reason", "headers", "resolved_addresses",
            "connected_address",
        }
        or not isinstance(response.get("status"), int)
        or not 200 <= int(response["status"]) < 300
        or not isinstance(response.get("reason"), str)
        or not _headers_have_valid_shape(response.get("headers"))
        or not _public_address_evidence(
            response.get("resolved_addresses"), response.get("connected_address")
        )
    ):
        return _blocked("invalid ledger", "the final URL response evidence changed")
    return None


def _validate_frozen_first_source(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    supplied: Path | None,
    supplied_url: str | None = None,
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
    if source.get("adapter") == {"name": "url", "version": URL_ADAPTER_VERSION}:
        if supplied is not None:
            return _blocked(
                "source origin changed", "this intake is bound to a URL, not a local file"
            )
        if entries[6].get("answers_question") != FIRST_SOURCE_QUESTION["id"]:
            return _blocked(
                "invalid ledger", "the acquisition is not linked to the first-source question"
            )
        try:
            frozen = (work / str(source.get("stored_path"))).read_bytes()
        except OSError:
            return _blocked(
                "immutable source unavailable", "the frozen first URL source cannot be read"
            )
        return _validate_url_source_record(source, 3, frozen, supplied_url)
    if supplied_url is not None:
        return _blocked(
            "source origin changed", "this intake is bound to a local file, not a URL"
        )
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
    source_path = work / str(source["stored_path"])
    try:
        source_bytes = source_path.read_bytes()
    except OSError:
        return _blocked("immutable source unavailable", str(source_path))
    if spreadsheet_projection.is_workbook(
        Path(str(source.get("filename", source_path.name))),
        str(source.get("media_type", "")),
        source_bytes,
    ):
        return _create_spreadsheet_projection(
            work, state, entries, source, entries[6]["projection"]
        )
    if source.get("media_type") == "application/pdf":
        return _request_first_pdf_projection(work, state, entries, source)
    if not str(source["media_type"]).startswith("image/"):
        return _create_first_verbatim_utf8_projection(
            work, state, entries, source
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


def _spreadsheet_projection_record(
    source_id: str,
    projection_bytes: bytes,
    projected: dict[str, object],
) -> dict[str, object]:
    return {
        "id": f"projection-{source_id}-v1",
        "source_id": source_id,
        "version": 1,
        "path": f"projections/{source_id}-v1.json",
        "sha256": _digest_bytes(projection_bytes),
        "method": "spreadsheet_ooxml_v1",
        "coverage": projected["coverage"],
    }


def _spreadsheet_failure(
    source_id: str, reason: str
) -> dict[str, object]:
    return {
        "id": f"projection-{source_id}-v1",
        "source_id": source_id,
        "version": 1,
        "status": "failed",
        "path": None,
        "sha256": None,
        "method": "spreadsheet_ooxml_v1",
        "coverage": {
            "status": "failed",
            "source_units": None,
            "represented_units": 0,
            "gaps": [reason],
        },
    }


def _spreadsheet_result(
    state: dict[str, object], work: Path, *, additional: bool, failed: bool
) -> dict[str, object]:
    pending = state.get("pending_additional_source")
    source = (
        pending.get("source")
        if additional and isinstance(pending, dict)
        else state["first_source"]
    )
    projection = (
        state["additional_source_projection"]
        if additional
        else state["first_projection"]
    )
    result = {
        "status": "ready_for_projection" if failed else "ready_for_projection_assessment",
        "stopped": (
            "additional_spreadsheet_projection_failed"
            if additional and failed
            else "additional_source_projection_recorded"
            if additional
            else "first_spreadsheet_projection_failed"
            if failed
            else "first_spreadsheet_projection_recorded"
        ),
        "intake_id": state["intake_id"],
        "source": source,
        "projection": projection,
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }
    if additional and isinstance(pending, dict):
        result["reserved_projection"] = pending["projection"]
        result["lineage"] = pending["lineage"]
    return result


def _create_spreadsheet_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    source: dict[str, object],
    reservation: object,
    *,
    pending: dict[str, object] | None = None,
) -> dict[str, object]:
    additional = pending is not None
    source_id = str(source["id"])
    source_path = work / str(source["stored_path"])
    try:
        source_bytes = source_path.read_bytes()
    except OSError:
        return _blocked("immutable source unavailable", str(source_path))
    if _digest_bytes(source_bytes) != source.get("sha256"):
        return _blocked(
            "immutable source changed",
            "the frozen spreadsheet changed before projection",
        )
    try:
        projected = spreadsheet_projection.project(source_bytes)
    except spreadsheet_projection.SpreadsheetProjectionError as error:
        failure = _spreadsheet_failure(source_id, str(error))
        failed = _ledger_entry(
            len(entries) + 1,
            "projection_conversion_failed",
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "intake_id": state["intake_id"],
                "source_id": source_id,
                "source_sha256": source["sha256"],
                "adapter": {
                    "name": "spreadsheet_ooxml_v1",
                    "version": spreadsheet_projection.ADAPTER_VERSION,
                },
                "reserved_projection": reservation,
                "failure": failure,
            },
            str(entries[-1]["entry_sha256"]),
        )
        _append_ledger(work / "ledger.jsonl", [failed])
        state.update(
            {
                "status": "ready_for_projection",
                "phase": (
                    "additional_spreadsheet_projection_failed"
                    if additional
                    else "first_spreadsheet_projection_failed"
                ),
                "waiting_for": None,
                "question": None,
                (
                    "additional_source_projection"
                    if additional
                    else "first_projection"
                ): failure,
                "spreadsheet_projection_completion": {
                    "role": "spreadsheet_ooxml_projection_failure",
                    "ledger_sequence": failed["sequence"],
                },
                "ledger_entries": failed["sequence"],
                "ledger_tail_sha256": failed["entry_sha256"],
            }
        )
        _write_state(work / "intake-state.json", state)
        return _spreadsheet_result(
            state, work, additional=additional, failed=True
        )
    projection_bytes = spreadsheet_projection.canonical_bytes(projected)
    projection = _spreadsheet_projection_record(
        source_id, projection_bytes, projected
    )
    reserved_id = reservation.get("id") if isinstance(reservation, dict) else None
    if isinstance(reserved_id, str) and projection["id"] != reserved_id:
        return _blocked(
            "invalid ledger",
            "the spreadsheet projection does not fill its reserved identity",
        )
    projection_path = work / str(projection["path"])
    if projection_path.exists():
        return _blocked(
            "unbound projection artifact",
            f"the spreadsheet projection already exists outside the ledger: {projection['path']}",
        )
    projection_path.write_bytes(projection_bytes)
    payload: dict[str, object] = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "intake_id": state["intake_id"],
        "attempt": 1,
        "role": "spreadsheet_ooxml_projection",
        "source_id": source_id,
        "source_sha256": source["sha256"],
        "reserved_projection": reservation,
        "projection": projection,
    }
    if additional:
        assert pending is not None
        payload.update(
            {
                "answers_question": pending["question"]["id"],
                "answers_gap": pending["question"]["answers_gap"],
                "lineage": pending["lineage"],
            }
        )
    created = _ledger_entry(
        len(entries) + 1,
        "projection_version_created",
        payload,
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [created])
    completion = {
        "role": "spreadsheet_ooxml_projection",
        "source_id": source_id,
        "source_sha256": source["sha256"],
        "projection_sha256": projection["sha256"],
        "reserved_projection": reservation,
        "ledger_sequence": created["sequence"],
    }
    if additional:
        assert pending is not None
        completion["lineage"] = pending["lineage"]
    state.update(
        {
            "status": "ready_for_projection_assessment",
            "phase": (
                "additional_source_projection_recorded"
                if additional
                else "first_spreadsheet_projection_recorded"
            ),
            "waiting_for": None,
            "question": None,
            (
                "additional_source_projection"
                if additional
                else "first_projection"
            ): projection,
            "spreadsheet_projection_completion": completion,
            "ledger_entries": created["sequence"],
            "ledger_tail_sha256": created["entry_sha256"],
        }
    )
    if additional:
        state["additional_projection_completion"] = completion
    _write_state(work / "intake-state.json", state)
    return _spreadsheet_result(
        state, work, additional=additional, failed=False
    )


def _validate_spreadsheet_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    *,
    additional: bool,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    pending = state.get("pending_additional_source")
    source = (
        pending.get("source")
        if additional and isinstance(pending, dict)
        else state.get("first_source")
    )
    projection = state.get(
        "additional_source_projection" if additional else "first_projection"
    )
    completion = state.get(
        "additional_projection_completion"
        if additional
        else "spreadsheet_projection_completion"
    )
    if not all(
        isinstance(item, dict) for item in (source, projection, completion)
    ):
        return _blocked(
            "invalid spreadsheet projection",
            "the source, projection, or completion identity is missing",
        )
    assert isinstance(source, dict)
    assert isinstance(projection, dict)
    assert isinstance(completion, dict)
    sequence = completion.get("ledger_sequence")
    if (
        not isinstance(sequence, int)
        or sequence < 1
        or sequence > len(entries)
        or (not allow_later_phase and sequence != len(entries))
    ):
        return _blocked(
            "invalid spreadsheet projection", "the ledger sequence changed"
        )
    try:
        source_bytes = (work / str(source["stored_path"])).read_bytes()
        projected = spreadsheet_projection.project(source_bytes)
        expected_bytes = spreadsheet_projection.canonical_bytes(projected)
        actual_bytes = (work / str(projection["path"])).read_bytes()
    except (OSError, spreadsheet_projection.SpreadsheetProjectionError) as error:
        return _blocked("immutable spreadsheet projection unavailable", str(error))
    expected = _spreadsheet_projection_record(
        str(source["id"]), expected_bytes, projected
    )
    reservation = (
        pending.get("projection")
        if additional and isinstance(pending, dict)
        else entries[6].get("projection")
    )
    expected_completion: dict[str, object] = {
        "role": "spreadsheet_ooxml_projection",
        "source_id": source["id"],
        "source_sha256": source["sha256"],
        "projection_sha256": expected["sha256"],
        "reserved_projection": reservation,
        "ledger_sequence": sequence,
    }
    if additional and isinstance(pending, dict):
        expected_completion["lineage"] = pending["lineage"]
    created = entries[sequence - 1]
    if (
        _digest_bytes(source_bytes) != source.get("sha256")
        or actual_bytes != expected_bytes
        or projection != expected
        or completion != expected_completion
        or created.get("event") != "projection_version_created"
        or created.get("attempt") != 1
        or created.get("role") != "spreadsheet_ooxml_projection"
        or created.get("source_id") != source.get("id")
        or created.get("source_sha256") != source.get("sha256")
        or created.get("reserved_projection") != reservation
        or created.get("projection") != projection
        or (
            additional
            and isinstance(pending, dict)
            and (
                created.get("answers_question") != pending["question"]["id"]
                or created.get("answers_gap")
                != pending["question"]["answers_gap"]
                or created.get("lineage") != pending["lineage"]
            )
        )
    ):
        return _blocked(
            "immutable spreadsheet projection changed",
            "the readable projection no longer matches its source and ledger",
        )
    return None


def _validate_spreadsheet_failure(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    *,
    additional: bool,
) -> dict[str, object] | None:
    pending = state.get("pending_additional_source")
    source = (
        pending.get("source")
        if additional and isinstance(pending, dict)
        else state.get("first_source")
    )
    failure = state.get(
        "additional_source_projection" if additional else "first_projection"
    )
    if not isinstance(source, dict) or not isinstance(failure, dict):
        return _blocked(
            "invalid spreadsheet projection failure", "the failure identity is missing"
        )
    try:
        source_bytes = (work / str(source["stored_path"])).read_bytes()
        spreadsheet_projection.project(source_bytes)
    except OSError as error:
        return _blocked("immutable source unavailable", str(error))
    except spreadsheet_projection.SpreadsheetProjectionError as error:
        expected = _spreadsheet_failure(str(source["id"]), str(error))
    else:
        return _blocked(
            "invalid spreadsheet projection failure",
            "the preserved source now produces a readable projection",
        )
    failed = entries[-1]
    reservation = (
        pending.get("projection")
        if additional and isinstance(pending, dict)
        else entries[6].get("projection")
    )
    if (
        _digest_bytes(source_bytes) != source.get("sha256")
        or failure != expected
        or failed.get("event") != "projection_conversion_failed"
        or failed.get("source_id") != source.get("id")
        or failed.get("source_sha256") != source.get("sha256")
        or failed.get("adapter")
        != {
            "name": "spreadsheet_ooxml_v1",
            "version": spreadsheet_projection.ADAPTER_VERSION,
        }
        or failed.get("reserved_projection") != reservation
        or failed.get("failure") != failure
        or state.get("status") != "ready_for_projection"
    ):
        return _blocked(
            "invalid spreadsheet projection failure",
            "the recorded failure changed",
        )
    return None


def _request_first_pdf_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    source: dict[str, object],
) -> dict[str, object]:
    source_id = str(source["id"])
    output_root = work / "pdf-projections" / f"{source_id}-v1"
    try:
        prepared = pdf_projection.prepare(
            work / str(source["stored_path"]),
            output_root,
            source_id=source_id,
            source_sha256=str(source["sha256"]),
        )
    except pdf_projection.PDFProjectionError as error:
        if output_root.exists():
            return _blocked("unbound PDF projection artifacts", str(error))
        failure = {
            "id": f"projection-{source_id}-v1",
            "source_id": source_id,
            "version": 1,
            "status": "failed",
            "path": None,
            "sha256": None,
            "method": "pdf_visible_pages",
            "coverage": {
                "status": "failed",
                "source_units": None,
                "represented_units": 0,
                "gaps": [str(error)],
            },
        }
        failed = _ledger_entry(
            len(entries) + 1,
            "projection_conversion_failed",
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "intake_id": state["intake_id"],
                "source_id": source_id,
                "source_sha256": source["sha256"],
                "adapter": {
                    "name": "pdf_visible_pages",
                    "version": pdf_projection.ADAPTER_VERSION,
                },
                "reserved_projection": entries[6]["projection"],
                "failure": failure,
            },
            str(entries[-1]["entry_sha256"]),
        )
        _append_ledger(work / "ledger.jsonl", [failed])
        state.update({
            "status": "ready_for_projection",
            "phase": "first_pdf_projection_failed",
            "waiting_for": None,
            "question": None,
            "first_projection": failure,
            "ledger_entries": failed["sequence"],
            "ledger_tail_sha256": failed["entry_sha256"],
        })
        _write_state(work / "intake-state.json", state)
        return _pdf_projection_failed_result(state, work)
    eighth = _ledger_entry(
        len(entries) + 1,
        "pdf_projection_started",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "source_id": source_id,
            "source_sha256": source["sha256"],
            "reserved_projection": entries[6]["projection"],
            "interview_contract": PROJECTION_INTERVIEW_CONTRACT,
            "prepared": prepared,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [eighth])
    state.update({
        "status": "waiting_for_model",
        "phase": "interviewing_pdf_page_projection",
        "waiting_for": _pdf_page_paths(source_id, 1)["interview_path"],
        "question": None,
        "projection_interview_contract": PROJECTION_INTERVIEW_CONTRACT,
        "pdf_projection": {
            "prepared": prepared,
            "active_page": 1,
            "completed_pages": [],
            "start_ledger_sequence": eighth["sequence"],
        },
        "ledger_entries": eighth["sequence"],
        "ledger_tail_sha256": eighth["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _pdf_projection_waiting_result(state, work, "project")


def _first_verbatim_projection_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "first_verbatim_projection_recorded",
        "intake_id": state["intake_id"],
        "source": state["first_source"],
        "projection": state["first_projection"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _create_first_verbatim_utf8_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    source: dict[str, object],
) -> dict[str, object]:
    source_id = str(source["id"])
    source_path = work / str(source["stored_path"])
    projection = _verbatim_utf8_projection_record(source_id, str(source["sha256"]))
    projection_path = work / str(projection["path"])
    if projection_path.exists():
        return _blocked(
            "unbound projection artifact",
            f"the verbatim projection already exists outside the ledger: {projection['path']}",
        )
    try:
        frozen = source_path.read_bytes()
    except OSError:
        return _blocked("immutable source unavailable", str(source_path))
    projection_bytes, projection_error = _verbatim_utf8_bytes(frozen)
    if projection_error:
        return projection_error
    assert projection_bytes is not None
    if _digest_bytes(projection_bytes) != source["sha256"]:
        return _blocked(
            "immutable source changed",
            "the frozen first source changed before verbatim projection",
        )
    projection_path.write_bytes(projection_bytes)
    projection_sha256 = _digest_bytes(projection_bytes)
    created = _ledger_entry(
        len(entries) + 1,
        "projection_version_created",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": 1,
            "role": "verbatim_utf8_projection",
            "source_id": source_id,
            "source_sha256": source["sha256"],
            "reserved_projection": entries[6]["projection"],
            "projection": projection,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [created])
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "first_verbatim_projection_recorded",
        "waiting_for": None,
        "question": None,
        "first_projection": projection,
        "ledger_entries": len(entries) + 1,
        "ledger_tail_sha256": created["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _first_verbatim_projection_ready_result(state, work)


def _validate_first_verbatim_utf8_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object] | None:
    if len(entries) != 8:
        return _blocked(
            "invalid ledger", "the first verbatim projection ledger length changed"
        )
    source = state.get("first_source")
    projection = state.get("first_projection")
    created = entries[7]
    if not isinstance(source, dict) or not isinstance(projection, dict):
        return _blocked(
            "invalid intake state", "the first verbatim projection identity is missing"
        )
    expected_projection = _verbatim_utf8_projection_record(
        str(source.get("id")), str(source.get("sha256"))
    )
    try:
        source_bytes = (work / str(source["stored_path"])).read_bytes()
        projection_bytes = (work / str(expected_projection["path"])).read_bytes()
    except OSError:
        return _blocked(
            "immutable projection unavailable", str(expected_projection["path"])
        )
    _, utf8_error = _verbatim_utf8_bytes(source_bytes)
    if utf8_error:
        return _blocked("invalid ledger", str(utf8_error["why"]))
    if (
        projection != expected_projection
        or source_bytes != projection_bytes
        or _digest_bytes(source_bytes) != source.get("sha256")
        or created.get("event") != "projection_version_created"
        or created.get("attempt") != 1
        or created.get("role") != "verbatim_utf8_projection"
        or created.get("source_id") != source.get("id")
        or created.get("source_sha256") != source.get("sha256")
        or created.get("reserved_projection") != entries[6].get("projection")
        or created.get("projection") != projection
        or state.get("status") != "ready_for_projection_assessment"
        or state.get("phase") != "first_verbatim_projection_recorded"
        or state.get("waiting_for") is not None
        or state.get("question") is not None
        or state.get("ledger_entries") != len(entries)
        or state.get("ledger_tail_sha256") != created.get("entry_sha256")
    ):
        return _blocked(
            "invalid ledger", "the first verbatim UTF-8 projection changed"
        )
    return None


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


def _consume_pdf_page_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    page = _active_pdf_page(state)
    saved = state.get("pdf_projection")
    if page is None or not isinstance(saved, dict):
        return _blocked("invalid PDF projection state", "the active PDF page is missing")
    page_number = int(page["page"])
    paths = _pdf_page_paths(str(saved["prepared"]["source_id"]), page_number)
    attempt_dir = work / paths["interview_dir"]
    try:
        projection, interview_sha256, candidate_sha256 = projection_interview.validate(
            attempt_dir,
            source_sha256=str(page["render_sha256"]),
            purpose=purpose,
            contract=PROJECTION_INTERVIEW_CONTRACT,
        )
        interview_entries = projection_interview._read_journal(
            attempt_dir / "interview.jsonl"
        )
    except projection_interview.InterviewError as error:
        return _blocked("invalid PDF page projection interview", str(error))
    verification_dir = work / paths["verification_dir"]
    if not (verification_dir / "verification.json").exists():
        return _pdf_projection_waiting_result(state, work, "verify")
    try:
        verification, verification_journal_sha256, verification_result_sha256 = (
            relationship_verification.validate(
                verification_dir,
                candidate_path=work / paths["candidate_path"],
                candidate_sha256=candidate_sha256,
                purpose=purpose,
            )
        )
    except relationship_verification.VerificationError as error:
        return _blocked("invalid PDF page relationship verification", str(error))
    corrections: dict[str, object] | None = None
    correction_journal_sha256: str | None = None
    correction_result_sha256: str | None = None
    correction_candidate_sha256: str | None = None
    correction_verification: dict[str, object] | None = None
    correction_verification_journal_sha256: str | None = None
    correction_verification_result_sha256: str | None = None
    rejected_count = sum(
        verdict["verdict"] != "supported" for verdict in verification["verdicts"]
    )
    if rejected_count:
        correction_dir = work / paths["correction_dir"]
        if not (correction_dir / "corrections.json").exists():
            return _pdf_projection_waiting_result(state, work, "correct")
        try:
            (
                corrections,
                correction_journal_sha256,
                correction_result_sha256,
                correction_candidate_sha256,
            ) = relationship_correction.validate(
                correction_dir,
                candidate_path=work / paths["candidate_path"],
                candidate_sha256=candidate_sha256,
                verification_path=work / paths["verification_path"],
                verification_sha256=verification_result_sha256,
                purpose=purpose,
            )
        except relationship_correction.CorrectionError as error:
            return _blocked("invalid PDF page relationship correction", str(error))
        proposed_count = sum(
            item["action"] == "propose_replacement_endpoint"
            for item in corrections["corrections"]
        )
        if proposed_count:
            correction_verification_dir = work / paths["correction_verification_dir"]
            if not (correction_verification_dir / "verification.json").exists():
                return _pdf_projection_waiting_result(state, work, "verify_correction")
            try:
                (
                    correction_verification,
                    correction_verification_journal_sha256,
                    correction_verification_result_sha256,
                ) = relationship_verification.validate(
                    correction_verification_dir,
                    candidate_path=work / paths["correction_candidate_path"],
                    candidate_sha256=str(correction_candidate_sha256),
                    purpose=purpose,
                )
            except relationship_verification.VerificationError as error:
                return _blocked(
                    "invalid PDF page relationship correction verification", str(error)
                )
    verification_error = _apply_independent_verification(
        projection, verification, corrections, correction_verification
    )
    if verification_error:
        return verification_error
    projection_path = work / paths["projection_path"]
    if projection_path.exists():
        return _blocked(
            "unbound PDF page projection artifact", paths["projection_path"]
        )
    projection_bytes = (
        json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    projection_path.write_bytes(projection_bytes)
    projection_sha256 = _digest_bytes(projection_bytes)
    gap_count = sum(item["status"] == "gap" for item in projection["elements"])
    gap_count += sum(item["status"] == "gap" for item in projection["relationships"])
    gap_count += sum(
        item["status"] == "gap" for item in projection.get("scan_regions", [])
    )
    page_projection = {
        "id": f"projection-{saved['prepared']['source_id']}-v1-page-{page_number:06d}",
        "page": page_number,
        "path": paths["projection_path"],
        "sha256": projection_sha256,
        "element_count": len(projection["elements"]),
        "relationship_count": len(projection["relationships"]),
        "gap_count": gap_count,
        "gap_inventory": _pdf_page_gap_inventory(
            projection,
            page=page_number,
            page_projection_path=paths["projection_path"],
            page_projection_sha256=projection_sha256,
            render_path=str(page["render_path"]),
            render_sha256=str(page["render_sha256"]),
        ),
        "coverage": "unassessed",
    }
    completed = _ledger_entry(
        len(entries) + 1,
        "pdf_page_projection_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "source_id": saved["prepared"]["source_id"],
            "source_sha256": saved["prepared"]["source_sha256"],
            "page": page_number,
            "render": page,
            "interview_contract": PROJECTION_INTERVIEW_CONTRACT,
            "interview_path": paths["interview_path"],
            "interview_sha256": interview_sha256,
            "candidate_path": paths["candidate_path"],
            "candidate_sha256": candidate_sha256,
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
            "verification_path": paths["verification_path"],
            "verification_journal_sha256": verification_journal_sha256,
            "verification_result_sha256": verification_result_sha256,
            "correction_path": paths["correction_path"] if corrections is not None else None,
            "correction_journal_sha256": correction_journal_sha256,
            "correction_result_sha256": correction_result_sha256,
            "correction_candidate_sha256": correction_candidate_sha256,
            "correction_verification_path": (
                paths["correction_verification_path"]
                if correction_verification is not None else None
            ),
            "correction_verification_journal_sha256": (
                correction_verification_journal_sha256
            ),
            "correction_verification_result_sha256": (
                correction_verification_result_sha256
            ),
            "projection": page_projection,
        },
        str(entries[-1]["entry_sha256"]),
    )
    completed_pages = [*saved["completed_pages"], page_projection]
    page_count = int(saved["prepared"]["page_count"])
    if page_number < page_count:
        _append_ledger(work / "ledger.jsonl", [completed])
        saved.update({
            "active_page": page_number + 1,
            "completed_pages": completed_pages,
        })
        state.update({
            "waiting_for": _pdf_page_paths(
                str(saved["prepared"]["source_id"]), page_number + 1
            )["interview_path"],
            "ledger_entries": completed["sequence"],
            "ledger_tail_sha256": completed["entry_sha256"],
        })
        _write_state(work / "intake-state.json", state)
        return _pdf_projection_waiting_result(state, work, "project")
    manifest = {
        "schema_version": 1,
        "method": "pdf_visible_pages",
        "source_id": saved["prepared"]["source_id"],
        "source_sha256": saved["prepared"]["source_sha256"],
        "page_count": page_count,
        "renderer": saved["prepared"]["renderer"],
        "gap_inventory": [
            gap
            for completed_page in completed_pages
            for gap in completed_page["gap_inventory"]
        ],
        "pages": [
            {
                "page": prepared_page["page"],
                "render": prepared_page,
                "readable_projection": completed_pages[index],
            }
            for index, prepared_page in enumerate(saved["prepared"]["pages"])
        ],
    }
    manifest_path = work / "projections" / "source-000003-v1.json"
    if manifest_path.exists():
        return _blocked("unbound projection artifact", str(manifest_path))
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    manifest_path.write_bytes(manifest_bytes)
    projection_record = {
        "id": "projection-source-000003-v1",
        "source_id": "source-000003",
        "version": 1,
        "path": "projections/source-000003-v1.json",
        "sha256": _digest_bytes(manifest_bytes),
        "method": "pdf_visible_pages",
        "page_count": page_count,
        "element_count": sum(int(item["element_count"]) for item in completed_pages),
        "relationship_count": sum(
            int(item["relationship_count"]) for item in completed_pages
        ),
        "gap_count": sum(int(item["gap_count"]) for item in completed_pages),
        "coverage": {
            "status": "complete",
            "source_units": page_count,
            "represented_units": page_count,
            "gaps": [
                f"page {item['page']}: {item['gap_count']} explicit projection gaps"
                for item in completed_pages
                if int(item["gap_count"]) > 0
            ],
        },
    }
    created = _ledger_entry(
        completed["sequence"] + 1,
        "projection_version_created",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": 1,
            "role": "pdf_visible_pages_projection",
            "source_id": "source-000003",
            "source_sha256": saved["prepared"]["source_sha256"],
            "reserved_projection": entries[6]["projection"],
            "projection": projection_record,
        },
        str(completed["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed, created])
    saved.update({
        "active_page": None,
        "completed_pages": completed_pages,
        "manifest_sha256": projection_record["sha256"],
    })
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "first_pdf_projection_recorded",
        "waiting_for": None,
        "first_projection": projection_record,
        "ledger_entries": created["sequence"],
        "ledger_tail_sha256": created["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _pdf_projection_ready_result(state, work)


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


def _validate_pdf_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    source = state.get("first_source")
    saved = state.get("pdf_projection")
    if (
        not isinstance(source, dict)
        or source.get("media_type") != "application/pdf"
        or not isinstance(saved, dict)
        or len(entries) < 8
    ):
        return _blocked("invalid PDF projection state", "the PDF projection identity is missing")
    prepared = saved.get("prepared")
    start = entries[7]
    if (
        start.get("event") != "pdf_projection_started"
        or start.get("source_id") != source.get("id")
        or start.get("source_sha256") != source.get("sha256")
        or start.get("reserved_projection") != entries[6].get("projection")
        or start.get("interview_contract") != PROJECTION_INTERVIEW_CONTRACT
        or start.get("prepared") != prepared
        or saved.get("start_ledger_sequence") != 8
    ):
        return _blocked("invalid PDF projection ledger", "the PDF preparation record changed")
    try:
        pdf_projection.validate_prepared(work, prepared)
    except pdf_projection.PDFProjectionError as error:
        return _blocked("immutable PDF rendering changed", str(error))
    assert isinstance(prepared, dict)
    prepared_pages = prepared["pages"]
    completed_pages = saved.get("completed_pages")
    if not isinstance(prepared_pages, list) or not isinstance(completed_pages, list):
        return _blocked("invalid PDF projection state", "the PDF page inventory changed")
    if len(completed_pages) > len(prepared_pages):
        return _blocked("invalid PDF projection state", "too many PDF pages were recorded")
    expected_completed: list[dict[str, object]] = []
    for index, page in enumerate(prepared_pages[: len(completed_pages)], start=1):
        if not isinstance(page, dict):
            return _blocked("invalid PDF projection state", f"PDF page {index} changed")
        ledger_index = 7 + index
        if ledger_index >= len(entries):
            return _blocked("invalid PDF projection ledger", f"PDF page {index} is missing")
        entry = entries[ledger_index]
        paths = _pdf_page_paths(str(source["id"]), index)
        try:
            projection, interview_sha256, candidate_sha256 = projection_interview.validate(
                work / paths["interview_dir"],
                source_sha256=str(page["render_sha256"]),
                purpose=purpose,
                contract=PROJECTION_INTERVIEW_CONTRACT,
            )
            interview_entries = projection_interview._read_journal(
                work / paths["interview_path"]
            )
            verification, verification_journal_sha256, verification_result_sha256 = (
                relationship_verification.validate(
                    work / paths["verification_dir"],
                    candidate_path=work / paths["candidate_path"],
                    candidate_sha256=candidate_sha256,
                    purpose=purpose,
                )
            )
        except (
            projection_interview.InterviewError,
            relationship_verification.VerificationError,
        ) as error:
            return _blocked("invalid PDF page projection", f"page {index}: {error}")
        corrections: dict[str, object] | None = None
        correction_journal_sha256: str | None = None
        correction_result_sha256: str | None = None
        correction_candidate_sha256: str | None = None
        correction_verification: dict[str, object] | None = None
        correction_verification_journal_sha256: str | None = None
        correction_verification_result_sha256: str | None = None
        if any(
            verdict["verdict"] != "supported" for verdict in verification["verdicts"]
        ):
            try:
                (
                    corrections,
                    correction_journal_sha256,
                    correction_result_sha256,
                    correction_candidate_sha256,
                ) = relationship_correction.validate(
                    work / paths["correction_dir"],
                    candidate_path=work / paths["candidate_path"],
                    candidate_sha256=candidate_sha256,
                    verification_path=work / paths["verification_path"],
                    verification_sha256=verification_result_sha256,
                    purpose=purpose,
                )
            except relationship_correction.CorrectionError as error:
                return _blocked("invalid PDF page correction", f"page {index}: {error}")
            if any(
                item["action"] == "propose_replacement_endpoint"
                for item in corrections["corrections"]
            ):
                try:
                    (
                        correction_verification,
                        correction_verification_journal_sha256,
                        correction_verification_result_sha256,
                    ) = relationship_verification.validate(
                        work / paths["correction_verification_dir"],
                        candidate_path=work / paths["correction_candidate_path"],
                        candidate_sha256=str(correction_candidate_sha256),
                        purpose=purpose,
                    )
                except relationship_verification.VerificationError as error:
                    return _blocked(
                        "invalid PDF page correction verification",
                        f"page {index}: {error}",
                    )
        verification_error = _apply_independent_verification(
            projection, verification, corrections, correction_verification
        )
        if verification_error:
            return verification_error
        canonical = json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        try:
            accepted_bytes = (work / paths["projection_path"]).read_bytes()
        except OSError:
            return _blocked("immutable PDF page projection unavailable", paths["projection_path"])
        gap_count = sum(item["status"] == "gap" for item in projection["elements"])
        gap_count += sum(item["status"] == "gap" for item in projection["relationships"])
        gap_count += sum(
            item["status"] == "gap" for item in projection.get("scan_regions", [])
        )
        expected_projection = {
            "id": f"projection-{source['id']}-v1-page-{index:06d}",
            "page": index,
            "path": paths["projection_path"],
            "sha256": _digest_bytes(canonical),
            "element_count": len(projection["elements"]),
            "relationship_count": len(projection["relationships"]),
            "gap_count": gap_count,
            "gap_inventory": _pdf_page_gap_inventory(
                projection,
                page=index,
                page_projection_path=paths["projection_path"],
                page_projection_sha256=_digest_bytes(canonical),
                render_path=str(page["render_path"]),
                render_sha256=str(page["render_sha256"]),
            ),
            "coverage": "unassessed",
        }
        expected_audit = {
            "event": "pdf_page_projection_completed",
            "source_id": source["id"],
            "source_sha256": source["sha256"],
            "page": index,
            "render": page,
            "interview_contract": PROJECTION_INTERVIEW_CONTRACT,
            "interview_path": paths["interview_path"],
            "interview_sha256": interview_sha256,
            "candidate_path": paths["candidate_path"],
            "candidate_sha256": candidate_sha256,
            "question_count": sum(
                item["event"] == "question_asked" for item in interview_entries
            ),
            "answer_count": sum(
                item["event"] == "answer_recorded" for item in interview_entries
            ),
            "rejected_answer_count": sum(
                item["event"] == "answer_recorded" and item["accepted"] is False
                for item in interview_entries
            ),
            "verification_path": paths["verification_path"],
            "verification_journal_sha256": verification_journal_sha256,
            "verification_result_sha256": verification_result_sha256,
            "correction_path": paths["correction_path"] if corrections is not None else None,
            "correction_journal_sha256": correction_journal_sha256,
            "correction_result_sha256": correction_result_sha256,
            "correction_candidate_sha256": correction_candidate_sha256,
            "correction_verification_path": (
                paths["correction_verification_path"]
                if correction_verification is not None else None
            ),
            "correction_verification_journal_sha256": (
                correction_verification_journal_sha256
            ),
            "correction_verification_result_sha256": (
                correction_verification_result_sha256
            ),
            "projection": expected_projection,
        }
        if (
            accepted_bytes != canonical
            or completed_pages[index - 1] != expected_projection
            or any(entry.get(key) != value for key, value in expected_audit.items())
        ):
            return _blocked(
                "immutable PDF page projection changed", f"PDF page {index} changed"
            )
        expected_completed.append(expected_projection)
    terminal = (
        len(expected_completed) == len(prepared_pages)
        and saved.get("active_page") is None
    )
    expected_ledger_length = 8 + len(expected_completed) + (1 if terminal else 0)
    if len(entries) < expected_ledger_length or (
        not allow_later_phase and len(entries) != expected_ledger_length
    ):
        return _blocked("invalid PDF projection ledger", "the PDF ledger length changed")
    if not terminal:
        active_page = len(expected_completed) + 1
        if (
            active_page > len(prepared_pages)
            or saved.get("active_page") != active_page
            or state.get("status") != "waiting_for_model"
            or state.get("waiting_for")
            != _pdf_page_paths(str(source["id"]), active_page)["interview_path"]
            or state.get("first_projection") is not None
        ):
            return _blocked("invalid PDF projection state", "the active PDF page changed")
        return None
    if len(expected_completed) != len(prepared_pages) or saved.get("active_page") is not None:
        return _blocked("invalid PDF projection state", "PDF completion lost a page")
    manifest = {
        "schema_version": 1,
        "method": "pdf_visible_pages",
        "source_id": source["id"],
        "source_sha256": source["sha256"],
        "page_count": len(prepared_pages),
        "renderer": prepared["renderer"],
        "gap_inventory": [
            gap
            for completed_page in expected_completed
            for gap in completed_page["gap_inventory"]
        ],
        "pages": [
            {
                "page": page["page"],
                "render": page,
                "readable_projection": expected_completed[index],
            }
            for index, page in enumerate(prepared_pages)
        ],
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        actual_manifest = (work / "projections/source-000003-v1.json").read_bytes()
    except OSError:
        return _blocked("immutable PDF projection unavailable", "the PDF manifest is missing")
    projection_record = {
        "id": "projection-source-000003-v1",
        "source_id": "source-000003",
        "version": 1,
        "path": "projections/source-000003-v1.json",
        "sha256": _digest_bytes(manifest_bytes),
        "method": "pdf_visible_pages",
        "page_count": len(prepared_pages),
        "element_count": sum(int(item["element_count"]) for item in expected_completed),
        "relationship_count": sum(
            int(item["relationship_count"]) for item in expected_completed
        ),
        "gap_count": sum(int(item["gap_count"]) for item in expected_completed),
        "coverage": {
            "status": "complete",
            "source_units": len(prepared_pages),
            "represented_units": len(prepared_pages),
            "gaps": [
                f"page {item['page']}: {item['gap_count']} explicit projection gaps"
                for item in expected_completed
                if int(item["gap_count"]) > 0
            ],
        },
    }
    created = entries[expected_ledger_length - 1]
    if (
        actual_manifest != manifest_bytes
        or saved.get("manifest_sha256") != projection_record["sha256"]
        or state.get("first_projection") != projection_record
        or (
            not allow_later_phase
            and state.get("status") != "ready_for_projection_assessment"
        )
        or (not allow_later_phase and state.get("waiting_for") is not None)
        or created.get("event") != "projection_version_created"
        or created.get("role") != "pdf_visible_pages_projection"
        or created.get("source_id") != source["id"]
        or created.get("source_sha256") != source["sha256"]
        or created.get("reserved_projection") != entries[6].get("projection")
        or created.get("projection") != projection_record
    ):
        return _blocked("immutable PDF projection changed", "the PDF manifest changed")
    return None


def _validate_pdf_projection_failure(
    state: dict[str, object], entries: list[dict[str, object]]
) -> dict[str, object] | None:
    source = state.get("first_source")
    failure = state.get("first_projection")
    if (
        len(entries) != 8
        or not isinstance(source, dict)
        or source.get("media_type") != "application/pdf"
        or not isinstance(failure, dict)
        or entries[7].get("event") != "projection_conversion_failed"
        or entries[7].get("source_id") != source.get("id")
        or entries[7].get("source_sha256") != source.get("sha256")
        or entries[7].get("adapter")
        != {"name": "pdf_visible_pages", "version": pdf_projection.ADAPTER_VERSION}
        or entries[7].get("reserved_projection") != entries[6].get("projection")
        or entries[7].get("failure") != failure
        or failure.get("id") != "projection-source-000003-v1"
        or failure.get("source_id") != "source-000003"
        or failure.get("version") != 1
        or failure.get("status") != "failed"
        or failure.get("path") is not None
        or failure.get("sha256") is not None
        or failure.get("method") != "pdf_visible_pages"
        or not isinstance(failure.get("coverage"), dict)
        or failure["coverage"].get("status") != "failed"
        or failure["coverage"].get("represented_units") != 0
        or not isinstance(failure["coverage"].get("gaps"), list)
        or len(failure["coverage"]["gaps"]) != 1
        or not isinstance(failure["coverage"]["gaps"][0], str)
        or not failure["coverage"]["gaps"][0]
        or state.get("status") != "ready_for_projection"
        or state.get("waiting_for") is not None
    ):
        return _blocked("invalid PDF projection failure", "the recorded failure changed")
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
    single_region: bool | None = None,
    expected_region_id: str | None = None,
    expected_obligation_id: str | None = None,
    expected_endpoint_evidence_sha256: str | None = None,
    region_binding_required: bool = False,
) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(encoding="utf-8")
        purpose = (work / "sources" / "source-000002.txt").read_text(encoding="utf-8")
    except OSError as error:
        return _blocked("interview context unavailable", str(error))
    current = drive(work, opening, purpose)
    if current.get("status") == "ready_for_projection_assessment":
        return current
    if current.get("status") != "waiting_for_model" or current.get("stopped") not in {
        "interviewing_first_projection",
        "interviewing_additional_source_projection",
    }:
        return _blocked("projection interview unavailable", json.dumps(current, sort_keys=True))
    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    entries, ledger_error = _validate_ledger(work / "ledger.jsonl")
    if ledger_error:
        return _blocked("invalid ledger", ledger_error)
    pdf_page = state.get("phase") == "interviewing_pdf_page_projection"
    additional = state.get("phase") == "interviewing_additional_source_projection"
    if pdf_page:
        page = _active_pdf_page(state)
        saved = state.get("pdf_projection")
        if page is None or not isinstance(saved, dict):
            return _blocked("projection interview unavailable", "the PDF page context is missing")
        paths = _pdf_page_paths(str(saved["prepared"]["source_id"]), int(page["page"]))
        source = {"sha256": page["render_sha256"]}
        source_path = work / str(page["render_path"])
        attempt_dir = work / paths["interview_dir"]
        contract = PROJECTION_INTERVIEW_CONTRACT
    elif additional:
        pending = state.get("pending_additional_source")
        active = state.get("active_additional_projection")
        if not isinstance(pending, dict) or not isinstance(active, dict):
            return _blocked("projection interview unavailable", "the additional projection context is missing")
        source = pending.get("source")
        paths = active.get("paths")
        request_sequence = active.get("request_ledger_sequence")
        if (
            not isinstance(source, dict)
            or not isinstance(paths, dict)
            or not isinstance(request_sequence, int)
        ):
            return _blocked("projection interview unavailable", "the additional projection context changed")
        attempt_dir = work / str(paths["interview_dir"])
        source_path = work / str(source["stored_path"])
        contract = int(entries[request_sequence - 1]["interview_contract"])
    else:
        source = state["first_source"]
        assert isinstance(source, dict)
        source_path = work / str(source["stored_path"])
        attempt_dir = work / "projection-interviews" / "attempt-000001"
        contract = int(entries[7]["interview_contract"])
    if expected_region_id is not None and expected_obligation_id is not None:
        return _blocked(
            "projection invocation invalid",
            "one command cannot bind both a region and a relationship obligation",
        )
    if expected_endpoint_evidence_sha256 is not None and (
        expected_obligation_id is None or expected_region_id is not None
    ):
        return _blocked(
            "projection invocation invalid",
            (
                "a fresh endpoint crop must remain bound to exactly one "
                "pending relationship obligation"
            ),
        )
    if (
        region_binding_required
        and contract >= 4
        and expected_region_id is None
        and expected_obligation_id is None
    ):
        return _blocked(
            "projection invocation invalid",
            "the generated command lost its active projection binding",
        )
    if expected_region_id is not None or expected_obligation_id is not None:
        try:
            journal = projection_interview._read_journal(
                attempt_dir / "interview.jsonl"
            )
            interview_state, _pending, _completed = projection_interview._replay(
                journal, purpose=purpose, contract=contract,
            )
            active_region = projection_interview._active_scan_region(
                interview_state
            )
            active_obligation = projection_interview._pending_obligation(
                interview_state
            )
        except projection_interview.InterviewError as error:
            return _blocked("projection invocation invalid", str(error))
        if expected_region_id is not None and (
            not isinstance(active_region, dict)
            or active_region.get("id") != expected_region_id
        ):
            return _blocked(
                "projection region invocation expired",
                (
                    f"the command was bound to {expected_region_id}, which is no "
                    "longer the active projection region"
                ),
            )
        if expected_obligation_id is not None and (
            active_region is not None
            or not isinstance(active_obligation, dict)
            or active_obligation.get("id") != expected_obligation_id
        ):
            return _blocked(
                "projection relationship invocation expired",
                (
                    f"the command was bound to {expected_obligation_id}, which "
                    "is no longer the next pending relationship obligation"
                ),
            )
        if expected_endpoint_evidence_sha256 is not None:
            evidence = interview_state.get("current", {}).get(
                "endpoint_crop_evidence"
            )
            if (
                not isinstance(evidence, dict)
                or not projection_interview._valid_endpoint_evidence(
                    interview_state, evidence,
                )
                or evidence.get("crop_sha256")
                != expected_endpoint_evidence_sha256
            ):
                return _blocked(
                    "projection endpoint verification invocation expired",
                    (
                        "the command is no longer bound to the active exact "
                        "endpoint crop"
                    ),
                )
    try:
        projection_interview.run(
            attempt_dir,
            source_sha256=str(source["sha256"]),
            purpose=purpose,
            contract=contract,
            input_fn=input_fn,
            output_fn=output_fn,
            stop_after_relationship=expected_obligation_id is not None,
            stop_after_endpoint_verification=(
                expected_endpoint_evidence_sha256 is not None
            ),
        )
        if expected_endpoint_evidence_sha256 is not None:
            return {
                "status": "waiting_for_model",
                "stopped": "projection_endpoint_verification_step_complete",
                "completed_obligation_id": expected_obligation_id,
                "endpoint_evidence_sha256": expected_endpoint_evidence_sha256,
                "work": str(work.resolve()),
                "ledger": str((work / "ledger.jsonl").resolve()),
            }
        if expected_obligation_id is not None:
            return {
                "status": "waiting_for_model",
                "stopped": "projection_relationship_step_complete",
                "completed_obligation_id": expected_obligation_id,
                "work": str(work.resolve()),
                "ledger": str((work / "ledger.jsonl").resolve()),
            }
        stop_after_region = input_fn is None if single_region is None else single_region
        while not stop_after_region and not (attempt_dir / "projection.json").exists():
            projection_interview.prepare_endpoint_evidence(
                attempt_dir,
                source_path=source_path,
                source_sha256=str(source["sha256"]),
                purpose=purpose,
                contract=contract,
            )
            projection_interview.prepare_region_evidence(
                attempt_dir,
                source_path=source_path,
                source_sha256=str(source["sha256"]),
                purpose=purpose,
                contract=contract,
            )
            projection_interview.run(
                attempt_dir,
                source_sha256=str(source["sha256"]),
                purpose=purpose,
                contract=contract,
                input_fn=input_fn,
                output_fn=output_fn,
            )
    except projection_interview.InterviewError as error:
        return _blocked("projection interview failed", str(error))
    if expected_region_id is not None:
        return {
            "status": "waiting_for_model",
            "stopped": "projection_region_step_complete",
            "completed_region_id": expected_region_id,
            "work": str(work.resolve()),
            "ledger": str((work / "ledger.jsonl").resolve()),
        }
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
        state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return _blocked("verification context unavailable", str(error))
    active = state.get("active_additional_projection")
    pdf_page = state.get("phase") == "interviewing_pdf_page_projection"
    additional = state.get("phase") == "interviewing_additional_source_projection"
    if pdf_page:
        page = _active_pdf_page(state)
        saved = state.get("pdf_projection")
        if page is None or not isinstance(saved, dict):
            return _blocked("verification context unavailable", "the PDF page context is missing")
        paths = _pdf_page_paths(str(saved["prepared"]["source_id"]), int(page["page"]))
        candidate_path = work / paths["candidate_path"]
        verification_dir = work / paths["verification_dir"]
    elif additional:
        if not isinstance(active, dict) or not isinstance(active.get("paths"), dict):
            return _blocked("verification context unavailable", "the additional projection context is missing")
        paths = active["paths"]
        candidate_path = work / str(paths["candidate_path"])
        verification_dir = work / str(paths["verification_dir"])
    else:
        candidate_path = work / "projection-interviews" / "attempt-000001" / "projection.json"
        verification_dir = work / "projection-verifications" / "attempt-000001"
    try:
        candidate_bytes = candidate_path.read_bytes()
    except OSError as error:
        return _blocked("verification context unavailable", str(error))
    current = drive(work, opening, purpose)
    if current.get("status") == "ready_for_projection_assessment":
        return current
    if current.get("status") != "waiting_for_model" or current.get("stopped") not in {
        "verifying_first_projection",
        "verifying_additional_source_projection",
    }:
        return _blocked("relationship verification unavailable", json.dumps(current, sort_keys=True))
    try:
        relationship_verification.run(
            verification_dir,
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
        state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return _blocked("correction context unavailable", str(error))
    active = state.get("active_additional_projection")
    pdf_page = state.get("phase") == "interviewing_pdf_page_projection"
    additional = state.get("phase") == "interviewing_additional_source_projection"
    if pdf_page:
        page = _active_pdf_page(state)
        saved = state.get("pdf_projection")
        if page is None or not isinstance(saved, dict):
            return _blocked("correction context unavailable", "the PDF page context is missing")
        paths = _pdf_page_paths(str(saved["prepared"]["source_id"]), int(page["page"]))
        candidate_path = work / paths["candidate_path"]
        verification_path = work / paths["verification_path"]
        correction_dir = work / paths["correction_dir"]
    elif additional:
        if not isinstance(active, dict) or not isinstance(active.get("paths"), dict):
            return _blocked("correction context unavailable", "the additional projection context is missing")
        paths = active["paths"]
        candidate_path = work / str(paths["candidate_path"])
        verification_path = work / str(paths["verification_path"])
        correction_dir = work / str(paths["correction_dir"])
    else:
        candidate_path = work / "projection-interviews" / "attempt-000001" / "projection.json"
        verification_path = work / "projection-verifications" / "attempt-000001" / "verification.json"
        correction_dir = work / "relationship-corrections" / "attempt-000001"
    try:
        candidate_bytes = candidate_path.read_bytes()
        verification_bytes = verification_path.read_bytes()
    except OSError as error:
        return _blocked("correction context unavailable", str(error))
    current = drive(work, opening, purpose)
    if current.get("status") == "ready_for_projection_assessment":
        return current
    if current.get("status") != "waiting_for_model" or current.get("stopped") not in {
        "correcting_rejected_relationships",
        "correcting_additional_source_relationships",
    }:
        return _blocked("relationship correction unavailable", json.dumps(current, sort_keys=True))
    try:
        relationship_correction.run(
            correction_dir,
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
        state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return _blocked("correction verification context unavailable", str(error))
    active = state.get("active_additional_projection")
    pdf_page = state.get("phase") == "interviewing_pdf_page_projection"
    additional = state.get("phase") == "interviewing_additional_source_projection"
    if pdf_page:
        page = _active_pdf_page(state)
        saved = state.get("pdf_projection")
        if page is None or not isinstance(saved, dict):
            return _blocked(
                "correction verification context unavailable",
                "the PDF page context is missing",
            )
        paths = _pdf_page_paths(str(saved["prepared"]["source_id"]), int(page["page"]))
        candidate_path = work / paths["correction_candidate_path"]
        correction_verification_dir = work / paths["correction_verification_dir"]
    elif additional:
        if not isinstance(active, dict) or not isinstance(active.get("paths"), dict):
            return _blocked("correction verification context unavailable", "the additional projection context is missing")
        paths = active["paths"]
        candidate_path = work / str(paths["correction_candidate_path"])
        correction_verification_dir = work / str(paths["correction_verification_dir"])
    else:
        candidate_path = work / "relationship-corrections" / "attempt-000001" / "verification-candidate.json"
        correction_verification_dir = work / "relationship-correction-verifications" / "attempt-000001"
    try:
        candidate_bytes = candidate_path.read_bytes()
    except OSError as error:
        return _blocked("correction verification context unavailable", str(error))
    current = drive(work, opening, purpose)
    if current.get("status") == "ready_for_projection_assessment":
        return current
    if current.get("status") != "waiting_for_model" or current.get("stopped") not in {
        "verifying_relationship_corrections",
        "verifying_additional_source_relationship_corrections",
    }:
        return _blocked(
            "relationship correction verification unavailable",
            json.dumps(current, sort_keys=True),
        )
    try:
        relationship_verification.run(
            correction_verification_dir,
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
        gaps = gap_clarification.require_gaps(projection, projection_sha256)
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return _blocked("gap question round unavailable", str(error))
    round_dir = work / "gap-question-rounds" / "round-000001"
    if round_dir.exists():
        return _blocked(
            "unbound gap question round",
            "gap question round artifacts already exist outside the ledger",
        )
    request_sequence = len(entries) + 1
    request = _ledger_entry(
        request_sequence,
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
            "contract": gap_clarification.ROUND_CONTRACT,
            "projection_sha256": projection_sha256,
            "gap_count": len(gaps),
            "gaps": gaps,
            "request_ledger_sequence": request_sequence,
        },
        "ledger_entries": request_sequence,
        "ledger_tail_sha256": request["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_question_round_model_result(state, work)


def _validate_gap_question_round_request(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> tuple[Path | None, str | None, dict[str, object] | None]:
    saved = state.get("gap_question_round")
    request_sequence = (
        saved.get("request_ledger_sequence") if isinstance(saved, dict) else None
    )
    if (
        not isinstance(request_sequence, int)
        or request_sequence < 1
        or len(entries) < request_sequence
        or entries[request_sequence - 1].get("event")
        != "model_gap_question_round_requested"
    ):
        return None, None, _blocked(
            "invalid ledger", "the gap question round request is missing"
        )
    request = entries[request_sequence - 1]
    projection_path, projection_sha256, projection_error = _projection_for_gap(
        work, state
    )
    if projection_error:
        return None, None, projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        gaps = gap_clarification.require_gaps(projection, projection_sha256)
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return None, None, _blocked("invalid gap question round", str(error))
    contract = request.get("contract")
    if contract not in gap_clarification.SUPPORTED_ROUND_CONTRACTS:
        return None, None, _blocked(
            "invalid gap question round", "the question-round contract is unsupported"
        )
    expected = {
        "round": 1,
        "contract": contract,
        "projection_path": str(state["first_projection"]["path"]),
        "projection_sha256": projection_sha256,
        "gap_count": len(gaps),
        "gaps": gaps,
        "interview_path": "gap-question-rounds/round-000001/interview.jsonl",
        "result_path": "gap-question-rounds/round-000001/clarification-round.json",
    }
    if (
        any(request.get(key) != value for key, value in expected.items())
        or not isinstance(saved, dict)
        or saved.get("contract", 1) != contract
        or any(saved.get(key) != value for key, value in {
            "round": 1,
            "projection_sha256": projection_sha256,
            "gap_count": len(gaps),
            "gaps": gaps,
            "request_ledger_sequence": request_sequence,
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
    contract: int = gap_clarification.ROUND_CONTRACT,
) -> str | None:
    if contract not in gap_clarification.SUPPORTED_ROUND_CONTRACTS:
        return "the question-round contract is unsupported"
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
        expected_gap = gap_clarification.gap_binding(gap)
        if not isinstance(question, dict) or question.get("answers_gap") != expected_gap:
            return "a question is not bound to its code-selected gap"
        allowed_answer_types = (
            {"operator_text", "local_file", "url"}
            if contract >= 3
            else {"operator_text", "local_file"}
        )
        if contract >= 2 and question.get("answer_type") not in allowed_answer_types:
            return "a question does not have one code-controlled answer type"
        if contract == 1 and "answer_type" in question:
            return "a legacy question gained an unsupported answer type"
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
    saved = state["gap_question_round"]
    assert isinstance(saved, dict)
    contract = saved.get("contract", 1)
    request_sequence = saved.get("request_ledger_sequence")
    if not isinstance(contract, int):
        return _blocked(
            "invalid gap question round", "the question-round contract is invalid"
        )
    round_dir = work / "gap-question-rounds" / "round-000001"
    try:
        result, journal_sha256, result_sha256 = gap_clarification.validate_round(
            round_dir,
            projection_path=projection_path,
            projection_sha256=projection_sha256,
            purpose=purpose,
            contract=contract,
        )
        journal_entries = gap_clarification._read_journal(
            round_dir / "interview.jsonl"
        )
    except gap_clarification.ClarificationError as error:
        return _blocked("invalid gap question round", str(error))
    gaps = saved["gaps"]
    assert isinstance(gaps, list)
    shape_error = _validate_question_round_shape(
        result, gaps, contract=contract
    )
    if shape_error:
        return _blocked("invalid gap question round", shape_error)
    timestamp = datetime.now(timezone.utc).isoformat()
    request_sequence = saved.get("request_ledger_sequence")
    if not isinstance(request_sequence, int) or len(entries) != request_sequence:
        return _blocked(
            "invalid gap question round",
            "the question-round request sequence changed",
        )
    completed = _ledger_entry(
        request_sequence + 1,
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
        request_sequence + 2,
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
        request_sequence + 3,
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
        "ledger_entries": request_sequence + 3,
        "ledger_tail_sha256": first_asked["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _gap_question_round_operator_result(state, work)


def _used_assessment_identities(state: dict[str, object]) -> set[tuple[int, int]]:
    used: set[tuple[int, int]] = set()
    history = state.get("gap_resolution_history", [])
    candidates = history if isinstance(history, list) else []
    current = state.get("gap_resolution")
    if isinstance(current, dict) and current.get("result_sha256"):
        candidates = [*candidates, current]
    for item in candidates:
        if isinstance(item, dict) and isinstance(
            item.get("selected_assessment_position"), int
        ):
            round_number = item.get("selected_assessment_round", 1)
            if isinstance(round_number, int):
                used.add((round_number, item["selected_assessment_position"]))
    admissions = state.get("operator_text_element_gap_admissions", [])
    if isinstance(admissions, list):
        for admission in admissions:
            if not isinstance(admission, dict):
                continue
            round_number = admission.get("assessment_round")
            position = admission.get("assessment_position")
            if isinstance(round_number, int) and isinstance(position, int):
                used.add((round_number, position))
    return used


def _prepared_round_snapshot(
    state: dict[str, object], round_number: int
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    history = state.get("prepared_question_round_history", [])
    if not isinstance(history, list) or not all(
        isinstance(item, dict) for item in history
    ):
        return None, None, _blocked(
            "invalid intake state",
            "the prepared question round history must remain an ordered list",
        )
    candidates: list[tuple[dict[str, object], dict[str, object]]] = []
    current_round = state.get("follow_up_gap_question_round")
    current_interview = state.get("prepared_question_round_interview")
    if isinstance(current_round, dict) and current_round.get("round") == round_number:
        if not isinstance(current_interview, dict):
            return None, None, _blocked(
                "invalid intake state",
                f"prepared round {round_number} lost its operator interview",
            )
        candidates.append((current_round, current_interview))
    previous_archived_round: int | None = None
    for item in history:
        prepared = item.get("question_round")
        interview = item.get("interview")
        archived_round = item.get("round")
        if (
            not isinstance(archived_round, int)
            or archived_round < 2
            or (
                previous_archived_round is not None
                and archived_round != previous_archived_round + 1
            )
            or not isinstance(prepared, dict)
            or not isinstance(interview, dict)
            or prepared.get("round") != archived_round
            or interview.get("round") != archived_round
            or set(item) != {"round", "question_round", "interview"}
        ):
            return None, None, _blocked(
                "invalid intake state",
                "the prepared question round history changed or lost canonical order",
            )
        previous_archived_round = archived_round
        if archived_round == round_number:
            candidates.append((prepared, interview))
    if len(candidates) != 1:
        return None, None, _blocked(
            "invalid intake state",
            f"prepared round {round_number} must have exactly one preserved snapshot",
        )
    return candidates[0][0], candidates[0][1], None


def _prepared_question_round_assessment_bindings_for_round(
    work: Path, state: dict[str, object], round_number: int
) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    prepared, interview, snapshot_error = _prepared_round_snapshot(
        state, round_number
    )
    if snapshot_error:
        return None, snapshot_error
    assert prepared is not None and interview is not None
    shadow = dict(state)
    shadow["follow_up_gap_question_round"] = prepared
    shadow["prepared_question_round_interview"] = interview
    return _prepared_question_round_assessment_bindings(work, shadow)


def _latest_assessed_round(
    work: Path, state: dict[str, object]
) -> tuple[
    int | None,
    list[dict[str, object]] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    records = state.get("prepared_question_round_assessments", [])
    if not isinstance(records, list) or not all(
        isinstance(item, dict) for item in records
    ):
        return None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "the prepared-round assessment history must remain an ordered list",
        )
    previous_round: int | None = None
    for item in records:
        round_number = item.get("round")
        if (
            not isinstance(round_number, int)
            or round_number < 2
            or (
                previous_round is not None
                and round_number != previous_round + 1
            )
        ):
            return None, None, None, _blocked(
                "follow-up gap clarification unavailable",
                "the prepared-round assessment history changed or lost canonical order",
            )
        previous_round = round_number
    if records:
        latest = records[-1]
        round_number = latest["round"]
        if (
            not isinstance(latest.get("result_sha256"), str)
            or not isinstance(latest.get("assessments"), list)
        ):
            return None, None, None, _blocked(
                "follow-up gap clarification unavailable",
                f"round {round_number} does not have one completed assessment",
            )
        bindings, binding_error = (
            _prepared_question_round_assessment_bindings_for_round(
                work, state, round_number
            )
        )
        return round_number, bindings, latest, binding_error
    bindings, binding_error = _gap_answer_assessment_bindings(work, state)
    saved = state.get("gap_answer_assessment")
    if binding_error:
        return None, None, None, binding_error
    if not isinstance(saved, dict) or not isinstance(saved.get("result_sha256"), str):
        return None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "the first completed assessment is missing",
        )
    return 1, bindings, saved, None


def _consumed_assessment_identities(
    resolutions: list[dict[str, object]],
) -> tuple[set[tuple[int, int]] | None, str | None]:
    consumed: dict[tuple[int, int], dict[str, object]] = {}
    for resolution in resolutions:
        if resolution.get("mode") != "assessed_answer":
            continue
        round_number = resolution.get("selected_assessment_round", 1)
        position = resolution.get("selected_assessment_position")
        if not isinstance(round_number, int) or not isinstance(position, int):
            return None, "an assessed-answer resolution lost its round and position"
        identity = (round_number, position)
        previous = consumed.get(identity)
        if previous is None:
            consumed[identity] = resolution
            continue
        retry_of = resolution.get("retry_of")
        if (
            not isinstance(retry_of, dict)
            or retry_of.get("attempt") != previous.get("attempt")
            or retry_of.get("candidate_sha256")
            != previous.get("candidate_sha256")
            or retry_of.get("resolution_result_sha256")
            != previous.get("result_sha256")
            or retry_of.get("verification_result_sha256")
            != previous.get("verification_result_sha256")
            or retry_of.get("verification_verdict")
            != previous.get("verification_verdict")
            or retry_of.get("verification_reason")
            != previous.get("verification_reason")
            or previous.get("verification_verdict")
            not in {"not_supported", "unreadable"}
            or resolution.get("accepted_assessment_sha256")
            != previous.get("accepted_assessment_sha256")
            or resolution.get("operator_answer_source_sha256")
            != previous.get("operator_answer_source_sha256")
            or resolution.get("operator_answer_projection_sha256")
            != previous.get("operator_answer_projection_sha256")
        ):
            return None, "an assessed answer was consumed more than once"
        consumed[identity] = resolution
    return set(consumed), None


def _retryable_rejected_resolution(
    work: Path,
    state: dict[str, object],
    parent: dict[str, object],
    current_by_identity: dict[tuple[object, object], dict[str, object]],
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    history = state.get("gap_resolution_history", [])
    if not isinstance(history, list) or not all(
        isinstance(item, dict) for item in history
    ):
        return None, None, _blocked(
            "clarification continuation unavailable",
            "gap resolution history must remain an ordered list",
        )
    resolutions = list(history)
    current = state.get("gap_resolution")
    if isinstance(current, dict):
        resolutions.append(current)
    retried_attempts = {
        retry_of["attempt"]
        for item in resolutions
        if isinstance((retry_of := item.get("retry_of")), dict)
        and isinstance(retry_of.get("attempt"), int)
    }
    for rejected in resolutions:
        attempt = rejected.get("attempt")
        terminal_phase = (
            rejected.get("terminal_phase")
            if rejected is not current
            else state.get("phase")
        )
        if (
            rejected.get("mode") != "assessed_answer"
            or terminal_phase != "gap_resolution_rejected"
            or rejected.get("verification_verdict")
            not in {"not_supported", "unreadable"}
            or not isinstance(attempt, int)
            or attempt in retried_attempts
            or isinstance(rejected.get("retry_of"), dict)
        ):
            continue
        gap_id = rejected.get("gap_id")
        current_gap = current_by_identity.get(("relationships", gap_id))
        if current_gap is None:
            continue
        round_number = rejected.get("selected_assessment_round", 1)
        position = rejected.get("selected_assessment_position")
        if (
            not isinstance(round_number, int)
            or round_number < 1
            or not isinstance(position, int)
        ):
            return None, None, _blocked(
                "clarification continuation unavailable",
                f"rejected attempt {attempt} lost its assessed-answer identity",
            )
        _, assessment, binding_error = _assessed_binding_at_position(
            work, state, round_number, position, parent
        )
        if binding_error:
            return None, None, binding_error
        assert assessment is not None
        expected_assessment_sha256 = _digest_bytes(
            json.dumps(assessment, sort_keys=True, separators=(",", ":")).encode()
        )
        if rejected.get("accepted_assessment_sha256") != expected_assessment_sha256:
            return None, None, _blocked(
                "clarification continuation unavailable",
                f"rejected attempt {attempt} no longer matches its accepted assessment",
            )
        decision = {
            "decision": "retry_rejected_resolution",
            "rejected_attempt": attempt,
            "assessment_round": round_number,
            "assessment_position": position,
            "gap": {
                key: current_gap[key]
                for key in (
                    "projection_sha256",
                    "collection",
                    "kind",
                    "id",
                    "record_sha256",
                )
            },
        }
        return rejected, decision, None
    return None, None, None


def _clarification_continuation(
    work: Path, state: dict[str, object]
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    latest_round, latest_bindings, latest_assessment, latest_error = (
        _latest_assessed_round(work, state)
    )
    if latest_error:
        return None, latest_error
    assert latest_round is not None and latest_bindings is not None
    assert latest_assessment is not None
    parent = state.get("current_projection", state.get("first_projection"))
    projection_path, projection_sha256, projection_error = (
        _validated_projection_record(work, parent if isinstance(parent, dict) else None)
    )
    if projection_error:
        return None, projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        current_gaps = gap_clarification.select_gaps(
            projection, projection_sha256
        )
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return None, _blocked("clarification continuation unavailable", str(error))
    current_by_identity = {
        (item["collection"], item["id"]): item for item in current_gaps
    }

    retryable, retry_decision, retry_error = _retryable_rejected_resolution(
        work, state, parent, current_by_identity
    )
    if retry_error:
        return None, retry_error
    if retryable is not None:
        assert retry_decision is not None
        return retry_decision, None

    history = state.get("gap_resolution_history", [])
    if not isinstance(history, list) or not all(
        isinstance(item, dict) for item in history
    ):
        return None, _blocked(
            "clarification continuation unavailable",
            "gap resolution history must remain an ordered list",
        )
    completed_resolutions = list(history)
    current_resolution = state.get("gap_resolution")
    if isinstance(current_resolution, dict) and current_resolution.get("result_sha256"):
        completed_resolutions.append(current_resolution)
    used, used_error = _consumed_assessment_identities(completed_resolutions)
    if used_error:
        return None, _blocked(
            "clarification continuation unavailable",
            used_error,
        )
    assert used is not None
    admissions = state.get("operator_text_element_gap_admissions", [])
    if not isinstance(admissions, list) or not all(
        isinstance(item, dict) for item in admissions
    ):
        return None, _blocked(
            "clarification continuation unavailable",
            "operator-text element admission history must remain an ordered list",
        )
    admission_identities: list[tuple[int, int]] = []
    for admission in admissions:
        round_number = admission.get("assessment_round")
        position = admission.get("assessment_position")
        if (
            not isinstance(round_number, int)
            or round_number < 1
            or not isinstance(position, int)
            or position < 1
        ):
            return None, _blocked(
                "clarification continuation unavailable",
                "an operator-text element admission lost its assessment identity",
            )
        admission_identities.append((round_number, position))
    if len(admission_identities) != len(set(admission_identities)):
        return None, _blocked(
            "clarification continuation unavailable",
            "an operator-text element assessment was admitted more than once",
        )
    used.update(admission_identities)

    first_assessment = state.get("gap_answer_assessment")
    round_numbers = (
        [1]
        if isinstance(first_assessment, dict)
        and isinstance(first_assessment.get("assessments"), list)
        else []
    )
    records = state.get("prepared_question_round_assessments", [])
    assert isinstance(records, list)
    round_numbers.extend(int(item["round"]) for item in records)
    latest_pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    for round_number in round_numbers:
        bindings, saved, round_error = _assessment_round_data(
            work, state, round_number
        )
        if round_error:
            return None, round_error
        assert bindings is not None and saved is not None
        assessments = saved.get("assessments")
        if not isinstance(assessments, list):
            return None, _blocked(
                "clarification continuation unavailable",
                f"round {round_number} assessment is incomplete",
            )
        shape_error = _validate_gap_answer_assessment_shape(
            {"assessments": assessments}, bindings
        )
        if shape_error:
            return None, _blocked(
                "clarification continuation unavailable", shape_error
            )
        pairs = list(zip(bindings, assessments, strict=True))
        if round_number == latest_round:
            latest_pairs = pairs
        for binding, assessment in pairs:
            if assessment.get("verdict") != "resolves_gap":
                continue
            position = assessment.get("position")
            if not isinstance(position, int) or (round_number, position) in used:
                continue
            gap = binding.get("gap")
            if not isinstance(gap, dict):
                return None, _blocked(
                    "clarification continuation unavailable",
                    f"round {round_number} assessment {position} lost its gap binding",
                )
            current_gap = current_by_identity.get(
                (gap.get("collection"), gap.get("id"))
            )
            if current_gap is None:
                continue
            if current_gap.get("record_sha256") != gap.get("record_sha256"):
                return None, _blocked(
                    "clarification continuation unavailable",
                    f"gap {gap.get('id')} changed after round {round_number} assessment {position}",
                )
            selected_binding, _, selection_error = (
                _resolving_assessed_answer_at_position(
                    work,
                    state,
                    round_number,
                    position,
                    parent,
                )
            )
            if selection_error:
                return None, selection_error
            assert selected_binding is not None
            selected_gap = selected_binding["gap"]
            assert isinstance(selected_gap, dict)
            return {
                "decision": "apply_resolving_answer",
                "assessment_round": round_number,
                "assessment_position": position,
                "gap": {
                    key: selected_gap[key]
                    for key in (
                        "projection_sha256",
                        "collection",
                        "kind",
                        "id",
                        "record_sha256",
                    )
                },
            }, None

    next_round_gaps: list[dict[str, object]] = []
    for binding, assessment in latest_pairs:
        if assessment.get("verdict") != "does_not_resolve_gap":
            continue
        gap = binding.get("gap")
        if not isinstance(gap, dict):
            return None, _blocked(
                "clarification continuation unavailable",
                "a non-resolving assessment lost its gap binding",
            )
        current_gap = current_by_identity.get((gap.get("collection"), gap.get("id")))
        if current_gap is None:
            continue
        if current_gap.get("record_sha256") != gap.get("record_sha256"):
            return None, _blocked(
                "clarification continuation unavailable",
                f"gap {gap.get('id')} changed after round {latest_round} assessment",
            )
        next_round_gaps.append({
            key: current_gap[key]
            for key in (
                "projection_sha256",
                "collection",
                "kind",
                "id",
                "record_sha256",
            )
        })
    if next_round_gaps:
        return {
            "decision": "prepare_next_round",
            "assessment_round": latest_round,
            "next_round": latest_round + 1,
            "gaps": next_round_gaps,
        }, None
    return {
        "decision": "clarification_complete",
        "assessment_round": latest_round,
        "remaining_current_gap_count": len(current_gaps),
    }, None


def _with_clarification_continuation(
    work: Path, state: dict[str, object], result: dict[str, object]
) -> dict[str, object]:
    continuation, continuation_error = _clarification_continuation(work, state)
    if continuation_error:
        return continuation_error
    assert continuation is not None
    return {**result, "continuation": continuation}


def _validate_terminal_context_deferrals(
    projection: dict[str, object],
    regions: list[dict[str, object]],
    element_by_id: dict[str, dict[str, object]],
) -> tuple[int, str | None]:
    schema_version = projection.get("schema_version")
    if not isinstance(schema_version, int):
        return 0, "projection schema version is missing or invalid"
    if schema_version < 12:
        return 0, None
    region_by_id = {str(region["id"]): region for region in regions}
    region_position = {
        str(region["id"]): position for position, region in enumerate(regions)
    }
    deferrals: dict[str, tuple[str, dict[str, object]]] = {}
    obligations: dict[str, tuple[str, dict[str, object]]] = {}
    for region in regions:
        region_id = str(region["id"])
        deferred = region.get("deferred_context_candidates")
        owned = region.get("context_candidate_obligations")
        if not isinstance(deferred, list) or not isinstance(owned, list):
            return 0, f"scan region {region_id} context-deferral ledger is missing"
        for position, item in enumerate(deferred, 1):
            if not isinstance(item, dict):
                return 0, f"scan region {region_id} deferral {position} is invalid"
            obligation_id = item.get("obligation_id")
            anchor = item.get("anchor")
            candidate_kind = item.get("candidate_kind")
            owner_region_id = item.get("owner_region_id")
            if not isinstance(obligation_id, str) or not obligation_id:
                return 0, f"scan region {region_id} deferral {position} has no identity"
            if obligation_id in deferrals:
                return 0, f"context deferral {obligation_id} is duplicated"
            if (
                not isinstance(anchor, list)
                or len(anchor) != 2
                or not all(isinstance(value, int) for value in anchor)
                or not all(0 <= value < 1000 for value in anchor)
            ):
                return 0, f"context deferral {obligation_id} has an invalid anchor"
            if not isinstance(candidate_kind, str) or not candidate_kind.strip():
                return 0, f"context deferral {obligation_id} has no candidate kind"
            if (
                not isinstance(owner_region_id, str)
                or owner_region_id not in region_by_id
            ):
                return 0, f"context deferral {obligation_id} names an unknown owner region"
            source_bounds = region["bounds"]
            context_bounds = projection_interview._forward_context_bounds(
                source_bounds
            )
            x, y = anchor
            if not (
                context_bounds[0] <= x < context_bounds[2]
                and context_bounds[1] <= y < context_bounds[3]
                and not (
                    source_bounds[0] <= x < source_bounds[2]
                    and source_bounds[1] <= y < source_bounds[3]
                )
            ):
                return 0, (
                    f"context deferral {obligation_id} anchor is not in the "
                    f"source region's context-only area"
                )
            actual_owner = next((
                candidate for candidate in regions
                if (
                    candidate["bounds"][0] <= x < candidate["bounds"][2]
                    and candidate["bounds"][1] <= y < candidate["bounds"][3]
                )
            ), None)
            if (
                actual_owner is None
                or actual_owner["id"] != owner_region_id
                or region_position[str(owner_region_id)] <= region_position[region_id]
            ):
                return 0, f"context deferral {obligation_id} owner contradicts its anchor"
            for hash_field in ("crop_sha256", "guide_sha256"):
                if (
                    not isinstance(item.get(hash_field), str)
                    or len(str(item[hash_field])) != 64
                ):
                    return 0, f"context deferral {obligation_id} has an invalid {hash_field}"
            evidence = region.get("evidence")
            if (
                not isinstance(evidence, dict)
                or evidence.get("crop_sha256") != item["crop_sha256"]
                or evidence.get("guide_sha256") != item["guide_sha256"]
            ):
                return 0, f"context deferral {obligation_id} contradicts its source evidence"
            if item.get("reason") != "context_only":
                return 0, f"context deferral {obligation_id} has an invalid reason"
            deferrals[obligation_id] = (region_id, item)
        for position, item in enumerate(owned, 1):
            if not isinstance(item, dict):
                return 0, f"scan region {region_id} context obligation {position} is invalid"
            obligation_id = item.get("id")
            if not isinstance(obligation_id, str) or not obligation_id:
                return 0, f"scan region {region_id} context obligation {position} has no identity"
            if obligation_id in obligations:
                return 0, f"context obligation {obligation_id} is duplicated"
            if item.get("status") != "resolved":
                return 0, f"context obligation {obligation_id} is not resolved"
            resolution = item.get("resolution")
            if not isinstance(resolution, str) or resolution not in {"element", "gap"}:
                return 0, f"context obligation {obligation_id} has an invalid resolution"
            obligations[obligation_id] = (region_id, item)
    if set(deferrals) != set(obligations):
        missing = sorted(set(deferrals) - set(obligations))
        extra = sorted(set(obligations) - set(deferrals))
        return 0, (
            "context deferral and owner-obligation identities differ: "
            f"missing owners {missing}; unbound obligations {extra}"
        )
    resolved_element_ids: set[str] = set()
    for obligation_id, (source_region_id, deferred) in deferrals.items():
        owner_region_id, obligation = obligations[obligation_id]
        if (
            deferred.get("owner_region_id") != owner_region_id
            or obligation.get("source_region_id") != source_region_id
            or obligation.get("anchor") != deferred.get("anchor")
            or obligation.get("candidate_kind") != deferred.get("candidate_kind")
        ):
            return 0, f"context obligation {obligation_id} contradicts its deferral"
        element_id = obligation.get("element_id")
        if not isinstance(element_id, str) or element_id not in element_by_id:
            return 0, f"context obligation {obligation_id} names no recorded element"
        if element_id in resolved_element_ids:
            return 0, f"context element {element_id} resolves multiple obligations"
        element = element_by_id[element_id]
        owner = region_by_id[owner_region_id]
        bounds = element.get("region")
        anchor = deferred["anchor"]
        if (
            element.get("scan_region_id") != owner_region_id
            or element_id not in owner.get("element_ids", [])
            or element.get("kind") != deferred.get("candidate_kind")
            or not isinstance(bounds, list)
            or len(bounds) != 4
            or not all(isinstance(value, int) for value in bounds)
            or not (
                bounds[0] <= anchor[0] < bounds[2]
                and bounds[1] <= anchor[1] < bounds[3]
            )
        ):
            return 0, f"context obligation {obligation_id} contradicts its resolved element"
        if obligation["resolution"] == "gap":
            if (
                element.get("status") != "gap"
                or not isinstance(obligation.get("gap_reason"), str)
                or not obligation["gap_reason"].strip()
                or obligation["gap_reason"] != element.get("gap_reason")
            ):
                return 0, f"context obligation {obligation_id} has invalid gap evidence"
        elif obligation.get("gap_reason") not in {None, ""}:
            return 0, f"context obligation {obligation_id} has contradictory gap evidence"
        resolved_element_ids.add(element_id)
    return len(obligations), None


def _visual_projection_qualification(
    work: Path, record: dict[str, object]
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Qualify one visual projection from canonical projection evidence."""
    path, projection_sha256, record_error = _validated_projection_record(
        work, record
    )
    if record_error:
        return None, _blocked("terminal_invalid", str(record_error["why"]))
    assert path is not None and projection_sha256 is not None
    if (
        not isinstance(record.get("id"), str)
        or not record["id"]
        or record.get("coverage") != "unassessed"
    ):
        return None, _blocked(
            "terminal_invalid", "projection record identity or coverage state is invalid"
        )
    try:
        projection = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, _blocked("terminal_invalid", f"projection is unreadable: {error}")
    if not isinstance(projection, dict):
        return None, _blocked("terminal_invalid", "projection must be one JSON object")

    elements = projection.get("elements")
    relationships = projection.get("relationships")
    obligations = projection.get("relationship_obligations")
    regions = projection.get("scan_regions")
    if not isinstance(elements, list):
        return None, _blocked("terminal_invalid", "projection elements are missing or invalid")
    if not isinstance(relationships, list):
        return None, _blocked(
            "terminal_invalid", "projection relationships are missing or invalid"
        )
    if not isinstance(obligations, list):
        return None, _blocked(
            "terminal_invalid", "relationship obligations are missing or invalid"
        )
    if not isinstance(regions, list):
        return None, _blocked(
            "terminal_invalid", "deterministic scan-region evidence is missing or invalid"
        )

    expected_regions = projection_interview._scan_regions()
    if len(regions) != len(expected_regions):
        return None, _blocked(
            "terminal_invalid",
            f"scan-region coverage has {len(regions)} outcomes; expected {len(expected_regions)}",
        )

    element_by_id: dict[str, dict[str, object]] = {}
    for position, element in enumerate(elements, 1):
        if not isinstance(element, dict):
            return None, _blocked(
                "terminal_invalid", f"element {position} is not one record"
            )
        element_id = element.get("id")
        if not isinstance(element_id, str) or not element_id:
            return None, _blocked(
                "terminal_invalid", f"element {position} has no stable identity"
            )
        if element_id in element_by_id:
            return None, _blocked(
                "terminal_invalid", f"element identity {element_id} is duplicated"
            )
        status = element.get("status")
        content = element.get("content")
        gap_reason = element.get("gap_reason")
        if status not in {"readable", "gap"}:
            return None, _blocked(
                "terminal_invalid", f"element {element_id} has invalid status {status!r}"
            )
        if (
            status == "readable"
            and (not isinstance(content, str) or not content.strip())
        ) or (
            status == "gap"
            and (not isinstance(gap_reason, str) or not gap_reason.strip())
        ):
            return None, _blocked(
                "terminal_invalid", f"element {element_id} has no {status} outcome evidence"
            )
        if (status == "readable" and gap_reason not in {None, ""}) or (
            status == "gap" and content not in {None, ""}
        ):
            return None, _blocked(
                "terminal_invalid", f"element {element_id} has contradictory outcome evidence"
            )
        element_by_id[element_id] = element

    recorded_region_elements: set[str] = set()
    for position, (region, expected) in enumerate(
        zip(regions, expected_regions, strict=True), 1
    ):
        if not isinstance(region, dict):
            return None, _blocked(
                "terminal_invalid", f"scan region {position} is not one record"
            )
        if region.get("id") != expected["id"] or region.get("bounds") != expected["bounds"]:
            return None, _blocked(
                "terminal_invalid",
                f"scan region {position} is missing, reordered, or has changed bounds",
            )
        status = region.get("status")
        gap_reason = region.get("gap_reason")
        if status not in {"scanned", "gap"}:
            return None, _blocked(
                "terminal_invalid",
                f"scan region {expected['id']} has no terminal coverage outcome",
            )
        if status == "gap" and (
            not isinstance(gap_reason, str) or not gap_reason.strip()
        ):
            return None, _blocked(
                "terminal_invalid", f"scan region {expected['id']} has no gap evidence"
            )
        if status == "scanned" and gap_reason not in {None, ""}:
            return None, _blocked(
                "terminal_invalid",
                f"scan region {expected['id']} has contradictory outcome evidence",
            )
        element_ids = region.get("element_ids")
        if not isinstance(element_ids, list) or any(
            not isinstance(item, str) or not item for item in element_ids
        ):
            return None, _blocked(
                "terminal_invalid", f"scan region {expected['id']} element ledger is invalid"
            )
        if len(element_ids) != len(set(element_ids)):
            return None, _blocked(
                "terminal_invalid", f"scan region {expected['id']} repeats an element identity"
            )
        for element_id in element_ids:
            if element_id not in element_by_id:
                return None, _blocked(
                    "terminal_invalid",
                    f"scan region {expected['id']} references missing element {element_id}",
                )
            if element_id in recorded_region_elements:
                return None, _blocked(
                    "terminal_invalid", f"element {element_id} is recorded in multiple regions"
                )
            if element_by_id[element_id].get("scan_region_id") != expected["id"]:
                return None, _blocked(
                    "terminal_invalid",
                    f"element {element_id} contradicts scan region {expected['id']}",
                )
            recorded_region_elements.add(element_id)
    for element_id, element in element_by_id.items():
        scan_region_id = element.get("scan_region_id")
        if scan_region_id is not None and element_id not in recorded_region_elements:
            return None, _blocked(
                "terminal_invalid",
                f"element {element_id} is missing from its scan-region ledger",
            )

    context_obligation_count, context_error = _validate_terminal_context_deferrals(
        projection, regions, element_by_id
    )
    if context_error:
        return None, _blocked("terminal_invalid", context_error)

    relationship_by_id: dict[str, dict[str, object]] = {}
    for position, relationship in enumerate(relationships, 1):
        if not isinstance(relationship, dict):
            return None, _blocked(
                "terminal_invalid", f"relationship {position} is not one record"
            )
        relationship_id = relationship.get("id")
        if not isinstance(relationship_id, str) or not relationship_id:
            return None, _blocked(
                "terminal_invalid", f"relationship {position} has no stable identity"
            )
        if relationship_id in relationship_by_id:
            return None, _blocked(
                "terminal_invalid", f"relationship identity {relationship_id} is duplicated"
            )
        status = relationship.get("status")
        description = relationship.get("description")
        gap_reason = relationship.get("gap_reason")
        if status not in {"readable", "gap"}:
            return None, _blocked(
                "terminal_invalid",
                f"relationship {relationship_id} has invalid status {status!r}",
            )
        if status == "readable":
            if not isinstance(description, str) or not description.strip():
                return None, _blocked(
                    "terminal_invalid",
                    f"relationship {relationship_id} has no readable outcome evidence",
                )
            for role in ("from_id", "to_id"):
                if relationship.get(role) not in element_by_id:
                    return None, _blocked(
                        "terminal_invalid",
                        f"relationship {relationship_id} references missing {role}",
                    )
            if (
                relationship.get("from_id") == relationship.get("to_id")
                or gap_reason not in {None, ""}
            ):
                return None, _blocked(
                    "terminal_invalid",
                    f"relationship {relationship_id} has contradictory outcome evidence",
                )
        elif not isinstance(gap_reason, str) or not gap_reason.strip():
            return None, _blocked(
                "terminal_invalid", f"relationship {relationship_id} has no gap evidence"
            )
        elif description not in {None, ""}:
            return None, _blocked(
                "terminal_invalid",
                f"relationship {relationship_id} has contradictory outcome evidence",
            )
        relationship_by_id[relationship_id] = relationship

    obligation_ids: set[str] = set()
    for position, obligation in enumerate(obligations, 1):
        if not isinstance(obligation, dict):
            return None, _blocked(
                "terminal_invalid", f"relationship obligation {position} is not one record"
            )
        obligation_id = obligation.get("id")
        if not isinstance(obligation_id, str) or not obligation_id:
            return None, _blocked(
                "terminal_invalid", f"relationship obligation {position} has no stable identity"
            )
        if obligation_id in obligation_ids:
            return None, _blocked(
                "terminal_invalid", f"relationship obligation {obligation_id} is duplicated"
            )
        relationship_id = obligation.get("relationship_id")
        if (
            obligation.get("element_id") not in element_by_id
            or obligation.get("status") != "resolved"
            or obligation.get("resolution") not in {"relationship", "gap"}
            or relationship_id not in relationship_by_id
        ):
            return None, _blocked(
                "terminal_invalid",
                f"relationship obligation {obligation_id} is not closed against recorded evidence",
            )
        obligation_ids.add(obligation_id)

    verified_obligation_ids: set[str] = set()
    for relationship_id, relationship in relationship_by_id.items():
        obligation_id = relationship.get("verified_obligation_id")
        if obligation_id is None:
            continue
        if obligation_id not in obligation_ids or obligation_id in verified_obligation_ids:
            return None, _blocked(
                "terminal_invalid",
                f"relationship {relationship_id} has invalid obligation {obligation_id}",
            )
        obligation = next(
            item for item in obligations if item.get("id") == obligation_id
        )
        if (
            obligation.get("relationship_id") != relationship_id
            or obligation.get("element_id") != relationship.get("verified_element_id")
        ):
            return None, _blocked(
                "terminal_invalid",
                f"relationship {relationship_id} contradicts obligation {obligation_id}",
            )
        verified_obligation_ids.add(obligation_id)

    explicit_gaps = [
        item
        for collection in (regions, elements, relationships)
        for item in collection
        if item.get("status") == "gap"
    ]
    if (
        record.get("element_count") != len(elements)
        or record.get("relationship_count") != len(relationships)
        or record.get("gap_count") != len(explicit_gaps)
    ):
        return None, _blocked(
            "terminal_invalid", "projection record counts contradict the immutable projection"
        )
    remaining_gaps: list[dict[str, object]] = []
    if explicit_gaps:
        try:
            remaining_gaps = gap_clarification.select_gaps(
                projection, projection_sha256
            )
        except gap_clarification.ClarificationError as error:
            return None, _blocked("terminal_invalid", str(error))
    qualification = {
        "qualification": (
            "readable_projection_incomplete"
            if remaining_gaps
            else "readable_projection_complete"
        ),
        "projection": {
            "id": record.get("id"),
            "path": record.get("path"),
            "sha256": projection_sha256,
        },
        "coverage": {
            "region_count": len(expected_regions),
            "region_outcome_count": len(regions),
            "element_count": len(elements),
            "relationship_count": len(relationships),
            "relationship_obligation_count": len(obligations),
            "closed_relationship_obligation_count": len(obligations),
            "context_candidate_obligation_count": context_obligation_count,
            "closed_context_candidate_obligation_count": context_obligation_count,
            "remaining_gap_count": len(remaining_gaps),
        },
        "remaining_gaps": remaining_gaps,
    }
    return qualification, None


def _terminal_projection_qualification(
    work: Path, state: dict[str, object]
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Qualify the active clarification projection."""
    record = state.get("current_projection", state.get("first_projection"))
    if not isinstance(record, dict):
        return None, _blocked(
            "terminal_invalid", "the active projection record is missing"
        )
    return _visual_projection_qualification(work, record)


def _clarification_terminal_disposition(
    decision: dict[str, object],
    qualification: dict[str, object],
    source_projection_closure: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Decide whether projection and intake-wide conversion evidence permit completion."""
    coverage = qualification.get("coverage")
    gaps = qualification.get("remaining_gaps")
    qualified_as = qualification.get("qualification")
    projection = qualification.get("projection")
    closure_verdict = source_projection_closure.get("verdict")
    source_count = source_projection_closure.get("source_count")
    outcome_counts = source_projection_closure.get("outcome_counts")
    outcomes = source_projection_closure.get("outcomes")
    if (
        closure_verdict not in {"all_projected", "conversion_incomplete"}
        or not isinstance(source_count, int)
        or source_count < 1
        or not isinstance(outcome_counts, dict)
        or set(outcome_counts) != {"projected", "pending", "failed"}
        or any(
            not isinstance(outcome_counts.get(name), int)
            or outcome_counts[name] < 0
            for name in ("projected", "pending", "failed")
        )
        or sum(outcome_counts.values()) != source_count
        or not isinstance(outcomes, list)
        or len(outcomes) != source_count
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("source_id"), str)
            or item.get("outcome") not in {"projected", "pending", "failed"}
            for item in outcomes
        )
        or any(
            (
                item["outcome"] == "projected"
                and (
                    not isinstance(item.get("projection"), dict)
                    or not isinstance(item["projection"].get("id"), str)
                    or not isinstance(item["projection"].get("sha256"), str)
                    or item.get("reason") is not None
                )
            )
            or (
                item["outcome"] in {"pending", "failed"}
                and (
                    item.get("projection") is not None
                    or not isinstance(item.get("reason"), str)
                    or not item["reason"].strip()
                )
            )
            for item in outcomes
        )
        or len({item["source_id"] for item in outcomes}) != source_count
        or any(
            outcome_counts[name]
            != sum(item["outcome"] == name for item in outcomes)
            for name in ("projected", "pending", "failed")
        )
        or (
            closure_verdict == "all_projected"
            and outcome_counts
            != {"projected": source_count, "pending": 0, "failed": 0}
        )
        or (
            closure_verdict == "conversion_incomplete"
            and outcome_counts["pending"] + outcome_counts["failed"] < 1
        )
    ):
        return None, _blocked(
            "terminal_invalid",
            "source-to-projection closure evidence is incomplete or contradictory",
        )
    if (
        decision.get("decision") != "clarification_complete"
        or not isinstance(decision.get("remaining_current_gap_count"), int)
        or not isinstance(coverage, dict)
        or not isinstance(coverage.get("remaining_gap_count"), int)
        or not isinstance(gaps, list)
        or not isinstance(projection, dict)
        or not isinstance(projection.get("sha256"), str)
        or coverage["remaining_gap_count"] != len(gaps)
        or decision["remaining_current_gap_count"] != len(gaps)
    ):
        return None, _blocked(
            "terminal_invalid",
            "clarification decision and projection gap evidence contradict each other",
        )
    if qualified_as == "readable_projection_complete" and not gaps:
        if closure_verdict == "conversion_incomplete":
            incomplete_outcomes = [
                item for item in outcomes if item["outcome"] != "projected"
            ]
            return {
                "disposition": "source_conversion_required",
                "projection_sha256": projection["sha256"],
                "remaining_gap_count": 0,
                "source_count": source_count,
                "outcome_counts": outcome_counts,
                "incomplete_source_outcomes": incomplete_outcomes,
            }, None
        return {
            "disposition": "first_layer_complete",
            "projection_sha256": projection["sha256"],
            "remaining_gap_count": 0,
            "source_count": source_count,
            "outcome_counts": outcome_counts,
        }, None
    if qualified_as == "readable_projection_incomplete" and gaps:
        return {
            "disposition": "clarification_required",
            "projection_sha256": projection["sha256"],
            "remaining_gap_count": len(gaps),
            "remaining_gaps": gaps,
        }, None
    return None, _blocked(
        "terminal_invalid",
        "projection qualification and its remaining gaps contradict each other",
    )


def _clarification_required_result(
    state: dict[str, object],
    work: Path,
    decision: dict[str, object],
    qualification: dict[str, object],
    disposition: dict[str, object],
    source_projection_closure: dict[str, object],
) -> dict[str, object]:
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "clarification_required",
        "intake_id": state["intake_id"],
        "projection": state.get("current_projection", state["first_projection"]),
        "continuation": decision,
        "projection_qualification": qualification,
        "source_projection_closure": source_projection_closure,
        "terminal_disposition": disposition,
        "gaps": disposition["remaining_gaps"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _source_conversion_required_result(
    state: dict[str, object],
    work: Path,
    decision: dict[str, object],
    qualification: dict[str, object],
    disposition: dict[str, object],
    source_projection_closure: dict[str, object],
) -> dict[str, object]:
    return {
        "status": "source_projection_closure",
        "stopped": "source_conversion_required",
        "intake_id": state["intake_id"],
        "projection": state.get("current_projection", state["first_projection"]),
        "continuation": decision,
        "projection_qualification": qualification,
        "source_projection_closure": source_projection_closure,
        "terminal_disposition": disposition,
        "incomplete_source_outcomes": disposition["incomplete_source_outcomes"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _clarification_completion_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    saved = state["clarification_completion"]
    assert isinstance(saved, dict) and isinstance(saved.get("decision"), dict)
    assert isinstance(saved.get("projection_qualification"), dict)
    assert isinstance(saved.get("source_projection_closure"), dict)
    assert isinstance(saved.get("terminal_disposition"), dict)
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "clarification_continuation_complete",
        "intake_id": state["intake_id"],
        "projection": state.get("current_projection", state["first_projection"]),
        "continuation": saved["decision"],
        "projection_qualification": saved["projection_qualification"],
        "source_projection_closure": saved["source_projection_closure"],
        "terminal_disposition": saved["terminal_disposition"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _validate_clarification_completion(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object] | None:
    saved = state.get("clarification_completion")
    if not isinstance(saved, dict):
        return _blocked(
            "invalid clarification completion",
            "the clarification completion record is missing",
        )
    sequence = saved.get("ledger_sequence")
    decision = saved.get("decision")
    projection_sha256 = saved.get("projection_sha256")
    projection_qualification = saved.get("projection_qualification")
    source_projection_closure = saved.get("source_projection_closure")
    terminal_disposition = saved.get("terminal_disposition")
    basis = saved.get("basis")
    if basis == "additional_source_element_gap_admission":
        try:
            purpose = (work / "sources" / "source-000002.txt").read_text(
                encoding="utf-8"
            )
        except OSError as error:
            return _blocked("invalid clarification completion", str(error))
        admission_error = _validate_additional_source_element_gap_admission(
            work,
            state,
            entries[:-1],
            purpose,
            allow_later_phase=True,
        )
        if admission_error:
            return admission_error
        (
            recomputed,
            recomputed_qualification,
            recomputed_closure,
            recomputed_disposition,
            recompute_error,
        ) = _additional_source_element_gap_continuation_evidence(
            work, state, entries[:-1]
        )
        if recompute_error:
            return recompute_error
    else:
        recomputed, decision_error = _clarification_continuation(work, state)
        if decision_error:
            return decision_error
        recomputed_qualification, qualification_error = (
            _terminal_projection_qualification(work, state)
        )
        if qualification_error:
            return qualification_error
        recomputed_closure, closure_error = _source_projection_closure_inventory(
            work, entries[:-1]
        )
        if closure_error:
            return _blocked("terminal_invalid", str(closure_error["why"]))
        assert recomputed is not None and recomputed_qualification is not None
        assert recomputed_closure is not None
        recomputed_disposition, disposition_error = (
            _clarification_terminal_disposition(
                recomputed, recomputed_qualification, recomputed_closure
            )
        )
        if disposition_error:
            return disposition_error
    assert recomputed is not None and recomputed_qualification is not None
    assert recomputed_closure is not None and recomputed_disposition is not None
    if (
        not isinstance(sequence, int)
        or not isinstance(decision, dict)
        or decision.get("decision") != "clarification_complete"
        or recomputed != decision
        or not isinstance(projection_qualification, dict)
        or recomputed_qualification != projection_qualification
        or not isinstance(source_projection_closure, dict)
        or recomputed_closure != source_projection_closure
        or not isinstance(terminal_disposition, dict)
        or recomputed_disposition != terminal_disposition
        or terminal_disposition.get("disposition") != "first_layer_complete"
        or not isinstance(projection_sha256, str)
        or sequence != len(entries)
        or entries[-1].get("event") != "clarification_continuation_completed"
        or entries[-1].get("basis") != basis
        or entries[-1].get("decision") != decision
        or entries[-1].get("projection_sha256") != projection_sha256
        or entries[-1].get("projection_qualification") != projection_qualification
        or entries[-1].get("source_projection_closure")
        != source_projection_closure
        or entries[-1].get("terminal_disposition") != terminal_disposition
        or state.get("status") != "ready_for_projection_assessment"
        or state.get("phase") != "clarification_continuation_complete"
        or state.get("waiting_for") is not None
        or state.get("question") is not None
        or state.get("ledger_entries") != len(entries)
        or state.get("ledger_tail_sha256") != entries[-1].get("entry_sha256")
    ):
        return _blocked(
            "invalid clarification completion",
            "the preserved clarification terminal decision changed",
        )
    parent = state.get("current_projection", state.get("first_projection"))
    if not isinstance(parent, dict) or parent.get("sha256") != projection_sha256:
        return _blocked(
            "invalid clarification completion",
            "the terminal projection identity changed",
        )
    return None


def _execute_clarification_continuation(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    if state.get("phase") == "clarification_continuation_complete":
        completion_error = _validate_clarification_completion(work, state, entries)
        if completion_error:
            return completion_error
        return _clarification_completion_result(state, work)
    if state.get("phase") not in {
        "gap_answer_assessment_recorded",
        "prepared_question_round_assessment_recorded",
        "operator_text_element_gap_admitted",
        "gap_resolution_applied",
        "gap_resolution_rejected",
    }:
        return _blocked(
            "clarification continuation unavailable",
            "the prior continuation transition has not reached a terminal state",
        )
    if state.get("phase") == "gap_resolution_rejected":
        rejected = state.get("gap_resolution")
        if not isinstance(rejected, dict):
            return _blocked(
                "gap resolution retry unavailable",
                "the rejected resolution record is missing",
            )
        if isinstance(rejected.get("retry_of"), dict):
            return _blocked(
                "gap resolution retry exhausted",
                "the code-controlled correction attempt was independently rejected; the preserved human answer was not asked again",
            )
        return _request_gap_resolution(
            work,
            state,
            entries,
            retry_rejected_resolution=rejected,
        )
    decision, decision_error = _clarification_continuation(work, state)
    if decision_error:
        return decision_error
    assert decision is not None
    if decision["decision"] == "apply_resolving_answer":
        gap = decision.get("gap")
        if isinstance(gap, dict) and gap.get("collection") == "elements":
            return _consume_operator_text_element_gap_admission(
                work, state, entries, decision
            )
        return _request_gap_resolution(
            work,
            state,
            entries,
            expected_continuation=decision,
        )
    if decision["decision"] == "retry_rejected_resolution":
        rejected_attempt = decision.get("rejected_attempt")
        candidates = [
            item
            for item in [
                *state.get("gap_resolution_history", []),
                state.get("gap_resolution"),
            ]
            if isinstance(item, dict)
            and item.get("attempt") == rejected_attempt
        ]
        if len(candidates) != 1:
            return _blocked(
                "gap resolution retry unavailable",
                "the selected rejected attempt is missing or duplicated",
            )
        return _request_gap_resolution(
            work,
            state,
            entries,
            expected_continuation=decision,
            retry_rejected_resolution=candidates[0],
        )
    if decision["decision"] == "prepare_next_round":
        return _request_follow_up_gap_question_round(
            work,
            state,
            entries,
            expected_continuation=decision,
        )
    if decision["decision"] != "clarification_complete":
        return _blocked(
            "invalid clarification continuation",
            f"unsupported continuation decision {decision.get('decision')!r}",
        )
    parent = state.get("current_projection", state.get("first_projection"))
    if not isinstance(parent, dict) or not isinstance(parent.get("sha256"), str):
        return _blocked(
            "clarification continuation unavailable",
            "the terminal projection identity is missing",
        )
    projection_qualification, qualification_error = _terminal_projection_qualification(
        work, state
    )
    if qualification_error:
        return qualification_error
    assert projection_qualification is not None
    source_projection_closure, closure_error = _source_projection_closure_inventory(
        work, entries
    )
    if closure_error:
        return _blocked("terminal_invalid", str(closure_error["why"]))
    assert source_projection_closure is not None
    terminal_disposition, disposition_error = _clarification_terminal_disposition(
        decision, projection_qualification, source_projection_closure
    )
    if disposition_error:
        return disposition_error
    assert terminal_disposition is not None
    if terminal_disposition["disposition"] == "clarification_required":
        return _clarification_required_result(
            state,
            work,
            decision,
            projection_qualification,
            terminal_disposition,
            source_projection_closure,
        )
    if terminal_disposition["disposition"] == "source_conversion_required":
        return _source_conversion_required_result(
            state,
            work,
            decision,
            projection_qualification,
            terminal_disposition,
            source_projection_closure,
        )
    history = state.get("gap_resolution_history", [])
    current_resolution = state.get("gap_resolution")
    if not isinstance(history, list):
        return _blocked(
            "clarification continuation unavailable",
            "gap resolution history must remain an ordered list",
        )
    sequence = len(entries) + 1
    completed = _ledger_entry(
        sequence,
        "clarification_continuation_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "decision": decision,
            "projection_sha256": parent["sha256"],
            "projection_qualification": projection_qualification,
            "source_projection_closure": source_projection_closure,
            "terminal_disposition": terminal_disposition,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed])
    if isinstance(current_resolution, dict):
        archived = json.loads(json.dumps(current_resolution))
        archived["terminal_phase"] = state.get("phase")
        archived["output_projection"] = state.get("current_projection")
        state["gap_resolution_history"] = [*history, archived]
        state.pop("gap_resolution", None)
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "clarification_continuation_complete",
        "waiting_for": None,
        "question": None,
        "clarification_completion": {
            "ledger_sequence": sequence,
            "decision": decision,
            "projection_sha256": parent["sha256"],
            "projection_qualification": projection_qualification,
            "source_projection_closure": source_projection_closure,
            "terminal_disposition": terminal_disposition,
        },
        "ledger_entries": sequence,
        "ledger_tail_sha256": completed["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _clarification_completion_result(state, work)


def _follow_up_gap_bindings(
    work: Path, state: dict[str, object]
) -> tuple[
    list[dict[str, object]] | None,
    Path | None,
    str | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    round_number, bindings, saved_assessment, binding_error = (
        _latest_assessed_round(work, state)
    )
    if binding_error:
        return None, None, None, None, binding_error
    assert round_number is not None and bindings is not None
    assert saved_assessment is not None
    assessments = (
        saved_assessment.get("assessments")
        if isinstance(saved_assessment, dict)
        else None
    )
    if not isinstance(assessments, list) or len(assessments) != len(bindings):
        return None, None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "the preserved assessment set is incomplete",
        )
    used = _used_assessment_identities(state)
    unused_resolving = [
        item.get("position")
        for item in assessments
        if isinstance(item, dict)
        and item.get("verdict") == "resolves_gap"
        and not (
            isinstance(item.get("basis"), dict)
            and item["basis"].get("kind") == "admitted_source"
        )
        and (round_number, item.get("position")) not in used
    ]
    if unused_resolving:
        return None, None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "apply every already-resolving assessment before asking follow-up questions",
        )
    parent = state.get("current_projection", state.get("first_projection"))
    if not isinstance(parent, dict):
        return None, None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "the current projection record is missing",
        )
    projection_path, projection_sha256, projection_error = (
        _validated_projection_record(work, parent)
    )
    if projection_error:
        return None, None, None, None, projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        current_gaps = gap_clarification.require_gaps(
            projection, projection_sha256
        )
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError) as error:
        return None, None, None, None, _blocked(
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
            return None, None, None, None, _blocked(
                "follow-up gap clarification unavailable",
                "a non-resolving assessment lost its bound gap",
            )
        key = (original_gap.get("collection"), original_gap.get("id"))
        current_gap = current_by_identity.get(key)
        if current_gap is None:
            continue
        if current_gap.get("record_sha256") != original_gap.get("record_sha256"):
            return None, None, None, None, _blocked(
                "follow-up gap clarification unavailable",
                f"gap {original_gap.get('id')} changed after its failed clarification",
            )
        follow_up = json.loads(json.dumps(current_gap))
        follow_up["follow_up_of"] = {
            "question_round": round_number,
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
        return None, None, None, None, _blocked(
            "follow-up gap clarification unavailable",
            "no still-current gap has a non-resolving preserved answer",
        )
    context = {
        "assessment_round": round_number,
        "assessment_result_sha256": saved_assessment["result_sha256"],
    }
    return follow_ups, projection_path, projection_sha256, context, None


def _request_follow_up_gap_question_round(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    *,
    expected_continuation: dict[str, object] | None = None,
) -> dict[str, object]:
    gaps, projection_path, projection_sha256, context, binding_error = (
        _follow_up_gap_bindings(work, state)
    )
    if binding_error:
        return binding_error
    assert gaps is not None and projection_path is not None
    assert projection_sha256 is not None and context is not None
    assessment_round = context["assessment_round"]
    prior_assessment_sha256 = context["assessment_result_sha256"]
    assert isinstance(assessment_round, int)
    assert isinstance(prior_assessment_sha256, str)
    round_number = assessment_round + 1
    actual_continuation = {
        "decision": "prepare_next_round",
        "assessment_round": assessment_round,
        "next_round": round_number,
        "gaps": [
            {
                key: gap[key]
                for key in (
                    "projection_sha256",
                    "collection",
                    "kind",
                    "id",
                    "record_sha256",
                )
            }
            for gap in gaps
        ],
    }
    if (
        expected_continuation is not None
        and expected_continuation != actual_continuation
    ):
        return _blocked(
            "stale clarification continuation",
            "the prepare-next-round decision changed before execution",
        )
    prepared_history = state.get("prepared_question_round_history", [])
    if not isinstance(prepared_history, list) or not all(
        isinstance(item, dict) for item in prepared_history
    ):
        return _blocked(
            "follow-up gap clarification unavailable",
            "the prepared question round history must remain an ordered list",
        )
    archived_prepared: dict[str, object] | None = None
    archived_interview: dict[str, object] | None = None
    if assessment_round >= 2:
        archived_prepared, archived_interview, snapshot_error = (
            _prepared_round_snapshot(state, assessment_round)
        )
        if snapshot_error:
            return snapshot_error
        if any(item.get("round") == assessment_round for item in prepared_history):
            return _blocked(
                "follow-up gap clarification unavailable",
                f"prepared round {assessment_round} is already archived",
            )
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
            "prior_assessment_round": assessment_round,
            "prior_assessment_sha256": prior_assessment_sha256,
            "interview_path": f"{relative_dir}/interview.jsonl",
            "result_path": f"{relative_dir}/clarification-round.json",
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [request])
    if archived_resolution is not None:
        state["gap_resolution_history"] = [*history, archived_resolution]
        state.pop("gap_resolution", None)
    if archived_prepared is not None and archived_interview is not None:
        state["prepared_question_round_history"] = [
            *prepared_history,
            {
                "round": assessment_round,
                "question_round": json.loads(json.dumps(archived_prepared)),
                "interview": json.loads(json.dumps(archived_interview)),
            },
        ]
        state.pop("prepared_question_round_interview", None)
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
            "prior_assessment_round": assessment_round,
            "prior_assessment_sha256": prior_assessment_sha256,
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
    *,
    contract: int = gap_clarification.ROUND_CONTRACT,
) -> str | None:
    shape_error = _validate_question_round_shape(
        result, gaps, round_number=round_number, contract=contract
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
    gaps, projection_path, projection_sha256, context, binding_error = (
        _follow_up_gap_bindings(work, state)
    )
    if binding_error:
        return binding_error
    assert gaps is not None and projection_path is not None
    assert projection_sha256 is not None and context is not None
    round_number = saved.get("round")
    contract = saved.get("contract", 1)
    assessment_round = context.get("assessment_round")
    prior_assessment_sha256 = context.get("assessment_result_sha256")
    if (
        not isinstance(round_number, int)
        or round_number < 2
        or contract not in gap_clarification.SUPPORTED_ROUND_CONTRACTS
        or not isinstance(assessment_round, int)
        or round_number != assessment_round + 1
        or not isinstance(prior_assessment_sha256, str)
    ):
        return _blocked(
            "invalid intake state", "the follow-up round predecessor changed"
        )
    relative_dir = f"gap-question-rounds/round-{round_number:06d}"
    request_sequence = saved.get("request_ledger_sequence")
    request_index = request_sequence - 1 if isinstance(request_sequence, int) else -1
    expected_request = {
        "round": round_number,
        "contract": contract,
        "projection_path": str(projection_path.relative_to(work)),
        "projection_sha256": projection_sha256,
        "gap_count": len(gaps),
        "gaps": gaps,
        "prior_assessment_round": assessment_round,
        "prior_assessment_sha256": prior_assessment_sha256,
        "interview_path": f"{relative_dir}/interview.jsonl",
        "result_path": f"{relative_dir}/clarification-round.json",
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
    round_dir = work / relative_dir
    try:
        result, journal_sha256, result_sha256 = gap_clarification.validate_round(
            round_dir,
            projection_path=projection_path,
            projection_sha256=projection_sha256,
            purpose=purpose,
            contract=contract,
            gaps=gaps,
            round_number=round_number,
        )
        journal_entries = gap_clarification._read_journal(
            round_dir / "interview.jsonl"
        )
    except gap_clarification.ClarificationError as error:
        return _blocked("invalid follow-up gap question round", str(error))
    shape_error = _validate_follow_up_question_round_shape(
        result, gaps, round_number, contract=contract
    )
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
            "round": round_number,
            "interview_path": f"{relative_dir}/interview.jsonl",
            "interview_sha256": journal_sha256,
            "result_path": f"{relative_dir}/clarification-round.json",
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
            "round": round_number,
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
    contract = saved.get("contract", 1)
    projection_value = saved.get("projection_path")
    projection_sha256 = saved.get("projection_sha256")
    gaps = saved.get("gaps")
    prior_assessment_round = saved.get("prior_assessment_round", round_number - 1)
    prior_assessment_sha256 = saved.get("prior_assessment_sha256")
    if (
        not isinstance(round_number, int)
        or round_number < 2
        or contract not in gap_clarification.SUPPORTED_ROUND_CONTRACTS
        or not isinstance(projection_value, str)
        or not isinstance(projection_sha256, str)
        or not isinstance(gaps, list)
        or not gaps
        or not isinstance(prior_assessment_round, int)
        or prior_assessment_round != round_number - 1
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
        "contract": contract,
        "projection_path": str(projection_path.relative_to(work)),
        "projection_sha256": projection_sha256,
        "gap_count": len(gaps),
        "gaps": gaps,
        "prior_assessment_sha256": prior_assessment_sha256,
        "interview_path": f"{round_dir_value}/interview.jsonl",
        "result_path": f"{round_dir_value}/clarification-round.json",
    }
    if "prior_assessment_round" in saved:
        expected_request["prior_assessment_round"] = prior_assessment_round
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
            contract=contract,
        )
        journal_entries = gap_clarification._read_journal(
            round_dir / "interview.jsonl"
        )
    except gap_clarification.ClarificationError as error:
        return _blocked("invalid follow-up gap question round", str(error))
    shape_error = _validate_follow_up_question_round_shape(
        result, gaps, round_number, contract=contract
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
            path = value.get("path", value.get("stored_path"))
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


def _additional_source_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    pending = state["pending_additional_source"]
    assert isinstance(pending, dict)
    return {
        "status": "ready_for_projection",
        "stopped": "additional_source_frozen",
        "intake_id": state["intake_id"],
        "question": pending["question"],
        "source": pending["source"],
        "projection": pending["projection"],
        "lineage": pending["lineage"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _acquire_additional_local_file(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    supplied: Path,
    *,
    question: dict[str, object],
    lineage: dict[str, object],
) -> dict[str, object]:
    if question.get("answer_type") != "local_file":
        return _blocked(
            "operator input type mismatch",
            "the current question requires non-empty text, not a local file",
        )
    resolved, content, source_error = _read_local_source(supplied)
    if source_error:
        return source_error
    assert resolved is not None and content is not None
    reservation = source_collection_reservation.reserve(
        [f"source-{number:06d}" for number in sorted(_known_source_numbers(entries))]
    )
    number = int(reservation["source_number"])
    stored_relative = f"sources/source-{number:06d}"
    stored_path = work / stored_relative
    if stored_path.exists():
        return _blocked(
            "unbound source artifact",
            "the additional local-file artifact already exists outside the ledger",
        )
    stored_path.write_bytes(content)
    media_type, media_type_basis = _detect_media_type(stored_path)
    source = _bind_local_file_to_question(
        _local_file_record(
            number,
            supplied,
            resolved,
            stored_relative,
            content,
            media_type,
            media_type_basis,
        ),
        question,
    )
    projection = _pending_additional_projection_record(number)
    if projection.get("id") != reservation["projection_id"]:
        return _blocked(
            "source reservation failed",
            "the reserved source and projection identities disagree",
        )
    entry = _ledger_entry(
        len(entries) + 1,
        "source_acquired",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "answers_question": question["id"],
            "answers_gap": question["answers_gap"],
            "source": source,
            "projection": projection,
            "lineage": lineage,
            "next_phase": "additional_source_frozen",
        },
        str(entries[-1]["entry_sha256"]),
    )
    pending = {
        "question": question,
        "source": source,
        "projection": projection,
        "lineage": lineage,
        "ledger_sequence": len(entries) + 1,
    }
    _append_ledger(work / "ledger.jsonl", [entry])
    state.update({
        "status": "ready_for_projection",
        "phase": "additional_source_frozen",
        "waiting_for": None,
        "question": None,
        "pending_additional_source": pending,
        "ledger_entries": len(entries) + 1,
        "ledger_tail_sha256": entry["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _additional_source_ready_result(state, work)


def _acquire_additional_url(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    supplied_url: str,
    *,
    question: dict[str, object],
    lineage: dict[str, object],
) -> dict[str, object]:
    if question.get("answer_type") != "url":
        return _blocked(
            "operator input type mismatch",
            "the current question requires a different answer type, not a URL",
        )
    reservation = source_collection_reservation.reserve(
        [f"source-{number:06d}" for number in sorted(_known_source_numbers(entries))]
    )
    number = int(reservation["source_number"])
    stored_relative = f"sources/source-{number:06d}"
    stored_path = work / stored_relative
    if stored_path.exists():
        return _blocked(
            "unbound source artifact",
            "the additional URL artifact already exists outside the ledger",
        )
    retrieval, content, retrieval_error = _fetch_public_url(supplied_url)
    if retrieval_error:
        return retrieval_error
    assert retrieval is not None and content is not None
    stored_path.write_bytes(content)
    media_type, media_type_basis = _url_media_type(retrieval, stored_path)
    source = {
        **_url_source_record(
            number,
            stored_relative,
            content,
            retrieval,
            media_type,
            media_type_basis,
        ),
        "answers_question": question["id"],
        "answers_gap": question["answers_gap"],
    }
    projection = _pending_additional_projection_record(number)
    if projection.get("id") != reservation["projection_id"]:
        return _blocked(
            "source reservation failed",
            "the reserved source and projection identities disagree",
        )
    entry = _ledger_entry(
        len(entries) + 1,
        "source_acquired",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "answers_question": question["id"],
            "answers_gap": question["answers_gap"],
            "source": source,
            "projection": projection,
            "lineage": lineage,
            "next_phase": "additional_source_frozen",
        },
        str(entries[-1]["entry_sha256"]),
    )
    pending = {
        "question": question,
        "source": source,
        "projection": projection,
        "lineage": lineage,
        "ledger_sequence": len(entries) + 1,
    }
    _append_ledger(work / "ledger.jsonl", [entry])
    state.update({
        "status": "ready_for_projection",
        "phase": "additional_source_frozen",
        "waiting_for": None,
        "question": None,
        "pending_additional_source": pending,
        "ledger_entries": len(entries) + 1,
        "ledger_tail_sha256": entry["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _additional_source_ready_result(state, work)


def _validate_pending_additional_source(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    supplied: Path | None,
    supplied_url: str | None = None,
    *,
    allow_projection: bool = False,
) -> dict[str, object] | None:
    pending = state.get("pending_additional_source")
    if not isinstance(pending, dict) or not entries:
        return _blocked(
            "invalid intake state", "the pending additional source record is missing"
        )
    question = pending.get("question")
    source = pending.get("source")
    projection = pending.get("projection")
    lineage = pending.get("lineage")
    sequence = pending.get("ledger_sequence")
    if (
        not isinstance(question, dict)
        or question.get("answer_type") not in {"local_file", "url"}
        or not isinstance(source, dict)
        or not isinstance(projection, dict)
        or not isinstance(lineage, dict)
        or not isinstance(sequence, int)
        or sequence < 1
        or sequence > len(entries)
        or (not allow_projection and sequence != len(entries))
    ):
        return _blocked(
            "invalid intake state", "the pending additional source identity changed"
        )
    entry = entries[sequence - 1]
    question_sequence = lineage.get("question_ledger_sequence")
    if (
        not isinstance(question_sequence, int)
        or question_sequence < 1
        or question_sequence >= sequence
        or entries[question_sequence - 1].get("event") != "operator_question_asked"
        or entries[question_sequence - 1].get("question") != question
        or entry.get("event") != "source_acquired"
        or entry.get("answers_question") != question.get("id")
        or entry.get("answers_gap") != question.get("answers_gap")
        or entry.get("source") != source
        or entry.get("projection") != projection
        or entry.get("lineage") != lineage
        or entry.get("next_phase") != "additional_source_frozen"
    ):
        return _blocked(
            "invalid ledger", "the additional source lost its question or gap lineage"
        )
    source_id = source.get("id")
    stored_relative = source.get("stored_path")
    if (
        not isinstance(source_id, str)
        or not source_id.startswith("source-")
        or not isinstance(stored_relative, str)
        or stored_relative != f"sources/{source_id}"
        or source.get("answers_question") != question.get("id")
        or source.get("answers_gap") != question.get("answers_gap")
    ):
        return _blocked(
            "invalid ledger", "the additional local-file source record changed"
        )
    try:
        number = int(source_id.removeprefix("source-"))
        frozen = (work / stored_relative).read_bytes()
    except (OSError, ValueError):
        return _blocked(
            "immutable source unavailable", "the frozen additional source cannot be read"
        )
    if question.get("answer_type") == "url":
        if supplied is not None:
            return _blocked(
                "operator input type mismatch",
                "the current question is bound to a URL, not a local file",
            )
        base_source = {
            key: value
            for key, value in source.items()
            if key not in {"answers_question", "answers_gap"}
        }
        url_error = _validate_url_source_record(
            base_source, number, frozen, supplied_url
        )
        if url_error:
            return url_error
        expected_source = {
            **base_source,
            "answers_question": question["id"],
            "answers_gap": question["answers_gap"],
        }
    else:
        if supplied_url is not None:
            return _blocked(
                "operator input type mismatch",
                "the current question is bound to a local file, not a URL",
            )
        if (
            source.get("kind") != "local_file"
            or source.get("adapter")
            != {"name": "local_file", "version": LOCAL_FILE_ADAPTER_VERSION}
        ):
            return _blocked(
                "invalid ledger", "the additional local-file source record changed"
            )
        expected_source = _bind_local_file_to_question(
            _local_file_record(
                number,
                Path(str(source.get("provided_path"))),
                Path(str(source.get("resolved_path"))),
                stored_relative,
                frozen,
                str(source.get("media_type")),
                str(source.get("media_type_basis")),
            ),
            question,
        )
    if (
        source != expected_source
        or projection != _pending_additional_projection_record(number)
        or number in _known_source_numbers(entries[: sequence - 1])
        or (
            not allow_projection
            and (
                state.get("status") != "ready_for_projection"
                or state.get("phase") != "additional_source_frozen"
                or state.get("waiting_for") is not None
            )
        )
        or (
            allow_projection
            and state.get("phase")
            not in {
                "interviewing_additional_source_projection",
                "additional_source_projection_recorded",
                "additional_spreadsheet_projection_failed",
                "assessing_additional_source_gap",
                "additional_source_gap_assessment_recorded",
                "additional_source_element_gap_admitted",
                "clarification_continuation_complete",
            }
        )
        or state.get("question") is not None
        or state.get("ledger_entries") != len(entries)
        or state.get("ledger_tail_sha256") != entries[-1].get("entry_sha256")
    ):
        return _blocked(
            "invalid ledger", "the frozen additional source or pending projection changed"
        )
    if supplied is not None:
        resolved, current, source_error = _read_local_source(supplied)
        if source_error:
            return source_error
        assert resolved is not None and current is not None
        if (
            str(supplied) != source.get("provided_path")
            or str(resolved) != source.get("resolved_path")
        ):
            return _blocked(
                "source origin changed",
                "this pending source is bound to a different local-file origin",
            )
        if current != frozen:
            return _blocked(
                "source changed",
                "the supplied local file no longer matches the frozen additional source",
            )
    return None


def _additional_projection_paths(source_id: str) -> dict[str, str]:
    root = f"additional-source-projections/{source_id}"
    return {
        "interview_dir": f"{root}/projection-interview",
        "interview_path": f"{root}/projection-interview/interview.jsonl",
        "candidate_path": f"{root}/projection-interview/projection.json",
        "verification_dir": f"{root}/relationship-verification",
        "verification_path": f"{root}/relationship-verification/verification.json",
        "verification_journal_path": f"{root}/relationship-verification/interview.jsonl",
        "correction_dir": f"{root}/relationship-correction",
        "correction_path": f"{root}/relationship-correction/corrections.json",
        "correction_journal_path": f"{root}/relationship-correction/interview.jsonl",
        "correction_candidate_path": f"{root}/relationship-correction/verification-candidate.json",
        "correction_verification_dir": f"{root}/relationship-correction-verification",
        "correction_verification_path": f"{root}/relationship-correction-verification/verification.json",
        "correction_verification_journal_path": f"{root}/relationship-correction-verification/interview.jsonl",
        "projection_path": f"projections/{source_id}-v1.json",
    }


def _additional_projection_waiting_result(
    state: dict[str, object],
    work: Path,
    stage: str = "project_additional_source",
) -> dict[str, object]:
    pending = state["pending_additional_source"]
    active = state["active_additional_projection"]
    assert isinstance(pending, dict) and isinstance(active, dict)
    source = pending["source"]
    assert isinstance(source, dict)
    stages = {
        "project_additional_source": {
            "flag": "--run-projection-interview",
            "stopped": "interviewing_additional_source_projection",
            "instruction": (
                "Inspect the attached frozen source, run the command, and answer only the "
                "typed question currently displayed. Code controls allowed choices and assembly."
            ),
        },
        "verify_additional_source_projection": {
            "flag": "--run-projection-verification",
            "stopped": "verifying_additional_source_projection",
            "instruction": (
                "Independently inspect the attached frozen source, run the command, and answer "
                "only the typed question currently displayed. Code controls allowed choices and assembly."
            ),
        },
        "correct_additional_source_relationships": {
            "flag": "--run-relationship-correction",
            "stopped": "correcting_additional_source_relationships",
            "instruction": (
                "Inspect the attached frozen source, run the command, and address only the independently "
                "rejected relationships. Code controls replacement choices, coordinate binding, and gaps."
            ),
        },
        "verify_additional_source_relationship_corrections": {
            "flag": "--run-correction-verification",
            "stopped": "verifying_additional_source_relationship_corrections",
            "instruction": (
                "Independently inspect the attached frozen source, run the command, and verify only the "
                "proposed corrected relationships. Code controls allowed verdicts and final assembly."
            ),
        },
    }
    selected = stages[stage]
    attachment: Path | tuple[Path, Path] = work / str(source["stored_path"])
    if stage == "project_additional_source":
        paths = active.get("paths")
        if not isinstance(paths, dict) or not isinstance(
            paths.get("interview_dir"), str
        ):
            return _blocked(
                "projection region evidence failed",
                "the additional-source projection identity is missing",
            )
        (
            attachment,
            region_id,
            obligation_id,
            endpoint_evidence_sha256,
            attachment_error,
        ) = _projection_model_attachment(
            work,
            source_path=attachment,
            source_sha256=str(source["sha256"]),
            attempt_dir=work / str(paths["interview_dir"]),
            contract=PROJECTION_INTERVIEW_CONTRACT,
        )
        if attachment_error:
            return attachment_error
        assert attachment is not None
    attachments = attachment if isinstance(attachment, tuple) else (attachment,)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--work",
        str(work.resolve()),
    ]
    if stage == "project_additional_source" and region_id is not None:
        command.extend(["--projection-region-id", region_id])
    elif stage == "project_additional_source" and obligation_id is not None:
        command.extend(["--projection-obligation-id", obligation_id])
    if (
        stage == "project_additional_source"
        and endpoint_evidence_sha256 is not None
    ):
        command.extend([
            "--projection-endpoint-evidence-sha256",
            endpoint_evidence_sha256,
        ])
    command.append(selected["flag"])
    return {
        "status": "waiting_for_model",
        "stopped": selected["stopped"],
        "intake_id": state["intake_id"],
        "source": source,
        "reserved_projection": pending["projection"],
        "lineage": pending["lineage"],
        "work": [{
            "stage": stage,
            "instruction": selected["instruction"],
            "attachments": [str(path.resolve()) for path in attachments],
            "command": command,
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _request_additional_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    pending = state["pending_additional_source"]
    assert isinstance(pending, dict)
    source = pending["source"]
    projection = pending["projection"]
    lineage = pending["lineage"]
    assert isinstance(source, dict) and isinstance(projection, dict)
    assert isinstance(lineage, dict)
    source_id = str(source["id"])
    source_path = work / str(source["stored_path"])
    try:
        source_bytes = source_path.read_bytes()
    except OSError:
        return _blocked("immutable source unavailable", str(source_path))
    if spreadsheet_projection.is_workbook(
        Path(str(source.get("filename", source_path.name))),
        str(source.get("media_type", "")),
        source_bytes,
    ):
        return _create_spreadsheet_projection(
            work,
            state,
            entries,
            source,
            projection,
            pending=pending,
        )
    if not str(source["media_type"]).startswith("image/"):
        return _create_additional_verbatim_utf8_projection(
            work, state, entries, pending
        )
    paths = _additional_projection_paths(source_id)
    artifact_root = work / f"additional-source-projections/{source_id}"
    projection_path = work / paths["projection_path"]
    if artifact_root.exists() or projection_path.exists():
        return _blocked(
            "unbound projection artifacts",
            f"projection artifacts for {source_id} already exist outside the ledger",
        )
    (work / paths["interview_dir"]).mkdir(parents=True)
    sequence = len(entries) + 1
    started = _ledger_entry(
        sequence,
        "model_projection_interview_started",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": 1,
            "role": "additional_source_projection",
            "source_id": source_id,
            "source_sha256": source["sha256"],
            "reserved_projection": projection,
            "answers_question": pending["question"]["id"],
            "answers_gap": pending["question"]["answers_gap"],
            "lineage": lineage,
            "interview_contract": PROJECTION_INTERVIEW_CONTRACT,
            "interview_path": paths["interview_path"],
            "attachment_path": source["stored_path"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    active = {
        "source_id": source_id,
        "source_sha256": source["sha256"],
        "reserved_projection": projection,
        "lineage": lineage,
        "request_ledger_sequence": sequence,
        "paths": paths,
    }
    _append_ledger(work / "ledger.jsonl", [started])
    state.update({
        "status": "waiting_for_model",
        "phase": "interviewing_additional_source_projection",
        "waiting_for": paths["interview_path"],
        "question": None,
        "active_additional_projection": active,
        "ledger_entries": sequence,
        "ledger_tail_sha256": started["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _additional_projection_waiting_result(state, work)


def _create_additional_verbatim_utf8_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    pending: dict[str, object],
) -> dict[str, object]:
    source = pending["source"]
    reservation = pending["projection"]
    assert isinstance(source, dict) and isinstance(reservation, dict)
    source_id = str(source["id"])
    projection = _verbatim_utf8_projection_record(source_id, str(source["sha256"]))
    if projection["id"] != reservation.get("id"):
        return _blocked(
            "invalid ledger", "the verbatim projection does not fill its reserved identity"
        )
    projection_path = work / str(projection["path"])
    if projection_path.exists():
        return _blocked(
            "unbound projection artifact",
            f"the verbatim projection already exists outside the ledger: {projection['path']}",
        )
    try:
        frozen = (work / str(source["stored_path"])).read_bytes()
    except OSError:
        return _blocked(
            "immutable source unavailable", "the frozen additional source cannot be read"
        )
    projection_bytes, projection_error = _verbatim_utf8_bytes(frozen)
    if projection_error:
        return projection_error
    assert projection_bytes is not None
    if _digest_bytes(projection_bytes) != source["sha256"]:
        return _blocked(
            "immutable source changed",
            "the frozen additional source changed before verbatim projection",
        )
    projection_path.write_bytes(projection_bytes)
    created = _ledger_entry(
        len(entries) + 1,
        "projection_version_created",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": 1,
            "role": "verbatim_utf8_projection",
            "source_id": source_id,
            "source_sha256": source["sha256"],
            "reserved_projection": reservation,
            "projection": projection,
            "answers_question": pending["question"]["id"],
            "answers_gap": pending["question"]["answers_gap"],
            "lineage": pending["lineage"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [created])
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "additional_source_projection_recorded",
        "waiting_for": None,
        "question": None,
        "additional_source_projection": projection,
        "additional_projection_completion": {
            "role": "verbatim_utf8_projection",
            "source_id": source_id,
            "source_sha256": source["sha256"],
            "projection_sha256": projection["sha256"],
            "reserved_projection": reservation,
            "lineage": pending["lineage"],
            "ledger_sequence": len(entries) + 1,
        },
        "ledger_entries": len(entries) + 1,
        "ledger_tail_sha256": created["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _additional_projection_ready_result(state, work)


def _validate_additional_verbatim_utf8_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    pending = state.get("pending_additional_source")
    completion = state.get("additional_projection_completion")
    projection = state.get("additional_source_projection")
    if (
        not isinstance(pending, dict)
        or not isinstance(completion, dict)
        or not isinstance(projection, dict)
    ):
        return _blocked(
            "invalid intake state", "the additional verbatim projection identity is missing"
        )
    source = pending.get("source")
    reservation = pending.get("projection")
    sequence = completion.get("ledger_sequence")
    if (
        not isinstance(source, dict)
        or not isinstance(reservation, dict)
        or not isinstance(sequence, int)
        or sequence > len(entries)
        or (not allow_later_phase and sequence != len(entries))
    ):
        return _blocked(
            "invalid ledger", "the additional verbatim projection sequence changed"
        )
    expected_projection = _verbatim_utf8_projection_record(
        str(source.get("id")), str(source.get("sha256"))
    )
    expected_completion = {
        "role": "verbatim_utf8_projection",
        "source_id": source.get("id"),
        "source_sha256": source.get("sha256"),
        "projection_sha256": expected_projection["sha256"],
        "reserved_projection": reservation,
        "lineage": pending.get("lineage"),
        "ledger_sequence": sequence,
    }
    created = entries[sequence - 1]
    try:
        source_bytes = (work / str(source["stored_path"])).read_bytes()
        projection_bytes = (work / str(expected_projection["path"])).read_bytes()
    except OSError:
        return _blocked(
            "immutable projection unavailable", str(expected_projection["path"])
        )
    _, utf8_error = _verbatim_utf8_bytes(source_bytes)
    if utf8_error:
        return _blocked("invalid ledger", str(utf8_error["why"]))
    if (
        projection != expected_projection
        or completion != expected_completion
        or source_bytes != projection_bytes
        or _digest_bytes(source_bytes) != source.get("sha256")
        or created.get("event") != "projection_version_created"
        or created.get("attempt") != 1
        or created.get("role") != "verbatim_utf8_projection"
        or created.get("source_id") != source.get("id")
        or created.get("source_sha256") != source.get("sha256")
        or created.get("reserved_projection") != reservation
        or created.get("projection") != projection
        or created.get("answers_question") != pending["question"]["id"]
        or created.get("answers_gap") != pending["question"]["answers_gap"]
        or created.get("lineage") != pending.get("lineage")
        or (
            not allow_later_phase
            and (
                state.get("status") != "ready_for_projection_assessment"
                or state.get("phase") != "additional_source_projection_recorded"
                or state.get("waiting_for") is not None
                or state.get("question") is not None
                or state.get("ledger_entries") != len(entries)
                or state.get("ledger_tail_sha256")
                != created.get("entry_sha256")
            )
        )
    ):
        return _blocked(
            "invalid ledger", "the additional verbatim UTF-8 projection changed"
        )
    return None


def _validate_additional_projection_request(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    *,
    recorded: bool = False,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    pending = state.get("pending_additional_source")
    active = state.get("active_additional_projection")
    if not isinstance(pending, dict) or not isinstance(active, dict):
        return _blocked(
            "invalid intake state", "the active additional projection identity is missing"
        )
    source = pending.get("source")
    projection = pending.get("projection")
    lineage = pending.get("lineage")
    sequence = active.get("request_ledger_sequence")
    if (
        not isinstance(source, dict)
        or not isinstance(projection, dict)
        or not isinstance(lineage, dict)
        or not isinstance(sequence, int)
        or sequence < 1
        or sequence > len(entries)
    ):
        return _blocked(
            "invalid intake state", "the active additional projection identity changed"
        )
    source_id = source.get("id")
    if not isinstance(source_id, str):
        return _blocked("invalid intake state", "the active projection source is missing")
    paths = _additional_projection_paths(source_id)
    expected_active = {
        "source_id": source_id,
        "source_sha256": source.get("sha256"),
        "reserved_projection": projection,
        "lineage": lineage,
        "request_ledger_sequence": sequence,
        "paths": paths,
    }
    started = entries[sequence - 1]
    expected_started = {
        "attempt": 1,
        "role": "additional_source_projection",
        "source_id": source_id,
        "source_sha256": source.get("sha256"),
        "reserved_projection": projection,
        "answers_question": pending["question"]["id"],
        "answers_gap": pending["question"]["answers_gap"],
        "lineage": lineage,
        "interview_contract": PROJECTION_INTERVIEW_CONTRACT,
        "interview_path": paths["interview_path"],
        "attachment_path": source.get("stored_path"),
    }
    if (
        active != expected_active
        or started.get("event") != "model_projection_interview_started"
        or any(started.get(key) != value for key, value in expected_started.items())
        or (
            not allow_later_phase
            and (
                state.get("phase")
                != (
                    "additional_source_projection_recorded"
                    if recorded
                    else "interviewing_additional_source_projection"
                )
                or state.get("status")
                != (
                    "ready_for_projection_assessment"
                    if recorded
                    else "waiting_for_model"
                )
                or state.get("waiting_for")
                != (None if recorded else paths["interview_path"])
            )
        )
    ):
        return _blocked(
            "invalid ledger", "the additional projection request changed"
        )
    return None


def _collect_additional_projection_artifacts(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> tuple[dict[str, object] | None, str | None, dict[str, object] | None]:
    pending = state["pending_additional_source"]
    active = state["active_additional_projection"]
    assert isinstance(pending, dict) and isinstance(active, dict)
    source = pending["source"]
    paths = active["paths"]
    request_sequence = active["request_ledger_sequence"]
    assert isinstance(source, dict) and isinstance(paths, dict)
    assert isinstance(request_sequence, int)
    attempt_dir = work / str(paths["interview_dir"])
    try:
        projection, journal_sha256, candidate_sha256 = projection_interview.validate(
            attempt_dir,
            source_sha256=str(source["sha256"]),
            purpose=purpose,
            contract=int(entries[request_sequence - 1]["interview_contract"]),
        )
        journal_entries = projection_interview._read_journal(
            attempt_dir / "interview.jsonl"
        )
    except projection_interview.InterviewError as error:
        return None, None, _blocked("invalid projection interview", str(error))
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
    if int(entries[request_sequence - 1]["interview_contract"]) >= 7:
        verification_dir = work / str(paths["verification_dir"])
        if not (verification_dir / "verification.json").exists():
            return None, "verify_additional_source_projection", None
        try:
            verification, verification_journal_sha256, verification_result_sha256 = (
                relationship_verification.validate(
                    verification_dir,
                    candidate_path=work / str(paths["candidate_path"]),
                    candidate_sha256=candidate_sha256,
                    purpose=purpose,
                )
            )
        except relationship_verification.VerificationError as error:
            return None, None, _blocked("invalid relationship verification", str(error))
        rejected_count = sum(
            verdict["verdict"] != "supported" for verdict in verification["verdicts"]
        )
        if rejected_count:
            correction_dir = work / str(paths["correction_dir"])
            if not (correction_dir / "corrections.json").exists():
                return None, "correct_additional_source_relationships", None
            try:
                (
                    corrections,
                    correction_journal_sha256,
                    correction_result_sha256,
                    correction_candidate_sha256,
                ) = relationship_correction.validate(
                    correction_dir,
                    candidate_path=work / str(paths["candidate_path"]),
                    candidate_sha256=candidate_sha256,
                    verification_path=work / str(paths["verification_path"]),
                    verification_sha256=str(verification_result_sha256),
                    purpose=purpose,
                )
            except relationship_correction.CorrectionError as error:
                return None, None, _blocked("invalid relationship correction", str(error))
            proposed_count = sum(
                item["action"] == "propose_replacement_endpoint"
                for item in corrections["corrections"]
            )
            if proposed_count:
                correction_verification_dir = work / str(
                    paths["correction_verification_dir"]
                )
                if not (correction_verification_dir / "verification.json").exists():
                    return (
                        None,
                        "verify_additional_source_relationship_corrections",
                        None,
                    )
                try:
                    (
                        correction_verification,
                        correction_verification_journal_sha256,
                        correction_verification_result_sha256,
                    ) = relationship_verification.validate(
                        correction_verification_dir,
                        candidate_path=work / str(paths["correction_candidate_path"]),
                        candidate_sha256=str(correction_candidate_sha256),
                        purpose=purpose,
                    )
                except relationship_verification.VerificationError as error:
                    return None, None, _blocked(
                        "invalid relationship correction verification", str(error)
                    )
        verification_error = _apply_independent_verification(
            projection, verification, corrections, correction_verification
        )
        if verification_error:
            return None, None, verification_error
    return {
        "projection": projection,
        "journal_sha256": journal_sha256,
        "candidate_sha256": candidate_sha256,
        "journal_entries": journal_entries,
        "verification": verification,
        "verification_journal_sha256": verification_journal_sha256,
        "verification_result_sha256": verification_result_sha256,
        "corrections": corrections,
        "correction_journal_sha256": correction_journal_sha256,
        "correction_result_sha256": correction_result_sha256,
        "correction_candidate_sha256": correction_candidate_sha256,
        "correction_verification": correction_verification,
        "correction_verification_journal_sha256": correction_verification_journal_sha256,
        "correction_verification_result_sha256": correction_verification_result_sha256,
    }, None, None


def _additional_projection_record(
    source_id: str,
    path: str,
    projection_bytes: bytes,
    projection: dict[str, object],
) -> dict[str, object]:
    gap_count = sum(item["status"] == "gap" for item in projection["elements"])
    gap_count += sum(item["status"] == "gap" for item in projection["relationships"])
    gap_count += sum(
        item["status"] == "gap" for item in projection.get("scan_regions", [])
    )
    return {
        "id": f"projection-{source_id}-v1",
        "source_id": source_id,
        "version": 1,
        "path": path,
        "sha256": _digest_bytes(projection_bytes),
        "method": "visual_spatial",
        "element_count": len(projection["elements"]),
        "relationship_count": len(projection["relationships"]),
        "gap_count": gap_count,
        "coverage": "unassessed",
    }


def _additional_projection_completion_payload(
    active: dict[str, object], bundle: dict[str, object]
) -> dict[str, object]:
    paths = active["paths"]
    assert isinstance(paths, dict)
    journal_entries = bundle["journal_entries"]
    assert isinstance(journal_entries, list)
    return {
        "attempt": 1,
        "role": "additional_source_projection",
        "source_id": active["source_id"],
        "reserved_projection": active["reserved_projection"],
        "lineage": active["lineage"],
        "interview_path": paths["interview_path"],
        "interview_sha256": bundle["journal_sha256"],
        "attempt_projection_path": paths["candidate_path"],
        "attempt_projection_sha256": bundle["candidate_sha256"],
        "question_count": sum(
            entry["event"] == "question_asked" for entry in journal_entries
        ),
        "answer_count": sum(
            entry["event"] == "answer_recorded" for entry in journal_entries
        ),
        "rejected_answer_count": sum(
            entry["event"] == "answer_recorded" and entry["accepted"] is False
            for entry in journal_entries
        ),
        "verification_path": (
            paths["verification_journal_path"]
            if bundle["verification"] is not None
            else None
        ),
        "verification_journal_sha256": bundle["verification_journal_sha256"],
        "verification_result_sha256": bundle["verification_result_sha256"],
        "correction_path": (
            paths["correction_journal_path"]
            if bundle["corrections"] is not None
            else None
        ),
        "correction_journal_sha256": bundle["correction_journal_sha256"],
        "correction_result_sha256": bundle["correction_result_sha256"],
        "correction_candidate_sha256": bundle["correction_candidate_sha256"],
        "correction_verification_path": (
            paths["correction_verification_journal_path"]
            if bundle["correction_verification"] is not None
            else None
        ),
        "correction_verification_journal_sha256": bundle[
            "correction_verification_journal_sha256"
        ],
        "correction_verification_result_sha256": bundle[
            "correction_verification_result_sha256"
        ],
    }


def _additional_projection_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    pending = state["pending_additional_source"]
    assert isinstance(pending, dict)
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "additional_source_projection_recorded",
        "intake_id": state["intake_id"],
        "source": pending["source"],
        "projection": state["additional_source_projection"],
        "reserved_projection": pending["projection"],
        "lineage": pending["lineage"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _additional_source_gap_assessment_paths(source_id: str) -> dict[str, str]:
    directory = f"additional-source-gap-assessments/{source_id}"
    return {
        "directory": directory,
        "interview_path": f"{directory}/interview.jsonl",
        "result_path": f"{directory}/assessment.json",
    }


def _gap_identity(gap: dict[str, object]) -> dict[str, object]:
    return {
        key: gap[key]
        for key in (
            "projection_sha256",
            "collection",
            "kind",
            "id",
            "record_sha256",
        )
    }


def _stable_gap_identity(gap: dict[str, object]) -> dict[str, object]:
    return {
        key: gap[key]
        for key in ("collection", "kind", "id", "record_sha256")
    }


def _pending_additional_source_gap(
    state: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    pending = state.get("pending_additional_source")
    if not isinstance(pending, dict):
        return None, _blocked(
            "additional source gap assessment unavailable",
            "the projected additional source lost its question lineage",
        )
    question = pending.get("question")
    lineage = pending.get("lineage")
    if not isinstance(question, dict) or not isinstance(lineage, dict):
        return None, _blocked(
            "additional source gap assessment unavailable",
            "the projected additional source lost its exact question or round",
        )
    round_number = lineage.get("question_round")
    saved_round = (
        state.get("gap_question_round")
        if round_number == 1
        else state.get("follow_up_gap_question_round")
    )
    gaps = saved_round.get("gaps") if isinstance(saved_round, dict) else None
    identity = question.get("answers_gap")
    if (
        not isinstance(round_number, int)
        or round_number < 1
        or not isinstance(gaps, list)
        or not isinstance(identity, dict)
    ):
        return None, _blocked(
            "additional source gap assessment unavailable",
            "the originating question round or gap inventory is missing",
        )
    matching = [
        gap
        for gap in gaps
        if isinstance(gap, dict) and _gap_identity(gap) == identity
    ]
    if len(matching) != 1:
        return None, _blocked(
            "additional source gap assessment unavailable",
            f"the originating question points to {len(matching)} exact gaps; expected 1",
        )
    return matching[0], None


def _original_gap_projection_identity(
    work: Path, state: dict[str, object], gap: dict[str, object]
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    projection_sha256 = gap.get("projection_sha256")
    for key in ("current_projection", "first_projection"):
        record = state.get(key)
        if (
            isinstance(record, dict)
            and record.get("sha256") == projection_sha256
            and isinstance(record.get("id"), str)
        ):
            return {
                "id": record["id"],
                "sha256": record["sha256"],
            }, None
    first = state.get("first_projection")
    if isinstance(first, dict) and first.get("method") == "pdf_visible_pages":
        try:
            manifest = json.loads(
                (work / str(first["path"])).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError, KeyError) as error:
            return None, _blocked(
                "additional source gap assessment unavailable",
                f"the original PDF projection cannot be reconstructed: {error}",
            )
        pages = manifest.get("pages") if isinstance(manifest, dict) else None
        matching = [
            item["readable_projection"]
            for item in pages or []
            if isinstance(item, dict)
            and isinstance(item.get("readable_projection"), dict)
            and item["readable_projection"].get("sha256") == projection_sha256
        ]
        if len(matching) == 1 and isinstance(matching[0].get("id"), str):
            return {
                "id": matching[0]["id"],
                "sha256": matching[0]["sha256"],
            }, None
    return None, _blocked(
        "additional source gap assessment unavailable",
        "the exact projection that produced the original gap is not preserved",
    )


def _additional_projection_evidence(
    work: Path,
    projection: dict[str, object],
) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    path, projection_sha256, path_error = _validated_projection_record(
        work, projection
    )
    if path_error:
        return None, path_error
    assert path is not None and projection_sha256 is not None
    method = projection.get("method")
    records: list[tuple[str, str, dict[str, object]]] = []
    if method == "verbatim_utf8":
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return None, _blocked(
                "additional source gap assessment unavailable",
                f"the verbatim additional projection is unreadable: {error}",
            )
        records.append(("content", "content-000001", {"text": text}))
    elif method == "visual_spatial":
        try:
            readable = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return None, _blocked(
                "additional source gap assessment unavailable",
                f"the visual additional projection is unreadable: {error}",
            )
        if not isinstance(readable, dict):
            return None, _blocked(
                "additional source gap assessment unavailable",
                "the visual additional projection is not one readable record",
            )
        for collection in ("elements", "relationships"):
            items = readable.get(collection)
            if not isinstance(items, list):
                return None, _blocked(
                    "additional source gap assessment unavailable",
                    f"the visual additional projection lost its {collection} list",
                )
            for position, item in enumerate(items, 1):
                if not isinstance(item, dict):
                    return None, _blocked(
                        "additional source gap assessment unavailable",
                        f"{collection} item {position} is not one record",
                    )
                if item.get("status") != "readable":
                    continue
                item_id = item.get("id")
                if not isinstance(item_id, str) or not item_id:
                    return None, _blocked(
                        "additional source gap assessment unavailable",
                        f"readable {collection} item {position} has no stable identity",
                    )
                records.append((collection, item_id, item))
    else:
        return None, _blocked(
            "additional source gap assessment unavailable",
            f"projection method {method!r} has no readable-evidence adapter",
        )
    return [
        {
            "evidence_id": f"evidence-{index:06d}",
            "projection_id": projection["id"],
            "projection_sha256": projection_sha256,
            "collection": collection,
            "item_id": item_id,
            "item_sha256": _digest_bytes(_canonical(item)),
            "item": item,
        }
        for index, (collection, item_id, item) in enumerate(records, 1)
    ], None


def _additional_source_gap_assessment_binding(
    work: Path,
    state: dict[str, object],
    *,
    current_projection: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    pending = state.get("pending_additional_source")
    projection = state.get("additional_source_projection")
    current = current_projection or state.get(
        "current_projection", state.get("first_projection")
    )
    if (
        not isinstance(pending, dict)
        or not isinstance(pending.get("source"), dict)
        or not isinstance(pending.get("question"), dict)
        or not isinstance(projection, dict)
        or not isinstance(current, dict)
        or not isinstance(current.get("id"), str)
        or not isinstance(current.get("sha256"), str)
    ):
        return None, _blocked(
            "additional source gap assessment unavailable",
            "the projected source, question, or current projection identity is missing",
        )
    gap, gap_error = _pending_additional_source_gap(state)
    if gap_error:
        return None, gap_error
    assert gap is not None
    original, original_error = _original_gap_projection_identity(
        work, state, gap
    )
    if original_error:
        return None, original_error
    evidence, evidence_error = _additional_projection_evidence(work, projection)
    if evidence_error:
        return None, evidence_error
    assert original is not None and evidence is not None
    return {
        "gap": gap,
        "question": pending["question"],
        "original_projection": original,
        "current_projection": {
            "id": current["id"],
            "sha256": current["sha256"],
        },
        "additional_source": pending["source"],
        "additional_projection": projection,
        "evidence": evidence,
    }, None


def _additional_source_gap_assessment_attachments(
    work: Path, state: dict[str, object], binding: dict[str, object]
) -> tuple[list[str] | None, dict[str, object] | None]:
    pending = state["pending_additional_source"]
    first_source = state.get("first_source")
    assert isinstance(pending, dict)
    gap = binding["gap"]
    additional_source = pending["source"]
    assert isinstance(gap, dict) and isinstance(additional_source, dict)
    candidates: list[tuple[str, str]] = []
    if isinstance(gap.get("render_path"), str) and isinstance(
        gap.get("render_sha256"), str
    ):
        candidates.append((str(gap["render_path"]), str(gap["render_sha256"])))
    elif (
        isinstance(first_source, dict)
        and isinstance(first_source.get("stored_path"), str)
        and isinstance(first_source.get("sha256"), str)
        and str(first_source.get("media_type", "")).startswith("image/")
    ):
        candidates.append(
            (str(first_source["stored_path"]), str(first_source["sha256"]))
        )
    if (
        isinstance(additional_source.get("stored_path"), str)
        and isinstance(additional_source.get("sha256"), str)
        and str(additional_source.get("media_type", "")).startswith("image/")
    ):
        candidates.append(
            (
                str(additional_source["stored_path"]),
                str(additional_source["sha256"]),
            )
        )
    attachments: list[str] = []
    for stored_path, expected_sha256 in candidates:
        path = (work / stored_path).resolve()
        try:
            path.relative_to(work.resolve())
            received_sha256 = _digest_bytes(path.read_bytes())
        except (ValueError, OSError) as error:
            return None, _blocked(
                "additional source gap assessment unavailable",
                f"a frozen assessment attachment is unavailable: {error}",
            )
        if received_sha256 != expected_sha256:
            return None, _blocked(
                "additional source gap assessment unavailable",
                f"assessment attachment {stored_path} changed",
            )
        resolved = str(path)
        if resolved not in attachments:
            attachments.append(resolved)
    if not attachments:
        return None, _blocked(
            "additional source gap assessment unavailable",
            "the original gap has no preserved visual context attachment",
        )
    return attachments, None


def _additional_source_gap_assessment_waiting_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    saved = state["additional_source_gap_assessment"]
    assert isinstance(saved, dict)
    binding = saved["binding"]
    assert isinstance(binding, dict)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--work",
        str(work.resolve()),
        "--run-additional-source-gap-assessment",
    ]
    return {
        "status": "waiting_for_model",
        "stopped": "assessing_additional_source_gap",
        "intake_id": state["intake_id"],
        "gap": binding["gap"],
        "evidence": binding["evidence"],
        "work": [{
            "stage": "assess_additional_source_gap",
            "instruction": (
                "Inspect the frozen source context, run the command, and answer only the "
                "typed question currently displayed. Code controls the gap, evidence choices, "
                "verdict choices, and immutable result."
            ),
            "attachments": saved["attachments"],
            "command": command,
        }],
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _additional_source_gap_assessment_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    saved = state["additional_source_gap_assessment"]
    pending = state["pending_additional_source"]
    assert isinstance(saved, dict) and isinstance(pending, dict)
    result = saved["result"]
    assert isinstance(result, dict) and isinstance(result.get("assessment"), dict)
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "additional_source_gap_assessment_recorded",
        "intake_id": state["intake_id"],
        "source": pending["source"],
        "projection": state["additional_source_projection"],
        "reserved_projection": pending["projection"],
        "lineage": pending["lineage"],
        "assessment": result["assessment"],
        "assessment_path": saved["paths"]["result_path"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _request_additional_source_gap_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    binding, binding_error = _additional_source_gap_assessment_binding(work, state)
    if binding_error:
        return binding_error
    assert binding is not None
    attachments, attachment_error = _additional_source_gap_assessment_attachments(
        work, state, binding
    )
    if attachment_error:
        return attachment_error
    assert attachments is not None
    source = binding["additional_source"]
    assert isinstance(source, dict) and isinstance(source.get("id"), str)
    paths = _additional_source_gap_assessment_paths(str(source["id"]))
    request = _ledger_entry(
        len(entries) + 1,
        "model_additional_source_gap_assessment_requested",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "contract": additional_source_gap_assessment.CONTRACT,
            "binding": binding,
            "attachments": attachments,
            "interview_path": paths["interview_path"],
            "result_path": paths["result_path"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [request])
    state.update({
        "status": "waiting_for_model",
        "phase": "assessing_additional_source_gap",
        "waiting_for": paths["interview_path"],
        "question": None,
        "additional_source_gap_assessment": {
            "contract": additional_source_gap_assessment.CONTRACT,
            "binding": binding,
            "attachments": attachments,
            "paths": paths,
            "request_ledger_sequence": request["sequence"],
        },
        "ledger_entries": request["sequence"],
        "ledger_tail_sha256": request["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _additional_source_gap_assessment_waiting_result(state, work)


def _validate_additional_source_gap_assessment_request(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    *,
    allow_later_phase: bool = False,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    saved = state.get("additional_source_gap_assessment")
    if not isinstance(saved, dict):
        return None, _blocked(
            "invalid additional source gap assessment",
            "the immutable assessment request is missing",
        )
    admission = state.get("additional_source_element_gap_admission")
    parent = (
        admission.get("parent_projection")
        if allow_later_phase and isinstance(admission, dict)
        else None
    )
    binding, binding_error = _additional_source_gap_assessment_binding(
        work,
        state,
        current_projection=parent if isinstance(parent, dict) else None,
    )
    if binding_error:
        return None, binding_error
    assert binding is not None
    attachments, attachment_error = _additional_source_gap_assessment_attachments(
        work, state, binding
    )
    if attachment_error:
        return None, attachment_error
    source = binding["additional_source"]
    assert isinstance(source, dict)
    paths = _additional_source_gap_assessment_paths(str(source["id"]))
    sequence = saved.get("request_ledger_sequence")
    if not isinstance(sequence, int) or sequence < 1 or sequence > len(entries):
        return None, _blocked(
            "invalid additional source gap assessment",
            "the assessment request sequence is missing or outside the ledger",
        )
    request = entries[sequence - 1]
    expected_saved = {
        "contract": additional_source_gap_assessment.CONTRACT,
        "binding": binding,
        "attachments": attachments,
        "paths": paths,
        "request_ledger_sequence": sequence,
    }
    if (
        any(saved.get(key) != value for key, value in expected_saved.items())
        or request.get("event")
        != "model_additional_source_gap_assessment_requested"
        or request.get("intake_id") != state.get("intake_id")
        or request.get("contract") != additional_source_gap_assessment.CONTRACT
        or request.get("binding") != binding
        or request.get("attachments") != attachments
        or request.get("interview_path") != paths["interview_path"]
        or request.get("result_path") != paths["result_path"]
    ):
        return None, _blocked(
            "invalid additional source gap assessment",
            "the assessment request, binding, evidence, or attachment list changed",
        )
    return binding, None


def _consume_additional_source_gap_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    binding, request_error = _validate_additional_source_gap_assessment_request(
        work, state, entries
    )
    if request_error:
        return request_error
    assert binding is not None
    saved = state["additional_source_gap_assessment"]
    assert isinstance(saved, dict) and isinstance(saved.get("paths"), dict)
    paths = saved["paths"]
    try:
        result, journal_sha256, result_sha256 = (
            additional_source_gap_assessment.validate(
                work / str(paths["directory"]),
                binding=binding,
                purpose=purpose,
            )
        )
        journal_entries = additional_source_gap_assessment._read_journal(
            work / str(paths["interview_path"])
        )
    except additional_source_gap_assessment.AssessmentError as error:
        return _blocked("invalid additional source gap assessment", str(error))
    assessment = result.get("assessment")
    if not isinstance(assessment, dict):
        return _blocked(
            "invalid additional source gap assessment",
            "the completed result contains no assessment",
        )
    completed = _ledger_entry(
        len(entries) + 1,
        "model_additional_source_gap_assessment_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "contract": additional_source_gap_assessment.CONTRACT,
            "request_ledger_sequence": saved["request_ledger_sequence"],
            "interview_path": paths["interview_path"],
            "interview_sha256": journal_sha256,
            "result_path": paths["result_path"],
            "result_sha256": result_sha256,
            "question_count": sum(
                entry["event"] == "question_asked" for entry in journal_entries
            ),
            "answer_count": sum(
                entry["event"] == "answer_recorded" for entry in journal_entries
            ),
            "rejected_answer_count": sum(
                entry["event"] == "answer_recorded"
                and entry["accepted"] is False
                for entry in journal_entries
            ),
            "assessment": assessment,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed])
    saved.update({
        "interview_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "result": result,
        "completion_ledger_sequence": completed["sequence"],
    })
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "additional_source_gap_assessment_recorded",
        "waiting_for": None,
        "question": None,
        "ledger_entries": completed["sequence"],
        "ledger_tail_sha256": completed["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _additional_source_gap_assessment_ready_result(state, work)


def _validate_recorded_additional_source_gap_assessment(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    binding, request_error = _validate_additional_source_gap_assessment_request(
        work, state, entries, allow_later_phase=allow_later_phase
    )
    if request_error:
        return request_error
    assert binding is not None
    saved = state["additional_source_gap_assessment"]
    assert isinstance(saved, dict) and isinstance(saved.get("paths"), dict)
    paths = saved["paths"]
    try:
        result, journal_sha256, result_sha256 = (
            additional_source_gap_assessment.validate(
                work / str(paths["directory"]),
                binding=binding,
                purpose=purpose,
            )
        )
        journal_entries = additional_source_gap_assessment._read_journal(
            work / str(paths["interview_path"])
        )
    except additional_source_gap_assessment.AssessmentError as error:
        return _blocked("invalid additional source gap assessment", str(error))
    sequence = saved.get("completion_ledger_sequence")
    completion = (
        entries[sequence - 1]
        if isinstance(sequence, int) and 1 <= sequence <= len(entries)
        else None
    )
    assessment = result.get("assessment")
    if (
        not isinstance(assessment, dict)
        or not isinstance(completion, dict)
        or sequence != saved.get("request_ledger_sequence", 0) + 1
        or (not allow_later_phase and len(entries) != sequence)
        or completion.get("event")
        != "model_additional_source_gap_assessment_completed"
        or completion.get("request_ledger_sequence")
        != saved.get("request_ledger_sequence")
        or completion.get("interview_path") != paths["interview_path"]
        or completion.get("interview_sha256") != journal_sha256
        or completion.get("result_path") != paths["result_path"]
        or completion.get("result_sha256") != result_sha256
        or completion.get("question_count")
        != sum(entry["event"] == "question_asked" for entry in journal_entries)
        or completion.get("answer_count")
        != sum(entry["event"] == "answer_recorded" for entry in journal_entries)
        or completion.get("rejected_answer_count")
        != sum(
            entry["event"] == "answer_recorded" and entry["accepted"] is False
            for entry in journal_entries
        )
        or completion.get("assessment") != assessment
        or saved.get("interview_sha256") != journal_sha256
        or saved.get("result_sha256") != result_sha256
        or saved.get("result") != result
        or (
            not allow_later_phase
            and (
                state.get("ledger_entries") != len(entries)
                or state.get("ledger_tail_sha256")
                != completion.get("entry_sha256")
            )
        )
    ):
        return _blocked(
            "invalid additional source gap assessment",
            "the completed assessment, journal, result, or ledger binding changed",
        )
    return None


def _additional_source_element_gap_admission_input(
    state: dict[str, object],
    *,
    parent_projection: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    saved = state.get("additional_source_gap_assessment")
    result = saved.get("result") if isinstance(saved, dict) else None
    assessment = result.get("assessment") if isinstance(result, dict) else None
    if not isinstance(assessment, dict):
        return None, _blocked(
            "additional source element-gap admission unavailable",
            "the immutable additional-source assessment is missing",
        )
    gap = assessment.get("gap")
    evidence = assessment.get("evidence")
    if (
        assessment.get("verdict") != "resolves_gap"
        or not isinstance(gap, dict)
        or gap.get("collection") != "elements"
    ):
        return None, None
    if not isinstance(evidence, list) or len(evidence) != 1:
        return None, _blocked(
            "additional source element-gap admission unavailable",
            "one element gap requires exactly one selected readable element",
        )
    selected = evidence[0]
    item = selected.get("item") if isinstance(selected, dict) else None
    if (
        not isinstance(selected, dict)
        or selected.get("collection") != "elements"
        or not isinstance(item, dict)
        or item.get("status") != "readable"
        or not isinstance(item.get("content"), str)
        or not item["content"].strip()
    ):
        return None, _blocked(
            "additional source element-gap admission unavailable",
            "the selected evidence is not one readable element with content",
        )
    parent = parent_projection or state.get(
        "current_projection", state.get("first_projection")
    )
    assessed_parent = assessment.get("current_projection")
    if (
        not isinstance(parent, dict)
        or not isinstance(assessed_parent, dict)
        or parent.get("id") != assessed_parent.get("id")
        or parent.get("sha256") != assessed_parent.get("sha256")
    ):
        return None, _blocked(
            "additional source element-gap admission unavailable",
            "the current parent projection changed after the assessment",
        )
    if (
        not isinstance(saved, dict)
        or not isinstance(saved.get("result_sha256"), str)
        or not isinstance(saved.get("completion_ledger_sequence"), int)
    ):
        return None, _blocked(
            "additional source element-gap admission unavailable",
            "the accepted assessment lost its result or ledger identity",
        )
    source = assessment.get("additional_source")
    additional_projection = assessment.get("additional_projection")
    if not isinstance(source, dict) or not isinstance(additional_projection, dict):
        return None, _blocked(
            "additional source element-gap admission unavailable",
            "the selected evidence lost its source or projection lineage",
        )
    admission = {
        "contract": 1,
        "parent_projection": parent,
        "gap": gap,
        "assessment_result_sha256": saved["result_sha256"],
        "assessment_completion_ledger_sequence": saved[
            "completion_ledger_sequence"
        ],
        "additional_source": source,
        "additional_projection": additional_projection,
        "selected_evidence": selected,
    }
    admission["input_sha256"] = _digest_bytes(_canonical(admission))
    return admission, None


def _build_additional_source_element_gap_projection(
    work: Path,
    admission: dict[str, object],
) -> tuple[bytes, dict[str, object]]:
    parent = admission["parent_projection"]
    gap = admission["gap"]
    selected = admission["selected_evidence"]
    assert isinstance(parent, dict)
    assert isinstance(gap, dict)
    assert isinstance(selected, dict)
    parent_path, _, parent_error = _validated_projection_record(work, parent)
    if parent_error or parent_path is None:
        raise ValueError(
            parent_error.get("why", "parent projection is unavailable")
            if isinstance(parent_error, dict)
            else "parent projection is unavailable"
        )
    projection = json.loads(parent_path.read_text(encoding="utf-8"))
    elements = projection.get("elements") if isinstance(projection, dict) else None
    if not isinstance(elements, list):
        raise ValueError("parent projection has no element collection")
    matches = [
        item
        for item in elements
        if isinstance(item, dict) and item.get("id") == gap.get("id")
    ]
    if len(matches) != 1:
        raise ValueError(
            f"element gap {gap.get('id')} appears {len(matches)} times in the parent projection"
        )
    original = matches[0]
    if (
        original != gap.get("record")
        or _digest_bytes(_canonical(original)) != gap.get("record_sha256")
        or original.get("status") != "gap"
    ):
        raise ValueError(
            f"element gap {gap.get('id')} changed after the assessment"
        )
    evidence_item = selected.get("item")
    assert isinstance(evidence_item, dict)
    audit = {
        "contract": admission["contract"],
        "parent_projection_id": parent["id"],
        "parent_projection_sha256": parent["sha256"],
        "original_gap_record_sha256": gap["record_sha256"],
        "assessment_result_sha256": admission["assessment_result_sha256"],
        "assessment_completion_ledger_sequence": admission[
            "assessment_completion_ledger_sequence"
        ],
        "additional_source_id": admission["additional_source"]["id"],
        "additional_source_sha256": admission["additional_source"]["sha256"],
        "additional_projection_id": admission["additional_projection"]["id"],
        "additional_projection_sha256": admission["additional_projection"][
            "sha256"
        ],
        "evidence_id": selected["evidence_id"],
        "evidence_item_id": selected["item_id"],
        "evidence_item_sha256": selected["item_sha256"],
        "admission_input_sha256": admission["input_sha256"],
    }
    replacement = json.loads(json.dumps(original))
    replacement.update({
        "status": "readable",
        "content": evidence_item["content"],
        "gap_reason": "",
        "resolution_audit": audit,
    })
    projection["elements"] = [
        replacement
        if isinstance(item, dict) and item.get("id") == gap.get("id")
        else item
        for item in elements
    ]
    projection["projection_lineage"] = {
        "kind": "additional_source_element_gap_admission",
        "parent_projection_id": parent["id"],
        "parent_projection_sha256": parent["sha256"],
        "resolved_gap_id": gap["id"],
        "admission_input_sha256": admission["input_sha256"],
    }
    content = json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    parent_version = parent.get("version")
    source_id = parent.get("source_id")
    if not isinstance(parent_version, int) or parent_version < 1:
        raise ValueError("parent projection version must be a positive integer")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("parent projection source identity is missing")
    version = parent_version + 1
    gap_count = sum(
        item.get("status") == "gap"
        for collection in ("scan_regions", "elements", "relationships")
        for item in projection.get(collection, [])
        if isinstance(item, dict)
    )
    record = {
        "id": f"projection-{source_id}-v{version}",
        "source_id": source_id,
        "version": version,
        "parent_projection_id": parent["id"],
        "path": f"projections/{source_id}-v{version}.json",
        "sha256": _digest_bytes(content),
        "element_count": len(projection["elements"]),
        "relationship_count": len(projection.get("relationships", [])),
        "gap_count": gap_count,
        "coverage": "unassessed",
    }
    return content, record


def _additional_source_element_gap_admission_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    admission = state["additional_source_element_gap_admission"]
    assert isinstance(admission, dict)
    return {
        "status": "ready_for_projection_assessment",
        "stopped": "additional_source_element_gap_admitted",
        "intake_id": state["intake_id"],
        "projection": admission["projection"],
        "parent_projection": admission["parent_projection"],
        "resolved_gap": admission["gap"],
        "evidence": admission["selected_evidence"],
        "assessment_result_sha256": admission["assessment_result_sha256"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }


def _consume_additional_source_element_gap_admission(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    assessment_error = _validate_recorded_additional_source_gap_assessment(
        work, state, entries, purpose
    )
    if assessment_error:
        return assessment_error
    admission, admission_error = _additional_source_element_gap_admission_input(
        state
    )
    if admission_error:
        return admission_error
    if admission is None:
        return _additional_source_gap_assessment_ready_result(state, work)
    try:
        projection_bytes, projection_record = (
            _build_additional_source_element_gap_projection(work, admission)
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return _blocked("additional source element-gap admission failed", str(error))
    projection_path = work / str(projection_record["path"])
    if projection_path.exists():
        return _blocked(
            "unbound projection version",
            f"projection path already exists: {projection_record['path']}",
        )
    projection_path.write_bytes(projection_bytes)
    created = _ledger_entry(
        len(entries) + 1,
        "projection_version_created",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "role": "additional_source_element_gap_admission",
            "parent_projection": admission["parent_projection"],
            "resolved_gap": admission["gap"],
            "assessment_result_sha256": admission["assessment_result_sha256"],
            "assessment_completion_ledger_sequence": admission[
                "assessment_completion_ledger_sequence"
            ],
            "additional_source": admission["additional_source"],
            "additional_projection": admission["additional_projection"],
            "selected_evidence": admission["selected_evidence"],
            "admission_input_sha256": admission["input_sha256"],
            "projection": projection_record,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [created])
    saved_admission = {
        **admission,
        "projection": projection_record,
        "ledger_sequence": created["sequence"],
    }
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "additional_source_element_gap_admitted",
        "waiting_for": None,
        "current_projection": projection_record,
        "additional_source_element_gap_admission": saved_admission,
        "ledger_entries": created["sequence"],
        "ledger_tail_sha256": created["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _additional_source_element_gap_admission_ready_result(state, work)


def _validate_additional_source_element_gap_admission(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    saved = state.get("additional_source_element_gap_admission")
    if not isinstance(saved, dict) or not isinstance(
        saved.get("parent_projection"), dict
    ):
        return _blocked(
            "invalid additional source element-gap admission",
            "the immutable admission record is missing",
        )
    assessment_error = _validate_recorded_additional_source_gap_assessment(
        work, state, entries, purpose, allow_later_phase=True
    )
    if assessment_error:
        return assessment_error
    admission, admission_error = _additional_source_element_gap_admission_input(
        state, parent_projection=saved["parent_projection"]
    )
    if admission_error:
        return admission_error
    if admission is None:
        return _blocked(
            "invalid additional source element-gap admission",
            "the preserved assessment is no longer eligible for admission",
        )
    try:
        projection_bytes, projection_record = (
            _build_additional_source_element_gap_projection(work, admission)
        )
        actual_projection_bytes = (work / str(projection_record["path"])).read_bytes()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return _blocked(
            "invalid additional source element-gap admission", str(error)
        )
    sequence = saved.get("ledger_sequence")
    created = (
        entries[sequence - 1]
        if isinstance(sequence, int) and 1 <= sequence <= len(entries)
        else None
    )
    expected_saved = {
        **admission,
        "projection": projection_record,
        "ledger_sequence": sequence,
    }
    if (
        saved != expected_saved
        or actual_projection_bytes != projection_bytes
        or not isinstance(created, dict)
        or sequence != admission["assessment_completion_ledger_sequence"] + 1
        or (not allow_later_phase and len(entries) != sequence)
        or created.get("event") != "projection_version_created"
        or created.get("role") != "additional_source_element_gap_admission"
        or created.get("parent_projection") != admission["parent_projection"]
        or created.get("resolved_gap") != admission["gap"]
        or created.get("assessment_result_sha256")
        != admission["assessment_result_sha256"]
        or created.get("assessment_completion_ledger_sequence")
        != admission["assessment_completion_ledger_sequence"]
        or created.get("additional_source") != admission["additional_source"]
        or created.get("additional_projection")
        != admission["additional_projection"]
        or created.get("selected_evidence") != admission["selected_evidence"]
        or created.get("admission_input_sha256") != admission["input_sha256"]
        or created.get("projection") != projection_record
        or state.get("current_projection") != projection_record
        or (
            not allow_later_phase
            and (
                state.get("ledger_entries") != sequence
                or state.get("ledger_tail_sha256")
                != created.get("entry_sha256")
            )
        )
    ):
        return _blocked(
            "immutable projection changed",
            "the admitted element, its lineage, or its child projection changed",
        )
    return None


def _additional_source_element_gap_continuation_evidence(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    qualification, qualification_error = _terminal_projection_qualification(
        work, state
    )
    if qualification_error:
        return None, None, None, None, qualification_error
    assert qualification is not None
    gaps = qualification.get("remaining_gaps")
    if not isinstance(gaps, list):
        return None, None, None, None, _blocked(
            "terminal_invalid",
            "the admitted child projection lost its exact remaining-gap inventory",
        )
    decision = {
        "decision": "clarification_complete",
        "basis": "additional_source_element_gap_admission",
        "remaining_current_gap_count": len(gaps),
    }
    closure, closure_error = _source_projection_closure_inventory(work, entries)
    if closure_error:
        return None, None, None, None, _blocked(
            "terminal_invalid", str(closure_error["why"])
        )
    assert closure is not None
    disposition, disposition_error = _clarification_terminal_disposition(
        decision, qualification, closure
    )
    if disposition_error:
        return None, None, None, None, disposition_error
    assert disposition is not None
    return decision, qualification, closure, disposition, None


def _resume_question_round_after_additional_source_admission(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    qualification: dict[str, object],
) -> dict[str, object]:
    pending = state.get("pending_additional_source")
    assessment = state.get("additional_source_gap_assessment")
    admission = state.get("additional_source_element_gap_admission")
    additional_projection = state.get("additional_source_projection")
    if (
        not isinstance(pending, dict)
        or not isinstance(assessment, dict)
        or not isinstance(admission, dict)
        or not isinstance(additional_projection, dict)
    ):
        return _blocked(
            "question round resumption unavailable",
            "the admitted additional source lost its immutable intake records",
        )
    lineage = pending.get("lineage")
    question = pending.get("question")
    round_number = (
        lineage.get("question_round") if isinstance(lineage, dict) else None
    )
    position = (
        lineage.get("question_position") if isinstance(lineage, dict) else None
    )
    if (
        not isinstance(lineage, dict)
        or not isinstance(question, dict)
        or not isinstance(round_number, int)
        or round_number < 1
        or not isinstance(position, int)
        or position < 1
    ):
        return _blocked(
            "question round resumption unavailable",
            "the admitted source lost its exact question round and position",
        )
    if round_number == 1:
        saved_round = state.get("gap_question_round")
        questions = state.get("questions")
        answers = state.get("gap_question_answers")
        prepared_result_sha256 = None
    else:
        saved_round = state.get("follow_up_gap_question_round")
        interview = state.get("prepared_question_round_interview")
        questions = (
            saved_round.get("questions") if isinstance(saved_round, dict) else None
        )
        answers = interview.get("answers") if isinstance(interview, dict) else None
        prepared_result_sha256 = (
            saved_round.get("result_sha256")
            if isinstance(saved_round, dict)
            else None
        )
        if (
            not isinstance(interview, dict)
            or interview.get("round") != round_number
            or interview.get("prepared_round_result_sha256")
            != prepared_result_sha256
        ):
            return _blocked(
                "question round resumption unavailable",
                "the prepared operator round identity changed during source intake",
            )
    gaps = saved_round.get("gaps") if isinstance(saved_round, dict) else None
    if (
        not isinstance(questions, list)
        or not isinstance(answers, list)
        or not isinstance(gaps, list)
        or len(questions) != len(gaps)
        or position != len(answers) + 1
        or position > len(questions)
        or questions[position - 1] != question
    ):
        return _blocked(
            "question round resumption unavailable",
            "the admitted source no longer occupies the active prepared question position",
        )
    resolved_gap = admission.get("gap")
    answer_gap = question.get("answers_gap")
    if (
        not isinstance(resolved_gap, dict)
        or not isinstance(answer_gap, dict)
        or _gap_identity(resolved_gap) != answer_gap
    ):
        return _blocked(
            "question round resumption unavailable",
            "the admitted source no longer resolves the active question's exact gap",
        )
    remaining_gaps = qualification.get("remaining_gaps")
    remaining_questions = questions[position:]
    expected_remaining = [
        item.get("answers_gap")
        for item in remaining_questions
        if isinstance(item, dict)
    ]
    if (
        not isinstance(remaining_gaps, list)
        or len(expected_remaining) != len(remaining_questions)
        or len(remaining_gaps) != len(expected_remaining)
        or any(not isinstance(item, dict) for item in remaining_gaps)
        or any(not isinstance(item, dict) for item in expected_remaining)
        or [
            _stable_gap_identity(item)
            for item in remaining_gaps
            if isinstance(item, dict)
        ]
        != [
            _stable_gap_identity(item)
            for item in expected_remaining
            if isinstance(item, dict)
        ]
    ):
        return _blocked(
            "question round resumption unavailable",
            "the exact remaining gaps no longer match the unanswered prepared questions",
        )
    result = assessment.get("result")
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("assessment"), dict)
        or not isinstance(assessment.get("result_sha256"), str)
        or not isinstance(assessment.get("completion_ledger_sequence"), int)
        or not isinstance(pending.get("ledger_sequence"), int)
        or not isinstance(admission.get("ledger_sequence"), int)
    ):
        return _blocked(
            "question round resumption unavailable",
            "the admitted source lost its assessment or ledger identity",
        )
    saved_answer = {
        "answer_kind": "additional_source_admission",
        "question": question,
        "source": pending["source"],
        "projection": additional_projection,
        "fulfillment": {
            "round": round_number,
            "question_position": position,
            "lineage": lineage,
            "reserved_projection": pending["projection"],
            "source_acquisition_ledger_sequence": pending["ledger_sequence"],
            "assessment": result["assessment"],
            "assessment_result_sha256": assessment["result_sha256"],
            "assessment_completion_ledger_sequence": assessment[
                "completion_ledger_sequence"
            ],
            "admission": admission,
        },
    }
    timestamp = datetime.now(timezone.utc).isoformat()
    fulfilled = _ledger_entry(
        len(entries) + 1,
        "operator_question_fulfilled_by_additional_source",
        {
            "recorded_at": timestamp,
            "intake_id": state["intake_id"],
            "round": round_number,
            "question_position": position,
            "answer": saved_answer,
            "remaining_gaps": remaining_gaps,
        },
        str(entries[-1]["entry_sha256"]),
    )
    answers.append(saved_answer)
    if len(answers) < len(questions):
        next_question = questions[len(answers)]
        assert isinstance(next_question, dict)
        following = _ledger_entry(
            len(entries) + 2,
            "operator_question_asked",
            {
                "recorded_at": timestamp,
                "intake_id": state["intake_id"],
                "round": round_number,
                "question_position": len(answers) + 1,
                "question": next_question,
                **(
                    {"prepared_round_result_sha256": prepared_result_sha256}
                    if isinstance(prepared_result_sha256, str)
                    else {}
                ),
            },
            str(fulfilled["entry_sha256"]),
        )
        state.update({
            "status": "needs_operator",
            "phase": (
                "awaiting_gap_answers"
                if round_number == 1
                else "awaiting_prepared_question_round_answers"
            ),
            "waiting_for": next_question["id"],
            "question": next_question,
        })
    else:
        following = _ledger_entry(
            len(entries) + 2,
            "operator_question_round_answered",
            {
                "recorded_at": timestamp,
                "intake_id": state["intake_id"],
                "round": round_number,
                "question_count": len(questions),
                "answered_question_count": len(answers),
                "answer_source_ids": [item["source"]["id"] for item in answers],
                **(
                    {"prepared_round_result_sha256": prepared_result_sha256}
                    if isinstance(prepared_result_sha256, str)
                    else {}
                ),
            },
            str(fulfilled["entry_sha256"]),
        )
        state.update({
            "status": "ready_for_projection_assessment",
            "phase": (
                "gap_question_round_answered"
                if round_number == 1
                else "prepared_question_round_answered"
            ),
            "waiting_for": None,
            "question": None,
        })
    _append_ledger(work / "ledger.jsonl", [fulfilled, following])
    state.update({
        "ledger_entries": len(entries) + 2,
        "ledger_tail_sha256": following["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    if round_number == 1:
        return (
            _gap_question_round_answered_result(state, work)
            if len(answers) == len(questions)
            else _gap_question_round_operator_result(state, work)
        )
    return (
        _prepared_question_round_answered_result(state, work)
        if len(answers) == len(questions)
        else _prepared_question_round_operator_result(state, work)
    )


def _continue_additional_source_element_gap_admission(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    admission_error = _validate_additional_source_element_gap_admission(
        work, state, entries, purpose
    )
    if admission_error:
        return admission_error
    decision, qualification, closure, disposition, evidence_error = (
        _additional_source_element_gap_continuation_evidence(work, state, entries)
    )
    if evidence_error:
        return evidence_error
    assert decision is not None and qualification is not None
    assert closure is not None and disposition is not None
    if disposition["disposition"] == "clarification_required":
        return _resume_question_round_after_additional_source_admission(
            work, state, entries, qualification
        )
    if disposition["disposition"] == "source_conversion_required":
        return _source_conversion_required_result(
            state, work, decision, qualification, disposition, closure
        )
    parent = state.get("current_projection")
    if not isinstance(parent, dict) or not isinstance(parent.get("sha256"), str):
        return _blocked(
            "clarification continuation unavailable",
            "the admitted child projection identity is missing",
        )
    sequence = len(entries) + 1
    completed = _ledger_entry(
        sequence,
        "clarification_continuation_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "basis": "additional_source_element_gap_admission",
            "decision": decision,
            "projection_sha256": parent["sha256"],
            "projection_qualification": qualification,
            "source_projection_closure": closure,
            "terminal_disposition": disposition,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed])
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "clarification_continuation_complete",
        "waiting_for": None,
        "question": None,
        "clarification_completion": {
            "basis": "additional_source_element_gap_admission",
            "ledger_sequence": sequence,
            "decision": decision,
            "projection_sha256": parent["sha256"],
            "projection_qualification": qualification,
            "source_projection_closure": closure,
            "terminal_disposition": disposition,
        },
        "ledger_entries": sequence,
        "ledger_tail_sha256": completed["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _clarification_completion_result(state, work)


def _consume_additional_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object]:
    bundle, stage, error = _collect_additional_projection_artifacts(
        work, state, entries, purpose
    )
    if error:
        return error
    if stage:
        return _additional_projection_waiting_result(state, work, stage)
    assert bundle is not None
    pending = state["pending_additional_source"]
    active = state["active_additional_projection"]
    assert isinstance(pending, dict) and isinstance(active, dict)
    source = pending["source"]
    paths = active["paths"]
    projection = bundle["projection"]
    assert isinstance(source, dict) and isinstance(paths, dict)
    assert isinstance(projection, dict)
    projection_path = work / str(paths["projection_path"])
    if projection_path.exists():
        return _blocked(
            "unbound projection artifact",
            f"the reserved projection for {source['id']} already exists outside the ledger",
        )
    projection_bytes = (
        json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    projection_path.write_bytes(projection_bytes)
    projection_record = _additional_projection_record(
        str(source["id"]), str(paths["projection_path"]), projection_bytes, projection
    )
    completion_payload = _additional_projection_completion_payload(active, bundle)
    completed = _ledger_entry(
        len(entries) + 1,
        "model_projection_interview_completed",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            **completion_payload,
        },
        str(entries[-1]["entry_sha256"]),
    )
    created = _ledger_entry(
        len(entries) + 2,
        "projection_version_created",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "attempt": 1,
            "role": "additional_source_projection",
            "projection": projection_record,
            "reserved_projection": pending["projection"],
            "answers_question": pending["question"]["id"],
            "answers_gap": pending["question"]["answers_gap"],
            "lineage": pending["lineage"],
        },
        str(completed["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed, created])
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "additional_source_projection_recorded",
        "waiting_for": None,
        "question": None,
        "additional_source_projection": projection_record,
        "additional_projection_completion": completion_payload,
        "ledger_entries": len(entries) + 2,
        "ledger_tail_sha256": created["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _additional_projection_ready_result(state, work)


def _validate_recorded_additional_projection(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    completion = state.get("additional_projection_completion")
    if (
        isinstance(completion, dict)
        and completion.get("role") == "spreadsheet_ooxml_projection"
    ):
        return _validate_spreadsheet_projection(
            work, state, entries, additional=True, allow_later_phase=allow_later_phase
        )
    if (
        isinstance(completion, dict)
        and completion.get("role") == "verbatim_utf8_projection"
    ):
        return _validate_additional_verbatim_utf8_projection(
            work, state, entries, allow_later_phase=allow_later_phase
        )
    request_error = _validate_additional_projection_request(
        work,
        state,
        entries,
        recorded=True,
        allow_later_phase=allow_later_phase,
    )
    if request_error:
        return request_error
    pending = state["pending_additional_source"]
    active = state["active_additional_projection"]
    assert isinstance(pending, dict) and isinstance(active, dict)
    request_sequence = active["request_ledger_sequence"]
    paths = active["paths"]
    source = pending["source"]
    assert isinstance(request_sequence, int) and isinstance(paths, dict)
    assert isinstance(source, dict)
    if len(entries) < request_sequence + 2 or (
        not allow_later_phase and len(entries) != request_sequence + 2
    ):
        return _blocked(
            "invalid ledger", "the additional projection ledger length changed"
        )
    bundle, stage, error = _collect_additional_projection_artifacts(
        work, state, entries, purpose
    )
    if error:
        return error
    if stage or bundle is None:
        return _blocked(
            "invalid ledger", "the recorded additional projection lost required artifacts"
        )
    projection = bundle["projection"]
    assert isinstance(projection, dict)
    projection_path = work / str(paths["projection_path"])
    try:
        projection_bytes = projection_path.read_bytes()
    except OSError:
        return _blocked(
            "immutable projection unavailable", str(projection_path)
        )
    canonical = (
        json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    projection_record = _additional_projection_record(
        str(source["id"]), str(paths["projection_path"]), projection_bytes, projection
    )
    completion_payload = _additional_projection_completion_payload(active, bundle)
    completed = entries[request_sequence]
    created = entries[request_sequence + 1]
    if (
        projection_bytes != canonical
        or state.get("additional_source_projection") != projection_record
        or state.get("additional_projection_completion") != completion_payload
        or completed.get("event") != "model_projection_interview_completed"
        or any(
            completed.get(key) != value
            for key, value in completion_payload.items()
        )
        or created.get("event") != "projection_version_created"
        or created.get("attempt") != 1
        or created.get("role") != "additional_source_projection"
        or created.get("projection") != projection_record
        or created.get("reserved_projection") != pending["projection"]
        or created.get("answers_question") != pending["question"]["id"]
        or created.get("answers_gap") != pending["question"]["answers_gap"]
        or created.get("lineage") != pending["lineage"]
        or (
            not allow_later_phase
            and (
                state.get("ledger_entries") != len(entries)
                or state.get("ledger_tail_sha256")
                != created.get("entry_sha256")
            )
        )
    ):
        return _blocked(
            "invalid ledger", "the recorded additional projection changed"
        )
    return None


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
    allow_archived: bool = False,
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
    original_projection_id = interview.get("original_projection_id")
    original_source_id = interview.get("original_source_id")
    projection_sha256 = saved.get("projection_sha256")
    projection_path = saved.get("projection_path")
    matching_projections: dict[str, dict[str, object]] = {}

    def collect_projection(value: object) -> None:
        if isinstance(value, dict):
            if (
                value.get("id") == original_projection_id
                and value.get("source_id") == original_source_id
                and value.get("sha256") == projection_sha256
                and value.get("path") == projection_path
            ):
                identity = json.dumps(value, sort_keys=True, separators=(",", ":"))
                matching_projections[identity] = value
            for nested in value.values():
                collect_projection(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_projection(nested)

    collect_projection({
        "first_projection": state.get("first_projection"),
        "current_projection": state.get("current_projection"),
        "gap_resolution_history": state.get("gap_resolution_history"),
        "gap_resolution": state.get("gap_resolution"),
        "additional_source_element_gap_admission": state.get(
            "additional_source_element_gap_admission"
        ),
    })
    if (
        not isinstance(original_projection_id, str)
        or not isinstance(original_source_id, str)
        or not isinstance(projection_sha256, str)
        or not isinstance(projection_path, str)
        or len(matching_projections) != 1
    ):
        return _blocked(
            "invalid intake state", "the prepared-round source lineage changed"
        )
    if any(
        isinstance(item, dict)
        and item.get("answer_kind") == "additional_source_admission"
        for item in answers
    ):
        if not all(isinstance(item, dict) for item in questions + answers):
            return _blocked(
                "invalid ledger",
                "the mixed prepared question round contains a non-record item",
            )
        mixed_error = _validate_mixed_question_answer_records(
            work,
            state,
            entries,
            questions,
            answers,
            round_number=round_number,
            first_question_sequence=first_sequence,
            original_source_id=original_source_id,
            original_projection_id=original_projection_id,
            prepared_result_sha256=result_sha256,
            allow_later_phase=allow_later_phase,
        )
        return _blocked("invalid ledger", mixed_error) if mixed_error else None
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
    if allow_archived:
        if len(answers) != len(questions):
            return _blocked(
                "invalid intake state",
                "an archived prepared-round interview is incomplete",
            )
        return None
    if len(answers) < len(questions):
        active = questions[len(answers)]
        pending = state.get("pending_additional_source")
        if (
            allow_later_phase
            and state.get("phase") in {
                "additional_source_frozen",
                "interviewing_additional_source_projection",
                "additional_source_projection_recorded",
                "additional_spreadsheet_projection_failed",
                "assessing_additional_source_gap",
                "additional_source_gap_assessment_recorded",
                "additional_source_element_gap_admitted",
                "clarification_continuation_complete",
            }
            and isinstance(pending, dict)
            and pending.get("question") == active
        ):
            expected_state = (
                state.get("status"),
                state.get("phase"),
                state.get("waiting_for"),
                None,
            )
        else:
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
                (
                    "waiting_for_model",
                    "resolving_gap_answer",
                    active_paths["interview_path"],
                    None,
                ),
                (
                    "waiting_for_model",
                    "verifying_gap_resolution",
                    active_paths["verification_interview_path"],
                    None,
                ),
                (
                    "ready_for_projection_assessment",
                    "gap_resolution_applied",
                    None,
                    None,
                ),
                (
                    "ready_for_projection_assessment",
                    "operator_text_element_gap_admitted",
                    None,
                    None,
                ),
                (
                    "ready_for_projection_assessment",
                    "gap_resolution_rejected",
                    None,
                    None,
                ),
                (
                    "ready_for_projection_assessment",
                    "clarification_continuation_complete",
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
    answer: str | None,
    supplied: Path | None = None,
    supplied_url: str | None = None,
) -> dict[str, object]:
    interview_error = _validate_prepared_question_round_interview(
        work, state, entries, purpose
    )
    if interview_error:
        return interview_error
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
    question_entries = [
        entry
        for entry in entries
        if entry.get("event") == "operator_question_asked"
        and entry.get("round") == round_number
        and entry.get("question_position") == index + 1
        and entry.get("question") == question
        and entry.get("prepared_round_result_sha256") == result_sha256
    ]
    if len(question_entries) != 1 or not isinstance(
        question_entries[0].get("sequence"), int
    ):
        return _blocked(
            "invalid ledger",
            f"prepared question {index + 1} does not have one immutable ledger position",
        )
    question_ledger_sequence = question_entries[0]["sequence"]
    assert isinstance(question_ledger_sequence, int)
    answer_type = question.get("answer_type", "operator_text")
    if answer_type == "local_file":
        if answer is not None or supplied_url is not None:
            return _blocked(
                "operator input type mismatch",
                "the current question requires one local file, not text",
            )
        if supplied is None:
            return _blocked(
                "local file required",
                "supply one existing local file for the current operator question",
            )
        return _acquire_additional_local_file(
            work,
            state,
            entries,
            supplied,
            question=question,
            lineage={
                "question_ledger_sequence": question_ledger_sequence,
                "question_round": round_number,
                "question_position": index + 1,
                "original_source_id": interview["original_source_id"],
                "original_projection_id": interview["original_projection_id"],
                "prepared_round_result_sha256": result_sha256,
            },
        )
    if answer_type == "url":
        if answer is not None or supplied is not None:
            return _blocked(
                "operator input type mismatch",
                "the current question requires one public URL, not text or a local file",
            )
        if supplied_url is None or not supplied_url.strip():
            return _blocked(
                "URL required",
                "supply one public HTTP(S) URL for the current operator question",
            )
        return _acquire_additional_url(
            work,
            state,
            entries,
            supplied_url,
            question=question,
            lineage={
                "question_ledger_sequence": question_ledger_sequence,
                "question_round": round_number,
                "question_position": index + 1,
                "original_source_id": interview["original_source_id"],
                "original_projection_id": interview["original_projection_id"],
                "prepared_round_result_sha256": result_sha256,
            },
        )
    if supplied is not None or supplied_url is not None:
        return _blocked(
            "operator input type mismatch",
            "the current question requires non-empty text, not a file or URL",
        )
    if answer is None or not answer.strip():
        return _blocked(
            "gap answer required",
            "answer the current operator question with non-whitespace text",
        )
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
                "question_ledger_sequence": question_ledger_sequence,
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


def _mixed_answer_artifact_error(
    work: Path,
    answer: dict[str, object],
    question: dict[str, object],
) -> str | None:
    source = answer.get("source")
    projection = answer.get("projection")
    if not isinstance(source, dict) or not isinstance(projection, dict):
        return "the answer lost its immutable source or projection"
    source_path_value = source.get("path", source.get("stored_path"))
    projection_path_value = projection.get("path")
    if not isinstance(source_path_value, str) or not isinstance(
        projection_path_value, str
    ):
        return "the answer artifact path is missing"
    try:
        source_bytes = (work / source_path_value).read_bytes()
        projection_bytes = (work / projection_path_value).read_bytes()
    except OSError:
        return "the answer source or projection is unavailable"
    if (
        _digest_bytes(source_bytes) != source.get("sha256")
        or _digest_bytes(projection_bytes) != projection.get("sha256")
        or answer.get("question") != question
    ):
        return "the answer source, projection, or question changed"
    return None


def _additional_source_answer_event(
    work: Path,
    entries: list[dict[str, object]],
    answer: dict[str, object],
    question: dict[str, object],
    round_number: int,
    position: int,
    question_sequence: int,
) -> tuple[int | None, str | None]:
    artifact_error = _mixed_answer_artifact_error(work, answer, question)
    if artifact_error:
        return None, artifact_error
    fulfillment = answer.get("fulfillment")
    source = answer.get("source")
    projection = answer.get("projection")
    if (
        answer.get("answer_kind") != "additional_source_admission"
        or not isinstance(fulfillment, dict)
        or not isinstance(source, dict)
        or not isinstance(projection, dict)
        or fulfillment.get("round") != round_number
        or fulfillment.get("question_position") != position
    ):
        return None, "the additional-source answer identity changed"
    lineage = fulfillment.get("lineage")
    reserved_projection = fulfillment.get("reserved_projection")
    admission = fulfillment.get("admission")
    assessment = fulfillment.get("assessment")
    source_sequence = fulfillment.get("source_acquisition_ledger_sequence")
    assessment_sequence = fulfillment.get("assessment_completion_ledger_sequence")
    admission_sequence = (
        admission.get("ledger_sequence") if isinstance(admission, dict) else None
    )
    if (
        not isinstance(lineage, dict)
        or lineage.get("question_round") != round_number
        or lineage.get("question_position") != position
        or lineage.get("question_ledger_sequence") != question_sequence
        or not isinstance(reserved_projection, dict)
        or not isinstance(admission, dict)
        or not isinstance(assessment, dict)
        or not isinstance(source_sequence, int)
        or not isinstance(assessment_sequence, int)
        or not isinstance(admission_sequence, int)
        or not (
            question_sequence < source_sequence < assessment_sequence
            < admission_sequence <= len(entries)
        )
    ):
        return None, "the additional-source answer ledger lineage changed"
    source_entry = entries[source_sequence - 1]
    assessment_entry = entries[assessment_sequence - 1]
    admission_entry = entries[admission_sequence - 1]
    if (
        source_entry.get("event") != "source_acquired"
        or source_entry.get("answers_question") != question.get("id")
        or source_entry.get("answers_gap") != question.get("answers_gap")
        or source_entry.get("source") != source
        or source_entry.get("projection") != reserved_projection
        or source_entry.get("lineage") != lineage
        or assessment_entry.get("event")
        != "model_additional_source_gap_assessment_completed"
        or assessment_entry.get("result_sha256")
        != fulfillment.get("assessment_result_sha256")
        or assessment_entry.get("assessment") != assessment
        or admission_entry.get("event") != "projection_version_created"
        or admission_entry.get("role")
        != "additional_source_element_gap_admission"
        or admission_entry.get("resolved_gap") != admission.get("gap")
        or admission_entry.get("assessment_result_sha256")
        != fulfillment.get("assessment_result_sha256")
        or admission_entry.get("additional_source") != source
        or admission_entry.get("additional_projection") != projection
        or admission_entry.get("selected_evidence")
        != admission.get("selected_evidence")
        or admission_entry.get("projection") != admission.get("projection")
        or assessment.get("verdict") != "resolves_gap"
        or assessment.get("gap") != admission.get("gap")
        or assessment.get("additional_source") != source
        or assessment.get("additional_projection") != projection
        or question.get("answers_gap") != _gap_identity(admission["gap"])
    ):
        return None, "the additional-source answer evidence changed"
    child = admission.get("projection")
    if (
        not isinstance(child, dict)
        or not isinstance(child.get("path"), str)
        or not isinstance(child.get("sha256"), str)
    ):
        return None, "the admitted child projection identity is missing"
    try:
        child_bytes = (work / str(child["path"])).read_bytes()
        child_projection = json.loads(child_bytes)
        child_gaps = gap_clarification.select_gaps(
            child_projection, str(child["sha256"])
        )
    except (OSError, json.JSONDecodeError, gap_clarification.ClarificationError):
        return None, "the admitted child projection is unavailable"
    if _digest_bytes(child_bytes) != child.get("sha256"):
        return None, "the admitted child projection changed"
    matches = [
        entry
        for entry in entries
        if entry.get("event")
        == "operator_question_fulfilled_by_additional_source"
        and entry.get("round") == round_number
        and entry.get("question_position") == position
        and entry.get("answer") == answer
    ]
    if len(matches) != 1:
        return None, (
            f"question {position} has {len(matches)} additional-source fulfillment "
            "events; expected 1"
        )
    if matches[0].get("remaining_gaps") != child_gaps:
        return None, "the additional-source fulfillment's remaining gaps changed"
    sequence = matches[0].get("sequence")
    if not isinstance(sequence, int) or sequence <= admission_sequence:
        return None, "the additional-source fulfillment event is out of order"
    return sequence, None


def _text_answer_event(
    work: Path,
    entries: list[dict[str, object]],
    answer: dict[str, object],
    question: dict[str, object],
    round_number: int,
    position: int,
    question_sequence: int,
    original_source_id: str,
    original_projection_id: str,
    prepared_result_sha256: str | None,
) -> tuple[int | None, str | None]:
    artifact_error = _mixed_answer_artifact_error(work, answer, question)
    if artifact_error:
        return None, artifact_error
    source = answer.get("source")
    projection = answer.get("projection")
    assert isinstance(source, dict) and isinstance(projection, dict)
    source_id = source.get("id")
    if not isinstance(source_id, str) or not source_id.startswith("source-"):
        return None, "the operator-text answer source identity is invalid"
    try:
        number = int(source_id.removeprefix("source-"))
        source_bytes = (work / str(source["path"])).read_bytes()
    except (OSError, ValueError, KeyError):
        return None, "the operator-text answer source is unavailable"
    expected_source = _round_answer_source_record(
        number, _digest_bytes(source_bytes), question
    )
    expected_projection = _round_answer_projection_record(
        number, _digest_bytes(source_bytes)
    )
    expected_lineage = {
        "question_ledger_sequence": question_sequence,
        "question_round": round_number,
        "question_position": position,
        "original_source_id": original_source_id,
        "original_projection_id": original_projection_id,
        **(
            {"prepared_round_result_sha256": prepared_result_sha256}
            if isinstance(prepared_result_sha256, str)
            else {}
        ),
    }
    matches = [
        entry
        for entry in entries
        if entry.get("event") == "source_projected"
        and entry.get("round") == round_number
        and entry.get("question_position") == position
        and entry.get("answers_question") == question.get("id")
        and entry.get("source") == source
        and entry.get("projection") == projection
    ]
    if (
        answer != {"question": question, "source": source, "projection": projection}
        or source != expected_source
        or projection != expected_projection
        or len(matches) != 1
        or matches[0].get("lineage") != expected_lineage
    ):
        return None, f"operator-text answer {position} changed"
    sequence = matches[0].get("sequence")
    if not isinstance(sequence, int) or sequence <= question_sequence:
        return None, f"operator-text answer {position} is out of order"
    return sequence, None


def _validate_mixed_question_answer_records(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    questions: list[dict[str, object]],
    answers: list[dict[str, object]],
    *,
    round_number: int,
    first_question_sequence: int,
    original_source_id: str,
    original_projection_id: str,
    prepared_result_sha256: str | None,
    allow_later_phase: bool,
) -> str | None:
    if len(answers) > len(questions):
        return "the mixed answer sequence is longer than its prepared question round"
    expected_question_sequence = first_question_sequence
    for index, answer in enumerate(answers):
        position = index + 1
        question = questions[index]
        if expected_question_sequence < 1 or expected_question_sequence > len(entries):
            return f"question {position} has no ledger position"
        asked = entries[expected_question_sequence - 1]
        if (
            asked.get("event") != "operator_question_asked"
            or asked.get("round") != round_number
            or asked.get("question_position") != position
            or asked.get("question") != question
            or (
                isinstance(prepared_result_sha256, str)
                and asked.get("prepared_round_result_sha256")
                != prepared_result_sha256
            )
        ):
            return f"question {position} changed or was presented out of order"
        if answer.get("answer_kind") == "additional_source_admission":
            answer_sequence, answer_error = _additional_source_answer_event(
                work,
                entries,
                answer,
                question,
                round_number,
                position,
                expected_question_sequence,
            )
        else:
            answer_sequence, answer_error = _text_answer_event(
                work,
                entries,
                answer,
                question,
                round_number,
                position,
                expected_question_sequence,
                original_source_id,
                original_projection_id,
                prepared_result_sha256,
            )
        if answer_error:
            return answer_error
        assert answer_sequence is not None
        following_sequence = answer_sequence + 1
        if following_sequence > len(entries):
            return f"answer {position} has no following ledger outcome"
        following = entries[following_sequence - 1]
        if position < len(questions):
            next_question = questions[position]
            if (
                following.get("event") != "operator_question_asked"
                or following.get("round") != round_number
                or following.get("question_position") != position + 1
                or following.get("question") != next_question
                or (
                    isinstance(prepared_result_sha256, str)
                    and following.get("prepared_round_result_sha256")
                    != prepared_result_sha256
                )
            ):
                return f"question {position + 1} was not presented after answer {position}"
            expected_question_sequence = following_sequence
        elif (
            following.get("event") != "operator_question_round_answered"
            or following.get("round") != round_number
            or following.get("question_count") != len(questions)
            or following.get("answered_question_count") != len(answers)
            or following.get("answer_source_ids")
            != [item["source"]["id"] for item in answers]
            or (
                isinstance(prepared_result_sha256, str)
                and following.get("prepared_round_result_sha256")
                != prepared_result_sha256
            )
        ):
            return "the mixed question round completion changed"
    if len(answers) < len(questions):
        active = questions[len(answers)]
        pending = state.get("pending_additional_source")
        in_source_intake = (
            allow_later_phase
            and state.get("phase") in {
                "additional_source_frozen",
                "interviewing_additional_source_projection",
                "additional_source_projection_recorded",
                "additional_spreadsheet_projection_failed",
                "assessing_additional_source_gap",
                "additional_source_gap_assessment_recorded",
                "additional_source_element_gap_admitted",
            }
            and isinstance(pending, dict)
            and pending.get("question") == active
            and state.get("question") is None
        )
        expected_phase = (
            "awaiting_gap_answers"
            if round_number == 1
            else "awaiting_prepared_question_round_answers"
        )
        if not in_source_intake and (
            state.get("status") != "needs_operator"
            or state.get("phase") != expected_phase
            or state.get("waiting_for") != active.get("id")
            or state.get("question") != active
        ):
            return f"question {len(answers) + 1} is not the active operator question"
    else:
        expected_phase = (
            "gap_question_round_answered"
            if round_number == 1
            else "prepared_question_round_answered"
        )
        expected_status = "ready_for_projection_assessment"
        expected_waiting_for: object = None
        expected_states = {(expected_status, expected_phase, expected_waiting_for)}
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
            active_prepared = state.get("follow_up_gap_question_round")
            active_prepared_round = (
                active_prepared.get("round")
                if isinstance(active_prepared, dict)
                else 2
            )
            active_prepared_path = (
                f"gap-question-rounds/round-{active_prepared_round:06d}/interview.jsonl"
                if isinstance(active_prepared_round, int)
                else state.get("waiting_for")
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
                ("ready_for_projection_assessment", "gap_resolution_applied", None),
                (
                    "ready_for_projection_assessment",
                    "operator_text_element_gap_admitted",
                    None,
                ),
                ("ready_for_projection_assessment", "gap_resolution_rejected", None),
                (
                    "waiting_for_model",
                    "formulating_follow_up_gap_question_round",
                    active_prepared_path,
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
                (
                    "ready_for_projection_assessment",
                    "clarification_continuation_complete",
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
            return "the mixed question round has an invalid completed state"
    if (
        state.get("ledger_entries") != len(entries)
        or state.get("ledger_tail_sha256") != entries[-1].get("entry_sha256")
    ):
        return "the mixed question round ledger tail changed"
    return None


def _validate_gap_question_answer_records(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    questions: list[dict[str, object]],
    *,
    allow_later_phase: bool = False,
) -> str | None:
    answers = state.get("gap_question_answers")
    saved_round = state.get("gap_question_round")
    request_sequence = (
        saved_round.get("request_ledger_sequence")
        if isinstance(saved_round, dict)
        else None
    )
    if not isinstance(request_sequence, int):
        return "the question-round request identity is missing"
    if not isinstance(answers, list) or len(answers) > len(questions):
        return "the preserved answer sequence is invalid"
    first_question_sequence = request_sequence + 3
    if any(
        isinstance(item, dict)
        and item.get("answer_kind") == "additional_source_admission"
        for item in answers
    ):
        if not all(isinstance(item, dict) for item in questions + answers):
            return "the mixed question round contains a non-record item"
        first_projection = state.get("first_projection")
        if not isinstance(first_projection, dict):
            return "the mixed question round lost its original projection"
        return _validate_mixed_question_answer_records(
            work,
            state,
            entries,
            questions,
            answers,
            round_number=1,
            first_question_sequence=first_question_sequence,
            original_source_id="source-000003",
            original_projection_id=str(first_projection.get("id")),
            prepared_result_sha256=None,
            allow_later_phase=allow_later_phase,
        )
    answer_ledger_length = first_question_sequence + (2 * len(answers))
    if (
        len(entries) < answer_ledger_length
        or (not allow_later_phase and len(entries) != answer_ledger_length)
    ):
        return "the answer ledger length does not match the preserved answers"
    if (
        entries[first_question_sequence - 1].get("event") != "operator_question_asked"
        or entries[first_question_sequence - 1].get("round") != 1
        or entries[first_question_sequence - 1].get("question_position") != 1
        or entries[first_question_sequence - 1].get("question") != questions[0]
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
        question_sequence = first_question_sequence + (2 * index)
        lineage = {
            "question_ledger_sequence": question_sequence,
            "question_round": 1,
            "question_position": index + 1,
            "original_source_id": "source-000003",
            "original_projection_id": state["first_projection"]["id"],
        }
        answer_entry = entries[question_sequence]
        following_entry = entries[question_sequence + 1]
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
        pending = state.get("pending_additional_source")
        pending_file_state = (
            allow_later_phase
            and state.get("phase") in {
                "additional_source_frozen",
                "interviewing_additional_source_projection",
                "additional_source_projection_recorded",
                "additional_spreadsheet_projection_failed",
                "assessing_additional_source_gap",
                "additional_source_gap_assessment_recorded",
                "additional_source_element_gap_admitted",
                "clarification_continuation_complete",
            }
            and state.get("question") is None
            and isinstance(pending, dict)
            and pending.get("question") == active
        )
        if not pending_file_state and (
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
            active_prepared = state.get("follow_up_gap_question_round")
            active_prepared_round = (
                active_prepared.get("round")
                if isinstance(active_prepared, dict)
                else 2
            )
            active_prepared_path = (
                f"gap-question-rounds/round-{active_prepared_round:06d}/interview.jsonl"
                if isinstance(active_prepared_round, int)
                else state.get("waiting_for")
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
                    "operator_text_element_gap_admitted",
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
                    active_prepared_path,
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
                (
                    "ready_for_projection_assessment",
                    "clarification_continuation_complete",
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
    saved = state.get("gap_question_round")
    if not isinstance(saved, dict) or not isinstance(saved.get("gaps"), list):
        return _blocked("invalid intake state", "the gap question round is missing")
    contract = saved.get("contract", 1)
    request_sequence = saved.get("request_ledger_sequence")
    if not isinstance(contract, int):
        return _blocked(
            "invalid gap question round", "the question-round contract is invalid"
        )
    round_dir = work / "gap-question-rounds" / "round-000001"
    try:
        result, journal_sha256, result_sha256 = gap_clarification.validate_round(
            round_dir,
            projection_path=projection_path,
            projection_sha256=projection_sha256,
            purpose=purpose,
            contract=contract,
        )
        journal_entries = gap_clarification._read_journal(
            round_dir / "interview.jsonl"
        )
    except gap_clarification.ClarificationError as error:
        return _blocked("invalid gap question round", str(error))
    shape_error = _validate_question_round_shape(
        result, saved["gaps"], contract=contract
    )
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
        or not isinstance(request_sequence, int)
        or len(entries) < request_sequence + 3
        or entries[request_sequence].get("event") != "model_gap_question_round_completed"
        or any(entries[request_sequence].get(key) != value for key, value in expected_completed.items())
        or entries[request_sequence + 1].get("event") != "operator_question_round_prepared"
        or entries[request_sequence + 1].get("questions") != result["questions"]
        or entries[request_sequence + 1].get("question_count") != len(result["questions"])
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
    answer: str | None,
    supplied: Path | None = None,
    supplied_url: str | None = None,
) -> dict[str, object]:
    questions = state["questions"]
    answers = state["gap_question_answers"]
    assert isinstance(questions, list) and isinstance(answers, list)
    index = len(answers)
    if index >= len(questions):
        return _blocked("gap answer not requested", "the question round is already answered")
    question = questions[index]
    assert isinstance(question, dict)
    saved_round = state.get("gap_question_round")
    request_sequence = (
        saved_round.get("request_ledger_sequence")
        if isinstance(saved_round, dict)
        else None
    )
    if not isinstance(request_sequence, int):
        return _blocked(
            "invalid gap question round",
            "the question-round request identity is missing",
        )
    question_entries = [
        entry
        for entry in entries
        if entry.get("event") == "operator_question_asked"
        and entry.get("round") == 1
        and entry.get("question_position") == index + 1
        and entry.get("question") == question
    ]
    if len(question_entries) != 1 or not isinstance(
        question_entries[0].get("sequence"), int
    ):
        return _blocked(
            "invalid ledger",
            f"question {index + 1} does not have one immutable ledger position",
        )
    question_ledger_sequence = question_entries[0]["sequence"]
    assert isinstance(question_ledger_sequence, int)
    answer_type = question.get("answer_type", "operator_text")
    if answer_type == "local_file":
        if answer is not None or supplied_url is not None:
            return _blocked(
                "operator input type mismatch",
                "the current question requires one local file, not text",
            )
        if supplied is None:
            return _blocked(
                "local file required",
                "supply one existing local file for the current operator question",
            )
        return _acquire_additional_local_file(
            work,
            state,
            entries,
            supplied,
            question=question,
            lineage={
                "question_ledger_sequence": question_ledger_sequence,
                "question_round": 1,
                "question_position": index + 1,
                "original_source_id": "source-000003",
                "original_projection_id": state["first_projection"]["id"],
            },
        )
    if answer_type == "url":
        if answer is not None or supplied is not None:
            return _blocked(
                "operator input type mismatch",
                "the current question requires one public URL, not text or a local file",
            )
        if supplied_url is None or not supplied_url.strip():
            return _blocked(
                "URL required",
                "supply one public HTTP(S) URL for the current operator question",
            )
        return _acquire_additional_url(
            work,
            state,
            entries,
            supplied_url,
            question=question,
            lineage={
                "question_ledger_sequence": question_ledger_sequence,
                "question_round": 1,
                "question_position": index + 1,
                "original_source_id": "source-000003",
                "original_projection_id": state["first_projection"]["id"],
            },
        )
    if supplied is not None or supplied_url is not None:
        return _blocked(
            "operator input type mismatch",
            "the current question requires non-empty text, not a file or URL",
        )
    if answer is None or not answer.strip():
        return _blocked(
            "gap answer required",
            "answer the current operator question with non-whitespace text",
        )
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
                "question_ledger_sequence": question_ledger_sequence,
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
        if answer_record.get("answer_kind") == "additional_source_admission":
            fulfillment = answer_record.get("fulfillment")
            assessment = (
                fulfillment.get("assessment")
                if isinstance(fulfillment, dict)
                else None
            )
            admission = (
                fulfillment.get("admission")
                if isinstance(fulfillment, dict)
                else None
            )
            assessment_result_sha256 = (
                fulfillment.get("assessment_result_sha256")
                if isinstance(fulfillment, dict)
                else None
            )
            selected = (
                admission.get("selected_evidence")
                if isinstance(admission, dict)
                else None
            )
            item = selected.get("item") if isinstance(selected, dict) else None
            artifact_error = _mixed_answer_artifact_error(
                work, answer_record, question
            )
            if (
                artifact_error
                or not isinstance(assessment, dict)
                or assessment.get("verdict") != "resolves_gap"
                or assessment.get("gap") != gap
                or assessment.get("additional_source") != source
                or assessment.get("additional_projection") != projection
                or not isinstance(assessment.get("reason"), str)
                or not assessment["reason"].strip()
                or not isinstance(admission, dict)
                or admission.get("gap") != gap
                or not isinstance(assessment_result_sha256, str)
                or len(assessment_result_sha256) != 64
                or not isinstance(admission.get("input_sha256"), str)
                or len(str(admission["input_sha256"])) != 64
                or not isinstance(admission.get("projection"), dict)
                or not isinstance(admission["projection"].get("id"), str)
                or not isinstance(admission["projection"].get("sha256"), str)
                or len(str(admission["projection"]["sha256"])) != 64
                or not isinstance(item, dict)
                or not isinstance(item.get("content"), str)
                or not item["content"].strip()
            ):
                return None, _blocked(
                    "gap answer assessment unavailable",
                    artifact_error
                    or f"answer {index} lost its admitted-source proof",
                )
            bindings.append({
                "position": index,
                "question": question,
                "gap": gap,
                "answer_source": source,
                "answer_projection": projection,
                "answer": item["content"],
                "assessment_mode": "admitted_source",
                "accepted_assessment": assessment,
                "accepted_assessment_result_sha256": assessment_result_sha256,
                "admission_input_sha256": admission.get("input_sha256"),
                "child_projection": admission.get("projection"),
            })
            continue
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
            "assessment_mode": "model",
        })
    model_bindings = [
        binding
        for binding in bindings
        if binding.get("assessment_mode") == "model"
    ]
    if len(model_bindings) == len(bindings):
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


def _answer_assessment_contract(
    bindings: list[dict[str, object]],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]] | None,
    dict[str, object] | None,
]:
    if not any(
        binding.get("assessment_mode") == "admitted_source"
        for binding in bindings
    ):
        return bindings, None, None
    model_bindings: list[dict[str, object]] = []
    plan: list[dict[str, object]] = []
    for binding in bindings:
        round_position = binding.get("position")
        if not isinstance(round_position, int):
            return [], None, _blocked(
                "gap answer assessment unavailable",
                "a mixed answer lost its round position",
            )
        if binding.get("assessment_mode") == "admitted_source":
            accepted = binding.get("accepted_assessment")
            child = binding.get("child_projection")
            if not isinstance(accepted, dict) or not isinstance(child, dict):
                return [], None, _blocked(
                    "gap answer assessment unavailable",
                    f"admitted-source answer {round_position} lost its accepted proof",
                )
            fixed = {
                **gap_answer_assessment._assessment_identity(binding),
                "verdict": "resolves_gap",
                "reason": accepted["reason"],
                "basis": {
                    "kind": "admitted_source",
                    "accepted_assessment_result_sha256": binding.get(
                        "accepted_assessment_result_sha256"
                    ),
                    "admission_input_sha256": binding.get(
                        "admission_input_sha256"
                    ),
                    "child_projection": {
                        "id": child.get("id"),
                        "sha256": child.get("sha256"),
                    },
                },
            }
            plan.append({
                "round_position": round_position,
                "mode": "admitted_source",
                "assessment": fixed,
            })
            continue
        model_binding = {
            key: value
            for key, value in binding.items()
            if key != "assessment_mode"
        }
        model_binding["position"] = len(model_bindings) + 1
        model_bindings.append(model_binding)
        plan.append({
            "round_position": round_position,
            "mode": "model",
            "model_position": len(model_bindings),
        })
    if not model_bindings:
        return [], None, _blocked(
            "gap answer assessment unavailable",
            "the mixed round has no human-text answer requiring model assessment",
        )
    return model_bindings, plan, None


def _merge_mixed_answer_assessments(
    model_result: dict[str, object],
    full_bindings: list[dict[str, object]],
    model_bindings: list[dict[str, object]],
    plan: list[dict[str, object]] | None,
) -> tuple[dict[str, object] | None, str | None]:
    if plan is None:
        shape_error = _validate_gap_answer_assessment_shape(
            model_result, full_bindings
        )
        return model_result, shape_error
    model_shape_error = _validate_gap_answer_assessment_shape(
        model_result, model_bindings
    )
    if model_shape_error:
        return None, model_shape_error
    model_assessments = model_result.get("assessments")
    assert isinstance(model_assessments, list)
    merged: list[dict[str, object]] = []
    for item in plan:
        round_position = item["round_position"]
        assert isinstance(round_position, int)
        if item.get("mode") == "admitted_source":
            fixed = item.get("assessment")
            if not isinstance(fixed, dict):
                return None, (
                    f"mixed assessment position {round_position} lost its fixed outcome"
                )
            merged.append(fixed)
            continue
        model_position = item.get("model_position")
        if (
            not isinstance(model_position, int)
            or not 1 <= model_position <= len(model_assessments)
            or not isinstance(model_assessments[model_position - 1], dict)
        ):
            return None, (
                f"mixed assessment position {round_position} lost its model outcome"
            )
        merged.append({
            **model_assessments[model_position - 1],
            "position": round_position,
        })
    merged_result = {
        "schema_version": model_result.get("schema_version"),
        "assessor": model_result.get("assessor"),
        "assessment_count": len(merged),
        "model_assessment_count": len(model_assessments),
        "assessments": merged,
    }
    shape_error = _validate_gap_answer_assessment_shape(
        merged_result, full_bindings
    )
    return (None, shape_error) if shape_error else (merged_result, None)


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
    model_bindings, assessment_plan, contract_error = (
        _answer_assessment_contract(bindings)
    )
    if contract_error:
        return contract_error
    assessment_dir = work / "gap-answer-assessments" / "round-000001"
    if assessment_dir.exists():
        return _blocked(
            "unbound gap answer assessment",
            "assessment artifacts already exist outside the ledger",
        )
    identities = gap_answer_assessment.identities(model_bindings)
    mixed_fields = (
        {
            "model_assessment_count": len(model_bindings),
            "assessment_plan": assessment_plan,
        }
        if assessment_plan is not None
        else {}
    )
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
            **mixed_fields,
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
            **mixed_fields,
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
    model_bindings, assessment_plan, contract_error = (
        _answer_assessment_contract(bindings)
    )
    if contract_error:
        return None, contract_error
    identities = gap_answer_assessment.identities(model_bindings)
    mixed_fields = (
        {
            "model_assessment_count": len(model_bindings),
            "assessment_plan": assessment_plan,
        }
        if assessment_plan is not None
        else {}
    )
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
        **mixed_fields,
        "interview_path": "gap-answer-assessments/round-000001/interview.jsonl",
        "result_path": "gap-answer-assessments/round-000001/assessment.json",
    }
    expected_saved = {
        "round": 1,
        "contract": gap_answer_assessment.CONTRACT,
        "request_ledger_sequence": request_sequence,
        "assessment_count": len(bindings),
        "bindings": identities,
        **mixed_fields,
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
    model_bindings, assessment_plan, contract_error = (
        _answer_assessment_contract(bindings)
    )
    if contract_error:
        return contract_error
    assessment_dir = work / "gap-answer-assessments" / "round-000001"
    try:
        result, journal_sha256, result_sha256 = gap_answer_assessment.validate(
            assessment_dir, bindings=model_bindings, purpose=purpose
        )
        journal_entries = gap_answer_assessment._read_journal(
            assessment_dir / "interview.jsonl"
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("invalid gap answer assessment", str(error))
    merged_result, shape_error = _merge_mixed_answer_assessments(
        result, bindings, model_bindings, assessment_plan
    )
    if shape_error:
        return _blocked("invalid gap answer assessment", shape_error)
    assert merged_result is not None
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
            "assessment_count": len(merged_result["assessments"]),
            **(
                {"model_assessment_count": len(result["assessments"])}
                if assessment_plan is not None
                else {}
            ),
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
            "assessments": merged_result["assessments"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed])
    state["gap_answer_assessment"].update({
        "interview_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "assessor": result["assessor"],
        "assessments": merged_result["assessments"],
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
    model_bindings, assessment_plan, contract_error = (
        _answer_assessment_contract(bindings)
    )
    if contract_error:
        return contract_error
    assessment_dir = work / "gap-answer-assessments" / "round-000001"
    try:
        result, journal_sha256, result_sha256 = gap_answer_assessment.validate(
            assessment_dir, bindings=model_bindings, purpose=purpose
        )
        journal_entries = gap_answer_assessment._read_journal(
            assessment_dir / "interview.jsonl"
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("invalid gap answer assessment", str(error))
    merged_result, shape_error = _merge_mixed_answer_assessments(
        result, bindings, model_bindings, assessment_plan
    )
    if merged_result is None:
        return _blocked(
            "invalid gap answer assessment",
            shape_error or "the mixed assessment could not be assembled",
        )
    expected = {
        "round": 1,
        "interview_path": "gap-answer-assessments/round-000001/interview.jsonl",
        "interview_sha256": journal_sha256,
        "result_path": "gap-answer-assessments/round-000001/assessment.json",
        "result_sha256": result_sha256,
        "assessment_count": len(merged_result["assessments"]),
        **(
            {"model_assessment_count": len(result["assessments"])}
            if assessment_plan is not None
            else {}
        ),
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
        "assessments": merged_result["assessments"],
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
        active_prepared = state.get("follow_up_gap_question_round")
        active_prepared_round = (
            active_prepared.get("round")
            if isinstance(active_prepared, dict)
            else 2
        )
        active_prepared_path = (
            f"gap-question-rounds/round-{active_prepared_round:06d}/interview.jsonl"
            if isinstance(active_prepared_round, int)
            else state.get("waiting_for")
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
            (
                "ready_for_projection_assessment",
                "operator_text_element_gap_admitted",
                None,
            ),
            ("ready_for_projection_assessment", "gap_resolution_rejected", None),
            (
                "ready_for_projection_assessment",
                "clarification_continuation_complete",
                None,
            ),
            (
                "waiting_for_model",
                "formulating_follow_up_gap_question_round",
                active_prepared_path,
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
        or saved.get("assessments") != merged_result["assessments"]
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
    result = {
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
    return _with_clarification_continuation(work, state, result)


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
    model_bindings, assessment_plan, contract_error = (
        _answer_assessment_contract(bindings)
    )
    if contract_error:
        return contract_error
    paths = _answer_assessment_paths(round_number)
    assessment_dir = work / paths["directory"]
    if assessment_dir.exists():
        return _blocked(
            "unbound prepared answer assessment",
            f"round {round_number} assessment artifacts already exist outside the ledger",
        )
    identities = gap_answer_assessment.identities(model_bindings)
    mixed_fields = (
        {
            "model_assessment_count": len(model_bindings),
            "assessment_plan": assessment_plan,
        }
        if assessment_plan is not None
        else {}
    )
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
            **mixed_fields,
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
        **mixed_fields,
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
    model_bindings, assessment_plan, contract_error = (
        _answer_assessment_contract(bindings)
    )
    if contract_error:
        return None, None, contract_error
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
    identities = gap_answer_assessment.identities(model_bindings)
    mixed_fields = (
        {
            "model_assessment_count": len(model_bindings),
            "assessment_plan": assessment_plan,
        }
        if assessment_plan is not None
        else {}
    )
    prepared = state.get("follow_up_gap_question_round")
    assert isinstance(prepared, dict)
    expected = {
        "round": round_number,
        "contract": gap_answer_assessment.CONTRACT,
        "assessment_count": len(bindings),
        "bindings": identities,
        **mixed_fields,
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
    model_bindings, assessment_plan, contract_error = (
        _answer_assessment_contract(bindings)
    )
    if contract_error:
        return contract_error
    round_number = saved["round"]
    assert isinstance(round_number, int)
    paths = _answer_assessment_paths(round_number)
    assessment_dir = work / paths["directory"]
    try:
        result, journal_sha256, result_sha256 = gap_answer_assessment.validate(
            assessment_dir, bindings=model_bindings, purpose=purpose
        )
        journal_entries = gap_answer_assessment._read_journal(
            assessment_dir / "interview.jsonl"
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("invalid prepared answer assessment", str(error))
    merged_result, shape_error = _merge_mixed_answer_assessments(
        result, bindings, model_bindings, assessment_plan
    )
    if shape_error:
        return _blocked("invalid prepared answer assessment", shape_error)
    assert merged_result is not None
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
            "assessment_count": len(merged_result["assessments"]),
            **(
                {"model_assessment_count": len(result["assessments"])}
                if assessment_plan is not None
                else {}
            ),
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
            "assessments": merged_result["assessments"],
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [completed])
    saved.update({
        "interview_sha256": journal_sha256,
        "result_sha256": result_sha256,
        "assessor": result["assessor"],
        "assessments": merged_result["assessments"],
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
    *,
    allow_later_phase: bool = False,
    allow_archived: bool = False,
) -> dict[str, object] | None:
    bindings, saved, request_error = (
        _validate_prepared_question_round_assessment_request(work, state, entries)
    )
    if request_error:
        return request_error
    assert bindings is not None and saved is not None
    model_bindings, assessment_plan, contract_error = (
        _answer_assessment_contract(bindings)
    )
    if contract_error:
        return contract_error
    round_number = saved["round"]
    request_sequence = saved["request_ledger_sequence"]
    assert isinstance(round_number, int) and isinstance(request_sequence, int)
    paths = _answer_assessment_paths(round_number)
    assessment_dir = work / paths["directory"]
    try:
        result, journal_sha256, result_sha256 = gap_answer_assessment.validate(
            assessment_dir, bindings=model_bindings, purpose=purpose
        )
        journal_entries = gap_answer_assessment._read_journal(
            assessment_dir / "interview.jsonl"
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("invalid prepared answer assessment", str(error))
    merged_result, shape_error = _merge_mixed_answer_assessments(
        result, bindings, model_bindings, assessment_plan
    )
    if merged_result is None:
        return _blocked(
            "invalid prepared answer assessment",
            shape_error or "the mixed assessment could not be assembled",
        )
    expected = {
        "round": round_number,
        "interview_path": paths["interview_path"],
        "interview_sha256": journal_sha256,
        "result_path": paths["result_path"],
        "result_sha256": result_sha256,
        "assessment_count": len(merged_result["assessments"]),
        **(
            {"model_assessment_count": len(result["assessments"])}
            if assessment_plan is not None
            else {}
        ),
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
        "assessments": merged_result["assessments"],
    }
    completed_index = request_sequence
    active_resolution = state.get("gap_resolution")
    active_attempt = (
        active_resolution.get("attempt")
        if isinstance(active_resolution, dict)
        else 1
    )
    active_paths = _resolution_paths(
        active_attempt if isinstance(active_attempt, int) else 1
    )
    expected_states = {
        (
            "ready_for_projection_assessment",
            "prepared_question_round_assessment_recorded",
            None,
        )
    }
    if allow_later_phase:
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
            (
                "ready_for_projection_assessment",
                "operator_text_element_gap_admitted",
                None,
            ),
            ("ready_for_projection_assessment", "gap_resolution_rejected", None),
            (
                "ready_for_projection_assessment",
                "clarification_continuation_complete",
                None,
            ),
        })
    if (
        shape_error
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
                "assessments": merged_result["assessments"],
            }.items()
        )
        or (
            not allow_archived
            and (
            state.get("status"), state.get("phase"), state.get("waiting_for")
            ) not in expected_states
        )
        or (not allow_archived and state.get("question") is not None)
        or (
            not allow_archived
            and
            not allow_later_phase
            and (
                len(entries) != request_sequence + 1
                or state.get("ledger_entries") != len(entries)
                or state.get("ledger_tail_sha256")
                != entries[-1].get("entry_sha256")
            )
        )
    ):
        return _blocked(
            "invalid ledger",
            shape_error or "the preserved prepared-round assessment changed",
        )
    return None


def _validate_prepared_question_round_history(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object] | None:
    history = state.get("prepared_question_round_history", [])
    if not isinstance(history, list) or not all(
        isinstance(item, dict) for item in history
    ):
        return _blocked(
            "invalid intake state",
            "the prepared question round history must remain an ordered list",
        )
    for item in history:
        round_number = item.get("round")
        if not isinstance(round_number, int):
            return _blocked(
                "invalid intake state", "an archived prepared round lost its identity"
            )
        prepared, interview, snapshot_error = _prepared_round_snapshot(
            state, round_number
        )
        if snapshot_error:
            return snapshot_error
        assert prepared is not None and interview is not None
        shadow = dict(state)
        shadow["follow_up_gap_question_round"] = prepared
        shadow["prepared_question_round_interview"] = interview
        round_error = _validate_follow_up_gap_question_round(
            work, shadow, entries, purpose, allow_interview=True
        )
        if round_error:
            return round_error
        interview_error = _validate_prepared_question_round_interview(
            work,
            shadow,
            entries,
            purpose,
            allow_later_phase=True,
            allow_archived=True,
        )
        if interview_error:
            return interview_error
        assessment_error = _validate_prepared_question_round_assessment(
            work,
            shadow,
            entries,
            purpose,
            allow_later_phase=True,
            allow_archived=True,
        )
        if assessment_error:
            return assessment_error
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


def _assessment_round_data(
    work: Path,
    state: dict[str, object],
    round_number: int,
) -> tuple[
    list[dict[str, object]] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    if round_number == 1:
        bindings, binding_error = _gap_answer_assessment_bindings(work, state)
        saved = state.get("gap_answer_assessment")
        if binding_error:
            return None, None, binding_error
        if not isinstance(saved, dict):
            return None, None, _blocked(
                "gap resolution unavailable",
                "round 1 assessed answer outcomes are missing",
            )
        return bindings, saved, None
    records = state.get("prepared_question_round_assessments", [])
    if not isinstance(records, list) or not all(
        isinstance(item, dict) for item in records
    ):
        return None, None, _blocked(
            "gap resolution unavailable",
            "later-round assessment history must be an ordered list",
        )
    matching = [item for item in records if item.get("round") == round_number]
    if len(matching) != 1:
        return None, None, _blocked(
            "gap resolution unavailable",
            f"round {round_number} must have exactly one preserved assessment",
        )
    bindings, binding_error = (
        _prepared_question_round_assessment_bindings_for_round(
            work, state, round_number
        )
    )
    if binding_error:
        return None, None, binding_error
    return bindings, matching[0], None


def _resolving_assessed_answer_at_position(
    work: Path,
    state: dict[str, object],
    round_number: int,
    position: int,
    parent: dict[str, object],
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    bindings, saved, binding_error = _assessment_round_data(
        work, state, round_number
    )
    if binding_error:
        return None, None, binding_error
    assert bindings is not None and saved is not None
    assessments = saved.get("assessments")
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
            f"round {round_number} assessment position {position} is outside 1..{len(bindings)}",
        )
    assessment = assessments[position - 1]
    binding = bindings[position - 1]
    assert isinstance(assessment, dict) and isinstance(binding, dict)
    gap = binding.get("gap")
    original_record = gap.get("record") if isinstance(gap, dict) else None
    collection = gap.get("collection") if isinstance(gap, dict) else None
    if (
        assessment.get("verdict") != "resolves_gap"
        or not isinstance(gap, dict)
        or collection not in {"elements", "relationships"}
    ):
        return None, None, _blocked(
            "gap resolution unavailable",
            f"round {round_number} assessment position {position} is not a resolving element or relationship gap",
        )
    projection_path, projection_sha256, projection_error = (
        _validated_projection_record(work, parent)
    )
    if projection_error:
        return None, None, projection_error
    assert projection_path is not None and projection_sha256 is not None
    try:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        records = projection[collection]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None, None, _blocked(
            "gap resolution unavailable",
            f"parent projection {collection} are invalid",
        )
    matches = [
        item
        for item in records
        if isinstance(item, dict) and item.get("id") == gap.get("id")
    ]
    if len(matches) != 1:
        return None, None, _blocked(
            "gap resolution unavailable",
            f"gap {gap.get('id')} appears {len(matches)} times in the parent projection; expected 1",
        )
    received_record_sha256 = _digest_bytes(_canonical(matches[0]))
    if received_record_sha256 != gap.get("record_sha256") or matches[0] != original_record:
        return None, None, _blocked(
            "gap resolution unavailable",
            f"gap {gap.get('id')} changed in parent projection {parent.get('id')}; expected unchanged record {gap.get('record_sha256')}, received {received_record_sha256}",
        )
    active_binding = json.loads(json.dumps(binding))
    active_binding["gap"]["projection_sha256"] = projection_sha256
    active_binding["question"]["answers_gap"]["projection_sha256"] = (
        projection_sha256
    )
    return active_binding, assessment, None


def _assessed_binding_at_position(
    work: Path,
    state: dict[str, object],
    round_number: int,
    position: int,
    parent: dict[str, object],
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    binding, assessment, selection_error = (
        _resolving_assessed_answer_at_position(
            work, state, round_number, position, parent
        )
    )
    if selection_error:
        return None, None, selection_error
    assert binding is not None and assessment is not None
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
        not isinstance(gap, dict)
        or gap.get("collection") != "relationships"
        or (
            not isinstance(binding_issue, dict)
            and missing_endpoint_count != 1
        )
    ):
        return None, None, _blocked(
            "gap resolution unavailable",
            f"round {round_number} assessment position {position} is not a resolving relationship gap with either an identity ambiguity or exactly one missing endpoint",
        )
    projection_path, _, projection_error = _validated_projection_record(
        work, parent
    )
    if projection_error:
        return None, None, projection_error
    assert projection_path is not None
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
    try:
        gap_resolution._participant_contract(projection, matches[0])
    except gap_resolution.ResolutionError as contract_error:
        return None, None, _blocked(
            "gap resolution unavailable",
            f"gap {gap.get('id')} participant contract is invalid: {contract_error}",
        )
    return binding, assessment, None


def _next_resolving_assessed_binding(
    work: Path, state: dict[str, object], parent: dict[str, object]
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    int | None,
    dict[str, object] | None,
]:
    used: set[tuple[int, int]] = set()
    history = state.get("gap_resolution_history", [])
    if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
        return None, None, None, _blocked(
            "gap resolution unavailable", "gap resolution history must be a list of records"
        )
    candidates = list(history)
    current = state.get("gap_resolution")
    if isinstance(current, dict) and current.get("result_sha256"):
        candidates.append(current)
    for item in candidates:
        position = item.get("selected_assessment_position")
        if isinstance(position, int):
            selected_round = item.get("selected_assessment_round", 1)
            if isinstance(selected_round, int):
                used.add((selected_round, position))
    admissions = state.get("operator_text_element_gap_admissions", [])
    if not isinstance(admissions, list) or not all(
        isinstance(item, dict) for item in admissions
    ):
        return None, None, None, _blocked(
            "gap resolution unavailable",
            "operator-text element admission history must be a list of records",
        )
    for admission in admissions:
        selected_round = admission.get("assessment_round")
        position = admission.get("assessment_position")
        if not isinstance(selected_round, int) or not isinstance(position, int):
            return None, None, None, _blocked(
                "gap resolution unavailable",
                "an operator-text element admission lost its assessment identity",
            )
        used.add((selected_round, position))
    round_numbers: list[int] = []
    saved = state.get("gap_answer_assessment")
    if isinstance(saved, dict) and isinstance(saved.get("assessments"), list):
        round_numbers.append(1)
    records = state.get("prepared_question_round_assessments", [])
    if isinstance(records, list):
        round_numbers.extend(
            item["round"]
            for item in records
            if isinstance(item, dict)
            and isinstance(item.get("round"), int)
            and item["round"] >= 2
        )
    for round_number in sorted(set(round_numbers)):
        _, round_record, round_error = _assessment_round_data(
            work, state, round_number
        )
        if round_error:
            return None, None, None, round_error
        assert round_record is not None
        assessments = round_record.get("assessments")
        if not isinstance(assessments, list):
            return None, None, None, _blocked(
                "gap resolution unavailable",
                f"round {round_number} assessed answer outcomes are missing",
            )
        for assessment in assessments:
            if (
                not isinstance(assessment, dict)
                or assessment.get("verdict") != "resolves_gap"
            ):
                continue
            position = assessment.get("position")
            if isinstance(position, int) and (round_number, position) not in used:
                binding, selected, selection_error = _assessed_binding_at_position(
                    work, state, round_number, position, parent
                )
                return binding, selected, round_number, selection_error
    return None, None, None, _blocked(
        "gap resolution unavailable", "no unused assessed answer resolves an exact remaining gap"
    )


def _operator_text_element_gap_admission_input(
    work: Path,
    state: dict[str, object],
    round_number: int,
    position: int,
    *,
    parent_projection: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    parent = parent_projection or state.get(
        "current_projection", state.get("first_projection")
    )
    if not isinstance(parent, dict):
        return None, _blocked(
            "operator-text element admission unavailable",
            "the current parent projection is missing",
        )
    binding, assessment, selection_error = (
        _resolving_assessed_answer_at_position(
            work, state, round_number, position, parent
        )
    )
    if selection_error:
        return None, selection_error
    assert binding is not None and assessment is not None
    gap = binding.get("gap")
    if not isinstance(gap, dict) or gap.get("collection") != "elements":
        return None, None
    if binding.get("assessment_mode") != "model":
        return None, _blocked(
            "operator-text element admission unavailable",
            "only a preserved operator-text answer can use deterministic element admission",
        )
    answer = binding.get("answer")
    source = binding.get("answer_source")
    projection = binding.get("answer_projection")
    question = binding.get("question")
    if (
        not isinstance(answer, str)
        or not answer.strip()
        or not isinstance(source, dict)
        or not isinstance(projection, dict)
        or not isinstance(question, dict)
    ):
        return None, _blocked(
            "operator-text element admission unavailable",
            "the resolving answer lost its immutable text, source, projection, or question",
        )
    answer_sha256 = _digest_bytes(answer.encode("utf-8"))
    if (
        source.get("sha256") != answer_sha256
        or projection.get("sha256") != answer_sha256
    ):
        return None, _blocked(
            "operator-text element admission unavailable",
            "the resolving text no longer matches its immutable source and projection",
        )
    _, assessment_record, round_error = _assessment_round_data(
        work, state, round_number
    )
    if round_error:
        return None, round_error
    assert assessment_record is not None
    result_sha256 = assessment_record.get("result_sha256")
    if not isinstance(result_sha256, str) or len(result_sha256) != 64:
        return None, _blocked(
            "operator-text element admission unavailable",
            "the accepted assessment lost its immutable result identity",
        )
    admission = {
        "contract": 1,
        "assessment_round": round_number,
        "assessment_position": position,
        "parent_projection": parent,
        "gap": gap,
        "question": question,
        "accepted_assessment": assessment,
        "accepted_assessment_sha256": _digest_bytes(_canonical(assessment)),
        "assessment_result_sha256": result_sha256,
        "answer_source": source,
        "answer_projection": projection,
        "answer_text": answer,
        "answer_text_sha256": answer_sha256,
    }
    admission["input_sha256"] = _digest_bytes(_canonical(admission))
    return admission, None


def _build_operator_text_element_gap_projection(
    work: Path,
    admission: dict[str, object],
) -> tuple[bytes, dict[str, object]]:
    parent = admission["parent_projection"]
    gap = admission["gap"]
    assert isinstance(parent, dict) and isinstance(gap, dict)
    parent_path, _, parent_error = _validated_projection_record(work, parent)
    if parent_error or parent_path is None:
        raise ValueError(
            parent_error.get("why", "parent projection is unavailable")
            if isinstance(parent_error, dict)
            else "parent projection is unavailable"
        )
    projection = json.loads(parent_path.read_text(encoding="utf-8"))
    elements = projection.get("elements") if isinstance(projection, dict) else None
    if not isinstance(elements, list):
        raise ValueError("parent projection has no element collection")
    matches = [
        item
        for item in elements
        if isinstance(item, dict) and item.get("id") == gap.get("id")
    ]
    if len(matches) != 1:
        raise ValueError(
            f"element gap {gap.get('id')} appears {len(matches)} times in the parent projection"
        )
    original = matches[0]
    if (
        original != gap.get("record")
        or _digest_bytes(_canonical(original)) != gap.get("record_sha256")
        or original.get("status") != "gap"
    ):
        raise ValueError(f"element gap {gap.get('id')} changed after assessment")
    audit = {
        "contract": admission["contract"],
        "assessment_round": admission["assessment_round"],
        "assessment_position": admission["assessment_position"],
        "parent_projection_id": parent["id"],
        "parent_projection_sha256": parent["sha256"],
        "original_gap_record_sha256": gap["record_sha256"],
        "accepted_assessment_sha256": admission[
            "accepted_assessment_sha256"
        ],
        "assessment_result_sha256": admission["assessment_result_sha256"],
        "answer_source_id": admission["answer_source"]["id"],
        "answer_source_sha256": admission["answer_source"]["sha256"],
        "answer_projection_id": admission["answer_projection"]["id"],
        "answer_projection_sha256": admission["answer_projection"]["sha256"],
        "answer_text_sha256": admission["answer_text_sha256"],
        "admission_input_sha256": admission["input_sha256"],
    }
    replacement = json.loads(json.dumps(original))
    replacement.update({
        "status": "readable",
        "content": admission["answer_text"],
        "gap_reason": "",
        "resolution_audit": audit,
    })
    projection["elements"] = [
        replacement
        if isinstance(item, dict) and item.get("id") == gap.get("id")
        else item
        for item in elements
    ]
    projection["projection_lineage"] = {
        "kind": "operator_text_element_gap_admission",
        "parent_projection_id": parent["id"],
        "parent_projection_sha256": parent["sha256"],
        "resolved_gap_id": gap["id"],
        "admission_input_sha256": admission["input_sha256"],
    }
    content = json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    parent_version = parent.get("version")
    source_id = parent.get("source_id")
    if not isinstance(parent_version, int) or parent_version < 1:
        raise ValueError("parent projection version must be a positive integer")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("parent projection source identity is missing")
    version = parent_version + 1
    gap_count = sum(
        item.get("status") == "gap"
        for collection in ("scan_regions", "elements", "relationships")
        for item in projection.get(collection, [])
        if isinstance(item, dict)
    )
    record = {
        "id": f"projection-{source_id}-v{version}",
        "source_id": source_id,
        "version": version,
        "parent_projection_id": parent["id"],
        "path": f"projections/{source_id}-v{version}.json",
        "sha256": _digest_bytes(content),
        "element_count": len(projection["elements"]),
        "relationship_count": len(projection.get("relationships", [])),
        "gap_count": gap_count,
        "coverage": "unassessed",
    }
    return content, record


def _operator_text_element_gap_admission_ready_result(
    state: dict[str, object], work: Path
) -> dict[str, object]:
    records = state.get("operator_text_element_gap_admissions")
    assert isinstance(records, list) and records and isinstance(records[-1], dict)
    admission = records[-1]
    result = {
        "status": "ready_for_projection_assessment",
        "stopped": "operator_text_element_gap_admitted",
        "intake_id": state["intake_id"],
        "projection": admission["projection"],
        "parent_projection": admission["parent_projection"],
        "resolved_gap": admission["gap"],
        "answer_source": admission["answer_source"],
        "answer_projection": admission["answer_projection"],
        "assessment_round": admission["assessment_round"],
        "assessment_position": admission["assessment_position"],
        "work": str(work.resolve()),
        "ledger": str((work / "ledger.jsonl").resolve()),
    }
    return _with_clarification_continuation(work, state, result)


def _consume_operator_text_element_gap_admission(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    decision: dict[str, object],
) -> dict[str, object]:
    round_number = decision.get("assessment_round")
    position = decision.get("assessment_position")
    if not isinstance(round_number, int) or not isinstance(position, int):
        return _blocked(
            "operator-text element admission unavailable",
            "the continuation decision lost its assessment identity",
        )
    admission, admission_error = _operator_text_element_gap_admission_input(
        work, state, round_number, position
    )
    if admission_error:
        return admission_error
    if admission is None:
        return _blocked(
            "operator-text element admission unavailable",
            "the selected resolving answer is not an element answer",
        )
    decision_gap = decision.get("gap")
    exact_gap = {
        key: admission["gap"][key]
        for key in (
            "projection_sha256", "collection", "kind", "id", "record_sha256"
        )
    }
    if decision_gap != exact_gap:
        return _blocked(
            "stale clarification continuation",
            "the operator-text element admission changed before execution",
        )
    records = state.get("operator_text_element_gap_admissions", [])
    if not isinstance(records, list) or not all(
        isinstance(item, dict) for item in records
    ):
        return _blocked(
            "operator-text element admission unavailable",
            "the admission history must remain an ordered list",
        )
    if any(
        item.get("assessment_round") == round_number
        and item.get("assessment_position") == position
        for item in records
    ):
        return _blocked(
            "operator-text element admission unavailable",
            "the exact assessed answer was already admitted",
        )
    try:
        projection_bytes, projection_record = (
            _build_operator_text_element_gap_projection(work, admission)
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return _blocked("operator-text element admission failed", str(error))
    projection_path = work / str(projection_record["path"])
    if projection_path.exists():
        return _blocked(
            "unbound projection version",
            f"projection path already exists: {projection_record['path']}",
        )
    projection_path.write_bytes(projection_bytes)
    created = _ledger_entry(
        len(entries) + 1,
        "projection_version_created",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "intake_id": state["intake_id"],
            "role": "operator_text_element_gap_admission",
            "assessment_round": round_number,
            "assessment_position": position,
            "parent_projection": admission["parent_projection"],
            "resolved_gap": admission["gap"],
            "question": admission["question"],
            "accepted_assessment_sha256": admission[
                "accepted_assessment_sha256"
            ],
            "assessment_result_sha256": admission["assessment_result_sha256"],
            "answer_source": admission["answer_source"],
            "answer_projection": admission["answer_projection"],
            "answer_text_sha256": admission["answer_text_sha256"],
            "admission_input_sha256": admission["input_sha256"],
            "projection": projection_record,
        },
        str(entries[-1]["entry_sha256"]),
    )
    _append_ledger(work / "ledger.jsonl", [created])
    saved = {
        **admission,
        "projection": projection_record,
        "ledger_sequence": created["sequence"],
    }
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "operator_text_element_gap_admitted",
        "waiting_for": None,
        "question": None,
        "current_projection": projection_record,
        "operator_text_element_gap_admissions": [*records, saved],
        "ledger_entries": created["sequence"],
        "ledger_tail_sha256": created["entry_sha256"],
    })
    _write_state(work / "intake-state.json", state)
    return _operator_text_element_gap_admission_ready_result(state, work)


def _validate_operator_text_element_gap_admissions(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    *,
    allow_later_phase: bool = False,
) -> dict[str, object] | None:
    records = state.get("operator_text_element_gap_admissions")
    if not isinstance(records, list) or not records or not all(
        isinstance(item, dict) for item in records
    ):
        return _blocked(
            "invalid operator-text element admission",
            "the immutable admission history is missing",
        )
    identities: list[tuple[int, int]] = []
    previous_sequence = 0
    for saved in records:
        round_number = saved.get("assessment_round")
        position = saved.get("assessment_position")
        parent = saved.get("parent_projection")
        if (
            not isinstance(round_number, int)
            or not isinstance(position, int)
            or not isinstance(parent, dict)
        ):
            return _blocked(
                "invalid operator-text element admission",
                "an admission lost its assessment or parent identity",
            )
        identities.append((round_number, position))
        admission, admission_error = _operator_text_element_gap_admission_input(
            work,
            state,
            round_number,
            position,
            parent_projection=parent,
        )
        if admission_error:
            return admission_error
        if admission is None:
            return _blocked(
                "invalid operator-text element admission",
                "a preserved admission no longer selects an element answer",
            )
        try:
            projection_bytes, projection_record = (
                _build_operator_text_element_gap_projection(work, admission)
            )
            actual_bytes = (work / str(projection_record["path"])).read_bytes()
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            return _blocked("invalid operator-text element admission", str(error))
        sequence = saved.get("ledger_sequence")
        created = (
            entries[sequence - 1]
            if isinstance(sequence, int) and 1 <= sequence <= len(entries)
            else None
        )
        expected_saved = {
            **admission,
            "projection": projection_record,
            "ledger_sequence": sequence,
        }
        expected_event = {
            "role": "operator_text_element_gap_admission",
            "assessment_round": round_number,
            "assessment_position": position,
            "parent_projection": admission["parent_projection"],
            "resolved_gap": admission["gap"],
            "question": admission["question"],
            "accepted_assessment_sha256": admission[
                "accepted_assessment_sha256"
            ],
            "assessment_result_sha256": admission["assessment_result_sha256"],
            "answer_source": admission["answer_source"],
            "answer_projection": admission["answer_projection"],
            "answer_text_sha256": admission["answer_text_sha256"],
            "admission_input_sha256": admission["input_sha256"],
            "projection": projection_record,
        }
        if (
            saved != expected_saved
            or actual_bytes != projection_bytes
            or not isinstance(sequence, int)
            or sequence <= previous_sequence
            or not isinstance(created, dict)
            or created.get("event") != "projection_version_created"
            or any(created.get(key) != value for key, value in expected_event.items())
        ):
            return _blocked(
                "immutable projection changed",
                "the operator answer, accepted assessment, or child projection changed",
            )
        previous_sequence = sequence
    if len(identities) != len(set(identities)):
        return _blocked(
            "invalid operator-text element admission",
            "one assessed answer was admitted more than once",
        )
    ledger_sequences = [
        entry.get("sequence")
        for entry in entries
        if entry.get("event") == "projection_version_created"
        and entry.get("role") == "operator_text_element_gap_admission"
    ]
    saved_sequences = [item.get("ledger_sequence") for item in records]
    if ledger_sequences != saved_sequences:
        return _blocked(
            "invalid operator-text element admission",
            "the admission history does not cover every ordered ledger event",
        )
    latest = records[-1]
    if (
        not allow_later_phase
        and (
            state.get("current_projection") != latest.get("projection")
            or (
                state.get("status") != "ready_for_projection_assessment"
                or state.get("phase") != "operator_text_element_gap_admitted"
                or state.get("waiting_for") is not None
                or state.get("question") is not None
                or state.get("ledger_entries") != len(entries)
                or state.get("ledger_tail_sha256")
                != entries[-1].get("entry_sha256")
            )
        )
    ):
        return _blocked(
            "invalid operator-text element admission",
            "the active child projection or admission state changed",
        )
    return None


def _gap_resolution_inputs(
    work: Path,
    state: dict[str, object],
    saved_resolution: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    saved_resolution = saved_resolution or state.get("gap_resolution")
    if isinstance(saved_resolution, dict) and saved_resolution.get("mode") == "assessed_answer":
        attempt = saved_resolution.get("attempt")
        round_number = saved_resolution.get("selected_assessment_round", 1)
        position = saved_resolution.get("selected_assessment_position")
        parent = _resolution_parent_record(state, saved_resolution)
        if (
            not isinstance(attempt, int)
            or not isinstance(round_number, int)
            or round_number < 1
            or not isinstance(position, int)
            or not isinstance(parent, dict)
        ):
            return None, _blocked(
                "gap resolution unavailable", "the assessed answer resolution identity is incomplete"
            )
        paths = _resolution_paths(attempt)
        binding, assessment, selection_error = _assessed_binding_at_position(
            work, state, round_number, position, parent
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
        assessment_gap = json.loads(json.dumps(binding["gap"]))
        assessment_gap["projection_sha256"] = assessment["gap"][
            "projection_sha256"
        ]
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
            "retry_of": clarification.get("prior_rejection"),
        }
        if round_number != 1 or "selected_assessment_round" in saved_resolution:
            expected["selected_assessment_round"] = round_number
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
            or clarification.get("prior_rejection")
            != saved_resolution.get("retry_of")
            or (
                "assessment_gap" in clarification
                and clarification.get("assessment_gap") != assessment_gap
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
    binding, assessment, _, error = _next_resolving_assessed_binding(
        work, shadow, first
    )
    return binding, assessment, error


def _request_gap_resolution(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    *,
    expected_continuation: dict[str, object] | None = None,
    retry_rejected_resolution: dict[str, object] | None = None,
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
    selected_round: int | None = None
    accepted_assessment_sha256: str | None = None
    retry_of: dict[str, object] | None = None
    if mode == "assessed_answer":
        parent = state.get("current_projection", state.get("first_projection"))
        if not isinstance(parent, dict):
            return _blocked(
                "gap resolution unavailable", "the current projection record is missing"
            )
        if retry_rejected_resolution is None:
            binding, assessment, selected_round, selection_error = _next_resolving_assessed_binding(
                work, state, parent
            )
        else:
            retry_is_current = retry_rejected_resolution is current
            retry_is_archived = any(
                retry_rejected_resolution is item
                for item in history
                if isinstance(item, dict)
            )
            retry_terminal_phase = (
                prior_phase
                if retry_is_current
                else retry_rejected_resolution.get("terminal_phase")
            )
            if not retry_is_current and not retry_is_archived:
                return _blocked(
                    "gap resolution retry unavailable",
                    "the retry is not bound to a preserved rejected resolution",
                )
            selected_round = retry_rejected_resolution.get(
                "selected_assessment_round", 1
            )
            selected_position_value = retry_rejected_resolution.get(
                "selected_assessment_position"
            )
            if (
                retry_terminal_phase != "gap_resolution_rejected"
                or retry_rejected_resolution.get("mode") != "assessed_answer"
                or retry_rejected_resolution.get("verification_verdict")
                not in {"not_supported", "unreadable"}
                or not isinstance(selected_round, int)
                or selected_round < 1
                or not isinstance(selected_position_value, int)
            ):
                return _blocked(
                    "gap resolution retry unavailable",
                    "the current rejection is not a complete independently verified assessed-answer resolution",
                )
            binding, assessment, selection_error = _assessed_binding_at_position(
                work,
                state,
                selected_round,
                selected_position_value,
                parent,
            )
        if selection_error:
            return selection_error
        assert binding is not None and assessment is not None
        selected_position = int(assessment["position"])
        current_gap = binding["gap"]
        actual_continuation = {
            "decision": (
                "retry_rejected_resolution"
                if retry_rejected_resolution is not None
                else "apply_resolving_answer"
            ),
            "assessment_round": selected_round,
            "assessment_position": selected_position,
            "gap": {
                key: current_gap[key]
                for key in (
                    "projection_sha256",
                    "collection",
                    "kind",
                    "id",
                    "record_sha256",
                )
            },
        }
        if retry_rejected_resolution is not None:
            actual_continuation["rejected_attempt"] = retry_rejected_resolution[
                "attempt"
            ]
        if (
            expected_continuation is not None
            and expected_continuation != actual_continuation
        ):
            return _blocked(
                "stale clarification continuation",
                "the apply-resolving-answer decision changed before execution",
            )
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
        if retry_rejected_resolution is not None:
            rejected_attempt = retry_rejected_resolution.get("attempt")
            if not isinstance(rejected_attempt, int):
                return _blocked(
                    "gap resolution retry unavailable",
                    "the rejected attempt identity is missing",
                )
            rejected_paths = _resolution_paths(rejected_attempt)
            try:
                rejected_candidate_bytes = (
                    work / rejected_paths["candidate_path"]
                ).read_bytes()
                rejected_candidate = json.loads(rejected_candidate_bytes)
                rejected_verification_bytes = (
                    work / rejected_paths["verification_result_path"]
                ).read_bytes()
                rejected_verification = json.loads(rejected_verification_bytes)
            except (OSError, json.JSONDecodeError):
                return _blocked(
                    "gap resolution retry unavailable",
                    "the immutable rejected proposal or verifier result is unavailable",
                )
            relationships = rejected_candidate.get("relationships")
            if (
                _digest_bytes(rejected_candidate_bytes)
                != retry_rejected_resolution.get("candidate_sha256")
                or _digest_bytes(rejected_verification_bytes)
                != retry_rejected_resolution.get("verification_result_sha256")
                or not isinstance(relationships, list)
                or len(relationships) != 1
                or not isinstance(relationships[0], dict)
                or rejected_verification.get("verdict")
                != retry_rejected_resolution.get("verification_verdict")
                or rejected_verification.get("reason")
                != retry_rejected_resolution.get("verification_reason")
            ):
                return _blocked(
                    "gap resolution retry unavailable",
                    "the rejected proposal or verifier reason changed",
                )
            retry_of = {
                "attempt": rejected_attempt,
                "candidate_sha256": retry_rejected_resolution["candidate_sha256"],
                "resolution_result_sha256": retry_rejected_resolution.get(
                    "result_sha256"
                ),
                "verification_result_sha256": retry_rejected_resolution[
                    "verification_result_sha256"
                ],
                "verification_verdict": rejected_verification["verdict"],
                "verification_reason": rejected_verification["reason"],
                "rejected_relationship": relationships[0],
            }
            clarification["prior_rejection"] = retry_of
        clarification_bytes = (
            json.dumps(clarification, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        attempt_dir.mkdir(parents=True)
        clarification_path = attempt_dir / "clarification.json"
        clarification_path.write_bytes(clarification_bytes)
        source = binding["answer_source"]
        projection = binding["answer_projection"]
        assert isinstance(source, dict) and isinstance(projection, dict)
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
            "selected_assessment_round": selected_round,
            "selected_assessment_position": selected_position,
            "accepted_assessment_sha256": accepted_assessment_sha256,
            "retry_of": retry_of,
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
            "selected_assessment_round": selected_round,
            "selected_assessment_position": selected_position,
            "accepted_assessment_sha256": accepted_assessment_sha256,
            "retry_of": retry_of,
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
    if isinstance(resolution.get("selected_assessment_round"), int):
        proposed["resolution_audit"]["accepted_assessment_round"] = resolution[
            "selected_assessment_round"
        ]
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
    if isinstance(resolution.get("selected_assessment_round"), int):
        original["projection_lineage"]["accepted_assessment_round"] = resolution[
            "selected_assessment_round"
        ]
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
        or entries[request_index].get("selected_assessment_round")
        != saved.get("selected_assessment_round")
        or entries[request_index].get("selected_assessment_position")
        != saved.get("selected_assessment_position")
        or entries[request_index].get("accepted_assessment_sha256")
        != saved.get("accepted_assessment_sha256")
        or entries[request_index].get("retry_of") != saved.get("retry_of")
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


def _validate_clarification_completion_predecessors(
    work: Path,
    state: dict[str, object],
    entries: list[dict[str, object]],
    purpose: str,
) -> dict[str, object] | None:
    completion = state.get("clarification_completion")
    if (
        isinstance(completion, dict)
        and completion.get("basis")
        == "additional_source_element_gap_admission"
    ):
        round_error = _validate_gap_question_round(
            work, state, entries, purpose, allow_later_phase=True
        )
        if round_error:
            return round_error
        additional_error = _validate_recorded_additional_projection(
            work, state, entries, purpose, allow_later_phase=True
        )
        if additional_error:
            return additional_error
        admission_error = _validate_additional_source_element_gap_admission(
            work, state, entries, purpose, allow_later_phase=True
        )
        if admission_error:
            return admission_error
        return None
    round_error = _validate_gap_question_round(
        work, state, entries, purpose, allow_later_phase=True
    )
    if round_error:
        return round_error
    assessment_error = _validate_gap_answer_assessment(
        work, state, entries, purpose, allow_later_phase=True
    )
    if assessment_error:
        return assessment_error
    records = state.get("prepared_question_round_assessments", [])
    if not isinstance(records, list):
        return _blocked(
            "invalid clarification completion",
            "the prepared-round assessment history is missing",
        )
    if records:
        follow_up_error = _validate_follow_up_gap_question_round(
            work, state, entries, purpose, allow_interview=True
        )
        if follow_up_error:
            return follow_up_error
        interview_error = _validate_prepared_question_round_interview(
            work,
            state,
            entries,
            purpose,
            allow_later_phase=True,
        )
        if interview_error:
            return interview_error
        prepared_assessment_error = _validate_prepared_question_round_assessment(
            work,
            state,
            entries,
            purpose,
            allow_later_phase=True,
        )
        if prepared_assessment_error:
            return prepared_assessment_error
    admissions = state.get("operator_text_element_gap_admissions", [])
    if admissions:
        admission_error = _validate_operator_text_element_gap_admissions(
            work, state, entries, allow_later_phase=True
        )
        if admission_error:
            return admission_error
    return _validate_gap_resolution_history(work, state, entries, purpose)


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
            gaps, projection_path, projection_sha256, context, binding_error = (
                _follow_up_gap_bindings(work, state)
            )
            if binding_error:
                return binding_error
            assert gaps is not None and projection_path is not None
            assert projection_sha256 is not None and context is not None
            assessment_round = context.get("assessment_round")
            if not isinstance(assessment_round, int):
                return _blocked(
                    "gap clarification unavailable",
                    "the assessed predecessor round is missing",
                )
            round_number = assessment_round + 1
            gap_clarification.run_round(
                work
                / "gap-question-rounds"
                / f"round-{round_number:06d}",
                projection_path=projection_path,
                projection_sha256=projection_sha256,
                purpose=purpose,
                gaps=gaps,
                round_number=round_number,
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
    bound_state, entries, load_error = _load_bound(work, opening.encode("utf-8"))
    if load_error:
        return load_error
    assert bound_state is not None
    state = bound_state
    if stopped == "assessing_prepared_question_round_answers":
        bindings, _, binding_error = (
            _validate_prepared_question_round_assessment_request(
                work, state, entries
            )
        )
        prepared = state.get("follow_up_gap_question_round")
        round_number = prepared.get("round") if isinstance(prepared, dict) else None
    else:
        bindings, binding_error = _validate_gap_answer_assessment_request(
            work, state, entries
        )
        round_number = 1
    if binding_error:
        return binding_error
    if bindings is None or not isinstance(round_number, int):
        return _blocked(
            "gap answer assessment unavailable",
            "the answer bindings or their round identity are missing",
        )
    model_bindings, _, contract_error = _answer_assessment_contract(bindings)
    if contract_error:
        return contract_error
    paths = _answer_assessment_paths(round_number)
    try:
        gap_answer_assessment.run(
            work / paths["directory"],
            bindings=model_bindings,
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except gap_answer_assessment.AssessmentError as error:
        return _blocked("gap answer assessment failed", str(error))
    return drive(work, opening, purpose)


def run_additional_source_gap_assessment(
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
    except OSError as error:
        return _blocked(
            "additional source gap assessment context unavailable", str(error)
        )
    current = drive(work, opening, purpose)
    if (
        current.get("status") != "waiting_for_model"
        or current.get("stopped") != "assessing_additional_source_gap"
    ):
        return _blocked(
            "additional source gap assessment unavailable",
            json.dumps(current, sort_keys=True),
        )
    try:
        state = json.loads(
            (work / "intake-state.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        return _blocked(
            "additional source gap assessment context unavailable", str(error)
        )
    saved = state.get("additional_source_gap_assessment")
    if not isinstance(saved, dict) or not isinstance(saved.get("paths"), dict):
        return _blocked(
            "additional source gap assessment unavailable",
            "the code-bound assessment request is missing",
        )
    try:
        additional_source_gap_assessment.run(
            work / str(saved["paths"]["directory"]),
            binding=saved["binding"],
            purpose=purpose,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    except additional_source_gap_assessment.AssessmentError as error:
        return _blocked("additional source gap assessment failed", str(error))
    return drive(work, opening, purpose)


def _clarification_boundary_result(
    result: dict[str, object], boundary: str
) -> dict[str, object]:
    if boundary == "needs_model_interview":
        work_items = result.get("work")
        if (
            result.get("status") != "waiting_for_model"
            or result.get("stopped") not in {
                "formulating_qualification_question_round",
                "formulating_gap_question",
                "formulating_gap_question_round",
                "formulating_follow_up_gap_question_round",
                "assessing_gap_answers",
                "assessing_prepared_question_round_answers",
                "resolving_gap_answer",
                "verifying_gap_resolution",
                "interviewing_additional_source_projection",
                "verifying_additional_source_projection",
                "correcting_additional_source_relationships",
                "verifying_additional_source_relationship_corrections",
                "assessing_additional_source_gap",
            }
            or not isinstance(work_items, list)
            or len(work_items) != 1
            or not isinstance(work_items[0], dict)
            or not isinstance(work_items[0].get("command"), list)
        ):
            return _blocked(
                "invalid clarification boundary",
                "the model boundary lost its single code-controlled interview command",
            )
    elif boundary == "needs_operator_answer":
        if (
            result.get("status") != "needs_operator"
            or result.get("stopped") not in {
                "awaiting_qualification_clarification_answers",
                "awaiting_gap_answer",
                "awaiting_gap_answers",
                "awaiting_prepared_question_round_answer",
            }
            or not isinstance(result.get("question"), dict)
        ):
            return _blocked(
                "invalid clarification boundary",
                "the operator boundary lost its single current question",
            )
    elif boundary == "clarification_complete":
        continuation = result.get("continuation")
        qualification = result.get("projection_qualification")
        closure = result.get("source_projection_closure")
        disposition = result.get("terminal_disposition")
        if (
            result.get("stopped") != "clarification_continuation_complete"
            or not isinstance(continuation, dict)
            or continuation.get("decision") != "clarification_complete"
            or not isinstance(qualification, dict)
            or qualification.get("qualification") != "readable_projection_complete"
            or not isinstance(closure, dict)
            or closure.get("verdict") != "all_projected"
            or not isinstance(disposition, dict)
            or disposition.get("disposition") != "first_layer_complete"
        ):
            return _blocked(
                "invalid clarification boundary",
                "the terminal boundary lost its grounded decision or projection qualification",
            )
    elif boundary == "source_conversion_required":
        continuation = result.get("continuation")
        qualification = result.get("projection_qualification")
        closure = result.get("source_projection_closure")
        disposition = result.get("terminal_disposition")
        incomplete = result.get("incomplete_source_outcomes")
        if (
            result.get("status") != "source_projection_closure"
            or result.get("stopped") != "source_conversion_required"
            or not isinstance(continuation, dict)
            or continuation.get("decision") != "clarification_complete"
            or not isinstance(qualification, dict)
            or qualification.get("qualification") != "readable_projection_complete"
            or not isinstance(closure, dict)
            or closure.get("verdict") != "conversion_incomplete"
            or not isinstance(disposition, dict)
            or disposition.get("disposition") != "source_conversion_required"
            or not isinstance(incomplete, list)
            or incomplete != disposition.get("incomplete_source_outcomes")
            or not isinstance(closure.get("outcomes"), list)
            or any(not isinstance(item, dict) for item in closure["outcomes"])
            or incomplete
            != [
                item
                for item in closure["outcomes"]
                if isinstance(item, dict) and item.get("outcome") != "projected"
            ]
        ):
            return _blocked(
                "invalid clarification boundary",
                "the source-conversion boundary lost its exact incomplete outcomes",
            )
    elif boundary == "clarification_required":
        continuation = result.get("continuation")
        qualification = result.get("projection_qualification")
        disposition = result.get("terminal_disposition")
        gaps = result.get("gaps")
        if (
            result.get("status") != "ready_for_projection_assessment"
            or result.get("stopped") != "clarification_required"
            or not isinstance(continuation, dict)
            or continuation.get("decision") != "clarification_complete"
            or not isinstance(qualification, dict)
            or qualification.get("qualification") != "readable_projection_incomplete"
            or not isinstance(disposition, dict)
            or disposition.get("disposition") != "clarification_required"
            or gaps != qualification.get("remaining_gaps")
            or gaps != disposition.get("remaining_gaps")
        ):
            return _blocked(
                "invalid clarification boundary",
                "the clarification-required boundary lost its exact remaining gaps",
            )
    elif boundary == "source_set_qualification_complete":
        closure = result.get("source_projection_closure")
        qualification = result.get("source_set_qualification")
        closure_outcomes = (
            closure.get("outcomes") if isinstance(closure, dict) else None
        )
        qualification_outcomes = (
            qualification.get("outcomes")
            if isinstance(qualification, dict)
            else None
        )
        if (
            result.get("status") != "source_set_qualification_complete"
            or result.get("stopped") != "source_set_qualification_complete"
            or not isinstance(closure_outcomes, list)
            or not isinstance(qualification_outcomes, list)
            or qualification.get("qualification")
            not in {
                "readable_source_set_complete",
                "readable_source_set_incomplete",
            }
            or qualification.get("source_count") != len(closure_outcomes)
            or len(qualification_outcomes) != len(closure_outcomes)
            or any(not isinstance(item, dict) for item in closure_outcomes)
            or any(not isinstance(item, dict) for item in qualification_outcomes)
            or [item.get("source_id") for item in qualification_outcomes]
            != [item.get("source_id") for item in closure_outcomes]
            or any(
                item.get("qualification")
                not in source_projection_qualification.QUALIFICATIONS
                for item in qualification_outcomes
                if isinstance(item, dict)
            )
        ):
            return _blocked(
                "invalid clarification boundary",
                "the source-set boundary lost its ordered adapter qualifications",
            )
    elif boundary == "qualification_admission_complete":
        qualification = result.get("source_set_qualification")
        route = result.get("route")
        obligations = result.get("clarification_obligations")
        if (
            result.get("status") != "qualification_admission_complete"
            or result.get("stopped") != "qualification_admission_complete"
            or route not in {
                "first_layer_complete",
                "clarification_required",
            }
            or not isinstance(qualification, dict)
            or not isinstance(obligations, list)
            or (route == "first_layer_complete" and obligations)
            or (route == "clarification_required" and not obligations)
        ):
            return _blocked(
                "invalid clarification boundary",
                "the qualification admission lost its terminal route or exact obligations",
            )
    elif boundary == "additional_source_projection_pending":
        if (
            result.get("status") != "ready_for_projection"
            or result.get("stopped") != "additional_source_frozen"
            or not isinstance(result.get("source"), dict)
            or not isinstance(result.get("projection"), dict)
            or result["projection"].get("status") != "pending"
        ):
            return _blocked(
                "invalid clarification boundary",
                "the additional-source boundary lost its frozen source or pending projection",
            )
    elif boundary == "first_source_projection_complete":
        projection = result.get("projection")
        method = projection.get("method") if isinstance(projection, dict) else None
        coverage = projection.get("coverage") if isinstance(projection, dict) else None
        spreadsheet_accounted = (
            method == "spreadsheet_ooxml_v1"
            and isinstance(coverage, dict)
            and coverage.get("status") in {"complete", "partial"}
            and isinstance(coverage.get("source_units"), int)
            and isinstance(coverage.get("represented_units"), int)
            and isinstance(coverage.get("gap_units"), int)
            and coverage["represented_units"] + coverage["gap_units"]
            == coverage["source_units"]
            and isinstance(coverage.get("parts"), list)
            and len(coverage["parts"]) == coverage["source_units"]
        )
        if (
            result.get("status") != "ready_for_projection_assessment"
            or result.get("stopped") not in {
                "first_verbatim_projection_recorded",
                "first_pdf_projection_recorded",
                "first_spreadsheet_projection_recorded",
            }
            or not isinstance(result.get("source"), dict)
            or not isinstance(projection, dict)
            or method not in {
                "verbatim_utf8", "pdf_visible_pages", "spreadsheet_ooxml_v1"
            }
            or not isinstance(coverage, dict)
            or (
                method != "spreadsheet_ooxml_v1"
                and coverage.get("status") != "complete"
            )
            or (method == "spreadsheet_ooxml_v1" and not spreadsheet_accounted)
        ):
            return _blocked(
                "invalid clarification boundary",
                "the first-source boundary lost its accounted readable projection",
            )
    elif boundary == "additional_source_projection_complete":
        projection = result.get("projection")
        if (
            result.get("status") != "ready_for_projection_assessment"
            or result.get("stopped") != "additional_source_projection_recorded"
            or not isinstance(result.get("source"), dict)
            or not isinstance(projection, dict)
            or projection.get("method") != "spreadsheet_ooxml_v1"
            or not isinstance(result.get("reserved_projection"), dict)
            or not isinstance(result.get("lineage"), dict)
        ):
            return _blocked(
                "invalid clarification boundary",
                "the additional-source boundary lost its spreadsheet projection identity",
            )
    elif boundary == "source_conversion_failed":
        projection = result.get("projection")
        if (
            result.get("status") != "ready_for_projection"
            or result.get("stopped") not in {
                "first_spreadsheet_projection_failed",
                "additional_spreadsheet_projection_failed",
            }
            or not isinstance(result.get("source"), dict)
            or not isinstance(projection, dict)
            or projection.get("status") != "failed"
            or projection.get("method") != "spreadsheet_ooxml_v1"
        ):
            return _blocked(
                "invalid clarification boundary",
                "the source-conversion failure lost its source-bound audit outcome",
            )
    elif boundary == "additional_source_gap_assessment_complete":
        assessment = result.get("assessment")
        if (
            result.get("status") != "ready_for_projection_assessment"
            or result.get("stopped")
            != "additional_source_gap_assessment_recorded"
            or not isinstance(result.get("source"), dict)
            or not isinstance(result.get("projection"), dict)
            or not isinstance(result.get("reserved_projection"), dict)
            or not isinstance(result.get("lineage"), dict)
            or not isinstance(assessment, dict)
            or assessment.get("verdict")
            not in additional_source_gap_assessment.VERDICTS
            or not isinstance(assessment.get("gap"), dict)
            or not isinstance(assessment.get("evidence"), list)
        ):
            return _blocked(
                "invalid clarification boundary",
                "the additional-source assessment boundary lost its exact gap, evidence, or verdict",
            )
    else:
        return _blocked(
            "invalid clarification boundary", f"unsupported boundary {boundary!r}"
        )
    return {**result, "boundary": boundary}


def run_clarification_boundary(work: Path) -> dict[str, object]:
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(
            encoding="utf-8"
        )
        purpose = (work / "sources" / "source-000002.txt").read_text(
            encoding="utf-8"
        )
    except OSError as error:
        return _blocked("clarification boundary unavailable", str(error))
    result = drive(work, opening, purpose)
    for _ in range(8):
        if result.get("status") == "blocked":
            return result
        if result.get("status") == "waiting_for_model":
            return _clarification_boundary_result(
                result, "needs_model_interview"
            )
        if result.get("status") == "needs_operator":
            return _clarification_boundary_result(
                result, "needs_operator_answer"
            )
        stopped = result.get("stopped")
        if stopped == "source_collection_complete":
            result = run_source_set_qualification(work)
            continue
        if stopped == "source_set_qualification_complete":
            result = run_qualification_admission(work)
            continue
        if stopped == "qualification_admission_complete":
            if result.get("route") == "clarification_required":
                result = request_qualification_question_round(work)
                continue
            return _clarification_boundary_result(
                result, "qualification_admission_complete"
            )
        if stopped == "clarification_continuation_complete":
            return _clarification_boundary_result(
                result, "clarification_complete"
            )
        if stopped in {
            "first_verbatim_projection_recorded",
            "first_spreadsheet_projection_recorded",
        }:
            return _clarification_boundary_result(
                result, "first_source_projection_complete"
            )
        if stopped == "first_pdf_projection_recorded":
            projection = result.get("projection")
            if isinstance(projection, dict) and projection.get("gap_count") == 0:
                return _clarification_boundary_result(
                    result, "first_source_projection_complete"
                )
            result = drive(work, opening, purpose, clarify_gap=True)
            continue
        if stopped == "source_conversion_required":
            return _clarification_boundary_result(
                result, "source_conversion_required"
            )
        if stopped in {
            "first_spreadsheet_projection_failed",
            "additional_spreadsheet_projection_failed",
        }:
            return _clarification_boundary_result(
                result, "source_conversion_failed"
            )
        if stopped == "additional_source_frozen":
            result = drive(work, opening, purpose, project_source=True)
            continue
        elif stopped == "additional_source_projection_recorded":
            projection = result.get("projection")
            if (
                isinstance(projection, dict)
                and projection.get("method") == "spreadsheet_ooxml_v1"
            ):
                return _clarification_boundary_result(
                    result, "additional_source_projection_complete"
                )
            state, entries, load_error = _load_bound(
                work, opening.encode("utf-8")
            )
            if load_error:
                return load_error
            assert state is not None
            result = _request_additional_source_gap_assessment(
                work, state, entries
            )
            continue
        elif stopped == "additional_source_gap_assessment_recorded":
            state, entries, load_error = _load_bound(
                work, opening.encode("utf-8")
            )
            if load_error:
                return load_error
            assert state is not None
            admission, admission_error = (
                _additional_source_element_gap_admission_input(state)
            )
            if admission_error:
                return admission_error
            if admission is None:
                return _clarification_boundary_result(
                    result, "additional_source_gap_assessment_complete"
                )
            result = _consume_additional_source_element_gap_admission(
                work, state, entries, purpose
            )
            if result.get("status") == "blocked":
                return result
            continue
        elif stopped == "additional_source_element_gap_admitted":
            state, entries, load_error = _load_bound(
                work, opening.encode("utf-8")
            )
            if load_error:
                return load_error
            assert state is not None
            result = _continue_additional_source_element_gap_admission(
                work, state, entries, purpose
            )
            if result.get("status") == "blocked":
                return result
            if result.get("stopped") == "clarification_required":
                return _clarification_boundary_result(
                    result, "clarification_required"
                )
            continue
        if stopped == "first_projection_recorded":
            result = drive(work, opening, purpose, clarify_gap=True)
        elif stopped == "clarification_required":
            result = drive(work, opening, purpose, clarify_gap=True)
        elif stopped == "follow_up_gap_question_round_recorded":
            result = drive(
                work, opening, purpose, conduct_question_round=True
            )
        elif stopped in {
            "gap_question_round_answered",
            "prepared_question_round_answered",
        }:
            result = drive(
                work, opening, purpose, assess_gap_answers=True
            )
        elif stopped in {
            "gap_answer_assessment_recorded",
            "prepared_question_round_assessment_recorded",
            "operator_text_element_gap_admitted",
            "gap_resolution_applied",
            "gap_resolution_rejected",
        }:
            result = drive(
                work, opening, purpose, continue_clarification=True
            )
        else:
            return _blocked(
                "clarification boundary unavailable",
                f"phase {stopped!r} is not a clarification-loop boundary",
            )
    return _blocked(
        "clarification boundary unavailable",
        "code-owned transitions did not reach an external boundary within 8 steps",
    )


def run_operator_turn(
    work: Path,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> dict[str, object]:
    boundary = run_clarification_boundary(work)
    question = boundary.get("question")
    if (
        boundary.get("boundary") != "needs_operator_answer"
        or not isinstance(question, dict)
        or not isinstance(question.get("id"), str)
        or not isinstance(question.get("asks"), str)
    ):
        return _blocked(
            "operator turn unavailable",
            "the intake does not have one code-controlled current operator question",
        )
    output_fn(f"Question: {question['asks']}")
    answer_type = question.get("answer_type", "operator_text")
    if answer_type not in {"operator_text", "local_file", "url"}:
        return _blocked(
            "operator turn unavailable",
            "the current question does not have a supported answer type",
        )
    output_fn({
        "local_file": "Answer type: one existing local file path",
        "url": "Answer type: one public HTTP(S) URL",
        "operator_text": "Answer type: non-empty text",
    }[str(answer_type)])
    try:
        answer = input_fn("Answer: ")
    except EOFError:
        return _blocked("operator answer unavailable", "no operator answer was supplied")
    confirmed = run_clarification_boundary(work)
    if (
        confirmed.get("boundary") != "needs_operator_answer"
        or confirmed.get("question") != question
        or confirmed.get("round") != boundary.get("round")
        or confirmed.get("answered_question_count")
        != boundary.get("answered_question_count")
    ):
        return _blocked(
            "operator question changed",
            "the active question changed before its answer could be preserved",
        )
    try:
        opening = (work / "sources" / "source-000001.txt").read_text(
            encoding="utf-8"
        )
        purpose = (work / "sources" / "source-000002.txt").read_text(
            encoding="utf-8"
        )
    except OSError as error:
        return _blocked("operator turn unavailable", str(error))
    if answer_type == "local_file":
        return drive(work, opening, purpose, gap_file=Path(answer))
    if answer_type == "url":
        return drive(work, opening, purpose, gap_url=answer)
    return drive(work, opening, purpose, gap_answer=answer)


def _resume(
    work: Path,
    opening_bytes: bytes,
    purpose: str | None,
    source: Path | None,
    project_source: bool,
    clarify_gap: bool,
    gap_answer: str | None,
    gap_file: Path | None,
    resolve_gap: bool,
    assess_gap_answers: bool,
    conduct_question_round: bool,
    continue_clarification: bool,
    source_url: str | None,
    gap_url: str | None,
    begin_source_collection: bool,
    source_collection_action: str | None,
    source_collection_kind: str | None,
) -> dict[str, object]:
    state, entries, error = _load_bound(work, opening_bytes)
    if error:
        return error
    assert state is not None
    phase = state.get("phase")
    if source is not None and source_url is not None:
        return _blocked(
            "operator input type mismatch",
            "supply either one local file or one URL as the first source, not both",
        )
    source_supplied = source is not None or source_url is not None
    if (
        begin_source_collection
        or source_collection_action is not None
        or source_collection_kind is not None
    ) and phase not in SOURCE_COLLECTION_TERMINAL_PHASES | SOURCE_COLLECTION_PHASES:
        return _blocked(
            "source collection unavailable",
            "begin source collection only after a source has a terminal projection outcome",
        )
    gap_inputs = sum(
        value is not None for value in (gap_answer, gap_file, gap_url)
    )
    if gap_inputs > 1:
        return _blocked(
            "operator input type mismatch",
            "supply exactly one of text, one local file, or one URL for the current question",
        )
    gap_input_supplied = gap_inputs == 1
    if continue_clarification and (
        source_supplied
        or project_source
        or clarify_gap
        or gap_input_supplied
        or resolve_gap
        or assess_gap_answers
        or conduct_question_round
    ):
        return _blocked(
            "clarification continuation invocation invalid",
            "execute one clarification continuation without another intake action",
        )
    if continue_clarification and phase not in {
        "gap_answer_assessment_recorded",
        "prepared_question_round_assessment_recorded",
        "operator_text_element_gap_admitted",
        "gap_resolution_applied",
        "gap_resolution_rejected",
        "clarification_continuation_complete",
    }:
        return _blocked(
            "clarification continuation unavailable",
            "continue only after an assessment, terminal admission, or prior clarification completion",
        )
    if conduct_question_round and (
        source_supplied
        or project_source
        or clarify_gap
        or gap_input_supplied
        or resolve_gap
        or assess_gap_answers
    ):
        return _blocked(
            "prepared question round invocation invalid",
            "start or resume the prepared question round without another intake action",
        )
    gap_input_phases = {
        "first_projection_recorded", "first_pdf_projection_recorded",
        "awaiting_gap_answer",
        "formulating_gap_question_round", "awaiting_gap_answers",
        "gap_question_round_answered",
        "gap_answer_assessment_recorded", "gap_resolution_applied",
        "gap_resolution_rejected", "formulating_follow_up_gap_question_round",
        "follow_up_gap_question_round_recorded",
        "prepared_question_round_assessment_recorded",
    }
    if clarify_gap and phase not in gap_input_phases:
        return _blocked(
            "gap clarification unavailable",
            "gap clarification input is only accepted after the first projection or at its operator question",
        )
    if gap_input_supplied and phase not in {
        *gap_input_phases,
        "awaiting_prepared_question_round_answers",
        "prepared_question_round_answered",
        "additional_source_frozen",
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
        "prepared_question_round_assessment_recorded",
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
            if source_supplied or project_source:
                return _blocked("purpose required", "answer the intake-purpose question before supplying a source")
            return _operator_result(state, work)
        if source_supplied or project_source:
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
        if source_supplied or project_source:
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
        "formulating_qualification_question_round",
        "awaiting_qualification_clarification_answers",
        "formulating_gap_question_round",
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
        "operator_text_element_gap_admitted",
        "clarification_continuation_complete",
        "additional_source_frozen",
        "interviewing_additional_source_projection",
        "additional_source_projection_recorded",
        "additional_spreadsheet_projection_failed",
        "assessing_additional_source_gap",
        "additional_source_gap_assessment_recorded",
        "additional_source_element_gap_admitted",
        "interviewing_pdf_page_projection",
        "first_pdf_projection_recorded",
        "first_pdf_projection_failed",
        "first_spreadsheet_projection_recorded",
        "first_spreadsheet_projection_failed",
    } or assessed_resolution_phase:
        supported_ledger_length = (
            len(entries) >= 8
            if phase in {
                "interviewing_pdf_page_projection",
                "first_pdf_projection_recorded",
                "first_pdf_projection_failed",
                "first_spreadsheet_projection_recorded",
                "first_spreadsheet_projection_failed",
            }
            else len(entries) >= 11
        )
    if phase in SOURCE_COLLECTION_PHASES:
        supported_ledger_length = len(entries) >= 8
    if phase not in {
        "awaiting_first_source", "clarifying_intake_purpose", "first_source_frozen",
        "interviewing_first_projection", "first_projection_recorded",
        "first_verbatim_projection_recorded",
        "first_spreadsheet_projection_recorded",
        "first_spreadsheet_projection_failed",
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
        "operator_text_element_gap_admitted",
        "clarification_continuation_complete",
        "additional_source_frozen",
        "interviewing_additional_source_projection",
        "additional_source_projection_recorded",
        "additional_spreadsheet_projection_failed",
        "assessing_additional_source_gap",
        "additional_source_gap_assessment_recorded",
        "additional_source_element_gap_admitted",
        "interviewing_pdf_page_projection",
        "first_pdf_projection_recorded",
        "first_pdf_projection_failed",
        "first_spreadsheet_projection_recorded",
        "first_spreadsheet_projection_failed",
        "formulating_qualification_question_round",
        "awaiting_qualification_clarification_answers",
        *SOURCE_COLLECTION_PHASES,
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

    if phase == "formulating_qualification_question_round":
        if (
            source_supplied
            or project_source
            or clarify_gap
            or gap_input_supplied
            or resolve_gap
            or assess_gap_answers
            or conduct_question_round
            or continue_clarification
            or begin_source_collection
            or source_collection_action is not None
            or source_collection_kind is not None
        ):
            return _blocked(
                "qualification question round active",
                "finish the current code-controlled question formulation without another intake action",
            )
        result_path = (
            work / "qualification-question-round" / "question-round.json"
        )
        if not result_path.exists():
            return _qualification_question_round_model_result(state, work)
        return _consume_qualification_question_round(
            work, state, entries, purpose_bytes.decode("utf-8")
        )

    if phase == "awaiting_qualification_clarification_answers":
        round_error = _validate_qualification_question_round(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
        if round_error:
            return round_error
        if (
            source_supplied
            or project_source
            or clarify_gap
            or gap_input_supplied
            or resolve_gap
            or assess_gap_answers
            or conduct_question_round
            or continue_clarification
            or begin_source_collection
            or source_collection_action is not None
            or source_collection_kind is not None
        ):
            return _blocked(
                "qualification clarification answer not implemented",
                (
                    "preserve the current first question without another intake action; "
                    "answer capture belongs to the next approved atom"
                ),
            )
        return _qualification_question_round_operator_result(state, work)

    expected_question = (
        FIRST_SOURCE_QUESTION
        if assessment["sufficient"] == "yes"
        else {"id": "intake-purpose-clarification", "asks": assessment["clarifying_question"]}
    )
    if entries[5].get("event") != "operator_question_asked" or entries[5].get("question") != expected_question:
        return _blocked("invalid ledger", "the current operator question is missing or changed")
    if assessment["sufficient"] == "no":
        if source_supplied or project_source:
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
        if not source_supplied:
            if project_source:
                return _blocked("source required", "freeze the first source before requesting its projection")
            return _operator_result(state, work)
        if project_source:
            return _blocked(
                "source not yet frozen",
                "freeze the supplied source before requesting its projection",
            )
        if source_url is not None:
            return _acquire_first_url(work, state, entries, source_url)
        assert source is not None
        return _acquire_first_source(work, state, entries, source)

    collection = state.get("source_collection")
    collection_active = (
        isinstance(collection, dict)
        and collection.get("mode") == "independent_multi_source"
    )
    if begin_source_collection or collection_active:
        if any((
            clarify_gap,
            gap_input_supplied,
            resolve_gap,
            assess_gap_answers,
            conduct_question_round,
            continue_clarification,
        )):
            return _blocked(
                "source collection invocation invalid",
                "source collection cannot be combined with semantic gap assessment",
            )
        return _resume_source_collection(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
            source,
            source_url,
            project_source,
            begin_source_collection,
            source_collection_action,
            source_collection_kind,
        )
    if source_collection_action is not None or source_collection_kind is not None:
        return _blocked(
            "source collection unavailable",
            "begin source collection after the current source reaches a terminal projection outcome",
        )

    frozen_error = _validate_frozen_first_source(
        work, state, entries, source, source_url
    )
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

    if phase == "first_verbatim_projection_recorded":
        verbatim_error = _validate_first_verbatim_utf8_projection(
            work, state, entries
        )
        if verbatim_error:
            return verbatim_error
        if (
            source_supplied
            or project_source
            or clarify_gap
            or gap_input_supplied
            or resolve_gap
            or assess_gap_answers
            or conduct_question_round
            or continue_clarification
        ):
            return _blocked(
                "first verbatim projection already recorded",
                "the frozen first source already has its immutable readable projection",
            )
        return _first_verbatim_projection_ready_result(state, work)

    if phase == "first_spreadsheet_projection_recorded":
        spreadsheet_error = _validate_spreadsheet_projection(
            work, state, entries, additional=False
        )
        if spreadsheet_error:
            return spreadsheet_error
        if any(
            (
                source_supplied,
                project_source,
                clarify_gap,
                gap_input_supplied,
                resolve_gap,
                assess_gap_answers,
                conduct_question_round,
                continue_clarification,
            )
        ):
            return _blocked(
                "first spreadsheet projection already recorded",
                "the frozen workbook already has its immutable readable projection",
            )
        return _spreadsheet_result(
            state, work, additional=False, failed=False
        )

    if phase == "first_spreadsheet_projection_failed":
        spreadsheet_error = _validate_spreadsheet_failure(
            work, state, entries, additional=False
        )
        if spreadsheet_error:
            return spreadsheet_error
        if any(
            (
                project_source,
                clarify_gap,
                gap_input_supplied,
                resolve_gap,
                assess_gap_answers,
                conduct_question_round,
                continue_clarification,
            )
        ):
            return _blocked(
                "spreadsheet conversion failure already recorded",
                "the failed outcome is immutable; preserve a corrected workbook as a new source",
            )
        return _spreadsheet_result(
            state, work, additional=False, failed=True
        )

    if phase in {
        "interviewing_pdf_page_projection",
        "first_pdf_projection_recorded",
    }:
        pdf_error = _validate_pdf_projection(
            work, state, entries, purpose_bytes.decode("utf-8")
        )
        if pdf_error:
            return pdf_error
        if phase == "first_pdf_projection_recorded":
            if clarify_gap:
                projection = state.get("first_projection")
                if not isinstance(projection, dict) or projection.get("gap_count") == 0:
                    return _blocked(
                        "gap clarification unavailable",
                        "the frozen PDF projection has no explicit gap",
                    )
                return _request_gap_question_round(work, state, entries)
            if (
                project_source
                or gap_input_supplied
                or resolve_gap
                or assess_gap_answers
                or conduct_question_round
                or continue_clarification
            ):
                return _blocked(
                    "first PDF projection already recorded",
                    "the frozen PDF already has its immutable readable projection",
                )
            return _pdf_projection_ready_result(state, work)
        page = _active_pdf_page(state)
        if page is None:
            return _blocked("invalid PDF projection state", "the active PDF page is missing")
        paths = _pdf_page_paths("source-000003", int(page["page"]))
        if not (work / paths["candidate_path"]).exists():
            return _pdf_projection_waiting_result(state, work, "project")
        return _consume_pdf_page_projection(
            work, state, entries, purpose_bytes.decode("utf-8")
        )

    if phase == "first_pdf_projection_failed":
        failure_error = _validate_pdf_projection_failure(state, entries)
        if failure_error:
            return failure_error
        if (
            project_source
            or clarify_gap
            or gap_input_supplied
            or resolve_gap
            or assess_gap_answers
            or conduct_question_round
            or continue_clarification
        ):
            return _blocked(
                "PDF conversion failure already recorded",
                "the failed projection outcome is immutable; preserve a converted source as a new intake source",
            )
        return _pdf_projection_failed_result(state, work)

    recorded_projection = state.get("first_projection")
    pdf_later_phase = (
        isinstance(recorded_projection, dict)
        and recorded_projection.get("method") == "pdf_visible_pages"
    )
    if pdf_later_phase:
        pdf_error = _validate_pdf_projection(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
            allow_later_phase=True,
        )
        if pdf_error:
            return pdf_error
    else:
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
        "operator_text_element_gap_admitted",
        "clarification_continuation_complete",
        "additional_source_frozen",
        "interviewing_additional_source_projection",
        "additional_source_projection_recorded",
        "additional_spreadsheet_projection_failed",
        "assessing_additional_source_gap",
        "additional_source_gap_assessment_recorded",
        "additional_source_element_gap_admitted",
    }
    if not pdf_later_phase:
        recorded_error = _validate_recorded_projection(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
            allow_later_phase=later_phase,
        )
        if recorded_error:
            return recorded_error
    prepared_history_error = _validate_prepared_question_round_history(
        work, state, entries, purpose_bytes.decode("utf-8")
    )
    if prepared_history_error:
        return prepared_history_error
    admission_events = [
        entry
        for entry in entries
        if entry.get("event") == "projection_version_created"
        and entry.get("role") == "operator_text_element_gap_admission"
    ]
    if state.get("operator_text_element_gap_admissions") or admission_events:
        admission_error = _validate_operator_text_element_gap_admissions(
            work,
            state,
            entries,
            allow_later_phase=phase != "operator_text_element_gap_admitted",
        )
        if admission_error:
            return admission_error
    if phase in {
        "additional_source_frozen",
        "interviewing_additional_source_projection",
        "additional_source_projection_recorded",
        "assessing_additional_source_gap",
        "additional_source_gap_assessment_recorded",
        "additional_source_element_gap_admitted",
    }:
        pending_error = _validate_pending_additional_source(
            work,
            state,
            entries,
            gap_file,
            gap_url,
            allow_projection=phase != "additional_source_frozen",
        )
        if pending_error:
            return pending_error
        pending = state.get("pending_additional_source")
        lineage = pending.get("lineage") if isinstance(pending, dict) else None
        round_number = (
            lineage.get("question_round") if isinstance(lineage, dict) else None
        )
        if not isinstance(round_number, int) or round_number < 1:
            return _blocked(
                "invalid intake state", "the pending source lost its question round"
            )
        round_error = _validate_gap_question_round(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
            allow_later_phase=True,
        )
        if round_error:
            return round_error
        if round_number > 1:
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
                allow_later_phase=True,
            )
            if interview_error:
                return interview_error
        if phase == "additional_source_element_gap_admitted":
            recorded_additional_error = _validate_recorded_additional_projection(
                work,
                state,
                entries,
                purpose_bytes.decode("utf-8"),
                allow_later_phase=True,
            )
            if recorded_additional_error:
                return recorded_additional_error
            admission_error = _validate_additional_source_element_gap_admission(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
            if admission_error:
                return admission_error
            if any((
                project_source,
                clarify_gap,
                resolve_gap,
                assess_gap_answers,
                conduct_question_round,
                continue_clarification,
            )) or gap_input_supplied:
                return _blocked(
                    "additional source element-gap admission complete",
                    "the immutable child projection is ready for the next atomic step",
                )
            return _additional_source_element_gap_admission_ready_result(
                state, work
            )
        if phase in {
            "assessing_additional_source_gap",
            "additional_source_gap_assessment_recorded",
        }:
            recorded_additional_error = _validate_recorded_additional_projection(
                work,
                state,
                entries,
                purpose_bytes.decode("utf-8"),
                allow_later_phase=True,
            )
            if recorded_additional_error:
                return recorded_additional_error
            if any((
                project_source,
                clarify_gap,
                resolve_gap,
                assess_gap_answers,
                conduct_question_round,
                continue_clarification,
            )) or gap_input_supplied:
                return _blocked(
                    "additional source gap assessment active",
                    "finish the exact code-controlled source-to-gap assessment before another intake action",
                )
            if phase == "assessing_additional_source_gap":
                _, request_error = (
                    _validate_additional_source_gap_assessment_request(
                        work, state, entries
                    )
                )
                if request_error:
                    return request_error
                saved_assessment = state.get(
                    "additional_source_gap_assessment"
                )
                paths = (
                    saved_assessment.get("paths")
                    if isinstance(saved_assessment, dict)
                    else None
                )
                if not isinstance(paths, dict):
                    return _blocked(
                        "invalid additional source gap assessment",
                        "the assessment artifact paths are missing",
                    )
                if not (work / str(paths["result_path"])).exists():
                    return _additional_source_gap_assessment_waiting_result(
                        state, work
                    )
                return _consume_additional_source_gap_assessment(
                    work,
                    state,
                    entries,
                    purpose_bytes.decode("utf-8"),
                )
            recorded_assessment_error = (
                _validate_recorded_additional_source_gap_assessment(
                    work,
                    state,
                    entries,
                    purpose_bytes.decode("utf-8"),
                )
            )
            if recorded_assessment_error:
                return recorded_assessment_error
            return _additional_source_gap_assessment_ready_result(state, work)
        if phase == "interviewing_additional_source_projection":
            request_error = _validate_additional_projection_request(
                work, state, entries
            )
            if request_error:
                return request_error
            if any((
                project_source,
                clarify_gap,
                resolve_gap,
                assess_gap_answers,
                conduct_question_round,
                continue_clarification,
            )) or gap_input_supplied:
                return _blocked(
                    "additional projection interview active",
                    "finish the current code-controlled projection interview before another intake action",
                )
            active = state.get("active_additional_projection")
            paths = active.get("paths") if isinstance(active, dict) else None
            if not isinstance(paths, dict):
                return _blocked(
                    "invalid intake state",
                    "the active additional projection paths are missing",
                )
            if not (work / str(paths["candidate_path"])).exists():
                return _additional_projection_waiting_result(state, work)
            return _consume_additional_projection(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
        if phase == "additional_source_projection_recorded":
            recorded_additional_error = _validate_recorded_additional_projection(
                work, state, entries, purpose_bytes.decode("utf-8")
            )
            if recorded_additional_error:
                return recorded_additional_error
            if any((
                project_source,
                clarify_gap,
                resolve_gap,
                assess_gap_answers,
                conduct_question_round,
                continue_clarification,
            )) or gap_input_supplied:
                return _blocked(
                    "additional projection already recorded",
                    "the additional source already has its immutable readable projection",
                )
            return _additional_projection_ready_result(state, work)
        if phase == "additional_spreadsheet_projection_failed":
            failure_error = _validate_spreadsheet_failure(
                work, state, entries, additional=True
            )
            if failure_error:
                return failure_error
            if any((
                project_source,
                clarify_gap,
                resolve_gap,
                assess_gap_answers,
                conduct_question_round,
                continue_clarification,
            )) or gap_input_supplied:
                return _blocked(
                    "spreadsheet conversion failure already recorded",
                    "the failed outcome is immutable; preserve a corrected workbook as a new source",
                )
            return _spreadsheet_result(
                state, work, additional=True, failed=True
            )
        if project_source:
            return _request_additional_projection(work, state, entries)
        if (
            any((
                clarify_gap,
                resolve_gap,
                assess_gap_answers,
                conduct_question_round,
                continue_clarification,
            ))
            or gap_answer is not None
        ):
            return _blocked(
                "additional source projection pending",
                "project the frozen additional source before another intake action",
            )
        return _additional_source_ready_result(state, work)
    if phase == "clarification_continuation_complete":
        predecessor_error = _validate_clarification_completion_predecessors(
            work,
            state,
            entries,
            purpose_bytes.decode("utf-8"),
        )
        if predecessor_error:
            return predecessor_error
        completion_error = _validate_clarification_completion(work, state, entries)
        if completion_error:
            return completion_error
        return _clarification_completion_result(state, work)
    if phase == "first_projection_recorded":
        if gap_input_supplied:
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
            if gap_input_supplied:
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
            if continue_clarification:
                return _execute_clarification_continuation(work, state, entries)
            if clarify_gap:
                return _request_follow_up_gap_question_round(work, state, entries)
            if resolve_gap:
                return _request_gap_resolution(work, state, entries)
            return _gap_answer_assessment_ready_result(state, work)
        if not gap_input_supplied:
            return _gap_question_round_operator_result(state, work)
        return _accept_gap_question_round_answer(
            work, state, entries, gap_answer, gap_file, gap_url
        )
    if phase == "operator_text_element_gap_admitted":
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
        admissions = state.get("operator_text_element_gap_admissions")
        latest_round = (
            admissions[-1].get("assessment_round")
            if isinstance(admissions, list)
            and admissions
            and isinstance(admissions[-1], dict)
            else None
        )
        if isinstance(latest_round, int) and latest_round >= 2:
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
                allow_later_phase=True,
            )
            if interview_error:
                return interview_error
            prepared_assessment_error = (
                _validate_prepared_question_round_assessment(
                    work,
                    state,
                    entries,
                    purpose_bytes.decode("utf-8"),
                    allow_later_phase=True,
                )
            )
            if prepared_assessment_error:
                return prepared_assessment_error
        admission_error = _validate_operator_text_element_gap_admissions(
            work, state, entries
        )
        if admission_error:
            return admission_error
        if continue_clarification:
            return _execute_clarification_continuation(work, state, entries)
        return _operator_text_element_gap_admission_ready_result(state, work)
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
            prepared = state.get("follow_up_gap_question_round")
            round_number = prepared.get("round") if isinstance(prepared, dict) else None
            if not isinstance(round_number, int):
                return _blocked(
                    "invalid intake state", "the active follow-up round is missing"
                )
            result_path = work / "gap-question-rounds" / f"round-{round_number:06d}" / "clarification-round.json"
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
            if gap_input_supplied:
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
            if gap_input_supplied:
                return _accept_prepared_question_round_answer(
                    work,
                    state,
                    entries,
                    purpose_bytes.decode("utf-8"),
                    gap_answer,
                    gap_file,
                    gap_url,
                )
            return _prepared_question_round_operator_result(state, work)
        if phase == "prepared_question_round_answered":
            if gap_input_supplied:
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
        if continue_clarification:
            return _execute_clarification_continuation(work, state, entries)
        if resolve_gap:
            return _request_gap_resolution(work, state, entries)
        if clarify_gap:
            return _request_follow_up_gap_question_round(work, state, entries)
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
        selected_round = resolution_state.get("selected_assessment_round", 1)
        if isinstance(selected_round, int) and selected_round >= 2:
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
                allow_later_phase=True,
            )
            if interview_error:
                return interview_error
            prepared_assessment_error = (
                _validate_prepared_question_round_assessment(
                    work,
                    state,
                    entries,
                    purpose_bytes.decode("utf-8"),
                    allow_later_phase=True,
                )
            )
            if prepared_assessment_error:
                return prepared_assessment_error
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
        if continue_clarification:
            return _execute_clarification_continuation(work, state, entries)
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
        if gap_file is not None or gap_url is not None:
            return _blocked(
                "operator input type mismatch",
                "this legacy question requires non-empty text, not a file or URL",
            )
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
    gap_file: Path | None = None,
    resolve_gap: bool = False,
    assess_gap_answers: bool = False,
    conduct_question_round: bool = False,
    continue_clarification: bool = False,
    source_url: str | None = None,
    gap_url: str | None = None,
    begin_source_collection: bool = False,
    source_collection_action: str | None = None,
    source_collection_kind: str | None = None,
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
            gap_file,
            resolve_gap,
            assess_gap_answers,
            conduct_question_round,
            continue_clarification,
            source_url,
            gap_url,
            begin_source_collection,
            source_collection_action,
            source_collection_kind,
        )
    if (
        purpose is not None
        or source is not None
        or source_url is not None
        or project_source
        or clarify_gap
        or gap_answer is not None
        or gap_file is not None
        or gap_url is not None
        or resolve_gap
        or assess_gap_answers
        or conduct_question_round
        or continue_clarification
        or begin_source_collection
        or source_collection_action is not None
        or source_collection_kind is not None
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
    parser.add_argument("--source-url", help="the first public HTTP(S) URL supplied by the operator")
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
        "--projection-region-id",
        help="the exact active region identity bound into a generated projection command",
    )
    parser.add_argument(
        "--projection-obligation-id",
        help=(
            "the exact pending relationship obligation identity bound into a "
            "generated projection command"
        ),
    )
    parser.add_argument(
        "--projection-endpoint-evidence-sha256",
        help=(
            "the exact endpoint crop identity bound into a generated fresh "
            "verification command"
        ),
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
        "--gap-file",
        type=Path,
        help="one local file supplied for a current file-typed gap question",
    )
    parser.add_argument(
        "--gap-url",
        help="one public HTTP(S) URL supplied for a current URL-typed gap question",
    )
    parser.add_argument(
        "--conduct-question-round",
        action="store_true",
        help="present the next question from a prepared operator round",
    )
    parser.add_argument(
        "--continue-clarification",
        action="store_true",
        help="execute exactly one code-selected clarification continuation",
    )
    parser.add_argument(
        "--clarification-boundary",
        action="store_true",
        help="advance code-only clarification transitions to one external boundary",
    )
    parser.add_argument(
        "--source-projection-closure",
        action="store_true",
        help="reconstruct one immutable readable-projection outcome for every source",
    )
    parser.add_argument(
        "--run-gap-clarification",
        action="store_true",
        help="formulate the code-bound operator question round for current gaps",
    )
    parser.add_argument(
        "--run-qualification-question-round",
        action="store_true",
        help="formulate one code-bound operator question for every admitted obligation",
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
        "--run-additional-source-gap-assessment",
        action="store_true",
        help="assess one projected additional source against its exact original gap",
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
    parser.add_argument(
        "--run-operator-turn",
        action="store_true",
        help="present and preserve exactly one current operator answer",
    )
    args = parser.parse_args()
    interview_flags = sum((
        args.run_projection_interview,
        args.run_projection_verification,
        args.run_relationship_correction,
        args.run_correction_verification,
        args.run_qualification_question_round,
        args.run_gap_clarification,
        args.run_gap_answer_assessment,
        args.run_additional_source_gap_assessment,
        args.run_gap_resolution,
        args.run_gap_resolution_verification,
        args.run_purpose_interview,
    ))
    if (
        args.projection_region_id is not None
        and args.projection_obligation_id is not None
    ):
        result = _blocked(
            "projection invocation invalid",
            "supply exactly one generated projection binding",
        )
    elif (
        args.projection_region_id is not None
        or args.projection_obligation_id is not None
        or args.projection_endpoint_evidence_sha256 is not None
    ) and not args.run_projection_interview:
        result = _blocked(
            "projection invocation invalid",
            "use a generated projection binding only for its projection interview",
        )
    elif (args.gap_file is not None or args.gap_url is not None) and (
        args.run_operator_turn
        or args.clarification_boundary
        or args.source_projection_closure
        or interview_flags
    ):
        result = _blocked(
            "operator input invocation invalid",
            "supply a gap file or URL only through the ordinary intake input path",
        )
    elif args.run_operator_turn and (
        interview_flags
        or args.clarification_boundary
        or args.source_projection_closure
        or any(
            value is not None
            for value in (
                args.opening,
                args.purpose,
                args.source,
                args.source_url,
                args.gap_answer,
                args.gap_url,
            )
        )
        or args.project_source
        or args.clarify_gap
        or args.resolve_gap
        or args.assess_gap_answers
        or args.conduct_question_round
        or args.continue_clarification
    ):
        result = _blocked(
            "operator turn invocation invalid",
            "run one operator turn with only --work and --run-operator-turn",
        )
    elif args.run_operator_turn:
        result = run_operator_turn(args.work)
    elif args.conduct_question_round and interview_flags:
        result = _blocked(
            "interview invocation invalid",
            "conduct the prepared operator round separately from model interviews",
        )
    elif interview_flags and (
        args.resolve_gap
        or args.assess_gap_answers
        or args.continue_clarification
    ):
        result = _blocked(
            "interview invocation invalid",
            "request or run one gap-resolution stage at a time",
        )
    elif interview_flags > 1:
        result = _blocked("interview invocation invalid", "run exactly one interview at a time")
    elif args.source_projection_closure:
        if (
            interview_flags
            or args.clarification_boundary
            or any(
                value is not None
                for value in (
                    args.opening,
                    args.purpose,
                    args.source,
                    args.source_url,
                    args.gap_answer,
                    args.gap_url,
                )
            )
            or args.project_source
            or args.clarify_gap
            or args.resolve_gap
            or args.assess_gap_answers
            or args.conduct_question_round
            or args.continue_clarification
        ):
            result = _blocked(
                "source projection closure invocation invalid",
                "run the source-projection closure gate with only --work and --source-projection-closure",
            )
        else:
            result = run_source_projection_closure(args.work)
    elif args.clarification_boundary:
        if (
            interview_flags
            or any(
                value is not None
                for value in (
                    args.opening,
                    args.purpose,
                    args.source,
                    args.source_url,
                    args.gap_answer,
                    args.gap_url,
                )
            )
            or args.project_source
            or args.clarify_gap
            or args.resolve_gap
            or args.assess_gap_answers
            or args.conduct_question_round
            or args.continue_clarification
        ):
            result = _blocked(
                "clarification boundary invocation invalid",
                "run the clarification boundary controller with only --work and --clarification-boundary",
            )
        else:
            result = run_clarification_boundary(args.work)
    elif args.run_purpose_interview:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
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
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
            or args.project_source or args.clarify_gap or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                (
                    "run the projection interview only through its code-generated "
                    "region-bound command"
                ),
            )
        else:
            result = run_first_projection_interview(
                args.work,
                expected_region_id=args.projection_region_id,
                expected_obligation_id=args.projection_obligation_id,
                expected_endpoint_evidence_sha256=(
                    args.projection_endpoint_evidence_sha256
                ),
                region_binding_required=True,
            )
    elif args.run_projection_verification:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
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
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
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
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
            or args.project_source or args.clarify_gap or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run correction verification with only --work and --run-correction-verification",
            )
        else:
            result = run_relationship_correction_verification(args.work)
    elif args.run_qualification_question_round:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
            or args.project_source or args.clarify_gap or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run qualification question formulation with only --work and --run-qualification-question-round",
            )
        else:
            result = run_qualification_question_round(args.work)
    elif args.run_gap_clarification:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
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
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
            or args.project_source or args.clarify_gap or args.resolve_gap
            or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run gap answer assessment with only --work and --run-gap-answer-assessment",
            )
        else:
            result = run_gap_answer_assessment(args.work)
    elif args.run_additional_source_gap_assessment:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
            or args.project_source or args.clarify_gap or args.resolve_gap
            or args.assess_gap_answers
        ):
            result = _blocked(
                "interview invocation invalid",
                "run additional-source gap assessment with only --work and --run-additional-source-gap-assessment",
            )
        else:
            result = run_additional_source_gap_assessment(args.work)
    elif args.run_gap_resolution:
        if (
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
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
            any(value is not None for value in (args.opening, args.purpose, args.source, args.source_url, args.gap_answer, args.gap_url))
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
            args.gap_file,
            args.resolve_gap,
            args.assess_gap_answers,
            args.conduct_question_round,
            args.continue_clarification,
            args.source_url,
            args.gap_url,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return {
        "ready_for_projection": 0,
        "ready_for_projection_assessment": 0,
        "ready_for_operator_interview": 0,
        "source_projection_closure": 0,
        "waiting_for_model": 2,
        "blocked": 3,
        "needs_operator": 4,
    }[str(result["status"])]


if __name__ == "__main__":
    raise SystemExit(main())
