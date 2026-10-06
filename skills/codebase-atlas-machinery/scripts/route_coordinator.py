#!/usr/bin/env python3
"""Resumable, identity-bound driver for Atlas's reviewed one-route map stages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ATLAS = Path(__file__).with_name("atlas.py")
MANIFEST = "manifest.json"
DEFAULT_MAX_BYTES = 2_147_483_647
ARTIFACT_NAMES = {
    "route-find.json", "evidence-pack.json", "luna-draft.json", "review-packet.json",
    "sol-review.json", "review-validation.json", "publish-result.json",
    "published-route-find.json",
}
MANIFEST_TEMP = re.compile(r"^\.manifest\.json\.[0-9]+\.tmp$")


class CoordinatorError(Exception):
    """An expected identity, integrity, or stage error."""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, label: str) -> tuple[dict[str, object], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CoordinatorError(f"{label} must be a JSON object")
    return value, raw


def _write_once(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CoordinatorError(f"refusing to overwrite existing artifact: {path}") from exc
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


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    raw = _json_bytes(manifest)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
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
        raise CoordinatorError(f"cannot update coordinator manifest: {exc}") from exc


def _canonical_repo(repo_arg: str) -> Path:
    requested = Path(repo_arg).expanduser().resolve(strict=True)
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(requested), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    except OSError as exc:
        raise CoordinatorError(f"cannot resolve repository root: {exc}") from exc
    if result.returncode:
        detail = os.fsdecode(result.stderr).strip() or "git returned an error"
        raise CoordinatorError(f"cannot resolve repository root: {detail}")
    return Path(os.fsdecode(result.stdout).strip()).resolve(strict=True)


def _identity(repo_arg: str, db_arg: str, route_fact_id: str) -> dict[str, str]:
    repo = _canonical_repo(repo_arg)
    db = Path(db_arg).expanduser().resolve(strict=True)
    if not db.is_file():
        raise CoordinatorError(f"database is not a regular file: {db}")
    if not route_fact_id.strip():
        raise CoordinatorError("route fact ID must be nonempty")
    return {"repository_root": os.fspath(repo), "database_path": os.fspath(db), "route_fact_id": route_fact_id}


def _run_atlas(args: list[str]) -> tuple[bytes, bytes, int, int]:
    started = time.monotonic_ns()
    try:
        result = subprocess.run(
            [sys.executable, os.fspath(ATLAS), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    except OSError as exc:
        raise CoordinatorError(f"cannot run Atlas stage: {exc}") from exc
    elapsed_ms = (time.monotonic_ns() - started) // 1_000_000
    return result.stdout, result.stderr, result.returncode, int(elapsed_ms)


def _manifest(run_dir: Path, expected: dict[str, str] | None = None) -> dict[str, object]:
    directory = run_dir.expanduser().resolve(strict=True)
    if not directory.is_dir() or directory.is_symlink():
        raise CoordinatorError("run directory must be a real directory")
    manifest_path = directory / MANIFEST
    temp_paths = sorted(item for item in directory.iterdir() if MANIFEST_TEMP.fullmatch(item.name))
    if len(temp_paths) > 1:
        raise CoordinatorError("run directory contains multiple interrupted manifest writes")
    if temp_paths:
        candidate, _ = _read_json(temp_paths[0], "interrupted coordinator manifest")
        _validate_manifest_artifacts(directory, candidate, expected)
        if manifest_path.exists():
            current, _ = _read_json(manifest_path, "coordinator manifest")
            current_identity = current.get("identity")
            candidate_identity = candidate.get("identity")
            if not isinstance(current_identity, dict) or not isinstance(candidate_identity, dict):
                raise CoordinatorError("interrupted manifest has no valid identity")
            for key in ("repository_root", "database_path", "route_fact_id"):
                if current_identity.get(key) != candidate_identity.get(key):
                    raise CoordinatorError("interrupted manifest identity conflicts with the saved run")
        os.replace(temp_paths[0], manifest_path)
        manifest = candidate
    else:
        manifest, _raw = _read_json(manifest_path, "coordinator manifest")
    _validate_manifest_artifacts(directory, manifest, expected)
    pending = manifest.get("pending_artifacts", {})
    artifacts = manifest["artifacts"]
    assert isinstance(pending, dict) and isinstance(artifacts, dict)
    changed = False
    for name, record in list(pending.items()):
        path = directory / name
        if path.exists():
            artifacts[name] = record
        pending.pop(name)
        changed = True
    if changed:
        _write_manifest(manifest_path, manifest)
        _validate_manifest_artifacts(directory, manifest, expected)
    return manifest


def _validate_manifest_artifacts(directory: Path, manifest: dict[str, object],
                                 expected: dict[str, str] | None) -> None:
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("identity"), dict):
        raise CoordinatorError("unsupported or malformed coordinator manifest")
    identity = manifest["identity"]
    if expected is not None and any(identity.get(key) != value for key, value in expected.items()):
        raise CoordinatorError("run directory belongs to a different repository, database, or route fact")
    artifacts = manifest.get("artifacts")
    pending = manifest.get("pending_artifacts", {})
    if not isinstance(artifacts, dict) or not isinstance(pending, dict):
        raise CoordinatorError("manifest artifact tables are malformed")
    for label, table in (("artifact", artifacts), ("pending artifact", pending)):
        for name, record in table.items():
            if (not isinstance(name, str) or name not in ARTIFACT_NAMES or Path(name).name != name
                    or not isinstance(record, dict)):
                raise CoordinatorError(f"manifest contains an invalid {label} entry")
            path = directory / name
            if not path.exists():
                if label == "artifact":
                    raise CoordinatorError(f"run artifact is missing: {name}")
                continue
            if path.is_symlink() or not path.is_file():
                raise CoordinatorError(f"run artifact is not a regular file: {name}")
            raw = path.read_bytes()
            if record.get("sha256") != _sha(raw) or record.get("bytes") != len(raw):
                raise CoordinatorError(f"run artifact was changed: {name}")
    temp_names = {item.name for item in directory.iterdir() if MANIFEST_TEMP.fullmatch(item.name)}
    observed = {item.name for item in directory.iterdir() if item.name != MANIFEST and item.name not in temp_names}
    known = set(artifacts) | {name for name in pending if (directory / name).exists()}
    if observed != known:
        raise CoordinatorError("run directory contains missing or unregistered artifacts")


def _record_artifact(manifest: dict[str, object], run_dir: Path, name: str, raw: bytes) -> None:
    if name not in ARTIFACT_NAMES:
        raise CoordinatorError(f"unrecognized staged artifact name: {name}")
    artifacts = manifest["artifacts"]
    pending = manifest.setdefault("pending_artifacts", {})
    assert isinstance(artifacts, dict) and isinstance(pending, dict)
    if name in artifacts:
        raise CoordinatorError(f"refusing to replace recorded artifact: {name}")
    record = {"sha256": _sha(raw), "bytes": len(raw)}
    if name in pending and pending[name] != record:
        raise CoordinatorError(f"staged artifact conflicts with pending write: {name}")
    if name not in pending:
        pending[name] = record
        _write_manifest(run_dir / MANIFEST, manifest)
    _write_once(run_dir / name, raw)
    artifacts[name] = record
    pending.pop(name, None)
    _write_manifest(run_dir / MANIFEST, manifest)


def _record_stage(manifest: dict[str, object], stage: str, stdout: bytes, elapsed_ms: int,
                  artifacts: list[str], stderr: bytes = b"", artifact_bytes: int | None = None) -> None:
    artifact_table = manifest["artifacts"]
    assert isinstance(artifact_table, dict)
    manifest.setdefault("stages", []).append({
        "stage": stage,
        "atlas_stdout_bytes": len(stdout),
        "atlas_stderr_bytes": len(stderr),
        "elapsed_ms": elapsed_ms,
        "artifact_bytes": artifact_bytes if artifact_bytes is not None else sum(
            int(artifact_table[name]["bytes"]) for name in artifacts
        ),
        "artifacts": artifacts,
        "provider_model_tokens": "unavailable_without_provider_telemetry",
    })


def _save_atlas_output(manifest: dict[str, object], run_dir: Path, name: str,
                       stdout: bytes, stderr: bytes, code: int, stage: str,
                       elapsed_ms: int) -> dict[str, object]:
    if code != 0:
        _record_stage(manifest, stage, stdout, elapsed_ms, [], stderr)
        _write_manifest(run_dir / MANIFEST, manifest)
        message = os.fsdecode(stderr).strip() or f"Atlas exited {code} during {stage}"
        raise CoordinatorError(message)
    try:
        value = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"Atlas {stage} returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CoordinatorError(f"Atlas {stage} did not return a JSON object")
    if name in manifest.get("artifacts", {}):
        # Stage outputs are write-once. A repeated invocation is still measured,
        # while its current result is returned to the caller without replacing evidence.
        _record_stage(manifest, stage, stdout, elapsed_ms, [])
        _write_manifest(run_dir / MANIFEST, manifest)
    else:
        _record_stage(manifest, stage, stdout, elapsed_ms, [name], artifact_bytes=len(stdout))
        _write_manifest(run_dir / MANIFEST, manifest)
        _record_artifact(manifest, run_dir, name, stdout)
    return value


def _atlas_prefix(identity: dict[str, str]) -> list[str]:
    return ["--db", identity["database_path"], "--repo", identity["repository_root"]]


def prepare(repo_arg: str, db_arg: str, route_fact_id: str, run_arg: str,
            max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    identity = _identity(repo_arg, db_arg, route_fact_id)
    if max_bytes < 1:
        raise CoordinatorError("--max-bytes must be positive")
    run_dir = Path(run_arg).expanduser()
    if run_dir.exists():
        if not run_dir.is_dir() or run_dir.is_symlink() or any(run_dir.iterdir()):
            raise CoordinatorError("prepare requires a new or empty, real run directory")
    else:
        run_dir.mkdir(parents=True)
    run_dir = run_dir.resolve(strict=True)
    manifest: dict[str, object] = {
        "schema_version": 1, "identity": identity,
        "artifacts": {}, "stages": [],
    }
    _write_manifest(run_dir / MANIFEST, manifest)
    prefix = _atlas_prefix(identity)
    stdout, stderr, code, elapsed = _run_atlas([
        "route-find", *prefix, "--route-fact-id", route_fact_id, "--max-tokens", str(max_bytes),
    ])
    route_status = _save_atlas_output(manifest, run_dir, "route-find.json", stdout, stderr, code,
                                      "route-find", elapsed)
    manifest["identity"].update({"snapshot_id": route_status.get("snapshot_id"),
                                 "extractor_identity": route_status.get("extractor_identity")})
    _write_manifest(run_dir / MANIFEST, manifest)
    if route_status.get("result") != "unmapped" or route_status.get("association_count") != 0:
        raise CoordinatorError("prepare requires a current open route with zero accepted associations")
    stdout, stderr, code, elapsed = _run_atlas([
        "evidence-pack", *prefix, "--route-fact-id", route_fact_id, "--max-tokens", str(max_bytes),
    ])
    evidence = _save_atlas_output(manifest, run_dir, "evidence-pack.json", stdout, stderr, code,
                                  "evidence-pack", elapsed)
    selection = evidence.get("selection")
    if not isinstance(selection, dict) or selection.get("complete") is not True or selection.get("omitted_candidate_bundles") != 0:
        raise CoordinatorError("prepare requires a complete evidence packet with no omitted candidate bundles")
    if evidence.get("snapshot_id") != route_status.get("snapshot_id") or evidence.get("extractor_identity") != route_status.get("extractor_identity"):
        raise CoordinatorError("route and evidence stages selected different snapshot identities")
    manifest["identity_binding"] = {
        "evidence_sha256": _sha(_json_bytes(evidence)),
        "route_find_sha256": _sha((run_dir / "route-find.json").read_bytes()),
    }
    _write_manifest(run_dir / MANIFEST, manifest)
    return {"result": "prepared", "run_dir": os.fspath(run_dir), "identity": manifest["identity"],
            "evidence_bytes": len(stdout), "provider_model_tokens": "unavailable_without_provider_telemetry"}


def _load_bound_run(repo_arg: str, db_arg: str, route_fact_id: str, run_arg: str) -> tuple[Path, dict[str, object]]:
    identity = _identity(repo_arg, db_arg, route_fact_id)
    run_dir = Path(run_arg).expanduser().resolve(strict=True)
    manifest = _manifest(run_dir, identity)
    identity_full = manifest["identity"]
    evidence, evidence_raw = _read_json(run_dir / "evidence-pack.json", "saved evidence packet")
    route_status, _route_raw = _read_json(run_dir / "route-find.json", "saved route lookup")
    if (evidence.get("route", {}).get("fact_id") != route_fact_id
            or evidence.get("snapshot_id") != identity_full.get("snapshot_id")
            or evidence.get("extractor_identity") != identity_full.get("extractor_identity")
            or route_status.get("route_fact_id") != route_fact_id
            or route_status.get("snapshot_id") != identity_full.get("snapshot_id")):
        raise CoordinatorError("saved route evidence does not match its run identity")
    identity_binding = manifest.get("identity_binding")
    if not isinstance(identity_binding, dict) or identity_binding.get("evidence_sha256") != _sha(_json_bytes(evidence)):
        raise CoordinatorError("saved evidence digest does not match the run identity")
    if identity_binding.get("route_find_sha256") != _sha((run_dir / "route-find.json").read_bytes()):
        raise CoordinatorError("saved route lookup digest does not match the run identity")
    return run_dir, manifest


def draft(repo_arg: str, db_arg: str, route_fact_id: str, run_arg: str,
          draft_arg: str, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    run_dir, manifest = _load_bound_run(repo_arg, db_arg, route_fact_id, run_arg)
    artifacts = manifest["artifacts"]
    draft_path = run_dir / "luna-draft.json"
    external = Path(draft_arg).expanduser().resolve(strict=True).read_bytes()
    if draft_path.exists():
        if draft_path.read_bytes() != external:
            raise CoordinatorError("a different Luna draft is already recorded; start a fresh run")
    else:
        _record_artifact(manifest, run_dir, draft_path.name, external)
        _write_manifest(run_dir / MANIFEST, manifest)
    try:
        draft_value = json.loads(external.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"Luna draft is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(draft_value, dict):
        raise CoordinatorError("Luna draft must be a JSON object")
    if draft_value.get("snapshot_id") != manifest["identity"].get("snapshot_id") or draft_value.get("extractor_identity") != manifest["identity"].get("extractor_identity"):
        raise CoordinatorError("Luna draft is bound to another snapshot or extractor")
    if "review-packet.json" in artifacts:
        packet, raw = _read_json(run_dir / "review-packet.json", "saved review packet")
        _write_manifest(run_dir / MANIFEST, manifest)
        return {"result": "review_ready", "packet_sha256": packet.get("packet_sha256"),
                "packet_path": os.fspath(run_dir / "review-packet.json"), "packet_bytes": len(raw), "resumed": True}
    prefix = _atlas_prefix(manifest["identity"])
    stdout, stderr, code, elapsed = _run_atlas([
        "route-map-prepare", *prefix, "--route-fact-id", route_fact_id,
        "--draft-file", os.fspath(draft_path), "--max-tokens", str(max_bytes),
    ])
    packet = _save_atlas_output(manifest, run_dir, "review-packet.json", stdout, stderr, code,
                                "route-map-prepare", elapsed)
    if packet.get("binding", {}).get("route_fact_id") != route_fact_id or packet.get("binding", {}).get("snapshot_id") != manifest["identity"].get("snapshot_id"):
        raise CoordinatorError("Atlas review packet does not match the prepared route identity")
    if packet.get("evidence_sha256") != manifest["identity_binding"].get("evidence_sha256"):
        raise CoordinatorError("review packet evidence differs from the prepared complete packet")
    _write_manifest(run_dir / MANIFEST, manifest)
    return {"result": "review_ready", "packet_sha256": packet.get("packet_sha256"),
            "packet_path": os.fspath(run_dir / "review-packet.json"), "packet_bytes": len(stdout),
            "provider_model_tokens": "unavailable_without_provider_telemetry"}


def _expected_overlay(packet: dict[str, object]) -> str:
    draft_text = packet.get("draft")
    if not isinstance(draft_text, str):
        raise CoordinatorError("review packet does not contain exact draft bytes")
    try:
        draft_value = json.loads(draft_text)
    except json.JSONDecodeError as exc:
        raise CoordinatorError("review packet draft is invalid JSON") from exc
    return _sha(_json_bytes(draft_value).rstrip(b"\n"))


def publish(repo_arg: str, db_arg: str, route_fact_id: str, run_arg: str,
            review_arg: str, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    run_dir, manifest = _load_bound_run(repo_arg, db_arg, route_fact_id, run_arg)
    artifacts = manifest["artifacts"]
    if "review-packet.json" not in artifacts:
        raise CoordinatorError("publish requires a saved Luna draft and independent-review packet")
    review_path = run_dir / "sol-review.json"
    review_input = Path(review_arg).expanduser().resolve(strict=True).read_bytes()
    if review_path.exists():
        if review_path.read_bytes() != review_input:
            raise CoordinatorError("a different Sol review is already recorded; start a fresh run")
    else:
        _record_artifact(manifest, run_dir, review_path.name, review_input)
        _write_manifest(run_dir / MANIFEST, manifest)
    packet, _packet_raw = _read_json(run_dir / "review-packet.json", "saved review packet")
    review, _review_raw = _read_json(review_path, "independent Sol review")
    if packet.get("binding", {}).get("route_fact_id") != route_fact_id:
        raise CoordinatorError("review packet belongs to another route fact")
    prefix = _atlas_prefix(manifest["identity"])
    existing, existing_stderr, existing_code, existing_elapsed = _run_atlas([
        "route-find", *prefix, "--route-fact-id", route_fact_id, "--max-tokens", str(max_bytes),
    ])
    if existing_code != 0:
        _record_stage(manifest, "route-find-before-publish", existing, existing_elapsed, [], existing_stderr)
        _write_manifest(run_dir / MANIFEST, manifest)
        raise CoordinatorError(os.fsdecode(existing_stderr).strip() or "Atlas could not verify the route before publish")
    _record_stage(manifest, "route-find-before-publish", existing, existing_elapsed, [])
    _write_manifest(run_dir / MANIFEST, manifest)
    try:
        current = json.loads(existing.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"Atlas route lookup failed during publish: {exc}") from exc
    expected_overlay = _expected_overlay(packet)
    recovered = current.get("result") == "fresh" and current.get("association", {}).get("binding", {}).get("overlay_id") == expected_overlay
    if current.get("result") == "fresh" and not recovered:
        raise CoordinatorError("route already has a different accepted map; refusing publication")
    if "review-validation.json" in artifacts:
        validation, _ = _read_json(run_dir / "review-validation.json", "saved review validation")
        if validation.get("packet_sha256") != packet.get("packet_sha256"):
            raise CoordinatorError("saved review validation belongs to another packet")
    else:
        if recovered:
            raise CoordinatorError("existing association has no saved successful independent-review validation")
        _write_manifest(run_dir / MANIFEST, manifest)
        review_stdout, review_stderr, review_code, review_elapsed = _run_atlas([
            "route-map-review", *prefix, "--packet-file", os.fspath(run_dir / "review-packet.json"),
            "--review-file", os.fspath(review_path),
        ])
        validation = _save_atlas_output(manifest, run_dir, "review-validation.json", review_stdout,
                                        review_stderr, review_code, "route-map-review", review_elapsed)
        _write_manifest(run_dir / MANIFEST, manifest)
    if validation.get("result") != "accepted":
        return {"result": "rejected", "writes": 0, "review_path": os.fspath(review_path)}
    # The Atlas writer rechecks the exact packet and review in one SQLite transaction.
    publish_stdout, publish_stderr, publish_code, publish_elapsed = _run_atlas([
        "route-map-publish", *prefix, "--packet-file", os.fspath(run_dir / "review-packet.json"),
        "--review-file", os.fspath(review_path),
    ])
    published = _save_atlas_output(manifest, run_dir, "publish-result.json", publish_stdout,
                                   publish_stderr, publish_code, "route-map-publish", publish_elapsed)
    _write_manifest(run_dir / MANIFEST, manifest)
    found_stdout, found_stderr, found_code, found_elapsed = _run_atlas([
        "route-find", *prefix, "--route-fact-id", route_fact_id, "--max-tokens", str(max_bytes),
    ])
    found = _save_atlas_output(manifest, run_dir, "published-route-find.json", found_stdout,
                               found_stderr, found_code, "route-find-after-publish", found_elapsed)
    if (found.get("result") != "fresh" or found.get("snapshot_id") != manifest["identity"].get("snapshot_id")
            or found.get("association", {}).get("binding", {}).get("overlay_id") != published.get("overlay_id")
            or found.get("claim_selection", {}).get("omitted_claims") != 0):
        raise CoordinatorError("published route failed fresh complete retrieval verification")
    _write_manifest(run_dir / MANIFEST, manifest)
    return {"result": "published_and_fresh", "snapshot_id": found["snapshot_id"],
            "route_fact_id": route_fact_id, "overlay_id": published["overlay_id"],
            "claim_count": found.get("claim_selection", {}).get("total_claims"),
            "idempotent_recovery": bool(published.get("idempotent")),
            "provider_model_tokens": "unavailable_without_provider_telemetry"}


def status(repo_arg: str, db_arg: str, route_fact_id: str, run_arg: str,
           max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    run_dir, manifest = _load_bound_run(repo_arg, db_arg, route_fact_id, run_arg)
    prefix = _atlas_prefix(manifest["identity"])
    stdout, stderr, code, elapsed = _run_atlas([
        "route-find", *prefix, "--route-fact-id", route_fact_id, "--max-tokens", str(max_bytes),
    ])
    if code != 0:
        raise CoordinatorError(os.fsdecode(stderr).strip() or "Atlas could not verify current route state")
    current = json.loads(stdout.decode("utf-8"))
    identity = manifest["identity"]
    if current.get("snapshot_id") != identity.get("snapshot_id") or current.get("route_fact_id") != route_fact_id:
        raise CoordinatorError("current route identity differs from this run")
    actual = "prepared"
    if "review-packet.json" in manifest["artifacts"]:
        actual = "review_ready"
    if "review-validation.json" in manifest["artifacts"]:
        validation, _ = _read_json(run_dir / "review-validation.json", "saved review validation")
        actual = "accepted_review_ready_to_publish" if validation.get("result") == "accepted" else "review_rejected"
    if current.get("result") == "fresh":
        overlay = current.get("association", {}).get("binding", {}).get("overlay_id")
        packet = None
        if "review-packet.json" in manifest["artifacts"]:
            packet, _ = _read_json(run_dir / "review-packet.json", "saved review packet")
        if packet is not None and overlay == _expected_overlay(packet):
            actual = "published_and_fresh"
        else:
            raise CoordinatorError("route is mapped, but its current association does not match this run")
    elif current.get("result") != "unmapped":
        raise CoordinatorError(f"unexpected route-find result for run status: {current.get('result')}")
    stages = manifest.get("stages", [])
    return {"result": actual, "route_result": current.get("result"), "identity": identity,
            "stage_count": len(stages), "stages": stages,
            "current_route_find_bytes": len(stdout), "current_route_find_elapsed_ms": elapsed,
            "provider_model_tokens": "unavailable_without_provider_telemetry"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "draft", "publish", "status"):
        sub = commands.add_parser(command)
        sub.add_argument("--repo", required=True)
        sub.add_argument("--db", required=True)
        sub.add_argument("--route-fact-id", required=True)
        sub.add_argument("--run-dir", required=True)
        sub.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
        if command == "draft":
            sub.add_argument("--draft-file", required=True)
        elif command == "publish":
            sub.add_argument("--review-file", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.repo, args.db, args.route_fact_id, args.run_dir, args.max_bytes)
        elif args.command == "draft":
            result = draft(args.repo, args.db, args.route_fact_id, args.run_dir, args.draft_file, args.max_bytes)
        elif args.command == "publish":
            result = publish(args.repo, args.db, args.route_fact_id, args.run_dir, args.review_file, args.max_bytes)
        else:
            result = status(args.repo, args.db, args.route_fact_id, args.run_dir, args.max_bytes)
    except (CoordinatorError, OSError, json.JSONDecodeError) as exc:
        print(f"route-coordinator: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
