# Architecture & Execution Evaluation — Does memory-knowledge deliver real, practical value?

**Status:** Research / evaluation draft
**Date:** 2026-06-03
**Method:** Evidence-based. Grounded in (a) a full read of the codebase this session, (b) eight architectural findings (F1–F8) found and fixed in production, (c) the embeddings migration, and (d) live production usage/scale signals pulled from the databases. Claims cite code, findings, or measured signals — not impressions.

> **Stance:** This is a candid review, not a endorsement. The goal is to separate *what is well-designed* from *what is well-executed* from *what actually delivers value today* — three different questions that are easy to conflate.

---

## 1. What the system is meant to be

A "multi-model code-intelligence + memory platform": ingest repositories, project them into three datastores (PostgreSQL = canonical + lexical, Qdrant = semantic vectors, Neo4j = structural graph), and serve an MCP retrieval API that routes each query to the right store(s) and fuses results — plus a "memory" layer that learns and stores reusable rules/decisions about the codebase.

The value proposition is real on paper: give an AI agent hybrid retrieval (exact + semantic + structural) over a codebase, with accumulated institutional memory.

---

## 2. Architecture — design quality (strong)

The **design** is genuinely good and shows real engineering maturity:

- **Sound polyglot-persistence rationale.** The three stores map cleanly to three irreducible query shapes (keyword, semantic, relational-traversal) — this is justified, not gratuitous (see `docs/DATABASE_UTILIZATION_RESEARCH.md`). PG-led `exact_lookup`, Qdrant-led `conceptual_lookup`, Neo4j-led `impact_analysis` is a coherent division of labor.
- **One clean linking primitive.** A deterministic `entity_key` (UUIDv5 over stable inputs, [`identity/entity_key.py`](../src/memory_knowledge/identity/entity_key.py)) ties an entity across all three stores and makes re-ingestion idempotent. This is elegant and avoids a mapping table.
- **Clear separation of concerns.** Canonical writes → projections (`projections/*`) → workflows (`workflows/*`) → MCP tools is a readable, layered structure. PG is the single source of truth; Qdrant/Neo4j are derived projections.
- **Operational maturity present.** Checkpointed ingestion, a job/manifest system, health/readiness probes, degraded-startup tolerance, remote write-guards, and a 398-test suite. These are signs of a team that has built production systems before.

**Verdict on design:** above-average. The bones are good.

---

## 3. Execution — quality (mixed; materially improved this session)

Design quality and execution quality diverged. A single session surfaced **eight real, shipped defects** — several of which silently degraded correctness in production:

| Finding | What it was | Severity |
|---|---|---|
| **F1** | PG retrieval served superseded/deleted content (no `is_active`/revision scoping); ~21% of chunks were stale | correctness |
| **F2** | No garbage collection anywhere — PG/Qdrant/Neo4j grew unbounded; `repair` only adds | operational |
| **F3** | Deleted files orphaned PG rows + Neo4j nodes; the audit couldn't even detect it | correctness |
| **F4** | `pg_ssl=True` used `CERT_NONE` — encrypted but MITM-exposed on the prod flag | security |
| **F5** | Qdrant readiness flipped the pod to `not_ready` despite degraded-startup design | availability |
| **F6** | `exact_lookup` never touched vectors; `decision_history` was silently lexical-only | retrieval quality |
| **F7** | Fusion summed incomparable score scales (PG ts_rank vs cosine) | ranking quality |
| **F8** | Route-policy columns (`third_store`/`fusion_strategy`/`rerank_strategy`) were dead config implying behavior that didn't run | maintainability |

Plus two non-finding execution facts uncovered:
- **Embeddings were broken in production** (`429 insufficient_quota`): the code authenticated OpenAI embedding calls with a ChatGPT OAuth token that has no embeddings entitlement — so semantic search (a core capability) was *failing* in prod.
- **CI was red on `main`** for the embeddings commit (a test asserting an old default was never updated).

**Pattern:** the failures cluster around *lifecycle and consistency* — the hard part of multi-store systems. Writing data into three stores is done well; keeping them correct over time (supersession, deletion, GC, drift, credential validity) was under-built. The is_active model existed only in Qdrant, not PG; nothing pruned; the audit checked presence but not staleness. This is a classic "the happy path works, the maintenance path rots" profile.

