#!/usr/bin/env bash
# Weekly review: produce review candidates without staging or committing repository changes.
# Scheduled via launchd (see SETUP-weekly-review.md). Fail-soft; never errors out the agent.
set -uo pipefail
REPO=/Users/kamenkamenov/memory-knowledge
PY="${CLAUDE_CORPUS_PYTHON:-$REPO/.venv/bin/python}"
# A5: scan the real repo set (Spark + consolidation read MK_SPARK_REPOS). Externally-set value wins.
export MK_SPARK_REPOS="${MK_SPARK_REPOS:-taggable-api,fcsapi,taggable-server,taggable-database,united-partners,agentic-trading,mcp-agents-workflow,memory-knowledge}"
cd "$REPO" || exit 0
TODAY=$(date +%F)
"$PY" working-agreement/weekly_review.py --date "$TODAY" || true
# Promotion, staging, commits, and Tier-2 synchronization remain explicit approval-gated steps.
exit 0
