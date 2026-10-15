#!/usr/bin/env python3
"""Immutable, resumable plain-task intake backed by an append-only event journal."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import atlas


DEFAULT_MAX_BYTES = 2_147_483_647


class IntakeError(Exception):
    """An expected identity, integrity, or persistence refusal."""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_once(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise IntakeError(f"refusing to overwrite immutable intake artifact: {path}") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _source_identity(repo_arg: str, db_arg: str) -> dict[str, object]:
    db_path = Path(db_arg).expanduser().resolve(strict=True)
    if not db_path.is_file():
        raise IntakeError(f"database is not a regular file: {db_path}")
    live = atlas._live_inventory_identity(repo_arg)
    return {
        "repository": live,
        "database": {"path": os.fspath(db_path), "sha256": _file_sha(db_path)},
    }


def _append_event(events_dir: Path, event_type: str, payload: dict[str, object], previous_hash: str | None) -> dict[str, object]:
    existing = sorted(events_dir.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"))
    sequence = len(existing) + 1
    body: dict[str, object] = {
        "sequence": sequence,
        "type": event_type,
        "previous_event_sha256": previous_hash,
        "payload": payload,
    }
    digest = _sha(_json_bytes(body))
    event = {**body, "event_sha256": digest}
    _write_once(events_dir / f"{sequence:06d}.json", _json_bytes(event))
    return event


def _read_journal(run_dir: Path) -> list[dict[str, object]]:
    events_dir = run_dir / "events"
    files = sorted(events_dir.glob("*.json")) if events_dir.exists() else []
    events: list[dict[str, object]] = []
    previous_hash = None
    for index, path in enumerate(files, 1):
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntakeError(f"journal event is unreadable: {path.name}: {exc}") from exc
        if (not isinstance(event, dict) or path.name != f"{index:06d}.json"
                or set(event) != {"sequence", "type", "previous_event_sha256", "payload", "event_sha256"}):
            raise IntakeError("journal event sequence is incomplete or malformed")
        body = {key: event.get(key) for key in ("sequence", "type", "previous_event_sha256", "payload")}
        if event.get("sequence") != index or event.get("previous_event_sha256") != previous_hash:
            raise IntakeError("journal event chain has a sequence or predecessor mismatch")
        if event.get("event_sha256") != _sha(_json_bytes(body)) or not isinstance(event.get("payload"), dict):
            raise IntakeError("journal event hash or payload is invalid")
        previous_hash = str(event["event_sha256"])
        events.append(event)
    if not events or events[0].get("type") != "intake_started":
        raise IntakeError("intake journal has no valid start event")
    if any(event.get("type") not in ("intake_started", "discovery_completed") for event in events):
        raise IntakeError("intake journal contains an unknown event")
    if sum(event.get("type") == "intake_started" for event in events) != 1 or sum(event.get("type") == "discovery_completed" for event in events) > 1:
        raise IntakeError("intake journal contains duplicate lifecycle events")
    start_payload = events[0]["payload"]
    assert isinstance(start_payload, dict)
    source_identity = start_payload.get("source_identity")
    if not isinstance(source_identity, dict) or start_payload.get("source_identity_sha256") != _sha(_json_bytes(source_identity)):
        raise IntakeError("journal start event source identity hash is invalid")
    if start_payload.get("run_id") != f"intake-{start_payload.get('task_sha256')}":
        raise IntakeError("journal start event task identity is invalid")
    if type(start_payload.get("max_bytes")) is not int or start_payload["max_bytes"] < 1:
        raise IntakeError("journal start event byte budget is invalid")
    if type(start_payload.get("task_bytes")) is not int or start_payload["task_bytes"] < 1:
        raise IntakeError("journal start event task length is invalid")
    if not isinstance(start_payload.get("task_sha256"), str) or len(start_payload["task_sha256"]) != 64:
        raise IntakeError("journal start event task hash is invalid")
    if len(events) == 2:
        completed = events[1]["payload"]
        assert isinstance(completed, dict)
        discovery = completed.get("discovery")
        if (completed.get("status") not in ("awaiting-scope-review", "refused")
                or not isinstance(discovery, dict)
                or completed.get("discovery_sha256") != _sha(_json_bytes(discovery))
                or completed.get("discovery_bytes") != len(_json_bytes(discovery))):
            raise IntakeError("journal discovery completion is inconsistent")
    return events


def _verify_saved_state(run_dir: Path, events: list[dict[str, object]]) -> bytes:
    started = events[0]["payload"]
    assert isinstance(started, dict)
    task_path = run_dir / "task.txt"
    if not task_path.is_file():
        raise IntakeError("bound task artifact is missing")
    try:
        task_bytes = task_path.read_bytes()
    except OSError as exc:
        raise IntakeError(f"cannot read bound task artifact: {exc}") from exc
    if (len(task_bytes) != started.get("task_bytes")
            or _sha(task_bytes) != started.get("task_sha256")):
        raise IntakeError("bound task artifact length or hash is invalid")
    return task_bytes


def _view(run_dir: Path, events: list[dict[str, object]]) -> dict[str, object]:
    _verify_saved_state(run_dir, events)
    started = events[0]["payload"]
    assert isinstance(started, dict)
    for event in events[1:]:
        if event["type"] == "discovery_completed":
            payload = event["payload"]
            assert isinstance(payload, dict)
            return {
                "status": payload["status"],
                "semantic_scope_state": "unselected",
                "run_id": started["run_id"],
                "task_sha256": started["task_sha256"],
                "max_bytes": started["max_bytes"],
                "source_identity_sha256": started["source_identity_sha256"],
                "discovery": payload["discovery"],
            }
    return {
        "status": "intake_started",
        "semantic_scope_state": "unselected",
        "run_id": started["run_id"],
        "task_sha256": started["task_sha256"],
        "max_bytes": started["max_bytes"],
        "source_identity_sha256": started["source_identity_sha256"],
    }


def _bind_or_start(run_dir: Path, task_bytes: bytes, identity: dict[str, object], max_bytes: int, create: bool) -> list[dict[str, object]]:
    run_dir.mkdir(parents=True, exist_ok=True)
    task_path = run_dir / "task.txt"
    events_dir = run_dir / "events"
    if events_dir.exists() and any(events_dir.iterdir()):
        events = _read_journal(run_dir)
        frozen_task = _verify_saved_state(run_dir, events)
        if frozen_task != task_bytes:
            raise IntakeError("task bytes differ from the immutable task already bound to this run")
        start = events[0]["payload"]
        assert isinstance(start, dict)
        if start.get("task_sha256") != _sha(task_bytes):
            raise IntakeError("task hash does not match the intake start event")
        if start.get("source_identity") != identity:
            raise IntakeError("repository or database source identity changed since intake started")
        if start.get("max_bytes") != max_bytes:
            raise IntakeError("discovery byte budget differs from the immutable intake configuration")
        return events
    if not create:
        raise IntakeError("intake journal has not been started")
    if task_path.exists():
        if not task_path.is_file() or task_path.read_bytes() != task_bytes:
            raise IntakeError("unbound task artifact differs from the requested task")
    else:
        _write_once(task_path, task_bytes)
    events_dir.mkdir(parents=True, exist_ok=True)
    task_hash = _sha(task_bytes)
    source_hash = _sha(_json_bytes(identity))
    _append_event(events_dir, "intake_started", {
        "run_id": f"intake-{task_hash}",
        "task_sha256": task_hash,
        "task_bytes": len(task_bytes),
        "max_bytes": max_bytes,
        "source_identity_sha256": source_hash,
        "source_identity": identity,
    }, None)
    return _read_journal(run_dir)


def intake(repo: str, db: str, task_file: str, run_dir_arg: str, max_bytes: int = DEFAULT_MAX_BYTES, *, create: bool) -> dict[str, object]:
    if max_bytes < 1:
        raise IntakeError("--max-bytes must be positive")
    task_path = Path(task_file).expanduser().resolve(strict=True)
    task_bytes = task_path.read_bytes()
    try:
        task_text = task_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntakeError("task file must be valid UTF-8") from exc
    if not task_text.strip():
        raise IntakeError("task file must not be empty")
    identity = _source_identity(repo, db)
    run_dir = Path(run_dir_arg).expanduser().resolve()
    events = _bind_or_start(run_dir, task_bytes, identity, max_bytes, create)
    current = _view(run_dir, events)
    if current["status"] != "intake_started":
        return current

    terms = sorted(atlas._lexical_words(task_text))
    discovery, encoded, code = atlas.discover(db, repo, terms, max_bytes)
    if _source_identity(repo, db) != identity:
        raise IntakeError("repository or database source identity changed during discovery")
    if code != 0:
        status = "refused"
    else:
        status = "awaiting-scope-review"
    last_hash = str(events[-1]["event_sha256"])
    _append_event(run_dir / "events", "discovery_completed", {
        "status": status,
        "terms": terms,
        "discovery_sha256": _sha(encoded),
        "discovery_bytes": len(encoded),
        "discovery": discovery,
    }, last_hash)
    return _view(run_dir, _read_journal(run_dir))


def status(run_dir_arg: str) -> dict[str, object]:
    run_dir = Path(run_dir_arg).expanduser().resolve(strict=True)
    return _view(run_dir, _read_journal(run_dir))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "resume"):
        command = subparsers.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--db", required=True)
        command.add_argument("--task-file", required=True)
        command.add_argument("--run-dir", required=True)
        command.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result = status(args.run_dir)
        else:
            result = intake(args.repo, args.db, args.task_file, args.run_dir, args.max_bytes, create=args.command == "start")
        sys.stdout.write(json.dumps(result, ensure_ascii=True, sort_keys=True) + "\n")
        return 0 if result.get("status") == "awaiting-scope-review" else 3
    except (IntakeError, atlas.AtlasError, OSError) as exc:
        sys.stderr.write(f"task intake refused: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
