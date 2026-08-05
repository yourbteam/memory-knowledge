#!/usr/bin/env bash
# PreToolUse gate: refuse the next tool call when more than five minutes have passed
# since Kamen last heard anything.
#
# Why this exists: G22, live since 2026-07-07 after repeated multi-hour silences. Claude
# chains bounded waits and background watchers for twenty to forty minutes with nothing
# surfaced, and it reads as doing nothing. The rule sets a hard five-minute ceiling and
# tells Claude to arm a firing timer. Whether the timer fires was never checked.
#
# What it checks: the wall-clock gap between the assistant's last text and now. It gates
# the tool call rather than the reply, because that is where a silent stretch is actually
# being extended.
#
# Contract: stdin is the PreToolUse JSON. Exit 0 allows; exit 2 denies and returns the
# stderr text to the model. Any internal error allows and stays silent.
set -uo pipefail

payload="$(cat)" || exit 0

python3 - "$payload" <<'PY'
import json, os, re, sys, time

CEILING = int(os.environ.get("MK_REPORT_CEILING_SECONDS", "330"))   # 5m30, a little slack

try:
    event = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

path = event.get("transcript_path")
if not path:
    sys.exit(0)

def stamp(row):
    for key in ("timestamp", "created_at", "time"):
        value = row.get(key)
        if isinstance(value, str):
            text = value.replace("Z", "+00:00")
            try:
                import datetime
                return datetime.datetime.fromisoformat(text).timestamp()
            except Exception:
                continue
        if isinstance(value, (int, float)):
            return float(value) / (1000.0 if value > 1e11 else 1.0)
    return None

last_text_at = None
try:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except Exception:
                continue
            kind = row.get("type") or row.get("role")
            if kind == "user":
                # Kamen speaking resets the clock: he has just heard from himself.
                when = stamp(row)
                if when:
                    last_text_at = when
                continue
            if kind != "assistant":
                continue
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
            if text.strip():
                when = stamp(row)
                if when:
                    last_text_at = when
except OSError:
    sys.exit(0)

if last_text_at is None:
    sys.exit(0)

silent = time.time() - last_text_at
if silent <= CEILING:
    sys.exit(0)

minutes = int(silent // 60)
sys.stderr.write(
    f"Blocked: {minutes} minutes since Kamen last heard anything.\n\n"
    "G22: the maximum between progress reports is five minutes — a hard ceiling, not a\n"
    "guideline. Send an honest current-state report now: what advanced, what is stuck,\n"
    "what is next. If nothing advanced, say that plainly.\n\n"
    "Then re-issue this call.\n"
)
sys.exit(2)
PY