All eight are now fixed and deployed, and a dry-run-first compaction path exists — so the *current* state is materially healthier than what shipped. But the existence of this many silent defects is itself the most honest signal about original execution rigor: **good intentions, thin verification of the steady-state.**

---

## 4. Practical value delivered — usage evidence (the sharpest question)

Whether sophisticated architecture delivers *real* value depends on whether the capabilities are exercised. The production signals (2026-06-03):

- **Retrieval is used, modestly:** 809 `route_executions` over the system's life. Real, but not heavy.
- **The query mix undercuts the third database:** `exact_lookup` 437, `conceptual_lookup` 354, `impact_analysis` **14**, `pattern_search` 4 (decision_history/mixed ≈ 0). So **~98% of real queries are exact + conceptual** — exactly what PG + Qdrant alone cover. The **Neo4j graph (impact_analysis), the most architecturally distinctive capability, is exercised ~1.7% of the time.**
- **The "memory/learning" layer — the project's namesake — is empty:** `memory.learned_records` = **0 rows**; `working_sessions` = 1. The entire learned-rule subsystem (PG tables, `LearnedRule` graph nodes, `learned_memory` vectors, the `APPLIES_TO`/`CONFLICTS_WITH` edges, the staleness cascade) is built and dormant. "Memory-knowledge" currently has no memory.
- **Data is going stale:** the most recent ingestion was **2026-04-27 (~5 weeks ago)**; only 12 of 21 ingestion runs completed. The freshness-warning code path is effectively the system's normal state.
- **Scale is small:** 56 repositories, but **47 are throwaway `mawf-*`/test repos** — only ~9 are real. ~66.6k active chunks, ~175k entities.
- **Feedback is auto-generated, not human:** `route_feedback` = 809 (1:1 with executions, all heuristic auto-feedback). There is no human-in-the-loop signal training the router.

**Net:** the system delivers *some* real value today — hybrid keyword+semantic search over ~9 repositories, ~800 queries' worth — but a large fraction of the built architecture is **dormant**: the graph database is barely queried, the *code-knowledge* memory layer is unused, and ingestion has stopped.

> **Correction (added during the §9 discovery pass):** this section under-counts the system's *other* half. The MCP surface is **~140 tools**, heavily weighted toward a **MAWF (multi-agent workflow) + triage + analytics** platform (≈40 `mawf_*` tools, plus triage/intake/planning). `triage_cases` = 47 and there is real MAWF activity, so the *agent-workflow memory* subsystem **is** used. The "memory is empty" claim is therefore accurate only for the **code-knowledge `learned_records`** (0 rows), not the triage/MAWF memory. This reframes the value picture: the 3-store *code-retrieval* engine evaluated above may be a *secondary* capability to a larger agent-orchestration product — which changes how Recs 2 and 3 should be prioritized.

---

## 5. Complexity vs. value — is the ambition matched by the demand?

At current demonstrated usage, the architecture is **over-built relative to load**:

- Three databases are justified *in principle*, but at this usage two (PG + Qdrant) carry ~98% of queries. Neo4j earns its operational cost (a third managed DB, a third projection path, a third consistency surface — which is exactly where F3/F2 bugs lived) for ~1.7% of traffic.
- The memory/learning layer is a substantial slice of the schema and code (multiple tables, three projections, graph edges, lifecycle logic) with **zero data** — pure carrying cost today.
- The operational complexity (three stores to keep consistent) is precisely what produced the correctness findings (F1/F3) and the unbounded-growth finding (F2). Complexity bought capability that isn't being consumed, while adding failure modes that *were* consumed.

This is not "the architecture is wrong" — it's "the architecture is sized for a much larger, more active, memory-accumulating deployment than currently exists." That's a reasonable bet *if* the usage is coming; it's a liability if it isn't.

---

## 6. Verdict

- **Architected:** **B+/A−.** Thoughtful, defensible multi-model design with a clean linking model and real operational scaffolding. The three-store rationale holds up.
- **Executed:** **C+/B−, trending up.** The build-path is solid; the steady-state/lifecycle path shipped with eight silent defects (correctness, security, availability) plus a broken core dependency (embeddings) — all now fixed. Verification of the non-happy-path was the weak link.
- **Practical value today:** **Partial.** It works and is used for hybrid search over a handful of repos, but the graph DB is barely exercised, the memory layer is empty, and ingestion has lapsed — so most of the sophistication is latent potential, not realized value.

