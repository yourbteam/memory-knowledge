#!/usr/bin/env python3
"""Select every readable projected relationship in stable source order."""

from __future__ import annotations

import re


class FormulaClaimSelectionError(ValueError):
    """The projection cannot produce an exact claim inventory."""


def select_relationships(
    projection: dict[str, object],
) -> list[dict[str, object]]:
    relationships = projection.get("relationships")
    if not isinstance(relationships, list):
        raise FormulaClaimSelectionError("relationships must be a list")
    selected: list[dict[str, object]] = []
    seen: set[str] = set()
    for position, item in enumerate(relationships, start=1):
        if not isinstance(item, dict):
            raise FormulaClaimSelectionError(
                f"relationship at position {position} must be an object"
            )
        relationship_id = item.get("id")
        if not isinstance(relationship_id, str) or not re.fullmatch(
            r"relationship-\d{6}", relationship_id
        ):
            raise FormulaClaimSelectionError(
                f"relationship at position {position} has invalid id "
                f"{relationship_id!r}"
            )
        if relationship_id in seen:
            raise FormulaClaimSelectionError(
                f"duplicate relationship id {relationship_id!r}"
            )
        seen.add(relationship_id)
        status = item.get("status")
        if status not in {"readable", "gap"}:
            raise FormulaClaimSelectionError(
                f"relationship {relationship_id!r} has invalid status {status!r}"
            )
        if status == "gap":
            continue
        for field in ("description", "from_id", "to_id"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise FormulaClaimSelectionError(
                    f"readable relationship {relationship_id!r} needs non-empty "
                    f"{field}"
                )
        selected.append(item)
    return selected
