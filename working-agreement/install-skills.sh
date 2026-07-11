#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
"$REPO/working-agreement/validate-skills.sh"
exec python3 "$REPO/working-agreement/install_skills.py" --source "$REPO/skills" --manifest "$REPO/skills/managed-skills.txt" "$@"
