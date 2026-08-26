#!/usr/bin/env python3
"""Run every declared approach for one mini-probe and preserve its recommendation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from development_probe_manifest import ManifestError, validate_manifest

CONTRACT = 1
EXPERIMENT_SPEC_CONTRACT = 2
MAX_BUILD_WORKERS = 4


class LaunchError(RuntimeError):
    """The single-probe experiment cannot safely continue."""

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
        raise LaunchError(stage, f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise LaunchError(stage, f"{label} must contain one JSON object")
    return value


def _exact(
    value: object, label: str, fields: set[str], stage: str
) -> dict[str, Any]:
    if type(value) is not dict:
        raise LaunchError(
            stage,
            f"{label} is {type(value).__name__}; provide an object with fields {sorted(fields)}",
        )
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise LaunchError(
            stage,
            f"{label} has missing fields {missing} and unexpected fields {extra}; "
            "add missing fields and remove unexpected fields",
        )
    return value


def _identifier(value: object, label: str, stage: str) -> str:
    if type(value) is not str or not value:
        raise LaunchError(stage, f"{label} must be a nonempty declared identity")
    return value


def _resolve(value: object, base: Path, label: str, stage: str) -> Path:
    if type(value) is not str or not value:
        raise LaunchError(stage, f"{label} must be a nonempty path")
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
            raise LaunchError(
                "prepare-output",
                f"output must be a new or empty directory: {path}",
            )
    else:
        path.mkdir(parents=True)


def _find_probe(manifest: dict[str, Any], probe_id: str) -> dict[str, Any]:
    probe = next(
        (item for item in manifest["mini_probes"] if item["id"] == probe_id),
        None,
    )
    if probe is None:
        raise LaunchError(
            "validate-request",
            f"probe_id {probe_id!r} is undeclared in the development manifest",
        )
    return probe


def _find_case(
    manifest: dict[str, Any], probe: dict[str, Any], case_id: str, manifest_path: Path
) -> tuple[dict[str, Any], Path]:
    allowed = [item["case_id"] for item in probe["inputs"]]
    if case_id not in allowed:
        raise LaunchError(
            "validate-request",
            f"case_id {case_id!r} is undeclared for probe {probe['id']!r}; choose from {allowed}",
        )
    case = next(
        item for item in manifest["atomic_step"]["captured_cases"] if item["id"] == case_id
    )
    case_path = _resolve(
        case["source"], manifest_path.parent, f"captured case {case_id!r} source", "validate-request"
    )
    if not case_path.is_file():
        raise LaunchError(
            "validate-request", f"captured case {case_id!r} source is missing: {case_path}"
        )
    actual = _digest(case_path.read_bytes())
    if actual != case["sha256"]:
        raise LaunchError(
            "validate-request",
            f"captured case {case_id!r} changed: expected {case['sha256']}, actual {actual}",
        )
    return case, case_path


def _reconcile_approaches(
    declared: list[dict[str, Any]], requests: object, base: Path
) -> list[dict[str, Any]]:
    if type(requests) is not list:
        raise LaunchError(
            "validate-request", "approach_build_requests must be a list"
        )
    accepted: list[dict[str, Any]] = []
    for index, value in enumerate(requests):
        item = _exact(
            value,
            f"approach_build_requests[{index}]",
            {"approach_id", "request"},
            "validate-request",
        )
        accepted.append(
            {
                "approach_id": _identifier(
                    item["approach_id"],
                    f"approach_build_requests[{index}].approach_id",
                    "validate-request",
                ),
                "request": _resolve(
                    item["request"],
                    base,
                    f"approach_build_requests[{index}].request",
                    "validate-request",
                ),
            }
        )
    declared_ids = [item["id"] for item in declared]
    actual_ids = [item["approach_id"] for item in accepted]
    declared_set = set(declared_ids)
    actual_set = set(actual_ids)
    duplicates = sorted(
        approach_id for approach_id in actual_set if actual_ids.count(approach_id) > 1
    )
    unknown = sorted(actual_set - declared_set)
    missing = [approach_id for approach_id in declared_ids if approach_id not in actual_set]
    errors = []
    if duplicates:
        errors.append(
            f"duplicate approaches {duplicates!r}; provide exactly one build request for each"
        )
    if unknown:
        errors.append(f"unknown approaches {unknown!r}; choose only from {declared_ids!r}")
    if missing:
        errors.append(f"missing approaches {missing!r}; provide their build requests")
    if errors:
        raise LaunchError("validate-request", "; ".join(errors))
    by_id = {item["approach_id"]: item for item in accepted}
    return [by_id[approach_id] for approach_id in declared_ids]


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _build_one(
    builder: Path,
    task: dict[str, Any],
    bundle_path: Path,
    log_root: Path,
    expected_manifest_sha256: str,
    probe_id: str,
) -> dict[str, Any]:
    approach_id = task["approach_id"]
    build = _run_command(
        [sys.executable, str(builder), "build", str(task["request"]), str(bundle_path)]
    )
    _write_text(log_root / "stdout.txt", build.stdout)
    _write_text(log_root / "stderr.txt", build.stderr)
    if build.returncode != 0:
        return {
            "approach_id": approach_id,
            "status": "build-refused",
            "error": build.stderr.strip() or f"candidate build exited {build.returncode}",
        }
    verify = _run_command(
        [sys.executable, str(builder), "verify", str(bundle_path)]
    )
    _write_text(log_root / "verify.stdout.txt", verify.stdout)
    _write_text(log_root / "verify.stderr.txt", verify.stderr)
    if verify.returncode != 0:
        return {
            "approach_id": approach_id,
            "status": "verification-refused",
            "error": verify.stderr.strip() or f"candidate verification exited {verify.returncode}",
        }
    try:
        built = json.loads(build.stdout)
        verified = json.loads(verify.stdout)
        bundle = _load(bundle_path / "bundle.json", "candidate bundle manifest", "build-candidates")
    except (json.JSONDecodeError, LaunchError) as error:
        return {
            "approach_id": approach_id,
            "status": "invalid-build-result",
            "error": str(error),
        }
    identity = bundle.get("identity", {})
    errors = []
    if built.get("approach_id") != approach_id or verified.get("approach_id") != approach_id:
        errors.append("build or verification returned a different approach identity")
    if identity.get("approach_id") != approach_id:
        errors.append("bundle contains a different approach identity")
    if identity.get("probe_id") != probe_id:
        errors.append("bundle contains a different probe identity")
    if identity.get("development_manifest_sha256") != expected_manifest_sha256:
        errors.append("bundle was built from a different development manifest")
    if built.get("bundle_sha256") != verified.get("bundle_sha256"):
        errors.append("built and verified bundle digests differ")
    if errors:
        return {
            "approach_id": approach_id,
            "status": "identity-refused",
            "error": "; ".join(errors),
        }
    return {
        "approach_id": approach_id,
        "status": "built",
        "bundle": bundle_path,
        "bundle_sha256": verified["bundle_sha256"],
        "probe_id": identity["probe_id"],
        "case_ids": bundle["inputs"]["case_ids"],
        "error": None,
    }


def _prepare_bundles(
    tasks: list[dict[str, Any]],
    output: Path,
    manifest: dict[str, Any],
    probe_id: str,
) -> list[dict[str, Any]]:
    builder = Path(__file__).with_name("development_probe_candidate.py")
    bundles = output / "bundles"
    logs = output / "builds"
    bundles.mkdir()
    logs.mkdir()
    expected_manifest_sha256 = _digest(_canonical(manifest))
    indexed: dict[int, dict[str, Any]] = {}
    workers = min(MAX_BUILD_WORKERS, len(tasks))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _build_one,
                builder,
                task,
                bundles / task["approach_id"],
                logs / task["approach_id"],
                expected_manifest_sha256,
                probe_id,
            ): index
            for index, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                indexed[index] = future.result()
            except (KeyError, LaunchError, OSError, TypeError, ValueError) as error:
                indexed[index] = {
                    "approach_id": tasks[index]["approach_id"],
                    "status": "internal-build-failure",
                    "error": str(error),
                }
    results = [indexed[index] for index in range(len(tasks))]
    _write_once(
        output / "build-results.json",
        {
            "schema_version": CONTRACT,
            "results": [
                {
                    **item,
                    **(
                        {"bundle": str(item["bundle"].relative_to(output))}
                        if "bundle" in item
                        else {}
                    ),
                }
                for item in results
            ],
        },
    )
    failures = [item for item in results if item["status"] != "built"]
    if failures:
        details = "; ".join(
            f"{item['approach_id']}: {item['error']}" for item in failures
        )
        raise LaunchError(
            "build-candidates",
            f"candidate bundle preparation failed; preserved all build results: {details}",
        )
    return results


def _source_digest(runner: Path, source: Path) -> str:
    completed = _run_command(
        [sys.executable, str(runner), "--hash-source", str(source)]
    )
    if completed.returncode != 0:
        raise LaunchError(
            "run-experiment",
            completed.stderr.strip() or "Experiment Machinery could not hash its source",
        )
    return completed.stdout.strip()


def _variant_map(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mappings = []
    for index, result in enumerate(results, start=1):
        variant_id = "control" if index == 1 else f"variation-{index}"
        mappings.append(
            {
                "variant_id": variant_id,
                "approach_id": result["approach_id"],
                "bundle": result["bundle"],
                "bundle_sha256": result["bundle_sha256"],
                "probe_id": result["probe_id"],
                "case_ids": result["case_ids"],
            }
        )
    return mappings


def _experiment_id(
    manifest: dict[str, Any], probe_id: str, case_id: str, mappings: list[dict[str, Any]]
) -> str:
    identity = {
        "atomic_step_id": manifest["atomic_step"]["id"],
        "probe_id": probe_id,
        "case_id": case_id,
        "bundles": [item["bundle_sha256"] for item in mappings],
    }
    return f"development-probe-{_digest(_canonical(identity))[:20]}"


def _run_experiment(
    output: Path,
    manifest: dict[str, Any],
    probe: dict[str, Any],
    case: dict[str, Any],
    case_path: Path,
    mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    scripts = Path(__file__).parent
    runner = scripts / "run_experiment.py"
    candidate = scripts / "development_probe_candidate.py"
    experiment_id = _experiment_id(manifest, probe["id"], case["id"], mappings)
    spec = {
        "schema_version": EXPERIMENT_SPEC_CONTRACT,
        "experiment_id": experiment_id,
        "hypothesis": (
            f"Every approach declared by mini-probe {probe['id']!r} can run against "
            f"captured case {case['id']!r}, and the declared metrics recommend one bundle."
        ),
        "target": {
            "machinery": "experiment-machinery",
            "phase": "development-probe-candidate",
            "source": {
                "path": str(scripts),
                "sha256": _source_digest(runner, scripts),
            },
            "entrypoint": candidate.name,
        },
        "frozen_input": {"path": str(case_path), "sha256": case["sha256"]},
        "variants": [
            {
                "id": item["variant_id"],
                "command": [
                    sys.executable,
                    str(candidate),
                    "execute",
                    str(item["bundle"]),
                ],
                "adapter": {"path": str(candidate), "sha256": _digest(candidate.read_bytes())},
                "configuration": {"case_id": case["id"]},
            }
            for item in mappings
        ],
        "evaluation": {"metrics": probe["evaluation"]["metrics"]},
    }
    _write_once(output / "experiment.json", spec)
    _write_once(
        output / "variant-map.json",
        {
            "schema_version": CONTRACT,
            "experiment_id": experiment_id,
            "variants": [
                {
                    **item,
                    "bundle": str(item["bundle"].relative_to(output)),
                }
                for item in mappings
            ],
        },
    )
    completed = _run_command(
        [
            sys.executable,
            str(runner),
            "--spec",
            str(output / "experiment.json"),
            "--output",
            str(output / "experiment"),
        ]
    )
    _write_text(output / "experiment.stdout.txt", completed.stdout)
    _write_text(output / "experiment.stderr.txt", completed.stderr)
    summary_path = output / "experiment" / "summary.json"
    if not summary_path.is_file():
        raise LaunchError(
            "run-experiment",
            completed.stderr.strip()
            or f"Experiment Machinery exited {completed.returncode} without a summary",
        )
    summary = _load(summary_path, "experiment summary", "verify-experiment")
    if summary.get("promotion_applied") is not False:
        raise LaunchError(
            "verify-experiment",
            "experiment summary does not prove promotion_applied is false",
        )
    expected = [item["variant_id"] for item in mappings]
    by_id = {item.get("variant_id"): item for item in summary.get("variants", [])}
    incomplete = [
        variant_id
        for variant_id in expected
        if variant_id not in by_id
        or not by_id[variant_id].get("eligible")
        or by_id[variant_id].get("status") != "completed"
    ]
    if completed.returncode != 0 or incomplete:
        raise LaunchError(
            "verify-experiment",
            f"experiment did not complete every declared approach; incomplete variants: {incomplete}",
        )
    return summary


def _fresh_bundle_digest(builder: Path, bundle: Path) -> str:
    completed = _run_command(
        [sys.executable, str(builder), "verify", str(bundle)]
    )
    if completed.returncode != 0:
        raise LaunchError(
            "bind-recommendation",
            completed.stderr.strip() or f"candidate bundle verification exited {completed.returncode}",
        )
    try:
        return str(json.loads(completed.stdout)["bundle_sha256"])
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise LaunchError(
            "bind-recommendation", f"candidate verification result is invalid: {error}"
        ) from None


def _bind_recommendation(
    output: Path,
    manifest: dict[str, Any],
    probe_id: str,
    case_id: str,
    summary: dict[str, Any],
    mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    champion = summary.get("champion")
    if champion is None:
        raise LaunchError(
            "bind-recommendation",
            "summary champion is null; bind only a completed eligible variant",
        )
    index: dict[str, list[dict[str, Any]]] = {}
    builder = Path(__file__).with_name("development_probe_candidate.py")
    for item in mappings:
        item["verified_bundle_sha256"] = _fresh_bundle_digest(builder, item["bundle"])
        index.setdefault(item["variant_id"], []).append(item)
    matches = index.get(champion, [])
    if len(matches) != 1:
        raise LaunchError(
            "bind-recommendation",
            f"champion {champion!r} has {len(matches)} bundle mappings; require exactly one",
        )
    ranking_rows = summary.get("ranking", [])
    ranked = [row for row in ranking_rows if row.get("variant_id") == champion]
    if len(ranked) != 1 or ranked[0].get("rank") != 1:
        raise LaunchError(
            "bind-recommendation",
            f"champion {champion!r} must occur exactly once at ranking position 1",
        )
    selected = matches[0]
    if selected["bundle_sha256"] != selected["verified_bundle_sha256"]:
        raise LaunchError(
            "bind-recommendation", f"champion {champion!r} bundle digest changed"
        )
    if selected["probe_id"] != probe_id or case_id not in selected["case_ids"]:
        raise LaunchError(
            "bind-recommendation",
            f"champion {champion!r} does not belong to requested probe and case",
        )
    return {
        "schema_version": CONTRACT,
        "status": "recommended",
        "atomic_step_id": manifest["atomic_step"]["id"],
        "probe_id": probe_id,
        "case_id": case_id,
        "experiment_id": summary["experiment_id"],
        "variant_id": champion,
        "approach_id": selected["approach_id"],
        "bundle": str(selected["bundle"].relative_to(output)),
        "bundle_sha256": selected["bundle_sha256"],
        "rank": 1,
        "promotion_applied": False,
    }


def run_launcher(request_path: Path, output: Path) -> dict[str, Any]:
    request_path = request_path.absolute()
    request = _exact(
        _load(request_path, "single-probe experiment request", "validate-request"),
        "single-probe experiment request",
        {
            "schema_version",
            "development_manifest",
            "probe_id",
            "case_id",
            "approach_build_requests",
        },
        "validate-request",
    )
    if type(request["schema_version"]) is not int or request["schema_version"] != CONTRACT:
        raise LaunchError(
            "validate-request", f"request schema_version must be integer {CONTRACT}"
        )
    output = output.absolute()
    _prepare_output(output)
    _write_once(output / "launch-request.json", request)
    try:
        manifest_path = _resolve(
            request["development_manifest"],
            request_path.parent,
            "development_manifest",
            "validate-request",
        )
        manifest_value = _load(
            manifest_path, "development manifest", "validate-request"
        )
        try:
            manifest = validate_manifest(manifest_value)
        except ManifestError as error:
            raise LaunchError(
                "validate-request", f"development manifest is invalid: {error}"
            ) from None
        probe_id = _identifier(request["probe_id"], "probe_id", "validate-request")
        case_id = _identifier(request["case_id"], "case_id", "validate-request")
        probe = _find_probe(manifest, probe_id)
        case, case_path = _find_case(manifest, probe, case_id, manifest_path)
        tasks = _reconcile_approaches(
            probe["approaches"], request["approach_build_requests"], request_path.parent
        )
        results = _prepare_bundles(tasks, output, manifest, probe_id)
        mappings = _variant_map(results)
        summary = _run_experiment(
            output, manifest, probe, case, case_path, mappings
        )
        recommendation = _bind_recommendation(
            output, manifest, probe_id, case_id, summary, mappings
        )
        recommendation_sha256 = _write_once(
            output / "recommendation.json", recommendation
        )
        _write_once(
            output / "launch-summary.json",
            {
                "schema_version": CONTRACT,
                "status": "completed",
                "atomic_step_id": manifest["atomic_step"]["id"],
                "probe_id": probe_id,
                "case_id": case_id,
                "experiment_id": summary["experiment_id"],
                "recommendation_sha256": recommendation_sha256,
                "promotion_applied": False,
            },
        )
        return recommendation
    except LaunchError as error:
        if not (output / "launch-summary.json").exists():
            _write_once(
                output / "launch-summary.json",
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
    run = subparsers.add_parser("run", help="run one complete mini-probe experiment")
    run.add_argument("request", type=Path)
    run.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = run_launcher(args.request, args.output)
    except (LaunchError, OSError, subprocess.SubprocessError) as error:
        print(f"Development-probe experiment refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
