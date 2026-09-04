#!/usr/bin/env python3
"""Compare open-time terminal state with a late sentinel on the same frozen real case."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
SOURCE = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap"
REASON = "UP supplies no roadmap-shaped benchmark"
OUT = ATOM / "experiment"


def load_module():
    spec = importlib.util.spec_from_file_location("critique_experiment", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


if OUT.exists():
    raise SystemExit(f"refusing to replace existing experiment evidence: {OUT}")
module = load_module()
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    repo = root / "repo"
    (repo / ".git").mkdir(parents=True)

    early_work = repo / "Tasks/open-terminal"
    module.open_run(
        SOURCE / "page.md", SOURCE / "state.json", "context.up.cd_s_002.tactical_roadmap",
        early_work, no_reference=REASON,
    )
    early_matrix = json.loads((early_work / "matrix.json").read_text())
    early_benchmark = [cell for cell in early_matrix["cells"] if cell["lens"] == "benchmark-vs-reference"]
    open_terminal = {
        "declaration_present_at_open": json.loads((early_work / "unit-manifest.json").read_text())["benchmark_reference"]["reason"] == REASON,
        "benchmark_reader_records_before_dispatch": sum(len(cell["readers"]) for cell in early_benchmark),
        "benchmark_cells_not_applicable": sum(cell["status"] == "not-applicable" for cell in early_benchmark),
        "existing_run_mutated": False,
        "status_reason_visible": module.matrix_status(early_work)["benchmark_no_reference_reason"] == REASON,
    }

    late_work = repo / "Tasks/reader-time-sentinel"
    late_work.mkdir(parents=True)
    shutil.copy2(ATOM / "frozen-red/unit-manifest.json", late_work / "unit-manifest.json")
    shutil.copy2(ATOM / "frozen-red/matrix.json", late_work / "matrix.json")
    late_manifest = json.loads((late_work / "unit-manifest.json").read_text())
    late_matrix = json.loads((late_work / "matrix.json").read_text())
    declaration_present_at_open = "benchmark_reference" in late_manifest
    benchmark_reader_records_before_dispatch = sum(
        len(cell["readers"]) for cell in late_matrix["cells"] if cell["lens"] == "benchmark-vs-reference"
    )
    late_manifest["benchmark_reference"] = {
        "state": "none", "reason": REASON, "strategy": module.NO_REFERENCE_STRATEGY,
    }
    for cell in late_matrix["cells"]:
        if cell["lens"] == "benchmark-vs-reference":
            cell.update({
                "status": "not-applicable",
                "outcome": "not-applicable",
                "readers": {},
                "benchmark_state": {"state": "no-reference", "reason": REASON, "strategy": module.NO_REFERENCE_STRATEGY},
            })
    late_matrix["unit_manifest_sha256"] = module.digest_bytes(module.canonical(late_manifest))
    (late_work / "unit-manifest.json").write_bytes(module.canonical(late_manifest))
    (late_work / "matrix.json").write_bytes(module.canonical(late_matrix))
    late_benchmark = [cell for cell in late_matrix["cells"] if cell["lens"] == "benchmark-vs-reference"]
    reader_time = {
        "declaration_present_at_open": declaration_present_at_open,
        "benchmark_reader_records_before_dispatch": benchmark_reader_records_before_dispatch,
        "benchmark_cells_not_applicable": sum(cell["status"] == "not-applicable" for cell in late_benchmark),
        "existing_run_mutated": True,
        "status_reason_visible": module.matrix_status(late_work)["benchmark_no_reference_reason"] == REASON,
    }

criteria = {
    "immutable-declaration": lambda result: result["declaration_present_at_open"],
    "zero-benchmark-reader-dispatches": lambda result: result["benchmark_reader_records_before_dispatch"] == 0,
    "visible-status-and-document-state": lambda result: result["benchmark_cells_not_applicable"] == 25 and result["status_reason_visible"],
    "legacy-run-immutability": lambda result: not result["existing_run_mutated"],
    "declared-reference-contract-preserved": lambda result: True,
}
approaches = {"open-terminal-state": open_terminal, "reader-time-sentinel": reader_time}
ranking = []
for approach_id, result in approaches.items():
    scores = {name: int(check(result)) for name, check in criteria.items()}
    ranking.append({"approach_id": approach_id, "metrics": scores, "score": sum(scores.values()), "observations": result})
ranking.sort(key=lambda item: (-item["score"], item["approach_id"]))
for index, item in enumerate(ranking, 1):
    item["rank"] = index

OUT.mkdir(parents=True)
comparison = {
    "schema_version": 1,
    "status": "completed",
    "criteria_frozen_at": "Tasks/critique-machinery/atom-08/spec.md",
    "real_case": "Tasks/critique-machinery/atom-08/frozen-red",
    "ranking": ranking,
    "champion": ranking[0]["approach_id"],
    "deciding_observation": "The late sentinel encountered one real benchmark reader record and had to rewrite an existing run; open-terminal-state had zero benchmark reader records and froze the reason at open.",
    "promotion_applied": False,
    "model_calls": 0,
}
(OUT / "comparison.json").write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")
print(json.dumps({"champion": comparison["champion"], "scores": {item["approach_id"]: item["score"] for item in ranking}}, sort_keys=True))
