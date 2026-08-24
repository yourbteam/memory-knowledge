#!/usr/bin/env bash
# Claude Code Stop hook for the installed auto-capture package.
VENV_PY="${CLAUDE_CORPUS_PYTHON:-/Users/kamenkamenov/memory-knowledge/.venv/bin/python}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
HELPER="${MK_AUTOCAPTURE_HELPER:-$SCRIPT_DIR/auto_capture.py}"
[ "${MK_AUTOCAPTURE:-0}" = "1" ] || exit 0
[ "${MK_AUTOCAPTURE_NESTED:-0}" = "1" ] && exit 0
[ -x "$VENV_PY" ] || exit 0
[ -f "$HELPER" ] || exit 0
if [ "${MK_AUTOCAPTURE_DRY_RUN:-0}" = "1" ]; then
  PYTHONDONTWRITEBYTECODE=1 MK_CLIENT_KIND="${MK_CLIENT_KIND:-claude}" "$VENV_PY" "$HELPER"
else
  PYTHONDONTWRITEBYTECODE=1 MK_CLIENT_KIND="${MK_CLIENT_KIND:-claude}" "$VENV_PY" "$HELPER" 2>/dev/null
fi
exit 0
