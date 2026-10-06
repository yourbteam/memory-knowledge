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
        raise AtlasError(f"reviewed-flow overlay not found: {overlay_id}")
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
        _validate_review_receipt(receipt, snapshot_id, overlay_id, payload["content_hash"], flow["extractor_identity"])
        review_status = receipt["decision"]
    return {
        "snapshot_id": snapshot_id,
        "overlay_id": overlay_id,
        "content_hash": payload["content_hash"],
        "validation": "content integrity and source references verified; semantic review is represented by a matching receipt and is not mechanically validated by Atlas",
        "review_status": review_status,
        "overlay": payload,
        "review_receipt": receipt_payload,
    }


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
    review_parser = commands.add_parser("flow-review", help="attach one immutable review receipt to an exact overlay")
    review_parser.add_argument("--db", required=True)
    review_parser.add_argument("--snapshot", required=True)
    review_parser.add_argument("--overlay", required=True)
    review_parser.add_argument("--input", required=True)
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
        elif args.command == "flow-add":
            output = attach_flow(args.db, args.snapshot, args.input)
        elif args.command == "flow-review":
            output = attach_review(args.db, args.snapshot, args.overlay, args.input)
        elif args.command == "focus":
            output, encoded_output, exit_code = focus(args.db, args.repo, args.snapshot, args.overlay, args.max_tokens)
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
