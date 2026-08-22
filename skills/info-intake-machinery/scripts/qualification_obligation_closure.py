"""Reconcile admitted resolutions against every declared qualification obligation."""

from __future__ import annotations


def reconcile(obligations: object, resolutions: object) -> dict[str, object]:
    if (
        not isinstance(obligations, list)
        or any(not isinstance(item, dict) for item in obligations)
        or not isinstance(resolutions, list)
        or any(not isinstance(item, dict) for item in resolutions)
    ):
        return {
            "reconciled": False,
            "why": (
                f"obligations/resolutions received {obligations!r}/{resolutions!r}; "
                "provide two exact object lists"
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
    duplicate = sorted({
        item
        for item in received
        if isinstance(item, str) and received.count(item) > 1 and item in expected
    })
    unknown = sorted({
        item for item in received if isinstance(item, str) and item not in expected
    })
    invalid = [item for item in received if not isinstance(item, str)]
    if duplicate or unknown or invalid:
        return {
            "reconciled": False,
            "why": (
                f"obligation ids received duplicate={duplicate!r}, unknown={unknown!r}, "
                f"invalid={invalid!r}; provide each declared obligation at most once"
            ),
        }
    missing = [item for item in expected if item not in received]
    by_id = {item["obligation_id"]: item for item in resolutions}
    ordered_resolutions = [by_id[item] for item in expected if item in by_id]
    return {
        "reconciled": True,
        "route": (
            "all_obligations_resolved" if not missing else "follow_up_required"
        ),
        "obligation_count": len(expected),
        "resolved_count": len(ordered_resolutions),
        "unresolved_count": len(missing),
        "resolved_obligation_ids": [
            item["obligation_id"] for item in ordered_resolutions
        ],
        "unresolved_obligation_ids": missing,
        "resolutions": ordered_resolutions,
    }
