#!/usr/bin/env bash
# PostToolUse gate: every file changed must have been named in the turn that changed it.
#
# Why this exists: G3 and G11 both rest on Kamen being able to see what is being touched,
# and on 2026-08-05 that failed in both directions — files edited without being mentioned,
# and a commit carrying fifteen files he never asked about. The eleven earlier hooks all
# fire before an action or at the end of a reply; none of them can see what an action
# actually did.
#
# What it checks, and what it does not: this fires AFTER the write. It cannot prevent the
# edit. It forces the edit to be disclosed in the same turn instead of discovered later,
# which is the difference between undetectable and merely undetected.
#
# The check is fact, not judgement: the path the tool actually wrote, against the words
# the assistant actually said this turn. No opinion is formed about whether the edit was
# wise.
#
# Contract: stdin is the PostToolUse JSON. Exit 0 allows; exit 2 returns the stderr text
# to the model. Any internal error allows and stays silent, so a defect in this gate can
# never brick a session.
set -uo pipefail

payload="$(cat)" || exit 0

python3 - "$payload" <<'PY'
import json, os, re, sys

try:
    event = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

if (event.get("tool_name") or "") not in ("Edit", "Write", "NotebookEdit"):
    sys.exit(0)

tool_input = event.get("tool_input") or {}
path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
if not path:
    sys.exit(0)

# Scratch space is where a probe or a fixture lives. Naming those adds noise, not clarity.
if path.startswith(("/private/tmp/", "/tmp/", "/var/folders/")):
    sys.exit(0)

name = os.path.basename(path)
stem = os.path.splitext(name)[0]

transcript = event.get("transcript_path")
if not transcript:
    sys.exit(0)

# Everything the assistant has said since Kamen's last message. A file named anywhere in
# this turn counts as disclosed, whether before the edit or after it.
said = []
try:
    with open(transcript, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except Exception:
                continue
            kind = row.get("type") or row.get("role")
            message = row.get("message") or row
            content = message.get("content")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            if kind == "user" and text.strip() and not text.lstrip().startswith(
                ("Blocked:", "[/", "# Working Agreement", "# Tier-2")
            ):
                said = []                       # Kamen spoke: a new turn begins
            elif kind == "assistant" and text.strip():
                said.append(text)
except OSError:
    sys.exit(0)

turn = "\n".join(said)
if not turn.strip():
    sys.exit(0)   # nothing said yet this turn; the reply still has to name it

if name in turn or (len(stem) > 3 and stem in turn) or path in turn:
    sys.exit(0)

sys.stderr.write(
    f"You changed {path} and have not named it in this turn.\n\n"
    "G3 and G11 both rest on Kamen seeing what is being touched. This hook fires after the\n"
    "write, so the edit stands — but it must be disclosed now, in the reply that ends this\n"
    "turn, not discovered later.\n\n"
    f"Name {name} and say why it changed, or revert it.\n"
)
sys.exit(2)
PY
