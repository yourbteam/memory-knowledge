# Gap Audit — our-approach-vs-open-brain-gaps.md

Gate 1 of the research-playbook hardening pipeline: **doc-gap-closure-loop** (internal readiness only).
Target: `/Users/kamenkamenov/Downloads/our-approach-vs-open-brain-gaps.md` (143 lines at audit start).
Scope note: this is a **research/comparison findings doc**, so the "implementation-planning readiness" lenses are applied as *claim-grounding, internal-consistency, and self-sufficiency* checks (R1: cite or flag). Convergence here = internal readiness only; it does NOT establish that any proposed fix actually works (that is Gates 2–3).

---

## Cycle 1 Assessment

### Section Inventory

| unit_id | section/title | unit type | implementation relevance |
| --- | --- | --- | --- |
| U0 | Title + metadata + inputs (L1–12) | intro | frames what is compared; cited sources must be real |
| U1 | Framing caveat + R1 note (L8–12) | callout | sets scope; consistency anchor |
| U2 | §1 Fragmented across four stores (L14–26) | finding | core claim about our store count + OB1 principle |
| U3 | §2 Capture friction (L28–40) | finding | claim about corpus-add + learned-memory mechanism |
| U4 | §3 Reactive-only directives (L42–54) | finding | absence claim about proactive routine |
| U5 | §4 Tool-bound portability (L56–68) | finding | claim about hook vs MCP reach |
| U6 | §5 Retrieval recency [VERIFY] (L70–82) | finding | explicitly unverified premise |
| U7 | §6 Surface sprawl (L84–96) | finding | numeric claim (56 repos / ~40 empty) |
| U8 | §7 Review cadence (L98–110) | finding | claim about stamp + consolidation tools |
| U9 | Where we are already ahead (L112–123) | analysis | balance claims about our strengths |
| U10 | Suggested priority table (L125–137) | table | value/effort ranking |
| U11 | Status & next step (L139–143) | callout | playbook handoff |

### Coverage Matrix (lenses applied per unit)

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U0 | repo grounding | checked | brief + OB1 repo paths exist; inputs accurate |
| U1 | contradictions | checked | framing consistent with body |
| U2 | repo grounding | gap found | corpus `kind` values + vector store ungrounded → GAP-005 |
| U3 | repo grounding / accuracy | gap found | conflates repo-scoped learned-memory with global corpus → GAP-001 |
| U4 | repo grounding | gap found | absence claim not qualified as inference → GAP-002 |
| U5 | grounding | checked | hook-injection + MCP reach consistent with system facts |
| U6 | grounding | checked | already [VERIFY]-flagged; grounding strengthened via GAP-003 |
| U7 | factual precision | gap found | "~40 empty" imprecise → GAP-004 |
| U8 | repo grounding | checked | stamp at directives header; tools exist (consolidate-memory, compaction, integrity audit) |
| U9 | repo grounding | checked | AGENTS.md:54 evidence-vs-instruction confirmed |
| U10 | consistency | checked | priorities map 1:1 to §1–§7 |
| U11 | consistency | checked | matches research-playbook handoff |
| ALL | doc-wide citation (R1) | gap found | load-bearing claims lack concrete path:line/tool refs → GAP-003 |

### Blocker Gap Ledger

| gap_id | severity | unit_id | lens | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAP-001 | blocker | U3 | accuracy | `run_learned_memory_proposal_workflow` = repo-scoped, evidence-backed; `run_corpus_upsert_workflow` = "global, not repository-scoped" | §2 implies one pipeline auto-feeds the corpus; it actually spans two distinct subsystems → overclaim | Distinguish repo-scoped learned-memory (propose→commit, evidence+approval) from global corpus (manual `run_corpus_upsert_workflow`/`corpus-add`) | — | open |
| GAP-002 | blocker | U4 | grounding | §3 asserts "no routine … turns telemetry into candidate directives" | Asserting an absence as fact without scoping it to what was inspected violates R1 | Qualify as "none found among available memory-knowledge tools"; name analytics tools exactly; mark absence as inference | — | open |
| GAP-003 | blocker | ALL | citation (R1) | body cites sources by name but without path:line/tool refs | A reader cannot verify load-bearing claims → fails self-sufficiency | Add an "Evidence grounding" appendix table mapping each §'s key claim → path:line or tool name | — | open |
| GAP-004 | blocker | U7 | precision | actual `list_repositories`: 56 total, 9 with file_count>0 | "~40 empty" undercounts; numeric claim must be exact | Correct to "47 of 56 have zero files; 9 real repos" + list the 9 | — | open |
| GAP-005 | blocker | U2 | grounding | corpus kinds + storage engine unstated/loose | §1 is the headline; its store description must be exact | Ground kinds verbatim ("directive rationale, playbook detail, example, reference"); add PG+Qdrant vs pgvector data point | — | open |

### Cleanup List

| item_id | unit_id | issue | optional fix |
| --- | --- | --- | --- |
| C1 | U6 | §5 title says "appears similarity-only" — acceptable hedge | leave; it is the intentionally-flagged item |

---

## Cycle 1 Plan

