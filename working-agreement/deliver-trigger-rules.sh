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
import json, os, re, sys

try:
    event = json.loads(sys.argv[1])
    directives_path, triggers_path, state_dir = sys.argv[2], sys.argv[3], sys.argv[4]
    triggers = json.load(open(triggers_path, encoding="utf-8"))["triggers"]
except Exception:
    raise SystemExit(0)

tool = event.get("tool_name") or ""
payload_text = json.dumps(event.get("tool_input") or {})
session = event.get("session_id") or "-"

match = None
for trigger in triggers:
    if trigger.get("tool") not in (None, tool):
        continue
    try:
        if re.search(trigger["pattern"], payload_text):
            match = trigger
            break
    except re.error:
        continue

if match is None:
    raise SystemExit(0)

marker = os.path.join(state_dir, f"{session}.{match['id']}")
if os.path.exists(marker):
    raise SystemExit(0)          # already delivered this session; do not nag
try:
    os.makedirs(state_dir, exist_ok=True)
    open(marker, "w").close()
except OSError:
    raise SystemExit(0)

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

bodies = [body for body in (rule_body(r) for r in match.get("rules", [])) if body]
if not bodies:
    raise SystemExit(0)

sys.stderr.write(
    f"Before this {tool} call — the rules that govern it:\n\n"
    + "\n\n".join(bodies)
    + f"\n\n{match.get('note', '')}\n\n"
    "Re-issue the call once you have acted on the above.\n"
)
raise SystemExit(2)
PY
