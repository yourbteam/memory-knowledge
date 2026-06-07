# Plan: fix `search_qa_knowledge` always returning empty (qa-suggest)

**Source of truth:** `docs/qa-suggest-not-returning-findings.md` (Candidates 1–3) +
the live diagnosis below (run 2026-06-07 against the deployed Supabase + Qdrant).

**Scope:** memory-knowledge side only, the full set **#1–#5**:
1. Lexical fallback when semantic returns zero candidates (Candidate 2).
2. Lower `min_similarity` for advisory suggestions, made configurable (Candidate 3).
3. Info logging of `repository_key` + result counts on ingest and search.
4. Reconcile the embedding config (env files vs deployed reality).
4b. Startup dimension-guard: fail loud on a collection/config vector-size mismatch.
5. Tests for the new behavior (incl. rewriting one test that pins the current bug).

**Execution rule (per CLAUDE.md):** each step is a discrete, approval-gated change.
Present the exact diff → wait for approval → apply → run the step's validation gate →
next step. memory-knowledge ships and is verified before any MAWF-side change.

---

## Confirmed diagnosis (what the live data proved)

| Check | Result | Verdict |
|---|---|---|
| `memory.qa_pairs` rows | 12 (taggable-server 8, neocurrency-dashboard 4, all active) | Ingest works → **Candidate 1 ruled out** |
| `ALLOW_REMOTE_WRITES` / `DATA_MODE` (deployed) | `true` / `remote` | Write guard not blocking |
| Qdrant `qa_pairs` vectors | 12/12 present, 768-dim, status green, payloads correct | "missing embeddings" ruled out |
| Self-match (stored vector vs collection) | score **1.0**, passes 0.65; repo filter works | Search path healthy |
| Distinct same-repo question scores | **0.49–0.60**, all **below 0.65** | **Operative cause** |
| All Qdrant collections vector size | **768 / Cosine** (code_chunks 54,878 … qa_pairs 12) | Deployed runs bge-base/768/local |

**Root cause (Candidate 3, confirmed):** `min_similarity = 0.65` is too high for advisory
Q&A retrieval; real questions are *near*-identical (≈0.5–0.6), not byte-identical. Because
`search_qa_knowledge` is semantic-only and returns empty when nothing clears the threshold
(`qa_memory.py:192-194`, lexical fallback wired only for `qdrant_client is None`), every such
query yields `rows: []`.

