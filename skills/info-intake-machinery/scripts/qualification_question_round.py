#!/usr/bin/env python3
"""Form one evidence-bound operator question for every admitted obligation."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1
ANSWER_TYPES = ("operator_text", "local_file", "url")
OBLIGATION_FIELDS = {
    "id",
    "qualification_event_sha256",
    "source_position",
    "gap_position",
    "source_id",
    "projection_id",
    "projection_sha256",
    "method",
    "qualification",
    "unit",
    "reason",
    "gap_sha256",
}


class QuestionRoundError(ValueError):
    """The admission, interview, or prepared question round is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: object) -> str:
    content = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(content).hexdigest()


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def bind_contexts(admission: dict[str, object]) -> list[dict[str, object]]:
    event_sha256 = admission.get("qualification_event_sha256")
    obligations = admission.get("clarification_obligations")
    if (
        admission.get("event") != "qualification_admission_completed"
        or admission.get("route") != "clarification_required"
    ):
        raise QuestionRoundError(
            "qualification admission must be the completed clarification_required event"
        )
    if not _is_digest(event_sha256):
        raise QuestionRoundError(
            f"qualification event digest {event_sha256!r} is invalid; preserve its exact 64-character ledger digest"
        )
    if not isinstance(obligations, list) or not obligations:
        raise QuestionRoundError(
            f"clarification obligations {obligations!r} are invalid; preserve at least one exact admitted obligation"
        )
    contexts: list[dict[str, object]] = []
    identities: set[str] = set()
    for position, obligation in enumerate(obligations, 1):
        if not isinstance(obligation, dict) or set(obligation) != OBLIGATION_FIELDS:
            received = sorted(obligation) if isinstance(obligation, dict) else obligation
            raise QuestionRoundError(
                f"obligation {position} fields {received!r} are invalid; preserve exactly {sorted(OBLIGATION_FIELDS)!r}"
            )
        identity = obligation.get("id")
        if not isinstance(identity, str) or not identity or identity in identities:
            raise QuestionRoundError(
                f"obligation {position} id {identity!r} is invalid; preserve one nonempty unique identity"
            )
        identities.add(identity)
        if obligation.get("qualification_event_sha256") != event_sha256:
            raise QuestionRoundError(
                f"obligation {identity!r} qualification digest {obligation.get('qualification_event_sha256')!r} changed; preserve {event_sha256!r}"
            )
        missing = [
            field
            for field in ("source_id", "qualification", "unit", "reason", "gap_sha256")
            if not isinstance(obligation.get(field), str) or not obligation[field]
        ]
        if missing:
            raise QuestionRoundError(
                f"obligation {identity!r} has empty evidence fields {missing!r}; preserve their admitted nonempty values"
            )
        contexts.append({
            "obligation_id": identity,
            "position": position,
            "evidence": obligation,
            "evidence_sha256": _digest(obligation),
        })
    return contexts


def _entry(
    sequence: int,
    event: str,
    payload: dict[str, object],
    previous: str | None,
) -> dict[str, object]:
    result = {
        "sequence": sequence,
        "event": event,
        "previous_entry_sha256": previous,
        **payload,
    }
    result["entry_sha256"] = _digest(result)
    return result


