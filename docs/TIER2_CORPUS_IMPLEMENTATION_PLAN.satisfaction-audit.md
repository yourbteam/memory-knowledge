# Satisfaction Audit — TIER2_CORPUS_IMPLEMENTATION_PLAN.md

Depth gate (`requirements-satisfaction-gap-loop`). Verifies each addressed requirement holds
against the **real** `memory-knowledge` codebase, not just the document.

## Cycle 1 Assessment

### Requirement Inventory (addressed set, from coverage pass)

R1–R16 per `TIER2_CORPUS_IMPLEMENTATION_PLAN.coverage-audit.md`. Depth re-confirms the
implied-essential invariants below.

### End-to-End Trace Table (key requirements)

| req_id | trace | runtime evidence | holds? |
| --- | --- | --- | --- |
| R1/R8 | table in `memory` schema | `memory` schema + `memory.learned_records` created in `migrations/versions/001_initial_schema.py:23,207` | yes |
| R7 | embed body @ 768 | `config.py:57-59` (bge-base, 768); `db/qdrant.py:60` creates collections at `settings.embedding_dimensions`; `_assert_collection_dims` (`db/qdrant.py:34`) enforces | yes, via central path |
| R10 | ensure collection | **central** `ensure_collections()` over a `COLLECTIONS` list (`db/qdrant.py:52-58`), at startup | gap — plan said ad-hoc |
| R3.b/c | filter kind/link_slug | filtered Qdrant queries need a **payload index** or Qdrant rejects them (`db/qdrant.py:75-90` + comment "Qdrant rejects the filter without this index") | gap — no index planned for kind/link_slug |
| R11 | exclude inactive | producer `set_payload(is_active=False)` keeps the point (`learned_memory_qdrant.py:48-55`); reader filters `is_active=True` (`impact_analysis.py:76-78`) | yes — but plan wording ambiguous |
| R12 | write guard | `@mcp.tool()` + `check_remote_write_guard(get_settings(), name)` (`server.py:251,289`) | yes |
| R4 | supersede | `set_payload(is_active=False)` on old point; new point added; PG `is_active=false` | yes (mechanism ambiguous, see SGAP-003) |
| R3 (read) | corpus_query | mirror `query_points(... query=<embedded text>, filter=...)` (`impact_analysis.py:67`) | gap — query-embed symmetry unstated |

### Lens Coverage Matrix (summary)

| lens | result |
| --- | --- |
| 1 cross-feature contract | gaps: collection registration (SGAP-001), payload index (SGAP-002) |
| 2 data-reality | entry_key is the Qdrant point id (mirror `learned_memory_qdrant.py:43`) — lock (SGAP-003) |
| 3 intent vs mechanism | checked — kind/link_slug filtering serves "retrieve corpus for a directive" intent |
| 4 end-to-end trace | gap: query must be embedded with same model (SGAP-004) |
| 5 producer/consumer symmetry | gap: is_active deactivate-vs-filter contract ambiguous (SGAP-003) |
| 6 silent-inert | a missing payload index → filter throws (caught by SGAP-002); embedding mismatch → garbage results (SGAP-004) |
| 7 config dependence | embedding dims enforced by `_assert_collection_dims`; satisfied via central path (SGAP-001 fix) |
| 8 scope-vs-usage | corpus is global; retrieval not repo-scoped — consistent with R8 |

### Blocker Gap Ledger

| gap_id | severity | req_id | lens | evidence (both sides) | why it breaks | planned fix | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SGAP-001 | blocker | R10/R7 | 1 | plan: `corpus_qdrant.py` ensures collection ad-hoc; real: central `COLLECTIONS`+`ensure_collections` (`db/qdrant.py:52`) | ad-hoc creation diverges from startup path, skips payload-index step, risks dim drift | lock: add `corpus_entries` to `COLLECTIONS`; created by `ensure_collections` | closed |
| SGAP-002 | blocker | R3.b/c | 1/6 | real: filtered queries require payload index else rejected (`db/qdrant.py:84-90` + comment) | `corpus_query`'s `kind`/`link_slug` filters would throw at runtime | lock: add payload indexes for `kind`, `link_slug` (and confirm `is_active`) on the collection | closed |
| SGAP-003 | blocker | R4/R11 | 5 | real: deactivate = `set_payload(is_active=False)`, point retained (`learned_memory_qdrant.py:48-55`); reader filters `is_active=True` (`impact_analysis.py:76-78`) | plan said "removes/deactivates" — ambiguous; if built as point-removal, supersede history lost and contract diverges | lock: deactivate via `set_payload(is_active=false)` (point retained); retrieval filters `is_active=true`; `entry_key` == Qdrant point id | closed |
| SGAP-004 | blocker | R3 | 4/5 | real: write embeds body with Settings model; read must embed query with the **same** model or cosine search is meaningless | query embedded by a different model → garbage retrieval (silent-wrong) | lock: `corpus_query` embeds the query text with the same Settings embedding model as the write path | closed |

### Cycle 1 Plan (Gap-To-Fix Map)

SGAP-001→§Write path/§Locked (central collection registration); SGAP-002→§Write path (payload
indexes) + §Acceptance; SGAP-003→§Write path/§Retrieval/§Acceptance (lock is_active contract +
point id); SGAP-004→§Retrieval (query-embedding symmetry). All edits to the plan document.

### Cycle 1 Edits

Applied to `TIER2_CORPUS_IMPLEMENTATION_PLAN.md` — see diff.

## Cycle 2 Assessment (fresh, post-edit)

Re-traced each requirement against the codebase with the edited plan:
- R10/R7: collection now registered in `COLLECTIONS` → created+dim-checked by `ensure_collections`. holds.
- R3 filters: payload indexes for `kind`/`link_slug`/`is_active` now required by the plan → filters won't be rejected. holds.
- R4/R11: deactivate=`set_payload(is_active=false)`, point retained, reader filters `is_active=true`, `entry_key`=point id → symmetric. holds.
- R3 read: query embedded with same Settings model → cosine search meaningful. holds.

No new blocker surfaced. No producer/consumer boundary left one-sided.

### Final Readiness Proof

| req_id | satisfied end-to-end? | evidence |
| --- | --- | --- |
| R1,R8 | yes | `memory` schema real (`001_initial_schema.py:23`) |
| R3 | yes | query_points+filters with payload indexes; same-model query embed |
| R4,R11 | yes | set_payload(is_active=false) + reader filter (`learned_memory_qdrant.py:48`, `impact_analysis.py:77`) |
| R7,R10 | yes | central `ensure_collections` at 768/cosine (`db/qdrant.py:52-62`) |
| R12 | yes | guard pattern (`server.py:251`) |
| R13,R16 | yes | validation returns + downgrade |
| R14 | scoped-out | PG authoritative; integrity tooling reconciles |
| R15 | yes | tests slice |

## Cycle 2 Validation

Assessment-only cycle, no edits. Zero open blocker gaps.

## Final Convergence Check

Depth converged: every addressed requirement traces to confirming evidence in the real
codebase; every producer/consumer boundary (collection creation, payload index, is_active
flag, embedding model, point-id key) checked on both sides. This is the last gate before
implementation.
