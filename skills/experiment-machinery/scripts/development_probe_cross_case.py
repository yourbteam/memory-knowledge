#!/usr/bin/env python3
"""Run one development mini-probe across every case it declares."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from development_probe_manifest import ManifestError, validate_manifest

CONTRACT = 1
MAX_CASE_WORKERS = 4


class CrossCaseError(RuntimeError):
    """The cross-case experiment cannot safely continue."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path, label: str, stage: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CrossCaseError(stage, f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise CrossCaseError(stage, f"{label} must contain one JSON object")
    return value


def _exact(value: object, label: str, fields: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise CrossCaseError(
            "validate-request",
            f"{label} is {type(value).__name__}; provide an object with fields {sorted(fields)}",
        )
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise CrossCaseError(
            "validate-request",
            f"{label} has missing fields {missing} and unexpected fields {extra}; "
            "add missing fields and remove unexpected fields",
        )
    return value


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise CrossCaseError("validate-request", f"{label} must be a nonempty identity")
    return value


def _resolve(value: object, base: Path, label: str) -> Path:
    if type(value) is not str or not value:
        raise CrossCaseError("validate-request", f"{label} must be a nonempty path")
    path = Path(value)
    return (path if path.is_absolute() else base / path).absolute()


def _write_once(path: Path, value: object) -> str:
    payload = _document(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(payload)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value)


def _prepare_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise CrossCaseError(
                "prepare-output", f"output must be a new or empty directory: {path}"
            )
    else:
        path.mkdir(parents=True)


def _find_probe(manifest: dict[str, Any], probe_id: str) -> dict[str, Any]:
    probe = next(
        (item for item in manifest["mini_probes"] if item["id"] == probe_id), None
    )
    if probe is None:
        raise CrossCaseError(
            "validate-request", f"probe_id {probe_id!r} is undeclared in the manifest"
        )
    return probe


def _approach_requests(
    declared: list[dict[str, Any]], values: object, base: Path
) -> list[dict[str, str]]:
    if type(values) is not list:
        raise CrossCaseError("validate-request", "approach_build_requests must be a list")
    accepted: list[dict[str, str]] = []
    for index, value in enumerate(values):
        item = _exact(
            value,
            f"approach_build_requests[{index}]",
            {"approach_id", "request"},
        )
        accepted.append(
            {
                "approach_id": _identifier(
                    item["approach_id"], f"approach_build_requests[{index}].approach_id"
                ),
                "request": str(
                    _resolve(
                        item["request"], base, f"approach_build_requests[{index}].request"
                    )
                ),
            }
        )
    declared_ids = [item["id"] for item in declared]
    actual_ids = [item["approach_id"] for item in accepted]
    duplicates = sorted({item for item in actual_ids if actual_ids.count(item) > 1})
    unknown = sorted(set(actual_ids) - set(declared_ids))
    missing = [item for item in declared_ids if item not in actual_ids]
    failures = []
    if duplicates:
        failures.append(f"duplicate approaches {duplicates!r}")
    if unknown:
        failures.append(f"unknown approaches {unknown!r}")
    if missing:
        failures.append(f"missing approaches {missing!r}")
    if failures:
        raise CrossCaseError(
            "validate-request",
            "; ".join(failures) + "; provide exactly every declared approach once",
        )
    by_id = {item["approach_id"]: item for item in accepted}
    return [by_id[item] for item in declared_ids]


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _run_case(
    launcher: Path,
    case_id: str,
    request_path: Path,
    case_output: Path,
    log_root: Path,
) -> dict[str, Any]:
    completed = _run_command(
        [sys.executable, str(launcher), "run", str(request_path), str(case_output)]
    )
    _write_text(log_root / "stdout.txt", completed.stdout)
    _write_text(log_root / "stderr.txt", completed.stderr)
    status = "completed" if completed.returncode == 0 else "failed"
    result: dict[str, Any] = {
        "case_id": case_id,
        "status": status,
        "returncode": completed.returncode,
        "output": str(case_output),
    }
    if status == "failed":
        result["error"] = completed.stderr.strip() or f"case launcher exited {completed.returncode}"
    return result


def _run_cases(
    output: Path,
    manifest_path: Path,
    probe: dict[str, Any],
    approach_requests: list[dict[str, str]],
    evaluator: object,
) -> list[dict[str, Any]]:
    launcher = Path(__file__).with_name("development_probe_experiment.py")
    case_ids = [item["case_id"] for item in probe["inputs"]]
    requests = output / "case-requests"
    results: dict[int, dict[str, Any]] = {}
    tasks = []
    for index, case_id in enumerate(case_ids):
        request_path = requests / f"{case_id}.json"
        _write_once(
            request_path,
            {
                "schema_version": CONTRACT,
                "development_manifest": str(manifest_path),
                "probe_id": probe["id"],
                "case_id": case_id,
                "approach_build_requests": approach_requests,
                "evaluator": evaluator,
            },
        )
        tasks.append((index, case_id, request_path))
    workers = min(MAX_CASE_WORKERS, len(tasks))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _run_case,
                launcher,
                case_id,
                request_path,
                output / "cases" / case_id,
                output / "case-logs" / case_id,
            ): (index, case_id)
            for index, case_id, request_path in tasks
        }
        for future in as_completed(futures):
            index, case_id = futures[future]
            try:
                results[index] = future.result()
            except (OSError, TypeError, ValueError) as error:
                results[index] = {
                    "case_id": case_id,
                    "status": "failed",
                    "returncode": 2,
                    "output": str(output / "cases" / case_id),
                    "error": str(error),
                }
    ordered = [results[index] for index in range(len(tasks))]
    actual = [item["case_id"] for item in ordered]
    if actual != case_ids or len(set(actual)) != len(case_ids):
        raise CrossCaseError(
            "run-cases", f"case results {actual!r} do not exactly cover {case_ids!r}"
        )
    _write_once(
        output / "case-results.json",
        {
            "schema_version": CONTRACT,
            "results": [
                {
                    **item,
                    "output": str(Path(item["output"]).relative_to(output)),
                }
                for item in ordered
            ],
        },
    )
    failures = [item for item in ordered if item["status"] != "completed"]
    if failures:
        details = "; ".join(
            f"{item['case_id']}: {item.get('error', 'failed')}" for item in failures
        )
        raise CrossCaseError(
            "run-cases", f"one or more declared cases failed; preserved every result: {details}"
        )
    return ordered


