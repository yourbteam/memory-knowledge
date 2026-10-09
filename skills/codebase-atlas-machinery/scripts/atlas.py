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
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile


SCHEMA_VERSION = 2
INVENTORY_BASIS = "git-index-paths+working-tree-bytes"
SOURCE_CALL_GRAPH_SCHEMA_VERSION = 2
SOURCE_CALL_GRAPH_CAPS = {
    "roots": 20_000,
    "nodes": 50_000,
    "edges": 250_000,
    "inspected_invocations": 500_000,
    "unsupported": 250_000,
    "nested_body_exclusions": 100_000,
    "serialized_graph_bytes": 134_217_728,
    "impact_witness_hops": 2_000_000,
    "traversal_work": 2_000_000,
    "interface_candidate_checks": 2_000_000,
    "compatibility_records": 2_000_000,
}
LEXICAL_METHOD_MANIFEST_SCHEMA_VERSION = 1
LEXICAL_METHOD_MANIFEST_MAX_METHODS = 250000
LEXICAL_METHOD_MANIFEST_MAX_BYTES = 67108864


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
    review_sha256: str | None = None,
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
    draft, draft_bytes = _route_map_draft(packet)
    expected_overlay_id = hashlib.sha256(_canonical_json(draft)).hexdigest()
    route_status, _route_bytes, _route_exit = route_find(db_arg, repo_arg, route_fact_id, 2**31 - 1)
    revision = packet.get("revision")
    if revision is None:
        if route_status.get("result") != "unmapped":
            existing_overlay = route_status.get("association", {}).get("binding", {}).get("overlay_id")
            if not (allow_existing_overlay_id is not None and route_status.get("result") == "fresh"
                    and existing_overlay == allow_existing_overlay_id):
                raise AtlasError("route-map workflow requires one open route with zero accepted associations")
    else:
        if not isinstance(revision, dict) or revision.get("revision_schema_version") != 1:
            raise AtlasError("route-map revision packet is malformed")
        predecessor = revision.get("predecessor")
        if not isinstance(predecessor, dict):
            raise AtlasError("route-map revision packet is missing its exact predecessor")
        required_predecessor = (
            "snapshot_id", "route_fact_id", "overlay_id", "flow_review_receipt_hash",
            "binding_hash", "association_review_hash", "binding", "association_review",
            "overlay", "review_receipt",
        )
        if any(field not in predecessor for field in required_predecessor):
            raise AtlasError("route-map revision predecessor is incomplete")
        if (predecessor.get("snapshot_id") != binding.get("snapshot_id")
                or predecessor.get("route_fact_id") != route_fact_id):
            raise AtlasError("route-map revision predecessor must be a direct association on this exact snapshot and route")
        prior_binding = predecessor.get("binding")
        prior_review = predecessor.get("association_review")
        if not isinstance(prior_binding, dict) or not isinstance(prior_review, dict):
            raise AtlasError("route-map revision predecessor binding and association review must be objects")
        prior_review_body = {key: value for key, value in prior_review.items()
                             if key != "association_review_hash"}
        if (hashlib.sha256(_canonical_json(prior_binding)).hexdigest() != predecessor.get("binding_hash")
                or hashlib.sha256(_canonical_json(prior_review_body)).hexdigest() != predecessor.get("association_review_hash")
                or prior_binding.get("snapshot_id") != predecessor.get("snapshot_id")
                or prior_binding.get("route_fact_id") != predecessor.get("route_fact_id")
                or prior_binding.get("overlay_id") != predecessor.get("overlay_id")
                or prior_binding.get("flow_review_receipt_hash") != predecessor.get("flow_review_receipt_hash")
                or prior_review.get("association_review_hash") != predecessor.get("association_review_hash")):
            raise AtlasError("route-map revision predecessor hashes do not match its exact binding and review")
        prior_flow = query_flow(db_arg, str(predecessor["snapshot_id"]), str(predecessor["overlay_id"]))
        if (prior_flow.get("review_status") != "accepted"
                or prior_flow.get("review_receipt", {}).get("receipt_hash") != predecessor.get("flow_review_receipt_hash")
                or prior_flow.get("overlay") != predecessor.get("overlay")
                or prior_flow.get("review_receipt") != predecessor.get("review_receipt")):
            raise AtlasError("route-map revision predecessor's accepted map or review changed")
        _validate_route_binding(prior_binding, snapshot, route_fact_id)
        _validate_route_association_review(prior_review_body, prior_binding, str(predecessor.get("binding_hash")))
        current_association = route_status.get("association") if route_status.get("result") == "fresh" else None
        predecessor_matches = (isinstance(current_association, dict)
            and "carry_provenance" not in current_association
            and current_association.get("binding", {}).get("snapshot_id") == predecessor.get("snapshot_id")
            and current_association.get("binding", {}).get("route_fact_id") == predecessor.get("route_fact_id")
            and current_association.get("binding", {}).get("overlay_id") == predecessor.get("overlay_id")
            and current_association.get("binding_hash") == predecessor.get("binding_hash")
            and current_association.get("association_review_hash") == predecessor.get("association_review_hash"))
        retry_matches = (allow_existing_overlay_id == expected_overlay_id
                         and route_status.get("result") == "fresh"
                         and route_status.get("association_count") == 1
                         and review_sha256 is not None
                         and _route_map_exact_supersession_exists(
                             Path(db_arg).expanduser().absolute(), revision, expected_overlay_id,
                             packet.get("packet_sha256"), review_sha256,
                         ))
        if not predecessor_matches and not retry_matches:
            raise AtlasError("route-map revision is stale: its exact predecessor is no longer the current direct route map")
        if predecessor_matches:
            if (current_association.get("binding") != predecessor.get("binding")
                    or current_association.get("association_review") != predecessor.get("association_review")):
                raise AtlasError("route-map revision predecessor binding or association review changed")
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


def _route_map_exact_supersession_exists(
    db_path: Path, revision: dict[str, object], successor_overlay_id: str,
    packet_sha256: object, review_sha256: object,
) -> bool:
    predecessor = revision.get("predecessor")
    if not isinstance(predecessor, dict):
        return False
    try:
        with sqlite3.connect(db_path.absolute().as_uri() + "?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM atlas_route_supersessions WHERE snapshot_id=? AND route_fact_id=? "
                "AND predecessor_overlay_id=? AND successor_overlay_id=?",
                (predecessor.get("snapshot_id"), predecessor.get("route_fact_id"),
                 predecessor.get("overlay_id"), successor_overlay_id),
            ).fetchone()
    except sqlite3.Error:
        return False
    if row is None:
        return False
    try:
        payload = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return False
    return (payload.get("packet_sha256") == packet_sha256
            and payload.get("review_sha256") == review_sha256
            and payload.get("predecessor_binding_hash") == predecessor.get("binding_hash")
            and payload.get("predecessor_association_review_hash") == predecessor.get("association_review_hash"))


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


def route_map_prepare(db_arg: str, repo_arg: str, route_fact_id: str, draft_path: str, max_bytes: int,
                      revise: bool = False) -> tuple[dict[str, object], bytes, int]:
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    route_status, _route_bytes, _route_exit = route_find(db_arg, repo_arg, route_fact_id, 2**31 - 1)
    if revise:
        if route_status.get("result") != "fresh":
            raise AtlasError("route-map revision requires exactly one current reviewed route map")
        current = route_status.get("association")
        if not isinstance(current, dict) or "carry_provenance" in current:
            raise AtlasError("route-map revision requires a same-snapshot direct predecessor; carried maps cannot be revised")
        binding = current.get("binding")
        if not isinstance(binding, dict) or binding.get("snapshot_id") != route_status.get("snapshot_id"):
            raise AtlasError("route-map revision requires a same-snapshot direct predecessor")
        flow = query_flow(db_arg, str(binding["snapshot_id"]), str(binding["overlay_id"]))
        if flow.get("review_status") != "accepted":
            raise AtlasError("route-map revision predecessor must have an accepted flow review")
        revision = {
            "revision_schema_version": 1,
            "predecessor": {
                "snapshot_id": binding["snapshot_id"], "route_fact_id": route_fact_id,
                "overlay_id": binding["overlay_id"],
                "flow_review_receipt_hash": binding["flow_review_receipt_hash"],
                "binding_hash": current["binding_hash"],
                "association_review_hash": current["association_review_hash"],
                "binding": binding, "association_review": current["association_review"],
                "overlay": flow["overlay"], "review_receipt": flow["review_receipt"],
            },
        }
    elif route_status.get("result") != "unmapped":
        raise AtlasError("route-map prepare requires one open route with zero accepted associations")
    else:
        revision = None
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
    if revision is not None:
        packet["revision"] = revision
        packet["review_instructions"] += (
            " This is a revision of the exact predecessor included above. Review that predecessor's map, "
            "flow receipt, route binding, and association review as immutable context; assess the successor "
            "against the new complete evidence and do not imply that the predecessor record was replaced."
        )
    packet["packet_sha256"] = _route_map_packet_digest(packet)
    encoded = _canonical_json(packet) + b"\n"
    if len(encoded) > max_bytes:
        raise AtlasError(f"complete route-map review packet requires {len(encoded)} ASCII stdout bytes including newline; --max-tokens limit is {max_bytes}; stdout withheld")
    return packet, encoded, 0


