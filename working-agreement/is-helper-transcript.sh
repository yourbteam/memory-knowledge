#!/usr/bin/env bash
# Answer one question for the gates: is this transcript a helper run rather than the
# conversation with Kamen?
#
# Why this exists: every gate in this directory is written about Kamen — what he last
# heard, what he was told, what he approved. A helper run has no channel to him; its text
# goes to the agent that spawned it. So a gate keyed to "time since Kamen heard anything"
# can never be satisfied from inside one, and it hard-blocks every tool call the helper
# tries to make. That happened twice on 2026-08-07: two helper runs producing real
# findings were frozen mid-work, one of them losing an unwritten document. The working
# agreement's own standard for proving a rule is two helper runs, one with the rule and
# one without — so the gates were making that standard unreachable.
#
# The discriminator is `agent_id` in the hook payload: present and non-empty when the call
# comes from a helper, absent otherwise. Measured on 2026-08-07 by logging every payload the
# gates received across one probe: three helper calls all carried `agent_id` and `agent_type`,
# and all fourteen of the main conversation's calls carried neither.
#
# The first attempt looked for `isSidechain` inside the transcript file. That marker is real
# and it is in the helper's own transcript — but the payload's `transcript_path` is ALWAYS the
# main conversation's file, in a helper as much as anywhere else, so the check could never fire
# and the next helper was frozen exactly as before. Proving a discriminator against a file on
# disk proved nothing about the input it actually receives.
#
# A second kind of helper arrived later and `agent_id` says nothing about it: a worker the
# implementation machinery starts as its own `claude -p` process. It is its own main conversation,
# so no payload field marks it — but its launcher controls its environment, and on 2026-08-16 an
# r19 builder spent 11.4 minutes blocked by these gates and delivered nothing, which is the same
# failure the `agent_id` check was written for. So the launcher states what its workers are, in
# `WORKING_AGREEMENT_HELPER`, and that is the discriminator for anything the payload cannot mark.
# It is set by the machinery, never by a worker: a worker inherits it and cannot grant it to
# itself, and the machinery's own gates still decide everything about the work it produces.
#
# Contract: the PreToolUse/Stop JSON arrives on stdin. Exit 0 when the call comes from a helper
# (the caller should stand down), 1 otherwise. Any error exits 1, so a defect here can only
# leave the gates as strict as they were, never looser.
set -uo pipefail

payload="$(cat)" || exit 1

if [ -n "${WORKING_AGREEMENT_HELPER:-}" ]; then
  exit 0
fi

python3 - "$payload" <<'PY'
import json, sys

try:
    event = json.loads(sys.argv[1])
except Exception:
    sys.exit(1)

agent = event.get("agent_id")
sys.exit(0 if isinstance(agent, str) and agent.strip() else 1)
PY
