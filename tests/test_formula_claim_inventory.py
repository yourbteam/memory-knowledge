from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/info-intake-machinery/scripts"


def _module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _projection() -> dict[str, object]:
    return {
        "schema_version": 1,
        "elements": [
            {
                "id": "element-000001",
                "status": "readable",
                "kind": "annotation callout",
                "content": "Column AF",
                "region": [1, 2, 3, 4],
            },
            {
                "id": "element-000002",
                "status": "readable",
                "kind": "metric",
                "content": "$8,100",
                "region": [5, 6, 7, 8],
            },
        ],
        "relationships": [
            {
                "id": "relationship-000001",
                "status": "readable",
                "kind": "formula annotation",
                "description": "Column AF supplies the displayed metric.",
                "from_id": "element-000001",
                "to_id": "element-000002",
            }
        ],
    }


def _work(tmp_path: Path) -> tuple[Path, Path]:
    start = _module("start_intake")
    work = tmp_path / "intake"
    projections = work / "projections"
    projections.mkdir(parents=True)
    projection_path = projections / "source-000003-v6.json"
    projection_path.write_text(
        json.dumps(_projection(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    projection_sha256 = start._digest_bytes(projection_path.read_bytes())
    opening = start._ledger_entry(
        1,
        "effective_first_layer_terminal_recorded",
        {
            "intake_id": "intake-test",
            "disposition": "first_layer_complete",
        },
        None,
    )
    (work / "ledger.jsonl").write_bytes(start._canonical(opening) + b"\n")
    state = {
        "intake_id": "intake-test",
        "status": "first_layer_complete",
        "ledger_tail_sha256": opening["entry_sha256"],
        "effective_first_layer_terminal": {
            "entry_sha256": opening["entry_sha256"],
        },
        "source_set_qualification": {
            "qualification": {
                "source_count": 1,
                "qualification": "readable_source_set_complete",
                "outcomes": [
                    {
                        "source_id": "source-000003",
                        "projection_id": "projection-source-000003-v6",
                        "projection_sha256": projection_sha256,
                        "method": "visual_spatial_v1",
                        "qualification": "readable_projection_complete",
                        "gaps": [],
                    }
                ],
            }
        },
    }
    (work / "intake-state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return work, projection_path


def test_real_inventory_is_exact_evidence_bound_and_idempotent(tmp_path: Path) -> None:
    module = _module("formula_claim_inventory")
    work, projection = _work(tmp_path)

    first = module.publish(work, projection)
    repeated = module.publish(work, projection)

    assert first == repeated
    assert first["claim_count"] == 1
    inventory = json.loads((work / "formula-map/claim-inventory.json").read_text())
    claim = inventory["claims"][0]
    assert claim["id"] == "claim-000001"
    assert claim["relationship_id"] == "relationship-000001"
    assert len(claim["relationship_sha256"]) == 64
    assert len(claim["origin"]["element_sha256"]) == 64
    assert len(claim["target"]["element_sha256"]) == 64
    assert claim["status"] == "pending_code_assessment"
    ledger = json.loads((work / "formula-map/ledger.jsonl").read_text())
    assert ledger["event"] == "formula_claim_inventory_recorded"
    assert ledger["claim_count"] == 1


def test_duplicate_relationship_is_refused_before_publication(tmp_path: Path) -> None:
    module = _module("formula_claim_inventory")
    work, projection = _work(tmp_path)
    value = json.loads(projection.read_text())
    value["relationships"].append(dict(value["relationships"][0]))
    projection.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    state_path = work / "intake-state.json"
    state = json.loads(state_path.read_text())
    state["source_set_qualification"]["qualification"]["outcomes"][0][
        "projection_sha256"
    ] = module._digest_bytes(projection.read_bytes())
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match="duplicate relationship id"):
        module.publish(work, projection)

    assert not (work / "formula-map/claim-inventory.json").exists()
    assert not (work / "formula-map/ledger.jsonl").exists()


def test_projection_must_match_qualified_immutable_bytes(tmp_path: Path) -> None:
    module = _module("formula_claim_inventory")
    work, projection = _work(tmp_path)
    projection.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="bytes differ from qualified evidence"):
        module.publish(work, projection)

    assert not (work / "formula-map").exists()
