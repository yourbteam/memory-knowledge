from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/system-alignment-assessment-machinery/scripts/alignment_units.py"


def _module():
    spec = importlib.util.spec_from_file_location("alignment_units", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["alignment_units"] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path):
    source = tmp_path / "intake-units.json"
    source_value = {
        "units": [{
            "id": "unit-000001",
            "label": "$8,100",
            "subject": {"identity": "element-000005", "kind": "dashboard metric", "evidence_sha256": "subject-sha"},
            "claims": [{"id": "claim-000001", "text": "Column AF supplies the value.", "evidence_sha256": "claim-sha"}],
        }],
    }
    _write_json(source, source_value)
    spec = {
        "schema_version": 1,
        "source_artifact": {"path": str(source), "sha256": _sha(source)},
        "units": [{
            "unit_id": "unit-000001",
            "sequence": 1,
            "label": "$8,100",
            "subject": {"identity": "element-000005", "kind": "dashboard metric", "evidence_sha256": "subject-sha"},
            "intent_statements": [{"statement_id": "claim-000001", "text": "Column AF supplies the value.", "evidence_sha256": "claim-sha"}],
        }],
    }
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, spec)
    return _module(), source, spec, spec_path


def test_create_and_verify_admits_grounded_units_without_results(tmp_path: Path) -> None:
    module, _, _, spec_path = _fixture(tmp_path)
    package = module.create(spec_path)
    output = tmp_path / "units.json"
    module._write_once(package, output)

    assert module.verify(output) == package
    assert package["unit_count"] == 1
    assert package["units"][0]["subject"]["identity"] == "element-000005"
    assert not module.FORBIDDEN_RESULT_FIELDS.intersection(package["units"][0])


def test_duplicate_unit_identity_refuses(tmp_path: Path) -> None:
    module, _, spec, spec_path = _fixture(tmp_path)
    duplicate = deepcopy(spec["units"][0])
    duplicate["sequence"] = 2
    spec["units"].append(duplicate)
    _write_json(spec_path, spec)

    with pytest.raises(module.AlignmentUnitError, match="unit_id is duplicated"):
        module.create(spec_path)


def test_reordered_sequence_refuses(tmp_path: Path) -> None:
    module, _, spec, spec_path = _fixture(tmp_path)
    spec["units"][0]["sequence"] = 2
    _write_json(spec_path, spec)

    with pytest.raises(module.AlignmentUnitError, match="sequence must be 1"):
        module.create(spec_path)


def test_altered_statement_refuses_unbound_evidence(tmp_path: Path) -> None:
    module, _, spec, spec_path = _fixture(tmp_path)
    spec["units"][0]["intent_statements"][0]["text"] = "Altered statement"
    _write_json(spec_path, spec)

    with pytest.raises(module.AlignmentUnitError, match="intent evidence is unbound"):
        module.create(spec_path)


def test_changed_source_bytes_refuse_reverification(tmp_path: Path) -> None:
    module, source, _, spec_path = _fixture(tmp_path)
    package = module.create(spec_path)
    output = tmp_path / "units.json"
    module._write_once(package, output)
    source.write_text('{"changed":true}\n', encoding="utf-8")

    with pytest.raises(module.AlignmentUnitError, match="source_artifact bytes changed"):
        module.verify(output)


def test_write_once_preserves_existing_package(tmp_path: Path) -> None:
    module, _, _, spec_path = _fixture(tmp_path)
    package = module.create(spec_path)
    output = tmp_path / "units.json"
    module._write_once(package, output)

    with pytest.raises(module.AlignmentUnitError, match="already exists"):
        module._write_once(package, output)
