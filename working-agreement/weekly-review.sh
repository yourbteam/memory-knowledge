#!/usr/bin/env bash
# #7 weekly review: directive Spark + consolidation + bump "Last reviewed" + commit.
# Scheduled via launchd (see SETUP-weekly-review.md). Fail-soft; never errors out the agent.
set -uo pipefail
REPO=/Users/kamenkamenov/memory-knowledge
PY="${CLAUDE_CORPUS_PYTHON:-$REPO/.venv/bin/python}"
cd "$REPO" || exit 0
TODAY=$(date +%F)
"$PY" working-agreement/weekly_review.py --date "$TODAY" || true
# Commit the stamp bump (+ refreshed spark candidates) so the post-commit sync mirrors directives.
if ! git diff --quiet -- working-agreement/DIRECTIVES.md 2>/dev/null; then
  git add working-agreement/DIRECTIVES.md working-agreement/spark-candidates.md 2>/dev/null || true
  git commit -q -m "chore(weekly-review): refresh spark candidates + bump Last reviewed ($TODAY)" || true
fi
exit 0
