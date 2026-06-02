# OpenAI / Codex Auth & Model Research

**Status:** Research / findings (pre-implementation). No fix proposed here yet.
**Date:** 2026-06-02
**Scope:** Why production retrieval fails with OpenAI `429 insufficient_quota`, how the OpenAI/Codex credential and model selection actually work, and the distinct problems an eventual fix must address (embeddings vs. completions).

> **Verification note.** Credential shapes were inspected with values masked (prefix/length/boolean only). Code claims are cited file:line. Statements about OpenAI *Platform vs. ChatGPT-subscription entitlement* are inferred from the observed `429 insufficient_quota` plus the credential type; they are the most consistent explanation, not a quoted OpenAI policy.

---

## 1. Symptom

A production `run_retrieval_workflow` call (fcsapi) returned:
```
status: error
error: "Error code: 429 - ... 'You exceeded your current quota ...',
        'type': 'insufficient_quota', 'code': 'insufficient_quota'"
```
The failure occurs at the **query-embedding step**, before Qdrant semantic search. The PG-only path (`exact_lookup`) is unaffected.

---

## 2. How auth + model selection work today (verified)

- **Auth mode:** prod runs `AUTH_MODE=codex` (`feature: never change this — [[feedback_never_change_auth_mode]]`).
- **API key resolution:** `_get_api_key()` returns, for `auth_mode == "codex"`, the value from `codex_token_provider()` ([openai_client.py:25-31](../src/memory_knowledge/llm/openai_client.py:25)).
- **`codex_token_provider()` returns `tokens["access_token"]`** from `~/.codex/auth.json` ([codex.py:52](../src/memory_knowledge/auth/codex.py:52)) — i.e. the **ChatGPT OAuth JWT**, not a Platform API key.
- That value is then passed straight to the standard SDK: `AsyncOpenAI(api_key=<jwt>)`, with **no custom `base_url`** — so calls hit `api.openai.com`:
  - **Embeddings:** `client.embeddings.create(model=settings.embedding_model, dimensions=settings.embedding_dimensions)` ([openai_client.py:60-69](../src/memory_knowledge/llm/openai_client.py:60)).
  - **Completions:** in `auth_mode == "codex"` (prod), `complete()` returns early via `_complete_via_codex()` → `CodexMcpClient`, which **already shells out to the Codex binary** as a `codex mcp-server` subprocess over JSON-RPC ([openai_client.py:138-170](../src/memory_knowledge/llm/openai_client.py:138), [codex_mcp.py:58-70](../src/memory_knowledge/llm/codex_mcp.py:58)). The `client.chat.completions.create(...)` path ([openai_client.py:141-154](../src/memory_knowledge/llm/openai_client.py:141)) is **only** reached when `auth_mode != codex`. `complete_batch_summaries()` also calls `complete()` ([openai_client.py:316](../src/memory_knowledge/llm/openai_client.py:316)), so every completion path is Codex-routed in prod.
  - **Embeddings:** `embed()`/`embed_single()` have **no codex branch** — they always call `client.embeddings.create(...)` with the JWT ([openai_client.py:60-69](../src/memory_knowledge/llm/openai_client.py:60)). This is the *only* OpenAI dependency in codex mode.

### Model values
| Purpose | Setting | Prod value | Where |
|---|---|---|---|
| Embeddings | `embedding_model` | **`text-embedding-3-small`** (1536-dim) | set in prod app settings |
| Completions | `completion_model` | **`gpt-4o`** (default; **not** overridden in prod) | [config.py:45](../src/memory_knowledge/config.py:45) |

---

## 3. Evidence (credential & environment)

- `~/.codex/auth.json`: `auth_mode: "chatgpt"`; **`OPENAI_API_KEY` field is empty** (`present=False, len=0`); `tokens.access_token` is a **JWT** (`prefix "eyJ"`, len 1965, two dots). → The only usable credential is the ChatGPT OAuth JWT; there is **no Platform `sk-` key** in the codex auth.
- **Prod app settings set neither `OPENAI_API_KEY` nor `COMPLETION_MODEL`.** `settings.openai_api_key` default is `None` ([config.py:42](../src/memory_knowledge/config.py:42)). → In production there is **no OpenAI Platform API key anywhere**; every OpenAI call authenticates with the ChatGPT JWT.
- **Codex model entitlements** (from `~/.codex/models_cache.json` + `config.toml`): `gpt-5.5` (flagged available via `[tui.model_availability_nux] "gpt-5.5" = 1`), plus `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex-spark`, `codex-auto-review`. These are **chat/completion** models served by the Codex/ChatGPT backend — there is **no embedding model** in this set.

