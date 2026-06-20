# Satisfaction Audit — our-approach-vs-open-brain-gaps.md

Gate 3 of the research-playbook pipeline: **requirements-satisfaction-gap-loop** (depth).
Question: do the doc's proposed improvements actually *hold* against the **live** `memory-knowledge` MCP, its real tool surface, and stored data — not just against the document? Evidence = live tool schemas + observed `corpus_query` output.

---

## Cycle 1 Assessment

### Requirement Inventory (addressed improvements under depth test)

| req_id | claim in doc | type | source |
| --- | --- | --- | --- |
| D1 | §5: corpus retrieval is similarity-only; lacks recency + threshold | stated | doc §5 |
| D2 | §8: `entry_key`/`link_slug` exist and are usable for citation | stated | doc §8 |
| D3 | §1: corpus could serve as the single store; four stores are parallel truths | implied-essential | doc §1 |
| D4 | disposition: dedup-via-supersede exists | stated | disposition table |
| D5 | disposition: export/import covers our memory | stated | disposition table |
| D6 | disposition: model-swap via `run_embedding_backfill` re-embed | stated | disposition table |
| D7 | §2: learned-memory proposal is repo-scoped (vs global corpus) | stated | doc §2 |

### End-to-End Trace Table (against live tool surface)

| req_id | trace | runtime evidence | holds? |
| --- | --- | --- | --- |
| D1 | query → `corpus_query` → ranked results | `corpus_query` schema params = `query_text`, `limit` (default 5), `kind`, `link_slug` — **no recency, no threshold**; observed output ordered by descending `score` (0.62→0.52). Repo path `run_retrieval_workflow`/`run_context_assembly_workflow` expose only `query`+`repository_key` (no recency) | **holds (gap real)** — confirmed similarity-only at tool surface |
| D2 | result → cite source | observed `corpus_query` output includes `entry_key` (UUID) + `link_slug` per result | **holds** — handles real |
| D3 | unify stores | `run_corpus_upsert_workflow.kind` is a free string (no enum) → can hold arbitrary kinds; **but** `corpus_deactivate` desc: "used by the **directives sync** to prune orphans" → directives↔corpus already synced | **partial** — feasible, but §1 overstates independence → SGAP-002 |
| D4 | supersede/prune | `corpus_deactivate` ("soft-delete … idempotent; PG + Qdrant") + `run_corpus_upsert_workflow.supersedes_id` | **holds** |
| D5 | export memory | `export_repo_memory_tool` desc: "Export **repository** memory as JSONL" — requires `repository_key` (repo-scoped) | **breaks** — does NOT export the global corpus → SGAP-003 |
| D6 | re-embed on model change | `run_embedding_backfill` desc: "Backfill **missing** Qdrant embeddings from PG canonical" — requires `repository_key` (repo-scoped, missing-only) | **breaks** — not a global-corpus full re-embed → SGAP-004 |
| D7 | repo-scoped learned memory | `run_learned_memory_proposal_workflow` requires `repository_key` | **holds** |

### Lens Coverage Matrix (key lenses)

| req_id | lens | status | evidence |
| --- | --- | --- | --- |
| D1 | data-reality / config dependence | checked | no threshold/recency knob at tool surface |
| D2 | producer/consumer symmetry | checked | retrieval returns the citation handle the fix needs |
| D3 | intent vs mechanism | gap found | §1 intent (unify) partly already met by directives-sync → SGAP-002 |
| D5 | scope-vs-usage reality | gap found | export tool scoped to repos, not corpus → SGAP-003 |
| D6 | scope-vs-usage reality | gap found | backfill repo-scoped + missing-only → SGAP-004 |
| D2,D4,D7 | end-to-end trace | checked | tools resolve as claimed |

### Blocker Gap Ledger

| gap_id | severity | req_id | lens | evidence (both sides) | why it breaks | planned fix | closure | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SGAP-001 | blocker | D1 | data-reality | `corpus_query` has no recency/threshold param (schema); doc §5 left it `[VERIFY]` | An unresolved premise can't pass a depth gate; must resolve to confirmed/▢ | Update §5: remove `[VERIFY]`; state confirmed-at-tool-surface (only `limit`/`kind`/`link_slug`; no threshold either), with the honest caveat that internal ranking isn't externally observable | — | open |
| SGAP-002 | blocker | D3 | intent vs mechanism | `corpus_deactivate` "used by the directives sync"; doc §1 frames all four stores as independent | Overstates fragmentation → a planner would rebuild a sync that partly exists | §1: note directives↔corpus are already synced; the real split is file-memory + CLAUDE.md vs the synced directives/corpus pair | — | open |
| SGAP-003 | blocker | D5 | scope-vs-usage | `export_repo_memory_tool` is repo-scoped JSONL; disposition says "Covered" for data ownership/export | Overclaims corpus/directive export coverage | Correct disposition: repo memory has export/import; global-corpus export is via the directives file (text) — the tool does not cover it | — | open |
| SGAP-004 | blocker | D6 | scope-vs-usage | `run_embedding_backfill` is repo-scoped + missing-only; disposition implies corpus re-embed | Overclaims model-swap ease for the corpus | Correct disposition: backfill is repo-scoped/missing-only; a global-corpus re-embed on model change is not a documented path | — | open |

