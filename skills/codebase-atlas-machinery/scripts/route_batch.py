#!/usr/bin/env python3
"""Resumable, explicit native-worker orchestration for at most three Atlas routes.

This module does not invoke model providers. It freezes role-specific relay jobs for
fresh native workers and admits only the parent-observed terminal result path.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat as statmod
import subprocess
import sys
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if os.fspath(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_DIR))

import atlas  # noqa: E402
import route_coordinator  # noqa: E402

SCHEMA_VERSION = 4
MANIFEST = "batch.json"
MAX_ROUTES = 3
MAX_BYTES_DEFAULT = 1_048_576
ID_RE = re.compile(r"^[0-9a-f]{24}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_ROOTS = {"workers", "route-runs"}


class BatchError(Exception):
    """Expected identity, state, or integrity refusal."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise BatchError(f"{label} must be a regular, nonsymlink file: {path}")
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatchError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise BatchError(f"{label} must be a JSON object")
    return value, raw


def _read_staged_result(path: Path, max_bytes: int) -> bytes:
    try:
        canonical = _ensure_safe_path(path)
        before = canonical.lstat()
        if (canonical.is_symlink() or not canonical.is_file() or before.st_size < 1
                or before.st_size > max_bytes or before.st_nlink != 1):
            raise BatchError("staged result is missing, symlinked, nonregular, or exceeds the frozen response byte limit")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(canonical, flags)
        try:
            opened = os.fstat(fd)
            if not statmod.S_ISREG(opened.st_mode):
                raise BatchError("staged result is missing, symlinked, nonregular, or exceeds the frozen response byte limit")
            if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
                raise BatchError("staged result file identity changed while opening")
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after_fd = os.fstat(fd)
        finally:
            os.close(fd)
        after = canonical.lstat()
        if ((after_fd.st_dev, after_fd.st_ino, after_fd.st_size, after_fd.st_mtime_ns)
                != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)):
            raise BatchError("staged result file identity changed while reading")
        if not raw or len(raw) > max_bytes:
            raise BatchError("staged result is missing, symlinked, nonregular, or exceeds the frozen response byte limit")
        return raw
    except BatchError:
        raise
    except OSError as exc:
        raise BatchError("staged result is missing, symlinked, nonregular, or exceeds the frozen response byte limit") from exc


