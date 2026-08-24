#!/usr/bin/env python3
"""Adapter-specific qualification of one immutable readable projection."""

from __future__ import annotations

import json


QUALIFICATIONS = {
    "readable_projection_complete",
    "readable_projection_incomplete",
    "conversion_incomplete",
}


def _gap(source_id: str, unit: object, reason: object) -> dict[str, object]:
    return {
        "source_id": source_id,
        "unit": unit,
        "reason": reason,
    }


def _verbatim_gaps(
    item: dict[str, object], record: dict[str, object], artifact_sha256: str
) -> list[dict[str, object]]:
    expected_coverage = {
        "status": "complete",
        "source_units": 1,
        "represented_units": 1,
        "gaps": [],
    }
    if (
        record.get("coverage") == expected_coverage
        and record.get("sha256") == item.get("source_sha256")
        and artifact_sha256 == record.get("sha256")
    ):
        return []
    return [
        _gap(
            str(item["source_id"]),
            "complete-source",
            "verbatim projection does not exactly preserve the frozen source",
        )
    ]


def _spreadsheet_gaps(
    item: dict[str, object], record: dict[str, object], artifact_sha256: str
) -> list[dict[str, object]]:
    source_id = str(item["source_id"])
    coverage = record.get("coverage")
    if not isinstance(coverage, dict) or not isinstance(coverage.get("parts"), list):
        return [_gap(source_id, "workbook", "spreadsheet coverage parts are missing")]
    parts = coverage["parts"]
    if any(not isinstance(part, dict) for part in parts):
        return [
            _gap(
                source_id,
                "workbook",
                "spreadsheet coverage contains a malformed part outcome",
            )
        ]
    represented = [part for part in parts if part.get("outcome") == "represented"]
    gaps = [part for part in parts if part.get("outcome") == "gap"]
    if (
        artifact_sha256 != record.get("sha256")
        or len(parts) != coverage.get("source_units")
        or len(represented) != coverage.get("represented_units")
        or len(gaps) != coverage.get("gap_units")
        or coverage.get("status")
        != ("complete" if not gaps else "partial")
    ):
        return [
            _gap(
                source_id,
                "workbook",
                "spreadsheet coverage counts contradict its immutable part inventory",
            )
        ]
    return [
        _gap(
            source_id,
            part.get("path"),
            part.get("reason") or "workbook part has no readable representation",
        )
        for part in gaps
    ]


def _pdf_gaps(
    item: dict[str, object],
    record: dict[str, object],
    artifact_bytes: bytes,
    artifact_sha256: str,
) -> tuple[list[dict[str, object]] | None, str | None]:
    source_id = str(item["source_id"])
    try:
        manifest = json.loads(artifact_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None, f"{source_id} PDF projection manifest is unreadable"
    if not isinstance(manifest, dict):
        return None, f"{source_id} PDF projection manifest is not one object"
    pages = manifest.get("pages")
    gaps = manifest.get("gap_inventory")
    if (
        artifact_sha256 != record.get("sha256")
        or manifest.get("method") != "pdf_visible_pages"
        or manifest.get("source_id") != source_id
        or not isinstance(pages, list)
        or any(not isinstance(page, dict) for page in pages)
        or len(pages) != manifest.get("page_count")
        or manifest.get("page_count") != record.get("page_count")
        or not isinstance(gaps, list)
        or any(not isinstance(gap, dict) for gap in gaps)
    ):
        return None, f"{source_id} PDF page or gap inventory contradicts its ledger record"
    return [
        _gap(
            source_id,
            f"page-{gap.get('page')}:{gap.get('item_id')}",
            gap.get("reason") or "PDF visible-page projection gap",
        )
        for gap in gaps
        if isinstance(gap, dict)
    ], None


def qualify(
    item: dict[str, object],
    artifact_bytes: bytes | None,
    artifact_sha256: str | None,
    *,
    visual_qualification: dict[str, object] | None = None,
) -> dict[str, object]:
    source_id = item.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        return {"complete": False, "why": "bound qualification has no source identity"}
    if item.get("outcome") != "projected":
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            return {
                "complete": False,
                "why": f"nonprojected source {source_id} has no conversion reason",
            }
        return {
            "complete": True,
            "qualification": {
                "source_id": source_id,
                "projection_id": None,
                "projection_sha256": None,
                "method": None,
                "qualification": "conversion_incomplete",
                "gaps": [_gap(source_id, "projection", reason)],
            },
        }
    record = item.get("record")
    if (
        not isinstance(record, dict)
        or not isinstance(artifact_bytes, bytes)
        or not isinstance(artifact_sha256, str)
    ):
        return {
            "complete": False,
            "why": f"projected source {source_id} lost its immutable readable artifact",
        }
    method = record.get("method")
    if method == "verbatim_utf8":
        gaps = _verbatim_gaps(item, record, artifact_sha256)
    elif method == "spreadsheet_ooxml_v1":
        gaps = _spreadsheet_gaps(item, record, artifact_sha256)
    elif method == "pdf_visible_pages":
        gaps, error = _pdf_gaps(item, record, artifact_bytes, artifact_sha256)
        if error:
            return {"complete": False, "why": error}
        assert gaps is not None
    elif method == "visual_spatial_v1":
        if not isinstance(visual_qualification, dict):
            return {
                "complete": False,
                "why": f"{source_id} visual qualification evidence is unavailable",
            }
        visual_projection = visual_qualification.get("projection")
        if (
            not isinstance(visual_projection, dict)
            or visual_projection.get("sha256") != artifact_sha256
        ):
            return {
                "complete": False,
                "why": f"{source_id} visual qualification is bound to another projection",
            }
        remaining = visual_qualification.get("remaining_gaps")
        if not isinstance(remaining, list):
            return {
                "complete": False,
                "why": f"{source_id} visual qualification lost its gap inventory",
            }
        gaps = [
            {
                "source_id": source_id,
                "unit": gap.get("id") if isinstance(gap, dict) else None,
                "reason": (
                    gap.get("gap_reason", "visual projection gap")
                    if isinstance(gap, dict)
                    else "visual projection gap"
                ),
                "projection_gap": gap,
            }
            for gap in remaining
        ]
    else:
        return {
            "complete": False,
            "why": f"{source_id} has unsupported projection method {method!r}",
        }
    qualification = {
        "source_id": source_id,
        "projection_id": record.get("id"),
        "projection_sha256": record.get("sha256"),
        "method": method,
        "qualification": (
            "readable_projection_incomplete"
            if gaps
            else "readable_projection_complete"
        ),
        "gaps": gaps,
    }
    compatibility = record.get("method_compatibility")
    if isinstance(compatibility, dict):
        qualification["method_compatibility"] = compatibility
    return {
        "complete": True,
        "qualification": qualification,
    }
