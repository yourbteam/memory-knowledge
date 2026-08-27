from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "skills"
    / "experiment-machinery"
    / "scripts"
    / "development_probe_manifest.py"
)


def _module() -> object:
    spec = importlib.util.spec_from_file_location("development_probe_manifest", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _probe(probe_id: str, artifact: str) -> dict:
    return {
        "id": probe_id,
        "goal": f"Build {probe_id} as an independently testable capability.",
        "practical_value": f"The atomic implementation gains {probe_id} behavior.",
        "work_type": "code",
        "work_type_reason": "The boundary is deterministic.",
        "allowed_paths": [f"skills/{probe_id}"],
        "inputs": [{"case_id": "works"}, {"case_id": "refuses"}],
        "approaches": [
            {
                "id": "indexed",
                "hypothesis": "Indexed validation will satisfy the probe.",
                "implementation": "Build identity indexes before validation.",
                "predicted_tradeoff": "Uses a small amount of temporary memory.",
            },
            {
                "id": "ordered",
                "hypothesis": "Ordered validation will satisfy the probe.",
                "implementation": "Walk declarations in their recorded order.",
                "predicted_tradeoff": "Performs repeated small scans.",
            },
        ],
        "proof": {
            "success_criterion": "The captured success case produces the probe outcome.",
            "failure_criterion": "The captured failure case is refused clearly.",
        },
        "evaluation": {
            "metrics": [
                {"name": "practical-outcome", "direction": "maximize"},
                {"name": "implementation-cost", "direction": "minimize"},
            ],
            "across_cases": [
                {"name": "practical-outcome", "method": "sum"},
                {"name": "implementation-cost", "method": "mean"},
            ],
        },
        "winner_output": {
            "artifact": artifact,
            "description": f"The promotion candidate produced by {probe_id}.",
        },
    }


def manifest() -> dict:
    probes = [
        _probe("source-reader", "source-reader-candidate"),
        _probe("ledger-writer", "ledger-writer-candidate"),
    ]
    return {
        "schema_version": 1,
        "atomic_step": {
            "id": "read-and-record-source",
            "outcome": "One immutable source becomes a complete readable ledger entry.",
            "practical_value": "The operator can trace every readable unit to source evidence.",
            "stopping_condition": "The composed operator path accepts the source or records every gap.",
            "captured_cases": [
                {
                    "id": "works",
                    "source": "captured/works.json",
                    "sha256": "1" * 64,
                    "kind": "success",
                    "expected_outcome": "The complete source is preserved and readable.",
                },
                {
                    "id": "refuses",
                    "source": "captured/refuses.json",
                    "sha256": "2" * 64,
                    "kind": "failure",
                    "expected_outcome": "The unreadable unit remains an explicit gap.",
                },
                {
                    "id": "also-works",
                    "source": "captured/also-works.json",
                    "sha256": "3" * 64,
                    "kind": "success",
                    "expected_outcome": "The second readable source is also preserved.",
                },
            ],
        },
        "mini_probes": probes,
        "composition": {
            "consumes": [
                {"probe_id": probe["id"], "artifact": probe["winner_output"]["artifact"]}
                for probe in probes
            ],
            "assembly_contract": "Link both promotion candidates behind one operator entrypoint.",
            "final_validation": {
                "operator_path": "development-probe validate manifest.json",
                "case_ids": ["works", "refuses", "also-works"],
                "success_criterion": "The composed path produces the approved atomic outcome.",
                "failure_criterion": "The composed path preserves the explicit failure outcome.",
            },
        },
    }


def test_complete_parallel_manifest_is_accepted_without_mutating_input() -> None:
    module = _module()
    value = manifest()
    before = copy.deepcopy(value)

    accepted = module.validate_manifest(value)

    assert accepted == before
    assert accepted is not value
    assert value == before


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update({"unexpected": True}), "unexpected"),
        (
            lambda value: (
                value["mini_probes"].clear(),
                value["composition"]["consumes"].clear(),
            ),
            "at least one",
        ),
        (
            lambda value: value["atomic_step"]["captured_cases"].append(
                copy.deepcopy(value["atomic_step"]["captured_cases"][0])
            ),
            "unique id",
        ),
        (lambda value: value["mini_probes"][0]["approaches"].pop(), "approach"),
        (
            lambda value: value["mini_probes"][0]["evaluation"]["metrics"].clear(),
            "metric",
        ),
        (
            lambda value: value["mini_probes"][0]["evaluation"]["metrics"].append(
                {"name": "practical-outcome", "direction": "minimize"}
            ),
            "unique",
        ),
        (
            lambda value: value["mini_probes"][0]["evaluation"]["across_cases"][0].update(
                {"method": "median"}
            ),
            "sum",
        ),
        (
            lambda value: value["mini_probes"][0]["evaluation"]["across_cases"].pop(),
            "same ordered metrics",
        ),
        (
            lambda value: value["mini_probes"][0]["approaches"][1].update(
                {"implementation": "Build identity indexes before validation."}
            ),
            "different implementation",
        ),
        (
            lambda value: value["mini_probes"][0].update({"allowed_paths": []}),
            "declare what this mini-probe may change",
        ),
        (
            lambda value: value["mini_probes"][0].update(
                {"allowed_paths": ["../outside"]}
            ),
            "repository-relative",
        ),
        (
            lambda value: value["mini_probes"][0].update(
                {"allowed_paths": ["skills/source-reader", "skills/source-reader"]}
            ),
            "duplicates",
        ),
        (
            lambda value: value["mini_probes"][0]["inputs"].append(
                {"from_probe": "ledger-writer", "artifact": "ledger-writer-candidate"}
            ),
            "captured cases only",
        ),
        (
            lambda value: value["composition"]["consumes"].pop(),
            "ledger-writer",
        ),
        (
            lambda value: value["composition"]["consumes"][0].update(
                {"artifact": "wrong-candidate"}
            ),
            "wrong-candidate",
        ),
        (
            lambda value: value["composition"]["final_validation"].update(
                {"case_ids": ["works"]}
            ),
            "exact captured case order",
        ),
        (
            lambda value: value["composition"]["final_validation"].update(
                {"case_ids": ["works", "refuses"]}
            ),
            "exact captured case order",
        ),
        (
            lambda value: value["composition"]["final_validation"].update(
                {"case_ids": ["works", "also-works", "refuses"]}
            ),
            "exact captured case order",
        ),
        (
            lambda value: value["composition"]["final_validation"].update(
                {"case_ids": ["works", "refuses", "refuses"]}
            ),
            "exact captured case order",
        ),
        (
            lambda value: value["composition"]["final_validation"].update(
                {"case_ids": ["works", "refuses", "unknown"]}
            ),
            "exact captured case order",
        ),
    ],
)
def test_incomplete_or_sequential_manifest_is_refused_with_actionable_error(
    mutate,
    message: str,
) -> None:
    module = _module()
    value = manifest()
    mutate(value)

    with pytest.raises(module.ManifestError, match=message):
        module.validate_manifest(value)


def test_cli_validates_one_manifest_and_reports_parallel_probe_count(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest()), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "atomic_step_id": "read-and-record-source",
        "mini_probe_count": 2,
        "parallel": True,
        "status": "valid",
    }
