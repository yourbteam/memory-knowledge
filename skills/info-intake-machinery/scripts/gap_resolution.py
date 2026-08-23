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


CONTRACT = 2


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


def _participant_contract(
    projection: dict[str, Any], relationship: dict[str, Any]
) -> dict[str, Any]:
    elements = projection.get("elements")
    if not isinstance(elements, list):
        raise ResolutionError("resolution-projection-shape-invalid")
    element_by_id = {
        item.get("id"): item for item in elements if isinstance(item, dict)
    }
    binding = relationship.get("binding_issue")
    if isinstance(binding, dict):
        participant = binding.get("participant")
        choices = binding.get("matching_element_ids")
        ids = {
            "origin": relationship.get("from_id"),
            "target": relationship.get("to_id"),
        }
        points = {
            "origin": relationship.get("origin_point"),
            "target": relationship.get("target_point"),
        }
        if choices == [] and all(isinstance(ids[role], str) for role in ids):
            for role in ("origin", "target"):
                element = element_by_id.get(ids[role])
                if (
                    not isinstance(element, dict)
                    or element.get("status") != "readable"
                    or not _contains(element.get("region"), points[role])
                ):
                    raise ResolutionError(
                        f"resolution-complete-{role}-binding-invalid"
                    )
            return {
                "mode": "complete_recorded_participants",
                "origin_id": ids["origin"],
                "target_id": ids["target"],
                "origin_point": points["origin"],
                "target_point": points["target"],
            }
        if (
            participant not in {"origin", "target"}
            or not isinstance(choices, list)
            or not choices
        ):
            raise ResolutionError("resolution-bound-gap-not-eligible")
        point = relationship.get(
            "origin_point" if participant == "origin" else "target_point"
        )
        for element_id in choices:
            element = element_by_id.get(element_id)
            if (
                not isinstance(element, dict)
                or element.get("status") != "readable"
                or not _contains(element.get("region"), point)
            ):
                raise ResolutionError(
                    f"resolution-gap-choice-{element_id}-does-not-contain-bound-point"
                )
        known_role = "target" if participant == "origin" else "origin"
        return {
            "mode": "ambiguous_identity",
            "unresolved_role": participant,
            "known_role": known_role,
            "known_id": relationship.get(
                "to_id" if known_role == "target" else "from_id"
            ),
            "choices": choices,
        }
    if binding is not None:
        raise ResolutionError("resolution-bound-gap-not-eligible")
    ids = {
        "origin": relationship.get("from_id"),
        "target": relationship.get("to_id"),
    }
    missing_roles = [role for role, element_id in ids.items() if element_id is None]
    if len(missing_roles) == 2:
        identity_mismatch = relationship.get("identity_mismatch")
        if (
            not isinstance(identity_mismatch, dict)
            or identity_mismatch.get("verdict") != "different_source_unit"
            or not isinstance(identity_mismatch.get("required_claim"), str)
            or not identity_mismatch["required_claim"].strip()
        ):
            raise ResolutionError("resolution-bound-gap-not-eligible")
        return {"mode": "missing_both_participants"}
    if len(missing_roles) != 1:
        raise ResolutionError("resolution-bound-gap-not-eligible")
    unresolved_role = missing_roles[0]
    known_role = "target" if unresolved_role == "origin" else "origin"
    known_id = ids[known_role]
    known_element = element_by_id.get(known_id)
    known_status = (
        known_element.get("status") if isinstance(known_element, dict) else None
    )
    known_gap_is_preserved = (
        known_status == "gap"
        and known_element.get("content") == ""
        and isinstance(known_element.get("gap_reason"), str)
        and bool(known_element["gap_reason"].strip())
        and isinstance(known_element.get("region"), list)
        and len(known_element["region"]) == 4
        and all(isinstance(value, int) for value in known_element["region"])
    )
    if (
        not isinstance(known_id, str)
        or not isinstance(known_element, dict)
        or (known_status != "readable" and not known_gap_is_preserved)
        or (
            relationship.get("participant_id") is not None
            and relationship.get("participant_id") != known_id
        )
    ):
        raise ResolutionError(f"resolution-known-{known_role}-binding-invalid")
    known_point = relationship.get(
        "target_point" if known_role == "target" else "origin_point"
    )
    if known_point is not None and not _contains(
        known_element.get("region"), known_point
    ):
        raise ResolutionError(f"resolution-known-{known_role}-binding-invalid")
    return {
        "mode": "missing_participant",
        "unresolved_role": unresolved_role,
        "known_role": known_role,
        "known_id": known_id,
        "known_point": known_point,
        "known_status": known_status,
    }


