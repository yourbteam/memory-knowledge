from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/info-intake-machinery/scripts"


def _module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_packet_assembly_binds_exact_claim_and_column_evidence() -> None:
    module = _module("formula_assessment_packet_assembly")
    claim = {"id": "claim-1", "statement": "Column A is used"}
    column = {"excel_column": "A", "column_record_sha256": "a" * 64}
    binding = {
        "claim_id": "claim-1",
        "referenced_columns": [
            {"excel_column": "A", "column_record_sha256": "a" * 64}
        ],
    }

    packets = module.assemble(
        {"claims": [claim]},
        {"bindings": [binding]},
        {"columns": [column]},
    )

    assert packets[0]["claim"] == claim
    assert packets[0]["column_evidence"] == [column]
    assert packets[0]["evidence_status"] == "code_evidence_bound"
    assert len(packets[0]["packet_sha256"]) == 64


def test_packet_assembly_refuses_missing_and_changed_evidence() -> None:
    module = _module("formula_assessment_packet_assembly")
    inventory = {"claims": [{"id": "claim-1"}]}
    with pytest.raises(ValueError, match="missing=.*claim-1"):
        module.assemble(inventory, {"bindings": []}, {"columns": []})
    with pytest.raises(ValueError, match="changed between binding and provenance"):
        module.assemble(
            inventory,
            {
                "bindings": [
                    {
                        "claim_id": "claim-1",
                        "referenced_columns": [
                            {"excel_column": "A", "column_record_sha256": "a" * 64}
                        ],
                    }
                ]
            },
            {
                "columns": [
                    {"excel_column": "A", "column_record_sha256": "b" * 64}
                ]
            },
        )


def test_live_artifacts_assemble_27_packets_with_22_code_bound() -> None:
    lineage_module = _module("formula_assessment_artifact_lineage")
    packet_module = _module("formula_assessment_packet_assembly")
    formula_root = Path(
        "/Users/kamenkamenov/InfoIntakes/operator-dashboard-formula-map-2026-08-22/"
        "formula-map"
    )
    if not (formula_root / "reporting-v3-provenance-index.json").is_file():
        pytest.skip("captured live formula-map evidence is unavailable")
    lineage = lineage_module.load_verified(formula_root)

    packets = packet_module.assemble(
        lineage["inventory"], lineage["bindings"], lineage["provenance"]
    )

    assert len(packets) == 27
    assert sum(bool(packet["column_evidence"]) for packet in packets) == 22
    assert [packet["claim"]["id"] for packet in packets] == [
        f"claim-{number:06d}" for number in range(1, 28)
    ]
    assert all(len(packet["packet_sha256"]) == 64 for packet in packets)
