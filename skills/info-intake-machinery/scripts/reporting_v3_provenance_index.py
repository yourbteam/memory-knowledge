#!/usr/bin/env python3
"""Publish calculation provenance for referenced Reporting V3 columns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting_v3_calculation_provenance import trace_root
from reporting_v3_expression_roots import extract_root
from reporting_v3_column_index import (
    ReportingV3IndexError,
    _canonical,
    _read_object,
    _sha,
    _validate_formula_ledger,
)


class ReportingV3ProvenanceError(ValueError):
    """Calculation provenance cannot be published safely."""


def build(
    source: str,
    columns: list[object],
    referenced_columns: list[object],
) -> list[dict[str, object]]:
    """Build exact provenance records in canonical Excel-column order."""

    if not isinstance(source, str):
        raise ReportingV3ProvenanceError("Reporting V3 source must be text")
    if not isinstance(columns, list) or not isinstance(referenced_columns, list):
        raise ReportingV3ProvenanceError(
            "columns and referenced_columns must both be lists"
        )
    index: dict[str, dict[str, object]] = {}
    for position, value in enumerate(columns):
        if not isinstance(value, dict) or not isinstance(
            value.get("excel_column"), str
        ):
            raise ReportingV3ProvenanceError(
                f"column index item {position} has no valid Excel-column identity"
            )
        identity = str(value["excel_column"])
        if identity in index:
            raise ReportingV3ProvenanceError(
                f"column index repeats Excel column {identity!r}"
            )
        index[identity] = value
    requested: list[str] = []
    for position, value in enumerate(referenced_columns):
        if not isinstance(value, str) or not value:
            raise ReportingV3ProvenanceError(
                f"referenced column {position} must be a nonempty string"
            )
        if value in requested:
            raise ReportingV3ProvenanceError(
                f"referenced columns repeat Excel column {value!r}"
            )
        requested.append(value)
    unknown = sorted(set(requested) - set(index))
    if unknown:
        raise ReportingV3ProvenanceError(
            f"referenced columns are absent from the Reporting V3 index: {unknown}"
        )
    records: list[dict[str, object]] = []
    for identity in sorted(requested, key=lambda item: int(index[item]["column_number"])):
        column = index[identity]
        writer = column.get("writer")
        if not isinstance(writer, dict):
            raise ReportingV3ProvenanceError(
                f"column {identity!r} has no writer record"
            )
        expression = writer.get("expression")
        writer_line = writer.get("line_number")
        if not isinstance(expression, str) or not isinstance(writer_line, int):
            raise ReportingV3ProvenanceError(
                f"column {identity!r} has incomplete writer evidence"
            )
        root = extract_root(expression)
        spans = trace_root(source, root, writer_line)
        if not spans:
            raise ReportingV3ProvenanceError(
                f"column {identity!r} root {root!r} has no calculation provenance before its writer"
            )
        record = {
            "excel_column": identity,
            "column_record_sha256": _sha(_canonical(column)),
            "root": root,
            "writer_line_number": writer_line,
            "provenance_spans": spans,
        }
        record["record_sha256"] = _sha(_canonical(record))
        records.append(record)
    return records


def publish(work: Path) -> dict[str, object]:
    work = work.resolve()
    formula_root = work / "formula-map"
    index_path = formula_root / "reporting-v3-column-index.json"
    bindings_path = formula_root / "claim-column-bindings.json"
    index_bytes = index_path.read_bytes()
    bindings_bytes = bindings_path.read_bytes()
    column_index = _read_object(index_path, "Reporting V3 column index")
    bindings = _read_object(bindings_path, "claim-column bindings")
    entries = _validate_formula_ledger(formula_root / "ledger.jsonl")
    if len(entries) < 3:
        raise ReportingV3ProvenanceError(
            "calculation provenance requires the first three formula-map ledger entries"
        )
    if (
        entries[1].get("event") != "reporting_v3_column_index_recorded"
        or entries[1].get("index_sha256") != _sha(index_bytes)
        or entries[2].get("event") != "formula_claim_column_bindings_recorded"
        or entries[2].get("bindings_sha256") != _sha(bindings_bytes)
    ):
        raise ReportingV3ProvenanceError(
            "column index or claim bindings differ from formula-map ledger evidence"
        )
    source_record = column_index.get("source")
    if not isinstance(source_record, dict) or not isinstance(
        source_record.get("path"), str
    ):
        raise ReportingV3ProvenanceError("column index has no source record")
    source_path = (work / str(source_record["path"])).resolve()
    if source_path.parent != (work / "sources").resolve():
        raise ReportingV3ProvenanceError(
            "column-index source escapes the immutable source directory"
        )
    source_bytes = source_path.read_bytes()
    if _sha(source_bytes) != source_record.get("sha256"):
        raise ReportingV3ProvenanceError(
            "Reporting V3 source differs from its column-index evidence"
        )
    try:
        source = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReportingV3ProvenanceError(
            "Reporting V3 source is not UTF-8 text"
        ) from exc
    columns = column_index.get("columns")
    referenced = bindings.get("unique_referenced_columns")
    records = build(source, columns, referenced)  # type: ignore[arg-type]
    result = {
        "schema_version": 1,
        "intake_id": column_index.get("intake_id"),
        "source": source_record,
        "column_index_sha256": _sha(index_bytes),
        "claim_column_bindings_sha256": _sha(bindings_bytes),
        "referenced_column_count": len(records),
        "columns": records,
    }
    result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
    result_sha256 = _sha(result_bytes)
    result_path = formula_root / "reporting-v3-provenance-index.json"
    event = {
        "schema_version": 1,
        "sequence": 4,
        "event": "reporting_v3_provenance_index_recorded",
        "previous_entry_sha256": entries[2]["entry_sha256"],
        "intake_id": column_index.get("intake_id"),
        "source_id": source_record.get("id"),
        "source_sha256": source_record.get("sha256"),
        "provenance_index_path": str(result_path.relative_to(work)),
        "provenance_index_sha256": result_sha256,
        "referenced_column_count": len(records),
    }
    event["entry_sha256"] = _sha(_canonical(event))
    event_bytes = _canonical(event) + b"\n"
    if result_path.exists():
        if result_path.read_bytes() != result_bytes:
            raise ReportingV3ProvenanceError(
                "provenance index exists with different immutable bytes"
            )
    else:
        with result_path.open("xb") as handle:
            handle.write(result_bytes)
    ledger_path = formula_root / "ledger.jsonl"
    if len(entries) == 3:
        with ledger_path.open("ab") as handle:
            handle.write(event_bytes)
    elif len(entries) != 4 or _canonical(entries[3]) + b"\n" != event_bytes:
        raise ReportingV3ProvenanceError(
            "formula-map ledger contains a different event after claim-column bindings"
        )
    return {
        "status": "reporting_v3_provenance_index_recorded",
        "referenced_column_count": len(records),
        "provenance_index": str(result_path),
        "provenance_index_sha256": result_sha256,
        "ledger_tail_sha256": event["entry_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = publish(args.work)
    except (OSError, ValueError, ReportingV3IndexError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
