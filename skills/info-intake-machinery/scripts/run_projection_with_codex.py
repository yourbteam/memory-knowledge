#!/usr/bin/env python3
"""Drive pending image-intake model stages to the next external boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

START_INTAKE = Path(__file__).resolve().with_name("start_intake.py")
_INTERVIEW_SPEC = importlib.util.spec_from_file_location(
    "info_intake_projection_interview_for_runner",
    Path(__file__).resolve().with_name("projection_interview.py"),
)
if _INTERVIEW_SPEC is None or _INTERVIEW_SPEC.loader is None:
    raise RuntimeError("projection interview engine is unavailable")
projection_interview = importlib.util.module_from_spec(_INTERVIEW_SPEC)
_INTERVIEW_SPEC.loader.exec_module(projection_interview)


class LaunchError(ValueError):
    """The saved intake cannot be launched through this adapter."""


BOUNDARY_EXIT_CODES = {
    "needs_model_interview": 2,
    "needs_operator_answer": 4,
    "clarification_complete": 0,
    "clarification_required": 0,
    "source_conversion_required": 0,
    "first_source_projection_complete": 0,
    "additional_source_projection_pending": 0,
    "additional_source_gap_assessment_complete": 0,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_stage_progress(work: Path) -> dict[str, str | None]:
    state_path = work / "intake-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LaunchError("the intake state is unavailable or invalid") from error
    if not isinstance(state, dict):
        raise LaunchError("the intake state must be an object")
    waiting_for = state.get("waiting_for")
    if not isinstance(waiting_for, str):
        return {
            "intake_state_sha256": _sha256(state_path),
            "model_journal_sha256": None,
        }
    journal = (work / waiting_for).resolve()
    try:
        journal.relative_to(work.resolve())
    except ValueError as error:
        raise LaunchError("the active model journal escapes the intake") from error
    if not journal.is_file():
        raise LaunchError("the active model journal is unavailable")
    return {
        "intake_state_sha256": _sha256(state_path),
        "model_journal_sha256": _sha256(journal),
    }


def load_request(work: Path) -> tuple[Path | tuple[Path, ...], list[str]]:
    work = work.expanduser().resolve()
    try:
        state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LaunchError("the intake state is unavailable or invalid") from error
    if not isinstance(state, dict):
        raise LaunchError("the intake state must be an object")
    projection_phase = (
        state.get("status") == "waiting_for_model"
        and (
            (
                state.get("phase") == "interviewing_first_projection"
                and state.get("waiting_for")
                == "projection-interviews/attempt-000001/interview.jsonl"
            )
            or (
                state.get("phase") == "interviewing_additional_source_projection"
                and isinstance(state.get("active_additional_projection"), dict)
                and isinstance(
                    state["active_additional_projection"].get("paths"), dict
                )
                and state.get("waiting_for")
                == state["active_additional_projection"]["paths"].get(
                    "interview_path"
                )
            )
            or (
                state.get("phase") == "interviewing_pdf_page_projection"
                and isinstance(state.get("pdf_projection"), dict)
                and isinstance(state["pdf_projection"].get("prepared"), dict)
                and isinstance(state["pdf_projection"].get("active_page"), int)
                and state.get("waiting_for")
                == (
                    "pdf-projections/"
                    f"{state['pdf_projection']['prepared'].get('source_id')}-v1/"
                    "page-projections/"
                    f"page-{state['pdf_projection']['active_page']:06d}/"
                    "projection-interview/interview.jsonl"
                )
            )
        )
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
                and isinstance(state.get("follow_up_gap_question_round"), dict)
                and isinstance(
                    state["follow_up_gap_question_round"].get("round"), int
                )
                and state.get("waiting_for")
                == (
                    "gap-question-rounds/"
                    f"round-{state['follow_up_gap_question_round']['round']:06d}/"
                    "interview.jsonl"
                )
            )
        )
    )
    gap_answer_assessment_phase = (
        state.get("status") == "waiting_for_model"
        and (
            (
                state.get("phase") == "assessing_gap_answers"
                and state.get("waiting_for")
                == "gap-answer-assessments/round-000001/interview.jsonl"
            )
            or (
                state.get("phase") == "assessing_prepared_question_round_answers"
                and isinstance(state.get("prepared_question_round_interview"), dict)
                and isinstance(
                    state["prepared_question_round_interview"].get("round"), int
                )
                and state.get("waiting_for")
                == (
                    "gap-answer-assessments/"
                    f"round-{state['prepared_question_round_interview']['round']:06d}/"
                    "interview.jsonl"
                )
            )
        )
    )
    additional_source_gap_assessment_phase = (
        state.get("status") == "waiting_for_model"
        and state.get("phase") == "assessing_additional_source_gap"
        and isinstance(state.get("additional_source_gap_assessment"), dict)
        and isinstance(
            state["additional_source_gap_assessment"].get("paths"), dict
        )
        and state.get("waiting_for")
        == state["additional_source_gap_assessment"]["paths"].get(
            "interview_path"
        )
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
            additional_source_gap_assessment_phase,
            resolution_phase,
            resolution_verification_phase,
        )
    ):
        raise LaunchError("the intake is not waiting for a supported visual model stage")
    if additional_source_gap_assessment_phase:
        saved = state["additional_source_gap_assessment"]
        attachments = saved.get("attachments")
        binding = saved.get("binding")
        if (
            not isinstance(attachments, list)
            or not attachments
            or not isinstance(binding, dict)
        ):
            raise LaunchError(
                "the additional-source assessment lost its bound attachments"
            )
        gap = binding.get("gap")
        first_source = state.get("first_source")
        additional_source = binding.get("additional_source")
        expected: list[tuple[str, str]] = []
        if (
            isinstance(gap, dict)
            and isinstance(gap.get("render_path"), str)
            and isinstance(gap.get("render_sha256"), str)
        ):
            expected.append((gap["render_path"], gap["render_sha256"]))
        elif (
            isinstance(first_source, dict)
            and str(first_source.get("media_type", "")).startswith("image/")
            and isinstance(first_source.get("stored_path"), str)
            and isinstance(first_source.get("sha256"), str)
        ):
            expected.append(
                (first_source["stored_path"], first_source["sha256"])
            )
        if (
            isinstance(additional_source, dict)
            and str(additional_source.get("media_type", "")).startswith("image/")
            and isinstance(additional_source.get("stored_path"), str)
            and isinstance(additional_source.get("sha256"), str)
        ):
            expected.append(
                (
                    additional_source["stored_path"],
                    additional_source["sha256"],
                )
            )
        expected_paths = [
            str((work / stored_path).resolve())
            for stored_path, _sha256_value in expected
        ]
        if attachments != expected_paths:
            raise LaunchError(
                "the additional-source assessment attachment identity changed"
            )
        resolved: list[Path] = []
        for item, (_stored_path, expected_sha256) in zip(attachments, expected):
            if not isinstance(item, str):
                raise LaunchError(
                    "an additional-source assessment attachment is invalid"
                )
            attachment = Path(item).resolve()
            try:
                attachment.relative_to(work)
            except ValueError as error:
                raise LaunchError(
                    "an additional-source assessment attachment escapes the intake"
                ) from error
            if (
                not attachment.is_file()
                or _sha256(attachment) != expected_sha256
            ):
                raise LaunchError(
                    "an additional-source assessment attachment changed"
                )
            resolved.append(attachment)
        return tuple(resolved), [
            sys.executable,
            str(START_INTAKE),
            "--work",
            str(work),
            "--run-additional-source-gap-assessment",
        ]
    if (
        gap_round_phase
        and isinstance(state.get("first_projection"), dict)
        and state["first_projection"].get("method") == "pdf_visible_pages"
    ):
        saved_round = state.get("gap_question_round")
        gaps = saved_round.get("gaps") if isinstance(saved_round, dict) else None
        if not isinstance(gaps, list) or not gaps:
            raise LaunchError("the PDF gap inventory is missing")
        attachments: list[Path] = []
        seen_paths: set[str] = set()
        previous_page = 0
        for gap in gaps:
            if not isinstance(gap, dict):
                raise LaunchError("the PDF gap inventory is invalid")
            page = gap.get("page")
            stored_path = gap.get("render_path")
            expected_sha256 = gap.get("render_sha256")
            if (
                not isinstance(page, int)
                or page < previous_page
                or not isinstance(stored_path, str)
                or not isinstance(expected_sha256, str)
            ):
                raise LaunchError("the PDF gap page identity is invalid")
            previous_page = page
            if stored_path in seen_paths:
                continue
            attachment = (work / stored_path).resolve()
            try:
                attachment.relative_to(work)
            except ValueError as error:
                raise LaunchError("a PDF gap page escapes the intake directory") from error
            if not attachment.is_file() or _sha256(attachment) != expected_sha256:
                raise LaunchError("a frozen PDF gap page is unavailable or has changed")
            seen_paths.add(stored_path)
            attachments.append(attachment)
        return tuple(attachments), [
            sys.executable,
            str(START_INTAKE),
            "--work",
            str(work),
            "--run-gap-clarification",
        ]
    additional_projection = (
        projection_phase
        and state.get("phase") == "interviewing_additional_source_projection"
    )
    pdf_projection = (
        projection_phase
        and state.get("phase") == "interviewing_pdf_page_projection"
    )
    pending = state.get("pending_additional_source")
    if pdf_projection:
        saved_pdf = state.get("pdf_projection")
        prepared = saved_pdf.get("prepared") if isinstance(saved_pdf, dict) else None
        active_page = saved_pdf.get("active_page") if isinstance(saved_pdf, dict) else None
        pages = prepared.get("pages") if isinstance(prepared, dict) else None
        if (
            not isinstance(active_page, int)
            or not isinstance(pages, list)
            or active_page < 1
            or active_page > len(pages)
            or not isinstance(pages[active_page - 1], dict)
        ):
            raise LaunchError("the active PDF page record is missing")
        page = pages[active_page - 1]
        source = {
            "stored_path": page.get("render_path"),
            "sha256": page.get("render_sha256"),
            "media_type": page.get("media_type"),
        }
    else:
        source = (
            pending.get("source")
            if additional_projection and isinstance(pending, dict)
            else state.get("first_source")
        )
    if not isinstance(source, dict):
        raise LaunchError(
            "the frozen additional-source record is missing"
            if additional_projection
            else "the frozen first-source record is missing"
        )
    media_type = source.get("media_type")
    if not isinstance(media_type, str) or not media_type.startswith("image/"):
        raise LaunchError("the pending source is not supported by the image projection adapter")
    stored_path = source.get("stored_path")
    expected_sha256 = source.get("sha256")
    if not isinstance(stored_path, str) or not isinstance(expected_sha256, str):
        raise LaunchError(
            "the frozen additional-source identity is incomplete"
            if additional_projection
            else "the frozen first-source identity is incomplete"
        )
    attachment = (work / stored_path).resolve()
    try:
        attachment.relative_to(work)
    except ValueError as error:
        raise LaunchError(
            "the frozen additional source escapes the intake directory"
            if additional_projection
            else "the frozen first source escapes the intake directory"
        ) from error
    if not attachment.is_file() or _sha256(attachment) != expected_sha256:
        raise LaunchError(
            "the frozen additional source is unavailable or has changed"
            if additional_projection
            else "the frozen first source is unavailable or has changed"
        )
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
    active = state.get("active_additional_projection")
    paths = active.get("paths") if isinstance(active, dict) else None
    if pdf_projection:
        assert isinstance(saved_pdf, dict) and isinstance(prepared, dict)
        assert isinstance(active_page, int)
        root = (
            "pdf-projections/"
            f"{prepared['source_id']}-v1/page-projections/page-{active_page:06d}"
        )
        candidate = work / root / "projection-interview" / "projection.json"
        verification = work / root / "relationship-verification" / "verification.json"
        corrections = work / root / "relationship-correction" / "corrections.json"
        correction_verification = (
            work / root / "relationship-correction-verification" / "verification.json"
        )
    elif additional_projection:
        if not isinstance(paths, dict):
            raise LaunchError("the additional projection artifact paths are missing")
        candidate = work / str(paths["candidate_path"])
        verification = work / str(paths["verification_path"])
        corrections = work / str(paths["correction_path"])
        correction_verification = work / str(
            paths["correction_verification_path"]
        )
    else:
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
    if flag == "--run-projection-interview":
        try:
            purpose = (work / "sources" / "source-000002.txt").read_text(
                encoding="utf-8"
            )
            contract = int(
                state.get(
                    "projection_interview_contract",
                    projection_interview.CONTRACT,
                )
            )
            projection_interview.enable_endpoint_crop_verification(
                candidate.parent, purpose=purpose, contract=contract,
            )
            projection_interview.enable_existing_participant_crop_verification(
                candidate.parent, purpose=purpose, contract=contract,
            )
            projection_interview.enable_contextual_endpoint_verification(
                candidate.parent, purpose=purpose, contract=contract,
            )
            projection_interview.enable_endpoint_context_evidence(
                candidate.parent, purpose=purpose, contract=contract,
            )
            projection_interview.enable_endpoint_selector_context(
                candidate.parent, purpose=purpose, contract=contract,
            )
            projection_interview.enable_endpoint_identity_context_choice(
                candidate.parent, purpose=purpose, contract=contract,
            )
            projection_interview.enable_negative_context_replacement(
                candidate.parent, purpose=purpose, contract=contract,
            )
            projection_interview.enable_rejected_endpoint_reuse_block(
                candidate.parent, purpose=purpose, contract=contract,
            )
            projection_interview.enable_rejected_endpoint_collision_exclusion(
                candidate.parent, purpose=purpose, contract=contract,
            )
            endpoint_evidence = projection_interview.prepare_endpoint_evidence(
                candidate.parent,
                source_path=attachment,
                source_sha256=str(expected_sha256),
                purpose=purpose,
                contract=contract,
            )
            crop = projection_interview.prepare_region_evidence(
                candidate.parent,
                source_path=attachment,
                source_sha256=str(expected_sha256),
                purpose=purpose,
                contract=contract,
            )
            interview_state, _pending, _completed = (
                projection_interview.prepare_resume(
                    candidate.parent,
                    purpose=purpose,
                    contract=contract,
                )
            )
            replacement_attachments = (
                projection_interview.required_participant_replacement_attachments(
                    candidate.parent,
                    interview_state,
                    source_path=attachment,
                    source_sha256=str(expected_sha256),
                )
            )
            if contract >= 4:
                active_region = projection_interview._active_scan_region(
                    interview_state
                )
                if isinstance(active_region, dict) and isinstance(
                    active_region.get("id"), str
                ):
                    command[-1:-1] = [
                        "--projection-region-id", str(active_region["id"]),
                    ]
                else:
                    obligation = projection_interview._pending_obligation(
                        interview_state
                    )
                    if not isinstance(obligation, dict) or not isinstance(
                        obligation.get("id"), str
                    ):
                        raise projection_interview.InterviewError(
                            "active-projection-binding-missing"
                        )
                    command[-1:-1] = [
                        "--projection-obligation-id",
                        str(obligation["id"]),
                    ]
                    if endpoint_evidence is not None:
                        command[-1:-1] = [
                            "--projection-endpoint-evidence-sha256",
                            endpoint_evidence[1],
                        ]
        except (OSError, projection_interview.InterviewError) as error:
            raise LaunchError(
                f"projection binding evidence failed: {error}"
            ) from error
        if endpoint_evidence is not None:
            attachment = endpoint_evidence[0]
        elif replacement_attachments is not None:
            attachment = replacement_attachments
        elif crop is not None:
            attachment = crop
    return attachment, command


def build_codex_argv(
    executable: str,
    work: Path,
    attachment: Path | tuple[Path, ...],
    interview_command: list[str],
) -> list[str]:
    command_text = " ".join(json.dumps(part) for part in interview_command)
    flag = interview_command[-1]
    purpose_assessment = flag == "--run-purpose-interview"
    independently = flag in {
        "--run-projection-verification",
        "--run-correction-verification",
        "--run-gap-resolution-verification",
    }
    correction = flag == "--run-relationship-correction"
    gap_clarification = flag == "--run-gap-clarification"
    gap_answer_assessment = flag == "--run-gap-answer-assessment"
    additional_source_gap_assessment = (
        flag == "--run-additional-source-gap-assessment"
    )
    gap_resolution = flag == "--run-gap-resolution"
    evidence_instruction = (
        "the code-bound preserved operator purpose answer"
        if purpose_assessment else
        "the code-bound preserved answer and visible source context"
        if gap_answer_assessment or additional_source_gap_assessment or gap_resolution
        else "visible source evidence"
    )
    prompt = (
        (
            "Assess only the code-bound preserved operator purpose answer. "
            if purpose_assessment else
            "Inspect the attached frozen source and formulate one focused operator question for each code-bound gap presented. "
            if gap_clarification else
            "Inspect the attached frozen source and judge each code-bound preserved answer only against its exact gap. "
            if gap_answer_assessment else
            "Inspect the attached frozen original and additional sources and assess only whether code-listed evidence resolves the exact bound gap. "
            if additional_source_gap_assessment else
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
    attachments = attachment if isinstance(attachment, tuple) else (attachment,)
    image_arguments = [part for path in attachments for part in ("--image", str(path))]
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
        *image_arguments,
        "--",
        prompt,
    ]


def run_clarification_boundary(work: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(START_INTAKE),
            "--work",
            str(work),
            "--clarification-boundary",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise LaunchError("the clarification boundary did not return valid JSON") from error
    if not isinstance(result, dict):
        raise LaunchError("the clarification boundary must return an object")
    if result.get("status") == "blocked":
        return result
    boundary = result.get("boundary")
    if boundary not in BOUNDARY_EXIT_CODES:
        raise LaunchError("the clarification boundary returned an unsupported outcome")
    if completed.returncode != BOUNDARY_EXIT_CODES[boundary]:
        raise LaunchError("the clarification boundary exit code does not match its outcome")
    return result


def next_model_request(
    work: Path,
    boundary_result: dict[str, object],
) -> tuple[Path | tuple[Path, ...], list[str]] | None:
    boundary = boundary_result.get("boundary")
    if boundary != "needs_model_interview":
        return None
    work_items = boundary_result.get("work")
    if (
        not isinstance(work_items, list)
        or len(work_items) != 1
        or not isinstance(work_items[0], dict)
    ):
        raise LaunchError("the model boundary lost its single work item")
    boundary_command = work_items[0].get("command")
    boundary_attachments = work_items[0].get("attachments")
    attachment, interview_command = load_request(work)
    if boundary_command != interview_command:
        raise LaunchError("the model boundary command does not match the saved intake")
    attachments = attachment if isinstance(attachment, tuple) else (attachment,)
    if boundary_attachments != [str(path) for path in attachments]:
        raise LaunchError("the model boundary attachment does not match the frozen source")
    return attachment, interview_command


def conduct_operator_turn(work: Path) -> int:
    completed = subprocess.run(
        [
            sys.executable,
            str(START_INTAKE),
            "--work",
            str(work),
            "--run-operator-turn",
        ],
        check=False,
    )
    return completed.returncode


def _projection_region_journal(
    work: Path, interview_command: list[str],
) -> Path | None:
    if not interview_command or interview_command[-1] != "--run-projection-interview":
        return None
    try:
        state = json.loads(
            (work / "intake-state.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise LaunchError(
            "the projection region state is unavailable or invalid"
        ) from error
    waiting_for = state.get("waiting_for") if isinstance(state, dict) else None
    if not isinstance(waiting_for, str):
        raise LaunchError("the projection region journal identity is missing")
    journal = (work / waiting_for).resolve()
    try:
        journal.relative_to(work.resolve())
    except ValueError as error:
        raise LaunchError("the projection region journal escapes the intake") from error
    if journal.name != "interview.jsonl":
        raise LaunchError("the projection region journal identity is invalid")
    return journal


def _projection_region_outcome_count(journal: Path) -> int:
    try:
        entries = projection_interview._read_journal(journal)
    except projection_interview.InterviewError as error:
        raise LaunchError(f"the projection region journal is invalid: {error}") from error
    return sum(entry.get("event") == "region_outcome_recorded" for entry in entries)


def _projection_relationship_outcome_count(journal: Path) -> int:
    try:
        entries = projection_interview._read_journal(journal)
    except projection_interview.InterviewError as error:
        raise LaunchError(
            f"the projection relationship journal is invalid: {error}"
        ) from error
    purposes = {
        context.get("intake_purpose")
        for entry in entries
        if entry.get("event") == "question_asked"
        for question in (entry.get("question"),)
        if isinstance(question, dict)
        for context in (question.get("context"),)
        if isinstance(context, dict)
        and isinstance(context.get("intake_purpose"), str)
    }
    if len(purposes) != 1:
        raise LaunchError(
            "the projection relationship journal has no unique bound purpose"
        )
    try:
        state, _pending, _completed = projection_interview._replay(
            entries,
            purpose=next(iter(purposes)),
            contract=projection_interview.CONTRACT,
        )
    except projection_interview.InterviewError as error:
        raise LaunchError(
            f"the projection relationship journal is not replayable: {error}"
        ) from error
    return len(state["relationships"])


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps({"ok": False, "error": "this launcher accepts no arguments"}))
        return 2
    print("Question: Intake work directory")
    print("Response format: One absolute directory path.")
    print("Example: /private/tmp/example-intake")
    print("Constraints: Use an image intake waiting for model work or one operator answer.")
    try:
        work = Path(input("Answer: ").strip()).expanduser().resolve()
    except EOFError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    return drive_work(work)


def drive_work(
    work: Path,
    *,
    projection_region_limit: int | None = None,
    projection_relationship_limit: int | None = None,
) -> int:
    """Drive one already-created intake from its current external boundary."""
    if (
        projection_region_limit is not None
        and (
            not isinstance(projection_region_limit, int)
            or isinstance(projection_region_limit, bool)
            or projection_region_limit < 1
        )
    ):
        print(json.dumps({
            "ok": False,
            "error": "projection region limit must be a positive integer",
        }, sort_keys=True))
        return 3
    if (
        projection_relationship_limit is not None
        and (
            not isinstance(projection_relationship_limit, int)
            or isinstance(projection_relationship_limit, bool)
            or projection_relationship_limit < 1
        )
    ):
        print(json.dumps({
            "ok": False,
            "error": "projection relationship limit must be a positive integer",
        }, sort_keys=True))
        return 3
    boundary_result: dict[str, object] | None = None
    request: tuple[Path | tuple[Path, ...], list[str]] | None
    try:
        request = load_request(work)
    except LaunchError:
        try:
            boundary_result = run_clarification_boundary(work)
        except LaunchError as error:
            print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
            return 3
        request = None
    executable: str | None = None
    seen_model_stages: set[str] = set()
    completed_projection_regions = 0
    completed_projection_relationships = 0
    while True:
        if request is not None:
            attachment, interview_command = request
            try:
                relationship_bound = "--projection-obligation-id" in interview_command
                if (
                    projection_relationship_limit is not None
                    and not relationship_bound
                ):
                    raise LaunchError(
                        "projection relationship limiting requires completed spatial coverage and a pending relationship obligation"
                    )
                region_journal = (
                    _projection_region_journal(work, interview_command)
                    if projection_region_limit is not None
                    else None
                )
                region_outcomes_before = (
                    _projection_region_outcome_count(region_journal)
                    if region_journal is not None
                    else None
                )
                relationship_journal = (
                    _projection_region_journal(work, interview_command)
                    if projection_relationship_limit is not None
                    else None
                )
                relationship_outcomes_before = (
                    _projection_relationship_outcome_count(
                        relationship_journal
                    )
                    if relationship_journal is not None
                    else None
                )
            except LaunchError as error:
                print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
                return 3
            if executable is None:
                executable = shutil.which("codex")
                if executable is None:
                    print(json.dumps({"ok": False, "error": "codex executable is unavailable"}, sort_keys=True))
                    return 3
            try:
                stage_key = json.dumps(
                    {
                        "progress": _model_stage_progress(work),
                        "attachments": [
                            str(path)
                            for path in (
                                attachment
                                if isinstance(attachment, tuple)
                                else (attachment,)
                            )
                        ],
                        "command": interview_command,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            except (LaunchError, OSError) as error:
                print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
                return 3
            if stage_key in seen_model_stages:
                print(json.dumps({"ok": False, "error": "the intake did not advance after a model stage"}, sort_keys=True))
                return 3
            seen_model_stages.add(stage_key)
            argv = build_codex_argv(executable, work, attachment, interview_command)
            completed = subprocess.run(argv, check=False)
            if completed.returncode != 0:
                return completed.returncode
            if region_journal is not None:
                try:
                    region_outcomes_after = _projection_region_outcome_count(
                        region_journal
                    )
                except LaunchError as error:
                    print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
                    return 3
                if region_outcomes_after != region_outcomes_before + 1:
                    print(json.dumps({
                        "ok": False,
                        "error": (
                            "the projection model stage did not preserve exactly "
                            "one new region outcome"
                        ),
                    }, sort_keys=True))
                    return 3
                completed_projection_regions += 1
                if (
                    projection_region_limit is not None
                    and completed_projection_regions == projection_region_limit
                ):
                    print(json.dumps({
                        "ok": True,
                        "status": "paused",
                        "stopped": "projection_region_limit_reached",
                        "projection_regions_completed": completed_projection_regions,
                        "work": str(work),
                    }, indent=2, sort_keys=True))
                    return 0
            if relationship_journal is not None:
                try:
                    relationship_outcomes_after = (
                        _projection_relationship_outcome_count(
                            relationship_journal
                        )
                    )
                except LaunchError as error:
                    print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
                    return 3
                relationship_delta = (
                    relationship_outcomes_after - relationship_outcomes_before
                )
                if relationship_delta not in {0, 1}:
                    print(json.dumps({
                        "ok": False,
                        "error": (
                            "one projection model stage added more than one "
                            "relationship outcome or removed an existing outcome"
                        ),
                    }, sort_keys=True))
                    return 3
                completed_projection_relationships += relationship_delta
                if (
                    projection_relationship_limit is not None
                    and completed_projection_relationships
                    == projection_relationship_limit
                ):
                    print(json.dumps({
                        "ok": True,
                        "status": "paused",
                        "stopped": "projection_relationship_limit_reached",
                        "projection_relationships_completed": (
                            completed_projection_relationships
                        ),
                        "work": str(work),
                    }, indent=2, sort_keys=True))
                    return 0
            try:
                request = load_request(work)
            except LaunchError:
                try:
                    boundary_result = run_clarification_boundary(work)
                except LaunchError as error:
                    print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
                    return 3
                request = None
            if request is not None:
                continue
        assert boundary_result is not None
        try:
            request = next_model_request(work, boundary_result)
        except LaunchError as error:
            print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
            return 3
        if request is not None:
            continue
        if boundary_result.get("boundary") == "needs_operator_answer":
            operator_returncode = conduct_operator_turn(work)
            if operator_returncode not in {0, 4}:
                return operator_returncode
            try:
                boundary_result = run_clarification_boundary(work)
            except LaunchError as error:
                print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
                return 3
            continue
        print(json.dumps(boundary_result, indent=2, sort_keys=True))
        if boundary_result.get("status") == "blocked":
            return 3
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
