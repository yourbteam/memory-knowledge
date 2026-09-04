#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
ATOM = ROOT / "Tasks/critique-machinery/atom-11"
FROZEN = ATOM / "frozen-red"
OUTPUT = ATOM / "experiment"
TARGET_CELL = "u-018-55cd0f78::upstream-trace"
OWNER_WORDS = "Kamen: approved in bulk 2026-09-04"
FROZEN_HASHES = {
    "run/matrix.json": "82c6372ac39295ef34d21063b1639a0812ffd22cc1646556be636873677dfb16",
    "run/sources.json": "923e8914d6aa8c17ebc7a34508c27b6be7f43bf716c4ee5e8bfbebf56b1b0e52",
    "state.json": "0cd36c228a79e9bca61ac3504f24ab21743f2c71bc1a81e224c8cdbc8c5c03a3",
    "assessment.md": "4148f27d76e36b7614388c5a56a3797c3f29306e7cab2611003e2ae2396d5c8d",
    "run/owner-rulings.json": "be0a832de5345b25f4bae744797379e1ff9425c67caf0a36b099a722eb331eb7",
    "page-v3-located.txt": "52e236ccbba18fab847e39b809a9b25d5a5d7943e37d28fb84ac5f543d61081b",
    "page.md": "590ec561b472cecf118160c176527d9eeb687313961efce0ca0e94217d633023",
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_hashes() -> dict[str, str]:
    return {name: digest(FROZEN / name) for name in FROZEN_HASHES}


def writable_copy(name: str) -> Path:
    destination = OUTPUT / "runs" / name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(FROZEN / "run", destination)
    for path in [destination, *destination.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    return destination


def reset_owner_rulings(module, work: Path) -> None:
    matrix_path = work / "matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    for cell in matrix["cells"]:
        if cell.get("outcome") != "owner-resolved":
            continue
        for key in ("owner_ruling", "owner_ruling_history", "resolved_verdict"):
            cell.pop(key, None)
        cell["outcome"] = module._reader_outcome(cell)
        cell["status"] = "judged" if cell["outcome"].startswith("agreement-") else "unresolved"
    matrix_path.write_bytes(module.canonical(matrix))
    (work / "owner-rulings.json").unlink(missing_ok=True)
    module.owner_queue(work)


def raw_claims(matrix: dict, cell_id: str) -> dict:
    cell = next(item for item in matrix["cells"] if item["cell_id"] == cell_id)
    return {
        seat: {
            "verdict": reader.get("verdict"),
            "quote": reader.get("quote"),
            "source_id": reader.get("source_id"),
            "source_quote": reader.get("source_quote"),
            **({"intake": copy.deepcopy(reader["intake"])} if reader.get("intake") else {}),
        }
        for seat, reader in cell["readers"].items()
    }


def reset_cell(module, work: Path, cell_id: str) -> dict:
    manifest = json.loads((work / "unit-manifest.json").read_text(encoding="utf-8"))
    matrix_path = work / "matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    claims = raw_claims(matrix, cell_id)
    baseline = next(cell for cell in module.build_matrix(manifest)["cells"] if cell["cell_id"] == cell_id)
    index = next(index for index, cell in enumerate(matrix["cells"]) if cell["cell_id"] == cell_id)
    matrix["cells"][index] = baseline
    matrix_path.write_bytes(module.canonical(matrix))
    return claims


def main() -> int:
    before = frozen_hashes()
    if before != FROZEN_HASHES:
        raise RuntimeError(f"frozen v3 evidence changed before experiment: {before}")
    candidate = load("critique_atom_11_candidate", OUTPUT / "candidate/critique.py")
    baseline = load("critique_atom_11_baseline", ROOT / "skills/critique-machinery/scripts/critique.py")

    baseline_work = writable_copy("baseline-short-line")
    baseline_claims = reset_cell(baseline, baseline_work, TARGET_CELL)
    baseline_cell = baseline.record_cell_readers(baseline_work, TARGET_CELL, baseline_claims)

    accepted_work = writable_copy("candidate-short-line")
    accepted_claims = reset_cell(candidate, accepted_work, TARGET_CELL)
    accepted_cell = candidate.record_cell_readers(accepted_work, TARGET_CELL, accepted_claims)

    altered_work = writable_copy("candidate-altered-line")
    altered_claims = reset_cell(candidate, altered_work, TARGET_CELL)
    altered_claims["reader-2"]["source_quote"] = "Always-on after launch!"
    altered_cell = candidate.record_cell_readers(altered_work, TARGET_CELL, altered_claims)
    altered_queue = candidate.owner_queue(altered_work)
    document_refusal = ""
    try:
        candidate.reporting_route(altered_work, "document")
    except candidate.Refusal as exc:
        document_refusal = str(exc)

    state_path, payload_key, source_specs, derivation = candidate.derive_open_inputs(
        FROZEN / "state.json", "tactical_roadmap"
    )
    derived_root = OUTPUT / "runs/derived-open-root"
    if derived_root.exists():
        shutil.rmtree(derived_root)
    (derived_root / ".git").mkdir(parents=True)
    derived_work = derived_root / "Tasks/run"
    candidate.open_run(
        FROZEN / "page.md", state_path, payload_key, derived_work,
        no_reference="UP supplies no roadmap-shaped benchmark", upstream_sources=source_specs,
    )
    expected_sources = [
        {key: item[key] for key in ("source_id", "key", "value_sha256")}
        for item in json.loads((FROZEN / "run/sources.json").read_text(encoding="utf-8"))["sources"]
    ]

    bulk_work = writable_copy("candidate-bulk")
    reset_owner_rulings(candidate, bulk_work)
    before_bulk = {
        name: digest(bulk_work / name) if (bulk_work / name).is_file() else None
        for name in ("matrix.json", "owner-rulings.json", "owner-queue.json")
    }
    bulk_result = candidate.rule_bulk(bulk_work, FROZEN / "assessment.md", OWNER_WORDS)
    actual_rulings = json.loads((bulk_work / "owner-rulings.json").read_text(encoding="utf-8"))["rulings"]
    expected_rulings = json.loads((FROZEN / "run/owner-rulings.json").read_text(encoding="utf-8"))["rulings"]
    choice_parity = [item["choice"] for item in actual_rulings] == [item["choice"] for item in expected_rulings]
    cell_parity = [item["cell_id"] for item in actual_rulings] == [item["cell_id"] for item in expected_rulings]
    marker_prefix = OWNER_WORDS + candidate.BULK_RULING_MARKER
    marker_parity = all(item["because"].startswith(marker_prefix) for item in actual_rulings)

    located_work = writable_copy("candidate-located")
    reset_owner_rulings(candidate, located_work)
    located_output = candidate.located(located_work, "disputed")
    expected_lines = (FROZEN / "page-v3-located.txt").read_text(encoding="utf-8").splitlines()[3:]
    located_equal = located_output.splitlines() == expected_lines
    (OUTPUT / "located-output.txt").write_text(located_output, encoding="utf-8")

    after = frozen_hashes()
    result = {
        "schema_version": 1,
        "status": "completed",
        "new_model_calls": 0,
        "frozen_hashes_before": before,
        "frozen_hashes_after": after,
        "producer_grounding": {
            "baseline": {
                "status": baseline_cell["status"],
                "outcome": baseline_cell["outcome"],
                "owner_queue_count": baseline.matrix_status(baseline_work)["owner_queue_count"],
            },
            "candidate_exact": {
                "status": accepted_cell["status"],
                "outcome": accepted_cell["outcome"],
                "source_quote": accepted_cell["readers"]["reader-2"]["upstream_trace"]["quote"],
            },
            "candidate_altered": {
                "status": altered_cell["status"],
                "outcome": altered_cell["outcome"],
                "queue_cell": altered_queue["question"]["cell_id"],
                "refusal": altered_cell["recording_refusal"]["failures"],
                "document_refusal": document_refusal,
            },
            "instruction_refusal_phrase": candidate.TRACE_GROUNDING_RULE,
        },
        "derived_open": {
            "derivation": derivation,
            "expected_sources": expected_sources,
            "exact_source_parity": derivation["sources"] == expected_sources,
            "opened_sources_sha256": digest(derived_work / "sources.json"),
        },
        "bulk_ruling": {
            "result": bulk_result,
            "before": before_bulk,
            "choice_parity": choice_parity,
            "cell_parity": cell_parity,
            "marker_parity": marker_parity,
            "actual_count": len(actual_rulings),
        },
        "located": {
            "line_for_line": located_equal,
            "cell_count": sum(line.startswith("### ") for line in located_output.splitlines()),
            "output_sha256": digest(OUTPUT / "located-output.txt"),
            "expected_body_sha256": hashlib.sha256(("\n".join(expected_lines) + "\n").encode()).hexdigest(),
        },
        "baseline_commands_absent": {
            name: not hasattr(baseline, name)
            for name in ("derive_open_inputs", "rule_bulk", "located")
        },
    }
    checks = [
        before == after,
        baseline_cell["outcome"] == "recording-refusal",
        baseline.matrix_status(baseline_work)["owner_queue_count"] == 0,
        accepted_cell["outcome"] == "agreement-defect",
        accepted_cell["readers"]["reader-2"]["upstream_trace"]["quote"] == "Always-on after launch.",
        altered_cell["outcome"] == "claim-without-grounded-words",
        altered_queue["question"]["cell_id"] == TARGET_CELL,
        "owner questions remain open" in document_refusal,
        derivation["sources"] == expected_sources,
        choice_parity and cell_parity and marker_parity and len(actual_rulings) == 16,
        located_equal,
        result["located"]["cell_count"] == 20,
        all(result["baseline_commands_absent"].values()),
    ]
    result["verdict"] = "passed" if all(checks) else "failed"
    target = OUTPUT / "probe-result.json"
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if result["verdict"] != "passed":
        raise RuntimeError(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps({"verdict": result["verdict"], "checks": len(checks)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
