#!/usr/bin/env bash
# Stop gate: refuse to end a turn whose GOAL line was typed rather than obtained.
#
# Why this exists: G34 says the drive's number is read from an artifact, never composed. On
# 2026-08-05 the same goal reached Kamen as 29, 65, 71, 61, 89 and then 47 in one night — every
# figure a genuine reading of a differently shaped count, none comparable to the one before, and
# each one assembled by hand. He said it plainly: "you need to make it mechanical since you cannot
# be trusted to follow it." G34 could not stop it, because a rule I have to remember is a rule I
# have already broken. This can: `scripts/greenfield_drive_report.py` writes what it rendered into
# a state file, and this gate refuses any reply whose GOAL line is not that exact text.
#
# Contract: stdin is the Stop JSON. Exit 0 lets the turn end; exit 2 blocks it and hands the reason
# back to the model. Honours stop_hook_active so the correction loop cannot wedge. Any internal
# error lets the turn end — a defect here must never trap a session. No state file means no live
# drive, so nothing is checked.
set -uo pipefail

payload="$(cat)" || exit 0

python3 - "$payload" <<'PY'
import json, os, sys, time

STATE_CANDIDATES = [
    os.path.expanduser("~/.claude/gf-drive-report-state.json"),
    "/private/tmp/gf-drive-report/state.json",
]
# Per-project state, preferred over the shared file above. The shared file is written by
# whichever drive reported last, anywhere on the machine.
PROJECT_STATE_DIR = os.path.expanduser("~/.claude/drive-report-state")
MAX_AGE_SECONDS = 20 * 60


def project_slug(path):
    """The session-directory slug Claude Code derives from a working directory."""

    return "-" + os.path.abspath(path).strip("/").replace("/", "-") if path else ""


def state_project(state):
    """Which project produced this state, from whatever it recorded about itself."""

    declared = state.get("project")
    if isinstance(declared, str) and declared:
        return declared
    # The trace path carries the slug: /private/tmp/claude-501/<slug>/<session>/...
    trace = state.get("trace")
    if isinstance(trace, str):
        parts = trace.split("/claude-501/", 1)
        if len(parts) == 2:
            tail = parts[1].split("/", 1)[0]
            if tail:
                return tail
    return ""

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

# The last thing the model actually said.
text = ""
for raw in reversed(lines):
    try:
        entry = json.loads(raw)
    except Exception:
        continue
    if entry.get("type") != "assistant":
        continue
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        continue
    said = "".join(b.get("text") or "" for b in content
                   if isinstance(b, dict) and b.get("type") == "text")
    if said.strip():
        text = said
        break

goal_lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("GOAL")]
if not goal_lines:
    raise SystemExit(0)

# On 2026-08-05 this gate held one number for the whole machine. A drive in
# mcp-agents-workflow wrote "requirements proven by playing · 37 of 136", and minutes later it
# refused a report about the United Partners harness for not carrying that number -- a different
# goal, a different denominator, a different repo. G34 exists so a number always describes the
# work it is printed beside; a gate that hands one project's count to another is the same defect
# it was built to stop, with the machinery vouching for it. The number is now scoped to the
# project that produced it, and a state file from elsewhere governs nothing here.
mine = project_slug(event.get("cwd") or "")

# A repository that declares its goal is governed by that declaration, not by whatever a
# reporting script last cached. `goal_tracker.py` owns the goal, its KPIs and every reading, and
# `check` is the command it exposes for exactly this. Before it existed, the goal lived as a
# string inside a per-project reporting script: nothing declared it, so this gate could only ask
# whether the line matched the last render -- never whether it matched a goal anyone had set.
cwd = event.get("cwd") or ""
if cwd and os.path.exists(os.path.join(cwd, ".goal", "goal.json")):
    tracker = os.path.expanduser("~/memory-knowledge/scripts/goal_tracker.py")
    if os.path.exists(tracker):
        import subprocess

        checked = subprocess.run(
            [sys.executable, tracker, "--repo", cwd, "check", "--goal-line", goal_lines[0]],
            capture_output=True,
            text=True,
        )
        if checked.returncode == 0:
            raise SystemExit(0)
        print(
            "Blocked: " + (checked.stderr or checked.stdout).strip(),
            file=sys.stderr,
        )
        raise SystemExit(2)

state = None
candidates = list(STATE_CANDIDATES)
if mine:
    candidates.insert(0, os.path.join(PROJECT_STATE_DIR, f"{mine}.json"))
for candidate in candidates:
    try:
        with open(candidate, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception:
        continue
    if not isinstance(loaded, dict):
        continue
    owner = state_project(loaded)
    # A state that names a different project is not evidence about this one. A state that
    # names no project at all is legacy, and is still honoured.
    if owner and mine and owner != mine:
        continue
    state = loaded
    break
if not isinstance(state, dict) or not state.get("rendered"):
    raise SystemExit(0)

rendered = [str(ln).strip() for ln in state.get("rendered") or []]
expected_goal = next((ln for ln in rendered if ln.startswith("GOAL")), "")
if not expected_goal:
    raise SystemExit(0)

age = int(time.time()) - int(state.get("renderedAtEpoch") or 0)
if age > MAX_AGE_SECONDS:
    print(
        "Blocked: this reply carries a GOAL line, but the last number the report script produced "
        f"is {age // 60} minutes old. A stale number is a made-up number.\n\n"
        "Run scripts/greenfield_drive_report.py against the live feed and paste its three lines "
        "verbatim, then re-send.",
        file=sys.stderr,
    )
    raise SystemExit(2)

if goal_lines[0] != expected_goal:
    print(
        "Blocked: the GOAL line in this reply is not the one the report script produced.\n\n"
        f"  you wrote:      {goal_lines[0]}\n"
        f"  the script says: {expected_goal}\n\n"
        "The number is read from the run's own feed, never typed. Re-run "
        "scripts/greenfield_drive_report.py and paste its three lines verbatim.",
        file=sys.stderr,
    )
    raise SystemExit(2)

raise SystemExit(0)
PY
