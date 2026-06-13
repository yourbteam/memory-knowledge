# Coverage Audit — TIER2_CORPUS_IMPLEMENTATION_PLAN.md

Breadth gate (`requirements-coverage-gap-loop`). Target: `docs/TIER2_CORPUS_IMPLEMENTATION_PLAN.md`.

## Cycle 1 Assessment

### Requirement Inventory

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |
| R1 | store entry: kind, title, body, tags, link_slug | explicit | "Store a corpus entry with: a kind, a title, body text, free-form tags, and a link slug" |
| R2 | direct write tool, no propose→commit | explicit | "Write an entry directly via an MCP tool — no propose→commit" |
| R3 | semantic retrieval, filter by kind/link_slug | explicit | "Retrieve entries by semantic similarity … optionally filtered by kind and/or link slug" |
| R4 | update + supersede/deactivate | explicit | "Support updating an entry and superseding/deactivating an old one" |
| R5 | PG source of truth + Qdrant, no Neo4j | explicit | "Persist to Postgres as source of truth and to Qdrant … No Neo4j" |
| R6 | follow repo conventions (migration, schema, layout, server wiring) | explicit | "Follow the repo's existing conventions" |
| R7 | embedding generation config | implied | entailed by R3/R5 — body must be embedded; model/dim unstated |
| R8 | repository scoping decision (global vs repo-keyed) | implied | whole store is keyed by `repository_key`; table dropped it |
| R9 | entry_key generation | implied | "upsert" needs a key; new entries need one generated |
| R10 | Qdrant collection bootstrap | implied | a new collection must be created before first upsert |
| R11 | retrieval excludes inactive/superseded entries | implied/negative | R4 deactivates; R3 must not return deactivated |
| R12 | remote-write guard on the write tool | non-functional | R6 convention: every write MCP tool guards remote writes |
| R13 | error behavior (invalid kind, missing body, store failure) | non-functional/negative | user-facing tool must handle bad input + backend failure |
| R14 | PG/Qdrant consistency on partial failure | non-functional | two-store write can drift |
| R15 | tests for the new path | non-functional | R6 convention: repo has `tests/` |
| R16 | migration downgrade | non-functional | R6 convention: migrations carry `downgrade()` |

### Obligation Decomposition (key ones)

- R1 → columns exist for each field; `kind` constrained.
- R3 → (a) semantic search; (b) `kind` filter; (c) `link_slug` filter; (d) exclude inactive (→R11).
- R4 → (a) update existing; (b) supersede sets old `is_active=false`; (c) remove/deactivate old Qdrant point.
- R6 → (a) alembic migration up; (b) downgrade (→R16); (c) schema placement; (d) module layout; (e) server wiring; (f) write-guard (→R12); (g) tests (→R15).
- R7 → (a) model = repo default; (b) dimension matches collection.
- R13 → (a) invalid kind rejected; (b) missing body rejected; (c) embedding/Qdrant failure surfaced.

### Coverage Matrix (focused on gaps; covered items omitted for brevity)

| req_id.obligation | status | addressed where / gap |
| --- | --- | --- |
| R1.* | addressed | Schema table (plan §Schema) |
| R2 | addressed | §Locked decision 4 + §MCP wiring |
| R3.a/b/c | addressed | §Retrieval path |
| R3.d (exclude inactive) | **absent** | retrieval says nothing about `is_active` |
| R4.a/b/c | partial | supersede mentioned; Qdrant-point removal in writer list but not tied to retrieval |
| R5 | addressed | §Locked decision 3 |
| R7.a/b | **absent** | no embedding model/dimension stated |
| R8 | **absent** | `repository_key` dropped with no global-vs-scoped decision |
| R9 | **absent** | entry_key generation unspecified |
| R10 | partial | "collection bootstrap" named in build order, no mechanism |
| R11 | **absent** | not stated |
| R12 | **absent** | no remote-write guard in MCP wiring |
| R13.a/b/c | **absent** | no error behavior stated |
| R14 | **absent** | partial-failure drift not addressed |
| R15 | **absent** | acceptance criteria present but no test obligation |
| R16 | **absent** | downgrade not mentioned |

### Conflict Register

