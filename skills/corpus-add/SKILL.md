---
name: corpus-add
description: This skill should be used when Kamen wants to persist a piece of durable working-agreement knowledge into the Tier-2 corpus for later semantic retrieval — a directive's rationale, a playbook detail, a worked example, or a reference. It curates one entry on demand via the deployed memory-knowledge MCP. Do not use it for one-off conversation notes or for bulk loading (that is the backfill script).
---

# Skill: corpus-add

Add one entry to the Tier-2 working-agreement corpus (`memory.corpus_entries`) so it can be
retrieved later by semantic search.

## Runtime requirement

Needs the **memory-knowledge MCP** connected — the tool `mcp__memory-knowledge__run_corpus_upsert_workflow`.
If that tool is **not available in this session**, STOP and tell Kamen the corpus can't be reached
from here (the connection is per-session). Do **not** substitute a direct DB/Qdrant write or any
other workaround — that violates G4. Offer to run it in an MCP-connected session instead.

## Steps

1. **Assemble the entry** with Kamen:
   - `kind` — exactly one of: `directive_rationale` · `playbook_detail` · `example` · `reference`
   - `title` — short label
   - `body_text` — the content to embed and later retrieve (write it to read well out of context)
   - `link_slug` — the directive/playbook it supports (e.g. `g2`, `research-playbook`); omit if none
   - `tags` — optional array of strings
2. **Show Kamen the assembled entry and get confirmation before writing** — this is a production write.
3. Call `run_corpus_upsert_workflow` with those fields. Report `status` and the returned `entry_key`.
4. **Optional check:** `corpus_query` for the entry to confirm it's retrievable.

## Notes

- **Idempotent:** `entry_key` is derived from `(kind, link_slug, title)`, so re-adding the same
  logical entry updates it in place rather than duplicating. Changing the `title` creates a new
  entry — to retire an old one, pass `supersedes_id`.
- This is the curate-one-at-a-time path; the directives were seeded separately via
  `memory-knowledge/scripts/backfill_corpus.py`.