def _write_once(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_safe_path(path.parent)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise BatchError(f"refusing to replace immutable batch artifact: {path}") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    raw = _canonical(manifest)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    _ensure_safe_path(path.parent)
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise BatchError(f"cannot update batch manifest: {exc}") from exc


def _ensure_safe_path(path: Path) -> Path:
    requested = Path(os.path.abspath(os.fspath(path.expanduser())))
    current = Path(requested.anchor)
    for part in requested.parts[1:]:
        current = current / part
        if os.path.lexists(current) and current.is_symlink():
            raise BatchError(f"batch artifact path contains a symlink: {current}")
    resolved = requested.resolve(strict=False)
    if resolved != requested:
        raise BatchError(f"batch artifact path is not canonical: {requested}")
    return requested


def _producer_identity() -> dict[str, Any]:
    sources = {
        "route_batch.py": Path(__file__),
        "route_batch_launch.py": SCRIPT_DIR / "route_batch_launch.py",
        "atlas.py": SCRIPT_DIR / "atlas.py",
        "route_coordinator.py": SCRIPT_DIR / "route_coordinator.py",
    }
    identity = {}
    for name, path in sources.items():
        if path.is_symlink() or not path.is_file():
            raise BatchError(f"producer source is missing or unsafe: {name}")
        identity[name] = _sha(path.read_bytes())
    return identity


def _repo_db(repo_arg: str, db_arg: str) -> tuple[Path, Path]:
    raw_repo = Path(repo_arg).expanduser()
    if not raw_repo.is_absolute() or _ensure_safe_path(raw_repo) != raw_repo.absolute():
        raise BatchError("repository path must be absolute, canonical, and free of symlink ancestors")
    if not raw_repo.is_dir():
        raise BatchError("repository path must be an existing directory")
    try:
        repo = route_coordinator._canonical_repo(os.fspath(raw_repo))
    except route_coordinator.CoordinatorError as exc:
        raise BatchError(f"cannot resolve target repository: {exc}") from exc
    raw_db = Path(db_arg).expanduser()
    if not raw_db.is_absolute() or _ensure_safe_path(raw_db) != raw_db.absolute():
        raise BatchError("database path must be absolute, canonical, and free of symlink ancestors")
    if raw_db.is_symlink() or not raw_db.exists() or not raw_db.is_file():
        raise BatchError("database must be an existing regular nonsymlink file")
    db = raw_db.resolve(strict=True)
    if db == repo or db.is_relative_to(repo) or repo.is_relative_to(db):
        raise BatchError("Atlas database must be outside the target repository")
    return repo, db


def _allowed_run(run_arg: str, repo: Path) -> Path:
    run = _ensure_safe_path(Path(run_arg))
    if run == repo or run.is_relative_to(repo) or repo.is_relative_to(run):
        raise BatchError("batch directory and target repository must not contain or overlap each other")
    return run


def _snapshot(repo: Path, db: Path) -> tuple[dict[str, Any], str, dict[str, list[dict[str, Any]]]]:
    try:
        snapshot, all_snapshots, extractor, _live = atlas._current_route_snapshot(db, os.fspath(repo))
        associations = atlas._validated_route_associations(os.fspath(db), db, snapshot, all_snapshots)
    except (atlas.AtlasError, OSError) as exc:
        raise BatchError(f"cannot validate current Atlas route snapshot: {exc}") from exc
    return snapshot, extractor, associations


def _route_ids(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    ids = tuple(values)
    if not ids or len(ids) > MAX_ROUTES or len(set(ids)) != len(ids):
        raise BatchError("route batch must contain one to three unique route fact IDs")
    if any(not isinstance(item, str) or not ID_RE.fullmatch(item) for item in ids):
        raise BatchError("each route ID must be a 24-character lowercase hexadecimal fact ID")
    return ids


def _current_open_routes(snapshot: dict[str, Any], associations: dict[str, list[dict[str, Any]]],
                         ids: tuple[str, ...]) -> list[dict[str, Any]]:
    graph = snapshot.get("source_graph")
    facts = graph.get("facts") if isinstance(graph, dict) else None
    if not isinstance(facts, list):
        raise BatchError("current snapshot has no source graph facts")
    by_id = {fact.get("id"): fact for fact in facts if isinstance(fact, dict)}
    routes = []
    for fact_id in ids:
        fact = by_id.get(fact_id)
        if not isinstance(fact, dict) or fact.get("kind") != "route_action":
            raise BatchError(f"selected ID is not one current route_action fact: {fact_id}")
        if associations.get(fact_id, []):
            raise BatchError(f"selected route is not currently open: {fact_id}")
        routes.append(fact)
    return routes


def _identity(repo: Path, db: Path, ids: tuple[str, ...], run: Path, max_bytes: int,
              snapshot: dict[str, Any], extractor: str) -> dict[str, Any]:
    return {
        "repository_root": os.fspath(repo), "database_path": os.fspath(db),
        "route_fact_ids": list(ids), "run_dir": os.fspath(run),
        "max_bytes": max_bytes, "snapshot_id": snapshot.get("snapshot_id"),
        "extractor_identity": extractor, "producer_identity": _producer_identity(),
    }


def _load(run_arg: str, *, verify_producer: bool = True) -> tuple[Path, dict[str, Any]]:
    run = _ensure_safe_path(Path(run_arg))
    if run.is_symlink() or not run.is_dir():
        raise BatchError("batch run directory must be a real nonsymlink directory")
    manifest, raw = _read(run / MANIFEST, "batch manifest")
    if raw != _canonical(manifest) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise BatchError("batch manifest is noncanonical or has an unsupported schema")
    if verify_producer and manifest.get("identity", {}).get("producer_identity") != _producer_identity():
        raise BatchError("batch producer sources changed; prepare a new batch")
    identity = manifest.get("identity")
    if not isinstance(identity, dict) or identity.get("run_dir") != os.fspath(run):
        raise BatchError("batch manifest run identity is invalid")
    repo = Path(identity.get("repository_root", ""))
    if _allowed_run(os.fspath(run), repo) != run:
        raise BatchError("batch run directory overlaps the target repository")
    _repo_db(os.fspath(repo), identity.get("database_path", ""))
    _validate_batch_state(run, manifest)
    _validate_manifest_artifacts(run, manifest)
    _validate_job_sources(run, manifest)
    return run, manifest


def _validate_batch_state(run: Path, manifest: dict[str, Any]) -> None:
    expected_top = {"schema_version", "identity", "routes", "jobs", "active_job_id", "next_job_number",
                    "artifacts", "pending_artifacts", "created_at"}
    if set(manifest) != expected_top:
        raise BatchError("batch manifest fields do not match the closed schema")
    identity = manifest.get("identity")
    expected_identity = {"repository_root", "database_path", "route_fact_ids", "run_dir", "max_bytes",
                         "snapshot_id", "extractor_identity", "producer_identity"}
    if not isinstance(identity, dict) or set(identity) != expected_identity:
        raise BatchError("batch identity fields do not match the closed schema")
    ids = _route_ids(identity.get("route_fact_ids", []))
    routes = manifest.get("routes")
    jobs = manifest.get("jobs")
    if not isinstance(routes, list) or not isinstance(jobs, list) or len(routes) != len(ids):
        raise BatchError("batch route/job registry shape is invalid")
    if [item.get("route_fact_id") for item in routes if isinstance(item, dict)] != list(ids):
        raise BatchError("batch route registry must exactly preserve the requested route order")
    allowed_route_states = {"preparing", "luna_pending", "sol_pending", "published", "rejected",
                            "prepare_failed", "failed", "refused"}
    for route in routes:
        if not isinstance(route, dict) or route.get("state") not in allowed_route_states:
            raise BatchError("batch route entry has an unsupported state")
        if set(route) - {"route_fact_id", "state", "coordinator_result", "failure"}:
            raise BatchError("batch route entry contains unrecognized fields")
    seen: set[str] = set()
    expected_artifacts: set[str] = set()
    expected_pending_artifacts: set[str] = set()
    if "batch-relay.md" in manifest.get("pending_artifacts", {}):
        expected_pending_artifacts.add("batch-relay.md")
    else:
        expected_artifacts.add("batch-relay.md")
    route_roles: dict[str, list[str]] = {route_id: [] for route_id in ids}
    active_jobs: list[dict[str, Any]] = []
    allowed_job_states = {"reservation_persisting", "reserved", "in_flight", "response_persisting", "coordinator_pending",
                          "completed", "refused", "failed"}
    for index, job in enumerate(jobs, 1):
        if not isinstance(job, dict):
            raise BatchError("batch job registry contains a non-object")
        route_id, role = job.get("route_fact_id"), job.get("role")
        allowed_job_keys = {"job_id", "route_fact_id", "role", "requested_task_name", "prompt_created_at", "model_request",
                            "reasoning_effort_request", "fork_turns_request", "state", "task_name",
                            "prompt_path", "prompt_sha256", "schema_path", "schema_sha256", "relay_path",
                            "answer_path", "terminal_path", "stage_path", "spawn_args", "terminal_observation",
                            "result_sha256", "coordinator_result", "failure", "finished_at",
                            "spawn_recorded_at", "final_text", "response_raw_b64", "response_sha256",
                            "response_bytes", "response_error", "response_kind", "stage_admitted",
                            "staged_result_sha256", "staged_result_bytes"}
        if set(job) - allowed_job_keys:
            raise BatchError("batch job contains unrecognized fields")
        if route_id not in route_roles or role not in {"luna_draft", "sol_review"}:
            raise BatchError("batch job refers to an unselected route or unknown role")
        route_roles[route_id].append(role)
        expected_id = f"job-{index:02d}-{route_id}-{role}"
        expected_model = "gpt-6-luna" if role == "luna_draft" else "gpt-6.1-sol"
        expected_worker = f"workers/{route_id}/{role}"
        if (job.get("job_id") != expected_id or job.get("requested_task_name") != f"atlas_{role}_{route_id}"
                or job.get("model_request") != expected_model or job.get("reasoning_effort_request") != "high"
                or job.get("fork_turns_request") != "none" or job.get("state") not in allowed_job_states):
            raise BatchError("batch job identity, role settings, or state is invalid")
        if job["job_id"] in seen:
            raise BatchError("batch job IDs must be unique")
        seen.add(job["job_id"])
        expected_paths = {"prompt_path": f"{expected_worker}/prompt.md",
                          "schema_path": f"{expected_worker}/schema.json",
                          "relay_path": f"{expected_worker}/relay.md",
                          "answer_path": f"{expected_worker}/answer.json",
                          "terminal_path": f"{expected_worker}/terminal-observation.json",
                          "stage_path": f"{expected_worker}/staged-result.json"}
        if any(job.get(key) != value for key, value in expected_paths.items()):
            raise BatchError("batch job artifact paths are not the exact derived paths")
        if job.get("state") == "reservation_persisting":
            expected_pending_artifacts.update({expected_paths["prompt_path"], expected_paths["schema_path"],
                                               expected_paths["relay_path"]})
        else:
            expected_artifacts.update({expected_paths["prompt_path"], expected_paths["schema_path"],
                                       expected_paths["relay_path"]})
        if job.get("state") in {"reservation_persisting", "reserved", "in_flight", "response_persisting", "coordinator_pending"}:
            active_jobs.append(job)
        spawn = job.get("spawn_args")
        if job.get("state") in {"reservation_persisting", "reserved"}:
            if job.get("task_name") is not None or spawn is not None:
                raise BatchError("reserved job cannot contain an unobserved native spawn")
        elif job.get("state") != "reserved":
            if (not isinstance(spawn, dict) or set(spawn) != {"task_name", "model", "reasoning_effort", "fork_turns", "message"}
                    or spawn.get("task_name") != job["requested_task_name"] or spawn.get("model") != expected_model
                    or spawn.get("reasoning_effort") != "high" or spawn.get("fork_turns") != "none"
                    or not isinstance(job.get("task_name"), str) or not job["task_name"].strip()):
                raise BatchError("saved native spawn does not match the closed job request")
            if not isinstance(job.get("spawn_recorded_at"), str):
                raise BatchError("saved native spawn has no parent-observed timestamp")
        if job.get("state") in {"response_persisting", "coordinator_pending", "completed", "refused", "failed"}:
            terminal = job.get("terminal_observation")
            if (not isinstance(terminal, dict) or set(terminal) != {"task_name", "status", "final_text"}
                    or terminal.get("task_name") != job.get("task_name") or not isinstance(terminal.get("final_text"), str)):
                raise BatchError("consumed job has no exact saved terminal observation")
        admitted = job.get("stage_admitted")
        if not isinstance(admitted, bool):
            raise BatchError("job staged-result admission state is invalid")
        if admitted:
            if (not isinstance(job.get("staged_result_sha256"), str)
                    or not HEX_RE.fullmatch(job["staged_result_sha256"])
                    or not isinstance(job.get("staged_result_bytes"), int)
                    or job["staged_result_bytes"] < 1
                    or job.get("response_kind") != "staged_result"):
                raise BatchError("admitted staged result lacks its exact byte identity")
            record = {"sha256": job["staged_result_sha256"], "bytes": job["staged_result_bytes"]}
            if job.get("state") == "response_persisting":
                expected_pending_artifacts.add(expected_paths["stage_path"])
            elif job.get("state") in {"coordinator_pending", "completed", "refused"}:
                expected_artifacts.add(expected_paths["stage_path"])
            else:
                raise BatchError("staged result was admitted before terminal response consumption")
        elif (job.get("staged_result_sha256") is not None or job.get("staged_result_bytes") is not None):
            raise BatchError("unadmitted staged result cannot carry a trusted byte identity")
        if job.get("state") == "response_persisting":
            try:
                journal_raw = base64.b64decode(job["response_raw_b64"], validate=True)
            except (KeyError, TypeError, ValueError) as exc:
                raise BatchError("response-persisting job lacks its exact terminal-byte journal") from exc
            if (_sha(journal_raw) != job.get("response_sha256")
                    or len(journal_raw) != job.get("response_bytes")
                    or job.get("response_kind") not in {"staged_result", "invalid_pointer", "worker_failed"}):
                raise BatchError("response-persisting job journal does not match its closed byte identity")
        elif job.get("state") in {"coordinator_pending", "completed", "refused", "failed"}:
            if (job.get("response_raw_b64") is not None
                    or not isinstance(job.get("response_sha256"), str)
                    or not HEX_RE.fullmatch(job["response_sha256"])
                    or not isinstance(job.get("response_bytes"), int)
                    or job.get("response_kind") not in {"staged_result", "invalid_pointer", "worker_failed"}):
                raise BatchError("consumed job lost its exact response identity")
        elif any(job.get(key) is not None for key in ("response_raw_b64", "response_sha256", "response_bytes", "response_error", "response_kind")):
            raise BatchError("unconsumed job cannot contain a native terminal response")
        if job.get("state") in {"coordinator_pending", "completed", "refused", "failed"}:
            expected_artifacts.update({expected_paths["answer_path"], expected_paths["terminal_path"]})
        elif job.get("state") == "response_persisting":
            expected_pending_artifacts.update({expected_paths["answer_path"], expected_paths["terminal_path"]})
    if manifest.get("next_job_number") != len(jobs) + 1:
        raise BatchError("next job number does not follow the immutable job ledger")
    if len(active_jobs) > 1:
        raise BatchError("batch contains more than one active native/coordinator job")
    active_id = manifest.get("active_job_id")
    if (active_id is None) != (not active_jobs) or (active_id is not None and active_jobs[0].get("job_id") != active_id):
        raise BatchError("active job pointer does not match the closed job ledger")
    for route_id, roles in route_roles.items():
        if roles not in ([], ["luna_draft"], ["luna_draft", "sol_review"]):
            raise BatchError("route jobs must be ordered Luna draft followed by optional Sol review")
        route_state = next(item["state"] for item in routes if item["route_fact_id"] == route_id)
        route_jobs = [job for job in jobs if job["route_fact_id"] == route_id]
        if route_state == "luna_pending" and roles not in ([], ["luna_draft"]):
            raise BatchError("luna_pending route has a later-stage job")
        if route_state == "sol_pending":
            if roles not in (["luna_draft"], ["luna_draft", "sol_review"]) or route_jobs[0]["state"] != "completed":
                raise BatchError("sol_pending route lacks its completed Luna draft")
            if len(route_jobs) == 2 and route_jobs[1]["state"] not in {
                    "reserved", "in_flight", "response_persisting", "coordinator_pending"}:
                raise BatchError("sol_pending route has an invalid Sol job state")
        if route_state in {"published", "rejected"} and (
                roles != ["luna_draft", "sol_review"] or any(job["state"] != "completed" for job in route_jobs)):
            raise BatchError("terminal reviewed route lacks completed Luna and Sol jobs")
        if route_state in {"refused", "failed"} and not route_jobs:
            raise BatchError("failed route has no consumed native job")
    artifact_table = manifest.get("artifacts")
    pending_table = manifest.get("pending_artifacts")
    if (not isinstance(artifact_table, dict) or set(artifact_table) != expected_artifacts
            or not isinstance(pending_table, dict) or set(pending_table) != expected_pending_artifacts):
        raise BatchError("batch artifact registries do not exactly match the closed route/job state")


def _validate_manifest_artifacts(run: Path, manifest: dict[str, Any]) -> None:
    staged_paths = {job["stage_path"] for job in manifest.get("jobs", []) if isinstance(job, dict)}
    for item in run.rglob("*"):
        if item.is_symlink():
            raise BatchError(f"batch tree contains a symlink: {item.relative_to(run)}")
    artifacts = manifest.get("artifacts")
    pending_artifacts = manifest.get("pending_artifacts", {})
    if not isinstance(artifacts, dict) or not isinstance(pending_artifacts, dict):
        raise BatchError("batch artifact registry is malformed")
    for relative, record in list(artifacts.items()) + list(pending_artifacts.items()):
        if not isinstance(relative, str) or not isinstance(record, dict):
            raise BatchError("batch artifact registry entry is malformed")
        path = run / relative
        if (not path.resolve(strict=False).is_relative_to(run) or _ensure_safe_path(path) != path
                or path.is_symlink() or (relative in artifacts and not path.is_file())):
            raise BatchError(f"batch artifact is missing or unsafe: {relative}")
        if not path.exists():
            continue
        if not path.is_file():
            raise BatchError(f"batch artifact is not a regular file: {relative}")
        if relative in staged_paths and path.stat().st_size > manifest["identity"]["max_bytes"]:
            raise BatchError(f"staged result exceeds the frozen response byte limit: {relative}")
        raw = path.read_bytes()
        if record.get("sha256") != _sha(raw) or record.get("bytes") != len(raw):
            raise BatchError(f"batch artifact changed: {relative}")
    for relative in staged_paths:
        path = run / relative
        if path.exists():
            if path.is_symlink() or not path.is_file() or _ensure_safe_path(path) != path:
                raise BatchError(f"staged result is unsafe: {relative}")
            job = next(item for item in manifest["jobs"] if item.get("stage_path") == relative)
            if job.get("stage_admitted"):
                record = artifacts.get(relative) or pending_artifacts.get(relative)
                if record != {"sha256": job.get("staged_result_sha256"),
                              "bytes": job.get("staged_result_bytes")}:
                    raise BatchError(f"admitted staged result is not registered by its exact byte identity: {relative}")
            elif path.stat().st_size > manifest["identity"]["max_bytes"]:
                # An unadmitted file may be partial or malformed. It is only consumed
                # through the bounded pointer validator; it is never a batch artifact.
                raise BatchError(f"staged result exceeds the frozen response byte limit: {relative}")
    required = set(artifacts) | {MANIFEST}
    known = required | staged_paths
    observed = {item.relative_to(run).as_posix() for item in run.rglob("*")
                if item.is_file() and item.relative_to(run).parts[0] != "route-runs"}
    if not observed <= known | set(pending_artifacts) or not required <= observed | set(pending_artifacts):
        extra = sorted(observed - known)
        missing = sorted(required - observed)
        raise BatchError(f"batch artifact set differs from manifest; extra={extra}, missing={missing}")
    expected_routes = _route_ids(manifest["identity"].get("route_fact_ids", []))
    route_root = run / "route-runs"
    if route_root.exists():
        if _ensure_safe_path(route_root) != route_root or not route_root.is_dir():
            raise BatchError("route coordinator run root is unsafe")
        children = {item.name for item in route_root.iterdir()}
        if not children <= set(expected_routes):
            raise BatchError("route coordinator tree contains an unregistered route")
        for route_id in children:
            child = route_root / route_id
            if _ensure_safe_path(child) != child or not child.is_dir():
                raise BatchError(f"route coordinator directory is unsafe: {route_id}")
            coordinator_manifest, _ = _read(child / route_coordinator.MANIFEST, "route coordinator manifest")
            route_coordinator._validate_manifest_artifacts(child, coordinator_manifest, {
                "repository_root": manifest["identity"]["repository_root"],
                "database_path": manifest["identity"]["database_path"],
                "route_fact_id": route_id,
            })


def _record_artifact(manifest: dict[str, Any], run: Path, relative: str, raw: bytes) -> Path:
    if relative in manifest["artifacts"]:
        existing = run / relative
        if existing.is_file() and not existing.is_symlink() and existing.read_bytes() == raw:
            return existing
        raise BatchError(f"batch artifact is immutable and conflicts: {relative}")
    path = run / relative
    _write_once(path, raw)
    manifest["artifacts"][relative] = {"sha256": _sha(raw), "bytes": len(raw)}
    _write_manifest(run / MANIFEST, manifest)
    return path


def _coordinator_dir(run: Path, route_id: str) -> Path:
    return run / "route-runs" / route_id


def _worker_dir(run: Path, route_id: str, role: str) -> Path:
    return run / "workers" / route_id / role


def _batch_relay(run: Path) -> bytes:
    module_path = os.fspath(SCRIPT_DIR / "route_batch.py")
    run_path = os.fspath(run)
    return (f"""# Atlas route batch relay

Run directory: `{run_path}`
Python module: `{module_path}`

Read this file and follow the loop mechanically. Use native Codex collaboration tools; do not invoke a provider CLI.

1. Call `route_batch.next_job({run_path!r})` from `{module_path}`.
2. If it returns `complete`, stop and report the returned status.
3. If it returns `awaiting_existing_worker`, wait for that exact `task_name` only when one was recorded. If the task name is absent or the tool outcome is uncertain, stop and reconcile with the host; never start a replacement for a reserved or in-flight job.
4. For `job_reserved`, use the returned `spawn_message` exactly; it points to the complete immutable `prompt_path` and carries the required byte count and SHA-256. Spawn one fresh worker using collaboration `spawn_agent` with `task_name=requested_task_name`, `model=model_request`, `reasoning_effort=high`, and `fork_turns=none`. Capture the actual returned task name, then call `route_batch.record_spawn({run_path!r}, job_id, actual_spawn_args, returned_task_name)`; `actual_spawn_args` must record the exact object passed to `spawn_agent`.
5. Wait for that same returned task name to finish. Capture its actual terminal status and exact final pointer text as `{{task_name,status,final_text}}` and call `route_batch.finish_job({run_path!r}, job_id, terminal_observation)`. The runner verifies the code-issued staged path, byte count, SHA-256, and JSON shape, then journals and copies those exact file bytes before coordinator mutation. Workers must not directly mutate source, target, or database files. Atlas and the existing route coordinator own validation and any authorized publication.
6. Continue at step 1 after every conclusive terminal observation, including Atlas refusal, Sol rejection, or worker failure, until `complete`. Stop only when the native call outcome is uncertain or the orchestration API raises an error; preserve the recorded state and never silently retry with a new worker.

Luna drafts and Sol reviews are distinct fresh jobs. Sol is dispatched only after Atlas has created the exact current review packet. Atlas validation and the existing route coordinator own all source checks and publication. A model label in a prompt is not proof of provider identity or token usage.
""").encode("utf-8")


def prepare(repo: str, db: str, route_ids: list[str] | tuple[str, ...], run: str,
            max_bytes: int = MAX_BYTES_DEFAULT) -> dict[str, Any]:
    ids = _route_ids(route_ids)
    if not isinstance(max_bytes, int) or max_bytes < 1:
        raise BatchError("max_bytes must be a positive integer")
    canonical_repo, canonical_db = _repo_db(repo, db)
    run_dir = _allowed_run(run, canonical_repo)
    snapshot, extractor, associations = _snapshot(canonical_repo, canonical_db)
    expected_identity = _identity(canonical_repo, canonical_db, ids, run_dir, max_bytes, snapshot, extractor)
    if run_dir.exists():
        loaded, manifest = _load(os.fspath(run_dir))
        if manifest.get("identity") != expected_identity:
            raise BatchError("existing batch belongs to different inputs; refusing reuse")
        _recover_batch_relay(loaded, manifest)
        for item in manifest["routes"]:
            route_id = item.get("route_fact_id")
            if item.get("state") == "preparing":
                coord = _coordinator_dir(loaded, route_id)
                recovered = route_coordinator.status(os.fspath(canonical_repo), os.fspath(canonical_db),
                                                     route_id, os.fspath(coord), max_bytes)
                if recovered.get("result") != "prepared":
                    raise BatchError(f"interrupted route preparation requires a new batch: {route_id}")
                item["state"] = "luna_pending"
                _write_manifest(loaded / MANIFEST, manifest)
        return status(os.fspath(loaded))
    routes = _current_open_routes(snapshot, associations, ids)
    run_dir.mkdir(parents=True, exist_ok=False)
    relay_bytes = _batch_relay(run_dir)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "identity": expected_identity,
        "routes": [{"route_fact_id": route["id"], "state": "preparing"} for route in routes],
        "jobs": [], "active_job_id": None, "next_job_number": 1,
        "artifacts": {},
        "pending_artifacts": {"batch-relay.md": {"sha256": _sha(relay_bytes), "bytes": len(relay_bytes)}},
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    _write_manifest(run_dir / MANIFEST, manifest)
    _write_once(run_dir / "batch-relay.md", relay_bytes)
    manifest["artifacts"]["batch-relay.md"] = manifest["pending_artifacts"].pop("batch-relay.md")
    _write_manifest(run_dir / MANIFEST, manifest)
    for route in routes:
        route_id = str(route["id"])
        route_run = _coordinator_dir(run_dir, route_id)
        route_run.mkdir(parents=True)
        try:
            result = route_coordinator.prepare(os.fspath(canonical_repo), os.fspath(canonical_db),
                                               route_id, os.fspath(route_run), max_bytes)
        except (route_coordinator.CoordinatorError, OSError, ValueError) as exc:
            manifest["routes"][ids.index(route_id)]["state"] = "prepare_failed"
            manifest["routes"][ids.index(route_id)]["failure"] = str(exc)
            _write_manifest(run_dir / MANIFEST, manifest)
            raise BatchError(f"route preparation failed for {route_id}: {exc}") from exc
        if result.get("result") != "prepared":
            raise BatchError(f"route coordinator did not prepare route {route_id}")
        identity = manifest["routes"][ids.index(route_id)]
        identity.update({"state": "luna_pending", "coordinator_result": result})
        _write_manifest(run_dir / MANIFEST, manifest)
    return status(os.fspath(run_dir))


def _prompt_and_schema(run: Path, manifest: dict[str, Any], route: dict[str, Any], role: str,
                       job_id: str, prompt_created_at: str) -> tuple[str, dict[str, Any]]:
    route_id = route["route_fact_id"]
    coord = _coordinator_dir(run, route_id)
    stage_path = os.fspath(_ensure_safe_path(_worker_dir(run, route_id, role) / "staged-result.json"))
    if role == "luna_draft":
        evidence, _ = _read(coord / "evidence-pack.json", "complete route evidence packet")
        catalogue, contextual_sources = _canonical_citation_catalogue(manifest, evidence)
        schema = {
            "type": "object", "additionalProperties": False,
            "required": ["overlay_schema_version", "snapshot_id", "extractor_identity", "title", "reviewed_conclusions"],
            "properties": {
                "overlay_schema_version": {"const": 1},
                "snapshot_id": {"const": manifest["identity"]["snapshot_id"]},
                "extractor_identity": {"const": manifest["identity"]["extractor_identity"]},
                "title": {"type": "string", "minLength": 1},
                "reviewed_conclusions": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "additionalProperties": False, "required": ["claim", "evidence"],
                    "properties": {"claim": {"type": "string", "minLength": 1}, "evidence": {
                        "type": "array", "minItems": 1, "items": {
                            "oneOf": [_citation_entry_schema(entry) for entry in catalogue],
                        },
                    }},
                }},
            },
        }
        prompt = (
            "You are Luna, drafting one Atlas route map from the complete evidence packet below. "
            "Use only claims directly supported by exact packet source evidence. For ordinary Atlas facts, cite only one exact complete {fact_id, source} object from the code-owned canonical citation catalogue below. "
            "Never choose a citation source by copying a packet snippet. Other packet spans remain available for reasoning; the explicitly listed contextual spans are not canonical ordinary fact sources and must not be cited with their fact IDs. "
            "Compiler and runtime namespaces and provenance are preserved for reasoning; do not convert their synthetic IDs or anchors into ordinary fact citations. If a claim lacks a supported catalogue entry, omit it. "
            "Include the selected route fact in at least one conclusion. Do not claim runtime execution, runtime DI selection, or behavior not established by evidence. "
            f"Write exactly one complete JSON document matching the route-map schema below to this exclusive staged-result path: {stage_path}. "
            "Do not create or modify any other file. After writing, return only a pointer JSON object with exactly result_path, result_sha256, and result_bytes. "
            f"UTC timestamp for reviewed_at if required: {prompt_created_at}. "
            "\n\nROUTE FACT ID: " + route_id + "\n\nCOMPLETE EVIDENCE PACKET:\n" +
            json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) +
            "\n\nCANONICAL CITATION CATALOGUE (ordinary Atlas facts only; each fact_id is bound to its one saved fact.source):\n" +
            json.dumps(catalogue, ensure_ascii=False, sort_keys=True, indent=2) +
            "\n\nCONTEXTUAL PACKET SOURCES (visible in the packet for reasoning; not canonical citation anchors for ordinary facts):\n" +
            json.dumps(contextual_sources, ensure_ascii=False, sort_keys=True, indent=2) +
            "\n\nEXACT STAGED ROUTE-MAP JSON SCHEMA:\n" + json.dumps(schema, ensure_ascii=True, sort_keys=True, indent=2) +
            "\n\nEXACT FINAL POINTER JSON SCHEMA:\n" + json.dumps(_pointer_schema(stage_path), ensure_ascii=True, sort_keys=True, indent=2)
        )
        return prompt, schema
    if role == "sol_review":
        packet, _ = _read(coord / "review-packet.json", "exact Atlas route review packet")
        evidence, _ = _read(coord / "evidence-pack.json", "complete route evidence packet")
        packet_evidence = packet.get("complete_evidence_packet")
        if (not isinstance(packet_evidence, dict) or packet_evidence != evidence
                or packet.get("evidence_sha256") != _sha(_canonical(evidence))):
            raise BatchError("Sol review packet does not contain the exact saved complete evidence packet")
        catalogue, contextual_sources = _canonical_citation_catalogue(manifest, packet_evidence)
        schema = _sol_schema(packet)
        prompt = (
            "You are an independent Sol High reviewer. Assess the exact route-map review packet below. "
            "Review assignment fit, every numbered conclusion against its cited exact source spans, and route association as separate decisions. "
            "For ordinary Atlas facts, verify each citation against one exact complete {fact_id, source} object in the code-owned canonical citation catalogue below. "
            "Contextual packet spans remain available for reasoning, but the listed contextual spans are not canonical ordinary fact sources and cannot justify citations under their fact IDs. "
            "Compiler and runtime namespaces and provenance are preserved for reasoning; do not convert their synthetic IDs or anchors into ordinary fact citations. "
            "Accept only when all decisions are independently supported; otherwise reject and state concrete bases. "
            "This is a source-evidence review, not runtime dispatch proof. "
            f"Write exactly one complete JSON document matching the review schema below to this exclusive staged-result path: {stage_path}. "
            "Do not create or modify any other file. After writing, return only a pointer JSON object with exactly result_path, result_sha256, and result_bytes. "
            f"Use this UTC timestamp for reviewed_at: {prompt_created_at}.\n\nEXACT REVIEW PACKET:\n" +
            json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) +
            "\n\nCANONICAL CITATION CATALOGUE (ordinary Atlas facts only; each fact_id is bound to its one saved fact.source):\n" +
            json.dumps(catalogue, ensure_ascii=False, sort_keys=True, indent=2) +
            "\n\nCONTEXTUAL PACKET SOURCES (visible in the evidence packet for reasoning; not canonical citation anchors for ordinary facts):\n" +
            json.dumps(contextual_sources, ensure_ascii=False, sort_keys=True, indent=2) +
            "\n\nEXACT STAGED REVIEW JSON SCHEMA:\n" + json.dumps(schema, ensure_ascii=True, sort_keys=True, indent=2) +
            "\n\nEXACT FINAL POINTER JSON SCHEMA:\n" + json.dumps(_pointer_schema(stage_path), ensure_ascii=True, sort_keys=True, indent=2)
        )
        return prompt, schema
    raise BatchError(f"unsupported route batch role: {role}")


