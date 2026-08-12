#!/usr/bin/env python3
"""Assess one bound operator answer and propose one complete gap resolution."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1


class ResolutionError(ValueError):
    """The resolution journal or one of its frozen inputs is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise ResolutionError(f"resolution-{label}-unavailable") from error
    if _digest(content) != expected_sha256 or not isinstance(value, dict):
        raise ResolutionError(f"resolution-{label}-changed")
    return value


def _load_answer(
    source_path: Path,
    source_sha256: str,
    projection_path: Path,
    projection_sha256: str,
) -> str:
    try:
        source = source_path.read_bytes()
        projection = projection_path.read_bytes()
    except OSError as error:
        raise ResolutionError("resolution-operator-answer-unavailable") from error
    if _digest(source) != source_sha256:
        raise ResolutionError("resolution-operator-answer-source-changed")
    if _digest(projection) != projection_sha256 or projection != source:
        raise ResolutionError("resolution-operator-answer-projection-changed")
    try:
        answer = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ResolutionError("resolution-operator-answer-not-utf8") from error
    if not answer.strip():
        raise ResolutionError("resolution-operator-answer-empty")
    return answer


def _contains(region: object, point: object) -> bool:
    return (
        isinstance(region, list)
        and len(region) == 4
        and all(isinstance(value, int) for value in region)
        and isinstance(point, list)
        and len(point) == 2
        and all(isinstance(value, int) for value in point)
        and region[0] <= point[0] <= region[2]
        and region[1] <= point[1] <= region[3]
    )


