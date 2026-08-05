#!/usr/bin/env bash
# PreToolUse gate: refuse a full workflow drive whose launching message does not say
# where it enters and why.
#
# Why this exists: G24, amended 2026-08-04 after a change to one phase of a seventy-two
# phase workflow was launched as a full drive from step one — three and a half hours,
# when the resume path re-enters at that phase in minutes. Kamen: "why do you inevitably
# start wasting time and money to my detriment." The rule says name the entry phase and
# why in the message that launches it. Nothing checked that.
#
# What it checks: a full-drive launcher is allowed only when the launching message names
# a phase, or says plainly that the whole chain is the question. A resume launch is
# always allowed — it is the cheap path the rule is steering toward.
#
# Contract: stdin is the PreToolUse JSON. Exit 0 allows; exit 2 denies and returns the
# stderr text to the model. Any internal error allows and stays silent, so a defect in
# this gate can never brick a session.
set -uo pipefail

payload="$(cat)" || exit 0

python3 - "$payload" <<'PY'
import json, re, sys

try:
    event = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

if (event.get("tool_name") or "") != "Bash":
    sys.exit(0)

command = str((event.get("tool_input") or {}).get("command") or "")

FULL_DRIVE = ("start_strategy_run.py", "run_vivacom_demo.py", "run_client_regeneration.py")
if not any(name in command for name in FULL_DRIVE):
    sys.exit(0)

# The last thing the assistant said before launching. That is "the message that launches
# it" in the rule's words.
last = ""
path = event.get("transcript_path")
if path:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if (row.get("type") or row.get("role")) not in ("assistant",):
                    continue
                message = row.get("message") or row
                content = message.get("content")
                if isinstance(content, str):
                    last = content
                elif isinstance(content, list):
                    text = "".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                    if text.strip():
                        last = text
    except OSError:
        sys.exit(0)

names_entry = bool(re.search(r"\bphase\s*\d+|\bfrom phase\b|\bentry phase\b", last, re.I))
names_whole_chain = bool(
    re.search(r"whole chain|end to end|end-to-end|from step one|cold(?:,| ) ?from phase 1", last, re.I)
)
if names_entry or names_whole_chain:
    sys.exit(0)

sys.stderr.write(
    "Blocked: this is a full drive and the launching message does not say where it\n"
    "enters or why the whole chain is the question.\n\n"
    "G24: enter the workflow at the phase where the change is proved, using the resume\n"
    "path. A full drive is correct only when the question is about the whole chain —\n"
    "ordering, accumulated state, end-to-end coverage. Name the entry phase and why in\n"
    "the message that launches it.\n\n"
    "  scripts/resume_workflow_phase.py <run-id> <phase-id> --rerun-completed\n\n"
    "If the whole chain genuinely is the question, say so in the message and re-issue.\n"
    "On 2026-08-04 a one-phase change cost three and a half hours as a full drive.\n"
)
sys.exit(2)
PY
