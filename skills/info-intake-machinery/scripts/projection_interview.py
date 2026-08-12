#!/usr/bin/env python3
"""Run a code-controlled visual projection interview."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 7
SUPPORTED_CONTRACTS = {1, 2, 3, 4, 5, 6, CONTRACT}
SCAN_GRID_SIZE = 4


class InterviewError(ValueError):
    """The durable interview is unavailable, changed, or inconsistent."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise InterviewError(f"interview-journal-unavailable:{error}") from error
    entries: list[dict[str, object]] = []
    previous: str | None = None
    for sequence, line in enumerate(lines, start=1):
        try:
            raw = json.loads(line)
        except (json.JSONDecodeError, TypeError) as error:
            raise InterviewError(f"interview-journal-json-invalid:{sequence}") from error
        if not isinstance(raw, dict):
            raise InterviewError(f"interview-journal-entry-invalid:{sequence}")
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(_canonical(raw))
        raw["entry_sha256"] = claimed
        if raw.get("sequence") != sequence:
            raise InterviewError(f"interview-journal-sequence-invalid:{sequence}")
        if raw.get("previous_entry_sha256") != previous:
            raise InterviewError(f"interview-journal-chain-invalid:{sequence}")
        if claimed != actual:
            raise InterviewError(f"interview-journal-entry-changed:{sequence}")
        previous = str(claimed)
        entries.append(raw)
    return entries


