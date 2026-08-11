#!/usr/bin/env bash
# Stop gate: a change to what counts as evidence must be proven on the verdict, not the mechanism.
#
# Why this exists (G28, amended 2026-08-06): a change that dropped an unusable check after two
# failed rewrites was proven by two tests, both asserting the mechanism — that the check is
# rewritten twice and then dropped. Both passed and both were true. Nobody asked what the
# requirement's verdict becomes when a check disappears, and live that same hour a requirement
# whose fourth check had been dropped read PROVEN on its remaining three. Kamen: "i cannot tolerate
# more of 'my change' caused this."
#
# What it checks, mechanically: when the prover's verdict-bearing code has uncommitted changes, the
# prover's test file must contain at least one assertion about the ANSWER — proven, failed,
# inconclusive, or a standing count — and not only about the machinery that produces it.
#
# Contract: stdin is the Stop JSON. Exit 0 lets the turn end; exit 2 blocks it. Any internal error
# lets the turn end — a defect here must never trap a session.
set -uo pipefail

cat >/dev/null || true

REPO="/Users/kamenkamenov/mcp-agents-workflow"
MODULE="src/workflow_orch/greenfield_requirement_prover.py"
TESTS="tests/test_greenfield_requirement_prover.py"

[ -d "$REPO/.git" ] || exit 0

# Only fire inside the repository this rule is about. The gate is installed globally, so without
# this it ends every session on the machine whenever that one file is dirty — and on 2026-08-11 it
# did: a session working on united-partners was blocked four times running by uncommitted greenfield
# work it had never touched, with no way to reach anybody, which is the one thing the header above
# says must never happen. The rule itself is unchanged; it now applies where its subject lives.
case "$PWD/" in
  "$REPO"/*) : ;;
  *) exit 0 ;;
esac

# Only fire when the verdict-bearing module is actually dirty. A clean tree has nothing to prove.
changed="$(cd "$REPO" && git diff --name-only -- "$MODULE" 2>/dev/null)" || exit 0
[ -n "$changed" ] || exit 0

# Did the uncommitted diff touch the lines that DECIDE anything? These are the names a verdict is
# made of. A change elsewhere in the file — a comment, a prompt, a trace line — is not this rule's
# business.
deciding="$(cd "$REPO" && git diff -U0 -- "$MODULE" 2>/dev/null |
  grep -E '^\+' | grep -Ec 'proven|standing|demote|struck|dropped_now|have\[')" || deciding=0
[ "$deciding" -gt 0 ] || exit 0

# The proof must name the answer, and it must be THIS delta's proof. Counting verdict assertions
# anywhere in the file passes on tests written months ago: the first version of this gate did
# exactly that and allowed the very tree whose defect it was built for, because older tests already
# asserted on proven. Only lines this change ADDED to the test file count.
verdict_tests="$(cd "$REPO" && git diff -U0 -- "$TESTS" 2>/dev/null |
  grep -E '^\+' | grep -Ec 'assert .*\.(proven|failed|inconclusive)|standing\[|\["proven"\]')" || verdict_tests=0

[ "$verdict_tests" -gt 0 ] && exit 0

cat >&2 <<'MSG'
Blocked: the prover's verdict code changed, and no test asserts what the system now concludes.

Every test in the prover's test file describes the machinery — what the new code does. None names
the answer that comes out of it: whether a requirement reads proven, failed, or unjudged after this
change, exercised both ways.

Add a test that pins the verdict across this delta, then send again. If the change genuinely cannot
alter any verdict, say that in one clause and name what makes it impossible.
MSG
exit 2
