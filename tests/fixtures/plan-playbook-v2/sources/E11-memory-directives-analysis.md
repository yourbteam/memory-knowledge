# Gaps in Our Memory/Directives Approach vs Nate's Open Brain

**Prepared:** 2026-06-20 · **Mode:** Research (comparison/findings; no changes made) · **Author:** Claude, for Kamen
**Inputs compared:**
- *Our approach* — the Working Agreement directives (G0–G9), the `memory-knowledge` Tier-2 corpus (`corpus_query`), the file-based memory store (`~/.claude/.../memory/`, `MEMORY.md`), and the `CLAUDE.md` instruction files. Verified directly via the directives file, `corpus_query`, `list_repositories`, and the `corpus-add` skill description.
- *Nate's approach* — the OB1 / Open Brain brief (`open-brain-brief.md`), grounded in the OB1 repo.

> **Framing caveat (read first).** OB1 and our system are not the same kind of thing. OB1 is a *personal retrieval-memory product* optimized for frictionless capture, ownership, and portability across AI apps. Our system is a *governance + curated-knowledge layer* for an AI coding assistant, optimized for rigor, human confirmation, and self-improvement. So not every OB1 pattern should be copied — several would actively hurt us (see §3). This document extracts only the OB1 design principles that would genuinely make *our* approach better, and is explicit where the analogy breaks.

