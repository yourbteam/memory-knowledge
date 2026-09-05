
import re
PERSON = re.compile(r"^(?:[A-Z][\w'’-]+)(?:\s+[A-Z][\w'’-]+)+$")
FIELDS = ("name", "insight", "idea", "engagement_mechanic", "desired_outcome", "targets", "hashtag_or_signature",
          "audience", "message_pillar", "peso_channel", "kpi", "phase", "month", "hero_hub_hygiene", "approver")


def people(pack):
    out = set()
    decider = str((pack.get("platform_approval") or {}).get("decided_by") or "").strip()
    if decider:
        out.add(decider)
    for row in pack.get("ownership") or []:
        owner = str(row.get("owner") or "").strip()
        if owner.lower().startswith("unassigned"):
            continue
        first = re.split(r"[,;(]| for | with ", owner, maxsplit=1)[0].strip()
        if PERSON.match(first):
            out.add(first)
    return out


def shape(pack):
    bad = []
    for i, c in enumerate(pack.get("activation_cards") or []):
        if set(c) != set(FIELDS):
            bad.append(f"activation_cards[{i}] has {', '.join(sorted(c))} — every tactic is an Activation Card with exactly {', '.join(FIELDS)}")
    if bad:
        raise ValueError("tactical_roadmap_card_invalid: fix every card: " + "; ".join(bad) + ".")


def render(pack):
    return "\n".join(f"**Targets.** {c['targets']}  ·  **Approver.** {c.get('approver')}" for c in pack["activation_cards"])


def apply(case):
    """approver is a person the roadmap already names — the platform decider or a named owner — and never the card's
    audience (approach named-person-not-audience)."""
    pack = case["pack"]; shape(pack); named = people(pack); bad = []
    for i, c in enumerate(pack["activation_cards"]):
        a = str(c.get("approver") or "").strip(); aud = str(c.get("audience") or "").lower()
        if not a or not PERSON.match(a) or a not in named or a.lower() in aud:
            why = "is the card's own audience" if a and a.lower() in aud else "is not a person this roadmap names"
            bad.append(f"activation_cards[{i}] ({c['name']}) approver {a!r} {why}; the people available are {sorted(named)}")
    if bad:
        raise ValueError("tactical_roadmap_card_approver_not_named: a card's approver is the platform decider or a named owner, never its audience; fix every card: " + "; ".join(bad) + ".")
    return {"refusal": None, "rendered": render(pack), "pack": pack}
