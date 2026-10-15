#!/usr/bin/env python3
"""Capture real selected-batch, resume, and interruption observations."""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "codebase-atlas-machinery" / "scripts"
DRIVER = SCRIPTS / "route_batch_autorun.py"
ATLAS = SCRIPTS / "atlas.py"
CASE_IDS = ("6a6195854838e8590c4981d4", "a2a9cab121ad67c25c3f04cb")
EXPECTED_DRIVER_SHA256 = "178fff12acd2d258bc72df6fb20cda1e1b60c83d40f3d79f3fd02e6af664e759"
EXPECTED_C5_SHA256 = "31b96ec3a738a928663852451b9795b8a43df3212687d648364b8add6a9dd4d3"
SCHEMA_VERSION = 1


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _read_case(path):
    raw = Path(path).read_bytes()
    case = json.loads(raw.decode("utf-8"))
    if (not isinstance(case, dict) or case.get("schema_version") != 1
            or case.get("ordered_route_ids") != list(CASE_IDS)
            or case.get("case_id") not in {"batch-complete-and-resume", "batch-interruption-safety"}):
        raise ValueError("input is not one of the exact frozen two-route batch cases")
    if not isinstance(case.get("repository_root"), str) or not Path(case["repository_root"]).is_absolute():
        raise ValueError("frozen case repository_root must be an absolute path")
    return case, raw


def _inside(root, path):
    try:
        return Path(path).resolve(strict=False).is_relative_to(root.resolve(strict=False))
    except (OSError, ValueError):
        return False


class Evidence:
    """Write exact observed bytes outside product state and retain paired references."""

    def __init__(self, root):
        self.root = root / "evidence"
        self.root.mkdir(parents=True, exist_ok=False)
        self.paths = {}
        self.hashes = {}
        self.sizes = {}
        self.excluded = set()
        self.counter = 0

    def save(self, label, raw, suffix=".bin"):
        self.counter += 1
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)[:48]
        name = f"{self.counter:04d}-{safe}{suffix}"
        path = self.root / name
        path.write_bytes(raw)
        self.paths[name] = os.fspath(path)
        self.hashes[name] = _sha(raw)
        self.sizes[name] = len(raw)
        return {"path": os.fspath(path), "sha256": _sha(raw), "bytes": len(raw)}

    def save_file(self, label, path):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            return {"observed_path": os.fspath(path), "available": False}
        raw = path.read_bytes()
        ref = self.save(label, raw, path.suffix or ".bin")
        ref["observed_path"] = os.fspath(path)
        return ref

    def paired(self):
        return {"artifact_paths": {name: path for name, path in self.paths.items() if name not in self.excluded},
                "artifact_sha256": {name: digest for name, digest in self.hashes.items() if name not in self.excluded}}


def _command(evidence, label, argv, cwd, env=None, timeout=1800):
    start = time.monotonic_ns()
    try:
        completed = subprocess.run(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, check=False, timeout=timeout)
        out, err, code = completed.stdout, completed.stderr, completed.returncode
        error = None
    except Exception as exc:
        out, err, code = b"", str(exc).encode("utf-8", "replace"), None
        error = {"type": type(exc).__name__, "message": str(exc)}
    stdout_ref = evidence.save(label + "-stdout", out, ".stdout")
    stderr_ref = evidence.save(label + "-stderr", err, ".stderr")
    return {"argv": list(argv), "cwd": os.fspath(cwd), "returncode": code,
            "stdout": stdout_ref, "stderr": stderr_ref,
            "elapsed_ns": time.monotonic_ns() - start, "error": error}


def _env():
    value = os.environ.copy()
    value["PYTHONDONTWRITEBYTECODE"] = "1"
    return value


def _index(case, work, evidence):
    repo = case["repository_root"]
    db = work / "atlas.sqlite"
    command = _command(evidence, "public-index", [sys.executable, os.fspath(ATLAS), "index",
                        "--repo", repo, "--db", os.fspath(db)], work, _env())
    identity = {}
    if command["returncode"] == 0:
        indexed = json.loads(Path(command["stdout"]["path"]).read_bytes().decode("utf-8"))
        if not isinstance(indexed, dict):
            raise ValueError("public Atlas index returned a non-object")
        identity = {key: indexed.get(key) for key in (
            "snapshot_id", "repository_root", "head", "head_ref", "inventory_basis", "tracked_count",
            "extractor_identity")}
        raw_stdout_ref = command["stdout"]
        evidence.excluded.add(Path(raw_stdout_ref["path"]).name)
        command["stdout"] = {"actual_path": raw_stdout_ref["path"], "sha256": raw_stdout_ref["sha256"],
                             "bytes": raw_stdout_ref["bytes"], "identity": identity}
    db_ref = evidence.save_file("indexed-database", db)
    return {"command": command, "identity": identity, "database_path": os.fspath(db),
            "database_artifact": db_ref}, db