### Cleanup / Known-Limitation List

| item | note |
| --- | --- |
| K1 | Internal ranking of `run_retrieval_workflow` is not externally observable from the tool surface; §5 resolution is bounded to what the surface exposes (stated as such). |

---

## Cycle 1 Plan

### Gap-To-Fix Map

| gap_id | target | exact edit | validation |
| --- | --- | --- | --- |
| SGAP-001 | §5 (title + body) | drop `[VERIFY]`; "confirmed at tool surface — `corpus_query` exposes only `limit`/`kind`/`link_slug`, no recency, no threshold; internal ranking not externally observable" | grep §5 has no `[VERIFY]`; mentions "no threshold" |
| SGAP-002 | §1 body | add sentence: directives↔corpus already kept in sync (`corpus_deactivate` "used by the directives sync"); real fragmentation = file-memory + CLAUDE.md vs the synced pair | grep §1 for "directives sync" |
| SGAP-003 | disposition R19 | rewrite to repo-scoped truth | grep table for "repository memory" |
| SGAP-004 | disposition R13 | rewrite to repo-scoped/missing-only truth | grep table for "missing" |

Plan accepted; applying immediately.

---

## Cycle 1 Edits

- §5 (SGAP-001): retitled + rewrote evidence — dropped `[VERIFY]`; "confirmed at tool surface: `corpus_query` exposes only `query_text`/`limit`/`kind`/`link_slug`, no recency, no threshold"; added internal-ranking caveat. Updated cost + priority row 5 + R1 note + Status section.
- §1 (SGAP-002): added depth-pass refinement on the existing directives⇄corpus sync + free-form `kind`.
- Disposition R13/model-swap (SGAP-004): corrected to repo-scoped + missing-only.
- Disposition R19/export (SGAP-003): corrected to repo-scoped; corpus exports via the directives file.
- Added 4 depth rows to the Evidence appendix.

## Cycle 1 Validation

- `grep [VERIFY]` → only the R1 note (now phrased as "resolved in Gate-3"); no body `[VERIFY]` remains.
- Stale refs ("Verify/add", "remains the one item") → none.
- Unresolved-term scan → none.
- Each correction cites a real tool schema/description (`corpus_query`, `corpus_deactivate`, `run_corpus_upsert_workflow`, `export_repo_memory_tool`, `run_embedding_backfill`).

Post-Edit New-Gap Pass:

| changed unit | checked against | result | new gap |
| --- | --- | --- | --- |
| §5 rewrite | priority row 5 / R1 note / Status | all three updated to match (no stale "verify") | none |
| §1 refinement | headline "four stores" | consistent — refinement narrows, doesn't contradict ("four storage locations, two synced") | none |
| disposition R13/R19 | "Where ahead"/§ claims | consistent; now honest repo-scoped truth | none |

---

## Cycle 2 Assessment (fresh full depth pass, no edits)

Re-traced D1–D7 against the live tool surface:

| req_id | holds end-to-end? | evidence |
| --- | --- | --- |
| D1 | yes (gap real, now stated as confirmed-at-surface) | `corpus_query` schema — no recency/threshold |
| D2 | yes | `entry_key`+`link_slug` in observed output |
| D3 | yes (refined) | free-form `kind` + existing directives sync; §1 now reflects both |
| D4 | yes | `corpus_deactivate` + `supersedes_id` |
| D5 | yes (now accurate) | disposition states repo-scoped truth |
| D6 | yes (now accurate) | disposition states repo-scoped/missing-only truth |
| D7 | yes | `run_learned_memory_proposal_workflow` requires `repository_key` |

New blocker gaps in Cycle 2: **0**. SGAP-001…004 all `closed`.

## Final Convergence Check

### Final Readiness Proof

| req_id | satisfied end-to-end? | evidence |
| --- | --- | --- |
| D1 | yes — claim now matches runtime | `corpus_query` schema |
| D2 | yes | observed `corpus_query` output |
| D3 | yes — refined to live reality | `corpus_deactivate` desc + free-form `kind` |
| D4 | yes | `corpus_deactivate`/`supersedes_id` |
| D5 | yes — corrected to repo-scoped | `export_repo_memory_tool` desc |
| D6 | yes — corrected to repo-scoped | `run_embedding_backfill` desc |
| D7 | yes | proposal workflow schema |

**Convergence: reached.** Cycle 2 is a no-edit fresh depth pass with zero blocker gaps. Every doc claim that touches the live memory architecture now matches the real tool surface; over-claims were corrected; §5's premise is resolved.

**Known limitation (by evidence access):** internal ranking inside `run_retrieval_workflow`/`run_context_assembly_workflow` is not externally observable; §5's resolution is bounded to the exposed tool surface and says so.