def _inputs(
    projection_path: Path,
    projection_sha256: str,
    clarification_path: Path,
    clarification_sha256: str,
    answer_source_path: Path,
    answer_source_sha256: str,
    answer_projection_path: Path,
    answer_projection_sha256: str,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    str,
    dict[str, Any] | None,
]:
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
    if (
        gap.get("projection_sha256") != projection_sha256
        or question.get("answers_gap")
        != {
            key: gap.get(key)
            for key in ("projection_sha256", "collection", "kind", "id", "record_sha256")
        }
        or gap.get("collection") != "relationships"
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
    contract = _participant_contract(projection, relationship)
    accepted_assessment = clarification.get("accepted_assessment")
    prior_rejection = clarification.get("prior_rejection")
    if prior_rejection is not None and (
        not isinstance(prior_rejection, dict)
        or not isinstance(prior_rejection.get("attempt"), int)
        or prior_rejection["attempt"] < 1
        or prior_rejection.get("verification_verdict")
        not in {"not_supported", "unreadable"}
        or not isinstance(prior_rejection.get("verification_reason"), str)
        or not prior_rejection["verification_reason"].strip()
        or not isinstance(prior_rejection.get("rejected_relationship"), dict)
        or prior_rejection["rejected_relationship"].get("resolution_of")
        != gap.get("id")
    ):
        raise ResolutionError("resolution-prior-rejection-binding-invalid")
    if contract["mode"] in {
        "missing_participant",
        "missing_both_participants",
        "complete_recorded_participants",
    } and accepted_assessment is None:
        raise ResolutionError(
            "resolution-missing-participant-requires-accepted-assessment"
        )
    if accepted_assessment is not None:
        if contract["mode"] in {"ambiguous_identity", "missing_participant"}:
            known_role = contract["known_role"]
            known_id = contract["known_id"]
            known_point = relationship.get(
                "target_point" if known_role == "target" else "origin_point"
            )
            known_element = next(
                (
                    item
                    for item in elements
                    if isinstance(item, dict) and item.get("id") == known_id
                ),
                None,
            )
            if known_id is not None and (
                not isinstance(known_element, dict)
                or known_element.get("status") != contract.get("known_status", "readable")
                or (
                    contract["mode"] == "ambiguous_identity"
                    and not _contains(known_element.get("region"), known_point)
                )
                or (
                    contract["mode"] == "missing_participant"
                    and known_point is not None
                    and not _contains(known_element.get("region"), known_point)
                )
            ):
                raise ResolutionError(
                    f"resolution-known-{known_role}-binding-invalid"
                )
        active_identity = {
            key: gap.get(key)
            for key in (
                "projection_sha256", "collection", "kind", "id", "record_sha256"
            )
        }
        assessment_gap = clarification.get("assessment_gap", gap)
        if not isinstance(assessment_gap, dict):
            raise ResolutionError("resolution-assessment-gap-binding-invalid")
        assessment_identity = {
            key: assessment_gap.get(key)
            for key in (
                "projection_sha256", "collection", "kind", "id", "record_sha256"
            )
        }
        stable_identity_keys = ("collection", "kind", "id", "record_sha256")
        if (
            not isinstance(accepted_assessment, dict)
            or not isinstance(accepted_assessment.get("position"), int)
            or accepted_assessment["position"] < 1
            or accepted_assessment.get("question_id") != question.get("id")
            or accepted_assessment.get("gap") != assessment_identity
            or any(
                active_identity[key] != assessment_identity[key]
                for key in stable_identity_keys
            )
            or assessment_gap.get("record") != gap.get("record")
            or accepted_assessment.get("answer_source", {}).get("sha256")
            != answer_source_sha256
            or accepted_assessment.get("answer_projection", {}).get("sha256")
            != answer_projection_sha256
            or accepted_assessment.get("verdict") != "resolves_gap"
            or not isinstance(accepted_assessment.get("reason"), str)
            or not accepted_assessment["reason"].strip()
        ):
            raise ResolutionError("resolution-accepted-assessment-binding-invalid")
    return projection, clarification, relationship, answer, accepted_assessment


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


def _missing_participant_question(
    projection: dict[str, Any],
    clarification: dict[str, Any],
    relationship: dict[str, Any],
    context: dict[str, object],
    draft: dict[str, Any],
) -> dict[str, object] | None:
    contract = _participant_contract(projection, relationship)
    known_id = str(contract["known_id"])
    if "missing_participant_source" not in draft:
        return {
            "id": "missing_participant_source",
            "prompt": "Is the missing visible participant already recorded or must it be recorded now?",
            "type": "choice",
            "required": True,
            "choices": ["use_recorded_element", "record_visible_element"],
            "context": context,
        }
    if (
        draft["missing_participant_source"] == "use_recorded_element"
        and "missing_participant_element_id" not in draft
    ):
        choices, evidence = _element_choices(projection, {known_id})
        return {
            "id": "missing_participant_element_id",
            "prompt": "Which recorded readable element is the exact missing visible participant?",
            "type": "choice",
            "required": True,
            "choices": choices,
            "choice_evidence": evidence,
            "context": context,
        }
    if draft["missing_participant_source"] == "record_visible_element":
        fields = [
            ("missing_participant_kind", "What kind of visible element is the missing participant?", "string"),
            ("missing_participant_left", "Missing participant left bound (0-1000)?", "integer"),
            ("missing_participant_top", "Missing participant top bound (0-1000)?", "integer"),
            ("missing_participant_right", "Missing participant right bound (0-1000)?", "integer"),
            ("missing_participant_bottom", "Missing participant bottom bound (0-1000)?", "integer"),
            ("missing_participant_content", "What readable content is visible in the missing participant?", "string"),
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
            projection,
            {
                "counterpart_left": draft["missing_participant_left"],
                "counterpart_top": draft["missing_participant_top"],
                "counterpart_right": draft["missing_participant_right"],
                "counterpart_bottom": draft["missing_participant_bottom"],
            },
            set(),
        )
        reusable_overlap_choices = [
            element_id for element_id in overlap_choices if element_id != known_id
        ]
        if overlap_choices and "missing_participant_overlap_disposition" not in draft:
            return {
                "id": "missing_participant_overlap_disposition",
                "prompt": "Does this proposed participant reuse a spatially overlapping recorded element, or is it visibly distinct?",
                "type": "choice",
                "required": True,
                "choices": [
                    *(
                        ["reuse_recorded_overlap"]
                        if reusable_overlap_choices
                        else []
                    ),
                    "confirm_distinct_element",
                ],
                "overlap_evidence": overlap_evidence,
                "context": context,
            }
        if (
            overlap_choices
            and draft.get("missing_participant_overlap_disposition")
            == "reuse_recorded_overlap"
            and "missing_participant_overlap_element_id" not in draft
        ):
            return {
                "id": "missing_participant_overlap_element_id",
                "prompt": "Which overlapping recorded element is this same missing participant?",
                "type": "choice",
                "required": True,
                "choices": reusable_overlap_choices,
                "choice_evidence": {
                    element_id: overlap_evidence[element_id]
                    for element_id in reusable_overlap_choices
                },
                "context": context,
            }
    if draft.get("missing_participant_source") == "use_recorded_element":
        selected_id = draft.get("missing_participant_element_id")
        missing_bounds = next(
            item["region"]
            for item in projection["elements"]
            if item.get("id") == selected_id
        )
    elif draft.get("missing_participant_overlap_disposition") == "reuse_recorded_overlap":
        selected_id = draft.get("missing_participant_overlap_element_id")
        missing_bounds = next(
            item["region"]
            for item in projection["elements"]
            if item.get("id") == selected_id
        )
    else:
        missing_bounds = [
            draft["missing_participant_left"],
            draft["missing_participant_top"],
            draft["missing_participant_right"],
            draft["missing_participant_bottom"],
        ]
    for axis in ("x", "y"):
        field = f"missing_participant_{axis}"
        if field not in draft:
            return {
                "id": field,
                "prompt": f"What normalized {axis} coordinate lies inside the exact missing participant?",
                "type": "integer",
                "required": True,
                "point_role": contract["unresolved_role"],
                "point_bounds": missing_bounds,
                "context": context,
            }
    if contract.get("known_point") is None:
        known_bounds = next(
            item["region"]
            for item in projection["elements"]
            if item.get("id") == known_id
        )
        for axis in ("x", "y"):
            field = f"known_participant_{axis}"
            if field not in draft:
                return {
                    "id": field,
                    "prompt": f"What normalized {axis} coordinate lies inside the locked known participant {known_id}?",
                    "type": "integer",
                    "required": True,
                    "point_role": contract["known_role"],
                    "point_bounds": known_bounds,
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


def _missing_both_participants_question(
    projection: dict[str, Any],
    context: dict[str, object],
    draft: dict[str, Any],
) -> dict[str, object] | None:
    if "missing_origin_element_id" not in draft:
        choices, evidence = _element_choices(projection, set())
        return {
            "id": "missing_origin_element_id",
            "prompt": "Which code-listed recorded element is the exact relationship origin?",
            "type": "choice",
            "required": True,
            "choices": choices,
            "choice_evidence": evidence,
            "context": context,
        }
    origin_id = str(draft["missing_origin_element_id"])
    if "missing_target_element_id" not in draft:
        choices, evidence = _element_choices(projection, {origin_id})
        return {
            "id": "missing_target_element_id",
            "prompt": "Which code-listed recorded element is the exact relationship target?",
            "type": "choice",
            "required": True,
            "choices": choices,
            "choice_evidence": evidence,
            "context": context,
        }
    for role in ("origin", "target"):
        element_id = str(draft[f"missing_{role}_element_id"])
        bounds = next(
            item["region"]
            for item in projection["elements"]
            if item.get("id") == element_id
        )
        for axis in ("x", "y"):
            field = f"missing_{role}_{axis}"
            if field not in draft:
                return {
                    "id": field,
                    "prompt": f"What normalized {axis} coordinate lies inside the selected {role} element?",
                    "type": "integer",
                    "required": True,
                    "point_role": role,
                    "point_bounds": bounds,
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


def _question(
    projection: dict[str, Any],
    clarification: dict[str, Any],
    relationship: dict[str, Any],
    answer: str,
    state: dict[str, Any],
    contract_version: int = CONTRACT,
) -> dict[str, object] | None:
    context = {
        "bound_gap": clarification["gap"],
        "operator_question": clarification["question"]["asks"],
        "operator_answer": answer,
    }
    if clarification.get("accepted_assessment") is not None:
        context["accepted_assessment"] = clarification["accepted_assessment"]
    if clarification.get("prior_rejection") is not None:
        context["prior_rejection"] = clarification["prior_rejection"]
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
    contract = _participant_contract(projection, relationship)
    if clarification.get("prior_rejection") is not None:
        if contract_version >= 2 and contract["mode"] == "missing_participant":
            return _missing_participant_question(
                projection, clarification, relationship, context, draft
            )
        if "retry_from_element_id" not in draft:
            choices, evidence = _element_choices(projection, set())
            return {
                "id": "retry_from_element_id",
                "prompt": "Which code-listed recorded element is the corrected relationship origin?",
                "type": "choice",
                "required": True,
                "choices": choices,
                "choice_evidence": evidence,
                "context": context,
            }
        if "retry_to_element_id" not in draft:
            choices, evidence = _element_choices(
                projection, {str(draft["retry_from_element_id"])}
            )
            return {
                "id": "retry_to_element_id",
                "prompt": "Which code-listed recorded element is the corrected relationship target?",
                "type": "choice",
                "required": True,
                "choices": choices,
                "choice_evidence": evidence,
                "context": context,
            }
        for role in ("from", "to"):
            element_id = str(draft[f"retry_{role}_element_id"])
            bounds = next(
                item["region"]
                for item in projection["elements"]
                if item.get("id") == element_id
            )
            for axis in ("x", "y"):
                field = f"retry_{role}_{axis}"
                if field not in draft:
                    return {
                        "id": field,
                        "prompt": f"What normalized {axis} coordinate lies inside the corrected {role} element?",
                        "type": "integer",
                        "required": True,
                        "point_role": role,
                        "point_bounds": bounds,
                        "context": context,
                    }
        if "description" not in draft:
            return {
                "id": "resolved_relationship_description",
                "prompt": "What does the corrected complete visible relationship establish?",
                "type": "string",
                "required": True,
                "context": context,
            }
        return None
    if contract["mode"] == "missing_both_participants":
        return _missing_both_participants_question(projection, context, draft)
    if contract["mode"] == "complete_recorded_participants":
        if "description" not in draft:
            return {
                "id": "resolved_relationship_description",
                "prompt": "What does the now-complete visible relationship establish?",
                "type": "string",
                "required": True,
                "context": context,
            }
        return None
    binding = relationship.get("binding_issue")
    if not isinstance(binding, dict):
        return _missing_participant_question(
            projection, clarification, relationship, context, draft
        )
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
    if clarification.get("accepted_assessment") is not None and counterpart_id is not None:
        if "description" not in draft:
            return {
                "id": "resolved_relationship_description",
                "prompt": "What does the now-complete visible relationship establish?",
                "type": "string",
                "required": True,
                "context": context,
            }
        return None
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
    if question["id"] in {"counterpart_right", "missing_participant_right"}:
        left_key = (
            "counterpart_left"
            if question["id"] == "counterpart_right"
            else "missing_participant_left"
        )
        if parsed <= draft[left_key]:
            return None, (
                f"{question['id']}: received {parsed}; enter a value greater than "
                f"{left_key} {draft[left_key]}"
            )
    if question["id"] in {"counterpart_bottom", "missing_participant_bottom"}:
        top_key = (
            "counterpart_top"
            if question["id"] == "counterpart_bottom"
            else "missing_participant_top"
        )
        if parsed <= draft[top_key]:
            return None, (
                f"{question['id']}: received {parsed}; enter a value greater than "
                f"{top_key} {draft[top_key]}"
            )
    point_x_keys = {
        "counterpart_y": "counterpart_x",
        "missing_participant_y": "missing_participant_x",
        "missing_origin_y": "missing_origin_x",
        "missing_target_y": "missing_target_x",
        "known_participant_y": "known_participant_x",
        "retry_from_y": "retry_from_x",
        "retry_to_y": "retry_to_x",
    }
    if question["id"] in point_x_keys:
        x_key = point_x_keys[str(question["id"])]
        point = [draft[x_key], parsed]
        region = question.get("point_bounds")
        if not isinstance(region, list) or len(region) != 4:
            return None, f"{question['id']}: code could not bind the selected participant bounds"
        if not _contains(region, point):
            return None, (
                f"{question['id']}: point {point} falls outside selected bounds {region}; "
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
    accepted_assessment: dict[str, Any] | None,
    contract_version: int = CONTRACT,
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    draft = (
        {
            "verdict": "resolves_gap",
            "reason": accepted_assessment["reason"],
        }
        if accepted_assessment is not None
        else {}
    )
    state: dict[str, Any] = {"model": "", "harness": "", "draft": draft}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(
                projection, clarification, relationship, answer, state,
                contract_version,
            )
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
                projection, clarification, relationship, answer, state,
                contract_version,
            ) is not None:
                raise ResolutionError(f"resolution-completion-invalid:{entry['sequence']}")
            completed = True
        else:
            raise ResolutionError(f"resolution-event-unsupported:{entry['sequence']}")
    return state, pending, completed


def _missing_participant_candidate(
    projection: dict[str, Any],
    clarification: dict[str, Any],
    relationship: dict[str, Any],
    answer_source_sha256: str,
    draft: dict[str, Any],
) -> dict[str, object]:
    contract = _participant_contract(projection, relationship)
    unresolved_role = str(contract["unresolved_role"])
    known_role = str(contract["known_role"])
    known_id = str(contract["known_id"])
    new_elements: list[dict[str, object]] = []
    if draft["missing_participant_source"] == "use_recorded_element":
        missing_id = str(draft["missing_participant_element_id"])
    elif draft.get("missing_participant_overlap_disposition") == "reuse_recorded_overlap":
        missing_id = str(draft["missing_participant_overlap_element_id"])
    else:
        existing_ids = {
            str(item.get("id"))
            for item in projection["elements"]
            if isinstance(item, dict)
        }
        sequence = 1
        missing_id = f"resolution-element-{sequence:06d}"
        while missing_id in existing_ids:
            sequence += 1
            missing_id = f"resolution-element-{sequence:06d}"
        new_elements.append({
            "id": missing_id,
            "kind": draft["missing_participant_kind"],
            "region": [
                draft["missing_participant_left"],
                draft["missing_participant_top"],
                draft["missing_participant_right"],
                draft["missing_participant_bottom"],
            ],
            "status": "readable",
            "content": draft["missing_participant_content"],
            "gap_reason": "",
            "capture_scope": "gap_resolution_endpoint",
        })
    participant_ids = {
        unresolved_role: missing_id,
        known_role: known_id,
    }
    points = {
        unresolved_role: [
            draft["missing_participant_x"],
            draft["missing_participant_y"],
        ],
        known_role: (
            contract["known_point"]
            if contract.get("known_point") is not None
            else [draft["known_participant_x"], draft["known_participant_y"]]
        ),
    }
    resolved = {
        "id": f"{relationship['id']}-resolution-000001",
        "resolution_of": relationship["id"],
        "kind": relationship["kind"],
        "from_id": participant_ids["origin"],
        "to_id": participant_ids["target"],
        "origin_point": points["origin"],
        "target_point": points["target"],
        "status": "readable",
        "description": draft["description"],
        "gap_reason": "",
        "binding_method": "accepted_assessment_locked_known_endpoint_and_containment",
        "resolution_evidence": {
            "question_id": clarification["question"]["id"],
            "operator_answer_source_sha256": answer_source_sha256,
            "bound_gap_record_sha256": clarification["gap"]["record_sha256"],
            "accepted_assessment_sha256": _digest(
                _canonical(clarification["accepted_assessment"])
            ),
            "locked_known_role": known_role,
            "locked_known_element_id": known_id,
            "locked_known_element_status": contract.get(
                "known_status", "readable"
            ),
        },
    }
    return {
        "schema_version": CONTRACT,
        "source_sha256": projection.get("source_sha256"),
        "operator_answer_source_sha256": answer_source_sha256,
        "elements": [*projection["elements"], *new_elements],
        "relationships": [resolved],
    }


def _recorded_participants_candidate(
    projection: dict[str, Any],
    clarification: dict[str, Any],
    relationship: dict[str, Any],
    answer_source_sha256: str,
    draft: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, object]:
    if contract["mode"] == "missing_both_participants":
        origin_id = str(draft["missing_origin_element_id"])
        target_id = str(draft["missing_target_element_id"])
        origin_point = [draft["missing_origin_x"], draft["missing_origin_y"]]
        target_point = [draft["missing_target_x"], draft["missing_target_y"]]
        binding_method = "accepted_assessment_selected_both_recorded_participants"
    else:
        origin_id = str(contract["origin_id"])
        target_id = str(contract["target_id"])
        origin_point = contract["origin_point"]
        target_point = contract["target_point"]
        binding_method = "accepted_assessment_reused_complete_recorded_participants"
    resolved = {
        "id": f"{relationship['id']}-resolution-000001",
        "resolution_of": relationship["id"],
        "kind": relationship["kind"],
        "from_id": origin_id,
        "to_id": target_id,
        "origin_point": origin_point,
        "target_point": target_point,
        "status": "readable",
        "description": draft["description"],
        "gap_reason": "",
        "binding_method": binding_method,
        "resolution_evidence": {
            "question_id": clarification["question"]["id"],
            "operator_answer_source_sha256": answer_source_sha256,
            "bound_gap_record_sha256": clarification["gap"]["record_sha256"],
            "accepted_assessment_sha256": _digest(
                _canonical(clarification["accepted_assessment"])
            ),
        },
    }
    return {
        "schema_version": CONTRACT,
        "source_sha256": projection.get("source_sha256"),
        "operator_answer_source_sha256": answer_source_sha256,
        "elements": projection["elements"],
        "relationships": [resolved],
    }


def _candidate(
    projection: dict[str, Any],
    clarification: dict[str, Any],
    relationship: dict[str, Any],
    answer_source_sha256: str,
    state: dict[str, Any],
    contract_version: int = CONTRACT,
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
    if clarification.get("prior_rejection") is not None:
        contract = _participant_contract(projection, relationship)
        if contract_version >= 2 and contract["mode"] == "missing_participant":
            candidate = _missing_participant_candidate(
                projection,
                clarification,
                relationship,
                answer_source_sha256,
                draft,
            )
            resolved = candidate["relationships"][0]
            resolved["binding_method"] = (
                "verifier_rejection_corrected_missing_participant_with_locked_endpoint"
            )
            resolved["resolution_evidence"].update({
                "rejected_candidate_sha256": clarification["prior_rejection"][
                    "candidate_sha256"
                ],
                "rejected_verification_sha256": clarification[
                    "prior_rejection"
                ]["verification_result_sha256"],
            })
            return candidate
        resolved = {
            "id": f"{relationship['id']}-resolution-000001",
            "resolution_of": relationship["id"],
            "kind": relationship["kind"],
            "from_id": draft["retry_from_element_id"],
            "to_id": draft["retry_to_element_id"],
            "origin_point": [draft["retry_from_x"], draft["retry_from_y"]],
            "target_point": [draft["retry_to_x"], draft["retry_to_y"]],
            "status": "readable",
            "description": draft["description"],
            "gap_reason": "",
            "binding_method": "verifier_rejection_corrected_with_recorded_endpoints",
            "resolution_evidence": {
                "question_id": clarification["question"]["id"],
                "operator_answer_source_sha256": answer_source_sha256,
                "bound_gap_record_sha256": clarification["gap"]["record_sha256"],
                "accepted_assessment_sha256": _digest(
                    _canonical(clarification["accepted_assessment"])
                ),
                "rejected_candidate_sha256": clarification["prior_rejection"][
                    "candidate_sha256"
                ],
                "rejected_verification_sha256": clarification[
                    "prior_rejection"
                ]["verification_result_sha256"],
            },
        }
        return {
            "schema_version": CONTRACT,
            "source_sha256": projection.get("source_sha256"),
            "operator_answer_source_sha256": answer_source_sha256,
            "elements": projection["elements"],
            "relationships": [resolved],
        }
    contract = _participant_contract(projection, relationship)
    if contract["mode"] in {
        "missing_both_participants",
        "complete_recorded_participants",
    }:
        return _recorded_participants_candidate(
            projection,
            clarification,
            relationship,
            answer_source_sha256,
            draft,
            contract,
        )
    binding = relationship.get("binding_issue")
    if not isinstance(binding, dict):
        return _missing_participant_candidate(
            projection,
            clarification,
            relationship,
            answer_source_sha256,
            draft,
        )
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
    counterpart_point = (
        relationship[counterpart_point_key]
        if clarification.get("accepted_assessment") is not None
        and relationship.get(counterpart_point_key) is not None
        else [draft["counterpart_x"], draft["counterpart_y"]]
    )
    resolved = {
        "id": f"{relationship['id']}-resolution-000001",
        "resolution_of": relationship["id"],
        "kind": relationship["kind"],
        "from_id": participant_ids["origin"],
        "to_id": participant_ids["target"],
        ambiguous_point_key: relationship[ambiguous_point_key],
        counterpart_point_key: counterpart_point,
        "status": "readable",
        "description": draft["description"],
        "gap_reason": "",
        "binding_method": "operator_answer_selected_identity_and_containment",
        "resolution_evidence": {
            "question_id": clarification["question"]["id"],
            "operator_answer_source_sha256": answer_source_sha256,
            "bound_gap_record_sha256": clarification["gap"]["record_sha256"],
            "accepted_assessment_sha256": (
                _digest(_canonical(clarification["accepted_assessment"]))
                if clarification.get("accepted_assessment") is not None
                else None
            ),
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
    contract_version: int = CONTRACT,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    projection, clarification, relationship, answer, accepted_assessment = _inputs(
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
            accepted_assessment,
            contract_version,
        )
        candidate = _candidate(
            projection,
            clarification,
            relationship,
            answer_source_sha256,
            state,
            contract_version,
        )
        candidate["schema_version"] = contract_version
        candidate_bytes = json.dumps(candidate, indent=2, sort_keys=True).encode() + b"\n"
        result = {
            "schema_version": contract_version,
            "projection_sha256": projection_sha256,
            "clarification_sha256": clarification_sha256,
            "operator_answer_source_sha256": answer_source_sha256,
            "operator_answer_projection_sha256": answer_projection_sha256,
            "gap_id": relationship["id"],
            "reader": {"model": state["model"], "harness": state["harness"]},
            "verdict": state["draft"].get("verdict", ""),
            "reason": state["draft"].get("reason", ""),
            "accepted_assessment_sha256": (
                _digest(_canonical(accepted_assessment))
                if accepted_assessment is not None
                else None
            ),
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
            projection, clarification, relationship, answer, state,
            contract_version,
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
