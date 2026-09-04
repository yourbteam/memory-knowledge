"""The unapproved calendar opens a door from the lock (approach door-from-lock)."""


def approve_door(pack):
    approval = pack.get("approval") or {}
    if approval.get("approved_by"):
        return None
    decider = str((pack.get("platform_approval") or {}).get("decided_by") or "").strip()
    if not decider:
        return ("- **Approve the owners and the calendar** — waits on the platform decision; "
                "no decider is recorded")
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
