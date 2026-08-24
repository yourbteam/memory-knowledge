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


def _source(*, duplicate_writer: bool = False) -> str:
    headers = ",\n".join(f'        "Header {column}"' for column in range(1, 82))
    writers = []
    for column in range(1, 82):
        if column == 30:
            writers.append(
                "            V3ReportAccountingCellWriter.WriteRedemptionFeesOwed("
                "ws.Cell(r, 30), redemptionFeesOwed);"
            )
        elif column == 32:
            writers.append(
                "            V3ReportAccountingCellWriter.WriteNetOperatorPayout("
                "ws.Cell(r, 32), netOperatorPayout);"
            )
        else:
            writers.append(
                f"            ws.Cell(r, {column}).Value = value{column};"
            )
    if duplicate_writer:
        writers.append("            ws.Cell(r, 81).Value = duplicate;")
    return (
        "private static readonly string[] V3ColumnHeaders =\n[\n"
        f"{headers}\n];\n"
        "internal static ExcelExportResult BuildV3ExcelResult()\n{\n"
        + "\n".join(writers)
        + "\n}\nprivate static string V3I(int value) => value.ToString();\n"
    )


def _work(tmp_path: Path) -> tuple[Path, Path]:
    start = _module("start_intake")
    inventory = _module("formula_claim_inventory")
    work = tmp_path / "intake"
    (work / "sources").mkdir(parents=True)
    source = work / "sources/source-000010"
    source.write_text(_source(), encoding="utf-8")
    opening = start._ledger_entry(
        1,
        "effective_first_layer_terminal_recorded",
        {"intake_id": "intake-test"},
        None,
    )
    (work / "ledger.jsonl").write_bytes(start._canonical(opening) + b"\n")
    source_sha256 = start._digest_bytes(source.read_bytes())
    state = {
        "intake_id": "intake-test",
        "status": "first_layer_complete",
        "ledger_tail_sha256": opening["entry_sha256"],
        "source_set_qualification": {
            "qualification": {
                "outcomes": [
                    {
                        "source_id": "source-000010",
                        "method": "verbatim_utf8",
                        "projection_sha256": source_sha256,
                    }
                ]
            }
        },
    }
    (work / "intake-state.json").write_text(json.dumps(state) + "\n")
    formula = work / "formula-map"
    formula.mkdir()
    claim_event = inventory._ledger_entry(
        {
            "intake_id": "intake-test",
            "source_ledger_tail_sha256": opening["entry_sha256"],
            "projection_id": "projection-source-000003-v1",
            "projection_sha256": "a" * 64,
            "inventory_path": "formula-map/claim-inventory.json",
            "inventory_sha256": "b" * 64,
            "claim_count": 1,
        }
    )
    (formula / "ledger.jsonl").write_bytes(inventory._canonical(claim_event) + b"\n")
    return work, source


def test_all_81_columns_are_mapped_to_exact_writer_evidence(tmp_path: Path) -> None:
    module = _module("reporting_v3_column_index")
    work, source = _work(tmp_path)

    first = module.publish(work, source)
    repeated = module.publish(work, source)

    assert first == repeated
    assert first["column_count"] == 81
    value = json.loads((work / "formula-map/reporting-v3-column-index.json").read_text())
    assert [item["excel_column"] for item in value["columns"][:3]] == ["A", "B", "C"]
    assert value["columns"][29]["writer"]["write_kind"] == "helper_call"
    assert value["columns"][31]["excel_column"] == "AF"
    assert value["columns"][31]["writer"]["expression"].endswith("(netOperatorPayout)")
    assert len((work / "formula-map/ledger.jsonl").read_text().splitlines()) == 2


def test_duplicate_writer_refuses_without_publishing_index(tmp_path: Path) -> None:
    module = _module("reporting_v3_column_index")
    work, source = _work(tmp_path)
    source.write_text(_source(duplicate_writer=True), encoding="utf-8")
    state_path = work / "intake-state.json"
    state = json.loads(state_path.read_text())
    state["source_set_qualification"]["qualification"]["outcomes"][0][
        "projection_sha256"
    ] = module._sha(source.read_bytes())
    state_path.write_text(json.dumps(state) + "\n")

    with pytest.raises(ValueError, match="duplicate V3 writer"):
        module.publish(work, source)

    assert not (work / "formula-map/reporting-v3-column-index.json").exists()
    assert len((work / "formula-map/ledger.jsonl").read_text().splitlines()) == 1
