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


def test_recognition_is_case_insensitive_ordered_and_deduplicated() -> None:
    module = _module("formula_column_reference_recognition")

    assert module.recognize("column X over Column W and Column: x") == ["X", "W"]


def test_binding_rejects_unknown_and_hashes_exact_record() -> None:
    module = _module("formula_column_evidence_binding")
    columns = [{"excel_column": "AF", "header": "Net Operator Payout"}]

    value = module.bind("claim-000001", ["AF"], columns)

    assert value["referenced_columns"][0]["column_record"] == columns[0]
    assert len(value["referenced_columns"][0]["column_record_sha256"]) == 64
    with pytest.raises(ValueError, match="unknown Reporting V3 columns"):
        module.bind("claim-000001", ["ZZ"], columns)


def test_live_shape_counts_22_explicit_claims_and_ten_columns() -> None:
    recognition = _module("formula_column_reference_recognition")
    inventory_path = Path(
        "/Users/kamenkamenov/InfoIntakes/operator-dashboard-formula-map-2026-08-22/"
        "formula-map/claim-inventory.json"
    )
    if not inventory_path.is_file():
        pytest.skip("captured live intake is unavailable")
    claims = json.loads(inventory_path.read_text())["claims"]
    references = [recognition.recognize(claim["statement"]) for claim in claims]

    assert len(references) == 27
    assert sum(bool(item) for item in references) == 22
    assert sorted({value for item in references for value in item}) == [
        "AC",
        "AE",
        "AF",
        "AT",
        "C",
        "F",
        "I",
        "K",
        "W",
        "X",
    ]
