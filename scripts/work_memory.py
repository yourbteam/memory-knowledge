#!/usr/bin/env python3
"""Canonical work-only memory ledger, receipts, bundles, and run lifecycle."""

from __future__ import annotations

import argparse
import base64
import fcntl
import fnmatch
import hashlib
import json
import os
import re
import statistics
import sys
import tempfile
import urllib.parse
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "operations/work-memory/events.jsonl"
BLOCKER_VIEW = ROOT / "operations/blockers/BLOCKERS.md"
REGISTRY = ROOT / "operations/sequences/SEQUENCES.md"
RECEIPT_ROOT = Path("/private/tmp/work-memory")
OPERATION_KINDS = {
    "image", "container", "auth", "deploy", "workflow-drive", "package",
    "database", "remote-operator", "cleanup", "other", "read-only",
    "single-test", "single-build",
}
ALWAYS_OPERATIONAL = {"image", "container", "auth", "deploy", "workflow-drive"}
CONDITIONAL_OPERATIONAL = {"package", "database", "remote-operator", "cleanup", "other"}
NON_OPERATIONAL = {"read-only", "single-test", "single-build"}
EVENT_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "run_started": (
        {"run_id", "subject_id", "lineage_id", "mode", "operation_kind", "source_bundle",
         "source_bundle_hash", "classification_receipt_hash", "selection_receipt_hash",
         "started_at_utc"},
        {"predecessor_run_id", "verifies_correction_ids"},
    ),
    "blocker_opened": (
        {"run_id", "blocker_id", "occurrence_id", "fingerprint", "subject_id", "lineage_id",
         "step_id", "surface", "symptom", "evidence", "impact", "boundary", "status"}, set(),
    ),
    "blocker_recurred": (
        {"run_id", "blocker_id", "occurrence_id", "previous_status", "status", "evidence"}, set(),
    ),
    "correction_recorded": (
        {"run_id", "blocker_id", "occurrence_id", "correction_id", "subject_id", "lineage_id",
         "step_id", "changed_artifacts", "changed_artifact_hashes", "reusable_behavior_changed",
         "solution"}, {"supersedes_correction_id"},
    ),
    "bundle_transition_recorded": (
        {"lineage_id", "old_bundle_hash", "new_bundle_hash", "transition_reason"},
        {"run_id", "correction_ids", "changed_artifacts", "changed_artifact_hashes",
         "discovery_id", "promoted_sequence_id"},
    ),
    "verification_recorded": (
        {"run_id", "subject_id", "lineage_id", "source_bundle_hash", "outcome", "quality",
         "evidence", "blocker_ids", "correction_ids", "changed_artifact_hashes"}, set(),
    ),
    "blocker_transitioned": (
        {"run_id", "blocker_id", "from_status", "to_status"},
        {"verification_event_id", "remaining_work", "supersession_evidence", "non_gap_evidence"},
    ),
    "run_closed": (
        {"run_id", "subject_id", "lineage_id", "result", "completed_at_utc", "correction_count",
         "blocker_ids", "sequence_updated", "verification_quality"}, set(),
    ),
    "run_abandoned": (
        {"run_id", "subject_id", "lineage_id", "completed_at_utc", "reason"}, set(),
    ),
    "discovery_promoted": (
        {"discovery_id", "sequence_id", "lineage_id", "old_bundle_hash", "new_bundle_hash",
         "promoted_at_utc"}, set(),
    ),
}
BASE_FIELDS = {"schema_version", "event_id", "event_type", "recorded_at_utc"}
FORBIDDEN_KEYS = {
    "person", "people", "contact", "relationship", "profile", "diary", "journal",
    "transcript", "conversation_history", "chat_history", "message_history",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"(?:\?|&)sig=[^&\s]+", re.I),
)
PERSONAL_PATTERNS = (
    re.compile(r"\b(?:my|our|his|her|their)\s+(?:wife|husband|partner|mother|father|family|health)\b", re.I),
    re.compile(r"\b(?:i|we|[A-Z][a-z]+)\s+(?:prefer|prefers|like|likes|love|loves|hate|hates|feel|feels|went|visited|ate|slept)\b", re.I),
    re.compile(r"\b(?:diary|journal)\s+entry\b", re.I),
    re.compile(r"\b(?:user|personal)\s+profile\b", re.I),
)


class WorkMemoryError(Exception):
    def __init__(self, code: str, exit_code: int = 3):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise WorkMemoryError("invalid-timestamp", 2) from exc
    if parsed.tzinfo is None:
        raise WorkMemoryError("invalid-timestamp", 2)
    return parsed.astimezone(UTC)


