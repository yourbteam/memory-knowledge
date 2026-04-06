# Analysis: Parallel Summary Generation

## Problem

Summary generation during ingestion is impractically slow for large repos. A repo with 10,146 symbols + 2,243 files = 12,389 summaries. At ~3/minute (one sequential Codex CLI call per summary), this takes **~62 hours**.

## Root Cause

The system makes **one LLM call per summary**. Each call sends a single file or symbol's source code and gets back 2-3 sentences. The Codex CLI subprocess takes ~15-20 seconds per call regardless of prompt size. With 12,389 calls, the total time is dominated by call count, not prompt processing.

## The Fix: Batch Summaries

Instead of 1 call → 1 summary, send 1 call → N summaries.

### Current (1:1)
```
Call 1: "Summarize function getUserById" → "Returns a user object by ID..."
Call 2: "Summarize function createOrder" → "Creates a new order..."
Call 3: "Summarize function validateEmail" → "Validates email format..."
...
12,389 calls × 20s = 62 hours
```

### Proposed (1:N)
```
Call 1: "Here are 100 symbols. For each, return {name, summary}:"
  - getUserById: source...
  - createOrder: source...
  - validateEmail: source...
  - ... (97 more)
→ JSON array of 100 {name, summary} objects
...
124 calls × 30-60s = ~1-2 hours
```

## Batch Design

### Prompt Structure

```
You are summarizing code symbols. For each symbol below, provide a 2-3 sentence summary focusing on what it does, its inputs/outputs, and key behaviors.

Return a JSON array where each element has:
- "name": the symbol name exactly as given
- "summary": your 2-3 sentence summary

Symbols:

---
[1] getUserById (function) from src/services/UserService.cs
```typescript
public async Task<User> getUserById(int id) {
    return await _context.Users.FindAsync(id);
}
```

---
[2] createOrder (function) from src/services/OrderService.cs
```typescript
public async Task<Order> createOrder(OrderDto dto) {
    ...
}
```

... (up to 100 symbols)
```

### Batch Sizing

The constraint is the LLM context window. Each symbol contributes:
- Symbol metadata: ~20 tokens (name, kind, file path)
- Source code: up to 4,000 chars (~1,000 tokens) for symbols, 8,000 chars (~2,000 tokens) for files
- Output: ~75 tokens per summary

**For symbols (~1,000 tokens input each):**
- gpt-4o context: 128K tokens
- Practical limit with output: ~80K input tokens
- Batch size: ~80 symbols per call

**For files (~2,000 tokens input each):**
- Batch size: ~40 files per call

**Conservative default: 50 items per batch** (works for both files and symbols with margin).

### Batch Math

| Repo | Total Summaries | Batches (50/batch) | Time at 30s/batch | Time with 4 parallel |
|---|---|---|---|---|
| FCSAPI | ~1,700 | 34 | ~17 min | ~4 min |
| FCS Admin | ~500 | 10 | ~5 min | ~1.5 min |
| CSS-FE | ~8,200 | 164 | ~82 min | ~21 min |
| taggable-server | ~12,400 | 248 | ~124 min | ~31 min |

**taggable-server: 31 minutes instead of 62 hours. ~120x faster.**

### Response Parsing

The LLM returns a JSON array keyed by **batch index** (not name — names can collide across overloaded methods):
```json
[
  {"index": 1, "summary": "Returns a user by their database ID..."},
  {"index": 2, "summary": "Creates a new order from a DTO..."},
  ...
]
```

**Critical: The Codex CLI is a full agent framework**, not a raw API. Its text output may include:
- Preamble text ("Here are the summaries:")
- Markdown code fences (` ```json ... ``` `)
- Chain-of-thought reasoning before the JSON

The parser must:
1. Strip markdown fences if present
2. Find the JSON array within the text (first `[` to last `]`)
3. `json.loads()` the extracted substring
4. Match each item by `index` back to the batch's entity list by position

If a symbol is missing from the response, log a warning and retry individually. If JSON extraction fails entirely, fall back to individual calls for that batch.

### Error Handling

- **Partial response:** If the LLM returns 45 out of 50 summaries, save the 45 and retry the missing 5 individually.
- **JSON parse failure:** Strip markdown fences, extract JSON substring, retry parse. If still fails, fall back to individual calls for that batch.
- **Token limit exceeded:** Reduce batch size and retry.
- **Timeout:** Set to `max(120, BATCH_SIZE * 3)` seconds (e.g., 150s for 50-item batch). The current single-item timeout is 120s; batches should not be less.

### Skip Existing Summaries

Before building batches, query for entities that already have summaries:
```sql
SELECT e.entity_key FROM catalog.summaries s
JOIN catalog.entities e ON s.entity_id = e.id
WHERE e.repository_id = $1
```

Exclude these from the batch. This prevents wasted LLM calls on:
- Crash recovery (partial run already generated some summaries)
- Re-runs on unchanged files
- The current code does NOT skip existing summaries — `upsert_summary` overwrites unconditionally

## Speedup Summary

| Strategy | Calls | Time |
|---|---|---|
| Current (1:1, sequential) | 12,389 | ~62 hours |
| **Batch 50, sequential** | **248** | **~1.5-2 hours** |

Batching alone gives a **~50x speedup** with zero concurrency complexity — single Codex CLI subprocess, single lock, just fewer calls. Each call takes slightly longer (~30-60s for 50 items vs ~20s for 1), but the total wall time drops dramatically.

## Future Option: Direct OpenAI API for Maximum Speed

If `SUMMARY_API_KEY` is set, bypass Codex CLI entirely. Direct API calls with batching + concurrency = minutes for all repos combined, at ~$6 total cost. This is additive — the batching prompt works the same whether going through Codex CLI or direct API. Not in scope for now.

## Recommended Implementation

### Scope: Batched Summaries Only (No concurrency, no API key)
- Change the ingestion summary loop to collect symbols/files into batches of 50
- Format the batch prompt with indexed structure and request JSON array output
- Parse the response with JSON extraction (strip fences, find array substring)
- Match responses to entities by batch index
- Skip entities that already have summaries
- Fall back to individual calls on parse failure
- Single Codex CLI subprocess, sequential batched calls

## Risks

1. **JSON extraction from agent output:** The Codex CLI agent wraps responses with commentary and markdown. The parser must extract JSON from within agent text, not assume clean output. Mitigate with fence-stripping + substring extraction + individual fallback.
2. **Index matching:** Batch responses are matched by position index, not name. The prompt numbers each symbol `[1]`, `[2]`, etc. and the response must include the index. This avoids name collisions from overloaded methods or same-name symbols across scopes.
3. **Codex CLI rate limiting:** Unknown whether multiple MCP instances from the same account are rate-limited. Test with 2 before scaling to 8.
4. **Batch size tuning:** 50 is conservative. May need adjustment per model — Codex CLI's internal model may have different context limits than gpt-4o.
