#!/usr/bin/env bash
# Tier-2 corpus sync: when a commit touches DIRECTIVES.md, mirror the directives into the
# deployed corpus (upsert current + deactivate renamed/deleted orphans). Install as the repo's
# git post-commit hook (see INSTALL.md).
#
# Fail-open: if the commit didn't touch DIRECTIVES.md, or the venv/helper is missing, or
# anything errors, do nothing and exit 0 — never block or delay the commit. The helper
# enforces its own per-call timeout via the MCP client.
#
# Override paths via env: CLAUDE_CORPUS_PYTHON.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Only act when the just-made commit changed the directives file.
CHANGED="$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null)" || exit 0
echo "$CHANGED" | grep -q "^working-agreement/DIRECTIVES.md$" || exit 0

PY="${CLAUDE_CORPUS_PYTHON:-$REPO_ROOT/.venv/bin/python}"
HELPER="$REPO_ROOT/working-agreement/sync_corpus.py"

[ -x "$PY" ] || exit 0
[ -f "$HELPER" ] || exit 0

"$PY" "$HELPER" 2>/dev/null

# WS3: a DIRECTIVES change also refreshes this machine's generated Codex AGENTS.md projections
# (event-driven, replaces the weekly launchd refresh). --refresh-trusted only rewrites files this
# generator produced; never clobbers a repo's own AGENTS.md. Fail-open: never block the commit.
"$PY" "$REPO_ROOT/working-agreement/generate_projections.py" --refresh-trusted 2>/dev/null || true
exit 0
