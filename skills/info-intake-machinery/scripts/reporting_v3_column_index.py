#!/usr/bin/env python3
"""Publish the Reporting V3 column-to-code evidence index."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from reporting_v3_header_mapping import parse_headers
from reporting_v3_writer_provenance import parse_writers
from start_intake import _validate_ledger


class ReportingV3IndexError(ValueError):
    """The Reporting V3 column index cannot be published safely."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportingV3IndexError(f"{label} is not readable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ReportingV3IndexError(f"{label} must be one JSON object")
    return value


def _excel_letter(column: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _validate_formula_ledger(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise ReportingV3IndexError("formula-map ledger is unavailable")
    entries: list[dict[str, object]] = []
    previous: str | None = None
    for sequence, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReportingV3IndexError(
                f"formula-map ledger entry {sequence} is not valid JSON"
            ) from exc
        if not isinstance(entry, dict):
            raise ReportingV3IndexError(
                f"formula-map ledger entry {sequence} must be an object"
            )
        claimed = entry.pop("entry_sha256", None)
        actual = _sha(_canonical(entry))
        entry["entry_sha256"] = claimed
        if (
            entry.get("sequence") != sequence
            or entry.get("previous_entry_sha256") != previous
            or claimed != actual
        ):
            raise ReportingV3IndexError(
                f"formula-map ledger entry {sequence} fails its hash chain"
            )
        entries.append(entry)
        previous = str(claimed)
    if not entries:
        raise ReportingV3IndexError("formula-map ledger is empty")
    return entries


def publish(work: Path, source_path: Path) -> dict[str, object]:
    work = work.resolve()
    state = _read_object(work / "intake-state.json", "intake state")
    source_ledger, source_error = _validate_ledger(work / "ledger.jsonl")
    if (
        state.get("status") != "first_layer_complete"
        or source_error
        or not source_ledger
        or source_ledger[-1].get("entry_sha256") != state.get("ledger_tail_sha256")
    ):
        raise ReportingV3IndexError(
            f"source layer is not an intact terminal intake: {source_error or 'state mismatch'}"
        )
    source_path = source_path.resolve()
    if source_path.parent != (work / "sources").resolve():
        raise ReportingV3IndexError(
            "Reporting V3 source must be an immutable artifact directly under work/sources"
        )
    source_bytes = source_path.read_bytes()
    source_sha256 = _sha(source_bytes)
    source_id = source_path.name
    qualification_record = state.get("source_set_qualification")
    qualification = (
        qualification_record.get("qualification")
        if isinstance(qualification_record, dict)
        else None
    )
    outcomes = qualification.get("outcomes") if isinstance(qualification, dict) else None
    matches = [
        item
        for item in outcomes or []
        if isinstance(item, dict) and item.get("source_id") == source_id
    ]
    if len(matches) != 1:
        raise ReportingV3IndexError(
            f"source {source_id!r} must have exactly one qualification outcome"
        )
    outcome = matches[0]
    if (
        outcome.get("method") != "verbatim_utf8"
        or outcome.get("projection_sha256") != source_sha256
    ):
        raise ReportingV3IndexError(
            f"source {source_id!r} is not the exact qualified verbatim code"
        )
    try:
        source = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReportingV3IndexError("Reporting V3 source is not UTF-8 code") from exc
    headers = parse_headers(source)
    writers = parse_writers(source)
    columns = []
    for column, (header, writer) in enumerate(zip(headers, writers), start=1):
        if writer["column_number"] != column:
            raise ReportingV3IndexError(
                f"writer position {writer['column_number']} does not match header {column}"
            )
        columns.append(
            {
                "column_number": column,
                "excel_column": _excel_letter(column),
                "header": header["header"],
                "header_line_number": header["line_number"],
                "writer": writer,
            }
        )
    index = {
        "schema_version": 1,
        "intake_id": state.get("intake_id"),
        "source": {
            "id": source_id,
            "path": str(source_path.relative_to(work)),
            "sha256": source_sha256,
        },
        "column_count": len(columns),
        "columns": columns,
    }
    index_bytes = json.dumps(index, indent=2, sort_keys=True).encode() + b"\n"
    index_sha256 = _sha(index_bytes)
    formula_root = work / "formula-map"
    ledger_path = formula_root / "ledger.jsonl"
    entries = _validate_formula_ledger(ledger_path)
    if entries[0].get("event") != "formula_claim_inventory_recorded":
        raise ReportingV3IndexError(
            "Reporting V3 index requires the formula claim inventory ledger entry"
        )
    index_path = formula_root / "reporting-v3-column-index.json"
    event = {
        "schema_version": 1,
        "sequence": 2,
        "event": "reporting_v3_column_index_recorded",
        "previous_entry_sha256": entries[0]["entry_sha256"],
        "intake_id": state.get("intake_id"),
        "source_id": source_id,
        "source_sha256": source_sha256,
        "index_path": str(index_path.relative_to(work)),
        "index_sha256": index_sha256,
        "column_count": len(columns),
    }
    event["entry_sha256"] = _sha(_canonical(event))
    event_bytes = _canonical(event) + b"\n"
    if index_path.exists():
        if index_path.read_bytes() != index_bytes:
            raise ReportingV3IndexError(
                "Reporting V3 column index exists with different immutable bytes"
            )
    else:
        with index_path.open("xb") as handle:
            handle.write(index_bytes)
    if len(entries) == 1:
        with ledger_path.open("ab") as handle:
            handle.write(event_bytes)
    elif len(entries) != 2 or _canonical(entries[1]) + b"\n" != event_bytes:
        raise ReportingV3IndexError(
            "formula-map ledger contains a different event after claim inventory"
        )
    return {
        "status": "reporting_v3_column_index_recorded",
        "column_count": len(columns),
        "index": str(index_path),
        "index_sha256": index_sha256,
        "ledger_tail_sha256": event["entry_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = publish(args.work, args.source)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
