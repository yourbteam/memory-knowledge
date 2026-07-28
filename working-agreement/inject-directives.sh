#!/usr/bin/env bash
# Injects the working-agreement directives into Claude Code's context on every prompt.
# Registered as a global UserPromptSubmit hook in ~/.claude/settings.json.
#
# WHY THIS DOES NOT SEND THE WHOLE FILE
#   The harness caps how much hook output it places inline. Anything larger is written to a
#   file and replaced with a ~2KB preview. A whole-file inject (55KB) therefore delivered only
#   the first ~4% of the agreement, every prompt, silently. The cut landed one line before the
#   sentence in G0 that defines the anchor format — so the anchor was approximated in prose
#   instead of followed, and the controller/envelope fields that gate Write-code work never
#   appeared. Observed sizes: 53.4KB persisted, 10.2KB persisted, ~5.5KB delivered inline.
#   The default budget below sits under the lowest observed persist size.
#
# WHAT IS SENT
#   Verbatim and complete: the header, prime directive, task-mode router, and G0 — the routing
#   and self-check machinery needed on every turn. Then the verbatim title line of every rule,
#   so the full set is always known and any body can be read on demand.
#   No rule text is summarised, paraphrased, or rewritten. Kamen authors the agreement; this
#   script only selects and transmits.
#
# CONFIGURATION
#   CLAUDE_DIRECTIVES_PATH    path to DIRECTIVES.md (default below)
#   CLAUDE_DIRECTIVES_BUDGET  max content bytes to inject; 0 = send the whole file
DIRECTIVES="${CLAUDE_DIRECTIVES_PATH:-/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md}"
BUDGET="${CLAUDE_DIRECTIVES_BUDGET:-9000}"

# If the file is missing, inject nothing and exit cleanly (never break the prompt).
[ -f "$DIRECTIVES" ] || exit 0

DIRECTIVES="$DIRECTIVES" BUDGET="$BUDGET" python3 <<'PY'
import json, os, re, sys

path = os.environ["DIRECTIVES"]
try:
    budget = int(os.environ.get("BUDGET") or 0)
except ValueError:
    budget = 9000

try:
    text = open(path, encoding="utf-8").read()
except OSError:
    sys.exit(0)


def emit(body):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": body,
    }}))
    sys.exit(0)


# Budget disabled: send the file as-is (correct for a harness with no inline cap).
if budget <= 0:
    emit(text)

headings = list(re.finditer(r"(?m)^## .+$", text))
rule_titles = [m.group(0) for m in headings if re.match(r"^## G\d+ ", m.group(0))]

# Core = everything through the end of the G0 section: header, prime directive, router, G0.
core = text
for i, m in enumerate(headings):
    if m.group(0).startswith("## G0 "):
        core = text[: headings[i + 1].start()] if i + 1 < len(headings) else text
        break

note = (
    "\n<!-- delivery note from inject-directives.sh - not part of the agreement -->\n"
    "The harness caps inline hook output, so the full agreement is NOT in this message.\n"
    "Everything above this note is verbatim and complete.\n"
    "Below is the verbatim title of every rule. A rule whose body is not in context must be\n"
    "read from the file before it is relied on, cited, or claimed to be followed:\n"
    f"  {path}\n"
)

index = (
    "\n## Rule index (titles only - read the file for any body)\n"
    + "\n".join(rule_titles)
    + "\n"
)

payload = core + note + index
if len(payload.encode("utf-8")) > budget:
    payload = core + note + "\n(Rule index omitted: over the inline budget. Read the file.)\n"

size = len(payload.encode("utf-8"))
payload += f"\n<!-- injected {size} content bytes; budget {budget}; rules in file: {len(rule_titles)} -->\n"
emit(payload)
PY
