#!/usr/bin/env python3
"""Run Development-Probe and repair a failed probe through bounded experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Any

from development_probe_candidate import CandidateError, verify_bundle
from development_probe_manifest import ManifestError, validate_manifest
from development_probe_run import _bind_final_result, _normalize_request


CONTRACT = 1
APPROACH_FIELDS = {"id", "hypothesis", "instructions", "allowed_paths"}
REPAIR_FIELDS = {
    "schema_version",
    "whole_run",
    "repair_budget",
    "probe_repairs",
    "planner",
    "builder",
    "routing",
}


class RepairError(RuntimeError):
    """The bounded repair process cannot safely continue."""

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
        raise RepairError(stage, f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise RepairError(stage, f"{label} is {type(value).__name__}; provide one JSON object")
    return value


def _exact(value: object, label: str, fields: set[str], stage: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise RepairError(stage, f"{label} is {type(value).__name__}; provide fields {sorted(fields)}")
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise RepairError(
            stage,
            f"{label} has missing fields {missing} and unexpected fields {extra}; "
            "add the missing fields and remove the unexpected fields",
        )
    return value


def _write_json(path: Path, value: object) -> str:
    payload = _document(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(payload)


def _write_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(payload)


def _resolve(value: object, base: Path, label: str, stage: str = "validate-request") -> Path:
    if type(value) is not str or not value:
        raise RepairError(stage, f"{label} is {value!r}; provide one nonempty path")
    path = Path(value)
    return (path if path.is_absolute() else base / path).absolute()


def _file(value: object, base: Path, label: str) -> tuple[Path, dict[str, str]]:
    item = _exact(value, label, {"path", "sha256"}, "validate-request")
    path = _resolve(item["path"], base, f"{label}.path")
    expected = item["sha256"]
    if type(expected) is not str or len(expected) != 64:
        raise RepairError("validate-request", f"{label}.sha256 is {expected!r}; provide one SHA-256 digest")
    if path.is_symlink() or not path.is_file():
        raise RepairError("validate-request", f"{label}.path is {path}; provide one stable regular file")
    actual = _digest(path.read_bytes())
    if actual != expected:
        raise RepairError(
            "validate-request",
            f"{label} at {path} has SHA-256 {actual}; restore recorded {expected} or update the request",
        )
    return path, {"path": str(path), "sha256": actual}


def _adapter(
    value: object,
    base: Path,
    label: str,
    placeholders: list[str],
) -> dict[str, Any]:
    item = _exact(value, label, {"adapter", "command"}, "validate-request")
    path, record = _file(item["adapter"], base, f"{label}.adapter")
    command = item["command"]
    expected = ["{python}", placeholders[0], *placeholders[1:]]
    if type(command) is not list or command != expected:
        raise RepairError(
            "validate-request",
            f"{label}.command is {command!r}; use exactly {expected!r} so code controls the interview",
        )
    return {"path": path, "record": record, "command": command}


def _relative_paths(value: object, label: str) -> list[str]:
    if type(value) is not list or not value:
        raise RepairError("validate-request", f"{label} is {value!r}; provide one nonempty path list")
    accepted = []
    for index, raw in enumerate(value):
        if type(raw) is not str or not raw:
            raise RepairError("validate-request", f"{label}[{index}] is {raw!r}; provide a relative path")
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != raw:
            raise RepairError("validate-request", f"{label}[{index}] is {raw!r}; keep it inside the probe source")
        accepted.append(raw)
    if len(set(accepted)) != len(accepted):
        raise RepairError("validate-request", f"{label} repeats {accepted!r}; list each allowed path once")
    return accepted


def _normalize(request_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    request = _exact(_load(request_path, "repair request", "validate-request"), "repair request", REPAIR_FIELDS, "validate-request")
    if request["schema_version"] != CONTRACT or type(request["schema_version"]) is not int:
        raise RepairError("validate-request", "repair request schema_version must be integer 1")
    base = request_path.parent
    whole_path, whole_record = _file(request["whole_run"], base, "whole_run")
    try:
        whole_normalized, whole_paths = _normalize_request(whole_path)
    except Exception as error:
        raise RepairError("validate-request", f"whole_run is invalid: {error}") from None
    manifest = validate_manifest(_load(whole_paths["manifest"], "development manifest", "validate-request"))
    evaluators: dict[str, dict[str, Any]] = {}
    for probe_request in whole_normalized["probe_requests"]:
        source_path = Path(probe_request["request"])
        source = _load(source_path, f"probe {probe_request['probe_id']!r} request", "validate-request")
        evaluator = _exact(
            source.get("evaluator"),
            f"probe {probe_request['probe_id']!r} evaluator",
            {"adapter", "command"},
            "validate-request",
        )
        adapter = _exact(
            evaluator["adapter"],
            f"probe {probe_request['probe_id']!r} evaluator adapter",
            {"path", "sha256"},
            "validate-request",
        )
        evaluators[probe_request["probe_id"]] = {
            "adapter": {
                "path": str(_resolve(adapter["path"], source_path.parent, "evaluator adapter")),
                "sha256": adapter["sha256"],
            },
            "command": evaluator["command"],
        }
    whole_paths["evaluators"] = evaluators
    budget = request["repair_budget"]
    if type(budget) is not int or budget < 1:
        raise RepairError("validate-request", f"repair_budget is {budget!r}; provide a positive integer")
    declared = [probe["id"] for probe in manifest["mini_probes"]]
    rows = request["probe_repairs"]
    if type(rows) is not list or not rows:
        raise RepairError("validate-request", "probe_repairs must contain at least one declared probe repair contract")
    repairs: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        item = _exact(raw, f"probe_repairs[{index}]", {"probe_id", "allowed_paths", "approach_ids"}, "validate-request")
        probe_id = item["probe_id"]
        if probe_id not in declared:
            raise RepairError("validate-request", f"probe_repairs[{index}].probe_id is {probe_id!r}; use one of {declared!r}")
        if probe_id in repairs:
            raise RepairError("validate-request", f"probe_repairs repeats {probe_id!r}; keep exactly one contract")
        approaches = item["approach_ids"]
        if type(approaches) is not list or len(approaches) not in {2, 3} or any(type(value) is not str or not value for value in approaches):
            raise RepairError("validate-request", f"probe {probe_id!r} approach_ids are {approaches!r}; provide two or three identities")
        if len(set(approaches)) != len(approaches):
            raise RepairError("validate-request", f"probe {probe_id!r} approach_ids repeat; use unique identities")
        repairs[probe_id] = {
            "probe_id": probe_id,
            "allowed_paths": _relative_paths(item["allowed_paths"], f"probe {probe_id!r} allowed_paths"),
            "approach_ids": approaches,
        }
    planner = _adapter(request["planner"], base, "planner", ["{planner-adapter}", "{planner-request}", "{planner-response}"])
    builder = _adapter(request["builder"], base, "builder", ["{builder-adapter}", "{approach}", "{candidate}", "{builder-result}"])
    routing = _adapter(request["routing"], base, "routing", ["{routing-adapter}", "{routing-question}", "{routing-response}"])
    normalized = {
        "schema_version": CONTRACT,
        "whole_run": whole_record,
        "atomic_step_id": whole_normalized["atomic_step_id"],
        "repair_budget": budget,
        "probe_repairs": [repairs[probe_id] for probe_id in declared if probe_id in repairs],
        "planner": {"adapter": planner["record"], "command": planner["command"]},
        "builder": {"adapter": builder["record"], "command": builder["command"]},
        "routing": {"adapter": routing["record"], "command": routing["command"]},
        "promotion_applied": False,
    }
    return normalized, {
        "whole": whole_path,
        "whole_normalized": whole_normalized,
        "whole_paths": whole_paths,
        "manifest": manifest,
        "repairs": repairs,
        "planner": planner,
        "builder": builder,
        "routing": routing,
        "evaluators": evaluators,
    }


def _prepare_output(output: Path) -> None:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise RepairError("prepare-output", f"output must be a new or empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)


def _expand(command: list[str], replacements: dict[str, str]) -> list[str]:
    return [replacements.get(argument, argument) for argument in command]


def _invoke(
    command: list[str],
    replacements: dict[str, str],
    evidence_root: Path,
    label: str,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(_expand(command, replacements), text=True, capture_output=True, check=False)
    _write_bytes(evidence_root / f"{label}-stdout.txt", completed.stdout.encode("utf-8"))
    _write_bytes(evidence_root / f"{label}-stderr.txt", completed.stderr.encode("utf-8"))
    return completed


def _model_route(
    final_verdict: dict[str, Any],
    manifest: dict[str, Any],
    routing: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    failed = [item for item in final_verdict["cases"] if item.get("verdict") == "not-satisfied"]
    if len(failed) != 1:
        return {"route_kind": "final-validation", "probe_ids": [], "reason": f"final verdict has {len(failed)} failed cases"}
    case_id = failed[0]["case_id"]
    candidates = [
        probe["id"]
        for probe in manifest["mini_probes"]
        if case_id in [item["case_id"] for item in probe["inputs"]]
    ]
    if len(candidates) == 1:
        return {"route_kind": "probes", "probe_ids": candidates, "reason": f"failed case {case_id!r} maps uniquely to {candidates[0]!r}"}
    if not candidates:
        return {"route_kind": "final-validation", "probe_ids": [], "reason": f"failed case {case_id!r} maps to no probe"}
    choices = [*(f"probe:{probe_id}" for probe_id in candidates), "probes:" + ",".join(candidates), "final-validation", "operator-decision"]
    question = {
        "schema_version": CONTRACT,
        "question_id": "failure-route-" + _digest(_canonical({"case_id": case_id, "choices": choices}))[:16],
        "case_id": case_id,
        "allowed_answers": choices,
        "failed_evidence": {"path": "initial/final-verdict.json", "sha256": _digest(_document(final_verdict))},
    }
    question_path = root / "routing-question.json"
    response_path = root / "routing-response.json"
    _write_json(question_path, question)
    completed = _invoke(
        routing["command"],
        {
            "{python}": sys.executable,
            "{routing-adapter}": str(routing["path"]),
            "{routing-question}": str(question_path),
            "{routing-response}": str(response_path),
        },
        root,
        "routing",
    )
    if completed.returncode or not response_path.is_file():
        raise RepairError("route-failure", f"routing interview exited {completed.returncode}; correct the adapter and return one enum answer")
    response = _exact(_load(response_path, "routing response", "route-failure"), "routing response", {"schema_version", "question_id", "answer"}, "route-failure")
    answer = response["answer"]
    if response["schema_version"] != CONTRACT or response["question_id"] != question["question_id"] or answer not in choices:
        raise RepairError("route-failure", f"routing answer is {response!r}; use question {question['question_id']!r} and one of {choices!r}")
    if answer.startswith("probe:"):
        return {"route_kind": "probes", "probe_ids": [answer.split(":", 1)[1]], "reason": f"controlled answer selected {answer!r}"}
    if answer.startswith("probes:"):
        selected = answer.split(":", 1)[1].split(",")
        return {"route_kind": "probes", "probe_ids": [probe_id for probe_id in candidates if probe_id in selected], "reason": f"controlled answer selected {answer!r}"}
    return {"route_kind": answer, "probe_ids": [], "reason": f"controlled answer selected {answer!r}"}


def _validate_plan(value: object, contract: dict[str, Any]) -> list[dict[str, Any]]:
    response = _exact(value, "planner response", {"schema_version", "approaches"}, "plan-repair")
    if response["schema_version"] != CONTRACT:
        raise RepairError("plan-repair", f"planner schema_version is {response['schema_version']!r}; use integer 1")
    approaches = response["approaches"]
    if type(approaches) is not list or len(approaches) not in {2, 3}:
        raise RepairError("plan-repair", f"planner approaches are {approaches!r}; return two or three complete approaches")
    accepted = []
    for index, raw in enumerate(approaches):
        item = _exact(raw, f"planner approaches[{index}]", APPROACH_FIELDS, "plan-repair")
        if any(type(item[field]) is not str or not item[field].strip() for field in ("id", "hypothesis", "instructions")):
            raise RepairError("plan-repair", f"planner approaches[{index}] has an empty identity, hypothesis, or instructions; fill every field")
        paths = _relative_paths(item["allowed_paths"], f"planner approach {item['id']!r} allowed_paths")
        outside = sorted(set(paths) - set(contract["allowed_paths"]))
        if outside:
            raise RepairError("plan-repair", f"planner approach {item['id']!r} allows {outside!r}; use only {contract['allowed_paths']!r}")
        accepted.append({**item, "allowed_paths": paths})
    ids = [item["id"] for item in accepted]
    if ids != contract["approach_ids"]:
        raise RepairError("plan-repair", f"planner approach ids are {ids!r}; return ordered {contract['approach_ids']!r}")
    return accepted


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def _make_writable(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)


def _build_one(
    approach: dict[str, Any],
    baseline: Path,
    builder: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    approach_id = approach["id"]
    candidate = root / "candidates" / approach_id
    shutil.copytree(baseline, candidate)
    _make_writable(candidate)
    before = _snapshot(candidate)
    evidence = root / "builder-evidence" / approach_id
    approach_path = evidence / "approach.json"
    result_path = evidence / "result.json"
    _write_json(approach_path, approach)
    completed = _invoke(
        builder["command"],
        {
            "{python}": sys.executable,
            "{builder-adapter}": str(builder["path"]),
            "{approach}": str(approach_path),
            "{candidate}": str(candidate),
            "{builder-result}": str(result_path),
        },
        evidence,
        "builder",
    )
    after = _snapshot(candidate)
    changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    return {"approach": approach, "candidate": candidate, "returncode": completed.returncode, "result": result_path, "changed_paths": changed, "stderr": completed.stderr.strip()}


def _repair_manifest(manifest: dict[str, Any], probe: dict[str, Any], plan: list[dict[str, Any]]) -> dict[str, Any]:
    repaired_probe = json.loads(json.dumps(probe))
    repaired_probe["approaches"] = [
        {
            "id": item["id"],
            "hypothesis": item["hypothesis"],
            "implementation": item["instructions"],
            "predicted_tradeoff": f"Bounded repair approach {index + 1}.",
        }
        for index, item in enumerate(plan)
    ]
    value = {
        "schema_version": CONTRACT,
        "atomic_step": manifest["atomic_step"],
        "mini_probes": [repaired_probe],
        "composition": {
            "consumes": [{"probe_id": probe["id"], "artifact": probe["winner_output"]["artifact"]}],
            "assembly_contract": f"Select one repaired {probe['id']} candidate without changing other winners.",
            "final_validation": manifest["composition"]["final_validation"],
        },
    }
    try:
        return validate_manifest(value)
    except ManifestError as error:
        raise RepairError("prepare-experiment", f"repair manifest is invalid: {error}") from None


def _run_probe_experiment(
    round_root: Path,
    probe: dict[str, Any],
    manifest: dict[str, Any],
    original_bundle: dict[str, Any],
    baseline: Path,
    builds: list[dict[str, Any]],
    evaluator: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    experiment_root = round_root / probe["id"] / "experiment"
    repair_manifest = _repair_manifest(manifest, probe, [item["approach"] for item in builds])
    manifest_path = round_root / probe["id"] / "repair-manifest.json"
    _write_json(manifest_path, repair_manifest)
    requests = []
    for item in builds:
        approach_id = item["approach"]["id"]
        request_path = round_root / probe["id"] / "build-requests" / f"{approach_id}.json"
        _write_json(
            request_path,
            {
                "schema_version": CONTRACT,
                "development_manifest": str(manifest_path),
                "probe_id": probe["id"],
                "approach_id": approach_id,
                "source": {
                    "baseline": str(baseline),
                    "candidate": str(item["candidate"]),
                    "entrypoint": original_bundle["source"]["entrypoint"],
                },
                "execution": original_bundle["execution"],
            },
        )
        requests.append({"approach_id": approach_id, "request": str(request_path)})
    cross_request = round_root / probe["id"] / "cross-case-request.json"
    _write_json(
        cross_request,
        {
            "schema_version": CONTRACT,
            "development_manifest": str(manifest_path),
            "probe_id": probe["id"],
            "approach_build_requests": requests,
            "evaluator": evaluator,
        },
    )
    script = Path(__file__).parent / "development_probe_cross_case.py"
    completed = _invoke(
        ["{python}", "{script}", "run", "{request}", "{output}"],
        {"{python}": sys.executable, "{script}": str(script), "{request}": str(cross_request), "{output}": str(experiment_root)},
        round_root / probe["id"],
        "experiment",
    )
    recommendation_path = experiment_root / "recommendation.json"
    if completed.returncode or not recommendation_path.is_file():
        detail = completed.stderr.strip() or "repair experiment returned no recommendation"
        raise RepairError("run-experiment", f"probe {probe['id']!r} repair experiment failed: {detail}")
    recommendation = _load(recommendation_path, f"probe {probe['id']!r} repair recommendation", "run-experiment")
    selected = next((item for item in builds if item["approach"]["id"] == recommendation.get("approach_id")), None)
    if selected is None or recommendation.get("rank") != 1 or recommendation.get("promotion_applied") is not False:
        raise RepairError("run-experiment", f"probe {probe['id']!r} recommendation is {recommendation!r}; bind one unpromoted rank-one built approach")
    return recommendation, selected["candidate"]


def _absolutize_candidates(value: dict[str, Any], source_path: Path) -> dict[str, Any]:
    copied = json.loads(json.dumps(value))
    for item in copied["candidates"]:
        item["bundle"] = str(_resolve(item["bundle"], source_path.parent, f"probe {item['probe_id']!r} bundle", "repair-probe"))
        item["recommendation"] = str(_resolve(item["recommendation"], source_path.parent, f"probe {item['probe_id']!r} recommendation", "repair-probe"))
    return copied


def _repackage(
    root: Path,
    probe: dict[str, Any],
    current: dict[str, Any],
    selected_source: Path,
    original_bundle: dict[str, Any],
    paths: dict[str, Any],
) -> dict[str, Any]:
    request_path = root / probe["id"] / "replacement-build.json"
    bundle_path = root / probe["id"] / "replacement-bundle"
    _write_json(
        request_path,
        {
            "schema_version": CONTRACT,
            "development_manifest": str(paths["manifest"]),
            "probe_id": probe["id"],
            "approach_id": current["approach_id"],
            "source": {
                "baseline": str(paths["baseline"]),
                "candidate": str(selected_source),
                "entrypoint": original_bundle["source"]["entrypoint"],
            },
            "execution": original_bundle["execution"],
        },
    )
    script = Path(__file__).parent / "development_probe_candidate.py"
    completed = _invoke(
        ["{python}", "{script}", "build", "{request}", "{output}"],
        {"{python}": sys.executable, "{script}": str(script), "{request}": str(request_path), "{output}": str(bundle_path)},
        root / probe["id"],
        "replacement-build",
    )
    if completed.returncode:
        raise RepairError("package-repair", f"probe {probe['id']!r} replacement bundle failed: {completed.stderr.strip()}")
    try:
        _, _, digest = verify_bundle(bundle_path)
    except CandidateError as error:
        raise RepairError("package-repair", f"probe {probe['id']!r} replacement bundle is invalid: {error}") from None
    return {**current, "bundle": str(bundle_path), "bundle_sha256": digest, "recommendation": str(root / probe["id"] / "experiment" / "recommendation.json")}


def _repair_probe(
    round_root: Path,
    probe_id: str,
    candidates: dict[str, Any],
    manifest: dict[str, Any],
    contract: dict[str, Any],
    planner: dict[str, Any],
    builder: dict[str, Any],
    whole_paths: dict[str, Any],
    failed_verdict: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    probe = next(item for item in manifest["mini_probes"] if item["id"] == probe_id)
    current = next(item for item in candidates["candidates"] if item["probe_id"] == probe_id)
    bundle_path = Path(current["bundle"])
    try:
        original_bundle, bundled_manifest, fresh_digest = verify_bundle(bundle_path)
    except (CandidateError, OSError) as error:
        raise RepairError("repair-probe", f"probe {probe_id!r} current winner is invalid: {error}") from None
    if bundled_manifest != manifest or fresh_digest != current["bundle_sha256"]:
        raise RepairError("repair-probe", f"probe {probe_id!r} current winner identity changed; restore its recorded bundle")
    baseline = bundle_path / original_bundle["source"]["root"]
    missing = [path for path in contract["allowed_paths"] if not (baseline / path).is_file()]
    if missing:
        raise RepairError("repair-probe", f"probe {probe_id!r} allowed paths {missing!r} are absent; name files inside its current source")
    planner_root = round_root / probe_id / "planner"
    request_path = planner_root / "request.json"
    response_path = planner_root / "response.json"
    _write_json(
        request_path,
        {
            "schema_version": CONTRACT,
            "atomic_step_id": manifest["atomic_step"]["id"],
            "probe_id": probe_id,
            "failed_verdict": failed_verdict,
            "current_winner": {"approach_id": current["approach_id"], "bundle_sha256": current["bundle_sha256"]},
            "allowed_paths": contract["allowed_paths"],
            "allowed_approach_ids": contract["approach_ids"],
        },
    )
    completed = _invoke(
        planner["command"],
        {"{python}": sys.executable, "{planner-adapter}": str(planner["path"]), "{planner-request}": str(request_path), "{planner-response}": str(response_path)},
        planner_root,
        "planner",
    )
    if completed.returncode or not response_path.is_file():
        raise RepairError("plan-repair", f"probe {probe_id!r} planner exited {completed.returncode}; return two or three declared approaches")
    plan = _validate_plan(_load(response_path, f"probe {probe_id!r} planner response", "plan-repair"), contract)
    build_root = round_root / probe_id / "repair-builds"
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(plan)) as pool:
        futures = {pool.submit(_build_one, approach, baseline, builder, build_root): approach["id"] for approach in plan}
        for future in as_completed(futures):
            result = future.result()
            results[result["approach"]["id"]] = result
    ordered = [results[item["id"]] for item in plan]
    problems = []
    for item in ordered:
        if item["returncode"] or not item["result"].is_file():
            problems.append(f"approach {item['approach']['id']!r} exited {item['returncode']} with {item['stderr']!r}; correct that builder")
        outside = sorted(set(item["changed_paths"]) - set(item["approach"]["allowed_paths"]))
        if outside:
            problems.append(f"approach {item['approach']['id']!r} changed {outside!r}; change only {item['approach']['allowed_paths']!r}")
    if problems:
        raise RepairError("build-repairs", "; ".join(problems))
    _, selected = _run_probe_experiment(
        round_root,
        probe,
        manifest,
        original_bundle,
        baseline,
        ordered,
        whole_paths["evaluators"][probe_id],
    )
    replacement = _repackage(round_root, probe, current, selected, original_bundle, whole_paths)
    return probe_id, replacement


def _compose_and_validate(
    round_root: Path,
    candidates: dict[str, Any],
    paths: dict[str, Any],
    normalized: dict[str, Any],
) -> dict[str, Any]:
    candidates_path = round_root / "promotion-candidates.json"
    _write_json(candidates_path, candidates)
    composition_request = round_root / "composition-request.json"
    _write_json(
        composition_request,
        {"schema_version": CONTRACT, "development_manifest": str(paths["manifest"]), "baseline": str(paths["baseline"]), "promotion_candidates": str(candidates_path)},
    )
    scripts = Path(__file__).parent
    composed = _invoke(
        ["{python}", "{script}", "run", "{request}", "{output}"],
        {"{python}": sys.executable, "{script}": str(scripts / "development_probe_compose.py"), "{request}": str(composition_request), "{output}": str(round_root / "composition")},
        round_root,
        "composition",
    )
    if composed.returncode:
        raise RepairError("compose-repair", f"repaired candidates did not compose: {composed.stderr.strip()}")
    validation_request = round_root / "validation-request.json"
    _write_json(
        validation_request,
        {
            "schema_version": CONTRACT,
            "assembly": str(round_root / "composition" / "assembly"),
            "assessment": {"adapter": str(paths["adapter"]), "command": normalized["assessment"]["command"]},
        },
    )
    validated = _invoke(
        ["{python}", "{script}", "run", "{request}", "{output}"],
        {"{python}": sys.executable, "{script}": str(scripts / "development_probe_final_validation.py"), "{request}": str(validation_request), "{output}": str(round_root / "validation")},
        round_root,
        "validation",
    )
    if validated.returncode:
        raise RepairError("validate-repair", f"repaired assembly validation failed mechanically: {validated.stderr.strip()}")
    result_path = round_root / "validation" / "final-verdict.json"
    receipt = {"result": "validation/final-verdict.json", "result_sha256": _digest(result_path.read_bytes())}
    return _bind_final_result(round_root, normalized, receipt)


def _terminal(
    output: Path,
    normalized: dict[str, Any],
    terminal: str,
    rounds: int,
    initial: str,
    verdict: dict[str, Any] | None,
    attempts: list[dict[str, Any]],
    error: str | None = None,
) -> dict[str, Any]:
    value = {
        "schema_version": CONTRACT,
        "status": "completed" if terminal == "passed" else "failed",
        "terminal": terminal,
        "atomic_step_id": normalized["atomic_step_id"],
        "rounds": rounds,
        "initial_verdict": initial,
        "final_verdict_sha256": None if verdict is None else _digest(_document(verdict)),
        "attempts": attempts,
        "error": error,
        "promotion_applied": False,
    }
    _write_json(output / "repair-summary.json", value)
    if verdict is not None:
        _write_bytes(output / "final-verdict.json", _document(verdict))
    return value


def run(request_path: Path, output: Path) -> dict[str, Any]:
    output = output.absolute()
    _prepare_output(output)
    normalized, context = _normalize(request_path.absolute())
    _write_json(output / "repair-request.json", normalized)
    initial_output = output / "initial"
    completed = _invoke(
        ["{python}", "{script}", "run", "{request}", "{output}"],
        {"{python}": sys.executable, "{script}": str(Path(__file__).parent / "development_probe_run.py"), "{request}": str(context["whole"]), "{output}": str(initial_output)},
        output,
        "initial",
    )
    if completed.returncode:
        raise RepairError("initial-run", f"initial Development-Probe run failed mechanically: {completed.stderr.strip()}")
    verdict = _load(initial_output / "final-verdict.json", "initial final verdict", "initial-run")
    if verdict["verdict"] == "passed":
        return _terminal(output, normalized, "passed", 0, "passed", verdict, [])
    candidate_path = initial_output / "probes" / "promotion-candidates.json"
    candidates = _absolutize_candidates(_load(candidate_path, "initial promotion candidates", "initial-run"), candidate_path)
    initial_verdict = verdict["verdict"]
    attempts = []
    for round_number in range(1, normalized["repair_budget"] + 1):
        round_root = output / "repairs" / f"{round_number:03d}"
        route = _model_route(verdict, context["manifest"], context["routing"], round_root)
        route_record = {
            "schema_version": CONTRACT,
            "status": "routed",
            "atomic_step_id": normalized["atomic_step_id"],
            **route,
            "failed_evidence": [{"path": str((initial_output if round_number == 1 else output / "repairs" / f"{round_number - 1:03d}") / "final-verdict.json"), "sha256": _digest(_document(verdict))}],
            "promotion_applied": False,
        }
        _write_json(round_root / "failure-route.json", route_record)
        if route["route_kind"] == "operator-decision":
            return _terminal(output, normalized, "operator-decision", round_number - 1, initial_verdict, None, attempts, route["reason"])
        if route["route_kind"] != "probes":
            return _terminal(output, normalized, "operator-decision", round_number - 1, initial_verdict, None, attempts, f"route {route['route_kind']!r} needs its declared boundary repair contract")
        contracts = {}
        for probe_id in route["probe_ids"]:
            contract = context["repairs"].get(probe_id)
            if contract is None:
                raise RepairError("repair-probe", f"failed probe {probe_id!r} has no probe_repairs contract; add its allowed paths and approaches")
            contracts[probe_id] = contract
        replacements = {}
        with ThreadPoolExecutor(max_workers=min(4, len(route["probe_ids"]))) as pool:
            futures = {
                pool.submit(
                    _repair_probe,
                    round_root,
                    probe_id,
                    candidates,
                    context["manifest"],
                    contracts[probe_id],
                    context["planner"],
                    context["builder"],
                    context["whole_paths"],
                    verdict,
                ): probe_id
                for probe_id in route["probe_ids"]
            }
            for future in as_completed(futures):
                probe_id, replacement = future.result()
                replacements[probe_id] = replacement
        candidates["candidates"] = [
            replacements.get(item["probe_id"], item) for item in candidates["candidates"]
        ]
        verdict = _compose_and_validate(round_root, candidates, context["whole_paths"], context["whole_normalized"])
        attempts.append({"round": round_number, "route": route_record, "verdict": verdict["verdict"], "final_verdict_sha256": _digest(_document(verdict))})
        if verdict["verdict"] == "passed":
            return _terminal(output, normalized, "passed", round_number, initial_verdict, verdict, attempts)
    return _terminal(output, normalized, "repair-budget-exhausted", normalized["repair_budget"], initial_verdict, verdict, attempts, f"repair budget {normalized['repair_budget']} exhausted with verdict {verdict['verdict']!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("request", type=Path)
    run_parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.request, args.output)
    except (RepairError, OSError, KeyError, TypeError) as error:
        stage = error.stage if isinstance(error, RepairError) else "repair-loop"
        output = args.output.absolute()
        if output.exists() and output.is_dir() and not (output / "repair-summary.json").exists():
            try:
                _write_json(output / "repair-summary.json", {"schema_version": CONTRACT, "status": "failed", "stage": stage, "error": str(error), "promotion_applied": False})
            except OSError:
                pass
        print(f"Development-Probe repair refused at {stage}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["terminal"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
