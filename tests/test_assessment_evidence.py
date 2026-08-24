from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/assessment_evidence.py"


def _module():
    spec = importlib.util.spec_from_file_location("assessment_evidence", SCRIPT)
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
    roles = ("criterion", "observation", "context")
    obligations_body = {
        "schema_version": 1,
        "artifact_type": "info-intake-assessment-obligations",
        "status": "obligations-ready",
        "unit_count": 1,
        "obligation_count": 3,
        "units": [{
            "sequence": 1,
            "unit_id": "unit-1",
            "label": "Revenue",
            "subject": {"identity": "field-1", "kind": "metric", "evidence_sha256": "a" * 64},
            "obligations": [
                {
                    "id": f"unit-1:{role}",
                    "role": role,
                    "required": True,
                    "question": f"question {role}",
                    "status": "unfulfilled",
                    "evidence_refs": [],
                }
                for role in roles
            ],
        }],
    }
    obligations_body["artifact_sha256"] = module._digest(module._canonical(obligations_body))
    obligations = _write(tmp_path / "obligations.json", obligations_body)
    facts = _write(tmp_path / "facts.json", {"criterion": {"formula": "A-B"}, "observed": 10})
    code = tmp_path / "code.txt"
    code.write_text("one\nactual = 10\nthree\n", encoding="utf-8")
    plan_body = {
        "schema_version": 1,
        "obligations": module._artifact_ref(obligations, obligations.read_bytes(), obligations_body),
        "evidence": [
            {
                "evidence_id": "evidence-criterion",
                "obligation_id": "unit-1:criterion",
                "source": {"path": str(facts), "sha256": module._digest(facts.read_bytes())},
                "locator": {"kind": "json-pointer", "pointer": "/criterion"},
            },
            {
                "evidence_id": "evidence-observation",
                "obligation_id": "unit-1:observation",
                "source": {"path": str(code), "sha256": module._digest(code.read_bytes())},
                "locator": {"kind": "line-range", "start": 2, "end": 2},
            },
        ],
    }
    plan = _write(tmp_path / "plan.json", plan_body)
    return module, obligations, plan, facts, code


def test_freshly_binds_json_and_text_and_reports_missing(tmp_path: Path) -> None:
    module, obligations, plan, _facts, _code = _fixture(tmp_path)

    result = module.compile_evidence(obligations, plan, tmp_path / "evidence.json")

    assert result["bound_count"] == 2
    assert result["unbound_count"] == 1
    assert result["unbound_obligation_ids"] == ["unit-1:context"]
    rows = result["units"][0]["obligations"]
    assert rows[0]["evidence"][0]["representation"] == {"formula": "A-B"}
    assert rows[1]["evidence"][0]["representation"] == "actual = 10"
    assert rows[0]["status"] == "bound"
    assert rows[2]["status"] == "unbound"
    assert module.verify(tmp_path / "evidence.json") == result


def test_refuses_unknown_duplicate_and_changed_sources(tmp_path: Path) -> None:
    module, obligations, plan, _facts, _code = _fixture(tmp_path)
    value = json.loads(plan.read_text())
    value["evidence"][0]["obligation_id"] = "ghost"
    value["evidence"][1]["evidence_id"] = value["evidence"][0]["evidence_id"]
    value["evidence"][1]["source"]["sha256"] = "f" * 64
    _write(plan, value)

    with pytest.raises(module.AssessmentEvidenceError) as caught:
        module.compile_evidence(obligations, plan, tmp_path / "evidence.json")

    message = str(caught.value)
    assert "declared obligation id" in message
    assert "unique non-empty id" in message


def test_verify_refuses_source_change_and_output_overwrite(tmp_path: Path) -> None:
    module, obligations, plan, facts, _code = _fixture(tmp_path)
    output = tmp_path / "evidence.json"
    facts_bytes = facts.read_bytes()
    first = module.compile_evidence(obligations, plan, output)
    assert module.compile_evidence(obligations, plan, output) == first

    facts.write_text("{}\n", encoding="utf-8")
    with pytest.raises(module.AssessmentEvidenceError, match="source digest"):
        module.verify(output)

    facts.write_bytes(facts_bytes)
    output.write_text("{}\n", encoding="utf-8")
    with pytest.raises(module.AssessmentEvidenceError, match="different bytes"):
        module.compile_evidence(obligations, plan, output)


def test_relationship_packet_adapter_binds_all_roles_for_each_claim(tmp_path: Path) -> None:
    module, obligations, _plan, _facts, _code = _fixture(tmp_path)
    units = _write(tmp_path / "units.json", {
        "units": [{"id": "unit-1", "source_claim_ids": ["claim-1", "claim-2"]}]
    })
    packets = _write(tmp_path / "packets.json", {
        "packets": [
            {"claim": {"id": "claim-1", "target": {"content": "one"}}},
            {"claim": {"id": "claim-2", "target": {"content": "two"}}},
        ]
    })

    result = module.relationship_packet_plan(obligations, units, packets)

    assert len(result["evidence"]) == 6
    assert [row["obligation_id"] for row in result["evidence"]] == [
        "unit-1:criterion", "unit-1:observation", "unit-1:context",
        "unit-1:criterion", "unit-1:observation", "unit-1:context",
    ]
    assert result["evidence"][1]["locator"]["pointer"] == "/packets/0/claim/target"
