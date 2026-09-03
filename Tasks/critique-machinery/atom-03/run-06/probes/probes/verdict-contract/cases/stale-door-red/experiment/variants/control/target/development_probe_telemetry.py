#!/usr/bin/env python3
"""Append code-owned Development-Probe telemetry with cross-process ordering."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TelemetryError(RuntimeError):
    """The append-only telemetry feed is malformed or unavailable."""


def append_event(path: Path, event: str, state: str, identity: dict[str, Any], **details: Any) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        sequence = 1
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise TelemetryError(f"telemetry line {line_number} is invalid JSON: {error}") from None
            if type(record) is not dict or record.get("sequence") != sequence:
                raise TelemetryError(
                    f"telemetry line {line_number} sequence is {getattr(record, 'get', lambda _key: None)('sequence')!r}; require {sequence}"
                )
            sequence += 1
        record = {
            "schema_version": 1,
            "sequence": sequence,
            "event": event,
            "state": state,
            "recorded_at": datetime.now(UTC).isoformat(),
            **identity,
            **details,
        }
        stream.seek(0, os.SEEK_END)
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return record
