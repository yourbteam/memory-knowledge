#!/usr/bin/env bash
# PreToolUse gate: refuse an edit that introduces a refusal whose whole message is a
# rule name.
#
# Why this exists: G33, locked 2026-08-03. On 2026-08-05 a refusal reading only
# `owner_question_manifest_invalid:4` was returned three times to a live run, which then
# died at phase 55 of 74 — the model had nothing in the message to act on. The same file
# held eighty-five more of the same shape. The rule was in context the whole time.
#
# What it checks: a new `raise <Something>Error("token")` whose message string carries no
# space is a rule name and nothing else. A refusal that says what came back and what would
# satisfy it always contains prose, so it always contains a space.
#
# Contract: stdin is the PreToolUse JSON. Exit 0 allows; exit 2 denies and returns the
# stderr text to the model. Any internal error allows and stays silent, so a defect in
# this gate can never brick a session.
set -uo pipefail

payload="$(cat)" || exit 0

python3 - "$payload" <<'PY'
import json, re, sys

try:
    d = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

if (d.get("tool_name") or "") not in ("Edit", "Write", "NotebookEdit"):
    sys.exit(0)

ti = d.get("tool_input") or {}
path = str(ti.get("file_path") or "")
if not path.endswith(".py"):
    sys.exit(0)

added = str(ti.get("new_string") or ti.get("content") or ti.get("new_source") or "")
if not added:
    sys.exit(0)

# A refusal message that is one token: no space anywhere inside the quotes. Colons and
# braces are how these are usually built, so "rule:4" and f"rule:{index}" both qualify.
pattern = re.compile(r'raise\s+\w*(?:Error|Exception)\(\s*f?(["\'])([^"\']*)\1\s*\)')
offenders = [m.group(2) for m in pattern.finditer(added) if " " not in m.group(2)]
if not offenders:
    sys.exit(0)

shown = "\n  ".join(sorted(set(offenders))[:5])
sys.stderr.write(
    "Blocked: this edit adds a refusal whose whole message is a rule name.\n\n"
    f"  {shown}\n\n"
    "G33: a refusal states, in the same string, which item failed, what came back, and\n"
    "what would satisfy the rule instead. The model that reads it has no access to the\n"
    "code that raised it.\n\n"
    "  raise ValueError(f\"{where}: guide_grounding has {n} entries, want at least 2 -- \"\n"
    "                   \"one per option the question offers.\")\n\n"
    "On 2026-08-05 `owner_question_manifest_invalid:4` was returned three times to a live\n"
    "run and killed it at phase 55 of 74.\n\n"
    "Rewrite the message and re-issue the edit.\n"
)
sys.exit(2)
PY
