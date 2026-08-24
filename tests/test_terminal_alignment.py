import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/system-alignment-assessment-machinery/scripts"


def module():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("terminal_alignment", SCRIPTS / "terminal_alignment.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules["terminal_alignment"] = value
    spec.loader.exec_module(value)
    return value


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path):
    mod = module()
    units = {
        "schema_version": 1,
        "artifact_type": "system-alignment-assessment-units",
        "status": "units-admitted",
        "unit_count": 2,
        "source_artifact": {},
        "units": [
            {"unit_id": "unit-1", "sequence": 1, "label": "Revenue", "subject": {"identity": "a"}, "intent_statements": []},
            {"unit_id": "unit-2", "sequence": 2, "label": "Refresh", "subject": {"identity": "b"}, "intent_statements": []},
        ],
    }
    inventory = {"schema_version": 1, "artifact_type": "system-alignment-path-inventory", "status": "path-inventory-ready", "units_package": {}, "paths": [], "comparison": {}}
    actual = {"schema_version": 1, "artifact_type": "system-alignment-implementation-trace", "status": "trace-complete", "lane_role": "actual", "path_inventory": {}, "traces": []}
    reference = {"schema_version": 1, "artifact_type": "system-alignment-implementation-trace", "status": "trace-complete", "lane_role": "reference", "path_inventory": {}, "traces": []}
    mappings = {
        "schema_version": 1,
        "artifact_type": "system-alignment-unit-mappings",
        "status": "mapping-interview-complete",
        "catalog_artifact_sha256": "catalog",
        "answers": [
            {"question_id": "map:unit-1", "answer": "mapped", "actual_expression": "net payout", "reference_expression": "Column AF", "actual_evidence_ids": ["a1"], "reference_evidence_ids": ["r1"]},
            {"question_id": "map:unit-2", "answer": "not-applicable", "actual_expression": "", "reference_expression": "", "actual_evidence_ids": [], "reference_evidence_ids": []},
        ],
    }
    comparisons = {
        "schema_version": 1,
        "artifact_type": "system-alignment-comparison-results",
        "status": "comparison-complete",
        "catalog_artifact_sha256": "comparison-catalog",
        "results": [
            {"question_id": "compare:unit-1", "verdict": "aligned", "measure": {"kind": "formula-equivalence", "actual": "net payout", "expected": "Column AF"}, "reason": "same", "evidence_ids": ["a1", "r1"]}
        ],
        "dispositions": [{"unit_id": "unit-2", "mapping_answer": "not-applicable", "reason": "control"}],
    }
    values = {
        "alignment_units": units,
        "path_inventory": inventory,
        "actual_trace": actual,
        "reference_trace": reference,
        "mappings": mappings,
        "comparison_results": comparisons,
    }
    inputs = {}
    for name, value in values.items():
        value["artifact_sha256"] = mod.bind.__globals__["artifact_digest"](value)
        path = tmp_path / f"{name}.json"
        write(path, value)
        inputs[name] = {"path": str(path), "sha256": sha(path), "artifact_sha256": value["artifact_sha256"]}
    spec_path = tmp_path / "spec.json"
    write(spec_path, {"schema_version": 1, "inputs": inputs})
    return mod, spec_path, inputs


def test_real_contract_round_trip(tmp_path):
    mod, spec_path, _ = fixture(tmp_path)
    value = mod.create(spec_path)
    assert value["summary"] == {"total_units": 2, "aligned": 1, "misaligned": 0, "cannot-assess": 0, "not-applicable": 1}
    assert [item["unit_id"] for item in value["alignment"]] == ["unit-1", "unit-2"]
    output = tmp_path / "terminal.json"
    mod.write_once(value, output)
    assert mod.verify(output) == value


def test_changed_input_refuses_fresh_verification(tmp_path):
    mod, spec_path, inputs = fixture(tmp_path)
    value = mod.create(spec_path)
    output = tmp_path / "terminal.json"
    mod.write_once(value, output)
    Path(inputs["alignment_units"]["path"]).write_text("{}\n")
    with pytest.raises(mod.InputBindingError, match="bytes changed"):
        mod.verify(output)


def test_missing_comparison_result_refuses_package(tmp_path):
    mod, spec_path, inputs = fixture(tmp_path)
    result_path = Path(inputs["comparison_results"]["path"])
    value = json.loads(result_path.read_text())
    value["results"] = []
    value["artifact_sha256"] = mod.bind.__globals__["artifact_digest"](value)
    write(result_path, value)
    spec = json.loads(spec_path.read_text())
    spec["inputs"]["comparison_results"] = {"path": str(result_path), "sha256": sha(result_path), "artifact_sha256": value["artifact_sha256"]}
    write(spec_path, spec)
    with pytest.raises(mod.TerminalPackageError, match="partition every alignment unit"):
        mod.create(spec_path)


def test_write_once_refuses_overwrite(tmp_path):
    mod, spec_path, _ = fixture(tmp_path)
    output = tmp_path / "terminal.json"
    mod.write_once(mod.create(spec_path), output)
    with pytest.raises(mod.TerminalAlignmentError, match="already exists"):
        mod.write_once(mod.create(spec_path), output)