def _citation_entry_schema(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False, "required": ["fact_id", "source"],
        "properties": {"fact_id": {"const": entry["fact_id"]}, "source": {"const": entry["source"]}},
    }


def _canonical_citation_catalogue(manifest: dict[str, Any], evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        raise BatchError("canonical citation catalogue has no frozen batch identity")
    repo, db = _repo_db(identity.get("repository_root", ""), identity.get("database_path", ""))
    snapshot, extractor, _associations = _snapshot(repo, db)
    if (snapshot.get("snapshot_id") != identity.get("snapshot_id")
            or extractor != identity.get("extractor_identity")
            or evidence.get("snapshot_id") != identity.get("snapshot_id")
            or evidence.get("extractor_identity") != identity.get("extractor_identity")):
        raise BatchError("canonical citation catalogue source differs from the frozen batch snapshot")

    packet_snippets: list[dict[str, Any]] = []
    for field in ("source_snippets", "candidate_snippets"):
        snippets = evidence.get(field)
        if not isinstance(snippets, list):
            raise BatchError(f"route evidence packet has no ordinary {field} list")
        for snippet in snippets:
            if (not isinstance(snippet, dict) or not isinstance(snippet.get("fact_id"), str)
                    or not isinstance(snippet.get("path"), str) or not isinstance(snippet.get("sha256"), str)
                    or not isinstance(snippet.get("span"), dict)):
                raise BatchError(f"route evidence packet contains a malformed ordinary {field} entry")
            packet_snippets.append(snippet)

    relevant_ids = {snippet["fact_id"] for snippet in packet_snippets}
    route = evidence.get("route")
    route_fact_id = route.get("fact_id") if isinstance(route, dict) else None
    if not relevant_ids or not isinstance(route_fact_id, str) or route_fact_id not in relevant_ids:
        raise BatchError("ordinary packet citation catalogue is empty or omits its selected route fact")
    graph = snapshot.get("source_graph")
    facts = graph.get("facts") if isinstance(graph, dict) else None
    if not isinstance(facts, list):
        raise BatchError("current snapshot has no source graph facts for canonical citations")
    by_id: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        if isinstance(fact, dict) and fact.get("id") in relevant_ids:
            by_id.setdefault(fact["id"], []).append(fact)

    catalogue: list[dict[str, Any]] = []
    canonical_by_id: dict[str, dict[str, Any]] = {}
    for fact_id in sorted(relevant_ids):
        matches = by_id.get(fact_id, [])
        if len(matches) != 1 or not isinstance(matches[0].get("source"), dict):
            raise BatchError(f"ordinary packet fact has missing or ambiguous canonical source identity: {fact_id}")
        source = matches[0]["source"]
        if not any(snippet["fact_id"] == fact_id
                   and {key: snippet[key] for key in ("path", "sha256", "span")} == source
                   for snippet in packet_snippets):
            raise BatchError(f"canonical source for ordinary packet fact is not present as a packet snippet: {fact_id}")
        canonical_by_id[fact_id] = source
        catalogue.append({"fact_id": fact_id, "source": source})

    contextual_sources = []
    seen_contexts: set[tuple[str, str]] = set()
    for snippet in packet_snippets:
        fact_id = snippet["fact_id"]
        source = {key: snippet[key] for key in ("path", "sha256", "span")}
        if source != canonical_by_id[fact_id]:
            encoded = json.dumps(source, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            key = (fact_id, encoded)
            if key not in seen_contexts:
                seen_contexts.add(key)
                contextual_sources.append({"fact_id": fact_id, "source": source})
    return catalogue, contextual_sources


def _sol_schema(packet: dict[str, Any]) -> dict[str, Any]:
    claims = packet.get("claims")
    if not isinstance(claims, list):
        raise BatchError("Atlas review packet has no ordered claims")
    return {
        "type": "object", "additionalProperties": False,
        "required": ["review_schema_version", "packet_sha256", "evidence_sha256", "draft_sha256",
                     "reviewer_identity", "reviewer_model", "reviewed_at", "decision",
                     "assignment_review", "conclusion_reviews", "route_association_review"],
        "properties": {
            "review_schema_version": {"const": 1},
            "packet_sha256": {"const": packet.get("packet_sha256")},
            "evidence_sha256": {"const": packet.get("evidence_sha256")},
            "draft_sha256": {"const": packet.get("draft_sha256")},
            "reviewer_identity": {"type": "string", "minLength": 1},
            "reviewer_model": {"const": "GPT-6.1 Sol High"},
            "reviewed_at": {"type": "string", "minLength": 1},
            "decision": {"enum": ["accepted", "rejected"]},
            "assignment_review": _decision_schema(),
            "conclusion_reviews": {"type": "array", "minItems": len(claims), "maxItems": len(claims),
                                   "items": {"type": "object", "additionalProperties": False,
                                             "required": ["conclusion_number", "decision", "basis"],
                                             "properties": {"conclusion_number": {"type": "integer"},
                                                            "decision": {"enum": ["accepted", "rejected"]},
                                                            "basis": {"type": "string", "minLength": 20, "maxLength": 2000}}}},
            "route_association_review": _decision_schema(),
        },
    }


def _decision_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": ["decision", "basis"],
            "properties": {"decision": {"enum": ["accepted", "rejected"]},
                           "basis": {"type": "string", "minLength": 20, "maxLength": 2000}}}


def _pointer_schema(stage_path: str) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["result_path", "result_sha256", "result_bytes"],
        "properties": {
            "result_path": {"const": stage_path},
            "result_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "result_bytes": {"type": "integer", "minimum": 1},
        },
    }


