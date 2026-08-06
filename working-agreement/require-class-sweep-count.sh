#!/usr/bin/env bash
# PreToolUse gate: refuse a defect-fix commit that does not state how many instances of
# the class were found and how many were fixed.
#
# Why this exists: G35, locked 2026-08-05. Commit 29a0ad6 fixed one refusal in
# platform_decisions.py that said only its rule's name and left eighty-five siblings in
# the same file. Two hours later one of those siblings refused a live run three times
# and killed it at phase 55 of 74. The rule was locked as text within the hour and had
# no hook, which is the same failure one level up.
#
# What it checks: a commit whose own message describes fixing something must carry
# "<N> found, <M> fixed". Writing that number forces the search; not writing it is what
# let a subset ship as if it were the whole class.
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
  *"git commit"*|*scoped_git_publish.py*) ;;
  *) exit 0 ;;
esac

# Does this commit describe fixing a defect? Read the author's own words rather than the
# diff: a commit that calls itself a fix is claiming to have closed something.
if ! printf '%s' "$command_text" | grep -qiE '\b(fix|fixed|fixes|defect|bug|broke|broken|refus|reject|wrong|invalid|stale|killed|crash|regression)'; then
  exit 0
fi

# Already carries the count?
if printf '%s' "$command_text" | grep -qiE '[0-9]+ found[^0-9]{0,20}[0-9]+ fixed'; then
  exit 0
fi

cat >&2 <<'MSG'
Blocked: this commit describes fixing something and does not state the class count.

G35: sweep the same defect class in the same file in the same commit, and say how many.
The message must contain both numbers, in this shape:

  3 found, 3 fixed

"1 found, 1 fixed" is a legitimate and common answer — write it. If the class is larger
than this commit fixes, do not fix a subset: state the number and stop for Kamen.

Search the file for the same shape before you commit. On 2026-08-05 a commit that fixed
one refusal left eighty-five siblings in the same file, and one of them killed a live
run two hours later.
MSG
exit 2
