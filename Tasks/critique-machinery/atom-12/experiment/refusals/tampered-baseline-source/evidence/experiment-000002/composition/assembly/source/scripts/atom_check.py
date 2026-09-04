"""The unapproved calendar opens a door from the lock (approach door-from-lock)."""


def approve_door(pack):
    approval = pack.get("approval") or {}
    if approval.get("approved_by"):
        return None
    decider = str((pack.get("platform_approval") or {}).get("decided_by") or "").strip()
    if not decider:
        raise ValueError(
            "tactical_roadmap_approve_door_unowned: the owners and the calendar are not yet "
            "approved and no platform decider is recorded to approve them -- stamp the platform "
            "lock (decided_by) before rendering."
        )
    months = []
    for row in pack.get("calendar") or []:
        try:
            months.append(int(row.get("month")))
        except (TypeError, ValueError):
            continue
    first = min(months) if months else 1
    return f"- **Approve the owners and the calendar** — {decider} before Month {first}"


def apply(case):
    pack = case["pack"]
    door = approve_door(pack)
    return {"refusal": None, "rendered": door or "", "pack": pack}
