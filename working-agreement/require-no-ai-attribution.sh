#!/usr/bin/env bash
# PreToolUse gate: refuse a commit whose message carries an AI-attribution line.
#
# Why this exists: G12 bans `Co-Authored-By: Claude` and every other AI-attribution
# trailer, and it has been locked since 2026-06-20. On 2026-08-05 four commits carried
# it anyway, in one session, while the harness default that appends the line was known
# and the rule was in context the whole time.
#
# The command string carries the message whether it arrives through -m or through a
# heredoc piped to -F -, so both are covered by reading the same text.
#
# Contract: stdin is the PreToolUse JSON. Exit 0 allows; exit 2 denies and returns the
# stderr text to the model. Any internal error allows and stays silent, so a defect in
# this gate can never brick a session.
set -uo pipefail

payload="$(cat)" || exit 0

extract() {
  python3 -c 'import json,sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
ti = d.get("tool_input") or {}
sys.stdout.write("%s\n%s" % (d.get("tool_name") or "?", ti.get("command") or ""))
' "$payload" 2>/dev/null
}

tool_name="$(extract | sed -n 1p)"
command_text="$(extract | sed -n '2,$p')"
[ "$tool_name" != "Bash" ] && exit 0

case "$command_text" in
  # scoped_git_publish.py is how this machine actually commits -- the registry names it as
  # the automation for `commit-push-main` -- and it never contains the string "git commit".
  # On 2026-08-06 every commit of the day went through it, so all three of these gates were
  # blind to the path the work really took.
  *"git commit"*|*"git merge"*|*"git revert"*|*"git tag"*|*scoped_git_publish.py*) ;;
  *) exit 0 ;;
esac

# The banned shapes, case-insensitive. Kept explicit rather than a loose "claude" match:
# a commit message may legitimately discuss Claude, the harness, or a file named for it.
# What is banned is the attribution trailer.
offender="$(printf '%s' "$command_text" | grep -iEo \
  'Co-Authored-By:[^\n]*(Claude|Anthropic|GPT|Copilot|AI)|Generated with [^\n]*(Claude|Anthropic|Copilot)|Assisted-By:[^\n]*|🤖[^\n]*' \
  | head -1)"
[ -z "$offender" ] && exit 0

cat >&2 <<MSG
Blocked: this commit message carries an AI-attribution line.

  $offender

G12: no \`Co-Authored-By: Claude\` and no other AI-attribution trailer. It overrides the
harness default that appends one, so the default is what you are removing here.

Rewrite the message without that line and re-issue the call.

On 2026-08-05 four commits carried it in a single session while the rule sat in context.
MSG
exit 2