def _job_relay(job_id: str, role: str, model: str, prompt_bytes: bytes, schema_bytes: bytes) -> bytes:
    return (f"Batch relay job {job_id}: role={role}; model={model}; effort=high; fork_turns=none.\n"
            "The runner uses a short pointer to the complete immutable prompt and exact staged-result path. "
            "The worker may write only that one staged JSON file and returns its exact path/hash/byte-count pointer as final_text.\n"
            f"Prompt SHA-256: {_sha(prompt_bytes)}\nSchema SHA-256: {_sha(schema_bytes)}\n"
            "Do not retry an uncertain task. See the top-level batch-relay.md for the complete loop.\n").encode("utf-8")


def _spawn_message(run: Path, job: dict[str, Any], prompt_raw: bytes) -> str:
    prompt_path = _ensure_safe_path(run / job["prompt_path"])
    stage_path = _ensure_safe_path(run / job["stage_path"])
    digest = _sha(prompt_raw)
    if digest != job.get("prompt_sha256") or prompt_path.is_symlink() or not prompt_path.is_absolute():
        raise BatchError("worker prompt path or digest differs from the frozen job")
    return (
        f"Atlas route batch job {job['job_id']}; role={job['role']}. Read the COMPLETE immutable prompt at "
        f"{prompt_path} in bounded, non-truncated chunks. Verify it is exactly {len(prompt_raw)} UTF-8 bytes "
        f"with SHA-256 {digest} before acting. Follow its embedded complete output schema, use only its evidence, "
        f"You may create exactly one output file, the code-issued staged-result path {stage_path}; do not create or edit any other file, inspect unrelated files, or inspect credentials. "
        "The staged file must contain the complete role result JSON. Your final text must contain only a pointer JSON object with exactly these keys: "
        f"result_path={stage_path!r}, result_sha256=<lowercase SHA-256 of staged bytes>, result_bytes=<exact byte count>. "
        "Do not put the role result itself in final text."
    )