def _read_journal(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    previous: str | None = None
    for sequence, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise QuestionRoundError(
                f"interview entry {sequence} is not JSON; restore the immutable recorded entry"
            ) from error
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(raw)
        raw["entry_sha256"] = claimed
        if raw.get("sequence") != sequence:
            raise QuestionRoundError(
                f"interview entry {sequence} declares sequence {raw.get('sequence')!r}; restore sequence {sequence}"
            )
        if raw.get("previous_entry_sha256") != previous:
            raise QuestionRoundError(
                f"interview entry {sequence} predecessor {raw.get('previous_entry_sha256')!r} changed; restore {previous!r}"
            )
        if claimed != actual:
            raise QuestionRoundError(
                f"interview entry {sequence} digest {claimed!r} changed; restore {actual!r}"
            )
        previous = str(claimed)
        entries.append(raw)
    return entries


def _append(path: Path, event: str, payload: dict[str, object]) -> None:
    entries = _read_journal(path)
    row = _entry(
        len(entries) + 1,
        event,
        payload,
        str(entries[-1]["entry_sha256"]) if entries else None,
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")


def _question(
    state: dict[str, list[str]], contexts: list[dict[str, object]]
) -> dict[str, object] | None:
    index = len(state["questions"])
    if index >= len(contexts):
        return None
    context = contexts[index]
    if len(state["answer_types"]) == index:
        return {
            "id": f"qualification_answer_type_{index + 1:06d}",
            "prompt": "What must the operator provide for this exact clarification obligation?",
            "type": "enum",
            "choices": list(ANSWER_TYPES),
            "required": True,
            "obligation_context": context,
        }
    return {
        "id": f"qualification_operator_question_{index + 1:06d}",
        "prompt": "What one focused question should the operator answer to supply the information missing from this exact obligation?",
        "type": "string",
        "required": True,
        "obligation_context": context,
    }


def _parse(question: dict[str, object], raw: str) -> tuple[str | None, str | None]:
    value = raw.strip()
    if not value or "\n" in value or "\r" in value:
        return None, f"{question['id']}: received {raw!r}; provide one nonempty answer field"
    choices = question.get("choices")
    if isinstance(choices, list) and value not in choices:
        return None, (
            f"{question['id']}: received {value!r}; choose exactly one of "
            + ", ".join(str(choice) for choice in choices)
        )
    if str(question["id"]).startswith("qualification_operator_question_") and (
        len(value) > 300 or value.count("?") != 1 or not value.endswith("?")
    ):
        return None, (
            f"{question['id']}: received {value!r}; provide one focused question of at most 300 characters ending in exactly one ?"
        )
    return value, None


def _replay(
    entries: list[dict[str, object]], contexts: list[dict[str, object]]
) -> tuple[dict[str, list[str]], dict[str, object] | None, bool]:
    state: dict[str, list[str]] = {"answer_types": [], "questions": []}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(state, contexts)
            if pending is not None or entry.get("question") != expected:
                raise QuestionRoundError(
                    f"interview entry {entry['sequence']} question changed; restore the exact code-generated question"
                )
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise QuestionRoundError(
                    f"interview entry {entry['sequence']} answer is unbound; bind it to the pending question {pending!r}"
                )
            if entry.get("accepted"):
                if str(pending["id"]).startswith("qualification_answer_type_"):
                    state["answer_types"].append(str(entry["parsed"]))
                else:
                    state["questions"].append(str(entry["parsed"]))
            pending = None
        elif entry["event"] == "qualification_question_round_completed":
            if pending is not None or _question(state, contexts) is not None:
                raise QuestionRoundError(
                    f"interview entry {entry['sequence']} completed early; answer every code-generated obligation question first"
                )
            completed = True
        else:
            raise QuestionRoundError(
                f"interview entry {entry['sequence']} event {entry['event']!r} is unsupported; preserve only generated interview events"
            )
    return state, pending, completed


def _result(
    admission_sha256: str,
    contexts: list[dict[str, object]],
    state: dict[str, list[str]],
) -> dict[str, object]:
    questions = []
    for index, context in enumerate(contexts):
        questions.append({
            "id": f"qualification-clarification-answer-{index + 1:06d}",
            "asks": state["questions"][index] if index < len(state["questions"]) else "",
            "answer_type": state["answer_types"][index] if index < len(state["answer_types"]) else "",
            "answers_obligation": context["evidence"],
            "evidence_sha256": context["evidence_sha256"],
        })
    return {
        "schema_version": CONTRACT,
        "qualification_admission_sha256": admission_sha256,
        "questions": questions,
    }


def _prompt(
    question: dict[str, object], purpose: str
) -> str:
    context = question["obligation_context"]
    lines = [
        f"Intake purpose: {purpose}",
        "Immutable clarification obligation: " + json.dumps(context, sort_keys=True),
        f"Question: {question['prompt']}",
    ]
    choices = question.get("choices")
    if isinstance(choices, list):
        lines.extend(("Answer type: enum", "Allowed values: " + ", ".join(choices)))
    else:
        lines.append("Answer type: string")
    lines.append("Answer: ")
    return "\n".join(lines)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise QuestionRoundError(
            "model input ended while a generated question was pending; answer the displayed question"
        )
    return value.rstrip("\n")


def run(
    round_dir: Path,
    *,
    admission: dict[str, object],
    purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    contexts = bind_contexts(admission)
    admission_sha256 = admission.get("entry_sha256")
    if not _is_digest(admission_sha256):
        raise QuestionRoundError(
            f"qualification admission digest {admission_sha256!r} is invalid; preserve its exact ledger identity"
        )
    round_dir.mkdir(parents=True, exist_ok=True)
    journal_path = round_dir / "interview.jsonl"
    result_path = round_dir / "question-round.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _replay(_read_journal(journal_path), contexts)
        result = _result(str(admission_sha256), contexts, state)
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
            if result_path.read_bytes() != result_bytes:
                raise QuestionRoundError(
                    "prepared question-round bytes changed; restore the immutable completed result"
                )
            return result
        question = pending or _question(state, contexts)
        if question is None:
            _append(
                journal_path,
                "qualification_question_round_completed",
                {"result_sha256": _digest(result_bytes), "question_count": len(contexts)},
            )
            result_path.write_bytes(result_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, purpose))
        parsed, error = _parse(question, raw)
        _append(journal_path, "answer_recorded", {
            "question_id": question["id"],
            "raw": raw,
            "accepted": error is None,
            "parsed": parsed,
            "error": error,
        })
        if error:
            write(f"Invalid answer: {error}.")


def validate(
    round_dir: Path,
    *,
    admission: dict[str, object],
    purpose: str,
) -> tuple[dict[str, object], str, str]:
    result = run(
        round_dir,
        admission=admission,
        purpose=purpose,
        input_fn=lambda _prompt: (_ for _ in ()).throw(
            QuestionRoundError(
                "question round is incomplete; finish every generated interview answer"
            )
        ),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((round_dir / "interview.jsonl").read_bytes()),
        _digest((round_dir / "question-round.json").read_bytes()),
    )
