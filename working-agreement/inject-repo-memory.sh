#!/usr/bin/env bash
# Repo-scoped memory hydration: query the deployed brain with the prompt + cwd and inject
# the repo's notes into Claude Code's context. Fail-open: exit 0 on any error.
VENV_PY="${CLAUDE_REPO_HYDRATE_PYTHON:-/Users/kamenkamenov/memory-knowledge/.venv/bin/python}"
HELPER="${CLAUDE_REPO_HYDRATE_HELPER:-/Users/kamenkamenov/memory-knowledge/working-agreement/hydrate_repo_memory.py}"
[ -x "$VENV_PY" ] || exit 0
[ -f "$HELPER" ] || exit 0
"$VENV_PY" "$HELPER" 2>/dev/null
exit 0
