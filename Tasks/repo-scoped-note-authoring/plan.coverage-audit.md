# Coverage Audit — repo-scoped-note-authoring/plan.md

Gate A (breadth). Requirement set = feature obligations + implied-essential. Grounded in `learned_memory.py:run_proposal`, projections (`learned_memory_qdrant.py`, `learned_memory_neo4j.py`), `migrations/001`, `AGENTS.md`.

## Cycle 1 Assessment

### Requirement Inventory (key)
| req | requirement | type |
| --- | --- | --- |
| R1 | new `repository` root entity per repo | explicit |
| R2 | `author_repo_note` writes human-asserted `learned_records` | explicit |
| R3 | MCP tool + write-guard | explicit |
| R4 | embed + repo-scoped retrieval isolation | explicit |
| R5 | migrate 34 notes + delete file-memory | explicit |
| R6 | non-breaking/additive | non-functional |
| R7 | deploy to Azure | implied |
| R8 | tests | non-functional |
| R9 | **Neo4j projection** (scope node + `APPLIES_TO`) | implied-essential |
| R10 | `memory_type` in `VALID_MEMORY_TYPES` | implied-essential |
| R11 | evidence-free handling (no evidence entity/chunk) | implied-essential |
| R12 | propose-vs-commit semantics (PG@propose, Qdrant+Neo4j@commit) | implied-essential |
| R13 | embedding dimension match | non-functional |
| R14 | migration idempotency (S1 + S6) | negative/boundary |

### Coverage Matrix (gaps only)
| req | status | evidence |
| --- | --- | --- |
| R1,R2,R3,R5,R6,R7,R8 | addressed | plan S1–S6 + X-COMPAT |
| R4 | partial | plan says "embed + repo-scoped"; payload mechanism (`repository_key` in `learned_memory_qdrant.py:31`) not named → tighten |
| R9 | **absent** | plan never mentions Neo4j; `learned_memory_neo4j.py:25` MERGEs `APPLIES_TO`→scope → CGAP-001 |
| R10 | **absent** | `run_proposal` validates `memory_type ∈ VALID_MEMORY_TYPES`; plan uses `"note"` (likely invalid) → CGAP-002 |
| R11 | partial | plan sets evidence NULL, but `run_proposal` Step 2/4 **require** evidence entity + chunk; the note path must explicitly bypass, and projection/retrieval must tolerate null evidence → CGAP-003 |
| R12 | **absent** | existing pattern: proposal=PG-only (`verification_status='unverified'`), Qdrant+Neo4j at commit. Plan conflates "insert + embed" → must state author_repo_note is a single **human-asserted active** write projecting to PG+Qdrant+Neo4j → CGAP-004 |
| R13 | partial | listed as a risk, no acceptance criterion → CGAP-005 |
| R14 | partial | S1 idempotent; S6 (note migration) idempotency unstated (re-run dup risk) → CGAP-006 |

### Blocker Gap Ledger
| gap | req | fix | status |
| --- | --- | --- | --- |
| CGAP-001 | R9 | Plan must project the root entity + note to **Neo4j** (reuse `learned_memory_neo4j` MERGE `APPLIES_TO`→scope); root entity created in PG **and** Neo4j | open |
| CGAP-002 | R10 | Add `note` (or `operator_note`) to `VALID_MEMORY_TYPES`; acceptance: insert with that type succeeds | open |
| CGAP-003 | R11 | author_repo_note must NOT require evidence entity/chunk (insert `evidence_entity_id`/`evidence_chunk_id` NULL); confirm commit-projection + retrieval tolerate null evidence | open |
| CGAP-004 | R12 | Lock semantics: author_repo_note is a single write that lands the record **active + human-asserted** and projects PG+Qdrant+Neo4j (reusing the commit-path projection helpers), skipping the unverified-proposal stage | open |
| CGAP-005 | R13 | Acceptance: embedding uses the same model/dim as `learned_memory_qdrant`/corpus (assert dim) | open |
| CGAP-006 | R14 | S6 idempotency: entity_key derived from (repo, type, title-hash) so re-running the migration upserts, not duplicates | open |

Plan accepted; applying edits.

## Cycle 1 Edits
- CGAP-001/004 → design+S1/S2: project to PG+Qdrant+**Neo4j** in one human-asserted write reusing commit-path helpers; root entity created in PG **and** Neo4j.
- CGAP-002 → S1: add `note` to `VALID_MEMORY_TYPES`.
- CGAP-003 → design: evidence-free insert (NULL evidence entity/chunk), explicitly bypassing run_proposal's evidence requirement.
- CGAP-005 → S5: embedding parity acceptance.
- CGAP-006 → S6: idempotent migration via entity_key (repo+type+title-hash).

## Cycle 2 Assessment (fresh pass, no edits)
| req | covered? | where |
| --- | --- | --- |
| R1–R8 | yes | S1–S6 + X-COMPAT |
| R9 Neo4j | yes | design + S1/S2 |
| R10 memory_type | yes | S1 |
| R11 evidence-free | yes | design "Evidence-free" |
| R12 propose/commit | yes | design "Project to all three stores in one write" |
| R13 embed dim | yes | S5 |
| R14 idempotency | yes | S1 + S6 |

Blocker coverage gaps in Cycle 2: **0**. No open decisions (Option A confirmed).

## Final Convergence Check
**Breadth convergence: reached.** Every feature obligation + implied-essential (Neo4j projection, memory_type vocab, evidence-free path, propose/commit semantics, embedding parity, idempotency) is addressed with a testable acceptance criterion; non-breaking is explicit. Next: satisfaction/depth gate.
