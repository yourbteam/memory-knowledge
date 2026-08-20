#!/usr/bin/env python3
"""Code-controlled numbered interview contract for auto-capture."""

from __future__ import annotations

import copy
import json
import re
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import PurePosixPath
from typing import Any, TextIO

MAX_LESSONS = 3
MAX_EVIDENCE_REFS = 5

CAPTURE_OPTIONS = {
    1: "capture nothing",
    2: "capture durable lessons",
}
CONTENT_KIND_OPTIONS = {
    1: "root-cause",
    2: "corrected-approach",
    3: "repository-decision",
    4: "repository-fact",
}
EVIDENCE_KIND_OPTIONS = {
    1: "entity",
    2: "revision",
    3: "file",
}
CONTINUE_OPTIONS = {
    1: "finish",
    2: "add another",
}

_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class InterviewError(ValueError):
    """The model answer did not satisfy the displayed interview contract."""


def _menu(options: Mapping[int, str]) -> str:
    return "\n".join(f"{number}. {label}" for number, label in options.items())


SYSTEM_PROMPT = f"""\
Extract only durable WORK lessons grounded in repository evidence: a confirmed root cause,
corrected approach, repository decision, or repository fact. Never extract people, preferences,
relationships, diary/activity, transcript, conversation history, secrets, or transient status.

This is a code-controlled interview. Every finite choice is a numbered menu. Put only the selected
number in its JSON selection field; never send the option label as prose.

Capture selection options:
{_menu(CAPTURE_OPTIONS)}

Content-kind selection options:
{_menu(CONTENT_KIND_OPTIONS)}

Evidence-kind selection options:
{_menu(EVIDENCE_KIND_OPTIONS)}

Continuation selection options, used after every evidence reference and every lesson:
{_menu(CONTINUE_OPTIONS)}

Return strict JSON with exactly these top-level fields:
{{"capture_selection":1,"lessons":[]}}
or
{{"capture_selection":2,"lessons":[{{
  "title":"<=80 chars",
  "body":"concise operational lesson and why",
  "content_kind_selection":1,
  "evidence_refs":[{{
    "kind_selection":3,
    "file_path":"repo/relative/path",
    "revision_commit":"40-hex",
    "continue_selection":1
  }}],
  "continue_selection":1
}}]}}

Evidence selection 1 requires entity_key as a UUID. Selection 2 requires revision_commit.
Selection 3 requires file_path plus revision_commit. For each non-final reference or lesson choose
2 (add another); for the final one choose 1 (finish). Return 0 to {MAX_LESSONS} lessons and at most
{MAX_EVIDENCE_REFS} evidence references per lesson. Do not add canonical option labels or fields.
"""

INTERVIEW_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["capture_selection", "lessons"],
    "properties": {
        "capture_selection": {"type": "integer", "enum": sorted(CAPTURE_OPTIONS)},
        "lessons": {
            "type": "array",
            "maxItems": MAX_LESSONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title", "body", "content_kind_selection", "evidence_refs",
                    "continue_selection",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "content_kind_selection": {
                        "type": "integer", "enum": sorted(CONTENT_KIND_OPTIONS),
                    },
                    "evidence_refs": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_EVIDENCE_REFS,
                        "items": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "kind_selection", "continue_selection", "entity_key",
                                    ],
                                    "properties": {
                                        "kind_selection": {"type": "integer", "enum": [1]},
                                        "continue_selection": {
                                            "type": "integer", "enum": sorted(CONTINUE_OPTIONS),
                                        },
                                        "entity_key": {"type": "string"},
                                    },
                                },
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "kind_selection", "continue_selection", "revision_commit",
                                    ],
                                    "properties": {
                                        "kind_selection": {"type": "integer", "enum": [2]},
                                        "continue_selection": {
                                            "type": "integer", "enum": sorted(CONTINUE_OPTIONS),
                                        },
                                        "revision_commit": {"type": "string"},
                                    },
                                },
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "kind_selection", "continue_selection", "file_path",
                                        "revision_commit",
                                    ],
                                    "properties": {
                                        "kind_selection": {"type": "integer", "enum": [3]},
                                        "continue_selection": {
                                            "type": "integer", "enum": sorted(CONTINUE_OPTIONS),
                                        },
                                        "file_path": {"type": "string"},
                                        "revision_commit": {"type": "string"},
                                    },
                                },
                            ],
                        },
                    },
                    "continue_selection": {
                        "type": "integer", "enum": sorted(CONTINUE_OPTIONS),
                    },
                },
            },
        },
    },
}


