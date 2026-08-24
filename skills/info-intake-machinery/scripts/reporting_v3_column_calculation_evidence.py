"""Capture one Reporting V3 column and its complete calculation provenance."""

from __future__ import annotations

import hashlib
import json

from reporting_v3_calculation_provenance import trace_root


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def capture_column_evidence(
    column_index: object,
    source: str,
    *,
    excel_column: str,
    expected_header: str,
    expected_root: str,
) -> dict[str, object]:
    if not isinstance(column_index, dict) or not isinstance(
        column_index.get("columns"), list
    ):
        raise ValueError("Reporting V3 column index has invalid columns")
    matches = [
        item
        for item in column_index["columns"]
        if isinstance(item, dict) and item.get("excel_column") == excel_column
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Reporting V3 column {excel_column!r} occurs {len(matches)} times; expected one"
        )
    column = matches[0]
    writer = column.get("writer")
    if not isinstance(writer, dict):
        raise ValueError(f"Reporting V3 column {excel_column!r} has no writer record")
    if column.get("header") != expected_header:
        raise ValueError(
            f"Reporting V3 column {excel_column!r} header {column.get('header')!r} "
            f"differs from {expected_header!r}"
        )
    if writer.get("expression") != expected_root:
        raise ValueError(
            f"Reporting V3 column {excel_column!r} writer {writer.get('expression')!r} "
            f"differs from {expected_root!r}"
        )
    spans = trace_root(source, expected_root, writer.get("line_number"))
    if len(spans) != 1:
        raise ValueError(
            f"calculation root {expected_root!r} has {len(spans)} provenance spans; expected one"
        )
    evidence: dict[str, object] = {
        "schema_version": 1,
        "excel_column": excel_column,
        "column_record": column,
        "column_record_sha256": hashlib.sha256(_canonical(column)).hexdigest(),
        "root": expected_root,
        "provenance_spans": spans,
    }
    evidence["record_sha256"] = hashlib.sha256(_canonical(evidence)).hexdigest()
    return evidence
