from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/assessment_units.py"


def _module():
    spec = importlib.util.spec_from_file_location("assessment_units", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _fixture(tmp_path: Path):
    module = _module()
    packets_value = {"packets": []}
    claims = []
    for number, target in ((1, "target-a"), (2, "target-a"), (3, "target-b")):
        packet = {
            "claim": {
                "id": f"claim-{number}",
                "target": {
                    "element_id": target,
                    "element_sha256": ("a" if target == "target-a" else "b") * 64,
                    "content": "Alpha" if target == "target-a" else "Beta",
                    "kind": "field",
                },
            },
            "packet_sha256": str(number) * 64,
        }
        packets_value["packets"].append(packet)
        claims.append({
            "claim_id": f"claim-{number}",
            "statement": f"statement {number}",
            "packet_sha256": str(number) * 64,
            "verdict": "confirmed",
        })
    intake = _write(tmp_path / "intake.json", {"status":"terminal","claims":claims,"intake_id":"one"})
    intake_sha = module._digest(intake.read_bytes())
    charter = _write(tmp_path / "charter.json", {
        "status":"charter-ready",
        "intake":{"sha256":intake_sha},
        "artifact_sha256":"c"*64,
    })
    packets = _write(tmp_path / "packets.json", packets_value)
    plan_value = module.relationship_target_plan(packets)
    plan = _write(tmp_path / "plan.json", plan_value)
    return module, intake, charter, packets, plan


def test_relationship_adapter_groups_shared_target_and_compiler_covers_all_claims(tmp_path: Path) -> None:
    module, intake, charter, packets, plan = _fixture(tmp_path)

    result = module.compile_units(intake, charter, packets, plan, tmp_path / "units.json")

    assert result["unit_count"] == 2
    assert result["claim_count"] == 3
    assert result["units"][0]["source_claim_ids"] == ["claim-1", "claim-2"]
    assert result["units"][1]["source_claim_ids"] == ["claim-3"]
    assert module.verify(tmp_path / "units.json") == result


def test_compiler_refuses_missing_duplicate_and_unknown_claims_together(tmp_path: Path) -> None:
    module, intake, charter, packets, plan = _fixture(tmp_path)
    value = json.loads(plan.read_text())
    value["units"][0]["source_claim_ids"] = ["claim-1", "claim-1", "ghost"]
    value["units"].pop()
    _write(plan, value)

    with pytest.raises(module.AssessmentUnitsError) as caught:
        module.compile_units(intake, charter, packets, plan, tmp_path / "units.json")

    message = str(caught.value)
    assert "missing ['claim-2', 'claim-3']" in message
    assert "duplicated ['claim-1']" in message
    assert "unknown ['ghost']" in message


def test_compile_restores_terminal_claim_order(tmp_path: Path) -> None:
    module, intake, charter, packets, plan = _fixture(tmp_path)
    value = json.loads(plan.read_text())
    value["units"].reverse()
    _write(plan, value)

    result = module.compile_units(intake, charter, packets, plan, tmp_path / "units.json")

    assert [unit["label"] for unit in result["units"]] == ["Alpha", "Beta"]
