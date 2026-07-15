#!/usr/bin/env python3
"""Promote a ready discovery into a registered sequence with journaled recovery."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts import sequence_discovery_log, work_memory
except ImportError:
    import sequence_discovery_log  # type: ignore
    import work_memory  # type: ignore


STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "kamen-work-memory"
JOURNAL = STATE_DIR / "promotion.json"
PROMOTION_LOCK = STATE_DIR / "promotion.lock"
ABSENT = "<absent>"


def _hash(path: Path) -> str:
    return work_memory.sha256_bytes(path.read_bytes()) if path.exists() else ABSENT


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, data: bytes) -> None:
    work_memory._atomic_write(path, data)


def _journal_write(value: dict[str, Any]) -> None:
    _write(JOURNAL, work_memory.canonical_bytes(value)); _fsync_dir(JOURNAL.parent)


def _crash(label: str) -> None:
    if os.environ.get("MK_PROMOTION_CRASH_AT") == label:
        raise OSError(f"injected-crash:{label}")


def _decode(value: str) -> bytes:
    return base64.b64decode(value.encode())


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode()


def _cleanup(journal: dict[str, Any]) -> None:
    for target in journal["targets"]:
        Path(target["staged_path"]).unlink(missing_ok=True)
        Path(target["backup_path"]).unlink(missing_ok=True)
    JOURNAL.unlink(missing_ok=True); _fsync_dir(JOURNAL.parent)


def recover() -> dict[str, Any] | None:
    if not JOURNAL.is_file():
        return None
    journal = json.loads(JOURNAL.read_text())
    targets = journal.get("targets", [])
    if not isinstance(targets, list) or journal.get("phase") not in {"PREPARED", "APPLYING", "COMMITTED"}:
        raise work_memory.WorkMemoryError("invalid-promotion-journal", 3)
    observed = [_hash(Path(item["path"])) for item in targets]
    preimages = [item["preimage_hash"] for item in targets]
    staged = [item["staged_hash"] for item in targets]
    phase = journal["phase"]
    if phase == "PREPARED":
        if observed != preimages:
            raise work_memory.WorkMemoryError("promotion-recovery-conflict", 3)
        _cleanup(journal)
        return {"recovered": "prepared-cleaned"}
    if phase == "APPLYING":
        if observed == staged:
            journal["phase"] = "COMMITTED"; _journal_write(journal); _cleanup(journal)
            return {"recovered": "applying-completed"}
        if all(actual in {before, after} for actual, before, after in zip(observed, preimages, staged)):
            for item in targets:
                target = Path(item["path"])
                if item["preimage_hash"] == ABSENT:
                    target.unlink(missing_ok=True)
                else:
                    _write(target, _decode(item["preimage_bytes"]))
                _fsync_dir(target.parent)
            _cleanup(journal)
            return {"recovered": "applying-rolled-back"}
        raise work_memory.WorkMemoryError("promotion-recovery-conflict", 3)
    if observed != staged:
        raise work_memory.WorkMemoryError("promotion-recovery-conflict", 3)
    _cleanup(journal)
    return {"recovered": "committed-cleaned"}


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match:
        raise work_memory.WorkMemoryError(f"missing-discovery-section:{heading}", 3)
    return match.group(1).strip()


def _sequence_text(discovery: Path, sequence_id: str, use_when: str, pass_signal: str) -> bytes:
    text = discovery.read_text()
    name = discovery.stem
    intended = _section(text, "Intended Outcome")
    inputs = _section(text, "Required Inputs, Auth, Or Environment")
    commands = _section(text, "Commands And Observations")
    failure = _section(text, "Failure Handling")
    verified = _section(text, "Verified Path")
    body = f"""# {sequence_id}

## Use When

{use_when.strip()}

## Outcome

{intended}

## Required Inputs

{inputs}

## Commands

{commands}

## Failure Handling

{failure}

## Verification

{verified}

Pass signal: {pass_signal.strip()}

