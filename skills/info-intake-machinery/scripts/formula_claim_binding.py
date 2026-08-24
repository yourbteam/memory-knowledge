#!/usr/bin/env python3
"""Bind selected formula claims to immutable projection evidence."""

from __future__ import annotations

import hashlib
import json


class FormulaClaimBindingError(ValueError):
    """A selected claim is not completely bound to projection evidence."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def bind_claims(
    projection: dict[str, object],
    relationships: list[dict[str, object]],
    *,
    projection_id: str,
    projection_sha256: str,
) -> list[dict[str, object]]:
    elements = projection.get("elements")
    if not isinstance(elements, list):
        raise FormulaClaimBindingError("elements must be a list")
    index: dict[str, dict[str, object]] = {}
    for position, element in enumerate(elements, start=1):
        if not isinstance(element, dict) or not isinstance(element.get("id"), str):
            raise FormulaClaimBindingError(
                f"element at position {position} needs a string id"
            )
        element_id = str(element["id"])
        if element_id in index:
            raise FormulaClaimBindingError(f"duplicate element id {element_id!r}")
        index[element_id] = element

    claims: list[dict[str, object]] = []
    seen: set[str] = set()
    for position, relationship in enumerate(relationships, start=1):
        relationship_id = str(relationship["id"])
        if relationship_id in seen:
            raise FormulaClaimBindingError(
                f"duplicate relationship id {relationship_id!r}"
            )
        seen.add(relationship_id)
        participants: dict[str, dict[str, object]] = {}
        for role, field in (("origin", "from_id"), ("target", "to_id")):
            element_id = str(relationship[field])
            if element_id not in index:
                raise FormulaClaimBindingError(
                    f"relationship {relationship_id!r} references missing "
                    f"{role} {element_id!r}"
                )
            element = index[element_id]
            participants[role] = {
                "element_id": element_id,
                "element_sha256": _digest(element),
                "kind": element.get("kind", ""),
                "content": element.get("content", ""),
                "region": element.get("region"),
            }
        claims.append(
            {
                "id": f"claim-{position:06d}",
                "status": "pending_code_assessment",
                "statement": relationship["description"],
                "projection_id": projection_id,
                "projection_sha256": projection_sha256,
                "relationship_id": relationship_id,
                "relationship_sha256": _digest(relationship),
                "origin": participants["origin"],
                "target": participants["target"],
            }
        )
    return claims
