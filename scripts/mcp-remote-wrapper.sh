#!/usr/bin/env bash
# Wrapper for mcp-remote that detects parent (Claude Code) exit and cleans up.
#
# mcp-remote (node) does not listen for stdin 'end' events, so when Claude
# Code exits and closes the stdin pipe, mcp-remote hangs forever. This wrapper
# starts a background PPID watchdog that kills the process group when the
# parent dies, then exec's into npx so stdin/stdout pass through naturally.
set -uo pipefail

# Background watchdog: polls PPID every 2 seconds.
# When the parent exits, PPID changes to 1 (init/launchd).
# $$ in a subshell retains the parent shell's PID, which after exec
# becomes the npx PID — so we monitor the right process.
(
    trap '' TERM  # Survive our own group kill so SIGKILL escalation works
    MY_PGID=$$
    while kill -0 $$ 2>/dev/null; do
        CURRENT_PPID=$(ps -o ppid= -p $$ 2>/dev/null | tr -d ' ')
        if [[ -z "$CURRENT_PPID" || "$CURRENT_PPID" == "1" ]]; then
            kill -TERM -- -$MY_PGID 2>/dev/null || true
            sleep 1
            kill -KILL -- -$MY_PGID 2>/dev/null || true
            exit 0
        fi
        sleep 2
    done
) &

# Replace ourselves with npx — stdin/stdout pass through naturally.
exec npx "$@"
