#!/usr/bin/env python3
"""Publish one append-only, evidence-bound inventory of projected claims."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from formula_claim_binding import bind_claims
from formula_claim_selection import select_relationships
from start_intake import _validate_ledger


class FormulaClaimInventoryError(ValueError):
    """The formula claim inventory cannot be published safely."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FormulaClaimInventoryError(f"{label} is not readable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise FormulaClaimInventoryError(f"{label} must be one JSON object")
    return value


def _qualified_projection(
    state: dict[str, object], projection_id: str, projection_sha256: str
) -> dict[str, object]:
    qualification_record = state.get("source_set_qualification")
    if not isinstance(qualification_record, dict):
        raise FormulaClaimInventoryError("intake state has no source-set qualification")
    qualification = qualification_record.get("qualification")
    if not isinstance(qualification, dict) or not isinstance(
        qualification.get("outcomes"), list
    ):
        raise FormulaClaimInventoryError(
            "intake state has no complete source qualification outcomes"
        )
    matches = [
        item
        for item in qualification["outcomes"]
        if isinstance(item, dict) and item.get("projection_id") == projection_id
    ]
    if len(matches) != 1:
        raise FormulaClaimInventoryError(
            f"projection {projection_id!r} must have exactly one qualification outcome"
        )
    outcome = matches[0]
    if outcome.get("projection_sha256") != projection_sha256:
        raise FormulaClaimInventoryError(
            f"projection {projection_id!r} bytes differ from qualified evidence"
        )
    if outcome.get("method") != "visual_spatial_v1":
        raise FormulaClaimInventoryError(
            f"projection {projection_id!r} is not a visual_spatial_v1 projection"
        )
    return outcome


def _ledger_entry(payload: dict[str, object]) -> dict[str, object]:
    entry = {
        "schema_version": 1,
        "sequence": 1,
        "event": "formula_claim_inventory_recorded",
        "previous_entry_sha256": None,
        **payload,
    }
    entry["entry_sha256"] = _digest_bytes(_canonical(entry))
    return entry


def publish(work: Path, projection_path: Path) -> dict[str, object]:
    work = work.resolve()
    state = _read_json(work / "intake-state.json", "intake state")
    terminal = state.get("effective_first_layer_terminal")
    if (
        state.get("status") != "first_layer_complete"
        or not isinstance(terminal, dict)
        or not isinstance(terminal.get("entry_sha256"), str)
    ):
        raise FormulaClaimInventoryError(
            "claim inventory requires an immutable first_layer_complete intake"
        )
    source_entries, ledger_error = _validate_ledger(work / "ledger.jsonl")
    if ledger_error or not source_entries:
        raise FormulaClaimInventoryError(
            f"source ledger is invalid: {ledger_error or 'empty ledger'}"
        )
    if (
        source_entries[-1].get("entry_sha256") != state.get("ledger_tail_sha256")
        or terminal.get("entry_sha256") != state.get("ledger_tail_sha256")
    ):
        raise FormulaClaimInventoryError(
            "first-layer terminal, state, and source ledger tail do not match"
        )

    projection_path = projection_path.resolve()
    projection_root = (work / "projections").resolve()
    if projection_path.parent != projection_root:
        raise FormulaClaimInventoryError(
            "projection must be an immutable artifact directly under work/projections"
        )
    projection_bytes = projection_path.read_bytes()
    projection_sha256 = _digest_bytes(projection_bytes)
    projection_id = f"projection-{projection_path.stem}"
    qualification = _qualified_projection(state, projection_id, projection_sha256)
    projection = _read_json(projection_path, "claim source projection")
    relationships = select_relationships(projection)
    claims = bind_claims(
        projection,
        relationships,
        projection_id=projection_id,
        projection_sha256=projection_sha256,
    )
    inventory = {
        "schema_version": 1,
        "intake_id": state.get("intake_id"),
        "status": "pending_code_assessment",
        "source_ledger_tail_sha256": state["ledger_tail_sha256"],
        "source_projection": {
            "id": projection_id,
            "path": str(projection_path.relative_to(work)),
            "sha256": projection_sha256,
            "qualification": qualification.get("qualification"),
        },
        "claim_count": len(claims),
        "claims": claims,
    }
    inventory_bytes = json.dumps(
        inventory, indent=2, sort_keys=True
    ).encode() + b"\n"
    inventory_sha256 = _digest_bytes(inventory_bytes)
    formula_root = work / "formula-map"
    inventory_path = formula_root / "claim-inventory.json"
    ledger_path = formula_root / "ledger.jsonl"
    entry = _ledger_entry(
        {
            "intake_id": state.get("intake_id"),
            "source_ledger_tail_sha256": state["ledger_tail_sha256"],
            "projection_id": projection_id,
            "projection_sha256": projection_sha256,
            "inventory_path": str(inventory_path.relative_to(work)),
            "inventory_sha256": inventory_sha256,
            "claim_count": len(claims),
        }
    )
    entry_bytes = _canonical(entry) + b"\n"
    formula_root.mkdir(parents=True, exist_ok=True)
    if inventory_path.exists():
        if inventory_path.read_bytes() != inventory_bytes:
            raise FormulaClaimInventoryError(
                "claim inventory already exists with different immutable bytes"
            )
    else:
        with inventory_path.open("xb") as handle:
            handle.write(inventory_bytes)
    if ledger_path.exists():
        if ledger_path.read_bytes() != entry_bytes:
            raise FormulaClaimInventoryError(
                "formula-map ledger already exists with different immutable bytes"
            )
    else:
        with ledger_path.open("xb") as handle:
            handle.write(entry_bytes)
    return {
        "status": "formula_claim_inventory_recorded",
        "claim_count": len(claims),
        "inventory": str(inventory_path),
        "inventory_sha256": inventory_sha256,
        "ledger": str(ledger_path),
        "ledger_tail_sha256": entry["entry_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = publish(args.work, args.projection)
    except (FormulaClaimInventoryError, OSError, ValueError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
