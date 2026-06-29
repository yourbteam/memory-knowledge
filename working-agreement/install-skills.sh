#!/usr/bin/env bash
# Distribute memory-knowledge/skills/* into BOTH Claude and Codex skill dirs (copy model — never deletes
# unrelated skills). Idempotent, prints a sync summary, no secrets. Run once after clone (see SETUP-*.md),
# and it is auto-run by the tracked post-merge hook on every `git pull`.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"          # memory-knowledge repo root
SKILLS_SRC="$REPO/skills"
[ -d "$SKILLS_SRC" ] || { echo "install-skills: no $SKILLS_SRC — nothing to do"; exit 0; }

md5of(){ md5 -q "$1" 2>/dev/null || md5sum "$1" | awk '{print $1}'; }

synced=0
for dest in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  mkdir -p "$dest"
  for s in "$SKILLS_SRC"/*/; do
    [ -d "$s" ] || continue
    name="$(basename "$s")"
    cp -R "${s%/}" "$dest/"          # strip trailing slash so the dir copies AS dest/<name>, not its contents into dest/; add/overwrite this skill only, never deletes others
    echo "  synced $name -> $dest/$name"
    synced=$((synced + 1))
  done
done
echo "install-skills: $synced skill copies updated (Claude + Codex)."

# One-time per machine: activate the tracked post-merge hook so future `git pull` auto-syncs.
git -C "$REPO" config core.hooksPath .githooks && echo "install-skills: core.hooksPath -> .githooks"

# Verify a representative skill round-tripped (no silent miss).
if [ -f "$SKILLS_SRC/sequence-runner/SKILL.md" ]; then
  a=$(md5of "$SKILLS_SRC/sequence-runner/SKILL.md")
  b=$(md5of "$HOME/.claude/skills/sequence-runner/SKILL.md")
  c=$(md5of "$HOME/.codex/skills/sequence-runner/SKILL.md")
  if [ "$a" = "$b" ] && [ "$a" = "$c" ]; then
    echo "install-skills: verify OK — sequence-runner md5 $a in both tools"
  else
    echo "install-skills: VERIFY FAILED (src=$a claude=$b codex=$c)"; exit 1
  fi
fi
