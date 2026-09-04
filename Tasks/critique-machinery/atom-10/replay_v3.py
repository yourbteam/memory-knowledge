#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / "Tasks/critique-machinery/atom-10/frozen-red"
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
OUT = ROOT / "Tasks/critique-machinery/atom-10/operator-validation"
PAGE = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap/page.md"
STATE = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap/state.json"
KEY = "context.up.cd_s_002.tactical_roadmap"
EXPECTED = {
    "matrix.json": "a4355e11f7b535e94f4f39a3d89fa310663b67e15ee86bfbf0aebb080e7a96de",
    "unit-manifest.json": "6b31f4e2efb1504051199703a9f2d1bc83dfc7653e84f388d26b9ed6b97099f1",
    "sources.json": "f952d9342ffaa25e9151b45cc7242b2dc1f8fd0134d331e2aba567683f792b6e",
    "read-run.log": "a712dda0ce18905f4760cd1b15d49cc94f60cc43793b47695d5e45f76f4cc45c",
}


def load_module():
    spec = importlib.util.spec_from_file_location("critique_atom_10_replay", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def captured_result(path: Path) -> str:
    results = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") == "result":
            results.append(event.get("result"))
    if len(results) != 1 or not isinstance(results[0], str):
        raise RuntimeError(f"{path} contains {len(results)} string result events; expected exactly one")
    return results[0]


def main() -> int:
    module = load_module()
    before = {name: module.digest_file(FROZEN / name) for name in EXPECTED}
    if before != EXPECTED:
        raise RuntimeError(f"frozen v3 evidence changed: {before}")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / ".git").mkdir(parents=True)
    work = OUT / "Tasks/run"
    registry = json.loads((FROZEN / "sources.json").read_text(encoding="utf-8"))["sources"]
    _, manifest = module.open_run(
        PAGE,
        STATE,
        KEY,
        work,
        no_reference="UP supplies no roadmap-shaped benchmark",
        upstream_sources=[(item["source_id"], STATE, item["key"]) for item in registry],
    )
    sources = module.upstream_sources_for_run(work, manifest)
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    matrix = json.loads((work / "matrix.json").read_text(encoding="utf-8"))
    lenses_by_unit = {
        unit_id: [
            cell["lens"]
            for cell in matrix["cells"]
            if cell["unit_id"] == unit_id and cell["status"] != "not-applicable"
        ]
        for unit_id in units
    }
    outcomes = []
    claims_by_cell = {}
    responses = sorted(FROZEN.glob("reader-evidence/batch-*/reader-*/reader.stdout.txt"))
    for response_path in responses:
        unit_id = response_path.parents[1].name.removeprefix("batch-")
        batch_id = response_path.parents[1].name
        seat = response_path.parent.name
        lenses = lenses_by_unit[unit_id]
        attempt_root = work / "reader-evidence" / batch_id / seat / "attempt-001"
        attempt_root.mkdir(parents=True)
        shutil.copy2(response_path, attempt_root / "reader.stdout.txt")
        shutil.copy2(response_path.with_name("reader.stderr.txt"), attempt_root / "reader.stderr.txt")
        schema = module.reader_schema(lenses)
        (attempt_root / "reader-schema.json").write_bytes(module.canonical(schema))
        raw_result = captured_result(response_path)
        (attempt_root / "reader.reply.txt").write_text(raw_result, encoding="utf-8")
        result = module.classify_reader_reply(
            raw_result,
            schema,
            lenses,
            batch_id=batch_id,
            seat=seat,
            attempt=1,
            evidence_path=str(attempt_root),
        )
        (attempt_root / "reader-intake.json").write_bytes(module.canonical(result["intake"]))
        if result["outcome"] == "valid":
            (attempt_root / "reader-response.json").write_bytes(
                module.canonical({"judgments": result["judgments"]})
            )
        result = module.ground_reader_result(result, units[unit_id], sources)
        outcomes.append(result["intake"])
        claims = module._claims_from_reader_result(result, lenses)
        for lens in lenses:
            claims_by_cell.setdefault(f"{unit_id}::{lens}", {})[seat] = claims[lens]
    for cell_id, claims in claims_by_cell.items():
        module.record_cell_readers(work, cell_id, claims)
    status = module.matrix_status(work)
    result = {
        "schema_version": 1,
        "route": "captured-reply-code-interview-replay",
        "captured_response_files": len(responses),
        "new_model_calls": 0,
        "reply_outcomes": {
            name: sum(item["outcome"] == name for item in outcomes)
            for name in module.READER_REPLY_OUTCOMES
        },
        "recorded_count": status["recorded_count"],
        "unjudged_count": status["unjudged_count"],
        "half_recorded_count": status["half_recorded_count"],
        "retryable_failed_seat_count": status["retryable_failed_seat_count"],
        "retry_exhausted_seat_count": status["retry_exhausted_seat_count"],
        "owner_queue_count": status["owner_queue_count"],
        "failed_seats": status["failed_seats"],
        "frozen_hashes_before": before,
        "frozen_hashes_after": {name: module.digest_file(FROZEN / name) for name in EXPECTED},
        "matrix_sha256": module.digest_file(work / "matrix.json"),
    }
    expected = {
        "captured_response_files": 50,
        "new_model_calls": 0,
        "reply_outcomes": {
            "valid": 47, "malformed": 3, "empty": 0, "timeout": 0, "nonzero-exit": 0,
        },
        "recorded_count": 150,
        "unjudged_count": 0,
        "half_recorded_count": 0,
        "retryable_failed_seat_count": 3,
        "retry_exhausted_seat_count": 0,
    }
    for key, value in expected.items():
        if result[key] != value:
            raise RuntimeError(f"{key}: expected {value!r}, observed {result[key]!r}")
    if result["frozen_hashes_before"] != result["frozen_hashes_after"]:
        raise RuntimeError("frozen evidence changed during replay")
    (OUT / "pre-retry-result.json").write_bytes(module.canonical(result))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
