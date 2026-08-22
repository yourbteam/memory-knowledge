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


def test_live_shared_context_covers_all_ten_columns_with_headers() -> None:
    module = _module("formula_assessment_shared_context")
    root = Path(
        "/Users/kamenkamenov/InfoIntakes/operator-dashboard-formula-map-2026-08-22/"
        "formula-map"
    )
    if not (root / "assessment-packets.json").is_file():
        pytest.skip("captured live assessment packets are unavailable")
    packets = json.loads((root / "assessment-packets.json").read_text())
    provenance = json.loads((root / "reporting-v3-provenance-index.json").read_text())

    shared = module.build(packets, provenance)

    assert len(shared) == 10
    assert {item["excel_column"] for item in shared} == {
        "AC", "AE", "AF", "AT", "C", "F", "I", "K", "W", "X"
    }
    assert all(item["column_record"]["header"] for item in shared)
    assert all(item["provenance_spans"] for item in shared)


def test_shared_context_refuses_missing_provenance() -> None:
    module = _module("formula_assessment_shared_context")
    record = {
        "column_number": 1,
        "excel_column": "A",
        "header": "Count",
        "writer": {},
    }
    packets = {
        "packets": [
            {
                "binding": {
                    "referenced_columns": [
                        {"excel_column": "A", "column_record": record}
                    ]
                }
            }
        ]
    }
    with pytest.raises(ValueError, match="missing=.*A"):
        module.build(packets, {"columns": []})
