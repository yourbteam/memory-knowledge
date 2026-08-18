#!/usr/bin/env bash
# PreToolUse gate: refuse tool calls until the canonical directives have been read
# in this session, at their current content.
#
# Why this exists: the UserPromptSubmit hook can only inject G0 in full — everything
# else arrives as a title, with a note saying the body must be read from the file.
# Nothing enforced that. The G0 anchor names the artifact, but writing a filename is
# not reading a file, and no mechanism stopped a command from running first. On
# 2026-07-28 that gap let a commit-and-push run without consulting G18, which says to
# check the sequence registry first — where the right sequence already existed.
#
# Contract: stdin is the PreToolUse JSON. Exit 0 allows; exit 2 denies and returns the
# stderr text to the model. An unexpected internal error allows and warns, so a defect
# in this gate can never brick a session.
set -uo pipefail

DIRECTIVES="${MK_DIRECTIVES_PATH:-/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md}"
STATE_DIR="${MK_DIRECTIVE_READ_STATE_DIR:-/private/tmp/directive-read-state}"
MAX_AGE_SECONDS="${MK_DIRECTIVE_READ_MAX_AGE:-10800}"   # 3h; a long session re-reads

payload="$(cat)" || exit 0

# A helper run has no channel to Kamen, so a gate written about him cannot be satisfied from
# inside one. That includes a worker the implementation machinery starts as its own process:
# on 2026-08-16 an r19 builder spent 11.4 minutes blocked here and delivered nothing. Stand
# down there; see is-helper-transcript.sh.
printf '%s' "$payload" | "$(dirname "$0")/is-helper-transcript.sh" && exit 0

read -r tool_name file_path session_id <<EOF
$(python3 - "$payload" <<'PY' 2>/dev/null || echo "? ? ?"
import json, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    print("? ? ?"); raise SystemExit
ti = d.get("tool_input") or {}
print(
    d.get("tool_name") or "?",
    ti.get("file_path") or ti.get("notebook_path") or "-",
    d.get("session_id") or "-",
)
PY
)
EOF

[ "$tool_name" = "?" ] && exit 0

canonical_hash="$(shasum -a 256 "$DIRECTIVES" 2>/dev/null | cut -d' ' -f1)"
[ -z "$canonical_hash" ] && exit 0        # no directives file: nothing to enforce

receipt="$STATE_DIR/$session_id"

# Reading the directives themselves is always allowed, and records the receipt.
if [ "$tool_name" = "Read" ] && [ "$file_path" = "$DIRECTIVES" ]; then
  mkdir -p "$STATE_DIR" 2>/dev/null
  printf '%s\n' "$canonical_hash" > "$receipt" 2>/dev/null
  exit 0
fi

if [ -f "$receipt" ]; then
  recorded="$(cat "$receipt" 2>/dev/null)"
  now="$(date +%s)"
  changed="$(date -r "$receipt" +%s 2>/dev/null || echo 0)"
  age=$(( now - changed ))
  if [ "$recorded" = "$canonical_hash" ] && [ "$age" -lt "$MAX_AGE_SECONDS" ]; then
    exit 0
  fi
  reason="the directives have changed or the read has aged out"
else
  reason="the directives have not been read in this session"
fi

cat >&2 <<MSG
Blocked: $reason.

Read $DIRECTIVES in full before running anything else. The hook that delivers your
context sends rule titles only; the bodies are in that file. Writing the filename in
the anchor is not reading it.

Then re-issue this $tool_name call.
MSG
exit 2
