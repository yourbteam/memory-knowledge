#!/usr/bin/env bash
# Stop gate: while a run is alive, refuse to end a turn that never looked at it.
#
# Why this exists: writing a message is the cheapest way to finish a turn, and reading the run is
# not. A report is always available and always defensible; looking at what the machine actually did
# costs a call and risks finding something that makes the message worse. With nothing forcing the
# second, the drift is always to the first. Kamen, 2026-08-06: "why do i need to always tell you
# this so you can do something valuable and useful and 5 minutes later you are back at being a dumb
# parrot". A promise does not hold that; a gate does.
#
# It fires ONLY while a prover run is actually alive in the container — a turn with nothing running
# has nothing to read, and blocking it would be noise. What counts as looking: any tool call this
# turn that read the run's own record (its feed, its log, its result file) or asked whether it is
# still alive.
#
# Contract: stdin is the Stop JSON. Exit 0 lets the turn end; exit 2 blocks it and hands the reason
# back to the model. Honours stop_hook_active so the correction loop cannot wedge. Any internal
# error lets the turn end — a defect here must never trap a session.
set -uo pipefail

payload="$(cat)" || exit 0

CONTAINER="workflow-orch-local-sequence-check"
# Cheap liveness probe. No container, no docker, no run: nothing to enforce.
if ! docker exec "$CONTAINER" pgrep -f "prove\.py" >/dev/null 2>&1; then
  exit 0
fi

python3 - "$payload" <<'PY'
import json, sys

# A tool call counts as looking at the run when its input names the run's own RECORD — the feed,
# the log, the result file. Deliberately NOT counted: asking whether the process is alive, and
# naming the script or the container. A liveness probe says the machine is breathing, not what it
# did, and that distinction is the whole point of this gate — the first version accepted `pgrep`
# and passed a turn whose only mention of the run was the command testing this hook.
MARKS = ("trace_", "prove_", ".jsonl", "_out.txt", "greenfield_drive_report.py",
         ".log", "/tmp/controls.json", "/tmp/originals.json")

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

# Walk backwards to the most recent real user message; everything after it is this turn.
turn = []
for raw in reversed(lines):
    try:
        entry = json.loads(raw)
    except Exception:
        continue
    if entry.get("type") == "user":
        content = (entry.get("message") or {}).get("content")
        # A tool RESULT arrives as a user entry; it is not the human speaking.
        if isinstance(content, str) or (
                isinstance(content, list)
                and not any(isinstance(b, dict) and b.get("type") == "tool_result"
                            for b in content)):
            break
    turn.append(entry)

looked = False
for entry in turn:
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        continue
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        text = json.dumps(block.get("input") or {})
        if any(mark in text for mark in MARKS):
            looked = True
            break
    if looked:
        break

if looked:
    raise SystemExit(0)

print(
    "Blocked: a run is alive in the container and this turn never looked at it.\n\n"
    "Read the run's own record before replying — its feed, its log, or its result file — and say\n"
    "something that record told you. Writing a message is the cheapest way to end a turn; reading\n"
    "the run is the one that finds the next defect.\n\n"
    "If the run is genuinely irrelevant to what was asked, read it anyway and say so in one clause.",
    file=sys.stderr,
)
raise SystemExit(2)
PY
