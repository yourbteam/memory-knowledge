#!/usr/bin/env python3
"""Formulate one auditable operator question round for frozen projection gaps."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1
ROUND_CONTRACT = 4
SUPPORTED_ROUND_CONTRACTS = {1, 2, 3, ROUND_CONTRACT}
LEGACY_ANSWER_TYPES = ("operator_text", "local_file")
ANSWER_TYPES = (*LEGACY_ANSWER_TYPES, "url")
GAP_BINDING_FIELDS = (
    "projection_sha256",
    "collection",
    "kind",
    "id",
    "record_sha256",
    "page",
    "item_id",
    "page_projection_path",
    "page_projection_sha256",
    "render_path",
    "render_sha256",
)


class ClarificationError(ValueError):
    """The clarification journal or its frozen projection is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_projection(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        projection = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise ClarificationError("clarification-projection-unavailable") from error
    if _digest(content) != expected_sha256 or not isinstance(projection, dict):
        raise ClarificationError("clarification-projection-changed")
    return projection


def _matching_element_ids(record: dict[str, Any]) -> list[str]:
    binding = record.get("binding_issue")
    if not isinstance(binding, dict) or "matching_element_ids" not in binding:
        return []
    values = binding.get("matching_element_ids")
    if (
        not isinstance(values, list)
        or len(values) < 2
        or any(not isinstance(value, str) or not value for value in values)
        or len(set(values)) != len(values)
    ):
        raise ClarificationError("clarification-gap-candidate-identities-invalid")
    return list(values)


def select_gaps(
    projection: dict[str, Any], projection_sha256: str
) -> list[dict[str, object]]:
    """Return every explicit gap in canonical projection order."""
    if "gap_inventory" in projection:
        inventory = projection.get("gap_inventory")
        if not isinstance(inventory, list):
            raise ClarificationError("clarification-gap-inventory-invalid")
        selected: list[dict[str, object]] = []
        previous_page = 0
        identities: set[str] = set()
        for item in inventory:
            if not isinstance(item, dict):
                raise ClarificationError("clarification-gap-inventory-invalid")
            page = item.get("page")
            identity = item.get("id")
            record = item.get("record")
            if (
                not isinstance(page, int)
                or page < 1
                or page < previous_page
                or not isinstance(identity, str)
                or not identity
                or identity in identities
                or not isinstance(record, dict)
                or record.get("status") != "gap"
                or record.get("id") != item.get("item_id")
                or item.get("record_sha256") != _digest(_canonical(record))
                or not isinstance(item.get("recorded_context"), list)
            ):
                raise ClarificationError("clarification-gap-inventory-invalid")
            for field in (
                "collection",
                "kind",
                "item_id",
                "page_projection_path",
                "page_projection_sha256",
                "render_path",
                "render_sha256",
            ):
                if not isinstance(item.get(field), str) or not item[field]:
                    raise ClarificationError("clarification-gap-inventory-invalid")
            previous_page = page
            identities.add(identity)
            selected.append({"projection_sha256": projection_sha256, **item})
        return selected
    gaps: list[dict[str, object]] = []
    for collection, kind in (
        ("scan_regions", "scan_region"),
        ("elements", "element"),
        ("relationships", "relationship"),
    ):
        items = projection.get(collection, [])
        if not isinstance(items, list):
            raise ClarificationError(f"clarification-{collection}-invalid")
        for item in items:
            if not isinstance(item, dict):
                raise ClarificationError(f"clarification-{collection}-invalid")
            if item.get("status") != "gap":
                continue
            gap_id = item.get("id")
            reason = item.get("gap_reason")
            if not isinstance(gap_id, str) or not gap_id or not isinstance(reason, str) or not reason:
                raise ClarificationError("clarification-gap-identity-invalid")
            context: list[dict[str, Any]] = []
            if collection == "relationships":
                participant_ids = {item.get("from_id"), item.get("to_id")}
                candidate_ids = _matching_element_ids(item)
                participant_ids.update(candidate_ids)
                context = [
                    element for element in projection.get("elements", [])
                    if isinstance(element, dict) and element.get("id") in participant_ids
                ]
                recorded_candidate_ids = {
                    element.get("id") for element in context
                    if element.get("id") in candidate_ids
                }
                if recorded_candidate_ids != set(candidate_ids):
                    raise ClarificationError(
                        "clarification-gap-candidate-context-missing"
                    )
            gaps.append({
                "projection_sha256": projection_sha256,
                "collection": collection,
                "kind": kind,
                "id": gap_id,
                "record_sha256": _digest(_canonical(item)),
                "record": item,
                "recorded_context": context,
            })
    return gaps


def gap_binding(gap: dict[str, object]) -> dict[str, object]:
    """Return the immutable identity a human answer must resolve."""
    return {field: gap[field] for field in GAP_BINDING_FIELDS if field in gap}


def require_gaps(
    projection: dict[str, Any], projection_sha256: str
) -> list[dict[str, object]]:
    """Return current gaps for a question-producing path, refusing an empty set."""
    gaps = select_gaps(projection, projection_sha256)
    if not gaps:
        raise ClarificationError("clarification-no-gap")
    return gaps


def select_gap(projection: dict[str, Any], projection_sha256: str) -> dict[str, object]:
    """Select the first explicit gap for legacy single-gap intakes."""
    return require_gaps(projection, projection_sha256)[0]


def _entry(sequence: int, event: str, payload: dict[str, object], previous: str | None) -> dict[str, object]:
    result: dict[str, object] = {
        "sequence": sequence,
        "event": event,
        "previous_entry_sha256": previous,
        **payload,
    }
    result["entry_sha256"] = _digest(_canonical(result))
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
            raise ClarificationError(f"clarification-journal-json-invalid:{sequence}") from error
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(_canonical(raw))
        raw["entry_sha256"] = claimed
        if raw.get("sequence") != sequence or raw.get("previous_entry_sha256") != previous:
            raise ClarificationError(f"clarification-journal-chain-invalid:{sequence}")
        if claimed != actual:
            raise ClarificationError(f"clarification-journal-entry-changed:{sequence}")
        previous = str(claimed)
        entries.append(raw)
    return entries


def _append(path: Path, event: str, payload: dict[str, object]) -> None:
    entries = _read_journal(path)
    result = _entry(
        len(entries) + 1,
        event,
        payload,
        str(entries[-1]["entry_sha256"]) if entries else None,
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")


def _question(state: dict[str, str], gap: dict[str, object]) -> dict[str, object] | None:
    if not state["model"]:
        return {
            "id": "questioner_model",
            "prompt": "Which fresh model is formulating the operator clarification?",
            "type": "string",
            "required": True,
        }
    if not state["harness"]:
        return {
            "id": "questioner_harness",
            "prompt": "Which harness is running the clarification interview?",
            "type": "string",
            "required": True,
        }
    if not state["question"]:
        return {
            "id": "operator_question",
            "prompt": "What one focused question should the operator answer to supply the information missing from this exact gap?",
            "type": "string",
            "required": True,
            "bound_gap": gap,
        }
    return None


def _parse(question: dict[str, object], raw: str) -> tuple[str | None, str | None]:
    value = raw.strip()
    if not value or "\n" in value or "\r" in value:
        return None, f"{question['id']}: answer one non-empty field at a time"
    choices = question.get("choices")
    if isinstance(choices, list) and value not in choices:
        return None, f"{question['id']}: choose one of: {', '.join(choices)}"
    if str(question["id"]).startswith("operator_question") and (
        len(value) > 300 or value.count("?") != 1 or not value.endswith("?")
    ):
        return None, "operator_question: provide exactly one focused question ending in ?"
    return value, None


def _replay(
    entries: list[dict[str, object]], gap: dict[str, object]
) -> tuple[dict[str, str], dict[str, object] | None, bool]:
    state = {"model": "", "harness": "", "question": ""}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(state, gap)
            if pending is not None or expected != entry.get("question"):
                raise ClarificationError(f"clarification-question-invalid:{entry['sequence']}")
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise ClarificationError(f"clarification-answer-unbound:{entry['sequence']}")
            if entry.get("accepted"):
                field = {
                    "questioner_model": "model",
                    "questioner_harness": "harness",
                    "operator_question": "question",
                }[str(pending["id"])]
                state[field] = str(entry["parsed"])
            pending = None
        elif entry["event"] == "clarification_completed":
            if pending is not None or _question(state, gap) is not None:
                raise ClarificationError(f"clarification-completion-invalid:{entry['sequence']}")
            completed = True
        else:
            raise ClarificationError(f"clarification-event-unsupported:{entry['sequence']}")
    return state, pending, completed


def _prompt(question: dict[str, object], purpose: str, gap: dict[str, object]) -> str:
    lines = [
        f"Intake purpose: {purpose}",
        "Frozen unresolved gap: " + json.dumps(gap, sort_keys=True),
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
        raise ClarificationError("clarification-input-ended")
    return value.rstrip("\n")


def run(
    attempt_dir: Path,
    *,
    projection_path: Path,
    projection_sha256: str,
    purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    projection = _load_projection(projection_path, projection_sha256)
    gap = select_gap(projection, projection_sha256)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    result_path = attempt_dir / "clarification.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _replay(_read_journal(journal_path), gap)
        result = {
            "schema_version": CONTRACT,
            "projection_sha256": projection_sha256,
            "gap": gap,
            "questioner": {"model": state["model"], "harness": state["harness"]},
            "question": {
                "id": "gap-clarification-answer-000001",
                "asks": state["question"],
                "answers_gap": gap_binding(gap),
            },
        }
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
            if result_path.read_bytes() != result_bytes:
                raise ClarificationError("clarification-result-changed")
            return result
        question = pending or _question(state, gap)
        if question is None:
            _append(journal_path, "clarification_completed", {"result_sha256": _digest(result_bytes)})
            result_path.write_bytes(result_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, purpose, gap))
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
    attempt_dir: Path,
    *,
    projection_path: Path,
    projection_sha256: str,
    purpose: str,
) -> tuple[dict[str, object], str, str]:
    result = run(
        attempt_dir,
        projection_path=projection_path,
        projection_sha256=projection_sha256,
        purpose=purpose,
        input_fn=lambda _prompt: (_ for _ in ()).throw(
            ClarificationError("clarification-not-complete")
        ),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((attempt_dir / "interview.jsonl").read_bytes()),
        _digest((attempt_dir / "clarification.json").read_bytes()),
    )


def _candidate_question_context(
    gap: dict[str, object],
) -> dict[str, Any] | None:
    record = gap.get("record")
    if not isinstance(record, dict):
        return None
    candidate_ids = _matching_element_ids(record)
    if not candidate_ids:
        return None
    binding = record.get("binding_issue")
    participant = binding.get("participant") if isinstance(binding, dict) else None
    if not isinstance(participant, str) or not participant:
        raise ClarificationError("clarification-gap-candidate-participant-invalid")
    context = gap.get("recorded_context")
    if not isinstance(context, list):
        raise ClarificationError("clarification-gap-candidate-context-missing")
    by_id: dict[str, dict[str, Any]] = {}
    for element in context:
        if not isinstance(element, dict):
            raise ClarificationError("clarification-gap-candidate-context-invalid")
        element_id = element.get("id")
        if element_id in candidate_ids:
            if element_id in by_id:
                raise ClarificationError(
                    "clarification-gap-candidate-context-invalid"
                )
            by_id[str(element_id)] = element
    if set(by_id) != set(candidate_ids):
        raise ClarificationError("clarification-gap-candidate-context-missing")
    elements = [by_id[element_id] for element_id in candidate_ids]
    for element in elements:
        content = element.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ClarificationError("clarification-gap-candidate-content-invalid")
    return {
        "ids": candidate_ids,
        "participant": participant,
        "elements": elements,
    }


def _candidate_operator_question(
    gap: dict[str, object], selected_id: str
) -> str:
    context = _candidate_question_context(gap)
    if context is None or selected_id not in context["ids"]:
        raise ClarificationError("clarification-gap-candidate-selection-invalid")
    by_id = {element["id"]: element for element in context["elements"]}
    ordered_ids = [selected_id] + [
        element_id for element_id in context["ids"] if element_id != selected_id
    ]
    labels = [
        f'{element_id} (“{" ".join(by_id[element_id]["content"].split())}”)'
        for element_id in ordered_ids
    ]
    if len(labels) == 2:
        rendered = " or ".join(labels)
    else:
        rendered = ", ".join(labels[:-1]) + f", or {labels[-1]}"
    return (
        f"Which recorded element is the intended {context['participant']} for "
        f"{gap['id']}: {rendered}?"
    )


def _round_question(
    state: dict[str, Any],
    gaps: list[dict[str, object]],
    *,
    round_number: int = 1,
    contract: int = ROUND_CONTRACT,
) -> dict[str, object] | None:
    if contract not in SUPPORTED_ROUND_CONTRACTS:
        raise ClarificationError("clarification-round-contract-unsupported")
    if not state["model"]:
        return {
            "id": "questioner_model",
            "prompt": "Which fresh model is formulating this operator question round?",
            "type": "string",
            "required": True,
        }
    if not state["harness"]:
        return {
            "id": "questioner_harness",
            "prompt": "Which harness is running this clarification round?",
            "type": "string",
            "required": True,
        }
    index = len(state["questions"])
    if index >= len(gaps):
        return None
    if contract >= 2 and len(state["answer_types"]) == index:
        answer_types = ANSWER_TYPES if contract >= 3 else LEGACY_ANSWER_TYPES
        return {
            "id": f"operator_answer_type_{index + 1:06d}",
            "prompt": (
                "What must the operator provide to answer this exact gap: text, "
                "another local file, or one public URL?"
                if contract >= 3
                else "What must the operator provide to answer this exact gap: text "
                "or another local file?"
            ),
            "type": "enum",
            "choices": list(answer_types),
            "required": True,
            "gap_index": index,
            "bound_gap": gaps[index],
        }
    candidate = _candidate_question_context(gaps[index]) if contract >= 4 else None
    if candidate is not None:
        if len(state["candidate_selections"]) != index:
            raise ClarificationError("clarification-round-candidate-order-invalid")
        return {
            "id": f"gap_candidate_{index + 1:06d}",
            "prompt": (
                "Which code-listed recorded element should be the primary focus "
                "of the operator question for this exact ambiguous participant?"
            ),
            "type": "enum",
            "choices": candidate["ids"],
            "required": True,
            "gap_index": index,
            "bound_gap": gaps[index],
            "candidate_evidence": candidate["elements"],
        }
    return {
        "id": f"operator_question_{index + 1:06d}",
        "prompt": (
            "What one new focused question should the operator answer to supply "
            "the still-missing information identified by the prior failed "
            "clarification?"
            if round_number > 1
            else "What one focused question should the operator answer to supply "
            "the information missing from this exact gap?"
        ),
        "type": "string",
        "required": True,
        "gap_index": index,
        "bound_gap": gaps[index],
    }


def _round_replay(
    entries: list[dict[str, object]],
    gaps: list[dict[str, object]],
    *,
    round_number: int = 1,
    contract: int = ROUND_CONTRACT,
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state: dict[str, Any] = {
        "model": "",
        "harness": "",
        "answer_types": [],
        "candidate_selections": [],
        "questions": [],
    }
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _round_question(
                state, gaps, round_number=round_number, contract=contract
            )
            if pending is not None or expected != entry.get("question"):
                raise ClarificationError(
                    f"clarification-round-question-invalid:{entry['sequence']}"
                )
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise ClarificationError(
                    f"clarification-round-answer-unbound:{entry['sequence']}"
                )
            if entry.get("accepted"):
                question_id = str(pending["id"])
                if question_id == "questioner_model":
                    state["model"] = str(entry["parsed"])
                elif question_id == "questioner_harness":
                    state["harness"] = str(entry["parsed"])
                elif question_id.startswith("operator_answer_type_"):
                    expected_id = (
                        f"operator_answer_type_{len(state['answer_types']) + 1:06d}"
                    )
                    if question_id != expected_id:
                        raise ClarificationError(
                            f"clarification-round-order-invalid:{entry['sequence']}"
                        )
                    state["answer_types"].append(str(entry["parsed"]))
                elif question_id.startswith("gap_candidate_"):
                    index = len(state["questions"])
                    expected_id = f"gap_candidate_{index + 1:06d}"
                    if question_id != expected_id:
                        raise ClarificationError(
                            f"clarification-round-order-invalid:{entry['sequence']}"
                        )
                    selection = str(entry["parsed"])
                    state["candidate_selections"].append(selection)
                    state["questions"].append(
                        _candidate_operator_question(gaps[index], selection)
                    )
                else:
                    expected_id = f"operator_question_{len(state['questions']) + 1:06d}"
                    if question_id != expected_id:
                        raise ClarificationError(
                            f"clarification-round-order-invalid:{entry['sequence']}"
                        )
                    state["questions"].append(str(entry["parsed"]))
                    if contract >= 4:
                        state["candidate_selections"].append(None)
            pending = None
        elif entry["event"] == "clarification_round_completed":
            if (
                pending is not None
                or _round_question(
                    state, gaps, round_number=round_number, contract=contract
                ) is not None
            ):
                raise ClarificationError(
                    f"clarification-round-completion-invalid:{entry['sequence']}"
                )
            completed = True
        else:
            raise ClarificationError(
                f"clarification-round-event-unsupported:{entry['sequence']}"
            )
    return state, pending, completed


def _round_result(
    projection_sha256: str,
    gaps: list[dict[str, object]],
    state: dict[str, Any],
    *,
    round_number: int = 1,
    contract: int = ROUND_CONTRACT,
) -> dict[str, object]:
    questions = []
    for index, gap in enumerate(gaps):
        asks = state["questions"][index] if index < len(state["questions"]) else ""
        question = {
            "id": (
                f"gap-clarification-answer-{index + 1:06d}"
                if round_number == 1
                else f"gap-clarification-round-{round_number:06d}-question-{index + 1:06d}"
            ),
            "asks": asks,
            "answers_gap": gap_binding(gap),
        }
        if contract >= 2:
            question["answer_type"] = (
                state["answer_types"][index]
                if index < len(state["answer_types"])
                else ""
            )
        if contract >= 4 and index < len(state["candidate_selections"]):
            selection = state["candidate_selections"][index]
            if selection is not None:
                question["candidate_focus"] = selection
        questions.append(question)
    result: dict[str, object] = {
        "schema_version": contract,
        "projection_sha256": projection_sha256,
        "gaps": gaps,
        "questioner": {"model": state["model"], "harness": state["harness"]},
        "questions": questions,
    }
    if round_number > 1:
        result["round"] = round_number
    return result


def _validate_bound_gaps(
    projection: dict[str, Any],
    projection_sha256: str,
    gaps: list[dict[str, object]],
) -> None:
    current = {
        (item["collection"], item["id"]): item
        for item in select_gaps(projection, projection_sha256)
    }
    if not gaps:
        raise ClarificationError("clarification-follow-up-no-gap")
    for gap in gaps:
        if not isinstance(gap, dict):
            raise ClarificationError("clarification-follow-up-gap-invalid")
        key = (gap.get("collection"), gap.get("id"))
        selected = current.get(key)
        if selected is None:
            raise ClarificationError("clarification-follow-up-gap-not-current")
        for field, value in selected.items():
            if gap.get(field) != value:
                raise ClarificationError("clarification-follow-up-gap-changed")
        follow_up = gap.get("follow_up_of")
        if not isinstance(follow_up, dict):
            raise ClarificationError("clarification-follow-up-context-missing")


def run_round(
    round_dir: Path,
    *,
    projection_path: Path,
    projection_sha256: str,
    purpose: str,
    gaps: list[dict[str, object]] | None = None,
    round_number: int = 1,
    contract: int = ROUND_CONTRACT,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    if contract not in SUPPORTED_ROUND_CONTRACTS:
        raise ClarificationError("clarification-round-contract-unsupported")
    projection = _load_projection(projection_path, projection_sha256)
    if gaps is None:
        gaps = require_gaps(projection, projection_sha256)
    else:
        _validate_bound_gaps(projection, projection_sha256, gaps)
    round_dir.mkdir(parents=True, exist_ok=True)
    journal_path = round_dir / "interview.jsonl"
    result_path = round_dir / "clarification-round.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _round_replay(
            _read_journal(journal_path),
            gaps,
            round_number=round_number,
            contract=contract,
        )
        result = _round_result(
            projection_sha256,
            gaps,
            state,
            round_number=round_number,
            contract=contract,
        )
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
            if result_path.read_bytes() != result_bytes:
                raise ClarificationError("clarification-round-result-changed")
            return result
        question = pending or _round_question(
            state, gaps, round_number=round_number, contract=contract
        )
        if question is None:
            _append(
                journal_path,
                "clarification_round_completed",
                {"result_sha256": _digest(result_bytes), "gap_count": len(gaps)},
            )
            result_path.write_bytes(result_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        gap = (
            gaps[int(question["gap_index"])]
            if "gap_index" in question
            else {"round_gap_count": len(gaps)}
        )
        raw = read(_prompt(question, purpose, gap))
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


def validate_round(
    round_dir: Path,
    *,
    projection_path: Path,
    projection_sha256: str,
    purpose: str,
    gaps: list[dict[str, object]] | None = None,
    round_number: int = 1,
    contract: int = ROUND_CONTRACT,
) -> tuple[dict[str, object], str, str]:
    result = run_round(
        round_dir,
        projection_path=projection_path,
        projection_sha256=projection_sha256,
        purpose=purpose,
        gaps=gaps,
        round_number=round_number,
        contract=contract,
        input_fn=lambda _prompt: (_ for _ in ()).throw(
            ClarificationError("clarification-round-not-complete")
        ),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((round_dir / "interview.jsonl").read_bytes()),
        _digest((round_dir / "clarification-round.json").read_bytes()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--projection-sha256", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()
    try:
        result = run(
            args.attempt,
            projection_path=args.projection,
            projection_sha256=args.projection_sha256,
            purpose=args.purpose,
        )
    except ClarificationError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
