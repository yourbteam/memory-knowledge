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


def test_expression_root_accepts_supported_shapes_and_refuses_composition() -> None:
    module = _module("reporting_v3_expression_roots")

    assert module.extract_root("row.SingleFullPriceCount") == "row.SingleFullPriceCount"
    assert module.extract_root("(double)totalPaidTx") == "totalPaidTx"
    assert (
        module.extract_root(
            "V3ReportAccountingCellWriter.WriteNetOperatorPayout(netOperatorPayout)"
        )
        == "netOperatorPayout"
    )
    with pytest.raises(ValueError, match="does not identify one"):
        module.extract_root("row.X + row.Y")


def test_provenance_traces_only_mutations_and_complete_definitions() -> None:
    module = _module("reporting_v3_calculation_provenance")
    source = """public int Count { get; set; }
row.Count++;
var ratio = row.Total > 0
    ? row.Count / row.Total : 0;
write(ratio);
"""

    assert module.trace_root(source, "row.Count", 5) == [
        {
            "kind": "row_mutation",
            "start_line": 2,
            "end_line": 2,
            "source": "row.Count++;",
        }
    ]
    assert module.trace_root(source, "ratio", 5) == [
        {
            "kind": "local_definition",
            "start_line": 3,
            "end_line": 4,
            "source": "var ratio = row.Total > 0 ? row.Count / row.Total : 0;",
        }
    ]
    assert module.trace_root(source, "missing", 5) == []


def test_live_source_proves_all_ten_referenced_columns() -> None:
    module = _module("reporting_v3_provenance_index")
    live = Path(
        "/Users/kamenkamenov/InfoIntakes/operator-dashboard-formula-map-2026-08-22"
    )
    source_path = live / "sources/source-000010"
    index_path = live / "formula-map/reporting-v3-column-index.json"
    bindings_path = live / "formula-map/claim-column-bindings.json"
    if not all(path.is_file() for path in (source_path, index_path, bindings_path)):
        pytest.skip("captured live intake is unavailable")
    index = json.loads(index_path.read_text())
    bindings = json.loads(bindings_path.read_text())

    records = module.build(
        source_path.read_text(),
        index["columns"],
        bindings["unique_referenced_columns"],
    )

    assert len(records) == 10
    assert {record["excel_column"] for record in records} == {
        "AC", "AE", "AF", "AT", "C", "F", "I", "K", "W", "X"
    }
    assert all(record["provenance_spans"] for record in records)
    kinds = {
        span["kind"]
        for record in records
        for span in record["provenance_spans"]
    }
    assert kinds == {"local_definition", "row_mutation"}


def test_build_refuses_unknown_and_duplicate_definitions() -> None:
    module = _module("reporting_v3_provenance_index")
    column = {
        "column_number": 1,
        "excel_column": "A",
        "writer": {"expression": "total", "line_number": 3},
    }
    with pytest.raises(ValueError, match="absent"):
        module.build("var total = 1;\nwrite(total);", [column], ["B"])
    with pytest.raises(ValueError, match="multiple local definitions"):
        module.build(
            "var total = 1;\nvar total = 2;\nwrite(total);",
            [column],
            ["A"],
        )
