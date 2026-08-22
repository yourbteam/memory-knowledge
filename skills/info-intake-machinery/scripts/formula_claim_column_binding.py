#!/usr/bin/env python3
"""Publish exact Reporting V3 column evidence for every formula claim."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from formula_column_evidence_binding import bind
from formula_column_reference_recognition import recognize
from reporting_v3_column_index import (
    ReportingV3IndexError,
    _canonical,
    _read_object,
    _sha,
    _validate_formula_ledger,
)


class FormulaClaimColumnBindingError(ValueError):
    """Claim-to-column evidence cannot be published safely."""


def publish(work: Path) -> dict[str, object]:
    work = work.resolve()
    formula_root = work / "formula-map"
    inventory_path = formula_root / "claim-inventory.json"
    index_path = formula_root / "reporting-v3-column-index.json"
    inventory_bytes = inventory_path.read_bytes()
    index_bytes = index_path.read_bytes()
    inventory = _read_object(inventory_path, "formula claim inventory")
    index = _read_object(index_path, "Reporting V3 column index")
    entries = _validate_formula_ledger(formula_root / "ledger.jsonl")
    if len(entries) < 2:
        raise FormulaClaimColumnBindingError(
            "claim-column binding requires inventory and column-index ledger entries"
        )
    if (
        entries[0].get("event") != "formula_claim_inventory_recorded"
        or entries[0].get("inventory_sha256") != _sha(inventory_bytes)
        or entries[1].get("event") != "reporting_v3_column_index_recorded"
        or entries[1].get("index_sha256") != _sha(index_bytes)
    ):
        raise FormulaClaimColumnBindingError(
            "claim inventory or column index differs from its ledger evidence"
        )
    claims = inventory.get("claims")
    columns = index.get("columns")
    if not isinstance(claims, list) or not isinstance(columns, list):
        raise FormulaClaimColumnBindingError(
            "claim inventory and column index must expose their complete item lists"
        )
    bindings = []
    seen: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("id"), str):
            raise FormulaClaimColumnBindingError("claim inventory contains invalid identity")
        claim_id = str(claim["id"])
        if claim_id in seen:
            raise FormulaClaimColumnBindingError(f"duplicate claim id {claim_id!r}")
        seen.add(claim_id)
        statement = claim.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            raise FormulaClaimColumnBindingError(
                f"claim {claim_id!r} has no statement"
            )
        bindings.append(bind(claim_id, recognize(statement), columns))
    explicit = [item for item in bindings if item["referenced_columns"]]
    unique_columns = sorted(
        {
            reference["excel_column"]
            for item in bindings
            for reference in item["referenced_columns"]
        }
    )
    result = {
        "schema_version": 1,
        "intake_id": inventory.get("intake_id"),
        "claim_inventory_sha256": _sha(inventory_bytes),
        "column_index_sha256": _sha(index_bytes),
        "claim_count": len(bindings),
        "explicit_reference_claim_count": len(explicit),
        "no_explicit_reference_claim_count": len(bindings) - len(explicit),
        "unique_referenced_columns": unique_columns,
        "bindings": bindings,
    }
    result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
    result_sha256 = _sha(result_bytes)
    result_path = formula_root / "claim-column-bindings.json"
    event = {
        "schema_version": 1,
        "sequence": 3,
        "event": "formula_claim_column_bindings_recorded",
        "previous_entry_sha256": entries[1]["entry_sha256"],
        "intake_id": inventory.get("intake_id"),
        "bindings_path": str(result_path.relative_to(work)),
        "bindings_sha256": result_sha256,
        "claim_count": len(bindings),
        "explicit_reference_claim_count": len(explicit),
        "unique_referenced_columns": unique_columns,
    }
    event["entry_sha256"] = _sha(_canonical(event))
    event_bytes = _canonical(event) + b"\n"
    if result_path.exists():
        if result_path.read_bytes() != result_bytes:
            raise FormulaClaimColumnBindingError(
                "claim-column bindings exist with different immutable bytes"
            )
    else:
        with result_path.open("xb") as handle:
            handle.write(result_bytes)
    ledger_path = formula_root / "ledger.jsonl"
    if len(entries) == 2:
        with ledger_path.open("ab") as handle:
            handle.write(event_bytes)
    elif len(entries) != 3 or _canonical(entries[2]) + b"\n" != event_bytes:
        raise FormulaClaimColumnBindingError(
            "formula-map ledger contains a different event after the column index"
        )
    return {
        "status": "formula_claim_column_bindings_recorded",
        "claim_count": len(bindings),
        "explicit_reference_claim_count": len(explicit),
        "no_explicit_reference_claim_count": len(bindings) - len(explicit),
        "unique_referenced_columns": unique_columns,
        "bindings": str(result_path),
        "bindings_sha256": result_sha256,
        "ledger_tail_sha256": event["entry_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = publish(args.work)
    except (OSError, ValueError, ReportingV3IndexError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