def _inputs(
    projection_path: Path,
    projection_sha256: str,
    clarification_path: Path,
    clarification_sha256: str,
    answer_source_path: Path,
    answer_source_sha256: str,
    answer_projection_path: Path,
    answer_projection_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    projection = _load_json(projection_path, projection_sha256, "projection")
    clarification = _load_json(
        clarification_path, clarification_sha256, "clarification"
    )
    answer = _load_answer(
        answer_source_path,
        answer_source_sha256,
        answer_projection_path,
        answer_projection_sha256,
    )
    question = clarification.get("question")
    gap = clarification.get("gap")
    if not isinstance(question, dict) or not isinstance(gap, dict):
        raise ResolutionError("resolution-clarification-shape-invalid")
    binding = gap.get("record", {}).get("binding_issue")
    if (
        gap.get("projection_sha256") != projection_sha256
        or question.get("answers_gap")
        != {
            key: gap.get(key)
            for key in ("projection_sha256", "collection", "kind", "id", "record_sha256")
        }
        or gap.get("collection") != "relationships"
        or not isinstance(binding, dict)
        or binding.get("participant") not in {"origin", "target"}
        or not isinstance(binding.get("matching_element_ids"), list)
        or not binding["matching_element_ids"]
    ):
        raise ResolutionError("resolution-bound-gap-not-eligible")
    relationships = projection.get("relationships")
    elements = projection.get("elements")
    if not isinstance(relationships, list) or not isinstance(elements, list):
        raise ResolutionError("resolution-projection-shape-invalid")
    relationship = next(
        (item for item in relationships if isinstance(item, dict) and item.get("id") == gap.get("id")),
        None,
    )
    if relationship != gap.get("record") or _digest(_canonical(relationship)) != gap.get(
        "record_sha256"
    ):
        raise ResolutionError("resolution-bound-gap-record-changed")
    element_by_id = {
        item.get("id"): item for item in elements if isinstance(item, dict)
    }
    ambiguous_point = relationship.get(
        "origin_point" if binding["participant"] == "origin" else "target_point"
    )
    for element_id in binding["matching_element_ids"]:
        element = element_by_id.get(element_id)
        if (
            not isinstance(element, dict)
            or element.get("status") != "readable"
            or not _contains(element.get("region"), ambiguous_point)
        ):
            raise ResolutionError(
                f"resolution-gap-choice-{element_id}-does-not-contain-bound-point"
            )
    return projection, clarification, relationship, answer


def _entry(
    sequence: int, event: str, payload: dict[str, object], previous: str | None
) -> dict[str, object]:
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
            raise ResolutionError(f"resolution-journal-json-invalid:{sequence}") from error
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(_canonical(raw))
        raw["entry_sha256"] = claimed
        if raw.get("sequence") != sequence or raw.get("previous_entry_sha256") != previous:
            raise ResolutionError(f"resolution-journal-chain-invalid:{sequence}")
        if claimed != actual:
            raise ResolutionError(f"resolution-journal-entry-changed:{sequence}")
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


def _element_choices(
    projection: dict[str, Any], excluded: set[str]
) -> tuple[list[str], dict[str, object]]:
    elements = [
        element
        for element in projection["elements"]
        if element.get("status") == "readable" and element.get("id") not in excluded
    ]
    return (
        [str(element["id"]) for element in elements],
        {
            str(element["id"]): {
                "kind": element.get("kind"),
                "content": element.get("content"),
                "region": element.get("region"),
            }
            for element in elements
        },
    )


def _recorded_overlap_choices(
    projection: dict[str, Any], draft: dict[str, Any], excluded: set[str]
) -> tuple[list[str], dict[str, object]]:
    proposed = [
        draft["counterpart_left"],
        draft["counterpart_top"],
        draft["counterpart_right"],
        draft["counterpart_bottom"],
    ]
    proposed_area = (proposed[2] - proposed[0]) * (proposed[3] - proposed[1])
    matches: list[dict[str, Any]] = []
    for element in projection["elements"]:
        region = element.get("region")
        if (
            element.get("status") != "readable"
            or element.get("id") in excluded
            or not isinstance(region, list)
            or len(region) != 4
        ):
            continue
        width = max(0, min(proposed[2], region[2]) - max(proposed[0], region[0]))
        height = max(0, min(proposed[3], region[3]) - max(proposed[1], region[1]))
        intersection = width * height
        element_area = (region[2] - region[0]) * (region[3] - region[1])
        union = proposed_area + element_area - intersection
        if union > 0 and intersection / union >= 0.25:
            matches.append(element)
    return (
        [str(element["id"]) for element in matches],
        {
            str(element["id"]): {
                "kind": element.get("kind"),
                "content": element.get("content"),
                "region": element.get("region"),
            }
            for element in matches
        },
    )


def _question(
    projection: dict[str, Any],
    clarification: dict[str, Any],
    relationship: dict[str, Any],
    answer: str,
    state: dict[str, Any],
) -> dict[str, object] | None:
    context = {
        "bound_gap": clarification["gap"],
        "operator_question": clarification["question"]["asks"],
        "operator_answer": answer,
    }
    if not state["model"]:
        return {
            "id": "resolver_model",
            "prompt": "Which fresh model is assessing the bound operator answer?",
            "type": "string",
            "required": True,
        }
    if not state["harness"]:
        return {
            "id": "resolver_harness",
            "prompt": "Which harness is running the gap-resolution interview?",
            "type": "string",
            "required": True,
        }
    draft = state["draft"]
    if "verdict" not in draft:
        return {
            "id": "resolution_verdict",
            "prompt": "Does the preserved operator answer resolve the exact recorded ambiguity?",
            "type": "choice",
            "required": True,
            "choices": ["resolves_gap", "does_not_resolve_gap"],
            "context": context,
        }
    if "reason" not in draft:
        return {
            "id": "resolution_reason",
            "prompt": "Why does the answer resolve or fail to resolve that exact ambiguity?",
            "type": "string",
            "required": True,
            "context": context,
        }
    if draft["verdict"] == "does_not_resolve_gap":
        return None
    binding = relationship["binding_issue"]
    if "ambiguous_element_id" not in draft:
        choices = list(binding["matching_element_ids"])
        evidence = {
            element_id: next(
                {
                    "kind": item.get("kind"),
                    "content": item.get("content"),
                    "region": item.get("region"),
                }
                for item in projection["elements"]
                if item.get("id") == element_id
            )
            for element_id in choices
        }
        return {
            "id": "resolved_ambiguous_element_id",
            "prompt": "Which code-listed element identity does the operator answer select?",
            "type": "choice",
            "required": True,
            "choices": choices,
            "choice_evidence": evidence,
            "context": context,
        }
    counterpart_role = "target" if binding["participant"] == "origin" else "origin"
    counterpart_id = relationship.get(
        "to_id" if counterpart_role == "target" else "from_id"
    )
    if counterpart_id is None and "counterpart_source" not in draft:
        return {
            "id": "counterpart_source",
            "prompt": "Is the other visible participant already recorded or must it be recorded now?",
            "type": "choice",
            "required": True,
            "choices": ["use_recorded_element", "record_visible_element"],
            "context": context,
        }
    if counterpart_id is None and draft["counterpart_source"] == "use_recorded_element" and "counterpart_element_id" not in draft:
        choices, evidence = _element_choices(
            projection, {str(draft["ambiguous_element_id"])}
        )
        return {
            "id": "counterpart_element_id",
            "prompt": "Which recorded readable element is the other exact visible participant?",
            "type": "choice",
            "required": True,
            "choices": choices,
            "choice_evidence": evidence,
            "context": context,
        }
    if counterpart_id is None and draft["counterpart_source"] == "record_visible_element":
        fields = [
            ("counterpart_kind", "What kind of visible element is the other participant?", "string"),
            ("counterpart_left", "Other participant left bound (0-1000)?", "integer"),
            ("counterpart_top", "Other participant top bound (0-1000)?", "integer"),
            ("counterpart_right", "Other participant right bound (0-1000)?", "integer"),
            ("counterpart_bottom", "Other participant bottom bound (0-1000)?", "integer"),
            ("counterpart_content", "What readable content is visible in the other participant?", "string"),
        ]
        for field, prompt, answer_type in fields:
            if field not in draft:
                return {
                    "id": field,
                    "prompt": prompt,
                    "type": answer_type,
                    "required": True,
                    "context": context,
                }
        overlap_choices, overlap_evidence = _recorded_overlap_choices(
            projection, draft, {str(draft["ambiguous_element_id"])}
        )
        if overlap_choices and "counterpart_overlap_disposition" not in draft:
            return {
                "id": "counterpart_overlap_disposition",
                "prompt": "Does this proposed participant reuse a spatially overlapping recorded element, or is it visibly distinct?",
                "type": "choice",
                "required": True,
                "choices": ["reuse_recorded_overlap", "confirm_distinct_element"],
                "overlap_evidence": overlap_evidence,
                "context": context,
            }
        if (
            overlap_choices
            and draft.get("counterpart_overlap_disposition")
            == "reuse_recorded_overlap"
            and "counterpart_overlap_element_id" not in draft
        ):
            return {
                "id": "counterpart_overlap_element_id",
                "prompt": "Which overlapping recorded element is this same visible participant?",
                "type": "choice",
                "required": True,
                "choices": overlap_choices,
                "choice_evidence": overlap_evidence,
                "context": context,
            }
    point_key = "target" if counterpart_role == "target" else "origin"
    point_bounds: list[int] | None = None
    if counterpart_id is not None:
        point_bounds = next(
            item["region"]
            for item in projection["elements"]
            if item["id"] == counterpart_id
        )
    elif draft.get("counterpart_source") == "use_recorded_element" and draft.get(
        "counterpart_element_id"
    ):
        point_bounds = next(
            item["region"]
            for item in projection["elements"]
            if item["id"] == draft["counterpart_element_id"]
        )
    elif draft.get("counterpart_overlap_disposition") == "reuse_recorded_overlap":
        point_bounds = next(
            item["region"]
            for item in projection["elements"]
            if item["id"] == draft["counterpart_overlap_element_id"]
        )
    elif draft.get("counterpart_source") == "record_visible_element" and all(
        field in draft
        for field in (
            "counterpart_left", "counterpart_top", "counterpart_right", "counterpart_bottom"
        )
    ):
        point_bounds = [
            draft["counterpart_left"],
            draft["counterpart_top"],
            draft["counterpart_right"],
            draft["counterpart_bottom"],
        ]
    for axis in ("x", "y"):
        field = f"counterpart_{axis}"
        if field not in draft:
            return {
                "id": field,
                "prompt": f"What normalized {axis} coordinate lies inside the other exact participant?",
                "type": "integer",
                "required": True,
                "point_role": point_key,
                "point_bounds": point_bounds,
                "context": context,
            }
    if "description" not in draft:
        return {
            "id": "resolved_relationship_description",
            "prompt": "What does the now-complete visible relationship establish?",
            "type": "string",
            "required": True,
            "context": context,
        }
    return None


def _parse(
    question: dict[str, object], raw: str, projection: dict[str, Any], state: dict[str, Any]
) -> tuple[str | int | None, str | None]:
    value = raw.strip()
    if not value or "\n" in value or "\r" in value:
        return None, f"{question['id']}: answer one non-empty field at a time"
    if question["type"] == "choice" and value not in question["choices"]:
        return None, (
            f"{question['id']}: received {value!r}; choose one of: "
            + ", ".join(question["choices"])
        )
    if question["type"] != "integer":
        return value, None
    try:
        parsed = int(value)
    except ValueError:
        return None, f"{question['id']}: received {value!r}; enter one integer from 0 through 1000"
    if not 0 <= parsed <= 1000:
        return None, f"{question['id']}: received {parsed}; enter one integer from 0 through 1000"
    draft = state["draft"]
    if question["id"] == "counterpart_right" and parsed <= draft["counterpart_left"]:
        return None, (
            f"counterpart_right: received {parsed}; enter a value greater than "
            f"counterpart_left {draft['counterpart_left']}"
        )
    if question["id"] == "counterpart_bottom" and parsed <= draft["counterpart_top"]:
        return None, (
            f"counterpart_bottom: received {parsed}; enter a value greater than "
            f"counterpart_top {draft['counterpart_top']}"
        )
    if question["id"] == "counterpart_y":
        point = [draft["counterpart_x"], parsed]
        region = question.get("point_bounds")
        if not isinstance(region, list) or len(region) != 4:
            return None, "counterpart_y: code could not bind the selected participant bounds"
        if not _contains(region, point):
            return None, (
                f"counterpart_y: point {point} falls outside selected bounds {region}; "
                "enter coordinates inside that participant"
            )
    return parsed, None


def _apply_answer(state: dict[str, Any], question_id: str, value: str | int) -> None:
    if question_id == "resolver_model":
        state["model"] = value
    elif question_id == "resolver_harness":
        state["harness"] = value
    else:
        key = {
            "resolution_verdict": "verdict",
            "resolution_reason": "reason",
            "resolved_ambiguous_element_id": "ambiguous_element_id",
            "resolved_relationship_description": "description",
        }.get(question_id, question_id)
        state["draft"][key] = value


def _replay(
    entries: list[dict[str, object]],
    projection: dict[str, Any],
    clarification: dict[str, Any],
    relationship: dict[str, Any],
    answer: str,
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state: dict[str, Any] = {"model": "", "harness": "", "draft": {}}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(projection, clarification, relationship, answer, state)
            if pending is not None or expected != entry.get("question"):
                raise ResolutionError(f"resolution-question-invalid:{entry['sequence']}")
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise ResolutionError(f"resolution-answer-unbound:{entry['sequence']}")
            if entry.get("accepted"):
                _apply_answer(state, str(pending["id"]), entry["parsed"])
            pending = None
        elif entry["event"] == "resolution_completed":
            if pending is not None or _question(
                projection, clarification, relationship, answer, state
            ) is not None:
                raise ResolutionError(f"resolution-completion-invalid:{entry['sequence']}")
            completed = True
        else:
            raise ResolutionError(f"resolution-event-unsupported:{entry['sequence']}")
    return state, pending, completed


def _candidate(
    projection: dict[str, Any],
    clarification: dict[str, Any],
    relationship: dict[str, Any],
    answer_source_sha256: str,
    state: dict[str, Any],
) -> dict[str, object]:
    draft = state["draft"]
    if draft.get("verdict") != "resolves_gap" or "description" not in draft:
        return {
            "schema_version": CONTRACT,
            "source_sha256": projection.get("source_sha256"),
            "operator_answer_source_sha256": answer_source_sha256,
            "elements": projection["elements"],
            "relationships": [],
        }
    binding = relationship["binding_issue"]
    ambiguous_role = binding["participant"]
    counterpart_role = "target" if ambiguous_role == "origin" else "origin"
    counterpart_id = relationship.get(
        "to_id" if counterpart_role == "target" else "from_id"
    )
    new_elements: list[dict[str, object]] = []
    if counterpart_id is None:
        if draft["counterpart_source"] == "use_recorded_element":
            counterpart_id = draft["counterpart_element_id"]
        elif draft.get("counterpart_overlap_disposition") == "reuse_recorded_overlap":
            counterpart_id = draft["counterpart_overlap_element_id"]
        else:
            counterpart_id = "resolution-element-000001"
            new_elements.append({
                "id": counterpart_id,
                "kind": draft["counterpart_kind"],
                "region": [
                    draft["counterpart_left"],
                    draft["counterpart_top"],
                    draft["counterpart_right"],
                    draft["counterpart_bottom"],
                ],
                "status": "readable",
                "content": draft["counterpart_content"],
                "gap_reason": "",
                "capture_scope": "gap_resolution_endpoint",
            })
    participant_ids = {
        ambiguous_role: draft["ambiguous_element_id"],
        counterpart_role: counterpart_id,
    }
    ambiguous_point_key = (
        "origin_point" if ambiguous_role == "origin" else "target_point"
    )
    counterpart_point_key = (
        "target_point" if counterpart_role == "target" else "origin_point"
    )
    resolved = {
        "id": f"{relationship['id']}-resolution-000001",
        "resolution_of": relationship["id"],
        "kind": relationship["kind"],
        "from_id": participant_ids["origin"],
        "to_id": participant_ids["target"],
        ambiguous_point_key: relationship[ambiguous_point_key],
        counterpart_point_key: [draft["counterpart_x"], draft["counterpart_y"]],
        "status": "readable",
        "description": draft["description"],
        "gap_reason": "",
        "binding_method": "operator_answer_selected_identity_and_containment",
        "resolution_evidence": {
            "question_id": clarification["question"]["id"],
            "operator_answer_source_sha256": answer_source_sha256,
            "bound_gap_record_sha256": clarification["gap"]["record_sha256"],
        },
    }
    return {
        "schema_version": CONTRACT,
        "source_sha256": projection.get("source_sha256"),
        "operator_answer_source_sha256": answer_source_sha256,
        "elements": [*projection["elements"], *new_elements],
        "relationships": [resolved],
    }


def _prompt(question: dict[str, object], purpose: str) -> str:
    lines = [f"Intake purpose: {purpose}"]
    context = question.get("context")
    if isinstance(context, dict):
        lines.append("Bound clarification evidence: " + json.dumps(context, sort_keys=True))
    lines.extend([f"Question: {question['prompt']}", f"Answer type: {question['type']}"])
    if question["type"] == "choice":
        lines.append("Allowed values: " + ", ".join(question["choices"]))
    if "choice_evidence" in question:
        lines.append("Allowed-value evidence: " + json.dumps(question["choice_evidence"], sort_keys=True))
    if "overlap_evidence" in question:
        lines.append(
            "Spatially overlapping recorded elements: "
            + json.dumps(
                question["overlap_evidence"], sort_keys=True, ensure_ascii=False
            )
        )
    lines.append("Answer: ")
    return "\n".join(lines)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise ResolutionError("resolution-input-ended")
    return value.rstrip("\n")


def run(
    attempt_dir: Path,
    *,
    projection_path: Path,
    projection_sha256: str,
    clarification_path: Path,
    clarification_sha256: str,
    answer_source_path: Path,
    answer_source_sha256: str,
    answer_projection_path: Path,
    answer_projection_sha256: str,
    purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    projection, clarification, relationship, answer = _inputs(
        projection_path,
        projection_sha256,
        clarification_path,
        clarification_sha256,
        answer_source_path,
        answer_source_sha256,
        answer_projection_path,
        answer_projection_sha256,
    )
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    result_path = attempt_dir / "resolution.json"
    candidate_path = attempt_dir / "verification-candidate.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _replay(
            _read_journal(journal_path),
            projection,
            clarification,
            relationship,
            answer,
        )
        candidate = _candidate(
            projection,
            clarification,
            relationship,
            answer_source_sha256,
            state,
        )
        candidate_bytes = json.dumps(candidate, indent=2, sort_keys=True).encode() + b"\n"
        result = {
            "schema_version": CONTRACT,
            "projection_sha256": projection_sha256,
            "clarification_sha256": clarification_sha256,
            "operator_answer_source_sha256": answer_source_sha256,
            "operator_answer_projection_sha256": answer_projection_sha256,
            "gap_id": relationship["id"],
            "reader": {"model": state["model"], "harness": state["harness"]},
            "verdict": state["draft"].get("verdict", ""),
            "reason": state["draft"].get("reason", ""),
            "verification_candidate_sha256": _digest(candidate_bytes),
        }
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
                candidate_path.write_bytes(candidate_bytes)
            if result_path.read_bytes() != result_bytes or candidate_path.read_bytes() != candidate_bytes:
                raise ResolutionError("resolution-result-or-candidate-changed")
            return result
        question = pending or _question(
            projection, clarification, relationship, answer, state
        )
        if question is None:
            _append(journal_path, "resolution_completed", {"result_sha256": _digest(result_bytes)})
            result_path.write_bytes(result_bytes)
            candidate_path.write_bytes(candidate_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, purpose))
        parsed, error = _parse(question, raw, projection, state)
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
    **kwargs: Any,
) -> tuple[dict[str, object], str, str, str]:
    result = run(
        attempt_dir,
        **kwargs,
        input_fn=lambda _prompt: (_ for _ in ()).throw(
            ResolutionError("resolution-not-complete")
        ),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((attempt_dir / "interview.jsonl").read_bytes()),
        _digest((attempt_dir / "resolution.json").read_bytes()),
        _digest((attempt_dir / "verification-candidate.json").read_bytes()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--projection-sha256", required=True)
    parser.add_argument("--clarification", type=Path, required=True)
    parser.add_argument("--clarification-sha256", required=True)
    parser.add_argument("--answer-source", type=Path, required=True)
    parser.add_argument("--answer-source-sha256", required=True)
    parser.add_argument("--answer-projection", type=Path, required=True)
    parser.add_argument("--answer-projection-sha256", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()
    try:
        result = run(
            args.attempt,
            projection_path=args.projection,
            projection_sha256=args.projection_sha256,
            clarification_path=args.clarification,
            clarification_sha256=args.clarification_sha256,
            answer_source_path=args.answer_source,
            answer_source_sha256=args.answer_source_sha256,
            answer_projection_path=args.answer_projection,
            answer_projection_sha256=args.answer_projection_sha256,
            purpose=args.purpose,
        )
    except ResolutionError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
