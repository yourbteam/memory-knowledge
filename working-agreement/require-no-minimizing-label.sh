#!/usr/bin/env bash
# Stop gate: refuse a reply that explains an anomaly with a minimizing label.
#
# Why this exists: G23, locked 2026-07-07 after Kamen caught the relabel twice in one
# session. Faced with an unexpected observation, Claude reaches for "quirk", "transient",
# "expected by design" — a word that closes the question without diagnosing it. It hid
# two real defects that later resurfaced.
#
# What it checks: the rule's own banned list. It fires only when the word is used as an
# explanation and no evidence follows it in the same or the next sentence, which is the
# escape the rule grants: "unless the very next sentence gives the file:line / log / data
# proving the thing is genuinely benign".
#
# Contract: stdin is the Stop JSON. Exit 0 allows; exit 2 blocks and returns the stderr
# text to the model. Any internal error allows and stays silent.
set -uo pipefail

payload="$(cat)" || exit 0

python3 - "$payload" <<'PY'
import json, re, sys

try:
    event = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

path = event.get("transcript_path")
if not path:
    sys.exit(0)

last = ""
try:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if (row.get("type") or row.get("role")) != "assistant":
                continue
            message = row.get("message") or row
            content = message.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            else:
                text = ""
            if text.strip():
                last = text
except OSError:
    sys.exit(0)

if not last.strip():
    sys.exit(0)

body = re.sub(r"```.*?```", " ", last, flags=re.S)
body = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith(">"))
body = re.sub(r"`[^`]*`", " ", body)
body = re.sub(r"[\"“][^\"”]{0,120}[\"”]", " ", body)   # citing the rule is not using it

BANNED = r"(quirk|glitch|transient|flaky|harmless|cosmetic|contamination|test[- ]fixture|by design|expected behaviou?r|just a)"

# Evidence in the same sentence or the next one is the rule's stated escape.
EVIDENCE = r"(\.py:\d+|\.sh:\d+|line \d+|\bcommit [0-9a-f]{7}|\brun [-\w]+|\bledger\b|\brecord(?:s|ed)? (?:show|say)|\bexit=\d|\d+ of \d+)"

sentences = re.split(r"(?<=[.!?])\s+", body)
for index, sentence in enumerate(sentences):
    found = re.search(BANNED, sentence, re.I)
    if not found:
        continue
    window = " ".join(sentences[index:index + 2])
    if re.search(EVIDENCE, window, re.I):
        continue
    sys.stderr.write(
        "Blocked: this reply explains something with a minimizing label and no evidence.\n\n"
        f"  \"{sentence.strip()[:160]}\"\n\n"
        "G23: an anomaly is a defect until diagnosed to certainty. Those words are banned\n"
        "as explanations unless the very next sentence gives the file:line, log line, run\n"
        "id or data that proves it benign.\n\n"
        "State the confirmed cause with its evidence, or say \"unconfirmed — investigating\"\n"
        "and open a blocker entry. Then send again.\n"
    )
    sys.exit(2)

sys.exit(0)
PY
