#!/usr/bin/env python3
"""Run a code-controlled visual projection interview."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

CONTRACT = 13
SUPPORTED_CONTRACTS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, CONTRACT}
SCAN_GRID_SIZE = 4
REGION_CONTEXT_MARGIN = 50
REGION_EVIDENCE_ADAPTER_V1 = {
    "name": "pillow_exif_transpose_png_crop",
    "version": 1,
}
REGION_EVIDENCE_ADAPTER = {
    "name": "pillow_exif_transpose_png_context_crop",
    "version": 1,
}
REGION_OWNERSHIP_GUIDE_ADAPTER = {
    "name": "pillow_owned_core_context_guide",
    "version": 1,
    "owned_outline_rgba": [0, 255, 0, 255],
    "context_overlay_rgba": [0, 0, 0, 128],
}
ENDPOINT_CROP_EVIDENCE_ADAPTER = {
    "name": "pillow_exif_transpose_png_exact_element_crop",
    "version": 1,
}


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
    state = {
        "stage": "reader_model",
        "reader": {},
        "elements": [],
        "relationships": [],
        "relationship_obligations": [],
        "scan_regions": _scan_regions() if contract >= 4 else [],
        "scan_region_index": 0,
        "region_outcomes": [],
        "relationship_draft": None,
        "element_supersession_pending": None,
        "spatial_identity_refinement_pending": None,
        "spatial_identity_refinement_enabled": False,
        "overlap_identity_selection_enabled": False,
        "required_participant_binding_enabled": False,
        "endpoint_crop_verification_enabled": False,
        "existing_participant_crop_verification_enabled": False,
        "contextual_endpoint_verification_enabled": False,
        "endpoint_context_evidence_enabled": False,
        "endpoint_selector_context_enabled": False,
        "endpoint_identity_context_choice_enabled": False,
        "negative_context_replacement_enabled": False,
        "failed_participant_recovery_enabled": False,
        "locked_participant_replacement_blocked_enabled": False,
        "required_participant_replacement_identity_enabled": False,
        "required_participant_content_identity_separation_enabled": False,
        "_replacement_identity_migration_applied": False,
        "_context_selector_candidates": {},
        "rejected_endpoint_reuse_blocked_enabled": False,
        "unreadable_participant_reuse_blocked_enabled": False,
        "rejected_endpoint_collision_excluded_enabled": False,
        "context_deferral_pending": None,
        "current": {},
    }
    if contract >= 11:
        for region in state["scan_regions"]:
            region["deferred_context_candidates"] = []
            if contract >= 12:
                region["context_candidate_obligations"] = []
    return state


def _pending_obligation(state: dict[str, Any]) -> dict[str, Any] | None:
    return next((
        item for item in state["relationship_obligations"]
        if item["status"] == "pending"
    ), None)


def _active_scan_region(state: dict[str, Any]) -> dict[str, Any] | None:
    index = int(state["scan_region_index"])
    regions = state["scan_regions"]
    return regions[index] if index < len(regions) else None


def _context_space_available(evidence: dict[str, Any]) -> bool:
    core = evidence.get("core_normalized_bounds")
    visible = evidence.get("evidence_normalized_bounds")
    if (
        not isinstance(core, list)
        or len(core) != 4
        or not all(isinstance(value, int) for value in core)
        or not isinstance(visible, list)
        or len(visible) != 4
        or not all(isinstance(value, int) for value in visible)
    ):
        raise InterviewError("context-ownership-bounds-missing")
    return core != visible


def _pending_context_obligation(
    state: dict[str, Any],
) -> dict[str, Any] | None:
    region = _active_scan_region(state)
    if region is None:
        return None
    obligations = region.get("context_candidate_obligations")
    if not isinstance(obligations, list):
        return None
    return next((
        item for item in obligations if item.get("status") == "pending"
    ), None)


def _context_obligation_by_id(
    state: dict[str, Any], obligation_id: str,
) -> dict[str, Any]:
    matches = [
        obligation
        for region in state["scan_regions"]
        for obligation in region.get("context_candidate_obligations", [])
        if obligation.get("id") == obligation_id
    ]
    if len(matches) != 1:
        raise InterviewError("context-obligation-identity-invalid")
    return matches[0]


def _next_region_stage(state: dict[str, Any]) -> str:
    return (
        "context_obligation_resolution"
        if _pending_context_obligation(state) is not None
        else "region_element_more"
    )


def _region_outcome(region: dict[str, Any]) -> dict[str, object]:
    evidence = region.get("evidence")
    if not isinstance(evidence, dict):
        raise InterviewError("region-evidence-missing")
    result: dict[str, object] = {
        "region_id": region["id"],
        "status": region["status"],
        "element_ids": region["element_ids"],
        "gap_reason": region["gap_reason"],
        "crop_path": evidence["crop_path"],
        "crop_sha256": evidence["crop_sha256"],
    }
    if "deferred_context_candidates" in region:
        result["deferred_context_candidates"] = region[
            "deferred_context_candidates"
        ]
    if "context_candidate_obligations" in region:
        result["context_candidate_obligations"] = region[
            "context_candidate_obligations"
        ]
    return result


def _projection(
    state: dict[str, Any], *, source_sha256: str, purpose: str, contract: int,
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": contract,
        "source_sha256": source_sha256,
        "purpose_quote": purpose,
        "elements": state["elements"],
        "relationships": state["relationships"],
        "reader": state["reader"],
    }
    if contract >= 3:
        result["relationship_obligations"] = state["relationship_obligations"]
    if contract >= 4:
        result["scan_regions"] = state["scan_regions"]
    return result


def _elements_at_point(
    state: dict[str, Any], x: int, y: int,
) -> list[dict[str, Any]]:
    return [
        item for item in state["elements"]
        if (
            not _participant_reuse_blocked(state, item)
            and
            int(item["region"][0]) <= x < int(item["region"][2])
            and int(item["region"][1]) <= y < int(item["region"][3])
        )
    ]


def _element_collision_candidates(
    state: dict[str, Any], current: dict[str, Any],
) -> list[dict[str, Any]]:
    candidate = [
        int(current["left"]), int(current["top"]),
        int(current["right"]), int(current["bottom"]),
    ]
    return [
        item for item in state["elements"]
        if (
            (
                state.get("rejected_endpoint_collision_excluded_enabled")
                is not True
                or current.get("capture_scope") != "relationship_endpoint"
                or not _endpoint_was_rejected_v1(item)
            )
            and
            max(candidate[0], int(item["region"][0]))
            < min(candidate[2], int(item["region"][2]))
            and max(candidate[1], int(item["region"][1]))
            < min(candidate[3], int(item["region"][3]))
        )
    ]


def _element_by_id(
    state: dict[str, Any], element_id: str,
) -> dict[str, Any]:
    element = next((
        item for item in state["elements"] if item["id"] == element_id
    ), None)
    if element is None:
        raise InterviewError("element-supersession-target-missing")
    return element


def _advance_scan_region(state: dict[str, Any]) -> None:
    state["scan_region_index"] += 1
    state["stage"] = (
        _next_region_stage(state) if _active_scan_region(state) is not None
        else _next_relationship_stage(state)
    )


def _evidence_path(attempt_dir: Path, region_id: str) -> tuple[str, Path]:
    relative = f"region-evidence/{region_id}.png"
    path = (attempt_dir / relative).resolve()
    try:
        path.relative_to(attempt_dir.resolve())
    except ValueError as error:
        raise InterviewError("region-evidence-path-invalid") from error
    return relative, path


def _ownership_guide_path(
    attempt_dir: Path, region_id: str,
) -> tuple[str, Path]:
    relative = f"region-evidence/{region_id}.ownership.png"
    path = (attempt_dir / relative).resolve()
    try:
        path.relative_to(attempt_dir.resolve())
    except ValueError as error:
        raise InterviewError("region-ownership-guide-path-invalid") from error
    return relative, path


def _region_evidence_attachments(
    attempt_dir: Path, region: dict[str, Any], *, contract: int,
) -> Path | tuple[Path, Path]:
    crop = _evidence_path(attempt_dir, str(region["id"]))[1]
    if contract < 11:
        return crop
    guide = _ownership_guide_path(attempt_dir, str(region["id"]))[1]
    return crop, guide


def _context_bounds(core_bounds: list[int]) -> list[int]:
    left, top, right, bottom = core_bounds
    return [
        max(0, left - REGION_CONTEXT_MARGIN),
        max(0, top - REGION_CONTEXT_MARGIN),
        min(1000, right + REGION_CONTEXT_MARGIN),
        min(1000, bottom + REGION_CONTEXT_MARGIN),
    ]


def _forward_context_bounds(core_bounds: list[int]) -> list[int]:
    left, top, right, bottom = core_bounds
    return [
        left,
        top,
        min(1000, right + REGION_CONTEXT_MARGIN),
        min(1000, bottom + REGION_CONTEXT_MARGIN),
    ]


def _evidence_normalized_bounds(
    core_bounds: list[int], *, contract: int,
) -> list[int]:
    return (
        _forward_context_bounds(core_bounds)
        if contract >= 12
        else _context_bounds(core_bounds)
    )


def _region_for_point(
    state: dict[str, Any], x: int, y: int,
) -> dict[str, Any]:
    region = next((
        item for item in state["scan_regions"]
        if (
            int(item["bounds"][0]) <= x < int(item["bounds"][2])
            and int(item["bounds"][1]) <= y < int(item["bounds"][3])
        )
    ), None)
    if region is None:
        raise InterviewError("context-deferral-owner-missing")
    return region


def _pixel_bounds(
    normalized_bounds: list[int], *, width: int, height: int,
) -> list[int]:
    left, top, right, bottom = normalized_bounds
    return [
        width * left // 1000,
        height * top // 1000,
        (width * right + 999) // 1000,
        (height * bottom + 999) // 1000,
    ]


def _ownership_core_in_crop(
    core_pixel_bounds: list[int], crop_pixel_bounds: list[int],
) -> list[int]:
    return [
        core_pixel_bounds[0] - crop_pixel_bounds[0],
        core_pixel_bounds[1] - crop_pixel_bounds[1],
        core_pixel_bounds[2] - crop_pixel_bounds[0],
        core_pixel_bounds[3] - crop_pixel_bounds[1],
    ]


def _render_ownership_guide(
    cropped: Image.Image, core_in_crop: list[int],
) -> bytes:
    guide = cropped.convert("RGBA")
    overlay = Image.new("RGBA", guide.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = guide.size
    left, top, right, bottom = core_in_crop
    shade = tuple(REGION_OWNERSHIP_GUIDE_ADAPTER["context_overlay_rgba"])
    if top > 0:
        draw.rectangle((0, 0, width, top - 1), fill=shade)
    if bottom < height:
        draw.rectangle((0, bottom, width, height), fill=shade)
    if left > 0:
        draw.rectangle((0, top, left - 1, bottom - 1), fill=shade)
    if right < width:
        draw.rectangle((right, top, width, bottom - 1), fill=shade)
    guide = Image.alpha_composite(guide, overlay)
    line_width = max(1, min(width, height) // 150)
    ImageDraw.Draw(guide).rectangle(
        (left, top, right - 1, bottom - 1),
        outline=tuple(REGION_OWNERSHIP_GUIDE_ADAPTER["owned_outline_rgba"]),
        width=line_width,
    )
    output = BytesIO()
    guide.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _verify_region_evidence_files(
    attempt_dir: Path, state: dict[str, Any], *, source_sha256: str,
) -> None:
    for region in state["scan_regions"]:
        evidence = region.get("evidence")
        if evidence is None:
            continue
        if not isinstance(evidence, dict):
            raise InterviewError("region-evidence-invalid")
        relative, path = _evidence_path(attempt_dir, str(region["id"]))
        if (
            evidence.get("source_sha256") != source_sha256
            or evidence.get("crop_path") != relative
            or not path.is_file()
        ):
            raise InterviewError(f"region-evidence-unavailable:{region['id']}")
        try:
            crop_bytes = path.read_bytes()
        except OSError as error:
            raise InterviewError(f"region-evidence-unavailable:{region['id']}") from error
        if _digest(crop_bytes) != evidence.get("crop_sha256"):
            raise InterviewError(f"region-evidence-changed:{region['id']}")
        guide_relative = evidence.get("guide_path")
        if guide_relative is None:
            continue
        expected_relative, guide_path = _ownership_guide_path(
            attempt_dir, str(region["id"]),
        )
        if guide_relative != expected_relative or not guide_path.is_file():
            raise InterviewError(
                f"region-ownership-guide-unavailable:{region['id']}"
            )
        try:
            guide_bytes = guide_path.read_bytes()
        except OSError as error:
            raise InterviewError(
                f"region-ownership-guide-unavailable:{region['id']}"
            ) from error
        if _digest(guide_bytes) != evidence.get("guide_sha256"):
            raise InterviewError(
                f"region-ownership-guide-changed:{region['id']}"
            )


def _valid_region_evidence_entry(
    entry: dict[str, object], region: dict[str, Any], *, contract: int,
) -> bool:
    source_pixel_size = entry.get("source_pixel_size")
    if (
        contract < 8
        or entry.get("region_id") != region["id"]
        or not isinstance(entry.get("source_sha256"), str)
        or len(str(entry["source_sha256"])) != 64
        or not isinstance(source_pixel_size, list)
        or len(source_pixel_size) != 2
        or not all(
            isinstance(value, int) and value > 0
            for value in source_pixel_size
        )
        or entry.get("crop_path") != f"region-evidence/{region['id']}.png"
        or not isinstance(entry.get("crop_sha256"), str)
        or len(str(entry["crop_sha256"])) != 64
    ):
        return False
    width, height = [int(value) for value in source_pixel_size]
    core_normalized_bounds = [int(value) for value in region["bounds"]]
    core_pixel_bounds = _pixel_bounds(
        core_normalized_bounds, width=width, height=height,
    )
    if contract >= 9:
        evidence_normalized_bounds = _evidence_normalized_bounds(
            core_normalized_bounds, contract=contract,
        )
        context_valid = (
            entry.get("core_normalized_bounds") == core_normalized_bounds
            and entry.get("evidence_normalized_bounds")
            == evidence_normalized_bounds
            and entry.get("core_pixel_bounds") == core_pixel_bounds
            and entry.get("pixel_bounds") == _pixel_bounds(
                evidence_normalized_bounds, width=width, height=height,
            )
            and entry.get("adapter") == REGION_EVIDENCE_ADAPTER
        )
        if not context_valid or contract < 11:
            return context_valid
        pixel_bounds = _pixel_bounds(
            evidence_normalized_bounds, width=width, height=height,
        )
        return (
            entry.get("ownership_core_in_crop_pixels")
            == _ownership_core_in_crop(core_pixel_bounds, pixel_bounds)
            and entry.get("guide_path")
            == f"region-evidence/{region['id']}.ownership.png"
            and isinstance(entry.get("guide_sha256"), str)
            and len(str(entry["guide_sha256"])) == 64
            and entry.get("guide_adapter") == REGION_OWNERSHIP_GUIDE_ADAPTER
        )
    return (
        entry.get("normalized_bounds") == core_normalized_bounds
        and entry.get("pixel_bounds") == core_pixel_bounds
        and entry.get("adapter") == REGION_EVIDENCE_ADAPTER_V1
    )


def prepare_region_evidence(
    attempt_dir: Path,
    *,
    source_path: Path,
    source_sha256: str,
    purpose: str,
    contract: int = CONTRACT,
) -> Path | tuple[Path, Path] | None:
    """Bind the active normalized region to one immutable visual crop."""

    if contract < 8:
        return None
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    entries = _read_journal(journal_path)
    state, pending, completed = _replay(entries, purpose=purpose, contract=contract)
    if completed:
        return None
    region = _active_scan_region(state)
    if region is None:
        return None
    existing = region.get("evidence")
    if existing is not None:
        _verify_region_evidence_files(
            attempt_dir, state, source_sha256=source_sha256,
        )
        return _region_evidence_attachments(
            attempt_dir, region, contract=contract,
        )
    if pending is not None and pending.get("scan_region", {}).get("id") != region["id"]:
        raise InterviewError("region-evidence-question-binding-invalid")
    try:
        frozen = source_path.read_bytes()
    except OSError as error:
        raise InterviewError("region-source-unavailable") from error
    if _digest(frozen) != source_sha256:
        raise InterviewError("region-source-changed")
    try:
        with Image.open(BytesIO(frozen)) as opened:
            opened.seek(0)
            image = ImageOps.exif_transpose(opened)
            image.load()
            width, height = image.size
            core_normalized_bounds = [int(value) for value in region["bounds"]]
            evidence_normalized_bounds = (
                _evidence_normalized_bounds(
                    core_normalized_bounds, contract=contract,
                )
                if contract >= 9
                else core_normalized_bounds
            )
            core_pixel_bounds = _pixel_bounds(
                core_normalized_bounds, width=width, height=height,
            )
            pixel_bounds = _pixel_bounds(
                evidence_normalized_bounds, width=width, height=height,
            )
            if (
                width < 1
                or height < 1
                or pixel_bounds[0] >= pixel_bounds[2]
                or pixel_bounds[1] >= pixel_bounds[3]
            ):
                raise InterviewError("region-crop-empty")
            cropped = image.crop(tuple(pixel_bounds))
            output = BytesIO()
            cropped.save(output, format="PNG", optimize=False, compress_level=9)
            crop_bytes = output.getvalue()
            core_in_crop = _ownership_core_in_crop(
                core_pixel_bounds, pixel_bounds,
            )
            guide_bytes = (
                _render_ownership_guide(cropped, core_in_crop)
                if contract >= 11
                else None
            )
    except (OSError, UnidentifiedImageError) as error:
        raise InterviewError("region-source-image-invalid") from error
    relative, crop_path = _evidence_path(attempt_dir, str(region["id"]))
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    if crop_path.exists():
        try:
            if crop_path.read_bytes() != crop_bytes:
                raise InterviewError(f"region-evidence-changed:{region['id']}")
        except OSError as error:
            raise InterviewError(f"region-evidence-unavailable:{region['id']}") from error
    else:
        crop_path.write_bytes(crop_bytes)
    guide_relative: str | None = None
    guide_path: Path | None = None
    if guide_bytes is not None:
        guide_relative, guide_path = _ownership_guide_path(
            attempt_dir, str(region["id"]),
        )
        if guide_path.exists():
            try:
                if guide_path.read_bytes() != guide_bytes:
                    raise InterviewError(
                        f"region-ownership-guide-changed:{region['id']}"
                    )
            except OSError as error:
                raise InterviewError(
                    f"region-ownership-guide-unavailable:{region['id']}"
                ) from error
        else:
            guide_path.write_bytes(guide_bytes)
    payload: dict[str, object] = {
        "region_id": region["id"],
        "source_sha256": source_sha256,
        "source_pixel_size": [width, height],
        "pixel_bounds": pixel_bounds,
        "crop_path": relative,
        "crop_sha256": _digest(crop_bytes),
    }
    if contract >= 9:
        payload.update({
            "core_normalized_bounds": core_normalized_bounds,
            "evidence_normalized_bounds": evidence_normalized_bounds,
            "core_pixel_bounds": core_pixel_bounds,
            "adapter": REGION_EVIDENCE_ADAPTER,
        })
        if contract >= 11:
            assert guide_relative is not None and guide_bytes is not None
            payload.update({
                "ownership_core_in_crop_pixels": core_in_crop,
                "guide_path": guide_relative,
                "guide_sha256": _digest(guide_bytes),
                "guide_adapter": REGION_OWNERSHIP_GUIDE_ADAPTER,
            })
    else:
        payload.update({
            "normalized_bounds": core_normalized_bounds,
            "adapter": REGION_EVIDENCE_ADAPTER_V1,
        })
    _append(journal_path, "region_evidence_bound", payload)
    if contract >= 11:
        assert guide_path is not None
        return crop_path, guide_path
    return crop_path


def _endpoint_evidence_path(
    attempt_dir: Path, candidate_id: str, *, relative: str | None = None,
) -> tuple[str, Path]:
    relative = relative or f"endpoint-evidence/{candidate_id}.png"
    path = (attempt_dir / relative).resolve()
    try:
        path.relative_to(attempt_dir.resolve())
    except ValueError as error:
        raise InterviewError("endpoint-evidence-path-invalid") from error
    return relative, path


def _endpoint_candidate_id(state: dict[str, Any]) -> str:
    current = state.get("current", {})
    replacement_id = current.get("superseded_element_id")
    if (
        current.get("capture_scope") == "required_participant_replacement"
        and isinstance(replacement_id, str)
    ):
        return replacement_id
    if _required_participant_needs_crop_verification(state):
        obligation = _pending_obligation(state)
        if obligation is None:
            raise InterviewError("relationship-obligation-missing")
        return str(obligation["element_id"])
    return f"element-{len(state['elements']) + 1:06d}"


def _supported_endpoint_verification(
    element: dict[str, Any], *, require_context_contract: bool = False,
) -> bool:
    verification = element.get("endpoint_verification")
    return (
        isinstance(verification, dict)
        and verification.get("verdict") == "supported"
        and isinstance(verification.get("evidence"), dict)
        and (
            not require_context_contract
            or verification.get("claim_scope") in {
                "crop_complete_v2", "selector_with_context_v3",
            }
        )
    )


def _required_participant_needs_crop_verification(
    state: dict[str, Any],
) -> bool:
    if (
        state.get("existing_participant_crop_verification_enabled") is not True
        or state.get("stage") != "obligation_resolution"
    ):
        return False
    obligation = _pending_obligation(state)
    if obligation is None:
        return False
    element = _element_by_id(state, str(obligation["element_id"]))
    return (
        element.get("status") == "readable"
        and not _supported_endpoint_verification(
            element,
            require_context_contract=(
                state.get("contextual_endpoint_verification_enabled") is True
            ),
        )
    )


def _endpoint_crop_verdict_choices(state: dict[str, Any]) -> list[str]:
    choices = [
        "contains_claimed_content",
        "does_not_contain_claimed_content",
        "unreadable",
    ]
    if state.get("contextual_endpoint_verification_enabled") is True:
        choices.insert(1, "requires_visible_context")
    return choices


def _supported_verification_fields(state: dict[str, Any]) -> dict[str, str]:
    return (
        {"claim_scope": "crop_complete_v2"}
        if state.get("contextual_endpoint_verification_enabled") is True
        else {}
    )


def _endpoint_evidence_claim(
    state: dict[str, Any],
) -> dict[str, object] | None:
    current = state.get("current", {})
    if (
        state.get("stage") == "endpoint_context_crop_verdict"
        and current.get("capture_scope") in {
            "required_participant_context", "relationship_endpoint_context",
        }
    ):
        context_scope = str(current["capture_scope"])
        return {
            "candidate_id": (
                str(current["element_id"])
                if context_scope == "required_participant_context"
                else _endpoint_candidate_id(state)
            ),
            "normalized_bounds": [
                int(current["context_left"]), int(current["context_top"]),
                int(current["context_right"]), int(current["context_bottom"]),
            ],
            "claimed_content": str(
                current["claimed_content"]
                if context_scope == "required_participant_context"
                else current["content"]
            ),
            "verification_scope": context_scope,
        }
    if _required_participant_needs_crop_verification(state):
        obligation = _pending_obligation(state)
        if obligation is None:
            raise InterviewError("relationship-obligation-missing")
        element = _element_by_id(state, str(obligation["element_id"]))
        return {
            "candidate_id": element["id"],
            "normalized_bounds": list(element["region"]),
            "claimed_content": element["content"],
            "verification_scope": "required_recorded_participant",
        }
    capture_scope = current.get("capture_scope")
    if (
        state.get("stage") in {
            "element_content_crop_verdict",
            "required_participant_replacement_identity_verdict",
        }
        and capture_scope in {
            "relationship_endpoint", "required_participant_replacement",
        }
    ):
        return {
            "candidate_id": _endpoint_candidate_id(state),
            "normalized_bounds": [
                int(current["left"]), int(current["top"]),
                int(current["right"]), int(current["bottom"]),
            ],
            "claimed_content": str(current["content"]),
            "verification_scope": str(capture_scope),
        }
    return None


def _endpoint_evidence_relative_path(
    claim: dict[str, object], *, legacy: bool = False,
) -> str:
    candidate_id = str(claim["candidate_id"])
    scope = str(claim["verification_scope"])
    if scope == "relationship_endpoint":
        return f"endpoint-evidence/{candidate_id}.png"
    suffix = ""
    if not legacy:
        identity = {
            "candidate_id": candidate_id,
            "normalized_bounds": claim["normalized_bounds"],
            "claimed_content": claim["claimed_content"],
            "verification_scope": scope,
        }
        suffix = "-" + _digest(_canonical(identity))[:16]
    return (
        f"endpoint-evidence/{candidate_id}-{scope.replace('_', '-')}"
        f"{suffix}.png"
    )


def enable_endpoint_crop_verification(
    attempt_dir: Path, *, purpose: str, contract: int,
) -> None:
    """Append the capability activation required by fresh model launchers."""

    if contract < 12:
        return
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    if completed or state.get("endpoint_crop_verification_enabled") is True:
        return
    if pending is not None:
        raise InterviewError("endpoint-crop-verification-activation-question-pending")
    _append(
        journal_path,
        "endpoint_crop_verification_enabled",
        {
            "feature": "fresh_exact_endpoint_crop_verification_v1",
            "contract": contract,
        },
    )


def enable_existing_participant_crop_verification(
    attempt_dir: Path, *, purpose: str, contract: int,
) -> None:
    """Require immutable-crop evidence before a recorded participant is reused."""

    if contract < 12:
        return
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    if (
        completed
        or state.get("existing_participant_crop_verification_enabled") is True
    ):
        return
    if pending is not None:
        raise InterviewError(
            "existing-participant-crop-verification-activation-question-pending"
        )
    migration = _latest_unverified_required_participant_migration(state)
    if migration is not None:
        _append(
            journal_path,
            "unverified_required_participant_relationship_invalidated",
            migration,
        )
        state, pending, completed = _replay(
            _read_journal(journal_path), purpose=purpose, contract=contract,
        )
        if pending is not None or completed:
            raise InterviewError(
                "existing-participant-crop-verification-migration-invalid"
            )
    _append(
        journal_path,
        "existing_participant_crop_verification_enabled",
        {
            "feature": "existing_required_participant_crop_verification_v1",
            "contract": contract,
        },
    )


def enable_contextual_endpoint_verification(
    attempt_dir: Path, *, purpose: str, contract: int,
) -> None:
    """Require a crop to prove contextual qualifiers before endpoint reuse."""

    if contract < 12:
        return
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    if completed or state.get("contextual_endpoint_verification_enabled") is True:
        return
    if pending is not None:
        raise InterviewError(
            "contextual-endpoint-verification-activation-question-pending"
        )
    migration = _latest_context_unassessed_participant_migration(state)
    if migration is not None:
        _append(
            journal_path,
            "context_unassessed_required_participant_relationship_invalidated",
            migration,
        )
        state, pending, completed = _replay(
            _read_journal(journal_path), purpose=purpose, contract=contract,
        )
        if pending is not None or completed:
            raise InterviewError(
                "contextual-endpoint-verification-migration-invalid"
            )
    _append(
        journal_path,
        "contextual_endpoint_verification_enabled",
        {
            "feature": "contextual_endpoint_crop_verification_v1",
            "contract": contract,
        },
    )


def _endpoint_context_evidence_activation(
    state: dict[str, Any], pending: dict[str, object] | None, *, contract: int,
) -> dict[str, object]:
    recovery: dict[str, object] | None = None
    obligation = _pending_obligation(state)
    if obligation is not None:
        element_id = str(obligation["element_id"])
        element = _element_by_id(state, element_id)
        candidates = state.get("_context_selector_candidates", {})
        selector = candidates.get(element_id) if isinstance(candidates, dict) else None
        verification = element.get("endpoint_verification")
        if (
            element.get("status") == "gap"
            and isinstance(verification, dict)
            and verification.get("verdict") == "requires_visible_context"
            and isinstance(selector, dict)
        ):
            if pending is None:
                raise InterviewError(
                    "endpoint-context-evidence-recovery-question-missing"
                )
            recovery = {
                "action": "restore_precise_selector_and_collect_context",
                "abandoned_question_id": pending["id"],
                "element_id": element_id,
                "rejected_element": element,
                "restored_element": selector,
            }
    return {
        "feature": "separate_endpoint_context_evidence_v1",
        "contract": contract,
        "pending_context_recovery": recovery,
    }


def _locked_participant_replacement_activation(
    state: dict[str, Any],
    pending: dict[str, object] | None,
    history: list[dict[str, object]],
    *,
    contract: int,
) -> dict[str, object]:
    recovery: dict[str, object] | None = None
    draft = state.get("relationship_draft")
    current = state.get("current")
    if (
        pending is not None
        and pending.get("id") == "element_kind"
        and isinstance(draft, dict)
        and isinstance(current, dict)
        and current.get("capture_scope") == "relationship_endpoint"
        and isinstance(draft.get("locked_identity_participants"), dict)
    ):
        role_answers = [
            (index, entry)
            for index, entry in enumerate(history)
            if (
                entry.get("event") == "answer_recorded"
                and entry.get("question_id")
                == "relationship_visual_endpoint_role"
                and entry.get("accepted") is True
                and entry.get("parsed") in {"origin", "target"}
            )
        ]
        if not role_answers:
            raise InterviewError(
                "locked-participant-recovery-role-answer-missing"
            )
        role_index, role_answer = role_answers[-1]
        role = str(role_answer["parsed"])
        locked = draft["locked_identity_participants"]
        expected_return_stage = f"relationship_{role}_x"
        if (
            locked.get(role) is None
            or current.get("return_stage") != expected_return_stage
        ):
            return {
                "feature": "locked_relationship_participant_replacement_v1",
                "contract": contract,
                "pending_recovery": None,
            }
        resolution_answers = [
            (index, entry)
            for index, entry in enumerate(history[:role_index])
            if (
                entry.get("event") == "answer_recorded"
                and entry.get("question_id") == "relationship_visual_resolution"
                and entry.get("accepted") is True
                and entry.get("parsed") == "record_visible_endpoint"
            )
        ]
        verdict_answers = [
            (index, entry)
            for index, entry in enumerate(history[:role_index])
            if (
                entry.get("event") == "answer_recorded"
                and entry.get("question_id") == "relationship_visual_verdict"
                and entry.get("accepted") is True
                and entry.get("parsed") == "not_supported"
            )
        ]
        if not resolution_answers or not verdict_answers:
            raise InterviewError(
                "locked-participant-recovery-decision-evidence-missing"
            )
        resolution_index, resolution_answer = resolution_answers[-1]
        verdict_index, verdict_answer = verdict_answers[-1]
        if not verdict_index < resolution_index < role_index:
            raise InterviewError(
                "locked-participant-recovery-decision-order-invalid"
            )
        proposal_questions = [
            (index, entry)
            for index, entry in enumerate(history[:verdict_index])
            if (
                entry.get("event") == "question_asked"
                and isinstance(entry.get("question"), dict)
                and entry["question"].get("id")
                == "relationship_visual_verdict"
                and isinstance(
                    entry["question"].get("proposed_relationship"), dict,
                )
            )
        ]
        if not proposal_questions:
            raise InterviewError(
                "locked-participant-recovery-proposal-missing"
            )
        _, proposal_entry = proposal_questions[-1]
        proposal = proposal_entry["question"]["proposed_relationship"]
        restored = dict(draft)
        for participant_role in ("origin", "target"):
            participant = proposal.get(participant_role)
            if not isinstance(participant, dict):
                raise InterviewError(
                    "locked-participant-recovery-participant-missing"
                )
            element_id = participant.get("element_id")
            point = participant.get("point")
            if (
                not isinstance(element_id, str)
                or not isinstance(point, list)
                or len(point) != 2
                or not all(isinstance(value, int) for value in point)
            ):
                raise InterviewError(
                    "locked-participant-recovery-participant-invalid"
                )
            restored[f"{participant_role}_id"] = element_id
            restored[f"{participant_role}_x"] = point[0]
            restored[f"{participant_role}_y"] = point[1]
            restored[f"{participant_role}_point"] = list(point)
        required_element_id = proposal.get("required_element_id")
        if (
            locked.get(role) != restored[f"{role}_id"]
            or locked.get(role) != required_element_id
        ):
            raise InterviewError(
                "locked-participant-recovery-required-identity-changed"
            )
        restored["visual_verification"] = "not_supported"
        restored["verification_issue"] = {
            "origin_id": restored["origin_id"],
            "target_id": restored["target_id"],
            "required_element_id": required_element_id,
            "reason": "visible_connection_not_supported",
        }
        recovery = {
            "action": "restore_locked_pair_and_record_absence",
            "abandoned_question_id": pending["id"],
            "selected_locked_role": role,
            "proposal_question_sequence": proposal_entry.get("sequence"),
            "verdict_answer_sequence": verdict_answer.get("sequence"),
            "resolution_answer_sequence": resolution_answer.get("sequence"),
            "role_answer_sequence": role_answer.get("sequence"),
            "previous_current": current,
            "previous_relationship_draft": draft,
            "restored_current": restored,
        }
    return {
        "feature": "locked_relationship_participant_replacement_v1",
        "contract": contract,
        "pending_recovery": recovery,
    }


def _apply_locked_participant_replacement_activation(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    recovery = event.get("pending_recovery")
    if recovery is not None:
        if not isinstance(recovery, dict):
            raise InterviewError("locked-participant-recovery-invalid")
        if (
            state.get("current") != recovery.get("previous_current")
            or state.get("relationship_draft")
            != recovery.get("previous_relationship_draft")
        ):
            raise InterviewError("locked-participant-recovery-state-changed")
        restored = recovery.get("restored_current")
        if not isinstance(restored, dict):
            raise InterviewError("locked-participant-recovery-result-invalid")
        role = str(recovery.get("selected_locked_role"))
        locked = restored.get("locked_identity_participants")
        if (
            role not in {"origin", "target"}
            or not isinstance(locked, dict)
            or locked.get(role) != restored.get(f"{role}_id")
            or restored.get("visual_verification") != "not_supported"
        ):
            raise InterviewError("locked-participant-recovery-result-invalid")
        state["relationship_draft"] = None
        state["current"] = restored
        state["stage"] = "relationship_visual_gap_reason"
    state["locked_participant_replacement_blocked_enabled"] = True


def _replacement_content_identity_separation_activation(
    state: dict[str, Any], pending: dict[str, object] | None, *, contract: int,
) -> dict[str, object]:
    abandoned_question_id: str | None = None
    if pending is not None:
        if (
            pending.get("id") != "element_content_crop_verdict"
            or state.get("stage") != "element_content_crop_verdict"
            or state.get("current", {}).get("capture_scope")
            != "required_participant_replacement"
        ):
            raise InterviewError(
                "replacement-content-identity-separation-question-invalid"
            )
        abandoned_question_id = str(pending["id"])
    return {
        "feature": "required_participant_content_identity_separation_v1",
        "contract": contract,
        "abandoned_question_id": abandoned_question_id,
    }


def _apply_endpoint_context_evidence_activation(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    recovery = event.get("pending_context_recovery")
    if recovery is not None:
        if not isinstance(recovery, dict):
            raise InterviewError("endpoint-context-evidence-recovery-invalid")
        element_id = str(recovery["element_id"])
        current = _element_by_id(state, element_id)
        if current != recovery.get("rejected_element"):
            raise InterviewError("endpoint-context-evidence-recovery-changed")
        restored = recovery.get("restored_element")
        if (
            not isinstance(restored, dict)
            or restored.get("id") != element_id
            or restored.get("status") != "readable"
        ):
            raise InterviewError("endpoint-context-evidence-selector-invalid")
        state["elements"][state["elements"].index(current)] = restored
        state["current"] = {
            "capture_scope": "required_participant_context",
            "element_id": element_id,
            "claimed_content": restored["content"],
            "selector_region": list(restored["region"]),
        }
        state["stage"] = "endpoint_context_left"
    state["endpoint_context_evidence_enabled"] = True


def enable_endpoint_context_evidence(
    attempt_dir: Path, *, purpose: str, contract: int,
) -> None:
    """Keep precise endpoint geometry separate from its identifying context."""

    if contract < 12:
        return
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    if completed or state.get("endpoint_context_evidence_enabled") is True:
        return
    event = _endpoint_context_evidence_activation(
        state, pending, contract=contract,
    )
    _append(journal_path, "endpoint_context_evidence_enabled", event)


def _endpoint_selector_context_activation(
    state: dict[str, Any], pending: dict[str, object] | None, *, contract: int,
) -> dict[str, object]:
    recovery: dict[str, object] | None = None
    if (
        state.get("stage") == "element_content_crop_verdict"
        and state.get("current", {}).get("capture_scope")
        == "relationship_endpoint"
    ):
        recovery = {
            "action": "replace_crop_question_with_specificity_question",
            "abandoned_question_id": (
                pending.get("id") if isinstance(pending, dict) else None
            ),
        }
    return {
        "feature": "precise_endpoint_selector_with_context_v1",
        "contract": contract,
        "pending_scope_recovery": recovery,
    }


def _apply_endpoint_selector_context_activation(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    recovery = event.get("pending_scope_recovery")
    if recovery is not None:
        if (
            not isinstance(recovery, dict)
            or recovery.get("action")
            != "replace_crop_question_with_specificity_question"
            or state.get("stage") != "element_content_crop_verdict"
            or state.get("current", {}).get("capture_scope")
            != "relationship_endpoint"
        ):
            raise InterviewError("endpoint-selector-context-recovery-invalid")
        state["stage"] = "relationship_endpoint_specificity"
    state["endpoint_selector_context_enabled"] = True


def enable_endpoint_selector_context(
    attempt_dir: Path, *, purpose: str, contract: int,
) -> None:
    """Keep a relationship selector precise and collect identity context separately."""

    if contract < 12:
        return
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    if completed or state.get("endpoint_selector_context_enabled") is True:
        return
    event = _endpoint_selector_context_activation(
        state, pending, contract=contract,
    )
    _append(journal_path, "endpoint_selector_context_enabled", event)


def _endpoint_identity_context_choice_activation(
    state: dict[str, Any], pending: dict[str, object] | None, *, contract: int,
) -> dict[str, object]:
    recovery: dict[str, object] | None = None
    current = state.get("current", {})
    if (
        state.get("stage") == "element_relationship_obligation"
        and isinstance(pending, dict)
        and pending.get("id") == "element_relationship_obligation"
        and isinstance(current.get("element_id"), str)
    ):
        element = _element_by_id(state, str(current["element_id"]))
        verification = element.get("endpoint_verification")
        if (
            element.get("capture_scope") == "relationship_endpoint"
            and element.get("status") == "readable"
            and isinstance(verification, dict)
            and verification.get("verdict") == "supported"
            and isinstance(verification.get("evidence"), dict)
        ):
            replacement = {
                **element,
                "status": "gap",
                "content": "",
                "gap_reason": (
                    "The selector text was visible, but its complete endpoint "
                    "identity still required separate source context."
                ),
                "endpoint_verification": {
                    "verdict": "requires_visible_context",
                    "claimed_content": element["content"],
                    "evidence": verification["evidence"],
                },
            }
            recovery = {
                "action": "collect_context_for_supported_selector",
                "abandoned_question_id": pending["id"],
                "previous_element": element,
                "replacement_element": replacement,
                "return_stage": current.get(
                    "return_stage", "element_more",
                ),
            }
    return {
        "feature": "endpoint_identity_context_choice_v1",
        "contract": contract,
        "pending_identity_recovery": recovery,
    }


def _apply_endpoint_identity_context_choice_activation(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    recovery = event.get("pending_identity_recovery")
    if recovery is not None:
        if not isinstance(recovery, dict):
            raise InterviewError("endpoint-identity-context-recovery-invalid")
        previous = recovery.get("previous_element")
        replacement = recovery.get("replacement_element")
        if (
            not isinstance(previous, dict)
            or not isinstance(replacement, dict)
            or previous not in state["elements"]
            or replacement.get("id") != previous.get("id")
        ):
            raise InterviewError("endpoint-identity-context-recovery-changed")
        verification = previous.get("endpoint_verification")
        if not isinstance(verification, dict) or not isinstance(
            verification.get("evidence"), dict,
        ):
            raise InterviewError("endpoint-identity-selector-evidence-missing")
        state["elements"][state["elements"].index(previous)] = replacement
        state["current"] = {
            "capture_scope": "relationship_endpoint_context",
            "return_stage": recovery.get("return_stage", "element_more"),
            "kind": previous["kind"],
            "content": previous["content"],
            "status": "readable",
            "left": previous["region"][0],
            "top": previous["region"][1],
            "right": previous["region"][2],
            "bottom": previous["region"][3],
            "selector_region": list(previous["region"]),
            "selector_evidence": verification["evidence"],
        }
        state["stage"] = "endpoint_context_left"
    state["endpoint_identity_context_choice_enabled"] = True


def enable_endpoint_identity_context_choice(
    attempt_dir: Path, *, purpose: str, contract: int,
) -> None:
    """Let code enforce whether a precise endpoint needs identity context."""

    if contract < 12:
        return
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    if (
        completed
        or state.get("endpoint_identity_context_choice_enabled") is True
    ):
        return
    event = _endpoint_identity_context_choice_activation(
        state, pending, contract=contract,
    )
    _append(journal_path, "endpoint_identity_context_choice_enabled", event)


def _negative_context_replacement_activation(
    state: dict[str, Any], pending: dict[str, object] | None, *, contract: int,
) -> dict[str, object]:
    recovery: dict[str, object] | None = None
    current = state.get("current", {})
    evidence = current.get("last_context_evidence")
    if (
        current.get("capture_scope") == "required_participant_context"
        and current.get("last_context_verdict")
        == "does_not_contain_claimed_content"
        and _valid_negative_context_recovery_evidence(state, evidence)
    ):
        recovery = {
            "abandoned_question_id": (
                pending.get("id") if isinstance(pending, dict) else None
            ),
            "element_id": current.get("element_id"),
            "endpoint_crop_evidence": evidence,
        }
    return {
        "feature": "negative_context_reopens_participant_v1",
        "contract": contract,
        "pending_negative_context_recovery": recovery,
    }


def _apply_negative_context_replacement_activation(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    state["negative_context_replacement_enabled"] = True
    recovery = event.get("pending_negative_context_recovery")
    if recovery is None:
        return
    if not isinstance(recovery, dict):
        raise InterviewError("negative-context-recovery-invalid")
    current = state.get("current", {})
    evidence = recovery.get("endpoint_crop_evidence")
    if (
        current.get("element_id") != recovery.get("element_id")
        or not _valid_negative_context_recovery_evidence(state, evidence)
    ):
        raise InterviewError("negative-context-recovery-changed")
    bounds = evidence.get("normalized_bounds")
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise InterviewError("negative-context-recovery-bounds-invalid")
    for coordinate, value in zip(
        ("left", "top", "right", "bottom"), bounds, strict=True,
    ):
        current[f"context_{coordinate}"] = int(value)
    current["endpoint_crop_evidence"] = evidence
    state["stage"] = "endpoint_context_crop_verdict"
    _complete_endpoint_context_verdict(
        state, "does_not_contain_claimed_content",
    )


def _valid_negative_context_recovery_evidence(
    state: dict[str, Any], evidence: object,
) -> bool:
    if not isinstance(evidence, dict):
        return False
    bounds = evidence.get("normalized_bounds")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 4
        or not all(isinstance(value, int) for value in bounds)
    ):
        return False
    current = dict(state.get("current", {}))
    for coordinate, value in zip(
        ("left", "top", "right", "bottom"), bounds, strict=True,
    ):
        current[f"context_{coordinate}"] = int(value)
    probe = {**state, "stage": "endpoint_context_crop_verdict", "current": current}
    return _valid_endpoint_evidence(probe, evidence)


def enable_negative_context_replacement(
    attempt_dir: Path, *, purpose: str, contract: int,
) -> None:
    """Activate append-only recovery when context disproves a selector claim."""

    if contract < 12:
        return
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    if completed or state.get("negative_context_replacement_enabled") is True:
        return
    event = _negative_context_replacement_activation(
        state, pending, contract=contract,
    )
    if pending is not None and event["pending_negative_context_recovery"] is None:
        raise InterviewError("negative-context-activation-question-pending")
    _append(journal_path, "negative_context_replacement_enabled", event)


def enable_rejected_endpoint_reuse_block(
    attempt_dir: Path, *, purpose: str, contract: int,
) -> None:
    """Prevent exact-crop-rejected endpoints from being reused as evidence."""

    if contract < 12:
        return
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    while not completed and pending is None:
        migration = _readable_relationship_rejected_endpoint_migration(state)
        if migration is None:
            break
        _append(
            journal_path,
            "readable_relationship_rejected_endpoint_invalidated",
            migration,
        )
        state, pending, completed = _replay(
            _read_journal(journal_path), purpose=purpose, contract=contract,
        )
    if (
        completed
        or state.get("unreadable_participant_reuse_blocked_enabled") is True
    ):
        return
    if pending is not None:
        raise InterviewError(
            "rejected-endpoint-reuse-block-activation-question-pending"
        )
    _append(
        journal_path,
        "unreadable_participant_reuse_blocked_enabled",
        {
            "feature": "unreadable_participant_reuse_blocked_v2",
            "contract": contract,
        },
    )


def _rejected_endpoint_collision_activation(
    state: dict[str, Any], pending: dict[str, object] | None, *, contract: int,
) -> dict[str, object]:
    recovery: dict[str, object] | None = None
    if pending is not None:
        choices = pending.get("choices")
        pending_id = pending.get("id")
        current = state.get("current", {})
        rejected_ids = (
            list(choices)
            if pending_id == "element_same_unit_target"
            and isinstance(choices, list)
            else [current.get("superseded_element_id")]
            if pending_id in {
                "element_merge_left", "element_merge_top",
                "element_merge_right", "element_merge_bottom",
                "element_merge_status", "element_merge_content",
                "element_merge_gap_reason",
            }
            else []
        )
        if (
            current.get("capture_scope") != "relationship_endpoint"
            or not rejected_ids
            or any(
                not isinstance(element_id, str)
                or not _endpoint_was_rejected(_element_by_id(state, element_id))
                for element_id in rejected_ids
            )
        ):
            raise InterviewError(
                "rejected-endpoint-collision-activation-question-pending"
            )
        recovery = {
            "action": "continue_pending_capture_as_new_element_version",
            "abandoned_question_id": pending["id"],
            "rejected_collision_element_ids": rejected_ids,
        }
    return {
        "feature": "rejected_endpoint_collision_excluded_v1",
        "contract": contract,
        "pending_capture_recovery": recovery,
    }


def _apply_rejected_endpoint_collision_activation(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    recovery = event.get("pending_capture_recovery")
    if recovery is not None:
        if not isinstance(recovery, dict):
            raise InterviewError("rejected-endpoint-collision-recovery-invalid")
        for key in (
            "unit_collision_candidate_ids", "superseded_element_id",
            "merge_left", "merge_top", "merge_right", "merge_bottom",
            "merge_status", "merge_content", "merge_gap_reason",
        ):
            state["current"].pop(key, None)
        state["stage"] = "element_status"
    state["rejected_endpoint_collision_excluded_enabled"] = True


def enable_rejected_endpoint_collision_exclusion(
    attempt_dir: Path, *, purpose: str, contract: int,
) -> None:
    """Keep rejected endpoint attempts out of future unit-identity merging."""

    if contract < 12:
        return
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    if completed or state.get("rejected_endpoint_collision_excluded_enabled") is True:
        return
    event = _rejected_endpoint_collision_activation(
        state, pending, contract=contract,
    )
    _append(
        journal_path,
        "rejected_endpoint_collision_excluded_enabled",
        event,
    )


def _endpoint_evidence_payload(
    state: dict[str, Any], *, source_sha256: str, source_size: list[int],
    pixel_bounds: list[int], crop_path: str, crop_sha256: str,
) -> dict[str, object]:
    claim = _endpoint_evidence_claim(state)
    if claim is None:
        raise InterviewError("endpoint-evidence-claim-missing")
    return {
        "candidate_id": claim["candidate_id"],
        "source_sha256": source_sha256,
        "source_pixel_size": source_size,
        "normalized_bounds": claim["normalized_bounds"],
        "pixel_bounds": pixel_bounds,
        "crop_path": crop_path,
        "crop_sha256": crop_sha256,
        "claimed_content": claim["claimed_content"],
        "verification_scope": claim["verification_scope"],
        "adapter": ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }


def _valid_endpoint_evidence(
    state: dict[str, Any], evidence: object,
) -> bool:
    if not isinstance(evidence, dict):
        return False
    claim = _endpoint_evidence_claim(state)
    if claim is None:
        return False
    source_size = evidence.get("source_pixel_size")
    if (
        not isinstance(source_size, list)
        or len(source_size) != 2
        or not all(isinstance(value, int) and value > 0 for value in source_size)
    ):
        return False
    bounds = list(claim["normalized_bounds"])
    width, height = [int(value) for value in source_size]
    candidate_id = str(claim["candidate_id"])
    evidence_scope = evidence.get("verification_scope")
    if evidence_scope is None:
        evidence_scope = "relationship_endpoint"
    expected_claim = {**claim, "verification_scope": evidence_scope}
    return (
        evidence.get("candidate_id") == candidate_id
        and evidence.get("normalized_bounds") == bounds
        and evidence.get("pixel_bounds")
        == _pixel_bounds(bounds, width=width, height=height)
        and evidence.get("crop_path") in {
            _endpoint_evidence_relative_path(expected_claim),
            _endpoint_evidence_relative_path(expected_claim, legacy=True),
        }
        and isinstance(evidence.get("crop_sha256"), str)
        and len(str(evidence["crop_sha256"])) == 64
        and evidence.get("claimed_content") == claim["claimed_content"]
        and evidence_scope == claim["verification_scope"]
        and evidence.get("adapter") == ENDPOINT_CROP_EVIDENCE_ADAPTER
        and isinstance(evidence.get("source_sha256"), str)
        and len(str(evidence["source_sha256"])) == 64
    )


def _verify_endpoint_evidence_file(
    attempt_dir: Path, evidence: dict[str, object], *, source_sha256: str,
) -> Path:
    candidate_id = evidence.get("candidate_id")
    if (
        not isinstance(candidate_id, str)
        or evidence.get("source_sha256") != source_sha256
    ):
        raise InterviewError("endpoint-evidence-source-changed")
    crop_path = evidence.get("crop_path")
    if not isinstance(crop_path, str):
        raise InterviewError("endpoint-evidence-unavailable")
    relative, path = _endpoint_evidence_path(
        attempt_dir, candidate_id, relative=crop_path,
    )
    if crop_path != relative or not path.is_file():
        raise InterviewError("endpoint-evidence-unavailable")
    try:
        crop_bytes = path.read_bytes()
    except OSError as error:
        raise InterviewError("endpoint-evidence-unavailable") from error
    if _digest(crop_bytes) != evidence.get("crop_sha256"):
        raise InterviewError("endpoint-evidence-changed")
    return path


def _verify_endpoint_evidence_files(
    attempt_dir: Path, state: dict[str, Any], *, source_sha256: str,
) -> None:
    evidence_items: list[dict[str, object]] = []
    current_evidence = state.get("current", {}).get("endpoint_crop_evidence")
    if isinstance(current_evidence, dict):
        evidence_items.append(current_evidence)
    for element in state["elements"]:
        verification = element.get("endpoint_verification")
        evidence = verification.get("evidence") if isinstance(verification, dict) else None
        if isinstance(evidence, dict):
            evidence_items.append(evidence)
    seen: set[str] = set()
    for evidence in evidence_items:
        crop_sha256 = str(evidence.get("crop_sha256"))
        if crop_sha256 in seen:
            continue
        _verify_endpoint_evidence_file(
            attempt_dir, evidence, source_sha256=source_sha256,
        )
        seen.add(crop_sha256)


def required_participant_replacement_attachments(
    attempt_dir: Path,
    state: dict[str, Any],
    *,
    source_path: Path,
    source_sha256: str,
) -> tuple[Path, Path] | None:
    """Return focused rejected-crop evidence plus the complete frozen source."""

    current = state.get("current", {})
    target_id = current.get("superseded_element_id")
    if (
        current.get("capture_scope") != "required_participant_replacement"
        or not isinstance(target_id, str)
    ):
        return None
    element = _element_by_id(state, target_id)
    verification = element.get("endpoint_verification")
    evidence = (
        verification.get("evidence")
        if isinstance(verification, dict) else None
    )
    if (
        not isinstance(evidence, dict)
        or verification.get("verdict")
        not in {
            "does_not_contain_claimed_content",
            "requires_visible_context",
            "unreadable",
        }
    ):
        raise InterviewError("required-participant-replacement-evidence-missing")
    crop_path = _verify_endpoint_evidence_file(
        attempt_dir, evidence, source_sha256=source_sha256,
    )
    if not source_path.is_file():
        raise InterviewError("endpoint-source-unavailable")
    return crop_path, source_path


def prepare_endpoint_evidence(
    attempt_dir: Path,
    *,
    source_path: Path,
    source_sha256: str,
    purpose: str,
    contract: int = CONTRACT,
) -> tuple[Path, str] | None:
    """Bind a claimed relationship endpoint to its exact immutable crop."""

    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    claim = _endpoint_evidence_claim(state)
    if completed or claim is None:
        return None
    existing = state["current"].get("endpoint_crop_evidence")
    if existing is not None:
        if not _valid_endpoint_evidence(state, existing):
            raise InterviewError("endpoint-evidence-binding-invalid")
        path = _verify_endpoint_evidence_file(
            attempt_dir, existing, source_sha256=source_sha256,
        )
        return path, str(existing["crop_sha256"])
    if pending is not None:
        raise InterviewError("endpoint-evidence-question-binding-invalid")
    try:
        frozen = source_path.read_bytes()
    except OSError as error:
        raise InterviewError("endpoint-source-unavailable") from error
    if _digest(frozen) != source_sha256:
        raise InterviewError("endpoint-source-changed")
    try:
        with Image.open(BytesIO(frozen)) as opened:
            opened.seek(0)
            image = ImageOps.exif_transpose(opened)
            image.load()
            width, height = image.size
            bounds = list(claim["normalized_bounds"])
            pixel_bounds = _pixel_bounds(bounds, width=width, height=height)
            if (
                width < 1
                or height < 1
                or pixel_bounds[0] >= pixel_bounds[2]
                or pixel_bounds[1] >= pixel_bounds[3]
            ):
                raise InterviewError("endpoint-crop-empty")
            cropped = image.crop(tuple(pixel_bounds))
            output = BytesIO()
            cropped.save(output, format="PNG", optimize=False, compress_level=9)
            crop_bytes = output.getvalue()
    except (OSError, UnidentifiedImageError) as error:
        raise InterviewError("endpoint-source-image-invalid") from error
    candidate_id = str(claim["candidate_id"])
    relative = _endpoint_evidence_relative_path(claim)
    relative, crop_path = _endpoint_evidence_path(
        attempt_dir, candidate_id, relative=relative,
    )
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    if crop_path.exists():
        try:
            if crop_path.read_bytes() != crop_bytes:
                raise InterviewError("endpoint-evidence-changed")
        except OSError as error:
            raise InterviewError("endpoint-evidence-unavailable") from error
    else:
        crop_path.write_bytes(crop_bytes)
    payload = _endpoint_evidence_payload(
        state,
        source_sha256=source_sha256,
        source_size=[width, height],
        pixel_bounds=pixel_bounds,
        crop_path=relative,
        crop_sha256=_digest(crop_bytes),
    )
    _append(journal_path, "endpoint_crop_evidence_bound", payload)
    return crop_path, str(payload["crop_sha256"])


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
    if contract >= 8 and (
        stage.startswith(("region_", "context_obligation_"))
        or (
            stage.startswith("element_")
            and isinstance(current.get("scan_region_id"), str)
        )
    ):
        region = _active_scan_region(state)
        if region is None or not isinstance(region.get("evidence"), dict):
            raise InterviewError("region-evidence-required")
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
        deferred = region.get("deferred_context_candidates")
        if isinstance(deferred, list) and deferred:
            question["deferred_context_candidates"] = deferred
    elif stage == "context_obligation_resolution":
        obligation = _pending_context_obligation(state)
        if obligation is None:
            raise InterviewError("context-obligation-missing")
        question = _field(
            "context_obligation_resolution",
            "The active ownership core contains a candidate deferred from earlier context. What faithful outcome applies here?",
            "choice",
            choices=["record_owned_element", "record_explicit_gap"],
        )
        question["context_candidate_obligation"] = obligation
    elif stage == "context_obligation_gap_reason":
        obligation = _pending_context_obligation(state)
        if obligation is None:
            raise InterviewError("context-obligation-missing")
        question = _field(
            "context_obligation_gap_reason",
            "What visible condition prevents faithfully recording this deferred candidate in its owning region?",
            "string",
        )
        question["context_candidate_obligation"] = obligation
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
    elif stage == "element_ownership":
        choices = ["owned_by_active_core", "context_only"]
        prompt = (
            "Is this candidate's top-left anchor inside the ownership guide's "
            "outlined active core, or only in the surrounding context?"
        )
        if contract >= 13:
            evidence = region.get("evidence")
            if not isinstance(evidence, dict):
                raise InterviewError("context-ownership-evidence-missing")
            if not _context_space_available(evidence):
                choices = ["owned_by_active_core"]
                prompt = (
                    "The visible evidence contains no surrounding context outside "
                    "the ownership core. Confirm that this candidate is owned by "
                    "the active core."
                )
        question = _field(
            "element_ownership",
            prompt,
            "choice",
            choices=choices,
        )
    elif stage == "context_anchor_x":
        question = _field(
            "context_anchor_x",
            "What normalized x coordinate is the context-only candidate's top-left ownership anchor?",
            "integer",
            minimum=0,
            maximum=999,
        )
    elif stage == "context_anchor_y":
        question = _field(
            "context_anchor_y",
            "What normalized y coordinate is the context-only candidate's top-left ownership anchor?",
            "integer",
            minimum=0,
            maximum=999,
        )
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
    elif stage in {
        "endpoint_context_left", "endpoint_context_top",
        "endpoint_context_right", "endpoint_context_bottom",
    }:
        selector = current.get("selector_region")
        if not isinstance(selector, list) or len(selector) != 4:
            raise InterviewError("endpoint-context-selector-missing")
        coordinate = stage.removeprefix("endpoint_context_")
        limits = {
            "left": (0, int(selector[0])),
            "top": (0, int(selector[1])),
            "right": (int(selector[2]), 1000),
            "bottom": (int(selector[3]), 1000),
        }
        minimum, maximum = limits[coordinate]
        question = _field(
            stage,
            f"What is the identifying context window's normalized {coordinate} coordinate?",
            "integer",
            minimum=minimum,
            maximum=maximum,
        )
    elif stage == "endpoint_context_crop_verdict":
        evidence = current.get("endpoint_crop_evidence")
        if not _valid_endpoint_evidence(state, evidence):
            raise InterviewError("endpoint-context-evidence-missing")
        question = _field(
            "endpoint_context_crop_verdict",
            "Does this context window visibly establish the precise endpoint's complete claimed identity?",
            "choice",
            choices=[
                "contains_claimed_content",
                "requires_visible_context",
                "does_not_contain_claimed_content",
                "unreadable",
            ],
        )
        question["endpoint_crop_evidence"] = evidence
    elif stage == "element_unit_resolution":
        candidate_ids = current.get("unit_collision_candidate_ids")
        if not isinstance(candidate_ids, list) or not candidate_ids:
            raise InterviewError("element-unit-candidates-missing")
        candidates = [
            _element_by_id(state, str(element_id))
            for element_id in candidate_ids
        ]
        question = _field(
            "element_unit_resolution",
            "Is this candidate a distinct visible unit, or part of one listed existing visible unit?",
            "choice",
            choices=["distinct_unit", "same_unit"],
        )
        question["unit_collision_candidates"] = candidates
    elif stage == "element_same_unit_target":
        candidate_ids = current.get("unit_collision_candidate_ids")
        if not isinstance(candidate_ids, list) or not candidate_ids:
            raise InterviewError("element-unit-candidates-missing")
        question = _field(
            "element_same_unit_target",
            "Which listed existing element belongs to the same complete visible unit?",
            "choice",
            choices=[str(element_id) for element_id in candidate_ids],
        )
        question["unit_collision_candidates"] = [
            _element_by_id(state, str(element_id))
            for element_id in candidate_ids
        ]
    elif stage in {
        "element_merge_left", "element_merge_top",
        "element_merge_right", "element_merge_bottom",
    }:
        target_id = current.get("superseded_element_id")
        if not isinstance(target_id, str):
            raise InterviewError("element-supersession-target-missing")
        target = _element_by_id(state, target_id)
        union = [
            min(int(current["left"]), int(target["region"][0])),
            min(int(current["top"]), int(target["region"][1])),
            max(int(current["right"]), int(target["region"][2])),
            max(int(current["bottom"]), int(target["region"][3])),
        ]
        field = stage.removeprefix("element_merge_")
        limits = {
            "left": (0, union[0]),
            "top": (0, union[1]),
            "right": (union[2], 1000),
            "bottom": (union[3], 1000),
        }
        minimum, maximum = limits[field]
        question = _field(
            stage,
            f"What is the complete visible unit's normalized {field} coordinate?",
            "integer",
            minimum=minimum,
            maximum=maximum,
        )
    elif stage == "element_merge_status":
        question = _field(
            "element_merge_status",
            "Is the complete visible unit faithfully readable, or must it remain an explicit gap?",
            "choice",
            choices=["readable", "gap"],
        )
    elif stage == "element_merge_content":
        question = _field(
            "element_merge_content",
            "What exact AI-readable content does the complete visible unit contain?",
            "string",
        )
    elif stage == "element_merge_gap_reason":
        question = _field(
            "element_merge_gap_reason",
            "What visible condition prevents faithful reading of the complete visible unit?",
            "string",
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
    elif stage == "relationship_endpoint_specificity":
        identity_choice = (
            state.get("endpoint_identity_context_choice_enabled") is True
        )
        question = _field(
            "relationship_endpoint_specificity",
            (
                "Do the proposed bounds and content identify exactly one visible "
                "relationship endpoint, or do they combine multiple independent "
                "visible fields or elements? A value and the label that names that "
                "same value are one element; a section containing several separate "
                "metrics is multiple elements. For one precise element, also state "
                "whether its captured kind and meaning require a nearby label or "
                "other visible context."
                if identity_choice else
                "Do the proposed bounds and content identify exactly one visible "
                "relationship endpoint, or do they combine multiple independent "
                "visible fields or elements? A value and the label that names that "
                "same value are one element; a section containing several separate "
                "metrics is multiple elements."
            ),
            "choice",
            choices=(
                [
                    "one_precise_self_identifying_element",
                    "one_precise_element_requires_context",
                    "multiple_independent_visible_elements",
                ]
                if identity_choice else
                [
                    "one_precise_visible_element",
                    "multiple_independent_visible_elements",
                ]
            ),
        )
        question["endpoint_selector_candidate"] = {
            "kind": current["kind"],
            "normalized_bounds": [
                current["left"], current["top"],
                current["right"], current["bottom"],
            ],
            "claimed_content": current["content"],
        }
    elif stage == "element_content_crop_verdict":
        evidence = current.get("endpoint_crop_evidence")
        if not _valid_endpoint_evidence(state, evidence):
            raise InterviewError("endpoint-crop-evidence-missing")
        context_contract = (
            state.get("contextual_endpoint_verification_enabled") is True
        )
        replacement_content_only = (
            current.get("capture_scope")
            == "required_participant_replacement"
            and state.get(
                "required_participant_replacement_identity_enabled"
            ) is True
            and state.get(
                "required_participant_content_identity_separation_enabled"
            ) is True
        )
        question = _field(
            "element_content_crop_verdict",
            (
                "Does the exact attached crop visibly contain the proposed "
                "replacement content? Judge only that proposed content here; "
                "the code-controlled next question separately compares it "
                "with the preserved required identity."
                if replacement_content_only else
                "Does the exact attached crop alone visibly establish every "
                "part of the claimed content, including any label, category, "
                "time, role, or other contextual qualifier? Choose "
                "requires_visible_context when any claimed identity depends "
                "on visible source context outside this crop."
                if context_contract else
                "Does the exact attached crop visibly contain the claimed "
                "content for this proposed endpoint?"
            ),
            "choice",
            choices=_endpoint_crop_verdict_choices(state),
        )
        question["endpoint_crop_evidence"] = evidence
    elif stage == "required_participant_replacement_identity_verdict":
        required_claim = current.get("required_identity_claim")
        if not isinstance(required_claim, str) or not required_claim:
            raise InterviewError("required-participant-identity-claim-missing")
        evidence = current.get("endpoint_crop_evidence")
        if not _valid_endpoint_evidence(state, evidence):
            raise InterviewError("endpoint-crop-evidence-missing")
        question = _field(
            "required_participant_replacement_identity_verdict",
            (
                "Does the proposed replacement represent the same required "
                "source unit described by the preserved original claim, or a "
                "different visible unit?"
            ),
            "choice",
            choices=["same_required_source_unit", "different_source_unit"],
        )
        question["endpoint_crop_evidence"] = evidence
        question["required_identity_comparison"] = {
            "required_claim": required_claim,
            "proposed_kind": current["kind"],
            "proposed_content": current["content"],
            "proposed_bounds": [
                current["left"], current["top"],
                current["right"], current["bottom"],
            ],
        }
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
        if _required_participant_needs_crop_verification(state):
            evidence = current.get("endpoint_crop_evidence")
            if not _valid_endpoint_evidence(state, evidence):
                raise InterviewError("endpoint-crop-evidence-missing")
            context_contract = (
                state.get("contextual_endpoint_verification_enabled") is True
            )
            question = _field(
                "required_participant_crop_verdict",
                (
                    "Does the exact attached crop alone visibly establish every "
                    "part of the claimed content, including any label, category, "
                    "time, role, or other contextual qualifier? Choose "
                    "requires_visible_context when any claimed identity depends "
                    "on visible source context outside this crop."
                    if context_contract else
                    "Does the exact attached crop visibly contain the complete "
                    "claimed content for this already-recorded required participant?"
                ),
                "choice",
                choices=_endpoint_crop_verdict_choices(state),
            )
            question["endpoint_crop_evidence"] = evidence
        else:
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
    elif stage in {"obligation_endpoint_x", "obligation_endpoint_y"}:
        obligation = _pending_obligation(state)
        if obligation is None:
            raise InterviewError("relationship-obligation-missing")
        element = _element_by_id(state, str(obligation["element_id"]))
        axis = "x" if stage.endswith("_x") else "y"
        question = _field(
            stage,
            f"What normalized {axis} coordinate lies inside the obligated recorded element?",
            "integer",
            minimum=0,
            maximum=999,
        )
        question["binding_element"] = element
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
        if (
            state.get("overlap_identity_selection_enabled") is True
            and issue.get("reason") == "no_unique_recorded_element"
            and isinstance(issue.get("matching_element_ids"), list)
            and len(issue["matching_element_ids"]) > 1
        ):
            choices.insert(-1, "select_recorded_element")
        elif (
            state.get("spatial_identity_refinement_enabled") is True
            and issue.get("reason") == "no_unique_recorded_element"
            and isinstance(issue.get("matching_element_ids"), list)
            and len(issue["matching_element_ids"]) > 1
        ):
            choices.insert(-1, "refine_spatial_identity")
        question = _field(
            "relationship_binding_resolution",
            "Code could not bind the submitted participant coordinates to exactly one valid recorded element. What is the faithful next step?",
            "choice",
            choices=choices,
        )
        question["binding_issue"] = issue
    elif stage == "relationship_binding_intended_element":
        issue = current.get(
            "overlap_identity_selection_issue",
            current.get("spatial_identity_issue"),
        )
        if not isinstance(issue, dict) or not isinstance(
            issue.get("matching_element_ids"), list,
        ):
            raise InterviewError("relationship-spatial-identity-issue-missing")
        question = _field(
            "relationship_binding_intended_element",
            "Which listed recorded element is the exact visible participant intended by the submitted point?",
            "choice",
            choices=[str(item) for item in issue["matching_element_ids"]],
        )
        question["binding_issue"] = issue
        question["matching_elements"] = [
            _element_by_id(state, str(element_id))
            for element_id in issue["matching_element_ids"]
        ]
    elif stage == "relationship_spatial_conflict_element":
        conflict_ids = current.get("spatial_conflicting_element_ids")
        if not isinstance(conflict_ids, list) or not conflict_ids:
            raise InterviewError("relationship-spatial-conflicts-missing")
        question = _field(
            "relationship_spatial_conflict_element",
            "Which other recorded element creates the active spatial identity conflict?",
            "choice",
            choices=[str(item) for item in conflict_ids],
        )
        question["conflicting_elements"] = [
            _element_by_id(state, str(element_id))
            for element_id in conflict_ids
        ]
    elif stage == "relationship_spatial_identity":
        issue = current.get("spatial_identity_issue")
        intended_id = current.get("spatial_intended_element_id")
        conflicting_id = current.get("spatial_conflicting_element_id")
        if (
            not isinstance(issue, dict)
            or not isinstance(intended_id, str)
            or not isinstance(conflicting_id, str)
        ):
            raise InterviewError("relationship-spatial-identity-missing")
        question = _field(
            "relationship_spatial_identity",
            "Are these two overlapping records the same complete visible unit, or distinct visible units?",
            "choice",
            choices=["same_unit", "distinct_unit"],
        )
        question["binding_issue"] = issue
        question["intended_element"] = _element_by_id(state, intended_id)
        question["conflicting_element"] = _element_by_id(state, conflicting_id)
    elif stage in {
        "relationship_refine_left", "relationship_refine_top",
        "relationship_refine_right", "relationship_refine_bottom",
    }:
        conflicting_id = current.get("spatial_conflicting_element_id")
        if not isinstance(conflicting_id, str):
            raise InterviewError("relationship-spatial-conflict-missing")
        target = _element_by_id(state, conflicting_id)
        previous = [int(value) for value in target["region"]]
        field = stage.removeprefix("relationship_refine_")
        limits = {
            "left": (previous[0], previous[2] - 1),
            "top": (previous[1], previous[3] - 1),
            "right": (int(current.get("refine_left", previous[0])) + 1, previous[2]),
            "bottom": (int(current.get("refine_top", previous[1])) + 1, previous[3]),
        }
        minimum, maximum = limits[field]
        question = _field(
            stage,
            f"What is the distinct conflicting visible unit's refined normalized {field} coordinate?",
            "integer",
            minimum=minimum,
            maximum=maximum,
        )
        question["spatial_identity_refinement"] = {
            "point": current["spatial_identity_issue"]["point"],
            "intended_element_id": current["spatial_intended_element_id"],
            "conflicting_element": target,
        }
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
        choices = ["retry_coordinates"]
        if (
            state.get("locked_participant_replacement_blocked_enabled")
            is not True
            or len(current.get("locked_identity_participants", {})) < 2
        ):
            choices.append("record_visible_endpoint")
        choices.append("record_endpoint_gap")
        question = _field(
            "relationship_visual_resolution",
            "Visible source evidence does not support the proposed pair. What is the faithful next step?",
            "choice",
            choices=choices,
        )
        question["verification_issue"] = issue
    elif stage == "relationship_visual_endpoint_role":
        choices = ["origin", "target"]
        if state.get("locked_participant_replacement_blocked_enabled") is True:
            locked = current.get("locked_identity_participants", {})
            if not isinstance(locked, dict):
                raise InterviewError("locked-relationship-participants-invalid")
            choices = [role for role in choices if role not in locked]
        if not choices:
            raise InterviewError("no-replaceable-relationship-participant")
        question = _field(
            "relationship_visual_endpoint_role",
            "Which proposed participant must be replaced by a newly recorded visible endpoint?",
            "choice",
            choices=choices,
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
    if contract >= 4 and stage.startswith(
        ("region_", "context_obligation_")
    ):
        region = _active_scan_region(state)
        if region is None:
            raise InterviewError("scan-region-missing")
        question["scan_region"] = {
            "id": region["id"], "bounds": region["bounds"],
        }
        if contract >= 8:
            question["region_evidence"] = region["evidence"]
    elif contract >= 8 and isinstance(current.get("scan_region_id"), str):
        region = _active_scan_region(state)
        if region is None or region["id"] != current["scan_region_id"]:
            raise InterviewError("scan-region-binding-invalid")
        question["region_evidence"] = region["evidence"]
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
        if field_id in {"context_anchor_x", "context_anchor_y"}:
            evidence = question.get("region_evidence")
            if not isinstance(evidence, dict):
                return None, f"{field_id}: active region evidence is missing"
            context_bounds = evidence.get("evidence_normalized_bounds")
            core_bounds = evidence.get("core_normalized_bounds")
            if (
                not isinstance(context_bounds, list)
                or len(context_bounds) != 4
                or not isinstance(core_bounds, list)
                or len(core_bounds) != 4
            ):
                return None, f"{field_id}: active ownership bounds are missing"
            if field_id == "context_anchor_x":
                if not int(context_bounds[0]) <= parsed < int(context_bounds[2]):
                    return None, (
                        f"context_anchor_x: coordinate {parsed} must be inside "
                        f"the visible context bounds {context_bounds[0]} through "
                        f"{int(context_bounds[2]) - 1}"
                    )
            else:
                if not int(context_bounds[1]) <= parsed < int(context_bounds[3]):
                    return None, (
                        f"context_anchor_y: coordinate {parsed} must be inside "
                        f"the visible context bounds {context_bounds[1]} through "
                        f"{int(context_bounds[3]) - 1}"
                    )
                x = state["current"].get("context_anchor_x")
                if not isinstance(x, int):
                    return None, "context_anchor_y: the accepted x coordinate is missing"
                if (
                    int(core_bounds[0]) <= x < int(core_bounds[2])
                    and int(core_bounds[1]) <= parsed < int(core_bounds[3])
                ):
                    return None, (
                        "context_anchor_y: submitted point "
                        f"[{x}, {parsed}] is inside the active ownership core; "
                        "classify the candidate as owned_by_active_core instead"
                    )
        if field_id == "relationship_refine_bottom":
            issue = state["current"].get("spatial_identity_issue")
            if not isinstance(issue, dict) or not isinstance(issue.get("point"), list):
                return None, "relationship_refine_bottom: spatial identity point is missing"
            bounds = [
                int(state["current"]["refine_left"]),
                int(state["current"]["refine_top"]),
                int(state["current"]["refine_right"]),
                parsed,
            ]
            x, y = (int(item) for item in issue["point"])
            if bounds[0] <= x < bounds[2] and bounds[1] <= y < bounds[3]:
                return None, (
                    "relationship_refine_bottom: refined bounds must exclude "
                    f"the conflicting point [{x}, {y}]"
                )
        if field_id in {"obligation_endpoint_x", "obligation_endpoint_y"}:
            element = question.get("binding_element")
            if not isinstance(element, dict):
                return None, f"{field_id}: obligated element is missing"
            bounds = element.get("region")
            element_id = element.get("id")
            if (
                not isinstance(bounds, list)
                or len(bounds) != 4
                or not isinstance(element_id, str)
            ):
                return None, f"{field_id}: obligated element bounds are invalid"
            inside = (
                int(bounds[0]) <= parsed < int(bounds[2])
                if field_id.endswith("_x")
                else int(bounds[1]) <= parsed < int(bounds[3])
            )
            if not inside:
                return None, (
                    f"{field_id}: coordinate {parsed} must be inside obligated "
                    f"{element_id} bounds {bounds}"
                )
        if (
            field_id in {
                "element_left", "element_top", "element_right", "element_bottom",
            }
            and isinstance(state["current"].get("context_obligation_id"), str)
        ):
            obligation = _context_obligation_by_id(
                state, state["current"]["context_obligation_id"],
            )
            anchor = obligation.get("anchor")
            if (
                not isinstance(anchor, list)
                or len(anchor) != 2
                or not all(isinstance(item, int) for item in anchor)
            ):
                return None, f"{field_id}: deferred candidate anchor is invalid"
            outside = (
                (field_id == "element_left" and parsed > anchor[0])
                or (field_id == "element_top" and parsed > anchor[1])
                or (field_id == "element_right" and parsed <= anchor[0])
                or (field_id == "element_bottom" and parsed <= anchor[1])
            )
            if outside:
                relation = {
                    "element_left": f"at most {anchor[0]}",
                    "element_top": f"at most {anchor[1]}",
                    "element_right": f"greater than {anchor[0]}",
                    "element_bottom": f"greater than {anchor[1]}",
                }[field_id]
                return None, (
                    f"{field_id}: value {parsed} does not contain deferred "
                    f"candidate anchor {anchor}; enter a value {relation}"
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
    if isinstance(current.get("endpoint_verification"), dict):
        element["endpoint_verification"] = current["endpoint_verification"]
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
    context_obligation_id = current.get("context_obligation_id")
    if isinstance(context_obligation_id, str):
        obligation = _context_obligation_by_id(state, context_obligation_id)
        if obligation.get("status") != "pending":
            raise InterviewError("context-obligation-already-resolved")
        obligation.update({
            "status": "resolved",
            "resolution": "element",
            "element_id": element_id,
            "gap_reason": "",
        })
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


def _record_rejected_endpoint(
    state: dict[str, Any], verdict: str,
) -> None:
    current = state["current"]
    evidence = current.get("endpoint_crop_evidence")
    if verdict not in {
        "does_not_contain_claimed_content",
        "requires_visible_context",
        "unreadable",
    }:
        raise InterviewError("endpoint-crop-verdict-invalid")
    if not _valid_endpoint_evidence(state, evidence):
        raise InterviewError("endpoint-crop-evidence-missing")
    element_id = _endpoint_candidate_id(state)
    if verdict == "does_not_contain_claimed_content":
        reason = "The claimed content is not visible inside the claimed source bounds."
    elif verdict == "requires_visible_context":
        reason = (
            "The claimed identity requires visible context outside the recorded "
            "source bounds."
        )
    else:
        reason = "The exact claimed source bounds are not faithfully readable."
    state["elements"].append({
        "id": element_id,
        "kind": current["kind"],
        "region": [
            current["left"], current["top"],
            current["right"], current["bottom"],
        ],
        "status": "gap",
        "content": "",
        "gap_reason": reason,
        "capture_scope": "relationship_endpoint",
        "endpoint_verification": {
            "verdict": verdict,
            "claimed_content": current["content"],
            "evidence": evidence,
        },
    })
    state["current"] = {
        "return_stage": current.get("return_stage", "element_more"),
        "capture_scope": "relationship_endpoint",
    }
    state["stage"] = "element_kind"


def _record_overbroad_endpoint(state: dict[str, Any]) -> None:
    current = state["current"]
    element_id = _endpoint_candidate_id(state)
    verification: dict[str, object] = {
        "verdict": "multiple_independent_visible_elements",
        "claimed_content": current["content"],
    }
    evidence = current.get("endpoint_crop_evidence")
    if isinstance(evidence, dict):
        verification["evidence"] = evidence
    state["elements"].append({
        "id": element_id,
        "kind": current["kind"],
        "region": [
            current["left"], current["top"],
            current["right"], current["bottom"],
        ],
        "status": "gap",
        "content": "",
        "gap_reason": (
            "The proposed endpoint bounds combine multiple independent visible "
            "elements and cannot identify one relationship participant."
        ),
        "capture_scope": "relationship_endpoint",
        "endpoint_verification": verification,
    })
    state["current"] = {
        "return_stage": current.get("return_stage", "element_more"),
        "capture_scope": "relationship_endpoint",
    }
    state["stage"] = "element_kind"


def _start_relationship_endpoint_context(state: dict[str, Any]) -> None:
    current = state["current"]
    selector_evidence = current.pop("endpoint_crop_evidence", None)
    if not isinstance(selector_evidence, dict):
        raise InterviewError("endpoint-crop-evidence-missing")
    current["capture_scope"] = "relationship_endpoint_context"
    current["selector_region"] = [
        current["left"], current["top"],
        current["right"], current["bottom"],
    ]
    current["selector_evidence"] = selector_evidence
    state["stage"] = "endpoint_context_left"


def _required_participant_verdict_supersession(
    state: dict[str, Any], verdict: str,
) -> None:
    evidence = state["current"].get("endpoint_crop_evidence")
    if not _valid_endpoint_evidence(state, evidence):
        raise InterviewError("endpoint-crop-evidence-missing")
    obligation = _pending_obligation(state)
    if obligation is None:
        raise InterviewError("relationship-obligation-missing")
    element_id = str(obligation["element_id"])
    target = _element_by_id(state, element_id)
    previous = {**target, "region": list(target["region"])}
    if (
        verdict == "requires_visible_context"
        and state.get("endpoint_context_evidence_enabled") is True
    ):
        state["current"] = {
            "capture_scope": "required_participant_context",
            "element_id": element_id,
            "claimed_content": previous["content"],
            "selector_region": list(previous["region"]),
            "rejected_endpoint_evidence": evidence,
        }
        state["stage"] = "endpoint_context_left"
        return
    if verdict == "contains_claimed_content":
        replacement = {
            **previous,
            "endpoint_verification": {
                "verdict": "supported",
                "claimed_content": previous["content"],
                "evidence": evidence,
                **_supported_verification_fields(state),
            },
        }
        next_current: dict[str, object] | None = None
        return_stage = "obligation_resolution"
        reason = "required_participant_source_verified"
    elif verdict in {
        "does_not_contain_claimed_content",
        "requires_visible_context",
        "unreadable",
    }:
        if verdict == "does_not_contain_claimed_content":
            reason_text = (
                "The claimed content is not visible inside the claimed source bounds."
            )
        elif verdict == "requires_visible_context":
            reason_text = (
                "The claimed identity requires visible context outside the recorded "
                "source bounds."
            )
        else:
            reason_text = "The exact claimed source bounds are not faithfully readable."
        replacement = {
            **previous,
            "status": "gap",
            "content": "",
            "gap_reason": reason_text,
            "endpoint_verification": {
                "verdict": verdict,
                "claimed_content": previous["content"],
                "evidence": evidence,
            },
        }
        next_current = {
            "capture_scope": "required_participant_replacement",
            "return_stage": "obligation_resolution",
            "superseded_element_id": element_id,
            "required_identity_claim": previous["content"],
        }
        return_stage = "element_kind"
        reason = "required_participant_source_rejected"
    else:
        raise InterviewError("endpoint-crop-verdict-invalid")
    state["element_supersession_pending"] = {
        "event": {
            "element_id": element_id,
            "reason": reason,
            "previous_element": previous,
            "trigger_candidate": {
                "kind": previous["kind"],
                "region": list(previous["region"]),
                "verification_scope": "required_recorded_participant",
            },
            "replacement_element": replacement,
        },
        "return_stage": return_stage,
        "next_current": next_current,
    }
    state["stage"] = "element_supersession_pending"


def _complete_endpoint_context_verdict(
    state: dict[str, Any], verdict: str,
) -> None:
    current = state["current"]
    evidence = current.get("endpoint_crop_evidence")
    if not _valid_endpoint_evidence(state, evidence):
        raise InterviewError("endpoint-context-evidence-missing")
    if current.get("capture_scope") == "relationship_endpoint_context":
        selector = current.get("selector_region")
        selector_evidence = current.get("selector_evidence")
        if (
            not isinstance(selector, list)
            or len(selector) != 4
            or not isinstance(selector_evidence, dict)
        ):
            raise InterviewError("relationship-endpoint-selector-missing")
        if verdict == "contains_claimed_content":
            element_id = _endpoint_candidate_id(state)
            state["elements"].append({
                "id": element_id,
                "kind": current["kind"],
                "region": list(selector),
                "status": "readable",
                "content": current["content"],
                "gap_reason": "",
                "capture_scope": "relationship_endpoint",
                "endpoint_verification": {
                    "verdict": "supported",
                    "claimed_content": current["content"],
                    "evidence": evidence,
                    "selector_evidence": selector_evidence,
                    "selector_region": list(selector),
                    "claim_scope": "selector_with_context_v3",
                },
            })
            state["current"] = {
                "element_id": element_id,
                "return_stage": current.get(
                    "return_stage", "element_more",
                ),
            }
            state["stage"] = "element_relationship_obligation"
            return
        if verdict in {
            "does_not_contain_claimed_content", "unreadable",
        }:
            for coordinate, value in zip(
                ("left", "top", "right", "bottom"), selector, strict=True,
            ):
                current[coordinate] = value
            current["capture_scope"] = "relationship_endpoint"
            current["endpoint_crop_evidence"] = selector_evidence
            _record_rejected_endpoint(state, verdict)
            return
        if verdict != "requires_visible_context":
            raise InterviewError("endpoint-crop-verdict-invalid")
        for key in (
            "context_left", "context_top", "context_right", "context_bottom",
            "endpoint_crop_evidence",
        ):
            current.pop(key, None)
        current["last_context_verdict"] = verdict
        current["last_context_evidence"] = evidence
        state["stage"] = "endpoint_context_left"
        return
    element_id = current.get("element_id")
    if not isinstance(element_id, str):
        raise InterviewError("endpoint-context-element-missing")
    target = _element_by_id(state, element_id)
    previous = {**target, "region": list(target["region"])}
    if verdict == "contains_claimed_content":
        replacement = {
            **previous,
            "endpoint_verification": {
                "verdict": "supported",
                "claimed_content": previous["content"],
                "evidence": evidence,
                "selector_region": list(previous["region"]),
                "claim_scope": "selector_with_context_v3",
            },
        }
        state["element_supersession_pending"] = {
            "event": {
                "element_id": element_id,
                "reason": "required_participant_context_verified",
                "previous_element": previous,
                "trigger_candidate": {
                    "region": list(evidence["normalized_bounds"]),
                    "verification_scope": "required_participant_context",
                },
                "replacement_element": replacement,
            },
            "return_stage": "obligation_resolution",
            "next_current": None,
        }
        state["stage"] = "element_supersession_pending"
        return
    if (
        verdict == "does_not_contain_claimed_content"
        and state.get("negative_context_replacement_enabled") is True
    ):
        replacement = {
            **previous,
            "status": "gap",
            "content": "",
            "gap_reason": (
                "The claimed content is not visible inside the claimed source bounds."
            ),
            "endpoint_verification": {
                "verdict": verdict,
                "claimed_content": previous["content"],
                "evidence": evidence,
                "selector_region": list(previous["region"]),
            },
        }
        state["element_supersession_pending"] = {
            "event": {
                "element_id": element_id,
                "reason": "required_participant_source_rejected",
                "previous_element": previous,
                "trigger_candidate": {
                    "region": list(evidence["normalized_bounds"]),
                    "verification_scope": "required_participant_context",
                },
                "replacement_element": replacement,
            },
            "return_stage": "element_kind",
            "next_current": {
                "capture_scope": "required_participant_replacement",
                "return_stage": "obligation_resolution",
                "superseded_element_id": element_id,
                "required_identity_claim": previous["content"],
            },
        }
        state["stage"] = "element_supersession_pending"
        return
    for key in (
        "context_left", "context_top", "context_right", "context_bottom",
        "endpoint_crop_evidence",
    ):
        current.pop(key, None)
    current["last_context_verdict"] = verdict
    current["last_context_evidence"] = evidence
    state["stage"] = "endpoint_context_left"


def _required_participant_replacement_supersession(
    state: dict[str, Any], verdict: str,
) -> None:
    current = state["current"]
    evidence = current.get("endpoint_crop_evidence")
    if not _valid_endpoint_evidence(state, evidence):
        raise InterviewError("endpoint-crop-evidence-missing")
    target_id = current.get("superseded_element_id")
    if not isinstance(target_id, str):
        raise InterviewError("element-supersession-target-missing")
    target = _element_by_id(state, target_id)
    previous = {**target, "region": list(target["region"])}
    bounds = [
        current["left"], current["top"],
        current["right"], current["bottom"],
    ]
    if verdict == "contains_claimed_content":
        identity_continuity = None
        current_verification = current.get("endpoint_verification")
        if isinstance(current_verification, dict):
            identity_continuity = current_verification.get(
                "identity_continuity"
            )
        replacement = {
            **previous,
            "kind": current["kind"],
            "region": bounds,
            "status": "readable",
            "content": current["content"],
            "gap_reason": "",
            "endpoint_verification": {
                "verdict": "supported",
                "claimed_content": current["content"],
                "evidence": evidence,
                **_supported_verification_fields(state),
                **(
                    {"identity_continuity": identity_continuity}
                    if isinstance(identity_continuity, dict) else {}
                ),
            },
        }
        next_current: dict[str, object] | None = None
        return_stage = "obligation_resolution"
        reason = "required_participant_replaced_from_source"
    elif verdict in {
        "does_not_contain_claimed_content",
        "requires_visible_context",
        "unreadable",
    }:
        if verdict == "does_not_contain_claimed_content":
            reason_text = (
                "The replacement claim is not visible inside the claimed source bounds."
            )
        elif verdict == "requires_visible_context":
            reason_text = (
                "The replacement identity requires visible context outside the "
                "recorded source bounds."
            )
        else:
            reason_text = "The replacement source bounds are not faithfully readable."
        replacement = {
            **previous,
            "kind": current["kind"],
            "region": bounds,
            "status": "gap",
            "content": "",
            "gap_reason": reason_text,
            "endpoint_verification": {
                "verdict": verdict,
                "claimed_content": current["content"],
                "evidence": evidence,
            },
        }
        next_current = {
            "capture_scope": "required_participant_replacement",
            "return_stage": "obligation_resolution",
            "superseded_element_id": target_id,
            "required_identity_claim": current.get("required_identity_claim", ""),
        }
        return_stage = "element_kind"
        reason = "required_participant_replacement_rejected"
    else:
        raise InterviewError("endpoint-crop-verdict-invalid")
    state["element_supersession_pending"] = {
        "event": {
            "element_id": target_id,
            "reason": reason,
            "previous_element": previous,
            "trigger_candidate": {
                "kind": current["kind"],
                "region": bounds,
                "verification_scope": "required_participant_replacement",
            },
            "replacement_element": replacement,
        },
        "return_stage": return_stage,
        "next_current": next_current,
    }
    state["stage"] = "element_supersession_pending"


def _prepare_element_supersession(
    state: dict[str, Any], field: str, value: str,
) -> None:
    current = state["current"]
    current[field] = value
    target_id = current.get("superseded_element_id")
    if not isinstance(target_id, str):
        raise InterviewError("element-supersession-target-missing")
    target = _element_by_id(state, target_id)
    status = str(current["merge_status"])
    previous = {**target, "region": list(target["region"])}
    replacement = {
        **previous,
        "region": [
            current["merge_left"], current["merge_top"],
            current["merge_right"], current["merge_bottom"],
        ],
        "status": status,
        "content": current.get("merge_content", "") if status == "readable" else "",
        "gap_reason": (
            current.get("merge_gap_reason", "") if status == "gap" else ""
        ),
    }
    trigger_candidate: dict[str, object] = {
        "kind": current["kind"],
        "region": [
            current["left"], current["top"],
            current["right"], current["bottom"],
        ],
    }
    if isinstance(current.get("scan_region_id"), str):
        trigger_candidate["scan_region_id"] = current["scan_region_id"]
    event = {
        "element_id": target_id,
        "reason": "same_visible_unit",
        "previous_element": previous,
        "trigger_candidate": trigger_candidate,
        "replacement_element": replacement,
    }
    state["element_supersession_pending"] = {
        "event": event,
        "return_stage": current.get("return_stage", "element_more"),
    }
    state["stage"] = "element_supersession_pending"


def _apply_element_supersession(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    pending = state.get("element_supersession_pending")
    if not isinstance(pending, dict) or event != pending.get("event"):
        raise InterviewError("element-supersession-invalid")
    target_id = str(event["element_id"])
    target = _element_by_id(state, target_id)
    if target != event["previous_element"]:
        raise InterviewError("element-supersession-target-changed")
    replacement = event["replacement_element"]
    if not isinstance(replacement, dict) or replacement.get("id") != target_id:
        raise InterviewError("element-supersession-replacement-invalid")
    replacement_verification = replacement.get("endpoint_verification")
    if (
        event.get("reason") in {
            "required_participant_source_rejected",
            "required_participant_replacement_rejected",
        }
        and isinstance(replacement_verification, dict)
        and replacement_verification.get("verdict") == "requires_visible_context"
        and target.get("status") == "readable"
    ):
        state.setdefault("_context_selector_candidates", {}).setdefault(
            target_id, {**target, "region": list(target["region"])},
        )
    index = state["elements"].index(target)
    state["elements"][index] = replacement
    state["element_supersession_pending"] = None
    return_stage = str(pending["return_stage"])
    next_current = pending.get("next_current")
    relationship_draft = state.get("relationship_draft")
    if isinstance(next_current, dict):
        state["current"] = dict(next_current)
    elif return_stage.startswith("relationship_") and isinstance(
        relationship_draft, dict,
    ):
        state["current"] = relationship_draft
        state["relationship_draft"] = None
    else:
        state["current"] = {}
    state["stage"] = return_stage


def _prepare_spatial_identity_refinement(
    state: dict[str, Any], bottom: int,
) -> None:
    current = state["current"]
    current["refine_bottom"] = bottom
    issue = current.get("spatial_identity_issue")
    intended_id = current.get("spatial_intended_element_id")
    conflicting_id = current.get("spatial_conflicting_element_id")
    if (
        not isinstance(issue, dict)
        or issue.get("participant") not in {"origin", "target"}
        or not isinstance(issue.get("point"), list)
        or not isinstance(intended_id, str)
        or not isinstance(conflicting_id, str)
    ):
        raise InterviewError("relationship-spatial-identity-invalid")
    target = _element_by_id(state, conflicting_id)
    previous = {**target, "region": list(target["region"])}
    replacement = {
        **previous,
        "region": [
            int(current["refine_left"]), int(current["refine_top"]),
            int(current["refine_right"]), int(current["refine_bottom"]),
        ],
    }
    event: dict[str, object] = {
        "element_id": conflicting_id,
        "reason": "distinct_visible_unit",
        "intended_element_id": intended_id,
        "conflicting_point": list(issue["point"]),
        "previous_element": previous,
        "replacement_element": replacement,
    }
    state["spatial_identity_refinement_pending"] = {
        "event": event,
        "participant": issue["participant"],
    }
    state["stage"] = "spatial_identity_refinement_pending"


def _apply_spatial_identity_refinement(
    state: dict[str, Any], event: dict[str, object], *, contract: int,
) -> None:
    pending = state.get("spatial_identity_refinement_pending")
    if not isinstance(pending, dict) or event != pending.get("event"):
        raise InterviewError("relationship-spatial-identity-refinement-invalid")
    target_id = event.get("element_id")
    if not isinstance(target_id, str):
        raise InterviewError("relationship-spatial-identity-refinement-target-missing")
    target = _element_by_id(state, target_id)
    if target != event.get("previous_element"):
        raise InterviewError("relationship-spatial-identity-refinement-target-changed")
    replacement = event.get("replacement_element")
    if not isinstance(replacement, dict) or replacement.get("id") != target_id:
        raise InterviewError("relationship-spatial-identity-refinement-replacement-invalid")
    previous_region = target.get("region")
    replacement_region = replacement.get("region")
    point = event.get("conflicting_point")
    if (
        not isinstance(previous_region, list)
        or not isinstance(replacement_region, list)
        or len(previous_region) != 4
        or len(replacement_region) != 4
        or not isinstance(point, list)
        or len(point) != 2
        or not all(isinstance(value, int) for value in replacement_region + point)
        or int(replacement_region[0]) < int(previous_region[0])
        or int(replacement_region[1]) < int(previous_region[1])
        or int(replacement_region[2]) > int(previous_region[2])
        or int(replacement_region[3]) > int(previous_region[3])
        or int(replacement_region[0]) >= int(replacement_region[2])
        or int(replacement_region[1]) >= int(replacement_region[3])
        or (
            int(replacement_region[0]) <= int(point[0]) < int(replacement_region[2])
            and int(replacement_region[1]) <= int(point[1]) < int(replacement_region[3])
        )
    ):
        raise InterviewError("relationship-spatial-identity-refinement-bounds-invalid")
    state["elements"][state["elements"].index(target)] = replacement
    participant = str(pending["participant"])
    current = state["current"]
    issue = current.get("spatial_identity_issue")
    if not isinstance(issue, dict) or issue.get("participant") != participant:
        raise InterviewError("relationship-spatial-identity-refinement-state-changed")
    current.setdefault("legacy_binding_refinements", []).append({
        "participant": participant,
        "intended_element_id": event["intended_element_id"],
        "refined_element_id": target_id,
        "conflicting_point": event["conflicting_point"],
        "previous_element": event["previous_element"],
        "replacement_element": event["replacement_element"],
    })
    for key in (
        "spatial_identity_issue", "spatial_intended_element_id",
        "spatial_conflicting_element_id", "spatial_conflicting_element_ids",
        "refine_left", "refine_top", "refine_right", "refine_bottom",
    ):
        current.pop(key, None)
    state["spatial_identity_refinement_pending"] = None
    _bind_relationship_point(
        state, participant, int(current[f"{participant}_y"]), contract=contract,
    )


def _legacy_overlap_binding_migration(
    state: dict[str, Any],
) -> dict[str, object] | None:
    for relationship in reversed(state["relationships"]):
        refinements = relationship.get("legacy_binding_refinements")
        if (
            not isinstance(refinements, list)
            or not refinements
            or "legacy_binding_migration" in relationship
        ):
            continue
        working_elements = {
            str(item["id"]): item for item in state["elements"]
        }
        restorations: list[dict[str, object]] = []
        inactive_refinements: list[dict[str, object]] = []
        selected: dict[str, str] = {}
        active_participant_mismatch = False
        participant_ids = {
            "origin": relationship.get("from_id"),
            "target": relationship.get("to_id"),
        }
        for refinement in reversed(refinements):
            if not isinstance(refinement, dict):
                raise InterviewError("legacy-overlap-refinement-invalid")
            participant = refinement.get("participant")
            intended_id = refinement.get("intended_element_id")
            refined_id = refinement.get("refined_element_id")
            previous = refinement.get("previous_element")
            replacement = refinement.get("replacement_element")
            if (
                participant not in {"origin", "target"}
                or not isinstance(intended_id, str)
                or not isinstance(refined_id, str)
                or not isinstance(previous, dict)
                or not isinstance(replacement, dict)
            ):
                raise InterviewError("legacy-overlap-refinement-state-changed")
            current_element = working_elements.get(refined_id)
            if current_element == replacement:
                restorations.append({
                    "element_id": refined_id,
                    "previous_element": replacement,
                    "replacement_element": previous,
                })
                working_elements[refined_id] = previous
                if participant_ids.get(str(participant)) != intended_id:
                    active_participant_mismatch = True
            else:
                inactive_refinements.append({
                    "element_id": refined_id,
                    "recorded_replacement_element": replacement,
                    "current_element": current_element,
                    "outcome": "already_superseded",
                })
            if participant_ids.get(str(participant)) == intended_id:
                selected[str(participant)] = intended_id
        preserve = (
            relationship.get("status") == "readable"
            and relationship.get("visual_verification") == "supported"
            and not active_participant_mismatch
        )
        action = (
            "preserve_selected_identity" if preserve
            else "invalidate_false_gap"
        )
        previous_relationship = dict(relationship)
        replacement_relationship = {
            **previous_relationship,
            "legacy_binding_migration": {"action": action},
        }
        if preserve:
            replacement_relationship.update({
                "binding_method": (
                    "coordinate_selected_identity_and_containment"
                    if selected
                    else relationship.get("binding_method")
                ),
                "selected_identity_participants": selected,
            })
        else:
            replacement_relationship.update({
                "resolution_status": "invalidated",
                "resolution_invalidation_reason": (
                    "legacy unique-containment binding changed complete "
                    "element bounds"
                ),
            })
        event: dict[str, object] = {
            "relationship_id": relationship["id"],
            "action": action,
            "restorations": restorations,
            "inactive_refinements": inactive_refinements,
            "previous_relationship": previous_relationship,
            "replacement_relationship": replacement_relationship,
        }
        if not preserve:
            obligations = [
                item for item in state["relationship_obligations"]
                if item.get("relationship_id") == relationship["id"]
            ]
            if not obligations:
                raise InterviewError("legacy-overlap-obligation-invalid")
            event["obligation_migrations"] = [{
                "obligation_id": obligation["id"],
                "previous_obligation": dict(obligation),
                "replacement_obligation": {
                    **obligation,
                    "status": "pending",
                    "resolution": None,
                    "relationship_id": None,
                },
            } for obligation in obligations]
        return event
    return None


def _apply_legacy_overlap_binding_migration(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    relationship_id = event.get("relationship_id")
    relationship = next((
        item for item in state["relationships"]
        if item.get("id") == relationship_id
    ), None)
    if relationship is None or relationship != event.get("previous_relationship"):
        raise InterviewError("legacy-overlap-relationship-changed")
    restorations = event.get("restorations")
    if not isinstance(restorations, list):
        raise InterviewError("legacy-overlap-restorations-invalid")
    for restoration in restorations:
        if not isinstance(restoration, dict):
            raise InterviewError("legacy-overlap-restoration-invalid")
        element = _element_by_id(state, str(restoration.get("element_id")))
        if element != restoration.get("previous_element"):
            raise InterviewError("legacy-overlap-restoration-state-changed")
        replacement = restoration.get("replacement_element")
        if not isinstance(replacement, dict):
            raise InterviewError("legacy-overlap-restoration-invalid")
        state["elements"][state["elements"].index(element)] = replacement
    replacement_relationship = event.get("replacement_relationship")
    if not isinstance(replacement_relationship, dict):
        raise InterviewError("legacy-overlap-relationship-invalid")
    state["relationships"][state["relationships"].index(relationship)] = (
        replacement_relationship
    )
    if event.get("action") == "invalidate_false_gap":
        migrations = event.get("obligation_migrations")
        if not isinstance(migrations, list) or not migrations:
            raise InterviewError("legacy-overlap-obligation-invalid")
        for migration in migrations:
            if not isinstance(migration, dict):
                raise InterviewError("legacy-overlap-obligation-invalid")
            obligation = next((
                item for item in state["relationship_obligations"]
                if item.get("id") == migration.get("obligation_id")
            ), None)
            if (
                obligation is None
                or obligation != migration.get("previous_obligation")
            ):
                raise InterviewError("legacy-overlap-obligation-changed")
            replacement_obligation = migration.get("replacement_obligation")
            if not isinstance(replacement_obligation, dict):
                raise InterviewError("legacy-overlap-obligation-invalid")
            state["relationship_obligations"][
                state["relationship_obligations"].index(obligation)
            ] = replacement_obligation


def _required_participant_gap_migration(
    state: dict[str, Any],
) -> dict[str, object] | None:
    for relationship in reversed(state["relationships"]):
        issue = relationship.get("binding_issue")
        if (
            relationship.get("status") != "gap"
            or relationship.get("resolution_status") == "invalidated"
            or not isinstance(issue, dict)
            or issue.get("reason") != "required_element_not_bound"
            or "required_participant_migration" in relationship
        ):
            continue
        obligations = [
            obligation for obligation in state["relationship_obligations"]
            if obligation.get("relationship_id") == relationship.get("id")
        ]
        if not obligations:
            raise InterviewError("required-participant-obligation-invalid")
        previous_relationship = dict(relationship)
        replacement_relationship = {
            **previous_relationship,
            "required_participant_migration": {
                "action": "reopen_required_participant",
            },
            "resolution_status": "invalidated",
            "resolution_invalidation_reason": (
                "relationship outcome omitted the code-required element"
            ),
        }
        return {
            "relationship_id": relationship["id"],
            "previous_relationship": previous_relationship,
            "replacement_relationship": replacement_relationship,
            "obligation_migrations": [{
                "obligation_id": obligation["id"],
                "previous_obligation": dict(obligation),
                "replacement_obligation": {
                    **obligation,
                    "status": "pending",
                    "resolution": None,
                    "relationship_id": None,
                },
            } for obligation in obligations],
        }
    return None


def _apply_required_participant_gap_migration(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    relationship = next((
        item for item in state["relationships"]
        if item.get("id") == event.get("relationship_id")
    ), None)
    if (
        relationship is None
        or relationship != event.get("previous_relationship")
        or not isinstance(event.get("replacement_relationship"), dict)
    ):
        raise InterviewError("required-participant-relationship-changed")
    state["relationships"][state["relationships"].index(relationship)] = (
        event["replacement_relationship"]
    )
    migrations = event.get("obligation_migrations")
    if not isinstance(migrations, list) or not migrations:
        raise InterviewError("required-participant-obligation-invalid")
    for migration in migrations:
        if not isinstance(migration, dict):
            raise InterviewError("required-participant-obligation-invalid")
        obligation = next((
            item for item in state["relationship_obligations"]
            if item.get("id") == migration.get("obligation_id")
        ), None)
        if (
            obligation is None
            or obligation != migration.get("previous_obligation")
            or not isinstance(migration.get("replacement_obligation"), dict)
        ):
            raise InterviewError("required-participant-obligation-changed")
        state["relationship_obligations"][
            state["relationship_obligations"].index(obligation)
        ] = migration["replacement_obligation"]


def _prepare_context_deferral(
    state: dict[str, Any], *, contract: int,
) -> None:
    current = state["current"]
    region = _active_scan_region(state)
    if (
        region is None
        or current.get("scan_region_id") != region["id"]
        or not isinstance(region.get("evidence"), dict)
    ):
        raise InterviewError("context-deferral-region-invalid")
    evidence = region["evidence"]
    if not isinstance(evidence.get("guide_sha256"), str):
        raise InterviewError("context-deferral-guide-missing")
    event: dict[str, object] = {
        "region_id": region["id"],
        "candidate_kind": current["kind"],
        "reason": "context_only",
        "crop_sha256": evidence["crop_sha256"],
        "guide_sha256": evidence["guide_sha256"],
    }
    if contract >= 12:
        x = current.get("context_anchor_x")
        y = current.get("context_anchor_y")
        if not isinstance(x, int) or not isinstance(y, int):
            raise InterviewError("context-deferral-anchor-missing")
        owner = _region_for_point(state, x, y)
        source_index = state["scan_regions"].index(region)
        owner_index = state["scan_regions"].index(owner)
        if owner_index <= source_index:
            raise InterviewError("context-deferral-owner-not-future")
        obligation_count = sum(
            len(item.get("context_candidate_obligations", []))
            for item in state["scan_regions"]
        )
        event.update({
            "owner_region_id": owner["id"],
            "obligation_id": f"context-obligation-{obligation_count + 1:06d}",
            "anchor": [x, y],
        })
    state["context_deferral_pending"] = {
        "event": event,
        "return_stage": current.get("return_stage", "region_element_more"),
    }
    state["stage"] = "context_deferral_pending"


def _context_ownership_reclassification(
    state: dict[str, Any],
    pending: dict[str, object] | None,
    *,
    contract: int,
) -> dict[str, object] | None:
    if contract < 12 or state.get("stage") not in {
        "context_anchor_x", "context_anchor_y",
    }:
        return None
    region = _active_scan_region(state)
    current = state.get("current")
    if (
        not isinstance(region, dict)
        or not isinstance(current, dict)
        or current.get("scan_region_id") != region.get("id")
    ):
        raise InterviewError("context-ownership-reclassification-state-invalid")
    evidence = region.get("evidence")
    if not isinstance(evidence, dict):
        raise InterviewError("context-ownership-evidence-missing")
    if _context_space_available(evidence):
        return None
    pending_id = pending.get("id") if isinstance(pending, dict) else None
    if pending_id not in {None, "context_anchor_x", "context_anchor_y"}:
        raise InterviewError("context-ownership-reclassification-pending-invalid")
    return {
        "region_id": region["id"],
        "candidate_kind": current.get("kind"),
        "previous_classification": "context_only",
        "classification": "owned_by_active_core",
        "reason": "visible_evidence_contains_no_context_area",
        "cancelled_question_id": pending_id,
        "crop_sha256": evidence.get("crop_sha256"),
        "guide_sha256": evidence.get("guide_sha256"),
    }


def _apply_context_ownership_reclassification(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    current = state["current"]
    current.pop("context_anchor_x", None)
    current.pop("context_anchor_y", None)
    state["stage"] = "element_left"


def _apply_context_deferral(
    state: dict[str, Any], event: dict[str, object], *, contract: int,
) -> None:
    pending = state.get("context_deferral_pending")
    region = _active_scan_region(state)
    if contract < 12:
        if (
            not isinstance(pending, dict)
            or event != pending.get("event")
            or region is None
            or event.get("region_id") != region["id"]
            or not isinstance(region.get("deferred_context_candidates"), list)
        ):
            raise InterviewError("context-deferral-invalid")
        region["deferred_context_candidates"].append({
            "candidate_kind": event["candidate_kind"],
            "reason": event["reason"],
            "crop_sha256": event["crop_sha256"],
            "guide_sha256": event["guide_sha256"],
        })
        state["context_deferral_pending"] = None
        state["current"] = {}
        state["stage"] = str(pending["return_stage"])
        return
    anchor = event.get("anchor")
    owner = (
        _region_for_point(state, int(anchor[0]), int(anchor[1]))
        if (
            isinstance(anchor, list)
            and len(anchor) == 2
            and all(isinstance(value, int) for value in anchor)
        )
        else None
    )
    if (
        not isinstance(pending, dict)
        or event != pending.get("event")
        or region is None
        or event.get("region_id") != region["id"]
        or not isinstance(region.get("deferred_context_candidates"), list)
        or owner is None
        or event.get("owner_region_id") != owner["id"]
        or not isinstance(owner.get("context_candidate_obligations"), list)
        or not isinstance(event.get("obligation_id"), str)
        or any(
            event["obligation_id"] == obligation.get("id")
            for candidate_region in state["scan_regions"]
            for obligation in candidate_region.get(
                "context_candidate_obligations", []
            )
        )
    ):
        raise InterviewError("context-deferral-invalid")
    region["deferred_context_candidates"].append({
        "obligation_id": event["obligation_id"],
        "owner_region_id": event["owner_region_id"],
        "anchor": event["anchor"],
        "candidate_kind": event["candidate_kind"],
        "reason": event["reason"],
        "crop_sha256": event["crop_sha256"],
        "guide_sha256": event["guide_sha256"],
    })
    owner["context_candidate_obligations"].append({
        "id": event["obligation_id"],
        "source_region_id": event["region_id"],
        "candidate_kind": event["candidate_kind"],
        "anchor": event["anchor"],
        "status": "pending",
        "resolution": None,
        "element_id": None,
        "gap_reason": "",
    })
    state["context_deferral_pending"] = None
    state["current"] = {}
    state["stage"] = str(pending["return_stage"])


def _finish_context_obligation_gap(
    state: dict[str, Any], reason: str,
) -> None:
    obligation_id = state["current"].get("context_obligation_id")
    region = _active_scan_region(state)
    if not isinstance(obligation_id, str) or region is None:
        raise InterviewError("context-obligation-identity-invalid")
    obligation = _context_obligation_by_id(state, obligation_id)
    anchor = obligation.get("anchor")
    if (
        obligation.get("status") != "pending"
        or not isinstance(anchor, list)
        or len(anchor) != 2
        or not all(isinstance(value, int) for value in anchor)
    ):
        raise InterviewError("context-obligation-gap-invalid")
    element_id = f"element-{len(state['elements']) + 1:06d}"
    element = {
        "id": element_id,
        "kind": obligation["candidate_kind"],
        "region": [anchor[0], anchor[1], anchor[0] + 1, anchor[1] + 1],
        "status": "gap",
        "content": "",
        "gap_reason": reason,
        "capture_scope": region["id"],
        "scan_region_id": region["id"],
    }
    state["elements"].append(element)
    region["element_ids"].append(element_id)
    obligation.update({
        "status": "resolved",
        "resolution": "gap",
        "element_id": element_id,
        "gap_reason": reason,
    })
    state["current"] = {}
    state["stage"] = _next_region_stage(state)


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


def _relationship_obligation_reconciliation(
    state: dict[str, Any],
) -> dict[str, object] | None:
    for relationship in state["relationships"]:
        if (
            relationship.get("status") != "readable"
            or relationship.get("visual_verification") != "supported"
        ):
            continue
        participant_ids = {
            str(element_id)
            for element_id in (
                relationship.get("from_id"), relationship.get("to_id"),
            )
            if isinstance(element_id, str)
        }
        covered = [
            {
                "obligation_id": obligation["id"],
                "element_id": obligation["element_id"],
            }
            for obligation in state["relationship_obligations"]
            if (
                obligation["status"] == "pending"
                and obligation["element_id"] in participant_ids
            )
        ]
        if covered:
            return {
                "relationship_id": relationship["id"],
                "covered_obligations": covered,
            }
    return None


def _apply_relationship_obligation_reconciliation(
    state: dict[str, Any], reconciliation: dict[str, object],
) -> None:
    relationship_id = reconciliation["relationship_id"]
    covered = reconciliation["covered_obligations"]
    if not isinstance(relationship_id, str) or not isinstance(covered, list):
        raise InterviewError("relationship obligation reconciliation has invalid fields")
    obligation_by_id = {
        obligation["id"]: obligation
        for obligation in state["relationship_obligations"]
    }
    for item in covered:
        if not isinstance(item, dict):
            raise InterviewError("relationship obligation reconciliation item is invalid")
        obligation = obligation_by_id.get(item.get("obligation_id"))
        if (
            obligation is None
            or obligation["status"] != "pending"
            or obligation["element_id"] != item.get("element_id")
        ):
            raise InterviewError(
                "relationship obligation reconciliation does not match a pending participant"
            )
        obligation.update({
            "status": "resolved",
            "resolution": "relationship",
            "relationship_id": relationship_id,
        })
    if state["stage"] == "obligation_resolution" and not state["current"]:
        state["stage"] = _next_relationship_stage(state)


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
    if (
        status == "readable"
        and (
            state.get("rejected_endpoint_reuse_blocked_enabled") is True
            or state.get("unreadable_participant_reuse_blocked_enabled") is True
        )
    ):
        ineligible_role = next((
            role for role, element_id in (
                ("origin", relationship["from_id"]),
                ("target", relationship["to_id"]),
            )
            if (
                not isinstance(element_id, str)
                or _participant_reuse_blocked(
                    state, _element_by_id(state, element_id),
                )
            )
        ), None)
        if ineligible_role is not None:
            current.pop("status", None)
            current.pop("description", None)
            current["binding_issue"] = {
                "participant": ineligible_role,
                "point": current.get(f"{ineligible_role}_point"),
                "matching_element_ids": [],
                "reason": "recorded_element_not_readable",
            }
            state["stage"] = "relationship_binding_resolution"
            return
    if current.get("legacy_binding_refinements"):
        relationship["legacy_binding_refinements"] = current[
            "legacy_binding_refinements"
        ]
    if current.get("locked_identity_participants"):
        relationship["locked_identity_participants"] = current[
            "locked_identity_participants"
        ]
    if "origin_point" in current and "target_point" in current:
        locked = bool(current.get("locked_identity_participants"))
        selected = bool(current.get("selected_identity_participants"))
        if locked and selected:
            binding_method = "required_identity_and_selected_identity_containment"
        elif locked:
            binding_method = "required_identity_and_coordinate_containment"
        elif selected:
            binding_method = "coordinate_selected_identity_and_containment"
        else:
            binding_method = "coordinate_unique_containment"
        relationship.update({
            "binding_method": binding_method,
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


def _latest_unverified_required_participant_migration(
    state: dict[str, Any],
) -> dict[str, object] | None:
    if not state["relationships"]:
        return None
    relationship = state["relationships"][-1]
    element_id = relationship.get("verified_element_id")
    if (
        relationship.get("status") != "readable"
        or relationship.get("visual_verification") != "supported"
        or not isinstance(element_id, str)
        or relationship.get("participant_source_verification") is not None
    ):
        return None
    element = _element_by_id(state, element_id)
    if (
        element.get("status") != "readable"
        or _supported_endpoint_verification(element)
    ):
        return None
    obligation = next((
        item for item in state["relationship_obligations"]
        if (
            item.get("id") == relationship.get("verified_obligation_id")
            and item.get("element_id") == element_id
            and item.get("status") == "resolved"
            and item.get("resolution") == "relationship"
            and item.get("relationship_id") == relationship.get("id")
        )
    ), None)
    if obligation is None:
        return None
    reason = (
        "The required participant was reused without immutable-source crop "
        "verification."
    )
    return {
        "relationship_id": relationship["id"],
        "element_id": element_id,
        "previous_relationship": dict(relationship),
        "replacement_relationship": {
            **relationship,
            "status": "gap",
            "description": "",
            "gap_reason": reason,
            "resolution_status": "invalidated",
            "participant_source_verification": "required",
        },
        "previous_obligation": dict(obligation),
        "replacement_obligation": {
            **obligation,
            "status": "pending",
            "resolution": None,
            "relationship_id": None,
        },
    }


def _latest_unverified_replacement_identity_migration(
    state: dict[str, Any], entries: list[dict[str, object]],
) -> dict[str, object] | None:
    """Reopen a replacement accepted without proving required-unit continuity."""

    if state.get("_replacement_identity_migration_applied") is True:
        return None
    relationship = next((
        item for item in reversed(state["relationships"])
        if (
            item.get("status") == "readable"
            and item.get("visual_verification") == "supported"
            and isinstance(item.get("verified_element_id"), str)
        )
    ), None)
    if relationship is None:
        return None
    element_id = str(relationship["verified_element_id"])
    element = _element_by_id(state, element_id)
    verification = element.get("endpoint_verification")
    if (
        not isinstance(verification, dict)
        or isinstance(verification.get("identity_continuity"), dict)
    ):
        return None
    supersession = next((
        {
            key: entry.get(key)
            for key in (
                "element_id", "reason", "previous_element",
                "trigger_candidate", "replacement_element",
            )
        }
        for entry in reversed(entries)
        if (
            entry.get("event") == "element_superseded"
            and entry.get("element_id") == element_id
            and entry.get("reason") == "required_participant_replaced_from_source"
            and entry.get("replacement_element") == element
        )
    ), None)
    if supersession is None:
        return None
    restored_element = supersession.get("previous_element")
    if not isinstance(restored_element, dict):
        return None
    restored_verification = restored_element.get("endpoint_verification")
    required_claim = (
        restored_verification.get("claimed_content")
        if isinstance(restored_verification, dict) else None
    )
    if not isinstance(required_claim, str) or not required_claim:
        return None
    obligation = next((
        item for item in state["relationship_obligations"]
        if (
            item.get("id") == relationship.get("verified_obligation_id")
            and item.get("element_id") == element_id
            and item.get("status") == "resolved"
            and item.get("resolution") == "relationship"
            and item.get("relationship_id") == relationship.get("id")
        )
    ), None)
    if obligation is None:
        return None
    reason = (
        "The replacement was accepted without proving that it represents the "
        "same required source unit."
    )
    return {
        "element_id": element_id,
        "previous_element": {**element, "region": list(element["region"])},
        "replacement_element": restored_element,
        "relationship_id": relationship["id"],
        "previous_relationship": dict(relationship),
        "replacement_relationship": {
            **relationship,
            "status": "gap",
            "description": "",
            "gap_reason": reason,
            "resolution_status": "invalidated",
            "participant_replacement_identity_verification": "required",
        },
        "previous_obligation": dict(obligation),
        "replacement_obligation": {
            **obligation,
            "status": "pending",
            "resolution": None,
            "relationship_id": None,
        },
        "required_identity_claim": required_claim,
    }


def _apply_unverified_replacement_identity_migration(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    element = _element_by_id(state, str(event.get("element_id")))
    relationship = next((
        item for item in state["relationships"]
        if item.get("id") == event.get("relationship_id")
    ), None)
    previous_obligation = event.get("previous_obligation")
    obligation = next((
        item for item in state["relationship_obligations"]
        if (
            isinstance(previous_obligation, dict)
            and item.get("id") == previous_obligation.get("id")
        )
    ), None)
    if (
        element != event.get("previous_element")
        or relationship != event.get("previous_relationship")
        or obligation != previous_obligation
        or not isinstance(event.get("replacement_element"), dict)
        or not isinstance(event.get("replacement_relationship"), dict)
        or not isinstance(event.get("replacement_obligation"), dict)
        or not isinstance(event.get("required_identity_claim"), str)
    ):
        raise InterviewError(
            "replacement-identity-migration-state-changed"
        )
    state["elements"][state["elements"].index(element)] = event[
        "replacement_element"
    ]
    state["relationships"][state["relationships"].index(relationship)] = event[
        "replacement_relationship"
    ]
    state["relationship_obligations"][
        state["relationship_obligations"].index(obligation)
    ] = event["replacement_obligation"]
    state["current"] = {
        "capture_scope": "required_participant_replacement",
        "return_stage": "obligation_resolution",
        "superseded_element_id": event["element_id"],
        "required_identity_claim": event["required_identity_claim"],
    }
    state["_replacement_identity_migration_applied"] = True
    state["stage"] = "element_kind"


def _latest_context_unassessed_participant_migration(
    state: dict[str, Any],
) -> dict[str, object] | None:
    if not state["relationships"]:
        return None
    relationship = state["relationships"][-1]
    element_id = relationship.get("verified_element_id")
    if (
        relationship.get("status") != "readable"
        or relationship.get("visual_verification") != "supported"
        or not isinstance(element_id, str)
        or relationship.get("participant_context_verification") is not None
    ):
        return None
    element = _element_by_id(state, element_id)
    verification = element.get("endpoint_verification")
    if (
        element.get("status") != "readable"
        or not _supported_endpoint_verification(element)
        or not isinstance(verification, dict)
        or verification.get("claim_scope") == "crop_complete_v2"
    ):
        return None
    obligation = next((
        item for item in state["relationship_obligations"]
        if (
            item.get("id") == relationship.get("verified_obligation_id")
            and item.get("element_id") == element_id
            and item.get("status") == "resolved"
            and item.get("resolution") == "relationship"
            and item.get("relationship_id") == relationship.get("id")
        )
    ), None)
    if obligation is None:
        return None
    reason = (
        "The endpoint crop was not assessed for identity qualifiers that may "
        "depend on visible context outside its bounds."
    )
    return {
        "relationship_id": relationship["id"],
        "element_id": element_id,
        "previous_relationship": dict(relationship),
        "replacement_relationship": {
            **relationship,
            "status": "gap",
            "description": "",
            "gap_reason": reason,
            "resolution_status": "invalidated",
            "participant_context_verification": "required",
        },
        "previous_obligation": dict(obligation),
        "replacement_obligation": {
            **obligation,
            "status": "pending",
            "resolution": None,
            "relationship_id": None,
        },
    }


def _apply_latest_unverified_required_participant_migration(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    relationship = state["relationships"][-1] if state["relationships"] else None
    replacement_obligation = event.get("replacement_obligation")
    obligation = next((
        item for item in state["relationship_obligations"]
        if (
            isinstance(replacement_obligation, dict)
            and item.get("id") == replacement_obligation.get("id")
        )
    ), None)
    if (
        relationship != event.get("previous_relationship")
        or obligation != event.get("previous_obligation")
        or not isinstance(event.get("replacement_relationship"), dict)
        or not isinstance(replacement_obligation, dict)
    ):
        raise InterviewError(
            "unverified-required-participant-migration-state-changed"
        )
    state["relationships"][-1] = event["replacement_relationship"]
    state["relationship_obligations"][
        state["relationship_obligations"].index(obligation)
    ] = replacement_obligation
    state["current"] = {}
    state["stage"] = "obligation_resolution"


def _historical_endpoint_grounding_invalidation(
    state: dict[str, Any], *, element_id: str, relationship_id: str,
    reason: str,
) -> dict[str, object]:
    element = _element_by_id(state, element_id)
    relationship = next((
        item for item in state["relationships"]
        if item.get("id") == relationship_id
    ), None)
    if (
        element.get("capture_scope") != "relationship_endpoint"
        or element.get("status") != "readable"
        or not isinstance(relationship, dict)
        or element_id not in {
            relationship.get("from_id"), relationship.get("to_id"),
        }
        or relationship.get("status") != "readable"
    ):
        raise InterviewError("endpoint-grounding-invalidation-target-invalid")
    obligations = [
        item for item in state["relationship_obligations"]
        if item.get("relationship_id") == relationship_id
    ]
    if not obligations:
        raise InterviewError("endpoint-grounding-invalidation-obligation-missing")
    previous_element = {**element, "region": list(element["region"])}
    replacement_element = {
        **previous_element,
        "status": "gap",
        "content": "",
        "gap_reason": reason,
        "endpoint_verification": {
            "verdict": "not_supported",
            "claimed_content": previous_element["content"],
            "reason": reason,
            "evidence": "historical_external_audit",
        },
    }
    previous_relationship = dict(relationship)
    replacement_relationship = {
        **previous_relationship,
        "status": "gap",
        "description": "",
        "gap_reason": reason,
        "visual_verification": "not_supported",
        "resolution_status": "invalidated",
        "endpoint_grounding_invalidation": {
            "element_id": element_id,
            "reason": reason,
        },
    }
    return {
        "element_id": element_id,
        "relationship_id": relationship_id,
        "reason": reason,
        "previous_element": previous_element,
        "replacement_element": replacement_element,
        "previous_relationship": previous_relationship,
        "replacement_relationship": replacement_relationship,
        "obligation_migrations": [{
            "obligation_id": obligation["id"],
            "previous_obligation": dict(obligation),
            "replacement_obligation": {
                **obligation,
                "status": (
                    "resolved"
                    if obligation.get("element_id") == element_id
                    else "pending"
                ),
                "resolution": (
                    "invalidated_endpoint"
                    if obligation.get("element_id") == element_id
                    else None
                ),
                "relationship_id": (
                    relationship_id
                    if obligation.get("element_id") == element_id
                    else None
                ),
            },
        } for obligation in obligations],
    }


def _endpoint_was_rejected(element: dict[str, Any]) -> bool:
    verification = element.get("endpoint_verification")
    return (
        element.get("status") != "readable"
        or (
            isinstance(verification, dict)
            and verification.get("verdict") in {
                "does_not_contain_claimed_content",
                "requires_visible_context",
                "multiple_independent_visible_elements",
                "not_supported",
                "unreadable",
            }
        )
    )


def _endpoint_was_rejected_v1(element: dict[str, Any]) -> bool:
    verification = element.get("endpoint_verification")
    return (
        isinstance(verification, dict)
        and verification.get("verdict") in {
            "does_not_contain_claimed_content",
            "requires_visible_context",
            "multiple_independent_visible_elements",
            "not_supported",
            "unreadable",
        }
    )


def _participant_reuse_blocked(
    state: dict[str, Any], element: dict[str, Any],
) -> bool:
    if state.get("unreadable_participant_reuse_blocked_enabled") is True:
        return _endpoint_was_rejected(element)
    if state.get("rejected_endpoint_reuse_blocked_enabled") is True:
        return _endpoint_was_rejected_v1(element)
    return False


def _readable_relationship_rejected_endpoint_migration(
    state: dict[str, Any], *,
    eligibility_contract: str = "unreadable_participant_v2",
) -> dict[str, object] | None:
    if eligibility_contract == "rejected_endpoint_v1":
        participant_is_ineligible = _endpoint_was_rejected_v1
        reason = (
            "A readable relationship cannot reuse an endpoint rejected by "
            "exact source evidence."
        )
    elif eligibility_contract == "unreadable_participant_v2":
        participant_is_ineligible = _endpoint_was_rejected
        reason = (
            "A readable relationship cannot reuse a participant whose source "
            "projection is not readable."
        )
    else:
        raise InterviewError("rejected-endpoint-eligibility-contract-invalid")
    for relationship in reversed(state["relationships"]):
        if (
            relationship.get("status") != "readable"
            or "rejected_endpoint_invalidation" in relationship
        ):
            continue
        participant_ids = (relationship.get("from_id"), relationship.get("to_id"))
        rejected_ids = [
            str(element_id)
            for element_id in participant_ids
            if (
                isinstance(element_id, str)
                and participant_is_ineligible(_element_by_id(state, element_id))
            )
        ]
        if not rejected_ids:
            continue
        obligations = [
            obligation for obligation in state["relationship_obligations"]
            if obligation.get("relationship_id") == relationship.get("id")
        ]
        if not obligations:
            raise InterviewError("gap-participant-invalidation-obligation-missing")
        previous_relationship = dict(relationship)
        replacement_relationship = {
            **previous_relationship,
            "status": "gap",
            "description": "",
            "gap_reason": reason,
            "visual_verification": "not_supported",
            "resolution_status": "invalidated",
            "rejected_endpoint_invalidation": {
                "element_ids": rejected_ids,
                "reason": reason,
            },
        }
        event: dict[str, object] = {
            "relationship_id": relationship["id"],
            "previous_relationship": previous_relationship,
            "replacement_relationship": replacement_relationship,
            "obligation_migrations": [{
                "obligation_id": obligation["id"],
                "previous_obligation": dict(obligation),
                "replacement_obligation": {
                    **obligation,
                    "status": "pending",
                    "resolution": None,
                    "relationship_id": None,
                },
            } for obligation in obligations],
        }
        if eligibility_contract == "unreadable_participant_v2":
            event["eligibility_contract"] = eligibility_contract
        return event
    return None


def _apply_readable_relationship_rejected_endpoint_migration(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    relationship = next((
        item for item in state["relationships"]
        if item.get("id") == event.get("relationship_id")
    ), None)
    if (
        not isinstance(relationship, dict)
        or relationship != event.get("previous_relationship")
        or not isinstance(event.get("replacement_relationship"), dict)
        or not isinstance(event.get("obligation_migrations"), list)
    ):
        raise InterviewError("rejected-endpoint-invalidation-state-changed")
    state["relationships"][state["relationships"].index(relationship)] = (
        event["replacement_relationship"]
    )
    obligations_by_id = {
        item["id"]: item for item in state["relationship_obligations"]
    }
    for migration in event["obligation_migrations"]:
        if not isinstance(migration, dict):
            raise InterviewError("rejected-endpoint-obligation-invalid")
        obligation = obligations_by_id.get(migration.get("obligation_id"))
        replacement = migration.get("replacement_obligation")
        if (
            obligation != migration.get("previous_obligation")
            or not isinstance(replacement, dict)
        ):
            raise InterviewError("rejected-endpoint-obligation-state-changed")
        state["relationship_obligations"][
            state["relationship_obligations"].index(obligation)
        ] = replacement
    if state.get("stage") == "obligation_resolution" and not state.get("current"):
        state["stage"] = _next_relationship_stage(state)


def _apply_historical_endpoint_grounding_invalidation(
    state: dict[str, Any], event: dict[str, object],
) -> None:
    element = _element_by_id(state, str(event.get("element_id")))
    relationship = next((
        item for item in state["relationships"]
        if item.get("id") == event.get("relationship_id")
    ), None)
    if (
        element != event.get("previous_element")
        or not isinstance(relationship, dict)
        or relationship != event.get("previous_relationship")
    ):
        raise InterviewError("endpoint-grounding-invalidation-state-changed")
    replacement_element = event.get("replacement_element")
    replacement_relationship = event.get("replacement_relationship")
    migrations = event.get("obligation_migrations")
    if (
        not isinstance(replacement_element, dict)
        or not isinstance(replacement_relationship, dict)
        or not isinstance(migrations, list)
    ):
        raise InterviewError("endpoint-grounding-invalidation-invalid")
    state["elements"][state["elements"].index(element)] = replacement_element
    state["relationships"][state["relationships"].index(relationship)] = (
        replacement_relationship
    )
    obligation_by_id = {
        item["id"]: item for item in state["relationship_obligations"]
    }
    for migration in migrations:
        if not isinstance(migration, dict):
            raise InterviewError("endpoint-grounding-obligation-invalid")
        obligation = obligation_by_id.get(migration.get("obligation_id"))
        if obligation != migration.get("previous_obligation") or not isinstance(
            migration.get("replacement_obligation"), dict,
        ):
            raise InterviewError("endpoint-grounding-obligation-changed")
        state["relationship_obligations"][
            state["relationship_obligations"].index(obligation)
        ] = migration["replacement_obligation"]
    if state.get("stage") == "obligation_resolution" and not state.get("current"):
        state["stage"] = _next_relationship_stage(state)


def invalidate_historical_endpoint_grounding(
    attempt_dir: Path,
    *,
    purpose: str,
    contract: int,
    element_id: str,
    relationship_id: str,
    reason: str,
) -> dict[str, object]:
    """Append one audited invalidation without changing prior journal entries."""

    if not reason.strip():
        raise InterviewError("endpoint-grounding-invalidation-reason-missing")
    journal_path = attempt_dir / "interview.jsonl"
    state, pending, completed = _replay(
        _read_journal(journal_path), purpose=purpose, contract=contract,
    )
    if pending is not None or completed:
        raise InterviewError("endpoint-grounding-invalidation-boundary-invalid")
    event = _historical_endpoint_grounding_invalidation(
        state,
        element_id=element_id,
        relationship_id=relationship_id,
        reason=reason,
    )
    return _append(journal_path, "endpoint_grounding_invalidated", event)


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
    if current.get("legacy_binding_refinements"):
        relationship["legacy_binding_refinements"] = current[
            "legacy_binding_refinements"
        ]
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


def _misdirected_participant_gap_migration(
    state: dict[str, Any], history: list[dict[str, object]],
) -> dict[str, object] | None:
    for relationship in reversed(state["relationships"]):
        issue = relationship.get("binding_issue")
        if (
            relationship.get("status") != "gap"
            or relationship.get("resolution_status") == "invalidated"
            or not isinstance(issue, dict)
            or issue.get("reason") != "no_unique_recorded_element"
            or issue.get("participant") not in {"origin", "target"}
        ):
            continue
        obligation = next((
            item for item in state["relationship_obligations"]
            if (
                item.get("relationship_id") == relationship.get("id")
                and item.get("status") == "resolved"
                and item.get("resolution") == "gap"
            )
        ), None)
        if obligation is None:
            continue
        failed_id = str(obligation["element_id"])
        failed = _element_by_id(state, failed_id)
        role = str(issue["participant"])
        failed_field = "from_id" if role == "origin" else "to_id"
        other_field = "to_id" if role == "origin" else "from_id"
        other_id = relationship.get(other_field)
        if (
            relationship.get(failed_field) is not None
            or failed.get("status") != "gap"
            or not isinstance(other_id, str)
        ):
            continue
        gap_indexes = [
            index for index, entry in enumerate(history)
            if (
                entry.get("event") == "answer_recorded"
                and entry.get("question_id") == "relationship_binding_resolution"
                and entry.get("accepted") is True
                and entry.get("parsed") == "record_endpoint_gap"
            )
        ]
        if not gap_indexes:
            continue
        gap_index = gap_indexes[-1]
        visible_indexes = [
            index for index, entry in enumerate(history[:gap_index])
            if (
                entry.get("event") == "answer_recorded"
                and entry.get("question_id") == "relationship_binding_resolution"
                and entry.get("accepted") is True
                and entry.get("parsed") == "record_visible_endpoint"
            )
        ]
        if not visible_indexes:
            continue
        visible_index = visible_indexes[-1]
        supersessions = [
            entry for entry in history[visible_index + 1:gap_index]
            if (
                entry.get("event") == "element_superseded"
                and entry.get("element_id") == other_id
            )
        ]
        if not supersessions:
            continue
        evidence = {
            "failed_participant": role,
            "failed_element_id": failed_id,
            "misdirected_element_id": other_id,
            "record_visible_endpoint_sequence": history[visible_index].get(
                "sequence"
            ),
            "other_participant_supersession_sequence": supersessions[-1].get(
                "sequence"
            ),
            "record_endpoint_gap_sequence": history[gap_index].get("sequence"),
        }
        return {
            "relationship_id": relationship["id"],
            "previous_relationship": dict(relationship),
            "replacement_relationship": {
                **relationship,
                "resolution_status": "invalidated",
                "misdirected_participant_recovery": evidence,
            },
            "previous_obligation": dict(obligation),
            "replacement_obligation": {
                **obligation,
                "status": "pending",
                "resolution": None,
                "relationship_id": None,
            },
            "evidence": evidence,
        }
    return None


def _apply_misdirected_participant_gap_migration(
    state: dict[str, Any], migration: dict[str, object],
) -> None:
    relationship = next((
        item for item in state["relationships"]
        if item.get("id") == migration.get("relationship_id")
    ), None)
    if relationship != migration.get("previous_relationship"):
        raise InterviewError("misdirected-participant-relationship-changed")
    obligation = next((
        item for item in state["relationship_obligations"]
        if item == migration.get("previous_obligation")
    ), None)
    replacement_relationship = migration.get("replacement_relationship")
    replacement_obligation = migration.get("replacement_obligation")
    if (
        obligation is None
        or not isinstance(replacement_relationship, dict)
        or not isinstance(replacement_obligation, dict)
    ):
        raise InterviewError("misdirected-participant-migration-invalid")
    state["relationships"][state["relationships"].index(relationship)] = (
        replacement_relationship
    )
    state["relationship_obligations"][
        state["relationship_obligations"].index(obligation)
    ] = replacement_obligation
    if state.get("stage") == "obligation_resolution" and not state.get("current"):
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
    if current.get("legacy_binding_refinements"):
        relationship["legacy_binding_refinements"] = current[
            "legacy_binding_refinements"
        ]
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
    other_role = "target" if role == "origin" else "origin"
    if element_id == current.get(f"{other_role}_id"):
        current["binding_issue"] = {
            "participant": role,
            "point": [x, y],
            "matching_element_ids": [element_id],
            "reason": "same_element_as_other_participant",
        }
        state["stage"] = "relationship_binding_resolution"
        return
    current[f"{role}_id"] = element_id
    _advance_after_relationship_binding(state, contract=contract)


def _advance_after_relationship_binding(
    state: dict[str, Any], *, contract: int,
) -> None:
    current = state["current"]
    if "origin_id" not in current:
        state["stage"] = "relationship_origin_x"
        return
    if "target_id" not in current:
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
    elif field_id == "context_obligation_resolution":
        obligation = _pending_context_obligation(state)
        region = _active_scan_region(state)
        if obligation is None or region is None:
            raise InterviewError("context-obligation-missing")
        if value == "record_owned_element":
            state["current"] = {
                "kind": obligation["candidate_kind"],
                "context_obligation_id": obligation["id"],
                "return_stage": "region_element_more",
                "scan_region_id": region["id"],
            }
            state["stage"] = "element_left"
        else:
            state["current"] = {
                "context_obligation_id": obligation["id"],
                "scan_region_id": region["id"],
            }
            state["stage"] = "context_obligation_gap_reason"
    elif field_id == "context_obligation_gap_reason":
        _finish_context_obligation_gap(state, str(value))
    elif field_id == "element_more":
        state["stage"] = (
            "element_kind" if value == "yes"
            else _next_relationship_stage(state)
        )
    elif field_id == "element_kind":
        current["kind"] = value
        state["stage"] = (
            "element_ownership"
            if contract >= 11 and isinstance(current.get("scan_region_id"), str)
            else "element_left"
        )
    elif field_id == "element_ownership":
        if value == "context_only":
            if contract >= 12:
                state["stage"] = "context_anchor_x"
            else:
                _prepare_context_deferral(state, contract=contract)
        else:
            state["stage"] = "element_left"
    elif field_id == "context_anchor_x":
        current["context_anchor_x"] = value
        state["stage"] = "context_anchor_y"
    elif field_id == "context_anchor_y":
        current["context_anchor_y"] = value
        _prepare_context_deferral(state, contract=contract)
    elif field_id in {"element_left", "element_top", "element_right", "element_bottom"}:
        current[field_id.removeprefix("element_")] = value
        order = {
            "element_left": "element_top",
            "element_top": "element_right",
            "element_right": "element_bottom",
            "element_bottom": "element_status",
        }
        if (
            field_id == "element_bottom"
            and contract >= 10
            and current.get("capture_scope")
            != "required_participant_replacement"
        ):
            collision_candidates = _element_collision_candidates(state, current)
            if collision_candidates:
                current["unit_collision_candidate_ids"] = [
                    str(item["id"]) for item in collision_candidates
                ]
                state["stage"] = "element_unit_resolution"
            else:
                state["stage"] = "element_status"
        else:
            state["stage"] = order[field_id]
    elif field_id in {
        "endpoint_context_left", "endpoint_context_top",
        "endpoint_context_right", "endpoint_context_bottom",
    }:
        coordinate = field_id.removeprefix("endpoint_context_")
        current[f"context_{coordinate}"] = value
        order = {
            "endpoint_context_left": "endpoint_context_top",
            "endpoint_context_top": "endpoint_context_right",
            "endpoint_context_right": "endpoint_context_bottom",
            "endpoint_context_bottom": "endpoint_context_crop_verdict",
        }
        state["stage"] = order[field_id]
    elif field_id == "element_unit_resolution":
        state["stage"] = (
            "element_same_unit_target" if value == "same_unit"
            else "element_status"
        )
    elif field_id == "element_same_unit_target":
        current["superseded_element_id"] = value
        state["stage"] = "element_merge_left"
    elif field_id in {
        "element_merge_left", "element_merge_top",
        "element_merge_right", "element_merge_bottom",
    }:
        current[field_id.removeprefix("element_")] = value
        order = {
            "element_merge_left": "element_merge_top",
            "element_merge_top": "element_merge_right",
            "element_merge_right": "element_merge_bottom",
            "element_merge_bottom": "element_merge_status",
        }
        state["stage"] = order[field_id]
    elif field_id == "element_merge_status":
        current["merge_status"] = value
        state["stage"] = (
            "element_merge_content"
            if value == "readable"
            else "element_merge_gap_reason"
        )
    elif field_id == "element_merge_content":
        _prepare_element_supersession(state, "merge_content", str(value))
    elif field_id == "element_merge_gap_reason":
        _prepare_element_supersession(state, "merge_gap_reason", str(value))
    elif field_id == "element_status":
        current["status"] = value
        state["stage"] = "element_content" if value == "readable" else "element_gap_reason"
    elif field_id == "element_content":
        if (
            (
                current.get("capture_scope") == "relationship_endpoint"
                and state.get("endpoint_crop_verification_enabled") is True
            )
            or (
                current.get("capture_scope")
                == "required_participant_replacement"
                and state.get(
                    "existing_participant_crop_verification_enabled"
                ) is True
            )
        ):
            current["content"] = str(value)
            state["stage"] = (
                "relationship_endpoint_specificity"
                if (
                    current.get("capture_scope") == "relationship_endpoint"
                    and state.get("endpoint_selector_context_enabled") is True
                )
                else "element_content_crop_verdict"
            )
        else:
            _finish_element(state, "content", str(value), contract=contract)
    elif field_id == "relationship_endpoint_specificity":
        if value in {
            "one_precise_visible_element",
            "one_precise_self_identifying_element",
            "one_precise_element_requires_context",
        }:
            current["identity_context_required"] = (
                value == "one_precise_element_requires_context"
            )
            state["stage"] = "element_content_crop_verdict"
        else:
            _record_overbroad_endpoint(state)
    elif field_id == "element_content_crop_verdict":
        evidence = current.get("endpoint_crop_evidence")
        if not _valid_endpoint_evidence(state, evidence):
            raise InterviewError("endpoint-crop-evidence-missing")
        if (
            value == "contains_claimed_content"
            and current.get("capture_scope") == "relationship_endpoint"
            and current.get("identity_context_required") is True
            and state.get("endpoint_identity_context_choice_enabled") is True
        ):
            _start_relationship_endpoint_context(state)
        elif value == "contains_claimed_content":
            current["endpoint_verification"] = {
                "verdict": "supported",
                "claimed_content": current["content"],
                "evidence": evidence,
                **_supported_verification_fields(state),
            }
            if (
                current.get("capture_scope") == "required_participant_replacement"
                and state.get(
                    "required_participant_replacement_identity_enabled"
                ) is True
                and isinstance(current.get("required_identity_claim"), str)
                and current.get("required_identity_claim")
            ):
                state["stage"] = (
                    "required_participant_replacement_identity_verdict"
                )
            elif current.get("capture_scope") == "required_participant_replacement":
                _required_participant_replacement_supersession(
                    state, str(value),
                )
            else:
                _finish_element(
                    state, "content", str(current["content"]), contract=contract,
                )
        elif current.get("capture_scope") == "required_participant_replacement":
            _required_participant_replacement_supersession(state, str(value))
        elif (
            value == "requires_visible_context"
            and state.get("endpoint_selector_context_enabled") is True
            and state.get("endpoint_context_evidence_enabled") is True
        ):
            _start_relationship_endpoint_context(state)
        else:
            _record_rejected_endpoint(state, str(value))
    elif field_id == "required_participant_replacement_identity_verdict":
        if value == "same_required_source_unit":
            verification = current.get("endpoint_verification")
            if not isinstance(verification, dict):
                raise InterviewError(
                    "required-participant-replacement-verification-missing"
                )
            verification["identity_continuity"] = {
                "verdict": value,
                "required_claim": current["required_identity_claim"],
            }
            _required_participant_replacement_supersession(
                state, "contains_claimed_content",
            )
        else:
            current["last_identity_rejection"] = {
                "verdict": value,
                "required_claim": current["required_identity_claim"],
                "proposed_kind": current["kind"],
                "proposed_content": current["content"],
                "proposed_bounds": [
                    current["left"], current["top"],
                    current["right"], current["bottom"],
                ],
                "endpoint_crop_evidence": current["endpoint_crop_evidence"],
            }
            for key in (
                "kind", "left", "top", "right", "bottom", "status",
                "content", "gap_reason", "endpoint_verification",
                "endpoint_crop_evidence",
            ):
                current.pop(key, None)
            state["stage"] = "element_kind"
    elif field_id == "required_participant_crop_verdict":
        _required_participant_verdict_supersession(state, str(value))
    elif field_id == "endpoint_context_crop_verdict":
        _complete_endpoint_context_verdict(state, str(value))
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
            if return_stage == "obligation_resolution":
                state["stage"] = _next_relationship_stage(state)
            elif return_stage == "region_element_more":
                state["stage"] = _next_region_stage(state)
            else:
                state["stage"] = return_stage
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
        if state.get("required_participant_binding_enabled") is True:
            role = str(value)
            current[f"{role}_id"] = obligation["element_id"]
            current.setdefault("locked_identity_participants", {})[role] = (
                obligation["element_id"]
            )
            state["stage"] = "obligation_endpoint_x"
        else:
            current[
                "from_id" if value == "origin" else "to_id"
            ] = obligation["element_id"]
            state["stage"] = "obligation_other_element"
    elif field_id == "obligation_endpoint_x":
        current["obligation_endpoint_x"] = value
        state["stage"] = "obligation_endpoint_y"
    elif field_id == "obligation_endpoint_y":
        role = str(current.get("role"))
        if role not in {"origin", "target"}:
            raise InterviewError("relationship-obligation-role-missing")
        x = current.pop("obligation_endpoint_x", None)
        if not isinstance(x, int):
            raise InterviewError("relationship-obligation-endpoint-x-missing")
        current[f"{role}_x"] = x
        current[f"{role}_y"] = value
        current[f"{role}_point"] = [x, value]
        _advance_after_relationship_binding(state, contract=contract)
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
            "obligation_role"
            if (
                contract >= 5
                and state.get("required_participant_binding_enabled") is True
                and _pending_obligation(state)
            )
            else "relationship_origin_x" if contract >= 5
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
            obligation = _pending_obligation(state)
            failed_element_id = current.get(f"{role}_id")
            if (
                state.get("failed_participant_recovery_enabled") is True
                and
                issue.get("reason") == "recorded_element_not_readable"
                and obligation is not None
                and failed_element_id == obligation.get("element_id")
            ):
                state["relationship_draft"] = None
                state["current"] = {
                    "return_stage": "obligation_resolution",
                    "capture_scope": "required_participant_replacement",
                    "superseded_element_id": failed_element_id,
                }
            else:
                for key in (
                    f"{role}_x", f"{role}_y", f"{role}_id", f"{role}_point",
                ):
                    current.pop(key, None)
                state["relationship_draft"] = current
                state["current"] = {
                    "return_stage": f"relationship_{role}_x",
                    "capture_scope": "relationship_endpoint",
                }
            state["stage"] = "element_kind"
        elif value == "refine_spatial_identity":
            if (
                role == "relationship"
                or issue.get("reason") != "no_unique_recorded_element"
                or not isinstance(issue.get("matching_element_ids"), list)
                or len(issue["matching_element_ids"]) < 2
            ):
                raise InterviewError("relationship-spatial-identity-capture-invalid")
            current["spatial_identity_issue"] = issue
            state["stage"] = "relationship_binding_intended_element"
        elif value == "select_recorded_element":
            if (
                role == "relationship"
                or issue.get("reason") != "no_unique_recorded_element"
                or not isinstance(issue.get("matching_element_ids"), list)
                or len(issue["matching_element_ids"]) < 2
                or state.get("overlap_identity_selection_enabled") is not True
            ):
                raise InterviewError(
                    "relationship-overlap-identity-selection-invalid"
                )
            current["overlap_identity_selection_issue"] = issue
            state["stage"] = "relationship_binding_intended_element"
        else:
            current["binding_issue"] = issue
            state["stage"] = "relationship_binding_gap_reason"
    elif field_id == "relationship_binding_intended_element":
        selection_issue = current.pop(
            "overlap_identity_selection_issue", None,
        )
        if isinstance(selection_issue, dict):
            role = str(selection_issue.get("participant"))
            if (
                role not in {"origin", "target"}
                or value not in selection_issue.get("matching_element_ids", [])
            ):
                raise InterviewError(
                    "relationship-overlap-identity-selection-invalid"
                )
            if role == "target" and value == current.get("origin_id"):
                current["binding_issue"] = {
                    "participant": role,
                    "point": selection_issue["point"],
                    "matching_element_ids": selection_issue[
                        "matching_element_ids"
                    ],
                    "reason": "same_element_as_origin",
                }
                state["stage"] = "relationship_binding_resolution"
            else:
                current[f"{role}_id"] = value
                current.setdefault(
                    "selected_identity_participants", {},
                )[role] = value
                _advance_after_relationship_binding(state, contract=contract)
            return
        issue = current.get("spatial_identity_issue")
        if not isinstance(issue, dict):
            raise InterviewError("relationship-spatial-identity-issue-missing")
        current["spatial_intended_element_id"] = value
        conflicts = [
            str(element_id)
            for element_id in issue["matching_element_ids"]
            if str(element_id) != value
        ]
        current["spatial_conflicting_element_ids"] = conflicts
        if len(conflicts) == 1:
            current["spatial_conflicting_element_id"] = conflicts[0]
            state["stage"] = "relationship_spatial_identity"
        else:
            state["stage"] = "relationship_spatial_conflict_element"
    elif field_id == "relationship_spatial_conflict_element":
        current["spatial_conflicting_element_id"] = value
        state["stage"] = "relationship_spatial_identity"
    elif field_id == "relationship_spatial_identity":
        if value == "same_unit":
            issue = current.pop("spatial_identity_issue")
            issue["identity_verdict"] = "same_unit"
            issue["intended_element_id"] = current.pop(
                "spatial_intended_element_id",
            )
            issue["conflicting_element_id"] = current.pop(
                "spatial_conflicting_element_id",
            )
            current.pop("spatial_conflicting_element_ids", None)
            current["binding_issue"] = issue
            state["stage"] = "relationship_binding_gap_reason"
        else:
            state["stage"] = "relationship_refine_left"
    elif field_id in {
        "relationship_refine_left", "relationship_refine_top",
        "relationship_refine_right",
    }:
        current[field_id.removeprefix("relationship_")] = value
        order = {
            "relationship_refine_left": "relationship_refine_top",
            "relationship_refine_top": "relationship_refine_right",
            "relationship_refine_right": "relationship_refine_bottom",
        }
        state["stage"] = order[field_id]
    elif field_id == "relationship_refine_bottom":
        _prepare_spatial_identity_refinement(state, int(value))
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
        locked = current.get("locked_identity_participants", {})
        if (
            state.get("locked_participant_replacement_blocked_enabled") is True
            and isinstance(locked, dict)
            and role in locked
        ):
            raise InterviewError(
                "locked-relationship-participant-replacement"
            )
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


def _question_for_replay(
    state: dict[str, Any],
    *,
    purpose: str,
    contract: int,
    recorded: object,
) -> dict[str, object] | None:
    expected = _question(state, purpose=purpose, contract=contract)
    if recorded == expected:
        return expected
    if contract >= 13 and state.get("stage") == "element_ownership":
        region = _active_scan_region(state)
        evidence = region.get("evidence") if isinstance(region, dict) else None
        if isinstance(evidence, dict) and not _context_space_available(evidence):
            legacy = _question(state, purpose=purpose, contract=12)
            if recorded == legacy:
                return legacy
    return None


def _activation_contract_for_replay(
    entry: dict[str, object], *, current_contract: int, minimum: int = 12,
) -> int | None:
    recorded = entry.get("contract")
    if (
        type(recorded) is not int
        or recorded not in SUPPORTED_CONTRACTS
        or recorded < minimum
        or recorded > current_contract
    ):
        return None
    return recorded


def _replay(
    entries: list[dict[str, object]],
    *,
    purpose: str,
    contract: int,
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state = _initial_state(contract=contract)
    pending: dict[str, object] | None = None
    completed = False
    for entry_index, entry in enumerate(entries):
        event = entry.get("event")
        if event == "question_asked":
            expected = _question_for_replay(
                state,
                purpose=purpose,
                contract=contract,
                recorded=entry.get("question"),
            )
            if pending is not None or expected is None:
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
        elif event == "element_superseded":
            if contract < 10 or pending is not None:
                raise InterviewError(
                    f"element-supersession-invalid:{entry['sequence']}"
                )
            supersession = {
                key: entry.get(key)
                for key in (
                    "element_id", "reason", "previous_element",
                    "trigger_candidate", "replacement_element",
                )
            }
            try:
                _apply_element_supersession(state, supersession)
            except InterviewError as error:
                raise InterviewError(
                    f"element-supersession-invalid:{entry['sequence']}:{error}"
                ) from error
        elif event == "element_spatial_identity_refined":
            if contract < 12 or pending is not None:
                raise InterviewError(
                    f"relationship-spatial-identity-refinement-invalid:{entry['sequence']}"
                )
            refinement = {
                key: entry.get(key)
                for key in (
                    "element_id", "reason", "intended_element_id",
                    "conflicting_point", "previous_element",
                    "replacement_element",
                )
            }
            try:
                _apply_spatial_identity_refinement(
                    state, refinement, contract=contract,
                )
            except InterviewError as error:
                raise InterviewError(
                    "relationship-spatial-identity-refinement-invalid:"
                    f"{entry['sequence']}:{error}"
                ) from error
        elif event == "spatial_identity_refinement_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            expected = {
                "feature": "append_only_spatial_identity_refinement_v1",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 12
                or activation_contract is None
                or pending is not None
                or state.get("spatial_identity_refinement_enabled") is True
                or actual != expected
            ):
                raise InterviewError(
                    f"spatial-identity-refinement-activation-invalid:{entry['sequence']}"
                )
            state["spatial_identity_refinement_enabled"] = True
        elif event == "overlap_identity_selection_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            expected = {
                "feature": "explicit_overlap_identity_selection_v1",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 12
                or activation_contract is None
                or pending is not None
                or state.get("overlap_identity_selection_enabled") is True
                or actual != expected
            ):
                raise InterviewError(
                    f"overlap-identity-selection-activation-invalid:{entry['sequence']}"
                )
            state["overlap_identity_selection_enabled"] = True
        elif event == "legacy_overlap_binding_migrated":
            expected = _legacy_overlap_binding_migration(state)
            keys = (
                "relationship_id", "action", "restorations",
                "inactive_refinements",
                "previous_relationship", "replacement_relationship",
                "obligation_migrations",
            )
            actual = {
                key: entry.get(key)
                for key in keys
                if key in entry
            }
            if (
                contract < 12
                or pending is not None
                or expected is None
                or actual != expected
            ):
                raise InterviewError(
                    f"legacy-overlap-binding-migration-invalid:{entry['sequence']}"
                )
            _apply_legacy_overlap_binding_migration(state, actual)
        elif event == "required_participant_gap_migrated":
            expected = _required_participant_gap_migration(state)
            keys = (
                "relationship_id", "previous_relationship",
                "replacement_relationship", "obligation_migrations",
            )
            actual = {key: entry.get(key) for key in keys}
            if (
                contract < 12
                or pending is not None
                or expected is None
                or actual != expected
            ):
                raise InterviewError(
                    f"required-participant-gap-migration-invalid:{entry['sequence']}"
                )
            _apply_required_participant_gap_migration(state, actual)
        elif event == "unverified_required_participant_relationship_invalidated":
            keys = (
                "relationship_id", "element_id", "previous_relationship",
                "replacement_relationship", "previous_obligation",
                "replacement_obligation",
            )
            actual = {key: entry.get(key) for key in keys}
            expected = _latest_unverified_required_participant_migration(state)
            if (
                contract < 12
                or pending is not None
                or expected is None
                or actual != expected
            ):
                raise InterviewError(
                    "unverified-required-participant-migration-invalid:"
                    f"{entry['sequence']}"
                )
            _apply_latest_unverified_required_participant_migration(
                state, actual,
            )
        elif event == (
            "context_unassessed_required_participant_relationship_invalidated"
        ):
            keys = (
                "relationship_id", "element_id", "previous_relationship",
                "replacement_relationship", "previous_obligation",
                "replacement_obligation",
            )
            actual = {key: entry.get(key) for key in keys}
            expected = _latest_context_unassessed_participant_migration(state)
            if (
                contract < 12
                or pending is not None
                or expected is None
                or actual != expected
            ):
                raise InterviewError(
                    "context-unassessed-participant-migration-invalid:"
                    f"{entry['sequence']}"
                )
            _apply_latest_unverified_required_participant_migration(
                state, actual,
            )
        elif event == "endpoint_grounding_invalidated":
            keys = (
                "element_id", "relationship_id", "reason",
                "previous_element", "replacement_element",
                "previous_relationship", "replacement_relationship",
                "obligation_migrations",
            )
            actual = {key: entry.get(key) for key in keys}
            if contract < 12 or pending is not None:
                raise InterviewError(
                    f"endpoint-grounding-invalidation-invalid:{entry['sequence']}"
                )
            try:
                expected = _historical_endpoint_grounding_invalidation(
                    state,
                    element_id=str(actual["element_id"]),
                    relationship_id=str(actual["relationship_id"]),
                    reason=str(actual["reason"]),
                )
                if actual != expected:
                    raise InterviewError(
                        "endpoint-grounding-invalidation-content-changed"
                    )
                _apply_historical_endpoint_grounding_invalidation(state, actual)
            except InterviewError as error:
                raise InterviewError(
                    f"endpoint-grounding-invalidation-invalid:{entry['sequence']}:{error}"
                ) from error
        elif event == "readable_relationship_rejected_endpoint_invalidated":
            keys: tuple[str, ...] = (
                "relationship_id", "previous_relationship",
                "replacement_relationship", "obligation_migrations",
            )
            eligibility_contract = "rejected_endpoint_v1"
            if "eligibility_contract" in entry:
                keys += ("eligibility_contract",)
                eligibility_contract = str(entry.get("eligibility_contract"))
            actual = {key: entry.get(key) for key in keys}
            expected = _readable_relationship_rejected_endpoint_migration(
                state, eligibility_contract=eligibility_contract,
            )
            if (
                contract < 12
                or pending is not None
                or expected is None
                or actual != expected
            ):
                raise InterviewError(
                    "rejected-endpoint-invalidation-invalid:"
                    f"{entry['sequence']}"
                )
            _apply_readable_relationship_rejected_endpoint_migration(
                state, actual,
            )
        elif event == "misdirected_participant_gap_invalidated":
            keys = (
                "relationship_id", "previous_relationship",
                "replacement_relationship", "previous_obligation",
                "replacement_obligation", "evidence",
            )
            actual = {key: entry.get(key) for key in keys}
            expected = _misdirected_participant_gap_migration(
                state, entries[:entry_index],
            )
            if (
                contract < 13
                or pending is not None
                or expected is None
                or actual != expected
            ):
                raise InterviewError(
                    "misdirected-participant-gap-invalidation-invalid:"
                    f"{entry['sequence']}"
                )
            _apply_misdirected_participant_gap_migration(state, actual)
        elif event == "failed_participant_recovery_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract, minimum=13,
            )
            expected = {
                "feature": "exact_failed_participant_recovery_v1",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 13
                or activation_contract is None
                or pending is not None
                or state.get("failed_participant_recovery_enabled") is True
                or actual != expected
            ):
                raise InterviewError(
                    "failed-participant-recovery-activation-invalid:"
                    f"{entry['sequence']}"
                )
            state["failed_participant_recovery_enabled"] = True
        elif event == "locked_participant_replacement_blocked_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
                "pending_recovery": entry.get("pending_recovery"),
            }
            if (
                contract < 12
                or activation_contract is None
                or state.get(
                    "locked_participant_replacement_blocked_enabled"
                ) is True
            ):
                raise InterviewError(
                    "locked-participant-replacement-activation-invalid:"
                    f"{entry['sequence']}"
                )
            expected = _locked_participant_replacement_activation(
                state,
                pending,
                entries[:entry_index],
                contract=(activation_contract or contract),
            )
            if actual != expected:
                raise InterviewError(
                    "locked-participant-replacement-activation-content-changed:"
                    f"{entry['sequence']}"
                )
            _apply_locked_participant_replacement_activation(state, actual)
            if actual["pending_recovery"] is not None:
                pending = None
        elif event == "required_participant_replacement_identity_invalidated":
            keys = (
                "element_id", "previous_element", "replacement_element",
                "relationship_id", "previous_relationship",
                "replacement_relationship", "previous_obligation",
                "replacement_obligation", "required_identity_claim",
            )
            actual = {key: entry.get(key) for key in keys}
            expected = _latest_unverified_replacement_identity_migration(
                state, entries[:entry_index],
            )
            if (
                contract < 12
                or pending is not None
                or expected is None
                or actual != expected
            ):
                raise InterviewError(
                    "replacement-identity-invalidation-invalid:"
                    f"{entry['sequence']}"
                )
            _apply_unverified_replacement_identity_migration(state, actual)
        elif event == "required_participant_replacement_identity_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            expected = {
                "feature": "required_participant_replacement_identity_v1",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 12
                or activation_contract is None
                or pending is not None
                or state.get(
                    "required_participant_replacement_identity_enabled"
                ) is True
                or actual != expected
            ):
                raise InterviewError(
                    "replacement-identity-activation-invalid:"
                    f"{entry['sequence']}"
                )
            state["required_participant_replacement_identity_enabled"] = True
        elif event == "required_participant_content_identity_separation_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
                "abandoned_question_id": entry.get("abandoned_question_id"),
            }
            if (
                contract < 12
                or activation_contract is None
                or state.get(
                    "required_participant_content_identity_separation_enabled"
                ) is True
            ):
                raise InterviewError(
                    "replacement-content-identity-separation-invalid:"
                    f"{entry['sequence']}"
                )
            expected = _replacement_content_identity_separation_activation(
                state, pending, contract=(activation_contract or contract),
            )
            if actual != expected:
                raise InterviewError(
                    "replacement-content-identity-separation-content-changed:"
                    f"{entry['sequence']}"
                )
            state[
                "required_participant_content_identity_separation_enabled"
            ] = True
            if actual["abandoned_question_id"] is not None:
                pending = None
        elif event == "required_participant_binding_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            expected = {
                "feature": "required_obligation_identity_binding_v1",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 12
                or activation_contract is None
                or pending is not None
                or state.get("required_participant_binding_enabled") is True
                or actual != expected
            ):
                raise InterviewError(
                    f"required-participant-binding-activation-invalid:{entry['sequence']}"
                )
            state["required_participant_binding_enabled"] = True
        elif event == "endpoint_crop_verification_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            expected = {
                "feature": "fresh_exact_endpoint_crop_verification_v1",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 12
                or activation_contract is None
                or pending is not None
                or state.get("endpoint_crop_verification_enabled") is True
                or actual != expected
            ):
                raise InterviewError(
                    f"endpoint-crop-verification-activation-invalid:{entry['sequence']}"
                )
            state["endpoint_crop_verification_enabled"] = True
        elif event == "existing_participant_crop_verification_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            expected = {
                "feature": "existing_required_participant_crop_verification_v1",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 12
                or activation_contract is None
                or pending is not None
                or state.get(
                    "existing_participant_crop_verification_enabled"
                ) is True
                or actual != expected
            ):
                raise InterviewError(
                    "existing-participant-crop-verification-activation-invalid:"
                    f"{entry['sequence']}"
                )
            state["existing_participant_crop_verification_enabled"] = True
        elif event == "contextual_endpoint_verification_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            expected = {
                "feature": "contextual_endpoint_crop_verification_v1",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 12
                or activation_contract is None
                or pending is not None
                or state.get("contextual_endpoint_verification_enabled") is True
                or actual != expected
            ):
                raise InterviewError(
                    "contextual-endpoint-verification-activation-invalid:"
                    f"{entry['sequence']}"
                )
            state["contextual_endpoint_verification_enabled"] = True
        elif event == "endpoint_context_evidence_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
                "pending_context_recovery": entry.get(
                    "pending_context_recovery"
                ),
            }
            if (
                contract < 12
                or activation_contract is None
                or state.get("endpoint_context_evidence_enabled") is True
            ):
                raise InterviewError(
                    "endpoint-context-evidence-activation-invalid:"
                    f"{entry['sequence']}"
                )
            expected = _endpoint_context_evidence_activation(
                state, pending, contract=(activation_contract or contract),
            )
            if actual != expected:
                raise InterviewError(
                    "endpoint-context-evidence-activation-content-changed"
                )
            _apply_endpoint_context_evidence_activation(state, actual)
            pending = None
        elif event == "endpoint_selector_context_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
                "pending_scope_recovery": entry.get(
                    "pending_scope_recovery"
                ),
            }
            if (
                contract < 12
                or activation_contract is None
                or state.get("endpoint_selector_context_enabled") is True
            ):
                raise InterviewError(
                    "endpoint-selector-context-activation-invalid:"
                    f"{entry['sequence']}"
                )
            expected = _endpoint_selector_context_activation(
                state, pending, contract=(activation_contract or contract),
            )
            if actual != expected:
                raise InterviewError(
                    "endpoint-selector-context-activation-content-changed"
                )
            _apply_endpoint_selector_context_activation(state, actual)
            if actual["pending_scope_recovery"] is not None:
                pending = None
        elif event == "endpoint_identity_context_choice_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
                "pending_identity_recovery": entry.get(
                    "pending_identity_recovery"
                ),
            }
            if (
                contract < 12
                or activation_contract is None
                or state.get("endpoint_identity_context_choice_enabled")
                is True
            ):
                raise InterviewError(
                    "endpoint-identity-context-choice-activation-invalid:"
                    f"{entry['sequence']}"
                )
            expected = _endpoint_identity_context_choice_activation(
                state, pending, contract=(activation_contract or contract),
            )
            if actual != expected:
                raise InterviewError(
                    "endpoint-identity-context-choice-content-changed"
                )
            _apply_endpoint_identity_context_choice_activation(state, actual)
            if actual["pending_identity_recovery"] is not None:
                pending = None
        elif event == "negative_context_replacement_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
                "pending_negative_context_recovery": entry.get(
                    "pending_negative_context_recovery"
                ),
            }
            if (
                contract < 12
                or activation_contract is None
                or state.get("negative_context_replacement_enabled") is True
            ):
                raise InterviewError(
                    "negative-context-activation-invalid:"
                    f"{entry['sequence']}"
                )
            expected = _negative_context_replacement_activation(
                state, pending, contract=(activation_contract or contract),
            )
            if actual != expected:
                raise InterviewError(
                    "negative-context-activation-content-changed"
                )
            if (
                pending is not None
                and actual["pending_negative_context_recovery"] is None
            ):
                raise InterviewError(
                    "negative-context-activation-question-pending"
                )
            _apply_negative_context_replacement_activation(state, actual)
            pending = None
        elif event == "rejected_endpoint_reuse_blocked_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            expected = {
                "feature": "rejected_endpoint_reuse_blocked_v1",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 12
                or activation_contract is None
                or pending is not None
                or state.get(
                    "rejected_endpoint_reuse_blocked_enabled"
                ) is True
                or actual != expected
            ):
                raise InterviewError(
                    "rejected-endpoint-reuse-block-activation-invalid:"
                    f"{entry['sequence']}"
                )
            state["rejected_endpoint_reuse_blocked_enabled"] = True
        elif event == "unreadable_participant_reuse_blocked_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            expected = {
                "feature": "unreadable_participant_reuse_blocked_v2",
                "contract": activation_contract,
            }
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
            }
            if (
                contract < 12
                or activation_contract is None
                or pending is not None
                or state.get(
                    "unreadable_participant_reuse_blocked_enabled"
                ) is True
                or actual != expected
            ):
                raise InterviewError(
                    "unreadable-participant-reuse-block-activation-invalid:"
                    f"{entry['sequence']}"
                )
            state["unreadable_participant_reuse_blocked_enabled"] = True
        elif event == "rejected_endpoint_collision_excluded_enabled":
            activation_contract = _activation_contract_for_replay(
                entry, current_contract=contract,
            )
            actual = {
                "feature": entry.get("feature"),
                "contract": entry.get("contract"),
                "pending_capture_recovery": entry.get(
                    "pending_capture_recovery"
                ),
            }
            if (
                contract < 12
                or activation_contract is None
                or state.get("rejected_endpoint_collision_excluded_enabled")
                is True
            ):
                raise InterviewError(
                    "rejected-endpoint-collision-activation-invalid:"
                    f"{entry['sequence']}"
                )
            try:
                expected = _rejected_endpoint_collision_activation(
                    state, pending, contract=(activation_contract or contract),
                )
                if actual != expected:
                    raise InterviewError(
                        "rejected-endpoint-collision-activation-content-changed"
                    )
                _apply_rejected_endpoint_collision_activation(state, actual)
                pending = None
            except InterviewError as error:
                raise InterviewError(
                    "rejected-endpoint-collision-activation-invalid:"
                    f"{entry['sequence']}:{error}"
                ) from error
        elif event == "endpoint_crop_evidence_bound":
            evidence = {
                key: entry.get(key)
                for key in (
                    "candidate_id", "source_sha256", "source_pixel_size",
                    "normalized_bounds", "pixel_bounds", "crop_path",
                    "crop_sha256", "claimed_content", "verification_scope",
                    "adapter",
                )
            }
            if evidence["verification_scope"] is None:
                evidence.pop("verification_scope")
            if pending is not None or not _valid_endpoint_evidence(state, evidence):
                raise InterviewError(
                    f"endpoint-crop-evidence-invalid:{entry['sequence']}"
                )
            state["current"]["endpoint_crop_evidence"] = evidence
        elif event == "context_candidate_deferred":
            if contract < 11 or pending is not None:
                raise InterviewError(
                    f"context-deferral-invalid:{entry['sequence']}"
                )
            keys = (
                (
                    "region_id", "owner_region_id", "obligation_id",
                    "anchor", "candidate_kind", "reason",
                    "crop_sha256", "guide_sha256",
                )
                if contract >= 12
                else (
                    "region_id", "candidate_kind", "reason",
                    "crop_sha256", "guide_sha256",
                )
            )
            deferral = {key: entry.get(key) for key in keys}
            try:
                _apply_context_deferral(state, deferral, contract=contract)
            except InterviewError as error:
                raise InterviewError(
                    f"context-deferral-invalid:{entry['sequence']}:{error}"
                ) from error
        elif event == "relationship_obligations_reconciled":
            expected = _relationship_obligation_reconciliation(state)
            actual = {
                "relationship_id": entry.get("relationship_id"),
                "covered_obligations": entry.get("covered_obligations"),
            }
            if pending is not None or expected is None or actual != expected:
                raise InterviewError(
                    "relationship-obligation-reconciliation-invalid:"
                    f"{entry['sequence']}: expected {expected!r}; got {actual!r}"
                )
            try:
                _apply_relationship_obligation_reconciliation(state, actual)
            except InterviewError as error:
                raise InterviewError(
                    "relationship-obligation-reconciliation-invalid:"
                    f"{entry['sequence']}:{error}"
                ) from error
        elif event == "context_ownership_reclassified":
            expected = _context_ownership_reclassification(
                state, pending, contract=contract,
            )
            actual = {
                key: entry.get(key)
                for key in (
                    "region_id", "candidate_kind", "previous_classification",
                    "classification", "reason", "cancelled_question_id",
                    "crop_sha256", "guide_sha256",
                )
            }
            if expected is None or actual != expected:
                raise InterviewError(
                    f"context-ownership-reclassification-invalid:{entry['sequence']}"
                )
            _apply_context_ownership_reclassification(state, actual)
            pending = None
        elif event == "region_evidence_bound":
            region = _active_scan_region(state)
            if (
                region is None
                or region.get("evidence") is not None
                or not _valid_region_evidence_entry(
                    entry, region, contract=contract,
                )
            ):
                raise InterviewError(f"region-evidence-invalid:{entry['sequence']}")
            evidence_keys = (
                (
                    "core_normalized_bounds", "evidence_normalized_bounds",
                    "core_pixel_bounds", "source_sha256", "source_pixel_size",
                    "pixel_bounds", "crop_path", "crop_sha256", "adapter",
                    "ownership_core_in_crop_pixels", "guide_path",
                    "guide_sha256", "guide_adapter",
                )
                if contract >= 11
                else (
                    "core_normalized_bounds", "evidence_normalized_bounds",
                    "core_pixel_bounds", "source_sha256", "source_pixel_size",
                    "pixel_bounds", "crop_path", "crop_sha256", "adapter",
                )
                if contract >= 9
                else (
                    "normalized_bounds", "source_sha256", "source_pixel_size",
                    "pixel_bounds", "crop_path", "crop_sha256", "adapter",
                )
            )
            region["evidence"] = {
                key: entry[key]
                for key in evidence_keys
            }
        elif event == "region_outcome_recorded":
            outcome_index = len(state["region_outcomes"])
            region = (
                state["scan_regions"][outcome_index]
                if outcome_index < len(state["scan_regions"])
                else None
            )
            expected = _region_outcome(region) if isinstance(region, dict) else None
            if (
                contract < 8
                or pending is not None
                or expected is None
                or region["status"] == "pending"
                or any(entry.get(key) != value for key, value in expected.items())
            ):
                raise InterviewError(f"region-outcome-invalid:{entry['sequence']}")
            state["region_outcomes"].append(expected)
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
    region_evidence = question.get("region_evidence")
    if isinstance(region_evidence, dict):
        if "guide_path" in region_evidence:
            lines.append(
                "The first attached image is the immutable clean context crop: "
                f"{region_evidence['crop_path']} "
                f"sha256={region_evidence['crop_sha256']}. The second is its "
                "immutable ownership guide: "
                f"{region_evidence['guide_path']} "
                f"sha256={region_evidence['guide_sha256']}. In the guide, the "
                "bright green outline encloses the active ownership core and "
                "the dimmed area is context-only. Report coordinates in the "
                "full source's normalized 0..1000 space; the crop edges map "
                f"to {region_evidence['evidence_normalized_bounds']}."
            )
        elif "evidence_normalized_bounds" in region_evidence:
            lines.append(
                "Attached image is the immutable context crop for this active "
                f"region: {region_evidence['crop_path']} "
                f"sha256={region_evidence['crop_sha256']}. Report coordinates "
                "in the full source's normalized 0..1000 space; the crop edges "
                f"map to {region_evidence['evidence_normalized_bounds']}. "
                "Use surrounding context to read elements, but record a new "
                "element only when its left/top anchor is inside the ownership "
                f"core {region_evidence['core_normalized_bounds']}."
            )
        else:
            lines.append(
                "Attached image is the immutable crop for this active region: "
                f"{region_evidence['crop_path']} "
                f"sha256={region_evidence['crop_sha256']}. Report coordinates "
                "in the full source's normalized 0..1000 space; the crop edges "
                f"map to {region_evidence['normalized_bounds']}."
            )
    coordinate_region = question.get("coordinate_region")
    if isinstance(coordinate_region, dict):
        lines.append(
            "Element left/top anchor must be inside active source region: "
            f"{coordinate_region['id']} normalized bounds "
            f"{coordinate_region['bounds']}"
        )
    unit_collision_candidates = question.get("unit_collision_candidates")
    if isinstance(unit_collision_candidates, list):
        lines.append(
            "Spatially intersecting recorded elements: "
            + json.dumps(unit_collision_candidates, sort_keys=True)
        )
    deferred_context_candidates = question.get("deferred_context_candidates")
    if isinstance(deferred_context_candidates, list):
        lines.append(
            "Already deferred context-only candidates for this region: "
            + json.dumps(deferred_context_candidates, sort_keys=True)
        )
    binding_issue = question.get("binding_issue")
    if isinstance(binding_issue, dict):
        lines.append(
            "Coordinate binding issue: "
            + json.dumps(binding_issue, sort_keys=True)
        )
    matching_elements = question.get("matching_elements")
    if isinstance(matching_elements, list):
        lines.append(
            "Exact overlapping recorded element choices: "
            + json.dumps(matching_elements, sort_keys=True)
        )
    verification_issue = question.get("verification_issue")
    if isinstance(verification_issue, dict):
        lines.append(
            "Visual verification issue: "
            + json.dumps(verification_issue, sort_keys=True)
        )
    endpoint_crop_evidence = question.get("endpoint_crop_evidence")
    if isinstance(endpoint_crop_evidence, dict):
        lines.append(
            "The attached image is only the exact claimed endpoint crop: "
            f"{endpoint_crop_evidence['crop_path']} "
            f"sha256={endpoint_crop_evidence['crop_sha256']}. Judge whether "
            "that crop itself visibly contains the claimed content: "
            + json.dumps(endpoint_crop_evidence["claimed_content"])
        )
    identity_comparison = question.get("required_identity_comparison")
    if isinstance(identity_comparison, dict):
        lines.append(
            "Required participant identity comparison: "
            + json.dumps(identity_comparison, sort_keys=True)
        )
    endpoint_selector_candidate = question.get("endpoint_selector_candidate")
    if isinstance(endpoint_selector_candidate, dict):
        lines.append(
            "Proposed relationship endpoint selector: "
            + json.dumps(endpoint_selector_candidate, sort_keys=True)
        )
    proposed_relationship = question.get("proposed_relationship")
    if isinstance(proposed_relationship, dict):
        lines.append(
            "Proposed relationship participants: "
            + json.dumps(proposed_relationship, sort_keys=True)
        )
    if state.get("current", {}).get("capture_scope") == "relationship_endpoint":
        lines.append(
            "Relationship endpoint capture: record the other visible endpoint "
            "connected to the already-recorded required participant. Do not "
            "copy or recapture the already-recorded participant; its evidence "
            "below is context for locating the other endpoint only. Select one "
            "precise visible endpoint. If a nearby label is needed to identify "
            "it, keep that label out of the selector unless it is part of the "
            "same field; the machinery will collect a separate context window."
        )
    if (
        state.get("current", {}).get("capture_scope")
        == "required_participant_replacement"
        and not (
            state.get(
                "required_participant_content_identity_separation_enabled"
            ) is True
            and state.get("stage") in {
                "element_content_crop_verdict",
                "required_participant_replacement_identity_verdict",
            }
        )
    ):
        lines.append(
            "Required participant replacement capture: the first attached image "
            "shows why the old bounds were rejected and may contain the wrong or "
            "only a partial visible unit. The second attached image is the "
            "complete frozen source. Locate the source unit described by the "
            "preserved required identity, then record bounds that include its "
            "full value and label."
        )
        required_claim = state["current"].get("required_identity_claim")
        if isinstance(required_claim, str) and required_claim:
            lines.append(
                "Preserved required identity: " + json.dumps(required_claim)
            )
    if state.get("current", {}).get("capture_scope") in {
        "required_participant_context", "relationship_endpoint_context",
    }:
        lines.append(
            "Endpoint identity context capture: keep the precise endpoint bounds "
            "unchanged. Record a separate evidence window that contains that "
            "endpoint and every visible label or surrounding cue needed to prove "
            "its claimed identity."
        )
    obligation = _pending_obligation(state)
    if obligation is not None and _active_scan_region(state) is None:
        element = _element_by_id(state, str(obligation["element_id"]))
        lines.append(
            "Required relationship element evidence: "
            + json.dumps({
                "content": element["content"],
                "gap_reason": element["gap_reason"],
                "id": element["id"],
                "kind": element["kind"],
                "normalized_bounds": element["region"],
                "status": element["status"],
            }, sort_keys=True)
        )
        if question.get("id") == "obligation_resolution":
            candidates = [
                {
                    "content": candidate["content"],
                    "gap_reason": candidate["gap_reason"],
                    "id": candidate["id"],
                    "kind": candidate["kind"],
                    "normalized_bounds": candidate["region"],
                    "status": candidate["status"],
                }
                for candidate in sorted(
                    state["elements"], key=lambda item: str(item["id"]),
                )
                if candidate["id"] != obligation["element_id"]
            ]
            lines.append(
                "Complete index of other recorded relationship endpoint candidates: "
                + json.dumps(candidates, sort_keys=True)
            )
    lines.extend([
        f"Question id: {question['id']}",
        f"Question: {question['prompt']}",
        f"Answer type: {question['type']}",
    ])
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


def prepare_resume(
    attempt_dir: Path,
    *,
    purpose: str,
    contract: int = CONTRACT,
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    """Append deterministic compatibility events before selecting resume work."""

    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    while True:
        entries = _read_journal(journal_path)
        state, pending, completed = _replay(
            entries, purpose=purpose, contract=contract,
        )
        if completed or contract < 12:
            return state, pending, completed
        if pending is not None:
            if (
                state.get(
                    "required_participant_content_identity_separation_enabled"
                ) is not True
                and pending.get("id") == "element_content_crop_verdict"
                and state.get("current", {}).get("capture_scope")
                == "required_participant_replacement"
            ):
                _append(
                    journal_path,
                    "required_participant_content_identity_separation_enabled",
                    _replacement_content_identity_separation_activation(
                        state, pending, contract=contract,
                    ),
                )
                continue
            if (
                contract >= 12
                and state.get(
                    "locked_participant_replacement_blocked_enabled"
                ) is not True
            ):
                activation = _locked_participant_replacement_activation(
                    state, pending, entries, contract=contract,
                )
                _append(
                    journal_path,
                    "locked_participant_replacement_blocked_enabled",
                    activation,
                )
                continue
            return state, pending, completed
        if state.get("spatial_identity_refinement_enabled") is not True:
            _append(
                journal_path,
                "spatial_identity_refinement_enabled",
                {
                    "feature": "append_only_spatial_identity_refinement_v1",
                    "contract": contract,
                },
            )
            continue
        if state.get("overlap_identity_selection_enabled") is not True:
            migration = _legacy_overlap_binding_migration(state)
            if migration is not None:
                _append(journal_path, "legacy_overlap_binding_migrated", migration)
                continue
            _append(
                journal_path,
                "overlap_identity_selection_enabled",
                {
                    "feature": "explicit_overlap_identity_selection_v1",
                    "contract": contract,
                },
            )
            continue
        migration = _required_participant_gap_migration(state)
        if migration is not None:
            _append(journal_path, "required_participant_gap_migrated", migration)
            continue
        if state.get("required_participant_binding_enabled") is not True:
            _append(
                journal_path,
                "required_participant_binding_enabled",
                {
                    "feature": "required_obligation_identity_binding_v1",
                    "contract": contract,
                },
            )
            continue
        if contract >= 13:
            migration = _misdirected_participant_gap_migration(
                state, entries,
            )
            if migration is not None:
                _append(
                    journal_path,
                    "misdirected_participant_gap_invalidated",
                    migration,
                )
                continue
            if state.get("failed_participant_recovery_enabled") is not True:
                _append(
                    journal_path,
                    "failed_participant_recovery_enabled",
                    {
                        "feature": "exact_failed_participant_recovery_v1",
                        "contract": contract,
                    },
                )
                continue
        replacement_identity_migration = (
            _latest_unverified_replacement_identity_migration(state, entries)
        )
        if replacement_identity_migration is not None:
            _append(
                journal_path,
                "required_participant_replacement_identity_invalidated",
                replacement_identity_migration,
            )
            continue
        if (
            state.get(
                "required_participant_replacement_identity_enabled"
            ) is not True
        ):
            _append(
                journal_path,
                "required_participant_replacement_identity_enabled",
                {
                    "feature": "required_participant_replacement_identity_v1",
                    "contract": contract,
                },
            )
            continue
        if (
            state.get(
                "required_participant_content_identity_separation_enabled"
            ) is not True
        ):
            _append(
                journal_path,
                "required_participant_content_identity_separation_enabled",
                _replacement_content_identity_separation_activation(
                    state, pending, contract=contract,
                ),
            )
            continue
        if (
            state.get(
                "locked_participant_replacement_blocked_enabled"
            ) is not True
        ):
            _append(
                journal_path,
                "locked_participant_replacement_blocked_enabled",
                _locked_participant_replacement_activation(
                    state, pending, entries, contract=contract,
                ),
            )
            continue
        return state, pending, completed


def run(
    attempt_dir: Path,
    *,
    source_sha256: str,
    purpose: str,
    contract: int = CONTRACT,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
    stop_after_relationship: bool = False,
    stop_after_endpoint_verification: bool = False,
) -> dict[str, object]:
    """Resume the journal and return the code-assembled projection."""

    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    projection_path = attempt_dir / "projection.json"
    read = input_fn or _terminal_input
    write = output_fn or _terminal_output
    initial_relationship_count: int | None = None

    prepare_resume(attempt_dir, purpose=purpose, contract=contract)

    while True:
        entries = _read_journal(journal_path)
        state, pending, completed = _replay(
            entries,
            purpose=purpose,
            contract=contract,
        )
        if initial_relationship_count is None:
            initial_relationship_count = len(state["relationships"])
        if contract >= 8:
            _verify_region_evidence_files(
                attempt_dir, state, source_sha256=source_sha256,
            )
            _verify_endpoint_evidence_files(
                attempt_dir, state, source_sha256=source_sha256,
            )
            reclassification = _context_ownership_reclassification(
                state, pending, contract=contract,
            )
            if reclassification is not None:
                _append(
                    journal_path,
                    "context_ownership_reclassified",
                    reclassification,
                )
                continue
            supersession = state.get("element_supersession_pending")
            if isinstance(supersession, dict):
                event = supersession.get("event")
                if not isinstance(event, dict):
                    raise InterviewError("element-supersession-invalid")
                _append(journal_path, "element_superseded", event)
                continue
            refinement = state.get("spatial_identity_refinement_pending")
            if isinstance(refinement, dict):
                event = refinement.get("event")
                if not isinstance(event, dict):
                    raise InterviewError(
                        "relationship-spatial-identity-refinement-invalid"
                    )
                _append(
                    journal_path,
                    "element_spatial_identity_refined",
                    event,
                )
                continue
            deferral = state.get("context_deferral_pending")
            if isinstance(deferral, dict):
                event = deferral.get("event")
                if not isinstance(event, dict):
                    raise InterviewError("context-deferral-invalid")
                _append(journal_path, "context_candidate_deferred", event)
                continue
            outcome_index = len(state["region_outcomes"])
            if outcome_index < len(state["scan_regions"]):
                closed_region = state["scan_regions"][outcome_index]
                if closed_region["status"] != "pending":
                    _append(
                        journal_path,
                        "region_outcome_recorded",
                        _region_outcome(closed_region),
                    )
                    return _projection(
                        state,
                        source_sha256=source_sha256,
                        purpose=purpose,
                        contract=contract,
                    )
        reconciliation = _relationship_obligation_reconciliation(state)
        if reconciliation is not None:
            _append(
                journal_path,
                "relationship_obligations_reconciled",
                reconciliation,
            )
            continue
        if stop_after_relationship:
            relationship_delta = (
                len(state["relationships"]) - initial_relationship_count
            )
            if relationship_delta > 1:
                raise InterviewError("relationship-step-added-multiple-outcomes")
            if relationship_delta == 1:
                return _projection(
                    state,
                    source_sha256=source_sha256,
                    purpose=purpose,
                    contract=contract,
                )
        projection = _projection(
            state,
            source_sha256=source_sha256,
            purpose=purpose,
            contract=contract,
        )
        if (
            _endpoint_evidence_claim(state) is not None
            and not isinstance(
                state.get("current", {}).get("endpoint_crop_evidence"), dict,
            )
        ):
            return projection
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
        elif (
            question["id"] in {
                "element_content_crop_verdict",
                "required_participant_crop_verdict",
                "endpoint_context_crop_verdict",
                "required_participant_replacement_identity_verdict",
            }
            and stop_after_endpoint_verification
        ):
            state, _pending, _completed = _replay(
                _read_journal(journal_path), purpose=purpose, contract=contract,
            )
            return _projection(
                state,
                source_sha256=source_sha256,
                purpose=purpose,
                contract=contract,
            )


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