Promoted from `{name}`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
"""
    return body.encode()


def _registry_bytes(
    sequence_id: str, use_when: str, automation: str, pass_signal: str,
    operation_kinds: list[str], lineage_id: str,
) -> bytes:
    text = work_memory.REGISTRY.read_text()
    rows, _ = work_memory.registry_rows()
    if any(row["sequence_id"] == sequence_id for row in rows):
        raise work_memory.WorkMemoryError("sequence-id-already-registered", 3)
    if any(kind not in work_memory.OPERATION_KINDS for kind in operation_kinds):
        raise work_memory.WorkMemoryError("invalid-operation-kind", 2)
    cells = [sequence_id, use_when, f"operations/sequences/{sequence_id}/", automation,
             pass_signal, ",".join(sorted(set(operation_kinds))), lineage_id]
    if any("|" in value or "\n" in value for value in cells):
        raise work_memory.WorkMemoryError("invalid-registry-cell", 2)
    row = "| `" + cells[0] + "` | " + cells[1] + " | `" + cells[2] + "` | " + cells[3] + " | " + cells[4] + " | `" + cells[5] + "` | `" + cells[6] + "` |\n"
    marker = "\n\n## Missing Sequence Discovery"
    if marker not in text:
        raise work_memory.WorkMemoryError("registry-insertion-marker-missing", 3)
    return text.replace(marker, "\n" + row + marker, 1).encode()


def _registered_bundle_from_staged(
    sequence_id: str,
    sequence_bytes: bytes,
    manifest_bytes: bytes,
    manifest: dict[str, Any],
    *,
    repo_roots_file: str | None = None,
) -> tuple[list[dict[str, str]], str]:
    temp_dir = work_memory.ROOT / "operations/sequences" / f".promotion-{sequence_id}-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True)
    try:
        _write(temp_dir / "sequence.md", sequence_bytes)
        _write(temp_dir / "dependencies.json", manifest_bytes)
        entries, _, _ = work_memory.resolve_bundle(
            mode="registered", subject_id=sequence_id, document=temp_dir / "sequence.md",
            manifest=temp_dir / "dependencies.json",
            repo_roots_file=repo_roots_file,
        )
        prefix = str(temp_dir.relative_to(work_memory.ROOT))
        final = f"operations/sequences/{sequence_id}"
        for entry in entries:
            if entry["repository_key"] == "memory-knowledge" and entry["path"].startswith(prefix + "/"):
                entry["path"] = final + entry["path"][len(prefix):]
        entries.sort(key=lambda item: (item["repository_key"], item["path"], item["sha256"]))
        return entries, work_memory.sha256_bytes(work_memory.canonical_bytes(entries))
    finally:
        for child in temp_dir.iterdir():
            child.unlink()
        temp_dir.rmdir()


def _promoted_discovery_bytes(path: Path, sequence_id: str) -> bytes:
    text = path.read_text()
    for name, value in (("Status", "promoted"), ("PromotedSequenceId", sequence_id)):
        pattern = re.compile(rf"^{name}:.*$", re.M)
        if pattern.search(text):
            text = pattern.sub(f"{name}: {value}", text, count=1)
        else:
            text = text.replace("\nCreatedAtUtc:", f"\n{name}: {value}\nCreatedAtUtc:", 1)
    return text.encode()


def cmd_promote(args: argparse.Namespace) -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with PROMOTION_LOCK.open("a+b") as promotion_handle:
        fcntl.flock(promotion_handle.fileno(), fcntl.LOCK_EX)
        recovered = recover()
        discovery = Path(args.file).resolve()
        repo_roots_file = getattr(args, "repo_roots_file", None)
        state = sequence_discovery_log.discovery_state(
            discovery, repo_roots_file=repo_roots_file,
        )
        if state["status"] == "promoted":
            promoted_id = sequence_discovery_log._metadata(
                discovery.read_text(), "PromotedSequenceId"
            )
            if promoted_id != args.sequence_id:
                raise work_memory.WorkMemoryError("promotion-identity-conflict", 3)
            sequence_path = work_memory.ROOT / f"operations/sequences/{args.sequence_id}/sequence.md"
            registered_manifest_path = sequence_path.with_name("dependencies.json")
            source_manifest = json.loads(discovery.with_suffix(".dependencies.json").read_text())
            expected_manifest = {
                "schema_version": 1, "lineage_id": state["discovery_id"],
                "dependencies": source_manifest["dependencies"],
            }
            expected_sequence = _sequence_text(
                discovery, args.sequence_id, args.use_when, args.pass_signal
            )
            if (
                not sequence_path.is_file() or sequence_path.read_bytes() != expected_sequence
                or not registered_manifest_path.is_file()
                or registered_manifest_path.read_bytes() != work_memory.canonical_bytes(expected_manifest)
            ):
                raise work_memory.WorkMemoryError("promotion-target-drift", 3)
            _, new_bundle_hash, lineage = work_memory.resolve_bundle(
                mode="registered", subject_id=args.sequence_id, document=sequence_path,
                manifest=registered_manifest_path,
                repo_roots_file=repo_roots_file,
            )
            row = next(
                (item for item in work_memory.registry_rows()[0]
                 if item["sequence_id"] == args.sequence_id), None
            )
            if (
                row is None or row["lineage_id"] != lineage
                or row["use_when"] != args.use_when
                or row["automation"] != args.automation_display
                or row["pass_signal"] != args.pass_signal
                or sorted(row["operation_kinds"].split(",")) != sorted(set(args.operation_kind))
            ):
                raise work_memory.WorkMemoryError("promotion-registry-drift", 3)
            events, ledger_hash = work_memory.load_ledger()
            promoted = next((
                event for event in events
                if event["event_type"] == "discovery_promoted"
                and event["discovery_id"] == state["discovery_id"]
                and event["sequence_id"] == args.sequence_id
                and event["new_bundle_hash"] == new_bundle_hash
            ), None)
            transition = next((
                event for event in events
                if event["event_type"] == "bundle_transition_recorded"
                and event["transition_reason"] == "promotion"
                and event["discovery_id"] == state["discovery_id"]
                and event["promoted_sequence_id"] == args.sequence_id
                and event["new_bundle_hash"] == new_bundle_hash
            ), None)
            if promoted is None or transition is None:
                raise work_memory.WorkMemoryError("promotion-ledger-drift", 3)
            return {
                "ok": True, "idempotent_retry": True, "sequence_id": args.sequence_id,
                "sequence_path": str(sequence_path),
                "manifest_path": str(registered_manifest_path),
                "old_bundle_hash": promoted["old_bundle_hash"],
                "new_bundle_hash": new_bundle_hash, "event_id": promoted["event_id"],
                "transition_event_id": transition["event_id"],
                "ledger_hash": ledger_hash, "recovery": recovered,
            }
        if state["status"] not in {"ready", "overdue"} or state["unmet_predicates"]:
            raise work_memory.WorkMemoryError("discovery-not-ready", 3)
        manifest_path = discovery.with_suffix(".dependencies.json")
        manifest = json.loads(manifest_path.read_text())
        if manifest["lineage_id"] != state["discovery_id"]:
            raise work_memory.WorkMemoryError("discovery-lineage-mismatch", 3)
        registered_manifest = {"schema_version": 1, "lineage_id": state["discovery_id"],
                               "dependencies": manifest["dependencies"]}
        manifest_bytes = work_memory.canonical_bytes(registered_manifest)
        sequence_bytes = _sequence_text(discovery, args.sequence_id, args.use_when, args.pass_signal)
        bundle, new_bundle_hash = _registered_bundle_from_staged(
            args.sequence_id,
            sequence_bytes,
            manifest_bytes,
            registered_manifest,
            repo_roots_file=repo_roots_file,
        )
        registry_bytes = _registry_bytes(
            args.sequence_id, args.use_when, args.automation_display, args.pass_signal,
            args.operation_kind, state["discovery_id"],
        )
        discovery_bytes = _promoted_discovery_bytes(discovery, args.sequence_id)
        ledger_lock = work_memory.LEDGER.with_suffix(work_memory.LEDGER.suffix + ".lock")
        ledger_lock.parent.mkdir(parents=True, exist_ok=True)
        with ledger_lock.open("a+b") as ledger_handle:
            fcntl.flock(ledger_handle.fileno(), fcntl.LOCK_EX)
            ledger_before = work_memory.LEDGER.read_bytes() if work_memory.LEDGER.exists() else b""
            now = work_memory.utc_now()
            namespace = uuid.uuid5(uuid.NAMESPACE_URL, f"{state['discovery_id']}:{args.sequence_id}:{state['source_bundle_hash']}:{new_bundle_hash}")
            promoted = {
                "schema_version": 1, "event_id": str(uuid.uuid5(namespace, "discovery-promoted")),
                "event_type": "discovery_promoted", "recorded_at_utc": now,
                "discovery_id": state["discovery_id"], "sequence_id": args.sequence_id,
                "lineage_id": state["discovery_id"], "old_bundle_hash": state["source_bundle_hash"],
                "new_bundle_hash": new_bundle_hash, "promoted_at_utc": now,
            }
            transition = {
                "schema_version": 1, "event_id": str(uuid.uuid5(namespace, "bundle-transition")),
                "event_type": "bundle_transition_recorded", "recorded_at_utc": now,
                "lineage_id": state["discovery_id"], "old_bundle_hash": state["source_bundle_hash"],
                "new_bundle_hash": new_bundle_hash, "transition_reason": "promotion",
                "discovery_id": state["discovery_id"], "promoted_sequence_id": args.sequence_id,
                "correction_ids": [],
            }
            ledger_bytes, view_bytes, ledger_result = work_memory.stage_event_batch(
                ledger_before, {"schema_version": 1, "expected_ledger_hash": work_memory.sha256_bytes(ledger_before),
                                "events": [promoted, transition]},
            )
            target_data = {
                work_memory.ROOT / f"operations/sequences/{args.sequence_id}/sequence.md": sequence_bytes,
                work_memory.ROOT / f"operations/sequences/{args.sequence_id}/dependencies.json": manifest_bytes,
                work_memory.REGISTRY: registry_bytes, discovery: discovery_bytes,
                work_memory.LEDGER: ledger_bytes, work_memory.BLOCKER_VIEW: view_bytes,
            }
            targets = []
            for index, (path, data) in enumerate(target_data.items()):
                path.parent.mkdir(parents=True, exist_ok=True)
                staged_path = STATE_DIR / f"target-{index}.staged"
                backup_path = STATE_DIR / f"target-{index}.backup"
                preimage = path.read_bytes() if path.exists() else b""
                _write(staged_path, data)
                if path.exists():
                    _write(backup_path, preimage)
                targets.append({
                    "path": str(path), "preimage_hash": _hash(path),
                    "staged_hash": work_memory.sha256_bytes(data), "staged_path": str(staged_path),
                    "backup_path": str(backup_path),
                    "preimage_bytes": _encode(preimage) if path.exists() else "",
                })
            journal = {"schema_version": 1, "phase": "PREPARED", "targets": targets,
                       "sequence_id": args.sequence_id}
            _journal_write(journal); _crash("prepared")
            journal["phase"] = "APPLYING"; _journal_write(journal); _crash("applying")
            for index, item in enumerate(targets):
                path = Path(item["path"])
                _write(path, Path(item["staged_path"]).read_bytes()); _fsync_dir(path.parent)
                _crash(f"replaced-{index}")
            journal["phase"] = "COMMITTED"; _journal_write(journal); _crash("committed")
            _cleanup(journal)
        return {
            "ok": True, "sequence_id": args.sequence_id,
            "sequence_path": str(work_memory.ROOT / f"operations/sequences/{args.sequence_id}/sequence.md"),
            "manifest_path": str(work_memory.ROOT / f"operations/sequences/{args.sequence_id}/dependencies.json"),
            "old_bundle_hash": state["source_bundle_hash"], "new_bundle_hash": new_bundle_hash,
            "event_id": promoted["event_id"], "transition_event_id": transition["event_id"],
            "ledger_hash": ledger_result["ledger_hash"], "recovery": recovered,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    promote = sub.add_parser("promote"); promote.add_argument("--file", required=True); promote.add_argument("--sequence-id", required=True)
    promote.add_argument("--use-when", required=True); promote.add_argument("--operation-kind", action="append", required=True)
    promote.add_argument("--automation-display", required=True); promote.add_argument("--pass-signal", required=True)
    promote.add_argument("--repo-roots-file")
    promote.set_defaults(func=cmd_promote); return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv); print(json.dumps(args.func(args), sort_keys=True)); return 0
    except work_memory.WorkMemoryError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr); return exc.exit_code
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr); return 5


if __name__ == "__main__":
    raise SystemExit(main())