---

## 4. Root cause

The ChatGPT OAuth JWT is being used as a **Platform API key** for `api.openai.com`. A ChatGPT/Codex *subscription* credential is not entitled to the Platform **embeddings** product, so `text-embedding-3-small` returns `429 insufficient_quota` (credential recognized, no quota/billing for that model). Two distinct problems fall out:

### Problem A — Embeddings cannot use the Codex credential (the live breakage)
- `text-embedding-3-small` is Platform-only; the ChatGPT JWT has no embeddings entitlement → 429.
- There is no Platform key configured to fall back to.
- **Embeddings genuinely require a funded OpenAI Platform API key** (or a different embedding provider). Routing through Codex cannot solve this — the Codex plan has no embedding model.

### Problem B — Completions: NOT a problem (already Codex-routed) ✓
- **Correction to first draft:** completions are *not* hitting OpenAI in prod. In `auth_mode=codex`, `complete()` (and therefore `complete_batch_summaries()` and `llm_complete()`) route through `_complete_via_codex()` → `CodexMcpClient`, which spawns `codex mcp-server` as a subprocess ([codex_mcp.py:58-70](../src/memory_knowledge/llm/codex_mcp.py:58)). The OpenAI `chat.completions` path exists only for `auth_mode != codex`.
- The requirement to "use the Codex CLI binary for completions" (`[[feedback_codex_completions]]`) is **already satisfied**. No completion change is needed for this fix. (Optional later: the model the codex mcp-server uses is the account default; can be pinned to `gpt-5.5` if desired — out of scope here.)

---

## 5. Consumer map (what each problem affects)

**Embedding consumers (Problem A) — pervasive, currently broken in prod:**
- `workflows/retrieval.py` (query embedding for all vector/semantic + qdrant-first routes)
- `projections/qdrant_projector.py`, `projections/summary_qdrant.py` (ingestion chunk/summary embedding)
- `projections/learned_memory_qdrant.py`, `integrity/embedding_backfill.py`
- `routing/archetype_loader.py` (startup archetype load), `routing/prompt_feature_extractor.py` (archetype match override)
- `triage_memory.py` (triage case embedding/search)

**Completion consumers (Problem B):**
- `workflows/ingestion.py` → `complete_batch_summaries` (summaries; **off** in prod via `GENERATE_SUMMARIES=false`)
- `workflows/blueprint_refinement.py` → `llm_complete` ([blueprint_refinement.py:42](../src/memory_knowledge/workflows/blueprint_refinement.py:42)) — **runs regardless** of the summaries flag; would hit the mis-routed path if exercised.

---

## 6. Constraints the fix must respect (from memory + prod)
- `AUTH_MODE=codex` must not change (`[[feedback_never_change_auth_mode]]`); it is seeded in Azure via KV.
- Completions must use the Codex CLI binary, not the OpenAI completions API (`[[feedback_codex_completions]]`, `[[feedback_codex_auth]]`).
- Do not switch the app back to local env (`[[feedback_dont_switch_env]]`).
- Embedding dimension is coupled to the Qdrant collections (1536); changing the embedding model/provider would require recreating/re-embedding collections (see `docs/DATABASE_UTILIZATION_RESEARCH.md` §8 "embedding model coupling").

---

## 7. Decisions (2026-06-02) and the resulting hard constraint

**User decisions:**
- **D-A. No OpenAI Platform API key anywhere — Codex CLI only.**
- **D-B. Completions shell out to the Codex CLI binary** (`codex exec`), model **`gpt-5.5`**.

**Completions (Problem B): ALREADY DONE — no change needed.** Completions already shell out to the Codex binary via `CodexMcpClient` (`codex mcp-server` subprocess) in `auth_mode=codex`. The `codex exec` route exists as an alternative but is unnecessary since the MCP-subprocess path is in place and working. Scope of this fix excludes completions.