def user_prompt(transcript_text: str) -> str:
    return "Session transcript to assess:\n" + transcript_text


def _require_object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InterviewError(f"{where} returned {type(value).__name__}; return one JSON object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise InterviewError(
            f"{where} fields are invalid; missing={missing}; extra={extra}; "
            f"return exactly {sorted(expected)}"
        )


def _require_selection(
    value: Any, options: Mapping[int, str], where: str,
) -> int:
    if type(value) is not int or value not in options:
        raise InterviewError(
            f"{where} returned {value!r}; choose one selection number: {_menu(options)}"
        )
    return value


def _require_text(value: Any, where: str, *, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InterviewError(f"{where} returned {value!r}; provide non-empty text")
    normalized = value.strip()
    if maximum is not None and len(normalized) > maximum:
        raise InterviewError(
            f"{where} has {len(normalized)} characters; use at most {maximum}"
        )
    return normalized


def _require_commit(value: Any, where: str) -> str:
    commit = _require_text(value, where)
    if not _COMMIT_RE.fullmatch(commit):
        raise InterviewError(f"{where} returned {value!r}; provide one 40-hex commit")
    return commit.lower()


def _require_continuation(value: Any, *, final: bool, where: str) -> None:
    selection = _require_selection(value, CONTINUE_OPTIONS, where)
    expected = 1 if final else 2
    if selection != expected:
        raise InterviewError(
            f"{where} returned {selection}; choose {expected} "
            f"({'finish' if final else 'add another'}) for this list position"
        )


def _parse_evidence_ref(raw: Any, *, lesson_index: int, ref_index: int, final: bool) -> dict[str, str]:
    where = f"lesson {lesson_index} evidence {ref_index}"
    item = _require_object(raw, where)
    kind_selection = _require_selection(
        item.get("kind_selection"), EVIDENCE_KIND_OPTIONS, f"{where} kind selection",
    )
    common = {"kind_selection", "continue_selection"}
    kind = EVIDENCE_KIND_OPTIONS[kind_selection]
    if kind == "entity":
        expected = common | {"entity_key"}
    elif kind == "revision":
        expected = common | {"revision_commit"}
    else:
        expected = common | {"file_path", "revision_commit"}
    _require_exact_keys(item, expected, where)
    _require_continuation(
        item["continue_selection"], final=final, where=f"{where} continuation selection",
    )

    if kind == "entity":
        entity_key = _require_text(item["entity_key"], f"{where} entity key")
        try:
            uuid.UUID(entity_key)
        except ValueError as exc:
            raise InterviewError(
                f"{where} entity key returned {entity_key!r}; provide one UUID"
            ) from exc
        return {"kind": kind, "entity_key": entity_key}

    commit = _require_commit(item["revision_commit"], f"{where} revision commit")
    if kind == "revision":
        return {"kind": kind, "revision_commit": commit}

    file_path = _require_text(item["file_path"], f"{where} file path")
    path = PurePosixPath(file_path)
    if path.is_absolute() or ".." in path.parts:
        raise InterviewError(
            f"{where} file path returned {file_path!r}; provide one repository-relative path"
        )
    return {
        "kind": kind,
        "file_path": path.as_posix(),
        "revision_commit": commit,
    }


def parse_interview(raw: Any) -> list[dict[str, Any]]:
    envelope = _require_object(raw, "interview answer")
    _require_exact_keys(envelope, {"capture_selection", "lessons"}, "interview answer")
    capture_selection = _require_selection(
        envelope["capture_selection"], CAPTURE_OPTIONS, "capture selection",
    )
    lessons_raw = envelope["lessons"]
    if not isinstance(lessons_raw, list):
        raise InterviewError("lessons returned a non-list; provide one JSON list")
    if capture_selection == 1:
        if lessons_raw:
            raise InterviewError(
                "capture selection returned 1 (capture nothing) but lessons were supplied; "
                "return an empty lessons list"
            )
        return []
    if not 1 <= len(lessons_raw) <= MAX_LESSONS:
        raise InterviewError(
            f"capture selection returned 2 but lessons count is {len(lessons_raw)}; "
            f"provide 1 to {MAX_LESSONS} lessons"
        )

    lessons: list[dict[str, Any]] = []
    lesson_keys = {
        "title", "body", "content_kind_selection", "evidence_refs", "continue_selection",
    }
    for lesson_index, raw_lesson in enumerate(lessons_raw, start=1):
        where = f"lesson {lesson_index}"
        lesson = _require_object(raw_lesson, where)
        _require_exact_keys(lesson, lesson_keys, where)
        content_selection = _require_selection(
            lesson["content_kind_selection"],
            CONTENT_KIND_OPTIONS,
            f"{where} content-kind selection",
        )
        refs_raw = lesson["evidence_refs"]
        if not isinstance(refs_raw, list) or not 1 <= len(refs_raw) <= MAX_EVIDENCE_REFS:
            count = len(refs_raw) if isinstance(refs_raw, list) else "non-list"
            raise InterviewError(
                f"{where} evidence count is {count}; provide 1 to {MAX_EVIDENCE_REFS} references"
            )
        refs = [
            _parse_evidence_ref(
                raw_ref,
                lesson_index=lesson_index,
                ref_index=ref_index,
                final=ref_index == len(refs_raw),
            )
            for ref_index, raw_ref in enumerate(refs_raw, start=1)
        ]
        _require_continuation(
            lesson["continue_selection"],
            final=lesson_index == len(lessons_raw),
            where=f"{where} continuation selection",
        )
        lessons.append({
            "title": _require_text(lesson["title"], f"{where} title", maximum=80),
            "body": _require_text(lesson["body"], f"{where} body"),
            "content_kind": CONTENT_KIND_OPTIONS[content_selection],
            "evidence_refs": refs,
        })
    return lessons


def _ask_text(
    prompt: str,
    *,
    read: Callable[[str], str],
    output: TextIO,
) -> str:
    while True:
        value = read(f"{prompt}: ").strip()
        if value:
            return value
        print("A non-empty value is required.", file=output)


def _ask_selection(
    prompt: str,
    options: Mapping[int, str],
    *,
    read: Callable[[str], str],
    output: TextIO,
) -> int:
    while True:
        print(prompt, file=output)
        print(_menu(options), file=output)
        raw = read("Selection number: ").strip()
        try:
            selection = int(raw)
        except ValueError:
            selection = -1
        if selection in options and raw == str(selection):
            return selection
        print(
            f"Invalid selection {raw!r}. Enter one displayed selection number; prose labels "
            "are not accepted.",
            file=output,
        )


def collect_interactive(
    *,
    read: Callable[[str], str] = input,
    output: TextIO = sys.stdout,
) -> tuple[str, list[dict[str, Any]]]:
    """Collect one model-driven capture through numbered terminal menus."""
    repository_key = _ask_text("Repository key", read=read, output=output)
    capture_selection = _ask_selection(
        "Choose whether this session has durable lessons to capture:",
        CAPTURE_OPTIONS,
        read=read,
        output=output,
    )
    if capture_selection == 1:
        return repository_key, parse_interview({"capture_selection": 1, "lessons": []})

    raw_lessons: list[dict[str, Any]] = []
    while True:
        lesson_number = len(raw_lessons) + 1
        lesson: dict[str, Any] = {
            "title": _ask_text(
                f"Lesson {lesson_number} title (80 characters maximum)",
                read=read,
                output=output,
            ),
            "body": _ask_text(
                f"Lesson {lesson_number} operational lesson and why",
                read=read,
                output=output,
            ),
            "content_kind_selection": _ask_selection(
                f"Choose lesson {lesson_number} content kind:",
                CONTENT_KIND_OPTIONS,
                read=read,
                output=output,
            ),
            "evidence_refs": [],
        }
        refs: list[dict[str, Any]] = lesson["evidence_refs"]
        while True:
            ref_number = len(refs) + 1
            kind_selection = _ask_selection(
                f"Choose lesson {lesson_number} evidence {ref_number} kind:",
                EVIDENCE_KIND_OPTIONS,
                read=read,
                output=output,
            )
            ref: dict[str, Any] = {"kind_selection": kind_selection}
            if kind_selection == 1:
                ref["entity_key"] = _ask_text(
                    "Evidence entity UUID", read=read, output=output,
                )
            elif kind_selection == 2:
                ref["revision_commit"] = _ask_text(
                    "Evidence 40-hex revision commit", read=read, output=output,
                )
            else:
                ref["file_path"] = _ask_text(
                    "Evidence repository-relative file path", read=read, output=output,
                )
                ref["revision_commit"] = _ask_text(
                    "Evidence 40-hex revision commit", read=read, output=output,
                )
            while True:
                continuation = _ask_selection(
                    f"After lesson {lesson_number} evidence {ref_number}:",
                    CONTINUE_OPTIONS,
                    read=read,
                    output=output,
                )
                if continuation == 2 and ref_number == MAX_EVIDENCE_REFS:
                    print(
                        f"At most {MAX_EVIDENCE_REFS} evidence references are allowed; choose 1.",
                        file=output,
                    )
                    continue
                ref["continue_selection"] = continuation
                break
            refs.append(ref)
            if continuation == 1:
                break

        while True:
            continuation = _ask_selection(
                f"After lesson {lesson_number}:",
                CONTINUE_OPTIONS,
                read=read,
                output=output,
            )
            if continuation == 2 and lesson_number == MAX_LESSONS:
                print(
                    f"At most {MAX_LESSONS} lessons are allowed; choose 1.",
                    file=output,
                )
                continue
            lesson["continue_selection"] = continuation
            break
        raw_lessons.append(lesson)
        if continuation == 1:
            break

    return repository_key, parse_interview({
        "capture_selection": capture_selection,
        "lessons": raw_lessons,
    })


def _valid_probe_answer() -> dict[str, Any]:
    return {
        "capture_selection": 2,
        "lessons": [
            {
                "title": "Isolate Git dry-run writes",
                "body": "A temporary index alone still writes objects; isolate both stores.",
                "content_kind_selection": 2,
                "evidence_refs": [
                    {
                        "kind_selection": 3,
                        "file_path": "scripts/minimal_git_publish.py",
                        "revision_commit": "a" * 40,
                        "continue_selection": 2,
                    },
                    {
                        "kind_selection": 2,
                        "revision_commit": "b" * 40,
                        "continue_selection": 1,
                    },
                ],
                "continue_selection": 2,
            },
            {
                "title": "Use numbered selections",
                "body": "Code should map a selected number instead of accepting prose labels.",
                "content_kind_selection": 3,
                "evidence_refs": [
                    {
                        "kind_selection": 1,
                        "entity_key": "12345678-1234-5678-1234-567812345678",
                        "continue_selection": 1,
                    }
                ],
                "continue_selection": 1,
            },
        ],
    }


def run_probe() -> dict[str, Any]:
    valid = _valid_probe_answer()
    normalized = parse_interview(valid)
    mutations = []
    for label, mutate in (
        ("capture", lambda item: item.__setitem__("capture_selection", "capture durable lessons")),
        ("content-kind", lambda item: item["lessons"][0].__setitem__("content_kind_selection", "corrected-approach")),
        ("evidence-kind", lambda item: item["lessons"][0]["evidence_refs"][0].__setitem__("kind_selection", "file")),
        ("evidence-continuation", lambda item: item["lessons"][0]["evidence_refs"][0].__setitem__("continue_selection", "add another")),
        ("lesson-continuation", lambda item: item["lessons"][0].__setitem__("continue_selection", "add another")),
    ):
        candidate = copy.deepcopy(valid)
        mutate(candidate)
        try:
            parse_interview(candidate)
        except InterviewError:
            mutations.append(label)
        else:
            raise AssertionError(f"probe accepted prose selection: {label}")
    return {
        "ok": True,
        "numbered_selection_contexts": 5,
        "prose_rejections": mutations,
        "normalized_lessons": len(normalized),
        "zero_capture": parse_interview({"capture_selection": 1, "lessons": []}) == [],
    }


def main() -> int:
    try:
        result = run_probe()
    except (AssertionError, InterviewError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