**One-line summary:** *A well-designed, ambitious platform whose execution under-invested in multi-store consistency, and whose realized value is currently a fraction of its built capability — strong foundations, but the gap between "built" and "used" is the real story.*

---

## 7. Recommendations (to convert built capability into realized value)

1. **Restart and automate ingestion.** Stale data (5 weeks) silently erodes every downstream answer; the most valuable, cheapest win. Add a scheduled re-ingest so the freshness warning stops being the default.
2. **Decide the memory layer's fate.** Either drive adoption of learned-records (it's the differentiator and the project's namesake) or formally shelve it to shed carrying cost. Zero rows after this much build is the clearest signal to act on.
3. **Justify or right-size Neo4j.** At 1.7% impact-analysis usage, either surface graph value better (impact analysis is genuinely unique — promote it) or treat Neo4j as optional and reduce its consistency burden.
4. **Institutionalize the steady-state verification this session added.** The compaction/`is_active`/audit work should run on a schedule with alerts, not as one-off scripts — that's how F1/F2/F3-class rot is prevented from recurring.
5. **Add real feedback.** 100%-auto feedback can't improve routing; a thin human signal would let the routing/threshold machinery (now wired) actually learn.

## 8. Caveats / threats to this evaluation
- Some of the 809 executions and recent timestamps include this session's verification probes; the *pattern* (exact+conceptual dominance, near-zero graph/memory usage) is robust regardless.
- Usage being low ≠ value being low *if* the deployment is pre-adoption; this evaluation measures realized value, not potential.
- The eight findings are now fixed; this assesses original execution, not the current (improved) state.

---

## 9. Planning-readiness — discovery findings & remaining gaps

This evaluation is an *assessment*, not a *spec*. A follow-up implementation plan built directly on §7 would **not** be one-shot, because several recommendations rest on operating-model facts §1–§8 didn't establish. This section runs that discovery and lists what still must be resolved before planning.

### 9.1 Discovery findings (resolved during this pass)

| Question | Finding (evidence) |
|---|---|
| How is data fed into prod? | `run_repo_ingestion_workflow` — an MCP tool that **git-clones** each repo (GitHub App config in KV) to a temp path and parses it. "No git mounts" in the deploy notes ≠ no cloning. Real repos show `origin_url` set + 1–6 runs each. |
| Ingestion cadence / why lapsed? | **Manual, no scheduler.** 15 full + 6 incremental runs; last run ~2026-04-20→27. The codebase has no cron/recurring trigger for ingestion (only a job dispatcher poll + codex-token refresher). It simply stopped being invoked. |
| Is there a memory-creation path? | **Yes** — `run_learned_memory_proposal_workflow` + `run_learned_memory_commit_workflow` (propose→commit). `learned_records=0 *ever*` means the path was **never exercised**, not that it's missing. |
| Is there a feedback path? | **Yes** — `submit_route_feedback` MCP tool. All 809 `route_feedback` rows are auto-generated heuristics; the human path exists but is unused. |
| Is compaction operationalized? | **No** — `integrity/compaction.py` is a module run via a local script; it is **not** an MCP tool and **not** scheduled. (Audit *is* a tool: `run_integrity_audit_workflow`.) |
| Is the code-retrieval engine the whole product? | **No** — ~140 MCP tools; the bulk are MAWF/triage/intake/planning/analytics. The 3-store retrieval engine is one capability among many; MAWF/triage appear to be a primary workload. |

**Implication:** Recs 1, 2, 5 are "wire up / drive adoption of tools that already exist," not "build from scratch" — much smaller than the evaluation implied. Rec 4 needs compaction exposed as a tool first. Rec 1 needs a scheduler chosen.

### 9.2 Remaining gaps — must resolve BEFORE the implementation plan

These could not be determined from inside the codebase and will change the plan's shape:

