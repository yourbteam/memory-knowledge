# Satisfaction Audit — repo-scoped-note-authoring/plan.md

Gate B (depth). Does each addressed step hold against the real runtime? Evidence from `workflows/retrieval.py`, `workflows/context_assembly.py`, `projections/learned_memory_qdrant.py` + `_neo4j.py` + `learned_memory_writer.py`, `migrations/001`.

## Cycle 1 Assessment — End-to-End Trace (blockers)

| req | trace vs real runtime | holds? |
| --- | --- | --- |
| **R4 retrieval** | repo-note → embedded to Qdrant **`learned_memory`** collection (`learned_memory_qdrant.py`). But `run_retrieval_workflow`→`retrieval.py` only searches **`code_chunks`** + **`summary_units`** (`retrieval.py:174,238`); learned-records surface only via `context_assembly` `MATCH (lr)-[:APPLIES_TO]->(scope) WHERE scope.entity_key IN $entity_keys` from those code hits (`context_assembly.py:35-36`). A repo-note's scope (repo-root) never appears in chunk/summary hits → **never retrieved** | **BREAKS → SGAP-001 (silent-inert, critical)** |
| R9/Neo4j | `project_learned_rule` does `MATCH (scope {entity_key})` (`learned_memory_neo4j.py:25`) — assumes the scope node exists; Neo4j's existing `Repository` node is keyed by `repository_key` string, not a UUID. A new repo-root UUID node isn't auto-created → `APPLIES_TO` MERGE silently no-ops | **partial → SGAP-002** |
| R2/insert | `upsert_learned_record` (`learned_memory_writer.py:11`) types `evidence_entity_id: int`, `evidence_chunk_id: int` (not Optional); columns are nullable (`001:219-221`) so None persists at runtime, but the signature implies required | **holds w/ caveat → SGAP-003** |
| R10 memory_type | `VALID_MEMORY_TYPES` in `workflows/learned_memory.py:29` — add `note` there if author_repo_note validates against it | holds (S1 covers) |
| R1/entity_type | no code asserts a fixed entity_type set; `compaction.py:145` & integrity checks filter `IN ('file','symbol'[,'chunk'])`, so a new `repository` type is simply ignored → safe | **holds** |
| doc refs | plan cited `corpus_writer.py` for `upsert_learned_record`; actual is `learned_memory_writer.py`; collection is `learned_memory` | SGAP-004 (accuracy) |

## Blocker Gap Ledger
| gap | req | evidence | fix | status |
| --- | --- | --- | --- | --- |
| SGAP-001 | R4 | `retrieval.py` never searches `learned_memory`; notes have no code anchor for the APPLIES_TO path → inert | **Add a `learned_memory` Qdrant search to `retrieval.py`/`run` (filter `repository_key` + `is_active`), merge into evidence.** New plan step; this is the change that makes repo-notes (and learned-records generally) retrievable by repo. Acceptance: note returned for its repo, excluded for others | open |
| SGAP-002 | R9 | `project_learned_rule` MATCHes scope by UUID; repo-root Neo4j node not auto-created | With SGAP-001, retrieval no longer depends on the edge. Create the repo-root Neo4j node with the **matching UUID** for graph consistency, but mark the APPLIES_TO edge **best-effort/secondary** (retrieval rides the direct learned_memory search) | open |
| SGAP-003 | R2 | `upsert_learned_record` evidence params typed `int` | author_repo_note passes `None`; relax the two params to `int | None` (or confirm None persists) — columns are nullable | open |
| SGAP-004 | doc | wrong file/collection names in plan | correct to `learned_memory_writer.py` + `learned_memory` collection | open |

Plan accepted; applying edits.

## Cycle 1 Edits
- SGAP-001 → design §3 + S4: add a direct `learned_memory` Qdrant search (repository_key+is_active) to retrieval — the change that makes repo-notes actually surface.
- SGAP-002 → design: Neo4j `APPLIES_TO` marked best-effort/secondary (retrieval rides the direct search); root Neo4j node created with matching UUID in S1.
- SGAP-003 → design: relax `upsert_learned_record` evidence params to `int | None`; author_repo_note passes None.
- SGAP-004 → corrected to `learned_memory_writer.py` + `learned_memory` collection.

## Cycle 2 Assessment (fresh depth pass, no edits)
| req | holds end-to-end? | evidence |
| --- | --- | --- |
| R4 retrieval | yes — direct `learned_memory` search by repository_key surfaces notes; isolation test in S4 | retrieval.py extension |
| R9 Neo4j | yes — root node UUID created; edge best-effort, retrieval independent | design |
| R2 insert | yes — NULL evidence persists (nullable cols); hints relaxed | learned_memory_writer / 001:219 |
| R10 memory_type | yes | VALID_MEMORY_TYPES (S1) |
| R1 entity_type | yes — no fixed-set assertion; filters ignore new type | compaction.py:145 |

Blocker satisfaction gaps in Cycle 2: **0**.

## Final Convergence Check
**Depth convergence: reached.** The critical silent-inert blocker (notes never retrieved) is fixed by extending retrieval to search the `learned_memory` collection by `repository_key`; Neo4j edge made non-load-bearing for note retrieval; NULL-evidence insert confirmed against nullable columns; new `repository` entity_type confirmed non-breaking. Plan is build-ready.
