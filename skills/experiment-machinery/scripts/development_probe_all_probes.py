#!/usr/bin/env python3
"""Run every declared development mini-probe and collect its verified candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from evaluator_calibration import normalize_calibration
from independent_evaluation import normalize_reference

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from development_probe_manifest import ManifestError, validate_manifest

CONTRACT = 1
MAX_PROBE_WORKERS = 4


class AllProbeError(RuntimeError):
    """The all-probe run cannot safely continue."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _normalize_observation_assessment(value, base):
    try:
        return normalize_reference(value, base)
    except (ValueError, OSError) as error:
        raise AllProbeError("validate-request", f"assessment is invalid: {error}; correct the assessment reference before retrying") from error


def _normalize_calibration(value, base):
    try:
        return normalize_calibration(value, base)
    except (ValueError, OSError) as error:
        raise AllProbeError("validate-request", f"calibration is invalid: {error}; correct its path and hash before retrying") from error


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path, label: str, stage: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AllProbeError(stage, f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise AllProbeError(stage, f"{label} must contain one JSON object")
    return value


def _exact(
    value: object, label: str, fields: set[str], stage: str = "validate-request"
) -> dict[str, Any]:
    if type(value) is not dict:
        raise AllProbeError(
            stage,
            f"{label} is {type(value).__name__}; provide an object with fields {sorted(fields)}",
        )
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise AllProbeError(
            stage,
            f"{label} has missing fields {missing} and unexpected fields {extra}; "
            "add missing fields and remove unexpected fields",
        )
    return value


def _identifier(value: object, label: str, stage: str = "validate-request") -> str:
    if type(value) is not str or not value:
        raise AllProbeError(stage, f"{label} must be a nonempty identity")
    return value


def _resolve(value: object, base: Path, label: str) -> Path:
    if type(value) is not str or not value:
        raise AllProbeError("validate-request", f"{label} must be a nonempty path")
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
            raise AllProbeError(
                "prepare-output", f"output must be a new or empty directory: {path}"
            )
    else:
        path.mkdir(parents=True)


def _reconcile_probe_requests(
    probes: list[dict[str, Any]], values: object, request_base: Path
) -> list[dict[str, Any]]:
    if type(values) is not list:
        raise AllProbeError("validate-request", "probe_requests must be a list")
    accepted: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        item = _exact(value, f"probe_requests[{index}]", {"probe_id", "request"})
        accepted.append(
            {
                "probe_id": _identifier(item["probe_id"], f"probe_requests[{index}].probe_id"),
                "request": _resolve(
                    item["request"], request_base, f"probe_requests[{index}].request"
                ),
            }
        )
    declared_ids = [probe["id"] for probe in probes]
    declared = set(declared_ids)
    counts = Counter(item["probe_id"] for item in accepted)
    missing = [probe_id for probe_id in declared_ids if counts[probe_id] == 0]
    duplicate = sorted(probe_id for probe_id, count in counts.items() if count > 1)
    unknown = sorted(probe_id for probe_id in counts if probe_id not in declared)
    problems = []
    if missing:
        problems.append(
            f"missing probes {missing!r}; provide exactly one request per manifest probe"
        )
    if duplicate:
        problems.append(f"duplicate probes {duplicate!r}; remove repeated probe requests")
    if unknown:
        problems.append(
            f"unknown probes {unknown!r}; remove requests not declared by the manifest"
        )
    if problems:
        raise AllProbeError("validate-request", "; ".join(problems))
    by_probe = {item["probe_id"]: item for item in accepted}
    return [by_probe[probe_id] for probe_id in declared_ids]


def _normalize_cross_request(
    task: dict[str, Any], manifest_path: Path
) -> dict[str, Any]:
    source_path = task["request"]
    raw_value = _load(source_path, f"probe {task['probe_id']!r} request", "validate-request")
    value = _exact(
        raw_value,
        f"probe {task['probe_id']!r} request",
        {
            "schema_version",
            "development_manifest",
            "probe_id",
            "approach_build_requests",
            "evaluator",
        } | ({"assessment"} if "assessment" in raw_value else set()) | ({"selection"} if "selection" in raw_value else set()) | ({"calibration"} if "calibration" in raw_value else set()),
    )
    if value["schema_version"] != CONTRACT or type(value["schema_version"]) is not int:
        raise AllProbeError(
            "validate-request",
            f"probe {task['probe_id']!r} request schema_version must be integer {CONTRACT}",
        )
    inner_probe = _identifier(value["probe_id"], f"probe {task['probe_id']!r} request probe_id")
    if inner_probe != task["probe_id"]:
        raise AllProbeError(
            "validate-request",
            f"probe request {task['probe_id']!r} contains probe_id {inner_probe!r}; "
            f"change it to {task['probe_id']!r}",
        )
    inner_manifest = _resolve(
        value["development_manifest"], source_path.parent, "development_manifest"
    )
    if inner_manifest != manifest_path:
        raise AllProbeError(
            "validate-request",
            f"probe {task['probe_id']!r} uses development manifest {inner_manifest}; "
            f"use the all-probe manifest {manifest_path}",
        )
    requests = value["approach_build_requests"]
    if type(requests) is not list:
        raise AllProbeError(
            "validate-request",
            f"probe {task['probe_id']!r} approach_build_requests must be a list",
        )
    normalized = []
    for index, item_value in enumerate(requests):
        item = _exact(
            item_value,
            f"probe {task['probe_id']!r} approach_build_requests[{index}]",
            {"approach_id", "request"},
        )
        normalized.append(
            {
                "approach_id": _identifier(
                    item["approach_id"],
                    f"probe {task['probe_id']!r} approach_build_requests[{index}].approach_id",
                ),
                "request": str(
                    _resolve(
                        item["request"],
                        source_path.parent,
                        f"probe {task['probe_id']!r} approach_build_requests[{index}].request",
                    )
                ),
            }
        )
    evaluator = _exact(
        value["evaluator"],
        f"probe {task['probe_id']!r} evaluator",
        {"adapter", "command"},
    )
    adapter = _exact(
        evaluator["adapter"],
        f"probe {task['probe_id']!r} evaluator adapter",
        {"path", "sha256"},
    )
    return {
        "schema_version": CONTRACT,
        "development_manifest": str(manifest_path),
        "probe_id": task["probe_id"],
        "approach_build_requests": normalized,
        **({"selection": value["selection"]} if "selection" in value else {}),
        **({"calibration": _normalize_calibration(value["calibration"], source_path.parent)} if "calibration" in value else {}),
        **({"assessment": _normalize_observation_assessment(value["assessment"], source_path.parent)} if "assessment" in value else {}),
        "evaluator": {
            "adapter": {
                "path": str(
                    _resolve(
                        adapter["path"],
                        source_path.parent,
                        f"probe {task['probe_id']!r} evaluator adapter path",
                    )
                ),
                "sha256": adapter["sha256"],
            },
            "command": evaluator["command"],
        },
    }


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _run_probe(
    launcher: Path,
    probe_id: str,
    request_path: Path,
    probe_output: Path,
    log_root: Path,
) -> dict[str, Any]:
    completed = _run_command(
        [sys.executable, str(launcher), "run", str(request_path), str(probe_output)]
    )
    _write_text(log_root / "stdout.txt", completed.stdout)
    _write_text(log_root / "stderr.txt", completed.stderr)
    result: dict[str, Any] = {
        "probe_id": probe_id,
        "status": "completed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "output": str(probe_output),
    }
    if completed.returncode != 0:
        result["error"] = completed.stderr.strip() or f"probe launcher exited {completed.returncode}"
    return result


def _run_probes(output: Path, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    launcher = Path(__file__).with_name("development_probe_cross_case.py")
    indexed: dict[int, dict[str, Any]] = {}
    workers = min(MAX_PROBE_WORKERS, len(tasks))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _run_probe,
                launcher,
                task["probe_id"],
                task["request"],
                output / "probes" / task["probe_id"],
                output / "probe-logs" / task["probe_id"],
            ): (index, task["probe_id"])
            for index, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            index, probe_id = futures[future]
            try:
                indexed[index] = future.result()
            except (OSError, TypeError, ValueError) as error:
                indexed[index] = {
                    "probe_id": probe_id,
                    "status": "failed",
                    "returncode": 2,
                    "output": str(output / "probes" / probe_id),
                    "error": str(error),
                }
    ordered = [indexed[index] for index in range(len(tasks))]
    _write_once(
        output / "probe-results.json",
        {
            "schema_version": CONTRACT,
            "results": [
                {**item, "output": str(Path(item["output"]).relative_to(output))}
                for item in ordered
            ],
        },
    )
    failures = [item for item in ordered if item["status"] != "completed"]
    if failures:
        details = "; ".join(
            f"{item['probe_id']}: {item.get('error', 'failed')}" for item in failures
        )
        raise AllProbeError(
            "run-probes", f"one or more declared probes failed; preserved every result: {details}"
        )
    return ordered


def _fresh_digest(bundle: Path) -> str:
    verifier = Path(__file__).with_name("development_probe_candidate.py")
    completed = _run_command([sys.executable, str(verifier), "verify", str(bundle)])
    if completed.returncode != 0:
        raise AllProbeError(
            "bind-candidates",
            completed.stderr.strip() or f"candidate verification exited {completed.returncode}",
        )
    try:
        digest = json.loads(completed.stdout)["bundle_sha256"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise AllProbeError(
            "bind-candidates", f"candidate verification result is invalid: {error}"
        ) from None
    if type(digest) is not str or len(digest) != 64:
        raise AllProbeError("bind-candidates", "verified bundle digest is invalid")
    return digest


def _bind_one_candidate(
    output: Path, manifest: dict[str, Any], probe: dict[str, Any]
) -> dict[str, Any]:
    probe_id = probe["id"]
    probe_output = output / "probes" / probe_id
    summary_path = probe_output / "cross-case-summary.json"
    summary = _load(summary_path, f"probe {probe_id!r} summary", "bind-candidates")
    recommendation_path = probe_output / "recommendation.json"
    recommendation = _exact(
        _load(
            recommendation_path,
            f"probe {probe_id!r} recommendation",
            "bind-candidates",
        ),
        f"probe {probe_id!r} recommendation",
        {
            "schema_version",
            "status",
            "atomic_step_id",
            "probe_id",
            "approach_id",
            "aggregated_metrics",
            "case_ids",
            "case_count",
            "bundle_sha256",
            "rank",
            "promotion_applied",
        },
        "bind-candidates",
    )
    problems = []
    if summary.get("status") != "completed":
        problems.append(f"summary status is {summary.get('status')!r}; require 'completed'")
    if summary.get("atomic_step_id") != manifest["atomic_step"]["id"]:
        problems.append(
            f"summary atomic-step identity is {summary.get('atomic_step_id')!r}; "
            f"require {manifest['atomic_step']['id']!r}"
        )
    if summary.get("probe_id") != probe_id:
        problems.append(
            f"summary probe identity is {summary.get('probe_id')!r}; require {probe_id!r}"
        )
    if summary.get("promotion_applied") is not False:
        problems.append("summary promotion_applied is not false; provide unpromoted evidence")
    recorded_hash = summary.get("recommendation_sha256")
    actual_hash = _digest(recommendation_path.read_bytes())
    if recorded_hash != actual_hash:
        problems.append(
            f"recommendation digest is {actual_hash!r}, not recorded {recorded_hash!r}; "
            "restore the unchanged recommendation"
        )
    if recommendation["atomic_step_id"] != manifest["atomic_step"]["id"]:
        problems.append(
            f"atomic-step identity is {recommendation['atomic_step_id']!r}; "
            f"require {manifest['atomic_step']['id']!r}"
        )
    if recommendation["probe_id"] != probe_id:
        problems.append(
            f"probe identity is {recommendation['probe_id']!r}; require {probe_id!r}"
        )
    if recommendation["status"] != "recommended":
        problems.append(
            f"recommendation status is {recommendation['status']!r}; require 'recommended'"
        )
    if recommendation["rank"] != 1:
        problems.append(f"recommendation rank is {recommendation['rank']!r}; require 1")
    if recommendation["promotion_applied"] is not False:
        problems.append("promotion_applied is not false; provide an unpromoted recommendation")
    declared_approaches = [item["id"] for item in probe["approaches"]]
    if recommendation["approach_id"] not in declared_approaches:
        problems.append(
            f"approach is {recommendation['approach_id']!r}; choose from {declared_approaches!r}"
        )
    expected_cases = [item["case_id"] for item in probe["inputs"]]
    if recommendation["case_ids"] != expected_cases:
        problems.append(
            f"case_ids are {recommendation['case_ids']!r}; require ordered {expected_cases!r}"
        )
    if recommendation["case_count"] != len(expected_cases):
        problems.append(
            f"case_count is {recommendation['case_count']!r}; require {len(expected_cases)}"
        )
    if problems:
        raise AllProbeError(
            "bind-candidates", f"probe {probe_id!r} candidate is invalid: " + "; ".join(problems)
        )

    bundle_paths = []
    digests = []
    for case_id in expected_cases:
        case_output = probe_output / "cases" / case_id
        mapping = _load(
            case_output / "variant-map.json",
            f"probe {probe_id!r} case {case_id!r} variant map",
            "bind-candidates",
        )
        matches = [
            item
            for item in mapping.get("variants", [])
            if item.get("approach_id") == recommendation["approach_id"]
        ]
        if len(matches) != 1:
            raise AllProbeError(
                "bind-candidates",
                f"probe {probe_id!r} case {case_id!r} has {len(matches)} mappings for "
                f"approach {recommendation['approach_id']!r}; require exactly one",
            )
        selected = matches[0]
        bundle = (case_output / selected["bundle"]).resolve()
        fresh = _fresh_digest(bundle)
        recorded = selected.get("bundle_sha256")
        if selected.get("probe_id") != probe_id or case_id not in selected.get("case_ids", []):
            raise AllProbeError(
                "bind-candidates",
                f"probe {probe_id!r} case {case_id!r} bundle mapping has the wrong identity; "
                "provide the matching probe and case bundle",
            )
        if fresh != recorded or fresh != recommendation["bundle_sha256"]:
            raise AllProbeError(
                "bind-candidates",
                f"probe {probe_id!r} case {case_id!r} bundle digest is {fresh!r}; "
                f"require unchanged digest {recommendation['bundle_sha256']!r}",
            )
        bundle_paths.append(bundle)
        digests.append(fresh)
    if len(set(digests)) != 1:
        raise AllProbeError(
            "bind-candidates",
            f"probe {probe_id!r} has differing verified bundle digests {digests!r}; "
            "provide one unchanged candidate across every case",
        )
    return {
        "probe_id": probe_id,
        "artifact": probe["winner_output"]["artifact"],
        "approach_id": recommendation["approach_id"],
        "bundle": str(bundle_paths[0].relative_to(output)),
        "bundle_sha256": digests[0],
        "case_ids": expected_cases,
        "recommendation": str(recommendation_path.relative_to(output)),
    }


def _bind_candidates(
    output: Path, manifest: dict[str, Any], results: list[dict[str, Any]]
) -> dict[str, Any]:
    declared = [probe["id"] for probe in manifest["mini_probes"]]
    actual = [item["probe_id"] for item in results]
    if actual != declared or len(set(actual)) != len(declared):
        raise AllProbeError(
            "bind-candidates",
            f"completed probe results are {actual!r}; require exactly ordered {declared!r}",
        )
    candidates = [
        _bind_one_candidate(output, manifest, probe) for probe in manifest["mini_probes"]
    ]
    return {
        "schema_version": CONTRACT,
        "status": "candidates-ready",
        "atomic_step_id": manifest["atomic_step"]["id"],
        "candidates": candidates,
        "candidate_count": len(candidates),
        "promotion_applied": False,
    }


def run_launcher(request_path: Path, output: Path) -> dict[str, Any]:
    request_path = request_path.absolute()
    request = _exact(
        _load(request_path, "all-probe request", "validate-request"),
        "all-probe request",
        {"schema_version", "development_manifest", "probe_requests"},
    )
    if request["schema_version"] != CONTRACT or type(request["schema_version"]) is not int:
        raise AllProbeError(
            "validate-request", f"request schema_version must be integer {CONTRACT}"
        )
    output = output.absolute()
    _prepare_output(output)
    _write_once(output / "all-probe-request.json", request)
    try:
        manifest_path = _resolve(
            request["development_manifest"], request_path.parent, "development_manifest"
        )
        try:
            manifest = validate_manifest(
                _load(manifest_path, "development manifest", "validate-request")
            )
        except ManifestError as error:
            raise AllProbeError(
                "validate-request", f"development manifest is invalid: {error}"
            ) from None
        tasks = _reconcile_probe_requests(
            manifest["mini_probes"], request["probe_requests"], request_path.parent
        )
        normalized_tasks = []
        for task in tasks:
            normalized_path = output / "probe-requests" / f"{task['probe_id']}.json"
            _write_once(normalized_path, _normalize_cross_request(task, manifest_path))
            normalized_tasks.append({"probe_id": task["probe_id"], "request": normalized_path})
        results = _run_probes(output, normalized_tasks)
        unavailable = []
        for probe in manifest["mini_probes"]:
            result = _load(output / "probes" / probe["id"] / "cross-case-summary.json", "cross-case summary", "bind-candidates")
            if result.get("status") == "no-recommendation":
                unavailable.append({"probe_id":probe["id"], "selection_outcome":result["selection_outcome"]})
        if unavailable:
            result = {"schema_version":CONTRACT, "status":"no-recommendation", "recommendation":None,
                "unavailable_probes":unavailable, "promotion_applied":False}
            _write_once(output / "all-probes-summary.json", result)
            return result
        candidates = _bind_candidates(output, manifest, results)
        candidates_sha256 = _write_once(output / "promotion-candidates.json", candidates)
        _write_once(
            output / "all-probes-summary.json",
            {
                "schema_version": CONTRACT,
                "status": "completed",
                "atomic_step_id": manifest["atomic_step"]["id"],
                "probe_ids": [probe["id"] for probe in manifest["mini_probes"]],
                "promotion_candidates_sha256": candidates_sha256,
                "promotion_applied": False,
            },
        )
        return candidates
    except AllProbeError as error:
        if not (output / "all-probes-summary.json").exists():
            _write_once(
                output / "all-probes-summary.json",
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
    run = subparsers.add_parser("run", help="run every declared mini-probe")
    run.add_argument("request", type=Path)
    run.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = run_launcher(args.request, args.output)
    except (AllProbeError, OSError, subprocess.SubprocessError) as error:
        print(f"All-probe development run refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
