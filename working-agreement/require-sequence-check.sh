#!/usr/bin/env bash
# PreToolUse gate: refuse a governed operational command until the sequence registry
# has been consulted in this session.
#
# Why this exists: G18 says grep SEQUENCES.md for a match FIRST, even when it feels
# like a one-off. On 2026-08-05 thirty-six commits ran across two repositories without
# one registry check, and the last of them staged fifteen files nobody had asked for --
# in a repository where `commit-push-main` is registered and its whole stated guarantee
# is "unrelated unstaged work remains untouched". The rule was text. Text lost.
#
# Kamen, same day: "why do you have directives that do not have hooks. how in any
# universe this makes any sense at all."
#
# Contract: stdin is the PreToolUse JSON. Exit 0 allows; exit 2 denies and returns the
# stderr text to the model. Any internal error allows and stays silent, so a defect in
# this gate can never brick a session.
set -uo pipefail

SEQUENCES="${MK_SEQUENCES_PATH:-/Users/kamenkamenov/memory-knowledge/operations/sequences/SEQUENCES.md}"
STATE_DIR="${MK_SEQUENCE_CHECK_STATE_DIR:-/private/tmp/sequence-check-state}"
MAX_AGE_SECONDS="${MK_SEQUENCE_CHECK_MAX_AGE:-10800}"   # 3h; a long session re-checks

payload="$(cat)" || exit 0

read -r tool_name session_id <<EOF
$(python3 - "$payload" <<'PY' 2>/dev/null || echo "? ?"
import json, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    print("? ?"); raise SystemExit
print(d.get("tool_name") or "?", d.get("session_id") or "-")
PY
)
EOF
[ "$tool_name" = "?" ] && exit 0

extract_command() {
  python3 -c 'import json,sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
ti = d.get("tool_input") or {}
sys.stdout.write(str(ti.get("command") or ti.get("file_path") or ""))
' "$payload" 2>/dev/null
}
command_text="$(extract_command)"

receipt="$STATE_DIR/$session_id"
canonical_hash="$(shasum -a 256 "$SEQUENCES" 2>/dev/null | cut -d' ' -f1)"
[ -z "$canonical_hash" ] && exit 0        # no registry: nothing to enforce

# Consulting the registry is always allowed, and records the receipt. Reading it with
# the Read tool, grepping it, or driving it through sequence-runner all count.
case "$command_text" in
  *SEQUENCES.md*|*sequence_guard.py*|*work_memory.py*|*sequence_intake_launch.py*)
    mkdir -p "$STATE_DIR" 2>/dev/null
    printf '%s\n' "$canonical_hash" > "$receipt" 2>/dev/null
    exit 0
    ;;
esac

# What G18 calls governed: it changes something outside this working tree, or it drives
# a workflow. Read-only git, tests, and local edits are the fast path and never gated.
governed=""
case "$command_text" in
  # scoped_git_publish.py is how this machine actually commits -- the registry names it as
  # the automation for `commit-push-main` -- and it never contains the string "git commit".
  # On 2026-08-06 every commit of the day went through it, so all three of these gates were
  # blind to the path the work really took.
  *"git commit"*|*"git push"*|*"git merge"*|*"git rebase"*|*"git reset --hard"*|*scoped_git_publish.py*) governed="a git publish" ;;
  *"docker build"*|*"docker run"*|*"docker compose"*|*"docker-compose"*) governed="a container operation" ;;
  *"start_strategy_run.py"*|*"resume_workflow_phase.py"*|*"run_client_regeneration.py"*|*"run_cd_s_002_upgrade_canary.py"*) governed="a workflow drive" ;;
  *"pip install"*|*"uv pip install"*|*"npm install"*|*"brew install"*) governed="a package install" ;;
  *"rm -rf"*) governed="a destructive cleanup" ;;
esac
[ -z "$governed" ] && exit 0

if [ -f "$receipt" ]; then
  recorded="$(cat "$receipt" 2>/dev/null)"
  now="$(date +%s)"
  changed="$(date -r "$receipt" +%s 2>/dev/null || echo 0)"
  age=$(( now - changed ))
  if [ "$recorded" = "$canonical_hash" ] && [ "$age" -lt "$MAX_AGE_SECONDS" ]; then
    exit 0
  fi
  reason="the registry has changed or the check has aged out"
else
  reason="the sequence registry has not been consulted in this session"
fi

cat >&2 <<MSG
Blocked: this is $governed, and $reason.

G18: grep SEQUENCES.md for a match FIRST, even when it feels like a one-off.

  grep -in "<what you are about to do>" $SEQUENCES

If a sequence matches, follow its sequence.md and its script instead of hand-running
equivalent commands. If none matches, say "no match -> discovery log" in your anchor
before the first command.

On 2026-08-05 thirty-six commits ran without this check. The last one staged fifteen
files nobody asked for, in the repository where commit-push-main is registered and
guarantees exactly that unrelated work stays untouched.

Then re-issue this $tool_name call.
MSG
exit 2
