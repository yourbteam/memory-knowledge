#!/usr/bin/env python3
"""Task-run-owned prevention journal built on the canonical work-memory event engine."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts import work_memory
except ModuleNotFoundError:  # direct script execution
    import work_memory


@dataclass(frozen=True)
class JournalOwnership:
    task_id: str
    run_id: str
    branch_ref: str
    worktree_id: str

    def __post_init__(self) -> None:
        work_memory.require_id(self.task_id, "task-id")
        work_memory.require_uuid(self.run_id, "run-id")
        if self.branch_ref != f"task/{self.task_id}":
            raise work_memory.WorkMemoryError("task-branch-ownership-mismatch", 2)
        work_memory._require_hash(self.worktree_id, "worktree-id")


class PreventionJournal:
    """Append-only event authority for one task/workflow run directory."""

    def __init__(self, run_dir: Path, ownership: JournalOwnership):
        self.run_dir = run_dir
        self.ownership = ownership
        self.prevention_dir = run_dir / "prevention"
        self.ledger = self.prevention_dir / "events.jsonl"
        self.generated_view = self.prevention_dir / "generated-blocker-view.md"
        self.checkpoint = self.prevention_dir / "checkpoint.json"

    def _write_checkpoint(self) -> dict[str, Any]:
        events, ledger_hash = work_memory.load_ledger(self.ledger)
        checkpoint = {
            "schema_version": 1,
            "task_id": self.ownership.task_id,
            "run_id": self.ownership.run_id,
            "branch_ref": self.ownership.branch_ref,
            "worktree_id": self.ownership.worktree_id,
            "ledger_sha256": ledger_hash,
            "last_event_id": events[-1]["event_id"],
            "event_count": len(events),
        }
        work_memory._atomic_write(self.checkpoint, work_memory.canonical_bytes(checkpoint))
        return checkpoint

    def append(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        event_id: str | None = None,
        recorded_at_utc: str | None = None,
    ) -> dict[str, Any]:
        if event_type not in work_memory.PREVENTION_EVENT_TYPES:
            raise work_memory.WorkMemoryError("not-a-prevention-event", 2)
        overlap = work_memory.PREVENTION_OWNERSHIP_FIELDS & set(payload)
        if overlap:
            raise work_memory.WorkMemoryError("caller-supplied-journal-ownership", 2)
        event_id = event_id or str(uuid.uuid4())
        values = {
            **dict(payload),
            "task_id": self.ownership.task_id,
            "run_id": self.ownership.run_id,
            "branch_ref": self.ownership.branch_ref,
            "worktree_id": self.ownership.worktree_id,
        }
        event = work_memory._event(
            event_type,
            event_id,
            recorded_at_utc=recorded_at_utc or work_memory.utc_now(),
            **values,
        )
        result = work_memory.transact(
            {"schema_version": 1, "expected_ledger_hash": None, "events": [event]},
            ledger=self.ledger,
            view=self.generated_view,
        )
        checkpoint = self._write_checkpoint()
        return {**result, "event_id": event_id, "checkpoint": checkpoint}

    def append_unique(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        identity: Mapping[str, Any],
        event_id: str | None = None,
        recorded_at_utc: str | None = None,
    ) -> dict[str, Any]:
        """Compare-and-append one event identity under the canonical ledger lock."""
        if not identity or not set(identity) <= set(payload):
            raise work_memory.WorkMemoryError("invalid-unique-event-identity", 2)
        overlap = work_memory.PREVENTION_OWNERSHIP_FIELDS & set(payload)
        if overlap:
            raise work_memory.WorkMemoryError("caller-supplied-journal-ownership", 2)
        event_id = event_id or str(uuid.uuid4())
        recorded = recorded_at_utc or work_memory.utc_now()
        for _ in range(16):
            events, ledger_hash = self.replay()
            matches = [
                event for event in events
                if event["event_type"] == event_type
                and all(event.get(field) == value for field, value in identity.items())
            ]
            if len(matches) > 1:
                raise work_memory.WorkMemoryError(f"duplicate-{event_type}", 3)
            if matches:
                existing = matches[0]
                if any(existing.get(key) != value for key, value in payload.items()):
                    raise work_memory.WorkMemoryError(f"conflicting-{event_type}", 3)
                return {
                    "event_id": existing["event_id"],
                    "replayed": True,
                    "checkpoint": self._write_checkpoint(),
                }
            values = {
                **dict(payload),
                "task_id": self.ownership.task_id,
                "run_id": self.ownership.run_id,
                "branch_ref": self.ownership.branch_ref,
                "worktree_id": self.ownership.worktree_id,
            }
            event = work_memory._event(
                event_type, event_id, recorded_at_utc=recorded, **values
            )
            try:
                result = work_memory.transact(
                    {
                        "schema_version": 1,
                        "expected_ledger_hash": ledger_hash,
                        "events": [event],
                    },
                    ledger=self.ledger,
                    view=self.generated_view,
                )
            except work_memory.WorkMemoryError as exc:
                if exc.code == "ledger-hash-conflict":
                    continue
                raise
            return {
                **result,
                "event_id": event_id,
                "checkpoint": self._write_checkpoint(),
            }
        raise work_memory.WorkMemoryError("unique-event-contention-exhausted", 3)

    def replay(self) -> tuple[list[dict[str, Any]], str]:
        events, ledger_hash = work_memory.load_ledger(self.ledger)
        for event in events:
            actual = {field: event[field] for field in work_memory.PREVENTION_OWNERSHIP_FIELDS}
            expected = {
                "task_id": self.ownership.task_id,
                "run_id": self.ownership.run_id,
                "branch_ref": self.ownership.branch_ref,
                "worktree_id": self.ownership.worktree_id,
            }
            if actual != expected:
                raise work_memory.WorkMemoryError("journal-ownership-mismatch", 3)
        return events, ledger_hash

    def append_unique_group(
        self, specs: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]],
        *, event_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Atomically compare-and-append a closed group of unique events."""
        if not specs:
            raise work_memory.WorkMemoryError("empty-unique-event-group", 2)
        event_ids = event_ids or [str(uuid.uuid4()) for _ in specs]
        if len(event_ids) != len(specs):
            raise work_memory.WorkMemoryError("unique-event-group-id-cardinality", 2)
        recorded = work_memory.utc_now()
        for _ in range(16):
            events, ledger_hash = self.replay()
            existing_group: list[dict[str, Any] | None] = []
            for event_type, payload, identity in specs:
                if not identity or not set(identity) <= set(payload):
                    raise work_memory.WorkMemoryError("invalid-unique-event-identity", 2)
                if work_memory.PREVENTION_OWNERSHIP_FIELDS & set(payload):
                    raise work_memory.WorkMemoryError("caller-supplied-journal-ownership", 2)
                matches = [
                    event for event in events
                    if event["event_type"] == event_type
                    and all(event.get(field) == value for field, value in identity.items())
                ]
                if len(matches) > 1:
                    raise work_memory.WorkMemoryError(f"duplicate-{event_type}", 3)
                existing_group.append(matches[0] if matches else None)
            if all(existing_group):
                for existing, (_, payload, _) in zip(existing_group, specs, strict=True):
                    assert existing is not None
                    if any(existing.get(key) != value for key, value in payload.items()):
                        raise work_memory.WorkMemoryError(
                            f"conflicting-{existing['event_type']}", 3
                        )
                return [dict(event) for event in existing_group if event is not None]
            if any(existing_group):
                for existing, (_, payload, _) in zip(
                    existing_group, specs, strict=True
                ):
                    if existing is not None and any(
                        existing.get(key) != value for key, value in payload.items()
                    ):
                        raise work_memory.WorkMemoryError(
                            f"conflicting-{existing['event_type']}", 3
                        )
                raise work_memory.WorkMemoryError("partial-unique-event-group", 3)
            staged = []
            for event_id, (event_type, payload, _) in zip(event_ids, specs, strict=True):
                values = {
                    **dict(payload),
                    "task_id": self.ownership.task_id,
                    "run_id": self.ownership.run_id,
                    "branch_ref": self.ownership.branch_ref,
                    "worktree_id": self.ownership.worktree_id,
                }
                staged.append(work_memory._event(
                    event_type, event_id, recorded_at_utc=recorded, **values
                ))
            try:
                work_memory.transact(
                    {
                        "schema_version": 1,
                        "expected_ledger_hash": ledger_hash,
                        "events": staged,
                    },
                    ledger=self.ledger,
                    view=self.generated_view,
                )
            except work_memory.WorkMemoryError as exc:
                if exc.code == "ledger-hash-conflict":
                    continue
                raise
            self._write_checkpoint()
            return staged
        raise work_memory.WorkMemoryError("unique-event-contention-exhausted", 3)

    def load_checkpoint(self) -> dict[str, Any]:
        events, ledger_hash = self.replay()
        expected = {
            "schema_version": 1,
            "task_id": self.ownership.task_id,
            "run_id": self.ownership.run_id,
            "branch_ref": self.ownership.branch_ref,
            "worktree_id": self.ownership.worktree_id,
            "ledger_sha256": ledger_hash,
            "last_event_id": events[-1]["event_id"] if events else None,
            "event_count": len(events),
        }
        if not self.checkpoint.is_file():
            work_memory._atomic_write(self.checkpoint, work_memory.canonical_bytes(expected))
            return expected
        try:
            current = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = None
        if current != expected:
            work_memory._atomic_write(self.checkpoint, work_memory.canonical_bytes(expected))
        return expected