def _validate_job_sources(run: Path, manifest: dict[str, Any]) -> None:
    relay_path = run / "batch-relay.md"
    relay_expected = _batch_relay(run)
    relay_pending = "batch-relay.md" in manifest.get("pending_artifacts", {})
    if relay_path.exists() and (not relay_path.is_file() or relay_path.is_symlink() or relay_path.read_bytes() != relay_expected):
        raise BatchError("top-level batch relay differs from the code-owned loop")
    if not relay_path.exists() and not relay_pending:
        raise BatchError("top-level batch relay differs from the code-owned loop")
    for job in manifest["jobs"]:
        prompt, schema = _prompt_and_schema(run, manifest, {"route_fact_id": job["route_fact_id"]},
                                            job["role"], job["job_id"], job["prompt_created_at"])
        prompt_raw, schema_raw = prompt.encode("utf-8"), _canonical(schema)
        prompt_path, schema_path = run / job["prompt_path"], run / job["schema_path"]
        prompt_missing_pending = job["prompt_path"] in manifest.get("pending_artifacts", {})
        schema_missing_pending = job["schema_path"] in manifest.get("pending_artifacts", {})
        if (_sha(prompt_raw) != job.get("prompt_sha256") or _sha(schema_raw) != job.get("schema_sha256")
                or (prompt_path.exists() and prompt_path.read_bytes() != prompt_raw)
                or (schema_path.exists() and schema_path.read_bytes() != schema_raw)
                or (not prompt_path.exists() and not prompt_missing_pending)
                or (not schema_path.exists() and not schema_missing_pending)):
            raise BatchError("saved role prompt or JSON schema differs from current Atlas evidence")
        if job.get("spawn_args") is not None and job["spawn_args"].get("message") != _spawn_message(run, job, prompt_raw):
            raise BatchError("saved native spawn message differs from the exact bounded prompt pointer")
        relay_raw = _job_relay(job["job_id"], job["role"], job["model_request"], prompt_raw, schema_raw)
        job_relay_path = run / job["relay_path"]
        relay_pending = job["relay_path"] in manifest.get("pending_artifacts", {})
        if ((job_relay_path.exists() and job_relay_path.read_bytes() != relay_raw)
                or (not job_relay_path.exists() and not relay_pending)):
            raise BatchError("saved job relay differs from the code-owned native-worker request")
        terminal = job.get("terminal_observation")
        if terminal is not None:
            terminal_raw = _canonical(terminal)
            terminal_path, answer_path = run / job["terminal_path"], run / job["answer_path"]
            if (terminal.get("final_text") != job.get("final_text")
                    or (terminal_path.exists() and terminal_path.read_bytes() != terminal_raw)
                    or (answer_path.exists() and job.get("state") != "response_persisting"
                        and _sha(answer_path.read_bytes()) != job.get("result_sha256"))):
                raise BatchError("saved native response artifacts do not match the terminal observation")
            if (answer_path.exists() and job.get("state") == "response_persisting"
                    and _sha(answer_path.read_bytes()) != job.get("response_sha256")):
                raise BatchError("saved native response artifact differs from its pending exact-byte journal")
            if job.get("state") in {"completed", "refused", "failed"} and (
                    not isinstance(job.get("result_sha256"), str)
                    or (answer_path.exists() and _sha(answer_path.read_bytes()) != job["result_sha256"])):
                raise BatchError("consumed native response digest does not match its saved staged result")
            if job.get("state") == "response_persisting":
                try:
                    journal_raw = base64.b64decode(job["response_raw_b64"], validate=True)
                except (KeyError, TypeError, ValueError) as exc:
                    raise BatchError("saved native response journal is corrupt") from exc
                if (_sha(journal_raw) != job.get("response_sha256")
                        or len(journal_raw) != job.get("response_bytes")):
                    raise BatchError("saved native response journal changed")
        if job.get("stage_admitted"):
            staged = run / job["stage_path"]
            if (not staged.is_file() or staged.is_symlink()
                    or _sha(staged.read_bytes()) != job.get("staged_result_sha256")
                    or staged.stat().st_size != job.get("staged_result_bytes")):
                raise BatchError("admitted staged result differs from its saved byte identity")
        if job.get("state") == "completed" and (not isinstance(job.get("coordinator_result"), dict)
                                                  or not isinstance(job.get("finished_at"), str)):
            raise BatchError("completed job lacks its coordinator result or completion time")
        if job.get("state") in {"refused", "failed"} and not isinstance(job.get("failure"), str) and job["state"] == "refused":
            raise BatchError("refused job lacks its refusal reason")


def _recover_reservation(run: Path, manifest: dict[str, Any], job: dict[str, Any]) -> None:
    if job.get("state") != "reservation_persisting":
        return
    prompt, schema = _prompt_and_schema(run, manifest, {"route_fact_id": job["route_fact_id"]},
                                        job["role"], job["job_id"], job["prompt_created_at"])
    prompt_raw, schema_raw = prompt.encode("utf-8"), _canonical(schema)
    relay_raw = _job_relay(job["job_id"], job["role"], job["model_request"], prompt_raw, schema_raw)
    expected = {job["prompt_path"]: prompt_raw, job["schema_path"]: schema_raw, job["relay_path"]: relay_raw}
    for relative, raw in expected.items():
        record = manifest.get("pending_artifacts", {}).get(relative)
        if not isinstance(record, dict) or record != {"sha256": _sha(raw), "bytes": len(raw)}:
            raise BatchError("interrupted job reservation does not match its regenerated prompt/schema")
        path = run / relative
        if path.exists():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
                raise BatchError("interrupted job reservation artifact conflicts with its frozen bytes")
        else:
            _write_once(path, raw)
        manifest["artifacts"][relative] = manifest["pending_artifacts"].pop(relative)
    job["state"] = "reserved"
    _write_manifest(run / MANIFEST, manifest)


def _recover_batch_relay(run: Path, manifest: dict[str, Any]) -> None:
    record = manifest.get("pending_artifacts", {}).get("batch-relay.md")
    if record is None:
        return
    raw = _batch_relay(run)
    if record != {"sha256": _sha(raw), "bytes": len(raw)}:
        raise BatchError("interrupted batch relay differs from the code-owned loop")
    path = run / "batch-relay.md"
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
            raise BatchError("interrupted top-level relay conflicts with its frozen bytes")
    else:
        _write_once(path, raw)
    manifest["artifacts"]["batch-relay.md"] = manifest["pending_artifacts"].pop("batch-relay.md")
    _write_manifest(run / MANIFEST, manifest)


def _validate_luna(value: dict[str, Any], manifest: dict[str, Any]) -> None:
    # Atlas remains the authority for source refs and packet binding; check the closed shape here too.
    required = {"overlay_schema_version", "snapshot_id", "extractor_identity", "title", "reviewed_conclusions"}
    if set(value) != required or value.get("overlay_schema_version") != 1:
        raise BatchError("Luna result does not match the closed route-map draft shape")
    if value.get("snapshot_id") != manifest["identity"]["snapshot_id"] or value.get("extractor_identity") != manifest["identity"]["extractor_identity"]:
        raise BatchError("Luna draft snapshot or extractor differs from the frozen batch")
    conclusions = value.get("reviewed_conclusions")
    if not isinstance(conclusions, list) or not conclusions:
        raise BatchError("Luna draft must include at least one reviewed conclusion")
    for item in conclusions:
        if not isinstance(item, dict) or set(item) != {"claim", "evidence"}:
            raise BatchError("Luna conclusion must contain only claim and evidence")
        if not isinstance(item["claim"], str) or not item["claim"].strip() or not isinstance(item["evidence"], list) or not item["evidence"]:
            raise BatchError("Luna conclusion needs nonempty text and citations")


def _validate_sol(value: dict[str, Any], packet: dict[str, Any]) -> None:
    atlas._validate_route_map_review(value, packet)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BatchError("staged result is not one valid JSON object")
        result[key] = value
    return result


def _admit_pointer(run: Path, manifest: dict[str, Any], job: dict[str, Any], final_text: str) -> tuple[dict[str, Any], bytes]:
    try:
        pointer = json.loads(final_text, object_pairs_hook=_reject_duplicate_json_keys)
    except (json.JSONDecodeError, UnicodeDecodeError, BatchError) as exc:
        raise BatchError("native final pointer does not match the closed staged-result schema") from exc
    if not isinstance(pointer, dict) or set(pointer) != {"result_path", "result_sha256", "result_bytes"}:
        raise BatchError("native final pointer does not match the closed staged-result schema")
    stage_path = _ensure_safe_path(run / job["stage_path"])
    if pointer.get("result_path") != os.fspath(stage_path):
        raise BatchError("native final pointer path is not the code-issued staged-result path")
    digest, byte_count = pointer.get("result_sha256"), pointer.get("result_bytes")
    if (not isinstance(digest, str) or not HEX_RE.fullmatch(digest)
            or not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 1):
        raise BatchError("native final pointer does not match the closed staged-result schema")
    if byte_count > manifest["identity"]["max_bytes"]:
        raise BatchError("staged result is missing, symlinked, nonregular, or exceeds the frozen response byte limit")
    raw = _read_staged_result(stage_path, manifest["identity"]["max_bytes"])
    if len(raw) != byte_count or _sha(raw) != digest:
        raise BatchError("staged result byte count or SHA-256 does not match native pointer")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, BatchError) as exc:
        raise BatchError("staged result is not one valid JSON object") from exc
    if not isinstance(result, dict):
        raise BatchError("staged result is not one valid JSON object")
    return pointer, raw


