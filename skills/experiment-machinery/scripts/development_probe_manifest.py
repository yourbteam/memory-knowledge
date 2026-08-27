#!/usr/bin/env python3
"""Validate one atomic implementation manifest composed from parallel mini-probes."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

CONTRACT = 1
IDENTITY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """Raised when a development-probe manifest cannot drive the complete process."""


def _object(value: object, path: str, fields: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(
            f"{path} is {type(value).__name__}; provide an object with fields {sorted(fields)}"
        )
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    errors = [
        *(f"{path}.{name} is missing; add it" for name in missing),
        *(f"{path}.{name} is unexpected; remove it" for name in extra),
    ]
    if errors:
        raise ValueError("; ".join(errors))
    return value


def _list(value: object, path: str) -> list[Any]:
    if type(value) is not list:
        raise ValueError(f"{path} is {type(value).__name__}; provide a list")
    return value


def _text(value: object, path: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{path} is {value!r}; provide a nonempty string")
    return value


def _identifier(value: object, path: str) -> str:
    text = _text(value, path)
    if not IDENTITY.fullmatch(text):
        raise ValueError(
            f"{path} is {text!r}; use lowercase letters, digits, and hyphens"
        )
    return text


def _relative_path(value: object, path: str) -> str:
    text = _text(value, path)
    relative = PurePosixPath(text)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != text
        or text in {"", "."}
    ):
        raise ValueError(
            f"{path} is {text!r}; provide a safe repository-relative POSIX path"
        )
    return text.rstrip("/")


def _enum(value: object, path: str, choices: set[str]) -> str:
    text = _text(value, path)
    if text not in choices:
        raise ValueError(f"{path} is {text!r}; choose one of {sorted(choices)}")
    return text


def _check_case(value: object, path: str) -> None:
    case = _object(
        value,
        path,
        {"id", "source", "sha256", "kind", "expected_outcome"},
    )
    _identifier(case["id"], f"{path}.id")
    _text(case["source"], f"{path}.source")
    digest = _text(case["sha256"], f"{path}.sha256")
    if not SHA256.fullmatch(digest):
        raise ValueError(
            f"{path}.sha256 is {digest!r}; provide 64 lowercase hexadecimal characters"
        )
    _enum(case["kind"], f"{path}.kind", {"success", "failure"})
    _text(case["expected_outcome"], f"{path}.expected_outcome")


def _check_probe_shape(value: object, path: str) -> None:
    probe = _object(
        value,
        path,
        {
            "id",
            "goal",
            "practical_value",
            "work_type",
            "work_type_reason",
            "allowed_paths",
            "inputs",
            "approaches",
            "proof",
            "evaluation",
            "winner_output",
        },
    )
    _identifier(probe["id"], f"{path}.id")
    for name in ("goal", "practical_value", "work_type_reason"):
        _text(probe[name], f"{path}.{name}")
    _enum(probe["work_type"], f"{path}.work_type", {"code", "model", "hybrid"})
    allowed_paths = _list(probe["allowed_paths"], f"{path}.allowed_paths")
    if not allowed_paths:
        raise ValueError(
            f"{path}.allowed_paths is empty; declare what this mini-probe may change"
        )
    normalized_paths = [
        _relative_path(value, f"{path}.allowed_paths[{index}]")
        for index, value in enumerate(allowed_paths)
    ]
    if len(set(normalized_paths)) != len(normalized_paths):
        raise ValueError(
            f"{path}.allowed_paths contains duplicates; keep every boundary once"
        )
    for index, input_value in enumerate(_list(probe["inputs"], f"{path}.inputs")):
        item_path = f"{path}.inputs[{index}]"
        if isinstance(input_value, dict) and set(input_value) != {"case_id"}:
            unexpected = sorted(set(input_value) - {"case_id"})
            raise ValueError(
                f"{item_path} contains {unexpected}; mini-probe inputs may reference captured cases only"
            )
        item = _object(input_value, item_path, {"case_id"})
        _identifier(item["case_id"], f"{item_path}.case_id")
    for index, approach_value in enumerate(
        _list(probe["approaches"], f"{path}.approaches")
    ):
        item_path = f"{path}.approaches[{index}]"
        item = _object(
            approach_value,
            item_path,
            {"id", "hypothesis", "implementation", "predicted_tradeoff"},
        )
        _identifier(item["id"], f"{item_path}.id")
        for name in ("hypothesis", "implementation", "predicted_tradeoff"):
            _text(item[name], f"{item_path}.{name}")
    proof = _object(
        probe["proof"],
        f"{path}.proof",
        {"success_criterion", "failure_criterion"},
    )
    _text(proof["success_criterion"], f"{path}.proof.success_criterion")
    _text(proof["failure_criterion"], f"{path}.proof.failure_criterion")
    evaluation = _object(
        probe["evaluation"],
        f"{path}.evaluation",
        {"metrics", "across_cases"},
    )
    metrics = _list(evaluation["metrics"], f"{path}.evaluation.metrics")
    if not metrics:
        raise ValueError(
            f"{path}.evaluation.metrics is empty; provide at least one ordered winner-selection metric"
        )
    for index, metric_value in enumerate(metrics):
        metric_path = f"{path}.evaluation.metrics[{index}]"
        metric = _object(metric_value, metric_path, {"name", "direction"})
        _identifier(metric["name"], f"{metric_path}.name")
        _enum(metric["direction"], f"{metric_path}.direction", {"maximize", "minimize"})
    across_cases = _list(
        evaluation["across_cases"], f"{path}.evaluation.across_cases"
    )
    aggregation_names: list[str] = []
    for index, aggregation_value in enumerate(across_cases):
        aggregation_path = f"{path}.evaluation.across_cases[{index}]"
        aggregation = _object(
            aggregation_value, aggregation_path, {"name", "method"}
        )
        aggregation_names.append(
            _identifier(aggregation["name"], f"{aggregation_path}.name")
        )
        _enum(
            aggregation["method"],
            f"{aggregation_path}.method",
            {"sum", "mean", "worst"},
        )
    metric_names = [metric["name"] for metric in metrics]
    if len(set(metric_names)) != len(metric_names):
        raise ValueError(
            f"{path}.evaluation.metrics names are not unique; give every metric one name"
        )
    if aggregation_names != metric_names:
        raise ValueError(
            f"{path}.evaluation.across_cases names are {aggregation_names!r}; "
            f"use the same ordered metrics {metric_names!r}"
        )
    output = _object(
        probe["winner_output"],
        f"{path}.winner_output",
        {"artifact", "description"},
    )
    _text(output["artifact"], f"{path}.winner_output.artifact")
    _text(output["description"], f"{path}.winner_output.description")


def _check_shape(manifest: object) -> None:
    root = _object(
        manifest,
        "manifest",
        {"schema_version", "atomic_step", "mini_probes", "composition"},
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != CONTRACT:
        raise ValueError(
            f"manifest.schema_version is {root['schema_version']!r}; use integer {CONTRACT}"
        )
    step = _object(
        root["atomic_step"],
        "atomic_step",
        {"id", "outcome", "practical_value", "stopping_condition", "captured_cases"},
    )
    _identifier(step["id"], "atomic_step.id")
    for name in ("outcome", "practical_value", "stopping_condition"):
        _text(step[name], f"atomic_step.{name}")
    for index, case in enumerate(_list(step["captured_cases"], "atomic_step.captured_cases")):
        _check_case(case, f"atomic_step.captured_cases[{index}]")
    for index, probe in enumerate(_list(root["mini_probes"], "mini_probes")):
        _check_probe_shape(probe, f"mini_probes[{index}]")
    composition = _object(
        root["composition"],
        "composition",
        {"consumes", "assembly_contract", "final_validation"},
    )
    for index, value in enumerate(_list(composition["consumes"], "composition.consumes")):
        item_path = f"composition.consumes[{index}]"
        item = _object(value, item_path, {"probe_id", "artifact"})
        _identifier(item["probe_id"], f"{item_path}.probe_id")
        _text(item["artifact"], f"{item_path}.artifact")
    _text(composition["assembly_contract"], "composition.assembly_contract")
    final = _object(
        composition["final_validation"],
        "composition.final_validation",
        {"operator_path", "case_ids", "success_criterion", "failure_criterion"},
    )
    _text(final["operator_path"], "composition.final_validation.operator_path")
    for index, case_id in enumerate(
        _list(final["case_ids"], "composition.final_validation.case_ids")
    ):
        _identifier(case_id, f"composition.final_validation.case_ids[{index}]")
    _text(final["success_criterion"], "composition.final_validation.success_criterion")
    _text(final["failure_criterion"], "composition.final_validation.failure_criterion")


def _normalized_implementation(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _check_experiment_contract(manifest: dict[str, Any]) -> None:
    case_ids: set[str] = set()
    for index, case in enumerate(manifest["atomic_step"]["captured_cases"]):
        case_id = case["id"]
        if case_id in case_ids:
            raise ValueError(
                f"duplicate captured case {case_id!r} at index {index}; give every captured case a unique id"
            )
        case_ids.add(case_id)
    probes = manifest["mini_probes"]
    if not probes:
        raise ValueError(
            "mini_probes is empty; decompose the atomic implementation into at least one independently provable capability"
        )
    probe_ids: set[str] = set()
    winner_artifacts: set[str] = set()
    for probe_index, probe in enumerate(probes):
        probe_id = probe["id"]
        if probe_id in probe_ids:
            raise ValueError(
                f"mini_probes[{probe_index}] repeats {probe_id!r}; give every probe a unique id"
            )
        probe_ids.add(probe_id)
        winner_artifact = probe["winner_output"]["artifact"]
        if winner_artifact in winner_artifacts:
            raise ValueError(
                f"probe {probe_id!r} repeats winner artifact {winner_artifact!r}; give every winner a unique artifact"
            )
        winner_artifacts.add(winner_artifact)
        approaches = probe["approaches"]
        if len(approaches) < 2:
            raise ValueError(
                f"probe {probe_id!r} has {len(approaches)} approach(es); provide at least two competing approaches"
            )
        approach_ids: set[str] = set()
        implementations: set[str] = set()
        for approach_index, approach in enumerate(approaches):
            approach_id = approach["id"]
            if approach_id in approach_ids:
                raise ValueError(
                    f"probe {probe_id!r} approach[{approach_index}] repeats {approach_id!r}; give every approach a unique id"
                )
            approach_ids.add(approach_id)
            normalized = _normalized_implementation(approach["implementation"])
            if normalized in implementations:
                raise ValueError(
                    f"probe {probe_id!r} approach {approach_id!r} repeats an existing implementation; describe a materially different implementation"
                )
            implementations.add(normalized)
        metric_names: set[str] = set()
        for metric_index, metric in enumerate(probe["evaluation"]["metrics"]):
            metric_name = metric["name"]
            if metric_name in metric_names:
                raise ValueError(
                    f"probe {probe_id!r} evaluation metric[{metric_index}] repeats {metric_name!r}; give every winner-selection metric a unique name"
                )
            metric_names.add(metric_name)


def _check_parallel_boundary(manifest: dict[str, Any]) -> None:
    known_cases = {case["id"] for case in manifest["atomic_step"]["captured_cases"]}
    for probe in manifest["mini_probes"]:
        probe_id = probe["id"]
        inputs = probe["inputs"]
        if not inputs:
            raise ValueError(
                f"mini-probe {probe_id!r} has no inputs; give it captured atomic cases so it can run independently"
            )
        seen: set[str] = set()
        for index, item in enumerate(inputs):
            case_id = item["case_id"]
            if case_id not in known_cases:
                raise ValueError(
                    f"mini-probe {probe_id!r} input {index} references unknown captured case {case_id!r}; use a captured case id"
                )
            if case_id in seen:
                raise ValueError(
                    f"mini-probe {probe_id!r} has duplicate input {case_id!r}; reference each captured case once"
                )
            seen.add(case_id)


def _check_composition(manifest: dict[str, Any]) -> None:
    probes = manifest["mini_probes"]
    composition = manifest["composition"]
    consumes = composition["consumes"]
    seen: set[str] = set()
    by_probe = {item["probe_id"]: item for item in consumes}
    for index, item in enumerate(consumes):
        probe_id = item["probe_id"]
        if probe_id in seen:
            raise ValueError(
                f"composition entry {index} duplicates probe {probe_id!r}; consume each winner once"
            )
        seen.add(probe_id)
    declared = {probe["id"] for probe in probes}
    for item in consumes:
        if item["probe_id"] not in declared:
            raise ValueError(
                f"composition names unknown probe {item['probe_id']!r}; use a declared probe id"
            )
    for probe in probes:
        probe_id = probe["id"]
        if probe_id not in by_probe:
            raise ValueError(
                f"composition is missing probe {probe_id!r}; consume its winning artifact"
            )
        expected = probe["winner_output"]["artifact"]
        actual = by_probe[probe_id]["artifact"]
        if actual != expected:
            raise ValueError(
                f"composition probe {probe_id!r} uses artifact {actual!r}; use winning artifact {expected!r}"
            )
    final = composition["final_validation"]
    declared_case_ids = [
        case["id"] for case in manifest["atomic_step"]["captured_cases"]
    ]
    if final["case_ids"] != declared_case_ids:
        raise ValueError(
            f"final_validation case_ids are {final['case_ids']!r}; "
            f"require exact captured case order {declared_case_ids!r}"
        )


def validate_manifest(value: object) -> dict[str, Any]:
    """Return a defensive copy only when the complete parallel contract is valid."""

    try:
        _check_shape(value)
        assert isinstance(value, dict)
        _check_experiment_contract(value)
        _check_parallel_boundary(value)
        _check_composition(value)
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        raise ManifestError(str(error)) from None
    return copy.deepcopy(value)


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"manifest {path} is unavailable or invalid JSON: {error}") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate one development-probe manifest")
    validate.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        accepted = validate_manifest(_load(args.manifest))
    except ManifestError as error:
        print(f"Development-probe manifest refused: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "atomic_step_id": accepted["atomic_step"]["id"],
                "mini_probe_count": len(accepted["mini_probes"]),
                "parallel": True,
                "status": "valid",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
