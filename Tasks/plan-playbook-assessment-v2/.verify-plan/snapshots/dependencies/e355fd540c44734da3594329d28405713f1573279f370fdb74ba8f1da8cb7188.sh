#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$REPO/working-agreement/validate_skills.py" --skills-root "$REPO/skills" --manifest "$REPO/skills/managed-skills.txt" "$@"
