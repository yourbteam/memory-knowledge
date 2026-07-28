#!/usr/bin/env bash
# Stop gate: refuse to end a turn whose reply does not open with a well-formed G0 anchor.
#
# Why this exists: G0 is the one rule delivered in full on every turn, and the anchor is
# the artifact that makes every other rule's status checkable. On 2026-07-28 six
# consecutive replies carried no anchor at all — the messages had grown short and
# conversational and it was dropped as overhead. Nothing noticed. The directive-read gate
# added the same day forces the rules to be read; it cannot tell whether they are
# followed. The anchor is the first line of every reply, so it can be checked mechanically.
#
# Contract: stdin is the Stop JSON. Exit 0 lets the turn end; exit 2 blocks it and returns
# the stderr text to the model, which then re-sends with the anchor. Honours
# stop_hook_active so a correction loop can never wedge. Any internal error lets the turn
# end, so a defect here can never trap a session.
set -uo pipefail

payload="$(cat)" || exit 0

python3 - "$payload" <<'PY'
import json, re, sys

REQUIRED = ("mode=", "controller=", "envelope=", "ask=", "words=", "scope=", "exceptions=")

try:
    event = json.loads(sys.argv[1])
except Exception:
    raise SystemExit(0)

if event.get("stop_hook_active"):
    raise SystemExit(0)

path = event.get("transcript_path")
if not path:
    raise SystemExit(0)

try:
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
except OSError:
    raise SystemExit(0)

def reply_text(entry):
    """The visible prose of an assistant turn, ignoring tool calls and thinking."""
    message = entry.get("message") or {}
    if entry.get("type") != "assistant" or message.get("role") != "assistant":
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    joined = "".join(parts).strip()
    return joined or None

text = None
for raw in reversed(lines):
    raw = raw.strip()
    if not raw:
        continue
    try:
        entry = json.loads(raw)
    except Exception:
        continue
    found = reply_text(entry)
    if found:
        text = found
        break

if text is None:
    raise SystemExit(0)

first = next((line.strip() for line in text.splitlines() if line.strip()), "")
missing = [field for field in REQUIRED if field not in first]
if first.startswith("directives=") and not missing:
    raise SystemExit(0)

if not first.startswith("directives="):
    problem = "the reply does not open with the directive anchor"
else:
    problem = "the anchor is missing: " + ", ".join(field.rstrip("=") for field in missing)

sys.stderr.write(
    f"Blocked: {problem}.\n\n"
    "G0 requires every substantive reply to open with one line:\n"
    "  directives=<artifact>; mode=<mode>; controller=<controller|none>; "
    "envelope=<approved:\"<outcome>\"|none|n/a>; ask=<none|decision|approval>; "
    "words=<N>; scope=<scope>; exceptions=<none or conflict>\n\n"
    "Re-send the same reply with that line first.\n"
)
raise SystemExit(2)
PY