**Embedding consistency:** deployed uses the **code defaults** (`provider=local`,
`BAAI/bge-base-en-v1.5`, 768) for both ingest and search — so exact questions *would* score
~1.0. The repo's `.env`/`.env.remote` declare `text-embedding-3-small`/1536, which is **stale
and self-contradictory** (fastembed can't load an OpenAI model name; 1536 ≠ the 768 collections).
Harmless today only because the deployed container ignores those values. Step 4 fixes the files
so nobody "repairs" them into an outage.

---

## Dependency graph

```
Step 1  (#4  env files, no code) ── independent, do first
Step 1b (#4b dimension-guard, code) ── after Step 1
Step 2  (#1  lexical fallback) ─┐
Step 3  (#2  threshold+config) ─┼─► Step 5 (#5 tests) ─► Step 6 (validation gate)
Step 4  (#3  logging) ──────────┘
```
Steps 2–4 all edit `qa_memory.py` (Step 3 also `config.py` + `server.py`); apply in one
review pass or sequentially. Step 1b edits `db/qdrant.py` independently. Step 5 depends on 1b–4.

---

## Step 1 — #4 Reconcile embedding config (no runtime change)

**Why:** all five env files — `.env:33-34`, `.env.example:39-40`, `.env.local.example:39-40`,
`.env.remote:33-34`, `.env.remote.example:30-31` — set `EMBEDDING_MODEL=text-embedding-3-small`
and `EMBEDDING_DIMENSIONS=1536`, with `EMBEDDING_PROVIDER` unset (→ code default `local`,
`config.py:57`). That trio is self-contradictory: `provider=local` passes `EMBEDDING_MODEL` to
fastembed as the model name (`local_embed.py:32,48`), which cannot load an OpenAI name, and
1536 ≠ the live collections' 768. The files are a latent landmine.

**Deployed reality (inferred, not directly observed):** every Qdrant collection is 768-dim
(`code_chunks` 54,878 … `qa_pairs` 12; measured 2026-06-07), and the 4 `neocurrency-dashboard`
pairs were embedded at 768 dims *today*. A `local` provider with `text-embedding-3-small` would
have raised in fastembed and stored nothing; since today's ingest produced 768-dim vectors, the
deployed runtime must be running the code defaults (`local` / `BAAI/bge-base-en-v1.5` / 768) and
does **not** load these repo files' embedding values. The deployed env vars were not inspected
directly; this step edits repo files only and must not be read as changing deployed behavior.

**Action:** in each of the five files above, set the embedding block to match the 768 reality
and code defaults:
```
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DIMENSIONS=768
```
Add a one-line comment above it: `# dims MUST equal existing Qdrant collection size (768);
changing it requires a full re-embed (integrity/reembed_collections.py).`

**Hardening:** the startup dimension-guard is now **in scope as Step 1b** (resolved decision 2).

**Do NOT** change deployed runtime — it is already correct via defaults.

**Validation gate:** `grep -nE "EMBEDDING_(MODEL|DIMENSIONS|PROVIDER)" .env .env.example .env.local.example .env.remote .env.remote.example`
shows `local` / `BAAI/bge-base-en-v1.5` / `768` in all five; `git diff --check`;
`git diff --name-only` lists only those five env files.

---

## Step 1b — #4b Startup dimension-guard (code; small, approval-gated)

**File:** `src/memory_knowledge/db/qdrant.py`, in `ensure_collections` (`qdrant.py:31`).

**Why:** defuse the *failure mode* behind #4, not just the files. A future env change back to 1536,
or a fresh deploy that creates a collection at a different size than the existing 768 ones, would
otherwise break search **silently** (dimension mismatch → empty/erroring queries). Fail loud at
startup instead. The guard passes today (all collections are 768, matching the bge-base default).

**Action:** in `ensure_collections`, for each collection that **already exists** (skip ones being
freshly created — those are created at `settings.embedding_dimensions` and are inherently
consistent), read its configured vector size (`info.config.params.vectors.size`, the same field
the diagnosis used) and compare to `settings.embedding_dimensions`. On mismatch, emit a structured
`logger.error("qdrant_collection_dim_mismatch", collection=…, stored=…, configured=…)` and raise a
`RuntimeError` naming the collection, the stored size, the configured size, and pointing the
operator to `integrity/reembed_collections.py`. Hard-fail at startup is intended (a mismatched
collection means search is already broken); if availability is a concern, the softer variant is
warn-loud + refuse writes via the existing guard — but default to hard-fail.

**Acceptance / validation:** unit test with a fake Qdrant client whose `get_collection` reports
`size=768` while `settings.embedding_dimensions=1536` → `ensure_collections` raises with **both**
sizes in the message; equal sizes → no raise; a not-yet-existing collection → created, no raise.

**Validation gate:** `python -c "import memory_knowledge.db.qdrant"` clean; the new test passes.

---

## Step 2 — #1 Lexical fallback when semantic returns zero candidates

**File:** `src/memory_knowledge/qa_memory.py`, in `search_qa_knowledge`.

**Why:** root-cause-independent. If semantic clears nothing (threshold or any future embedding
drift), an exact/overlapping question still matches via Postgres full-text.

**Change:** replace the early empty-return (currently `qa_memory.py:192-194`)
```python
    # Semantic ran and found nothing → return empty (matches search_triage_cases:762-768).
    if qdrant_client is not None and not fallback_to_lexical and not candidates:
        return {"advisory_only": True, "rows": [], "warnings": warnings}
```
with a fall-through to lexical:
```python
    # Semantic ran but nothing cleared the threshold → try lexical before giving up.
    # An exact/overlapping question still matches via full-text even when the embedding
    # similarity is below min_similarity.
    if qdrant_client is not None and not fallback_to_lexical and not candidates:
        fallback_to_lexical = True
        warnings.append("No semantic matches above threshold; using lexical fallback.")
```
The existing `if fallback_to_lexical:` block then runs the `ts_rank` query. No other change.

**Note:** semantic returning *some* (but < limit) candidates still short-circuits lexical — only
the zero-candidate case falls through. Intended.

**Validation gate:** see Step 5 (`test_search_semantic_empty_*`).

---

## Step 3 — #2 Lower `min_similarity`, make it configurable

**Why:** measured intra-repo floor is 0.49; 0.65 filters genuine matches. **Locked at 0.45**
(resolved decision 1) — just under the 0.49 floor, with the lexical fallback as the safety net for
anything below it; tunable without a redeploy via a Settings field.

**3a. `src/memory_knowledge/config.py`** — add to `Settings`:
```python
    # Advisory Q&A retrieval: minimum cosine similarity to surface a suggestion.
    # Measured intra-repo near-duplicate scores are ~0.49–0.60; 0.65 over-filtered.
    qa_search_min_similarity: float = 0.45
```

**3b. `src/memory_knowledge/qa_memory.py`** — change the param default
`min_similarity: float = 0.65` → `min_similarity: float = 0.45` (used by direct callers/tests).

**3c. `src/memory_knowledge/server.py`** — in the `search_qa_knowledge` MCP tool
(`server.py:1623-1648`): make the tool param default `None` and resolve from settings so the
deployed threshold is config-driven:
```python
    min_similarity: float | None = None,
    ...
    settings = get_settings()
    data = await _qa_memory.search_qa_knowledge(
        get_pg_pool(), settings,
        repository_key=repository_key, question=question, limit=limit,
        min_similarity=(min_similarity if min_similarity is not None else settings.qa_search_min_similarity),
        qdrant_client=get_qdrant_client(),
    )
```

**Out of scope (note only):** surfacing below-threshold rows flagged low-confidence. Lowering the
threshold + lexical fallback already covers the observed gap; revisit if suggestions are still
sparse after deploy.

**Validation gate:** Step 5's `test_tool_search_resolves_threshold_from_settings` asserts the
**server tool** resolves `None` → `settings.qa_search_min_similarity` and forwards it to
`query_points` (the deployed path), and that an explicit `min_similarity` overrides it.

---

## Step 4 — #3 Info logging of `repository_key` + counts

**File:** `src/memory_knowledge/qa_memory.py` (structlog `logger` already imported, `qa_memory.py:17`).

**`ingest_qa_pairs`** (`qa_memory.py:71`):
- first line of the body: `logger.info("qa_ingest_start", repository_key=repository_key, pairs=len(pairs))`
- immediately before the single `return` (`qa_memory.py:148`):
  `logger.info("qa_ingest_done", repository_key=repository_key, ingested=len(qa_pair_ids), skipped=len(skipped))`

**`search_qa_knowledge`** (`qa_memory.py:155`) has three real exits — unknown-repo (`:168`), the
threshold/lexical-empty return (`:214`), and the success return (`:241`). Log at every exit so
empty results are visible (the step's purpose), and capture the semantic count *before* the
Step-2 lexical fallback can overwrite `candidates` (`:211`):
- right after the semantic block and before the Step-2 fallback assignment, add
  `semantic_hits = len(candidates)` (0 when Qdrant is None or failed).
- before the unknown-repo return (`:168`):
  `logger.info("qa_search_done", repository_key=repository_key, returned=0, reason="unknown_repository")`
- before the empty return (`:214`):
  `logger.info("qa_search_done", repository_key=repository_key, question_len=len(question), semantic_hits=semantic_hits, lexical_used=fallback_to_lexical, returned=0)`
- before the success return (`:241`):
  `logger.info("qa_search_done", repository_key=repository_key, question_len=len(question), semantic_hits=semantic_hits, lexical_used=fallback_to_lexical, returned=len(rows))`

**Why:** makes an ingest/search `repository_key` mismatch and every empty-result case visible
(addresses Candidate 1b / the cross-repo note without needing a DB dig next time).

**Validation gate:** `python -c "import memory_knowledge.qa_memory"` clean; no signature changes;
Step 5 tests still pass.

---

## Step 5 — #5 Tests

**File:** `tests/test_qa_memory.py`.

- **Rewrite** `test_search_semantic_empty_does_not_lexically_fallback` (lines 225-238) — it pins
  the *current bug*. New intent `test_search_semantic_empty_falls_back_to_lexical`: ingest a row,
  then search with `EmptyQdrant()` (its `query_points` returns no points, `test_qa_memory.py:34-37`)
  so semantic yields zero candidates → the Step-2 fallback runs. Assert `len(rows) == 1` and a
  `"lexical fallback"` warning. Note: `QAPool.fetch`'s `ts_rank` branch (`test_qa_memory.py:74-75`)
  returns all stored rows regardless of token match, so the assertion holds for any question text.
- **Add** `test_search_threshold_from_settings`: `semantic_query_points` forwards
  `score_threshold=min_similarity` to `query_points` (`db/qdrant.py:85-91`), captured by
  `FakeQdrant.query_calls` (`test_qa_memory.py:23,29`). Assert `qdrant.query_calls[0]["score_threshold"]
  == 0.45` with the default settings, and that an explicit `min_similarity` override is forwarded.
- **Add** `test_tool_search_resolves_threshold_from_settings` (server level, R7): under the
  `qa_env` fixture (`test_qa_memory.py:278-283`, which patches `server.get_settings`/`get_pg_pool`/
  `get_qdrant_client`), call `server.search_qa_knowledge(repository_key="taggable-server",
  question="q")` and assert `qdrant.query_calls[0]["score_threshold"] == SETTINGS.qa_search_min_similarity`;
  then call again with an explicit `min_similarity=0.9` and assert the override is forwarded.
  Requires the test `SETTINGS` object to carry the new `qa_search_min_similarity` field (Step 3a).
- **Add** (required) `test_search_logs_empty_result`: capture structlog and assert a
  `qa_search_done` event fires on the threshold-empty path with `repository_key`, `returned=0`,
  and `lexical_used` present (verifies R4 substantively, not just import-clean).
- **Keep** `test_search_round_trip` / `test_search_lexical_fallback_when_qdrant_none` green
  (FakeQdrant returns a fixed 0.83 score, threshold-independent — unaffected).
- Optional cleanup: assert the `qa_ingest_start`/`qa_ingest_done` events fire.

**Validation gate (Step 6):** run on a platform where fastembed/onnxruntime install (Linux/CI or
deployed) — local macOS x86_64 cannot install `onnxruntime`. qa_memory tests mock `embed_single`
and Qdrant, so they need no real model:
```
pytest tests/test_qa_memory.py -q
```
Then deploy + prod re-check: call `search_qa_knowledge` for `thebteambg/neocurrency-dashboard`
with a near-duplicate of a stored question → expect ≥1 advisory row.

---

## Out of scope (this repo) — workflow-orch (mcp-agents-workflow) handoff

Confirmed callers: `src/workflow_orch/feedback_qa_capture.py`, `workflow_engine.py`, `mcp_server.py`.
These changes live in the **workflow-orch** repo, not memory-knowledge — but item 1 is a **hard
co-blocker for R1 end-to-end**, so the memory-knowledge fix alone produces no user-visible effect
until it lands.

1. **REQUIRED (R1 end-to-end) — `handle_qa_suggest` envelope unwrap.** memory-knowledge
   `search_qa_knowledge` returns a `WorkflowResult` envelope — `{run_id, tool_name, status,
   data:{advisory_only, rows, warnings}}` (`server.py:1649-1654`, `workflows/base.py:8-14`).
   `knowledge_client.call_tool_json` returns that **full envelope**, no unwrap
   (`knowledge_client.py:314-319,364-395`). But `handle_qa_suggest` reads `rows`/`warnings` at the
   **top level** — `(data).get("rows")` (`mcp_server.py:15941,15946`) — which is `None` because
   `rows` lives at `data["data"]["rows"]`. Result: qa.suggest surfaces `[]` for every question
   regardless of the threshold/lexical fix. **Fix:** unwrap — `env = await client.call_tool_json(...)`;
   `payload = (env or {}).get("data") or {}`; `rows = payload.get("rows") or []`;
   `warnings = payload.get("warnings") or []`; treat `env.get("status") == "error"` as no-rows +
   warning. Add a workflow-orch test feeding a `WorkflowResult`-shaped envelope and asserting
   `rows` surface.
2. **Observability (nice-to-have):** `feedback_qa_capture` should **log** the `ingest_qa_pairs`
   result (status/error) instead of discarding it, so a blocked/failed ingest is never silent.
3. **`repository_key` symmetry — VERIFIED, no fix needed.** Producer (ingest) passes
   `workflow_state.context["repository_key"]` (`workflow_engine.py:13021`); consumer (search)
   resolves `remote_run["repository_key"]`/`context_json["repository_key"]`
   (`mcp_server.py:15896-15898`) — same context key, and live rows are stored under canonical keys
   (`taggable-server`, `thebteambg/neocurrency-dashboard`). Cross-task accumulation holds.

**R1 end-to-end acceptance** (the Step 5 prod re-check) requires **both** the memory-knowledge
change *and* the workflow-orch unwrap (item 1) to be deployed; either alone surfaces nothing.

---

## Resolved decisions

1. **Threshold value → `0.45`.** Just under the measured 0.49 near-dupe floor; the lexical
   fallback catches token-overlapping questions below it, so no need to go lower (0.40 = noise).
   `0.50` rejected (would drop the 0.49 case). Tunable later via `qa_search_min_similarity`.
   → locked in **Step 3**.
2. **Startup dimension-guard → include now**, as a small, separate, approval-gated step.
   Cheap insurance against a recurrence of exactly the #4 landmine; hard-fail at startup on a
   collection/config size mismatch. → now **Step 1b**.
3. **Low-confidence below-threshold rows → defer.** With 0.45 + lexical fallback the gap is
   narrow and it adds consumer complexity/noise. Revisit only if post-deploy suggestions stay
   sparse. → noted out-of-scope in **Step 3**.

**Rollout sequencing (from the satisfaction pass):** ship memory-knowledge (Steps 1–5) → deploy →
land the workflow-orch `handle_qa_suggest` unwrap (handoff item 1) → run the Step 5 prod re-check.
The memory-knowledge fix is **user-invisible** until the unwrap also ships, so don't read an empty
qa.suggest after the mk-only deploy as the fix failing.
