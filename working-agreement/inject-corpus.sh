#!/usr/bin/env bash
# Tier-2 corpus hydration: query the deployed corpus with the user's prompt and inject the
# top relevant entries into Claude Code's context. Registered as a global UserPromptSubmit
# hook in ~/.claude/settings.json, alongside inject-directives.sh.
#
# Fail-open: if the venv/helper is missing or anything errors, inject nothing and exit 0 —
# never block or break the prompt. The helper enforces its own timeout.
#
# Override paths via env: CLAUDE_CORPUS_PYTHON, CLAUDE_CORPUS_HELPER.
VENV_PY="${CLAUDE_CORPUS_PYTHON:-/Users/kamenkamenov/memory-knowledge/.venv/bin/python}"
HELPER="${CLAUDE_CORPUS_HELPER:-/Users/kamenkamenov/memory-knowledge/working-agreement/hydrate_corpus.py}"

[ -x "$VENV_PY" ] || exit 0
[ -f "$HELPER" ] || exit 0

# stdin (the hook's JSON) is inherited by the child; suppress errors; always exit 0.
"$VENV_PY" "$HELPER" 2>/dev/null
exit 0
