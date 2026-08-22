#!/usr/bin/env python3
"""Publish shared code evidence for every formula assessment question."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting_v3_column_index import _canonical, _read_object, _sha, _validate_formula_ledger


def build(
    packets_value: dict[str, object], provenance_value: dict[str, object]
) -> list[dict[str, object]]:
    packets = packets_value.get("packets")
    provenance = provenance_value.get("columns")
    if not isinstance(packets, list) or not isinstance(provenance, list):
        raise ValueError("assessment packets and provenance must expose item lists")
    column_records: dict[str, dict[str, object]] = {}
    for packet in packets:
        if not isinstance(packet, dict):
            raise ValueError("assessment packet is not an object")
        binding = packet.get("binding")
        references = binding.get("referenced_columns") if isinstance(binding, dict) else None
        if not isinstance(references, list):
            raise ValueError("assessment packet has no referenced-column list")
        for reference in references:
            if not isinstance(reference, dict) or not isinstance(
                reference.get("excel_column"), str
            ):
                raise ValueError("assessment packet has invalid column reference")
            identity = str(reference["excel_column"])
            record = reference.get("column_record")
            if not isinstance(record, dict):
                raise ValueError(f"column {identity!r} has no complete column record")
            previous = column_records.get(identity)
            if previous is not None and previous != record:
                raise ValueError(f"column {identity!r} has conflicting records")
            column_records[identity] = record
    provenance_index: dict[str, dict[str, object]] = {}
    for item in provenance:
        if not isinstance(item, dict) or not isinstance(item.get("excel_column"), str):
            raise ValueError("provenance contains invalid column identity")
        identity = str(item["excel_column"])
        if identity in provenance_index:
            raise ValueError(f"provenance repeats column {identity!r}")
        provenance_index[identity] = item
    missing = sorted(set(column_records) - set(provenance_index))
    unknown = sorted(set(provenance_index) - set(column_records))
    if missing or unknown:
        raise ValueError(
            f"shared code coverage differs: missing={missing}, unknown={unknown}"
        )
    shared: list[dict[str, object]] = []
    for identity in sorted(
        column_records, key=lambda value: int(column_records[value]["column_number"])
    ):
        record = column_records[identity]
        evidence = provenance_index[identity]
        if evidence.get("column_record_sha256") != _sha(_canonical(record)):
            raise ValueError(
                f"column {identity!r} record differs between packets and provenance"
            )
        shared.append(
            {
                "excel_column": identity,
                "column_record": record,
                "column_record_sha256": evidence["column_record_sha256"],
                "root": evidence.get("root"),
                "writer_line_number": evidence.get("writer_line_number"),
                "provenance_spans": evidence.get("provenance_spans"),
                "provenance_record_sha256": evidence.get("record_sha256"),
            }
        )
    return shared


def publish(work: Path) -> dict[str, object]:
    work = work.resolve()
    formula_root = work / "formula-map"
    packets_path = formula_root / "assessment-packets.json"
    provenance_path = formula_root / "reporting-v3-provenance-index.json"
    packets_bytes = packets_path.read_bytes()
    provenance_bytes = provenance_path.read_bytes()
    packets_value = _read_object(packets_path, "assessment packets")
    provenance_value = _read_object(provenance_path, "Reporting V3 provenance")
    entries = _validate_formula_ledger(formula_root / "ledger.jsonl")
    if (
        len(entries) < 5
        or entries[4].get("event") != "formula_assessment_packets_recorded"
        or entries[4].get("assessment_packets_sha256") != _sha(packets_bytes)
        or entries[3].get("provenance_index_sha256") != _sha(provenance_bytes)
    ):
        raise ValueError("shared context inputs differ from formula-map ledger evidence")
    shared = build(packets_value, provenance_value)
    result = {
        "schema_version": 1,
        "intake_id": packets_value.get("intake_id"),
        "assessment_packets_sha256": _sha(packets_bytes),
        "reporting_v3_provenance_index_sha256": _sha(provenance_bytes),
        "shared_code_evidence_count": len(shared),
        "shared_code_evidence": shared,
    }
    result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
    result_sha256 = _sha(result_bytes)
    result_path = formula_root / "assessment-shared-context.json"
    event = {
        "schema_version": 1,
        "sequence": 6,
        "event": "formula_assessment_shared_context_recorded",
        "previous_entry_sha256": entries[4]["entry_sha256"],
        "intake_id": packets_value.get("intake_id"),
        "shared_context_path": str(result_path.relative_to(work)),
        "shared_context_sha256": result_sha256,
        "shared_code_evidence_count": len(shared),
    }
    event["entry_sha256"] = _sha(_canonical(event))
    event_bytes = _canonical(event) + b"\n"
    if result_path.exists():
        if result_path.read_bytes() != result_bytes:
            raise ValueError("shared assessment context exists with different bytes")
    else:
        with result_path.open("xb") as handle:
            handle.write(result_bytes)
    ledger_path = formula_root / "ledger.jsonl"
    if len(entries) == 5:
        with ledger_path.open("ab") as handle:
            handle.write(event_bytes)
    elif len(entries) != 6 or _canonical(entries[5]) + b"\n" != event_bytes:
        raise ValueError("formula-map ledger contains a different event after packets")
    return {
        "status": "formula_assessment_shared_context_recorded",
        "shared_code_evidence_count": len(shared),
        "shared_context": str(result_path),
        "shared_context_sha256": result_sha256,
        "ledger_tail_sha256": event["entry_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = publish(args.work)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
