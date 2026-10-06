#!/usr/bin/env python3
"""Capture and query deterministic, source-linked tracked-file inventories."""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys


SCHEMA_VERSION = 2
INVENTORY_BASIS = "git-index-paths+working-tree-bytes"


class AtlasError(Exception):
    """An expected input, repository, or persistence error."""


def _git(repo: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise AtlasError(f"cannot run git: {exc}") from exc
    if result.returncode:
        message = os.fsdecode(result.stderr).strip() or f"git exited {result.returncode}"
        raise AtlasError(message)
    return result.stdout


def _git_optional(repo: Path, *args: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise AtlasError(f"cannot run git: {exc}") from exc
    return result.stdout if result.returncode == 0 else None


def _repo_root(repo_arg: str) -> Path:
    requested = Path(repo_arg).expanduser()
    try:
        root_output = os.fsdecode(_git(requested, "rev-parse", "--show-toplevel")).strip()
        root = Path(root_output).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AtlasError(f"cannot resolve repository {requested}: {exc}") from exc
    return root


def _read_working_file(root_fd: int, relative: str, collect_source: bool = False) -> dict[str, object]:
    """Inspect a tracked path without following any symlink component."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise AtlasError(f"safe no-follow path traversal is unavailable for {relative!r}")
    parts = os.fsencode(relative).split(os.fsencode(os.sep))
    if not parts or any(part in (b"", b".", b"..") for part in parts):
        raise AtlasError(f"invalid repository-relative tracked path: {relative!r}")

    parent_fd = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            try:
                child_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    return {"presence": "missing", "type": "missing", "size_bytes": None, "sha256": None}
                raise AtlasError(
                    f"unsafe tracked path {relative!r}: cannot open parent component "
                    f"{os.fsdecode(component)!r}: {exc.strerror}"
                ) from exc
            os.close(parent_fd)
            parent_fd = child_fd

        leaf = parts[-1]
        try:
            info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return {"presence": "missing", "type": "missing", "size_bytes": None, "sha256": None}
        except OSError as exc:
            raise AtlasError(f"cannot inspect tracked path {relative!r}: {exc.strerror}") from exc

        if stat.S_ISLNK(info.st_mode):
            try:
                content = os.fsencode(os.readlink(leaf, dir_fd=parent_fd))
            except OSError as exc:
                raise AtlasError(f"cannot read symlink evidence for {relative!r}: {exc.strerror}") from exc
            return {
                "presence": "present", "type": "symlink", "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        if stat.S_ISDIR(info.st_mode):
            return {"presence": "present", "type": "directory", "size_bytes": 0, "sha256": None}
        if not stat.S_ISREG(info.st_mode):
            return {"presence": "present", "type": "other", "size_bytes": 0, "sha256": None}

        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except OSError as exc:
            raise AtlasError(f"cannot safely open tracked file {relative!r}: {exc.strerror}") from exc
        digest = hashlib.sha256()
        size = 0
        content = bytearray() if collect_source else None
        try:
            with os.fdopen(fd, "rb", closefd=True) as stream:
                fd_info = os.fstat(stream.fileno())
                if not stat.S_ISREG(fd_info.st_mode):
                    raise AtlasError(f"tracked path changed type while reading: {relative!r}")
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    digest.update(chunk)
                    if content is not None:
                        content.extend(chunk)
        except OSError as exc:
            raise AtlasError(f"cannot read tracked file {relative!r}: {exc.strerror}") from exc
        evidence: dict[str, object] = {
            "presence": "present", "type": "file", "size_bytes": size, "sha256": digest.hexdigest()
        }
        if content is not None:
            evidence["_source_bytes"] = bytes(content)
        return evidence
    finally:
        os.close(parent_fd)


def _tracked_entries(root: Path, collect_source_bytes: bool = True) -> tuple[list[dict[str, object]], dict[str, bytes]]:
    raw = _git(root, "ls-files", "--stage", "-z")
    entries: list[dict[str, object]] = []
    sources: dict[str, bytes] = {}
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for record in raw.split(b"\0"):
            if not record:
                continue
            try:
                metadata, raw_path = record.split(b"\t", 1)
                mode_b, _blob, stage_b = metadata.split(b" ", 2)
                relative = os.fsdecode(raw_path)
                mode = mode_b.decode("ascii")
                stage = int(stage_b)
            except (ValueError, UnicodeDecodeError) as exc:
                raise AtlasError("git returned an invalid staged-path record") from exc
            if stage != 0:
                raise AtlasError(f"tracked path has unresolved merge stages: {relative!r}")
            evidence = _read_working_file(root_fd, relative, collect_source=collect_source_bytes and relative.lower().endswith(".cs"))
            source_bytes = evidence.pop("_source_bytes", None)
            if source_bytes is not None:
                sources[relative] = source_bytes
            entries.append({"path": relative, "git_mode": mode, **evidence})
    finally:
        os.close(root_fd)
    entries.sort(key=lambda entry: os.fsencode(str(entry["path"])))
    return entries, sources


def _status(root: Path) -> list[dict[str, str]]:
    records = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    result: list[dict[str, str]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise AtlasError("git returned an invalid porcelain status record")
        item = {"index_status": chr(record[0]), "worktree_status": chr(record[1]), "path": os.fsdecode(record[3:])}
        if b"R" in record[:2] or b"C" in record[:2]:
            if index >= len(records):
                raise AtlasError("git returned an incomplete rename status record")
            item["original_path"] = os.fsdecode(records[index])
            index += 1
        result.append(item)
    result.sort(key=lambda item: (os.fsencode(item["path"]), item["index_status"], item["worktree_status"]))
    return result


def capture(repo_arg: str) -> dict[str, object]:
    root = _repo_root(repo_arg)
    head_bytes = _git_optional(root, "rev-parse", "--verify", "HEAD")
    head = os.fsdecode(head_bytes).strip() if head_bytes is not None else None
    head_ref = None
    if head is None:
        ref_bytes = _git_optional(root, "symbolic-ref", "-q", "HEAD")
        if ref_bytes is None:
            raise AtlasError("repository has no commit and no symbolic HEAD ref")
        head_ref = os.fsdecode(ref_bytes).strip()
    files, source_bytes = _tracked_entries(root)
    status = _status(root)
    from csharp_facts import build_graph
    inventory_by_path = {str(entry["path"]): entry for entry in files}
    try:
        source_graph = build_graph(source_bytes, inventory_by_path)
    except ValueError as exc:
        raise AtlasError(str(exc)) from exc
    identity = {
        "schema_version": SCHEMA_VERSION,
        "repository_root": os.fspath(root),
        "head": head,
        "head_ref": head_ref,
        "inventory_basis": INVENTORY_BASIS,
        "tracked_count": len(files),
        "status": status,
        "files": files,
        "source_graph": source_graph,
    }
    canonical = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    fingerprint = hashlib.sha256(canonical).hexdigest()
    captured_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        **identity,
        "snapshot_id": f"atlas-v{SCHEMA_VERSION}-{fingerprint}",
        "evidence_fingerprint": fingerprint,
        "captured_at": captured_at,
    }


def _connect_for_index(db_path: Path) -> sqlite3.Connection:
    if not db_path.parent.exists():
        raise AtlasError(f"database parent directory does not exist: {db_path.parent}")
    try:
        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except sqlite3.Error as exc:
        raise AtlasError(f"cannot open database {db_path}: {exc}") from exc


def save(db_arg: str, snapshot: dict[str, object]) -> dict[str, object]:
    db_path = Path(db_arg).expanduser().absolute()
    payload = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    connection = _connect_for_index(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS atlas_snapshots ("
            "snapshot_id TEXT PRIMARY KEY, evidence_fingerprint TEXT NOT NULL UNIQUE, "
            "captured_at TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        existing = connection.execute(
            "SELECT evidence_fingerprint, payload_json FROM atlas_snapshots WHERE snapshot_id = ?",
            (snapshot["snapshot_id"],),
        ).fetchone()
        if existing:
            if existing[0] != snapshot["evidence_fingerprint"]:
                raise AtlasError("snapshot id collision: refusing to replace existing evidence")
            connection.commit()
            return json.loads(existing[1])
        try:
            connection.execute(
                "INSERT INTO atlas_snapshots(snapshot_id, evidence_fingerprint, captured_at, payload_json) "
                "VALUES (?, ?, ?, ?)",
                (snapshot["snapshot_id"], snapshot["evidence_fingerprint"], snapshot["captured_at"], payload),
            )
        except sqlite3.IntegrityError as exc:
            raise AtlasError(f"snapshot persistence conflict; existing snapshots were preserved: {exc}") from exc
        connection.commit()
        return snapshot
    except (sqlite3.Error, AtlasError):
        connection.rollback()
        raise
    finally:
        connection.close()


def query(db_arg: str, snapshot_id: str, path_filter: str | None, include_graph: bool = False) -> dict[str, object]:
    db_path = Path(db_arg).expanduser()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    try:
        uri = db_path.absolute().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
    except sqlite3.Error as exc:
        raise AtlasError(f"cannot query database {db_path}: {exc}") from exc
    if row is None:
        raise AtlasError(f"snapshot not found: {snapshot_id}")
    snapshot = json.loads(row[0])
    files = snapshot["files"]
    if path_filter is not None:
        files = [entry for entry in files if entry["path"] == path_filter]
    result = {
        "schema_version": snapshot["schema_version"],
        "snapshot_id": snapshot["snapshot_id"],
        "evidence_fingerprint": snapshot["evidence_fingerprint"],
        "captured_at": snapshot["captured_at"],
        "repository_root": snapshot["repository_root"],
        "head": snapshot["head"],
        "head_ref": snapshot.get("head_ref"),
        "inventory_basis": snapshot["inventory_basis"],
        "tracked_count": snapshot["tracked_count"],
        "status": snapshot["status"],
        "matched_count": len(files),
        "files": files,
    }
    if include_graph:
        if "source_graph" not in snapshot:
            raise AtlasError("snapshot predates source graph capture")
        result["source_graph"] = snapshot["source_graph"]
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _validate_snapshot_fingerprint(snapshot: dict[str, object], expected_id: str) -> None:
    identity_fields = ("schema_version", "repository_root", "head", "head_ref", "inventory_basis",
                       "tracked_count", "status", "files", "source_graph")
    if snapshot.get("snapshot_id") != expected_id or any(field not in snapshot for field in identity_fields):
        raise AtlasError(f"saved snapshot identity is incomplete or mismatched: {expected_id}")
    identity = {field: snapshot[field] for field in identity_fields}
    fingerprint = hashlib.sha256(_canonical_json(identity)).hexdigest()
    if snapshot.get("evidence_fingerprint") != fingerprint or expected_id != f"atlas-v{SCHEMA_VERSION}-{fingerprint}":
        raise AtlasError(f"saved snapshot evidence fingerprint is invalid: {expected_id}")


def _validate_reviewed_flow(snapshot: dict[str, object], flow: dict[str, object]) -> None:
    graph = snapshot.get("source_graph")
    if not isinstance(graph, dict):
        raise AtlasError("snapshot has no source graph")
    if flow.get("overlay_schema_version") != 1:
        raise AtlasError("unsupported reviewed-flow overlay schema version")
    if flow.get("snapshot_id") != snapshot.get("snapshot_id"):
        raise AtlasError("reviewed-flow snapshot_id does not match the selected snapshot")
    if flow.get("extractor_identity") != graph.get("extractor_identity"):
        raise AtlasError("reviewed-flow extractor_identity does not match the selected snapshot")
    if not isinstance(flow.get("title"), str) or not flow["title"].strip():
        raise AtlasError("reviewed-flow title must be a non-empty string")
    conclusions = flow.get("reviewed_conclusions")
    if not isinstance(conclusions, list) or not conclusions:
        raise AtlasError("reviewed-flow must contain at least one reviewed conclusion")
    facts = {fact["id"]: fact for fact in graph.get("facts", [])}
    for conclusion in conclusions:
        if not isinstance(conclusion, dict) or not isinstance(conclusion.get("claim"), str) or not conclusion["claim"].strip():
            raise AtlasError("each reviewed conclusion must have a non-empty claim")
        evidence = conclusion.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise AtlasError("each reviewed conclusion must cite at least one source fact")
        for citation in evidence:
            if not isinstance(citation, dict) or not isinstance(citation.get("fact_id"), str):
                raise AtlasError("reviewed-flow citation is missing a fact_id")
            fact = facts.get(citation["fact_id"])
            if fact is None:
                raise AtlasError(f"reviewed-flow cites unknown fact: {citation['fact_id']}")
            if citation.get("source") != fact.get("source"):
                raise AtlasError(f"reviewed-flow source path/hash/span does not match fact {citation['fact_id']}")


def attach_flow(db_arg: str, snapshot_id: str, input_path: str) -> dict[str, object]:
    db_path = Path(db_arg).expanduser().absolute()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    try:
        flow = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot read reviewed-flow JSON {input_path}: {exc}") from exc
    if not isinstance(flow, dict):
        raise AtlasError("reviewed-flow JSON must contain an object")
    if "content_hash" in flow:
        raise AtlasError("reviewed-flow input must not supply content_hash; it is computed canonically")
    if flow.get("snapshot_id") != snapshot_id:
        raise AtlasError("reviewed-flow snapshot_id does not match --snapshot")
    connection = _connect_for_index(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise AtlasError(f"snapshot not found: {snapshot_id}")
        snapshot = json.loads(row[0])
        _validate_reviewed_flow(snapshot, flow)
        content_hash = hashlib.sha256(_canonical_json(flow)).hexdigest()
        payload = {**flow, "content_hash": content_hash}
        payload_json = _canonical_json(payload).decode("ascii")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS atlas_reviewed_flows ("
            "snapshot_id TEXT NOT NULL, content_hash TEXT NOT NULL, payload_json TEXT NOT NULL, "
            "PRIMARY KEY(snapshot_id, content_hash), "
            "FOREIGN KEY(snapshot_id) REFERENCES atlas_snapshots(snapshot_id))"
        )
        previous = connection.execute(
            "SELECT payload_json FROM atlas_reviewed_flows WHERE snapshot_id = ? AND content_hash = ?",
            (snapshot_id, content_hash),
        ).fetchone()
        if previous is not None and previous[0] != payload_json:
            raise AtlasError("reviewed-flow content hash collision; refusing to replace existing overlay")
        if previous is None:
            connection.execute(
                "INSERT INTO atlas_reviewed_flows(snapshot_id, content_hash, payload_json) VALUES (?, ?, ?)",
                (snapshot_id, content_hash, payload_json),
            )
        connection.commit()
        return {"snapshot_id": snapshot_id, "overlay_id": content_hash, "content_hash": content_hash, "overlay": payload}
    except (sqlite3.Error, AtlasError):
        connection.rollback()
        raise
    finally:
        connection.close()


def query_flow(db_arg: str, snapshot_id: str, overlay_id: str) -> dict[str, object]:
    db_path = Path(db_arg).expanduser()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    try:
        uri = db_path.absolute().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            row = connection.execute(
                "SELECT f.payload_json, s.payload_json FROM atlas_reviewed_flows f "
                "JOIN atlas_snapshots s ON s.snapshot_id = f.snapshot_id "
                "WHERE f.snapshot_id = ? AND f.content_hash = ?", (snapshot_id, overlay_id)
            ).fetchone()
            has_receipt_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'atlas_flow_reviews'"
            ).fetchone() is not None
            receipt_row = connection.execute(
                "SELECT receipt_json FROM atlas_flow_reviews WHERE snapshot_id = ? AND overlay_id = ?",
                (snapshot_id, overlay_id),
            ).fetchone() if has_receipt_table else None
    except sqlite3.Error as exc:
        raise AtlasError(f"cannot query reviewed-flow overlay: {exc}") from exc
    if row is None:
        carried = _resolve_route_carry(db_path, snapshot_id, overlay_id)
        if carried is None:
            raise AtlasError(f"reviewed-flow overlay not found: {overlay_id}")
        row, carry, receipt_row = carried
    else:
        carry = None
    payload, snapshot = json.loads(row[0]), json.loads(row[1])
    flow = {key: value for key, value in payload.items() if key != "content_hash"}
    if hashlib.sha256(_canonical_json(flow)).hexdigest() != payload.get("content_hash"):
        raise AtlasError("saved reviewed-flow content hash is invalid")
    _validate_reviewed_flow(snapshot, flow)
    review_status = "unreviewed"
    receipt_payload = None
    if receipt_row is not None:
        receipt_payload = json.loads(receipt_row[0])
        receipt = {key: value for key, value in receipt_payload.items() if key != "receipt_hash"}
        if hashlib.sha256(_canonical_json(receipt)).hexdigest() != receipt_payload.get("receipt_hash"):
            raise AtlasError("saved review receipt content hash is invalid")
        receipt_snapshot_id = carry["origin_snapshot_id"] if carry is not None else snapshot_id
        receipt_overlay_id = carry["origin_overlay_id"] if carry is not None else overlay_id
        _validate_review_receipt(receipt, receipt_snapshot_id, receipt_overlay_id, payload["content_hash"], flow["extractor_identity"])
        review_status = receipt["decision"]
    result = {
        "snapshot_id": snapshot_id,
        "overlay_id": overlay_id,
        "content_hash": payload["content_hash"],
        "validation": "content integrity and source references verified; semantic review is represented by a matching receipt and is not mechanically validated by Atlas",
        "review_status": review_status,
        "overlay": payload,
        "review_receipt": receipt_payload,
    }
    if carry is not None:
        result["carry_provenance"] = carry
    return result


def _resolve_route_carry(db_path: Path, target_snapshot_id: str, overlay_id: str) -> tuple[tuple[str, str], dict[str, object], tuple[str] | None] | None:
    """Resolve and fully validate one carried overlay through its immutable origin records."""
    uri = db_path.absolute().as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='atlas_route_carries'"
            ).fetchone()
            if exists is None:
                return None
            rows = connection.execute(
                "SELECT target_snapshot_id, route_fact_id, overlay_id, origin_snapshot_id, origin_overlay_id, "
                "origin_receipt_hash, binding_hash, association_review_hash, packet_sha256 "
                "FROM atlas_route_carries WHERE target_snapshot_id=? AND overlay_id=?",
                (target_snapshot_id, overlay_id),
            ).fetchall()
            if not rows:
                return None
            if len(rows) != 1:
                raise AtlasError("carried overlay is ambiguous for this target snapshot")
            values = rows[0]
            if values[2] != values[4]:
                raise AtlasError("carried overlay registry identity differs from its accepted origin")
            target_row = connection.execute(
                "SELECT payload_json FROM atlas_snapshots WHERE snapshot_id=?", (target_snapshot_id,)
            ).fetchone()
            origin_row = connection.execute(
                "SELECT payload_json FROM atlas_snapshots WHERE snapshot_id=?", (values[3],)
            ).fetchone()
            binding_row = connection.execute(
                "SELECT binding_hash, association_review_hash, payload_json FROM atlas_route_bindings "
                "WHERE snapshot_id=? AND route_fact_id=? AND overlay_id=?", (values[3], values[1], values[4])
            ).fetchone()
    except sqlite3.Error as exc:
        raise AtlasError(f"cannot resolve carried reviewed flow: {exc}") from exc
    if target_row is None or origin_row is None or binding_row is None:
        raise AtlasError("carried route references a missing target, origin, or route association")
    try:
        target, origin = json.loads(target_row[0]), json.loads(origin_row[0])
        binding_document = json.loads(binding_row[2])
    except (json.JSONDecodeError, TypeError) as exc:
        raise AtlasError("carried route origin records are corrupt") from exc
    if not isinstance(target, dict) or not isinstance(origin, dict) or not isinstance(binding_document, dict):
        raise AtlasError("carried route origin records must be objects")
    if target.get("snapshot_id") != target_snapshot_id or origin.get("snapshot_id") != values[3]:
        raise AtlasError("carried route snapshot registry identity is invalid")
    _validate_snapshot_fingerprint(target, target_snapshot_id)
    _validate_snapshot_fingerprint(origin, str(values[3]))
    if values[3] == target_snapshot_id:
        raise AtlasError("carried route cannot point to itself")
    from csharp_facts import EXTRACTION_METHOD
    current_extractor = f"{EXTRACTION_METHOD}:python-stdlib-lexer"
    for label, saved in (("target", target), ("origin", origin)):
        graph = saved.get("source_graph")
        if (saved.get("schema_version") != SCHEMA_VERSION or saved.get("inventory_basis") != INVENTORY_BASIS
                or not isinstance(graph, dict) or graph.get("extractor_identity") != current_extractor):
            raise AtlasError(f"carried route {label} snapshot uses an obsolete schema or extractor")
    association_review_payload = binding_document.get("association_review")
    if not isinstance(association_review_payload, dict):
        raise AtlasError("carried route association review payload is corrupt")
    if (binding_row[0] != values[6] or binding_row[1] != values[7]
            or binding_document.get("binding_hash") != values[6]
            or association_review_payload.get("association_review_hash") != values[7]):
        raise AtlasError("carried route association provenance hash changed")
    original_flow = query_flow(os.fspath(db_path), str(values[3]), str(values[4]))
    if (original_flow.get("review_status") != "accepted"
            or original_flow.get("review_receipt", {}).get("receipt_hash") != values[5]):
        raise AtlasError("carried route origin review receipt is missing or changed")
    binding = binding_document.get("binding")
    review_payload = binding_document.get("association_review")
    if not isinstance(binding, dict) or not isinstance(review_payload, dict):
        raise AtlasError("carried route association payload is corrupt")
    review = {key: value for key, value in review_payload.items() if key != "association_review_hash"}
    _validate_route_binding(binding, origin, str(values[1]))
    _validate_route_association_review(review, binding, str(values[6]))
    if (binding.get("snapshot_id") != values[3] or binding.get("overlay_id") != values[4]
            or binding.get("flow_review_receipt_hash") != values[5]
            or hashlib.sha256(_canonical_json(binding)).hexdigest() != values[6]
            or hashlib.sha256(_canonical_json(review)).hexdigest() != values[7]):
        raise AtlasError("carried route association does not match its recorded origin hashes")
    target_graph, origin_graph = target.get("source_graph"), origin.get("source_graph")
    if not isinstance(target_graph, dict) or not isinstance(origin_graph, dict):
        raise AtlasError("carried route target or origin has no source graph")
    target_facts, origin_facts = target_graph.get("facts"), origin_graph.get("facts")
    if (not isinstance(target_facts, list) or any(not isinstance(fact, dict) for fact in target_facts)
            or not isinstance(origin_facts, list) or any(not isinstance(fact, dict) for fact in origin_facts)):
        raise AtlasError("carried route source graph facts are corrupt")
    target_routes = [fact for fact in target_facts if fact.get("id") == values[1]]
    origin_routes = [fact for fact in origin_facts if fact.get("id") == values[1]]
    if len(target_routes) != 1 or len(origin_routes) != 1 or target_routes[0] != origin_routes[0]:
        raise AtlasError("carried route fact is missing, ambiguous, or changed")
    target_root = Path(str(target.get("repository_root", "")))
    if origin.get("repository_root") != target.get("repository_root"):
        raise AtlasError("carried route repository root changed")
    old_packet, _, _ = evidence_pack(os.fspath(db_path), os.fspath(target_root), str(values[1]), 2**31 - 1,
                                      snapshot_override=origin)
    new_packet, _, _ = evidence_pack(os.fspath(db_path), os.fspath(target_root), str(values[1]), 2**31 - 1,
                                      snapshot_override=target)
    if not old_packet["selection"]["complete"] or old_packet["selection"]["omitted_candidate_bundles"] != 0:
        raise AtlasError("carried route origin evidence packet is incomplete")
    if not new_packet["selection"]["complete"] or new_packet["selection"]["omitted_candidate_bundles"] != 0:
        raise AtlasError("carried route target evidence packet is incomplete")
    old_content = {key: value for key, value in old_packet.items() if key not in {"snapshot_id", "budget"}}
    new_content = {key: value for key, value in new_packet.items() if key not in {"snapshot_id", "budget"}}
    packet_sha256 = hashlib.sha256(_canonical_json(old_content)).hexdigest()
    if old_content != new_content or packet_sha256 != values[8]:
        raise AtlasError("carried route evidence packet changed or no longer matches its recorded digest")
    old_flow = original_flow["overlay"]
    citation_facts = {citation["fact_id"] for claim in old_flow["reviewed_conclusions"] for citation in claim["evidence"]}
    for fact_id in citation_facts:
        old_matches = [fact for fact in origin_facts if fact.get("id") == fact_id]
        new_matches = [fact for fact in target_facts if fact.get("id") == fact_id]
        if (len(old_matches) != 1 or len(new_matches) != 1 or old_matches[0] != new_matches[0]
                or not isinstance(old_matches[0].get("source"), dict)):
            raise AtlasError(f"carried route citation fact is missing, ambiguous, or changed: {fact_id}")
    packet_fact_ids = {item["fact_id"] for field in ("source_snippets", "candidate_snippets")
                       for item in old_packet.get(field, [])}
    if not citation_facts.issubset(packet_fact_ids):
        raise AtlasError("carried route citations do not all occur in the complete evidence packet")
    with sqlite3.connect(uri, uri=True) as connection:
        origin_flow_rows = connection.execute(
            "SELECT f.payload_json, s.payload_json, r.receipt_json, r.receipt_hash FROM atlas_reviewed_flows f "
            "JOIN atlas_snapshots s ON s.snapshot_id=f.snapshot_id "
            "LEFT JOIN atlas_flow_reviews r ON r.snapshot_id=f.snapshot_id AND r.overlay_id=f.content_hash "
            "WHERE f.snapshot_id=? AND f.content_hash=?", (values[3], values[4])
        ).fetchall()
    if len(origin_flow_rows) != 1 or origin_flow_rows[0][2] is None:
        raise AtlasError("carried route origin overlay is missing or ambiguous")
    if origin_flow_rows[0][3] != values[5]:
        raise AtlasError("carried route origin review receipt registry hash changed")
    carry = {
        "target_snapshot_id": target_snapshot_id, "route_fact_id": values[1],
        "origin_snapshot_id": values[3], "origin_overlay_id": values[4],
        "origin_review_receipt_hash": values[5], "origin_binding_hash": values[6],
        "origin_association_review_hash": values[7], "packet_sha256": values[8],
    }
    return (origin_flow_rows[0][0], origin_flow_rows[0][1]), carry, (origin_flow_rows[0][2],)


def _validate_review_receipt(receipt: dict[str, object], snapshot_id: str, overlay_id: str, content_hash: str, extractor_identity: str) -> None:
    if receipt.get("receipt_schema_version") != 1:
        raise AtlasError("unsupported review receipt schema version")
    if receipt.get("snapshot_id") != snapshot_id:
        raise AtlasError("review receipt snapshot_id does not match the selected snapshot")
    if receipt.get("overlay_id") != overlay_id or receipt.get("overlay_content_hash") != content_hash:
        raise AtlasError("review receipt does not match the exact overlay content hash")
    if receipt.get("extractor_identity") != extractor_identity:
        raise AtlasError("review receipt extractor_identity does not match the overlay")
    if receipt.get("decision") not in {"accepted", "rejected"}:
        raise AtlasError("review receipt decision must be accepted or rejected")
    if not isinstance(receipt.get("reviewer_identity"), str) or not receipt["reviewer_identity"].strip():
        raise AtlasError("review receipt reviewer_identity must be non-empty")
    if not isinstance(receipt.get("reviewer_model"), str) or not receipt["reviewer_model"].strip():
        raise AtlasError("review receipt reviewer_model must be non-empty")
    basis = receipt.get("review_basis")
    if not isinstance(basis, str) or not basis.strip() or len(basis) > 2000:
        raise AtlasError("review receipt review_basis must contain 1 to 2000 characters")
    timestamp = receipt.get("reviewed_at")
    if not isinstance(timestamp, str):
        raise AtlasError("review receipt reviewed_at must be an ISO timestamp with timezone")
    try:
        parsed = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AtlasError("review receipt reviewed_at must be an ISO timestamp with timezone") from exc
    if parsed.tzinfo is None:
        raise AtlasError("review receipt reviewed_at must include a timezone")


def attach_review(db_arg: str, snapshot_id: str, overlay_id: str, input_path: str) -> dict[str, object]:
    db_path = Path(db_arg).expanduser().absolute()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    try:
        receipt = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot read review receipt JSON {input_path}: {exc}") from exc
    if not isinstance(receipt, dict):
        raise AtlasError("review receipt JSON must contain an object")
    if "receipt_hash" in receipt:
        raise AtlasError("review receipt input must not supply receipt_hash; it is computed canonically")
    connection = _connect_for_index(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT f.payload_json, s.payload_json FROM atlas_reviewed_flows f "
            "JOIN atlas_snapshots s ON s.snapshot_id = f.snapshot_id "
            "WHERE f.snapshot_id = ? AND f.content_hash = ?", (snapshot_id, overlay_id)
        ).fetchone()
        if row is None:
            raise AtlasError(f"reviewed-flow overlay not found: {overlay_id}")
        flow_payload, snapshot = json.loads(row[0]), json.loads(row[1])
        flow = {key: value for key, value in flow_payload.items() if key != "content_hash"}
        content_hash = hashlib.sha256(_canonical_json(flow)).hexdigest()
        if content_hash != flow_payload.get("content_hash") or content_hash != overlay_id:
            raise AtlasError("reviewed-flow overlay content hash is invalid")
        _validate_reviewed_flow(snapshot, flow)
        _validate_review_receipt(receipt, snapshot_id, overlay_id, content_hash, flow["extractor_identity"])
        receipt_hash = hashlib.sha256(_canonical_json(receipt)).hexdigest()
        payload = {**receipt, "receipt_hash": receipt_hash}
        payload_json = _canonical_json(payload).decode("ascii")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS atlas_flow_reviews ("
            "snapshot_id TEXT NOT NULL, overlay_id TEXT NOT NULL, receipt_hash TEXT NOT NULL, receipt_json TEXT NOT NULL, "
            "PRIMARY KEY(snapshot_id, overlay_id), "
            "FOREIGN KEY(snapshot_id, overlay_id) REFERENCES atlas_reviewed_flows(snapshot_id, content_hash))"
        )
        previous = connection.execute(
            "SELECT receipt_hash, receipt_json FROM atlas_flow_reviews WHERE snapshot_id = ? AND overlay_id = ?",
            (snapshot_id, overlay_id),
        ).fetchone()
        if previous is not None and (previous[0] != receipt_hash or previous[1] != payload_json):
            raise AtlasError("review receipt is immutable; a different decision already exists for this overlay")
        if previous is None:
            connection.execute(
                "INSERT INTO atlas_flow_reviews(snapshot_id, overlay_id, receipt_hash, receipt_json) VALUES (?, ?, ?, ?)",
                (snapshot_id, overlay_id, receipt_hash, payload_json),
            )
        connection.commit()
        return {"snapshot_id": snapshot_id, "overlay_id": overlay_id, "receipt_hash": receipt_hash, "receipt": payload}
    except (sqlite3.Error, AtlasError):
        connection.rollback()
        raise
    finally:
        connection.close()


def _validate_route_binding(binding: dict[str, object], snapshot: dict[str, object], route_fact_id: str) -> None:
    graph = snapshot.get("source_graph")
    if not isinstance(graph, dict):
        raise AtlasError("route binding snapshot has no source graph")
    if binding.get("snapshot_id") != snapshot.get("snapshot_id"):
        raise AtlasError("route binding snapshot_id does not match the selected snapshot")
    if binding.get("binding_schema_version") != 1:
        raise AtlasError("unsupported route binding schema version")
    if binding.get("extractor_identity") != graph.get("extractor_identity"):
        raise AtlasError("route binding extractor_identity does not match the selected snapshot")
    if binding.get("route_fact_id") != route_fact_id:
        raise AtlasError("route binding route_fact_id does not match the registry key")
    if "binding_hash" in binding or "association_review_hash" in binding:
        raise AtlasError("computed hashes must not be supplied inside route binding")
    route_facts = [fact for fact in graph.get("facts", [])
                   if fact.get("id") == route_fact_id and fact.get("kind") == "route_action"]
    if len(route_facts) != 1:
        raise AtlasError(f"route binding requires one route_action fact: {route_fact_id}")


def _validate_route_association_review(
    review: dict[str, object], binding: dict[str, object], binding_hash: str,
) -> None:
    if review.get("review_schema_version") != 1:
        raise AtlasError("unsupported route association review schema version")
    if review.get("binding_hash") != binding_hash:
        raise AtlasError("route association review does not match the exact binding hash")
    for field in ("snapshot_id", "extractor_identity", "route_fact_id", "overlay_id", "flow_review_receipt_hash"):
        if review.get(field) != binding.get(field):
            raise AtlasError(f"route association review {field} does not match the binding")
    if review.get("decision") != "accepted":
        raise AtlasError("route association review decision must be accepted")
    for field in ("reviewer_identity", "reviewer_model"):
        value = review.get(field)
        if not isinstance(value, str) or not value.strip():
            raise AtlasError(f"route association review {field} must be non-empty")
    basis = review.get("review_basis")
    if not isinstance(basis, str) or not basis.strip() or len(basis) > 2000:
        raise AtlasError("route association review review_basis must contain 1 to 2000 characters")
    timestamp = review.get("reviewed_at")
    if not isinstance(timestamp, str):
        raise AtlasError("route association review reviewed_at must be an ISO timestamp with timezone")
    try:
        parsed = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AtlasError("route association review reviewed_at must be an ISO timestamp with timezone") from exc
    if parsed.tzinfo is None:
        raise AtlasError("route association review reviewed_at must include a timezone")
    if "association_review_hash" in review:
        raise AtlasError("association_review_hash is computed by Atlas and must not be supplied")


def attach_route_binding(db_arg: str, expected_snapshot_id: str, input_path: str) -> dict[str, object]:
    db_path = Path(db_arg).expanduser().absolute()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    try:
        document = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot read route binding JSON {input_path}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("binding"), dict) or not isinstance(document.get("association_review"), dict):
        raise AtlasError("route binding JSON must contain binding and association_review objects")
    binding = document["binding"]
    review = document["association_review"]
    if binding.get("snapshot_id") != expected_snapshot_id:
        raise AtlasError("route binding snapshot_id does not match --snapshot")
    if "binding_hash" in document or "association_review_hash" in document:
        raise AtlasError("computed hashes must not be supplied in route binding input")
    required = ("snapshot_id", "extractor_identity", "route_fact_id", "overlay_id", "flow_review_receipt_hash")
    if any(not isinstance(binding.get(field), str) or not binding[field].strip() for field in required):
        raise AtlasError("route binding requires non-empty snapshot_id, extractor_identity, route_fact_id, overlay_id, and flow_review_receipt_hash")

    connection = _connect_for_index(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        snapshot_row = connection.execute(
            "SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (binding["snapshot_id"],)
        ).fetchone()
        if snapshot_row is None:
            raise AtlasError(f"snapshot not found: {binding['snapshot_id']}")
        snapshot = json.loads(snapshot_row[0])
        graph = snapshot.get("source_graph") if isinstance(snapshot, dict) else None
        from csharp_facts import EXTRACTION_METHOD
        current_extractor = f"{EXTRACTION_METHOD}:python-stdlib-lexer"
        if (snapshot.get("schema_version") != SCHEMA_VERSION or snapshot.get("inventory_basis") != INVENTORY_BASIS
                or not isinstance(graph, dict) or graph.get("extractor_identity") != current_extractor):
            raise AtlasError("route binding requires the current snapshot schema and extractor")
        live = _live_inventory_identity(str(snapshot.get("repository_root", "")))
        changed, reasons = _focus_source_identity(snapshot, live)
        if changed or reasons:
            raise AtlasError("route binding snapshot is not current against its recorded checkout: " + "; ".join(reasons))
        _validate_route_binding(binding, snapshot, str(binding["route_fact_id"]))
        flow = query_flow(db_arg, str(binding["snapshot_id"]), str(binding["overlay_id"]))
        if flow["review_status"] != "accepted":
            raise AtlasError("route binding requires an accepted reviewed-flow receipt")
        if flow["review_receipt"].get("receipt_hash") != binding["flow_review_receipt_hash"]:
            raise AtlasError("route binding flow_review_receipt_hash does not match the exact accepted receipt")
        if flow["overlay"].get("content_hash") != binding["overlay_id"]:
            raise AtlasError("route binding overlay_id does not match the overlay content hash")
        binding_hash = hashlib.sha256(_canonical_json(binding)).hexdigest()
        _validate_route_association_review(review, binding, binding_hash)
        review_hash = hashlib.sha256(_canonical_json(review)).hexdigest()
        binding_payload = {"binding": binding, "binding_hash": binding_hash}
        review_payload = {**review, "association_review_hash": review_hash}
        payload_json = _canonical_json({**binding_payload, "association_review": review_payload}).decode("ascii")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS atlas_route_bindings ("
            "snapshot_id TEXT NOT NULL, route_fact_id TEXT NOT NULL, overlay_id TEXT NOT NULL, "
            "binding_hash TEXT NOT NULL, association_review_hash TEXT NOT NULL, payload_json TEXT NOT NULL, "
            "PRIMARY KEY(snapshot_id, route_fact_id, overlay_id), "
            "FOREIGN KEY(snapshot_id, overlay_id) REFERENCES atlas_reviewed_flows(snapshot_id, content_hash))"
        )
        previous = connection.execute(
            "SELECT binding_hash, association_review_hash, payload_json FROM atlas_route_bindings "
            "WHERE snapshot_id = ? AND route_fact_id = ? AND overlay_id = ?",
            (binding["snapshot_id"], binding["route_fact_id"], binding["overlay_id"]),
        ).fetchone()
        if previous is not None and previous != (binding_hash, review_hash, payload_json):
            raise AtlasError("route binding is immutable; a different association review already exists for this key")
        if previous is None:
            connection.execute(
                "INSERT INTO atlas_route_bindings(snapshot_id, route_fact_id, overlay_id, binding_hash, association_review_hash, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (binding["snapshot_id"], binding["route_fact_id"], binding["overlay_id"], binding_hash, review_hash, payload_json),
            )
        connection.commit()
        return {"snapshot_id": binding["snapshot_id"], "route_fact_id": binding["route_fact_id"],
                "overlay_id": binding["overlay_id"], "binding_hash": binding_hash,
                "association_review_hash": review_hash, "binding": binding_payload["binding"],
                "association_review": review_payload}
    except (sqlite3.Error, AtlasError):
        connection.rollback()
        raise
    finally:
        connection.close()


def _read_json_file(path: str, label: str) -> tuple[dict[str, object], bytes]:
    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot read {label} JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AtlasError(f"{label} JSON must contain an object")
    return value, raw


def _route_map_packet_digest(packet: dict[str, object]) -> str:
    unsigned = {key: value for key, value in packet.items() if key != "packet_sha256"}
    return hashlib.sha256(_canonical_json(unsigned) + b"\n").hexdigest()


def _route_map_draft(packet: dict[str, object]) -> tuple[dict[str, object], bytes]:
    text = packet.get("draft")
    if not isinstance(text, str):
        raise AtlasError("route-map packet must contain the exact draft text")
    raw = text.encode("utf-8")
    if hashlib.sha256(raw).hexdigest() != packet.get("draft_sha256"):
        raise AtlasError("route-map draft hash does not match the exact draft text")
    try:
        draft = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AtlasError(f"route-map draft is not valid JSON: {exc}") from exc
    if not isinstance(draft, dict):
        raise AtlasError("route-map draft must contain an object")
    claims = draft.get("reviewed_conclusions")
    if not isinstance(claims, list) or not claims:
        raise AtlasError("route-map draft must contain at least one reviewed conclusion")
    expected_claims = [
        {"conclusion_number": index, "claim": item.get("claim"), "evidence": item.get("evidence")}
        for index, item in enumerate(claims, start=1) if isinstance(item, dict)
    ]
    if len(expected_claims) != len(claims) or packet.get("claims") != expected_claims:
        raise AtlasError("route-map packet claim list does not exactly match the complete draft")
    return draft, raw


def _route_map_validate_packet(
    packet: dict[str, object], db_arg: str, repo_arg: str,
    allow_existing_overlay_id: str | None = None,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], bytes]:
    if packet.get("packet_schema_version") != 1 or packet.get("result") != "route_map_review_required":
        raise AtlasError("unsupported route-map review packet")
    if _route_map_packet_digest(packet) != packet.get("packet_sha256"):
        raise AtlasError("route-map packet hash is invalid or the packet was changed")
    binding = packet.get("binding")
    evidence = packet.get("complete_evidence_packet")
    budget = packet.get("budget")
    if not isinstance(binding, dict) or not isinstance(evidence, dict) or not isinstance(budget, dict):
        raise AtlasError("route-map packet is missing its binding, complete evidence, or budget")
    route_fact_id = binding.get("route_fact_id")
    max_bytes = budget.get("max_stdout_bytes")
    if not isinstance(route_fact_id, str) or not route_fact_id or not isinstance(max_bytes, int) or max_bytes < 1:
        raise AtlasError("route-map packet route or evidence budget is invalid")
    if evidence.get("selection", {}).get("complete") is not True or evidence.get("selection", {}).get("omitted_candidate_bundles") != 0:
        raise AtlasError("route-map review requires the complete evidence packet; increase --max-tokens and prepare again")
    evidence_bytes = _canonical_json(evidence) + b"\n"
    evidence_hash = hashlib.sha256(evidence_bytes).hexdigest()
    if (evidence_hash != packet.get("evidence_sha256") or evidence.get("snapshot_id") != binding.get("snapshot_id")
            or evidence.get("extractor_identity") != binding.get("extractor_identity")
            or evidence.get("route", {}).get("fact_id") != route_fact_id):
        raise AtlasError("route-map evidence digest or identity does not match its packet binding")
    live_evidence, live_bytes, status = evidence_pack(
        db_arg, repo_arg, route_fact_id, max_bytes,
    )
    if status != 0 or live_evidence.get("selection", {}).get("complete") is not True:
        raise AtlasError("current route evidence is incomplete; no review or publication is allowed")
    if live_bytes != evidence_bytes:
        raise AtlasError("route-map packet is stale: current complete route evidence differs from the reviewed packet")
    snapshot, _snapshots, extractor_identity, _live = _current_route_snapshot(Path(db_arg).expanduser().absolute(), repo_arg)
    if (snapshot.get("snapshot_id") != binding.get("snapshot_id")
            or extractor_identity != binding.get("extractor_identity")):
        raise AtlasError("route-map packet is stale against the current snapshot or extractor")
    route_status, _route_bytes, _route_exit = route_find(db_arg, repo_arg, route_fact_id, 2**31 - 1)
    if route_status.get("result") != "unmapped":
        existing_overlay = route_status.get("association", {}).get("binding", {}).get("overlay_id")
        if not (allow_existing_overlay_id is not None and route_status.get("result") == "fresh"
                and existing_overlay == allow_existing_overlay_id):
            raise AtlasError("route-map workflow requires one open route with zero accepted associations")
    draft, draft_bytes = _route_map_draft(packet)
    if "content_hash" in draft:
        raise AtlasError("route-map draft must not supply content_hash; it is computed canonically")
    if draft.get("snapshot_id") != binding.get("snapshot_id") or draft.get("extractor_identity") != binding.get("extractor_identity"):
        raise AtlasError("route-map draft snapshot or extractor does not match its packet")
    _validate_reviewed_flow(snapshot, draft)
    graph = snapshot.get("source_graph", {})
    facts = {fact.get("id"): fact for fact in graph.get("facts", []) if isinstance(fact, dict)}
    route_fact = facts.get(route_fact_id)
    if not isinstance(route_fact, dict) or route_fact.get("kind") != "route_action":
        raise AtlasError("route-map packet route_fact_id is not one current route_action fact")
    packet_sources: dict[str, set[bytes]] = {}
    for field in ("source_snippets", "candidate_snippets"):
        snippets = evidence.get(field)
        if not isinstance(snippets, list):
            raise AtlasError(f"route-map evidence {field} must be a list")
        for snippet in snippets:
            if not isinstance(snippet, dict) or not isinstance(snippet.get("fact_id"), str):
                raise AtlasError(f"route-map evidence {field} contains a malformed source fact")
            source = {key: snippet.get(key) for key in ("path", "sha256", "span")}
            packet_sources.setdefault(snippet["fact_id"], set()).add(_canonical_json(source))
    graph_facts = graph.get("facts", [])
    for conclusion in draft.get("reviewed_conclusions", []):
        for citation in conclusion.get("evidence", []):
            fact_id = citation.get("fact_id")
            matches = [fact for fact in graph_facts if fact.get("id") == fact_id]
            if len(matches) != 1:
                raise AtlasError(f"route-map citation fact must resolve to one saved fact: {fact_id}")
            source = matches[0].get("source")
            if not isinstance(source, dict) or citation.get("source") != source:
                raise AtlasError(f"route-map citation source does not exactly match saved fact {fact_id}")
            if _canonical_json(source) not in packet_sources.get(str(fact_id), set()):
                raise AtlasError(f"route-map citation fact is not included with its exact source in the complete evidence packet: {fact_id}")
    if not any(any(citation.get("fact_id") == route_fact_id for citation in conclusion.get("evidence", []))
               for conclusion in draft.get("reviewed_conclusions", []) if isinstance(conclusion, dict)):
        raise AtlasError("route-map draft must cite the selected route fact in at least one conclusion")
    return snapshot, draft, route_fact, draft_bytes


def _validate_route_map_review(review: dict[str, object], packet: dict[str, object]) -> dict[str, object]:
    if review.get("review_schema_version") != 1:
        raise AtlasError("unsupported route-map independent review schema version")
    if review.get("packet_sha256") != packet.get("packet_sha256"):
        raise AtlasError("route-map review does not match the exact complete-evidence/draft packet")
    if review.get("evidence_sha256") != packet.get("evidence_sha256"):
        raise AtlasError("route-map review evidence_sha256 does not match the complete evidence packet")
    if review.get("draft_sha256") != packet.get("draft_sha256"):
        raise AtlasError("route-map review draft_sha256 does not match the exact Luna draft")
    for field in ("reviewer_identity", "reviewer_model"):
        value = review.get(field)
        if not isinstance(value, str) or not value.strip():
            raise AtlasError(f"route-map review requires nonempty {field} provenance label")
    if review.get("reviewer_model") != "GPT-6.1 Sol High":
        raise AtlasError("route-map review reviewer_model label must be exactly 'GPT-6.1 Sol High'")
    timestamp = review.get("reviewed_at")
    if not isinstance(timestamp, str):
        raise AtlasError("route-map review reviewed_at must be an ISO timestamp with timezone")
    try:
        parsed = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AtlasError("route-map review reviewed_at must be an ISO timestamp with timezone") from exc
    if parsed.tzinfo is None:
        raise AtlasError("route-map review reviewed_at must include a timezone")
    assignment = review.get("assignment_review")
    association = review.get("route_association_review")
    if not isinstance(assignment, dict) or not isinstance(association, dict):
        raise AtlasError("route-map review must include independent assignment and route-association decisions")
    if assignment.get("decision") not in {"accepted", "rejected"}:
        raise AtlasError("assignment_review decision must be accepted or rejected")
    if association.get("decision") not in {"accepted", "rejected"}:
        raise AtlasError("route_association_review decision must be accepted or rejected")
    for label, value in (("assignment_review", assignment), ("route_association_review", association)):
        basis = value.get("basis")
        if not isinstance(basis, str) or len(basis.strip()) < 20 or len(basis) > 2000:
            raise AtlasError(f"{label} basis must explain the decision in 20 to 2000 characters")
    claims = packet.get("claims")
    reviews = review.get("conclusion_reviews")
    if not isinstance(claims, list) or not isinstance(reviews, list) or len(reviews) != len(claims):
        raise AtlasError("route-map review must contain one ordered decision for every draft conclusion")
    accepted_claim_reviews = True
    for index, value in enumerate(reviews, start=1):
        if not isinstance(value, dict) or value.get("conclusion_number") != index:
            raise AtlasError(f"conclusion review {index} is missing or out of order")
        if value.get("decision") not in {"accepted", "rejected"}:
            raise AtlasError(f"conclusion {index} decision must be accepted or rejected")
        basis = value.get("basis")
        if not isinstance(basis, str) or len(basis.strip()) < 20 or len(basis) > 2000:
            raise AtlasError(f"conclusion {index} basis must explain the decision in 20 to 2000 characters")
        accepted_claim_reviews = accepted_claim_reviews and value["decision"] == "accepted"
    expected_decision = "accepted" if (
        assignment["decision"] == "accepted" and association["decision"] == "accepted" and accepted_claim_reviews
    ) else "rejected"
    if review.get("decision") != expected_decision:
        raise AtlasError(f"route-map review decision must be {expected_decision} based on all independent decisions")
    return review


def route_map_prepare(db_arg: str, repo_arg: str, route_fact_id: str, draft_path: str, max_bytes: int) -> tuple[dict[str, object], bytes, int]:
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    route_status, _route_bytes, _route_exit = route_find(db_arg, repo_arg, route_fact_id, 2**31 - 1)
    if route_status.get("result") != "unmapped":
        raise AtlasError("route-map prepare requires one open route with zero accepted associations")
    evidence, evidence_bytes, _status = evidence_pack(db_arg, repo_arg, route_fact_id, max_bytes)
    selection = evidence.get("selection", {})
    if selection.get("complete") is not True or selection.get("omitted_candidate_bundles") != 0:
        raise AtlasError("complete route-map evidence does not fit; increase --max-tokens and prepare again")
    try:
        draft_bytes = Path(draft_path).read_bytes()
        draft_text = draft_bytes.decode("utf-8")
        draft = json.loads(draft_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot read Luna route-map draft {draft_path}: {exc}") from exc
    if not isinstance(draft, dict):
        raise AtlasError("Luna route-map draft must contain an object")
    if "content_hash" in draft:
        raise AtlasError("route-map draft must not supply content_hash; it is computed canonically")
    snapshot_id = evidence["snapshot_id"]
    extractor_identity = evidence["extractor_identity"]
    if draft.get("snapshot_id") != snapshot_id or draft.get("extractor_identity") != extractor_identity:
        raise AtlasError("Luna route-map draft snapshot_id and extractor_identity must match the current evidence")
    snapshot, _snapshots, _extractor, _live = _current_route_snapshot(Path(db_arg).expanduser().absolute(), repo_arg)
    _validate_reviewed_flow(snapshot, draft)
    fact_ids = {item.get("fact_id") for item in evidence.get("source_snippets", []) + evidence.get("candidate_snippets", [])}
    fact_ids.add(route_fact_id)
    citations = [citation for conclusion in draft.get("reviewed_conclusions", [])
                 for citation in conclusion.get("evidence", [])]
    if any(citation.get("fact_id") not in fact_ids for citation in citations):
        raise AtlasError("Luna draft cites a fact outside the exact complete evidence packet")
    if not any(citation.get("fact_id") == route_fact_id for citation in citations):
        raise AtlasError("Luna draft must cite the selected route fact in at least one conclusion")
    evidence_hash = hashlib.sha256(evidence_bytes).hexdigest()
    claims = [
        {"conclusion_number": index, "claim": item["claim"], "evidence": item["evidence"]}
        for index, item in enumerate(draft["reviewed_conclusions"], start=1)
    ]
    packet: dict[str, object] = {
        "packet_schema_version": 1,
        "result": "route_map_review_required",
        "binding": {"snapshot_id": snapshot_id, "extractor_identity": extractor_identity,
                    "route_fact_id": route_fact_id},
        "budget": {"max_stdout_bytes": max_bytes, "unit": "ASCII stdout bytes including newline; not model tokens"},
        "evidence_sha256": evidence_hash,
        "complete_evidence_packet": evidence,
        "draft_sha256": hashlib.sha256(draft_bytes).hexdigest(),
        "draft": draft_text,
        "claims": claims,
        "review_instructions": (
            "Independently review this assignment and every conclusion against its exact cited source spans. "
            "Confirm the Luna draft stays within the one selected route and makes no inference about helper bodies "
            "or runtime behavior omitted from this packet. Give one accepted/rejected decision and concrete basis "
            "for every conclusion. Separately decide whether this complete map is correctly associated with the "
            "selected route. Accept only when the assignment, every conclusion, and route association are accepted. "
            "Reviewer identity and model are audit labels supplied by the caller and are not authenticated by Atlas."
        ),
    }
    packet["packet_sha256"] = _route_map_packet_digest(packet)
    encoded = _canonical_json(packet) + b"\n"
    if len(encoded) > max_bytes:
        raise AtlasError(f"complete route-map review packet requires {len(encoded)} ASCII stdout bytes including newline; --max-tokens limit is {max_bytes}; stdout withheld")
    return packet, encoded, 0


def route_map_review(db_arg: str, repo_arg: str, packet_path: str, review_path: str) -> tuple[dict[str, object], bytes, int]:
    packet, _packet_bytes = _read_json_file(packet_path, "route-map packet")
    review, _review_bytes = _read_json_file(review_path, "route-map independent review")
    _route_map_validate_packet(packet, db_arg, repo_arg)
    _validate_route_map_review(review, packet)
    result = {"result": review["decision"], "packet_sha256": packet["packet_sha256"],
              "evidence_sha256": packet["evidence_sha256"], "draft_sha256": packet["draft_sha256"],
              "review": review, "writes": 0}
    return result, _canonical_json(result) + b"\n", 0


def publish_route_map(db_arg: str, repo_arg: str, packet_path: str, review_path: str) -> dict[str, object]:
    packet, _packet_bytes = _read_json_file(packet_path, "route-map packet")
    review, _review_bytes = _read_json_file(review_path, "route-map independent review")
    if review.get("decision") != "accepted":
        raise AtlasError("route-map review was rejected; no atlas records were written")
    _validate_route_map_review(review, packet)
    db_path = Path(db_arg).expanduser().absolute()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    connection = _connect_for_index(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        preview_draft, _preview_bytes = _route_map_draft(packet)
        expected_overlay_id = hashlib.sha256(_canonical_json(preview_draft)).hexdigest()
        snapshot, draft, route_fact, _draft_bytes = _route_map_validate_packet(
            packet, db_arg, repo_arg, allow_existing_overlay_id=expected_overlay_id,
        )
        binding_info = packet["binding"]
        snapshot_id = str(binding_info["snapshot_id"])
        extractor_identity = str(binding_info["extractor_identity"])
        route_fact_id = str(binding_info["route_fact_id"])
        overlay_id = hashlib.sha256(_canonical_json(draft)).hexdigest()
        overlay_payload = {**draft, "content_hash": overlay_id}
        overlay_json = _canonical_json(overlay_payload).decode("ascii")
        receipt = {
            "receipt_schema_version": 1, "snapshot_id": snapshot_id, "overlay_id": overlay_id,
            "overlay_content_hash": overlay_id, "extractor_identity": extractor_identity,
            "reviewer_identity": review["reviewer_identity"], "reviewer_model": review["reviewer_model"],
            "decision": "accepted", "reviewed_at": review["reviewed_at"],
            "review_basis": review["assignment_review"]["basis"],
            "packet_sha256": packet["packet_sha256"], "evidence_sha256": packet["evidence_sha256"],
            "draft_sha256": packet["draft_sha256"],
            "conclusion_reviews": review["conclusion_reviews"],
            "route_association_review": review["route_association_review"],
        }
        _validate_reviewed_flow(snapshot, draft)
        _validate_review_receipt(receipt, snapshot_id, overlay_id, overlay_id, extractor_identity)
        receipt_hash = hashlib.sha256(_canonical_json(receipt)).hexdigest()
        receipt_payload = {**receipt, "receipt_hash": receipt_hash}
        receipt_json = _canonical_json(receipt_payload).decode("ascii")
        binding = {"binding_schema_version": 1, "snapshot_id": snapshot_id,
                   "extractor_identity": extractor_identity, "route_fact_id": route_fact_id,
                   "overlay_id": overlay_id, "flow_review_receipt_hash": receipt_hash}
        binding_hash = hashlib.sha256(_canonical_json(binding)).hexdigest()
        association_review = {
            "review_schema_version": 1, "binding_hash": binding_hash, **binding,
            "reviewer_identity": review["reviewer_identity"], "reviewer_model": review["reviewer_model"],
            "decision": "accepted", "reviewed_at": review["reviewed_at"],
            "review_basis": review["route_association_review"]["basis"],
        }
        _validate_route_binding(binding, snapshot, route_fact_id)
        _validate_route_association_review(association_review, binding, binding_hash)
        association_hash = hashlib.sha256(_canonical_json(association_review)).hexdigest()
        association_payload = {"binding": binding, "binding_hash": binding_hash,
                               "association_review": {**association_review, "association_review_hash": association_hash}}
        association_json = _canonical_json(association_payload).decode("ascii")

        connection.execute(
            "CREATE TABLE IF NOT EXISTS atlas_reviewed_flows ("
            "snapshot_id TEXT NOT NULL, content_hash TEXT NOT NULL, payload_json TEXT NOT NULL, "
            "PRIMARY KEY(snapshot_id, content_hash), FOREIGN KEY(snapshot_id) REFERENCES atlas_snapshots(snapshot_id))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS atlas_flow_reviews ("
            "snapshot_id TEXT NOT NULL, overlay_id TEXT NOT NULL, receipt_hash TEXT NOT NULL, receipt_json TEXT NOT NULL, "
            "PRIMARY KEY(snapshot_id, overlay_id), "
            "FOREIGN KEY(snapshot_id, overlay_id) REFERENCES atlas_reviewed_flows(snapshot_id, content_hash))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS atlas_route_bindings ("
            "snapshot_id TEXT NOT NULL, route_fact_id TEXT NOT NULL, overlay_id TEXT NOT NULL, "
            "binding_hash TEXT NOT NULL, association_review_hash TEXT NOT NULL, payload_json TEXT NOT NULL, "
            "PRIMARY KEY(snapshot_id, route_fact_id, overlay_id), "
            "FOREIGN KEY(snapshot_id, overlay_id) REFERENCES atlas_reviewed_flows(snapshot_id, content_hash))"
        )
        previous_overlay = connection.execute(
            "SELECT payload_json FROM atlas_reviewed_flows WHERE snapshot_id=? AND content_hash=?",
            (snapshot_id, overlay_id),
        ).fetchone()
        previous_receipt = connection.execute(
            "SELECT receipt_hash, receipt_json FROM atlas_flow_reviews WHERE snapshot_id=? AND overlay_id=?",
            (snapshot_id, overlay_id),
        ).fetchone()
        previous_binding = connection.execute(
            "SELECT binding_hash, association_review_hash, payload_json FROM atlas_route_bindings "
            "WHERE snapshot_id=? AND route_fact_id=? AND overlay_id=?",
            (snapshot_id, route_fact_id, overlay_id),
        ).fetchone()
        expected_binding_row = (binding_hash, association_hash, association_json)
        if previous_overlay is not None and previous_overlay[0] != overlay_json:
            raise AtlasError("reviewed-flow overlay is immutable; conflicting bytes already exist")
        if previous_receipt is not None and previous_receipt != (receipt_hash, receipt_json):
            raise AtlasError("review receipt is immutable; a conflicting decision already exists")
        if previous_binding is not None and previous_binding != expected_binding_row:
            raise AtlasError("route binding is immutable; a conflicting association review already exists")
        if previous_overlay is None:
            connection.execute("INSERT INTO atlas_reviewed_flows(snapshot_id,content_hash,payload_json) VALUES (?,?,?)",
                               (snapshot_id, overlay_id, overlay_json))
        if previous_receipt is None:
            connection.execute("INSERT INTO atlas_flow_reviews(snapshot_id,overlay_id,receipt_hash,receipt_json) VALUES (?,?,?,?)",
                               (snapshot_id, overlay_id, receipt_hash, receipt_json))
        if previous_binding is None:
            connection.execute(
                "INSERT INTO atlas_route_bindings(snapshot_id,route_fact_id,overlay_id,binding_hash,association_review_hash,payload_json) "
                "VALUES (?,?,?,?,?,?)",
                (snapshot_id, route_fact_id, overlay_id, binding_hash, association_hash, association_json),
            )
        # Recheck after all writes, immediately before commit. The SQLite transaction
        # rolls back if the checkout or evidence changed while records were assembled.
        _route_map_validate_packet(packet, db_arg, repo_arg, allow_existing_overlay_id=overlay_id)
        connection.commit()
        return {"result": "published", "snapshot_id": snapshot_id, "route_fact_id": route_fact_id,
                "overlay_id": overlay_id, "receipt_hash": receipt_hash, "binding_hash": binding_hash,
                "association_review_hash": association_hash, "packet_sha256": packet["packet_sha256"],
                "evidence_sha256": packet["evidence_sha256"], "idempotent": all(
                    row is not None for row in (previous_overlay, previous_receipt, previous_binding))}
    except (sqlite3.Error, AtlasError):
        connection.rollback()
        raise
    finally:
        connection.close()


def _route_find_render(document: dict[str, object], max_bytes: int) -> bytes:
    def render() -> bytes:
        return (json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    encoded = render()
    actual = len(encoded)
    for _ in range(4):
        if isinstance(document.get("budget"), dict):
            document["budget"]["stdout_bytes_including_newline"] = actual
        encoded = render()
        updated = len(encoded)
        if updated == actual:
            break
        actual = updated
    if actual > max_bytes:
        raise AtlasError(f"complete route-find output requires {actual} ASCII stdout bytes including newline; --max-tokens limit is {max_bytes}; stdout withheld")
    return encoded


def _current_route_snapshot(db_path: Path, repo_arg: str) -> tuple[dict[str, object], dict[str, dict[str, object]], str, dict[str, object]]:
    live = _live_inventory_identity(repo_arg)
    from csharp_facts import EXTRACTION_METHOD
    extractor_identity = f"{EXTRACTION_METHOD}:python-stdlib-lexer"
    uri = db_path.absolute().as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            rows = connection.execute("SELECT snapshot_id, payload_json FROM atlas_snapshots ORDER BY snapshot_id").fetchall()
    except sqlite3.Error as exc:
        raise AtlasError(f"cannot query snapshots for route lookup: {exc}") from exc
    compatible = []
    snapshots_by_id: dict[str, dict[str, object]] = {}
    for row_id, payload_json in rows:
        try:
            saved = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise AtlasError(f"saved snapshot JSON is corrupt: {row_id}") from exc
        graph = saved.get("source_graph") if isinstance(saved, dict) else None
        if isinstance(saved, dict) and saved.get("snapshot_id") == row_id:
            snapshots_by_id[row_id] = saved
        if (isinstance(saved, dict) and saved.get("snapshot_id") == row_id
                and saved.get("schema_version") == SCHEMA_VERSION and saved.get("inventory_basis") == INVENTORY_BASIS
                and isinstance(graph, dict) and graph.get("extractor_identity") == extractor_identity):
            changed, reasons = _focus_source_identity(saved, live)
            if not changed and not reasons:
                compatible.append(saved)
    if len(compatible) != 1:
        reason = "no_saved_snapshot_matches_current_extractor_and_checkout" if not compatible else "multiple_saved_snapshots_match_current_extractor_and_checkout"
        raise AtlasError(f"{reason}; compatible matching snapshots={len(compatible)}")
    return compatible[0], snapshots_by_id, extractor_identity, live


def _validated_route_associations(db_arg: str, db_path: Path, snapshot: dict[str, object],
                                  snapshots_by_id: dict[str, dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Validate every registered association exactly as route-find does, grouped by route ID."""
    uri = db_path.absolute().as_uri() + "?mode=ro"
    table_exists = False
    binding_rows = []
    with sqlite3.connect(uri, uri=True) as connection:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'atlas_route_bindings'"
        ).fetchone() is not None
        if table_exists:
            binding_rows = connection.execute(
                "SELECT snapshot_id, route_fact_id, overlay_id, binding_hash, association_review_hash, payload_json FROM atlas_route_bindings "
                "ORDER BY snapshot_id, route_fact_id, overlay_id"
            ).fetchall()

    associations: dict[str, list[dict[str, object]]] = {}
    for row_snapshot_id, row_route_fact_id, row_overlay_id, stored_binding_hash, stored_review_hash, payload_json in binding_rows:
        try:
            payload = json.loads(payload_json)
            binding = payload["binding"]
            review_payload = payload["association_review"]
            if not isinstance(binding, dict) or not isinstance(review_payload, dict):
                raise AtlasError("saved route binding and association review must be objects")
            review = {key: value for key, value in review_payload.items() if key != "association_review_hash"}
        except AtlasError:
            raise
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
            raise AtlasError("saved route binding is corrupt") from exc
        bound_snapshot = snapshots_by_id.get(str(binding.get("snapshot_id")))
        if bound_snapshot is None:
            raise AtlasError("saved route binding references a missing or corrupt snapshot")
        bound_route_id = binding.get("route_fact_id")
        if not isinstance(bound_route_id, str):
            raise AtlasError("saved route binding route_fact_id is invalid")
        _validate_route_binding(binding, bound_snapshot, bound_route_id)
        if (binding.get("snapshot_id") != row_snapshot_id or binding.get("route_fact_id") != row_route_fact_id
                or binding.get("overlay_id") != row_overlay_id):
            raise AtlasError("saved route binding payload does not match its registry key")
        binding_hash = hashlib.sha256(_canonical_json(binding)).hexdigest()
        review_hash = hashlib.sha256(_canonical_json(review)).hexdigest()
        if (binding_hash != stored_binding_hash or payload.get("binding_hash") != stored_binding_hash
                or review_hash != stored_review_hash or review_payload.get("association_review_hash") != stored_review_hash):
            raise AtlasError("saved route binding or association-review integrity hash is invalid")
        flow = query_flow(db_arg, str(binding["snapshot_id"]), str(binding.get("overlay_id")))
        if flow["review_status"] != "accepted":
            raise AtlasError("saved route binding points to a flow without an accepted review receipt")
        receipt_hash = flow["review_receipt"].get("receipt_hash")
        try:
            with sqlite3.connect(uri, uri=True) as connection:
                receipt_hash_row = connection.execute(
                    "SELECT receipt_hash FROM atlas_flow_reviews WHERE snapshot_id = ? AND overlay_id = ?",
                    (binding["snapshot_id"], binding["overlay_id"]),
                ).fetchone()
        except sqlite3.Error as exc:
            raise AtlasError(f"cannot verify flow review receipt registry hash: {exc}") from exc
        if receipt_hash_row is None or receipt_hash_row[0] != receipt_hash:
            raise AtlasError("flow review receipt registry hash does not match its validated receipt payload")
        if receipt_hash != binding.get("flow_review_receipt_hash"):
            raise AtlasError("saved route binding flow receipt is missing or changed")
        _validate_route_association_review(review, binding, binding_hash)
        if row_snapshot_id == snapshot["snapshot_id"]:
            associations.setdefault(str(row_route_fact_id), []).append(
                {"binding": binding, "binding_hash": binding_hash,
                 "association_review": review_payload, "association_review_hash": review_hash})
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            carry_rows = connection.execute(
                "SELECT route_fact_id, overlay_id FROM atlas_route_carries WHERE target_snapshot_id=? "
                "ORDER BY route_fact_id, overlay_id", (snapshot["snapshot_id"],)
            ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise AtlasError(f"cannot query carried route associations: {exc}") from exc
        carry_rows = []
    except sqlite3.Error as exc:
        raise AtlasError(f"cannot query carried route associations: {exc}") from exc
    for carried_route_id, carried_overlay_id in carry_rows:
        resolved = _resolve_route_carry(db_path, str(snapshot["snapshot_id"]), str(carried_overlay_id))
        if resolved is None:
            raise AtlasError("carried route association disappeared during validation")
        origin_row = next((row for row in binding_rows
                           if row[0] == resolved[1]["origin_snapshot_id"]
                           and row[1] == carried_route_id and row[2] == resolved[1]["origin_overlay_id"]), None)
        if origin_row is None:
            raise AtlasError("carried route origin association is missing")
        origin_payload = json.loads(origin_row[5])
        associations.setdefault(str(carried_route_id), []).append({
            "binding": origin_payload["binding"], "binding_hash": resolved[1]["origin_binding_hash"],
            "association_review": origin_payload["association_review"],
            "association_review_hash": resolved[1]["origin_association_review_hash"],
            "carry_provenance": resolved[1],
        })
    return associations


def route_find(db_arg: str, repo_arg: str, route_fact_id: str, max_bytes: int) -> tuple[dict[str, object], bytes, int]:
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    db_path = Path(db_arg).expanduser()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    snapshot, snapshots_by_id, extractor_identity, live = _current_route_snapshot(db_path, repo_arg)
    graph = snapshot["source_graph"]
    matching = [fact for fact in graph.get("facts", []) if fact.get("id") == route_fact_id]
    if not matching:
        raise AtlasError(f"unknown route fact ID: {route_fact_id}")
    if len(matching) != 1 or matching[0].get("kind") != "route_action":
        raise AtlasError(f"route fact ID has wrong kind or is ambiguous: {route_fact_id}")
    all_associations = _validated_route_associations(db_arg, db_path, snapshot, snapshots_by_id)
    associations = all_associations.get(route_fact_id, [])

    base = {"snapshot_id": snapshot["snapshot_id"], "extractor_identity": extractor_identity,
            "route_fact_id": route_fact_id, "association_count": len(associations),
            "budget": {"limit": max_bytes, "unit": "ASCII stdout bytes, a conservative byte proxy; not measured model tokens or prompt overhead",
                       "stdout_bytes_including_newline": 0}}
    if not associations:
        document = {"result": "unmapped", **base,
                    "next_step": {"command": "evidence-pack", "arguments": {
                        "--db": os.fspath(db_path.absolute()), "--repo": os.fspath(Path(live["repository_root"])),
                        "--route-fact-id": route_fact_id, "--max-tokens": max_bytes}}}
        return document, _route_find_render(document, max_bytes), 0
    if len(associations) > 1:
        document = {"result": "selection_required", **base, "associations": associations}
        return document, _route_find_render(document, max_bytes), 0

    association = associations[0]
    focused, _, status = focus(db_arg, repo_arg, snapshot["snapshot_id"], association["binding"]["overlay_id"], 2**31 - 1)
    if status != 0 or focused.get("result") != "fresh":
        raise AtlasError("route-find requires a fresh accepted focus result")
    selection = focused.get("claim_selection", {})
    if selection.get("omitted_claims") != 0 or selection.get("included_claims") != selection.get("total_claims"):
        raise AtlasError("route-find requires every reviewed map claim; focus omitted claims")
    document = {**focused, "route_fact_id": route_fact_id, "association": association,
                "association_count": 1,
                "budget": {"limit": max_bytes, "unit": "ASCII stdout bytes, a conservative byte proxy; not measured model tokens or prompt overhead",
                           "stdout_bytes_including_newline": 0}}
    return document, _route_find_render(document, max_bytes), 0


def _coverage_render(document: dict[str, object], max_bytes: int) -> bytes:
    def render() -> bytes:
        return (json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    encoded = render()
    actual = len(encoded)
    for _ in range(4):
        document["budget"]["stdout_bytes_including_newline"] = actual
        encoded = render()
        updated = len(encoded)
        if updated == actual:
            break
        actual = updated
    if actual > max_bytes:
        raise AtlasError(f"complete coverage page requires {actual} ASCII stdout bytes including newline; --max-tokens limit is {max_bytes}; stdout withheld")
    return encoded


def route_coverage(db_arg: str, repo_arg: str, max_bytes: int, offset: int = 0) -> tuple[dict[str, object], bytes, int]:
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    if offset < 0:
        raise AtlasError("--offset must be zero or greater")
    db_path = Path(db_arg).expanduser()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    snapshot, snapshots_by_id, extractor_identity, live = _current_route_snapshot(db_path, repo_arg)
    graph = snapshot["source_graph"]
    facts = graph.get("facts")
    if not isinstance(facts, list) or any(not isinstance(fact, dict) for fact in facts):
        raise AtlasError("saved source graph facts must be a list of objects")
    route_facts = [fact for fact in facts if fact.get("kind") == "route_action"]
    routes_by_id: dict[str, dict[str, object]] = {}
    for fact in route_facts:
        route_id = fact.get("id")
        if not isinstance(route_id, str) or not route_id.strip():
            raise AtlasError("saved route_action fact has a non-string or empty id")
        if route_id in routes_by_id:
            raise AtlasError(f"saved route_action fact ID is duplicated: {route_id}")
        for field in ("http_method", "route_literal", "action_name"):
            value = fact.get(field)
            if not isinstance(value, str) or not value.strip():
                raise AtlasError(f"saved route_action fact {route_id} has invalid {field}")
        routes_by_id[route_id] = fact
    for route_id in routes_by_id:
        if sum(1 for other in facts if other.get("id") == route_id) != 1:
            raise AtlasError(f"saved route_action fact ID is not unique across source graph facts: {route_id}")
    route_ids = sorted(routes_by_id)
    total = len(route_ids)
    if offset > total:
        raise AtlasError(f"--offset {offset} exceeds saved route count {total}")

    associations = _validated_route_associations(db_arg, db_path, snapshot, snapshots_by_id)
    states: dict[str, tuple[str, int]] = {}
    counts = {"open": 0, "one_reviewed_link": 0, "selection_required": 0}
    for route_id in route_ids:
        association_count = len(associations.get(route_id, []))
        state = "open" if association_count == 0 else "one_reviewed_link" if association_count == 1 else "selection_required"
        states[route_id] = (state, association_count)
        counts[state] += 1

    page_ids = route_ids[offset:]
    rows: list[dict[str, object]] = []
    base = {
        "snapshot": {"snapshot_id": snapshot["snapshot_id"], "extractor_identity": extractor_identity},
        "current_checkout": {key: live[key] for key in ("repository_root", "head", "head_ref", "status")},
        "counts": {**counts, "total_routes": total},
        "offset": offset,
        "included_routes": 0,
        "remaining_routes": total - offset,
        "next_offset": None if offset == total else offset,
        "routes": rows,
        "scope": "all saved route_action facts in the one current matching snapshot; does not claim full codebase or runtime coverage",
        "next_step": {
            "open_route_command": "atlas.py route-find --db DB --repo PATH --route-fact-id ROUTE_FACT_ID --max-tokens N; when result is unmapped, run atlas.py evidence-pack --db DB --repo PATH --route-fact-id ROUTE_FACT_ID --max-tokens N",
            "selection_required_command": "atlas.py route-find --db DB --repo PATH --route-fact-id ROUTE_FACT_ID --max-tokens N",
        },
        "budget": {"limit": max_bytes, "unit": "ASCII stdout bytes including newline; conservative proxy, not measured model tokens", "stdout_bytes_including_newline": 0},
    }
    if not page_ids:
        encoded = _coverage_render(base, max_bytes)
        return base, encoded, 0

    for route_id in page_ids:
        fact = routes_by_id[route_id]
        state, association_count = states[route_id]
        rows.append({"route_fact_id": route_id, "http_method": fact["http_method"],
                     "route_literal": fact["route_literal"], "action_name": fact["action_name"],
                     "association_state": state, "reviewed_association_count": association_count})
        included = len(rows)
        base["included_routes"] = included
        base["remaining_routes"] = total - offset - included
        base["next_offset"] = None if base["remaining_routes"] == 0 else offset + included
        # Test each complete row. If the first row cannot fit, report its exact required page size.
        try:
            encoded = _coverage_render(base, max_bytes)
        except AtlasError:
            if included == 1:
                raise
            rows.pop()
            base["included_routes"] = len(rows)
            base["remaining_routes"] = total - offset - len(rows)
            base["next_offset"] = offset + len(rows)
            encoded = _coverage_render(base, max_bytes)
            return base, encoded, 0
    return base, encoded, 0


def _live_inventory_identity(repo_arg: str) -> dict[str, object]:
    root = _repo_root(repo_arg)
    head_bytes = _git_optional(root, "rev-parse", "--verify", "HEAD")
    head = os.fsdecode(head_bytes).strip() if head_bytes is not None else None
    head_ref = None
    if head is None:
        ref_bytes = _git_optional(root, "symbolic-ref", "-q", "HEAD")
        if ref_bytes is None:
            raise AtlasError("repository has no commit and no symbolic HEAD ref")
        head_ref = os.fsdecode(ref_bytes).strip()
    files, _ = _tracked_entries(root, collect_source_bytes=False)
    return {
        "repository_root": os.fspath(root),
        "head": head,
        "head_ref": head_ref,
        "status": _status(root),
        "files": files,
    }


def _focus_source_identity(snapshot: dict[str, object], live: dict[str, object]) -> tuple[list[str], list[str]]:
    changed: set[str] = set()
    reasons: list[str] = []
    if snapshot.get("repository_root") != live["repository_root"]:
        reasons.append("canonical repository root changed")
    if snapshot.get("head") != live["head"]:
        reasons.append(f"HEAD changed: saved={snapshot.get('head')!r}, live={live['head']!r}")
    if snapshot.get("head_ref") != live["head_ref"]:
        reasons.append(f"HEAD ref changed: saved={snapshot.get('head_ref')!r}, live={live['head_ref']!r}")
    saved_status = snapshot.get("status", [])
    live_status = live["status"]
    if saved_status != live_status:
        reasons.append("structured Git status changed")
        old = {entry["path"] for entry in saved_status}
        new = {entry["path"] for entry in live_status}
        changed.update(old ^ new)
        changed.update(
            path for path in old & new
            if next(item for item in saved_status if item["path"] == path)
            != next(item for item in live_status if item["path"] == path)
        )
    saved_files = {entry["path"]: entry for entry in snapshot.get("files", [])}
    live_files = {entry["path"]: entry for entry in live["files"]}
    for path in sorted(saved_files.keys() | live_files.keys(), key=lambda value: os.fsencode(value)):
        before = saved_files.get(path)
        after = live_files.get(path)
        if before is None or after is None:
            changed.add(path)
            reasons.append(f"tracked path set changed: {path} ({'added' if before is None else 'removed'})")
            continue
        if before.get("presence") != after.get("presence"):
            changed.add(path)
            reasons.append(f"tracked path presence changed: {path} ({before.get('presence')} -> {after.get('presence')})")
        if before.get("type") != after.get("type"):
            changed.add(path)
            reasons.append(f"tracked path type changed: {path} ({before.get('type')} -> {after.get('type')})")
        if before.get("git_mode") != after.get("git_mode"):
            changed.add(path)
            reasons.append(f"tracked Git mode changed: {path}")
        if before.get("size_bytes") != after.get("size_bytes"):
            changed.add(path)
            reasons.append(f"tracked file size changed: {path}")
        if before.get("sha256") != after.get("sha256"):
            changed.add(path)
            reasons.append(f"tracked file content hash changed: {path}")
    return sorted(changed, key=lambda path: os.fsencode(path)), sorted(set(reasons))


def _discover_render(document: dict[str, object], max_bytes: int) -> bytes:
    def render() -> bytes:
        return (json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")

    encoded = render()
    actual = len(encoded)
    for _ in range(4):
        if document.get("budget"):
            document["budget"]["stdout_bytes_including_newline"] = actual
        encoded = render()
        updated = len(encoded)
        if updated == actual:
            break
        actual = updated
    if actual > max_bytes:
        raise AtlasError(
            f"complete discover output requires {actual} ASCII stdout bytes including newline; "
            f"--max-tokens limit is {max_bytes}; stdout withheld"
        )
    return encoded


def _discover_failure(reason: str, max_bytes: int, **details: object) -> tuple[dict[str, object], bytes, int]:
    document: dict[str, object] = {
        "result": "refused",
        "reason": reason,
        **details,
        "budget": {
            "limit": max_bytes,
            "unit": "ASCII stdout bytes, a conservative byte proxy; not measured model tokens or prompt overhead",
            "stdout_bytes_including_newline": 0,
        },
    }
    encoded = _discover_render(document, max_bytes)
    return document, encoded, 3


def _lexical_words(value: str) -> set[str]:
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    expanded = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", expanded)
    return set(re.findall(r"[a-z0-9]+", expanded.casefold()))


def discover(db_arg: str, repo_arg: str, raw_terms: list[str], max_bytes: int) -> tuple[dict[str, object], bytes, int]:
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    terms = sorted({word for term in raw_terms for word in _lexical_words(term)})
    if not terms:
        raise AtlasError("--terms must contain at least one lexical term")

    try:
        db_path = Path(db_arg).expanduser()
        if not db_path.is_file():
            raise AtlasError(f"database does not exist: {db_path}")
        live = _live_inventory_identity(repo_arg)
        from csharp_facts import EXTRACTION_METHOD
        extractor_identity = f"{EXTRACTION_METHOD}:python-stdlib-lexer"
        uri = db_path.absolute().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            rows = connection.execute(
                "SELECT snapshot_id, payload_json FROM atlas_snapshots ORDER BY snapshot_id"
            ).fetchall()

        matches: list[dict[str, object]] = []
        source_mismatches: list[dict[str, object]] = []
        compatible_count = 0
        for row_id, payload_json in rows:
            saved = json.loads(payload_json)
            graph = saved.get("source_graph") or {}
            if (
                saved.get("schema_version") != SCHEMA_VERSION
                or saved.get("inventory_basis") != INVENTORY_BASIS
                or graph.get("extractor_identity") != extractor_identity
            ):
                continue
            compatible_count += 1
            changed_paths, reasons = _focus_source_identity(saved, live)
            if not changed_paths and not reasons:
                matches.append(saved)
            elif saved.get("repository_root") == live["repository_root"]:
                source_mismatches.append({
                    "snapshot_id": row_id,
                    "changed_paths": changed_paths,
                    "reasons": reasons,
                })

        if len(matches) != 1:
            matching_ids = sorted(str(item["snapshot_id"]) for item in matches)
            reason = "no_saved_snapshot_matches_current_extractor_and_checkout" if not matches else "multiple_saved_snapshots_match_current_extractor_and_checkout"
            return _discover_failure(
                reason,
                max_bytes,
                repository_root=live["repository_root"],
                current_extractor_identity=extractor_identity,
                checked_snapshot_count=len(rows),
                compatible_snapshot_count=compatible_count,
                matching_snapshot_ids=matching_ids,
                source_mismatches=sorted(source_mismatches, key=lambda item: item["snapshot_id"]),
                candidate_selection={"included_candidates": 0, "omitted_candidates": 0, "total_candidates": 0},
            )

        snapshot = matches[0]
        graph = snapshot["source_graph"]
        type_facts: dict[str, list[dict[str, object]]] = {}
        for fact in graph.get("facts", []):
            if fact.get("kind") == "type_declaration":
                type_facts.setdefault(str(fact.get("type_id")), []).append(fact)

        candidates: list[dict[str, object]] = []
        unresolved_count = 0
        unmatched_route_count = 0
        for fact in graph.get("facts", []):
            if fact.get("kind") != "route_action":
                continue
            controller_types = type_facts.get(str(fact.get("controller_type_id")), [])
            action_source = fact.get("source")
            if len(controller_types) != 1 or not isinstance(action_source, dict) or action_source.get("span") is None:
                unresolved_count += 1
                continue
            controller_fact = controller_types[0]
            controller_source = controller_fact.get("source")
            if not isinstance(controller_source, dict) or controller_source.get("span") is None:
                unresolved_count += 1
                continue
            lexical_text = " ".join((
                str(fact.get("action_name", "")),
                str(fact.get("route_literal", "")),
                str(fact.get("controller_type_id", "")),
                str(action_source.get("path", "")),
            ))
            matched_terms = sorted(set(terms) & _lexical_words(lexical_text))
            if not matched_terms:
                unmatched_route_count += 1
                continue
            candidates.append({
                "fact_id": fact["id"],
                "http_method": fact.get("http_method"),
                "route": fact.get("route_literal"),
                "action": fact.get("action_name"),
                "controller_type_id": fact.get("controller_type_id"),
                "lexical_score": len(matched_terms),
                "matched_terms": matched_terms,
                "action_source": {"fact_id": fact["id"], **action_source},
                "controller_source": {"fact_id": controller_fact["id"], **controller_source},
                "controller_route_source": fact.get("controller_route_source"),
            })

        candidates.sort(key=lambda item: (
            -int(item["lexical_score"]),
            os.fsencode(str(item["action_source"]["path"])),
            str(item["route"] or "").encode("ascii", "backslashreplace"),
            str(item["action"] or "").encode("ascii", "backslashreplace"),
            str(item["fact_id"]),
        ))
        base: dict[str, object] = {
            "result": "candidates" if candidates else "no_lexical_matches",
            "snapshot_id": snapshot["snapshot_id"],
            "extractor_identity": extractor_identity,
            "repository": {
                "root": live["repository_root"],
                "head": live["head"],
                "head_ref": live["head_ref"],
                "tracked_count": len(live["files"]),
                "status_entry_count": len(live["status"]),
            },
            "terms": terms,
            "ranking": "one point per distinct exact lexical token in action name, route, controller type, or action source path; ties by source path bytes, route, action, then fact ID",
            "unresolved_route_count": unresolved_count,
            "unmatched_route_count": unmatched_route_count,
            "matched_route_count": len(candidates),
            "candidate_selection": {"included_candidates": 0, "omitted_candidates": len(candidates), "total_candidates": len(candidates)},
            "candidates": [],
            "budget": {
                "limit": max_bytes,
                "unit": "ASCII stdout bytes, a conservative byte proxy; not measured model tokens or prompt overhead",
                "stdout_bytes_including_newline": 0,
            },
        }
        encoded = _discover_render(base, max_bytes)
        for candidate in candidates:
            selected = base["candidates"] + [candidate]
            trial = dict(base)
            trial["candidates"] = selected
            trial["candidate_selection"] = {
                "included_candidates": len(selected),
                "omitted_candidates": len(candidates) - len(selected),
                "total_candidates": len(candidates),
            }
            try:
                trial_encoded = _discover_render(trial, max_bytes)
            except AtlasError:
                break
            base, encoded = trial, trial_encoded
        # Re-render once so every count and the self-reported size describe exact stdout.
        encoded = _discover_render(base, max_bytes)
        return base, encoded, 0
    except (AtlasError, OSError, sqlite3.Error, json.JSONDecodeError, KeyError, TypeError) as exc:
        return _discover_failure(
            f"discover_error: {exc}",
            max_bytes,
            candidate_selection={"included_candidates": 0, "omitted_candidates": 0, "total_candidates": 0},
        )


def _source_texts(root: Path, references: list[tuple[str, dict[str, object]]]) -> list[dict[str, object]]:
    """Read cited source safely and prove each saved Unicode-codepoint span."""
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    contents: dict[str, tuple[str, str]] = {}
    snippets: dict[tuple[str, str, int, int, str], dict[str, object]] = {}
    try:
        for fact_id, source in references:
            if not isinstance(source, dict) or not isinstance(source.get("span"), dict):
                raise AtlasError(f"source fact {fact_id} has no verifiable span")
            path = source.get("path")
            expected_hash = source.get("sha256")
            span = source["span"]
            if not isinstance(path, str) or not isinstance(expected_hash, str):
                raise AtlasError(f"source fact {fact_id} has incomplete source identity")
            if span.get("offset_unit") != "unicode_codepoint":
                raise AtlasError(f"source fact {fact_id} has unsupported span unit")
            start, end = span.get("start_offset"), span.get("end_offset")
            if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
                raise AtlasError(f"source fact {fact_id} has invalid span offsets")
            if path not in contents:
                evidence = _read_working_file(root_fd, path, collect_source=True)
                if evidence.get("presence") != "present" or evidence.get("type") != "file":
                    raise AtlasError(f"cited source is missing or not a regular file: {path}")
                actual_hash = str(evidence.get("sha256"))
                if actual_hash != expected_hash:
                    raise AtlasError(f"cited source hash changed: {path}")
                raw = evidence.get("_source_bytes")
                if not isinstance(raw, bytes):
                    raise AtlasError(f"cited source could not be read: {path}")
                try:
                    decoded = raw.decode("utf-8-sig")
                except UnicodeDecodeError as exc:
                    raise AtlasError(f"cited source is not UTF-8: {path}") from exc
                contents[path] = (decoded, actual_hash)
            decoded, actual_hash = contents[path]
            if actual_hash != expected_hash:
                raise AtlasError(f"cited source hash changed: {path}")
            if end > len(decoded):
                raise AtlasError(f"source fact {fact_id} span exceeds decoded source")
            snippet = decoded[start:end]
            key = (path, actual_hash, start, end, fact_id)
            snippets[key] = {
                "fact_id": fact_id,
                "path": path,
                "sha256": actual_hash,
                "span": span,
                "text": snippet,
            }
    finally:
        os.close(root_fd)
    return [snippets[key] for key in sorted(snippets, key=lambda item: (os.fsencode(item[0]), item[2], item[3], item[4]))]


def _impact_render(document: dict[str, object], max_bytes: int) -> bytes:
    budget = document["budget"]
    assert isinstance(budget, dict)
    size = 0
    for _ in range(8):
        budget["stdout_bytes_including_newline"] = size
        encoded = (json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        actual = len(encoded)
        if actual == size:
            if actual > max_bytes:
                raise AtlasError(
                    f"complete impact view requires {actual} ASCII stdout bytes including newline; "
                    f"--max-tokens limit is {max_bytes}; stdout withheld"
                )
            return encoded
        size = actual
    raise AtlasError("impact view byte-count field did not stabilize; stdout withheld")


def impact_view(db_arg: str, repo_arg: str, qualified_method_name: str, max_bytes: int) -> tuple[dict[str, object], bytes, int]:
    """Show one saved method and exact class-qualified lexical call candidates."""
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    parts = qualified_method_name.split(".")
    if len(parts) < 2 or any(not re.fullmatch(r"@?[A-Za-z_][A-Za-z0-9_]*", part) for part in parts):
        raise AtlasError("--method must be a qualified Type.Member or Namespace.Type.Member name")
    method_name = parts[-1].removeprefix("@").strip()
    requested_type = ".".join(part.removeprefix("@") for part in parts[:-1])
    db_path = Path(db_arg).expanduser().absolute()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")

    snapshot, _snapshots, extractor_identity, _live = _current_route_snapshot(db_path, repo_arg)
    _validate_snapshot_fingerprint(snapshot, str(snapshot.get("snapshot_id")))
    graph = snapshot.get("source_graph")
    if not isinstance(graph, dict) or graph.get("extractor_identity") != extractor_identity:
        raise AtlasError("current saved snapshot has no matching source graph")
    facts = graph.get("facts")
    if not isinstance(facts, list):
        raise AtlasError("current saved source graph has invalid facts")

    types_by_id: dict[str, list[dict[str, object]]] = {}
    for fact in facts:
        if isinstance(fact, dict) and fact.get("kind") == "type_declaration":
            type_id = fact.get("type_id")
            if isinstance(type_id, str):
                types_by_id.setdefault(type_id, []).append(fact)
    method_matches = []
    for fact in facts:
        if not isinstance(fact, dict) or fact.get("kind") != "method_declaration" or fact.get("method_name") != method_name:
            continue
        owners = types_by_id.get(str(fact.get("owner_type_id")), [])
        if len(owners) != 1:
            continue
        owner = owners[0]
        full_type = ".".join(part for part in (owner.get("namespace"), owner.get("name")) if isinstance(part, str) and part)
        if requested_type in {owner.get("name"), full_type}:
            method_matches.append((fact, owner))
    if len(method_matches) != 1:
        if method_matches:
            raise AtlasError(f"method name is ambiguous in the saved graph: {qualified_method_name} ({len(method_matches)} declarations)")
        raise AtlasError(f"unique method declaration not found in the current saved graph: {qualified_method_name}")
    method, owner = method_matches[0]
    method_source = method.get("source")
    if not isinstance(method_source, dict):
        raise AtlasError("saved method declaration has no source anchor")

    root = _repo_root(repo_arg)
    files = snapshot.get("files")
    if not isinstance(files, list):
        raise AtlasError("current saved snapshot has invalid tracked-file inventory")
    file_texts: dict[str, tuple[str, str]] = {}
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for entry in files:
            if not isinstance(entry, dict):
                raise AtlasError("current saved snapshot contains an invalid tracked-file entry")
            path = entry.get("path")
            if not isinstance(path, str) or not path.lower().endswith(".cs"):
                continue
            if entry.get("presence") != "present" or entry.get("type") != "file" or not isinstance(entry.get("sha256"), str):
                raise AtlasError(f"tracked C# source is missing or not a regular file: {path}")
            evidence = _read_working_file(root_fd, path, collect_source=True)
            if evidence.get("presence") != "present" or evidence.get("type") != "file":
                raise AtlasError(f"tracked C# source is missing or unsafe: {path}")
            if evidence.get("sha256") != entry["sha256"]:
                raise AtlasError(f"tracked C# source hash changed: {path}")
            raw = evidence.get("_source_bytes")
            if not isinstance(raw, bytes):
                raise AtlasError(f"tracked C# source could not be read: {path}")
            try:
                file_texts[path] = (raw.decode("utf-8-sig"), str(entry["sha256"]))
            except UnicodeDecodeError as exc:
                raise AtlasError(f"tracked C# source is not UTF-8: {path}") from exc
    finally:
        os.close(root_fd)

    definition_path = method_source.get("path")
    if definition_path not in file_texts:
        raise AtlasError("saved method source is not present among verified tracked C# files")
    definition_span = method_source.get("span")
    if not isinstance(definition_span, dict):
        raise AtlasError("saved method declaration has no source span")
    definition_text, definition_hash = file_texts[str(definition_path)]
    start, end = definition_span.get("start_offset"), definition_span.get("end_offset")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or end > len(definition_text):
        raise AtlasError("saved method declaration span is invalid for its verified source")
    definition = {
        "fact_id": method.get("id"), "path": definition_path, "sha256": definition_hash,
        "span": definition_span, "text": definition_text[start:end],
    }

    from csharp_facts import lex
    # The input may name the declaring namespace, while C# calls commonly use
    # only the simple type name. Selection is declaration-aware; occurrence
    # matching remains explicitly lexical and therefore uses that simple name.
    type_parts = [str(owner.get("name"))]
    expected_values: list[str] = []
    for index, part in enumerate(type_parts):
        if index:
            expected_values.append(".")
        expected_values.append(part)
    expected_values.extend((".", method_name, "("))
    methods_by_path: dict[str, list[dict[str, object]]] = {}
    for fact in facts:
        if isinstance(fact, dict) and fact.get("kind") == "method_declaration":
            source = fact.get("source")
            if isinstance(source, dict) and isinstance(source.get("path"), str):
                methods_by_path.setdefault(source["path"], []).append(fact)
    candidates: list[dict[str, object]] = []
    for path, (text, source_hash) in file_texts.items():
        tokens, _directives = lex(text)
        for token_index in range(0, len(tokens) - len(expected_values) + 1):
            sequence = tokens[token_index:token_index + len(expected_values)]
            actual_values = [token.value.removeprefix("@") if expected_values[index] not in {".", "("} else token.value
                             for index, token in enumerate(sequence)]
            if actual_values != expected_values or any(token.kind != "identifier" for index, token in enumerate(sequence)
                                                       if expected_values[index] not in {".", "("}):
                continue
            first, opening = sequence[0], sequence[-1]
            containing = []
            for method_fact in methods_by_path.get(path, []):
                source = method_fact.get("source")
                span = source.get("span") if isinstance(source, dict) else None
                if isinstance(span, dict) and isinstance(span.get("start_offset"), int) and isinstance(span.get("end_offset"), int):
                    if span["start_offset"] <= first.start < span["end_offset"]:
                        containing.append(method_fact)
            containing_method = None
            if len(containing) == 1:
                containing_fact = containing[0]
                containing_owners = types_by_id.get(str(containing_fact.get("owner_type_id")), [])
                if len(containing_owners) == 1 and isinstance(containing_fact.get("method_name"), str):
                    containing_owner = containing_owners[0]
                    containing_type = ".".join(
                        part for part in (containing_owner.get("namespace"), containing_owner.get("name"))
                        if isinstance(part, str) and part
                    )
                    containing_method = f"{containing_type}.{containing_fact['method_name']}"
            candidates.append({
                "path": path, "sha256": source_hash,
                "span": {"start_offset": first.start, "end_offset": opening.end,
                         "offset_unit": "unicode_codepoint", "start_line": first.line,
                         "start_column": first.column, "end_line": opening.end_line,
                         "end_column": opening.end_column},
                "expression": f"{'.'.join(type_parts)}.{method_name}(",
                "containing_method": containing_method,
            })
    candidates.sort(key=lambda item: (os.fsencode(str(item["path"])), item["span"]["start_offset"]))
    document: dict[str, object] = {
        "result": "impact_view", "snapshot_id": snapshot["snapshot_id"],
        "extractor_identity": extractor_identity,
        "qualified_method_name": qualified_method_name,
        "scope": "Complete for the exact class-qualified Type.Member( lexical token pattern in verified tracked C# files; candidates are not compiler-resolved calls.",
        "limitations": ["Aliases, unqualified calls, and calls with another receiver spelling are not included.",
                        "A same-named type in another namespace may produce a lexical candidate.",
                        "Interpolated-string expressions are opaque to the current lexer and are not included.",
                        "Runtime binding, overload selection, reflection, and generated calls are not resolved.",
                        "Containing method is null when the saved method spans do not identify exactly one enclosing method."],
        "definition": definition, "candidate_count": len(candidates), "invocation_candidates": candidates,
        "budget": {"limit": max_bytes, "unit": "ASCII stdout bytes including newline; conservative byte proxy, not model tokens",
                   "stdout_bytes_including_newline": 0},
    }
    encoded = _impact_render(document, max_bytes)
    return document, encoded, 0


def _evidence_pack_render(document: dict[str, object], max_bytes: int) -> bytes:
    reported = int(document["budget"].get("stdout_bytes_including_newline", 0))
    for _ in range(20):
        document["budget"]["stdout_bytes_including_newline"] = reported
        encoded = (json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        actual = len(encoded)
        if actual == reported:
            if actual > max_bytes:
                raise AtlasError(f"complete mandatory evidence pack requires {actual} ASCII stdout bytes including newline; --max-tokens limit is {max_bytes}; stdout withheld")
            return encoded
        reported = actual
    raise AtlasError("evidence pack byte-count field did not stabilize; stdout withheld")


def evidence_pack(db_arg: str, repo_arg: str, route_fact_id: str, max_bytes: int,
                  snapshot_override: dict[str, object] | None = None) -> tuple[dict[str, object], bytes, int]:
    """Build a bounded candidate-only source packet for one discovered route fact."""
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    db_path = Path(db_arg).expanduser()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    live = _live_inventory_identity(repo_arg)
    from csharp_facts import EXTRACTION_METHOD
    extractor_identity = f"{EXTRACTION_METHOD}:python-stdlib-lexer"
    uri = db_path.absolute().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute("SELECT snapshot_id, payload_json FROM atlas_snapshots ORDER BY snapshot_id").fetchall()
    if snapshot_override is None:
        compatible: list[dict[str, object]] = []
        for _row_id, payload_json in rows:
            saved = json.loads(payload_json)
            graph = saved.get("source_graph") or {}
            if (saved.get("schema_version") == SCHEMA_VERSION and saved.get("inventory_basis") == INVENTORY_BASIS
                    and graph.get("extractor_identity") == extractor_identity):
                changed, reasons = _focus_source_identity(saved, live)
                if not changed and not reasons:
                    compatible.append(saved)
        if len(compatible) != 1:
            reason = "no_saved_snapshot_matches_current_extractor_and_checkout" if not compatible else "multiple_saved_snapshots_match_current_extractor_and_checkout"
            raise AtlasError(f"{reason}; compatible matching snapshots={len(compatible)}")
        snapshot = compatible[0]
    else:
        snapshot = snapshot_override
        if (snapshot.get("schema_version") != SCHEMA_VERSION or snapshot.get("inventory_basis") != INVENTORY_BASIS
                or (snapshot.get("source_graph") or {}).get("extractor_identity") != extractor_identity):
            raise AtlasError("explicit evidence-pack snapshot has an obsolete schema or extractor")
        if snapshot.get("repository_root") != live.get("repository_root"):
            raise AtlasError("explicit evidence-pack snapshot repository root does not match the live checkout")
    graph = snapshot["source_graph"]
    facts = graph.get("facts", [])
    unresolved = graph.get("unresolved", [])
    candidates = graph.get("candidates", [])
    route_facts = [f for f in facts if f.get("id") == route_fact_id and f.get("kind") == "route_action"]
    if len(route_facts) != 1:
        all_ids = [f for f in facts if f.get("id") == route_fact_id]
        if all_ids:
            raise AtlasError(f"route fact ID has wrong kind: {route_fact_id}")
        raise AtlasError(f"unknown route fact ID: {route_fact_id}")
    route = route_facts[0]
    method_matches = [f for f in facts if f.get("id") == route.get("action_id") and f.get("kind") == "method_declaration"]
    controller_matches = [f for f in facts if f.get("kind") == "type_declaration" and f.get("type_id") == route.get("controller_type_id")]
    if len(method_matches) != 1 or len(controller_matches) != 1:
        raise AtlasError("route root lacks one unambiguous saved action method and controller declaration")
    root_method, controller = method_matches[0], controller_matches[0]

    mandatory_refs: list[tuple[str, dict[str, object]]] = [
        (route["id"], route["source"]), (root_method["id"], root_method["source"]),
        (controller["id"], controller["source"]),
    ]
    if isinstance(route.get("controller_route_source"), dict):
        mandatory_refs.append((route["id"], route["controller_route_source"]))
    authorization = sorted((f for f in facts if f.get("kind") == "authorization_attribute"
                            and ((f.get("owner_type_id") == route.get("controller_type_id") and f.get("method_id") is None)
                                 or f.get("method_id") == root_method["id"])),
                           key=lambda f: (f.get("source", {}).get("path", ""), f.get("source", {}).get("span", {}).get("start_offset", 0), f["id"]))
    for fact in authorization:
        mandatory_refs.append((fact["id"], fact["source"]))

    method_by_id = {f["id"]: f for f in facts if f.get("kind") == "method_declaration"}
    injection_by_id = {f["id"]: f for f in facts if f.get("kind") == "constructor_injection"}
    registration_facts = [f for f in facts if f.get("kind") == "dependency_registration"]
    candidate_by_id = {c["id"]: c for c in candidates}
    fact_by_id = {fact["id"]: fact for fact in facts}
    invocation_facts = [f for f in facts if f.get("kind") == "receiver_invocation_syntax"]
    def invocations(method: dict[str, object], depth: int) -> list[dict[str, object]]:
        result = []
        calls = sorted((f for f in invocation_facts if f.get("method_id") == method["id"]),
                       key=lambda f: (f.get("source", {}).get("path", ""), f.get("source", {}).get("span", {}).get("start_offset", 0), f["id"]))
        for call in calls:
            call_candidates = [c for c in candidates if c.get("subject_fact_id") == call["id"] and c.get("expression_side") == "receiver_name"]
            related_unresolved = [u for u in unresolved if u.get("fact_id") == call["id"] or any(c.get("id") == u.get("candidate_id") for c in call_candidates)]
            injections = [injection_by_id[item] for candidate in call_candidates for item in candidate.get("candidate_fact_ids", []) if item in injection_by_id]
            for candidate in call_candidates:
                for injection_id in candidate.get("candidate_fact_ids", []):
                    injection = fact_by_id.get(injection_id)
                    if injection is None or injection.get("kind") != "constructor_injection":
                        raise AtlasError(f"saved receiver candidate {candidate['id']} contains missing or wrong-kind injection fact ID: {injection_id}")
            # Candidate injection IDs are retained as a set; no receiver candidate is treated as a binding.
            injections = sorted({i["id"]: i for i in injections}.values(), key=lambda f: f["id"])
            injection_evidence = []
            for injection in injections:
                regs = sorted((r for r in registration_facts if r.get("service_type_expression") == injection.get("type_expression")), key=lambda f: f["id"])
                reg_evidence = []
                for registration in regs:
                    type_candidates = [c for c in candidates if c.get("subject_fact_id") == registration["id"]
                                      and c.get("expression_side") == "implementation"]
                    declarations = []
                    for candidate in type_candidates:
                        for declaration_id in candidate.get("candidate_fact_ids", []):
                            declaration = fact_by_id.get(declaration_id)
                            if declaration is None or declaration.get("kind") != "type_declaration":
                                raise AtlasError(f"saved implementation candidate {candidate['id']} contains missing or wrong-kind declaration fact ID: {declaration_id}")
                            declarations.append((candidate, declaration))
                    declaration_evidence = []
                    for candidate, declaration in sorted(declarations, key=lambda pair: (pair[1]["id"], pair[0]["id"])):
                        methods = sorted((m for m in method_by_id.values() if m.get("owner_type_id") == declaration.get("type_id")
                                          and m.get("method_name") == call.get("member_name")), key=lambda f: f["id"])
                        method_evidence = []
                        for target_method in methods:
                            if depth < 2:
                                method_evidence.append({"method_fact_id": target_method["id"], "method_name": target_method["method_name"],
                                                        "source": target_method["source"], "invocations": invocations(target_method, depth + 1)})
                            else:
                                method_evidence.append({"method_fact_id": target_method["id"], "method_name": target_method["method_name"], "source": target_method["source"]})
                        declaration_evidence.append({"candidate_id": candidate["id"], "candidate_fact_ids": candidate.get("candidate_fact_ids", []),
                                                     "traversable": candidate.get("traversable"), "declaration_fact_id": declaration["id"],
                                                     "type_id": declaration.get("type_id"), "methods": method_evidence,
                                                     "method_match_count": len(methods)})
                    reg_evidence.append({"registration_fact_id": registration["id"], "source": registration["source"],
                                         "service_type_expression": registration.get("service_type_expression"),
                                         "implementation_type_expression": registration.get("implementation_type_expression"),
                                         "implementation_candidates": declaration_evidence,
                                         "registration_match_count": len(regs),
                                         "unresolved": [u for u in unresolved if u.get("fact_id") == registration["id"]
                                                        or any(c.get("id") == u.get("candidate_id") for c in type_candidates)]})
                injection_evidence.append({"injection_fact_id": injection["id"], "source": injection["source"],
                                           "type_expression": injection.get("type_expression"), "registrations": reg_evidence,
                                           "registration_match_count": len(regs)})
            result.append({"invocation_fact_id": call["id"], "member_name": call.get("member_name"), "receiver_name": call.get("receiver_name"),
                           "source": call["source"], "depth": depth, "receiver_candidates": [
                               {"candidate_id": c["id"], "traversable": c.get("traversable"), "candidate_fact_ids": c.get("candidate_fact_ids", []),
                                "match_basis": c.get("match_basis"), "unresolved": [u for u in related_unresolved if u.get("candidate_id") == c["id"]]}
                               for c in call_candidates], "injection_candidates": injection_evidence,
                           "candidate_bundle_count": len(injections), "unresolved": related_unresolved})
        return result

    root_calls = invocations(root_method, 1)
    root_unresolved = [u for u in unresolved if u.get("fact_id") in {route["id"], root_method["id"]}]
    repo_root = Path(live["repository_root"])
    mandatory_snippets = _source_texts(repo_root, mandatory_refs)
    def bundle_fact_ids(value: object) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("_fact_id") and isinstance(item, str):
                    found.add(item)
                elif key == "candidate_fact_ids" and isinstance(item, list):
                    found.update(x for x in item if isinstance(x, str))
                found.update(bundle_fact_ids(item))
        elif isinstance(value, list):
            for item in value:
                found.update(bundle_fact_ids(item))
        return found

    def bundle_snippets(bundle: dict[str, object]) -> list[dict[str, object]]:
        def validate_candidates(value: object) -> None:
            if isinstance(value, dict):
                candidate_id = value.get("candidate_id")
                if isinstance(candidate_id, str):
                    if candidate_id not in candidate_by_id:
                        raise AtlasError(f"candidate references unknown saved candidate ID: {candidate_id}")
                    saved_candidate = candidate_by_id[candidate_id]
                    if "candidate_fact_ids" in value:
                        if value.get("candidate_fact_ids") != saved_candidate.get("candidate_fact_ids", []):
                            raise AtlasError(f"saved candidate IDs changed while building evidence packet: {candidate_id}")
                        expected_kind = "constructor_injection" if saved_candidate.get("expression_side") == "receiver_name" else "type_declaration"
                        for target_id in saved_candidate.get("candidate_fact_ids", []):
                            target = fact_by_id.get(target_id)
                            if target is None or target.get("kind") != expected_kind:
                                raise AtlasError(f"saved candidate {candidate_id} contains missing or wrong-kind fact ID: {target_id}")
                for item in value.values():
                    validate_candidates(item)
            elif isinstance(value, list):
                for item in value:
                    validate_candidates(item)
        validate_candidates(bundle)
        fact_ids = bundle_fact_ids(bundle)
        missing = sorted(fact_id for fact_id in fact_ids if fact_id not in fact_by_id)
        if missing:
            raise AtlasError(f"candidate references unknown fact IDs: {', '.join(missing)}")
        refs = []
        for fact_id in sorted(fact_ids):
            fact = fact_by_id[fact_id]
            if not isinstance(fact.get("source"), dict):
                raise AtlasError(f"candidate fact has no saved source span: {fact_id}")
            refs.append((fact_id, fact["source"]))
        return _source_texts(repo_root, refs) if refs else []

    complete_bundles = [call for call in root_calls]
    selected_bundles: list[dict[str, object]] = []
    selected_snippets: dict[tuple[str, str, int, int, str], dict[str, object]] = {}
    document: dict[str, object] = {
        "result": "evidence_pack", "snapshot_id": snapshot["snapshot_id"], "extractor_identity": extractor_identity,
        "route": {"fact_id": route["id"], "http_method": route.get("http_method"), "route": route.get("route_literal"),
                  "action": route.get("action_name"), "controller_type_id": route.get("controller_type_id"),
                  "action_id": root_method["id"], "controller_fact_id": controller["id"],
                  "authorization_fact_ids": [f["id"] for f in authorization]},
        "root": {"action_method_fact_id": root_method["id"], "action_method_name": root_method.get("method_name"),
                 "controller_route_source": route.get("controller_route_source"), "authorization_fact_ids": [f["id"] for f in authorization],
                 "invocation_fact_ids": [call["invocation_fact_id"] for call in root_calls]},
        "source_snippets": mandatory_snippets,
        "candidate_bundles": selected_bundles,
        "candidate_snippets": [],
        "selection": {"included_candidate_bundles": 0, "omitted_candidate_bundles": len(complete_bundles),
                      "complete": not complete_bundles, "candidate_bundle_count": len(complete_bundles)},
        "graph_context": {"relevant_unresolved_count": len([u for u in unresolved if u.get("fact_id") == route["id"] or u.get("fact_id") == root_method["id"]]),
                          "root_unresolved": root_unresolved,
                          "limitations": graph.get("limitations", []), "traversal_note": "All cross-file relationships are lexical candidates; no receiver, registration, overload, or invocation is resolved."},
        "budget": {"limit": max_bytes, "unit": "ASCII stdout bytes, a conservative byte proxy; not measured model tokens or prompt overhead", "stdout_bytes_including_newline": 0}
    }
    encoded = _evidence_pack_render(document, max_bytes)
    for bundle in complete_bundles:
        for snippet in bundle_snippets(bundle):
            key = (snippet["path"], snippet["sha256"], snippet["span"]["start_offset"], snippet["span"]["end_offset"], snippet["fact_id"])
            selected_snippets[key] = snippet
        trial_bundles = [*selected_bundles, bundle]
        trial = dict(document)
        trial["candidate_bundles"] = trial_bundles
        trial["candidate_snippets"] = [selected_snippets[key] for key in sorted(selected_snippets, key=lambda item: (os.fsencode(item[0]), item[2], item[3], item[4]))]
        trial["selection"] = {"included_candidate_bundles": len(trial_bundles), "omitted_candidate_bundles": len(complete_bundles) - len(trial_bundles),
                              "complete": len(trial_bundles) == len(complete_bundles), "candidate_bundle_count": len(complete_bundles)}
        try:
            encoded = _evidence_pack_render(trial, max_bytes)
        except AtlasError:
            # Later bundles are deterministic; a bundle is never split or silently dropped.
            # Rebuild omitted counts from the retained complete prefix.
            break
        selected_bundles = trial_bundles
        document = trial
    document["selection"] = {"included_candidate_bundles": len(selected_bundles), "omitted_candidate_bundles": len(complete_bundles) - len(selected_bundles),
                             "complete": len(selected_bundles) == len(complete_bundles), "candidate_bundle_count": len(complete_bundles)}
    encoded = _evidence_pack_render(document, max_bytes)
    return document, encoded, 0


def route_refresh(db_arg: str, repo_arg: str, from_snapshot_id: str, route_fact_id: str,
                  max_bytes: int) -> tuple[dict[str, object], bytes, int]:
    """Carry one accepted route association onto a fresh same-root snapshot when its packet is unchanged."""
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    db_path = Path(db_arg).expanduser().absolute()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    try:
        uri = db_path.as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            snapshot_rows = connection.execute(
                "SELECT snapshot_id, payload_json FROM atlas_snapshots ORDER BY snapshot_id"
            ).fetchall()
    except sqlite3.Error as exc:
        raise AtlasError(f"cannot read route refresh origin: {exc}") from exc
    snapshots: dict[str, dict[str, object]] = {}
    for row_id, payload_json in snapshot_rows:
        try:
            value = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise AtlasError(f"saved snapshot JSON is corrupt: {row_id}") from exc
        if isinstance(value, dict) and value.get("snapshot_id") == row_id:
            snapshots[str(row_id)] = value
    origin = snapshots.get(from_snapshot_id)
    if origin is None:
        raise AtlasError(f"origin snapshot not found or corrupt: {from_snapshot_id}")
    _validate_snapshot_fingerprint(origin, from_snapshot_id)
    from csharp_facts import EXTRACTION_METHOD
    extractor_identity = f"{EXTRACTION_METHOD}:python-stdlib-lexer"
    origin_graph = origin.get("source_graph")
    if (origin.get("schema_version") != SCHEMA_VERSION or origin.get("inventory_basis") != INVENTORY_BASIS
            or not isinstance(origin_graph, dict) or origin_graph.get("extractor_identity") != extractor_identity):
        raise AtlasError("route refresh origin does not use the current snapshot schema and extractor")
    root = _repo_root(repo_arg)
    if origin.get("repository_root") != os.fspath(root):
        raise AtlasError("route refresh requires the same canonical repository root as the accepted origin")
    origin_routes = [fact for fact in origin_graph.get("facts", []) if fact.get("id") == route_fact_id]
    if len(origin_routes) != 1 or origin_routes[0].get("kind") != "route_action":
        raise AtlasError("route refresh requires one unique origin route_action fact")
    origin_associations = _validated_route_associations(db_arg, db_path, origin, snapshots).get(route_fact_id, [])
    if len(origin_associations) != 1:
        raise AtlasError(f"route refresh requires exactly one accepted association; found {len(origin_associations)}")
    association = origin_associations[0]
    if association.get("carry_provenance") is not None:
        raise AtlasError("route refresh pilot refuses to carry an already-carried association")
    binding = association["binding"]
    overlay_id = str(binding["overlay_id"])
    flow = query_flow(db_arg, from_snapshot_id, overlay_id)
    if flow.get("review_status") != "accepted":
        raise AtlasError("route refresh requires an accepted original flow review")

    target = capture(os.fspath(root))
    target_graph = target.get("source_graph")
    if (target.get("schema_version") != SCHEMA_VERSION or not isinstance(target_graph, dict)
            or target_graph.get("extractor_identity") != extractor_identity):
        raise AtlasError("captured refresh target does not use the current snapshot schema and extractor")
    if target.get("repository_root") != origin.get("repository_root"):
        raise AtlasError("captured refresh target repository root changed")
    target_routes = [fact for fact in target_graph.get("facts", []) if fact.get("id") == route_fact_id]
    if len(target_routes) != 1 or target_routes[0] != origin_routes[0]:
        raise AtlasError("route fact is missing, ambiguous, or changed in the target snapshot")

    old_packet, _, _ = evidence_pack(db_arg, os.fspath(root), route_fact_id, 2**31 - 1, snapshot_override=origin)
    new_packet, _, _ = evidence_pack(db_arg, os.fspath(root), route_fact_id, 2**31 - 1, snapshot_override=target)
    for label, packet in (("origin", old_packet), ("target", new_packet)):
        if (packet.get("selection", {}).get("complete") is not True
                or packet.get("selection", {}).get("omitted_candidate_bundles") != 0):
            raise AtlasError(f"route refresh {label} evidence packet is incomplete")
    old_content = {key: value for key, value in old_packet.items() if key not in {"snapshot_id", "budget"}}
    new_content = {key: value for key, value in new_packet.items() if key not in {"snapshot_id", "budget"}}
    if old_content != new_content:
        raise AtlasError("route refresh evidence packet changed; independent review is required")
    packet_sha256 = hashlib.sha256(_canonical_json(old_content)).hexdigest()

    origin_graph_facts = origin_graph.get("facts", [])
    target_graph_facts = target_graph.get("facts", [])
    citations: dict[str, dict[str, object]] = {}
    for claim in flow["overlay"].get("reviewed_conclusions", []):
        for citation in claim.get("evidence", []):
            fact_id = citation.get("fact_id")
            if not isinstance(fact_id, str):
                raise AtlasError("route refresh found a citation without a fact ID")
            citations[fact_id] = citation
    for fact_id, citation in citations.items():
        old_matches = [fact for fact in origin_graph_facts if fact.get("id") == fact_id]
        new_matches = [fact for fact in target_graph_facts if fact.get("id") == fact_id]
        if (len(old_matches) != 1 or len(new_matches) != 1 or old_matches[0] != new_matches[0]
                or citation.get("source") != old_matches[0].get("source")):
            raise AtlasError(f"route refresh citation fact is missing, ambiguous, or changed: {fact_id}")
    packet_fact_ids = {item["fact_id"] for packet in (old_packet, new_packet)
                       for field in ("source_snippets", "candidate_snippets") for item in packet.get(field, [])}
    if not set(citations).issubset(packet_fact_ids):
        raise AtlasError("route refresh citations must all occur in both complete evidence packets")
    if capture(os.fspath(root)).get("evidence_fingerprint") != target.get("evidence_fingerprint"):
        raise AtlasError("repository changed during route refresh; target capture is stale")

    target_snapshot_id = str(target["snapshot_id"])
    if target_snapshot_id == from_snapshot_id:
        raise AtlasError("route refresh requires a changed checkout; target equals the accepted origin")
    receipt_hash = str(flow["review_receipt"]["receipt_hash"])
    binding_hash = str(association["binding_hash"])
    review_hash = str(association["association_review_hash"])
    carry_values = (target_snapshot_id, route_fact_id, overlay_id, from_snapshot_id, overlay_id,
                    receipt_hash, binding_hash, review_hash, packet_sha256)
    target_payload = _canonical_json(target).decode("ascii")
    result = {
        "result": "carried", "snapshot_id": target_snapshot_id, "route_fact_id": route_fact_id,
        "overlay_id": overlay_id, "association": association, "carry_provenance": {
            "target_snapshot_id": target_snapshot_id, "origin_snapshot_id": from_snapshot_id,
            "origin_overlay_id": overlay_id, "origin_review_receipt_hash": receipt_hash,
            "origin_binding_hash": binding_hash, "origin_association_review_hash": review_hash,
            "packet_sha256": packet_sha256,
        },
        "budget": {"limit": max_bytes, "unit": "ASCII stdout bytes, a conservative byte proxy; not measured model tokens or prompt overhead",
                   "stdout_bytes_including_newline": 0},
    }
    encoded = _route_find_render(result, max_bytes)
    connection = _connect_for_index(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS atlas_snapshots (snapshot_id TEXT PRIMARY KEY, evidence_fingerprint TEXT NOT NULL UNIQUE, captured_at TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        existing = connection.execute(
            "SELECT evidence_fingerprint, payload_json FROM atlas_snapshots WHERE snapshot_id=?", (target_snapshot_id,)
        ).fetchone()
        if existing is not None:
            saved_target = json.loads(existing[1])
            if not isinstance(saved_target, dict):
                raise AtlasError("existing target snapshot payload is corrupt")
            _validate_snapshot_fingerprint(saved_target, target_snapshot_id)
            if existing[0] != target.get("evidence_fingerprint") or saved_target.get("evidence_fingerprint") != target.get("evidence_fingerprint"):
                raise AtlasError("target snapshot ID conflicts with existing evidence")
            target_payload = existing[1]
        else:
            connection.execute(
                "INSERT INTO atlas_snapshots(snapshot_id,evidence_fingerprint,captured_at,payload_json) VALUES (?,?,?,?)",
                (target_snapshot_id, target["evidence_fingerprint"], target["captured_at"], target_payload),
            )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS atlas_route_carries ("
            "target_snapshot_id TEXT NOT NULL, route_fact_id TEXT NOT NULL, overlay_id TEXT NOT NULL, "
            "origin_snapshot_id TEXT NOT NULL, origin_overlay_id TEXT NOT NULL, origin_receipt_hash TEXT NOT NULL, "
            "binding_hash TEXT NOT NULL, association_review_hash TEXT NOT NULL, packet_sha256 TEXT NOT NULL, "
            "PRIMARY KEY(target_snapshot_id,route_fact_id), "
            "FOREIGN KEY(target_snapshot_id) REFERENCES atlas_snapshots(snapshot_id))"
        )
        previous = connection.execute(
            "SELECT target_snapshot_id,route_fact_id,overlay_id,origin_snapshot_id,origin_overlay_id,origin_receipt_hash,binding_hash,association_review_hash,packet_sha256 "
            "FROM atlas_route_carries WHERE target_snapshot_id=? AND route_fact_id=?", (target_snapshot_id, route_fact_id)
        ).fetchone()
        if previous is not None and tuple(previous) != carry_values:
            raise AtlasError("route carry is immutable; a different origin already exists for this target route")
        if previous is None:
            connection.execute(
                "INSERT INTO atlas_route_carries(target_snapshot_id,route_fact_id,overlay_id,origin_snapshot_id,origin_overlay_id,origin_receipt_hash,binding_hash,association_review_hash,packet_sha256) "
                "VALUES (?,?,?,?,?,?,?,?,?)", carry_values,
            )
        if capture(os.fspath(root)).get("evidence_fingerprint") != target.get("evidence_fingerprint"):
            raise AtlasError("repository changed before route refresh commit; target capture is stale")
        connection.commit()
    except (sqlite3.Error, AtlasError):
        connection.rollback()
        raise
    finally:
        connection.close()
    return result, encoded, 0


def _focus_document(snapshot: dict[str, object], flow_result: dict[str, object], freshness: dict[str, object], max_bytes: int) -> tuple[dict[str, object], bytes]:
    overlay = flow_result["overlay"]
    all_claims = overlay["reviewed_conclusions"]
    def build(claims: list[dict[str, object]], byte_count: int) -> dict[str, object]:
        keys = sorted(
            {(citation["source"]["path"], citation["source"]["sha256"])
             for claim in claims for citation in claim["evidence"]},
            key=lambda item: (os.fsencode(item[0]), item[1]),
        )
        source_ids = {key: f"source-{index + 1}" for index, key in enumerate(keys)}
        selected = []
        for claim in claims:
            selected.append({
                "claim": claim["claim"],
                "evidence": [
                    {
                        "fact_id": citation["fact_id"],
                        "source_id": source_ids[(citation["source"]["path"], citation["source"]["sha256"])],
                        "span": citation["source"]["span"],
                    }
                    for citation in claim["evidence"]
                ],
            })
        reviewer = flow_result["review_receipt"]
        return {
            "result": "fresh",
            "snapshot_id": snapshot["snapshot_id"],
            "overlay_id": flow_result["overlay_id"],
            "extractor_identity": overlay["extractor_identity"],
            "review_status": flow_result["review_status"],
            "reviewer": {
                "identity": reviewer["reviewer_identity"],
                "model": reviewer["reviewer_model"],
                "decision": reviewer["decision"],
                "reviewed_at": reviewer["reviewed_at"],
            },
            **({"carry_provenance": flow_result["carry_provenance"]}
               if flow_result.get("carry_provenance") is not None else {}),
            "freshness": freshness,
            "claim_selection": {
                "total_claims": len(all_claims),
                "included_claims": len(selected),
                "omitted_claims": len(all_claims) - len(selected),
                "selection": "deterministic input order; complete claim units only",
            },
            "source_anchors": [
                {"source_id": source_ids[key], "path": key[0], "sha256": key[1]}
                for key in keys
            ],
            "claims": selected,
            "budget": {
                "limit": max_bytes,
                "unit": "ASCII stdout bytes, a conservative byte proxy; not measured model tokens or prompt overhead",
                "stdout_bytes_including_newline": byte_count,
            },
        }

    def render(value: dict[str, object]) -> bytes:
        return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")

    selected: list[dict[str, object]] = []
    current = build(selected, 0)
    encoded = render(current)
    actual = len(encoded)
    while current["budget"]["stdout_bytes_including_newline"] != actual:
        current = build(selected, actual)
        encoded = render(current)
        actual = len(encoded)
    if actual > max_bytes:
        raise AtlasError(f"required focus header needs {actual} ASCII bytes including newline; limit is {max_bytes}")

    for claim in all_claims:
        candidate = selected + [claim]
        trial = build(candidate, 0)
        trial_bytes = render(trial)
        length = len(trial_bytes)
        while trial["budget"]["stdout_bytes_including_newline"] != length:
            trial = build(candidate, length)
            trial_bytes = render(trial)
            length = len(trial_bytes)
        if length <= max_bytes:
            selected = candidate
            current, encoded = trial, trial_bytes

    # Finalize counts and the self-reported exact stdout byte count.
    current = build(selected, 0)
    encoded = render(current)
    length = len(encoded)
    while current["budget"]["stdout_bytes_including_newline"] != length:
        current = build(selected, length)
        encoded = render(current)
        length = len(encoded)
    if length > max_bytes:
        raise AtlasError(f"required focus header needs {length} ASCII bytes including newline; limit is {max_bytes}")
    return current, encoded


def focus(db_arg: str, repo_arg: str, snapshot_id: str, overlay_id: str, max_bytes: int) -> tuple[dict[str, object], bytes, int]:
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    db_path = Path(db_arg).expanduser()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    snapshot_result = query(db_arg, snapshot_id, None, include_graph=False)
    flow_result = query_flow(db_arg, snapshot_id, overlay_id)
    if flow_result["review_status"] != "accepted":
        raise AtlasError(f"reviewed-flow receipt is {flow_result['review_status']}; claims withheld")
    live = _live_inventory_identity(repo_arg)
    changed_paths, reasons = _focus_source_identity(snapshot_result, live)
    checked_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    freshness = {
        "checked_at": checked_at,
        "repository_root": live["repository_root"],
        "head": live["head"],
        "head_ref": live["head_ref"],
        "tracked_count": len(live["files"]),
        "structured_status": live["status"],
        "changed_paths": changed_paths,
        "reasons": reasons,
    }
    if changed_paths or reasons:
        stale = {
            "result": "stale_refused",
            "snapshot_id": snapshot_id,
            "overlay_id": overlay_id,
            "review_status": flow_result["review_status"],
            "freshness": freshness,
            "claims": [],
            "budget": {
                "unit": "ASCII stdout bytes, a conservative byte proxy; not measured model tokens or prompt overhead",
                "stdout_bytes_including_newline": 0,
            },
        }
        encoded = (json.dumps(stale, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        actual = len(encoded)
        while stale["budget"]["stdout_bytes_including_newline"] != actual:
            stale["budget"]["stdout_bytes_including_newline"] = actual
            encoded = (json.dumps(stale, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
            actual = len(encoded)
        if actual > max_bytes:
            raise AtlasError(
                f"complete stale diagnostic requires {actual} ASCII stdout bytes including newline; "
                f"--max-tokens limit is {max_bytes}; diagnostic and claims withheld"
            )
        return stale, encoded, 3
    snapshot = {
        "snapshot_id": snapshot_result["snapshot_id"],
        "files": snapshot_result["files"],
        "status": snapshot_result["status"],
        "repository_root": snapshot_result["repository_root"],
        "head": snapshot_result["head"],
        "head_ref": snapshot_result["head_ref"],
    }
    value, encoded = _focus_document(snapshot, flow_result, freshness, max_bytes)
    return value, encoded, 0


def answer_check(
    db_arg: str, repo_arg: str, snapshot_id: str, overlay_id: str,
    question_path: str, draft_path: str, review_path: str | None,
) -> tuple[dict[str, object] | None, bytes, int]:
    """Bind a human-readable answer review to one complete, fresh focus result."""
    # The saved maps fit well below this fixed safety ceiling. Any future larger map
    # fails closed through omitted_claims rather than producing a partial review packet.
    focused, _, status = focus(db_arg, repo_arg, snapshot_id, overlay_id, 1_000_000)
    if status != 0 or focused.get("result") != "fresh":
        raise AtlasError("answer-check requires a fresh accepted focus result")
    selection = focused.get("claim_selection", {})
    claims = focused.get("claims", [])
    if selection.get("omitted_claims") != 0 or selection.get("included_claims") != selection.get("total_claims"):
        raise AtlasError("answer-check requires every reviewed claim; focus omitted claims")

    try:
        question_bytes = Path(question_path).read_bytes()
        draft_bytes = Path(draft_path).read_bytes()
        question = question_bytes.decode("utf-8")
        draft = draft_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AtlasError("question and draft files must contain UTF-8 text") from exc

    flow = query_flow(db_arg, snapshot_id, overlay_id)
    binding = {
        "snapshot_id": focused["snapshot_id"],
        "extractor_identity": focused["extractor_identity"],
        "overlay_id": focused["overlay_id"],
        "overlay_content_hash": flow["overlay"]["content_hash"],
        "question_sha256": hashlib.sha256(question_bytes).hexdigest(),
        "draft_sha256": hashlib.sha256(draft_bytes).hexdigest(),
    }
    packet = {
        "result": "semantic_review_required",
        "binding": binding,
        "review_provenance": {
            "reviewer": focused["reviewer"],
            "review_receipt_hash": flow["review_receipt"]["receipt_hash"],
            "carry_provenance": focused.get("carry_provenance"),
        },
        "question": question,
        "draft": draft,
        "claims": [
            {"claim_number": index, "claim": item["claim"], "evidence": item["evidence"]}
            for index, item in enumerate(claims, start=1)
        ],
        "source_anchors": focused["source_anchors"],
        "review_instructions": (
            "Independently inspect every relevant subfact in every numbered claim against its cited spans. "
            "For each claim, decide whether it is relevant to the exact question. Mark relevant claims covered "
            "only when the draft includes every relevant supported subfact; mark irrelevant claims not_relevant. "
            "Also check that the draft adds no unsupported assertion. A bare 'used' or equivalent is not evidence "
            "of completeness."
        ),
    }
    packet_bytes = (json.dumps(packet, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if review_path is None:
        return packet, packet_bytes, 0

    try:
        review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AtlasError(f"cannot read answer review JSON: {exc}") from exc
    if not isinstance(review, dict) or review.get("packet_sha256") != hashlib.sha256(packet_bytes).hexdigest():
        raise AtlasError("answer review is stale or does not match this exact packet")
    if review.get("decision") != "accepted":
        raise AtlasError("answer review did not accept the draft")
    for field in ("reviewer_identity", "reviewer_model"):
        value = review.get(field)
        if not isinstance(value, str) or not value.strip():
            raise AtlasError(f"answer review requires nonempty {field} audit provenance")
    reviews = review.get("claim_reviews")
    if not isinstance(reviews, list) or len(reviews) != len(claims):
        raise AtlasError("answer review must contain one disposition for every numbered claim")
    for index, item in enumerate(reviews, start=1):
        if not isinstance(item, dict) or item.get("claim_number") != index:
            raise AtlasError(f"answer review disposition {index} is missing or out of order")
        if item.get("disposition") not in {"covered", "not_relevant"}:
            raise AtlasError(f"claim {index} disposition must be covered or not_relevant")
        basis = item.get("basis")
        if not isinstance(basis, str) or len(basis.strip()) < 20 or basis.strip().lower() in {"used", "reviewed", "complete", "not relevant"}:
            raise AtlasError(f"claim {index} needs a concrete review basis; a bare disposition does not establish completeness")
    return None, draft_bytes, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    index_parser = commands.add_parser("index", help="capture and durably save a tracked-file inventory")
    index_parser.add_argument("--repo", required=True)
    index_parser.add_argument("--db", required=True)
    query_parser = commands.add_parser("query", help="retrieve a saved inventory")
    query_parser.add_argument("--db", required=True)
    query_parser.add_argument("--snapshot", required=True)
    query_parser.add_argument("--path", help="return only this exact repository-relative path")
    query_parser.add_argument("--graph", action="store_true", help="include the saved source-fact graph")
    discover_parser = commands.add_parser("discover", help="rank source-anchored route candidates from a plain question's lexical terms")
    discover_parser.add_argument("--db", required=True)
    discover_parser.add_argument("--repo", required=True)
    discover_parser.add_argument("--terms", required=True, nargs="+", help="model-chosen lexical terms; no semantic selection is performed")
    discover_parser.add_argument("--max-tokens", required=True, type=int, help="maximum ASCII stdout bytes (conservative proxy, not model tokens)")
    evidence_parser = commands.add_parser("evidence-pack", help="assemble bounded, source-verified candidate evidence for one route fact")
    evidence_parser.add_argument("--db", required=True)
    evidence_parser.add_argument("--repo", required=True)
    evidence_parser.add_argument("--route-fact-id", required=True)
    evidence_parser.add_argument("--max-tokens", required=True, type=int, help="maximum ASCII stdout bytes (conservative proxy, not model tokens)")
    impact_parser = commands.add_parser("impact", help="show one saved method and exact class-qualified lexical invocation candidates")
    impact_parser.add_argument("--db", required=True)
    impact_parser.add_argument("--repo", required=True)
    impact_parser.add_argument("--method", required=True, help="saved method name as Type.Member or Namespace.Type.Member")
    impact_parser.add_argument("--max-tokens", required=True, type=int, help="maximum ASCII stdout bytes (conservative proxy, not model tokens)")
    refresh_parser = commands.add_parser("route-refresh", help="carry one accepted route review onto a same-root fresh snapshot when its full evidence packet is unchanged")
    refresh_parser.add_argument("--db", required=True)
    refresh_parser.add_argument("--repo", required=True)
    refresh_parser.add_argument("--from-snapshot", required=True)
    refresh_parser.add_argument("--route-fact-id", required=True)
    refresh_parser.add_argument("--max-tokens", required=True, type=int, help="maximum ASCII stdout bytes (conservative proxy, not model tokens)")
    flow_add_parser = commands.add_parser("flow-add", help="attach a reviewed, source-cited flow overlay")
    flow_add_parser.add_argument("--db", required=True)
    flow_add_parser.add_argument("--snapshot", required=True)
    flow_add_parser.add_argument("--input", required=True)
    flow_query_parser = commands.add_parser("flow-query", help="retrieve a reviewed flow overlay")
    flow_query_parser.add_argument("--db", required=True)
    flow_query_parser.add_argument("--snapshot", required=True)
    flow_query_parser.add_argument("--overlay", required=True)
    focus_parser = commands.add_parser("focus", help="retrieve an accepted reviewed flow only when its source snapshot is fresh")
    focus_parser.add_argument("--db", required=True)
    focus_parser.add_argument("--repo", required=True)
    focus_parser.add_argument("--snapshot", required=True)
    focus_parser.add_argument("--overlay", required=True)
    focus_parser.add_argument("--max-tokens", required=True, type=int, help="maximum ASCII stdout bytes (conservative proxy, not model tokens)")
    answer_parser = commands.add_parser("answer-check", help="prepare or verify an independent answer review against a complete fresh map")
    answer_parser.add_argument("--db", required=True)
    answer_parser.add_argument("--repo", required=True)
    answer_parser.add_argument("--snapshot", required=True)
    answer_parser.add_argument("--overlay", required=True)
    answer_parser.add_argument("--question-file", required=True)
    answer_parser.add_argument("--draft-file", required=True)
    answer_parser.add_argument("--review", help="optional independent review JSON; accepted review prints only the exact draft")
    review_parser = commands.add_parser("flow-review", help="attach one immutable review receipt to an exact overlay")
    review_parser.add_argument("--db", required=True)
    review_parser.add_argument("--snapshot", required=True)
    review_parser.add_argument("--overlay", required=True)
    review_parser.add_argument("--input", required=True)
    route_bind_parser = commands.add_parser("route-bind-add", help="attach an independently reviewed route-to-map association")
    route_bind_parser.add_argument("--db", required=True)
    route_bind_parser.add_argument("--snapshot", required=True)
    route_bind_parser.add_argument("--input", required=True)
    map_prepare_parser = commands.add_parser("route-map-prepare", help="bind a Luna route-map draft to one complete current evidence packet for independent review")
    map_prepare_parser.add_argument("--db", required=True)
    map_prepare_parser.add_argument("--repo", required=True)
    map_prepare_parser.add_argument("--route-fact-id", required=True)
    map_prepare_parser.add_argument("--draft-file", required=True)
    map_prepare_parser.add_argument("--max-tokens", required=True, type=int, help="maximum ASCII stdout bytes (conservative proxy, not model tokens)")
    map_review_parser = commands.add_parser("route-map-review", help="validate an independent route-map review without writing atlas records")
    map_review_parser.add_argument("--db", required=True)
    map_review_parser.add_argument("--repo", required=True)
    map_review_parser.add_argument("--packet-file", required=True)
    map_review_parser.add_argument("--review-file", required=True)
    map_publish_parser = commands.add_parser("route-map-publish", help="atomically publish an accepted one-route map, receipt, and route association")
    map_publish_parser.add_argument("--db", required=True)
    map_publish_parser.add_argument("--repo", required=True)
    map_publish_parser.add_argument("--packet-file", required=True)
    map_publish_parser.add_argument("--review-file", required=True)
    route_find_parser = commands.add_parser("route-find", help="find one fresh reviewed map for a discovered route fact")
    route_find_parser.add_argument("--db", required=True)
    route_find_parser.add_argument("--repo", required=True)
    route_find_parser.add_argument("--route-fact-id", required=True)
    route_find_parser.add_argument("--max-tokens", required=True, type=int, help="maximum ASCII stdout bytes (conservative proxy, not model tokens)")
    coverage_parser = commands.add_parser("coverage", help="page through saved route facts and their reviewed association state")
    coverage_parser.add_argument("--db", required=True)
    coverage_parser.add_argument("--repo", required=True)
    coverage_parser.add_argument("--max-tokens", required=True, type=int, help="maximum ASCII stdout bytes (conservative proxy, not model tokens)")
    coverage_parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        exit_code = 0
        encoded_output = None
        if args.command == "index":
            output = save(args.db, capture(args.repo))
        elif args.command == "query":
            output = query(args.db, args.snapshot, args.path, args.graph)
        elif args.command == "discover":
            output, encoded_output, exit_code = discover(args.db, args.repo, args.terms, args.max_tokens)
        elif args.command == "evidence-pack":
            output, encoded_output, exit_code = evidence_pack(args.db, args.repo, args.route_fact_id, args.max_tokens)
        elif args.command == "impact":
            output, encoded_output, exit_code = impact_view(args.db, args.repo, args.method, args.max_tokens)
        elif args.command == "route-refresh":
            output, encoded_output, exit_code = route_refresh(args.db, args.repo, args.from_snapshot, args.route_fact_id, args.max_tokens)
        elif args.command == "flow-add":
            output = attach_flow(args.db, args.snapshot, args.input)
        elif args.command == "flow-review":
            output = attach_review(args.db, args.snapshot, args.overlay, args.input)
        elif args.command == "route-bind-add":
            output = attach_route_binding(args.db, args.snapshot, args.input)
        elif args.command == "route-map-prepare":
            output, encoded_output, exit_code = route_map_prepare(
                args.db, args.repo, args.route_fact_id, args.draft_file, args.max_tokens,
            )
        elif args.command == "route-map-review":
            output, encoded_output, exit_code = route_map_review(
                args.db, args.repo, args.packet_file, args.review_file,
            )
        elif args.command == "route-map-publish":
            output = publish_route_map(args.db, args.repo, args.packet_file, args.review_file)
        elif args.command == "route-find":
            output, encoded_output, exit_code = route_find(args.db, args.repo, args.route_fact_id, args.max_tokens)
        elif args.command == "coverage":
            output, encoded_output, exit_code = route_coverage(args.db, args.repo, args.max_tokens, args.offset)
        elif args.command == "focus":
            output, encoded_output, exit_code = focus(args.db, args.repo, args.snapshot, args.overlay, args.max_tokens)
        elif args.command == "answer-check":
            output, encoded_output, exit_code = answer_check(args.db, args.repo, args.snapshot, args.overlay, args.question_file, args.draft_file, args.review)
        else:
            output = query_flow(args.db, args.snapshot, args.overlay)
    except (AtlasError, sqlite3.Error, OSError, json.JSONDecodeError) as exc:
        print(f"atlas: {exc}", file=sys.stderr)
        return 2
    if encoded_output is None:
        print(json.dumps(output, ensure_ascii=True, sort_keys=True, indent=2))
    else:
        sys.stdout.buffer.write(encoded_output)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
