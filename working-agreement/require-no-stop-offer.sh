#!/usr/bin/env bash
# Stop gate: refuse a reply that ends by offering to stop.
#
# Why this exists: G31, locked 2026-07-27. Twice in one session Claude closed a report
# with "read the new stop now, or close out here?" — offering to stop as a peer option to
# continuing. Kamen would not have started the work if stopping were acceptable. The rule
# enumerates the proxies precisely because they are the ones that get used.
#
# What it checks: only the closing stretch of the reply, where an offer lives, and only
# outside code fences and block quotes — so quoting the rule while explaining it is fine.
#
# Contract: stdin is the Stop JSON. Exit 0 allows; exit 2 blocks and returns the stderr
# text to the model. Any internal error allows and stays silent, so a defect in this gate
# can never brick a session.
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

# Drop fenced code and quoted lines: explaining the rule is not offering to stop.
body = re.sub(r"```.*?```", " ", last, flags=re.S)
body = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith(">"))
# Quoted text is a citation, not an offer. Explaining what the rule bans must stay legal,
# or the gate punishes the one message that teaches the rule.
body = re.sub(r"`[^`]*`", " ", body)
body = re.sub(r"[\"“][^\"”]{0,80}[\"”]", " ", body)

# An offer lives at the end. Judge the closing stretch only.
closing = body[-500:]

PROXIES = [
    r"a natural stopping point",
    r"we could leave it here",
    r"want me to keep going\??",
    r"shall i continue\??",
    r"should i continue\??",
    r"do you want me to continue\??",
    r"let me know if you want me to (?:continue|carry on|keep going)",
    r"i can (?:pick this up|resume|continue) (?:later|next session|tomorrow)",
    r"(?:happy to )?(?:pause|stop|close out) here",
    r"or (?:close out|stop) here\??",
]
hit = next((p for p in PROXIES if re.search(p, closing, re.I)), None)
if not hit:
    sys.exit(0)

found = re.search(hit, closing, re.I).group(0)
sys.stderr.write(
    "Blocked: this reply ends by offering to stop.\n\n"
    f"  \"{found}\"\n\n"
    "G31: stopping is not one of the options. State the issue and keep working — the next\n"
    "action is yours to take, not Kamen's to authorize. If you need something only he can\n"
    "give, ask for exactly that and say what proceeds once it is answered.\n\n"
    "Rewrite the ending and send again.\n"
)
sys.exit(2)
PY
