#!/usr/bin/env bash
# Injects the working-agreement directives into Claude Code's context on every prompt.
# Registered as a global UserPromptSubmit hook in ~/.claude/settings.json.
#
# Path resolution: override with CLAUDE_DIRECTIVES_PATH, else use the default below.
# On a new machine, set the env var or edit this default to match your repo location.
DIRECTIVES="${CLAUDE_DIRECTIVES_PATH:-/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md}"

# If the file is missing, inject nothing and exit cleanly (never break the prompt).
[ -f "$DIRECTIVES" ] || exit 0

# Emit the documented JSON form so the contents are added to context.
# python3 handles JSON-escaping of arbitrary markdown safely (no jq dependency).
python3 -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":open(sys.argv[1]).read()}}))' "$DIRECTIVES"
