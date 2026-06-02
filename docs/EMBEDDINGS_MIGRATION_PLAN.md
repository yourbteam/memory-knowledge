# Embeddings Migration Plan — Self-hosted fastembed (bge-base, 768-dim)

**Status:** Awaiting approval. No code changes until each step is approved.
**Research:** [`docs/OPENAI_CODEX_AUTH_RESEARCH.md`](OPENAI_CODEX_AUTH_RESEARCH.md).
**Scope:** Replace OpenAI embeddings (the only OpenAI dependency in `auth_mode=codex`, cause of prod `429`) with an in-process self-hosted model. **Completions are out of scope — already Codex-routed** (`CodexMcpClient`).

## Decisions locked
- Embeddings: **in-process `fastembed` (ONNX/CPU)**, model **`BAAI/bge-base-en-v1.5`** (768-dim). No API key.
- Completions: **unchanged** (already shell out to `codex mcp-server`).
- Migration: dimension changes 1536→768 ⟹ **recreate all 5 Qdrant collections + re-embed all active content** (offline).

## Context that lowers risk
- Embeddings are **already broken in prod** (`429`), so semantic retrieval is currently down. Recreating collections + re-embedding can only improve things — **no usable-functionality regression window**.
- `repair_drift.repair` already shows the exact PG→payload reconstruction for code_chunks/summaries/learned_memory; the migration reuses that logic, extended to **all active revisions** (repair covers only the latest revision).

---

## Part A — Code changes (reviewed/committed, then deployed)

### A.1 — Dependency
**File:** `pyproject.toml`
- Add `fastembed` to `dependencies` (pin a range, e.g. `fastembed>=0.4,<1.0`; confirm latest at implementation time). Pulls `onnxruntime`. *Verify the exact model id `BAAI/bge-base-en-v1.5` is in fastembed's supported list during implementation.*

### A.2 — Config
**File:** [`src/memory_knowledge/config.py`](../src/memory_knowledge/config.py)
- Add `embedding_provider: Literal["local", "openai"] = "local"`.
- Change defaults: `embedding_model = "BAAI/bge-base-en-v1.5"`, `embedding_dimensions = 768`.
- (Prod app settings currently override `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS` — updated in Part C.)

### A.3 — Local embedding backend
**New file:** `src/memory_knowledge/llm/local_embed.py`
- Module-level **lazy singleton** `TextEmbedding(model_name=settings.embedding_model)` (load once; ~440 MB resident).
- `async def embed_texts(texts: list[str], settings) -> list[list[float]]`: run the synchronous fastembed call in `asyncio.to_thread`, convert each vector to `list[float]`. Batch internally to bound memory.
- No network, no API key, no retry needed (local).

### A.4 — Rewire `embed()` / `embed_single()`
**File:** [`src/memory_knowledge/llm/openai_client.py`](../src/memory_knowledge/llm/openai_client.py:52)
- In `embed()`: `if settings.embedding_provider == "local": return await local_embed.embed_texts(texts, settings)` before the OpenAI path. Keep the OpenAI path for `embedding_provider == "openai"` (dev/fallback).
- `embed_single()` unchanged (delegates to `embed()`).
- Net: in prod (`provider=local`) no OpenAI/JWT call happens for embeddings → `429` eliminated.

### A.5 — Dockerfile: bake the model into the image
**File:** [`Dockerfile`](../Dockerfile)
- Set `ENV FASTEMBED_CACHE_PATH=/app/.fastembed_cache` (confirm env var name for the pinned fastembed version).
- In the **runtime** stage, after deps are present, pre-pull the model so no runtime/cold-start download:
  `RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-base-en-v1.5')"`
- `chown -R appuser` the cache dir. (Keeps egress out of the request path; `WEBSITES_ENABLE_APP_SERVICE_STORAGE=false` means image-local fs.)

### A.6 — Tests
**File:** `tests/` (new)
- `local_embed.embed_texts(["x"])` returns a 768-length float vector.
- `embed()` honors `embedding_provider` (local vs openai branch) — mock the OpenAI client; for local, assert it calls `local_embed`.
- **CI note:** loading the real model in CI is heavy; gate the real-model test behind a marker or mock fastembed in unit tests. Flag CI image-size/time impact.