def route_map_review(db_arg: str, repo_arg: str, packet_path: str, review_path: str) -> tuple[dict[str, object], bytes, int]:
    packet, _packet_bytes = _read_json_file(packet_path, "route-map packet")
    review, _review_bytes = _read_json_file(review_path, "route-map independent review")
    _route_map_validate_packet(
        packet, db_arg, repo_arg,
        review_sha256=hashlib.sha256(_canonical_json(review)).hexdigest(),
    )
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
            review_sha256=hashlib.sha256(_canonical_json(review)).hexdigest(),
        )
        binding_info = packet["binding"]
        snapshot_id = str(binding_info["snapshot_id"])
        extractor_identity = str(binding_info["extractor_identity"])
        route_fact_id = str(binding_info["route_fact_id"])
        overlay_id = hashlib.sha256(_canonical_json(draft)).hexdigest()
        overlay_payload = {**draft, "content_hash": overlay_id}
        overlay_json = _canonical_json(overlay_payload).decode("ascii")
        route_map_review_sha256 = hashlib.sha256(_canonical_json(review)).hexdigest()
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
        revision = packet.get("revision")
        if revision is not None:
            predecessor = revision.get("predecessor") if isinstance(revision, dict) else None
            if not isinstance(predecessor, dict):
                raise AtlasError("route-map revision packet is missing its exact predecessor")
            receipt["route_map_review_sha256"] = route_map_review_sha256
            receipt["revision"] = {
                "revision_schema_version": 1,
                "predecessor_snapshot_id": predecessor["snapshot_id"],
                "predecessor_route_fact_id": predecessor["route_fact_id"],
                "predecessor_overlay_id": predecessor["overlay_id"],
                "predecessor_flow_review_receipt_hash": predecessor["flow_review_receipt_hash"],
                "predecessor_binding_hash": predecessor["binding_hash"],
                "predecessor_association_review_hash": predecessor["association_review_hash"],
                "packet_sha256": packet["packet_sha256"],
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
        supersession = None
        supersession_json = None
        supersession_hash = None
        if revision is not None:
            predecessor = revision.get("predecessor") if isinstance(revision, dict) else None
            if not isinstance(predecessor, dict):
                raise AtlasError("route-map revision packet is missing its exact predecessor")
            supersession = {
                "supersession_schema_version": 1, "snapshot_id": snapshot_id,
                "route_fact_id": route_fact_id,
                "predecessor_overlay_id": predecessor["overlay_id"],
                "successor_overlay_id": overlay_id,
                "predecessor_binding_hash": predecessor["binding_hash"],
                "predecessor_association_review_hash": predecessor["association_review_hash"],
                "predecessor_flow_review_receipt_hash": predecessor["flow_review_receipt_hash"],
                "successor_binding_hash": binding_hash,
                "successor_association_review_hash": association_hash,
                "successor_flow_review_receipt_hash": receipt_hash,
                "packet_sha256": packet["packet_sha256"],
                "review_sha256": route_map_review_sha256,
            }
            supersession_hash = hashlib.sha256(_canonical_json(supersession)).hexdigest()
            supersession_json = _canonical_json(supersession).decode("ascii")

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
        if supersession is not None:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS atlas_route_supersessions ("
                "snapshot_id TEXT NOT NULL, route_fact_id TEXT NOT NULL, predecessor_overlay_id TEXT NOT NULL, "
                "successor_overlay_id TEXT NOT NULL, edge_hash TEXT NOT NULL, payload_json TEXT NOT NULL, "
                "PRIMARY KEY(snapshot_id, route_fact_id, predecessor_overlay_id), "
                "UNIQUE(snapshot_id, route_fact_id, successor_overlay_id))"
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
        previous_supersession = None
        if supersession is not None:
            previous_supersession = connection.execute(
                "SELECT edge_hash,payload_json FROM atlas_route_supersessions WHERE snapshot_id=? AND route_fact_id=? "
                "AND predecessor_overlay_id=?",
                (snapshot_id, route_fact_id, supersession["predecessor_overlay_id"]),
            ).fetchone()
        expected_binding_row = (binding_hash, association_hash, association_json)
        if previous_overlay is not None and previous_overlay[0] != overlay_json:
            raise AtlasError("reviewed-flow overlay is immutable; conflicting bytes already exist")
        if previous_receipt is not None and previous_receipt != (receipt_hash, receipt_json):
            raise AtlasError("review receipt is immutable; a conflicting decision already exists")
        if previous_binding is not None and previous_binding != expected_binding_row:
            raise AtlasError("route binding is immutable; a conflicting association review already exists")
        if previous_supersession is not None and previous_supersession != (supersession_hash, supersession_json):
            raise AtlasError("route-map predecessor was already revised by a different packet or review")
        if supersession is not None and previous_supersession is None:
            existing_source = connection.execute(
                "SELECT 1 FROM atlas_route_supersessions WHERE snapshot_id=? AND route_fact_id=? AND predecessor_overlay_id=?",
                (snapshot_id, route_fact_id, supersession["predecessor_overlay_id"]),
            ).fetchone()
            existing_target = connection.execute(
                "SELECT 1 FROM atlas_route_supersessions WHERE snapshot_id=? AND route_fact_id=? AND successor_overlay_id=?",
                (snapshot_id, route_fact_id, overlay_id),
            ).fetchone()
            if existing_source is not None or existing_target is not None:
                raise AtlasError("route-map revision would fork or merge immutable supersession history")
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
        if supersession is not None and previous_supersession is None:
            connection.execute(
                "INSERT INTO atlas_route_supersessions(snapshot_id,route_fact_id,predecessor_overlay_id,successor_overlay_id,edge_hash,payload_json) "
                "VALUES (?,?,?,?,?,?)",
                (snapshot_id, route_fact_id, supersession["predecessor_overlay_id"], overlay_id,
                 supersession_hash, supersession_json),
            )
        # Recheck after all writes, immediately before commit. The SQLite transaction
        # rolls back if the checkout or evidence changed while records were assembled.
        _route_map_validate_packet(
            packet, db_arg, repo_arg, allow_existing_overlay_id=overlay_id,
            review_sha256=route_map_review_sha256,
        )
        if supersession is not None:
            successor_flow_row = connection.execute(
                "SELECT payload_json FROM atlas_reviewed_flows WHERE snapshot_id=? AND content_hash=?",
                (snapshot_id, overlay_id),
            ).fetchone()
            successor_receipt_row = connection.execute(
                "SELECT receipt_hash,receipt_json FROM atlas_flow_reviews WHERE snapshot_id=? AND overlay_id=?",
                (snapshot_id, overlay_id),
            ).fetchone()
            successor_binding_row = connection.execute(
                "SELECT binding_hash,association_review_hash,payload_json FROM atlas_route_bindings "
                "WHERE snapshot_id=? AND route_fact_id=? AND overlay_id=?",
                (snapshot_id, route_fact_id, overlay_id),
            ).fetchone()
            predecessor = revision["predecessor"]
            predecessor_binding_row = connection.execute(
                "SELECT binding_hash,association_review_hash,payload_json FROM atlas_route_bindings "
                "WHERE snapshot_id=? AND route_fact_id=? AND overlay_id=?",
                (snapshot_id, route_fact_id, predecessor["overlay_id"]),
            ).fetchone()
            predecessor_receipt_row = connection.execute(
                "SELECT receipt_hash,receipt_json FROM atlas_flow_reviews WHERE snapshot_id=? AND overlay_id=?",
                (snapshot_id, predecessor["overlay_id"]),
            ).fetchone()
            edge_row = connection.execute(
                "SELECT edge_hash,payload_json FROM atlas_route_supersessions WHERE snapshot_id=? AND route_fact_id=? "
                "AND predecessor_overlay_id=? AND successor_overlay_id=?",
                (snapshot_id, route_fact_id, supersession["predecessor_overlay_id"], overlay_id),
            ).fetchone()
            source_edge = connection.execute(
                "SELECT COUNT(*) FROM atlas_route_supersessions WHERE snapshot_id=? AND route_fact_id=? AND predecessor_overlay_id=?",
                (snapshot_id, route_fact_id, supersession["predecessor_overlay_id"]),
            ).fetchone()[0]
            target_edge = connection.execute(
                "SELECT COUNT(*) FROM atlas_route_supersessions WHERE snapshot_id=? AND route_fact_id=? AND successor_overlay_id=?",
                (snapshot_id, route_fact_id, overlay_id),
            ).fetchone()[0]
            if (successor_flow_row != (overlay_json,)
                    or successor_receipt_row != (receipt_hash, receipt_json)
                    or successor_binding_row != expected_binding_row
                    or predecessor_binding_row is None
                    or predecessor_binding_row[0] != predecessor["binding_hash"]
                    or predecessor_binding_row[1] != predecessor["association_review_hash"]
                    or predecessor_binding_row[2] != _canonical_json({
                        "binding": predecessor["binding"],
                        "binding_hash": predecessor["binding_hash"],
                        "association_review": predecessor["association_review"],
                    }).decode("ascii")
                    or predecessor_receipt_row is None
                    or predecessor_receipt_row[0] != predecessor["flow_review_receipt_hash"]
                    or predecessor_receipt_row[1] != _canonical_json(predecessor["review_receipt"]).decode("ascii")
                    or edge_row != (supersession_hash, supersession_json)
                    or source_edge != 1 or target_edge != 1):
                raise AtlasError("prospective route-map revision is not one validated leaf on the writer connection")
        connection.commit()
        return {"result": "published", "snapshot_id": snapshot_id, "route_fact_id": route_fact_id,
                "overlay_id": overlay_id, "receipt_hash": receipt_hash, "binding_hash": binding_hash,
                "association_review_hash": association_hash, "packet_sha256": packet["packet_sha256"],
                "evidence_sha256": packet["evidence_sha256"], "idempotent": all(
                    row is not None for row in (previous_overlay, previous_receipt, previous_binding))
                and (supersession is None or previous_supersession is not None)}
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
    direct_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    direct_receipts: dict[tuple[str, str, str], dict[str, object]] = {}
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
        validated = {"binding": binding, "binding_hash": binding_hash,
                     "association_review": review_payload, "association_review_hash": review_hash}
        direct_by_key[(str(row_snapshot_id), str(row_route_fact_id), str(row_overlay_id))] = validated
        direct_receipts[(str(row_snapshot_id), str(row_route_fact_id), str(row_overlay_id))] = flow["review_receipt"]
        if row_snapshot_id == snapshot["snapshot_id"]:
            associations.setdefault(str(row_route_fact_id), []).append(validated)

    # A supersession row is accepted only when it links two fully validated direct
    # associations and its own immutable payload agrees with every registry key.
    superseded: set[tuple[str, str, str]] = set()
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='atlas_route_supersessions'"
            ).fetchone()
            edge_rows = [] if exists is None else connection.execute(
                "SELECT snapshot_id, route_fact_id, predecessor_overlay_id, successor_overlay_id, "
                "edge_hash, payload_json FROM atlas_route_supersessions "
                "ORDER BY snapshot_id, route_fact_id, predecessor_overlay_id"
            ).fetchall()
    except sqlite3.Error as exc:
        raise AtlasError(f"cannot query route-map supersession history: {exc}") from exc
    outgoing: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    incoming: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    edges_by_route: dict[tuple[str, str], list[tuple[tuple[str, str, str], tuple[str, str, str]]]] = {}
    for row_snapshot, row_route, predecessor, successor, edge_hash, payload_json in edge_rows:
        try:
            payload = json.loads(payload_json)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AtlasError("saved route-map supersession payload is corrupt") from exc
        key_fields = {"snapshot_id": row_snapshot, "route_fact_id": row_route,
                      "predecessor_overlay_id": predecessor, "successor_overlay_id": successor}
        if (not isinstance(payload, dict) or any(payload.get(key) != value for key, value in key_fields.items())
                or payload.get("supersession_schema_version") != 1 or "edge_hash" in payload):
            raise AtlasError("saved route-map supersession payload does not match its registry key")
        computed_edge_hash = hashlib.sha256(_canonical_json(payload)).hexdigest()
        if computed_edge_hash != edge_hash:
            raise AtlasError("saved route-map supersession integrity hash is invalid")
        source_key = (str(row_snapshot), str(row_route), str(predecessor))
        target_key = (str(row_snapshot), str(row_route), str(successor))
        if source_key == target_key:
            raise AtlasError("route-map supersession cannot point to itself")
        source = direct_by_key.get(source_key)
        target = direct_by_key.get(target_key)
        predecessor_receipt = direct_receipts.get(source_key)
        successor_receipt = direct_receipts.get(target_key)
        if source is None or target is None:
            raise AtlasError("route-map supersession has a dangling predecessor or successor")
        if not isinstance(predecessor_receipt, dict) or not isinstance(successor_receipt, dict):
            raise AtlasError("route-map supersession accepted receipt is missing")
        for edge_field, assoc, hash_field in (
            ("predecessor_binding_hash", source, "binding_hash"),
            ("predecessor_association_review_hash", source, "association_review_hash"),
            ("successor_binding_hash", target, "binding_hash"),
            ("successor_association_review_hash", target, "association_review_hash"),
        ):
            if payload.get(edge_field) != assoc.get(hash_field):
                raise AtlasError(f"route-map supersession {edge_field} does not match its association")
        if (payload.get("predecessor_flow_review_receipt_hash") != predecessor_receipt.get("receipt_hash")
                or payload.get("successor_flow_review_receipt_hash") != successor_receipt.get("receipt_hash")
                or payload.get("packet_sha256") != successor_receipt.get("packet_sha256")
                or payload.get("review_sha256") != successor_receipt.get("route_map_review_sha256")):
            raise AtlasError("route-map supersession packet or accepted receipt provenance does not match its endpoints")
        expected_revision_identity = {
            "revision_schema_version": 1,
            "predecessor_snapshot_id": row_snapshot,
            "predecessor_route_fact_id": row_route,
            "predecessor_overlay_id": predecessor,
            "predecessor_flow_review_receipt_hash": predecessor_receipt.get("receipt_hash"),
            "predecessor_binding_hash": source.get("binding_hash"),
            "predecessor_association_review_hash": source.get("association_review_hash"),
            "packet_sha256": payload.get("packet_sha256"),
        }
        if successor_receipt.get("revision") != expected_revision_identity:
            raise AtlasError("successor accepted review receipt does not preserve its exact revision identity")
        if source_key in outgoing:
            raise AtlasError("route-map supersession history forks from one predecessor")
        if target_key in incoming:
            raise AtlasError("route-map supersession history merges into one successor")
        outgoing[source_key] = target_key
        incoming[target_key] = source_key
        superseded.add(source_key)
        edges_by_route.setdefault((str(row_snapshot), str(row_route)), []).append((source_key, target_key))
    for route_edges in edges_by_route.values():
        for start, _target in route_edges:
            visited: set[tuple[str, str, str]] = set()
            node = start
            while node in outgoing:
                if node in visited:
                    raise AtlasError("route-map supersession history contains a cycle")
                visited.add(node)
                node = outgoing[node]
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
    return {route_id: [association for association in values
                       if ("carry_provenance" in association
                           or (str(association["binding"]["snapshot_id"]), route_id,
                               str(association["binding"]["overlay_id"])) not in superseded)]
            for route_id, values in associations.items()}


def route_find(
    db_arg: str,
    repo_arg: str,
    route_fact_id: str | None,
    max_bytes: int,
    http_method: str | None = None,
    route_literal: str | None = None,
) -> tuple[dict[str, object], bytes, int]:
    if max_bytes < 1:
        raise AtlasError("--max-tokens must be a positive integer")
    has_id = route_fact_id is not None
    has_method = http_method is not None
    has_route = route_literal is not None
    if has_id and (has_method or has_route):
        raise AtlasError("choose either --route-fact-id ID or both --http-method METHOD and --route LITERAL; do not mix selectors")
    if not has_id and not (has_method and has_route):
        raise AtlasError("route-find requires --route-fact-id ID or both --http-method METHOD and --route LITERAL")
    if has_id and route_fact_id == "":
        raise AtlasError("--route-fact-id must not be empty")
    if has_method and http_method == "":
        raise AtlasError("--http-method must not be empty")
    if has_route and route_literal == "":
        raise AtlasError("--route must not be empty")
    db_path = Path(db_arg).expanduser()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    snapshot, snapshots_by_id, extractor_identity, live = _current_route_snapshot(db_path, repo_arg)
    graph = snapshot["source_graph"]
    if not has_id:
        facts = graph.get("facts")
        if not isinstance(facts, list) or any(not isinstance(fact, dict) for fact in facts):
            raise AtlasError("saved source graph facts must be a list of objects for exact route selection")
        exact_matches = [fact for fact in facts
                         if fact.get("kind") == "route_action"
                         and fact.get("http_method") == http_method
                         and fact.get("route_literal") == route_literal]
        if not exact_matches:
            raise AtlasError(
                f"no route_action matches the exact saved method and route: {http_method!r} {route_literal!r}; "
                "check the current coverage output for saved values"
            )
        if len(exact_matches) != 1:
            raise AtlasError(
                f"{len(exact_matches)} route_action facts match the exact saved method and route: "
                f"{http_method!r} {route_literal!r}; use --route-fact-id with a reviewed unique route"
            )
        route_fact_id = exact_matches[0].get("id")
        if not isinstance(route_fact_id, str) or not route_fact_id:
            raise AtlasError("exact route match has an invalid route fact ID; repair the saved snapshot")
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


def _compiler_safe_tree(root: Path, relative_root: str) -> list[dict[str, object]]:
    """Hash a generated input tree without following links or special files."""
    base = root / relative_root
    if not base.exists():
        return []
    if base.is_symlink() or not base.is_dir():
        raise AtlasError(f"unsafe compiler input tree {relative_root!r}: expected a real directory")
    result: list[dict[str, object]] = []
    for directory, directories, filenames in os.walk(base, followlinks=False):
        current = Path(directory)
        for name in sorted(directories, key=os.fsencode):
            path = current / name
            if path.is_symlink():
                raise AtlasError(f"unsafe compiler input tree {relative_root!r}: symlink directory {path.relative_to(root)}")
        for name in sorted(filenames, key=os.fsencode):
            path = current / name
            if path.is_symlink() or not path.is_file():
                raise AtlasError(f"unsafe compiler input tree {relative_root!r}: non-regular file {path.relative_to(root)}")
            relative = path.relative_to(root).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result.append({"logical_path": relative, "sha256": digest, "size_bytes": path.stat().st_size})
    return sorted(result, key=lambda item: os.fsencode(str(item["logical_path"])))


def _compiler_temp_env(temp_root: Path, dotnet: Path, package_cache: Path) -> dict[str, str]:
    env = dict(os.environ)
    sdk_version = subprocess.run([str(dotnet), "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, check=False).stdout.strip()
    sdk_dir = dotnet.parent / "sdk" / sdk_version if sdk_version else None
    env.update({
        "DOTNET_ROOT": str(dotnet.parent), "DOTNET_CLI_HOME": str(temp_root / "dotnet-home"),
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_NOLOGO": "1", "NUGET_PACKAGES": str(package_cache),
        "NUGET_HTTP_CACHE_PATH": str(temp_root / "nuget-http-cache"),
        "RestoreIgnoreFailedSources": "true",
        "DOTNET_HOST_PATH": str(dotnet),
    })
    if sdk_dir is not None and (sdk_dir / "MSBuild.dll").is_file():
        env["MSBUILD_EXE_PATH"] = str(sdk_dir / "MSBuild.dll")
        env["MSBuildSDKsPath"] = str(sdk_dir / "Sdks")
    return env


def _compiler_copy_inputs(root: Path, snapshot: dict[str, object], mirror: Path,
                          generated_relative: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    files = snapshot.get("files")
    if not isinstance(files, list):
        raise AtlasError("current compiler snapshot has invalid tracked-file inventory")
    tracked_manifest: list[dict[str, object]] = []
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for entry in files:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise AtlasError("current compiler snapshot contains an invalid tracked-file entry")
            path = str(entry["path"])
            evidence = _read_working_file(root_fd, path, collect_source=True)
            if evidence.get("presence") != entry.get("presence") or evidence.get("type") != entry.get("type") or evidence.get("sha256") != entry.get("sha256"):
                raise AtlasError(f"tracked compiler input changed since snapshot: {path}; re-index before compiler-index")
            tracked_manifest.append({"logical_path": f"tracked/{path}", "path": path,
                                     "sha256": entry.get("sha256"), "size_bytes": entry.get("size_bytes"),
                                     "presence": entry.get("presence"), "type": entry.get("type"),
                                     "git_mode": entry.get("git_mode")})
            if entry.get("presence") != "present":
                continue
            if entry.get("type") != "file":
                raise AtlasError(f"compiler input is not a regular tracked file: {path}")
            raw = evidence.get("_source_bytes")
            if not isinstance(raw, bytes):
                raise AtlasError(f"tracked compiler input could not be read: {path}")
            destination = mirror / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    finally:
        os.close(root_fd)
    generated_source = root / generated_relative
    generated_manifest = _compiler_safe_tree(root, generated_relative)
    if generated_manifest:
        for item in generated_manifest:
            relative = str(item["logical_path"])
            destination = mirror / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / relative, destination)
    return tracked_manifest, generated_manifest


def _compiler_span(source: object) -> tuple[str, int, int] | None:
    if not isinstance(source, dict) or not isinstance(source.get("path"), str):
        return None
    span = source.get("span")
    if not isinstance(span, dict):
        return None
    start, end = span.get("start_offset"), span.get("end_offset")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
        return None
    return str(source["path"]), start, end


def _compiler_shipped_tool_inputs() -> list[dict[str, object]]:
    source = Path(__file__).resolve().parent / "compiler"
    result = []
    for name in ("WorkspaceProgram.cs", "extractor.csproj"):
        path = source / name
        if not path.is_file():
            raise AtlasError(f"shipped Roslyn compiler extractor source is incomplete: {path}")
        result.append({"logical_path": f"atlas-compiler/{name}", "path": path.as_posix(),
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def _compiler_lexical_method_manifest(snapshot: dict[str, object], extractor_identity: str) -> dict[str, object]:
    """Build the bounded canonical declaration allowlist from the saved lexical snapshot."""
    source_graph = snapshot.get("source_graph")
    facts = source_graph.get("facts") if isinstance(source_graph, dict) else None
    if (not isinstance(facts, list) or not isinstance(extractor_identity, str) or not extractor_identity
            or not isinstance(source_graph, dict) or source_graph.get("extractor_identity") != extractor_identity):
        raise AtlasError("compiler lexical method manifest has no verified saved source facts")
    methods = []
    identities: set[tuple[object, ...]] = set()
    fact_ids: set[str] = set()
    for fact in facts:
        if not isinstance(fact, dict) or fact.get("kind") != "method_declaration":
            continue
        fact_id, name, source = fact.get("id"), fact.get("method_name"), fact.get("source")
        span = _compiler_span(source)
        if (not isinstance(fact_id, str) or not fact_id or not isinstance(name, str) or not name
                or span is None or not isinstance(source, dict) or not isinstance(source.get("sha256"), str)
                or not source.get("sha256")):
            raise AtlasError("compiler lexical method manifest contains an incomplete saved method fact")
        identity = (name, span[0], source["sha256"], span[1], span[2])
        if fact_id in fact_ids or identity in identities:
            raise AtlasError("compiler lexical method manifest contains duplicate saved method identities")
        fact_ids.add(fact_id); identities.add(identity)
        methods.append({"fact_id": fact_id, "method_name": name, "source": {
            "path": span[0], "sha256": source["sha256"], "span": {
                "start_offset": span[1], "end_offset": span[2], "offset_unit": "unicode_codepoint"}}})
        if len(methods) > LEXICAL_METHOD_MANIFEST_MAX_METHODS:
            raise AtlasError("compiler lexical method manifest method cap exceeded")
    methods.sort(key=lambda item: (item["source"]["path"], item["source"]["span"]["start_offset"],
                                  item["source"]["span"]["end_offset"], item["method_name"], item["fact_id"]))
    manifest = {"schema_version": LEXICAL_METHOD_MANIFEST_SCHEMA_VERSION,
                "snapshot_id": snapshot.get("snapshot_id"), "extractor_identity": extractor_identity,
                "methods": methods}
    if len(_canonical_json(manifest)) > LEXICAL_METHOD_MANIFEST_MAX_BYTES:
        raise AtlasError("compiler lexical method manifest byte cap exceeded")
    return manifest


def _compiler_copied_tool_files(extractor_output: Path, sdk_path: str) -> list[dict[str, object]]:
    """Map SDK tool files copied beside the extractor back to stable SDK paths."""
    format_root = Path(sdk_path) / "DotnetTools" / "dotnet-format"
    if not format_root.is_dir():
        raise AtlasError(f"selected SDK dotnet-format tool directory is missing: {format_root}")
    result: list[dict[str, object]] = []
    for output in sorted(extractor_output.iterdir(), key=lambda path: os.fsencode(path.name)):
        if not output.is_file() or output.suffix not in {".dll", ".exe"} or output.name.startswith("extractor."):
            continue
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        matches = []
        for source in format_root.rglob(output.name):
            if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == digest:
                matches.append(source)
        for source in matches:
            result.append({"logical_path": source.relative_to(format_root).as_posix(),
                           "path": source.as_posix(), "sha256": digest})
    return sorted(result, key=lambda item: (os.fsencode(str(item["logical_path"])), os.fsencode(str(item["path"]))))


def _verify_compiler_relationship_graph(snapshot: dict[str, object], relationship: dict[str, object]) -> None:
    graph = snapshot.get("source_graph")
    facts = graph.get("facts") if isinstance(graph, dict) else None
    if not isinstance(facts, list):
        raise AtlasError("compiler supplement cannot verify anchors against lexical graph")
    method_facts = [fact for fact in facts if isinstance(fact, dict) and fact.get("kind") == "method_declaration"]
    action = _compiler_span(relationship.get("action_source"))
    implementation = _compiler_span(relationship.get("implementation_source"))
    def method_match(span: tuple[str, int, int] | None, symbol: object, containing: bool = False) -> list[dict[str, object]]:
        if span is None or not isinstance(symbol, str):
            return []
        symbol_name = symbol.rsplit(".", 1)[-1].split("(", 1)[0]
        def matches(saved: tuple[str, int, int] | None) -> bool:
            if saved is None or saved[0] != span[0]:
                return False
            return saved[1] <= span[1] and span[2] <= saved[2] if containing else saved[1] == span[1] and abs(saved[2] - span[2]) <= 1
        return [fact for fact in method_facts if matches(_compiler_span(fact.get("source")))
                and fact.get("method_name", "").split(".")[-1] == symbol_name]
    action_matches = method_match(action, relationship.get("action_method"))
    implementation_matches = method_match(implementation, relationship.get("implementation_method"), containing=True)
    if len(action_matches) != 1:
        raise AtlasError(f"compiler action anchor does not identify exactly one saved lexical method fact: matches={len(action_matches)}")
    if len(implementation_matches) != 1:
        raise AtlasError(f"compiler implementation anchor does not identify exactly one saved lexical method fact: matches={len(implementation_matches)}")
    action_fact = action_matches[0]
    relationship["lexical_action_fact_id"] = action_fact["id"]
    relationship["lexical_implementation_fact_id"] = implementation_matches[0]["id"]
    route_facts = [fact for fact in facts if isinstance(fact, dict) and fact.get("kind") == "route_action"
                   and fact.get("action_id") == action_fact.get("id")
                   and fact.get("http_method") == relationship.get("http_method")
                   and fact.get("route_literal") == relationship.get("route")]
    if len(route_facts) != 1:
        same_action = [(fact.get("http_method"), fact.get("route_literal"), fact.get("id"))
                       for fact in facts if isinstance(fact, dict) and fact.get("kind") == "route_action"
                       and fact.get("action_id") == action_fact.get("id")]
        raise AtlasError(
            "compiler relationship must bind to exactly one lexical route fact by action method, HTTP verb, "
            f"and normalized route literal; matches={len(route_facts)} route={relationship.get('route')!r} "
            f"verb={relationship.get('http_method')!r} candidates={same_action!r}"
        )
    relationship["lexical_route_fact_id"] = route_facts[0]["id"]
    action_fact_id = action_fact.get("id")
    parameter = _compiler_span(relationship.get("service_parameter_source"))
    if parameter is None or not any(isinstance(fact, dict) and fact.get("kind") == "constructor_injection"
                                    and fact.get("owner_type_id") == action_fact.get("owner_type_id")
                                    and fact.get("parameter_name") == relationship.get("service_parameter")
                                    and _compiler_span(fact.get("source")) == parameter for fact in facts):
        raise AtlasError("compiler service parameter anchor does not exactly match a saved lexical constructor-injection fact")
    callsite = _compiler_span(relationship.get("call_site_source"))
    if callsite is None or not any(isinstance(fact, dict) and fact.get("kind") == "receiver_invocation_syntax"
                                   and fact.get("method_id") == action_fact_id
                                   and (span := _compiler_span(fact.get("source"))) is not None
                                   and span[0] == callsite[0] and span[1] <= callsite[1] <= callsite[2] <= span[2]
                                   for fact in facts):
        raise AtlasError("compiler call-site anchor is not contained in a saved lexical receiver-invocation fact")
    for registration in relationship.get("registrations", []):
        source = _compiler_span(registration.get("source")) if isinstance(registration, dict) else None
        matches = [fact for fact in facts if isinstance(fact, dict) and fact.get("kind") == "dependency_registration"
                   and (span := _compiler_span(fact.get("source"))) is not None and source is not None
                   and span[0] == source[0] and source[1] <= span[1] <= span[2] <= source[2]]
        if len(matches) != 1:
            raise AtlasError(f"compiler registration syntax anchor does not contain exactly one saved lexical registration fact: matches={len(matches)}")
        registration["lexical_registration_fact_id"] = matches[0]["id"]


def _verify_compiler_source_call_edges(snapshot: dict[str, object], relationships: list[dict[str, object]],
                                       edges: object) -> list[dict[str, object]]:
    """Bind compiler call edges to exact saved handler, helper, and route facts."""
    graph = snapshot.get("source_graph")
    facts = graph.get("facts") if isinstance(graph, dict) else None
    if not isinstance(facts, list) or not isinstance(edges, list):
        raise AtlasError("compiler source-call graph is malformed; no supplement published")
    methods = [fact for fact in facts if isinstance(fact, dict) and fact.get("kind") == "method_declaration"]
    files = {str(entry.get("path")): entry for entry in snapshot.get("files", []) if isinstance(entry, dict)}

    def exact_method(anchor: object, symbol: object, label: str) -> dict[str, object]:
        span = _compiler_span(anchor)
        if span is None or not isinstance(anchor, dict) or not isinstance(anchor.get("sha256"), str):
            raise AtlasError(f"compiler source-call edge has invalid {label} anchor; no supplement published")
        saved_file = files.get(span[0])
        if saved_file is None or saved_file.get("presence") != "present" or saved_file.get("type") != "file" or saved_file.get("sha256") != anchor["sha256"]:
            raise AtlasError(f"compiler source-call {label} anchor does not match tracked lexical snapshot: {span[0]}; no supplement published")
        matches = [fact for fact in methods if _compiler_span(fact.get("source")) == span
                   and isinstance(symbol, str) and fact.get("method_name") == symbol.rsplit(".", 1)[-1].split("(", 1)[0]]
        if len(matches) != 1:
            raise AtlasError(f"compiler source-call {label} anchor does not identify exactly one saved lexical method fact: matches={len(matches)}; no supplement published")
        return matches[0]

    verified: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for raw in edges:
        if not isinstance(raw, dict):
            raise AtlasError("compiler source-call edge is not an object; no supplement published")
        for key in ("route", "http_method", "implementation_type", "implementation_method", "caller_method", "callee_method"):
            if not isinstance(raw.get(key), str) or not raw[key]:
                raise AtlasError(f"compiler source-call edge has invalid {key}; no supplement published")
        _validate_compiler_source_call_edge_proof(raw, "no supplement published")
        if raw.get("dispatch_kind") == "interface_implementation_source":
            binding = raw.get("interface_binding")
            if (not isinstance(binding, dict) or binding.get("claim") != "compiler_confirmed_source_interface_implementation_correspondence"
                    or binding.get("compiler_implementation_match") is not True or binding.get("runtime_DI_selection_proven") is not False):
                raise AtlasError("compiler projected interface edge has invalid source evidence; no supplement published")
        elif raw.get("interface_binding") is not None:
            raise AtlasError("compiler projected direct edge contains unexpected interface evidence; no supplement published")
        callers = [relation for relation in relationships
                   if relation.get("route") == raw.get("route") and relation.get("http_method") == raw.get("http_method")
                   and relation.get("implementation_type") == raw.get("implementation_type")
                   and relation.get("implementation_method") == raw.get("implementation_method")]
        if len(callers) != 1:
            raise AtlasError(f"compiler source-call edge must bind to exactly one mapped handler relationship: matches={len(callers)} route={raw.get('route')!r}; no supplement published")
        caller_fact = exact_method(raw.get("caller_source"), raw.get("caller_method"), "caller")
        callee_fact = exact_method(raw.get("callee_source"), raw.get("callee_method"), "callee")
        if caller_fact.get("id") != callers[0].get("lexical_implementation_fact_id"):
            raise AtlasError("compiler source-call caller anchor does not match its mapped handler fact; no supplement published")
        call_span = _compiler_span(raw.get("call_site_source"))
        if call_span is None or not isinstance(raw.get("call_site_source"), dict):
            raise AtlasError("compiler source-call edge has invalid call-site anchor; no supplement published")
        caller_span = _compiler_span(caller_fact.get("source"))
        call_anchor = raw["call_site_source"]
        if (caller_span is None or call_span[0] != caller_span[0] or not isinstance(call_anchor.get("sha256"), str)
                or call_anchor.get("sha256") != caller_fact.get("source", {}).get("sha256")
                or not caller_span[1] <= call_span[1] <= call_span[2] <= caller_span[2]):
            raise AtlasError(f"compiler source-call site is outside its verified handler method: route={raw.get('route')!r} verb={raw.get('http_method')!r} caller_method={raw.get('caller_method')!r} callee={raw.get('callee_method')!r} caller={caller_span!r} call={call_span!r} "+
                             f"anchor_hash={call_anchor.get('sha256')!r} handler_hash={caller_fact.get('source', {}).get('sha256')!r}; no supplement published")
        if not isinstance(call_anchor.get("span"), dict) or not all(isinstance(call_anchor["span"].get(k), int) for k in ("start_offset", "end_offset")):
            raise AtlasError("compiler source-call site has an invalid span; no supplement published")
        if not isinstance(raw.get("callee_source"), dict) or raw["callee_source"].get("sha256") != files[_compiler_span(raw["callee_source"])[0]].get("sha256"):
            raise AtlasError("compiler source-call callee anchor does not match its tracked lexical snapshot; no supplement published")
        edge = dict(raw)
        edge.update({"route_fact_id": callers[0].get("lexical_route_fact_id"),
                     "caller_lexical_method_fact_id": caller_fact.get("id"),
                     "callee_lexical_method_fact_id": callee_fact.get("id"),
                     "lexical_implementation_fact_id": callers[0].get("lexical_implementation_fact_id")})
        identity = (edge.get("route_fact_id"), edge.get("caller_lexical_method_fact_id"),
                    edge.get("callee_lexical_method_fact_id"), call_span, edge.get("implementation_type"),
                    (edge.get("interface_binding") or {}).get("candidate_identity"))
        if identity in seen:
            raise AtlasError("compiler source-call graph contains a duplicate callsite relationship; no supplement published")
        seen.add(identity)
        verified.append(edge)
    return sorted(verified, key=lambda edge: (str(edge.get("route_fact_id")), str(edge.get("caller_lexical_method_fact_id")),
                                               str(edge.get("call_site_source", {}).get("path")),
                                               int(edge.get("call_site_source", {}).get("span", {}).get("start_offset", 0)),
                                               str(edge.get("callee_method")), str(edge.get("implementation_type")),
                                               str((edge.get("interface_binding") or {}).get("candidate_identity", ""))))


def _validate_compiler_source_call_edge_proof(edge: dict[str, object], context: str) -> None:
    """Enforce the closed dispatch and proof-label contract at every trust boundary."""
    dispatch_kind = edge.get("dispatch_kind")
    if not isinstance(dispatch_kind, str) or dispatch_kind not in {"static_source", "non_virtual_instance_source", "interface_implementation_source"}:
        raise AtlasError(f"compiler source-call edge has missing or invalid dispatch_kind; {context}")
    if (edge.get("compiler_binding_confirmed") is not True
            or edge.get("runtime_reachability_proven") is not False
            or edge.get("runtime_DI_selection_proven") is not False):
        raise AtlasError(f"compiler source-call edge has invalid proof labels; {context}")
    if dispatch_kind == "interface_implementation_source":
        binding = edge.get("interface_binding")
        if (not isinstance(binding, dict) or binding.get("claim") != "compiler_confirmed_source_interface_implementation_correspondence"
                or binding.get("compiler_implementation_match") is not True
                or binding.get("runtime_DI_selection_proven") is not False):
            raise AtlasError(f"compiler interface edge has invalid source-correspondence evidence; {context}")


def _source_call_node_id(source: object) -> str | None:
    span = _compiler_span(source)
    if span is None:
        return None
    return f"method:{span[0]}:{span[1]}:{span[2]}"


def _verify_compiler_source_call_graph(
    snapshot: dict[str, object], relationships: list[dict[str, object]], raw_graph: object, repo: Path,
    *, bind: bool, lexical_manifest: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    """Bind and validate the complete reachable method graph before it can be filtered by a consumer."""
    if not isinstance(raw_graph, dict):
        raise AtlasError("compiler source-call graph is missing or malformed; no supplement published")
    if (not isinstance(raw_graph.get("schema_version"), int) or isinstance(raw_graph.get("schema_version"), bool)
            or raw_graph.get("schema_version") != SOURCE_CALL_GRAPH_SCHEMA_VERSION or raw_graph.get("status") != "complete"):
        raise AtlasError("compiler source-call graph version or completion status is invalid; no supplement published")
    raw_caps = raw_graph.get("caps")
    if (not isinstance(raw_caps, dict) or set(raw_caps) != set(SOURCE_CALL_GRAPH_CAPS)
            or any(not isinstance(value, int) or isinstance(value, bool) for value in raw_caps.values())
            or raw_caps != SOURCE_CALL_GRAPH_CAPS):
        raise AtlasError("compiler source-call graph caps do not match the code-owned limits; no supplement published")
    graph = json.loads(json.dumps(raw_graph))
    facts = (snapshot.get("source_graph") or {}).get("facts")
    if not isinstance(facts, list):
        raise AtlasError("compiler source-call graph has no saved lexical graph; no supplement published")
    method_facts = [fact for fact in facts if isinstance(fact, dict) and fact.get("kind") == "method_declaration"]
    manifest_methods = lexical_manifest.get("methods") if isinstance(lexical_manifest, dict) else None
    if (not isinstance(manifest_methods, list) or lexical_manifest.get("schema_version") != LEXICAL_METHOD_MANIFEST_SCHEMA_VERSION
            or lexical_manifest.get("snapshot_id") != snapshot.get("snapshot_id")):
        raise AtlasError("compiler lexical method manifest is stale or malformed; no supplement published")
    expected_manifest = _compiler_lexical_method_manifest(
        snapshot, lexical_manifest.get("extractor_identity") if isinstance(lexical_manifest, dict) else "")
    if _canonical_json(lexical_manifest) != _canonical_json(expected_manifest):
        raise AtlasError("compiler lexical method manifest disagrees with the saved snapshot; no supplement published")
    manifest_by_identity = {}
    for entry in manifest_methods:
        if not isinstance(entry, dict) or not isinstance(entry.get("fact_id"), str):
            raise AtlasError("compiler lexical method manifest entry is malformed; no supplement published")
        source = entry.get("source")
        span = _compiler_span(source)
        identity = (entry.get("method_name"), *(span or ()), source.get("sha256") if isinstance(source, dict) else None)
        matches = [fact for fact in method_facts if fact.get("id") == entry["fact_id"]
                   and fact.get("method_name") == entry.get("method_name")
                   and _compiler_span(fact.get("source")) == span
                   and isinstance(source, dict) and isinstance(fact.get("source"), dict)
                   and fact["source"].get("sha256") == source.get("sha256")]
        if len(matches) != 1 or identity in manifest_by_identity:
            raise AtlasError("compiler lexical method manifest does not bind unique saved lexical facts; no supplement published")
        manifest_by_identity[identity] = matches[0]
    type_facts = [fact for fact in facts if isinstance(fact, dict) and fact.get("kind") == "type_declaration"]
    files = {str(entry.get("path")): entry for entry in snapshot.get("files", []) if isinstance(entry, dict)}
    lexical_type_cache: dict[str, tuple[list[object], dict[int, int], dict[int, int]]] = {}

    def expected_type_display(fact: dict[str, object]) -> str:
        span = _compiler_span(fact.get("source"))
        if span is None:
            raise AtlasError("compiler interface type has no source span; no supplement published")
        fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
        try:
            evidence = _read_working_file(fd, span[0], collect_source=True)
        finally:
            os.close(fd)
        raw = evidence.get("_source_bytes")
        if not isinstance(raw, bytes) or evidence.get("sha256") != fact.get("source", {}).get("sha256"):
            raise AtlasError("compiler interface type source changed during validation; no supplement published")
        source_text = raw.decode("utf-8-sig")
        from csharp_facts import lex
        tokens, _directives = lex(source_text)
        opening = next((token for token in tokens if token.start >= span[2] and token.value == "{"), None)
        if opening is None:
            raise AtlasError("compiler interface type has no source body; no supplement published")
        probe = {"owner_type_id": fact.get("type_id"), "source": {"path": span[0], "span": {
            "start_offset": opening.start + 1, "end_offset": opening.start + 1}}}
        return expected_containing_type(probe)

    def verify_type_anchor(binding: dict[str, object], key: str, type_id_key: str, label: str,
                           display_key: str | None = None) -> dict[str, object]:
        anchor, type_id = binding.get(key), binding.get(type_id_key)
        span = _compiler_span(anchor)
        if span is None or not isinstance(anchor, dict) or not isinstance(type_id, str):
            raise AtlasError(f"compiler interface {label} type reference is malformed; no supplement published")
        file = files.get(span[0])
        matches = [fact for fact in type_facts if fact.get("type_id") == type_id and _compiler_span(fact.get("source")) == span
                   and isinstance(fact.get("source"), dict) and fact["source"].get("sha256") == anchor.get("sha256")
                   and file is not None and file.get("sha256") == anchor.get("sha256")]
        if len(matches) != 1:
            raise AtlasError(f"compiler interface {label} type anchor does not identify one exact saved lexical type fact; no supplement published")
        if display_key is not None and binding.get(display_key) != expected_type_display(matches[0]):
            raise AtlasError(f"compiler interface {label} display identity disagrees with its lexical owner; no supplement published")
        return matches[0]

    def verify_interface_binding(binding: object, *, supported: bool, edge: dict[str, object] | None = None) -> None:
        if not isinstance(binding, dict):
            raise AtlasError("compiler interface dispatch evidence is missing; no supplement published")
        common = {"bound_interface_type", "bound_interface_type_id", "bound_interface_type_source", "bound_interface_declaration_source", "bound_interface_member",
                  "bound_interface_signature", "bound_interface_parameters", "bound_interface_arity", "bound_interface_parameter_count",
                  "bound_interface_member_source", "bound_interface_member_name_source",
                  "candidate_type", "candidate_type_id", "candidate_type_source", "candidate_identity"}
        expected = (common | {"implementation_method", "implementation_signature", "implementation_method_source",
                              "implementation_parameters",
                              "implementation_owner_type", "implementation_owner_type_id", "implementation_owner_type_source",
                              "candidate_to_interface_path", "candidate_to_implementation_owner_path", "claim",
                              "compiler_implementation_match", "runtime_DI_selection_proven"}) if supported else (
                              common | {"implementation_method", "implementation_method_source", "reason"})
        if set(binding) != expected:
            raise AtlasError("compiler interface evidence has unknown or missing fields; no supplement published")
        interface_fact = verify_type_anchor(binding, "bound_interface_type_source", "bound_interface_type_id", "interface", "bound_interface_type")
        candidate_fact = verify_type_anchor(binding, "candidate_type_source", "candidate_type_id", "candidate", "candidate_type")
        candidate_span = _compiler_span(binding.get("candidate_type_source"))
        expected_candidate_identity = f"{binding.get('candidate_type')}|{candidate_span[0]}|{candidate_span[1]}|{candidate_span[2]}" if candidate_span else None
        if (binding.get("candidate_identity") != expected_candidate_identity
                or not isinstance(binding.get("bound_interface_arity"), int) or isinstance(binding.get("bound_interface_arity"), bool)
                or binding.get("bound_interface_arity") != 0
                or not isinstance(binding.get("bound_interface_parameter_count"), int)
                or isinstance(binding.get("bound_interface_parameter_count"), bool)
                or binding.get("bound_interface_parameter_count") < 0
                or not isinstance(binding.get("bound_interface_parameters"), list)
                or len(binding["bound_interface_parameters"]) != binding.get("bound_interface_parameter_count")):
            raise AtlasError("compiler interface candidate identity or bound signature is invalid; no supplement published")
        add_reference("interface-proof:" + str(binding.get("candidate_identity")) + ":interface", binding.get("bound_interface_type_source"))
        add_reference("interface-proof:" + str(binding.get("candidate_identity")) + ":candidate", binding.get("candidate_type_source"))
        member_span = _compiler_span(binding.get("bound_interface_member_source"))
        member_name_span = _compiler_span(binding.get("bound_interface_member_name_source"))
        declaration_span = _compiler_span(binding.get("bound_interface_declaration_source"))
        if (member_span is None or member_name_span is None or member_span[0] != member_name_span[0]
                or declaration_span is None or declaration_span[0] != member_span[0]
                or declaration_span[1] != _compiler_span(binding.get("bound_interface_type_source"))[1]
                or not _compiler_span(binding.get("bound_interface_type_source"))[2] <= declaration_span[2]
                or not declaration_span[1] <= member_span[1] <= member_span[2] <= declaration_span[2]
                or not member_span[1] <= member_name_span[1] <= member_name_span[2] <= member_span[2]
                or member_span[0] != _compiler_span(binding.get("bound_interface_type_source"))[0]
                or member_span[1] <= _compiler_span(binding.get("bound_interface_type_source"))[2]):
            raise AtlasError("compiler interface member source is not contained in its bound interface source file; no supplement published")
        member_owner_probe = {"owner_type_id": interface_fact.get("type_id"), "source": binding.get("bound_interface_member_source")}
        if expected_containing_type(member_owner_probe) != expected_type_display(interface_fact):
            raise AtlasError("compiler interface member declaration belongs to a different lexical interface; no supplement published")
        member_reference_id = f"interface-proof:{binding.get('candidate_identity')}:{member_span[0]}:{member_span[1]}:{member_span[2]}"
        add_reference(member_reference_id + ":interface-declaration", binding.get("bound_interface_declaration_source"))
        add_reference(member_reference_id + ":member", binding.get("bound_interface_member_source"))
        add_reference(member_reference_id + ":member-name", binding.get("bound_interface_member_name_source"))
        if (interface_fact.get("declaration_kind") != "interface"
                or (supported and candidate_fact.get("declaration_kind") not in {"class", "record"})
                or (not supported and candidate_fact.get("declaration_kind") not in {"class", "struct", "record"})):
            raise AtlasError("compiler interface evidence has a source declaration of the wrong kind; no supplement published")
        if supported:
            owner_fact = verify_type_anchor(binding, "implementation_owner_type_source", "implementation_owner_type_id", "implementation owner", "implementation_owner_type")
            if edge is None or (binding.get("implementation_method") != edge.get("callee_method")
                    or binding.get("implementation_method_source") != edge.get("callee_source")
                    or binding.get("implementation_owner_type") != edge.get("callee_containing_type")):
                raise AtlasError("compiler interface implementation evidence disagrees with its edge endpoint; no supplement published")
            impl_span = _compiler_span(binding.get("implementation_method_source"))
            impl_matches = [fact for fact in method_facts if _compiler_span(fact.get("source")) == impl_span
                            and fact.get("method_name") == str(binding.get("implementation_signature", "")).split("(", 1)[0].split("`", 1)[0]
                            and fact.get("owner_type_id") == owner_fact.get("type_id")]
            if len(impl_matches) != 1:
                raise AtlasError("compiler interface implementation method does not match its exact source owner; no supplement published")
            if binding.get("claim") != "compiler_confirmed_source_interface_implementation_correspondence" or binding.get("compiler_implementation_match") is not True or binding.get("runtime_DI_selection_proven") is not False:
                raise AtlasError("compiler interface edge has invalid correspondence labels; no supplement published")
            paths = ((binding.get("candidate_to_interface_path"), binding.get("candidate_type_id"), binding.get("bound_interface_type_id")),
                     (binding.get("candidate_to_implementation_owner_path"), binding.get("candidate_type_id"), binding.get("implementation_owner_type_id")))
            for path, start, end in paths:
                if not isinstance(path, list):
                    raise AtlasError("compiler interface membership path is malformed; no supplement published")
                cursor = start
                for step in path:
                    fields = {"from_type", "from_type_id", "from_type_source", "from_type_declaration_source", "to_type", "to_type_id", "to_type_source", "edge_kind", "base_list_source", "type_syntax_source"}
                    if not isinstance(step, dict) or set(step) != fields or step.get("from_type_id") != cursor or step.get("edge_kind") not in {"base", "interface"}:
                        raise AtlasError("compiler interface membership path has an invalid step; no supplement published")
                    verify_type_anchor(step, "from_type_source", "from_type_id", "membership source", "from_type")
                    verify_type_anchor(step, "to_type_source", "to_type_id", "membership target", "to_type")
                    declaration_span = _compiler_span(step.get("from_type_declaration_source"))
                    from_span = _compiler_span(step.get("from_type_source"))
                    base_span, syntax_span = _compiler_span(step.get("base_list_source")), _compiler_span(step.get("type_syntax_source"))
                    if (declaration_span is None or from_span is None or declaration_span[0] != from_span[0]
                            or not declaration_span[1] <= from_span[1] <= from_span[2] <= declaration_span[2]
                            or base_span is None or syntax_span is None or declaration_span[0] != base_span[0]
                            or not declaration_span[1] <= base_span[1] <= base_span[2] <= declaration_span[2]
                            or base_span[0] != syntax_span[0]
                            or not base_span[1] <= syntax_span[1] <= syntax_span[2] <= base_span[2]):
                        raise AtlasError("compiler interface membership syntax anchor is invalid; no supplement published")
                    cursor = step.get("to_type_id")
                if cursor != end:
                    raise AtlasError("compiler interface membership path reaches a different type; no supplement published")
        elif not isinstance(binding.get("reason"), str) or not binding.get("reason"):
            raise AtlasError("compiler interface candidate exclusion has no reason; no supplement published")
        if supported:
            add_reference("interface-proof:" + str(binding.get("candidate_identity")) + ":implementation-owner", binding.get("implementation_owner_type_source"))
            add_reference("interface-proof:" + str(binding.get("candidate_identity")) + ":implementation", binding.get("implementation_method_source"))
            for path_key in ("candidate_to_interface_path", "candidate_to_implementation_owner_path"):
                for index, step in enumerate(binding[path_key]):
                    for field in ("from_type_source", "from_type_declaration_source", "to_type_source", "base_list_source", "type_syntax_source"):
                        add_reference(f"interface-proof:{binding.get('candidate_identity')}:{path_key}:{index}:{field}", step[field])
        elif isinstance(binding.get("implementation_method_source"), dict):
            add_reference("interface-proof:" + str(binding.get("candidate_identity")) + ":excluded-implementation", binding.get("implementation_method_source"))

    def expected_containing_type(method_fact: dict[str, object]) -> str:
        owner_id = method_fact.get("owner_type_id")
        owners = [fact for fact in type_facts if fact.get("type_id") == owner_id]
        if not owners:
            raise AtlasError("compiler source-call method owner does not identify a lexical type declaration; no supplement published")
        method_span = _compiler_span(method_fact.get("source"))
        if method_span is None or not any(_compiler_span(candidate.get("source")) is not None
                                          and _compiler_span(candidate.get("source"))[0] == method_span[0]
                                          for candidate in owners):
            raise AtlasError("compiler source-call lexical owner is outside its declaration file; no supplement published")
        file_record = files.get(method_span[0])
        if file_record is None:
            raise AtlasError("compiler source-call owner file changed or is missing; no supplement published")
        if method_span[0] not in lexical_type_cache:
            root_fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
            try:
                evidence = _read_working_file(root_fd, method_span[0], collect_source=True)
            finally:
                os.close(root_fd)
            raw_source = evidence.get("_source_bytes")
            if (evidence.get("presence") != "present" or evidence.get("type") != "file"
                    or evidence.get("sha256") != file_record.get("sha256") or not isinstance(raw_source, bytes)):
                raise AtlasError("compiler source-call owner file changed or is missing; no supplement published")
            try:
                source_text = raw_source.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise AtlasError("compiler source-call owner file is not UTF-8; no supplement published") from exc
            from csharp_facts import lex, _matches, _angle_matches
            tokens, _directives = lex(source_text)
            lexical_type_cache[method_span[0]] = (tokens, _matches(tokens), _angle_matches(tokens))
        tokens, braces, angles = lexical_type_cache[method_span[0]]
        containing = []
        for type_fact in type_facts:
            span = _compiler_span(type_fact.get("source"))
            if span is None or span[0] != method_span[0] or span[1] >= method_span[1]:
                continue
            declaration_indices = [index for index, token in enumerate(tokens)
                                   if token.start == span[1] and token.value in {"class", "struct", "interface", "record"}]
            if len(declaration_indices) != 1:
                continue
            index = declaration_indices[0]
            name_index = index + 1
            if tokens[index].value == "record" and name_index < len(tokens) and tokens[name_index].value in {"class", "struct"}:
                name_index += 1
            while name_index < len(tokens) and tokens[name_index].kind != "identifier":
                name_index += 1
            if name_index >= len(tokens):
                continue
            cursor = name_index + 1
            if cursor < len(tokens) and tokens[cursor].value == "<" and cursor in angles:
                cursor = angles[cursor] + 1
            while cursor < len(tokens) and tokens[cursor].value not in {"{", ";"}:
                cursor += 1
            if cursor >= len(tokens) or tokens[cursor].value != "{" or cursor not in braces:
                continue
            close_index = braces[cursor]
            if tokens[cursor].start <= method_span[1] and method_span[2] <= tokens[close_index].end:
                containing.append((span[1], type_fact, name_index))
        containing.sort(key=lambda item: item[0])
        owner_declarations = [item for item in containing if item[1].get("type_id") == owner_id]
        if len(owner_declarations) != 1 or containing[-1][1].get("type_id") != owner_id:
            raise AtlasError("compiler source-call lexical owner is not the innermost enclosing type; no supplement published")
        owner = owner_declarations[0][1]
        segments = []
        for _start, type_fact, name_index in containing:
            name = str(type_fact.get("name"))
            arity = type_fact.get("arity")
            if not isinstance(arity, int) or isinstance(arity, bool) or arity < 0:
                raise AtlasError("compiler source-call lexical type arity is invalid; no supplement published")
            if arity:
                open_index = name_index + 1
                if open_index >= len(tokens) or tokens[open_index].value != "<" or open_index not in angles:
                    raise AtlasError("compiler source-call generic owner arity is not lexically verifiable; no supplement published")
                close_index = angles[open_index]
                names = [tokens[part].value.removeprefix("@").split(":", 1)[0]
                         for part in range(open_index + 1, close_index) if tokens[part].kind == "identifier"]
                if len(names) < arity:
                    raise AtlasError("compiler source-call generic owner parameters are incomplete; no supplement published")
                segments.append(name + "<" + ", ".join(names[:arity]) + ">")
            else:
                segments.append(name)
        namespace = str(owner.get("namespace") or "")
        prefix = "global::" + (namespace + "." if namespace else "")
        return prefix + ".".join(segments)

    collections = {
        "roots": graph.get("roots"), "nodes": graph.get("nodes"), "edges": graph.get("edges"),
        "unsupported": graph.get("unsupported"), "nested_body_exclusions": graph.get("nested_body_exclusions"),
    }
    if set(graph) != {"schema_version", "status", "caps", "counts", *collections.keys()}:
        raise AtlasError("compiler source-call graph has unknown or missing fields; no supplement published")
    item_fields = {
        "roots": {"route", "http_method", "implementation_type", "implementation_method", "root_method", "root_node_id", "root_source", "route_fact_id", "lexical_implementation_method_fact_id"},
        "nodes": {"id", "method", "containing_type", "source", "lexical_method_fact_id"},
        "edges": {"caller_node_id", "callee_node_id", "caller_method", "caller_source", "callee_method", "callee_containing_type", "callee_source", "call_site_source", "dispatch_kind", "compiler_binding_confirmed", "runtime_reachability_proven", "runtime_DI_selection_proven", "caller_lexical_method_fact_id", "callee_lexical_method_fact_id", "interface_binding"},
        "unsupported": {"caller_node_id", "caller_method", "caller_source", "call_site_source", "kind", "reason", "callee_method", "callee_source", "interface_binding"},
        "nested_body_exclusions": {"caller_node_id", "caller_method", "caller_source", "nested_body_kind", "source", "reason"},
    }
    if any(not isinstance(items, list) or any(not isinstance(item, dict) for item in items)
           for items in collections.values()):
        raise AtlasError("compiler source-call graph collections are malformed; no supplement published")
    for key, items in collections.items():
        required = item_fields[key]
        if bind:
            if key == "roots": required -= {"route_fact_id", "lexical_implementation_method_fact_id"}
            if key == "nodes": required -= {"lexical_method_fact_id"}
            if key == "edges": required -= {"caller_lexical_method_fact_id", "callee_lexical_method_fact_id"}
        if key == "edges":
            required = required - {"interface_binding"}
        if key == "unsupported":
            required = required - {"callee_method", "callee_source", "interface_binding"}
        if any(not required <= set(item) or set(item) - item_fields[key] for item in items):
            raise AtlasError(f"compiler source-call graph {key} entries have unknown or missing fields; no supplement published")
    for item in collections["unsupported"]:
        lexical_boundary = item.get("kind") == "unsupported_lexical_source_method"
        has_callee_method = "callee_method" in item
        has_callee_source = "callee_source" in item
        if lexical_boundary != has_callee_method or lexical_boundary != has_callee_source:
            raise AtlasError("compiler source-call graph lexical boundary fields are incomplete or unexpected; no supplement published")
        if (item.get("kind") == "unsupported_interface_candidate") != isinstance(item.get("interface_binding"), dict):
            raise AtlasError("compiler interface candidate boundary evidence is incomplete or unexpected; no supplement published")
    counts = graph.get("counts")
    count_fields = {"roots", "nodes", "edges", "inspected_invocations", "interface_candidate_checks", "unsupported", "nested_body_exclusions", "method_bodies_traversed", "serialized_graph_bytes", "traversal_work", "compatibility_records"}
    if not isinstance(counts, dict) or set(counts) != count_fields:
        raise AtlasError("compiler source-call graph counts are missing; no supplement published")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts.values()):
        raise AtlasError("compiler source-call graph counts must be nonnegative integers; no supplement published")
    for key, items in collections.items():
        if counts.get(key) != len(items) or len(items) > int(SOURCE_CALL_GRAPH_CAPS[key]):
            raise AtlasError(f"compiler source-call graph {key} count exceeds or disagrees with its cap; no supplement published")
    inspected = counts.get("inspected_invocations")
    invocation_sites = {(str(item.get("caller_node_id")), _compiler_span(item.get("call_site_source")))
                        for item in collections["edges"] + collections["unsupported"]}
    if (not isinstance(inspected, int) or inspected != len(invocation_sites)
            or inspected > SOURCE_CALL_GRAPH_CAPS["inspected_invocations"]):
        raise AtlasError("compiler source-call graph inspected-invocation count is inconsistent; no supplement published")
    if counts.get("method_bodies_traversed") != len(collections["nodes"]):
        raise AtlasError("compiler source-call graph method-body traversal count is inconsistent; no supplement published")
    if (counts.get("traversal_work") != inspected + counts["interface_candidate_checks"]
            or counts["interface_candidate_checks"] > SOURCE_CALL_GRAPH_CAPS["interface_candidate_checks"]
            or counts["traversal_work"] > SOURCE_CALL_GRAPH_CAPS["traversal_work"]
            or counts["compatibility_records"] > SOURCE_CALL_GRAPH_CAPS["compatibility_records"]):
        raise AtlasError("compiler source-call graph traversal or compatibility work count is inconsistent; no supplement published")
    if not isinstance(counts.get("serialized_graph_bytes"), int) or counts["serialized_graph_bytes"] < 1:
        raise AtlasError("compiler source-call graph serialized-byte count is invalid; no supplement published")

    def exact_method(source: object, symbol: object, label: str) -> dict[str, object]:
        span = _compiler_span(source)
        if span is None or not isinstance(source, dict) or not isinstance(source.get("sha256"), str):
            raise AtlasError(f"compiler source-call graph {label} anchor is invalid; no supplement published")
        file = files.get(span[0])
        if (file is None or file.get("presence") != "present" or file.get("type") != "file"
                or file.get("sha256") != source["sha256"]):
            raise AtlasError(f"compiler source-call graph {label} anchor does not match the tracked snapshot: {span[0]}; no supplement published")
        name = symbol.rsplit(".", 1)[-1].split("(", 1)[0] if isinstance(symbol, str) else None
        manifest_matches = [fact for identity, fact in manifest_by_identity.items()
                            if identity[0] == name and identity[1:4] == span]
        matches = manifest_matches
        if len(matches) != 1:
            location = (f"path={span[0]!r} start_offset={span[1]} end_offset={span[2]}"
                        if span is not None else "path=<invalid> start_offset=<invalid> end_offset=<invalid>")
            raise AtlasError(f"compiler source-call graph {label} anchor does not identify one exact lexical method: "
                             f"symbol={symbol!r} {location} matches={len(matches)}; no supplement published")
        return matches[0]

    references: list[tuple[str, dict[str, object]]] = []

    def add_reference(label: str, anchor: object) -> None:
        if not isinstance(anchor, dict):
            raise AtlasError(f"compiler source-call graph {label} has no source anchor; no supplement published")
        references.append((label, anchor))

    node_by_id: dict[str, dict[str, object]] = {}
    for node in collections["nodes"]:
        node_id = node.get("id")
        source = node.get("source")
        expected_id = _source_call_node_id(source)
        if (not isinstance(node_id, str) or not node_id or node_id != expected_id or node_id in node_by_id
                or any(not isinstance(node.get(key), str) or not node[key]
                       for key in ("method", "containing_type"))):
            raise AtlasError("compiler source-call graph contains a duplicate or invalid lexical method node; no supplement published")
        method = exact_method(source, node.get("method"), "method-node")
        if node.get("containing_type") != expected_containing_type(method):
            raise AtlasError("compiler source-call graph containing type disagrees with its lexical owner declaration; no supplement published")
        lexical_id = method.get("id")
        if bind:
            node["lexical_method_fact_id"] = lexical_id
        elif node.get("lexical_method_fact_id") != lexical_id:
            raise AtlasError("compiler source-call graph method node lost its lexical fact binding; impact refused")
        node_by_id[node_id] = node
        add_reference(f"node:{node_id}", source)

    if any(not isinstance(relation, dict) for relation in relationships):
        raise AtlasError("compiler source-call graph relationship list is malformed; no supplement published")
    roots_by_identity: set[tuple[str, str, str]] = set()
    root_nodes: list[str] = []
    for root in collections["roots"]:
        source = root.get("root_source")
        method = exact_method(source, root.get("root_method"), "root")
        root_node_id = root.get("root_node_id")
        node = node_by_id.get(str(root_node_id))
        if node is None or node.get("source") != source or node.get("method") != root.get("root_method"):
            raise AtlasError("compiler source-call graph root does not identify its exact method node; no supplement published")
        candidates = [relation for relation in relationships
                      if relation.get("route") == root.get("route")
                      and relation.get("http_method") == root.get("http_method")
                      and relation.get("implementation_type") == root.get("implementation_type")
                      and relation.get("implementation_method") == root.get("implementation_method")
                      and relation.get("lexical_implementation_fact_id") == method.get("id")]
        if len(candidates) != 1:
            raise AtlasError("compiler source-call graph root must join exactly one mapped route/handler relationship; no supplement published")
        relation = candidates[0]
        if (any(not isinstance(root.get(key), str) or not root[key] for key in
                ("route", "http_method", "implementation_type", "implementation_method", "root_method", "root_node_id"))
                or node.get("containing_type") != relation.get("implementation_method_containing_type")):
            raise AtlasError("compiler source-call graph root identity or containing type is invalid; no supplement published")
        identity = (str(relation.get("lexical_route_fact_id")), str(relation.get("lexical_implementation_fact_id")),
                    str(relation.get("implementation_type")))
        if identity in roots_by_identity:
            raise AtlasError("compiler source-call graph contains a duplicate route root; no supplement published")
        roots_by_identity.add(identity)
        root_nodes.append(str(root_node_id))
        if bind:
            root["route_fact_id"] = relation.get("lexical_route_fact_id")
            root["lexical_implementation_method_fact_id"] = relation.get("lexical_implementation_fact_id")
        elif (root.get("route_fact_id") != relation.get("lexical_route_fact_id")
              or root.get("lexical_implementation_method_fact_id") != relation.get("lexical_implementation_fact_id")):
            raise AtlasError("compiler source-call graph root lost its route or handler binding; impact refused")
        add_reference(f"root:{root_node_id}", source)
    expected_root_identities = {(str(relation.get("lexical_route_fact_id")),
                                 str(relation.get("lexical_implementation_fact_id")),
                                 str(relation.get("implementation_type"))) for relation in relationships}
    if roots_by_identity != expected_root_identities:
        raise AtlasError("compiler source-call graph omits or invents a mapped route root; no supplement published")

    edge_keys: set[tuple[str, tuple[str, int, int]]] = set()
    adjacency: dict[str, list[dict[str, object]]] = {}
    for edge in collections["edges"]:
        caller_id, callee_id = edge.get("caller_node_id"), edge.get("callee_node_id")
        caller, callee = node_by_id.get(str(caller_id)), node_by_id.get(str(callee_id))
        if caller is None or callee is None:
            raise AtlasError("compiler source-call graph edge has a missing endpoint; no supplement published")
        if edge.get("caller_method") != caller.get("method") or edge.get("callee_method") != callee.get("method"):
            raise AtlasError("compiler source-call graph edge method identity disagrees with an endpoint; no supplement published")
        if (any(not isinstance(edge.get(key), str) or not edge[key] for key in
                ("caller_node_id", "callee_node_id", "caller_method", "callee_method", "callee_containing_type"))
                or edge.get("callee_containing_type") != callee.get("containing_type")):
            raise AtlasError("compiler source-call graph edge identity or callee type is invalid; no supplement published")
        if (any(not isinstance(edge.get(key), str) or not edge[key] for key in
                ("caller_node_id", "callee_node_id", "caller_method", "callee_method", "callee_containing_type"))
                or edge.get("callee_containing_type") != callee.get("containing_type")):
            raise AtlasError("compiler source-call graph edge identity or callee type is invalid; no supplement published")
        call_span = _compiler_span(edge.get("call_site_source"))
        caller_span, callee_span = _compiler_span(caller.get("source")), _compiler_span(callee.get("source"))
        if (call_span is None or caller_span is None or callee_span is None
                or call_span[0] != caller_span[0] or not caller_span[1] <= call_span[1] <= call_span[2] <= caller_span[2]):
            raise AtlasError("compiler source-call graph callsite is outside its exact caller method; no supplement published")
        if edge.get("caller_source") != caller.get("source") or edge.get("callee_source") != callee.get("source"):
            raise AtlasError("compiler source-call graph edge source anchor disagrees with its endpoint; no supplement published")
        _validate_compiler_source_call_edge_proof(edge, "no supplement published")
        interface_edge = edge.get("dispatch_kind") == "interface_implementation_source"
        if interface_edge:
            verify_interface_binding(edge.get("interface_binding"), supported=True, edge=edge)
        elif "interface_binding" in edge:
            raise AtlasError("compiler direct source-call edge contains unexpected interface evidence; no supplement published")
        key = (str(caller_id), call_span, str((edge.get("interface_binding") or {}).get("candidate_identity")) if interface_edge else "direct")
        if key in edge_keys:
            raise AtlasError("compiler source-call graph contains a duplicate callsite edge; no supplement published")
        edge_keys.add(key)
        caller_fact = node_by_id[str(caller_id)]["lexical_method_fact_id"]
        callee_fact = node_by_id[str(callee_id)]["lexical_method_fact_id"]
        if bind:
            edge["caller_lexical_method_fact_id"] = caller_fact
            edge["callee_lexical_method_fact_id"] = callee_fact
        elif (edge.get("caller_lexical_method_fact_id") != caller_fact
              or edge.get("callee_lexical_method_fact_id") != callee_fact):
            raise AtlasError("compiler source-call graph edge lost its exact method fact endpoints; impact refused")
        add_reference(f"edge-caller:{caller_id}:{call_span[1]}", edge.get("caller_source"))
        add_reference(f"edge-callee:{callee_id}:{call_span[1]}", edge.get("callee_source"))
        add_reference(f"edge-callsite:{caller_id}:{call_span[1]}", edge.get("call_site_source"))
        if interface_edge:
            binding = edge["interface_binding"]
            candidate_identity = str(binding["candidate_identity"])
            for refkey in ("bound_interface_type_source", "bound_interface_declaration_source", "candidate_type_source", "implementation_owner_type_source",
                           "bound_interface_member_source", "bound_interface_member_name_source", "implementation_method_source"):
                add_reference(f"interface:{caller_id}:{call_span[1]}:{candidate_identity}:{refkey}", binding.get(refkey))
            for path_key in ("candidate_to_interface_path", "candidate_to_implementation_owner_path"):
                for step_index, step in enumerate(binding[path_key]):
                    for refkey in ("from_type_source", "from_type_declaration_source", "to_type_source", "base_list_source", "type_syntax_source"):
                        add_reference(f"interface:{caller_id}:{call_span[1]}:{candidate_identity}:{path_key}:{step_index}:{refkey}", step.get(refkey))
        adjacency.setdefault(str(caller_id), []).append(edge)

    def check_contained_anchor(caller_id: object, anchor: object, label: str) -> None:
        caller = node_by_id.get(str(caller_id))
        outer, inner = _compiler_span(caller.get("source")) if caller else None, _compiler_span(anchor)
        if outer is None or inner is None or outer[0] != inner[0] or not outer[1] <= inner[1] <= inner[2] <= outer[2]:
            raise AtlasError(f"compiler source-call graph {label} is outside its visited caller; no supplement published")

    unsupported_identities = set()
    for item in collections["unsupported"]:
        caller_id = item.get("caller_node_id")
        caller = node_by_id.get(str(caller_id))
        if (not isinstance(caller_id, str) or caller is None or item.get("caller_method") != caller.get("method")
                or item.get("caller_source") != caller.get("source")
                or not isinstance(item.get("kind"), str)
                or item.get("kind") not in {"unsupported_source_call", "unsupported_source_method_body", "unsupported_lexical_source_method", "unsupported_interface_candidate"}
                or not isinstance(item.get("reason"), str) or not item.get("reason")):
            raise AtlasError("compiler source-call graph limitation is not bound to its visited caller; no supplement published")
        if item.get("kind") == "unsupported_interface_candidate":
            verify_interface_binding(item.get("interface_binding"), supported=False)
            binding = item["interface_binding"]
            unsupported_call_span = _compiler_span(item.get("call_site_source"))
            assert unsupported_call_span is not None
            for refkey in ("bound_interface_type_source", "bound_interface_declaration_source", "candidate_type_source",
                           "bound_interface_member_source", "bound_interface_member_name_source"):
                add_reference(f"interface:{caller_id}:{unsupported_call_span[1]}:{binding['candidate_identity']}:{refkey}", binding.get(refkey))
        elif "interface_binding" in item:
            raise AtlasError("compiler unsupported boundary contains unexpected interface evidence; no supplement published")
        unsupported_identity = (caller_id, _compiler_span(item.get("call_site_source")), item.get("kind"),
                                item.get("interface_binding", {}).get("candidate_identity") if isinstance(item.get("interface_binding"), dict) else None)
        if unsupported_identity in unsupported_identities:
            raise AtlasError("compiler source-call graph contains a duplicate unsupported boundary; no supplement published")
        unsupported_identities.add(unsupported_identity)
        check_contained_anchor(caller_id, item.get("call_site_source"), "unsupported callsite")
        unsupported_span = _compiler_span(item.get("call_site_source"))
        add_reference(f"unsupported:{caller_id}:{unsupported_span[1] if unsupported_span else -1}", item.get("call_site_source"))
        if item["kind"] == "unsupported_lexical_source_method":
            callee_method, callee_source = item.get("callee_method"), item.get("callee_source")
            callee_span = _compiler_span(callee_source)
            callee_name = callee_method.split("(", 1)[0].rsplit(".", 1)[-1] if isinstance(callee_method, str) else ""
            file_record = files.get(callee_span[0]) if callee_span else None
            if (not callee_name or not isinstance(callee_method, str) or callee_span is None
                    or not isinstance(callee_source, dict) or file_record is None
                    or file_record.get("sha256") != callee_source.get("sha256")):
                raise AtlasError("compiler lexical boundary lacks an exact tracked callee diagnostic; no supplement published")
            callee_identity = (callee_name, callee_span[0], callee_span[1], callee_span[2], callee_source.get("sha256"))
            if callee_identity in manifest_by_identity:
                raise AtlasError("compiler lexical boundary callee was already admitted; no supplement published")
            add_reference(f"unsupported-callee:{caller_id}:{unsupported_span[1] if unsupported_span else -1}", callee_source)
    positive_candidate_calls = {(str(edge.get("caller_node_id")), _compiler_span(edge.get("call_site_source")),
                                 str((edge.get("interface_binding") or {}).get("candidate_identity")))
                                for edge in collections["edges"] if edge.get("dispatch_kind") == "interface_implementation_source"}
    excluded_candidate_calls = {(str(item.get("caller_node_id")), _compiler_span(item.get("call_site_source")),
                                 str((item.get("interface_binding") or {}).get("candidate_identity")))
                                for item in collections["unsupported"] if item.get("kind") == "unsupported_interface_candidate"}
    if positive_candidate_calls & excluded_candidate_calls:
        raise AtlasError("compiler interface candidate is both supported and excluded at one callsite; no supplement published")
    nested_identities = set()
    for item in collections["nested_body_exclusions"]:
        caller_id = item.get("caller_node_id")
        caller = node_by_id.get(str(caller_id))
        if (not isinstance(caller_id, str) or caller is None or item.get("caller_method") != caller.get("method")
                or item.get("caller_source") != caller.get("source")
                or not isinstance(item.get("reason"), str) or not item.get("reason")):
            raise AtlasError("compiler source-call graph nested-body boundary is not bound to its visited caller; no supplement published")
        if not isinstance(item.get("nested_body_kind"), str) or item.get("nested_body_kind") not in {"local_function", "anonymous_function"}:
            raise AtlasError("compiler source-call graph has an unknown nested-body exclusion; no supplement published")
        check_contained_anchor(caller_id, item.get("source"), "nested-body exclusion")
        nested_identity = (caller_id, _compiler_span(item.get("source")), item.get("nested_body_kind"))
        if nested_identity in nested_identities:
            raise AtlasError("compiler source-call graph contains a duplicate nested-body boundary; no supplement published")
        nested_identities.add(nested_identity)
        nested_span = _compiler_span(item.get("source"))
        add_reference(f"nested:{caller_id}:{nested_span[1] if nested_span else -1}", item.get("source"))

    # Check callsite token boundaries against actual hashed source text; this catches rehashed span substitutions.
    snippets = _source_texts(repo, references)
    snippet_by_id = {str(item["fact_id"]): str(item["text"]) for item in snippets}
    from csharp_facts import lex

    known_source_type_names: dict[str, tuple[str, ...] | None] = {}
    bodyless_source_type_displays: dict[tuple[str, int, int], str] = {}

    def normalized_type(values: list[str]) -> str:
        values = [value for value in values if value not in {"global", "::"}]
        aliases = {"String": "string", "Boolean": "bool", "Byte": "byte", "SByte": "sbyte",
                   "Int16": "short", "UInt16": "ushort", "Int32": "int", "UInt32": "uint",
                   "Int64": "long", "UInt64": "ulong", "Single": "float", "Double": "double",
                   "Decimal": "decimal", "Char": "char", "Object": "object"}
        return " ".join(aliases.get(value, value) for value in values)

    def source_type_matches_compiler(source_values: list[str], compiler_type: str) -> bool:
        aliases = {"String": "string", "Boolean": "bool", "Byte": "byte", "SByte": "sbyte",
                   "Int16": "short", "UInt16": "ushort", "Int32": "int", "UInt32": "uint",
                   "Int64": "long", "UInt64": "ulong", "Single": "float", "Double": "double",
                   "Decimal": "decimal", "Char": "char", "Object": "object"}

        def parse(values: list[str]) -> tuple[tuple[str, ...], tuple[object, ...], tuple[tuple[str, int], ...]] | None:
            values = [value for value in values if value]
            position = 0

            def type_node() -> tuple[tuple[str, ...], tuple[object, ...], tuple[tuple[str, int], ...]] | None:
                nonlocal position
                if position + 1 < len(values) and values[position] == "global" and values[position + 1] == "::":
                    position += 2
                parts: list[str] = []
                arguments: list[object] = []
                if position < len(values) and values[position] == "(":
                    position += 1
                    tuple_items: list[object] = []
                    has_comma = False
                    while True:
                        element = type_node()
                        if element is None:
                            return None
                        element_name = None
                        if (position < len(values)
                                and re.fullmatch(r"@?[A-Za-z_][A-Za-z_0-9]*", values[position])
                                and values[position] not in {"in", "out", "ref"}):
                            element_name = values[position].removeprefix("@")
                            position += 1
                        tuple_items.append((element, element_name))
                        if position >= len(values):
                            return None
                        if values[position] == ",":
                            has_comma = True
                            position += 1
                            continue
                        if values[position] != ")" or not has_comma:
                            return None
                        position += 1
                        break
                    parts = ["<tuple>"]
                    arguments = tuple_items
                else:
                    if position >= len(values) or not re.fullmatch(r"@?[A-Za-z_][A-Za-z_0-9]*", values[position]):
                        return None
                    parts.append(aliases.get(values[position].removeprefix("@"), values[position].removeprefix("@")))
                    position += 1
                    while position < len(values) and values[position] == ".":
                        position += 1
                        if position >= len(values) or not re.fullmatch(r"@?[A-Za-z_][A-Za-z_0-9]*", values[position]):
                            return None
                        parts.append(aliases.get(values[position].removeprefix("@"), values[position].removeprefix("@")))
                        position += 1
                if parts != ["<tuple>"] and position < len(values) and values[position] == "<":
                    position += 1
                    while True:
                        argument = type_node()
                        if argument is None:
                            return None
                        arguments.append(argument)
                        if position >= len(values):
                            return None
                        if values[position] == ",":
                            position += 1
                            continue
                        if values[position] != ">":
                            return None
                        position += 1
                        break
                suffixes: list[tuple[str, int]] = []
                while position < len(values):
                    if values[position] == "?":
                        suffixes.append(("nullable", 0)); position += 1
                    elif values[position] == "*":
                        suffixes.append(("pointer", 0)); position += 1
                    elif values[position] == "[":
                        position += 1; rank = 1
                        while position < len(values) and values[position] == ",":
                            rank += 1; position += 1
                        if position >= len(values) or values[position] != "]":
                            return None
                        position += 1; suffixes.append(("array", rank))
                    else:
                        break
                return (tuple(parts), tuple(arguments), tuple(suffixes))

            root = type_node()
            return root if root is not None and position == len(values) else None

        def source_type_display(fact: dict[str, object]) -> str:
            span = _compiler_span(fact.get("source"))
            if span is None:
                raise AtlasError("compiler interface source type has no exact lexical anchor; no supplement published")
            cache_key = (span[0], span[1], span[2])
            cached = bodyless_source_type_displays.get(cache_key)
            if cached is not None:
                return cached
            source_fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
            try:
                evidence = _read_working_file(source_fd, span[0], collect_source=True)
            finally:
                os.close(source_fd)
            source_bytes = evidence.get("_source_bytes")
            if (not isinstance(source_bytes, bytes)
                    or evidence.get("sha256") != fact.get("source", {}).get("sha256")):
                raise AtlasError("compiler interface source type changed during validation; no supplement published")
            from csharp_facts import _angle_matches, _matches
            tokens, _directives = lex(source_bytes.decode("utf-8-sig"))
            braces, angles = _matches(tokens), _angle_matches(tokens)
            from csharp_facts import _namespace_at

            def declaration_shape(owner: dict[str, object]) -> tuple[int, int, int, int | None] | None:
                owner_span = _compiler_span(owner.get("source"))
                if (owner_span is None or owner_span[0] != span[0]
                        or owner.get("source", {}).get("sha256") != evidence.get("sha256")):
                    return None
                starts = [index for index, token in enumerate(tokens)
                          if token.start == owner_span[1] and token.value in {"class", "interface", "struct", "record"}]
                if len(starts) != 1:
                    return None
                keyword_index = starts[0]
                name_index = keyword_index + 1
                if tokens[keyword_index].value == "record" and name_index < len(tokens) and tokens[name_index].value in {"class", "struct"}:
                    name_index += 1
                while name_index < len(tokens) and tokens[name_index].kind != "identifier":
                    name_index += 1
                if (name_index >= len(tokens) or tokens[name_index].value.removeprefix("@") != owner.get("name")
                        or tokens[name_index].end != owner_span[2]
                        or _namespace_at(tokens, keyword_index, braces) != str(owner.get("namespace") or "")):
                    return None
                cursor = name_index + 1
                actual_arity = 0
                if cursor < len(tokens) and tokens[cursor].value == "<" and cursor in angles:
                    parameter_close = angles[cursor]
                    actual_arity = 1 + sum(1 for index in range(cursor + 1, parameter_close)
                                           if tokens[index].value == ",")
                    cursor = parameter_close + 1
                expected_arity = owner.get("arity")
                if (not isinstance(expected_arity, int) or isinstance(expected_arity, bool)
                        or expected_arity != actual_arity):
                    return None
                angle = square = paren = 0
                terminator = None
                for index in range(cursor, len(tokens)):
                    value = tokens[index].value
                    if value == "(" : paren += 1
                    elif value == ")": paren = max(0, paren - 1)
                    elif value == "[": square += 1
                    elif value == "]": square = max(0, square - 1)
                    elif value == "<": angle += 1
                    elif value == ">": angle = max(0, angle - 1)
                    elif value in {"{", ";"} and angle == square == paren == 0:
                        terminator = index; break
                if terminator is None:
                    return None
                close = braces.get(terminator) if tokens[terminator].value == "{" else None
                return keyword_index, name_index, terminator, close

            target_shape = declaration_shape(fact)
            if target_shape is None:
                raise AtlasError("compiler interface source type is not one exact lexical declaration; no supplement published")

            def segment(owner: dict[str, object], shape: tuple[int, int, int, int | None]) -> str:
                _keyword, name_index, _terminator, _close = shape
                name = str(owner.get("name"))
                arity = owner.get("arity")
                if not isinstance(arity, int) or isinstance(arity, bool) or arity < 0:
                    raise AtlasError("compiler interface source type arity is malformed; no supplement published")
                if arity == 0:
                    return name
                open_index = name_index + 1
                close_index = angles.get(open_index)
                if close_index is None:
                    raise AtlasError("compiler interface source type parameters are not lexically bounded; no supplement published")
                parameters = [tokens[index].value.removeprefix("@") for index in range(open_index + 1, close_index)
                              if tokens[index].kind == "identifier" and tokens[index].value not in {"in", "out"}]
                if len(parameters) != arity:
                    raise AtlasError("compiler interface source type parameters disagree with lexical arity; no supplement published")
                return name + "<" + ", ".join(parameters) + ">"

            enclosing_by_physical: dict[tuple[int, int, int], tuple[int, dict[str, object], tuple[int, int, int, int | None]]] = {}
            for owner in type_facts:
                owner_span = _compiler_span(owner.get("source"))
                if owner_span is None or owner_span[0] != span[0] or owner_span[1] >= span[1]:
                    continue
                shape = declaration_shape(owner)
                if shape is None or shape[3] is None:
                    continue
                if tokens[shape[2]].start < span[1] < tokens[shape[3]].end:
                    physical_owner = (tokens[shape[1]].start, tokens[shape[2]].start, tokens[shape[3]].end)
                    enclosing_by_physical.setdefault(physical_owner, (owner_span[1], owner, shape))
            enclosing = list(enclosing_by_physical.values())
            enclosing.sort(key=lambda item: item[0])
            namespace = str(fact.get("namespace") or "")
            parts = [segment(owner, shape) for _start, owner, shape in enclosing]
            parts.append(segment(fact, target_shape))
            result = "global::" + (namespace + "." if namespace else "") + ".".join(parts)
            bodyless_source_type_displays[cache_key] = result
            return result

        source = parse(source_values)
        compiler_tokens = [token.value for token in lex(compiler_type)[0]]
        compiler = parse(compiler_tokens)
        if source is None or compiler is None:
            return False

        def source_identity(name: tuple[str, ...], compiler_name: tuple[str, ...]) -> bool:
            if len(name) > 1:
                return name == compiler_name
            leaf = name[-1]
            if leaf not in known_source_type_names:
                matches = [fact for fact in type_facts if fact.get("name") == leaf and fact.get("arity") == 0]
                if matches:
                    # The saved lexical index can contain multiple anchors for
                    # one C# declaration (notably `record struct`, whose
                    # `record` and `struct` keywords each produce a fact).
                    # Reconstruct every full lexical identity from its exact
                    # source anchor and collapse only identical identities;
                    # type_id is intentionally not used as a deduplication key.
                    identities: set[tuple[str, ...]] = set()
                    for fact in matches:
                        fact_span = _compiler_span(fact.get("source"))
                        if fact_span is None:
                            raise AtlasError("compiler interface source type has no exact lexical anchor; no supplement published")
                        source_fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            source_evidence = _read_working_file(source_fd, fact_span[0], collect_source=True)
                        finally:
                            os.close(source_fd)
                        if (not isinstance(source_evidence.get("_source_bytes"), bytes)
                                or source_evidence.get("sha256") != fact.get("source", {}).get("sha256")):
                            raise AtlasError("compiler interface source type changed during validation; no supplement published")
                        canonical_text = source_type_display(fact)
                        canonical = parse([token.value for token in lex(canonical_text)[0]])
                        if canonical is None:
                            raise AtlasError("compiler interface source type identity is malformed; no supplement published")
                        identities.add(canonical[0])
                    known_source_type_names[leaf] = next(iter(identities)) if len(identities) == 1 else None
                else:
                    known_source_type_names[leaf] = ()
            canonical_name = known_source_type_names[leaf]
            if canonical_name:
                return canonical_name == compiler_name
            if canonical_name is None:
                return False
            return bool(compiler_name) and leaf == compiler_name[-1]

        def equivalent(left: tuple[tuple[str, ...], tuple[object, ...], tuple[tuple[str, int], ...]],
                       right: tuple[tuple[str, ...], tuple[object, ...], tuple[tuple[str, int], ...]]) -> bool:
            left_name, left_arguments, left_suffixes = left
            right_name, right_arguments, right_suffixes = right
            if left_name == ("<tuple>",) or right_name == ("<tuple>",):
                if left_name != right_name or left_suffixes != right_suffixes or len(left_arguments) != len(right_arguments):
                    return False
                return all(isinstance(left_item, tuple) and isinstance(right_item, tuple)
                           and left_item[1] == right_item[1]
                           and equivalent(left_item[0], right_item[0])
                           for left_item, right_item in zip(left_arguments, right_arguments))
            names_match = source_identity(left_name, right_name)
            return (names_match and len(left_arguments) == len(right_arguments)
                    and all(equivalent(a, b) for a, b in zip(left_arguments, right_arguments))
                    and left_suffixes == right_suffixes)

        return equivalent(source, compiler)

    def signature_parameter_part(signature: str) -> list[str]:
        open_paren = signature.find("(")
        close_marker = signature.find(")->", open_paren + 1)
        if open_paren < 0 or close_marker < 0:
            raise AtlasError("compiler interface signature is malformed; no supplement published")
        body = signature[open_paren + 1:close_marker]
        if not body:
            return []
        pieces: list[str] = []
        start = angle = square = paren = 0
        for index, value in enumerate(body):
            if value == "," and angle == square == paren == 0:
                pieces.append(body[start:index]); start = index + 1; continue
            if value == "<": angle += 1
            elif value == ">": angle = max(0, angle - 1)
            elif value == "[": square += 1
            elif value == "]": square = max(0, square - 1)
            elif value == "(": paren += 1
            elif value == ")": paren = max(0, paren - 1)
        pieces.append(body[start:])
        return pieces

    def signature_agrees_with_parameters(signature: object, parameters: object) -> bool:
        if not isinstance(signature, str) or not isinstance(parameters, list):
            return False
        actual = signature_parameter_part(signature)
        if actual != parameters:
            return False
        return True

    def source_parameter_signatures(text: str, method_name: str) -> list[str]:
        tokens, _directives = lex(text)
        name_index = next((index for index, token in enumerate(tokens[:-1])
                           if token.value.removeprefix("@") == method_name and tokens[index + 1].value == "("), None)
        if name_index is None:
            raise AtlasError("compiler interface source declaration has no exact named parameter list; no supplement published")
        opening = name_index + 1; depth = 0; closing = None
        for index in range(opening, len(tokens)):
            if tokens[index].value == "(": depth += 1
            elif tokens[index].value == ")":
                depth -= 1
                if depth == 0:
                    closing = index; break
        if closing is None:
            raise AtlasError("compiler interface source parameter list is unclosed; no supplement published")
        groups: list[list[str]] = [[]]
        angle = square = paren = brace = 0
        for token in tokens[opening + 1:closing]:
            value = token.value
            if value == "," and angle == square == paren == brace == 0:
                groups.append([]); continue
            groups[-1].append(value)
            if value == "<": angle += 1
            elif value == ">": angle = max(0, angle - 1)
            elif value == "[": square += 1
            elif value == "]": square = max(0, square - 1)
            elif value == "(": paren += 1
            elif value == ")": paren = max(0, paren - 1)
            elif value == "{": brace += 1
            elif value == "}": brace = max(0, brace - 1)
        if len(groups) == 1 and not groups[0]:
            return []
        result: list[str] = []
        modifiers = {"this", "params", "scoped", "ref", "out", "in", "readonly"}
        ref_kinds = {"ref": "Ref", "out": "Out", "in": "In"}
        for group in groups:
            before_default = []
            depth_angle = depth_square = depth_paren = 0
            for value in group:
                if value == "=" and depth_angle == depth_square == depth_paren == 0:
                    break
                before_default.append(value)
                if value == "<": depth_angle += 1
                elif value == ">": depth_angle = max(0, depth_angle - 1)
                elif value == "[": depth_square += 1
                elif value == "]": depth_square = max(0, depth_square - 1)
                elif value == "(": depth_paren += 1
                elif value == ")": depth_paren = max(0, depth_paren - 1)
            ids = [index for index, value in enumerate(before_default) if re.fullmatch(r"@?[A-Za-z_][A-Za-z_0-9]*", value)]
            if len(ids) < 2:
                raise AtlasError("compiler interface source parameter shape is outside the supported lexical form; no supplement published")
            parameter_name_index = ids[-1]
            prefix = before_default[:parameter_name_index]
            ref_kind = next((ref_kinds[value] for value in prefix if value in ref_kinds), "None")
            type_values = [value for value in prefix if value not in modifiers]
            result.append(ref_kind + ":" + normalized_type(type_values))
        return result

    def source_return_signature(text: str, method_name: str) -> str:
        tokens, _directives = lex(text)
        index = next((position for position, token in enumerate(tokens[:-1])
                      if token.value.removeprefix("@") == method_name and tokens[position + 1].value == "("), None)
        if index is None:
            raise AtlasError("compiler interface source declaration has no exact return type; no supplement published")
        modifiers = {"public", "protected", "private", "internal", "new", "static", "abstract", "virtual",
                     "override", "sealed", "extern", "unsafe", "async", "partial"}
        type_values = [token.value for token in tokens[:index] if token.value not in modifiers]
        if not type_values:
            raise AtlasError("compiler interface source declaration has no return type; no supplement published")
        return normalized_type(type_values)

    def verify_source_signature(binding: dict[str, object], *, caller_id: str, call_start: int) -> None:
        candidate_identity = str(binding["candidate_identity"])
        member_name = str(binding["bound_interface_signature"]).split("(", 1)[0].split("`", 1)[0]
        if not signature_agrees_with_parameters(binding.get("bound_interface_signature"),
                                                binding.get("bound_interface_parameters")):
            raise AtlasError("compiler interface bound signature disagrees with its parameter evidence; no supplement published")
        member_key = f"interface:{caller_id}:{call_start}:{candidate_identity}:bound_interface_member_source"
        member_text = snippet_by_id.get(member_key, "")
        member_actual = source_parameter_signatures(member_text, member_name)
        expected = binding.get("bound_interface_parameters")
        if not isinstance(expected, list) or any(not isinstance(item, str) or ":" not in item for item in expected):
            raise AtlasError("compiler interface parameter signature is malformed; no supplement published")
        expected_parameters: list[tuple[str, str]] = []
        for item in expected:
            ref_kind, type_name = item.split(":", 1)
            expected_parameters.append((ref_kind, type_name))
        if (len(member_actual) != len(expected_parameters)
                or any(actual.split(":", 1)[0] != expected_ref_kind
                       or not source_type_matches_compiler(
                           [token.value for token in lex(actual.split(":", 1)[1])[0]],
                           expected_type)
                       for actual, (expected_ref_kind, expected_type) in zip(member_actual, expected_parameters))):
            member_span = _compiler_span(binding.get("bound_interface_member_source"))
            member_path = member_span[0] if member_span else "?"
            member_offset = member_span[1] if member_span else -1
            raise AtlasError(
                "compiler interface member source overload disagrees with the compiler-bound parameter signature; "
                f"member={binding.get('bound_interface_member')!r} source={member_path}:{member_offset} "
                f"source_parameters={member_actual[:40]!r} source_parameter_count={len(member_actual)} "
                f"bound_interface_parameters={[item[:160] for item in expected[:40]]!r} "
                f"bound_interface_parameter_count={len(expected)} "
                f"bound_interface_signature={binding.get('bound_interface_signature')!r}; no supplement published")
        expected_return_text = str(binding["bound_interface_signature"]).rsplit(")->", 1)[1]
        expected_return = normalized_type([token.value for token in lex(expected_return_text)[0]])
        actual_member_return = source_return_signature(member_text, member_name)
        if not source_type_matches_compiler([token.value for token in lex(actual_member_return)[0]], expected_return_text):
            actual_tokens = [token.value for token in lex(actual_member_return)[0]]
            member_span = _compiler_span(binding.get("bound_interface_member_source"))
            member_path = member_span[0] if member_span else "?"
            member_offset = member_span[1] if member_span else -1
            raise AtlasError(
                "compiler interface member source return type disagrees with its compiler-bound signature; "
                f"member={binding.get('bound_interface_member')!r} source={member_path}:{member_offset} "
                f"source_return_tokens={actual_tokens[:80]!r} source_return_token_count={len(actual_tokens)} "
                f"compiler_return_type={expected_return_text!r}; no supplement published")
        if binding.get("bound_interface_member") != str(binding.get("bound_interface_type")) + "." + str(binding.get("bound_interface_signature")):
            raise AtlasError("compiler interface member label disagrees with its declaring type and signature; no supplement published")
        declaration_key = f"interface:{caller_id}:{call_start}:{candidate_identity}:bound_interface_declaration_source"
        declaration_tokens, _directives = lex(snippet_by_id.get(declaration_key, ""))
        expected_type_name = str(binding.get("bound_interface_type", "")).rsplit(".", 1)[-1]
        opening = next((index for index, token in enumerate(declaration_tokens) if token.value == "{"), None)
        if (len(declaration_tokens) < 3 or declaration_tokens[0].value != "interface"
                or declaration_tokens[1].value.removeprefix("@") != expected_type_name or opening is None):
            raise AtlasError("compiler interface declaration source has the wrong exact owner; no supplement published")
        depth = 0; closing = None
        for index in range(opening, len(declaration_tokens)):
            if declaration_tokens[index].value == "{": depth += 1
            elif declaration_tokens[index].value == "}":
                depth -= 1
                if depth == 0:
                    closing = index; break
        if closing != len(declaration_tokens) - 1:
            raise AtlasError("compiler interface declaration anchor does not end at its owner's closing brace; no supplement published")
        if binding.get("implementation_signature") is not None:
            implementation_name = str(binding["implementation_signature"]).split("(", 1)[0].split("`", 1)[0]
            implementation_key = f"interface:{caller_id}:{call_start}:{candidate_identity}:implementation_method_source"
            implementation_actual = source_parameter_signatures(snippet_by_id.get(implementation_key, ""), implementation_name)
            implementation_expected = binding.get("implementation_parameters")
            if not isinstance(implementation_expected, list):
                raise AtlasError("compiler interface implementation parameter signature is malformed; no supplement published")
            if not signature_agrees_with_parameters(binding.get("implementation_signature"), implementation_expected):
                raise AtlasError("compiler interface implementation signature disagrees with its parameter evidence; no supplement published")
            implementation_parameters: list[tuple[str, str]] = []
            for item in implementation_expected:
                if not isinstance(item, str) or ":" not in item:
                    raise AtlasError("compiler interface implementation parameter signature is malformed; no supplement published")
                ref_kind, type_name = item.split(":", 1)
                implementation_parameters.append((ref_kind, type_name))
            if (len(implementation_actual) != len(implementation_parameters)
                    or any(actual.split(":", 1)[0] != expected_ref_kind
                           or not source_type_matches_compiler(
                               [token.value for token in lex(actual.split(":", 1)[1])[0]],
                               expected_type)
                           for actual, (expected_ref_kind, expected_type) in zip(implementation_actual, implementation_parameters))
                    or implementation_expected != expected):
                raise AtlasError("compiler interface implementation source disagrees with the bound interface signature; no supplement published")
            implementation_return_text = str(binding["implementation_signature"]).rsplit(")->", 1)[1]
            implementation_return = normalized_type([token.value for token in lex(implementation_return_text)[0]])
            if not source_type_matches_compiler(
                    [token.value for token in lex(source_return_signature(snippet_by_id.get(implementation_key, ""), implementation_name))[0]],
                    implementation_return_text):
                raise AtlasError("compiler interface implementation source return type disagrees with its compiler-bound signature; no supplement published")
            if implementation_return != expected_return:
                raise AtlasError("compiler interface implementation return type disagrees with the bound member; no supplement published")

    for item in collections["unsupported"]:
        if item.get("kind") != "unsupported_interface_candidate":
            continue
        binding = item["interface_binding"]
        call_span = _compiler_span(item["call_site_source"])
        assert call_span is not None
        candidate_identity = str(binding["candidate_identity"])
        verify_source_signature(binding, caller_id=str(item["caller_node_id"]), call_start=call_span[1])
        name_key = f"interface:{item['caller_node_id']}:{call_span[1]}:{candidate_identity}:bound_interface_member_name_source"
        name_tokens, _directives = lex(snippet_by_id.get(name_key, ""))
        method_name = str(binding["bound_interface_signature"]).split("(", 1)[0].split("`", 1)[0]
        declaration_key = f"interface:{item['caller_node_id']}:{call_span[1]}:{candidate_identity}:bound_interface_declaration_source"
        declaration_tokens, _directives = lex(snippet_by_id.get(declaration_key, ""))
        if (len(name_tokens) != 1 or name_tokens[0].value.removeprefix("@") != method_name
                or len(declaration_tokens) < 3 or declaration_tokens[0].value != "interface"
                or not any(token.value == "{" for token in declaration_tokens)
                or declaration_tokens[-1].value != "}"):
            raise AtlasError("compiler interface exclusion member is outside its exact interface declaration; no supplement published")

    for edge in collections["edges"]:
        key = f"edge-callsite:{edge['caller_node_id']}:{_compiler_span(edge['call_site_source'])[1]}"
        text = snippet_by_id.get(key, "")
        tokens, _directives = lex(text)
        if len(tokens) < 3 or tokens[-1].value != ")":
            raise AtlasError("compiler source-call graph callsite is not an exact invocation span; no supplement published")
        depth = 0
        opening = None
        for index in range(len(tokens) - 1, -1, -1):
            if tokens[index].value == ")": depth += 1
            elif tokens[index].value == "(":
                depth -= 1
                if depth == 0:
                    opening = index
                    break
        if opening is None or opening == 0:
            raise AtlasError("compiler source-call graph callsite has no exact invocation head; no supplement published")
        called_name = tokens[opening - 1].value.removeprefix("@")
        if edge.get("dispatch_kind") == "interface_implementation_source":
            expected_name = str(edge["interface_binding"].get("bound_interface_signature", "")).split("(", 1)[0].split("`", 1)[0]
        else:
            expected_name = str(edge.get("callee_method", "")).rsplit(".", 1)[-1].split("(", 1)[0]
        if called_name != expected_name:
            raise AtlasError("compiler source-call graph callsite head does not match its callee; impact refused")
        binding = edge.get("interface_binding")
        if isinstance(binding, dict):
            verify_source_signature(binding, caller_id=str(edge["caller_node_id"]),
                                    call_start=_compiler_span(edge["call_site_source"])[1])
            member_span = _compiler_span(binding.get("bound_interface_member_name_source"))
            candidate_identity = str(binding["candidate_identity"])
            member_key = f"interface:{edge['caller_node_id']}:{_compiler_span(edge['call_site_source'])[1]}:{candidate_identity}:bound_interface_member_name_source"
            member_tokens, _directives = lex(snippet_by_id.get(member_key, ""))
            expected_member_name = str(binding.get("bound_interface_signature", "")).split("(", 1)[0].split("`", 1)[0]
            if member_span is None or len(member_tokens) != 1 or member_tokens[0].value.removeprefix("@") != expected_member_name:
                raise AtlasError("compiler interface member-name anchor does not match the bound signature; no supplement published")
            declaration_key = f"interface:{edge['caller_node_id']}:{_compiler_span(edge['call_site_source'])[1]}:{candidate_identity}:bound_interface_member_source"
            declaration_tokens, _directives = lex(snippet_by_id.get(declaration_key, ""))
            if not any(token.value.removeprefix("@") == expected_member_name for token in declaration_tokens):
                raise AtlasError("compiler interface member declaration anchor has the wrong member name; no supplement published")
            for path_key in ("candidate_to_interface_path", "candidate_to_implementation_owner_path"):
                for step_index, step in enumerate(binding[path_key]):
                    key = f"interface:{edge['caller_node_id']}:{_compiler_span(edge['call_site_source'])[1]}:{candidate_identity}:{path_key}:{step_index}:type_syntax_source"
                    syntax_tokens, _directives = lex(snippet_by_id.get(key, ""))
                    declaration_key = f"interface:{edge['caller_node_id']}:{_compiler_span(edge['call_site_source'])[1]}:{candidate_identity}:{path_key}:{step_index}:from_type_declaration_source"
                    declaration_tokens, _directives = lex(snippet_by_id.get(declaration_key, ""))
                    from_type_name = str(step.get("from_type", "")).rsplit(".", 1)[-1].split("`", 1)[0]
                    type_keywords = {"class", "interface", "struct", "record"}
                    declaration_keyword_index = next((index for index, token in enumerate(declaration_tokens[:8])
                                                       if token.value in type_keywords), None)
                    record_class = (declaration_keyword_index is not None
                                    and declaration_tokens[declaration_keyword_index].value == "record"
                                    and declaration_keyword_index + 1 < len(declaration_tokens)
                                    and declaration_tokens[declaration_keyword_index + 1].value in {"class", "struct"})
                    declaration_name_index = (declaration_keyword_index + 2 if record_class
                                              else declaration_keyword_index + 1 if declaration_keyword_index is not None else 0)
                    allowed_modifiers = {"public", "protected", "private", "internal", "new", "static", "abstract",
                                         "sealed", "partial", "unsafe", "readonly", "ref", "file"}
                    if (len(declaration_tokens) < 4
                            or declaration_keyword_index is None
                            or declaration_name_index >= len(declaration_tokens)
                            or any(token.value not in allowed_modifiers for token in declaration_tokens[:declaration_keyword_index])
                            or declaration_tokens[declaration_name_index].value.removeprefix("@") != from_type_name):
                        raise AtlasError("compiler interface membership declaration is not one exact lexical type owner; no supplement published")
                    body_open = next((index for index in range(declaration_name_index + 1, len(declaration_tokens))
                                      if declaration_tokens[index].value == "{"), None)
                    depth = 0; body_close = None
                    if body_open is not None:
                        for index in range(body_open, len(declaration_tokens)):
                            if declaration_tokens[index].value == "{": depth += 1
                            elif declaration_tokens[index].value == "}":
                                depth -= 1
                                if depth == 0:
                                    body_close = index; break
                    if body_open is None or body_close != len(declaration_tokens) - 1:
                        raise AtlasError("compiler interface membership declaration is not one exact lexical type owner; no supplement published")
                    target_name = str(step.get("to_type_id", "")).split(".")[-1].split("`")[0]
                    if not syntax_tokens or not any(token.value.removeprefix("@") == target_name for token in syntax_tokens):
                        raise AtlasError(f"compiler interface membership syntax does not name its target type: target={target_name!r} tokens={[token.value for token in syntax_tokens]!r}; no supplement published")
                    base_key = f"interface:{edge['caller_node_id']}:{_compiler_span(edge['call_site_source'])[1]}:{candidate_identity}:{path_key}:{step_index}:base_list_source"
                    base_tokens, _directives = lex(snippet_by_id.get(base_key, ""))
                    syntax_values = [token.value for token in syntax_tokens]
                    base_values = [token.value for token in base_tokens]
                    matches = [index for index in range(len(base_values) - len(syntax_values) + 1)
                               if base_values[index:index + len(syntax_values)] == syntax_values]
                    declaration_values = [token.value for token in declaration_tokens[:body_open]]
                    base_matches = [index for index in range(len(declaration_values) - len(base_values) + 1)
                                    if declaration_values[index:index + len(base_values)] == base_values]
                    slots: list[list[str]] = []
                    if base_values and base_values[0] == ":":
                        slot: list[str] = []; angle = square = paren = 0
                        for value in base_values[1:]:
                            if value == "," and angle == square == paren == 0:
                                slots.append(slot); slot = []; continue
                            slot.append(value)
                            if value == "<": angle += 1
                            elif value == ">": angle = max(0, angle - 1)
                            elif value == "[": square += 1
                            elif value == "]": square = max(0, square - 1)
                            elif value == "(": paren += 1
                            elif value == ")": paren = max(0, paren - 1)
                        if slot: slots.append(slot)
                    if (len(matches) != 1 or len(base_matches) != 1 or syntax_values not in slots):
                        raise AtlasError("compiler interface membership source is not one exact base-list slot; no supplement published")
    for item in collections["unsupported"]:
        if item["kind"] not in {"unsupported_source_call", "unsupported_lexical_source_method"}:
            continue
        span = _compiler_span(item["call_site_source"])
        snippet = snippet_by_id.get(f"unsupported:{item['caller_node_id']}:{span[1] if span else -1}", "")
        tokens, _directives = lex(snippet)
        if len(tokens) < 3 or tokens[-1].value != ")":
            raise AtlasError("compiler source-call graph unsupported boundary is not an exact invocation; no supplement published")
        if item["kind"] == "unsupported_lexical_source_method":
            caller_id = item["caller_node_id"]
            callee_span = _compiler_span(item["callee_source"])
            callee_key = f"unsupported-callee:{caller_id}:{span[1] if span else -1}"
            callee_text = snippet_by_id.get(callee_key, "")
            callee_tokens, _directives = lex(callee_text)
            callee_name = str(item["callee_method"]).split("(", 1)[0].rsplit(".", 1)[-1]
            depth = 0
            opening = None
            for index in range(len(tokens) - 1, -1, -1):
                if tokens[index].value == ")": depth += 1
                elif tokens[index].value == "(":
                    depth -= 1
                    if depth == 0:
                        opening = index
                        break
            if opening is None or opening == 0 or tokens[opening - 1].value.removeprefix("@") != callee_name:
                raise AtlasError("compiler lexical boundary callsite head does not match its callee; no supplement published")
            names = [index for index, token in enumerate(callee_tokens) if token.value.removeprefix("@") == callee_name]
            if (callee_span is None or not names or not any(
                    index + 1 < len(callee_tokens) and callee_tokens[index + 1].value == "(" for index in names)
                    or not any(token.value in {"=>", "{"} for token in callee_tokens)
                    or callee_tokens[-1].value not in {";", "}"}):
                raise AtlasError("compiler lexical boundary callee declaration is not source-verifiable; no supplement published")
    for item in collections["nested_body_exclusions"]:
        span = _compiler_span(item["source"])
        snippet = snippet_by_id.get(f"nested:{item['caller_node_id']}:{span[1] if span else -1}", "")
        tokens, _directives = lex(snippet)
        values = [token.value for token in tokens]
        if item["nested_body_kind"] == "anonymous_function":
            if "=>" not in values and "delegate" not in values:
                raise AtlasError("compiler source-call graph anonymous-function boundary is not exact; no supplement published")
        else:
            if not any(token.value == "(" and any(value in {"=>", "{"} for value in values[index + 1:])
                       for index, token in enumerate(tokens)):
                raise AtlasError("compiler source-call graph local-function boundary is not exact; no supplement published")

    # Validate every node is reachable from at least one mapped route root, including roots with no calls.
    reachable = set(root_nodes)
    pending = list(root_nodes)
    cursor = 0
    while cursor < len(pending):
        current = pending[cursor]; cursor += 1
        for edge in adjacency.get(current, []):
            target = str(edge["callee_node_id"])
            if target not in reachable:
                reachable.add(target); pending.append(target)
    if reachable != set(node_by_id):
        raise AtlasError("compiler source-call graph contains a disconnected method node; impact refused")

    graph["nodes"] = sorted(collections["nodes"], key=lambda node: str(node["id"]))
    graph["roots"] = sorted(collections["roots"], key=lambda root: (
        str(root["route"]), str(root["http_method"]), str(root["implementation_type"]), str(root["implementation_method"])))
    graph["edges"] = sorted(collections["edges"], key=lambda edge: (
        str(edge["call_site_source"]["path"]), int(edge["call_site_source"]["span"]["start_offset"]), str(edge["caller_node_id"]),
        str((edge.get("interface_binding") or {}).get("candidate_identity", ""))))
    graph["unsupported"] = sorted(collections["unsupported"], key=lambda item: (
        str(item["call_site_source"]["path"]), int(item["call_site_source"]["span"]["start_offset"]), str(item["caller_node_id"]),
        str((item.get("interface_binding") or {}).get("candidate_identity", ""))))
    graph["nested_body_exclusions"] = sorted(collections["nested_body_exclusions"], key=lambda item: (
        str(item["source"]["path"]), int(item["source"]["span"]["start_offset"]), str(item["caller_node_id"])))
    if bind:
        for _attempt in range(4):
            actual_graph_bytes = len(_canonical_json(graph))
            if counts["serialized_graph_bytes"] == actual_graph_bytes:
                break
            counts["serialized_graph_bytes"] = actual_graph_bytes
        else:
            raise AtlasError("compiler source-call graph serialized-byte count did not stabilize; no supplement published")
    else:
        actual_graph_bytes = len(_canonical_json(graph))
    if not bind and counts["serialized_graph_bytes"] != actual_graph_bytes:
        raise AtlasError("compiler source-call graph serialized-byte count disagrees with persisted graph; impact refused")
    if actual_graph_bytes > SOURCE_CALL_GRAPH_CAPS["serialized_graph_bytes"]:
        raise AtlasError("compiler source-call graph serialized-output cap exceeded; no supplement published")

    direct_edges: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    edges_by_caller: dict[str, list[dict[str, object]]] = {}
    unsupported_by_caller: dict[str, list[dict[str, object]]] = {}
    projected_count = 0
    for edge in graph["edges"]:
        edges_by_caller.setdefault(str(edge["caller_node_id"]), []).append(edge)
    for item in graph["unsupported"]:
        unsupported_by_caller.setdefault(str(item["caller_node_id"]), []).append(item)
    for root in graph["roots"]:
        route_identity = {"route": root["route"], "http_method": root["http_method"],
                          "implementation_type": root["implementation_type"],
                          "implementation_method": root["implementation_method"]}
        root_id = str(root["root_node_id"])
        for edge in edges_by_caller.get(root_id, []):
            projected_count += 1
            if projected_count > SOURCE_CALL_GRAPH_CAPS["compatibility_records"]:
                raise AtlasError("compiler source-call compatibility projection cap exceeded; no supplement published")
            direct_edges.append({**route_identity, "caller_method": root["root_method"],
                                 "caller_source": root["root_source"], "callee_method": edge["callee_method"],
                                 "callee_containing_type": edge["callee_containing_type"],
                                 "callee_source": edge["callee_source"], "call_site_source": edge["call_site_source"],
                                 "dispatch_kind": edge["dispatch_kind"], "compiler_binding_confirmed": True,
                                 "runtime_reachability_proven": False, "runtime_DI_selection_proven": False,
                                 **({"interface_binding": edge["interface_binding"]} if edge.get("interface_binding") else {})})
        for item in unsupported_by_caller.get(root_id, []):
            projected_count += 1
            if projected_count > SOURCE_CALL_GRAPH_CAPS["compatibility_records"]:
                raise AtlasError("compiler source-call compatibility projection cap exceeded; no supplement published")
            unresolved.append({**route_identity, "caller_method": item["caller_method"],
                               "caller_source": item["caller_source"],
                               "kind": "unsupported_handler_source_call" if item["kind"] == "unsupported_source_call" else item["kind"],
                               "source": item["call_site_source"], "reason": item["reason"],
                               **({"interface_binding": item["interface_binding"]} if item.get("interface_binding") else {})})

    if counts["compatibility_records"] != projected_count:
        raise AtlasError("compiler source-call graph compatibility count disagrees with root-expanded projections; no supplement published")

    if bind:
        return graph, direct_edges, unresolved
    return graph, direct_edges, unresolved


def _verify_compiler_source_call_unresolved(snapshot: dict[str, object], relationships: list[dict[str, object]],
                                            records: object) -> list[dict[str, object]]:
    """Require every unsupported handler call to retain one exact route/handler identity."""
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise AtlasError("Roslyn returned malformed source-call limitations; no supplement published")
    files = {str(entry.get("path")): entry for entry in snapshot.get("files", []) if isinstance(entry, dict)}
    verified: list[dict[str, object]] = []
    for item in records:
        for key in ("route", "http_method", "implementation_type", "implementation_method"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise AtlasError(f"compiler source-call limitation has invalid {key}; no supplement published")
        matches = [relation for relation in relationships
                   if all(relation.get(key) == item.get(key) for key in
                          ("route", "http_method", "implementation_type", "implementation_method"))]
        if len(matches) != 1:
            raise AtlasError("compiler source-call limitation must bind to exactly one mapped handler relationship: "
                             f"matches={len(matches)} route={item.get('route')!r}; no supplement published")
        anchor = item.get("source")
        span = _compiler_span(anchor)
        saved = files.get(span[0]) if span is not None else None
        if (span is None or not isinstance(anchor, dict) or not isinstance(anchor.get("sha256"), str)
                or saved is None or saved.get("presence") != "present" or saved.get("type") != "file"
                or saved.get("sha256") != anchor["sha256"]):
            raise AtlasError("compiler source-call limitation has an unverified source anchor; no supplement published")
        verified.append(dict(item))
    return sorted(verified, key=lambda item: (str(item.get("route")), str(item.get("http_method")),
                                               str(item.get("implementation_type")), str(item.get("implementation_method")),
                                               str(item.get("source", {}).get("path")),
                                               int(item.get("source", {}).get("span", {}).get("start_offset", 0))))


def _compiler_build_extractor(temp_root: Path, env: dict[str, str], dotnet: Path) -> Path:
    source = Path(__file__).resolve().parent / "compiler"
    if not (source / "WorkspaceProgram.cs").is_file() or not (source / "extractor.csproj").is_file():
        raise AtlasError("shipped Roslyn compiler extractor source is incomplete")
    work = temp_root / "extractor"
    work.mkdir()
    shutil.copy2(source / "WorkspaceProgram.cs", work / "WorkspaceProgram.cs")
    shutil.copy2(source / "extractor.csproj", work / "extractor.csproj")
    empty_feed = temp_root / "empty-feed"
    empty_feed.mkdir()
    config = temp_root / "NuGet.Config"
    config.write_text("<?xml version=\"1.0\" encoding=\"utf-8\"?><configuration><packageSources><clear/><add key=\"empty\" value=\"" + str(empty_feed) + "\"/></packageSources></configuration>", encoding="utf-8")
    restore = subprocess.run([str(dotnet), "restore", str(work / "extractor.csproj"), "--configfile", str(config), "--ignore-failed-sources"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, check=False)
    if restore.returncode:
        raise AtlasError(f"offline Roslyn extractor restore failed: {(restore.stderr or restore.stdout).strip()}")
    build = subprocess.run([str(dotnet), "build", str(work / "extractor.csproj"), "--no-restore", "--configuration", "Release"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, check=False)
    if build.returncode:
        raise AtlasError(f"Roslyn extractor build failed: {(build.stderr or build.stdout).strip()}")
    executable = work / "bin" / "Release" / "net10.0" / "extractor.dll"
    if not executable.is_file():
        raise AtlasError("Roslyn extractor build produced no executable")
    sdk_version = subprocess.run([str(dotnet), "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, check=False).stdout.strip()
    sdk_format = dotnet.parent / "sdk" / sdk_version / "DotnetTools" / "dotnet-format"
    build_host = sdk_format / "BuildHost-netcore"
    if not (build_host / "Microsoft.CodeAnalysis.Workspaces.MSBuild.BuildHost.dll").is_file():
        build_host = None
    if build_host is None:
        raise AtlasError("installed SDK has no cached Roslyn MSBuild build host")
    shutil.copytree(build_host, executable.parent / "BuildHost-netcore")
    return executable


def compiler_index(db_arg: str, repo_arg: str, project_relative: str, framework: str) -> dict[str, object]:
    """Create one immutable Roslyn supplement for the unique current lexical snapshot."""
    if Path(project_relative).is_absolute() or any(part in {"", ".", ".."} for part in project_relative.split("/")):
        raise AtlasError(f"compiler project must be a safe repository-relative path: {project_relative!r}")
    if not project_relative.endswith(".csproj"):
        raise AtlasError("compiler project must name one .csproj file")
    db_path = Path(db_arg).expanduser().absolute()
    if not db_path.is_file():
        raise AtlasError(f"database does not exist: {db_path}")
    snapshot, _snapshots, extractor_identity, live = _current_route_snapshot(db_path, repo_arg)
    _validate_snapshot_fingerprint(snapshot, str(snapshot.get("snapshot_id")))
    lexical_manifest = _compiler_lexical_method_manifest(snapshot, extractor_identity)
    lexical_manifest_hash = hashlib.sha256(_canonical_json(lexical_manifest)).hexdigest()
    files = snapshot.get("files", [])
    files_by_path = {str(entry["path"]): entry for entry in files if isinstance(entry, dict) and isinstance(entry.get("path"), str)}
    projects = [entry for entry in files if isinstance(entry, dict) and entry.get("path") == project_relative
                and entry.get("presence") == "present" and entry.get("type") == "file"]
    if len(projects) != 1:
        raise AtlasError(f"compiler project must match exactly one current tracked file: {project_relative}; matches={len(projects)}")
    project_entry = projects[0]
    project_dir = Path(project_relative).parent.as_posix()
    if project_dir == ".":
        project_dir = ""
    generated_relative = f"{project_dir + '/' if project_dir else ''}obj"
    root = Path(live["repository_root"])
    dotnet_arg = os.environ.get("ATLAS_DOTNET") or shutil.which("dotnet")
    if not dotnet_arg:
        raise AtlasError("compiler-index requires a local dotnet executable; set ATLAS_DOTNET to its absolute path")
    dotnet = Path(dotnet_arg).expanduser().resolve(strict=True)
    package_cache = Path(os.environ.get("NUGET_PACKAGES", Path.home() / ".nuget" / "packages")).expanduser().absolute()
    with tempfile.TemporaryDirectory(prefix="atlas-compiler-") as temp_name:
        temp_root = Path(temp_name)
        mirror = temp_root / "mirror"
        mirror.mkdir()
        tracked_manifest, generated_manifest = _compiler_copy_inputs(root, snapshot, mirror, generated_relative)
        if not generated_manifest or not any(item.get("logical_path") == f"{generated_relative}/project.assets.json" for item in generated_manifest):
            raise AtlasError(f"compiler-index requires current offline project assets under {generated_relative}; no target restore or network access was attempted")
        mirror_project = mirror / project_relative
        mirror_project.parent.mkdir(parents=True, exist_ok=True)
        if not mirror_project.is_file():
            raise AtlasError(f"compiler project is missing from the protected mirror: {project_relative}")
        env = _compiler_temp_env(temp_root, dotnet, package_cache)
        executable = _compiler_build_extractor(temp_root, env, dotnet)
        lexical_manifest_path = temp_root / "lexical-method-manifest.json"
        lexical_manifest_path.write_bytes(_canonical_json(lexical_manifest))
        runtime_env = dict(os.environ)
        runtime_env.pop("ATLAS_DOTNET", None)
        run = subprocess.run([str(dotnet), str(executable), str(mirror_project), str(mirror), str(root), framework,
                              str(lexical_manifest_path)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=runtime_env, check=False)
        if run.returncode:
            raise AtlasError(f"Roslyn workspace extraction failed; no supplement published: {(run.stderr or run.stdout).strip()}")
        try:
            extracted = json.loads(run.stdout)
        except json.JSONDecodeError as exc:
            raise AtlasError(f"Roslyn extractor returned invalid JSON; no supplement published: {exc}") from exc
        if not isinstance(extracted, dict):
            raise AtlasError("Roslyn extractor returned a non-object; no supplement published")
        if extracted.get("compiler_errors"):
            raise AtlasError(f"Roslyn reported compiler errors; no supplement published: {extracted['compiler_errors']}")
        if any("Error" in str(item) for item in extracted.get("workspace_diagnostics", [])):
            raise AtlasError(f"MSBuildWorkspace reported failures; no supplement published: {extracted['workspace_diagnostics']}")
        live_after = _live_inventory_identity(repo_arg)
        changed, reasons = _focus_source_identity(snapshot, live_after)
        if changed or reasons:
            raise AtlasError(f"tracked checkout changed during compiler indexing; no supplement published: {reasons}")
        generated_after = _compiler_safe_tree(root, generated_relative)
        if generated_after != generated_manifest:
            raise AtlasError(f"generated compiler inputs changed during indexing at {generated_relative}; no supplement published")
        refs = extracted.get("references")
        if not isinstance(refs, list) or any(not isinstance(ref, dict) or not isinstance(ref.get("sha256"), str) for ref in refs):
            raise AtlasError("Roslyn reference manifest is incomplete; no supplement published")
        imports = extracted.get("imports")
        toolchain = extracted.get("toolchain_assemblies")
        build_host_files = extracted.get("build_host_files")
        if not isinstance(imports, list) or not isinstance(toolchain, list) or not isinstance(build_host_files, list):
            raise AtlasError("Roslyn import or toolchain manifest is incomplete; no supplement published")
        relationships = extracted.get("relationships")
        if not isinstance(relationships, list):
            raise AtlasError("Roslyn returned a malformed relationship list; no supplement published")
        for relationship in relationships:
            if not isinstance(relationship, dict):
                raise AtlasError("Roslyn returned a malformed relationship; no supplement published")
            _verify_compiler_relationship_graph(snapshot, relationship)
            for anchor_key in ("action_source", "call_site_source", "service_parameter_source", "bound_member_source", "implementation_source"):
                anchor = relationship.get(anchor_key)
                if not isinstance(anchor, dict) or not isinstance(anchor.get("path"), str) or not isinstance(anchor.get("sha256"), str):
                    raise AtlasError(f"compiler relationship has incomplete {anchor_key}; no supplement published")
                path = str(anchor["path"])
                saved = next((entry for entry in files if isinstance(entry, dict) and entry.get("path") == path), None)
                if saved is None or saved.get("presence") != "present" or saved.get("type") != "file" or saved.get("sha256") != anchor["sha256"]:
                    raise AtlasError(f"compiler relationship anchor does not match tracked lexical snapshot: {path}; no supplement published")
                span = anchor.get("span")
                if not isinstance(span, dict) or not isinstance(span.get("start_offset"), int) or not isinstance(span.get("end_offset"), int):
                    raise AtlasError(f"compiler relationship anchor has invalid span: {path}; no supplement published")
        source_call_graph, projected_edges, projected_unresolved = _verify_compiler_source_call_graph(
            snapshot, relationships, extracted.get("source_call_graph"), root, bind=True,
            lexical_manifest=lexical_manifest)
        source_call_edges = _verify_compiler_source_call_edges(snapshot, relationships, extracted.get("source_call_edges"))
        checked_projected_edges = _verify_compiler_source_call_edges(snapshot, relationships, projected_edges)
        if _canonical_json(source_call_edges) != _canonical_json(checked_projected_edges):
            raise AtlasError("compiler direct source-call compatibility view disagrees with the complete graph; no supplement published")
        source_call_unresolved = _verify_compiler_source_call_unresolved(
            snapshot, relationships, extracted.get("source_call_unresolved"))
        checked_projected_unresolved = _verify_compiler_source_call_unresolved(snapshot, relationships, projected_unresolved)
        if _canonical_json(source_call_unresolved) != _canonical_json(checked_projected_unresolved):
            raise AtlasError("compiler direct unsupported-call compatibility view disagrees with the complete graph; no supplement published")
        input_identity = {
            "lexical_method_manifest": lexical_manifest,
            "lexical_method_manifest_sha256": lexical_manifest_hash,
            "tracked_inputs": tracked_manifest,
            "generated_inputs": generated_manifest,
            "references": refs,
            "imports": imports,
            "toolchain_assemblies": toolchain,
            "copied_tool_files": _compiler_copied_tool_files(executable.parent, str(extracted.get("sdk_path") or "")),
            "build_host_files": build_host_files,
            "shipped_tool_inputs": _compiler_shipped_tool_inputs(),
            "dotnet_host": {"path": dotnet.as_posix(), "sha256": hashlib.sha256(dotnet.read_bytes()).hexdigest()},
            "project": project_relative,
            "target_framework": framework,
            "sdk_path": extracted.get("sdk_path"),
            "roslyn_version": extracted.get("roslyn_version"),
            "language_version": extracted.get("language_version"),
            "compilation_options": extracted.get("compilation_options"),
            "parse_options": extracted.get("parse_options"),
        }
        input_hash = hashlib.sha256(_canonical_json(input_identity)).hexdigest()
        payload: dict[str, object] = {
            "supplement_schema_version": 1,
            "binding": {"snapshot_id": snapshot["snapshot_id"], "evidence_fingerprint": snapshot["evidence_fingerprint"],
                        "repository_root": root.as_posix(), "extractor_identity": extractor_identity,
                        "project_path": project_relative, "target_framework": framework},
            "input_identity": input_identity,
            "input_sha256": input_hash,
            "provenance": {key: extracted.get(key) for key in ("sdk_path", "roslyn_version", "language_version", "target_framework", "source_trees", "compiler_warnings")},
            "relationships": extracted.get("relationships", []),
            "unresolved": extracted.get("unresolved", []),
            "source_call_graph": source_call_graph,
            "source_call_edges": source_call_edges,
            "source_call_unresolved": source_call_unresolved,
            "runtime_DI_selection_proven": False,
        }
    content_hash = hashlib.sha256(_canonical_json(payload)).hexdigest()
    saved_payload = {**payload, "content_sha256": content_hash}
    serialized = _canonical_json(saved_payload).decode("ascii")
    connection = _connect_for_index(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS atlas_compiler_supplements (snapshot_id TEXT NOT NULL, project_path TEXT NOT NULL, content_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(snapshot_id,project_path), FOREIGN KEY(snapshot_id) REFERENCES atlas_snapshots(snapshot_id))")
        previous = connection.execute("SELECT content_sha256,payload_json FROM atlas_compiler_supplements WHERE snapshot_id=? AND project_path=?", (snapshot["snapshot_id"], project_relative)).fetchone()
        if previous is not None and previous != (content_hash, serialized):
            try:
                old_payload = json.loads(previous[1])
                changed_fields = sorted(key for key in set(old_payload) | set(saved_payload) if old_payload.get(key) != saved_payload.get(key))
                input_fields = sorted(key for key in set(old_payload.get("input_identity", {})) | set(input_identity)
                                      if old_payload.get("input_identity", {}).get(key) != input_identity.get(key))
            except (json.JSONDecodeError, AttributeError):
                changed_fields, input_fields = ["unreadable_previous_payload"], []
            raise AtlasError(f"compiler supplement is immutable; conflicting bytes already exist; changed_fields={changed_fields}; changed_inputs={input_fields}; old={previous[0]}; new={content_hash}")
        if previous is None:
            connection.execute("INSERT INTO atlas_compiler_supplements(snapshot_id,project_path,content_sha256,payload_json) VALUES (?,?,?,?)", (snapshot["snapshot_id"], project_relative, content_hash, serialized))
        connection.commit()
    except (sqlite3.Error, AtlasError):
        connection.rollback()
        raise
    finally:
        connection.close()
    return {"result": "compiler_indexed", "snapshot_id": snapshot["snapshot_id"], "project_path": project_relative,
            "relationship_count": len(payload["relationships"]), "unresolved_count": len(payload["unresolved"]),
            "content_sha256": content_hash, "input_sha256": input_hash, "runtime_DI_selection_proven": False}


def _current_compiler_supplements(db_path: Path, snapshot: dict[str, object], repo: Path) -> list[dict[str, object]]:
    """Load and recheck every supplement bound to this snapshot; stale records fail closed."""
    uri = db_path.absolute().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='atlas_compiler_supplements'").fetchone()
        if exists is None:
            return []
        rows = connection.execute("SELECT project_path,content_sha256,payload_json FROM atlas_compiler_supplements WHERE snapshot_id=? ORDER BY project_path", (snapshot["snapshot_id"],)).fetchall()
    output: list[dict[str, object]] = []
    for project_path, stored_hash, payload_json in rows:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise AtlasError(f"compiler supplement is corrupt for {project_path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise AtlasError(f"compiler supplement is not an object for {project_path}")
        stable = {key: value for key, value in payload.items() if key != "content_sha256"}
        actual_hash = hashlib.sha256(_canonical_json(stable)).hexdigest()
        if stored_hash != actual_hash or payload.get("content_sha256") != actual_hash:
            raise AtlasError(f"compiler supplement content hash mismatch for {project_path}")
        binding = payload.get("binding")
        if (not isinstance(binding, dict) or binding.get("snapshot_id") != snapshot.get("snapshot_id")
                or binding.get("evidence_fingerprint") != snapshot.get("evidence_fingerprint")
                or binding.get("repository_root") != repo.as_posix() or binding.get("project_path") != project_path):
            raise AtlasError(f"compiler supplement identity mismatch for {project_path}")
        inputs = payload.get("input_identity")
        if not isinstance(inputs, dict):
            raise AtlasError(f"compiler supplement input identity is missing for {project_path}")
        input_hash = hashlib.sha256(_canonical_json(inputs)).hexdigest()
        if payload.get("input_sha256") != input_hash:
            raise AtlasError(f"compiler supplement input hash mismatch for {project_path}")
        extractor_identity = binding.get("extractor_identity") if isinstance(binding, dict) else None
        expected_lexical_manifest = _compiler_lexical_method_manifest(snapshot, extractor_identity)
        expected_lexical_manifest_hash = hashlib.sha256(_canonical_json(expected_lexical_manifest)).hexdigest()
        if (inputs.get("lexical_method_manifest") != expected_lexical_manifest
                or inputs.get("lexical_method_manifest_sha256") != expected_lexical_manifest_hash):
            raise AtlasError(f"compiler supplement lexical method manifest is stale or corrupt for {project_path}")
        if inputs.get("tracked_inputs") != [{"logical_path": f"tracked/{entry['path']}", "path": entry["path"],
                                               "sha256": entry.get("sha256"), "size_bytes": entry.get("size_bytes"),
                                               "presence": entry.get("presence"), "type": entry.get("type"),
                                               "git_mode": entry.get("git_mode")}
                                              for entry in snapshot.get("files", []) if isinstance(entry, dict)]:
            raise AtlasError(f"compiler supplement tracked inputs are stale for {project_path}")
        relative_obj = str(Path(project_path).parent / "obj")
        if relative_obj.startswith("./"):
            relative_obj = relative_obj[2:]
        current_generated = _compiler_safe_tree(repo, relative_obj)
        if current_generated != inputs.get("generated_inputs"):
            raise AtlasError(f"compiler supplement generated inputs are stale for {project_path}: {relative_obj}")
        refs = inputs.get("references")
        if not isinstance(refs, list):
            raise AtlasError(f"compiler supplement references are missing for {project_path}")
        for reference in refs:
            if not isinstance(reference, dict):
                raise AtlasError(f"compiler supplement has malformed reference for {project_path}")
            display = reference.get("display")
            expected = reference.get("sha256")
            if not isinstance(display, str) or not isinstance(expected, str) or not Path(display).is_file():
                raise AtlasError(f"compiler supplement reference is missing for {project_path}: {display!r}")
            if hashlib.sha256(Path(display).read_bytes()).hexdigest() != expected:
                raise AtlasError(f"compiler supplement reference changed for {project_path}: {display}")
        for import_record in inputs.get("imports", []):
            if not isinstance(import_record, dict):
                raise AtlasError(f"compiler supplement has malformed import record for {project_path}")
            logical = import_record.get("logical_path")
            stored_path = import_record.get("path")
            expected = import_record.get("sha256")
            if not isinstance(logical, str) or not isinstance(stored_path, str) or not isinstance(expected, str):
                raise AtlasError(f"compiler supplement import identity is incomplete for {project_path}")
            if logical.startswith("repo/"):
                path = repo / stored_path
            elif logical.startswith("external/"):
                path = Path(stored_path)
            else:
                raise AtlasError(f"compiler supplement import has an unsupported durable identity for {project_path}: {logical}")
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise AtlasError(f"compiler supplement import changed or is missing for {project_path}: {logical}")
        for assembly in inputs.get("toolchain_assemblies", []):
            if not isinstance(assembly, dict) or not isinstance(assembly.get("path"), str) or not isinstance(assembly.get("sha256"), str):
                raise AtlasError(f"compiler supplement toolchain identity is incomplete for {project_path}")
            path = Path(str(assembly["path"]))
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != assembly["sha256"]:
                raise AtlasError(f"compiler supplement toolchain assembly changed or is missing for {project_path}: {path}")
        for copied in inputs.get("copied_tool_files", []):
            if not isinstance(copied, dict) or not isinstance(copied.get("path"), str) or not isinstance(copied.get("sha256"), str):
                raise AtlasError(f"compiler supplement copied SDK tool identity is malformed for {project_path}")
            path = Path(copied["path"])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != copied["sha256"]:
                raise AtlasError(f"compiler supplement copied SDK tool file changed or is missing for {project_path}: {path}")
        sdk_path = inputs.get("sdk_path")
        if not isinstance(sdk_path, str) or not sdk_path:
            raise AtlasError(f"compiler supplement SDK identity is missing for {project_path}")
        for build_host_file in inputs.get("build_host_files", []):
            if not isinstance(build_host_file, dict) or not isinstance(build_host_file.get("path"), str) or not isinstance(build_host_file.get("sha256"), str):
                raise AtlasError(f"compiler supplement BuildHost file identity is malformed for {project_path}")
            path = Path(sdk_path) / "DotnetTools" / "dotnet-format" / "BuildHost-netcore" / build_host_file["path"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != build_host_file["sha256"]:
                raise AtlasError(f"compiler supplement BuildHost file changed or is missing for {project_path}: {path}")
        if inputs.get("shipped_tool_inputs") != _compiler_shipped_tool_inputs():
            raise AtlasError(f"compiler supplement shipped extractor inputs changed for {project_path}")
        dotnet_host = inputs.get("dotnet_host")
        if not isinstance(dotnet_host, dict) or not isinstance(dotnet_host.get("path"), str) or not isinstance(dotnet_host.get("sha256"), str):
            raise AtlasError(f"compiler supplement dotnet host identity is malformed for {project_path}")
        dotnet_path = Path(dotnet_host["path"])
        if not dotnet_path.is_file() or hashlib.sha256(dotnet_path.read_bytes()).hexdigest() != dotnet_host["sha256"]:
            raise AtlasError(f"compiler supplement dotnet host changed or is missing for {project_path}: {dotnet_path}")
        relationships = payload.get("relationships")
        if not isinstance(relationships, list):
            raise AtlasError(f"compiler supplement relationships are malformed for {project_path}")
        graph, projected_edges, projected_unresolved = _verify_compiler_source_call_graph(
            snapshot, relationships, payload.get("source_call_graph"), repo, bind=False,
            lexical_manifest=expected_lexical_manifest)
        verified_edges = _verify_compiler_source_call_edges(snapshot, relationships, projected_edges)
        verified_unresolved = _verify_compiler_source_call_unresolved(snapshot, relationships, projected_unresolved)
        if (_canonical_json(payload.get("source_call_edges")) != _canonical_json(verified_edges)
                or _canonical_json(payload.get("source_call_unresolved")) != _canonical_json(verified_unresolved)):
            raise AtlasError(f"compiler supplement compatibility call views disagree with its complete graph for {project_path}")
        output.append(payload)
    return output


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
    supplements = _current_compiler_supplements(db_path, snapshot, root)
    if supplements:
        compiler_callers = []
        compiler_route_paths = []
        graph_scopes = []
        for supplement in supplements:
            relationships = supplement.get("relationships", [])
            if not isinstance(relationships, list):
                raise AtlasError("compiler supplement relationships are malformed")
            relationships_by_identity: dict[tuple[object, object, object], list[dict[str, object]]] = {}
            for relation in relationships:
                if not isinstance(relation, dict):
                    raise AtlasError("compiler supplement contains a malformed relationship")
                relationships_by_identity.setdefault((relation.get("lexical_route_fact_id"),
                                                       relation.get("lexical_implementation_fact_id"),
                                                       relation.get("implementation_type")), []).append(relation)
                if relation.get("lexical_implementation_fact_id") == method.get("id"):
                    compiler_callers.append({"route": relation.get("route"), "http_method": relation.get("http_method"),
                                             "action_method": relation.get("action_method"),
                                             "service_type": relation.get("service_type"),
                                             "bound_member": relation.get("bound_member"),
                                             "implementation_method": relation.get("implementation_method"),
                                             "source_anchors": [relation.get(key) for key in ("action_source", "call_site_source", "service_parameter_source", "bound_member_source", "implementation_source")],
                                             "registrations": relation.get("registrations", []),
                                             "claim": "compiler_confirmed_interface_caller_associated_with_implementation",
                                             "compiler_binding_confirmed": True, "runtime_DI_selection_proven": False})
            call_graph = supplement.get("source_call_graph")
            if not isinstance(call_graph, dict):
                raise AtlasError("compiler supplement source-call graph is malformed")
            graph_edges = call_graph.get("edges", [])
            graph_counts = call_graph.get("counts", {})
            graph_scopes.append({
                "project_path": supplement.get("binding", {}).get("project_path"),
                "coverage": "complete traversal of exactly lexically admitted declarations reachable from compiler-mapped handler roots through supported same-compilation ordinary non-generic static or non-virtual instance calls",
                "counts": {key: graph_counts.get(key) for key in
                           ("roots", "nodes", "edges", "unsupported", "nested_body_exclusions")},
                "unsupported_and_nested_boundaries_are_excluded_from_route_claims": True,
                "compiler_binding_confirmed": True,
                "runtime_reachability_proven": False,
                "runtime_DI_selection_proven": False,
                "whole_codebase_or_all_runtime_routes_proven": False,
            })
            reverse: dict[str, list[dict[str, object]]] = {}
            for edge in graph_edges:
                reverse.setdefault(str(edge["callee_node_id"]), []).append(edge)
            for incoming in reverse.values():
                incoming.sort(key=lambda edge: (str(edge["caller_node_id"]), str(edge["call_site_source"]["path"]),
                                                int(edge["call_site_source"]["span"]["start_offset"]),
                                                str((edge.get("interface_binding") or {}).get("candidate_identity", ""))))
            target_nodes = {str(node["id"]): node for node in call_graph["nodes"]
                            if node.get("lexical_method_fact_id") == method.get("id")}
            next_edge: dict[str, dict[str, object]] = {}
            distance: dict[str, int] = {}
            queue = sorted(target_nodes)
            for target_id in queue:
                distance[target_id] = 0
            cursor = 0
            while cursor < len(queue):
                callee_id = queue[cursor]; cursor += 1
                for edge in reverse.get(callee_id, []):
                    caller_id = str(edge["caller_node_id"])
                    if caller_id not in distance:
                        distance[caller_id] = distance[callee_id] + 1
                        next_edge[caller_id] = edge
                        queue.append(caller_id)
            witnesses = 0
            for root_record in call_graph["roots"]:
                root_id = str(root_record["root_node_id"])
                if root_id not in distance or distance[root_id] == 0:
                    continue
                relation_matches = [relation for relation in relationships
                                    if relation.get("route") == root_record.get("route")
                                    and relation.get("http_method") == root_record.get("http_method")
                                    and relation.get("implementation_type") == root_record.get("implementation_type")
                                    and relation.get("implementation_method") == root_record.get("implementation_method")]
                if len(relation_matches) != 1:
                    raise AtlasError("compiler source-call root does not match exactly one route relationship")
                relation = relation_matches[0]
                chain = []
                current = root_id
                while current not in target_nodes:
                    edge = next_edge.get(current)
                    if edge is None:
                        raise AtlasError("compiler source-call shortest witness is discontinuous; impact refused")
                    chain.append(edge); current = str(edge["callee_node_id"])
                    witnesses += 1
                    if witnesses > SOURCE_CALL_GRAPH_CAPS["impact_witness_hops"]:
                        raise AtlasError("compiler source-call impact witness cap exceeded; stdout withheld")
                witness = {
                    "route": relation.get("route"), "http_method": relation.get("http_method"),
                    "route_fact_id": relation.get("lexical_route_fact_id"),
                    "handler": {"implementation_type": relation.get("implementation_type"),
                                "implementation_method": relation.get("implementation_method"),
                                "lexical_method_fact_id": relation.get("lexical_implementation_fact_id")},
                    "hop_count": len(chain),
                    "call_chain": [{"caller_method": edge["caller_method"], "callee_method": edge["callee_method"],
                                    "caller_lexical_method_fact_id": edge["caller_lexical_method_fact_id"],
                                    "callee_lexical_method_fact_id": edge["callee_lexical_method_fact_id"],
                                    "dispatch_kind": edge["dispatch_kind"], "call_site_source": edge["call_site_source"],
                                    "callee_source": edge["callee_source"],
                                    **({"interface_binding": edge["interface_binding"]} if edge.get("interface_binding") else {})} for edge in chain],
                    "claim": "compiler_confirmed_shortest_source_call_chain_associated_with_route_handler",
                    "compiler_binding_confirmed": True, "runtime_reachability_proven": False,
                    "runtime_DI_selection_proven": False,
                }
                if len(chain) == 1:
                    edge = chain[0]
                    witness["call"] = {"caller_method": edge["caller_method"], "callee_method": edge["callee_method"],
                                       "dispatch_kind": edge["dispatch_kind"],
                                       "caller_lexical_method_fact_id": edge["caller_lexical_method_fact_id"],
                                       "callee_lexical_method_fact_id": edge["callee_lexical_method_fact_id"],
                                       "call_site_source": edge["call_site_source"], "callee_source": edge["callee_source"],
                                       **({"interface_binding": edge["interface_binding"]} if edge.get("interface_binding") else {})}
                compiler_route_paths.append(witness)
        if compiler_callers:
            document["compiler_confirmed_interface_callers"] = sorted(compiler_callers,
                key=lambda item: (str(item.get("route")), str(item.get("action_method")), str(item.get("bound_member"))))
        if graph_scopes:
            document["compiler_source_call_graph_scope"] = graph_scopes
        if compiler_route_paths:
            unique_paths = {}
            for path in compiler_route_paths:
                chain = path["call_chain"]
                key = (path.get("route_fact_id"), path["handler"].get("lexical_method_fact_id"),
                       path["handler"].get("implementation_type"), chain[-1].get("callee_lexical_method_fact_id"))
                unique_paths[key] = path
            document["compiler_associated_route_paths"] = sorted(unique_paths.values(),
                key=lambda item: (str(item.get("route")), str(item.get("http_method")),
                                  str(item.get("handler", {}).get("implementation_type")),
                                  int(item["call_chain"][0].get("call_site_source", {}).get("span", {}).get("start_offset", 0))))
            document["compiler_associated_route_path_counts"] = {
                "distinct_routes": len({path.get("route_fact_id") for path in unique_paths.values()}),
                "route_handler_pairs": len(unique_paths),
            }
            document["compiler_associated_route_paths_scope"] = {
                "relationship": "deterministic shortest source-call chain bound by Roslyn and associated with an existing compiler-mapped handler and lexical route fact",
                "compiler_binding_confirmed": True, "runtime_reachability_proven": False,
                "runtime_DI_selection_proven": False,
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
    repo_root = Path(live["repository_root"])
    injection_by_id = {f["id"]: f for f in facts if f.get("kind") == "constructor_injection"}
    registration_facts = [f for f in facts if f.get("kind") == "dependency_registration"]
    candidate_by_id = {c["id"]: c for c in candidates}
    fact_by_id = {fact["id"]: fact for fact in facts}
    invocation_facts = [f for f in facts if f.get("kind") == "receiver_invocation_syntax"]
    from csharp_facts import lex

    def local_helpers(method: dict[str, object]) -> list[dict[str, object]]:
        """Find bare same-owner calls in a verified saved method body; never resolve them."""
        snippets = _source_texts(repo_root, [(method["id"], method["source"])])
        text = snippets[0]["text"] if snippets else ""
        tokens, _directives = lex(text)
        name = str(method.get("method_name", ""))
        name_index = next((i for i, token in enumerate(tokens)
                           if token.kind == "identifier" and token.value.removeprefix("@") == name), None)
        if name_index is None:
            return []
        # Skip the declaration header, then inspect only its body.
        open_index = next((i for i in range(name_index + 1, len(tokens)) if tokens[i].value in {"{", "=>"}), None)
        if open_index is None:
            return []
        body = tokens[open_index + 1:]
        calls: dict[str, dict[str, object]] = {}
        for i in range(len(body) - 1):
            token = body[i]
            if token.kind != "identifier" or body[i + 1].value != "(":
                continue
            if i and body[i - 1].value in {".", "?.", "::", "new"}:
                continue
            call_name = token.value.removeprefix("@")
            targets = sorted((candidate for candidate in method_by_id.values()
                              if candidate.get("owner_type_id") == method.get("owner_type_id")
                              and candidate.get("method_name") == call_name), key=lambda candidate: candidate["id"])
            if targets:
                calls[call_name] = {"call_name": call_name, "candidate_method_fact_ids": [target["id"] for target in targets],
                                    "traversable": False, "bound": False, "reachable": False}
        return [calls[key] for key in sorted(calls)]

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
                                method_record = {"method_fact_id": target_method["id"], "method_name": target_method["method_name"],
                                                 "source": target_method["source"], "invocations": invocations(target_method, depth + 1)}
                                helpers = local_helpers(target_method)
                                if helpers:
                                    method_record["local_helper_candidates"] = helpers
                                    helper_ids = sorted({fact_id for helper in helpers for fact_id in helper["candidate_method_fact_ids"]})
                                    method_record["local_helper_methods"] = [
                                        {"method_fact_id": helper_id, "method_name": method_by_id[helper_id]["method_name"],
                                         "source": method_by_id[helper_id]["source"], "invocations": [
                                             {"invocation_fact_id": call["id"], "member_name": call.get("member_name"),
                                              "receiver_name": call.get("receiver_name"), "source": call["source"]}
                                             for call in sorted(invocation_facts, key=lambda f: (f.get("source", {}).get("path", ""),
                                                 f.get("source", {}).get("span", {}).get("start_offset", 0), f["id"]))
                                             if call.get("method_id") == helper_id]}
                                        for helper_id in helper_ids]
                                method_evidence.append(method_record)
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
    mandatory_snippets = _source_texts(repo_root, mandatory_refs)
    compiler_relations: list[dict[str, object]] = []
    compiler_snippets: list[dict[str, object]] = []
    supplements = _current_compiler_supplements(db_path, snapshot, repo_root)
    action_span = root_method.get("source", {}).get("span", {})
    action_path = root_method.get("source", {}).get("path")
    for supplement in supplements:
        relationships = supplement.get("relationships", [])
        if not isinstance(relationships, list):
            raise AtlasError("compiler supplement relationships are malformed")
        for relation in relationships:
            if not isinstance(relation, dict):
                raise AtlasError("compiler supplement contains a malformed relationship")
            anchor = relation.get("action_source")
            span = anchor.get("span") if isinstance(anchor, dict) else None
            if isinstance(relation, dict) and relation.get("lexical_route_fact_id") == route_fact_id:
                compiler_relations.append(relation)
    if compiler_relations:
        compiler_refs: list[tuple[str, dict[str, object]]] = []
        for index, relation in enumerate(compiler_relations):
            for key in ("action_source", "call_site_source", "service_parameter_source", "bound_member_source", "implementation_source"):
                source = relation.get(key)
                if not isinstance(source, dict):
                    raise AtlasError(f"compiler relation has no {key} source anchor")
                compiler_refs.append((f"compiler:{index}:{key}", source))
            registrations = relation.get("registrations", [])
            if not isinstance(registrations, list):
                raise AtlasError("compiler relation registrations are malformed")
            for reg_index, registration in enumerate(registrations):
                source = registration.get("source") if isinstance(registration, dict) else None
                if not isinstance(source, dict):
                    raise AtlasError("compiler registration source anchor is missing")
                compiler_refs.append((f"compiler:{index}:registration:{reg_index}", source))
                if registration.get("runtime_DI_selection_proven") is not False:
                    raise AtlasError("compiler registration must remain labeled runtime-unproven")
        compiler_snippets = _source_texts(repo_root, compiler_refs)
    def bundle_fact_ids(value: object) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("_fact_id") and isinstance(item, str):
                    found.add(item)
                elif key == "candidate_fact_ids" and isinstance(item, list):
                    found.update(x for x in item if isinstance(x, str))
                elif key == "candidate_method_fact_ids" and isinstance(item, list):
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
    if compiler_relations:
        document["compiler_relationships"] = compiler_relations
        document["compiler_source_snippets"] = compiler_snippets
        document["compiler_relationship_semantics"] = {
            "compiler_binding_confirmed": True,
            "registrations_are_source_syntax_only": True,
            "runtime_DI_selection_proven": False,
        }
    encoded = _evidence_pack_render(document, max_bytes)
    for bundle in complete_bundles:
        staged_snippets = dict(selected_snippets)
        for snippet in bundle_snippets(bundle):
            key = (snippet["path"], snippet["sha256"], snippet["span"]["start_offset"], snippet["span"]["end_offset"], snippet["fact_id"])
            staged_snippets[key] = snippet
        trial_bundles = [*selected_bundles, bundle]
        trial = dict(document)
        trial["candidate_bundles"] = trial_bundles
        trial["candidate_snippets"] = [staged_snippets[key] for key in sorted(staged_snippets, key=lambda item: (os.fsencode(item[0]), item[2], item[3], item[4]))]
        trial["selection"] = {"included_candidate_bundles": len(trial_bundles), "omitted_candidate_bundles": len(complete_bundles) - len(trial_bundles),
                              "complete": len(trial_bundles) == len(complete_bundles), "candidate_bundle_count": len(complete_bundles)}
        try:
            encoded = _evidence_pack_render(trial, max_bytes)
        except AtlasError:
            # Later bundles are deterministic; a bundle is never split or silently dropped.
            # Rebuild omitted counts from the retained complete prefix.
            break
        selected_bundles = trial_bundles
        selected_snippets = staged_snippets
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


def _focus_span_identity(span: dict[str, object]) -> bytes:
    return json.dumps(span, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _focus_snippet_identity(path: str, source_hash: str, span: dict[str, object]) -> tuple[str, str, bytes]:
    return path, source_hash, _focus_span_identity(span)


def _focus_snippet_id(identity: tuple[str, str, bytes]) -> str:
    # Length-prefix every field so concatenation cannot make two identities collide.
    fields = (identity[0].encode("utf-8"), identity[1].encode("ascii"), identity[2])
    payload = b"codebase-atlas-source-snippet-v1\0" + b"".join(
        len(field).to_bytes(8, "big") + field for field in fields
    )
    return "snippet-" + hashlib.sha256(payload).hexdigest()


def _focus_document(
    snapshot: dict[str, object], flow_result: dict[str, object], freshness: dict[str, object],
    max_bytes: int, verified_sources: list[dict[str, object]],
) -> tuple[dict[str, object], bytes]:
    overlay = flow_result["overlay"]
    all_claims = overlay["reviewed_conclusions"]
    verified_by_citation: dict[tuple[str, str, str, bytes], dict[str, object]] = {}
    snippets_by_identity: dict[tuple[str, str, bytes], dict[str, object]] = {}
    for item in verified_sources:
        span = item["span"]
        identity = _focus_snippet_identity(item["path"], item["sha256"], span)
        verified_by_citation[(item["fact_id"], item["path"], item["sha256"], identity[2])] = item
        snippets_by_identity.setdefault(identity, {
            "snippet_id": _focus_snippet_id(identity), "span": span, "text": item["text"],
        })

    def build(claims: list[dict[str, object]], byte_count: int) -> dict[str, object]:
        identities = {
            _focus_snippet_identity(citation["source"]["path"], citation["source"]["sha256"], citation["source"]["span"])
            for claim in claims for citation in claim["evidence"]
        }
        keys = sorted({(identity[0], identity[1]) for identity in identities}, key=lambda item: (os.fsencode(item[0]), item[1]))
        source_ids = {key: f"source-{index + 1}" for index, key in enumerate(keys)}
        selected_snippets = [
            {**snippets_by_identity[identity], "source_id": source_ids[(identity[0], identity[1])]}
            for identity in sorted(identities, key=lambda item: (os.fsencode(item[0]), item[1], item[2]))
        ]
        selected = []
        for claim in claims:
            citations = []
            for citation in claim["evidence"]:
                source = citation["source"]
                identity = _focus_snippet_identity(source["path"], source["sha256"], source["span"])
                verified = verified_by_citation.get((citation["fact_id"], source["path"], source["sha256"], identity[2]))
                if verified is None:
                    raise AtlasError(f"source citation could not be matched to verified text: {citation['fact_id']}")
                citations.append({
                    "fact_id": citation["fact_id"],
                    "source_id": source_ids[(identity[0], identity[1])],
                    "span": source["span"],
                    "snippet_id": _focus_snippet_id(identity),
                })
            selected.append({
                "claim": claim["claim"],
                "evidence": citations,
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
            "source_snippets": selected_snippets,
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
    references = [
        (citation["fact_id"], citation["source"])
        for claim in flow_result["overlay"]["reviewed_conclusions"]
        for citation in claim["evidence"]
    ]
    # Read and hash-check all cited files once after receipt and freshness have passed.
    # The same verified text is reused for every atomic budget trial below.
    verified_sources = _source_texts(Path(live["repository_root"]), references)
    value, encoded = _focus_document(snapshot, flow_result, freshness, max_bytes, verified_sources)
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
        "source_snippets": focused["source_snippets"],
        "review_instructions": (
            "Independently inspect every question-relevant exact detail in each cited source snippet, including "
            "return values, constructor calls, and arguments. Exact assertions supported by cited snippet text "
            "may be accepted even when the map claim paraphrase omits them. Check complete relevant coverage, "
            "contradictions between the draft, map claims, and cited bodies, and every unsupported addition. "
            "For each numbered claim, decide relevance to the exact question and mark relevant claims covered "
            "only when the draft includes every question-relevant supported detail; otherwise mark not_relevant "
            "only when the claim is unrelated. Treat candidate bindings and lexical relationships as limitations, "
            "not proof of runtime behavior. A bare 'used' or equivalent is not evidence of completeness."
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


ANSWER_LIFECYCLE_VERSION = 1
SUPPORTED_ANSWER_LIFECYCLE_VERSIONS = {1, 2}
EVIDENCE_MEASUREMENT_EXCLUDED_CLAIMS = [
    "historical_retrieval_stdout_bytes",
    "command_execution",
    "elapsed_time",
    "provider_tokens",
    "total_workflow_cost",
]


def _answer_packet_hash(packet: dict[str, object]) -> str:
    """Hash canonical ASCII JSON without packet_sha256, including the CLI newline."""
    unsigned = {key: value for key, value in packet.items() if key != "packet_sha256"}
    return hashlib.sha256(_canonical_json(unsigned) + b"\n").hexdigest()


def _answer_packet_bytes(packet: dict[str, object]) -> bytes:
    return _canonical_json(packet) + b"\n"


def _answer_review_contract(corrected: bool = False) -> dict[str, object]:
    return {
        "review_schema_version": ANSWER_LIFECYCLE_VERSION,
        "required_top_level_fields": [
            "review_schema_version", "packet_sha256", "decision", "reviewer_identity",
            "reviewer_model", "claim_reviews",
        ],
        "optional_top_level_fields": ["rejection_reasons"],
        "allowed_top_level_fields": [
            "review_schema_version", "packet_sha256", "decision", "reviewer_identity",
            "reviewer_model", "claim_reviews", "rejection_reasons",
        ],
        "top_level_field_types": {
            "review_schema_version": "integer, exactly 1",
            "packet_sha256": "string, copy the exact embedded packet value",
            "decision": "string, accepted or rejected",
            "reviewer_identity": "nonempty string",
            "reviewer_model": "nonempty string",
            "claim_reviews": "array",
            "rejection_reasons": "array when present",
        },
        "reviewer_fields": {
            "reviewer_identity": "nonempty audit label",
            "reviewer_model": "nonempty audit label",
            "authentication": "these caller-supplied fields do not authenticate reviewer identity",
        },
        "packet_hash_binding": {
            "field": "packet_sha256",
            "value": "copy packet.packet_sha256 exactly",
            "digest": "SHA-256 of canonical ASCII JSON for the packet with packet_sha256 omitted, followed by one newline",
        },
        "claim_reviews": {
            "coverage": "exactly one entry for each numbered packet claim, in packet order, with no omissions or duplicates",
            "required_item_fields": ["claim_number", "disposition", "basis"],
            "allowed_item_fields": ["claim_number", "disposition", "basis"],
            "item_field_types": {
                "claim_number": "integer equal to one-based packet order",
                "disposition": "string from allowed_dispositions",
                "basis": "string at least basis_minimum_characters long",
            },
            "allowed_dispositions": ["covered", "not_relevant", "incomplete"],
            "basis_minimum_characters": 20,
            "incomplete_meaning": "the claim is relevant, but supported question details in its cited source snippets are absent from the answer",
        },
        "decision": {
            "allowed_values": ["accepted", "rejected"],
            "accepted": "no claim is incomplete and rejection_reasons is absent or empty",
            "rejected": "rejection_reasons is nonempty; every incomplete claim has one claim-scoped reason naming its number and correction",
        },
        "rejection_reasons": {
            "required_when": "decision is rejected",
            "reason_minimum_characters": 20,
            "correction_minimum_characters": 10,
            "allowed_item_shapes": [
                {
                    "scope": "claim",
                    "required_fields": ["scope", "claim_number", "reason", "correction"],
                    "allowed_fields": ["scope", "claim_number", "reason", "correction"],
                    "claim_number": "an existing packet claim marked incomplete; never infer a number from free text",
                },
                {
                    "scope": "answer",
                    "required_fields": ["scope", "category", "reason", "correction"],
                    "allowed_fields": ["scope", "category", "reason", "correction"],
                    "allowed_categories": ["unsupported_addition", "contradiction"],
                    "claim_number": "not present; answer-level reason is separately scoped",
                },
            ],
            "uniqueness": "at most one claim-scoped reason per claim; no claim-scoped reason for claims not marked incomplete",
        },
        "corrected_answer_review": corrected,
    }


def _measurement_contract() -> dict[str, object]:
    return {
        "measurement_schema_version": "integer, exactly 1",
        "measurement_kind": "string, exactly canonical_review_evidence",
        "original_packet_sha256": "SHA-256 of the exact original lifecycle packet, canonical ASCII JSON with packet_sha256 omitted plus one newline",
        "canonical_evidence_sha256": "SHA-256 of canonical evidence bytes defined below",
        "canonical_evidence_bytes": "integer, not boolean; byte length of canonical evidence bytes defined below",
        "unit": "string, exactly ASCII bytes including one trailing newline",
        "excluded_claims": list(EVIDENCE_MEASUREMENT_EXCLUDED_CLAIMS),
        "canonical_evidence": {
            "value": "{claims: original.answer_packet.claims, source_anchors: original.answer_packet.source_anchors, source_snippets: original.answer_packet.source_snippets}",
            "encoding": "ASCII JSON with ensure_ascii=true, sorted keys, separators=(',', ':'), and one trailing newline",
            "excludes": ["question", "draft", "checked_at", "full packet", "prompts", "double copies"],
        },
        "meaning": "evidence-content size only; it does not prove model consumption or measure retrieval stdout",
        "recheck": "Atlas recomputes the complete object at accept from the exact original packet using the same helper",
    }


def _canonical_review_evidence_measurement(original_packet: dict[str, object]) -> dict[str, object]:
    answer_packet = original_packet.get("answer_packet")
    if not isinstance(answer_packet, dict):
        raise AtlasError("original lifecycle packet answer_packet must be an object for evidence measurement")
    evidence = {
        "claims": answer_packet.get("claims"),
        "source_anchors": answer_packet.get("source_anchors"),
        "source_snippets": answer_packet.get("source_snippets"),
    }
    evidence_bytes = _canonical_json(evidence) + b"\n"
    try:
        evidence_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise AtlasError("canonical review evidence is not ASCII encodable") from exc
    return {
        "measurement_schema_version": 1,
        "measurement_kind": "canonical_review_evidence",
        "original_packet_sha256": _answer_packet_hash(original_packet),
        "canonical_evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "canonical_evidence_bytes": len(evidence_bytes),
        "unit": "ASCII bytes including one trailing newline",
        "excluded_claims": list(EVIDENCE_MEASUREMENT_EXCLUDED_CLAIMS),
    }


def _measurement_matches(actual: object, expected: dict[str, object]) -> bool:
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return False
    return all(type(actual[key]) is type(value) and actual[key] == value for key, value in expected.items())


def _answer_lifecycle_packet(
    db_arg: str, repo_arg: str, snapshot_id: str, overlay_id: str,
    question_path: str, draft_path: str, lifecycle_version: int = ANSWER_LIFECYCLE_VERSION,
) -> tuple[dict[str, object], bytes]:
    original, _, status = answer_check(
        db_arg, repo_arg, snapshot_id, overlay_id, question_path, draft_path, None,
    )
    if status != 0 or not isinstance(original, dict):
        raise AtlasError("answer lifecycle could not build the complete current answer packet")
    packet: dict[str, object] = {
        "lifecycle_schema_version": lifecycle_version,
        "packet_type": "answer_review",
        "result": "semantic_review_required",
        "answer_packet": original,
        "review_contract": _answer_review_contract(),
        "hash_contract": {
            "packet_sha256": "SHA-256 of canonical ASCII JSON for this packet with packet_sha256 omitted, followed by one newline; this binds reviews to the canonical packet payload.",
            "cli_file_sha256": "SHA-256 of every emitted ASCII CLI byte, including packet_sha256 and the final newline; this verifies byte-for-byte file transfer and is not the review binding.",
            "question_sha256": "SHA-256 of exact UTF-8 question file bytes, including any final newline.",
            "draft_sha256": "SHA-256 of exact UTF-8 draft file bytes, including any final newline.",
        },
    }
    if lifecycle_version == 2:
        packet["measurement_contract"] = _measurement_contract()
    packet["packet_sha256"] = _answer_packet_hash(packet)
    return packet, _answer_packet_bytes(packet)


def _answer_nonempty(value: object, label: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise AtlasError(f"{label} must be a nonempty string of at least {minimum} characters")
    return value


def _answer_review_labels(review: dict[str, object], label: str = "answer review") -> None:
    for field in ("reviewer_identity", "reviewer_model"):
        _answer_nonempty(review.get(field), f"{label} {field}")


def _validate_lifecycle_review(
    packet: dict[str, object], review: object,
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    if not isinstance(review, dict):
        raise AtlasError("answer review must be a JSON object")
    if type(review.get("review_schema_version")) is not int or review.get("review_schema_version") != ANSWER_LIFECYCLE_VERSION:
        raise AtlasError("answer review review_schema_version must be 1")
    allowed_review_fields = {
        "review_schema_version", "packet_sha256", "decision", "reviewer_identity",
        "reviewer_model", "claim_reviews", "rejection_reasons",
    }
    required_review_fields = allowed_review_fields - {"rejection_reasons"}
    if not required_review_fields.issubset(review) or set(review) - allowed_review_fields:
        raise AtlasError("answer review fields must match the advertised review_contract top-level shape")
    packet_hash = _answer_packet_hash(packet)
    if review.get("packet_sha256") != packet_hash:
        raise AtlasError("answer review packet_sha256 does not match the exact versioned packet")
    _answer_review_labels(review)
    answer_packet = packet.get("answer_packet")
    claims = answer_packet.get("claims") if isinstance(answer_packet, dict) else packet.get("claims")
    if not isinstance(claims, list):
        raise AtlasError("versioned packet answer_packet.claims must be an ordered list")
    reviews = review.get("claim_reviews")
    if not isinstance(reviews, list) or len(reviews) != len(claims):
        raise AtlasError("claim_reviews must contain one ordered entry for every packet claim")
    incomplete: list[dict[str, object]] = []
    for index, item in enumerate(reviews, start=1):
        if not isinstance(item, dict) or set(item) != {"claim_number", "disposition", "basis"}:
            raise AtlasError(f"claim_reviews[{index - 1}] must contain only claim_number, disposition, and basis")
        if type(item.get("claim_number")) is not int or item.get("claim_number") != index:
            raise AtlasError(f"claim_reviews[{index - 1}] must name claim {index} in packet order")
        disposition = item.get("disposition")
        if not isinstance(disposition, str) or disposition not in {"covered", "not_relevant", "incomplete"}:
            raise AtlasError(f"claim {index} disposition must be covered, not_relevant, or incomplete")
        _answer_nonempty(item.get("basis"), f"claim {index} basis", 20)
        if disposition == "incomplete":
            incomplete.append(item)
    reasons = review.get("rejection_reasons", [])
    if not isinstance(reasons, list):
        raise AtlasError("rejection_reasons must be a structured list")
    for index, reason in enumerate(reasons):
        if not isinstance(reason, dict):
            raise AtlasError(f"rejection_reasons[{index}] must be an object")
        scope = reason.get("scope")
        if scope == "claim":
            if set(reason) != {"scope", "claim_number", "reason", "correction"}:
                raise AtlasError(f"rejection_reasons[{index}] claim reason must contain scope, claim_number, reason, and correction")
            number = reason.get("claim_number")
            if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= len(claims):
                raise AtlasError(f"rejection_reasons[{index}].claim_number must identify a packet claim")
        elif scope == "answer":
            if set(reason) != {"scope", "category", "reason", "correction"}:
                raise AtlasError(f"rejection_reasons[{index}] answer-level reason must contain scope, category, reason, and correction")
            category = reason.get("category")
            if not isinstance(category, str) or category not in {"unsupported_addition", "contradiction"}:
                raise AtlasError(f"rejection_reasons[{index}].category must be unsupported_addition or contradiction")
        else:
            raise AtlasError(f"rejection_reasons[{index}].scope must be claim or answer")
        _answer_nonempty(reason.get("reason"), f"rejection_reasons[{index}].reason", 20)
        _answer_nonempty(reason.get("correction"), f"rejection_reasons[{index}].correction", 10)
    decision = review.get("decision")
    reasoned_claims = [r["claim_number"] for r in reasons if r.get("scope") == "claim"]
    if len(set(reasoned_claims)) != len(reasoned_claims):
        raise AtlasError("rejection_reasons contains duplicate claim numbers")
    incomplete_numbers = {item["claim_number"] for item in incomplete}
    if any(number not in incomplete_numbers for number in reasoned_claims):
        raise AtlasError("claim-level rejection reasons may name only claims marked incomplete")
    if decision == "accepted":
        if incomplete:
            raise AtlasError(f"accepted review has incomplete claim {incomplete[0]['claim_number']}")
        if reasons:
            raise AtlasError("accepted review must not contain rejection_reasons")
    elif decision == "rejected":
        if not reasons:
            raise AtlasError("rejected review requires at least one structured rejection reason")
        reasoned_claims = set(reasoned_claims)
        for item in incomplete:
            number = item["claim_number"]
            if number not in reasoned_claims:
                raise AtlasError(f"incomplete claim {number} requires a structured rejection reason naming its correction")
    else:
        raise AtlasError("answer review decision must be accepted or rejected")
    return review, claims, reasons


def _lifecycle_review_result(packet: dict[str, object], review: object) -> tuple[dict[str, object], bytes]:
    checked, claims, reasons = _validate_lifecycle_review(packet, review)
    review_hash = hashlib.sha256(_canonical_json(checked) + b"\n").hexdigest()
    answer_packet = packet["answer_packet"]
    lifecycle_version = packet.get("lifecycle_schema_version")
    if checked["decision"] == "accepted":
        result: dict[str, object] = {
            "lifecycle_schema_version": lifecycle_version,
            "result": "accepted",
            "answer": answer_packet["draft"],
            "answer_sha256": answer_packet["binding"]["draft_sha256"],
            "question_sha256": answer_packet["binding"]["question_sha256"],
            "packet_sha256": _answer_packet_hash(packet),
            "review_sha256": review_hash,
            "reviewer_identity": checked["reviewer_identity"],
            "reviewer_model": checked["reviewer_model"],
        }
        if lifecycle_version == 2:
            result["evidence_measurement"] = _canonical_review_evidence_measurement(packet)
            result["measurement_contract"] = _measurement_contract()
        return result, _answer_packet_bytes(result)
    correction: dict[str, object] = {
        "lifecycle_schema_version": lifecycle_version,
        "packet_type": "answer_correction",
        "result": "correction_required",
        "original_packet": packet,
        "original_packet_sha256": _answer_packet_hash(packet),
        "question_sha256": answer_packet["binding"]["question_sha256"],
        "draft_sha256": answer_packet["binding"]["draft_sha256"],
        "rejected_review": checked,
        "rejected_review_sha256": review_hash,
        "reviewer_identity": checked["reviewer_identity"],
        "reviewer_model": checked["reviewer_model"],
        "rejected_claim_numbers": sorted({r["claim_number"] for r in reasons if r.get("scope") == "claim"}),
        "rejection_reasons": reasons,
        "claims": claims,
        "evidence": {
            "source_anchors": answer_packet["source_anchors"],
            "source_snippets": answer_packet["source_snippets"],
            "review_provenance": answer_packet["review_provenance"],
            "binding": answer_packet["binding"],
        },
        "correction_round": 1,
        "max_corrections": 1,
        "hash_contract": {
            "packet_sha256": "SHA-256 of canonical ASCII JSON for this object with packet_sha256 omitted, followed by one newline",
            "cli_file_sha256": "SHA-256 of every emitted ASCII CLI byte, including packet_sha256 and the final newline; transport integrity only, not the review binding",
            "review_sha256": "SHA-256 of canonical ASCII JSON review bytes followed by one newline",
            "answer_sha256": "SHA-256 of exact UTF-8 answer bytes, including any final newline",
            "question_sha256": "SHA-256 of exact UTF-8 question bytes, including any final newline",
        },
    }
    if lifecycle_version == 2:
        correction["measurement_contract"] = _measurement_contract()
    correction["packet_sha256"] = _answer_packet_hash(correction)
    return correction, _answer_packet_bytes(correction)


def _validate_correction_packet(packet: object) -> dict[str, object]:
    if not isinstance(packet, dict) or packet.get("packet_type") != "answer_correction":
        raise AtlasError("correction packet must be a versioned answer_correction object")
    version = packet.get("lifecycle_schema_version")
    if type(version) is not int or version not in SUPPORTED_ANSWER_LIFECYCLE_VERSIONS:
        raise AtlasError("correction packet lifecycle_schema_version must be integer 1 or 2")
    if packet.get("result") != "correction_required" or packet.get("correction_round") != 1 or packet.get("max_corrections") != 1:
        raise AtlasError("only an original round-zero rejection can prepare correction round 1")
    if packet.get("packet_sha256") != _answer_packet_hash(packet):
        raise AtlasError("correction packet packet_sha256 does not match its canonical contents")
    original = packet.get("original_packet")
    if not isinstance(original, dict) or original.get("packet_type") != "answer_review":
        raise AtlasError("correction packet original_packet must be the exact versioned answer review packet")
    if (type(original.get("lifecycle_schema_version")) is not int
            or original.get("lifecycle_schema_version") != version
            or original.get("result") != "semantic_review_required"
            or not isinstance(original.get("answer_packet"), dict)):
        raise AtlasError("correction packet original_packet has an invalid lifecycle version or answer_packet shape")
    if original.get("packet_sha256") != _answer_packet_hash(original):
        raise AtlasError("original lifecycle packet hash is invalid")
    if version == 2 and original.get("measurement_contract") != _measurement_contract():
        raise AtlasError("original lifecycle packet measurement_contract is invalid")
    if version == 2 and packet.get("measurement_contract") != _measurement_contract():
        raise AtlasError("correction packet measurement_contract is invalid")
    _validate_lifecycle_review(original, packet.get("rejected_review"))
    review = packet["rejected_review"]
    if review.get("decision") != "rejected" or packet.get("rejected_review_sha256") != hashlib.sha256(_canonical_json(review) + b"\n").hexdigest():
        raise AtlasError("correction packet rejected review binding is invalid")
    answer = original["answer_packet"]
    binding = answer.get("binding")
    if not isinstance(binding, dict):
        raise AtlasError("original answer packet binding must be an object")
    for field in ("question_sha256", "draft_sha256"):
        if packet.get(field) != binding.get(field):
            raise AtlasError(f"correction packet {field} does not match the original answer packet")
    expected_claims = answer.get("claims")
    if not isinstance(expected_claims, list):
        raise AtlasError("original answer packet claims must be an ordered list")
    if packet.get("claims") != expected_claims:
        raise AtlasError("correction packet claims differ from the original complete claim list")
    evidence = packet.get("evidence")
    if not isinstance(evidence, dict):
        raise AtlasError("correction packet evidence must be an object")
    if evidence.get("source_snippets") != answer.get("source_snippets") or evidence.get("source_anchors") != answer.get("source_anchors"):
        raise AtlasError("correction packet evidence differs from the original preserved source anchors and snippets")
    rebuilt, _ = _lifecycle_review_result(original, review)
    if _answer_packet_bytes(rebuilt) != _answer_packet_bytes(packet):
        raise AtlasError("correction packet does not reconstruct from its original rejected review")
    return packet


def _validate_structured_answer(
    answer: object, draft_bytes: bytes, correction: dict[str, object], *, allow_atlas_measurement: bool = False,
) -> dict[str, object]:
    if not isinstance(answer, dict):
        raise AtlasError("structured answer JSON must be an object")
    required = {"question_id", "answer", "material_claims", "limitations", "evidence_measurement"}
    if set(answer) != required:
        raise AtlasError("structured answer must contain exactly question_id, answer, material_claims, limitations, evidence_measurement")
    _answer_nonempty(answer.get("question_id"), "question_id")
    answer_text = _answer_nonempty(answer.get("answer"), "answer")
    try:
        draft = draft_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AtlasError("corrected draft must contain UTF-8 text") from exc
    if answer_text != draft:
        raise AtlasError("structured answer.answer must exactly equal the corrected UTF-8 draft")
    claims = answer.get("material_claims")
    if not isinstance(claims, list) or not claims:
        raise AtlasError("material_claims must be a nonempty list of atomic cited assertions")
    packet_claims = correction["claims"]
    packet_answer = correction["original_packet"]["answer_packet"]
    anchor_by_source = {item["source_id"]: item for item in packet_answer["source_anchors"]}
    snippet_ids = {item["snippet_id"] for item in packet_answer["source_snippets"]}
    claim_by_number = {item["claim_number"]: item for item in packet_claims}
    for index, item in enumerate(claims):
        if not isinstance(item, dict) or set(item) != {"assertion", "claim_numbers", "citations"}:
            raise AtlasError(f"material_claims[{index}] must contain assertion, claim_numbers, and citations")
        assertion = _answer_nonempty(item.get("assertion"), f"material_claims[{index}].assertion", 8)
        if "\n" in assertion or ";" in assertion or len(assertion.split(". ")) > 1:
            raise AtlasError(f"material_claims[{index}].assertion must be one atomic sentence")
        numbers = item.get("claim_numbers")
        if not isinstance(numbers, list) or not numbers or any(not isinstance(n, int) or isinstance(n, bool) or n not in claim_by_number for n in numbers):
            raise AtlasError(f"material_claims[{index}].claim_numbers must name existing packet claims")
        if len(set(numbers)) != len(numbers):
            raise AtlasError(f"material_claims[{index}].claim_numbers contains duplicates")
        citations = item.get("citations")
        if not isinstance(citations, list) or not citations:
            raise AtlasError(f"material_claims[{index}] requires at least one citation")
        cited_numbers: set[int] = set()
        for ci, citation in enumerate(citations):
            required_citation = {"claim_number", "fact_id", "path", "sha256", "span", "snippet_id"}
            if not isinstance(citation, dict) or set(citation) != required_citation:
                raise AtlasError(f"material_claims[{index}].citations[{ci}] must contain exact claim, fact, path, hash, span, and snippet fields")
            number = citation["claim_number"]
            if not isinstance(number, int) or isinstance(number, bool) or number not in numbers:
                raise AtlasError(f"material_claims[{index}].citations[{ci}].claim_number must match claim_numbers")
            claim = claim_by_number[number]
            matches = []
            for evidence in claim["evidence"]:
                anchor = anchor_by_source.get(evidence["source_id"])
                if anchor and (citation["fact_id"] == evidence["fact_id"] and citation["path"] == anchor["path"] and citation["sha256"] == anchor["sha256"] and citation["span"] == evidence["span"] and citation["snippet_id"] == evidence["snippet_id"]):
                    matches.append(evidence)
            if not matches or citation["snippet_id"] not in snippet_ids:
                raise AtlasError(f"material_claims[{index}].citations[{ci}] does not resolve to a preserved packet source anchor and evidence span")
            cited_numbers.add(number)
        if cited_numbers != set(numbers):
            raise AtlasError(f"material_claims[{index}] claim_numbers do not match its cited map claims")
    limitations = answer.get("limitations")
    if not isinstance(limitations, list) or any(not isinstance(v, str) or not v.strip() for v in limitations):
        raise AtlasError("limitations must be a list of nonempty strings")
    measurement = answer.get("evidence_measurement")
    if not isinstance(measurement, dict):
        raise AtlasError("evidence_measurement must be a JSON object")
    if correction.get("lifecycle_schema_version") == 2:
        if allow_atlas_measurement:
            original_packet = correction["original_packet"]
            expected = _canonical_review_evidence_measurement(original_packet)
            if not _measurement_matches(measurement, expected):
                raise AtlasError("evidence_measurement does not match Atlas's exact measurement of the original review evidence")
        elif measurement:
            raise AtlasError("lifecycle version 2 worker evidence_measurement must be exactly {}; Atlas supplies the recomputed measurement")
    return answer


def _corrected_review_packet(correction: dict[str, object], answer: dict[str, object]) -> dict[str, object]:
    if correction.get("lifecycle_schema_version") == 2:
        answer = dict(answer)
        answer["evidence_measurement"] = _canonical_review_evidence_measurement(correction["original_packet"])
    packet: dict[str, object] = {
        "lifecycle_schema_version": correction["lifecycle_schema_version"],
        "packet_type": "corrected_answer_review",
        "result": "semantic_review_required",
        "correction_packet": correction,
        "correction_packet_sha256": correction["packet_sha256"],
        "correction_lineage": {
            "original_packet_sha256": correction["original_packet_sha256"],
            "rejected_review_sha256": correction["rejected_review_sha256"],
            "correction_round": correction["correction_round"],
            "max_corrections": correction["max_corrections"],
        },
        "structured_answer": answer,
        "question": correction["original_packet"]["answer_packet"]["question"],
        "claims": correction["claims"],
        "source_anchors": correction["evidence"]["source_anchors"],
        "source_snippets": correction["evidence"]["source_snippets"],
        "review_contract": {
            **_answer_review_contract(corrected=True),
            "instructions": "Re-review the final structured answer against every exact source snippet and citation. Judge truth, completeness, assertion-to-citation correspondence, candidate-binding limitations, unsupported additions, and contradictions.",
        },
        "hash_contract": {
            "packet_sha256": "SHA-256 of canonical ASCII JSON for this packet with packet_sha256 omitted, followed by one newline; this binds the accepted review.",
            "cli_file_sha256": "SHA-256 of every emitted ASCII CLI byte, including packet_sha256 and the final newline; this verifies byte-for-byte file transfer and is not the review binding.",
            "answer_sha256": "SHA-256 of exact UTF-8 structured answer bytes, including any final newline in answer.",
            "question_sha256": "SHA-256 of exact UTF-8 question bytes, including any final newline.",
        },
    }
    if correction.get("lifecycle_schema_version") == 2:
        packet["measurement_contract"] = _measurement_contract()
    packet["packet_sha256"] = _answer_packet_hash(packet)
    return packet


def answer_lifecycle(
    stage: str, db_arg: str | None = None, repo_arg: str | None = None,
    snapshot_id: str | None = None, overlay_id: str | None = None,
    question_path: str | None = None, draft_path: str | None = None,
    review_path: str | None = None, correction_path: str | None = None,
    answer_path: str | None = None, packet_path: str | None = None,
    lifecycle_version: int = ANSWER_LIFECYCLE_VERSION,
) -> tuple[dict[str, object], bytes, int]:
    if stage == "prepare":
        if type(lifecycle_version) is not int or lifecycle_version not in SUPPORTED_ANSWER_LIFECYCLE_VERSIONS:
            raise AtlasError("lifecycle version must be integer 1 or 2")
        packet, _ = _answer_lifecycle_packet(db_arg, repo_arg, snapshot_id, overlay_id, question_path, draft_path, lifecycle_version)
        if review_path is None:
            return packet, _answer_packet_bytes(packet), 0
        review, _ = _read_json_file(review_path, "answer lifecycle review")
        result, encoded = _lifecycle_review_result(packet, review)
        return result, encoded, 0
    if stage == "correct":
        correction_obj, _ = _read_json_file(correction_path, "correction packet")
        correction = _validate_correction_packet(correction_obj)
        try:
            draft_bytes = Path(draft_path).read_bytes()
        except OSError as exc:
            raise AtlasError(f"cannot read corrected draft: {exc}") from exc
        answer, _ = _read_json_file(answer_path, "structured answer")
        structured = _validate_structured_answer(answer, draft_bytes, correction)
        packet = _corrected_review_packet(correction, structured)
        return packet, _answer_packet_bytes(packet), 0
    if stage == "accept":
        packet, _ = _read_json_file(packet_path, "corrected answer review packet")
        version = packet.get("lifecycle_schema_version") if isinstance(packet, dict) else None
        if (packet.get("packet_type") != "corrected_answer_review"
                or type(version) is not int
                or version not in SUPPORTED_ANSWER_LIFECYCLE_VERSIONS):
            raise AtlasError("accept requires a corrected_answer_review packet at lifecycle version 1 or 2")
        if version == 2 and packet.get("measurement_contract") != _measurement_contract():
            raise AtlasError("corrected review packet measurement_contract is invalid")
        if packet.get("packet_sha256") != _answer_packet_hash(packet):
            raise AtlasError("corrected review packet packet_sha256 does not match canonical contents")
        correction = _validate_correction_packet(packet.get("correction_packet"))
        structured_answer = packet.get("structured_answer")
        if not isinstance(structured_answer, dict) or not isinstance(structured_answer.get("answer"), str):
            raise AtlasError("corrected review packet structured_answer must contain an answer string")
        answer = _validate_structured_answer(
            structured_answer, structured_answer["answer"].encode("utf-8"), correction,
            allow_atlas_measurement=(version == 2),
        )
        rebuilt = _corrected_review_packet(correction, answer)
        if _answer_packet_bytes(rebuilt) != _answer_packet_bytes(packet):
            raise AtlasError("corrected review packet does not reconstruct from its correction lineage and answer")
        original = correction["original_packet"]["answer_packet"]
        binding = original["binding"]
        fresh, _ = _answer_lifecycle_packet_from_values(db_arg, repo_arg, binding, original["question"], original["draft"], version)
        if _answer_packet_bytes(fresh) != _answer_packet_bytes(correction["original_packet"]):
            raise AtlasError("original answer packet is stale against current map, source, or receipt evidence")
        review, _ = _read_json_file(review_path, "corrected answer review")
        checked, _claims, _reasons = _validate_lifecycle_review(packet, review)
        if checked["decision"] != "accepted":
            raise AtlasError("corrected answer review rejected; a second correction is not permitted")
        final = {
            "lifecycle_schema_version": version,
            "result": "accepted",
            "question": original["question"],
            "question_sha256": binding["question_sha256"],
            "answer": answer,
            "answer_sha256": hashlib.sha256(answer["answer"].encode("utf-8")).hexdigest(),
            "provenance": {
                "snapshot_id": binding["snapshot_id"],
                "extractor_identity": binding["extractor_identity"],
                "overlay_id": binding["overlay_id"],
                "overlay_content_hash": binding["overlay_content_hash"],
                "review_receipt_hash": original["review_provenance"]["review_receipt_hash"],
                "carry_provenance": original["review_provenance"].get("carry_provenance"),
            },
            "claims": packet["claims"],
            "source_anchors": packet["source_anchors"],
            "source_snippets": packet["source_snippets"],
            "correction_provenance": packet["correction_lineage"],
            "review": {
                "packet_sha256": _answer_packet_hash(packet),
                "review_sha256": hashlib.sha256(_canonical_json(checked) + b"\n").hexdigest(),
                "reviewer_identity": checked["reviewer_identity"],
                "reviewer_model": checked["reviewer_model"],
            },
        }
        if version == 2:
            final["measurement_contract"] = _measurement_contract()
        return final, _answer_packet_bytes(final), 0
    raise AtlasError("answer-lifecycle stage must be prepare, correct, or accept")


def _answer_lifecycle_packet_from_values(
    db_arg: str, repo_arg: str, binding: dict[str, object], question: str, draft: str,
    lifecycle_version: int = ANSWER_LIFECYCLE_VERSION,
) -> tuple[dict[str, object], bytes]:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="atlas-answer-lifecycle-") as temporary:
        question_path = Path(temporary) / "question.txt"
        draft_path = Path(temporary) / "draft.txt"
        question_path.write_bytes(question.encode("utf-8"))
        draft_path.write_bytes(draft.encode("utf-8"))
        try:
            return _answer_lifecycle_packet(
                db_arg, repo_arg, binding["snapshot_id"], binding["overlay_id"],
                os.fspath(question_path), os.fspath(draft_path), lifecycle_version,
            )
        except AtlasError as exc:
            raise AtlasError(f"original answer packet is stale against current map, source, or receipt evidence: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    index_parser = commands.add_parser("index", help="capture and durably save a tracked-file inventory")
    index_parser.add_argument("--repo", required=True)
    index_parser.add_argument("--db", required=True)
    compiler_index_parser = commands.add_parser("compiler-index", help="capture one immutable offline Roslyn supplement for a tracked C# project")
    compiler_index_parser.add_argument("--repo", required=True)
    compiler_index_parser.add_argument("--db", required=True)
    compiler_index_parser.add_argument("--project", required=True, help="exact repository-relative .csproj path")
    compiler_index_parser.add_argument("--framework", required=True, help="target framework moniker evaluated from the project")
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
    lifecycle_parser = commands.add_parser("answer-lifecycle", help="run the explicitly versioned one-correction answer review lifecycle")
    lifecycle_stages = lifecycle_parser.add_subparsers(dest="lifecycle_stage", required=True)
    lifecycle_prepare = lifecycle_stages.add_parser("prepare", help="prepare or validate the original versioned answer review")
    lifecycle_prepare.add_argument("--db", required=True)
    lifecycle_prepare.add_argument("--repo", required=True)
    lifecycle_prepare.add_argument("--snapshot", required=True)
    lifecycle_prepare.add_argument("--overlay", required=True)
    lifecycle_prepare.add_argument("--question-file", required=True)
    lifecycle_prepare.add_argument("--draft-file", required=True)
    lifecycle_prepare.add_argument("--review-file", help="optional independent accepted or rejected lifecycle review JSON")
    lifecycle_prepare.add_argument("--lifecycle-version", type=int, choices=(1, 2), default=1,
                                   help="default 1 is legacy/unverified and retained for byte compatibility; use 2 for an Atlas-recomputed, machine-verified evidence measurement")
    lifecycle_correct = lifecycle_stages.add_parser("correct", help="prepare a corrected answer review from one exact rejection packet")
    lifecycle_correct.add_argument("--correction-packet", required=True)
    lifecycle_correct.add_argument("--draft-file", required=True)
    lifecycle_correct.add_argument("--answer-file", required=True, help="worker-authored structured answer JSON")
    lifecycle_accept = lifecycle_stages.add_parser("accept", help="validate a fresh accepted review and emit the final answer package")
    lifecycle_accept.add_argument("--db", required=True)
    lifecycle_accept.add_argument("--repo", required=True)
    lifecycle_accept.add_argument("--packet-file", required=True)
    lifecycle_accept.add_argument("--review-file", required=True)
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
    map_prepare_parser.add_argument("--revise", action="store_true", help="revise the one current same-snapshot direct reviewed map")
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
    route_find_parser.add_argument("--route-fact-id")
    route_find_parser.add_argument("--http-method")
    route_find_parser.add_argument("--route")
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
        elif args.command == "compiler-index":
            output = compiler_index(args.db, args.repo, args.project, args.framework)
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
                args.db, args.repo, args.route_fact_id, args.draft_file, args.max_tokens, args.revise,
            )
        elif args.command == "route-map-review":
            output, encoded_output, exit_code = route_map_review(
                args.db, args.repo, args.packet_file, args.review_file,
            )
        elif args.command == "route-map-publish":
            output = publish_route_map(args.db, args.repo, args.packet_file, args.review_file)
        elif args.command == "route-find":
            output, encoded_output, exit_code = route_find(
                args.db, args.repo, args.route_fact_id, args.max_tokens, args.http_method, args.route,
            )
        elif args.command == "coverage":
            output, encoded_output, exit_code = route_coverage(args.db, args.repo, args.max_tokens, args.offset)
        elif args.command == "focus":
            output, encoded_output, exit_code = focus(args.db, args.repo, args.snapshot, args.overlay, args.max_tokens)
        elif args.command == "answer-check":
            output, encoded_output, exit_code = answer_check(args.db, args.repo, args.snapshot, args.overlay, args.question_file, args.draft_file, args.review)
        elif args.command == "answer-lifecycle":
            output, encoded_output, exit_code = answer_lifecycle(
                args.lifecycle_stage,
                db_arg=getattr(args, "db", None), repo_arg=getattr(args, "repo", None),
                snapshot_id=getattr(args, "snapshot", None), overlay_id=getattr(args, "overlay", None),
                question_path=getattr(args, "question_file", None), draft_path=getattr(args, "draft_file", None),
                review_path=getattr(args, "review_file", None), correction_path=getattr(args, "correction_packet", None),
                answer_path=getattr(args, "answer_file", None), packet_path=getattr(args, "packet_file", None),
                lifecycle_version=getattr(args, "lifecycle_version", ANSWER_LIFECYCLE_VERSION),
            )
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
