#!/usr/bin/env python3
"""Prepare, inspect, and publish one durable source-grounded Atlas workspace."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
ATLAS = HERE / "atlas.py"
ROUTE_COORDINATOR = HERE / "route_coordinator.py"
SCHEMA_VERSION = 1
MAX_BYTES = 1_048_576
PROFILES = ("local-storage", "cloud-storage")


class WorkspaceError(Exception):
    """An expected workspace identity, integrity, or stage failure."""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hash_file(path: Path) -> str:
    return _sha(path.read_bytes())


def _safe_path(path_arg: str | Path, *, allow_missing: bool, label: str) -> Path:
    path = Path(path_arg).expanduser()
    if not path.is_absolute():
        raise WorkspaceError(f"{label} must be an absolute path")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise WorkspaceError(f"{label} contains a symbolic link: {item}")
    if allow_missing:
        resolved = path.resolve(strict=False)
    else:
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise WorkspaceError(f"{label} does not exist: {path}") from exc
    if path.as_posix() != resolved.as_posix():
        raise WorkspaceError(f"{label} is not canonical: {path}")
    return resolved


def _state_child(root: Path, child: str | Path, *, allow_missing: bool, label: str) -> Path:
    path = _safe_path(root / child, allow_missing=allow_missing, label=label)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WorkspaceError(f"{label} resolves outside the canonical workspace state root") from exc
    return path


def _state_root(state_arg: str | Path, repo: Path | None = None) -> Path:
    root = _safe_path(state_arg, allow_missing=True, label="workspace state path")
    if repo is not None:
        try:
            root.relative_to(repo)
        except ValueError:
            pass
        else:
            raise WorkspaceError("workspace state must be outside the target repository")
    return root


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        path = _safe_path(path, allow_missing=False, label=label)
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"cannot read {label} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkspaceError(f"{label} must be a JSON object: {path}")
    return value


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    path = _safe_path(path, allow_missing=True, label="workspace artifact")
    raw = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _safe_path(path, allow_missing=True, label="workspace artifact")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise WorkspaceError(f"cannot save workspace state {path}: {exc}") from exc


def _command(args: list[str], *, dotnet: str | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    if dotnet:
        env["ATLAS_DOTNET"] = dotnet
    try:
        result = subprocess.run([sys.executable, os.fspath(ATLAS), *args], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False, env=env)
    except OSError as exc:
        raise WorkspaceError(f"cannot run Atlas command {args[0]}: {exc}") from exc
    if result.returncode:
        detail = os.fsdecode(result.stderr).strip() or f"Atlas exited {result.returncode}"
        raise WorkspaceError(f"Atlas {args[0]} failed: {detail}")
    try:
        value = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"Atlas {args[0]} did not return valid JSON") from exc
    if not isinstance(value, dict):
        raise WorkspaceError(f"Atlas {args[0]} returned a non-object result")
    return value


def _copy_sqlite_once(seed: Path, database: Path) -> None:
    database = _safe_path(database, allow_missing=True, label="workspace Atlas database")
    expected = _hash_file(seed)
    if database.exists():
        return
    database.parent.mkdir(parents=True, exist_ok=True)
    temporary = database.with_name(f".{database.name}.{os.getpid()}.tmp")
    temporary = _safe_path(temporary, allow_missing=True, label="workspace database temporary file")
    if temporary.exists():
        raise WorkspaceError(f"interrupted database copy needs operator review: {temporary}")
    try:
        source = sqlite3.connect(seed.as_uri() + "?mode=ro", uri=True)
        target = sqlite3.connect(temporary)
        try:
            source.backup(target)
            target.commit()
        finally:
            target.close()
            source.close()
        if _hash_file(seed) != expected:
            raise WorkspaceError("historical seed changed while it was copied")
        os.replace(temporary, database)
    except (sqlite3.Error, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise WorkspaceError(f"cannot preserve historical Atlas records: {exc}") from exc


def _producer_identity() -> dict[str, str]:
    return {name: _hash_file(path) for name, path in (
        ("atlas_sha256", ATLAS), ("workspace_sha256", Path(__file__).resolve()),
        ("route_coordinator_sha256", ROUTE_COORDINATOR),
        ("launcher_sha256", HERE / "atlas_launch.py"),
    )}


def _historical_routes_from_database(database: Path, current_snapshot_id: str,
                                     seed_sha256: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sys.path.insert(0, os.fspath(HERE))
    import atlas  # type: ignore

    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute("SELECT snapshot_id,payload_json FROM atlas_snapshots ORDER BY snapshot_id").fetchall()
    snapshots = {str(row_id): json.loads(payload) for row_id, payload in rows}
    origins_by_route: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    ordered = sorted((item for item in snapshots.values() if item.get("snapshot_id") != current_snapshot_id),
                     key=lambda item: str(item.get("snapshot_id", "")))
    for snapshot in ordered:
        terminal = atlas._validated_route_associations(os.fspath(database), database, snapshot, snapshots)
        for route_id, candidates in terminal.items():
            current = [item for item in candidates if item.get("binding", {}).get("snapshot_id") == snapshot.get("snapshot_id")]
            if len(current) > 1:
                raise WorkspaceError(f"historical route {route_id} has multiple terminal associations on one snapshot")
            if not current:
                continue
            association = current[0]
            flow = atlas.query_flow(os.fspath(database), str(snapshot["snapshot_id"]), str(association["binding"]["overlay_id"]))
            origins_by_route.setdefault(route_id, []).append(
                (str(snapshot["snapshot_id"]), str(association["binding"]["overlay_id"]), flow["overlay"]))
    routes = []
    for route_id, origins in sorted(origins_by_route.items()):
        if not isinstance(route_id, str) or Path(route_id).name != route_id or route_id in {"", ".", ".."}:
            raise WorkspaceError("historical route ID is not a safe workspace filename")
        identities = {(snapshot_id, overlay_id) for snapshot_id, overlay_id, _overlay in origins}
        if len(identities) != 1 or len(origins) != 1:
            raise WorkspaceError(f"historical route {route_id} has ambiguous accepted origins across snapshots")
        snapshot_id, overlay_id, overlay = origins[0]
        routes.append({"route_fact_id": route_id, "origin_snapshot_id": snapshot_id,
                       "origin_overlay_id": overlay_id, "title": overlay["title"],
                       "reviewed_conclusions": overlay["reviewed_conclusions"]})
    return routes, {"seed_sha256": seed_sha256,
                    "snapshot_ids": sorted(item for item in snapshots if item != current_snapshot_id),
                    "terminal_route_count": len(routes),
                    "reviewed_conclusion_count": sum(len(item["reviewed_conclusions"]) for item in routes)}


def _candidate_draft(route: dict[str, Any], snapshot_id: str, extractor_identity: str) -> dict[str, Any]:
    return {"overlay_schema_version": 1, "title": route["title"], "snapshot_id": snapshot_id,
            "extractor_identity": extractor_identity,
            "reviewed_conclusions": route["reviewed_conclusions"]}


def _prepare_historical_candidate(repo: Path, database: Path, route: dict[str, Any],
                                 run_dir: Path, candidate_path: Path, max_bytes: int,
                                 correction_packet_path: Path | None = None,
                                 correction_review_path: Path | None = None) -> None:
    import route_coordinator as coordinator  # type: ignore

    run_dir = _safe_path(run_dir, allow_missing=True, label="route run directory")
    candidate_path = _safe_path(candidate_path, allow_missing=False, label="historical candidate draft")
    route_id = route["route_fact_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    run_dir, manifest = coordinator._load_bound_run(
        os.fspath(repo), os.fspath(database), route_id, os.fspath(run_dir),
    )
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    raw = candidate_path.read_bytes()
    if "luna-draft.json" in artifacts:
        if (run_dir / "luna-draft.json").read_bytes() != raw:
            raise WorkspaceError(f"historical route {route_id} has conflicting saved candidate bytes")
    else:
        coordinator._record_artifact(manifest, run_dir, "luna-draft.json", raw)
    if "review-packet.json" in artifacts:
        packet = _read_json(run_dir / "review-packet.json", "historical route packet")
        if packet.get("historical_origin", {}).get("snapshot_id") != route["origin_snapshot_id"] or packet.get("historical_origin", {}).get("overlay_id") != route["origin_overlay_id"]:
            raise WorkspaceError(f"historical route {route_id} packet is bound to another origin")
        if correction_packet_path is not None:
            import atlas  # type: ignore
            prior_packet = _read_json(correction_packet_path, "rejected predecessor packet")
            prior_review = _read_json(correction_review_path, "rejected predecessor review") if correction_review_path else {}
            correction = packet.get("historical_correction")
            if (not isinstance(correction, dict)
                    or correction.get("prior_packet_sha256") != prior_packet.get("packet_sha256")
                    or correction.get("prior_review_sha256") != hashlib.sha256(atlas._canonical_json(prior_review)).hexdigest()):
                raise WorkspaceError(f"historical route {route_id} R1 packet is bound to different R0 review bytes")
        return
    args = ["route-map-prepare", "--db", os.fspath(database), "--repo", os.fspath(repo),
            "--route-fact-id", route_id, "--draft-file", os.fspath(run_dir / "luna-draft.json"),
            "--max-tokens", str(max_bytes), "--origin-snapshot", route["origin_snapshot_id"],
            "--origin-overlay", route["origin_overlay_id"]]
    if correction_packet_path is not None and correction_review_path is not None:
        args.extend(["--correction-packet-file", os.fspath(correction_packet_path),
                     "--correction-review-file", os.fspath(correction_review_path)])
    stdout, stderr, code, elapsed = coordinator._run_atlas(args)
    coordinator._save_atlas_output(manifest, run_dir, "review-packet.json", stdout, stderr, code,
                                   "route-map-prepare-historical", elapsed)


def _route_run_status(repo: Path, database: Path, route: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    import route_coordinator as coordinator  # type: ignore
    import atlas  # type: ignore

    route_id = route["route_fact_id"]
    expected = {"repository_root": os.fspath(repo), "database_path": os.fspath(database),
                "route_fact_id": route_id}
    run_dir = _safe_path(run_dir, allow_missing=False, label="route run directory")
    manifest_path = run_dir / coordinator.MANIFEST
    manifest = _read_json(manifest_path, "route coordinator manifest")
    coordinator._validate_manifest_artifacts(run_dir, manifest, expected)
    if manifest.get("pending_artifacts") or any(coordinator.MANIFEST_TEMP.fullmatch(item.name) for item in run_dir.iterdir()):
        raise WorkspaceError(f"route {route_id} has an interrupted coordinator write; run prepare to recover it")
    artifacts = manifest.get("artifacts", {})
    state = "prepared"
    packet_sha = None
    packet_path = run_dir / "review-packet.json"
    packet = None
    if "review-packet.json" in artifacts:
        packet = _read_json(packet_path, "route review packet")
        packet_sha = packet.get("packet_sha256")
        state = "review-ready"
        if packet.get("binding", {}).get("route_fact_id") != route_id:
            raise WorkspaceError(f"route {route_id} packet is bound to a different route")
        try:
            expected_overlay_id = coordinator._expected_overlay(packet)
            atlas._route_map_validate_packet(packet, os.fspath(database), os.fspath(repo),
                                             allow_existing_overlay_id=expected_overlay_id)
        except Exception as exc:
            raise WorkspaceError(f"route {route_id} saved review packet no longer validates: {exc}") from exc
        origin = packet.get("historical_origin")
        if (not isinstance(origin, dict)
                or origin.get("snapshot_id") != route.get("origin_snapshot_id")
                or origin.get("overlay_id") != route.get("origin_overlay_id")):
            raise WorkspaceError(f"route {route_id} packet is not bound to its preserved historical origin")
    if "review-validation.json" in artifacts:
        validation = _read_json(run_dir / "review-validation.json", "route review validation")
        if "sol-review.json" not in artifacts or packet is None:
            raise WorkspaceError(f"route {route_id} review validation has no exact saved review or packet")
        checked = _command(["route-map-review", "--repo", os.fspath(repo), "--db", os.fspath(database),
                            "--packet-file", os.fspath(packet_path), "--review-file", os.fspath(run_dir / "sol-review.json")])
        if checked.get("packet_sha256") != packet_sha or checked.get("result") != validation.get("result"):
            raise WorkspaceError(f"route {route_id} saved review validation does not reconstruct")
        state = "accepted-review" if checked.get("result") == "accepted" else "review-rejected"
    found = _command(["route-find", "--repo", os.fspath(repo), "--db", os.fspath(database),
                      "--route-fact-id", route_id, "--max-tokens", str(MAX_BYTES)])
    if found.get("result") == "fresh":
        overlay_id = found.get("association", {}).get("binding", {}).get("overlay_id")
        expected_overlay = coordinator._expected_overlay(packet) if packet is not None else None
        if overlay_id != expected_overlay:
            state = "conflict-mapped"
        else:
            if packet is None or "sol-review.json" not in artifacts or "review-validation.json" not in artifacts:
                raise WorkspaceError(f"route {route_id} has a current map without its exact accepted saved review")
            review = _read_json(run_dir / "sol-review.json", "route independent review")
            if review.get("decision") != "accepted" or state != "accepted-review":
                raise WorkspaceError(f"route {route_id} current map is not backed by its saved accepted review")
            association = found.get("association")
            binding = association.get("binding") if isinstance(association, dict) else None
            if not isinstance(binding, dict):
                raise WorkspaceError(f"route {route_id} current association lacks its exact binding")
            flow = atlas.query_flow(os.fspath(database), str(binding.get("snapshot_id")), str(overlay_id))
            expected_receipt = atlas._route_map_review_receipt(packet, review)
            expected_receipt_payload = {**expected_receipt,
                                        "receipt_hash": hashlib.sha256(atlas._canonical_json(expected_receipt)).hexdigest()}
            if (flow.get("review_status") != "accepted"
                    or flow.get("review_receipt") != expected_receipt_payload
                    or flow.get("overlay", {}).get("content_hash") != overlay_id):
                raise WorkspaceError(f"route {route_id} current receipt does not reconstruct from its exact saved packet and review")
            if "publish-result.json" in artifacts:
                published = _read_json(run_dir / "publish-result.json", "route publish result")
                expected_publish = {
                    "result": "published", "snapshot_id": binding["snapshot_id"],
                    "route_fact_id": route_id, "overlay_id": overlay_id,
                    "receipt_hash": expected_receipt_payload["receipt_hash"],
                    "binding_hash": association.get("binding_hash"),
                    "association_review_hash": association.get("association_review_hash"),
                    "packet_sha256": packet["packet_sha256"],
                    "evidence_sha256": packet["evidence_sha256"],
                }
                if (set(published) != set(expected_publish) | {"idempotent"}
                        or any(published.get(key) != value for key, value in expected_publish.items())
                        or not isinstance(published.get("idempotent"), bool)):
                    raise WorkspaceError(f"route {route_id} publish result does not match its exact validated receipt")
                state = "published"
            else:
                state = "publish-recovery"
    elif found.get("result") != "unmapped":
        raise WorkspaceError(f"route {route_id} returned unexpected current state {found.get('result')!r}")
    return {"route_fact_id": route_id, "origin_snapshot_id": route["origin_snapshot_id"],
            "origin_overlay_id": route["origin_overlay_id"], "state": state, "run_dir": os.fspath(run_dir),
            "packet_path": os.fspath(packet_path) if packet_sha else None, "packet_sha256": packet_sha}


def _rejected_r0_status(repo: Path, database: Path, route: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    import atlas  # type: ignore
    import route_coordinator as coordinator  # type: ignore

    route_id = route["route_fact_id"]
    run_dir = _safe_path(run_dir, allow_missing=False, label="R0 route run directory")
    manifest = _read_json(run_dir / coordinator.MANIFEST, "R0 route coordinator manifest")
    expected = {"repository_root": os.fspath(repo), "database_path": os.fspath(database), "route_fact_id": route_id}
    coordinator._validate_manifest_artifacts(run_dir, manifest, expected)
    if manifest.get("pending_artifacts") or any(coordinator.MANIFEST_TEMP.fullmatch(item.name) for item in run_dir.iterdir()):
        raise WorkspaceError(f"route {route_id} has an interrupted R0 write; correction is refused")
    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, dict) or not {"review-packet.json", "sol-review.json", "review-validation.json"} <= set(artifacts):
        raise WorkspaceError("historical correction requires a complete R0 packet, review, and validation artifact")
    packet = _read_json(run_dir / "review-packet.json", "R0 review packet")
    review = _read_json(run_dir / "sol-review.json", "R0 independent review")
    validation = _read_json(run_dir / "review-validation.json", "R0 review validation")
    try:
        atlas._validate_historical_rejected_predecessor(packet, review, os.fspath(database), os.fspath(repo))
    except atlas.AtlasError as exc:
        raise WorkspaceError(f"historical correction R0 packet/review refuses: {exc}") from exc
    expected_validation = {"result": "rejected", "packet_sha256": packet.get("packet_sha256"),
                           "evidence_sha256": packet.get("evidence_sha256"), "draft_sha256": packet.get("draft_sha256"),
                           "review": review, "writes": 0}
    if validation != expected_validation:
        raise WorkspaceError("saved R0 review-validation artifact does not match the exact reconstructed rejected review")
    return {"route_fact_id": route_id, "origin_snapshot_id": route["origin_snapshot_id"],
            "origin_overlay_id": route["origin_overlay_id"], "state": "review-rejected",
            "run_dir": os.fspath(run_dir), "packet_path": os.fspath(run_dir / "review-packet.json"),
            "packet_sha256": packet.get("packet_sha256")}


def _active_route_run_status(repo: Path, database: Path, route: dict[str, Any], base_run_dir: Path) -> dict[str, Any]:
    state = base_run_dir.parents[1]
    correction_dir = _state_child(state, Path("correction-runs") / route["route_fact_id"] / "r1",
                                  allow_missing=True,
                                label="historical correction run directory")
    if not correction_dir.exists():
        return _route_run_status(repo, database, route, base_run_dir)
    _rejected_r0_status(repo, database, route, base_run_dir)
    corrected = _route_run_status(repo, database, route, correction_dir)
    if corrected["packet_path"] is None:
        raise WorkspaceError(f"route {route['route_fact_id']} correction round has no validated R1 packet")
    return corrected


def _validate_workspace(root: Path) -> tuple[dict[str, Any], Path]:
    manifest_path = root / "workspace.json"
    manifest = _read_json(manifest_path, "workspace manifest")
    keys = {"schema_version", "inputs", "database_path", "snapshot_id", "extractor_identity",
            "compiler_supplement_sha256", "runtime_profiles", "historical", "routes", "producer_identity"}
    if set(manifest) != keys or manifest.get("schema_version") != SCHEMA_VERSION:
        raise WorkspaceError("workspace manifest has an unsupported or noncanonical schema")
    database = _safe_path(manifest["database_path"], allow_missing=False, label="Atlas database")
    if database != root / "atlas.sqlite":
        raise WorkspaceError("workspace database path does not match its state root")
    repo = Path(manifest.get("inputs", {}).get("repository_root", ""))
    _state_root(root, repo)
    if manifest.get("producer_identity") != _producer_identity():
        raise WorkspaceError("workspace producer files changed; prepare again to refresh identity")
    _validate_current_layers(manifest, database)
    routes = manifest.get("routes")
    if not isinstance(routes, list):
        raise WorkspaceError("workspace route table is malformed")
    seen: set[str] = set()
    for route in routes:
        if not isinstance(route, dict) or set(route) != {"route_fact_id", "origin_snapshot_id", "origin_overlay_id", "state", "run_dir", "packet_path", "packet_sha256"}:
            raise WorkspaceError("workspace route row has an unsupported schema")
        route_id = route.get("route_fact_id")
        if not isinstance(route_id, str) or route_id in seen or not route_id:
            raise WorkspaceError("workspace route IDs must be unique nonempty strings")
        seen.add(route_id)
        expected_run = root / "route-runs" / route_id
        if route.get("run_dir") != os.fspath(expected_run):
            raise WorkspaceError(f"route {route_id} run directory must be its canonical workspace child")
    expected_routes, expected_history = _historical_routes_from_database(
        database, str(manifest.get("snapshot_id")), manifest.get("inputs", {}).get("seed_sha256"),
    )
    expected_origins = {item["route_fact_id"]: (item["origin_snapshot_id"], item["origin_overlay_id"])
                        for item in expected_routes}
    if set(seen) != set(expected_origins):
        raise WorkspaceError("workspace route queue does not match all accepted historical routes in its database")
    if manifest.get("historical") != expected_history:
        raise WorkspaceError("workspace historical summary does not reconstruct from its preserved database")
    for route in routes:
        if (route["origin_snapshot_id"], route["origin_overlay_id"]) != expected_origins[route["route_fact_id"]]:
            raise WorkspaceError(f"route {route['route_fact_id']} origin does not match the preserved database")
        source_route = next(item for item in expected_routes if item["route_fact_id"] == route["route_fact_id"])
        candidate_path = _safe_path(root / "candidates" / f"{route['route_fact_id']}.json",
                                    allow_missing=False, label="historical candidate draft")
        candidate = _read_json(candidate_path, "historical candidate draft")
        expected_candidate = _candidate_draft(source_route, str(manifest["snapshot_id"]),
                                              str(manifest["extractor_identity"]))
        if _json_bytes(candidate) != _json_bytes(expected_candidate):
            raise WorkspaceError(f"route {route['route_fact_id']} candidate draft differs from its preserved origin")
    return manifest, database


def _validate_current_layers(manifest: dict[str, Any], database: Path) -> None:
    import atlas  # type: ignore

    repo = Path(manifest["inputs"]["repository_root"])
    snapshot, _snapshots, extractor, _live = atlas._current_route_snapshot(database, os.fspath(repo))
    if snapshot.get("snapshot_id") != manifest.get("snapshot_id") or extractor != manifest.get("extractor_identity"):
        raise WorkspaceError("workspace snapshot or extractor is stale against the current checkout")
    supplements = atlas._current_compiler_supplements(database, snapshot, repo)
    matching = [item for item in supplements if item.get("binding", {}).get("project_path") == manifest["inputs"]["project_path"]
                and item.get("binding", {}).get("target_framework") == manifest["inputs"]["framework"]
                and item.get("content_sha256") == manifest.get("compiler_supplement_sha256")]
    if len(matching) != 1:
        raise WorkspaceError("workspace compiler supplement is missing, stale, or ambiguous")
    observations = atlas._current_runtime_observations(database, snapshot, repo, supplements)
    selected = [item for item in observations
                if item.get("binding", {}).get("project_path") == manifest["inputs"]["project_path"]
                and item.get("binding", {}).get("interface_type") == manifest["inputs"]["interface_name"]]
    by_profile = {item.get("binding", {}).get("profile"): item for item in selected}
    if set(by_profile) != set(PROFILES):
        raise WorkspaceError("workspace requires one current validated startup receipt for each approved profile")
    observed = _profile_summaries(atlas, by_profile)
    if manifest.get("runtime_profiles") != observed:
        raise WorkspaceError("workspace runtime profile summaries do not match the current validated receipts")


def _profile_summaries(atlas_module: Any, by_profile: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {profile: {"profile": profile,
                      "expected_runtime_type": by_profile[profile]["binding"].get("candidate_type"),
                      "observed_runtime_type": by_profile[profile]["capture"].get("observed_runtime_type"),
                      "input_sha256": by_profile[profile].get("input_sha256"),
                      "content_sha256": hashlib.sha256(atlas_module._canonical_json(by_profile[profile])).hexdigest(),
                      "status": "validated"}
            for profile in PROFILES}


def prepare(repo_arg: str, state_arg: str, project_path: str, framework: str,
            interface_name: str, dotnet: str, seed_db_arg: str | None = None,
            max_bytes: int = MAX_BYTES) -> dict[str, Any]:
    producer_identity_at_entry = _producer_identity()
    repo = Path(repo_arg).expanduser().resolve(strict=True)
    if not repo.is_dir() or not (repo / ".git").exists():
        raise WorkspaceError("repository must be a real Git checkout")
    state = _state_root(state_arg, repo)
    if max_bytes < 1:
        raise WorkspaceError("max_bytes must be positive")
    project = Path(project_path)
    if project.is_absolute() or ".." in project.parts or project.suffix != ".csproj":
        raise WorkspaceError("project_path must be one exact repository-relative .csproj path")
    project_file = _safe_path(repo / project, allow_missing=False, label="project file")
    try:
        project_file.relative_to(repo)
    except ValueError as exc:
        raise WorkspaceError("project file resolves outside the target repository") from exc
    try:
        dotnet_path = Path(dotnet).expanduser().resolve(strict=True)
    except OSError as exc:
        raise WorkspaceError(f"dotnet SDK executable does not exist: {dotnet}") from exc
    if not dotnet_path.is_file():
        raise WorkspaceError(f"dotnet SDK executable is not a file: {dotnet_path}")
    seed = _safe_path(seed_db_arg, allow_missing=False, label="historical seed database") if seed_db_arg else None
    if seed == state / "atlas.sqlite":
        raise WorkspaceError("historical seed cannot be the workspace database")
    state = _safe_path(state, allow_missing=True, label="workspace state path")
    state.mkdir(parents=True, exist_ok=True)
    state = _safe_path(state, allow_missing=False, label="workspace state path")
    ignore = _state_child(state, ".gitignore", allow_missing=True, label="workspace .gitignore")
    if ignore.exists() and ignore.read_text(encoding="utf-8") != "*\n":
        raise WorkspaceError("workspace .gitignore must contain only '*'")
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    database = _state_child(state, "atlas.sqlite", allow_missing=True, label="workspace Atlas database")
    project_rel = project_file.relative_to(repo).as_posix()
    proposed_inputs = {"repository_root": os.fspath(repo), "project_path": project_rel,
                       "framework": framework, "interface_name": interface_name,
                       "seed_sha256": _hash_file(seed) if seed is not None else None, "dotnet_path": os.fspath(dotnet_path),
                       "max_bytes": max_bytes}
    existing_path = _state_child(state, "workspace.json", allow_missing=True, label="workspace manifest")
    init_path = _state_child(state, "workspace-initializing.json", allow_missing=True, label="workspace initialization record")
    existing_manifest = None
    if existing_path.exists():
        existing_manifest, _ = _validate_workspace(state)
        if existing_manifest.get("inputs") != proposed_inputs:
            raise WorkspaceError("workspace is bound to different inputs; use a new empty state path")
    if init_path.exists():
        initializing = _read_json(init_path, "workspace initialization record")
        if set(initializing) != {"schema_version", "inputs"} or initializing.get("schema_version") != SCHEMA_VERSION or initializing.get("inputs") != proposed_inputs:
            raise WorkspaceError("interrupted workspace preparation belongs to different inputs")
    elif not existing_path.exists() and database.exists():
        raise WorkspaceError("Atlas database exists without a workspace manifest or initialization record; refusing to adopt it")
    else:
        _write_atomic(init_path, {"schema_version": SCHEMA_VERSION, "inputs": proposed_inputs})
    sys.path.insert(0, os.fspath(HERE))
    import atlas  # type: ignore
    if existing_manifest is not None:
        snapshot_id = str(existing_manifest["snapshot_id"])
        extractor = str(existing_manifest["extractor_identity"])
        supplement_hash = str(existing_manifest["compiler_supplement_sha256"])
        profiles = existing_manifest["runtime_profiles"]
    else:
        if seed is not None:
            _copy_sqlite_once(seed, database)
        elif not database.exists():
            connection = sqlite3.connect(database)
            connection.close()
        index = _command(["index", "--repo", os.fspath(repo), "--db", os.fspath(database)])
        snapshot_id = index.get("snapshot_id")
        if not isinstance(snapshot_id, str):
            raise WorkspaceError("Atlas index did not return a current snapshot identity")
        extractor = index.get("extractor_identity")
        if not isinstance(extractor, str):
            extractor = index.get("source_graph", {}).get("extractor_identity") if isinstance(index.get("source_graph"), dict) else None
        if not isinstance(extractor, str):
            raise WorkspaceError("current index lacks its extractor identity")
        compiler = _command(["compiler-index", "--repo", os.fspath(repo), "--db", os.fspath(database),
                             "--project", project_rel, "--framework", framework], dotnet=os.fspath(dotnet_path))
        supplement_hash = compiler.get("content_sha256")
        if not isinstance(supplement_hash, str):
            raise WorkspaceError("compiler-index did not return a supplement hash")
        runtime = _command(["runtime-index", "--repo", os.fspath(repo), "--db", os.fspath(database),
                            "--project", project_rel, "--framework", framework,
                            "--interface", interface_name, "--profile", "both", "--max-tokens", str(max_bytes)],
                           dotnet=os.fspath(dotnet_path))
        observations = runtime.get("observations")
        runtime_profiles = {str(item.get("profile")): item for item in observations if isinstance(item, dict)} if isinstance(observations, list) else {}
        if set(runtime_profiles) != set(PROFILES):
            raise WorkspaceError("runtime-index did not return both approved startup profiles")
        current_snapshot, _all_snapshots, _current_extractor, _live = atlas._current_route_snapshot(database, os.fspath(repo))
        current_supplements = atlas._current_compiler_supplements(database, current_snapshot, repo)
        current_observations = atlas._current_runtime_observations(database, current_snapshot, repo, current_supplements)
        selected_observations = [item for item in current_observations
                                 if item.get("binding", {}).get("project_path") == project_rel
                                 and item.get("binding", {}).get("interface_type") == interface_name]
        by_profile = {item.get("binding", {}).get("profile"): item for item in selected_observations}
        if set(by_profile) != set(PROFILES):
            raise WorkspaceError("runtime-index receipts failed immediate source-bound revalidation")
        profiles = _profile_summaries(atlas, by_profile)
    seed_routes, history = _historical_routes_from_database(database, snapshot_id, proposed_inputs["seed_sha256"])
    route_states: list[dict[str, Any]] = []
    candidates = _state_child(state, "candidates", allow_missing=True, label="candidate directory")
    candidates.mkdir(exist_ok=True)
    candidates = _state_child(state, "candidates", allow_missing=False, label="candidate directory")
    runs = _state_child(state, "route-runs", allow_missing=True, label="route-run directory")
    runs.mkdir(exist_ok=True)
    runs = _state_child(state, "route-runs", allow_missing=False, label="route-run directory")
    import route_coordinator as coordinator  # type: ignore
    for route in seed_routes:
        route_id = route["route_fact_id"]
        candidate = _candidate_draft(route, snapshot_id, extractor)
        if Path(route_id).name != route_id or route_id in {".", ".."}:
            raise WorkspaceError("historical route ID is not a safe workspace filename")
        candidate_path = _state_child(state, Path("candidates") / f"{route_id}.json",
                                      allow_missing=True, label="historical candidate draft")
        raw = _json_bytes(candidate)
        if candidate_path.exists():
            if candidate_path.read_bytes() != raw:
                raise WorkspaceError(f"candidate draft for route {route_id} conflicts with saved bytes")
        else:
            candidate_path.write_bytes(raw)
        run_dir = _state_child(state, Path("route-runs") / route_id,
                               allow_missing=True, label="route run directory")
        if not run_dir.exists():
            coordinator.prepare(os.fspath(repo), os.fspath(database), route_id, os.fspath(run_dir), max_bytes)
        try:
            _prepare_historical_candidate(repo, database, route, run_dir, candidate_path, max_bytes)
        except coordinator.CoordinatorError as exc:
            current = _command(["route-find", "--repo", os.fspath(repo), "--db", os.fspath(database),
                                "--route-fact-id", route_id, "--max-tokens", str(max_bytes)])
            if current.get("result") != "fresh":
                raise WorkspaceError(f"cannot prepare origin-bound candidate for historical route {route_id}: {exc}") from exc
        route_states.append(_active_route_run_status(repo, database, route, run_dir))
    manifest = {"schema_version": SCHEMA_VERSION, "inputs": proposed_inputs,
                "database_path": os.fspath(database), "snapshot_id": snapshot_id,
                "extractor_identity": extractor, "compiler_supplement_sha256": supplement_hash,
                "runtime_profiles": profiles, "historical": history, "routes": route_states,
                "producer_identity": producer_identity_at_entry}
    if _producer_identity() != producer_identity_at_entry:
        raise WorkspaceError("workspace producer files changed during prepare; partial artifacts were preserved without publishing a manifest")
    _write_atomic(existing_path, manifest)
    _state_child(state, "workspace-initializing.json", allow_missing=True,
                 label="workspace initialization record").unlink(missing_ok=True)
    return {"result": "prepared", "state_root": os.fspath(state), "database_path": os.fspath(database),
            "snapshot_id": snapshot_id, "extractor_identity": extractor,
            "compiler_supplement_sha256": supplement_hash, "runtime_profiles": profiles,
            "historical": history, "routes": route_states, "pending_route_reviews": sum(1 for item in route_states if item["state"] != "published")}


def status(state_arg: str) -> dict[str, Any]:
    state = _state_root(state_arg)
    manifest, database = _validate_workspace(state)
    repo = Path(manifest["inputs"]["repository_root"])
    historical_routes, _history = _historical_routes_from_database(
        database, manifest["snapshot_id"], manifest["inputs"].get("seed_sha256"),
    )
    route_rows = {item["route_fact_id"]: item for item in manifest["routes"]}
    route_states = [_active_route_run_status(repo, database, item, Path(route_rows[item["route_fact_id"]]["run_dir"]))
                    for item in historical_routes]
    return {"result": "status", "state_root": os.fspath(state), "database_path": os.fspath(database),
            "snapshot_id": manifest["snapshot_id"], "extractor_identity": manifest["extractor_identity"],
            "compiler_supplement_sha256": manifest["compiler_supplement_sha256"],
            "runtime_profiles": manifest["runtime_profiles"], "historical": manifest["historical"],
            "routes": route_states, "pending_route_reviews": sum(1 for item in route_states if item["state"] != "published")}


def correct(state_arg: str, route_fact_id: str, draft_arg: str) -> dict[str, Any]:
    state = _state_root(state_arg)
    manifest, database = _validate_workspace(state)
    repo = Path(manifest["inputs"]["repository_root"])
    historical_routes, _history = _historical_routes_from_database(
        database, manifest["snapshot_id"], manifest["inputs"].get("seed_sha256"),
    )
    matches = [item for item in historical_routes if item["route_fact_id"] == route_fact_id]
    if len(matches) != 1:
        raise WorkspaceError(f"route {route_fact_id!r} is not one of the prepared historical candidates")
    route = matches[0]
    row = next(item for item in manifest["routes"] if item["route_fact_id"] == route_fact_id)
    original_run = _safe_path(row["run_dir"], allow_missing=False, label="R0 route run directory")
    original_packet_path = _safe_path(original_run / "review-packet.json", allow_missing=False,
                                      label="R0 review packet")
    original_review_path = _safe_path(original_run / "sol-review.json", allow_missing=False,
                                      label="R0 independent review")
    validation = _read_json(original_run / "review-validation.json", "R0 review validation")
    import atlas  # type: ignore
    original_packet = _read_json(original_packet_path, "R0 review packet")
    original_review = _read_json(original_review_path, "R0 independent review")
    try:
        atlas._validate_historical_rejected_predecessor(
            original_packet, original_review, os.fspath(database), os.fspath(repo),
        )
    except atlas.AtlasError as exc:
        raise WorkspaceError(f"historical correction R0 packet/review refuses: {exc}") from exc
    expected_validation = {
        "result": "rejected", "packet_sha256": original_packet.get("packet_sha256"),
        "evidence_sha256": original_packet.get("evidence_sha256"),
        "draft_sha256": original_packet.get("draft_sha256"),
        "review": original_review, "writes": 0,
    }
    if validation != expected_validation:
        raise WorkspaceError("saved R0 review-validation artifact does not match the exact reconstructed rejected review")
    draft_path = _safe_path(draft_arg, allow_missing=False, label="R1 correction draft")
    try:
        draft_raw = draft_path.read_bytes()
        draft = json.loads(draft_raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"cannot read R1 correction draft: {exc}") from exc
    if not isinstance(draft, dict):
        raise WorkspaceError("R1 correction draft must be a JSON object")
    # Validate the complete origin-bound correction before creating a candidate,
    # coordinator manifest, or run directory. A refused draft must not consume
    # the write-once R1 slot and prevent a corrected retry.
    try:
        atlas.route_map_prepare(
            os.fspath(database), os.fspath(repo), route_fact_id, os.fspath(draft_path),
            int(manifest["inputs"]["max_bytes"]), False,
            str(row["origin_snapshot_id"]), str(row["origin_overlay_id"]),
            os.fspath(original_packet_path), os.fspath(original_review_path),
        )
    except atlas.AtlasError as exc:
        raise WorkspaceError(f"R1 correction draft failed source-bound preflight: {exc}") from exc
    correction_runs = _state_child(state, "correction-runs", allow_missing=True,
                                   label="historical correction directory")
    correction_runs.mkdir(exist_ok=True)
    _state_child(state, "correction-runs", allow_missing=False, label="historical correction directory")
    correction_root = _state_child(state, Path("correction-runs") / route_fact_id,
                                   allow_missing=True, label="historical correction directory")
    correction_root.mkdir(exist_ok=True)
    correction_root = _state_child(state, Path("correction-runs") / route_fact_id,
                                   allow_missing=False, label="historical correction directory")
    correction_run = _state_child(state, Path("correction-runs") / route_fact_id / "r1",
                                  allow_missing=True, label="R1 correction run directory")
    candidate = _state_child(state, Path("candidates") / f"{route_fact_id}-correction-r1.json",
                             allow_missing=True, label="R1 correction candidate")
    if candidate.exists():
        if candidate.read_bytes() != draft_raw:
            raise WorkspaceError("an R1 correction candidate already exists with different bytes; a second round is not allowed")
    else:
        candidate.write_bytes(draft_raw)
    import route_coordinator as coordinator  # type: ignore
    if not correction_run.exists():
        coordinator.prepare(os.fspath(repo), os.fspath(database), route_fact_id,
                            os.fspath(correction_run), int(manifest["inputs"]["max_bytes"]))
    _prepare_historical_candidate(
        repo, database, route, correction_run, candidate, int(manifest["inputs"]["max_bytes"]),
        original_packet_path, original_review_path,
    )
    active = _route_run_status(repo, database, route, correction_run)
    return {"result": "correction-prepared", "route_fact_id": route_fact_id,
            "prior_run_dir": os.fspath(original_run), "correction_run_dir": os.fspath(correction_run),
            "packet_path": active["packet_path"], "packet_sha256": active["packet_sha256"],
            "state": active["state"]}


def publish(state_arg: str, route_fact_id: str, review_arg: str) -> dict[str, Any]:
    state = _state_root(state_arg)
    manifest, database = _validate_workspace(state)
    repo = Path(manifest["inputs"]["repository_root"])
    historical_routes, _history = _historical_routes_from_database(
        database, manifest["snapshot_id"], manifest["inputs"].get("seed_sha256"),
    )
    matches = [item for item in historical_routes if item.get("route_fact_id") == route_fact_id]
    if len(matches) != 1:
        raise WorkspaceError(f"route {route_fact_id!r} is not one of the prepared historical candidates")
    row = next(item for item in manifest["routes"] if item["route_fact_id"] == route_fact_id)
    route_state = _active_route_run_status(repo, database, matches[0], Path(row["run_dir"]))
    if route_state["state"] not in {"review-ready", "accepted-review", "review-rejected", "published"}:
        raise WorkspaceError(f"route {route_fact_id} has no saved review packet")
    import route_coordinator as coordinator  # type: ignore
    result = coordinator.publish(os.fspath(repo), os.fspath(database), route_fact_id,
                                 route_state["run_dir"], review_arg, int(manifest["inputs"]["max_bytes"]))
    return {"result": result.get("result"), "route_fact_id": route_fact_id,
            "state_root": os.fspath(state), "publication": result,
            "status": status(os.fspath(state))}


def publish_reviews(state_arg: str, review_dir_arg: str) -> dict[str, Any]:
    """Publish one explicit batch of saved route reviews, then rebuild full status once."""
    state = _state_root(state_arg)
    manifest, database = _validate_workspace(state)
    repo = Path(manifest["inputs"]["repository_root"])
    review_dir = _safe_path(review_dir_arg, allow_missing=False, label="review directory")
    if not review_dir.is_dir():
        raise WorkspaceError("review directory must be an existing directory")
    historical_routes, _history = _historical_routes_from_database(
        database, manifest["snapshot_id"], manifest["inputs"].get("seed_sha256"),
    )
    known = {item["route_fact_id"]: item for item in historical_routes}
    entries = sorted(review_dir.iterdir(), key=lambda item: item.name)
    if not entries:
        raise WorkspaceError("review directory must contain at least one known route review JSON file")
    review_files: dict[str, Path] = {}
    for item in entries:
        safe_item = _safe_path(item, allow_missing=False, label="review directory entry")
        if not safe_item.is_file() or safe_item.suffix != ".json":
            raise WorkspaceError("review directory may contain only regular <route_fact_id>.json files")
        route_id = safe_item.name[:-5]
        if route_id not in known or safe_item.name != f"{route_id}.json":
            raise WorkspaceError(f"review directory contains an unknown route review file: {safe_item.name}")
        if route_id in review_files:
            raise WorkspaceError(f"review directory contains duplicate files for route {route_id}")
        review_files[route_id] = safe_item

    rows = {item["route_fact_id"]: item for item in manifest["routes"]}
    import route_coordinator as coordinator  # type: ignore

    outcomes: list[dict[str, Any]] = []
    for route_id, review_path in sorted(review_files.items()):
        route = known[route_id]
        row = rows.get(route_id)
        if row is None:
            raise WorkspaceError(f"route {route_id} is missing from the validated workspace manifest")
        active = _active_route_run_status(repo, database, route, Path(row["run_dir"]))
        run_dir = _safe_path(active["run_dir"], allow_missing=False, label="active route run directory")
        review_path = _safe_path(review_path, allow_missing=False, label="route review JSON")
        if active["state"] == "published":
            saved_review = _safe_path(run_dir / "sol-review.json", allow_missing=False,
                                      label="published route review")
            if saved_review.read_bytes() != review_path.read_bytes():
                raise WorkspaceError(f"route {route_id} is already published with different review bytes")
            outcomes.append({"route_fact_id": route_id, "result": "already-published"})
            continue
        if active["state"] not in {"review-ready", "accepted-review", "review-rejected", "publish-recovery"}:
            raise WorkspaceError(f"route {route_id} is not ready for review publication: {active['state']}")
        try:
            publication = coordinator.publish(
                os.fspath(repo), os.fspath(database), route_id, os.fspath(run_dir),
                os.fspath(review_path), int(manifest["inputs"]["max_bytes"]),
            )
        except coordinator.CoordinatorError as exc:
            outcomes.append({"route_fact_id": route_id, "result": "refused", "reason": str(exc)})
        else:
            outcomes.append({"route_fact_id": route_id, "result": publication.get("result"),
                             "publication": publication})

    final_status = status(os.fspath(state))
    final_rows = {item["route_fact_id"]: item for item in final_status["routes"]}
    for outcome in outcomes:
        current = final_rows.get(outcome["route_fact_id"])
        outcome["state"] = current.get("state") if isinstance(current, dict) else "missing"
    complete = all(item.get("state") == "published" for item in outcomes)
    return {"result": "published" if complete else "partial", "state_root": os.fspath(state),
            "selected_route_count": len(review_files), "routes": outcomes,
            "pending_route_reviews": final_status["pending_route_reviews"],
            "status": final_status}