def next_job(run_arg: str) -> dict[str, Any]:
    run, manifest = _load(run_arg)
    _recover_batch_relay(run, manifest)
    active = manifest.get("active_job_id")
    if active is not None:
        job = next((item for item in manifest["jobs"] if item.get("job_id") == active), None)
        if not isinstance(job, dict):
            raise BatchError("batch active job reference is missing")
        if job.get("state") == "reservation_persisting":
            _assert_route_fresh(manifest, job["route_fact_id"], _coordinator_dir(run, job["route_fact_id"]))
            _recover_reservation(run, manifest, job)
            return {"result": "job_reserved", "job_id": job["job_id"], "role": job["role"],
                    "requested_task_name": job["requested_task_name"], "model_request": job["model_request"],
                    "reasoning_effort_request": "high", "fork_turns_request": "none",
                    "relay_path": os.fspath(run / "batch-relay.md"),
                    "prompt_path": os.fspath(run / job["prompt_path"]),
                    "schema_path": os.fspath(run / job["schema_path"]),
                    "spawn_message": _spawn_message(run, job, (run / job["prompt_path"]).read_bytes()),
                    "answer_path": os.fspath(run / job["answer_path"]),
                    "stage_path": os.fspath(run / job["stage_path"])}
        if job.get("state") in {"response_persisting", "coordinator_pending"}:
            return _reconcile_response(run, manifest, job)
        if job.get("state") in {"reserved", "in_flight"}:
            _assert_route_fresh(manifest, job["route_fact_id"], _coordinator_dir(run, job["route_fact_id"]))
            return {"result": "awaiting_existing_worker", "job_id": active,
                    "state": job["state"], "task_name": job.get("task_name"),
                    "relay_path": os.fspath(run / "batch-relay.md")}
    pending = next((item for item in manifest["routes"] if item.get("state") in {"luna_pending", "sol_pending"}), None)
    if pending is None:
        return {"result": "complete", "status": status(os.fspath(run))}
    role = "luna_draft" if pending["state"] == "luna_pending" else "sol_review"
    _assert_route_fresh(manifest, pending["route_fact_id"], _coordinator_dir(run, pending["route_fact_id"]))
    number = manifest["next_job_number"]
    job_id = f"job-{number:02d}-{pending['route_fact_id']}-{role}"
    worker = _worker_dir(run, pending["route_fact_id"], role)
    prompt_created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    prompt, schema = _prompt_and_schema(run, manifest, pending, role, job_id, prompt_created_at)
    prompt_path = worker / "prompt.md"
    schema_path = worker / "schema.json"
    prompt_bytes = prompt.encode("utf-8")
    schema_bytes = _canonical(schema)
    relay_path = worker / "relay.md"
    model = "gpt-6-luna" if role == "luna_draft" else "gpt-6.1-sol"
    relay = _job_relay(job_id, role, model, prompt_bytes, schema_bytes)
    relative = lambda path: path.relative_to(run).as_posix()
    job = {
        "job_id": job_id, "route_fact_id": pending["route_fact_id"], "role": role,
        "requested_task_name": f"atlas_{role}_{pending['route_fact_id']}",
        "prompt_created_at": prompt_created_at,
        "model_request": model, "reasoning_effort_request": "high", "fork_turns_request": "none",
        "state": "reservation_persisting", "task_name": None,
        "prompt_path": relative(prompt_path), "prompt_sha256": _sha(prompt_bytes),
        "schema_path": relative(schema_path), "schema_sha256": _sha(schema_bytes),
        "relay_path": relative(relay_path), "answer_path": relative(worker / "answer.json"),
        "terminal_path": relative(worker / "terminal-observation.json"),
        "stage_path": relative(worker / "staged-result.json"),
        "spawn_args": None, "terminal_observation": None, "result_sha256": None,
        "response_raw_b64": None, "response_sha256": None, "response_bytes": None,
        "response_error": None, "response_kind": None, "stage_admitted": False,
        "staged_result_sha256": None, "staged_result_bytes": None,
    }
    manifest["jobs"].append(job)
    manifest["active_job_id"] = job_id
    manifest["next_job_number"] = number + 1
    pending_artifacts = manifest.setdefault("pending_artifacts", {})
    for path, raw in ((prompt_path, prompt_bytes), (schema_path, schema_bytes), (relay_path, relay)):
        pending_artifacts[relative(path)] = {"sha256": _sha(raw), "bytes": len(raw)}
    _write_manifest(run / MANIFEST, manifest)
    worker.mkdir(parents=True, exist_ok=True)
    for path, raw in ((prompt_path, prompt_bytes), (schema_path, schema_bytes), (relay_path, relay)):
        _write_once(path, raw)
        manifest["artifacts"][relative(path)] = manifest["pending_artifacts"].pop(relative(path))
    job["state"] = "reserved"
    _write_manifest(run / MANIFEST, manifest)
    _validate_manifest_artifacts(run, manifest)
    return {"result": "job_reserved", "job_id": job_id, "role": role,
            "requested_task_name": job["requested_task_name"],
            "model_request": model, "reasoning_effort_request": "high", "fork_turns_request": "none",
            "relay_path": os.fspath(run / "batch-relay.md"), "prompt_path": os.fspath(prompt_path),
            "schema_path": os.fspath(schema_path), "spawn_message": _spawn_message(run, job, prompt_bytes),
            "answer_path": os.fspath(worker / "answer.json"),
            "stage_path": os.fspath(worker / "staged-result.json")}


