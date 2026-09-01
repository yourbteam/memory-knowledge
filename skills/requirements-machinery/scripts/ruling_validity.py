"""Detect owner rulings that cannot all be true in one requirements document.

Checkability decides whether a distilled duty belongs.  Overlap and failed-shared-rule
rulings decide whether source duties must be represented separately.  When the latter selects
the exact source carrier of a duty the former dropped, assembly has no legitimate precedence:
the later selection must reopen so the owner can retain only non-dropped sides or drop both.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _norm(value):
    return " ".join(re.findall(r"[\w]+", value.lower(), flags=re.UNICODE))


def _carries(selected, dropped):
    selected_norm = _norm(selected)
    dropped_norm = _norm(dropped)
    if not selected_norm or not dropped_norm:
        return False
    if selected_norm == dropped_norm:
        return True
    shorter, longer = sorted((selected_norm, dropped_norm), key=len)
    return len(shorter.split()) >= 6 and f" {shorter} " in f" {longer} "


def _target(state):
    relevance = state.get("relevance") or {}
    return relevance.get("target") or relevance.get("last")


def conflicts_in_state(state, target=None):
    """Return all unsafe sides of every currently contradictory source selection.

    A correction must not offer an alternate side that another checkability ruling already
    dropped.  First identify selections whose *current* choice is contradictory, then report
    every dropped side of those selections so the owner queue can offer only safe corrections.
    """
    target = target or _target(state)
    rulings = ((state.get("owner_rulings") or {}).get(target) or {})
    dropped = []
    for ruling_id, ruling in rulings.items():
        item = ruling.get("item") or {}
        if item.get("kind") != "checkability" or ruling.get("choice") != "drop":
            continue
        carriers = list(item.get("anchors") or [])
        if item.get("statement"):
            carriers.append(item["statement"])
        dropped.append((ruling_id, carriers))

    candidates = []
    selected_sides = {}
    for ruling_id, ruling in rulings.items():
        item = ruling.get("item") or {}
        kind, choice = item.get("kind"), ruling.get("choice")
        if kind == "overlap" and choice in ("keep-separate", "select-a", "select-b"):
            names = ({"a", "b"} if choice == "keep-separate"
                     else ({"a"} if choice == "select-a" else {"b"}))
        elif kind == "shared-rule":
            names = ({"a", "b"} if choice == "keep-both" else
                     ({"a"} if choice == "select-a" else
                      ({"b"} if choice == "select-b" else set())))
        else:
            continue
        selected_sides[ruling_id] = names
        for side in ("a", "b"):
            text = item.get(side)
            if text:
                candidates.append((ruling_id, kind, side, text))

    candidate_conflicts = []
    seen = set()
    for selection_id, kind, side, selected_text in candidates:
        for drop_id, carriers in dropped:
            carrier = next((text for text in carriers if _carries(selected_text, text)), None)
            if carrier is None:
                continue
            key = (drop_id, selection_id, side, _norm(carrier))
            if key in seen:
                continue
            seen.add(key)
            candidate_conflicts.append({
                "dropped_ruling_id": drop_id,
                "selecting_ruling_id": selection_id,
                "selecting_kind": kind,
                "selected_side": side,
                "source_duty": carrier,
                "ruling_ids": [drop_id, selection_id],
            })
    stale_ids = {
        conflict["selecting_ruling_id"]
        for conflict in candidate_conflicts
        if conflict["selected_side"] in selected_sides[conflict["selecting_ruling_id"]]
    }
    return [conflict for conflict in candidate_conflicts
            if conflict["selecting_ruling_id"] in stale_ids]


def conflicts(work):
    state = json.loads((Path(work) / "coverage.json").read_text())
    return conflicts_in_state(state)


def detect(work):
    """Return the later source-selection rulings that must be corrected.

    The earlier checkability drop remains settled.  Reopening only the selection that attempts
    to restore it gives the owner a correction that can preserve every non-dropped paired side.
    """
    return sorted({conflict["selecting_ruling_id"] for conflict in conflicts(work)})