**Embeddings (Problem A): UNRESOLVED — hard conflict.** D-A + the verified fact that **Codex has no embedding capability** (no `embed` subcommand; the plan exposes only chat models `gpt-5.5/5.4/5.4-mini/5.3-codex-spark`) means embeddings **cannot** be produced by either an API key (disallowed) or Codex (incapable). The only ways forward that respect "no API key, Codex only":
- **E1. Local/self-hosted embedding model** in the container (e.g., `fastembed`/`sentence-transformers`, or Qdrant-side fastembed) — no API key, fully self-contained. **Cost:** new embedding backend; almost certainly a different vector dimension (common local models are 384/768/1024-dim vs current 1536), so **all 5 Qdrant collections must be recreated and every vector re-embedded** (≈84.8k chunks + 37.7k summaries + learned + archetypes + triage). Retrieval quality/characteristics change.
- **E2. Drop vector search** — serve retrieval from PG full-text + Neo4j only. Large capability loss (no semantic/conceptual retrieval); the routing policies and Qdrant collections become largely dead. Not recommended.
- **E3. Reconsider D-A *for embeddings only*** — allow a funded Platform `sk-` key used *exclusively* by `embed()/embed_single()` while completions still go through Codex CLI. Keeps `text-embedding-3-small`/1536-dim and avoids any re-embed. (Explicitly contradicts D-A; listed because it is the only zero-migration option.)

This embeddings decision is the gating choice for the implementation plan and is the open question below.

---

## 8. Open questions / uncertainties
1. **GATING DECISION — embeddings:** choose **E1 (local model + full re-embed)**, **E2 (drop vector search)**, or **E3 (Platform key for embeddings only)**. Everything in the implementation plan for Problem A depends on this. Recommendation: E1 if "no API key" is absolute (accept the re-embed migration); E3 only if a funded key is acceptable for embeddings alone.
2. If **E1**: which local embedding model/dimension, and run on CPU in the existing container or as a sidecar? (Affects image size, latency, and the re-embed migration.)
3. **How did the existing 84,827 chunks get embedded** with no Platform key in prod? Likely earlier local ingestion with a real `OPENAI_API_KEY`. Confirm — it tells us whether the prod embedding path *ever* worked under `auth_mode=codex`.
4. **codex exec auth in the container:** confirm the `cli-auth-codex` KV seeding makes `codex exec` authenticate headlessly (no interactive login), and that `gpt-5.5` is available to that account non-interactively.

### Resolved since first draft
- Completion requirement intent → **shell out to `codex exec`** (D-B).
- Platform key availability → **none; not allowed** (D-A).

## 9. E1 feasibility — self-hosted embeddings on the Azure Web App

**Infra reality (verified):** `workflow-orch-plan` = **B3 Basic** (4 vCPU, 7 GB RAM, 1 instance), **shared by `memory-knowledge` + `workflow-orch-app`**. `always_on=true`. RAM (not CPU) is the binding constraint.

**Recommended: `fastembed` (ONNX/CPU), in-process, model baked into image.**
- Model/dim options: `bge-small-en-v1.5` (384-dim, ~130 MB, leanest) or `bge-base-en-v1.5` (768-dim, ~440 MB, better quality). Avoid `bge-large` (1024) and PyTorch/sentence-transformers (~2 GB resident — too heavy for shared 7 GB).
- Image grows ~+400–700 MB (onnxruntime + model). Per-query embed ~10–30 ms on CPU.
- `embed()/embed_single()` swap from `AsyncOpenAI` to the local model; return type unchanged (`list[float]`), so downstream is untouched.

**Migration (one-time, unavoidable):** dimension changes (384/768 ≠ 1536) ⟹ recreate all 5 Qdrant collections and **re-embed ~130k vectors** (84.8k chunks + 37.7k summaries + learned/archetypes/triage). Run the bulk re-embed **offline** against remote Qdrant (not on B3). Update `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS`.

**Risks:** (1) RAM headroom on shared B3 — validate current usage; mitigations: scale plan (B3→S3/P1v3), dedicated plan, or embeddings sidecar (separate Container App, HTTP, still keyless). (2) Retrieval quality shift vs `text-embedding-3-small` (bge-base safer). (3) Re-embed cost.

**RAM check (24h, verified):** plan at **41%** of 7 GB (~4 GB free); `workflow-orch-app` ~1.08 GB, `memory-knowledge` ~0.35 GB. → ample headroom; `bge-base` (768) fits **in-process** (no sidecar needed); plan stays ~≤55% after load.

**Resolved:** **in-process** fastembed; **`bge-base-en-v1.5` (768-dim)** recommended (RAM allows the quality-safer choice). Remaining: final model confirmation, then write the implementation plan.
