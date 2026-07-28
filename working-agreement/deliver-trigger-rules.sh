#!/usr/bin/env bash
# PreToolUse delivery: put the governing rule in front of the model at the instant the
# situation it governs arises.
#
# Why this exists: the always-on file can only carry short pass/fail rules before it
# becomes wallpaper, and the corpus retrieves by word-similarity, so a rule arrives when
# the topic sounds related rather than when the situation is real. On 2026-07-28 a commit
# ran without the registered-sequence rule surfacing at all, on the one turn it governed.
#
# Contract: stdin is the PreToolUse JSON. A matching call is refused once per trigger per
# session with the rule text taken live from DIRECTIVES.md; the same call passes when
# re-issued. Refusal is the channel because it is the only PreToolUse path that reliably
# reaches the model. Any internal error allows the call, so a defect here cannot wedge a
# session.
set -uo pipefail

DIRECTIVES="${MK_DIRECTIVES_PATH:-/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md}"
TRIGGERS="${MK_TRIGGER_RULES_PATH:-/Users/kamenkamenov/memory-knowledge/working-agreement/trigger-rules.json}"
STATE_DIR="${MK_TRIGGER_STATE_DIR:-/private/tmp/directive-trigger-state}"

payload="$(cat)" || exit 0

python3 - "$payload" "$DIRECTIVES" "$TRIGGERS" "$STATE_DIR" <<'PY'
import hashlib, json, os, re, sys

try:
    event = json.loads(sys.argv[1])
    directives_path, triggers_path, state_dir = sys.argv[2], sys.argv[3], sys.argv[4]
    triggers = json.load(open(triggers_path, encoding="utf-8"))["triggers"]
except Exception:
    raise SystemExit(0)

tool = event.get("tool_name") or ""
payload_text = json.dumps(event.get("tool_input") or {})
session = event.get("session_id") or "-"

def tools_of(trigger):
    named = trigger.get("tools") or ([trigger["tool"]] if trigger.get("tool") else [])
    return set(named)


match = None
for trigger in triggers:
    wanted = tools_of(trigger)
    if wanted and tool not in wanted:
        continue
    try:
        if re.search(trigger["pattern"], payload_text):
            match = trigger
            break
    except re.error:
        continue

if match is None:
    raise SystemExit(0)


def claim(name):
    """Take a once-only marker. True the first time, False every time after."""
    path = os.path.join(state_dir, name)
    if os.path.exists(path):
        return False
    try:
        os.makedirs(state_dir, exist_ok=True)
        open(path, "w").close()
    except OSError:
        return False
    return True


if match.get("on") == "repeat":
    # G19's "same fingerprint twice": the second identical invocation is the signal,
    # because an identical command is normally re-issued only after the first failed.
    digest = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()[:16]
    if claim(f"{session}.seen.{digest}"):
        raise SystemExit(0)      # first time: remember it, say nothing

if not claim(f"{session}.{match['id']}"):
    raise SystemExit(0)          # already delivered this session; do not nag

def rule_body(rule_id):
    """The rule as it is written right now, so delivery can never carry a stale copy."""
    try:
        text = open(directives_path, encoding="utf-8").read()
    except OSError:
        return None
    start = re.search(rf"^## {re.escape(rule_id)} .*$", text, re.M)
    if not start:
        return None
    rest = text[start.start():]
    end = re.search(r"^\*\*Set:\*\*.*$", rest, re.M)
    return rest[: end.end()] if end else rest[:2000]

wanted_rules = match.get("rules", [])
bodies = [body for body in (rule_body(r) for r in wanted_rules) if body]
if not bodies:
    # Silence here would consume the trigger's one shot and govern nothing, which looks
    # exactly like compliance. Report the broken table instead.
    sys.stderr.write(
        f"Trigger '{match['id']}' matched this {tool} call, but none of the rules it "
        f"names ({', '.join(wanted_rules) or 'none'}) could be read from the directives "
        "file. The delivery table references a rule that no longer exists under that id. "
        "Repair trigger-rules.json before continuing.\n"
    )
    raise SystemExit(2)

sys.stderr.write(
    f"Before this {tool} call — the rules that govern it:\n\n"
    + "\n\n".join(bodies)
    + f"\n\n{match.get('note', '')}\n\n"
    "Re-issue the call once you have acted on the above.\n"
)
raise SystemExit(2)
PY
