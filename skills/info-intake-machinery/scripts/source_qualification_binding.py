#!/usr/bin/env python3
"""Bind source-collection outcomes to their exact projection ledger records."""

from __future__ import annotations


SUPPORTED_METHODS = {
    "verbatim_utf8",
    "spreadsheet_ooxml_v1",
    "pdf_visible_pages",
    "visual_spatial_v1",
}


def _projection_method(entry: dict[str, object], record: dict[str, object]) -> object:
    method = record.get("method")
    if method is not None:
        return method
    if entry.get("event") in {
        "source_projected",
        "qualification_answer_source_projected",
    }:
        return "verbatim_utf8"
    if record.get("coverage") == "unassessed":
        return "visual_spatial_v1"
    return None


def _entry_source_id(entry: dict[str, object], record: dict[str, object]) -> object:
    answer = entry.get("answer")
    source = entry.get("source")
    if not isinstance(source, dict) and isinstance(answer, dict):
        source = answer.get("source")
    return record.get(
        "source_id",
        entry.get("source_id", source.get("id") if isinstance(source, dict) else None),
    )


def _entry_source_sha256(entry: dict[str, object]) -> object:
    answer = entry.get("answer")
    source = entry.get("source")
    if not isinstance(source, dict) and isinstance(answer, dict):
        source = answer.get("source")
    return entry.get(
        "source_sha256",
        source.get("sha256") if isinstance(source, dict) else None,
    )


def _source_digests(
    entries: list[dict[str, object]],
) -> tuple[dict[str, object], str | None]:
    digests: dict[str, object] = {}
    for entry in entries:
        if entry.get("event") not in {
            "source_acquired",
            "source_projected",
            "qualification_answer_source_projected",
        }:
            continue
        answer = entry.get("answer")
        source = entry.get("source")
        if not isinstance(source, dict) and isinstance(answer, dict):
            source = answer.get("source")
        if not isinstance(source, dict):
            continue
        source_id = source.get("id")
        source_sha256 = source.get("sha256")
        if not isinstance(source_id, str) or not source_id:
            continue
        previous = digests.get(source_id)
        if previous is not None and previous != source_sha256:
            return {}, f"{source_id} has conflicting immutable source digests"
        digests[source_id] = source_sha256
    return digests, None


def bind(
    closure: dict[str, object], entries: list[dict[str, object]]
) -> dict[str, object]:
    outcomes = closure.get("outcomes")
    if not isinstance(outcomes, list):
        return {"complete": False, "why": "closure outcomes must be one ordered list"}
    source_digests, source_error = _source_digests(entries)
    if source_error is not None:
        return {"complete": False, "why": source_error}
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for position, outcome in enumerate(outcomes, 1):
        if not isinstance(outcome, dict):
            return {
                "complete": False,
                "why": f"closure outcome {position} is not one record",
            }
        source_id = outcome.get("source_id")
        terminal = outcome.get("outcome")
        if not isinstance(source_id, str) or not source_id or source_id in seen:
            return {
                "complete": False,
                "why": f"closure outcome {position} has an invalid or duplicate source identity",
            }
        seen.add(source_id)
        if terminal not in {"projected", "pending", "failed"}:
            return {
                "complete": False,
                "why": f"{source_id} has invalid projection outcome {terminal!r}",
            }
        if terminal != "projected":
            reason = outcome.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                return {
                    "complete": False,
                    "why": f"{terminal} source {source_id} has no conversion reason",
                }
            records.append(
                {
                    "source_id": source_id,
                    "source_sha256": outcome.get("source_sha256"),
                    "outcome": terminal,
                    "reason": reason,
                    "record": None,
                }
            )
            continue

        projection = outcome.get("projection")
        sequence = (
            projection.get("ledger_sequence")
            if isinstance(projection, dict)
            else None
        )
        if not isinstance(sequence, int) or sequence < 1 or sequence > len(entries):
            return {
                "complete": False,
                "why": f"projected {source_id} has no exact projection ledger sequence",
            }
        entry = entries[sequence - 1]
        full = entry.get("projection")
        answer = entry.get("answer")
        if not isinstance(full, dict) and isinstance(answer, dict):
            full = answer.get("projection")
        if not isinstance(full, dict):
            return {
                "complete": False,
                "why": f"ledger entry {sequence} lost the projection for {source_id}",
            }
        if _entry_source_id(entry, full) != source_id:
            return {
                "complete": False,
                "why": f"ledger entry {sequence} is bound to a different source than {source_id}",
            }
        if source_digests.get(source_id) != outcome.get("source_sha256"):
            return {
                "complete": False,
                "why": f"{source_id} source digest differs between closure and ledger",
            }
        for key in ("id", "version", "path", "sha256"):
            if projection.get(key) != full.get(key):
                return {
                    "complete": False,
                    "why": f"{source_id} projection {key} differs between closure and ledger",
                }
        method = _projection_method(entry, full)
        compatibility = None
        if method == "visual_spatial":
            compatibility = {
                "legacy_method": "visual_spatial",
                "canonical_method": "visual_spatial_v1",
            }
            method = "visual_spatial_v1"
        if method not in SUPPORTED_METHODS:
            return {
                "complete": False,
                "why": f"{source_id} has unsupported projection method {method!r}",
            }
        records.append(
            {
                "source_id": source_id,
                "source_sha256": outcome.get("source_sha256"),
                "outcome": terminal,
                "reason": None,
                "record": {
                    **full,
                    "method": method,
                    **(
                        {"method_compatibility": compatibility}
                        if compatibility is not None
                        else {}
                    ),
                },
                "projection_ledger_sequence": sequence,
            }
        )
    return {"complete": True, "records": records}
