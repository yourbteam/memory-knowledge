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
    index = state["elements"].index(target)
    state["elements"][index] = replacement
    state["element_supersession_pending"] = None
    state["current"] = {}
    state["stage"] = str(pending["return_stage"])


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
        if field_id == "element_bottom" and contract >= 10:
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
        if contract >= 8:
            _verify_region_evidence_files(
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
        projection = _projection(
            state,
            source_sha256=source_sha256,
            purpose=purpose,
            contract=contract,
        )
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