def _inventory(evidence, root, label):
    result = {}
    if not root.exists():
        return result
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: os.fsencode(p.as_posix())):
        relative = path.relative_to(root).as_posix()
        result[relative] = evidence.save_file(label + "-" + relative, path)
    return result


def _load_modules():
    if os.fspath(SCRIPTS) not in sys.path:
        sys.path.insert(0, os.fspath(SCRIPTS))
    import atlas
    import route_batch
    import route_coordinator
    return atlas, route_coordinator, route_batch


def _native_queries(case, db, batch, evidence):
    atlas, coordinator, _route_batch = _load_modules()
    values = {"route_find": {}, "coordinator_status": {}}
    for route_id in CASE_IDS:
        try:
            result = atlas.route_find(os.fspath(db), case["repository_root"], route_id, 2_147_483_647)
            if isinstance(result, tuple) and len(result) == 3:
                value, encoded, code = result
                values["route_find"][route_id] = {"value": value, "returncode": code,
                    "encoded": evidence.save("route-find-" + route_id, encoded, ".json")}
            else:
                values["route_find"][route_id] = {"raw_return": repr(result)}
        except Exception as exc:
            values["route_find"][route_id] = {"error": {"type": type(exc).__name__, "message": str(exc)}}
        coord_dir = batch / f"job-{CASE_IDS.index(route_id) + 1:02d}-{route_id}" / "coordinator"
        try:
            status = coordinator.status(case["repository_root"], os.fspath(db), route_id, os.fspath(coord_dir))
            values["coordinator_status"][route_id] = status
        except Exception as exc:
            values["coordinator_status"][route_id] = {"error": {"type": type(exc).__name__, "message": str(exc)}}
    return values


def _cli_argv(case, db, batch):
    argv = [sys.executable, os.fspath(DRIVER), "--repo", case["repository_root"],
            "--db", os.fspath(db), "--run-dir", os.fspath(batch)]
    for route_id in CASE_IDS:
        argv.extend(("--route-id", route_id))
    return argv


def _checkpoint(batch):
    path = batch / "batch-autorun.json"
    if not path.is_file() or path.is_symlink():
        return {"available": False, "path": os.fspath(path)}
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = None
    return {"available": True, "path": os.fspath(path), "sha256": _sha(raw),
            "bytes": len(raw), "value": value}


def _driver_sources(evidence):
    driver_ref = evidence.save_file("executing-batch-driver", DRIVER)
    result = {"driver": driver_ref, "driver_authoring_baseline_sha256": EXPECTED_DRIVER_SHA256,
              "driver_comparison_to_authoring_baseline": driver_ref.get("sha256") == EXPECTED_DRIVER_SHA256}
    c5 = SCRIPTS / "route_autorun.py"
    result["c5"] = evidence.save_file("immutable-c5-worker-source", c5)
    result["c5_authoring_baseline_sha256"] = EXPECTED_C5_SHA256
    result["c5_comparison_to_authoring_baseline"] = result["c5"].get("sha256") == EXPECTED_C5_SHA256
    return result


def _run_public(case, db, batch, work, evidence, label, timeout=1800):
    argv = _cli_argv(case, db, batch)
    database_before = evidence.save_file(label + "-database-before", db)
    before = {"checkpoint": _checkpoint(batch), "files": _inventory(evidence, batch, label + "-before"),
              "database": database_before}
    command = _command(evidence, label + "-public-cli", argv, work, _env(), timeout)
    database_after = evidence.save_file(label + "-database-after", db)
    after = {"checkpoint": _checkpoint(batch), "files": _inventory(evidence, batch, label + "-after"),
             "database": database_after}
    return {"command": command, "before": before, "after": after}