1. **External orchestration reality.** The codebase has no scheduler, but is there an **external** trigger (Azure cron, a CI job, or the MAWF orchestrator) that is *supposed* to drive ingestion and lapsed — or was ingestion always hand-run? Rec 1's design (build a scheduler vs. fix an existing one) depends on this. **Owner input required.**
2. **Product intent / primacy.** Is the 3-store code-retrieval engine a first-class product, or supporting infrastructure for the MAWF platform? This sets the priority of Recs 2 (memory) and 3 (Neo4j) — invest vs. right-size. **Owner decision required.**
3. **Per-recommendation success criteria & targets** (none exist yet): ingestion freshness SLA; query-volume threshold that justifies Neo4j; definition of "memory-layer adopted" (e.g., N learned_records/repo); target human-feedback rate.
4. **Memory-layer intended trigger.** The propose/commit tools exist but who/what is meant to call them — an ingestion-time step, a periodic agent, or a human workflow? Without the intended trigger, "drive adoption" has no concrete subject.
5. **Repo scope for ingestion.** Which of the registered repos are in-scope to keep fresh (the ~9 real ones; `tpp-petkey` is registered but never ingested; two have no `origin_url`)? And what commit-detection model (webhook vs. poll)?

### 9.3 Per-recommendation planning readiness

| Rec | Mechanism resolved? | Still needed before planning |
|---|---|---|
| **1. Restart/automate ingestion** | ✅ tool known (git-clone) | scheduler choice (gap 9.2.1), repo scope + cadence (9.2.5), commit-detection model |
| **2. Decide memory-layer fate** | ✅ create path known (propose/commit) | product-intent decision (9.2.2), intended trigger (9.2.4), keep-vs-remove surface inventory + success metric |
| **3. Justify/right-size Neo4j** | n/a | product-intent (9.2.2), decision criteria + the query-volume threshold (9.2.3) |
| **4. Schedule steady-state verification** | partial — audit is a tool; **compaction is not** | expose compaction as a tool; scheduler (9.2.1); thresholds + alert channel + owner |
| **5. Add real feedback** | ✅ tool known (`submit_route_feedback`) | where/how it's surfaced to a human/agent; target rate (9.2.3) |

### 9.4 Recommended pre-plan step
A short **discovery spec** that (a) gets owner answers to gaps 9.2.1 and 9.2.2 (the two that fork the whole plan), (b) sets the success metrics in 9.2.3, and (c) for the chosen recs, inventories surface area + effort. With those, the implementation plan can be one-shot. Without 9.2.1/9.2.2, any plan risks building the wrong thing for Recs 1–4.

### 9.5 Owner decisions (resolved 2026-06-03) — and how they reshape the plan

- **9.2.1 → Ingestion was always hand-run; no external scheduler exists.** The plan must **build freshness automation from scratch** (no broken external trigger to restore). Simplest fit: a scheduled caller (Azure cron / the existing job dispatcher) invoking `run_repo_ingestion_workflow` for the ~9 real repos.
- **9.2.2 → The 3-store retrieval engine is INFRASTRUCTURE for the MAWF platform, not a first-class product.** This is the decisive steer: **right-size, don't invest** in the code-retrieval-specific capabilities.

**Resulting recommendation re-rank (supersedes the §7 ordering):**

| Rec | New disposition under "MAWF-infra + hand-run" |
|---|---|
| **1. Automate ingestion** | **DO** — but scope to repos MAWF actually reasons over; freshness matters because stale infra degrades the agent platform. Build a scheduled trigger. |
| **4. Operationalize maintenance** (audit + expose compaction as a tool, scheduled) | **DO** — keeps the infra healthy/bounded with low effort; highest value-per-effort now. |
| **2. Code-knowledge memory layer** (`learned_records`) | **SHELVE** — unused, and not the product. Formally deprioritize/park it to shed carrying cost rather than drive adoption. |
| **3. Neo4j** | **RIGHT-SIZE / treat as optional** — already degraded-tolerant; at 1.7% usage and infra role, don't invest in promotion. **Dependency check (resolved):** MAWF/triage/planning/intake have **zero** Neo4j usage; retrieval/ingestion/context-assembly all degrade gracefully; only `impact_analysis` (1.7%) + `integrity_audit`/`repair_rebuild` hard-require it. So Neo4j is safely optional — keep minimal now; full removal is feasible later (cost: lose impact_analysis; make 2 maintenance tools graph-optional). |
| **5. Human feedback** | **DEPRIORITIZE** — router self-tuning is low-value when retrieval is MAWF support. |

**Net:** the plan collapses to two active workstreams — **(1) automate ingestion freshness** and **(4) operationalize the maintenance/compaction we built** — plus explicit **shelve/right-size decisions** for the memory layer, Neo4j, and feedback. Remaining inputs before a one-shot plan: success metrics (9.2.3 — freshness SLA, repo scope) and confirming no MAWF hard-dependency on Neo4j (9.2 / Rec 3).
