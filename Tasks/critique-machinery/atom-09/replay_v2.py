#!/usr/bin/env python3
"""Replay the frozen Claude v2 seat responses without launching a model."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = ROOT / "Tasks/critique-machinery/atom-09"
FROZEN = ATOM / "frozen-red"
WORK = ATOM / "operator-validation/run"
RESULT = ATOM / "operator-validation/result.json"
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
PAGE = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap/page.md"
STATE = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap/state.json"
PAYLOAD_KEY = "context.up.cd_s_002.tactical_roadmap"
NO_REFERENCE = "UP supplies no roadmap-shaped benchmark"
FROZEN_HASHES = {
    "unit-manifest.json": "72df294a2ab750b82eca2af02b9ffc6febff40dd430c775c6f6e0480387d841d",
    "matrix.json": "64b28589ebee1a0e25be0a4af92debdc6e98f222059141035be9cb1bf4fc67e7",
    "sources.json": "f952d9342ffaa25e9151b45cc7242b2dc1f8fd0134d331e2aba567683f792b6e",
    "read-run.log": "3b5c65de6bda41dc479ffd1824f8f5d09314beb5a9590f544f01cc97387cfabb",
}


def load_module():
    spec = importlib.util.spec_from_file_location("critique_machinery", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_module()
    observed_hashes = {name: module.digest_file(FROZEN / name) for name in FROZEN_HASHES}
    if observed_hashes != FROZEN_HASHES:
        raise RuntimeError(f"frozen red evidence changed: {observed_hashes}")
    if module.digest_file(PAGE) != "10113814ebeb9d5f503fd1cffce8ac80e44f148ab13a495d3c989075160a7bbc":
        raise RuntimeError("committed replay page no longer matches the recorded v2 page")
    if module.digest_file(STATE) != "5ca9724769a49cbefdf3d847f8e18d13fe61f7930b5fd4dda1834514c908193c":
        raise RuntimeError("committed replay state no longer matches the recorded v2 state")

    registry = json.loads((FROZEN / "sources.json").read_text(encoding="utf-8"))["sources"]
    source_specs = [(item["source_id"], STATE, item["key"]) for item in registry]
    if WORK.exists():
        shutil.rmtree(WORK)
    _, manifest = module.open_run(
        PAGE,
        STATE,
        PAYLOAD_KEY,
        WORK,
        no_reference=NO_REFERENCE,
        upstream_sources=source_specs,
    )
    frozen_manifest = json.loads((FROZEN / "unit-manifest.json").read_text(encoding="utf-8"))
    if [item["unit_id"] for item in manifest["units"]] != [item["unit_id"] for item in frozen_manifest["units"]]:
        raise RuntimeError("fresh run did not reproduce the frozen unit identities")

    units = {item["unit_id"]: item for item in manifest["units"]}
    claims_by_cell = {}
    responses = sorted((FROZEN / "reader-evidence").glob("batch-*/reader-*/reader-response.json"))
    for response_path in responses:
        unit_id = response_path.parents[1].name.removeprefix("batch-")
        seat = response_path.parent.name
        lines = units[unit_id]["text"].splitlines()
        response = json.loads(response_path.read_text(encoding="utf-8"))
        for item in response["judgments"]:
            claim = dict(item)
            claim["quote"] = "\n".join(lines[item["start_line"] - 1 : item["end_line"]])
            cell_id = f"{unit_id}::{item['lens']}"
            claims_by_cell.setdefault(cell_id, {})[seat] = claim
    if len(responses) != 50 or sum(len(claims) for claims in claims_by_cell.values()) != 300:
        raise RuntimeError("captured replay does not contain exactly 50 responses and 300 seat judgments")

    for cell_id, claims in claims_by_cell.items():
        module.record_cell_readers(WORK, cell_id, claims)
    status = module.matrix_status(WORK)
    owner = module.owner_queue(WORK)
    matrix = json.loads((WORK / "matrix.json").read_text(encoding="utf-8"))
    owner_cells = [cell for cell in matrix["cells"] if cell.get("status") == "unresolved"]
    result = {
        "schema_version": 1,
        "source_run": "claude-seat-s12-btm-v2",
        "new_model_calls": 0,
        "captured_response_files": len(responses),
        "captured_seat_judgments": sum(len(claims) for claims in claims_by_cell.values()),
        "status": status,
        "owner_queue_count": owner["open_count"],
        "owner_questions_have_both_seats": all(
            set(cell["readers"]) == set(module.READER_SEATS) for cell in owner_cells
        ),
        "all_applicable_cells_recorded": status["recorded_count"] == 150,
        "frozen_hashes": observed_hashes,
        "matrix_sha256": module.digest_file(WORK / "matrix.json"),
        "sources_sha256": module.digest_file(WORK / "sources.json"),
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_bytes(module.canonical(result))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