- R2 (no approval step) vs R6 (follow conventions; learned-memory uses propose→commit). Reconciled in plan §R2 rationale (process-level gate, not DB) — no blocker.

### Blocker Gap Ledger

| gap_id | severity | req_id.obligation | lens | why uncovered | planned fix | status |
| --- | --- | --- | --- | --- | --- | --- |
| CGAP-001 | blocker | R8 | elicitation | global-vs-repo-scoped never decided; table has no repo key | lock "corpus is global, not repo-scoped"; note `corpus_query` is not repo-filtered | closed |
| CGAP-002 | blocker | R7 | omission | embedding model/dim unstated | state collection uses Settings embedding config (BAAI/bge-base-en-v1.5, 768) | closed |
| CGAP-003 | blocker | R12 | omission | write tool lacks remote-write guard | add `check_remote_write_guard` to write tool + acceptance | closed |
| CGAP-004 | blocker | R3.d/R11 | partial | retrieval doesn't exclude inactive | state `corpus_query` filters `is_active=true` | closed |
| CGAP-005 | blocker | R9 | omission | entry_key generation unspecified | lock deterministic key from `link_slug`+`title` hash (re-upsert updates, not duplicates) | closed |
| CGAP-006 | blocker | R16 | omission | no downgrade | add `downgrade()` drops table | closed |
| CGAP-007 | blocker | R13 | omission | no error behavior | add error obligations (CHECK on kind; workflow returns error WorkflowResult on bad input / store failure) | closed |
| CGAP-008 | blocker | R10 | partial | collection bootstrap has no mechanism | state ensure-collection (768/cosine) before first upsert | closed |
| CGAP-009 | blocker | R15 | omission | no test obligation | add tests to build order + acceptance | closed |
| CGAP-010 | blocker | R14 | scope-boundary | partial-failure drift unaddressed | scope-out v1 with rationale (PG authoritative; existing integrity tooling reconciles) | closed |

### Cycle 1 Plan (Gap-To-Fix Map)

Each CGAP above → the named doc edit. All target `docs/TIER2_CORPUS_IMPLEMENTATION_PLAN.md`.

### Cycle 1 Edits

Applied: added requirements R7–R16 coverage via new/expanded sections (Locked decisions, Schema notes, Write/Retrieval path, MCP wiring, Build order, Acceptance, Out-of-scope). See plan diff.

## Cycle 2 Assessment (fresh, post-edit)

Re-ran the full inventory against the edited plan. Every requirement R1–R16 now traces to an addressing mechanism or an explicit out-of-scope statement (R14). No new requirement surfaced; no conflict left unreconciled; each carries a testable acceptance criterion.

### Final Coverage Proof

| req_id | every obligation covered or scoped-out? | acceptance criterion present? | evidence |
| --- | --- | --- | --- |
| R1 | yes | yes | §Schema, §Acceptance bullet 1 |
| R2 | yes | yes | §Locked 4, §Acceptance bullet 2 |
| R3 | yes (incl. exclude-inactive) | yes | §Retrieval, §Acceptance bullet 3 |
| R4 | yes | yes | §Write path, §Acceptance bullet 4 |
| R5 | yes | yes | §Locked 3 |
| R6 | yes | yes | §Build order, §Acceptance |
| R7 | yes | yes | §Locked (embedding), §Acceptance |
| R8 | yes | yes | §Locked (global corpus) |
| R9 | yes | yes | §Locked (entry_key) |
| R10 | yes | yes | §Write path (ensure-collection) |
| R11 | yes | yes | §Retrieval (is_active filter) |
| R12 | yes | yes | §MCP wiring (guard), §Acceptance |
| R13 | yes | yes | §Error behavior |
| R14 | scoped-out (rationale) | n/a | §Out of scope |
| R15 | yes | yes | §Build order, §Acceptance |
| R16 | yes | yes | §Schema/migration |

## Cycle 2 Validation

No edits in Cycle 2 (assessment-only). Zero open blocker gaps. 

## Final Convergence Check

Breadth converged: complete requirement set (R1–R16), every obligation addressed or explicitly scoped-out, each with a testable acceptance criterion. Convergence = **breadth only**; depth (does each hold against real runtime/data/sibling features) is the next gate (`requirements-satisfaction-gap-loop`).
