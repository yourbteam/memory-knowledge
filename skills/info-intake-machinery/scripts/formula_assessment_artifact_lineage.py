"""Load and verify the immutable artifacts used by formula assessment."""

from __future__ import annotations

from pathlib import Path

from reporting_v3_column_index import _read_object, _sha, _validate_formula_ledger


def load_verified(formula_root: Path) -> dict[str, object]:
    """Return parsed artifacts only when bytes, ledger, and lineage all agree."""

    names = {
        "inventory": "claim-inventory.json",
        "bindings": "claim-column-bindings.json",
        "provenance": "reporting-v3-provenance-index.json",
    }
    paths = {name: formula_root / filename for name, filename in names.items()}
    payloads = {name: path.read_bytes() for name, path in paths.items()}
    values = {
        name: _read_object(path, f"formula assessment {name}")
        for name, path in paths.items()
    }
    hashes = {name: _sha(data) for name, data in payloads.items()}
    entries = _validate_formula_ledger(formula_root / "ledger.jsonl")
    expected = [
        (0, "formula_claim_inventory_recorded", "inventory_sha256", "inventory"),
        (2, "formula_claim_column_bindings_recorded", "bindings_sha256", "bindings"),
        (
            3,
            "reporting_v3_provenance_index_recorded",
            "provenance_index_sha256",
            "provenance",
        ),
    ]
    if len(entries) < 4:
        raise ValueError("formula assessment requires four prior ledger entries")
    for position, event, field, artifact in expected:
        entry = entries[position]
        if entry.get("event") != event or entry.get(field) != hashes[artifact]:
            raise ValueError(
                f"{artifact} artifact differs from formula-map ledger entry {position + 1}"
            )
    if values["bindings"].get("claim_inventory_sha256") != hashes["inventory"]:
        raise ValueError("claim bindings do not bind the exact claim inventory")
    if (
        values["provenance"].get("claim_column_bindings_sha256")
        != hashes["bindings"]
    ):
        raise ValueError("calculation provenance does not bind the exact claim bindings")
    return {
        "inventory": values["inventory"],
        "bindings": values["bindings"],
        "provenance": values["provenance"],
        "sha256": hashes,
        "ledger_entries": entries,
    }
