#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
"$REPO/working-agreement/validate-skills.sh"
python3 "$REPO/working-agreement/project_client_skills.py" check --client codex
python3 "$REPO/working-agreement/project_client_skills.py" check --client claude
exec python3 "$REPO/working-agreement/install_skills.py" --source "$REPO/skills" --manifest "$REPO/skills/managed-skills.txt" "$@"