def _numeric(value: object, label: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise CrossCaseError("aggregate-results", f"{label} must be one finite number")
    return float(value)


def _case_metrics(
    output: Path,
    probe: dict[str, Any],
    case_ids: list[str],
) -> tuple[dict[str, dict[str, dict[str, float]]], dict[str, dict[str, dict[str, Any]]]]:
    approach_ids = [item["id"] for item in probe["approaches"]]
    metric_names = [item["name"] for item in probe["evaluation"]["metrics"]]
    scores: dict[str, dict[str, dict[str, float]]] = {}
    mappings: dict[str, dict[str, dict[str, Any]]] = {}
    for case_id in case_ids:
        case_output = output / "cases" / case_id
        summary = _load(
            case_output / "experiment" / "summary.json",
            f"case {case_id!r} experiment summary",
            "aggregate-results",
        )
        mapping = _load(
            case_output / "variant-map.json",
            f"case {case_id!r} variant map",
            "aggregate-results",
        )
        by_variant: dict[str, dict[str, Any]] = {}
        for item in mapping.get("variants", []):
            variant_id = item.get("variant_id")
            if type(variant_id) is str:
                by_variant[variant_id] = item
        case_scores: dict[str, dict[str, float]] = {}
        case_mappings: dict[str, dict[str, Any]] = {}
        for row in summary.get("variants", []):
            variant_id = row.get("variant_id")
            item = by_variant.get(variant_id)
            if item is None or row.get("status") != "completed" or not row.get("eligible"):
                continue
            approach_id = item.get("approach_id")
            if approach_id in case_scores:
                raise CrossCaseError(
                    "aggregate-results",
                    f"case {case_id!r} repeats approach {approach_id!r}",
                )
            metrics = row.get("metrics")
            if type(metrics) is not dict or set(metrics) != set(metric_names):
                raise CrossCaseError(
                    "aggregate-results",
                    f"case {case_id!r} approach {approach_id!r} has incomplete metrics; "
                    f"require exactly {metric_names!r}",
                )
            case_scores[approach_id] = {
                name: _numeric(metrics[name], f"{case_id}.{approach_id}.{name}")
                for name in metric_names
            }
            case_mappings[approach_id] = item
        actual_ids = list(case_scores)
        if set(actual_ids) != set(approach_ids) or len(actual_ids) != len(approach_ids):
            raise CrossCaseError(
                "aggregate-results",
                f"case {case_id!r} approaches {actual_ids!r} do not exactly cover {approach_ids!r}",
            )
        scores[case_id] = case_scores
        mappings[case_id] = case_mappings
    return scores, mappings


def _aggregate(
    probe: dict[str, Any],
    case_ids: list[str],
    scores: dict[str, dict[str, dict[str, float]]],
) -> dict[str, Any]:
    metrics = probe["evaluation"]["metrics"]
    methods = {
        item["name"]: item["method"]
        for item in probe["evaluation"]["across_cases"]
    }
    descriptors = [
        {**metric, "method": methods[metric["name"]]} for metric in metrics
    ]
    aggregate: dict[str, dict[str, float]] = {}
    for approach in probe["approaches"]:
        approach_id = approach["id"]
        aggregate[approach_id] = {}
        for metric in descriptors:
            values = [scores[case][approach_id][metric["name"]] for case in case_ids]
            method = metric["method"]
            if method == "sum":
                result = sum(values)
            elif method == "mean":
                result = sum(values) / len(values)
            elif method == "worst":
                result = min(values) if metric["direction"] == "maximize" else max(values)
            else:
                raise CrossCaseError(
                    "aggregate-results",
                    f"aggregation method {method!r} is undeclared; use sum, mean, or worst",
                )
            aggregate[approach_id][metric["name"]] = float(result)

    def rank_key(approach_id: str) -> tuple[object, ...]:
        values: list[object] = []
        for metric in descriptors:
            value = aggregate[approach_id][metric["name"]]
            values.append(-value if metric["direction"] == "maximize" else value)
        values.append(approach_id)
        return tuple(values)

    ordered = sorted(aggregate, key=rank_key)
    return {
        "schema_version": CONTRACT,
        "status": "completed",
        "probe_id": probe["id"],
        "case_ids": case_ids,
        "evaluation": {"metrics": descriptors},
        "champion": ordered[0],
        "ranking": [
            {
                "rank": index,
                "approach_id": approach_id,
                "aggregated_metrics": aggregate[approach_id],
            }
            for index, approach_id in enumerate(ordered, start=1)
        ],
        "promotion_applied": False,
    }


def _fresh_digest(bundle: Path) -> str:
    verifier = Path(__file__).with_name("development_probe_candidate.py")
    completed = _run_command([sys.executable, str(verifier), "verify", str(bundle)])
    if completed.returncode != 0:
        raise CrossCaseError(
            "bind-recommendation",
            completed.stderr.strip() or f"candidate verification exited {completed.returncode}",
        )
    try:
        value = json.loads(completed.stdout)
        digest = value["bundle_sha256"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise CrossCaseError(
            "bind-recommendation", f"candidate verification result is invalid: {error}"
        ) from None
    if type(digest) is not str or len(digest) != 64:
        raise CrossCaseError("bind-recommendation", "verified bundle digest is invalid")
    return digest


def _bind_recommendation(
    output: Path,
    manifest: dict[str, Any],
    probe: dict[str, Any],
    case_ids: list[str],
    aggregate: dict[str, Any],
    mappings: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    champion = aggregate.get("champion")
    ranked = [
        item for item in aggregate.get("ranking", []) if item.get("approach_id") == champion
    ]
    if len(ranked) != 1 or ranked[0].get("rank") != 1:
        raise CrossCaseError(
            "bind-recommendation",
            f"champion {champion!r} must occur exactly once at ranking position 1",
        )
    digests = []
    for case_id in case_ids:
        selected = mappings.get(case_id, {}).get(champion)
        if selected is None:
            raise CrossCaseError(
                "bind-recommendation",
                f"case {case_id!r} has no exact bundle mapping for champion {champion!r}",
            )
        bundle = output / "cases" / case_id / selected["bundle"]
        fresh = _fresh_digest(bundle)
        recorded = selected.get("bundle_sha256")
        if fresh != recorded:
            raise CrossCaseError(
                "bind-recommendation", f"case {case_id!r} champion bundle digest changed"
            )
        digests.append(fresh)
    if len(set(digests)) != 1:
        raise CrossCaseError(
            "bind-recommendation",
            f"champion {champion!r} has differing bundle digests across cases: {digests!r}",
        )
    return {
        "schema_version": CONTRACT,
        "status": "recommended",
        "atomic_step_id": manifest["atomic_step"]["id"],
        "probe_id": probe["id"],
        "approach_id": champion,
        "aggregated_metrics": ranked[0]["aggregated_metrics"],
        "case_ids": case_ids,
        "case_count": len(case_ids),
        "bundle_sha256": digests[0],
        "rank": 1,
        "promotion_applied": False,
    }


def run_launcher(request_path: Path, output: Path) -> dict[str, Any]:
    request_path = request_path.absolute()
    request = _exact(
        _load(request_path, "cross-case experiment request", "validate-request"),
        "cross-case experiment request",
        {
            "schema_version",
            "development_manifest",
            "probe_id",
            "approach_build_requests",
            "evaluator",
        },
    )
    if type(request["schema_version"]) is not int or request["schema_version"] != CONTRACT:
        raise CrossCaseError(
            "validate-request", f"request schema_version must be integer {CONTRACT}"
        )
    output = output.absolute()
    _prepare_output(output)
    _write_once(output / "cross-case-request.json", request)
    try:
        manifest_path = _resolve(
            request["development_manifest"], request_path.parent, "development_manifest"
        )
        try:
            manifest = validate_manifest(
                _load(manifest_path, "development manifest", "validate-request")
            )
        except ManifestError as error:
            raise CrossCaseError(
                "validate-request", f"development manifest is invalid: {error}"
            ) from None
        probe = _find_probe(manifest, _identifier(request["probe_id"], "probe_id"))
        approach_requests = _approach_requests(
            probe["approaches"], request["approach_build_requests"], request_path.parent
        )
        evaluator = _exact(
            request["evaluator"],
            "evaluator",
            {"adapter", "command"},
        )
        evaluator_adapter = _exact(
            evaluator["adapter"],
            "evaluator.adapter",
            {"path", "sha256"},
        )
        normalized_evaluator = {
            "adapter": {
                "path": str(
                    _resolve(
                        evaluator_adapter["path"],
                        request_path.parent,
                        "evaluator.adapter.path",
                    )
                ),
                "sha256": evaluator_adapter["sha256"],
            },
            "command": evaluator["command"],
        }
        case_ids = [item["case_id"] for item in probe["inputs"]]
        _run_cases(output, manifest_path, probe, approach_requests, normalized_evaluator)
        scores, mappings = _case_metrics(output, probe, case_ids)
        aggregate = _aggregate(probe, case_ids, scores)
        aggregate_sha256 = _write_once(output / "aggregated-summary.json", aggregate)
        recommendation = _bind_recommendation(
            output, manifest, probe, case_ids, aggregate, mappings
        )
        recommendation_sha256 = _write_once(output / "recommendation.json", recommendation)
        _write_once(
            output / "cross-case-summary.json",
            {
                "schema_version": CONTRACT,
                "status": "completed",
                "atomic_step_id": manifest["atomic_step"]["id"],
                "probe_id": probe["id"],
                "case_ids": case_ids,
                "aggregated_summary_sha256": aggregate_sha256,
                "recommendation_sha256": recommendation_sha256,
                "promotion_applied": False,
            },
        )
        return recommendation
    except CrossCaseError as error:
        if not (output / "cross-case-summary.json").exists():
            _write_once(
                output / "cross-case-summary.json",
                {
                    "schema_version": CONTRACT,
                    "status": "failed",
                    "stage": error.stage,
                    "error": str(error),
                    "promotion_applied": False,
                },
            )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run one mini-probe across every declared case")
    run.add_argument("request", type=Path)
    run.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = run_launcher(args.request, args.output)
    except (CrossCaseError, OSError, subprocess.SubprocessError) as error:
        print(f"Cross-case development probe refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