def _append(path: Path, event: str, payload: dict[str, object]) -> dict[str, object]:
    entries = _read_journal(path)
    result = _entry(
        len(entries) + 1,
        event,
        payload,
        str(entries[-1]["entry_sha256"]) if entries else None,
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")
    return result


def _scan_regions() -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for row in range(SCAN_GRID_SIZE):
        for column in range(SCAN_GRID_SIZE):
            regions.append({
                "id": f"region-r{row + 1:02d}-c{column + 1:02d}",
                "bounds": [
                    column * 1000 // SCAN_GRID_SIZE,
                    row * 1000 // SCAN_GRID_SIZE,
                    (column + 1) * 1000 // SCAN_GRID_SIZE,
                    (row + 1) * 1000 // SCAN_GRID_SIZE,
                ],
                "status": "pending",
                "element_ids": [],
                "gap_reason": "",
            })
    return regions


def _initial_state(*, contract: int) -> dict[str, Any]:
    return {
        "stage": "reader_model",
        "reader": {},
        "elements": [],
        "relationships": [],
        "relationship_obligations": [],
        "scan_regions": _scan_regions() if contract >= 4 else [],
        "scan_region_index": 0,
        "relationship_draft": None,
        "current": {},
    }


def _pending_obligation(state: dict[str, Any]) -> dict[str, Any] | None:
    return next((
        item for item in state["relationship_obligations"]
        if item["status"] == "pending"
    ), None)


def _active_scan_region(state: dict[str, Any]) -> dict[str, Any] | None:
    index = int(state["scan_region_index"])
    regions = state["scan_regions"]
    return regions[index] if index < len(regions) else None


def _elements_at_point(
    state: dict[str, Any], x: int, y: int,
) -> list[dict[str, Any]]:
    return [
        item for item in state["elements"]
        if (
            int(item["region"][0]) <= x < int(item["region"][2])
            and int(item["region"][1]) <= y < int(item["region"][3])
        )
    ]


def _advance_scan_region(state: dict[str, Any]) -> None:
    state["scan_region_index"] += 1
    state["stage"] = (
        "region_element_more" if _active_scan_region(state) is not None
        else _next_relationship_stage(state)
    )


def _field(
    field_id: str,
    prompt: str,
    field_type: str,
    *,
    choices: list[str] | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": field_id,
        "prompt": prompt,
        "type": field_type,
        "required": True,
    }
    if choices is not None:
        result["choices"] = choices
    if minimum is not None:
        result["minimum"] = minimum
    if maximum is not None:
        result["maximum"] = maximum
    return result


def _question(
    state: dict[str, Any],
    *,
    purpose: str,
    contract: int,
) -> dict[str, object] | None:
    stage = state["stage"]
    current = state["current"]
    if stage == "complete":
        if contract >= 3 and _pending_obligation(state) is not None:
            raise InterviewError("relationship-obligation-unresolved")
        return None
    if contract not in SUPPORTED_CONTRACTS:
        raise InterviewError(f"interview-contract-unsupported:{contract}")
    question: dict[str, object]
    if stage == "reader_model":
        question = _field("reader_model", "Which model is inspecting the frozen source?", "string")
        return question
    if stage == "reader_harness":
        question = _field("reader_harness", "Which harness is running this interview?", "string")
        return question
    if stage == "region_element_more":
        region = _active_scan_region(state)
        if region is None:
            raise InterviewError("scan-region-missing")
        question = _field(
            "region_element_more",
            "Does the active source region contain another purpose-relevant visible element that has not been recorded?",
            "choice",
            choices=["yes", "no", "gap"],
        )
    elif stage == "region_gap_reason":
        question = _field(
            "region_gap_reason",
            "What visible condition prevents faithful inspection of the active source region?",
            "string",
        )
    elif stage == "element_more":
        question = _field(
            "element_more",
            "Is there another purpose-relevant visible element that has not been recorded?",
            "choice",
            choices=["yes", "no"],
        )
    elif stage == "element_kind":
        question = _field("element_kind", "What source-neutral kind best identifies this visible element?", "string")
    elif stage == "element_left":
        question = _field("element_left", "What is the element's normalized left coordinate?", "integer", minimum=0, maximum=999)
    elif stage == "element_top":
        question = _field("element_top", "What is the element's normalized top coordinate?", "integer", minimum=0, maximum=999)
    elif stage == "element_right":
        question = _field(
            "element_right",
            "What is the element's normalized right coordinate?",
            "integer",
            minimum=int(current["left"]) + 1,
            maximum=1000,
        )
    elif stage == "element_bottom":
        question = _field(
            "element_bottom",
            "What is the element's normalized bottom coordinate?",
            "integer",
            minimum=int(current["top"]) + 1,
            maximum=1000,
        )
    elif stage == "element_status":
        question = _field(
            "element_status",
            "Is this element faithfully readable, or must it remain an explicit gap?",
            "choice",
            choices=["readable", "gap"],
        )
    elif stage == "element_content":
        question = _field("element_content", "What exact AI-readable content does this element contain?", "string")
    elif stage == "element_gap_reason":
        question = _field("element_gap_reason", "What visible condition prevents faithful reading of this element?", "string")
    elif stage == "element_relationship_obligation":
        question = _field(
            "element_relationship_obligation",
            "Does this recorded element participate in one or more purpose-relevant visible relationships?",
            "choice",
            choices=["yes", "no"],
        )
    elif stage == "obligation_resolution":
        question = _field(
            "obligation_resolution",
            "What is the next faithful step for this element's required relationship?",
            "choice",
            choices=[
                "use_recorded_endpoint",
                "record_visible_endpoint",
                "record_endpoint_gap",
            ],
        )
    elif stage == "obligation_role":
        question = _field(
            "obligation_role",
            "What visible role does the obligated element have in this relationship?",
            "choice",
            choices=["origin", "target"],
        )
    elif stage == "obligation_other_element":
        obligation = _pending_obligation(state)
        if obligation is None:
            raise InterviewError("relationship-obligation-missing")
        choices = [
            str(item["id"]) for item in state["elements"]
            if item["id"] != obligation["element_id"]
        ]
        question = _field(
            "obligation_other_element",
            "Which separately recorded element is the other visible endpoint?",
            "choice",
            choices=choices,
        )
    elif stage == "obligation_gap_kind":
        question = _field(
            "obligation_gap_kind",
            "What source-neutral kind best identifies the visible relationship that cannot be fully recorded?",
            "string",
        )
    elif stage == "obligation_gap_role":
        question = _field(
            "obligation_gap_role",
            "What visible role does the obligated element have in the incomplete relationship?",
            "choice",
            choices=["origin", "target", "unknown"],
        )
    elif stage == "obligation_gap_reason":
        question = _field(
            "obligation_gap_reason",
            "What visible condition prevents recording the other endpoint or the relationship faithfully?",
            "string",
        )
    elif stage == "relationship_more":
        question = _field(
            "relationship_more",
            "Is there another purpose-relevant visible relationship that has not been recorded?",
            "choice",
            choices=["yes", "no"],
        )
    elif stage == "relationship_kind":
        question = _field("relationship_kind", "What source-neutral kind best identifies this visible relationship?", "string")
    elif stage in {"relationship_origin_x", "relationship_origin_y", "relationship_target_x", "relationship_target_y"}:
        role = "origin" if "origin" in stage else "target"
        axis = "x" if stage.endswith("_x") else "y"
        question = _field(
            stage,
            f"What normalized {axis} coordinate lies inside the visible relationship {role}'s recorded element?",
            "integer",
            minimum=0,
            maximum=999,
        )
    elif stage == "relationship_binding_resolution":
        issue = current.get("binding_issue")
        if not isinstance(issue, dict):
            raise InterviewError("relationship-binding-issue-missing")
        choices = ["retry_coordinates", "record_endpoint_gap"]
        if issue.get("participant") != "relationship":
            choices.insert(1, "record_visible_endpoint")
        question = _field(
            "relationship_binding_resolution",
            "Code could not bind the submitted participant coordinates to exactly one valid recorded element. What is the faithful next step?",
            "choice",
            choices=choices,
        )
        question["binding_issue"] = issue
    elif stage == "relationship_binding_gap_reason":
        question = _field(
            "relationship_binding_gap_reason",
            "What visible condition prevents binding this relationship to two recorded elements faithfully?",
            "string",
        )
    elif stage == "relationship_visual_verdict":
        obligation = _pending_obligation(state)
        if obligation is None:
            raise InterviewError("relationship-obligation-missing")
        question = _field(
            "relationship_visual_verdict",
            "Based only on visible source evidence, are these proposed participants visibly connected for the currently required relationship?",
            "choice",
            choices=["supported", "not_supported", "unreadable"],
        )
        question["proposed_relationship"] = _proposed_relationship(state)
    elif stage == "relationship_visual_resolution":
        issue = current.get("verification_issue")
        if not isinstance(issue, dict):
            raise InterviewError("relationship-verification-issue-missing")
        question = _field(
            "relationship_visual_resolution",
            "Visible source evidence does not support the proposed pair. What is the faithful next step?",
            "choice",
            choices=[
                "retry_coordinates",
                "record_visible_endpoint",
                "record_endpoint_gap",
            ],
        )
        question["verification_issue"] = issue
    elif stage == "relationship_visual_endpoint_role":
        question = _field(
            "relationship_visual_endpoint_role",
            "Which proposed participant must be replaced by a newly recorded visible endpoint?",
            "choice",
            choices=["origin", "target"],
        )
    elif stage == "relationship_visual_gap_reason":
        question = _field(
            "relationship_visual_gap_reason",
            "What visible condition prevents confirming a supported relationship between these participants?",
            "string",
        )
    elif stage == "relationship_from":
        question = _field(
            "relationship_from",
            "Which recorded element is the relationship's visible origin?",
            "choice",
            choices=[str(item["id"]) for item in state["elements"]],
        )
    elif stage == "relationship_to":
        choices = [str(item["id"]) for item in state["elements"] if item["id"] != current["from_id"]]
        question = _field(
            "relationship_to",
            "Which recorded element is the relationship's visible target?",
            "choice",
            choices=choices,
        )
    elif stage == "relationship_status":
        question = _field(
            "relationship_status",
            "Is this relationship faithfully readable, or must it remain an explicit gap?",
            "choice",
            choices=["readable", "gap"],
        )
    elif stage == "relationship_description":
        question = _field("relationship_description", "What does this visible relationship establish?", "string")
    elif stage == "relationship_gap_reason":
        question = _field("relationship_gap_reason", "What visible condition prevents faithful reading of this relationship?", "string")
    else:
        raise InterviewError(f"interview-stage-unsupported:{stage}")
    if (
        contract >= 4
        and stage in {
            "element_left", "element_top", "element_right", "element_bottom",
        }
        and current.get("scan_region_id")
    ):
        region = _active_scan_region(state)
        if region is None or region["id"] != current["scan_region_id"]:
            raise InterviewError("scan-region-binding-invalid")
        question["coordinate_region"] = {
            "id": region["id"], "bounds": region["bounds"],
        }
    if contract >= 2:
        question["context"] = {"intake_purpose": purpose}
    if contract >= 4 and stage.startswith("region_"):
        region = _active_scan_region(state)
        if region is None:
            raise InterviewError("scan-region-missing")
        question["scan_region"] = {
            "id": region["id"], "bounds": region["bounds"],
        }
    return question


def _parse(question: dict[str, object], raw: str, state: dict[str, Any]) -> tuple[object | None, str | None]:
    value = raw.strip()
    field_id = str(question["id"])
    if not value:
        return None, f"{field_id}: a value is required"
    if "\n" in value or "\r" in value:
        return None, f"{field_id}: answer one field at a time"
    field_type = question["type"]
    if field_type == "choice":
        choices = question["choices"]
        if value not in choices:
            return None, f"{field_id}: choose one of: {', '.join(choices)}"
        if field_id == "element_more" and value == "no" and not state["elements"]:
            return None, "element_more: record at least one visible element; use status gap when it cannot be read"
        if field_id == "relationship_more" and value == "yes" and len(state["elements"]) < 2:
            return None, "relationship_more: at least two recorded elements are required before recording a relationship"
        if field_id == "obligation_resolution" and value == "use_recorded_endpoint" and len(state["elements"]) < 2:
            return None, "obligation_resolution: no other endpoint is recorded; choose record_visible_endpoint or record_endpoint_gap"
        return value, None
    if field_type == "integer":
        try:
            parsed = int(value)
        except ValueError:
            return None, f"{field_id}: enter one whole number"
        minimum = int(question["minimum"])
        maximum = int(question["maximum"])
        if not minimum <= parsed <= maximum:
            return None, f"{field_id}: enter a value from {minimum} through {maximum}"
        coordinate_region = question.get("coordinate_region")
        if isinstance(coordinate_region, dict):
            bounds = coordinate_region["bounds"]
            if field_id == "element_left" and not bounds[0] <= parsed < bounds[2]:
                return None, (
                    f"element_left: left coordinate {parsed} must be inside "
                    f"active {coordinate_region['id']} horizontal bounds "
                    f"{bounds[0]} through {bounds[2] - 1}"
                )
            if field_id == "element_top" and not bounds[1] <= parsed < bounds[3]:
                return None, (
                    f"element_top: top coordinate {parsed} must be inside "
                    f"active {coordinate_region['id']} vertical bounds "
                    f"{bounds[1]} through {bounds[3] - 1}"
                )
        return parsed, None
    return value, None


def _finish_element(
    state: dict[str, Any], field: str, value: str, *, contract: int,
) -> None:
    current = state["current"]
    current[field] = value
    status = str(current["status"])
    element_id = f"element-{len(state['elements']) + 1:06d}"
    element: dict[str, Any] = {
        "id": element_id,
        "kind": current["kind"],
        "region": [current["left"], current["top"], current["right"], current["bottom"]],
        "status": status,
        "content": current.get("content", "") if status == "readable" else "",
        "gap_reason": current.get("gap_reason", "") if status == "gap" else "",
    }
    if contract >= 4:
        scan_region_id = current.get("scan_region_id")
        element["capture_scope"] = scan_region_id or "relationship_endpoint"
        if scan_region_id:
            element["scan_region_id"] = scan_region_id
            region = _active_scan_region(state)
            if region is None or region["id"] != scan_region_id:
                raise InterviewError("scan-region-binding-invalid")
            region["element_ids"].append(element_id)
    state["elements"].append(element)
    state["current"] = (
        {
            "element_id": element_id,
            "return_stage": current.get("return_stage", "element_more"),
        }
        if contract >= 3 else {}
    )
    state["stage"] = (
        "element_relationship_obligation" if contract >= 3
        else "element_more"
    )


def _resolve_obligations(
    state: dict[str, Any], relationship_id: str, element_ids: set[str],
) -> None:
    for obligation in state["relationship_obligations"]:
        if (
            obligation["status"] == "pending"
            and obligation["element_id"] in element_ids
        ):
            obligation.update({
                "status": "resolved",
                "resolution": "relationship",
                "relationship_id": relationship_id,
            })


def _resolve_current_obligation(
    state: dict[str, Any], relationship_id: str, resolution: str,
) -> None:
    obligation = _pending_obligation(state)
    if obligation is None:
        raise InterviewError("relationship-obligation-missing")
    obligation.update({
        "status": "resolved",
        "resolution": resolution,
        "relationship_id": relationship_id,
    })


def _next_relationship_stage(state: dict[str, Any]) -> str:
    return "obligation_resolution" if _pending_obligation(state) else "relationship_more"


def _finish_relationship(
    state: dict[str, Any], field: str, value: str, *, contract: int,
) -> None:
    current = state["current"]
    current[field] = value
    status = str(current["status"])
    relationship_id = f"relationship-{len(state['relationships']) + 1:06d}"
    relationship = {
        "id": relationship_id,
        "kind": current["kind"],
        "from_id": current.get("origin_id", current.get("from_id")),
        "to_id": current.get("target_id", current.get("to_id")),
        "status": status,
        "description": current.get("description", "") if status == "readable" else "",
        "gap_reason": current.get("gap_reason", "") if status == "gap" else "",
    }
    if "origin_point" in current and "target_point" in current:
        relationship.update({
            "binding_method": "coordinate_unique_containment",
            "origin_point": current["origin_point"],
            "target_point": current["target_point"],
        })
    if contract >= 6:
        if current.get("visual_verification") != "supported":
            raise InterviewError("relationship-visual-verification-missing")
        obligation = _pending_obligation(state)
        if obligation is None:
            raise InterviewError("relationship-obligation-missing")
        relationship.update({
            "visual_verification": "supported",
            "verified_obligation_id": obligation["id"],
            "verified_element_id": obligation["element_id"],
        })
    state["relationships"].append(relationship)
    if contract >= 6:
        _resolve_current_obligation(state, relationship_id, "relationship")
    else:
        _resolve_obligations(
            state, relationship_id,
            {str(relationship["from_id"]), str(relationship["to_id"])},
        )
    state["current"] = {}
    state["stage"] = _next_relationship_stage(state)


def _finish_binding_gap(state: dict[str, Any], reason: str) -> None:
    current = state["current"]
    relationship_id = f"relationship-{len(state['relationships']) + 1:06d}"
    relationship = {
        "id": relationship_id,
        "kind": current["kind"],
        "from_id": current.get("origin_id"),
        "to_id": current.get("target_id"),
        "status": "gap",
        "description": "",
        "gap_reason": reason,
        "binding_method": "coordinate_unique_containment",
        "binding_issue": current["binding_issue"],
    }
    if "origin_point" in current:
        relationship["origin_point"] = current["origin_point"]
    if "target_point" in current:
        relationship["target_point"] = current["target_point"]
    state["relationships"].append(relationship)
    obligation = _pending_obligation(state)
    if obligation is not None:
        obligation.update({
            "status": "resolved",
            "resolution": "gap",
            "relationship_id": relationship_id,
        })
    state["current"] = {}
    state["stage"] = _next_relationship_stage(state)


def _finish_visual_gap(state: dict[str, Any], reason: str) -> None:
    current = state["current"]
    verdict = str(current.get("visual_verification"))
    if verdict not in {"not_supported", "unreadable"}:
        raise InterviewError("relationship-visual-gap-verdict-invalid")
    relationship_id = f"relationship-{len(state['relationships']) + 1:06d}"
    relationship: dict[str, Any] = {
        "id": relationship_id,
        "kind": current["kind"],
        "from_id": current["origin_id"],
        "to_id": current["target_id"],
        "status": "gap",
        "description": "",
        "gap_reason": reason,
        "binding_method": "coordinate_unique_containment",
        "origin_point": current["origin_point"],
        "target_point": current["target_point"],
        "visual_verification": verdict,
    }
    if "verification_issue" in current:
        relationship["verification_issue"] = current["verification_issue"]
    obligation = _pending_obligation(state)
    if obligation is None:
        raise InterviewError("relationship-obligation-missing")
    relationship.update({
        "verified_obligation_id": obligation["id"],
        "verified_element_id": obligation["element_id"],
    })
    state["relationships"].append(relationship)
    _resolve_current_obligation(state, relationship_id, "gap")
    state["current"] = {}
    state["stage"] = _next_relationship_stage(state)


def _proposed_relationship(state: dict[str, Any]) -> dict[str, Any]:
    current = state["current"]
    obligation = _pending_obligation(state)
    if obligation is None:
        raise InterviewError("relationship-obligation-missing")
    participants: dict[str, Any] = {}
    for role in ("origin", "target"):
        element_id = str(current[f"{role}_id"])
        element = next((
            item for item in state["elements"] if item["id"] == element_id
        ), None)
        if element is None:
            raise InterviewError(f"relationship-{role}-missing")
        participants[role] = {
            "element_id": element_id,
            "point": current[f"{role}_point"],
            "bounds": element["region"],
            "kind": element["kind"],
            "status": element["status"],
            "content": element["content"],
            "gap_reason": element["gap_reason"],
        }
    return {
        "kind": current["kind"],
        "required_obligation_id": obligation["id"],
        "required_element_id": obligation["element_id"],
        **participants,
    }


def _bind_relationship_point(
    state: dict[str, Any], role: str, y: int, *, contract: int,
) -> None:
    current = state["current"]
    x = int(current[f"{role}_x"])
    matches = _elements_at_point(state, x, y)
    current[f"{role}_point"] = [x, y]
    if len(matches) != 1:
        current["binding_issue"] = {
            "participant": role,
            "point": [x, y],
            "matching_element_ids": [str(item["id"]) for item in matches],
            "reason": "no_unique_recorded_element",
        }
        state["stage"] = "relationship_binding_resolution"
        return
    element_id = str(matches[0]["id"])
    if role == "target" and element_id == current.get("origin_id"):
        current["binding_issue"] = {
            "participant": role,
            "point": [x, y],
            "matching_element_ids": [element_id],
            "reason": "same_element_as_origin",
        }
        state["stage"] = "relationship_binding_resolution"
        return
    current[f"{role}_id"] = element_id
    if role == "origin":
        state["stage"] = "relationship_target_x"
        return
    obligation = _pending_obligation(state)
    participants = {str(current["origin_id"]), str(current["target_id"])}
    if obligation is not None and str(obligation["element_id"]) not in participants:
        current["binding_issue"] = {
            "participant": "relationship",
            "origin_id": current["origin_id"],
            "target_id": current["target_id"],
            "required_element_id": obligation["element_id"],
            "reason": "required_element_not_bound",
        }
        state["stage"] = "relationship_binding_resolution"
        return
    state["stage"] = (
        "relationship_visual_verdict" if contract >= 6
        else "relationship_status"
    )


def _finish_obligation_gap(state: dict[str, Any], reason: str) -> None:
    obligation = _pending_obligation(state)
    if obligation is None:
        raise InterviewError("relationship-obligation-missing")
    relationship_id = f"relationship-{len(state['relationships']) + 1:06d}"
    role = str(state["current"]["role"])
    element_id = str(obligation["element_id"])
    state["relationships"].append({
        "id": relationship_id,
        "kind": state["current"]["kind"],
        "from_id": element_id if role == "origin" else None,
        "to_id": element_id if role == "target" else None,
        "participant_id": element_id,
        "status": "gap",
        "description": "",
        "gap_reason": reason,
    })
    obligation.update({
        "status": "resolved",
        "resolution": "gap",
        "relationship_id": relationship_id,
    })
    state["current"] = {}
    state["stage"] = _next_relationship_stage(state)


def _advance(
    state: dict[str, Any], field_id: str, value: object, *, contract: int,
) -> None:
    current = state["current"]
    if field_id == "reader_model":
        state["reader"]["model"] = value
        state["stage"] = "reader_harness"
    elif field_id == "reader_harness":
        state["reader"]["harness"] = value
        state["stage"] = (
            "region_element_more" if contract >= 4 else "element_more"
        )
    elif field_id == "region_element_more":
        region = _active_scan_region(state)
        if region is None:
            raise InterviewError("scan-region-missing")
        if value == "yes":
            state["current"] = {
                "return_stage": "region_element_more",
                "scan_region_id": region["id"],
            }
            state["stage"] = "element_kind"
        elif value == "gap":
            state["stage"] = "region_gap_reason"
        else:
            region["status"] = "scanned"
            _advance_scan_region(state)
    elif field_id == "region_gap_reason":
        region = _active_scan_region(state)
        if region is None:
            raise InterviewError("scan-region-missing")
        region.update({"status": "gap", "gap_reason": str(value)})
        _advance_scan_region(state)
    elif field_id == "element_more":
        state["stage"] = (
            "element_kind" if value == "yes"
            else _next_relationship_stage(state)
        )
    elif field_id == "element_kind":
        current["kind"] = value
        state["stage"] = "element_left"
    elif field_id in {"element_left", "element_top", "element_right", "element_bottom"}:
        current[field_id.removeprefix("element_")] = value
        order = {
            "element_left": "element_top",
            "element_top": "element_right",
            "element_right": "element_bottom",
            "element_bottom": "element_status",
        }
        state["stage"] = order[field_id]
    elif field_id == "element_status":
        current["status"] = value
        state["stage"] = "element_content" if value == "readable" else "element_gap_reason"
    elif field_id == "element_content":
        _finish_element(state, "content", str(value), contract=contract)
    elif field_id == "element_gap_reason":
        _finish_element(state, "gap_reason", str(value), contract=contract)
    elif field_id == "element_relationship_obligation":
        element_id = str(current["element_id"])
        return_stage = str(current.get("return_stage", "element_more"))
        if value == "yes":
            state["relationship_obligations"].append({
                "id": f"obligation-{len(state['relationship_obligations']) + 1:06d}",
                "element_id": element_id,
                "status": "pending",
                "resolution": None,
                "relationship_id": None,
            })
        relationship_draft = state.get("relationship_draft")
        if return_stage.startswith("relationship_") and isinstance(relationship_draft, dict):
            state["current"] = relationship_draft
            state["relationship_draft"] = None
            state["stage"] = return_stage
        else:
            state["current"] = {}
            state["stage"] = (
                _next_relationship_stage(state)
                if return_stage == "obligation_resolution"
                else return_stage
            )
    elif field_id == "obligation_resolution":
        state["current"] = {}
        if value == "use_recorded_endpoint":
            state["stage"] = "relationship_kind"
        elif value == "record_visible_endpoint":
            state["current"] = {
                "return_stage": "obligation_resolution",
                "capture_scope": "relationship_endpoint",
            }
            state["stage"] = "element_kind"
        else:
            state["stage"] = "obligation_gap_kind"
    elif field_id == "obligation_role":
        obligation = _pending_obligation(state)
        if obligation is None:
            raise InterviewError("relationship-obligation-missing")
        current["role"] = value
        current["from_id" if value == "origin" else "to_id"] = obligation["element_id"]
        state["stage"] = "obligation_other_element"
    elif field_id == "obligation_other_element":
        role = str(current["role"])
        current["to_id" if role == "origin" else "from_id"] = value
        state["stage"] = "relationship_status"
    elif field_id == "obligation_gap_kind":
        current["kind"] = value
        state["stage"] = "obligation_gap_role"
    elif field_id == "obligation_gap_role":
        current["role"] = value
        state["stage"] = "obligation_gap_reason"
    elif field_id == "obligation_gap_reason":
        _finish_obligation_gap(state, str(value))
    elif field_id == "relationship_more":
        state["stage"] = "relationship_kind" if value == "yes" else "complete"
    elif field_id == "relationship_kind":
        current["kind"] = value
        state["stage"] = (
            "relationship_origin_x" if contract >= 5
            else "obligation_role" if _pending_obligation(state)
            else "relationship_from"
        )
    elif field_id in {"relationship_origin_x", "relationship_target_x"}:
        current[field_id.removeprefix("relationship_")] = value
        state["stage"] = field_id.removesuffix("_x") + "_y"
    elif field_id == "relationship_origin_y":
        current["origin_y"] = value
        _bind_relationship_point(state, "origin", int(value), contract=contract)
    elif field_id == "relationship_target_y":
        current["target_y"] = value
        _bind_relationship_point(state, "target", int(value), contract=contract)
    elif field_id == "relationship_binding_resolution":
        issue = current.pop("binding_issue")
        role = str(issue["participant"])
        if value == "retry_coordinates":
            if role == "relationship":
                for key in (
                    "origin_x", "origin_y", "origin_id", "origin_point",
                    "target_x", "target_y", "target_id", "target_point",
                ):
                    current.pop(key, None)
                state["stage"] = "relationship_origin_x"
            else:
                for key in (f"{role}_x", f"{role}_y", f"{role}_id", f"{role}_point"):
                    current.pop(key, None)
                state["stage"] = f"relationship_{role}_x"
        elif value == "record_visible_endpoint":
            if role == "relationship":
                raise InterviewError("relationship-binding-capture-invalid")
            for key in (f"{role}_x", f"{role}_y", f"{role}_id", f"{role}_point"):
                current.pop(key, None)
            state["relationship_draft"] = current
            state["current"] = {
                "return_stage": f"relationship_{role}_x",
                "capture_scope": "relationship_endpoint",
            }
            state["stage"] = "element_kind"
        else:
            current["binding_issue"] = issue
            state["stage"] = "relationship_binding_gap_reason"
    elif field_id == "relationship_binding_gap_reason":
        _finish_binding_gap(state, str(value))
    elif field_id == "relationship_visual_verdict":
        current["visual_verification"] = value
        if value == "supported":
            state["stage"] = "relationship_status"
        elif value == "not_supported":
            current["verification_issue"] = {
                "origin_id": current["origin_id"],
                "target_id": current["target_id"],
                "required_element_id": _pending_obligation(state)["element_id"],
                "reason": "visible_connection_not_supported",
            }
            state["stage"] = "relationship_visual_resolution"
        else:
            state["stage"] = "relationship_visual_gap_reason"
    elif field_id == "relationship_visual_resolution":
        if value == "retry_coordinates":
            for key in (
                "origin_x", "origin_y", "origin_id", "origin_point",
                "target_x", "target_y", "target_id", "target_point",
                "visual_verification", "verification_issue",
            ):
                current.pop(key, None)
            state["stage"] = "relationship_origin_x"
        elif value == "record_visible_endpoint":
            state["stage"] = "relationship_visual_endpoint_role"
        else:
            state["stage"] = "relationship_visual_gap_reason"
    elif field_id == "relationship_visual_endpoint_role":
        role = str(value)
        for key in (f"{role}_x", f"{role}_y", f"{role}_id", f"{role}_point"):
            current.pop(key, None)
        current.pop("visual_verification", None)
        current.pop("verification_issue", None)
        state["relationship_draft"] = current
        state["current"] = {
            "return_stage": f"relationship_{role}_x",
            "capture_scope": "relationship_endpoint",
        }
        state["stage"] = "element_kind"
    elif field_id == "relationship_visual_gap_reason":
        _finish_visual_gap(state, str(value))
    elif field_id == "relationship_from":
        current["from_id"] = value
        state["stage"] = "relationship_to"
    elif field_id == "relationship_to":
        current["to_id"] = value
        state["stage"] = "relationship_status"
    elif field_id == "relationship_status":
        current["status"] = value
        state["stage"] = "relationship_description" if value == "readable" else "relationship_gap_reason"
    elif field_id == "relationship_description":
        _finish_relationship(state, "description", str(value), contract=contract)
    elif field_id == "relationship_gap_reason":
        _finish_relationship(state, "gap_reason", str(value), contract=contract)
    else:
        raise InterviewError(f"interview-field-unsupported:{field_id}")


def _replay(
    entries: list[dict[str, object]],
    *,
    purpose: str,
    contract: int,
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state = _initial_state(contract=contract)
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        event = entry.get("event")
        if event == "question_asked":
            expected = _question(state, purpose=purpose, contract=contract)
            if pending is not None or expected is None or entry.get("question") != expected:
                raise InterviewError(f"interview-question-invalid:{entry['sequence']}")
            pending = expected
        elif event == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise InterviewError(f"interview-answer-unbound:{entry['sequence']}")
            raw = entry.get("raw")
            if not isinstance(raw, str):
                raise InterviewError(f"interview-answer-invalid:{entry['sequence']}")
            parsed, error = _parse(pending, raw, state)
            accepted = error is None
            if (
                entry.get("accepted") is not accepted
                or entry.get("error") != error
                or entry.get("parsed") != parsed
            ):
                raise InterviewError(f"interview-answer-changed:{entry['sequence']}")
            if accepted:
                _advance(
                    state, str(pending["id"]), parsed, contract=contract,
                )
            pending = None
        elif event == "interview_completed":
            if (
                pending is not None
                or _question(state, purpose=purpose, contract=contract) is not None
                or completed
            ):
                raise InterviewError(f"interview-completion-invalid:{entry['sequence']}")
            completed = True
        else:
            raise InterviewError(f"interview-event-unsupported:{entry['sequence']}")
    return state, pending, completed


def _prompt(question: dict[str, object], state: dict[str, Any]) -> str:
    lines: list[str] = []
    context = question.get("context")
    if isinstance(context, dict):
        lines.append(f"Intake purpose: {context['intake_purpose']}")
    scan_region = question.get("scan_region")
    if isinstance(scan_region, dict):
        lines.append(
            f"Active source region: {scan_region['id']} normalized bounds "
            f"{scan_region['bounds']}"
        )
    coordinate_region = question.get("coordinate_region")
    if isinstance(coordinate_region, dict):
        lines.append(
            "Element left/top anchor must be inside active source region: "
            f"{coordinate_region['id']} normalized bounds "
            f"{coordinate_region['bounds']}"
        )
    binding_issue = question.get("binding_issue")
    if isinstance(binding_issue, dict):
        lines.append(
            "Coordinate binding issue: "
            + json.dumps(binding_issue, sort_keys=True)
        )
    verification_issue = question.get("verification_issue")
    if isinstance(verification_issue, dict):
        lines.append(
            "Visual verification issue: "
            + json.dumps(verification_issue, sort_keys=True)
        )
    proposed_relationship = question.get("proposed_relationship")
    if isinstance(proposed_relationship, dict):
        lines.append(
            "Proposed relationship participants: "
            + json.dumps(proposed_relationship, sort_keys=True)
        )
    lines.extend([f"Question: {question['prompt']}", f"Answer type: {question['type']}"])
    if question["type"] == "choice":
        lines.append("Allowed values: " + ", ".join(question["choices"]))
    if question["type"] == "integer":
        lines.append(f"Allowed range: {question['minimum']} through {question['maximum']}")
    if str(question["id"]) in {
        "relationship_from", "relationship_to", "obligation_other_element",
    } and state["elements"]:
        lines.append("Recorded elements: " + "; ".join(
            f"{item['id']}={item['kind']}:{item['content'] or item['gap_reason']}"
            for item in state["elements"]
        ))
    obligation = _pending_obligation(state)
    if str(question["id"]).startswith("obligation_") and obligation:
        lines.append(
            "Required relationship for element: "
            f"{obligation['element_id']}"
        )
    lines.append("Answer: ")
    return "\n".join(lines)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise InterviewError("interview-input-ended")
    return value.rstrip("\n")


def _terminal_output(message: str) -> None:
    print(message, file=sys.stderr)


def run(
    attempt_dir: Path,
    *,
    source_sha256: str,
    purpose: str,
    contract: int = CONTRACT,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Resume the journal and return the code-assembled projection."""

    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    projection_path = attempt_dir / "projection.json"
    read = input_fn or _terminal_input
    write = output_fn or _terminal_output

    while True:
        entries = _read_journal(journal_path)
        state, pending, completed = _replay(
            entries,
            purpose=purpose,
            contract=contract,
        )
        projection = {
            "schema_version": contract,
            "source_sha256": source_sha256,
            "purpose_quote": purpose,
            "elements": state["elements"],
            "relationships": state["relationships"],
            "reader": state["reader"],
        }
        if contract >= 3:
            projection["relationship_obligations"] = state["relationship_obligations"]
        if contract >= 4:
            projection["scan_regions"] = state["scan_regions"]
        projection_bytes = json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        if completed:
            completion = entries[-1]
            if (
                completion.get("projection_path") != "projection.json"
                or completion.get("projection_sha256") != _digest(projection_bytes)
            ):
                raise InterviewError("completed-projection-record-invalid")
            if not projection_path.exists():
                projection_path.write_bytes(projection_bytes)
            try:
                recorded = projection_path.read_bytes()
            except OSError as error:
                raise InterviewError("completed-projection-unavailable") from error
            if recorded != projection_bytes:
                raise InterviewError("completed-projection-changed")
            return projection

        question = pending or _question(state, purpose=purpose, contract=contract)
        if question is None:
            if projection_path.exists():
                raise InterviewError("unbound-projection-artifact")
            _append(journal_path, "interview_completed", {
                "projection_path": "projection.json",
                "projection_sha256": _digest(projection_bytes),
            })
            projection_path.write_bytes(projection_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, state))
        parsed, error = _parse(question, raw, state)
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
    source_sha256: str,
    purpose: str,
    contract: int = CONTRACT,
) -> tuple[dict[str, object], str, str]:
    """Return the completed projection and hashes after replaying every answer."""

    journal_path = attempt_dir / "interview.jsonl"
    projection = run(
        attempt_dir,
        source_sha256=source_sha256,
        purpose=purpose,
        contract=contract,
        input_fn=lambda _prompt: (_ for _ in ()).throw(InterviewError("interview-not-complete")),
        output_fn=lambda _message: None,
    )
    projection_path = attempt_dir / "projection.json"
    return projection, _digest(journal_path.read_bytes()), _digest(projection_path.read_bytes())
