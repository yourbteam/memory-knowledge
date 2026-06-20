# Coverage Audit — our-approach-vs-open-brain-gaps.md

Gate 2 of the research-playbook pipeline: **requirements-coverage-gap-loop** (breadth).
"Requirement set" = the complete set of distinguishing OB1 design principles/patterns that could reveal a gap in our memory/directives approach. Each must be addressed in the doc as: a **gap**, **where-we're-ahead/parity**, or **explicit out-of-scope + rationale**. A silently-missing differentiator is a coverage blocker.

---

## Cycle 1 Assessment

### Requirement Inventory (OB1 distinguishing principles)

| req_id | OB1 principle/pattern | type | source (grounded) |
| --- | --- | --- | --- |
| R1 | Single source of truth / one store | explicit | `OB1-main/README.md:7` |
| R2 | Frictionless capture / auto-capture habit | explicit | `OB1-main/skills/auto-capture/README.md:3,7` |
| R3 | Proactive discovery (Spark / Matchmaker) | explicit | `open-brain-brief.md` §6.2–6.3 |
| R4 | Portability / client-agnostic / Open Skills | explicit | `open-brain-brief.md:148` |
| R5 | Retrieval tuning: recency + threshold + dedup | explicit | `OB1-main/schemas/recency-boosted-match-thoughts/`; getting-started threshold |
| R6 | Radical simplicity / legibility | explicit | `open-brain-brief.md` §6.1 |
| R7 | Review/consolidation ritual cadence | explicit | `open-brain-brief.md` §6.2; `integrations/consolidation-workers/` |
| R8 | Trust tiers / evidence-vs-instruction | explicit | `OB1-main/AGENTS.md:54` |
| R9 | Contract rigor analog | implied | brief (OB1 metadata is "best-effort") |
| R10 | Self-improving analytics | implied | OB1 has none; ours does |
| R11 | Checkable compliance | implied | OB1 has none; ours does (G0) |
| **R12** | **Citation / linkable retrieval (stable URL per memory)** | **explicit** | `OB1-main/server/index.ts:42-43` (`thoughtUrl`); brief §4.3 (`fetch` returns url) |
| **R13** | **Model / embedding swappability** | **explicit** | `OB1-main/docs/01-getting-started.md:913` ("Swapping Models Later") |
| **R14** | **Cost / operational footprint** | **non-functional** | `open-brain-brief.md:207` (~$0.10/mo) |
| **R15** | **Chunking long content + hybrid metadata+vector filtering** | **explicit** | `OB1-main/docs/03-faq.md:119,135` |
| **R16** | **Sharing / RLS / multi-user scoped access** | **explicit** | `OB1-main/primitives/rls/`, `primitives/shared-mcp/` |
| **R17** | **Open extensibility / contribution model** | **explicit** | brief §4.4 (recipes/extensions/schemas) |
| **R18** | **Migration / bulk import of existing knowledge** | **explicit** | brief §6.2 (Memory/Second-Brain Migration) |
| **R19** | **Data ownership / export-import portability** | **explicit** | brief §2–3 (own the DB) |

### Coverage Matrix (does the doc address each?)

| req_id | status in doc | where / disposition |
| --- | --- | --- |
| R1 | addressed (gap) | §1 |
| R2 | addressed (gap) | §2 |
| R3 | addressed (gap) | §3 |
| R4 | addressed (gap) | §4 |
| R5 | addressed (gap, partial) | §5 — recency + threshold; **dedup sub-obligation not mentioned** |
| R6 | addressed (gap) | §6 |
| R7 | addressed (gap) | §7 |
| R8 | addressed (ahead) | "Where we are already ahead" #1 |
| R9 | addressed (ahead) | "Where ahead" #2 |
| R10 | addressed (ahead) | "Where ahead" #3 |
| R11 | addressed (ahead) | "Where ahead" #4 |
| R12 | **ABSENT** | not in doc → CGAP-001 |
| R13 | **ABSENT** | not in doc → CGAP-002 |
| R14 | **ABSENT** (touched obliquely by §6 but cost never stated) | → CGAP-003 |
| R15 | **ABSENT** | not in doc → CGAP-004 |
| R16 | **ABSENT** | not in doc → CGAP-005 |
| R17 | **ABSENT** | not in doc → CGAP-006 |
| R18 | **ABSENT** | not in doc → CGAP-007 |
| R19 | **ABSENT** | not in doc → CGAP-008 |

