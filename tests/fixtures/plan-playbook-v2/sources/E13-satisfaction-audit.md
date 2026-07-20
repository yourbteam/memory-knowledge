# Satisfaction Audit — close-8-gaps-plan.md

Plan-playbook Gate B: **requirements-satisfaction-gap-loop** (depth). Does each addressed plan step actually hold against the real runtime (scripts, MCP tools, DB schema, Codex behavior)? Evidence = `memory-knowledge` source/migrations + live tool schemas + Codex config.

---

## Cycle 1 Assessment — End-to-End Trace (blockers extracted)

| req | trace vs real system | holds? |
| --- | --- | --- |
| G5 recency | `memory.corpus_entries` HAS `created_utc`/`updated_utc` (`migrations/versions/027_corpus_schema.py:34-35`) → recency feasible. BUT Qdrant `CorpusEntryPayload` (`src/memory_knowledge/projections/qdrant_payload_schemas.py:47-53`) has **no timestamp field** → not available at vector-rank time | **partial → SGAP-001** |
| G6 prune | `purge_repository` = "Purge all repo-owned data across PostgreSQL, Qdrant, and Neo4j" → **destructive**; `mawf_deactivate_repository` = "Soft-deactivate" (takes `repository_id`, not `repository_key`) | **breaks (plan implied non-destructive default) → SGAP-002** |
| §0.2/§1.1/§1.4 kind | migration 027 CHECK: `kind IN ('directive_rationale','playbook_detail','example','reference')`. Plan §0.2 says "kind is free-form — confirmed" → **false** | **breaks → SGAP-003** |
| G1.2/G4 Codex projection | Codex global `~/.codex/AGENTS.md` does not exist; `~/AGENTS.md` only loads when cwd=~; research doc does not confirm a global AGENTS.md load. Per-project `AGENTS.md` in the repo tree is the reliable load path | **partial (rests on unverified global load) → SGAP-004** |
| G2 Codex auto-capture | Codex exposes only `notify=[...,"turn-ended"]` (per-turn external notification); **no session-end/capture hook** | **partial (assumes a hook that doesn't exist) → SGAP-005** |
| G8 entry_key | `corpus_query` returns `entry_key`/`link_slug` (observed) | holds |
| G1 sync direction | `sync_corpus.py` mirrors file→corpus (confirmed) | holds |
| G3 telemetry | tools repo-scoped; plan now iterates active repo set | holds |

## Blocker Gap Ledger

| gap_id | req | evidence (real system) | fix | status |
| --- | --- | --- | --- | --- |
| SGAP-001 | G5 | timestamps exist in PG (`027:34-35`) but absent from `CorpusEntryPayload` | §5: lock the recency source — add `created_utc`/`updated_utc` to `CorpusEntryPayload` + re-index, **or** post-query PG re-rank; pick the PG re-rank (no re-index) as default | open |
| SGAP-002 | G6 | `purge_repository` destructive; `mawf_deactivate_repository` soft (uses `repository_id`) | §6: default to `mawf_deactivate_repository` (soft); `purge_repository` only with explicit per-repo confirmation; note id-vs-key arg | open |
| SGAP-003 | §0.2/§1.4 | CHECK constrains `kind` to 4 values (`027`) | §0.2: correct "free-form" → enum {directive_rationale, playbook_detail, example, reference}; §1.4: map file-memory types onto these (or migrate the CHECK) | open |
| SGAP-004 | G1.2/G4 | no confirmed global Codex AGENTS.md load | §1.2/§4: generate **per-project `AGENTS.md`** in each in-scope repo (reliable); `~/.codex/AGENTS.md` only if global load is verified first | open |
| SGAP-005 | G2 | Codex has only `notify=turn-ended`, no session hook | §2: scope auto-capture to Claude Code `Stop` hook (exists); Codex = best-effort via the `notify` turn-ended program, else documented known-limitation/follow-up | open |

## Cycle 1 Plan (gap-to-fix)
SGAP-001→§5; SGAP-002→§6; SGAP-003→§0.2+§1.4; SGAP-004→§1.2+§4; SGAP-005→§2. Plan accepted; applying.

---

## Cycle 1 Edits
- SGAP-001 → §5: recency source locked to PG re-rank on `updated_utc` (no Qdrant re-index); +X-TEST/X-DEPLOY acceptance.
- SGAP-002 → §6: default `mawf_deactivate_repository` (soft, `repository_id`); `purge_repository` flagged destructive, confirmation-only.
- SGAP-003 → §0.2 + §1.4: corrected "free-form" → CHECK enum {directive_rationale, playbook_detail, example, reference}; file-memory type mapping locked.
- SGAP-004 → §1.2: per-project `AGENTS.md` (reliable) not unverified global.
- SGAP-005 → §2: Claude `Stop` hook primary; Codex best-effort via `notify=turn-ended` / documented follow-up.

## Cycle 1 Validation
- grep confirms each fix present; unresolved-term scan (incl. the old "confirm which") → none.
- Post-edit new-gap pass: §5 PG re-rank introduces a PG read per query — acceptable (corpus is small, already PG-backed); no new interop break. §6 id-vs-key resolved in text. §1.4 kind-mapping consistent with §0.2 enum. No new blocker.

## Cycle 2 Assessment (fresh depth pass, no edits)
| req | holds end-to-end? | evidence |
| --- | --- | --- |
| G5 | yes — `updated_utc` exists; PG re-rank avoids the payload gap | `027:34-35` |
| G6 | yes — soft-deactivate default; destructive tool fenced | tool descs |
| §0.2/§1.4 kind | yes — enum honored; mapping + migration path stated | `027` CHECK |
| G1.2/G4 | yes — per-project AGENTS.md is load-guaranteed | Codex load behavior |
| G2 | yes — Claude Stop exists; Codex scoped honestly | `~/.codex/config.toml` |
| G1/G3/G8 | yes (held in cycle 1) | sync_corpus.py / telemetry / corpus_query |

Blocker satisfaction gaps in Cycle 2: **0**. SGAP-001…005 all closed.

## Final Convergence Check
**Depth convergence: reached.** Every addressed requirement now holds against the real schema (`corpus_entries` columns + `kind` CHECK), the real tools (`mawf_deactivate_repository` vs `purge_repository`), and the real client behavior (Claude `Stop` hook; Codex `notify`/per-project `AGENTS.md`). The plan no longer rests on any unverified premise. **Only open item remains the §0.1 endpoint decision (Kamen).**
