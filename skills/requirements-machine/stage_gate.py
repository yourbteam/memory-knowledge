#!/usr/bin/env python3
"""Fail closed on model-stage records before a Requirements Machinery stage advances."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Callable


Identity = Callable[[dict[str, object], Path], str]
Validator = Callable[[dict[str, object]], list[str]]


def field_identity(field: str) -> Identity:
    return lambda record, _path: str(record.get(field) or "")


def pair_identity(record: dict[str, object], _path: Path) -> str:
    left, right = str(record.get("left") or ""), str(record.get("right") or "")
    return "|".join(sorted((left, right))) if left and right else ""


def inspect(
    directory: Path,
    expected_ids: list[str] | set[str],
    identity: Identity,
    validate: Validator | None = None,
    *,
    require_filename: bool = False,
) -> dict[str, object]:
    """Check exact identity coverage, readability, duplicates, and stage-specific values."""

    expected = set(expected_ids)
    loaded: list[tuple[Path, str, dict[str, object]]] = []
    unreadable: list[dict[str, str]] = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            if path.name == "summary.json":
                continue
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(row, dict):
                    raise ValueError("record is not an object")
            except (OSError, json.JSONDecodeError, ValueError) as error:
                unreadable.append({"file": path.name, "why": str(error)})
                continue
            loaded.append((path, identity(row, path), row))

    counts = Counter(identifier for _, identifier, _ in loaded)
    unknown = [
        {"file": path.name, "id": identifier}
        for path, identifier, _ in loaded
        if not identifier or identifier not in expected
    ]
    duplicates = sorted(identifier for identifier, count in counts.items() if identifier and count > 1)
    misnamed = [
        {"file": path.name, "id": identifier, "expected_file": f"{identifier}.json"}
        for path, identifier, _ in loaded
        if require_filename and identifier and path.stem != identifier
    ]
    invalid: list[dict[str, object]] = []
    invalid_files: set[str] = set()
    if validate:
        for path, identifier, row in loaded:
            reasons = validate(row)
            if reasons:
                invalid.append({"file": path.name, "id": identifier, "why": reasons})
                invalid_files.add(path.name)

    accepted = {
        identifier for record_path, identifier, row in loaded
        if (identifier in expected and counts[identifier] == 1
            and (not require_filename or record_path.stem == identifier)
            and record_path.name not in invalid_files)
    }
    missing = sorted(expected - accepted)
    reject_files = sorted({
        item["file"] for item in unreadable + unknown + misnamed + invalid
    } | {
        path.name for path, identifier, _ in loaded if identifier in duplicates
    })
    complete = (not missing and not unreadable and not unknown and not duplicates
                and not misnamed and not invalid)
    return {
        "directory": str(directory),
        "expected": len(expected),
        "accepted": len(accepted),
        "missing": missing,
        "unreadable": unreadable,
        "unknown": unknown,
        "duplicates": duplicates,
        "misnamed": misnamed,
        "invalid": invalid,
        "reject_files": reject_files,
        "complete": complete,
    }


def enum(field: str, allowed: set[str], *, require_citations: bool = False,
         require_needed_for_no: bool = False) -> Validator:
    """Build the common validator used by verdict and answer stages."""

    def validate(record: dict[str, object]) -> list[str]:
        reasons: list[str] = []
        value = str(record.get(field) or "").strip().lower()
        if value not in allowed:
            reasons.append(f"{field} must be one of {sorted(allowed)}")
        if require_citations:
            reasons.extend(citation_reasons(record))
        if require_needed_for_no and value == "no":
            needed = str(record.get("needed") or "").strip().lower()
            if needed not in {"add", "change", "remove"}:
                reasons.append("a no answer needs add, change, or remove")
        return reasons

    return validate


def citation_reasons(record: dict[str, object]) -> list[str]:
    """Require citations that the executable resolver can actually inspect."""

    citations = record.get("citations")
    if not isinstance(citations, list) or not citations:
        return ["citations must contain at least one citation"]
    reasons = []
    for index, citation in enumerate(citations, start=1):
        if not isinstance(citation, dict):
            reasons.append(f"citation {index} must be an object")
            continue
        if not str(citation.get("where") or "").strip():
            reasons.append(f"citation {index} must name where")
        if not isinstance(citation.get("line"), int):
            reasons.append(f"citation {index} line must be an integer")
        if not str(citation.get("text") or "").strip():
            reasons.append(f"citation {index} must quote text")
    return reasons