def _complete_case(case, db, batch, work, evidence):
    first = _run_public(case, db, batch, work, evidence, "initial-batch")
    queries_after_first = _native_queries(case, db, batch, evidence)
    resume = _run_public(case, db, batch, work, evidence, "completed-resume")
    queries_after_resume = _native_queries(case, db, batch, evidence)
    return {"initial_execution": first, "source_queries_after_initial": queries_after_first,
            "identical_resume": resume, "source_queries_after_resume": queries_after_resume,
            "final_checkpoint": _checkpoint(batch)}


def _wrapper_source(driver_path, repo, db, batch, receipt):
    return f'''import importlib.util, json, os, sys
from pathlib import Path
path = Path({str(driver_path)!r})
spec = importlib.util.spec_from_file_location("frozen_batch_driver", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
original = module._batch_atomic
batch = Path({str(batch)!r})
receipt = Path({str(receipt)!r})
selected = {list(CASE_IDS)!r}
def observed(path, value):
    original(path, value)
    if path.name != module.BATCH_MANIFEST:
        return
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    routes = saved.get("routes")
    if not isinstance(routes, list) or [r.get("route_fact_id") for r in routes if isinstance(r, dict)] != selected:
        return
    first, second = routes
    if first.get("state") != "completed" or second.get("state") != "pending":
        return
    raw = path.read_bytes()
    receipt.write_text(json.dumps({{"manifest_path": str(path), "manifest_sha256": __import__("hashlib").sha256(raw).hexdigest(), "manifest_bytes": len(raw), "manifest": saved}}, sort_keys=True), encoding="utf-8")
    os._exit(73)
module._batch_atomic = observed
raise SystemExit(module.main(["--repo", {repo!r}, "--db", {os.fspath(db)!r}, "--run-dir", {str(batch)!r}, "--route-id", selected[0], "--route-id", selected[1]]))
'''


def _interrupt_between(case, db, batch, work, evidence):
    receipt_path = work / "first-completion-fault-receipt.json"
    wrapper = _wrapper_source(DRIVER, case["repository_root"], db, batch, receipt_path)
    wrapper_ref = evidence.save("pass-through-atomic-wrapper-source", wrapper.encode("utf-8"), ".py")
    wrapper_path = work / "pass-through-atomic-wrapper.py"
    wrapper_path.write_text(wrapper, encoding="utf-8")
    database_before = evidence.save_file("between-database-before-invocation", db)
    before = {"checkpoint": _checkpoint(batch), "files": _inventory(evidence, batch, "between-before"),
              "database": database_before}
    child = _command(evidence, "between-route-instrumented-public-main",
                     [sys.executable, os.fspath(wrapper_path)], work, _env(), 3600)
    database_after_termination = evidence.save_file("between-database-after-termination", db)
    receipt_ref = evidence.save_file("actual-first-completion-fault-receipt", receipt_path)
    receipt_value = None
    if receipt_path.is_file():
        try:
            receipt_value = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    interrupted = {"wrapper_source": wrapper_ref, "wrapper_argv": [sys.executable, os.fspath(wrapper_path)],
                   "child": child, "receipt": receipt_ref, "receipt_value": receipt_value,
                   "checkpoint_after_termination": _checkpoint(batch),
                   "database_after_termination": database_after_termination,
                   "second_job_exists": (batch / f"job-02-{CASE_IDS[1]}").exists()}
    after_interruption = _inventory(evidence, batch, "between-interrupted-state")
    resumed = _run_public(case, db, batch, work, evidence, "between-route-uninstrumented-resume")
    return {"before": before, "actual_interruption": interrupted,
            "interrupted_state_files": after_interruption, "identical_uninstrumented_resume": resumed,
            "source_queries_after_resume": _native_queries(case, db, batch, evidence),
            "final_checkpoint": _checkpoint(batch)}


def _worker_started_unfinished(job):
    events = job / "luna" / "events.jsonl"
    argv = job / "luna" / "argv.json"
    if not argv.is_file() or not events.is_file():
        return None
    try:
        lines = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    thread_started = any(isinstance(item, dict) and item.get("type") == "thread.started" for item in lines)
    turn_started = any(isinstance(item, dict) and item.get("type") == "turn.started" for item in lines)
    terminal = any(isinstance(item, dict) and item.get("type") in {"turn.completed", "turn.failed", "turn.cancelled"} for item in lines)
    if not thread_started or not turn_started or terminal:
        return None
    return {"argv_path": os.fspath(argv), "events_path": os.fspath(events),
            "events": lines, "argv": json.loads(argv.read_text(encoding="utf-8"))}