### Blocker Gap Ledger

| gap_id | severity | req_id | lens | evidence | why uncovered | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CGAP-001 | blocker | R12 | omission | OB1 `fetch` returns a stable URL per thought (`server/index.ts:42`); our corpus injects text as background with no per-entry citation in the response | A genuine differentiator + ties to our own G0 "checkable artifact" value; silently missing | Add §8 "Citation / linkable retrieval" as a gap | — | open |
| CGAP-002 | blocker | R13 | omission | OB1 documents one-line model swap (`getting-started:913`); ours uses Qdrant embeddings + `run_embedding_backfill` | Differentiator silently missing; needs honest disposition (we have backfill → partial) | Add to disposition table as partial/minor | — | open |
| CGAP-003 | blocker | R14 | elicitation (non-functional) | OB1 ~$0.10/mo vs our PG+Qdrant+workflow stack | Cost/complexity tradeoff never stated | Add to disposition table as accepted tradeoff (tie to §6) | — | open |
| CGAP-004 | blocker | R15 | omission | OB1 chunking + hybrid filter (`faq:119`); our `corpus_query` already does kind+link_slug+semantic hybrid; entries atomic | Silently missing; actually near-parity → scope as ahead/parity | Add to disposition table (parity) | — | open |
| CGAP-005 | blocker | R16 | omission | OB1 `primitives/rls`, `shared-mcp`; ours is single-operator (Kamen) | Silently missing; needs explicit out-of-scope | Add to disposition table (out-of-scope + rationale) | — | open |
| CGAP-006 | blocker | R17 | omission | OB1 contribution/extension model; ours extensible via schemas/workflows/skills | Silently missing; → ahead/parity | Add to disposition table (parity) | — | open |
| CGAP-007 | blocker | R18 | omission | OB1 Migration prompts; ours has a backfill script (`corpus-add` desc) | Silently missing; → covered | Add to disposition table (covered) | — | open |
| CGAP-008 | blocker | R19 | omission | OB1 own-the-DB export; ours has `export_repo_memory_tool`/`import_repo_memory_tool` | Silently missing; → covered | Add to disposition table (covered) | — | open |

Also note R5 partial: §5 covers recency + threshold but not **dedup** (OB1 `content_fingerprint` upsert-merge). Our corpus has supersede (`corpus_deactivate`/`supersedes_id`) — near-parity. → fold a one-line dedup note into the disposition table (CGAP-004 cluster). Recorded as cleanup C1 (not a separate blocker, since supersede ≈ dedup).

### Cleanup List

| item_id | req_id | issue | optional fix |
| --- | --- | --- | --- |
| C1 | R5 | dedup sub-obligation unstated; we have supersede (parity) | one-line note in disposition table |

---

## Cycle 1 Plan

### Gap-To-Fix Map

| gap_id | target | exact addition | validation |
| --- | --- | --- | --- |
| CGAP-001 | new §8 | "Citation / linkable retrieval" gap (consequence → evidence → fix → cost) | grep "§8" + "linkable" |
| CGAP-002–008, C1 | new "## Coverage of the remaining OB1 differentiators" table | each remaining principle → disposition (gap/partial/parity/ahead/out-of-scope) + one-line rationale + grounding | table has rows R13–R19 + R5-dedup |
| CGAP-001 | priority table | add §8 row | grep priority table for §8 |
| all | Evidence appendix | add rows R12–R19 | appendix grows |

