#!/usr/bin/env python3
"""Start or resume one information intake through a code-controlled interview."""

from __future__ import annotations

from collections.abc import Callable
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


def _load_sibling(name: str, filename: str) -> object:
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().with_name(filename)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{filename} is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


start_intake = _load_sibling("info_intake_start", "start_intake.py")
projection_runner = _load_sibling(
    "info_intake_projection_runner", "run_projection_with_codex.py"
)
terminal_archiver = _load_sibling(
    "info_intake_terminal_archiver", "archive_terminal_run.py"
)


def _ask(
    question: str,
    response_format: str,
    constraints: str,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> str:
    while True:
        output_fn(f"Question: {question}")
        output_fn(f"Response format: {response_format}")
        output_fn(f"Constraints: {constraints}")
        try:
            answer = input_fn("Answer: ")
        except EOFError as error:
            raise ValueError("no operator answer was supplied") from error
        if answer:
            return answer
        output_fn("Invalid answer: a non-empty answer is required.")


def _choose(
    question: str,
    allowed: tuple[str, ...],
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> str:
    while True:
        answer = _ask(
            question,
            "One listed value.",
            "Choose exactly one allowed value: " + ", ".join(allowed) + ".",
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if answer in allowed:
            return answer
        output_fn(
            "Invalid answer: choose one of: " + ", ".join(allowed) + "."
        )


def _positive_integer(
    question: str,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    while True:
        answer = _ask(
            question,
            "One positive whole number.",
            "Enter a whole number greater than zero.",
            input_fn=input_fn,
            output_fn=output_fn,
        )
        try:
            value = int(answer)
        except ValueError:
            value = 0
        if str(value) == answer.strip() and value > 0:
            return value
        output_fn("Invalid answer: enter a whole number greater than zero.")


def _blocked(
    result: dict[str, object], output_fn: Callable[[str], None] = print
) -> int | None:
    if result.get("status") != "blocked":
        return None
    output_fn(json.dumps(result, indent=2, sort_keys=True))
    return 3


def _run_purpose_model(
    work: Path, result: dict[str, object], *, run_fn: Callable[..., object]
) -> int:
    work_items = result.get("work")
    if (
        result.get("status") != "waiting_for_model"
        or result.get("stopped") != "assessing_intake_purpose"
        or not isinstance(work_items, list)
        or len(work_items) != 1
        or not isinstance(work_items[0], dict)
        or not isinstance(work_items[0].get("command"), list)
    ):
        raise ValueError("the purpose stage lost its code-controlled model command")
    try:
        client = projection_runner.active_model_client()
        executable = projection_runner.resolve_model_executable(client)
    except projection_runner.LaunchError as error:
        raise ValueError(str(error)) from error
    argv = projection_runner.build_model_argv(
        client, executable, work, tuple(), work_items[0]["command"]
    )
    completed = run_fn(argv, check=False)
    return int(completed.returncode)


def _preserved_text(work: Path, name: str, *, required: bool) -> str | None:
    path = work / "sources" / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if not required:
            return None
        raise ValueError(f"the preserved intake source is unavailable: {name}")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"the preserved intake source is unreadable: {name}") from error


def _completed_intake_action(
    result: dict[str, object],
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> str | None:
    if (
        result.get("status")
        not in {"first_layer_complete", "first_layer_complete_with_preserved_gaps"}
        or result.get("stopped") != "effective_first_layer_terminal_recorded"
    ):
        return None
    return _choose(
        (
            "The intake is complete with preserved gaps. What should happen next?"
            if result.get("status") == "first_layer_complete_with_preserved_gaps"
            else "The intake is complete. What should happen next?"
        ),
        ("return_result", "add_source"),
        input_fn=input_fn,
        output_fn=output_fn,
    )


def _conduct_source_collection_interview(
    work: Path,
    opening: str,
    purpose: str,
    result: dict[str, object],
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> dict[str, object]:
    terminal_stops = {
        "first_projection_recorded",
        "first_verbatim_projection_recorded",
        "first_pdf_projection_recorded",
        "first_pdf_projection_failed",
        "first_spreadsheet_projection_recorded",
        "first_spreadsheet_projection_failed",
        "gap_resolution_applied",
    }
    if result.get("stopped") in terminal_stops:
        result = start_intake.drive(
            work, opening, purpose, begin_source_collection=True
        )
    while result.get("status") == "needs_operator":
        question = result.get("question")
        if not isinstance(question, dict) or not isinstance(question.get("id"), str):
            raise ValueError("the source collection lost its code-controlled question")
        question_id = str(question["id"])
        if question_id.startswith("source-collection-decision-"):
            action = _choose(
                str(question["asks"]),
                tuple(str(value) for value in question["allowed_values"]),
                input_fn=input_fn,
                output_fn=output_fn,
            )
            result = start_intake.drive(
                work,
                opening,
                purpose,
                source_collection_action=action,
            )
        elif question_id.startswith("source-collection-kind-"):
            kind = _choose(
                str(question["asks"]),
                tuple(str(value) for value in question["allowed_values"]),
                input_fn=input_fn,
                output_fn=output_fn,
            )
            result = start_intake.drive(
                work,
                opening,
                purpose,
                source_collection_kind=kind,
            )
        elif question_id.startswith("independent-source-"):
            answer_type = str(question.get("answer_type"))
            supplied = _ask(
                str(question["asks"]),
                "One existing local file path."
                if answer_type == "local_file"
                else "One public HTTP(S) URL.",
                "Provide only the independent source requested for this intake.",
                input_fn=input_fn,
                output_fn=output_fn,
            )
            result = (
                start_intake.drive(work, opening, purpose, Path(supplied))
                if answer_type == "local_file"
                else start_intake.drive(
                    work, opening, purpose, source_url=supplied
                )
            )
        else:
            raise ValueError(
                f"unsupported source collection question: {question_id}"
            )
        failed = _blocked(result, output_fn)
        if failed is not None:
            raise ValueError(str(result.get("why", result.get("stopped"))))
        if result.get("stopped") == "additional_source_frozen":
            result = start_intake.drive(
                work, opening, purpose, project_source=True
            )
            failed = _blocked(result, output_fn)
            if failed is not None:
                raise ValueError(str(result.get("why", result.get("stopped"))))
        if result.get("stopped") in {
            "additional_source_projection_recorded",
            "additional_spreadsheet_projection_failed",
        }:
            result = start_intake.drive(work, opening, purpose)
    return result


def _conduct_qualification_answer_interview(
    work: Path,
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    model_run_fn: Callable[..., object],
    projection_region_limit: int | None,
    projection_relationship_limit: int | None,
) -> int:
    while True:
        boundary = start_intake.run_clarification_boundary(work)
        failed = _blocked(boundary, output_fn)
        if failed is not None:
            return failed
        if boundary.get("boundary") == "qualification_answers_complete":
            output_fn(json.dumps(boundary, indent=2, sort_keys=True))
            return 0
        if (
            boundary.get("boundary") != "needs_operator_answer"
            or boundary.get("stopped") not in {
                "awaiting_qualification_clarification_answers",
                "awaiting_qualification_followup_answers",
            }
        ):
            returncode = projection_runner.drive_work(
                work,
                projection_region_limit=projection_region_limit,
                projection_relationship_limit=projection_relationship_limit,
                model_run_fn=model_run_fn,
            )
            if returncode == 4:
                continue
            return returncode
        answered = start_intake.run_operator_turn(
            work, input_fn=input_fn, output_fn=output_fn
        )
        failed = _blocked(answered, output_fn)
        if failed is not None:
            return failed
        if answered.get("stopped") == "additional_source_frozen":
            try:
                opening = (work / "sources/source-000001.txt").read_text(
                    encoding="utf-8"
                )
                purpose = (work / "sources/source-000002.txt").read_text(
                    encoding="utf-8"
                )
            except OSError as error:
                output_fn(json.dumps({
                    "status": "blocked",
                    "stopped": "qualification answer source unavailable",
                    "why": str(error),
                }, indent=2, sort_keys=True))
                return 3
            projected = start_intake.drive(
                work, opening, purpose, project_source=True
            )
            failed = _blocked(projected, output_fn)
            if failed is not None:
                return failed
            if projected.get("status") == "waiting_for_model":
                returncode = projection_runner.drive_work(
                    work,
                    projection_region_limit=projection_region_limit,
                    projection_relationship_limit=projection_relationship_limit,
                    model_run_fn=model_run_fn,
                )
                if returncode not in {0, 4}:
                    return returncode
            elif projected.get("stopped") == "additional_source_projection_recorded":
                preserved = start_intake.drive(work, opening, purpose)
                failed = _blocked(preserved, output_fn)
                if failed is not None:
                    return failed


def _resume_after_projection_boundary(
    returncode: int,
    work: Path,
    opening: str,
    purpose: str,
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    model_run_fn: Callable[..., object],
    projection_region_limit: int | None,
    projection_relationship_limit: int | None,
) -> int:
    if returncode != 4:
        return returncode
    return _continue_intake(
        work,
        opening,
        purpose,
        input_fn=input_fn,
        output_fn=output_fn,
        model_run_fn=model_run_fn,
        projection_region_limit=projection_region_limit,
        projection_relationship_limit=projection_relationship_limit,
    )


def _continue_intake(
    work: Path,
    opening: str,
    purpose: str | None,
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    model_run_fn: Callable[..., object],
    projection_region_limit: int | None,
    projection_relationship_limit: int | None,
) -> int:
    result = start_intake.drive(work, opening, purpose)
    failed = _blocked(result, output_fn)
    if failed is not None:
        return failed
    completed_action = _completed_intake_action(
        result, input_fn=input_fn, output_fn=output_fn
    )
    if completed_action == "return_result":
        output_fn(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if completed_action == "add_source":
        result = start_intake.drive(
            work, opening, purpose, begin_source_collection=True
        )
        failed = _blocked(result, output_fn)
        if failed is not None:
            return failed
    question = result.get("question")
    if (
        result.get("status") == "needs_operator"
        and isinstance(question, dict)
        and question.get("id") == "intake-purpose"
    ):
        purpose = _ask(
            str(question["asks"]),
            "One plain-language answer.",
            "Describe what the intake must make AI-readable.",
            input_fn=input_fn,
            output_fn=output_fn,
        )
        result = start_intake.drive(work, opening, purpose)
        failed = _blocked(result, output_fn)
        if failed is not None:
            return failed
    if purpose is None:
        raise ValueError("the intake purpose was not preserved")
    if (
        result.get("status") == "waiting_for_model"
        and result.get("stopped") == "assessing_intake_purpose"
    ):
        model_returncode = _run_purpose_model(
            work, result, run_fn=model_run_fn
        )
        if model_returncode != 0:
            return model_returncode
        result = start_intake.drive(work, opening, purpose)
        failed = _blocked(result, output_fn)
        if failed is not None:
            return failed
    question = result.get("question")
    if (
        result.get("status") == "needs_operator"
        and isinstance(question, dict)
        and question.get("id") == "first-source"
    ):
        source_type = _choose(
            "How will you provide the first source?",
            ("local_file", "url"),
            input_fn=input_fn,
            output_fn=output_fn,
        )
        source_value = _ask(
            str(question["asks"]),
            "One existing local file path."
            if source_type == "local_file"
            else "One public HTTP(S) URL.",
            "Provide only the source requested for this intake.",
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if source_type == "local_file":
            result = start_intake.drive(
                work, opening, purpose, Path(source_value)
            )
        else:
            result = start_intake.drive(
                work, opening, purpose, source_url=source_value
            )
        failed = _blocked(result, output_fn)
        if failed is not None:
            return failed
    elif (
        result.get("status") == "needs_operator"
        and result.get("stopped") != "awaiting_source_collection_decision"
    ):
        if result.get("stopped") in {
            "awaiting_qualification_clarification_answers",
            "awaiting_qualification_followup_answers",
        }:
            return _conduct_qualification_answer_interview(
                work,
                input_fn=input_fn,
                output_fn=output_fn,
                model_run_fn=model_run_fn,
                projection_region_limit=projection_region_limit,
                projection_relationship_limit=projection_relationship_limit,
            )
        output_fn(json.dumps(result, indent=2, sort_keys=True))
        return 4
    if (
        result.get("status") == "ready_for_projection"
        and result.get("stopped") == "first_source_frozen"
    ):
        result = start_intake.drive(
            work, opening, purpose, project_source=True
        )
        failed = _blocked(result, output_fn)
        if failed is not None:
            return failed
    if result.get("stopped") in {
        "first_projection_recorded",
        "first_verbatim_projection_recorded",
        "first_pdf_projection_recorded",
        "first_pdf_projection_failed",
        "first_spreadsheet_projection_recorded",
        "first_spreadsheet_projection_failed",
        "additional_source_projection_recorded",
        "additional_spreadsheet_projection_failed",
        "gap_resolution_applied",
        "awaiting_source_collection_decision",
    }:
        result = _conduct_source_collection_interview(
            work,
            opening,
            purpose,
            result,
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if result.get("status") == "source_collection_complete":
            result = start_intake.run_source_set_qualification(work)
            failed = _blocked(result, output_fn)
            if failed is not None:
                return failed
            result = start_intake.run_qualification_admission(work)
            failed = _blocked(result, output_fn)
            if failed is not None:
                return failed
            if result.get("route") == "clarification_required":
                result = start_intake.request_qualification_question_round(work)
                failed = _blocked(result, output_fn)
                if failed is not None:
                    return failed
                returncode = projection_runner.drive_work(
                    work,
                    projection_region_limit=projection_region_limit,
                    projection_relationship_limit=projection_relationship_limit,
                    model_run_fn=model_run_fn,
                )
                if returncode != 4:
                    return returncode
                return _conduct_qualification_answer_interview(
                    work,
                    input_fn=input_fn,
                    output_fn=output_fn,
                    model_run_fn=model_run_fn,
                    projection_region_limit=projection_region_limit,
                    projection_relationship_limit=projection_relationship_limit,
                )
            result = start_intake.run_clarification_boundary(work)
            failed = _blocked(result, output_fn)
            if failed is not None:
                return failed
            output_fn(json.dumps(result, indent=2, sort_keys=True))
            return 0
        output_fn(json.dumps(result, indent=2, sort_keys=True))
        if result.get("status") == "waiting_for_model":
            return _resume_after_projection_boundary(
                projection_runner.drive_work(
                    work,
                    projection_region_limit=projection_region_limit,
                    projection_relationship_limit=projection_relationship_limit,
                    model_run_fn=model_run_fn,
                ),
                work,
                opening,
                purpose,
                input_fn=input_fn,
                output_fn=output_fn,
                model_run_fn=model_run_fn,
                projection_region_limit=projection_region_limit,
                projection_relationship_limit=projection_relationship_limit,
            )
        return 4
    return _resume_after_projection_boundary(
        projection_runner.drive_work(
            work,
            projection_region_limit=projection_region_limit,
            projection_relationship_limit=projection_relationship_limit,
            model_run_fn=model_run_fn,
        ),
        work,
        opening,
        purpose,
        input_fn=input_fn,
        output_fn=output_fn,
        model_run_fn=model_run_fn,
        projection_region_limit=projection_region_limit,
        projection_relationship_limit=projection_relationship_limit,
    )


def run(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    model_run_fn: Callable[..., object] = subprocess.run,
    archive_root: Path = terminal_archiver.DEFAULT_ARCHIVE_ROOT,
) -> int:
    action = _choose(
        "What should this launcher do?",
        ("new", "resume"),
        input_fn=input_fn,
        output_fn=output_fn,
    )
    work = Path(
        _ask(
            "Intake work directory",
            "One directory path.",
            "Use a fresh directory for new, or the existing intake directory for resume.",
            input_fn=input_fn,
            output_fn=output_fn,
        )
    ).expanduser().resolve()
    projection_scope = _choose(
        "How far should this launcher drive visual projection?",
        (
            "next_external_boundary",
            "region_limit",
            "relationship_limit",
        ),
        input_fn=input_fn,
        output_fn=output_fn,
    )
    projection_region_limit = (
        _positive_integer(
            "How many completed visual regions should this invocation add?",
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if projection_scope == "region_limit"
        else None
    )
    projection_relationship_limit = (
        _positive_integer(
            "How many completed visual relationships should this invocation add?",
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if projection_scope == "relationship_limit"
        else None
    )
    if action == "resume":
        opening = _preserved_text(work, "source-000001.txt", required=True)
        purpose = _preserved_text(work, "source-000002.txt", required=False)
        assert opening is not None
    else:
        opening = _ask(
            "How are you opening this intake?",
            "The operator's exact opening words.",
            "A statement such as 'There is a new intake' is enough.",
            input_fn=input_fn,
            output_fn=output_fn,
        )
        purpose = None
    returncode = _continue_intake(
        work,
        opening,
        purpose,
        input_fn=input_fn,
        output_fn=output_fn,
        model_run_fn=model_run_fn,
        projection_region_limit=projection_region_limit,
        projection_relationship_limit=projection_relationship_limit,
    )
    if returncode == 0:
        archived = terminal_archiver.archive_if_terminal(
            work, archive_root=archive_root
        )
        if archived is not None:
            output_fn(json.dumps({"intake_archive": archived}, indent=2, sort_keys=True))
    return returncode


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps({"ok": False, "error": "this launcher accepts no arguments"}))
        return 2
    try:
        return run()
    except ValueError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
