#!/usr/bin/env python3
"""Run the two frozen source-only route observations through Atlas production APIs."""

import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "codebase-atlas-machinery" / "scripts"
if os.fspath(SCRIPTS) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPTS))

import route_autorun
import route_coordinator

SCHEMA_VERSION = 1
CONTEXTUAL_REFUSAL_REPOSITORY_ROOT = "/Users/kamenkamenov/taggable-api"
EXPECTED_REFUSAL = (
    "reviewed-flow source path/hash/span does not match fact f1dbca9ceb43bd9d180613e0"
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _read_case(path):
    raw = Path(path).read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("input must be one schema_version 1 case JSON object")
    case_id = value.get("case_id")
    if case_id == "one-open-operators-route":
        identity = value.get("captured_input", {}).get("identity")
        route = value.get("captured_input", {}).get("route")
        if not isinstance(identity, dict) or not isinstance(identity.get("repository_root"), str):
            raise ValueError("operators case must contain captured_input.identity.repository_root")
        if not isinstance(route, dict) or not isinstance(route.get("fact_id"), str):
            raise ValueError("operators case must contain captured_input.route.fact_id")
    elif case_id == "contextual-citation-refusal":
        if not isinstance(value.get("route_fact_id"), str) or not value["route_fact_id"]:
            raise ValueError("refusal case must contain its top-level route_fact_id")
        if not isinstance(value.get("draft"), dict):
            raise ValueError("refusal case must contain its exact top-level draft object")
    else:
        raise ValueError("input case_id is not one of the two frozen route cases")
    return value, raw


def _target(case):
    if case["case_id"] == "one-open-operators-route":
        return case["captured_input"]["identity"]["repository_root"], case["captured_input"]["route"]["fact_id"]
    return CONTEXTUAL_REFUSAL_REPOSITORY_ROOT, case["route_fact_id"]


def _index(repo, db, workdir):
    command = [sys.executable, os.fspath(SCRIPTS / "atlas.py"), "index",
               "--repo", repo, "--db", os.fspath(db)]
    result = subprocess.run(command, cwd=workdir, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    stdout_path = workdir / "public-index.stdout"
    stderr_path = workdir / "public-index.stderr"
    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    identity = {}
    if result.returncode == 0:
        indexed = json.loads(result.stdout.decode("utf-8"))
        if not isinstance(indexed, dict) or not isinstance(indexed.get("snapshot_id"), str):
            raise RuntimeError("public Atlas index did not return a saved snapshot identity")
        identity = {key: indexed.get(key) for key in (
            "snapshot_id", "repository_root", "head", "head_ref", "inventory_basis", "tracked_count")}
    return {
        "argv": command,
        "returncode": result.returncode,
        "stdout_evidence": {"path": os.fspath(stdout_path), "sha256": _sha(result.stdout), "bytes": len(result.stdout)},
        "stderr_evidence": {"path": os.fspath(stderr_path), "sha256": _sha(result.stderr), "bytes": len(result.stderr)},
        "identity": identity,
        "database_path": os.fspath(db),
    }


def _collect_files(root):
    collected = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: os.fsencode(item.as_posix())):
        raw = path.read_bytes()
        collected.append({
            "path": os.fspath(path),
            "sha256": _sha(raw),
            "bytes": len(raw),
            "text": raw.decode("utf-8", "replace"),
        })
    return collected


def _worker_spy():
    original = route_autorun.run_worker
    calls = []

    def observed(*args, **kwargs):
        calls.append({"role": args[0] if args else kwargs.get("role")})
        return original(*args, **kwargs)

    route_autorun.run_worker = observed
    return original, calls


def _run_operators(repo, db, route_id, workdir, observations):
    job = workdir / "route-job"
    original, calls = _worker_spy()
    try:
        result = route_autorun.run_once(repo, os.fspath(db), route_id, os.fspath(job))
    finally:
        route_autorun.run_worker = original
    observations["run_once"] = result
    observations["worker_calls"] = calls
    if len(calls) != 2:
        raise RuntimeError(f"run_once returned without two observed production worker calls: {len(calls)}")
    if result.get("result") != "published_and_fresh" or result.get("status", {}).get("result") != "published_and_fresh":
        raise RuntimeError("run_once did not return a fresh published route result")
    if result.get("luna", {}).get("model") != "gpt-6-luna" or result.get("sol", {}).get("model") != "gpt-6.1-sol":
        raise RuntimeError("run_once worker results do not carry the production Luna and Sol role identities")
    if result.get("luna", {}).get("thread_id") == result.get("sol", {}).get("thread_id"):
        raise RuntimeError("run_once worker calls did not return distinct thread identities")

    original, same_job_calls = _worker_spy()
    caught = None
    try:
        route_autorun.run_once(repo, os.fspath(db), route_id, os.fspath(job))
    except FileExistsError as exc:
        caught = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        route_autorun.run_worker = original
    observations["same_job_refusal"] = {"caught": caught, "worker_calls": same_job_calls}
    if caught is None or same_job_calls:
        raise RuntimeError("same-job invocation did not refuse before an additional worker call")
    observations["observation_kind"] = "one_route_published_and_fresh_with_existing_job_refusal"


def _run_refusal(repo, db, route_id, case, workdir, observations):
    run_dir = workdir / "route-job" / "coordinator"
    run_dir.mkdir(parents=True, exist_ok=False)
    prepared = route_coordinator.prepare(repo, os.fspath(db), route_id, os.fspath(run_dir))
    observations["coordinator_prepare"] = prepared
    if prepared.get("result") != "prepared":
        raise RuntimeError("canonical route coordinator did not prepare the refusal case")

    proof_dir = workdir / "negative-proof"
    proof_dir.mkdir(parents=True, exist_ok=False)

    def save_proof(name, raw):
        path = proof_dir / name
        path.write_bytes(raw)
        return {"path": os.fspath(path), "sha256": _sha(raw), "bytes": len(raw)}

    draft_raw = _canonical(case["draft"])
    draft_path = workdir / "captured-wrong-context-draft.json"
    draft_path.write_bytes(draft_raw)
    observations["captured_draft"] = {
        "source_identity": case.get("draft_source"),
        "input_identity": case.get("context_source"),
        "semantic_object": case["draft"],
        "materialized_path": os.fspath(draft_path),
        "materialized_sha256": _sha(draft_raw),
        "materialized_bytes": len(draft_raw),
    }
    draft_before_raw = draft_path.read_bytes()
    db_before_raw = db.read_bytes()
    observations["captured_draft"]["before_snapshot"] = save_proof("draft-before.json", draft_before_raw)
    observations["database_before_snapshot"] = save_proof("database-before.sqlite", db_before_raw)

    original, calls = _worker_spy()
    original_subprocess_run = route_coordinator.subprocess.run
    subprocess_calls = []

    def observed_subprocess_run(*args, **kwargs):
        result = original_subprocess_run(*args, **kwargs)
        argv = args[0] if args else kwargs.get("args")
        call_index = len(subprocess_calls)
        call_name = f"subprocess-{call_index:02d}.json"
        stdout_raw = result.stdout.encode("utf-8") if isinstance(result.stdout, str) else result.stdout
        stderr_raw = result.stderr.encode("utf-8") if isinstance(result.stderr, str) else result.stderr
        stdout_name = f"subprocess-{call_index:02d}.stdout.txt"
        stderr_name = f"subprocess-{call_index:02d}.stderr.txt"
        stdout_evidence = save_proof(stdout_name, stdout_raw)
        stderr_evidence = save_proof(stderr_name, stderr_raw)
        record = {
            "argv": argv,
            "returncode": result.returncode,
            "stdout_sha256": _sha(stdout_raw),
            "stdout_bytes": len(stdout_raw),
            "stderr_sha256": _sha(stderr_raw),
            "stderr_bytes": len(stderr_raw),
            "stdout_evidence": stdout_evidence,
            "stderr_evidence": stderr_evidence,
            "artifact": call_name,
        }
        save_proof(call_name, _canonical({
            **record,
            "stdout_base64": base64.b64encode(stdout_raw).decode("ascii"),
            "stderr_base64": base64.b64encode(stderr_raw).decode("ascii"),
        }))
        subprocess_calls.append(record)
        return result

    refusal = None
    try:
        route_coordinator.subprocess.run = observed_subprocess_run
        route_coordinator.draft(repo, os.fspath(db), route_id, os.fspath(run_dir), os.fspath(draft_path))
    except route_coordinator.CoordinatorError as exc:
        refusal = str(exc)
    finally:
        route_coordinator.subprocess.run = original_subprocess_run
        route_autorun.run_worker = original
    draft_after_raw = draft_path.read_bytes()
    db_after_raw = db.read_bytes()
    observations["captured_draft"]["after_snapshot"] = save_proof("draft-after.json", draft_after_raw)
    observations["database_after_snapshot"] = save_proof("database-after.sqlite", db_after_raw)
    observations["captured_draft"]["before_sha256"] = _sha(draft_before_raw)
    observations["captured_draft"]["before_bytes"] = len(draft_before_raw)
    observations["captured_draft"]["after_sha256"] = _sha(draft_after_raw)
    observations["captured_draft"]["after_bytes"] = len(draft_after_raw)
    observations["database_sha256_before_refusal"] = _sha(db_before_raw)
    observations["database_bytes_before_refusal"] = len(db_before_raw)
    observations["database_sha256_after_refusal"] = _sha(db_after_raw)
    observations["database_bytes_after_refusal"] = len(db_after_raw)
    observations["canonical_refusal"] = refusal
    observations["canonical_refusal_exact"] = isinstance(refusal, str) and refusal.endswith(EXPECTED_REFUSAL)
    observations["database_unchanged"] = db_before_raw == db_after_raw
    observations["captured_draft"]["unchanged_after_attempt"] = draft_before_raw == draft_after_raw
    observations["worker_calls"] = calls
    observations["subprocess_calls"] = subprocess_calls
    save_proof("worker-calls.json", _canonical(calls))
    operator_source = Path(__file__).read_bytes()
    save_proof("executing-operator.py", operator_source)
    observations["coordinator_status"] = route_coordinator.status(repo, os.fspath(db), route_id, os.fspath(run_dir))
    if (not observations["canonical_refusal_exact"] or not observations["database_unchanged"]
            or not observations["captured_draft"]["unchanged_after_attempt"] or calls):
        raise RuntimeError("canonical citation refusal or its preservation observations did not match the frozen case")
    negative_proof = {
        "artifact_paths": {},
        "artifact_sha256": {},
        "artifact_bytes": {},
    }
    observations["negative_proof"] = negative_proof
    for path in sorted(proof_dir.iterdir(), key=lambda item: os.fsencode(item.name)):
        raw = path.read_bytes()
        negative_proof["artifact_paths"][path.name] = os.fspath(path)
        negative_proof["artifact_sha256"][path.name] = _sha(raw)
        negative_proof["artifact_bytes"][path.name] = len(raw)
    observations["observation_kind"] = "canonical_citation_refusal_source_only"


def run_once(case_path, result_path, telemetry_path):
    workdir_value = os.environ.get("EXPERIMENT_WORK_DIR")
    if not workdir_value:
        raise ValueError("EXPERIMENT_WORK_DIR must name the experiment work directory")
    workdir = Path(workdir_value).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    case, case_raw = _read_case(case_path)
    repo, route_id = _target(case)
    repo_path = Path(repo).expanduser().resolve(strict=True)
    if not repo_path.is_dir():
        raise ValueError("target repository root must be an existing directory")
    if workdir == repo_path or workdir.is_relative_to(repo_path) or repo_path.is_relative_to(workdir):
        raise ValueError("experiment workdir and target repository must not overlap")
    db = workdir / "atlas.sqlite"
    run_dir = workdir / "route-job"
    if db.exists() or db.is_symlink() or run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError("experiment workdir already contains atlas.sqlite or route-job")

    observations = {
        "case_id": case["case_id"],
        "input_sha256": _sha(case_raw),
        "case_source_capture": case.get("source_capture"),
        "case_source_packet": case.get("source_packet"),
        "target_repository": repo,
        "route_fact_id": route_id,
        "database_path": os.fspath(db),
        "worker_calls": [],
        "publication": None,
    }
    indexed = _index(repo, db, workdir)
    observations["public_index"] = indexed
    if indexed["returncode"] != 0:
        raise RuntimeError("public Atlas index returned a nonzero exit status")

    if case["case_id"] == "one-open-operators-route":
        _run_operators(repo, db, route_id, workdir, observations)
    else:
        _run_refusal(repo, db, route_id, case, workdir, observations)
    observations["database_sha256_after_route_steps"] = _sha(db.read_bytes())
    observations["coordinator_artifacts"] = _collect_files(run_dir) if run_dir.exists() else []
    observations["artifact_paths"] = {
        Path(item["path"]).relative_to(run_dir).as_posix(): item["path"]
        for item in observations["coordinator_artifacts"]
    }
    observations["artifact_sha256"] = {
        Path(item["path"]).relative_to(run_dir).as_posix(): item["sha256"]
        for item in observations["coordinator_artifacts"]
    }
    return observations


def _write_result(path, value):
    Path(path).write_bytes(_canonical(value))


def _append_telemetry(path, variant_id, event, message, observations, evidence_raw, correction=None):
    entry = {
        "schema_version": 1,
        "sequence": int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1")),
        "variant_id": variant_id,
        "event": event,
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "message": message,
        "evidence_sha256": _sha(evidence_raw),
        "observations": {"raw_observations": observations},
    }
    if correction is not None:
        entry["correction"] = correction
    with Path(path).open("ab") as stream:
        stream.write(_canonical(entry))


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        print("usage: test_codebase_atlas_route_autorun.py FROZEN-INPUT RESULT-PATH TELEMETRY-PATH", file=sys.stderr)
        return 2
    case_path, result_path, telemetry_path = args
    variant_id = os.environ.get("EXPERIMENT_VARIANT_ID")
    if not variant_id:
        print("EXPERIMENT_VARIANT_ID is required", file=sys.stderr)
        return 2
    try:
        observations = run_once(case_path, result_path, telemetry_path)
        result = {"schema_version": SCHEMA_VERSION, "variant_id": variant_id,
                  "status": "completed", "outcome": {"raw_observations": observations},
                  "metrics": {}, "error": None}
        _write_result(result_path, result)
        _append_telemetry(telemetry_path, variant_id, "decision_recorded",
                          observations["observation_kind"], observations, _canonical(observations))
        sys.stdout.buffer.write(_canonical(observations))
        return 0
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc),
                 "traceback": traceback.format_exc()}
        result = {"schema_version": SCHEMA_VERSION, "variant_id": variant_id,
                  "status": "failed", "outcome": {"raw_observations": {}},
                  "metrics": {}, "error": str(exc)}
        try:
            _write_result(result_path, result)
            _append_telemetry(telemetry_path, variant_id, "operator_error",
                              str(exc), {}, _canonical(error),
                              correction="Correct the frozen input or experiment workdir and rerun.")
        except Exception as recording_error:
            print(f"operator error: {exc}; result recording failed: {recording_error}", file=sys.stderr)
        print(f"operator error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
