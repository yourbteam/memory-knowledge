# Task: Memory / Directives ↔ Second-Brain Gaps

Close the 8 gaps between our working-agreement directives + Tier-2 corpus approach and Nate B. Jones' Open Brain (OB1) model. Created 2026-06-20.

## Files
- **`analysis.md`** — the gap analysis (8 gaps: our approach vs OB1, with §1 reframed to "DIRECTIVES.md authoritative → all tools projected"). 3-gate hardened.
- **`plan.md`** — the implementation plan to close all 8 gaps. Coverage + satisfaction hardened. §0.1 endpoint **decided: Azure**. No open decisions.
- **`artifacts/`** — hardening audit trails + source research:
  - `analysis.gap-audit.md`, `analysis.coverage-audit.md`, `analysis.satisfaction-audit.md` — the three gates run on the analysis.
  - `plan.coverage-audit.md`, `plan.satisfaction-audit.md` — the two plan-hardening gates.
  - `open-brain-brief.md` — the OB1 research brief that seeded the comparison.

## Filename note
These docs were authored in `~/Downloads` and moved here. Inside the audit files the targets are referenced by their original names:
- `analysis.md` was `our-approach-vs-open-brain-gaps.md`
- `plan.md` was `close-8-gaps-plan.md`

## Status — ALL 8 GAPS CLOSED (2026-06-20)
Research ✅ → Plan ✅ (hardened) → **Implementation ✅ complete.** On `main`, deployed to Azure (`sha-232d57f`); 50 feature tests green.

| Gap | Result | Key commits |
| --- | --- | --- |
| #6 prune clutter | ✅ `list_repositories` hides inactive (filter on `REPO_INACTIVE`); 46 test repos soft-deactivated; live-verified (9 real) | `9a38540`, `00c7953` |
| #5 recency + threshold | ✅ `corpus_query` recency tiebreak + `min_score`; live-verified | `c9e5c93` |
| #8 cite retrieved memory | ✅ injection shows `slug·id` + cite line; live | `c9e5c93` |
| #1 one authoritative source | ✅ G10–G15 locked→brain; home `CLAUDE.md`/`AGENTS.md` demoted to generated pointers; endpoint→Azure; repo-note feature; 9 notes migrated | `ed237f1`, `1b2c2f6`, generator `c98c174` |
| #4 portable read path | ✅ `generate_projections.py` + `SETUP-codex.md` + one endpoint (per-project AGENTS.md = remaining cross-repo tail) | `c98c174` |
| #2 auto-capture | ✅ candidate tier (deployed) + skill (`auto-capture.skill.md`) + opt-in Stop-hook extractor (`auto_capture.py`) | `5588bd1`, `232d57f`, `7fff0ad` |
| #3 directive Spark | ✅ `directive_spark.py` → `spark-candidates.md` (never auto-promotes) | `9a4a89a` |
| #7 review cadence | ✅ `weekly_review.py` + launchd plist + `SETUP-weekly-review.md` | `d2edae7` |

**Repo-note feature** (enabling #1 Bucket B): see sibling task `Tasks/repo-scoped-note-authoring/` (S1–S6 built, deployed `sha-3dee9be`+, migration `028` relaxed evidence cols to nullable).

### Remaining tails (none block the above)
- ~~#2 cosmetic fix `7fff0ad`~~ **DEPLOYED 2026-06-20** (`sha-98b50a4`); `include_inactive` now live (verified: active=9, include_inactive=56).
- ~~#4 per-project `AGENTS.md`~~ **RESOLVED 2026-06-20** across the 8 Codex trusted projects: full-directives `AGENTS.md` generated into 5 clean repos (taggable-database, taggable-api, united-partners, agentic-trading, claude-working-agreement-setup); fenced+idempotent merge appended into the 2 with their own substantive `AGENTS.md` (mcp-agents-workflow 388→591, FCSAPI 40→243, content preserved); memory-knowledge already a correct thin pointer (untouched). New `--append-to` merge mode + tests committed (`591c70e`). **Note:** the 7 sibling-repo files are written to working trees (Codex loads them) but **uncommitted** — commit each in its own repo flow when ready.
- ~~Operator enablement~~ **ACTIVATED 2026-06-20:** #7 plist loaded (`launchctl list` → `com.kamen.memory-weekly-review`); #2 Stop hook wired in `~/.claude/settings.json` + `env.MK_AUTOCAPTURE=1` (verified inherited by hook subprocess); #2 skill installed at `~/.claude/skills/auto-capture/SKILL.md`. **One manual step left:** restart Claude Code so it picks up the new `Stop` hook + `env`.
- 36 Bucket-B notes in non-ingested repos — **not authorized** in the 2026-06-20 sweep. `taggable-backoffice` also hard-blocked (no local clone); `mcp-agents-workflow` + `memory-knowledge` are on disk if you later want them.
- Cleanups: ~~`test_guards.py` env-leak~~ **FIXED 2026-06-20** (boundary fix in test baseline; suite 57/57 green). Still open: 2 test-marker notes in taggable-server brain; 3 redundant taggable-server file-memory files. `tpp-petkey` null ingestion-status diagnosed as benign legacy artifact (no action).