---

## Part B — Re-embed migration (offline, one-time)

### B.1 — Migration routine
**New file:** `src/memory_knowledge/integrity/reembed_collections.py`
For a given repository (and a global archetypes pass):
1. **Recreate collections at 768.** For safety/rollback, create under **temp names** (e.g. `code_chunks__768`) rather than dropping in place — then swap (see B.3). If swap is too complex, fall back to drop+recreate (accepting harder rollback).
2. **code_chunks:** query **all active** chunks across revisions — `WHERE c.is_active AND e.repository_id=$1`, joining each chunk's own `repo_revisions` for `commit_sha`/`branch_name`, plus `file_path`, `chunk_type`, `title`. Build per-chunk `CodeChunkPayload` (reuse `qdrant_projector` payload shape; payloads must carry correct per-revision `commit_sha`/`branch_name`/`retrieval_surface`, not a single latest value). Embed with local model; upsert.
3. **summary_units:** all active summaries (`s.is_active`), payload from each summary's revision.
4. **learned_memory:** active + verified learned records (full `LearnedMemoryPayload`).
5. **routing_archetypes:** call `archetype_loader.load_archetypes` (re-embeds templates).
6. **triage_cases:** `triage_memory.reproject_triage_cases` per repo.

> This extends `repair_drift.repair` (which only does the latest revision and minimal coverage). Reuse its payload-construction code; broaden the queries to all-active.

### B.2 — Execution
- Run **offline** (local machine or temp box with fastembed + baked model) against **remote Qdrant + remote PG** (pull `DATABASE_URL`/`QDRANT_*` from `.env`, `statement_cache_size=0`), looping all repositories.
- Heaviest step (~130k vectors); CPU-bound. Keep off the B3 instance.

### B.3 — Cutover & rollback safety
- **Decision D1:** temp-collection-then-swap (safer rollback — keep 1536 collections until 768 ones are populated, then rename/repoint) **vs.** in-place drop+recreate (simpler, but rollback requires re-embedding back to 1536 via the now-broken OpenAI path). Recommend temp-then-swap given prod is live.
- Because semantic search is already `429`-broken, an in-place approach has no *additional* user-facing downtime — but swap is still preferable for clean rollback.

---

## Part C — Deploy & sequence

1. Commit Part A to `main`; build image (fastembed + baked model) via `az acr build`; tag = new SHA.
2. **Run Part B migration offline** (recreate 768 collections + re-embed) — *before* pointing prod at the new image, so the deployed app meets 768 collections.
3. Update prod app settings: `EMBEDDING_MODEL=BAAI/bge-base-en-v1.5`, `EMBEDDING_DIMENSIONS=768`, `EMBEDDING_PROVIDER=local`.
4. `az webapp config container set` → new image; `az webapp restart`. Startup `load_archetypes` now embeds with the local model into the 768 `routing_archetypes`.
5. **Verify:** `/ready` green; a **conceptual** retrieval query (previously `429`) returns results with no OpenAI call; confirm collection vector size = 768 and non-zero counts.

> Sequence rationale: collections must be 768 before the new code's startup archetype upsert runs; and the old running code's embeddings are already broken, so recreating collections first causes no new regression.

## Part D — Verification & rollback
- **Verify:** semantic retrieval works end-to-end; no `429` in logs; RAM on B3 stays within headroom (re-check plan memory % post-deploy).
- **Rollback:** revert image + app settings to the previous SHA. If collections were swapped (D1), repoint to the retained 1536 collections; if dropped in-place, rollback is limited (1536 re-embed needs OpenAI, which is unavailable) — another reason to prefer swap.

## Open decisions before implementation
- **D1 (cutover):** temp-collection swap (recommended) vs. in-place drop+recreate.
- **D2 (migration delivery):** offline local runner (like the Phase-1 backfill) vs. an `@mcp.tool()` `run_reembed_workflow` (reusable, gated by `allow_remote_rebuilds`). Recommend local runner for a one-time job.
- **D3 (CI):** mock fastembed in unit tests vs. allow the model download in CI (slower, larger). Recommend mock + one gated integration test.
- Confirm `fastembed` version + exact model id + cache env var at implementation time (no guessing in code).
