#!/usr/bin/env python3
"""Prepare and verify a resumable set of reviewed route evidence for one controller."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if os.fspath(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_DIR))

import atlas  # noqa: E402
import route_coordinator  # noqa: E402


MANIFEST = "area-manifest.json"
ROUTES_DIR = "routes"
DEFAULT_MAX_BYTES = route_coordinator.DEFAULT_MAX_BYTES


class AreaError(Exception):
    """An expected area identity, integrity, or readiness failure."""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _child_name(route_fact_id: str) -> str:
    return hashlib.sha256(route_fact_id.encode("utf-8")).hexdigest()


def _association_identity(association: dict[str, object]) -> dict[str, str]:
    binding = association.get("binding")
    if not isinstance(binding, dict):
        raise AreaError("validated route association has no binding object")
    overlay_id = binding.get("overlay_id")
    binding_hash = association.get("binding_hash")
    review_hash = association.get("association_review_hash")
    if not all(isinstance(value, str) and value for value in (overlay_id, binding_hash, review_hash)):
        raise AreaError("validated route association has incomplete identity hashes")
    return {"overlay_id": overlay_id, "binding_hash": binding_hash,
            "association_review_hash": review_hash}


def _capture(repo_arg: str, db_arg: str, anchor_route_fact_id: str) -> dict[str, object]:
    repo = route_coordinator._canonical_repo(repo_arg)
    db = Path(db_arg).expanduser().resolve(strict=True)
    if not db.is_file():
        raise AreaError(f"database is not a regular file: {db}")
    if not isinstance(anchor_route_fact_id, str) or not anchor_route_fact_id.strip():
        raise AreaError("anchor route fact ID must be nonempty")
    try:
        snapshot, snapshots_by_id, extractor_identity, _live = atlas._current_route_snapshot(db, os.fspath(repo))
        associations = atlas._validated_route_associations(os.fspath(db), db, snapshot, snapshots_by_id)
    except (atlas.AtlasError, sqlite3.Error) as exc:
        raise AreaError(str(exc)) from exc

    graph = snapshot.get("source_graph")
    facts = graph.get("facts") if isinstance(graph, dict) else None
    if not isinstance(facts, list) or any(not isinstance(fact, dict) for fact in facts):
        raise AreaError("saved source graph facts must be a list of objects")
    ids: dict[str, dict[str, object]] = {}
    for fact in facts:
        fact_id = fact.get("id")
        if not isinstance(fact_id, str) or not fact_id:
            raise AreaError("saved source graph contains a fact with an invalid ID")
        if fact_id in ids:
            raise AreaError(f"source graph fact ID is not unique across facts: {fact_id}")
        ids[fact_id] = fact

    anchors = [fact for fact in facts if fact.get("id") == anchor_route_fact_id]
    if len(anchors) != 1 or anchors[0].get("kind") != "route_action":
        raise AreaError(f"anchor ID must identify exactly one saved route_action fact: {anchor_route_fact_id}")
    controller_type_id = anchors[0].get("controller_type_id")
    if not isinstance(controller_type_id, str) or not controller_type_id:
        raise AreaError("anchor route has no saved controller type ID")
    routes = sorted((fact for fact in facts if fact.get("kind") == "route_action"
                     and fact.get("controller_type_id") == controller_type_id), key=lambda item: item["id"])
    if not routes:
        raise AreaError("anchor controller has no saved route_action facts")

    members: list[dict[str, object]] = []
    for route in routes:
        route_id = route["id"]
        linked = associations.get(route_id, [])
        if len(linked) > 1:
            raise AreaError(f"controller route has multiple reviewed associations; resolve before area preparation: {route_id}")
        if linked:
            try:
                found, _rendered, code = atlas.route_find(os.fspath(db), os.fspath(repo), route_id,
                                                          DEFAULT_MAX_BYTES)
            except (atlas.AtlasError, sqlite3.Error) as exc:
                raise AreaError(f"reviewed route is not fresh ({route_id}): {exc}") from exc
            if code != 0 or found.get("result") != "fresh" or found.get("association_count") != 1:
                raise AreaError(f"reviewed route did not return one fresh accepted map: {route_id}")
            selection = found.get("claim_selection")
            if not isinstance(selection, dict) or selection.get("omitted_claims") != 0:
                raise AreaError(f"reviewed route has incomplete claim retrieval: {route_id}")
            members.append({"route_fact_id": route_id, "state": "reviewed",
                            "association": _association_identity(linked[0])})
        else:
            members.append({"route_fact_id": route_id, "state": "open", "association": None})

    return {
        "schema_version": 1,
        "identity": {
            "repository_root": os.fspath(repo), "database_path": os.fspath(db),
            "anchor_route_fact_id": anchor_route_fact_id,
            "controller_type_id": controller_type_id,
            "snapshot_id": snapshot["snapshot_id"], "extractor_identity": extractor_identity,
        },
        "routes": members,
    }


def _read_manifest(area_dir: Path, expected: dict[str, object]) -> dict[str, object]:
    if area_dir.is_symlink() or not area_dir.is_dir():
        raise AreaError("area run path must be a real directory")
    path = area_dir / MANIFEST
    if not path.is_file() or path.is_symlink():
        raise AreaError(f"area run manifest is missing or unsafe: {MANIFEST}")
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AreaError(f"area run manifest is corrupt: {exc}") from exc
    if not isinstance(manifest, dict) or raw != _json_bytes(manifest):
        raise AreaError("area run manifest is malformed or not canonical")
    if (set(manifest) != {"schema_version", "identity", "max_bytes", "routes"}
            or manifest.get("schema_version") != 1 or manifest.get("identity") != expected.get("identity")
            or manifest.get("max_bytes") != expected.get("max_bytes")):
        raise AreaError("area run identity or evidence budget differs from the current saved checkout")
    original_routes = manifest.get("routes")
    current_routes = expected.get("routes")
    if not isinstance(original_routes, list) or not isinstance(current_routes, list):
        raise AreaError("area run route membership is malformed")
    original_by_id = {item.get("route_fact_id"): item for item in original_routes if isinstance(item, dict)}
    current_by_id = {item.get("route_fact_id"): item for item in current_routes if isinstance(item, dict)}
    if (len(original_by_id) != len(original_routes) or len(current_by_id) != len(current_routes)
            or original_by_id.keys() != current_by_id.keys()):
        raise AreaError("area route membership differs from the current saved checkout")
    for route_id, original in original_by_id.items():
        live = current_by_id[route_id]
        if original.get("state") == "reviewed":
            if live != original:
                raise AreaError(f"originally reviewed route association changed or became stale: {route_id}")
        elif original.get("state") == "open":
            if original.get("association") is not None or live.get("state") not in {"open", "reviewed"}:
                raise AreaError(f"open route has an invalid current state: {route_id}")
        else:
            raise AreaError(f"area manifest has an invalid original route state: {route_id}")
    expected_entries = {MANIFEST, ROUTES_DIR}
    observed_entries = {entry.name for entry in area_dir.iterdir()}
    if observed_entries != expected_entries:
        extras = sorted(observed_entries - expected_entries)
        missing = sorted(expected_entries - observed_entries)
        raise AreaError(f"area run directory entries differ from its manifest; extra={extras}, missing={missing}")
    routes_dir = area_dir / ROUTES_DIR
    if routes_dir.is_symlink() or not routes_dir.is_dir():
        raise AreaError("area route child directory is missing or unsafe")
    expected_children = {_child_name(str(item["route_fact_id"])) for item in manifest["routes"]
                         if item["state"] == "open"}
    observed_children = {entry.name for entry in routes_dir.iterdir()}
    if observed_children - expected_children:
        raise AreaError(f"area contains unregistered child directories: {sorted(observed_children - expected_children)}")
    return manifest


def _load_or_create(area_arg: str, current: dict[str, object]) -> tuple[Path, dict[str, object]]:
    area_dir = Path(area_arg).expanduser()
    if area_dir.exists():
        if area_dir.is_symlink() or not area_dir.is_dir():
            raise AreaError("area run path must be a real directory")
    else:
        area_dir.mkdir(parents=True)
    area_dir = area_dir.resolve(strict=True)
    manifest_path = area_dir / MANIFEST
    if manifest_path.exists():
        manifest = _read_manifest(area_dir, current)
    else:
        if any(area_dir.iterdir()):
            raise AreaError(f"partial area run has no {MANIFEST}; refusing to overwrite it")
        (area_dir / ROUTES_DIR).mkdir()
        try:
            fd = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise AreaError("area manifest appeared during initialization") from exc
        with os.fdopen(fd, "wb") as stream:
            stream.write(_json_bytes(current))
            stream.flush()
            os.fsync(stream.fileno())
        manifest = current
    return area_dir, manifest


def _route_child(area_dir: Path, route_id: str) -> Path:
    return area_dir / ROUTES_DIR / _child_name(route_id)


def _check_child(repo: str, db: str, area_dir: Path, route_id: str, current_state: str,
                 *, create: bool, max_bytes: int) -> dict[str, object]:
    child = _route_child(area_dir, route_id)
    if not child.exists():
        if not create:
            raise AreaError(f"open route child is missing: {route_id} ({child})")
        if current_state != "open":
            raise AreaError(f"route acquired an association without its prepared child evidence: {route_id}")
        result = route_coordinator.prepare(repo, db, route_id, os.fspath(child), max_bytes)
        if result.get("result") != "prepared":
            raise AreaError(f"single-route preparation did not finish for {route_id}")
    else:
        if child.is_symlink() or not child.is_dir():
            raise AreaError(f"open route child is unsafe: {route_id} ({child})")
        if not (child / route_coordinator.MANIFEST).is_file():
            missing = route_coordinator.MANIFEST
            raise AreaError(f"partial child for route {route_id} is missing {missing}; refusing to overwrite ({child})")
        try:
            result = route_coordinator.status(repo, db, route_id, os.fspath(child), max_bytes)
        except route_coordinator.CoordinatorError as exc:
            raise AreaError(f"child for route {route_id} is partial, corrupt, or stale: {exc}") from exc
    child_state = result.get("result")
    if child_state not in {"prepared", "review_ready", "accepted_review_ready_to_publish",
                           "published_and_fresh", "review_rejected"}:
        raise AreaError(f"open route child is unusable: {route_id}: {child_state}")
    if child_state == "published_and_fresh":
        if current_state != "reviewed":
            raise AreaError(f"child reports a published map that Atlas does not associate with the route: {route_id}")
        try:
            packet, _ = route_coordinator._read_json(child / "review-packet.json", "saved review packet")
            validation, _ = route_coordinator._read_json(child / "review-validation.json", "saved review validation")
            published, _ = route_coordinator._read_json(child / "publish-result.json", "saved publish result")
            expected_overlay = route_coordinator._expected_overlay(packet)
        except route_coordinator.CoordinatorError as exc:
            raise AreaError(f"published route child is missing accepted publication evidence ({route_id}): {exc}") from exc
        if (validation.get("result") != "accepted" or validation.get("packet_sha256") != packet.get("packet_sha256")
                or published.get("overlay_id") != expected_overlay):
            raise AreaError(f"published route is not bound to this child's accepted review and overlay: {route_id}")
    elif current_state != "open":
        raise AreaError(f"route acquired an external or different association while its child is {child_state}: {route_id}")
    identity = result.get("identity")
    if not isinstance(identity, dict):
        raise AreaError(f"route child has no identity: {route_id}")
    parent_identity = json.loads((area_dir / MANIFEST).read_text(encoding="utf-8"))["identity"]
    if (identity.get("snapshot_id") != parent_identity.get("snapshot_id")
            or identity.get("extractor_identity") != parent_identity.get("extractor_identity")):
        raise AreaError(f"route child snapshot or extractor differs from its area: {route_id}")
    try:
        evidence = json.loads((child / "evidence-pack.json").read_text(encoding="utf-8"))
        route_lookup = json.loads((child / "route-find.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AreaError(f"route child has unreadable prepared evidence: {route_id}: {exc}") from exc
    selection = evidence.get("selection") if isinstance(evidence, dict) else None
    evidence_route = evidence.get("route") if isinstance(evidence, dict) else None
    if (not isinstance(selection, dict) or selection.get("complete") is not True
            or selection.get("omitted_candidate_bundles") != 0
            or not isinstance(evidence_route, dict) or evidence_route.get("fact_id") != route_id
            or evidence.get("snapshot_id") != parent_identity.get("snapshot_id")
            or evidence.get("extractor_identity") != parent_identity.get("extractor_identity")):
        raise AreaError(f"route child evidence is incomplete or identity-mismatched: {route_id}")
    if (not isinstance(route_lookup, dict) or route_lookup.get("result") != "unmapped"
            or route_lookup.get("route_fact_id") != route_id
            or route_lookup.get("association_count") != 0
            or route_lookup.get("snapshot_id") != parent_identity.get("snapshot_id")
            or route_lookup.get("extractor_identity") != parent_identity.get("extractor_identity")):
        raise AreaError(f"route child saved lookup is not an identity-matched open route: {route_id}")
    return result


def prepare(repo_arg: str, db_arg: str, anchor_route_fact_id: str, area_arg: str,
            max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    if max_bytes < 1:
        raise AreaError("--max-bytes must be positive")
    current = {**_capture(repo_arg, db_arg, anchor_route_fact_id), "max_bytes": max_bytes}
    area_dir, manifest = _load_or_create(area_arg, current)
    identity = manifest["identity"]
    live_members = {item["route_fact_id"]: item for item in current["routes"]}
    # Validate every existing child before creating any missing sibling.
    for member in manifest["routes"]:
        if member["state"] == "open" and _route_child(area_dir, member["route_fact_id"]).exists():
            _check_child(identity["repository_root"], identity["database_path"], area_dir,
                         member["route_fact_id"], live_members[member["route_fact_id"]]["state"],
                         create=False, max_bytes=max_bytes)
    for member in manifest["routes"]:
        if member["state"] == "open" and not _route_child(area_dir, member["route_fact_id"]).exists():
            _check_child(identity["repository_root"], identity["database_path"], area_dir,
                         member["route_fact_id"], live_members[member["route_fact_id"]]["state"],
                         create=True, max_bytes=max_bytes)
    status_result = status(repo_arg, db_arg, anchor_route_fact_id, os.fspath(area_dir), max_bytes)
    return {**status_result, "result": "prepared" if status_result["ready"] else "incomplete"}


def status(repo_arg: str, db_arg: str, anchor_route_fact_id: str, area_arg: str,
           max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    if max_bytes < 1:
        raise AreaError("--max-bytes must be positive")
    current = {**_capture(repo_arg, db_arg, anchor_route_fact_id), "max_bytes": max_bytes}
    area_dir = Path(area_arg).expanduser()
    if area_dir.is_symlink():
        raise AreaError("area run path must be a real directory")
    area_dir = area_dir.resolve(strict=True)
    manifest = _read_manifest(area_dir, current)
    identity = manifest["identity"]
    route_statuses: list[dict[str, object]] = []
    ready = True
    captured_members = {item["route_fact_id"]: item for item in current["routes"]}
    reviewed_count = sum(item["state"] == "reviewed" for item in manifest["routes"])
    for member in manifest["routes"]:
        route_id = member["route_fact_id"]
        if member["state"] == "reviewed":
            route_statuses.append({"route_fact_id": route_id, "state": "reviewed", "ready": True,
                                   "overlay_id": member["association"]["overlay_id"]})
        else:
            live_state = captured_members[route_id]["state"]
            child = _route_child(area_dir, route_id)
            if not child.exists():
                if live_state == "reviewed":
                    raise AreaError(f"route acquired an association without its prepared child evidence: {route_id}")
                ready = False
                route_statuses.append({"route_fact_id": route_id, "state": "open", "ready": False,
                                       "reason": "child_not_prepared"})
                continue
            result = _check_child(identity["repository_root"], identity["database_path"], area_dir,
                                  route_id, live_state, create=False, max_bytes=max_bytes)
            published = result["result"] == "published_and_fresh"
            if published:
                reviewed_count += 1
            if result["result"] == "review_rejected":
                ready = False
            route_statuses.append({"route_fact_id": route_id,
                                   "state": "reviewed" if published else "open",
                                   "ready": result["result"] != "review_rejected",
                                   "child_result": result["result"]})
    return {"result": "ready" if ready else "incomplete", "ready": ready,
            "identity": identity, "route_count": len(manifest["routes"]),
            "reviewed_count": reviewed_count,
            "open_count": len(manifest["routes"]) - reviewed_count,
            "routes": route_statuses, "area_dir": os.fspath(area_dir)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "status"):
        sub = commands.add_parser(command)
        sub.add_argument("--repo", required=True)
        sub.add_argument("--db", required=True)
        sub.add_argument("--anchor-route-fact-id", required=True)
        sub.add_argument("--area-dir", required=True)
        sub.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)
    try:
        result = (prepare(args.repo, args.db, args.anchor_route_fact_id, args.area_dir, args.max_bytes)
                  if args.command == "prepare" else
                  status(args.repo, args.db, args.anchor_route_fact_id, args.area_dir, args.max_bytes))
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
        return 0
    except (AreaError, route_coordinator.CoordinatorError, atlas.AtlasError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
