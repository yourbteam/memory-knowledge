#!/usr/bin/env bash
# #7 weekly review: directive Spark + consolidation + bump "Last reviewed" + commit.
# Scheduled via launchd (see SETUP-weekly-review.md). Fail-soft; never errors out the agent.
set -uo pipefail
REPO=/Users/kamenkamenov/memory-knowledge
PY="${CLAUDE_CORPUS_PYTHON:-$REPO/.venv/bin/python}"
# A5: scan the real repo set (Spark + consolidation read MK_SPARK_REPOS). Externally-set value wins.
export MK_SPARK_REPOS="${MK_SPARK_REPOS:-taggable-api,fcsapi,taggable-server,taggable-database,united-partners,agentic-trading,mcp-agents-workflow,memory-knowledge}"
cd "$REPO" || exit 0
TODAY=$(date +%F)
"$PY" working-agreement/weekly_review.py --date "$TODAY" || true
# Commit the stamp bump (+ refreshed spark candidates) so the post-commit sync mirrors directives.
if ! git diff --quiet -- working-agreement/DIRECTIVES.md 2>/dev/null; then
  git add working-agreement/DIRECTIVES.md working-agreement/spark-candidates.md 2>/dev/null || true
  git commit -q -m "chore(weekly-review): refresh spark candidates + bump Last reviewed ($TODAY)" || true
fi
exit 0