def require_uuid(value: Any, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise WorkMemoryError(f"invalid-{field}", 2) from exc


def require_id(value: Any, field: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", text):
        raise WorkMemoryError(f"invalid-{field}", 2)
    return text


def _validate_work_only(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise WorkMemoryError(f"prohibited-memory-shape:{path}.{key}", 2)
            _validate_work_only(child, f"{path}.{key}")
    elif isinstance(value, list):
        if len(value) > 100:
            raise WorkMemoryError(f"work-memory-array-too-large:{path}", 2)
        for index, child in enumerate(value):
            _validate_work_only(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) > 4000:
            raise WorkMemoryError(f"work-memory-text-too-large:{path}", 2)
        decoded = value
        for _ in range(3):
            next_value = urllib.parse.unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        if any(pattern.search(decoded) for pattern in SECRET_PATTERNS):
            raise WorkMemoryError(f"prohibited-secret-shape:{path}", 2)
        if any(pattern.search(decoded) for pattern in PERSONAL_PATTERNS):
            raise WorkMemoryError(f"prohibited-memory-shape:{path}", 2)


def _validate_event_shape(event: dict[str, Any]) -> None:
    if not isinstance(event, dict):
        raise WorkMemoryError("event-must-be-object", 2)
    event_type = event.get("event_type")
    if event_type not in EVENT_FIELDS:
        raise WorkMemoryError("unknown-event-type", 2)
    required, optional = EVENT_FIELDS[event_type]
    allowed = BASE_FIELDS | required | optional
    missing = (BASE_FIELDS | required) - set(event)
    extra = set(event) - allowed
    if missing:
        raise WorkMemoryError("missing-event-fields:" + ",".join(sorted(missing)), 2)
    if extra:
        raise WorkMemoryError("unknown-event-fields:" + ",".join(sorted(extra)), 2)
    if event.get("schema_version") != SCHEMA_VERSION:
        raise WorkMemoryError("unsupported-event-schema", 2)
    require_uuid(event["event_id"], "event-id")
    parse_utc(event["recorded_at_utc"])
    _validate_work_only(event)
    _validate_event_values(event)


def _require_list(event: dict[str, Any], field: str, *, nonempty: bool = False) -> list[Any]:
    value = event.get(field)
    if not isinstance(value, list) or (nonempty and not value):
        raise WorkMemoryError(f"invalid-{field.replace('_', '-')}", 2)
    return value


def _validate_event_values(event: dict[str, Any]) -> None:
    kind = event["event_type"]
    for field in ("run_id", "occurrence_id", "correction_id", "predecessor_run_id"):
        if field in event:
            require_uuid(event[field], field.replace("_", "-"))
    if kind == "run_started":
        if event["mode"] not in {"registered", "discovery"} or event["operation_kind"] not in OPERATION_KINDS:
            raise WorkMemoryError("invalid-run-start-enum", 2)
        if ("predecessor_run_id" in event) != ("verifies_correction_ids" in event):
            raise WorkMemoryError("incomplete-successor-binding", 2)
        if "verifies_correction_ids" in event:
            _require_list(event, "verifies_correction_ids", nonempty=True)
    elif kind in {"blocker_opened", "blocker_recurred"}:
        if event["status"] != "open":
            raise WorkMemoryError("invalid-blocker-open-status", 2)
        if kind == "blocker_recurred" and event["previous_status"] != "closed":
            raise WorkMemoryError("invalid-recurrence-state", 2)
    elif kind == "correction_recorded":
        artifacts = _require_list(event, "changed_artifacts", nonempty=True)
        hashes = _require_list(event, "changed_artifact_hashes", nonempty=True)
        if len(artifacts) != len(hashes) or not isinstance(event["reusable_behavior_changed"], bool):
            raise WorkMemoryError("invalid-correction-artifacts", 2)
    elif kind == "bundle_transition_recorded":
        reason = event["transition_reason"]
        if reason == "correction":
            required = {"run_id", "correction_ids", "changed_artifacts", "changed_artifact_hashes"}
            prohibited = {"discovery_id", "promoted_sequence_id"}
            if not required <= set(event) or prohibited & set(event):
                raise WorkMemoryError("invalid-correction-transition", 2)
            ids = _require_list(event, "correction_ids", nonempty=True)
            arts = _require_list(event, "changed_artifacts", nonempty=True)
            hashes = _require_list(event, "changed_artifact_hashes", nonempty=True)
            if not ids or len(arts) != len(hashes):
                raise WorkMemoryError("invalid-correction-transition", 2)
        elif reason == "promotion":
            required = {"discovery_id", "promoted_sequence_id", "correction_ids"}
            prohibited = {"run_id", "changed_artifacts", "changed_artifact_hashes"}
            if not required <= set(event) or prohibited & set(event) or event["correction_ids"] != []:
                raise WorkMemoryError("invalid-promotion-transition", 2)
        else:
            raise WorkMemoryError("invalid-transition-reason", 2)
    elif kind == "verification_recorded":
        if event["outcome"] not in {"passed", "failed"} or event["quality"] not in {"proxy", "same-path"}:
            raise WorkMemoryError("invalid-verification-enum", 2)
        blockers = _require_list(event, "blocker_ids")
        corrections = _require_list(event, "correction_ids")
        hashes = _require_list(event, "changed_artifact_hashes")
        if bool(blockers) != bool(corrections) or bool(corrections) != bool(hashes):
            raise WorkMemoryError("incomplete-verification-binding", 2)
    elif kind == "blocker_transitioned":
        target = event["to_status"]
        expected_optional = {
            "fixed-awaiting-verification": set(),
            "verified": {"verification_event_id"},
            "closed": {"verification_event_id", "remaining_work"},
            "superseded": {"supersession_evidence"},
            "non-gap": {"non_gap_evidence"},
        }
        if target not in expected_optional or not expected_optional[target] <= set(event):
            raise WorkMemoryError("invalid-blocker-transition-fields", 2)
        optional_present = set(event) & EVENT_FIELDS[kind][1]
        if optional_present != expected_optional[target] or (target == "closed" and event["remaining_work"] != "none"):
            raise WorkMemoryError("invalid-blocker-transition-fields", 2)
    elif kind == "run_closed":
        if event["result"] not in {"passed", "failed"} or event["verification_quality"] not in {"none", "proxy", "same-path"}:
            raise WorkMemoryError("invalid-run-close-enum", 2)
        if not isinstance(event["correction_count"], int) or event["correction_count"] < 0:
            raise WorkMemoryError("invalid-correction-count", 2)


def parse_ledger_bytes(data: bytes) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_no, raw in enumerate(data.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkMemoryError(f"malformed-ledger-line:{line_no}", 3) from exc
        try:
            _validate_event_shape(event)
        except WorkMemoryError as exc:
            raise WorkMemoryError(f"invalid-ledger-line:{line_no}:{exc.code}", 3) from exc
        events.append(event)
    validate_lifecycle(events)
    return events


def _event_index(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = event["event_id"]
        if event_id in index and index[event_id] != event:
            raise WorkMemoryError("event-id-conflict", 3)
        index[event_id] = event
    return index


def validate_lifecycle(events: list[dict[str, Any]]) -> None:
    _event_index(events)
    runs: dict[str, dict[str, Any]] = {}
    blockers: dict[str, str] = {}
    blocker_meta: dict[str, dict[str, Any]] = {}
    corrections: dict[str, dict[str, Any]] = {}
    verifications: dict[str, dict[str, Any]] = {}
    for event in events:
        kind = event["event_type"]
        run_id = event.get("run_id")
        if kind == "run_started":
            if run_id in runs:
                raise WorkMemoryError("duplicate-run-start", 3)
            runs[run_id] = {"start": event, "terminal": None, "blockers": set(), "corrections": [], "verifications": []}
            continue
        if run_id is not None:
            if run_id not in runs:
                raise WorkMemoryError("event-before-run-start", 3)
            if runs[run_id]["terminal"] is not None:
                raise WorkMemoryError("event-after-terminal", 3)
        if kind == "blocker_opened":
            if event["blocker_id"] in blockers:
                raise WorkMemoryError("duplicate-blocker-open", 3)
            blockers[event["blocker_id"]] = "open"
            blocker_meta[event["blocker_id"]] = event
            runs[run_id]["blockers"].add(event["blocker_id"])
        elif kind == "blocker_recurred":
            if blockers.get(event["blocker_id"]) != "closed":
                raise WorkMemoryError("invalid-blocker-recurrence", 3)
            blockers[event["blocker_id"]] = "open"
            runs[run_id]["blockers"].add(event["blocker_id"])
        elif kind == "correction_recorded":
            if blockers.get(event["blocker_id"]) != "open":
                raise WorkMemoryError("correction-for-nonopen-blocker", 3)
            if event.get("supersedes_correction_id") and event["supersedes_correction_id"] not in corrections:
                raise WorkMemoryError("unknown-superseded-correction", 3)
            corrections[event["correction_id"]] = event
            runs[run_id]["corrections"].append(event)
        elif kind == "verification_recorded":
            start = runs[run_id]["start"]
            if event["subject_id"] != start["subject_id"] or event["lineage_id"] != start["lineage_id"]:
                raise WorkMemoryError("verification-run-binding-mismatch", 3)
            if event["source_bundle_hash"] != start["source_bundle_hash"]:
                raise WorkMemoryError("verification-bundle-mismatch", 3)
            if event["correction_ids"]:
                run_corrections = {item["correction_id"]: item for item in runs[run_id]["corrections"]}
                successor_ids = set(start.get("verifies_correction_ids", []))
                available = set(run_corrections) | successor_ids
                if set(event["correction_ids"]) != available:
                    raise WorkMemoryError("verification-correction-mismatch", 3)
                selected = [corrections[item] for item in event["correction_ids"] if item in corrections]
                if len(selected) != len(event["correction_ids"]):
                    raise WorkMemoryError("verification-correction-not-found", 3)
                if set(event["blocker_ids"]) != {item["blocker_id"] for item in selected}:
                    raise WorkMemoryError("verification-blocker-mismatch", 3)
                expected_hashes = [value for item in selected for value in item["changed_artifact_hashes"]]
                if event["changed_artifact_hashes"] != expected_hashes:
                    raise WorkMemoryError("verification-artifact-hash-mismatch", 3)
            elif runs[run_id]["blockers"] or runs[run_id]["corrections"]:
                raise WorkMemoryError("clean-verification-after-correction", 3)
            verifications[event["event_id"]] = event
            runs[run_id]["verifications"].append(event)
        elif kind == "blocker_transitioned":
            current = blockers.get(event["blocker_id"])
            if current != event["from_status"]:
                raise WorkMemoryError("blocker-from-status-mismatch", 3)
            valid = {
                "open": {"fixed-awaiting-verification", "superseded", "non-gap"},
                "fixed-awaiting-verification": {"verified"}, "verified": {"closed"},
            }
            if event["to_status"] not in valid.get(current, set()):
                raise WorkMemoryError("invalid-blocker-status-transition", 3)
            verification_id = event.get("verification_event_id")
            if verification_id:
                verification = verifications.get(verification_id)
                if (
                    not verification or verification["outcome"] != "passed"
                    or verification["quality"] != "same-path"
                    or verification["run_id"] != event["run_id"]
                    or event["blocker_id"] not in verification["blocker_ids"]
                ):
                    raise WorkMemoryError("invalid-transition-verification", 3)
                candidates = [item for item in corrections.values() if item["blocker_id"] == event["blocker_id"]]
                superseded = {item.get("supersedes_correction_id") for item in candidates}
                active = [item for item in candidates if item["correction_id"] not in superseded]
                active_ids = {item["correction_id"] for item in active}
                successor = runs[event["run_id"]]["start"]
                predecessor_ids = {item["run_id"] for item in active}
                if (
                    not active_ids
                    or set(verification["correction_ids"]) != active_ids
                    or set(successor.get("verifies_correction_ids", [])) != active_ids
                    or successor.get("predecessor_run_id") not in predecessor_ids
                    or verification["lineage_id"] != blocker_meta[event["blocker_id"]]["lineage_id"]
                ):
                    raise WorkMemoryError("verification-successor-binding-mismatch", 3)
            blockers[event["blocker_id"]] = event["to_status"]
        elif kind in {"run_closed", "run_abandoned"}:
            start = runs[run_id]["start"]
            if event["subject_id"] != start["subject_id"] or event["lineage_id"] != start["lineage_id"]:
                raise WorkMemoryError("terminal-run-binding-mismatch", 3)
            if kind == "run_closed":
                if event["correction_count"] != len(runs[run_id]["corrections"]):
                    raise WorkMemoryError("terminal-correction-count-mismatch", 3)
                quality = runs[run_id]["verifications"][-1]["quality"] if runs[run_id]["verifications"] else "none"
                if event["verification_quality"] != quality:
                    raise WorkMemoryError("terminal-verification-quality-mismatch", 3)
            runs[run_id]["terminal"] = event


def stage_event_batch(existing: bytes, request: dict[str, Any]) -> tuple[bytes, bytes, dict[str, Any]]:
    """Pure, non-locking reducer used by transact and promotion."""
    if set(request) != {"schema_version", "expected_ledger_hash", "events"} or request.get("schema_version") != 1:
        raise WorkMemoryError("invalid-transact-request", 2)
    if not isinstance(request.get("events"), list) or not request["events"]:
        raise WorkMemoryError("empty-event-batch", 2)
    previous_hash = sha256_bytes(existing)
    if request["expected_ledger_hash"] is not None and request["expected_ledger_hash"] != previous_hash:
        raise WorkMemoryError("ledger-hash-conflict", 3)
    current = parse_ledger_bytes(existing)
    by_id = _event_index(current)
    added: list[dict[str, Any]] = []
    idempotent: list[str] = []
    for event in request["events"]:
        _validate_event_shape(event)
        prior = by_id.get(event["event_id"])
        if prior is not None:
            if prior != event:
                raise WorkMemoryError("event-id-conflict", 3)
            idempotent.append(event["event_id"])
            continue
        by_id[event["event_id"]] = event
        added.append(event)
    result_events = current + added
    validate_lifecycle(result_events)
    ledger_bytes = b"".join(canonical_bytes(event) for event in result_events)
    ledger_hash = sha256_bytes(ledger_bytes)
    view_bytes = render_blocker_view(result_events, ledger_hash).encode()
    response = {
        "ok": True, "previous_ledger_hash": previous_hash, "ledger_hash": ledger_hash,
        "event_ids": [event["event_id"] for event in request["events"]],
        "idempotent_event_ids": idempotent, "blocker_view_hash": sha256_bytes(view_bytes),
    }
    return ledger_bytes, view_bytes, response


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        tmp.unlink(missing_ok=True)


def transact(request: dict[str, Any], ledger: Path = LEDGER, view: Path = BLOCKER_VIEW) -> dict[str, Any]:
    lock = ledger.with_suffix(ledger.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        existing = ledger.read_bytes() if ledger.exists() else b""
        ledger_bytes, view_bytes, response = stage_event_batch(existing, request)
        _atomic_write(ledger, ledger_bytes)
        try:
            _atomic_write(view, view_bytes)
        except OSError as exc:
            raise WorkMemoryError("view-write-failed:ledger-committed", 5) from exc
    return response


def render_blocker_view(events: list[dict[str, Any]], ledger_hash: str) -> str:
    blockers: dict[str, dict[str, Any]] = {}
    for event in events:
        if event["event_type"] == "blocker_opened":
            blockers[event["blocker_id"]] = dict(event)
        elif event["event_type"] == "blocker_recurred" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]].update(status="open", evidence=event["evidence"])
        elif event["event_type"] == "blocker_transitioned" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]]["status"] = event["to_status"]
    lines = ["# Work Blockers", "", f"Ledger-SHA256: `{ledger_hash}`", "",
             "This file is generated from `operations/work-memory/events.jsonl`.", ""]
    for blocker_id in sorted(blockers):
        item = blockers[blocker_id]
        lines.extend([
            f"## {blocker_id}", "", f"- Status: `{item['status']}`",
            f"- Subject: `{item['subject_id']}`", f"- Step: `{item['step_id']}`",
            f"- Surface: `{item['surface']}`", f"- Symptom: {item['symptom']}",
            f"- Evidence: {item['evidence']}", "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def load_ledger(path: Path = LEDGER) -> tuple[list[dict[str, Any]], str]:
    data = path.read_bytes() if path.exists() else b""
    return parse_ledger_bytes(data), sha256_bytes(data)


def blocker_view_stale(ledger_hash: str, view: Path = BLOCKER_VIEW) -> bool:
    if not view.is_file():
        return True
    match = re.search(r"Ledger-SHA256: `([0-9a-f]{64})`", view.read_text(errors="replace"))
    return match is None or match.group(1) != ledger_hash


def semantic_discovery_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    required = ["CreatedAtUtc:", "## Intended Outcome", "## Why This Looks Repeatable",
                "## Required Inputs, Auth, Or Environment", "## Commands And Observations",
                "## Failure Handling", "## Verified Path", "## Promotion Readiness"]
    if not all(marker in text for marker in required):
        raise WorkMemoryError("invalid-discovery-document", 3)
    lines = [line for line in text.splitlines() if not re.match(
        r"^(Status|ReadyAtUtc|PromotedSequenceId|SuccessfulRuns|LastValidatedAtUtc):", line
    )]
    return ("\n".join(lines).rstrip() + "\n").encode()


def _repo_roots(path: str | None = None) -> dict[str, Path]:
    roots = {"memory-knowledge": ROOT}
    source = Path(path or os.environ.get("MK_REPO_ROOTS_FILE", "~/.config/memory-knowledge/repositories.json")).expanduser()
    if source.is_file():
        raw = json.loads(source.read_text())
        if not isinstance(raw, dict):
            raise WorkMemoryError("invalid-repo-roots", 2)
        roots.update({str(key): Path(value).expanduser().resolve() for key, value in raw.items()})
    return roots


def _safe_file(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise WorkMemoryError("dependency-path-escape", 3)
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkMemoryError("dependency-path-escape", 3) from exc
    if not resolved.is_file():
        raise WorkMemoryError("missing-dependency", 3)
    return resolved


def resolve_bundle(
    *, mode: str, subject_id: str, document: Path, manifest: Path,
    repo_roots_file: str | None = None,
) -> tuple[list[dict[str, str]], str, str]:
    roots = _repo_roots(repo_roots_file)
    seen: set[tuple[str, str]] = set()
    stack: list[str] = []
    entries: list[dict[str, str]] = []

    def add(repo_key: str, relative: str, raw_path: Path, *, semantic: bool = False) -> None:
        key = (repo_key, relative)
        if key in seen:
            raise WorkMemoryError("duplicate-bundle-file", 3)
        seen.add(key)
        data = semantic_discovery_bytes(raw_path) if semantic else raw_path.read_bytes()
        entries.append({"repository_key": repo_key, "path": relative, "sha256": sha256_bytes(data)})

    def visit(sequence_id: str, doc: Path, manifest_path: Path, discovery: bool = False) -> str:
        if sequence_id in stack:
            raise WorkMemoryError("dependency-cycle", 3)
        stack.append(sequence_id)
        if not manifest_path.is_file():
            raise WorkMemoryError("missing-dependency-manifest", 3)
        try:
            manifest_data = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as exc:
            raise WorkMemoryError("invalid-dependency-manifest", 3) from exc
        if set(manifest_data) != {"schema_version", "lineage_id", "dependencies"} or manifest_data["schema_version"] != 1:
            raise WorkMemoryError("invalid-dependency-manifest", 3)
        lineage = require_id(manifest_data["lineage_id"], "lineage-id")
        if not isinstance(manifest_data["dependencies"], list):
            raise WorkMemoryError("invalid-dependency-manifest", 3)
        doc_rel = str(doc.resolve().relative_to(ROOT))
        manifest_rel = str(manifest_path.resolve().relative_to(ROOT))
        add("memory-knowledge", doc_rel, doc, semantic=discovery)
        add("memory-knowledge", manifest_rel, manifest_path)
        for dep in manifest_data["dependencies"]:
            if not isinstance(dep, dict) or set(dep) != {"kind", "repository_key", "path_or_sequence_id"}:
                raise WorkMemoryError("invalid-dependency-entry", 3)
            dep_kind, repo_key, value = dep["kind"], dep["repository_key"], dep["path_or_sequence_id"]
            if dep_kind == "sequence":
                child_doc = ROOT / "operations/sequences" / value / "sequence.md"
                child_manifest = child_doc.with_name("dependencies.json")
                visit(value, child_doc, child_manifest)
            elif dep_kind in {"file", "glob"}:
                if repo_key not in roots:
                    raise WorkMemoryError("missing-repository-root", 3)
                repo_root = roots[repo_key]
                paths = [_safe_file(repo_root, value)] if dep_kind == "file" else sorted(repo_root.glob(value))
                if not paths or any(not path.is_file() for path in paths):
                    raise WorkMemoryError("unmatched-dependency-glob", 3)
                for path in paths:
                    relative = str(path.resolve().relative_to(repo_root.resolve()))
                    add(repo_key, relative, path)
            else:
                raise WorkMemoryError("invalid-dependency-kind", 3)
        stack.pop()
        return lineage

    lineage_id = visit(subject_id, document.resolve(), manifest.resolve(), mode == "discovery")
    entries.sort(key=lambda item: (item["repository_key"], item["path"], item["sha256"]))
    document_text = document.read_text(encoding="utf-8")
    control_scripts = {
        "scripts/work_memory.py", "scripts/sequence_guard.py",
        "scripts/sequence_discovery_log.py", "scripts/blocker_catalog.py",
        "scripts/directive_guard.py",
    }
    references = re.findall(
        r"(?:(?P<repo>[A-Za-z0-9_.-]+):)?(?P<path>(?:scripts|tools|dist)/[A-Za-z0-9_.*?/{<>}-]+\.(?:py|sh))",
        document_text,
    )
    for repo_key, referenced_path in references:
        if referenced_path in control_scripts or "<" in referenced_path or ">" in referenced_path:
            continue
        covered = any(
            (not repo_key or item["repository_key"] == repo_key)
            and (item["path"] == referenced_path or fnmatch.fnmatch(item["path"], referenced_path))
            for item in entries
        )
        if not covered:
            raise WorkMemoryError(f"executable-outside-manifest:{repo_key}:{referenced_path}", 3)
    bundle_hash = sha256_bytes(canonical_bytes(entries))
    return entries, bundle_hash, lineage_id


def registry_rows(path: Path = REGISTRY) -> tuple[list[dict[str, str]], str]:
    rows: list[dict[str, str]] = []
    for line in path.read_text().splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        rows.append({"sequence_id": cells[0].strip("`"), "use_when": cells[1],
                     "folder": cells[2].strip("`"), "automation": cells[3],
                     "pass_signal": cells[4], "operation_kinds": cells[5].strip("`"),
                     "lineage_id": cells[6].strip("`")})
    return rows, sha256_bytes(path.read_bytes())


def receipt_path(task_id: str, name: str) -> Path:
    require_id(task_id, "task-id")
    return RECEIPT_ROOT / task_id / f"{name}.json"


def write_receipt(task_id: str, name: str, payload: dict[str, Any]) -> tuple[Path, str]:
    path = receipt_path(task_id, name)
    data = canonical_bytes(payload)
    _atomic_write(path, data)
    return path, sha256_bytes(data)


def load_receipt(task_id: str, name: str, *, require_fresh: bool = True) -> tuple[dict[str, Any], str, Path]:
    path = receipt_path(task_id, name)
    if not path.is_file():
        raise WorkMemoryError(f"missing-{name}-receipt", 4)
    data = path.read_bytes()
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise WorkMemoryError(f"invalid-{name}-receipt", 4) from exc
    if payload.get("task_id") != task_id:
        raise WorkMemoryError("receipt-task-mismatch", 4)
    if require_fresh and parse_utc(payload["expires_at_utc"]) <= datetime.now(UTC):
        raise WorkMemoryError("expired-receipt", 4)
    return payload, sha256_bytes(data), path


def cmd_classify(args: argparse.Namespace) -> dict[str, Any]:
    if args.operation_kind not in OPERATION_KINDS or args.meaningful_steps < 0:
        raise WorkMemoryError("invalid-classification-input", 2)
    repeatable = args.repeatable == "yes"
    operational = (
        args.operation_kind in ALWAYS_OPERATIONAL
        or (args.operation_kind in CONDITIONAL_OPERATIONAL and (repeatable or args.meaningful_steps >= 3))
        or (args.operation_kind in NON_OPERATIONAL and (repeatable or args.meaningful_steps >= 3))
    )
    now = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "schema_version": 1, "task_id": args.task_id, "operation_kind": args.operation_kind,
        "repeatable": repeatable, "meaningful_steps": args.meaningful_steps,
        "verdict": "operational" if operational else "non-operational",
        "reason": "repeatable-or-multistep" if operational else "bounded-non-operational",
        "created_at_utc": now.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (now + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
    }
    path, digest = write_receipt(args.task_id, "classification", payload)
    return {**payload, "classification_path": str(path), "classification_receipt_hash": digest}


def cmd_select(args: argparse.Namespace) -> dict[str, Any]:
    classification, class_hash, _ = load_receipt(args.task_id, "classification")
    if classification["verdict"] != "operational":
        raise WorkMemoryError("classification-is-not-operational", 4)
    if args.sequence_id and args.discovery_log:
        raise WorkMemoryError("selection-source-conflict", 2)
    rows, registry_hash = registry_rows()
    events, ledger_hash = load_ledger()
    candidates = [row for row in rows if classification["operation_kind"] in row["operation_kinds"].split(",")]
    fingerprint_row = None
    fingerprint_link: tuple[str, int, str, str] | None = None
    if args.fingerprint and not args.sequence_id and not args.discovery_log:
        opened = {
            event["blocker_id"]: event for event in events
            if event["event_type"] == "blocker_opened" and event["fingerprint"] == args.fingerprint
        }
        states = {blocker_id: "open" for blocker_id in opened}
        verified_at: dict[str, str] = {}
        for event in events:
            blocker_id = event.get("blocker_id")
            if blocker_id not in opened:
                continue
            if event["event_type"] == "blocker_recurred":
                states[blocker_id] = "open"
            elif event["event_type"] == "blocker_transitioned":
                states[blocker_id] = event["to_status"]
                if event["to_status"] in {"verified", "closed"}:
                    verified_at[blocker_id] = event["recorded_at_utc"]
        successful_runs = Counter(
            event["subject_id"] for event in events
            if event["event_type"] == "run_closed" and event["result"] == "passed"
        )
        linked = [
            (verified_at.get(blocker_id, "1970-01-01T00:00:00Z"),
             successful_runs[opened[blocker_id]["subject_id"]],
             opened[blocker_id]["subject_id"], blocker_id)
            for blocker_id, status in states.items() if status in {"verified", "closed"}
        ]
        linked.sort(key=lambda item: (
            -parse_utc(item[0]).timestamp(), -item[1], item[2], item[3]
        ))
        if linked:
            fingerprint_link = linked[0]
            fingerprint_row = next(
                (row for row in rows if row["sequence_id"] == fingerprint_link[2]), None
            )
            if fingerprint_row is None:
                raise WorkMemoryError("fingerprint-linked-sequence-missing", 4)
    explicit = False
    if args.discovery_log:
        document = Path(args.discovery_log).resolve()
        mode = "discovery"
        match = re.search(r"^DiscoveryId:\s*(\S+)\s*$", document.read_text(), re.M)
        if not match:
            raise WorkMemoryError("discovery-id-missing", 3)
        subject_id = match.group(1)
        manifest = document.with_suffix(".dependencies.json")
    else:
        if args.sequence_id:
            matching = [row for row in candidates if row["sequence_id"] == args.sequence_id]
            if not matching:
                raise WorkMemoryError("sequence-not-valid-for-operation", 3)
            row, explicit = matching[0], True
        elif fingerprint_row is not None:
            row = fingerprint_row
        elif len(candidates) == 1:
            row = candidates[0]
        elif not candidates:
            raise WorkMemoryError("discovery-required", 3)
        else:
            raise WorkMemoryError("ambiguous-sequence:" + ",".join(sorted(r["sequence_id"] for r in candidates)), 3)
        subject_id, mode = row["sequence_id"], "registered"
        document = ROOT / row["folder"] / "sequence.md"
        manifest = document.with_name("dependencies.json")
    bundle, bundle_hash, lineage = resolve_bundle(
        mode=mode, subject_id=subject_id, document=document, manifest=manifest,
        repo_roots_file=args.repo_roots_file,
    )
    if mode == "registered" and row["lineage_id"] != lineage:
        raise WorkMemoryError("registry-manifest-lineage-mismatch", 3)
    if fingerprint_row is not None:
        starts = {
            event["run_id"]: event for event in events
            if event["event_type"] == "run_started"
            and event["subject_id"] == subject_id
            and event["source_bundle_hash"] == bundle_hash
        }
        verified_runs = {
            event["run_id"] for event in events
            if event["event_type"] == "verification_recorded"
            and event["run_id"] in starts and event["outcome"] == "passed"
            and event["quality"] == "same-path"
            and event["source_bundle_hash"] == bundle_hash
        }
        current_success = any(
            event["event_type"] == "run_closed" and event["run_id"] in verified_runs
            and event["result"] == "passed"
            for event in events
        )
        if not current_success:
            raise WorkMemoryError("fingerprint-linked-sequence-stale", 4)
    opened = {
        event["blocker_id"]: event for event in events
        if event["event_type"] == "blocker_opened" and event["lineage_id"] == lineage
        and (not args.fingerprint or event["fingerprint"] == args.fingerprint)
    }
    blocker_states = {blocker_id: "open" for blocker_id in opened}
    for event in events:
        blocker_id = event.get("blocker_id")
        if blocker_id not in opened:
            continue
        if event["event_type"] == "blocker_recurred":
            blocker_states[blocker_id] = "open"
        elif event["event_type"] == "blocker_transitioned":
            blocker_states[blocker_id] = event["to_status"]
    correction_rows = [
        event for event in events if event["event_type"] == "correction_recorded"
        and event["lineage_id"] == lineage and event["blocker_id"] in opened
    ]
    superseded = {event.get("supersedes_correction_id") for event in correction_rows}
    latest = {
        event["correction_id"]: event for event in correction_rows
        if event["correction_id"] not in superseded
    }
    eligible: list[dict[str, Any]] = []
    for verification in events:
        if (
            verification["event_type"] != "verification_recorded"
            or verification["outcome"] != "passed" or verification["quality"] != "same-path"
            or verification["source_bundle_hash"] != bundle_hash
        ):
            continue
        for correction_id in verification["correction_ids"]:
            correction = latest.get(correction_id)
            if correction is None or blocker_states.get(correction["blocker_id"]) not in {"verified", "closed"}:
                continue
            if (
                correction["blocker_id"] not in verification["blocker_ids"]
            ):
                continue
            eligible.append({
                "blocker_id": correction["blocker_id"], "correction_id": correction_id,
                "solution": correction["solution"], "changed_artifacts": correction["changed_artifacts"],
                "verification_event_id": verification["event_id"],
                "verified_at_utc": verification["recorded_at_utc"],
            })
    eligible.sort(key=lambda item: (item["verified_at_utc"], item["blocker_id"]), reverse=True)
    recent_runs = [
        event for event in events if event["event_type"] == "run_started"
        and event["lineage_id"] == lineage
    ]
    recent_runs.sort(key=lambda event: (event["started_at_utc"], event["run_id"]), reverse=True)
    now = datetime.now(UTC).replace(microsecond=0)
    successor_ids = args.verifies_correction_id or []
    if bool(args.verification_successor_of) != bool(successor_ids):
        raise WorkMemoryError("incomplete-successor-selection", 2)
    reason = "successor-verification" if args.verification_successor_of else (
        "fingerprint-link" if fingerprint_row is not None else
        ("explicit-override" if explicit else "operation-kind-match")
    )
    payload = {
        "schema_version": 1, "task_id": args.task_id, "created_at_utc": now.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (now + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
        "classification_receipt_hash": class_hash, "registry_hash": registry_hash,
        "ledger_hash": ledger_hash, "mode": mode, "subject_id": subject_id, "lineage_id": lineage,
        "document": str(document), "manifest": str(manifest), "source_bundle": bundle,
        "source_bundle_hash": bundle_hash, "selection_reason": reason, "explicit_override": explicit,
        "relevant_blocker_ids": sorted(opened),
        "recent_run_ids": [event["run_id"] for event in recent_runs[:10]],
        "eligible_corrections": eligible,
        "repository_roots_file": args.repo_roots_file,
        "predecessor_run_id": args.verification_successor_of,
        "verifies_correction_ids": sorted(successor_ids),
    }
    path, digest = write_receipt(args.task_id, "selection", payload)
    return {**payload, "selection_path": str(path), "selection_receipt_hash": digest}


def _event(kind: str, event_id: str | None = None, **fields: Any) -> dict[str, Any]:
    return {"schema_version": 1, "event_id": event_id or str(uuid.uuid4()), "event_type": kind,
            "recorded_at_utc": utc_now(), **fields}


def _run_state(events: list[dict[str, Any]], run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    related = [event for event in events if event.get("run_id") == run_id]
    start = next((event for event in related if event["event_type"] == "run_started"), None)
    if start is None:
        raise WorkMemoryError("run-not-found", 3)
    return start, related


def cmd_run_start(args: argparse.Namespace) -> dict[str, Any]:
    classification, class_hash, _ = load_receipt(args.task_id, "classification")
    selection, selection_hash, _ = load_receipt(args.task_id, "selection")
    if selection["classification_receipt_hash"] != class_hash:
        raise WorkMemoryError("receipt-chain-mismatch", 4)
    bundle, digest, lineage = resolve_bundle(
        mode=selection["mode"], subject_id=selection["subject_id"], document=Path(selection["document"]),
        manifest=Path(selection["manifest"]),
        repo_roots_file=selection.get("repository_roots_file"),
    )
    if digest != selection["source_bundle_hash"] or lineage != selection["lineage_id"]:
        raise WorkMemoryError("stale-selection-bundle", 4)
    run_id = args.run_id or str(uuid.uuid4())
    fields: dict[str, Any] = {
        "run_id": run_id, "subject_id": selection["subject_id"], "lineage_id": lineage,
        "mode": selection["mode"], "operation_kind": classification["operation_kind"],
        "source_bundle": bundle, "source_bundle_hash": digest,
        "classification_receipt_hash": class_hash, "selection_receipt_hash": selection_hash,
        "started_at_utc": utc_now(),
    }
    if selection.get("predecessor_run_id"):
        fields["predecessor_run_id"] = selection["predecessor_run_id"]
        fields["verifies_correction_ids"] = selection["verifies_correction_ids"]
    event = _event("run_started", args.event_id, **fields)
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "run_id": run_id, "event_id": event["event_id"]}


def _artifact_hashes(paths: Iterable[str]) -> tuple[list[str], list[str]]:
    artifacts, hashes = [], []
    for raw in paths:
        path = Path(raw).resolve()
        if not path.is_file():
            raise WorkMemoryError("changed-artifact-not-found", 2)
        try:
            relative = str(path.relative_to(ROOT))
        except ValueError as exc:
            raise WorkMemoryError("changed-artifact-outside-repository", 2) from exc
        artifacts.append(relative)
        hashes.append(sha256_bytes(path.read_bytes()))
    return artifacts, hashes


def cmd_correct(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, related = _run_state(events, args.run_id)
    if any(event["event_type"] in {"run_closed", "run_abandoned"} for event in related):
        raise WorkMemoryError("run-is-terminal", 3)
    artifacts, hashes = _artifact_hashes(args.changed_artifact)
    document = next(Path(item["path"]) for item in start["source_bundle"] if item["repository_key"] == "memory-knowledge" and item["path"].endswith(("sequence.md", ".md")))
    document = ROOT / document
    manifest = document.with_name("dependencies.json") if start["mode"] == "registered" else document.with_suffix(".dependencies.json")
    _, new_hash, _ = resolve_bundle(mode=start["mode"], subject_id=start["subject_id"], document=document, manifest=manifest)
    correction_id = args.correction_id or str(uuid.uuid4())
    correction = _event(
        "correction_recorded", args.event_id, run_id=args.run_id, blocker_id=args.blocker_id,
        occurrence_id=args.occurrence_id, correction_id=correction_id, subject_id=start["subject_id"],
        lineage_id=start["lineage_id"], step_id=args.step_id, changed_artifacts=artifacts,
        changed_artifact_hashes=hashes, reusable_behavior_changed=args.reusable_behavior_changed == "yes",
        solution=args.solution, **({"supersedes_correction_id": args.supersedes_correction_id} if args.supersedes_correction_id else {}),
    )
    transition = _event(
        "bundle_transition_recorded", args.transition_event_id, lineage_id=start["lineage_id"],
        old_bundle_hash=start["source_bundle_hash"], new_bundle_hash=new_hash, transition_reason="correction",
        run_id=args.run_id, correction_ids=[correction_id], changed_artifacts=artifacts,
        changed_artifact_hashes=hashes,
    )
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [correction, transition]})
    return {**result, "correction_id": correction_id, "event_id": correction["event_id"],
            "transition_event_id": transition["event_id"], "old_bundle_hash": start["source_bundle_hash"],
            "new_bundle_hash": new_hash, "changed_artifact_hashes": hashes}


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, related = _run_state(events, args.run_id)
    corrections = args.correction_id or []
    blockers = args.blocker_id or []
    if len(corrections) != len(blockers):
        raise WorkMemoryError("paired-correction-blocker-required", 2)
    artifact_hashes: list[str] = []
    for correction_id in corrections:
        match = next((event for event in events if event["event_type"] == "correction_recorded" and event["correction_id"] == correction_id), None)
        if match is None:
            raise WorkMemoryError("correction-not-found", 3)
        artifact_hashes.extend(match["changed_artifact_hashes"])
    event = _event(
        "verification_recorded", args.event_id, run_id=args.run_id, subject_id=start["subject_id"],
        lineage_id=start["lineage_id"], source_bundle_hash=start["source_bundle_hash"],
        outcome=args.outcome, quality=args.quality, evidence=args.evidence,
        blocker_ids=blockers, correction_ids=corrections, changed_artifact_hashes=artifact_hashes,
    )
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "event_id": event["event_id"], "changed_artifact_hashes": artifact_hashes}


def cmd_run_close(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, related = _run_state(events, args.run_id)
    corrections = [event for event in related if event["event_type"] == "correction_recorded"]
    blockers = sorted({event["blocker_id"] for event in related if "blocker_id" in event})
    verifications = [event for event in related if event["event_type"] == "verification_recorded"]
    transitions = [event for event in events if event["event_type"] == "bundle_transition_recorded" and event.get("run_id") == args.run_id]
    event = _event(
        "run_closed", args.event_id, run_id=args.run_id, subject_id=start["subject_id"],
        lineage_id=start["lineage_id"], result=args.result, completed_at_utc=utc_now(),
        correction_count=len(corrections), blocker_ids=blockers, sequence_updated=bool(transitions),
        verification_quality=verifications[-1]["quality"] if verifications else "none",
    )
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "event_id": event["event_id"], "metrics": summarize(events + [event], start["subject_id"], start["source_bundle_hash"])}


def cmd_run_abandon(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, _ = _run_state(events, args.run_id)
    event = _event("run_abandoned", args.event_id, run_id=args.run_id, subject_id=start["subject_id"],
                   lineage_id=start["lineage_id"], completed_at_utc=utc_now(), reason=args.reason)
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "event_id": event["event_id"]}


def _run_records(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for event in events:
        run_id = event.get("run_id")
        if event["event_type"] == "run_started":
            runs[run_id] = {"start": event, "events": [event], "terminal": None}
        elif run_id in runs:
            runs[run_id]["events"].append(event)
            if event["event_type"] in {"run_closed", "run_abandoned"}:
                runs[run_id]["terminal"] = event
    return list(runs.values())


def _metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [record for record in records if record["terminal"] and record["terminal"]["event_type"] == "run_closed"]
    verification_events = [event for record in closed for event in record["events"] if event["event_type"] == "verification_recorded"]
    corrections = [event for record in closed for event in record["events"] if event["event_type"] == "correction_recorded"]
    fingerprints: dict[str, set[str]] = defaultdict(set)
    blocker_fingerprints = {
        event["blocker_id"]: event["fingerprint"]
        for record in records for event in record["events"]
        if event["event_type"] == "blocker_opened"
    }
    durations: list[int] = []
    first_pass = 0
    passed = 0
    for record in closed:
        terminal, start = record["terminal"], record["start"]
        passed += terminal["result"] == "passed"
        has_fix = any(event["event_type"] in {"correction_recorded", "blocker_opened", "blocker_recurred"} for event in record["events"])
        first_pass += terminal["result"] == "passed" and not has_fix
        durations.append(int((parse_utc(terminal["completed_at_utc"]) - parse_utc(start["started_at_utc"])).total_seconds() * 1000))
        for event in record["events"]:
            if event["event_type"] == "blocker_opened":
                fingerprints[event["fingerprint"]].add(start["run_id"])
            elif event["event_type"] == "blocker_recurred" and event["blocker_id"] in blocker_fingerprints:
                fingerprints[blocker_fingerprints[event["blocker_id"]]].add(start["run_id"])
    denominator = len(closed)
    return {
        "closed_runs": denominator, "pass_rate": [passed, denominator],
        "first_pass_success_rate": [first_pass, denominator],
        "corrections_per_run": [len(corrections), denominator],
        "repeated_blocker_count": sum(len(ids) >= 2 for ids in fingerprints.values()),
        "same_path_verification_rate": [sum(event["outcome"] == "passed" and event["quality"] == "same-path" for event in verification_events), len(verification_events)],
        "median_duration_ms": int(statistics.median(durations)) if durations else None,
    }


def _ratio_direction(old: list[int], new: list[int], higher_better: bool) -> str:
    old_n, old_d = old; new_n, new_d = new
    if old_d == 0 or new_d == 0:
        return "unchanged" if old_d == new_d else "mixed"
    delta = new_n * old_d - old_n * new_d
    if delta == 0:
        return "unchanged"
    improved = delta > 0 if higher_better else delta < 0
    return "improved" if improved else "regressed"


def _compare(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    left, right = _metrics(before), _metrics(after)
    speed = "unchanged"
    if left["median_duration_ms"] != right["median_duration_ms"]:
        speed = "improved" if right["median_duration_ms"] < left["median_duration_ms"] else "regressed"
    components = {
        "pass_rate": _ratio_direction(left["pass_rate"], right["pass_rate"], True),
        "first_pass_success_rate": _ratio_direction(left["first_pass_success_rate"], right["first_pass_success_rate"], True),
        "corrections_per_run": _ratio_direction(left["corrections_per_run"], right["corrections_per_run"], False),
        "same_path_verification_rate": _ratio_direction(left["same_path_verification_rate"], right["same_path_verification_rate"], True),
        "repeated_blocker_count": "improved" if right["repeated_blocker_count"] < left["repeated_blocker_count"] else ("regressed" if right["repeated_blocker_count"] > left["repeated_blocker_count"] else "unchanged"),
    }
    values = set(components.values())
    quality = "mixed" if {"improved", "regressed"} <= values else ("improved" if "improved" in values else ("regressed" if "regressed" in values else "unchanged"))
    pair = {speed, quality}
    overall = "mixed" if "mixed" in pair or {"improved", "regressed"} <= pair else ("improved" if "improved" in pair else ("regressed" if "regressed" in pair else "unchanged"))
    return {"before": left, "after": right, "component_directions": components,
            "speed_status": speed, "quality_status": quality, "overall_status": overall}


def summarize(events: list[dict[str, Any]], subject_id: str, bundle_hash: str | None = None) -> dict[str, Any]:
    records = [record for record in _run_records(events) if record["start"]["subject_id"] == subject_id]
    if bundle_hash:
        records = [record for record in records if record["start"]["source_bundle_hash"] == bundle_hash]
    closed = [record for record in records if record["terminal"] and record["terminal"]["event_type"] == "run_closed"]
    closed.sort(key=lambda record: (record["start"]["started_at_utc"], record["start"]["run_id"]))
    result = {"subject_id": subject_id, "source_bundle_hash": bundle_hash,
              "metrics": _metrics(closed), "abandoned_runs": sum(record["terminal"] and record["terminal"]["event_type"] == "run_abandoned" for record in records),
              "history_status": "insufficient-history", "trend": None, "change_effects": []}
    if len(closed) >= 6:
        result["history_status"] = "sufficient"
        result["trend"] = _compare(closed[-6:-3], closed[-3:])
    transitions = [event for event in events if event["event_type"] == "bundle_transition_recorded" and event["transition_reason"] == "correction"]
    all_records = _run_records(events)
    for transition in transitions:
        transition_run = next((r for r in all_records if r["start"]["run_id"] == transition["run_id"]), None)
        operation_kind = transition_run["start"]["operation_kind"] if transition_run else None
        before = [r for r in all_records if r["start"]["lineage_id"] == transition["lineage_id"] and r["start"]["operation_kind"] == operation_kind and r["start"]["source_bundle_hash"] == transition["old_bundle_hash"] and r["start"]["started_at_utc"] <= transition["recorded_at_utc"] and r["terminal"] and r["terminal"]["event_type"] == "run_closed"][-3:]
        after = [r for r in all_records if r["start"]["lineage_id"] == transition["lineage_id"] and r["start"]["operation_kind"] == operation_kind and r["start"]["source_bundle_hash"] == transition["new_bundle_hash"] and r["start"]["started_at_utc"] > transition["recorded_at_utc"] and r["terminal"] and r["terminal"]["event_type"] == "run_closed"][:3]
        effect: dict[str, Any] = {"transition_event_id": transition["event_id"], "correction_ids": transition["correction_ids"], "old_bundle_hash": transition["old_bundle_hash"], "new_bundle_hash": transition["new_bundle_hash"]}
        if not transition_run or not transition_run["terminal"]:
            effect["status"] = "transition-run-not-terminal"
        elif len(before) < 3 or len(after) < 3:
            effect["status"] = "insufficient-cross-version-history"
        else:
            effect.update(status="sufficient", comparison=_compare(before, after))
        result["change_effects"].append(effect)
    return result


def cmd_transact(args: argparse.Namespace) -> dict[str, Any]:
    raw = sys.stdin.read() if args.request_json == "-" else Path(args.request_json).read_text()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkMemoryError("invalid-request-json", 2) from exc
    return transact(request, Path(args.ledger).resolve() if args.ledger else LEDGER,
                    Path(args.view).resolve() if args.view else BLOCKER_VIEW)


def cmd_summary(args: argparse.Namespace) -> dict[str, Any]:
    events, digest = load_ledger(Path(args.ledger).resolve() if args.ledger else LEDGER)
    return {**summarize(events, args.subject_id, args.source_bundle_hash),
            "ledger_hash": digest, "view_stale": blocker_view_stale(digest)}


def cmd_repair_view(args: argparse.Namespace) -> dict[str, Any]:
    ledger = Path(args.ledger).resolve() if args.ledger else LEDGER
    view = Path(args.view).resolve() if args.view else BLOCKER_VIEW
    lock = ledger.with_suffix(ledger.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        events, digest = load_ledger(ledger)
        data = render_blocker_view(events, digest).encode()
        _atomic_write(view, data)
    return {"ok": True, "ledger_hash": digest, "blocker_view_hash": sha256_bytes(data)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    classify = sub.add_parser("classify")
    classify.add_argument("--task-id", required=True); classify.add_argument("--operation-kind", required=True, choices=sorted(OPERATION_KINDS))
    classify.add_argument("--repeatable", required=True, choices=["yes", "no"]); classify.add_argument("--meaningful-steps", required=True, type=int)
    classify.set_defaults(func=cmd_classify)
    select = sub.add_parser("select")
    select.add_argument("--task-id", required=True); select.add_argument("--sequence-id"); select.add_argument("--discovery-log")
    select.add_argument("--fingerprint"); select.add_argument("--verification-successor-of"); select.add_argument("--verifies-correction-id", action="append")
    select.add_argument("--repo-roots-file"); select.set_defaults(func=cmd_select)
    transact_p = sub.add_parser("transact")
    transact_p.add_argument("--request-json", required=True); transact_p.add_argument("--ledger"); transact_p.add_argument("--view")
    transact_p.set_defaults(func=cmd_transact)
    run_start = sub.add_parser("run-start")
    run_start.add_argument("--task-id", required=True); run_start.add_argument("--run-id"); run_start.add_argument("--event-id")
    run_start.set_defaults(func=cmd_run_start)
    correct = sub.add_parser("correct")
    correct.add_argument("--run-id", required=True); correct.add_argument("--blocker-id", required=True); correct.add_argument("--occurrence-id", required=True)
    correct.add_argument("--step-id", required=True); correct.add_argument("--changed-artifact", action="append", required=True)
    correct.add_argument("--solution", required=True); correct.add_argument("--reusable-behavior-changed", choices=["yes", "no"], required=True)
    correct.add_argument("--supersedes-correction-id"); correct.add_argument("--correction-id"); correct.add_argument("--event-id"); correct.add_argument("--transition-event-id")
    correct.set_defaults(func=cmd_correct)
    verify = sub.add_parser("verify")
    verify.add_argument("--run-id", required=True); verify.add_argument("--outcome", choices=["passed", "failed"], required=True)
    verify.add_argument("--quality", choices=["proxy", "same-path"], required=True); verify.add_argument("--evidence", required=True)
    verify.add_argument("--blocker-id", action="append"); verify.add_argument("--correction-id", action="append"); verify.add_argument("--event-id")
    verify.set_defaults(func=cmd_verify)
    close = sub.add_parser("run-close")
    close.add_argument("--run-id", required=True); close.add_argument("--result", choices=["passed", "failed"], required=True); close.add_argument("--event-id")
    close.set_defaults(func=cmd_run_close)
    abandon = sub.add_parser("run-abandon")
    abandon.add_argument("--run-id", required=True); abandon.add_argument("--reason", required=True); abandon.add_argument("--event-id")
    abandon.set_defaults(func=cmd_run_abandon)
    summary = sub.add_parser("summary")
    summary.add_argument("--subject-id", required=True); summary.add_argument("--source-bundle-hash"); summary.add_argument("--ledger")
    summary.set_defaults(func=cmd_summary)
    repair = sub.add_parser("repair-view")
    repair.add_argument("--ledger"); repair.add_argument("--view"); repair.set_defaults(func=cmd_repair_view)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = args.func(args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except WorkMemoryError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
