#!/usr/bin/env python3
"""Exercise candidate lifecycle telemetry through real nested runner paths."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def load_tests(root: Path):
    path = root / "tests/test_development_probe_candidate.py"
    spec = importlib.util.spec_from_file_location("candidate_telemetry_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load real-path fixture {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def records(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run_probe(root: Path, work: Path) -> dict[str, int]:
    module = load_tests(root)
    valid = work / "valid"
    valid.mkdir(parents=True)
    valid_passed = True
    try:
        module.test_two_real_bundles_run_as_one_experiment_and_undeclared_case_is_refused(valid)
    except (AssertionError, OSError, RuntimeError):
        valid_passed = False
    variant_feeds = list((valid / "run" / "variants").glob("*/telemetry.jsonl"))
    variant_records = [records(path) for path in variant_feeds]
    ordered = bool(variant_records) and all(
        [item.get("sequence") for item in feed] == list(range(1, len(feed) + 1))
        and feed[0].get("event") == "candidate_started"
        and feed[-1].get("event") == "candidate_finished"
        for feed in variant_records
        if feed
    )
    meaningful = bool(variant_records) and all(
        any(item.get("event") in {"operator_work", "operator_decision"} for item in feed)
        for feed in variant_records
    )

    invalid_results = []
    invalid_function = getattr(
        module,
        "test_candidate_refuses_invalid_operator_telemetry_with_actionable_terminal_event",
        None,
    )
    if invalid_function is not None:
        mutations = [
            (
                lambda source: source.replace(
                    'int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1"))',
                    "2",
                ),
                "require 1",
            ),
            (
                lambda source: source.replace(
                    '"event": "work_completed"',
                    '"event": "unknown"',
                ),
                "unsupported",
            ),
        ]
        for index, (mutation, diagnostic) in enumerate(mutations, start=1):
            invalid = work / f"invalid-{index}"
            invalid.mkdir()
            passed = True
            try:
                invalid_function(invalid, mutation, diagnostic)
            except (AssertionError, OSError, RuntimeError):
                passed = False
            invalid_results.append((passed, records(invalid / "telemetry.jsonl")))
    invalid_ineligible = len(invalid_results) == 2 and all(item[0] for item in invalid_results)
    actionable = invalid_ineligible and all(
        any(
            event.get("event") == "operator_failed"
            and isinstance(event.get("correction"), str)
            and bool(event["correction"].strip())
            for event in feed
        )
        for _, feed in invalid_results
    )

    whole = work / "whole"
    whole.mkdir()
    whole_passed = True
    try:
        module.test_whole_process_runs_from_probe_experiments_to_passed_verdict(whole)
    except (AssertionError, OSError, RuntimeError):
        whole_passed = False
    top = records(whole / "development-probe-output" / "telemetry.jsonl")
    unified = whole_passed and bool(top) and [item.get("sequence") for item in top] == list(
        range(1, len(top) + 1)
    )
    watcher_identity = unified and any(
        item.get("event") == "operator_work"
        and all(item.get(name) for name in ("atomic_step_id", "probe_id", "case_id", "approach_id"))
        and item.get("state") == "working"
        for item in top
    )
    return {
        "ordered-lifecycle": int(valid_passed and ordered),
        "meaningful-work": int(valid_passed and meaningful),
        "invalid-ineligible": int(invalid_ineligible),
        "actionable-failure": int(actionable),
        "unified-feed": int(unified),
        "watcher-identity": int(watcher_identity),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    work = Path(os.environ["EXPERIMENT_WORK_DIR"])
    frozen = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    case = json.loads(frozen.read_text(encoding="utf-8"))["case"]
    metrics = run_probe(root, work / "probe")
    telemetry = {
        "schema_version": 1,
        "sequence": int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1")),
        "event": "work_completed",
        "recorded_at": datetime.now(UTC).isoformat(),
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "message": "Executed valid, invalid, and complete-run telemetry paths.",
        "evidence_sha256": hashlib.sha256(frozen.read_bytes()).hexdigest(),
        "observations": {"case": case, "metrics": metrics},
    }
    with Path(os.environ["EXPERIMENT_TELEMETRY_PATH"]).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(telemetry, sort_keys=True) + "\n")
    Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
                "status": "completed",
                "outcome": {"case": case},
                "metrics": metrics,
                "error": None,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
