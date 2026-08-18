#!/usr/bin/env python3
"""Durably record only choices the Requirements Machinery explicitly handed to its owner."""
from __future__ import annotations

import json
from pathlib import Path


def merge_decision_id(left: str, right: str) -> str:
    return "merge:" + "|".join(sorted((left, right)))


def part_decision_id(part_id: str) -> str:
    return f"part:{part_id}"


def load(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("decisions") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("owner decisions must contain a decisions list")
    found: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("every owner decision must be an object")
        decision_id = str(row.get("decision_id") or "").strip()
        choice = str(row.get("choice") or "").strip().lower()
        if not decision_id or not choice:
            raise ValueError("every owner decision needs decision_id and choice")
        found[decision_id] = choice
    return found


def record(path: Path, available: dict[str, set[str]], decision_id: str, choice: str) -> None:
    """Write one owner answer only when the current machinery result offered that exact choice."""

    normalized = choice.strip().lower()
    if decision_id not in available:
        raise ValueError(f"owner decision is not currently requested: {decision_id}")
    if normalized not in available[decision_id]:
        raise ValueError(
            f"choice for {decision_id} must be one of {sorted(available[decision_id])}"
        )
    current = load(path)
    current[decision_id] = normalized
    payload = {
        "schema_version": 1,
        "decisions": [
            {"decision_id": key, "choice": value, "decided_by": "owner"}
            for key, value in sorted(current.items())
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