Plan accepted; applying immediately.

---

## Cycle 1 Edits

- Added **§8 "Retrieved memory isn't cited back to its source"** (closes CGAP-001 / R12).
- Added **"## Coverage of the remaining OB1 differentiators"** disposition table (8 rows) closing CGAP-002…008 + C1 (R13–R19, R5-dedup), each with disposition + grounded rationale.
- Added priority-table row 8 (§8).
- Added 8 rows to the Evidence-grounding appendix (R12–R19).

## Cycle 1 Validation

- `grep '^## '` → 13 sections incl. new §8 + disposition table.
- §8 markers (`linkable`/`entry_key`) → 7 hits. Disposition rows (Parity/Out of scope/Accepted tradeoff/Covered/Minor) → 8.
- Unresolved-term scan → **none**.
- Each disposition row cites a real path/tool (OB1-main path, brief:line, or `*_tool`/`run_*`/`corpus_query`).

Post-Edit New-Gap Pass:

| changed unit | checked against | result | new gap |
| --- | --- | --- | --- |
| §8 (citation) | G0 value + existing §4 portability | complementary, no conflict | none |
| disposition: model-swap | §"ahead" / §6 | framed as minor/partial honestly (we have `run_embedding_backfill`) | none |
| disposition: cost | §6 sprawl | consistent (cost = the price of the complexity §6 flags) | none |
| disposition: sharing | doc scope (single operator) | explicit out-of-scope with rationale | none |
| appendix rows R12–R19 | real paths/tools | all resolve | none |

---

## Cycle 2 Assessment (fresh full pass over the complete requirement set, no edits)

Re-elicited the OB1-differentiator requirement set (R1–R19) and re-traced each.

| req_id | covered? | disposition location |
| --- | --- | --- |
| R1–R7 | yes (gap) | §1–§7 |
| R8–R11 | yes (ahead) | "Where ahead" |
| R12 | yes (gap) | §8 |
| R13 | yes (partial) | disposition table |
| R14 | yes (tradeoff) | disposition table |
| R15 | yes (parity) | disposition table |
| R16 | yes (out-of-scope+rationale) | disposition table |
| R17 | yes (parity/ahead) | disposition table |
| R18 | yes (covered) | disposition table |
| R19 | yes (covered) | disposition table |
| R5-dedup | yes (parity) | disposition table |

Elicitation re-sweep for additional OB1 differentiators not yet listed: considered (a) observability of retrieval, (b) versioning/lifecycle of entries, (c) offline/local fallback (OB1 `local-brain-no-mcp`). (a) ⊆ §8 citation/audit-trail; (b) ⊆ R5 supersede parity; (c) is an OB1 deployment convenience, not a memory-quality differentiator → not a coverage requirement. No new blocker requirements.

Blocker coverage gaps in Cycle 2: **0**. Ledger CGAP-001…008 + C1 all `closed`.

## Final Convergence Check

### Final Coverage Proof

| req_id | covered or scoped-out? | acceptance criterion | evidence |
| --- | --- | --- | --- |
| R1–R7, R12 | covered as gaps | each has consequence + fix + cost | §1–§8 |
| R8–R11 | covered as "ahead" | each names our stronger mechanism | "Where ahead" |
| R13–R19, R5-dedup | covered (parity/covered/tradeoff/out-of-scope) | each row has disposition + rationale | disposition table |

**Convergence: reached.** Cycle 2 is a no-edit fresh pass over the complete requirement set with zero blocker coverage gaps. Every OB1 differentiator is now addressed as a gap, a strength, parity, covered, an accepted tradeoff, or an explicit out-of-scope item.

**Scope (honest):** breadth only — every OB1 differentiator is *addressed*. It does NOT establish that each proposed fix actually *works* against our live memory architecture/data. That is Gate 3 (`requirements-satisfaction-gap-loop`).