> **R1 (cite or flag):** Every gap below cites what I verified on each side. The one originally-unverified premise (§5, corpus retrieval ranking) was **resolved in the Gate-3 depth pass** against the live tool schemas; remaining inferences (e.g. §3's absence claim) are labelled inline.

---

## 1. The headline gap — our memory is fragmented across four stores; OB1's core principle is *one* store

**Practical consequence.** The same durable fact can live in — or fall between — four places: a `CLAUDE.md` instruction, a file in `~/.claude/.../memory/`, a Tier-1 directive, or a Tier-2 corpus entry. When you (or I) go looking for "what do we know about X," there is no single place that answers it, and a fact written to one store is invisible to the others. This is exactly the failure mode OB1 was built to kill ("every AI you use forgets you because your memory is siloed"), but our siloing is *internal*.

**Evidence.**
- *Ours:* four distinct stores with different write paths, retrieval mechanisms, *and storage engines* — directives (hook-injected, "lock it"), corpus (`corpus_query` MCP, stored in **PG + Qdrant**, global/not repo-scoped), file-memory (`MEMORY.md` index + frontmatter `type:` user/feedback/project/reference), and `CLAUDE.md` (global + project). The file-memory and the corpus even use *overlapping but different* taxonomies — file-memory `type:` is user/feedback/project/reference; corpus `kind` is "directive rationale, playbook detail, example, reference" (verbatim from `run_corpus_upsert_workflow`). Our vectors live in a *separate* store (Qdrant), unlike OB1's in-Postgres pgvector — one more moving part.
- *OB1:* "One database, one AI gateway, one chat channel" (`README.md:7`); a single `thoughts` table is the sole source of truth, and the guard rail is *never fragment the core* (`CLAUDE.md`: "Never modify the core `thoughts` table structure").

**What OB1 would have us do.** Pick one authoritative store and make the others *projections* of it, not parallel truths, so nothing lives in two places with two lifecycles.

> **Depth-pass refinement:** this is already *partly* realized — `sync_corpus.py` makes the **corpus mirror `DIRECTIVES.md`** (file→corpus full mirror + prune via `corpus_deactivate`). So the file is the source of truth and the corpus is its projection; the live fragmentation is narrower than "four independent truths."

### Target architecture (Kamen's decision, 2026-06-20)

**`DIRECTIVES.md` stays the single authoritative, human-authored directive file** — it is what is actually injected, and the corpus already mirrors it. Every other surface becomes a **generated projection of it (or of the brain it mirrors), never an independent source**:

1. **Claude Code** — already a projection (the `inject-directives.sh` `UserPromptSubmit` hook injects `DIRECTIVES.md` every prompt). No change to the source-of-truth role.
2. **Codex** — *new work.* Today Codex receives **no directives** (its `~/.codex/config.toml` wires the `memory-knowledge` MCP but has no directive injection; `SETUP-claude.md` flags "Codex plumbing … added later"). Add a Codex projection so the same `DIRECTIVES.md` reaches Codex (via a generated `AGENTS.md` and/or a Codex-side inject), making the file authoritative for **both** tools.
3. **`CLAUDE.md` and `AGENTS.md` are demoted to ignorable, generated pointers** — but only **after** their durable content is distilled into `DIRECTIVES.md`/the brain. Un-distilled content that must move first: global `~/.claude/CLAUDE.md` ("never invent API/DB schema/column names"; "granular change-by-change plan, wait for approval"); `~/CLAUDE.md` ("no `Co-Authored-By: Claude`" + repo mappings); `~/AGENTS.md` (repo index, duplicates the mappings).
4. **file-memory** (`~/.claude/.../memory/`) folds into the same model — either projected from the brain or retired into it — so it stops being a fourth independent truth.

Net: **one authored source (`DIRECTIVES.md`) ⇄ one brain (corpus mirror) → many generated, disposable projections.** Editing stays a file-edit + "lock it"; the brain gives cross-tool retrieval + portability; no hand-authored file can silently drift.

**Cost.** Highest-effort gap. New pieces: a Codex directive projection, a brain→`CLAUDE.md`/`AGENTS.md` pointer generator, a one-time distillation migration of the four files' durable content, and resolving the Claude(local `:8000`) vs Codex(Azure) endpoint split so both tools read a consistent brain.

---

## 2. Capture is high-friction and non-habitual; OB1's whole thesis is that capture must be effortless

**Practical consequence.** A useful lesson learned mid-session (a worked example, a gotcha, a "that approach didn't work") only reaches Tier-2 if someone *deliberately* runs `corpus-add` for it. In practice that means most session-level knowledge evaporates, because the bar to capture is a conscious curation act. We get the lesson into memory only when it's painful enough to become a directive — i.e., after it has already cost us.

**Evidence.**
- *Ours:* the `corpus-add` skill is explicitly "on demand … Do not use it for one-off conversation notes or for bulk loading." Directives are added reactively — every G-rule's "Why:" is a past failure (G2 "broken the same day it was set," G4 "asked to test the MCP, Claude … silently ran a different test"). Capture follows damage.
- *OB1:* capture is one sentence from any client ("Remember this: …"), plus dedicated low-friction sources (Slack/Discord/Telegram capture) and **Auto-Capture** (saves action items + session summary at session close) and **Panning for Gold** (mines transcripts for ideas). The design assumption is that *friction is the enemy of memory*.

**What OB1 would have us do.** Add a low-friction, session-close auto-capture path that writes *candidate* knowledge to an evidence tier, to be curated/promoted later — rather than requiring a deliberate `corpus-add` each time. **Note — two distinct subsystems, not one pipeline:** we have a propose→approve mechanism for *repository-scoped* learned memory — `run_learned_memory_proposal_workflow` ("Propose a learned-memory candidate backed by evidence"; takes `evidence_entity_key` + `confidence`) → `run_learned_memory_commit_workflow` ("Approve, reject, or supersede"). But that is **repo-scoped and evidence-backed**, and it does **not** auto-feed the **global** Tier-2 corpus, which is written manually via `run_corpus_upsert_workflow` ("global, not repository-scoped") / the `corpus-add` skill. So the building blocks (an evidence tier + an approval gate) exist, but there is no habitual, low-friction path from a session into either store. The capability is partial; the ritual doesn't exist.

**Cost.** Low–medium (an evidence-tier mechanism already exists for repo-scoped memory; the global-corpus path would need new wiring). Main risk is corpus noise — mitigated by keeping auto-captures in an evidence/candidate tier (which aligns with our existing trust-tier model, §"Where we are already ahead").

---

## 3. Our directives are reactive-only; OB1 invests in *proactive discovery* of what to capture next

**Practical consequence.** We only learn from mistakes we've already made — a directive appears after a lapse, never before. There is no forward-looking pass that says "your recent sessions show a recurring pattern that no directive covers yet." So the same *class* of mistake can recur in a new form before it earns its rule.

**Evidence.**
- *Ours:* G0–G9 are each retrospective ("**Why:** Claude …"). We have the raw signal for proactive work — `get_finding_pattern_summary`, `get_clarification_policy`, `get_triage_confusion_clusters`, `get_agent_failure_mode_summary`. **[INFERENCE — absence, not verified exhaustively]:** among the available `memory-knowledge` tools I found none that turns that telemetry into *candidate directives before they bite* (the proposal workflow in §2 takes a hand-authored candidate; it does not mine the analytics itself). If such a routine exists outside the exposed toolset, this gap narrows to "not wired into the directive lifecycle."
- *OB1:* **Open Brain Spark** (personalized use-case discovery — "what should you capture, based on your actual workflow") and the **Extension Matchmaker** (interviews you and recommends what to build next). OB1 treats "help the user discover what's worth remembering" as a first-class feature.

**What OB1 would have us do.** A periodic "directive Spark": mine our own failure-pattern/clarification analytics and surface *proposed* directives (and corpus gaps) for you to accept or reject — converting our self-improvement data, which today is read on demand, into a proactive proposal stream.

**Cost.** Medium. Data and tools already exist; the work is the synthesis routine + a review surface. Risk: proposal spam — bound it to high-frequency patterns only.

---

## 4. Our working agreement is tool-bound; OB1's defining principle is portability across *any* AI client

**Practical consequence.** The Tier-1 directives are enforced only inside Claude Code (they arrive via a Claude Code hook). The moment you work in ChatGPT, Cursor, or Gemini, none of the G-rules travel with you — the "way you work" is not portable, which is precisely the thing OB1's companion *Open Skills* is built to fix ("keeps the way you work yours, not rented back by whichever AI app wins").

**Evidence.**
- *Ours:* directives are injected as a per-turn hook (Claude Code-specific). The corpus *is* reachable as an MCP (so it could be queried from other clients), but the authoritative directive layer is not exposed as a portable, client-agnostic read path.
- *OB1:* "any MCP-capable AI client … one URL, no extra config"; explicitly client-agnostic by design, with the same memory available to Claude, ChatGPT, Cursor, Gemini, Grok.

**What OB1 would have us do.** Expose the directives as a retrievable corpus `kind` (they already are — `directive_rationale` entries exist) and connect the `memory-knowledge` MCP to your other AI clients the way OB1 connects one URL everywhere, so the working agreement is consultable wherever you work — not just in Claude Code.

**Cost.** Low–medium. Mostly already possible (corpus is an MCP; directive rationale is already in it). The missing piece is a portable, authoritative *Tier-1* read path and wiring it into other clients.

---

## 5. Corpus retrieval is similarity-only and has no relevance floor; OB1 weights recency and exposes a threshold

**Practical consequence.** If an older or superseded-but-textually-similar rationale outranks a newer, more applicable one, the wrong guidance gets injected as "relevant background" — and because it arrives as authoritative-looking context, the error is invisible. There's also no minimum-relevance floor, so weakly-related entries can still be injected as background noise. OB1 hit both problems and added a recency dimension and a tunable threshold on purpose.

**Evidence.**
- *Ours (confirmed at the tool surface — depth pass):* `corpus_query`'s schema exposes only `query_text`, `limit`, `kind`, and `link_slug` — **no recency parameter and no similarity threshold** — and observed results are ordered by descending `score` alone. The repo-scoped retrieval path (`run_retrieval_workflow`, `run_context_assembly_workflow`) likewise exposes no recency knob. *Caveat:* internal ranking inside those workflows isn't externally observable, so this is "no recency/threshold at the exposed surface," not a claim about hidden internals.
- *OB1:* ships a dedicated `recency-boosted-match-thoughts` schema — i.e., they found pure cosine similarity insufficient and added recency boosting as a first-class retrieval mode, plus a user-tunable `match_threshold` to widen/narrow recall.

**What OB1 would have us do.** Add a recency/authority term and a minimum-relevance threshold to corpus retrieval/injection, so freshness and a relevance floor shape what gets injected — not similarity alone.

**Cost.** Low–medium to add a recency term + threshold (the `score` and entry timestamps already exist to build on).

---

## 6. Surface-area sprawl undermines G1 ("keep Kamen in grasp"); OB1's superpower is radical simplicity

**Practical consequence.** Our own directive G1 says detail must stay inside what you can track — yet the memory platform's surface area works against that. `list_repositories` returns 56 repositories, of which only **9 have any content** (`file_count > 0`); the other **47 are empty `mawf-*` / `repo-…-example.invalid` test artifacts** mixed in with the real ones. Anyone (you or an agent) inspecting "what's in our memory" wades through clutter to find signal, which is the opposite of "in grasp."

**Evidence.**
- *Ours:* 56 repos in `list_repositories`; the 9 with content are css-scheduler, css-fe, fcs-admin, fcsapi, millennium-wp, neocurrency-dashboard, taggable-api, taggable-server, tpp-petkey. The remaining 47 (`mawf-live-repo-*`, `mawf-lease-*`, `repo-…-example.invalid`) have `file_count: 0`. The platform also spans many tool families (MAWF orchestration, triage, behavior policy, …).
- *OB1:* "one Postgres database, one MCP server, every AI"; ~30-minute setup, deliberately minimal core, additive extensions only. Legibility is the design goal.

**What OB1 would have us do.** Prune or namespace test/smoke artifacts out of the primary listings, and keep a deliberately small "core" surface that a human can hold — treating legibility as a feature, the way OB1 does. (This is housekeeping, not architecture, but it directly serves G1.)

**Cost.** Low. Mostly cleanup + a naming/visibility convention.

---

## 7. No enforced review/consolidation cadence; OB1 makes the Weekly Review a ritual

**Practical consequence.** The directives carry a manual "Last reviewed: 2026-06-19" stamp, but nothing *makes* the review happen — so drift (stale rationale, duplicate corpus entries, dead links) accumulates silently between ad-hoc cleanups.

**Evidence.**
- *Ours:* we have the *tools* (`consolidate-memory` skill, `run_compaction_workflow`, `run_integrity_audit_workflow`) but no scheduled cadence; the review stamp is hand-maintained.
- *OB1:* **The Weekly Review** is a named, recurring ritual in the five-prompt lifecycle ("a Friday ritual that surfaces themes, forgotten action items, and connections"), backed by consolidation workers.

**What OB1 would have us do.** Put the consolidation/integrity pass on a real cadence (e.g., a scheduled routine) so review is a ritual, not a remembered chore.

**Cost.** Low. Schedulable with existing tooling.

---

## 8. Retrieved memory isn't cited back to its source; OB1 makes every memory individually linkable

**Practical consequence.** When a corpus entry shapes a decision, the response doesn't say *which* entry did — the Tier-2 corpus arrives as "relevance-ranked background" and gets absorbed silently. So there's no audit trail from an action back to the memory that drove it, and a wrong or stale entry that influenced an answer is hard to trace and retract. This directly undercuts our own G0 value ("anchor compliance to a *checkable artifact*").

**Evidence.**
- *Ours:* `corpus_query` returns `entry_key` (UUID) and `link_slug` per result, so entries *are* addressable — but nothing in the retrieval/injection path requires citing the entry that informed a response. Citation is by convention (we cite `link_slug` like `g0` for directives), not enforced.
- *OB1:* every thought is individually fetchable by a stable URL — `fetch` returns `url: thoughtUrl(id)` (`OB1-main/server/index.ts:42-43`), and the ChatGPT `search`/`fetch` shape exists precisely so retrieved memories can be **cited** in answers.

**What OB1 would have us do.** Treat each retrieved corpus entry as a citable artifact: when an entry materially informs an action, reference its `entry_key`/`link_slug` so the decision is traceable back to its memory — making retrieval auditable, not just injected.

**Cost.** Low. The handles (`entry_key`, `link_slug`) already exist; the change is a citation convention/enforcement, not new storage.

---

## Coverage of the remaining OB1 differentiators (addressed or scoped out)

For breadth: the OB1 principles not covered by §1–§8 above, each with an explicit disposition so none is silently dropped. Grounding in the Evidence appendix.

| OB1 principle | Disposition for us | Rationale (grounded) |
| --- | --- | --- |
| **Dedup of near-identical entries** (OB1 `content_fingerprint` upsert-merge) | **Parity** | We supersede instead of fingerprint-merge: `corpus_deactivate` + `supersedes_id` on `run_corpus_upsert_workflow`. Equivalent effect; no gap. |
| **Model / embedding swappability** (OB1 one-line OpenRouter swap, `getting-started:913`) | **Gap (larger than it first looks)** | *Depth pass:* `run_embedding_backfill` is **repository-scoped and backfills only *missing* embeddings from PG** ("Backfill missing Qdrant embeddings from PG canonical") — it is **not** a global-corpus full re-embed on a model change, and there is no documented model-gateway indirection like OB1's OpenRouter. So swapping the corpus embedding model has no clean documented path today. |
| **Cost / operational footprint** (OB1 ~$0.10/mo, `brief:207`) | **Accepted tradeoff** | Our PG + Qdrant + workflow stack is far heavier than OB1's two services. We deliberately buy rigor/self-improvement with that complexity (see §6 and "Where ahead"); not a defect, but the cost is real and worth naming. |
| **Chunking long content + hybrid metadata+vector filtering** (`faq:119,135`) | **Parity** | `corpus_query` already supports `kind` + `link_slug` filters alongside semantic search (hybrid), and corpus entries are atomic by design (like OB1's "one idea per entry"). No gap. |
| **Sharing / RLS / multi-user scoped access** (OB1 `primitives/rls`, `shared-mcp`) | **Out of scope** | Our working agreement is single-operator (Kamen). If team scope ever arrives, OB1's `shared-mcp` scoped-access pattern is the reference. Deliberately excluded now. |
| **Open extensibility / contribution model** (brief §4.4) | **Parity / ahead** | Our system is already extensible (schemas, workflows, skills, `corpus-add`); extension is additive, mirroring OB1's "extend, don't modify core." No gap. |
| **Migration / bulk import of existing knowledge** (brief §6.2) | **Covered** | We have a bulk backfill path (the `corpus-add` skill notes "bulk loading (that is the backfill script)"). No gap. |
| **Data ownership / export-import portability** (brief §2–3) | **Partial** | *Depth pass:* `export_repo_memory_tool` / `import_repo_memory_tool` are **repository-scoped** ("Export **repository** memory as JSONL"). Repo memory is portable; the **global Tier-2 corpus** has no equivalent export tool — the directives file (plain text) is its portable form. So "covered" holds for repo memory, not for the corpus. |

---

## Where we are already ahead of OB1 (don't regress these by copying it)

OB1 is not strictly better — several of our choices are deliberately *stronger* for a governance system, and naively adopting OB1's frictionless model would damage them:

1. **Trust tiers + human confirmation.** Our Tier-1/Tier-2 split with "lock it" promotion is exactly the discipline OB1 only reaches for in its *Agent Memory* sub-product ("inferred/generated memory is evidence by default; instruction-grade memory requires human confirmation"). Our *core* already works this way. OB1's default capture is ungoverned by comparison.
2. **Contract-first rigor (G8).** "Fix the contract, not an exception garden" has no OB1 analog — OB1's metadata extraction is explicitly "best-effort." For code work, our standard is higher and should stay.
3. **Self-improving analytics.** Our failure-pattern/clarification/triage telemetry is far beyond OB1's scope; OB1 has no feedback loop on its own retrieval quality.
4. **Citable, checkable compliance (G0).** OB1 has nothing like the per-turn directive anchor that makes lapses visible.

**Implication:** the gaps worth closing are the *frictionless-capture, portability, proactive-discovery, single-store, and legibility* ones (§1–§6) — adopt OB1's **ease and unification**, but keep them *behind* our trust-tier gate so we don't trade rigor for convenience.

---

## Suggested priority (if you choose to act — not started)

| # | Gap | Value | Effort |
|---|-----|-------|--------|
| 1 | Make `DIRECTIVES.md` the one authoritative source → project to Claude Code + Codex; distill & demote `CLAUDE.md`/`AGENTS.md`; fold in file-memory (§1) | High | High |
| 2 | Habitual session-close auto-capture into evidence tier (§2) | High | Low–Med |
| 3 | Proactive "directive Spark" from our own analytics (§3) | High | Med |
| 4 | Portable, client-agnostic directive read path (§4) | Med | Low–Med |
| 5 | Add recency + relevance-threshold to corpus retrieval (§5) | Med | Low |
| 6 | Prune test-repo clutter; keep a small core surface (§6) | Med | Low |
| 7 | Scheduled review/consolidation cadence (§7) | Low–Med | Low |
| 8 | Cite retrieved memory back to its `entry_key`/`link_slug` (§8) | Med | Low |

---

## Evidence grounding

Each load-bearing claim and its concrete source, so every assertion is checkable (R1). Paths under `OB1-main/` are the local OB1 repo checkout; "tool desc" = the `memory-knowledge` MCP tool description.

| § | Claim | Evidence |
| --- | --- | --- |
| §1 | OB1 = one database / sole source of truth | `OB1-main/README.md:7`; `OB1-main/CLAUDE.md` guard rail "Never modify the core `thoughts` table structure" |
| §1 | Corpus `kind` values | `run_corpus_upsert_workflow` tool desc: "directive rationale, playbook detail, example, reference" |
| §1 | Corpus stored in PG + Qdrant, global | `run_corpus_upsert_workflow` tool desc: "Written directly to PG + Qdrant; global, not repository-scoped" |
| §1 | OB1 vectors in-Postgres | `open-brain-brief.md` §4.2 (`embedding vector(1536)`, pgvector HNSW index) |
| §2 | `corpus-add` is on-demand, not bulk | `corpus-add` skill description (available-skills list) |
| §2 | OB1 Auto-Capture at session close | `OB1-main/skills/auto-capture/README.md:3,7` ("captures … when a session ends"; "treat session close as a capture moment") |
| §2 | Repo-scoped learned-memory pipeline | `run_learned_memory_proposal_workflow` desc ("Propose a learned-memory candidate backed by evidence") + `run_learned_memory_commit_workflow` desc ("Approve, reject, or supersede") |
| §3 | Analytics tools exist | `get_finding_pattern_summary`, `get_clarification_policy`, `get_triage_confusion_clusters`, `get_agent_failure_mode_summary` (loaded tool schemas) |
| §3 | OB1 Spark + Extension Matchmaker | `open-brain-brief.md` §6.2–6.3 |
| §4 | OB1 client-agnostic / Open Skills thesis | `open-brain-brief.md:148` ("not rented back by whichever AI app wins this month") |
| §5 | Our corpus_query returns similarity score, filters superseded | observed `corpus_query` output (score field; "Filters out inactive/superseded entries") |
| §5 | OB1 recency-boosted matching | `OB1-main/schemas/recency-boosted-match-thoughts/` (directory exists) |
| §6 | 56 repos, 9 with content, 47 empty | `list_repositories` output (count 56; `file_count>0` for 9 named repos) |
| §7 | "Last reviewed" stamp is manual | Working Agreement directives header ("Last reviewed: 2026-06-19") |
| §7 | OB1 Weekly Review + consolidation workers | `open-brain-brief.md` §6.2; `OB1-main/integrations/consolidation-workers/` |
| ahead | Evidence-vs-instruction trust model | `OB1-main/AGENTS.md:54` ("inferred or generated memory as evidence by default. Instruction-grade memory requires human confirmation") |
| §8 | OB1 linkable/citable memory | `OB1-main/server/index.ts:42-43` (`thoughtUrl`); brief §4.3 (`fetch` returns `url`) |
| §8 | Our entries are addressable | `corpus_query` output (`entry_key`, `link_slug` per result) |
| cov | Model swap (OB1) / re-embed (ours) | `OB1-main/docs/01-getting-started.md:913`; `run_embedding_backfill` tool |
| cov | OB1 cost ~$0.10/mo | `open-brain-brief.md:207` |
| cov | OB1 chunking + hybrid filter | `OB1-main/docs/03-faq.md:119,135`; our `corpus_query` `kind`/`link_slug` filters |
| cov | OB1 sharing / RLS | `OB1-main/primitives/rls/`, `primitives/shared-mcp/` |
| cov | Our dedup via supersede | `corpus_deactivate`; `run_corpus_upsert_workflow` `supersedes_id` |
| cov | Our export/import | `export_repo_memory_tool`, `import_repo_memory_tool` tools |
| §5 (depth) | `corpus_query` has no recency/threshold param | `corpus_query` schema: params `query_text`/`limit`/`kind`/`link_slug` only |
| §1 (depth) | directives↔corpus already synced | `corpus_deactivate` desc: "used by the directives sync to prune orphans" |
| §1 (depth) | corpus `kind` is free-form | `run_corpus_upsert_workflow` schema: `kind` is `string`, no enum |
| disp (depth) | export/backfill are repo-scoped | `export_repo_memory_tool` ("repository memory"), `run_embedding_backfill` ("Backfill missing… from PG canonical"), both require `repository_key` |

---

## Status & next step (per research-playbook)

This is a **findings/comparison document** — the requested deliverable. I made no changes to directives, corpus, or any other existing file (only this doc and its sibling audit file).

**This is build-bound** (it could feed an implementation of one or more gaps). All three hardening gates have been run against this document on Kamen's instruction and converged: Gate 1 `doc-gap-closure-loop` (internal readiness), Gate 2 `requirements-coverage-gap-loop` (breadth), Gate 3 `requirements-satisfaction-gap-loop` (depth) — audits in the `.gap-audit.md`, `.coverage-audit.md`, and `.satisfaction-audit.md` siblings. §5's previously-unverified premise was resolved in Gate 3 (corpus retrieval exposes no recency/threshold at the tool surface). The doc is now ready to seed a `plan-playbook` for whichever gap(s) you pick from the priority table.
