# Findings: `search_qa_knowledge` always returns empty (qa-suggest accumulation broken)

Diagnosed from the memory-knowledge code (`src/memory_knowledge/qa_memory.py`,
`server.py`, `guards.py`). The caller (workflow-orch `workflow.qa.suggest`) is verified to
reach `search_qa_knowledge` with a resolved, registered `repository_key` (the search returns
no "unknown repository" warning) yet gets `rows: []` for every question — same-task and
cross-task, including near-identical questions to ones just answered.

A definitive split needs one DB check (below). Three concrete candidate causes, in priority
order, all in this repo:

---

## Candidate 1 — `ingest_qa_pairs` is blocked/failing, so nothing is ever stored

### 1a. Remote write guard (`server.py:1584`, `guards.py:13`)
`ingest_qa_pairs` is a write-path tool and runs `check_remote_write_guard()` first:
```python
guard = check_remote_write_guard(get_settings(), "ingest_qa_pairs")
if guard is not None:
    return guard.model_dump_json()   # returns an ERROR, writes NOTHING
```
If the **deployed** instance has `DATA_MODE=remote` and `ALLOW_REMOTE_WRITES` is not `true`,
every ingest is rejected. `search_qa_knowledge` has **no** guard → it works and returns empty
because nothing was ever written. (The local `.env` has `ALLOW_REMOTE_WRITES=true`, but the
**deployed** env must be confirmed.)

The caller (workflow-orch `feedback_qa_capture`) discards the `ingest_qa_pairs` return value
and swallows exceptions, so this guard error is invisible upstream.

### 1b. Unregistered `repository_key` (`qa_memory.py:80-82`)
`ingest_qa_pairs` raises `ValueError("Repository '<key>' not found")` if the `repository_key`
isn't in `catalog.repositories`. The **search** key is registered (no "unknown repository"
warning), but if the **capture** sends a different key (e.g. a session-scoped one), ingest
raises and writes nothing — again swallowed upstream.

---

## Candidate 2 — search is semantic-only with no lexical fallback when Qdrant is present (robustness bug)

This one will silently break suggestions even when the PG row WAS written:

- **Ingest** writes the Postgres row unconditionally (`qa_memory.py:100`) but only upserts the
  Qdrant embedding `if qdrant_client is not None` **and** `embed_single` succeeds; an embed
  failure is swallowed (`qa_memory.py:127-144`).
- **Search** (`qa_memory.py:171-196`): when `qdrant_client is not None` it does semantic-only
  and, if semantic returns no candidates, **returns empty** (`193-194`). It only runs the
  Postgres lexical query when `qdrant_client is None` (`196`).

So if an embedding is missing (ingest's Qdrant upsert was skipped or `embed_single` failed at
ingest time, e.g. a transient OpenAI error, or `qdrant_client` was None during that ingest)
the Q&A is permanently invisible to search — even though the PG row exists and an exact-text
match would be found lexically. A transient ingest-time embed failure = a permanently
unsearchable pair.

**Recommended fix (defensive, correct regardless of root cause):** in
`search_qa_knowledge`, fall back to the lexical Postgres search when the semantic path returns
**no candidates**, not only when `qdrant_client is None`. e.g.:
```python
# after the semantic block
if not candidates and not fallback_to_lexical:
    fallback_to_lexical = True   # semantic found nothing → try lexical before giving up
```
and drop/adjust the early `return` at `qa_memory.py:193-194`.

---

## Candidate 3 — `min_similarity = 0.65` threshold (`qa_memory.py:162,181`; `server.py:1627`)

Cross-task, non-identical questions may score below 0.65 and be filtered. Less likely the
*primary* cause (a same-task exact-question search also returned empty), but worth confirming
once ingest is verified — consider lowering for advisory suggestions, or returning
below-threshold rows marked as low-confidence.

---

## The one diagnostic that splits ingest-vs-search

Run against the deployed DB:
```sql
SELECT count(*) FROM memory.qa_pairs;
SELECT r.repository_key, count(*) FROM memory.qa_pairs q
  JOIN catalog.repositories r ON r.id = q.repository_id
  GROUP BY r.repository_key ORDER BY 2 DESC;
```
- **No rows for the repo** → ingest is blocked/failing → Candidate 1 (check the deployed
  `ALLOW_REMOTE_WRITES`/`DATA_MODE`, and the `repository_key` the capture sends vs registered
  repos). Also call `ingest_qa_pairs` directly and read its return — it returns the guard
  error or "Repository not found".
- **Rows exist but search still empty** → Candidate 2 (missing embeddings + semantic-only
  search) or Candidate 3 (threshold). Check whether the `qa_pairs` Qdrant collection has
  vectors for those `qa_pair_id`s.

---

## Cross-repo note (workflow-orch side)

For suggestions to accumulate across tasks, the `repository_key` must be the **canonical,
stable repo key** on both ingest and search — identical for every task/session targeting the
repo. If it's session-scoped, suggestions can't cross tasks regardless of the fixes here.
memory-knowledge should log the `repository_key` it receives on ingest vs search so we can
confirm; if they differ, the key-derivation fix is on the workflow-orch side.

Also recommend: workflow-orch's `feedback_qa_capture` should **log** the `ingest_qa_pairs`
result (status/error) instead of discarding it, so a blocked/failed ingest is never silent.
