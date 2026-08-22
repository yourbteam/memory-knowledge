#!/usr/bin/env python3
"""Publish immutable assessment packets for all formula claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from formula_assessment_artifact_lineage import load_verified
from formula_assessment_packet_assembly import assemble
from reporting_v3_column_index import (
    ReportingV3IndexError,
    _canonical,
    _sha,
)


class FormulaAssessmentPacketError(ValueError):
    """Formula assessment packets cannot be published safely."""


def publish(work: Path) -> dict[str, object]:
    work = work.resolve()
    formula_root = work / "formula-map"
    lineage = load_verified(formula_root)
    inventory = lineage["inventory"]
    bindings = lineage["bindings"]
    provenance = lineage["provenance"]
    hashes = lineage["sha256"]
    entries = lineage["ledger_entries"]
    assert isinstance(inventory, dict)
    assert isinstance(bindings, dict)
    assert isinstance(provenance, dict)
    assert isinstance(hashes, dict)
    assert isinstance(entries, list)
    packets = assemble(inventory, bindings, provenance)
    explicit = sum(bool(packet["column_evidence"]) for packet in packets)
    result = {
        "schema_version": 1,
        "intake_id": inventory.get("intake_id"),
        "claim_inventory_sha256": hashes["inventory"],
        "claim_column_bindings_sha256": hashes["bindings"],
        "reporting_v3_provenance_index_sha256": hashes["provenance"],
        "packet_count": len(packets),
        "code_evidence_packet_count": explicit,
        "no_explicit_column_evidence_packet_count": len(packets) - explicit,
        "packets": packets,
    }
    result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
    result_sha256 = _sha(result_bytes)
    result_path = formula_root / "assessment-packets.json"
    event = {
        "schema_version": 1,
        "sequence": 5,
        "event": "formula_assessment_packets_recorded",
        "previous_entry_sha256": entries[3]["entry_sha256"],
        "intake_id": inventory.get("intake_id"),
        "assessment_packets_path": str(result_path.relative_to(work)),
        "assessment_packets_sha256": result_sha256,
        "packet_count": len(packets),
        "code_evidence_packet_count": explicit,
    }
    event["entry_sha256"] = _sha(_canonical(event))
    event_bytes = _canonical(event) + b"\n"
    if result_path.exists():
        if result_path.read_bytes() != result_bytes:
            raise FormulaAssessmentPacketError(
                "assessment packets exist with different immutable bytes"
            )
    else:
        with result_path.open("xb") as handle:
            handle.write(result_bytes)
    ledger_path = formula_root / "ledger.jsonl"
    if len(entries) == 4:
        with ledger_path.open("ab") as handle:
            handle.write(event_bytes)
    elif len(entries) != 5 or _canonical(entries[4]) + b"\n" != event_bytes:
        raise FormulaAssessmentPacketError(
            "formula-map ledger contains a different event after provenance indexing"
        )
    return {
        "status": "formula_assessment_packets_recorded",
        "packet_count": len(packets),
        "code_evidence_packet_count": explicit,
        "no_explicit_column_evidence_packet_count": len(packets) - explicit,
        "assessment_packets": str(result_path),
        "assessment_packets_sha256": result_sha256,
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