### Gap-To-Fix Map

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |
| GAP-001 | U3 (§2) | Two subsystems, not one | Rewrite the "Note" in §2 to separate repo-scoped learned-memory (propose→commit, evidence_entity_key + confidence + approval gate) from the global corpus (`run_corpus_upsert_workflow`/`corpus-add`, manual) | grep §2 for "global"/"repo-scoped" distinction present |
| GAP-002 | U4 (§3) | Absence is scoped inference | Add "[INFERENCE — none found among available tools]" qualifier + name `get_finding_pattern_summary`, `get_clarification_policy`, `get_triage_confusion_clusters`, `get_agent_failure_mode_summary` | grep §3 for the qualifier + tool names |
| GAP-003 | new appendix | Every § grounded | Append "## Evidence grounding" table | table present with ≥10 rows |
| GAP-004 | U7 (§6) | Exact repo counts | Replace "~40" with "47 of 56 (9 real: css-scheduler, css-fe, fcs-admin, fcsapi, millennium-wp, neocurrency-dashboard, taggable-api, taggable-server, tpp-petkey)" | grep §6 for "47 of 56" |
| GAP-005 | U2 (§1) | Exact kinds + engine | Quote corpus kinds verbatim; add "(PG + Qdrant)" vs OB1 "(Postgres + pgvector)" | grep §1 for "Qdrant" and kind list |

Plan accepted; applying immediately.

---

## Cycle 1 Edits

| gap_id | edit | location |
| --- | --- | --- |
| GAP-001 | Split §2 "Note" into the repo-scoped learned-memory pipeline vs the global corpus; quoted both tool descs | doc L36, L38 |
| GAP-002 | Added "[INFERENCE — absence, not verified exhaustively]" qualifier; named analytics tools | doc L47 |
| GAP-003 | Added "## Evidence grounding" appendix (16 rows, path:line/tool refs) | doc L143–160 |
| GAP-004 | "~40" → "47 of 56 empty; 9 with content" + named the 9 | doc L86, L89 |
| GAP-005 | Quoted corpus `kind` verbatim; added PG+Qdrant vs pgvector | doc L19, L146–147 |
| (incidental) | Fixed stale cross-ref §2 "trust-tier model, §3" → §"Where we are already ahead" | doc L38 |

## Cycle 1 Validation

Commands run from `/Users/kamenkamenov/Downloads`:

- `wc -l` → 168 lines (was 143).
- `grep -nEi 'TBD|TODO|maybe|not locked|needs further|or equivalent'` → **none**.
- GAP-001 → present (L19, L36, L38, L147). GAP-002 → present (L47). GAP-003 → 16 evidence rows. GAP-004 → "47 of 56" (L86, L89). GAP-005 → Qdrant + verbatim kinds (L19, L146).
- `git` not applicable (target dir is not a tracked repo).

Post-Edit New-Gap Pass:

| changed unit | checked against | result | new gap id |
| --- | --- | --- | --- |
| §1 (PG+Qdrant) | headline "four stores" | consistent — Qdrant framed as the corpus's vector engine, not a 5th knowledge store | none |
| §2 (two subsystems) | §"Where we are already ahead" trust-tier claim | consistent; cross-ref corrected | none |
| §3 (INFERENCE) | R1 cite-or-flag | now honestly scoped as absence/inference | none |
| Evidence appendix | every cited path/tool | all 16 rows resolve to a real path:line or tool desc | none |
| §6 (47/56) | `list_repositories` output | matches (9 named repos with file_count>0) | none |

---

## Cycle 2 Assessment (fresh full-document pass, no edits)

Re-inventoried all 12 units (U0–U11) plus the new Evidence-grounding appendix (U12). Applied every lens top to bottom.

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U0–U1 | grounding/consistency | checked | inputs + framing accurate |
| U2 (§1) | grounding | checked | kinds verbatim; PG+Qdrant grounded (L19, L146–147) |
| U3 (§2) | accuracy | checked | two subsystems distinguished; tool descs quoted (L36) |
| U4 (§3) | R1 | checked | absence scoped as inference (L47) |
| U5 (§4) | grounding | checked | brief:148 quote in appendix |
| U6 (§5) | flagging | checked | [VERIFY] intact; recency schema dir cited |
| U7 (§6) | precision | checked | exact 9/47/56 counts (L86, L89) |
| U8 (§7) | grounding | checked | stamp + consolidation-workers path |
| U9 (ahead) | grounding | checked | AGENTS.md:54 |
| U10 (priority) | consistency | checked | maps 1:1 to §1–§7 |
| U11 (status) | consistency | checked | reflects gates being run |
| U12 (evidence) | grounding | checked | 16 rows, all resolve |

Blocker gaps found in Cycle 2: **0**. Carried-forward ledger: GAP-001…GAP-005 all `closed`.

## Final Convergence Check

| category | status | evidence |
| --- | --- | --- |
| Claim grounding (R1) | ready | every load-bearing claim has path:line/tool ref in Evidence appendix |
| Internal consistency | ready | post-edit pass found no contradictions; stale cross-ref fixed |
| Self-sufficiency | ready | a reader can verify each gap from cited sources without external context |
| Honest scoping | ready | §5 [VERIFY] + §3 [INFERENCE] explicitly flagged |
| Numeric accuracy | ready | repo counts and kind/engine values exact |
| Out-of-scope boundary | ready | doc states it makes no changes to directives/corpus; proposes only |

**Convergence: reached.** Cycle 2 is a no-edit assessment over the already-edited document with zero blocker gaps.

**Scope of this convergence (honest):** this establishes **internal document readiness only** — the gaps doc is self-sufficient, internally consistent, and its cited claims are real. It does **not** establish that the proposed improvements (§1–§7) actually work against our live memory architecture, sibling features, or stored data. That is what Gates 2 (`requirements-coverage-gap-loop`) and 3 (`requirements-satisfaction-gap-loop`) test next.
