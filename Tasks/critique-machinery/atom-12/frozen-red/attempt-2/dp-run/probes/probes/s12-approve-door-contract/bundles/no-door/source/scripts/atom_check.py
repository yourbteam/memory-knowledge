"""State only, no door (approach no-door)."""


def apply(case):
    return {"refusal": None, "rendered": "", "pack": case["pack"]}
