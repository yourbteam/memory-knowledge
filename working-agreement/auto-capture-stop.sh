#!/usr/bin/env bash
# Claude Code `Stop` hook: automatic session-close auto-capture (#2 option 1).
# Opt-in via MK_AUTOCAPTURE=1. Fail-open: never block or delay session end.
VENV_PY="${CLAUDE_CORPUS_PYTHON:-/Users/kamenkamenov/memory-knowledge/.venv/bin/python}"
HELPER="${MK_AUTOCAPTURE_HELPER:-/Users/kamenkamenov/memory-knowledge/working-agreement/auto_capture.py}"
[ "${MK_AUTOCAPTURE:-0}" = "1" ] || exit 0
[ -x "$VENV_PY" ] || exit 0
[ -f "$HELPER" ] || exit 0
"$VENV_PY" "$HELPER" 2>/dev/null
exit 0
