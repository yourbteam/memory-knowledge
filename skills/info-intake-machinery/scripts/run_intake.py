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
    executable = shutil.which("codex")
    if executable is None:
        raise ValueError("codex executable is unavailable")
    argv = projection_runner.build_codex_argv(
        executable, work, tuple(), work_items[0]["command"]
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


def _continue_intake(
    work: Path,
    opening: str,
    purpose: str | None,
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    model_run_fn: Callable[..., object],
    projection_region_limit: int | None,
) -> int:
    result = start_intake.drive(work, opening, purpose)
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
    elif result.get("status") == "needs_operator":
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
    return projection_runner.drive_work(
        work, projection_region_limit=projection_region_limit,
    )


def run(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    model_run_fn: Callable[..., object] = subprocess.run,
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
        ("next_external_boundary", "region_limit"),
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
    return _continue_intake(
        work,
        opening,
        purpose,
        input_fn=input_fn,
        output_fn=output_fn,
        model_run_fn=model_run_fn,
        projection_region_limit=projection_region_limit,
    )


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
