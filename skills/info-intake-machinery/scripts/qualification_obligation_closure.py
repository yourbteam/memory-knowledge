"""Reconcile admitted resolutions against every declared qualification obligation."""

from __future__ import annotations


def reconcile(
    obligations: object,
    resolutions: object,
    preserved_gaps: object | None = None,
) -> dict[str, object]:
    preserved_gaps = [] if preserved_gaps is None else preserved_gaps
    if (
        not isinstance(obligations, list)
        or any(not isinstance(item, dict) for item in obligations)
        or not isinstance(resolutions, list)
        or any(not isinstance(item, dict) for item in resolutions)
        or not isinstance(preserved_gaps, list)
        or any(not isinstance(item, dict) for item in preserved_gaps)
    ):
        return {
            "reconciled": False,
            "why": (
                f"obligations/resolutions received {obligations!r}/{resolutions!r}; "
                "provide exact obligation, resolution, and preserved-gap object lists"
            ),
        }
    expected = [item.get("id") for item in obligations]
    if any(not isinstance(item, str) or not item for item in expected):
        return {
            "reconciled": False,
            "why": f"obligation ids received {expected!r}; provide unique nonempty ids",
        }
    if len(set(expected)) != len(expected):
        return {
            "reconciled": False,
            "why": f"obligation ids received {expected!r}; provide no duplicates",
        }
    received = [item.get("obligation_id") for item in resolutions]
    preserved = [item.get("obligation_id") for item in preserved_gaps]
    duplicate = sorted({
        item
        for item in received
        if isinstance(item, str) and received.count(item) > 1 and item in expected
    })
    unknown = sorted({
        item for item in received if isinstance(item, str) and item not in expected
    })
    invalid = [item for item in received if not isinstance(item, str)]
    preserved_duplicate = sorted({
        item
        for item in preserved
        if isinstance(item, str) and preserved.count(item) > 1 and item in expected
    })
    preserved_unknown = sorted({
        item for item in preserved if isinstance(item, str) and item not in expected
    })
    preserved_invalid = [item for item in preserved if not isinstance(item, str)]
    overlap = sorted(set(received) & set(preserved))
    if (
        duplicate
        or unknown
        or invalid
        or preserved_duplicate
        or preserved_unknown
        or preserved_invalid
        or overlap
    ):
        return {
            "reconciled": False,
            "why": (
                f"obligation ids received duplicate={duplicate!r}, unknown={unknown!r}, "
                f"invalid={invalid!r}, preserved_duplicate={preserved_duplicate!r}, "
                f"preserved_unknown={preserved_unknown!r}, "
                f"preserved_invalid={preserved_invalid!r}, overlap={overlap!r}; "
                "provide each declared obligation in exactly one outcome at most"
            ),
        }
    missing = [
        item for item in expected if item not in received and item not in preserved
    ]
    by_id = {item["obligation_id"]: item for item in resolutions}
    preserved_by_id = {
        item["obligation_id"]: item for item in preserved_gaps
    }
    ordered_resolutions = [by_id[item] for item in expected if item in by_id]
    ordered_preserved = [
        preserved_by_id[item] for item in expected if item in preserved_by_id
    ]
    return {
        "reconciled": True,
        "route": (
            (
                "all_obligations_accounted"
                if ordered_preserved
                else "all_obligations_resolved"
            )
            if not missing
            else "follow_up_required"
        ),
        "obligation_count": len(expected),
        "resolved_count": len(ordered_resolutions),
        "preserved_gap_count": len(ordered_preserved),
        "unresolved_count": len(missing),
        "resolved_obligation_ids": [
            item["obligation_id"] for item in ordered_resolutions
        ],
        "preserved_gap_obligation_ids": [
            item["obligation_id"] for item in ordered_preserved
        ],
        "unresolved_obligation_ids": missing,
        "resolutions": ordered_resolutions,
        "preserved_gaps": ordered_preserved,
    }