def _interrupt_inflight(case, db, batch, work, evidence):
    argv = _cli_argv(case, db, batch)
    database_before = evidence.save_file("inflight-database-before-invocation", db)
    before = {"checkpoint": _checkpoint(batch), "files": _inventory(evidence, batch, "inflight-before"),
              "database": database_before}
    process = subprocess.Popen(argv, cwd=work, env=_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    job = batch / f"job-02-{CASE_IDS[1]}"
    observed = None
    deadline = time.monotonic() + 3600
    while time.monotonic() < deadline and process.poll() is None:
        observed = _worker_started_unfinished(job)
        if observed is not None and _checkpoint(batch).get("value", {}).get("routes", [{}])[0].get("state") == "completed":
            break
        time.sleep(0.1)
    if observed is not None and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            signal_sent = signal.SIGKILL
        except ProcessLookupError:
            signal_sent = None
        try:
            stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            stdout, stderr = b"", b"process group kill did not reap the public CLI"
    else:
        signal_sent = None
        try:
            stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
    database_after_kill = evidence.save_file("inflight-database-after-process-stop", db)
    raw_process = {"argv": argv, "pid": process.pid, "signal_sent": signal_sent,
                   "returncode": process.returncode, "observed_unfinished_worker": observed,
                   "database_after_process_stop": database_after_kill,
                   "stdout": evidence.save("inflight-killed-cli-stdout", stdout, ".stdout"),
                   "stderr": evidence.save("inflight-killed-cli-stderr", stderr, ".stderr")}
    if observed is not None:
        raw_process["unfinished_worker_argv"] = evidence.save_file("unfinished-worker-argv", observed["argv_path"])
        raw_process["unfinished_worker_events"] = evidence.save_file("unfinished-worker-events", observed["events_path"])
    uncertain = {"checkpoint": _checkpoint(batch), "files": _inventory(evidence, batch, "inflight-after-kill")}
    resumed = _run_public(case, db, batch, work, evidence, "inflight-uncertain-uninstrumented-resume")
    return {"before": before, "actual_process": raw_process, "uncertain_state": uncertain,
            "identical_uninstrumented_resume": resumed,
            "source_queries_after_resume": _native_queries(case, db, batch, evidence),
            "final_checkpoint": _checkpoint(batch)}


def _control_case(case, db, work, evidence):
    _atlas, _coordinator, route_batch = _load_modules()
    batch = work / "native-batch-control"
    before = db.read_bytes()
    database_before = evidence.save("control-database-before", before, ".sqlite")
    try:
        prepared = route_batch.prepare(case["repository_root"], os.fspath(db), list(CASE_IDS), os.fspath(batch))
        status = route_batch.status(os.fspath(batch))
    except Exception as exc:
        prepared = {"error": {"type": type(exc).__name__, "message": str(exc)}}
        status = None
    after = db.read_bytes()
    database_after = evidence.save("control-database-after", after, ".sqlite")
    return {"capability": "native route_batch prepare/status control; no worker dispatch",
            "prepare": prepared, "status": status,
            "batch_artifacts": _inventory(evidence, batch, "native-control"),
            "database_before": database_before, "database_after": database_after,
            "database_unchanged": before == after}


def execute(case_path):
    work_value = os.environ.get("EXPERIMENT_WORK_DIR")
    if not work_value:
        raise ValueError("EXPERIMENT_WORK_DIR must name an isolated experiment workdir")
    allocated_work = Path(work_value).expanduser()
    if allocated_work.is_symlink() or not allocated_work.is_dir():
        raise ValueError("EXPERIMENT_WORK_DIR must name an existing allocated directory")
    allocated_work = allocated_work.resolve()
    case, case_raw = _read_case(case_path)
    repo = Path(case["repository_root"]).expanduser().resolve(strict=True)
    if not repo.is_dir() or _inside(repo, allocated_work) or _inside(allocated_work, repo):
        raise ValueError("frozen target and experiment workdir must be existing, separate directories")
    work = allocated_work / "batch-autorun-operator"
    if work.is_symlink() or work.exists():
        raise FileExistsError(f"operator workdir must be fresh and exclusive: {work}")
    work.mkdir(exist_ok=False)
    evidence = Evidence(work)
    obs = {"case_id": case["case_id"], "case_input": evidence.save("exact-frozen-case-input", case_raw, ".json"),
           "case_identity": {key: case.get(key) for key in ("case_id", "schema_version", "snapshot_id", "extractor_identity", "ordered_route_ids", "repository_root", "expected_after", "test_recipe")},
           "target_repository": os.fspath(repo), "selected_route_ids": list(CASE_IDS),
           "executing_operator": evidence.save_file("executing-operator-source", Path(__file__)),
           "immutable_sources": _driver_sources(evidence)}
    db = work / "atlas.sqlite"
    batch = work / "batch-run"
    indexed, db = _index(case, work, evidence)
    obs["public_index"] = indexed
    if indexed["command"]["returncode"] != 0:
        obs["execution_error"] = "public Atlas source-only index returned nonzero"
        return obs
    identity = indexed["identity"]
    obs["identity_comparison"] = {"snapshot_id_matches": identity.get("snapshot_id") == case.get("snapshot_id"),
        "extractor_identity_matches": identity.get("extractor_identity") == case.get("extractor_identity"),
        "repository_root_matches": identity.get("repository_root") == os.fspath(repo)}
    if not DRIVER.is_file():
        obs["native_control"] = _control_case(case, db, work, evidence)
    elif case["case_id"] == "batch-complete-and-resume":
        obs["batch_experiment"] = _complete_case(case, db, batch, work, evidence)
    else:
        obs["between_route_interruption"] = _interrupt_between(case, db, batch, work, evidence)
        inflight_work = work / "inflight-work"
        inflight_work.mkdir()
        inflight_index, inflight_db = _index(case, inflight_work, evidence)
        obs["inflight_public_index"] = inflight_index
        inflight_batch = inflight_work / "inflight-batch"
        obs["inflight_interruption"] = _interrupt_inflight(case, inflight_db, inflight_batch,
                                                            inflight_work, evidence)
    obs["database_after_all_steps"] = evidence.save_file("database-after-all-steps", db)
    obs.update(evidence.paired())
    return obs


def _write_result(path, value):
    Path(path).write_bytes(_canonical(value) + b"\n")


def _telemetry(path, variant, sequence, event, message, observations, evidence_sha, correction=None):
    entry = {"schema_version": 1, "sequence": sequence, "variant_id": variant,
             "event": event, "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
             "message": message, "evidence_sha256": evidence_sha,
             "observations": {"raw_observations": observations}}
    if correction is not None:
        entry["correction"] = correction
    with Path(path).open("ab") as stream:
        stream.write(_canonical(entry) + b"\n")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        print("usage: test_codebase_atlas_batch_autorun.py FROZEN-INPUT RESULT-FILE TELEMETRY-JSONL", file=sys.stderr)
        return 2
    case_path, result_path, telemetry_path = args
    variant = os.environ.get("EXPERIMENT_VARIANT_ID")
    if not variant:
        print("EXPERIMENT_VARIANT_ID is required", file=sys.stderr)
        return 2
    try:
        observations = execute(case_path)
        evidence_raw = _canonical(observations)
        result = {"schema_version": SCHEMA_VERSION, "variant_id": variant,
                  "status": "completed", "outcome": {"raw_observations": observations},
                  "metrics": {}, "error": None}
        _write_result(result_path, result)
        sequence = int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1"))
        _telemetry(telemetry_path, variant, sequence, "decision_recorded",
                   "actual selected-batch execution observations recorded", observations, _sha(evidence_raw))
        sys.stdout.buffer.write(_canonical(observations) + b"\n")
        return 0
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        result = {"schema_version": SCHEMA_VERSION, "variant_id": variant,
                  "status": "failed", "outcome": {"raw_observations": {}},
                  "metrics": {}, "error": error["message"]}
        try:
            _write_result(result_path, result)
            sequence = int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1"))
            correction = (
                f"Allocate a new framework-owned experiment work directory and preserve the existing operator child identified by {error['message']}."
                if isinstance(exc, FileExistsError) and "operator workdir must be fresh and exclusive" in str(exc)
                else f"Correct the recorded {error['type']} at {error['message']} and rerun in a fresh framework-allocated experiment work directory."
            )
            _telemetry(telemetry_path, variant, sequence, "operator_error", error["message"],
                       {"error": error}, _sha(_canonical(error)), correction=correction)
        except Exception as record_error:
            print(f"operator error: {exc}; recording error: {record_error}", file=sys.stderr)
        print(f"operator error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
