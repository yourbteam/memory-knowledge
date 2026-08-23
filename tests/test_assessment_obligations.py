from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/assessment_obligations.py"


def _module():
    spec = importlib.util.spec_from_file_location("assessment_obligations", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _units(tmp_path: Path, module, ids: tuple[str, ...] = ("unit-a", "unit-b")) -> Path:
    rows = [
        {
            "sequence": sequence,
            "id": unit_id,
            "label": unit_id.upper(),
            "subject": {
                "identity": f"subject-{unit_id}",
                "kind": "field",
                "evidence_sha256": str(sequence) * 64,
            },
        }
        for sequence, unit_id in enumerate(ids, start=1)
    ]
    body = {
        "schema_version": 1,
        "artifact_type": "info-intake-assessment-units",
        "status": "units-ready",
        "unit_count": len(rows),
        "units": rows,
    }
    body["artifact_sha256"] = module._digest(module._canonical(body))
    return _write(tmp_path / "units.json", body)


def test_compiles_exact_required_roles_for_every_unit(tmp_path: Path) -> None:
    module = _module()
    units = _units(tmp_path, module)

    result = module.compile_obligations(units, tmp_path / "obligations.json")

    assert result["unit_count"] == 2
    assert result["obligation_count"] == 6
    assert [
        obligation["role"]
        for row in result["units"]
        for obligation in row["obligations"]
    ] == ["criterion", "observation", "context"] * 2
    assert all(
        obligation["status"] == "unfulfilled"
        and obligation["evidence_refs"] == []
        for row in result["units"]
        for obligation in row["obligations"]
    )
    assert module.verify(tmp_path / "obligations.json") == result


def test_compiler_derives_changed_unit_order_instead_of_copying_a_plan(tmp_path: Path) -> None:
    module = _module()
    units = _units(tmp_path, module, ("unit-new", "unit-a", "unit-b"))

    result = module.compile_obligations(units, tmp_path / "obligations.json")

    assert [row["unit_id"] for row in result["units"]] == [
        "unit-new",
        "unit-a",
        "unit-b",
    ]
    assert result["obligation_count"] == 9


def test_verify_refuses_source_or_role_drift(tmp_path: Path) -> None:
    module = _module()
    units = _units(tmp_path, module)
    output = tmp_path / "obligations.json"
    module.compile_obligations(units, output)

    source = json.loads(units.read_text())
    source["units"][0]["label"] = "changed"
    _write(units, source)
    with pytest.raises(module.AssessmentObligationsError, match="source changed"):
        module.verify(output)

    units = _units(tmp_path, module)
    output.unlink()
    module.compile_obligations(units, output)
    artifact = json.loads(output.read_text())
    artifact["units"][0]["obligations"].pop()
    artifact["obligation_count"] -= 1
    body = {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    artifact["artifact_sha256"] = module._digest(module._canonical(body))
    _write(output, artifact)
    with pytest.raises(module.AssessmentObligationsError, match="count changed"):
        module.verify(output)


def test_compile_is_create_only_and_idempotent(tmp_path: Path) -> None:
    module = _module()
    units = _units(tmp_path, module)
    output = tmp_path / "obligations.json"

    first = module.compile_obligations(units, output)
    assert module.compile_obligations(units, output) == first
    output.write_text("{}\n", encoding="utf-8")
    with pytest.raises(module.AssessmentObligationsError, match="different bytes"):
        module.compile_obligations(units, output)