def record_spawn(run_arg: str, job_id: str, spawn_args: dict[str, Any], task_name: str) -> dict[str, Any]:
    run, manifest = _load(run_arg)
    job = _job(manifest, job_id)
    if manifest.get("active_job_id") != job_id or job.get("state") != "reserved":
        raise BatchError("only the active reserved job can record a native spawn")
    _assert_route_fresh(manifest, job["route_fact_id"], _coordinator_dir(run, job["route_fact_id"]))
    if not isinstance(spawn_args, dict) or set(spawn_args) != {"task_name", "model", "reasoning_effort", "fork_turns", "message"} or not isinstance(task_name, str) or not task_name.strip():
        raise BatchError("record_spawn needs the actual spawn argument object and returned task name")
    model = spawn_args.get("model")
    effort = spawn_args.get("reasoning_effort", spawn_args.get("thinking"))
    fork_turns = spawn_args.get("fork_turns")
    if model != job.get("model_request") or effort != "high" or fork_turns not in ("none", None):
        raise BatchError("actual native spawn settings do not match the frozen job request")
    prompt_raw = (run / job["prompt_path"]).read_bytes()
    if (spawn_args.get("task_name") != job.get("requested_task_name")
            or spawn_args.get("message") != _spawn_message(run, job, prompt_raw)):
        raise BatchError("native task label or message differs from the reserved bounded prompt pointer")
    if job.get("fork_turns_request") == "none" and fork_turns != "none":
        raise BatchError("fresh worker spawn must explicitly use fork_turns=none")
    job["spawn_args"] = spawn_args
    job["task_name"] = task_name
    job["state"] = "in_flight"
    job["spawn_recorded_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    _write_manifest(run / MANIFEST, manifest)
    return {"result": "spawn_recorded", "job_id": job_id, "task_name": task_name, "state": job["state"]}


def _job(manifest: dict[str, Any], job_id: str) -> dict[str, Any]:
    matches = [item for item in manifest.get("jobs", []) if isinstance(item, dict) and item.get("job_id") == job_id]
    if len(matches) != 1:
        raise BatchError(f"job ID is absent or duplicated: {job_id}")
    return matches[0]


def _reconcile_response(run: Path, manifest: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    if job.get("state") == "response_persisting":
        try:
            response_raw = base64.b64decode(job["response_raw_b64"], validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise BatchError("saved native response journal is incomplete or corrupt") from exc
        if (_sha(response_raw) != job.get("response_sha256")
                or len(response_raw) != job.get("response_bytes")):
            raise BatchError("saved native response journal does not match its byte identity")
        terminal_raw = _canonical(job["terminal_observation"])
        for name, raw in ((job["answer_path"], response_raw), (job["terminal_path"], terminal_raw)):
            record = manifest.get("pending_artifacts", {}).get(name)
            if not isinstance(record, dict):
                raise BatchError("saved native response has an incomplete persistence record")
            path = run / name
            if path.exists():
                if path.is_symlink() or not path.is_file() or _sha(path.read_bytes()) != record.get("sha256"):
                    raise BatchError("saved native response artifact conflicts during recovery")
            else:
                if _sha(raw) != record.get("sha256"):
                    raise BatchError("saved native response bytes do not match their recovery record")
                _write_once(path, raw)
            manifest["artifacts"][name] = record
            manifest["pending_artifacts"].pop(name)
        if job.get("stage_admitted"):
            name = job["stage_path"]
            record = manifest.get("pending_artifacts", {}).get(name)
            if not isinstance(record, dict) or record != {
                    "sha256": job.get("staged_result_sha256"), "bytes": job.get("staged_result_bytes")}:
                raise BatchError("admitted staged result has no exact persistence record")
            stage_raw = _read_staged_result(run / name, manifest["identity"]["max_bytes"])
            if stage_raw != response_raw:
                raise BatchError("staged result changed after exact response admission")
            manifest["artifacts"][name] = record
            manifest["pending_artifacts"].pop(name)
        job["result_sha256"] = _sha(response_raw)
        job["response_raw_b64"] = None
        job["state"] = "coordinator_pending"
        _write_manifest(run / MANIFEST, manifest)
    if job.get("state") != "coordinator_pending":
        raise BatchError("active job has no recoverable completed response")
    terminal = job.get("terminal_observation")
    if (not isinstance(terminal, dict) or terminal.get("status") != "completed"
            or job.get("response_error") is not None):
        failed = terminal.get("status") != "completed" if isinstance(terminal, dict) else True
        job["state"] = "failed" if failed else "refused"
        job["result_sha256"] = _sha((run / job["answer_path"]).read_bytes())
        job["failure"] = job.get("response_error") or "native worker did not complete successfully"
        job["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        route = next(item for item in manifest["routes"] if item["route_fact_id"] == job["route_fact_id"])
        route["state"] = job["state"]
        manifest["active_job_id"] = None
        _write_manifest(run / MANIFEST, manifest)
        return {"result": "worker_failed" if failed else "refused",
                "route_fact_id": job["route_fact_id"], "reason": job["failure"]}
    result_raw = (run / job["answer_path"]).read_bytes()
    try:
        result = json.loads(result_raw.decode("utf-8"))
        if not isinstance(result, dict):
            raise BatchError("native worker response must be one JSON object")
        coord = _coordinator_dir(run, job["route_fact_id"])
        if job["role"] == "luna_draft":
            _validate_luna(result, manifest)
            packet, _packet_bytes, packet_code = atlas.route_map_prepare(
                manifest["identity"]["database_path"], manifest["identity"]["repository_root"],
                job["route_fact_id"], os.fspath(run / job["answer_path"]), manifest["identity"]["max_bytes"])
            if packet_code != 0:
                raise BatchError("Atlas source validation refused the completed Luna draft")
        else:
            packet, _ = _read(coord / "review-packet.json", "saved exact Atlas review packet")
            _validate_sol(result, packet)
        if job["role"] == "sol_review":
            _assert_sol_recovery_match(manifest, job["route_fact_id"], coord)
            review_check, _review_bytes, review_code = atlas.route_map_review(
                manifest["identity"]["database_path"], manifest["identity"]["repository_root"],
                os.fspath(coord / "review-packet.json"), os.fspath(run / job["answer_path"]))
            if review_code != 0 or review_check.get("result") not in {"accepted", "rejected"}:
                raise BatchError("Atlas review validation refused the completed Sol response")
        else:
            _assert_route_fresh(manifest, job["route_fact_id"], coord)
    except (BatchError, atlas.AtlasError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        job["state"] = "refused"
        job["failure"] = str(exc)
        job["result_sha256"] = _sha(result_raw)
        job["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        route = next(item for item in manifest["routes"] if item["route_fact_id"] == job["route_fact_id"])
        route["state"] = "refused"
        manifest["active_job_id"] = None
        _write_manifest(run / MANIFEST, manifest)
        return {"result": "refused", "route_fact_id": job["route_fact_id"], "reason": str(exc)}
    route = next(item for item in manifest["routes"] if item["route_fact_id"] == job["route_fact_id"])
    coord = _coordinator_dir(run, job["route_fact_id"])
    if job["role"] == "luna_draft":
        draft_result = route_coordinator.draft(manifest["identity"]["repository_root"],
                                                manifest["identity"]["database_path"],
                                                job["route_fact_id"], os.fspath(coord),
                                                os.fspath(run / job["answer_path"]), manifest["identity"]["max_bytes"])
        if draft_result.get("result") != "review_ready":
            raise BatchError("route coordinator did not produce an independent review packet")
        route["state"] = "sol_pending"
        final = {"result": "review_ready", "route_fact_id": job["route_fact_id"], **draft_result}
    else:
        publish_result = route_coordinator.publish(manifest["identity"]["repository_root"],
                                                   manifest["identity"]["database_path"],
                                                   job["route_fact_id"], os.fspath(coord),
                                                   os.fspath(run / job["answer_path"]), manifest["identity"]["max_bytes"])
        route["state"] = "published" if publish_result.get("result") == "published_and_fresh" else "rejected"
        final = {"route_fact_id": job["route_fact_id"], **publish_result}
    job["coordinator_result"] = final
    job["state"] = "completed"
    job["result_sha256"] = _sha(result_raw)
    job["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest["active_job_id"] = None
    _write_manifest(run / MANIFEST, manifest)
    return final


def finish_job(run_arg: str, job_id: str, terminal_observation: dict[str, Any]) -> dict[str, Any]:
    run, manifest = _load(run_arg)
    job = _job(manifest, job_id)
    if manifest.get("active_job_id") != job_id or job.get("state") != "in_flight":
        raise BatchError("only the active in-flight job can consume a terminal observation")
    if (not isinstance(terminal_observation, dict)
            or set(terminal_observation) != {"task_name", "status", "final_text"}
            or terminal_observation.get("task_name") != job.get("task_name")
            or terminal_observation.get("status") not in {"completed", "failed", "cancelled"}
            or not isinstance(terminal_observation.get("final_text"), str)):
        raise BatchError("terminal observation must be the exact closed same-task native terminal record")
    final_text = terminal_observation["final_text"]
    if len(final_text.encode("utf-8")) > manifest["identity"]["max_bytes"]:
        raise BatchError("native final text exceeds the frozen batch response byte limit")
    final_raw = final_text.encode("utf-8")
    response_error = None
    stage_raw = None
    if terminal_observation["status"] == "completed":
        try:
            _pointer, stage_raw = _admit_pointer(run, manifest, job, final_text)
        except (BatchError, atlas.AtlasError) as exc:
            response_error = str(exc)
            response_kind = "invalid_pointer"
            response_raw = final_raw
            job["stage_admitted"] = False
            job["staged_result_sha256"] = None
            job["staged_result_bytes"] = None
        else:
            response_kind = "staged_result"
            response_raw = stage_raw
            job["stage_admitted"] = True
            job["staged_result_sha256"] = _sha(stage_raw)
            job["staged_result_bytes"] = len(stage_raw)
    else:
        response_kind = "worker_failed"
        response_error = "native worker did not complete successfully"
        response_raw = final_raw
        job["stage_admitted"] = False
        job["staged_result_sha256"] = None
        job["staged_result_bytes"] = None
    answer_rel = job["answer_path"]
    terminal_rel = job["terminal_path"]
    terminal_raw = _canonical(terminal_observation)
    job["terminal_observation"] = terminal_observation
    job["final_text"] = final_text
    job["response_kind"] = response_kind
    job["response_error"] = response_error
    job["response_raw_b64"] = base64.b64encode(response_raw).decode("ascii")
    job["response_sha256"] = _sha(response_raw)
    job["response_bytes"] = len(response_raw)
    job["state"] = "response_persisting"
    pending = manifest.setdefault("pending_artifacts", {})
    for relative, raw in ((answer_rel, response_raw), (terminal_rel, terminal_raw)):
        pending[relative] = {"sha256": _sha(raw), "bytes": len(raw)}
    if stage_raw is not None:
        pending[job["stage_path"]] = {"sha256": _sha(stage_raw), "bytes": len(stage_raw)}
    _write_manifest(run / MANIFEST, manifest)
    return _reconcile_response(run, manifest, job)


def _route_current(manifest: dict[str, Any], route_id: str) -> dict[str, Any]:
    identity = manifest["identity"]
    try:
        result, _encoded, code = atlas.route_find(identity["database_path"], identity["repository_root"],
                                                 route_id, identity["max_bytes"])
    except (atlas.AtlasError, OSError) as exc:
        raise BatchError(f"current route verification failed ({route_id}): {exc}") from exc
    if code != 0:
        raise BatchError(f"current route verification returned refusal ({route_id})")
    if result.get("snapshot_id") != identity["snapshot_id"] or result.get("extractor_identity") != identity["extractor_identity"]:
        raise BatchError("current route snapshot or extractor changed; prepare a new batch")
    return result


def _assert_route_fresh(manifest: dict[str, Any], route_id: str, coord: Path) -> None:
    identity = manifest["identity"]
    found = _route_current(manifest, route_id)
    if found.get("result") != "unmapped" or found.get("association_count") != 0:
        raise BatchError("route changed from open before native response consumption")
    _assert_prepared_evidence_current(manifest, route_id, coord)


def _assert_prepared_evidence_current(manifest: dict[str, Any], route_id: str, coord: Path) -> None:
    identity = manifest["identity"]
    try:
        evidence, _encoded, code = atlas.evidence_pack(identity["database_path"], identity["repository_root"],
                                                       route_id, identity["max_bytes"])
    except (atlas.AtlasError, OSError) as exc:
        raise BatchError(f"current complete route evidence no longer validates: {exc}") from exc
    if code != 0:
        raise BatchError("current complete route evidence returned refusal")
    coordinator_manifest, _ = _read(coord / route_coordinator.MANIFEST, "route coordinator manifest")
    binding = coordinator_manifest.get("identity_binding")
    if not isinstance(binding, dict) or binding.get("evidence_sha256") != _sha(_canonical(evidence)):
        raise BatchError("prepared complete route evidence is stale; refusing native response")
    if (coord / "review-packet.json").exists():
        saved, _saved_raw = _read(coord / "review-packet.json", "saved exact Atlas review packet")
        current, _current_bytes, current_code = atlas.route_find(
            identity["database_path"], identity["repository_root"], route_id, identity["max_bytes"])
        if current_code != 0:
            raise BatchError("current route lookup refused while validating the saved review packet")
        if current.get("result") == "unmapped":
            draft_path = coord / "luna-draft.json"
            try:
                packet, _packet_bytes, packet_code = atlas.route_map_prepare(
                    identity["database_path"], identity["repository_root"], route_id,
                    os.fspath(draft_path), identity["max_bytes"])
            except (atlas.AtlasError, OSError) as exc:
                raise BatchError(f"current review packet no longer validates: {exc}") from exc
            if packet_code != 0:
                raise BatchError("current review packet generation returned refusal")
            if _canonical(packet) != _canonical(saved) or packet.get("packet_sha256") != saved.get("packet_sha256"):
                raise BatchError("saved Atlas review packet differs from current source/evidence")
        elif current.get("result") == "fresh":
            review_path = coord / "sol-review.json"
            if not review_path.is_file() or review_path.is_symlink():
                raise BatchError("published route has no saved exact Sol review for packet reconstruction")
            try:
                review_result, _review_bytes, review_code = atlas.route_map_review(
                    identity["database_path"], identity["repository_root"],
                    os.fspath(coord / "review-packet.json"), os.fspath(review_path))
            except (atlas.AtlasError, OSError) as exc:
                raise BatchError(f"current published review packet no longer validates: {exc}") from exc
            if (review_code != 0 or review_result.get("result") not in {"accepted", "rejected"}
                    or review_result.get("packet_sha256") != saved.get("packet_sha256")):
                raise BatchError("current published route review returned refusal")
            current_overlay = current.get("association", {}).get("binding", {}).get("overlay_id")
            if current_overlay != route_coordinator._expected_overlay(saved):
                raise BatchError("published route does not match the saved exact review packet")
        else:
            raise BatchError("current route state cannot validate the saved review packet")


def _validate_published_route(run: Path, manifest: dict[str, Any], route_id: str,
                              current: dict[str, Any], publish_result: dict[str, Any]) -> None:
    coord = _coordinator_dir(run, route_id)
    route_jobs = [job for job in manifest["jobs"] if job["route_fact_id"] == route_id]
    if ([job.get("role") for job in route_jobs] != ["luna_draft", "sol_review"]
            or any(job.get("state") != "completed" for job in route_jobs)):
        raise BatchError("published route lacks its completed, ordered Luna and Sol native responses")
    luna_raw = (run / route_jobs[0]["answer_path"]).read_bytes()
    sol_raw = (run / route_jobs[1]["answer_path"]).read_bytes()
    if ((coord / "luna-draft.json").read_bytes() != luna_raw
            or (coord / "sol-review.json").read_bytes() != sol_raw):
        raise BatchError("coordinator publication inputs differ from the exact saved native responses")
    packet, _ = _read(coord / "review-packet.json", "published route review packet")
    validation, _ = _read(coord / "review-validation.json", "published route review validation")
    review_result, _review_bytes, review_code = atlas.route_map_review(
        manifest["identity"]["database_path"], manifest["identity"]["repository_root"],
        os.fspath(coord / "review-packet.json"), os.fspath(coord / "sol-review.json"))
    if review_code != 0 or _canonical(review_result) != _canonical(validation) or validation.get("result") != "accepted":
        raise BatchError("saved Sol review no longer validates against the exact current Atlas packet")
    overlay_id = route_coordinator._expected_overlay(packet)
    association = current.get("association")
    binding = association.get("binding") if isinstance(association, dict) else None
    review = json.loads(sol_raw.decode("utf-8"))
    try:
        receipt = atlas._route_map_review_receipt(packet, review)
        receipt_hash = hashlib.sha256(atlas._canonical_json(receipt)).hexdigest()
    except (atlas.AtlasError, KeyError, TypeError, ValueError) as exc:
        raise BatchError(f"exact native review receipt cannot be reconstructed: {exc}") from exc
    expected_binding = {
        "binding_schema_version": 1,
        "snapshot_id": manifest["identity"]["snapshot_id"],
        "extractor_identity": manifest["identity"]["extractor_identity"],
        "route_fact_id": route_id,
        "overlay_id": overlay_id,
        "flow_review_receipt_hash": receipt_hash,
    }
    binding_hash = hashlib.sha256(atlas._canonical_json(expected_binding)).hexdigest()
    expected_association_review = {
        "review_schema_version": 1, "binding_hash": binding_hash, **expected_binding,
        "reviewer_identity": review["reviewer_identity"], "reviewer_model": review["reviewer_model"],
        "decision": "accepted", "reviewed_at": review["reviewed_at"],
        "review_basis": review["route_association_review"]["basis"],
    }
    association_review_hash = hashlib.sha256(atlas._canonical_json(expected_association_review)).hexdigest()
    expected_association_review["association_review_hash"] = association_review_hash
    expected_publish_fields = {
        "result": "published", "snapshot_id": manifest["identity"]["snapshot_id"],
        "route_fact_id": route_id, "overlay_id": overlay_id, "receipt_hash": receipt_hash,
        "binding_hash": binding_hash, "association_review_hash": association_review_hash,
        "packet_sha256": packet["packet_sha256"], "evidence_sha256": packet["evidence_sha256"],
    }
    if (current.get("result") != "fresh" or current.get("association_count") != 1
            or not isinstance(association, dict) or binding != expected_binding
            or association.get("binding_hash") != binding_hash
            or association.get("association_review_hash") != association_review_hash
            or association.get("association_review") != expected_association_review
            or set(publish_result) != set(expected_publish_fields) | {"idempotent"}
            or any(publish_result.get(key) != value for key, value in expected_publish_fields.items())
            or not isinstance(publish_result.get("idempotent"), bool)):
        raise BatchError("current route association and publish receipt do not match the exact native review")
    try:
        flow = atlas.query_flow(manifest["identity"]["database_path"], expected_binding["snapshot_id"], overlay_id)
    except atlas.AtlasError as exc:
        raise BatchError(f"current exact reviewed-flow receipt cannot be reconstructed: {exc}") from exc
    expected_receipt_payload = {**receipt, "receipt_hash": receipt_hash}
    if (flow.get("review_status") != "accepted"
            or flow.get("review_receipt") != expected_receipt_payload
            or flow.get("content_hash") != overlay_id):
        raise BatchError("current flow receipt does not match the exact saved native review")
    saved_find, _ = _read(coord / "published-route-find.json", "saved publication route lookup")
    def without_observation_time(value: dict[str, Any]) -> dict[str, Any]:
        projected = json.loads(json.dumps(value))
        freshness = projected.get("freshness")
        if not isinstance(freshness, dict) or not isinstance(freshness.get("checked_at"), str):
            raise BatchError("route lookup is missing its source-freshness observation time")
        freshness.pop("checked_at")
        return projected

    if _canonical(without_observation_time(saved_find)) != _canonical(without_observation_time(current)):
        raise BatchError("current route lookup differs from the coordinator's full publication receipt")
    publish_job = route_jobs[1].get("coordinator_result")
    if (not isinstance(publish_job, dict) or publish_job.get("overlay_id") != overlay_id
            or publish_job.get("result") != "published_and_fresh"):
        raise BatchError("completed Sol job does not retain the exact successful publication result")


def _assert_sol_recovery_match(manifest: dict[str, Any], route_id: str, coord: Path) -> None:
    identity = manifest["identity"]
    found = _route_current(manifest, route_id)
    if found.get("result") == "unmapped" and found.get("association_count") == 0:
        _assert_route_fresh(manifest, route_id, coord)
        return
    if found.get("result") != "fresh" or found.get("association_count") != 1:
        raise BatchError("route changed before Sol response recovery")
    packet, _ = _read(coord / "review-packet.json", "saved exact Atlas review packet")
    review, _ = _read(coord / "sol-review.json", "saved exact Sol response")
    current_overlay = found.get("association", {}).get("binding", {}).get("overlay_id")
    if current_overlay != route_coordinator._expected_overlay(packet):
        raise BatchError("a different map is published; refusing coordinator recovery")
    try:
        validation, _raw, code = atlas.route_map_review(identity["database_path"], identity["repository_root"],
                                                        os.fspath(coord / "review-packet.json"),
                                                        os.fspath(coord / "sol-review.json"))
    except (atlas.AtlasError, OSError) as exc:
        raise BatchError(f"saved Sol response does not validate for exact publication recovery: {exc}") from exc
    if code != 0 or validation.get("result") != "accepted":
        raise BatchError("only an exact fresh accepted Sol review can recover publication")
    _assert_prepared_evidence_current(manifest, route_id, coord)


def status(run_arg: str) -> dict[str, Any]:
    run, manifest = _load(run_arg)
    identity = manifest["identity"]
    repo, db = _repo_db(identity["repository_root"], identity["database_path"])
    snapshot, extractor, associations = _snapshot(repo, db)
    if snapshot.get("snapshot_id") != identity.get("snapshot_id") or extractor != identity.get("extractor_identity"):
        raise BatchError("current snapshot or extractor differs from the frozen batch")
    ids = _route_ids(identity.get("route_fact_ids", []))
    current = []
    for item in manifest["routes"]:
        if not isinstance(item, dict) or item.get("route_fact_id") not in ids:
            raise BatchError("batch route registry is malformed")
        route_id = item["route_fact_id"]
        found = _route_current(manifest, route_id)
        state = item.get("state")
        if state in {"luna_pending", "sol_pending", "preparing", "rejected", "failed", "refused"}:
            _assert_route_fresh(manifest, route_id, _coordinator_dir(run, route_id))
        elif state == "published":
            _assert_prepared_evidence_current(manifest, route_id, _coordinator_dir(run, route_id))
        if state == "published":
            coord = _coordinator_dir(run, route_id)
            cm, _ = _read(coord / route_coordinator.MANIFEST, "route coordinator manifest")
            if not isinstance(cm.get("artifacts"), dict) or "publish-result.json" not in cm["artifacts"]:
                raise BatchError("published route lacks a recorded coordinator publish receipt")
            publish_result, _ = _read(coord / "publish-result.json", "saved publish result")
            _validate_published_route(run, manifest, route_id, found, publish_result)
        elif state in {"luna_pending", "sol_pending", "preparing"}:
            if found.get("result") != "unmapped" or associations.get(route_id):
                raise BatchError(f"unpublished batch route is no longer open: {route_id}")
        elif state == "rejected":
            if found.get("result") != "unmapped":
                raise BatchError(f"rejected route unexpectedly has a published association: {route_id}")
            coord = _coordinator_dir(run, route_id)
            validation, _ = _read(coord / "review-validation.json", "saved rejected review validation")
            if validation.get("result") != "rejected":
                raise BatchError("batch marks route rejected without exact Atlas rejection evidence")
        elif state == "prepare_failed":
            if found.get("result") != "unmapped":
                raise BatchError(f"failed route is no longer open: {route_id}")
        elif state in {"failed", "refused"}:
            if found.get("result") != "unmapped":
                raise BatchError(f"terminally failed route unexpectedly has a published association: {route_id}")
        else:
            raise BatchError(f"unknown batch route state: {state}")
        current.append({"route_fact_id": route_id, "state": state,
                        "current_route_result": found.get("result"),
                        "overlay_id": found.get("association", {}).get("binding", {}).get("overlay_id")})
    active = manifest.get("active_job_id")
    active_state = None
    if active:
        active_job = _job(manifest, active)
        active_state = active_job.get("state")
    result = "complete" if all(item["state"] in {"published", "rejected", "prepare_failed", "failed", "refused"} for item in current) else "in_progress"
    return {"result": result, "run_dir": os.fspath(run), "identity": identity,
            "relay_path": os.fspath(run / "batch-relay.md"),
            "routes": current, "active_job_id": active, "active_job_state": active_state,
            "jobs_completed": sum(item.get("state") == "completed" for item in manifest["jobs"]),
            "jobs_total": len(manifest["jobs"])}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--repo", required=True)
    prep.add_argument("--db", required=True)
    prep.add_argument("--route-id", action="append", required=True)
    prep.add_argument("--run-dir", required=True)
    prep.add_argument("--max-bytes", type=int, default=MAX_BYTES_DEFAULT)
    nxt = sub.add_parser("next")
    nxt.add_argument("--run-dir", required=True)
    spawn = sub.add_parser("record-spawn")
    spawn.add_argument("--run-dir", required=True)
    spawn.add_argument("--job-id", required=True)
    spawn.add_argument("--spawn-json", required=True)
    spawn.add_argument("--task-name", required=True)
    finish = sub.add_parser("finish")
    finish.add_argument("--run-dir", required=True)
    finish.add_argument("--job-id", required=True)
    finish.add_argument("--observation-json", required=True)
    stat = sub.add_parser("status")
    stat.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.repo, args.db, args.route_id, args.run_dir, args.max_bytes)
        elif args.command == "next":
            result = next_job(args.run_dir)
        elif args.command == "record-spawn":
            result = record_spawn(args.run_dir, args.job_id, json.loads(Path(args.spawn_json).read_text()), args.task_name)
        elif args.command == "finish":
            observation = json.loads(Path(args.observation_json).read_text())
            result = finish_job(args.run_dir, args.job_id, observation)
        else:
            result = status(args.run_dir)
    except (BatchError, route_coordinator.CoordinatorError, atlas.AtlasError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"route-batch: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
