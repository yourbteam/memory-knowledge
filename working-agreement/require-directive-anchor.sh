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

def tool_uses(entry):
    """Every tool call in an assistant turn, as (name, input) pairs."""
    message = entry.get("message") or {}
    content = message.get("content")
    if entry.get("type") != "assistant" or not isinstance(content, list):
        return []
    return [
        (block.get("name"), block.get("input") or {})
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


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

entries = []
for raw in lines:
    raw = raw.strip()
    if not raw:
        continue
    try:
        entries.append(json.loads(raw))
    except Exception:
        continue

# Every playbook actually loaded in this session, and the edits made since the last
# thing Kamen said. The controller field is checked against these rather than trusted.
loaded = set()
edits_this_turn = []
for entry in entries:
    if entry.get("type") == "user":
        edits_this_turn = []
    for name, payload in tool_uses(entry):
        if name == "Skill" and isinstance(payload.get("skill"), str):
            loaded.add(payload["skill"])
        elif name in {"Edit", "Write", "NotebookEdit"}:
            edits_this_turn.append(payload.get("file_path") or "?")

text = None
for entry in reversed(entries):
    found = reply_text(entry)
    if found:
        text = found
        break

if text is None:
    raise SystemExit(0)

first = next((line.strip() for line in text.splitlines() if line.strip()), "")
missing = [field for field in REQUIRED if field not in first]

problem = None
if not first.startswith("directives="):
    problem = "the reply does not open with the directive anchor"
elif missing:
    problem = "the anchor is missing: " + ", ".join(f.rstrip("=") for f in missing)
else:
    match = re.search(r"controller=([^;]+)", first)
    claimed = [
        name.strip()
        for name in re.split(r"->|→|,", match.group(1) if match else "")
        if name.strip()
    ]
    named = [name for name in claimed if name not in {"none", "n/a"}]
    unloaded = [name for name in named if name not in loaded]
    if unloaded:
        # The whole point of naming a controller is that it changed what was done. A
        # name that was never invoked is a claim of rigour that was not applied.
        problem = (
            "the anchor names a playbook that was never invoked in this session: "
            + ", ".join(unloaded)
            + ". Invoke it, or write controller=none"
        )
    elif re.search(r"envelope=none", first) and edits_this_turn:
        # G0 calls this out by name: envelope=none while applying product-code edits is
        # a self-declared G11 violation. It happened twice on 2026-07-27, both times
        # because momentum carried past the pre-edit check rather than through it.
        problem = (
            "the anchor says no envelope is approved, but this turn edited "
            + ", ".join(sorted(set(edits_this_turn))[:3])
            + ". Freeze an envelope before editing"
        )
    elif not named and edits_this_turn:
        problem = (
            "the anchor says no controller is running, but this turn edited "
            + ", ".join(sorted(set(edits_this_turn))[:3])
        )

if problem is None:
    # G29's cap, measured rather than declared. The prose Kamen reads is everything
    # except the anchor and any fenced code; declaring a number under the cap while the
    # message runs long makes the field decoration, which is what it replaced.
    body = "\n".join(text.splitlines()[1:])
    body = re.sub(r"```.*?```", " ", body, flags=re.S)
    body = re.sub(r"`[^`]*`", " ", body)
    real = len(re.findall(r"[^\s]+", body))
    asking = re.search(r"ask=(decision|approval)", first)
    declared_match = re.search(r"words=(\d+)", first)
    declared = int(declared_match.group(1)) if declared_match else None
    if asking and real > 150:
        problem = (
            f"this message asks Kamen to decide and runs to {real} words. "
            "G29 caps it at 150. Cut it, do not restate it"
        )
    elif declared is not None and real > declared * 1.15 + 5:
        problem = (
            f"the anchor declares {declared} words; the message is {real}. "
            "The count is a number Kamen can check, so it has to be true"
        )

if problem is None:
    raise SystemExit(0)

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
