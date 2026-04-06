# Plan: Batched Summary Generation

## Context

Summary generation makes one Codex CLI call per symbol/file (~20s each). For a 12K-symbol repo, this takes 62 hours. Batching 50 summaries per call reduces this to ~248 calls → ~1.5-2 hours. Same Codex CLI, same auth, no concurrency complexity.

---

## Files to Modify

| File | Change |
|---|---|
| `src/memory_knowledge/workflows/ingestion.py` | Replace sequential summary loop (lines 465-544) with batch collection + batch call + parse. Add `import os`, `from itertools import groupby`, and `from memory_knowledge.llm.openai_client import complete_batch_summaries` at top. |
| `src/memory_knowledge/llm/openai_client.py` | Add `complete_batch_summaries()` function + `_format_batch_prompt()` + `_extract_json_array()`. Add `import json, re` at top. Add `timeout` param to `complete()` and `_complete_via_codex()`. |
| `src/memory_knowledge/llm/codex_mcp.py` | Add `timeout` param to `complete()` method, pass through to `_send_request()`. (~2 lines) |
| `tests/test_batch_summaries.py` | New — test batch prompt formatting, JSON extraction, index matching |

---

## Change 1: Batch Summary Function in `openai_client.py`

Add a new function that takes a list of items and returns a list of summaries:

```python
async def complete_batch_summaries(
    items: list[dict[str, str]],  # [{"index": 1, "name": "fn", "kind": "function", "file": "a.py", "source": "..."}]
    settings: Settings,
    language: str,
    batch_size: int = 50,
) -> list[dict[str, str]]:
    """Generate summaries for multiple symbols/files in batched LLM calls.
    
    Returns [{"index": 1, "summary": "..."}, ...] for all items.
    Items that fail are retried individually.
    """
```

### Batch Prompt Template

```python
def _format_batch_prompt(items: list[dict], language: str) -> str:
    header = (
        f"You are summarizing {language} code. For each numbered item below, "
        "provide a 2-3 sentence summary focusing on what it does, its inputs/outputs, "
        "and key behaviors.\n\n"
        "Return ONLY a JSON array where each element has:\n"
        '- "index": the item number\n'
        '- "summary": your 2-3 sentence summary\n\n'
        "Items:\n"
    )
    body = ""
    for item in items:
        body += f"\n---\n[{item['index']}] {item['name']} ({item['kind']}) from {item['file']}\n"
        body += f"```\n{item['source']}\n```\n"
    return header + body
```

### JSON Extraction from Agent Output

```python
def _extract_json_array(text: str) -> list[dict] | None:
    """Extract a JSON array from LLM text that may include markdown fences and commentary."""
    import re
    # Strip markdown code fences
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```', '', text)
    # Find the JSON array
    start = text.find('[')
    end = text.rfind(']')
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
```

### Timeout Threading

Add `timeout` parameter through the call chain (~6 lines across 2 files):

**`codex_mcp.py`** — `complete()` method:
```python
async def complete(self, prompt: str, timeout: float = _REQUEST_TIMEOUT) -> str:
    # ... existing code ...
    result = await self._send_request("tools/call", {...}, timeout=timeout)  # was _REQUEST_TIMEOUT
```

**`openai_client.py`** — `_complete_via_codex()` and `complete()`:
```python
async def _complete_via_codex(prompt, system_prompt=None, timeout=None):
    client = CodexMcpClient.get()
    return await client.complete(full_prompt, timeout=timeout) if timeout else await client.complete(full_prompt)

async def complete(prompt, settings, system_prompt=None, timeout=None):
    if settings.auth_mode == "codex":
        return await _complete_via_codex(prompt, system_prompt, timeout=timeout)
    # ... rest unchanged
```

### Individual Fallback

```python
async def _retry_individual(item: dict, settings: Settings, language: str) -> dict | None:
    """Fall back to a single-item summary call when batch parsing fails for an item."""
    prompt = (
        f"Summarize the following {language} code in 2-3 sentences. "
        "Focus on what it does, its inputs/outputs, and key behaviors.\n\n"
        f"{item['name']} ({item['kind']}) from {item['file']}\n\n"
        f"{item['source']}"
    )
    try:
        summary = await complete(prompt, settings)
        if summary and summary.strip():
            return {"index": item["index"], "summary": summary.strip()}
    except Exception as exc:
        logger.warning("individual_summary_failed", name=item["name"], error=str(exc))
    return None
```

### Batch Call Flow

```python
all_summaries = []
for batch_start in range(0, len(items), batch_size):
    batch = items[batch_start:batch_start + batch_size]
    prompt = _format_batch_prompt(batch, language)
    
    timeout = max(120, len(batch) * 3)
    response = await complete(prompt, settings, timeout=timeout)  # goes through Codex CLI
    
    parsed = _extract_json_array(response)
    if parsed:
        # Match by index
        index_to_summary = {r["index"]: r["summary"] for r in parsed if "index" in r and "summary" in r}
        for item in batch:
            if item["index"] in index_to_summary:
                all_summaries.append({"index": item["index"], "summary": index_to_summary[item["index"]]})
            else:
                # Missing from batch response — retry individually
                individual = await _retry_individual(item, settings, language)
                if individual:
                    all_summaries.append(individual)
    else:
        # JSON extraction failed — fall back to individual calls for entire batch
        for item in batch:
            individual = await _retry_individual(item, settings, language)
            if individual:
                all_summaries.append(individual)
    
    logger.info("batch_summaries_progress", completed=len(all_summaries), total=len(items))

return all_summaries
```

---

## Change 2: Rewrite Summary Loop in `ingestion.py`

Replace `ingestion.py:465-543` (the sequential file+symbol summary loop) with:

### Step 1: Collect all items needing summaries

```python
# Collect all file-level and symbol-level items
summary_items = []
item_index = 1

# Skip entities that already have summaries
existing_summary_keys = set()
rows = await pool.fetch(
    """SELECT e.entity_key FROM catalog.summaries s
       JOIN catalog.entities e ON s.entity_id = e.id
       WHERE e.repository_id = $1""",
    repository_id,
)
existing_summary_keys = {str(r["entity_key"]) for r in rows}

for fp, source in file_path_to_source.items():
    file_ek = file_path_to_entity_key.get(fp, "")
    s_ek = str(summary_entity_key(repository_key, commit_sha, file_ek, "file"))
    if s_ek not in existing_summary_keys:
        summary_items.append({
            "index": item_index,
            "name": os.path.basename(fp),
            "kind": "file",
            "file": fp,
            "source": source[:8000],
            "entity_key": file_ek,
            "summary_level": "file",
            "language": detect_language(fp),
        })
        item_index += 1

    # Symbol-level items
    for fs in neo4j_file_symbols:
        if fs["file_path"] != fp:
            continue
        cached_parse = file_path_to_parse_output.get(fp)
        if not cached_parse:
            continue
        source_lines = source.splitlines()
        for sym_rec in fs["symbols"]:
            sym_ek = sym_rec["entity_key"]
            s_ek = str(summary_entity_key(repository_key, commit_sha, sym_ek, "symbol"))
            if s_ek in existing_summary_keys:
                continue
            sym_source = None
            for psym in cached_parse.symbols:
                if psym.name == sym_rec["name"]:
                    sym_source = "\n".join(source_lines[psym.line_start - 1 : psym.line_end])
                    break
            if not sym_source:
                continue
            summary_items.append({
                "index": item_index,
                "name": sym_rec["name"],
                "kind": sym_rec["kind"],
                "file": fp,
                "source": sym_source[:4000],
                "entity_key": sym_ek,
                "summary_level": "symbol",
                "language": detect_language(fp),
            })
            item_index += 1

logger.info("summary_items_collected", total=len(summary_items), skipped=len(existing_summary_keys))
```

### Step 2: Group by language and batch

```python
from itertools import groupby

# Group by language for consistent prompts
summary_items.sort(key=lambda x: x["language"])
by_language = {lang: list(items) for lang, items in groupby(summary_items, key=lambda x: x["language"])}

all_results = []
for language, lang_items in by_language.items():
    results = await complete_batch_summaries(lang_items, settings, language, batch_size=50)
    all_results.extend(results)
```

### Step 3: Persist summaries

```python
all_summaries_for_embedding = []
summaries_created = 0

# Build index→item map
index_to_item = {item["index"]: item for item in summary_items}

for result in all_results:
    item = index_to_item.get(result["index"])
    if not item:
        continue
    
    s_ek = summary_entity_key(repository_key, commit_sha, item["entity_key"], item["summary_level"])
    
    if item["summary_level"] == "file":
        entity_id = file_path_to_entity_id.get(item["file"])
    else:
        row = await pool.fetchrow(
            "SELECT id FROM catalog.entities WHERE entity_key = $1",
            uuid.UUID(item["entity_key"]),
        )
        entity_id = row["id"] if row else None
    
    if entity_id:
        await upsert_summary(pool, s_ek, entity_id, item["summary_level"], result["summary"])
        all_summaries_for_embedding.append({
            "entity_key": str(s_ek),
            "summary_text": result["summary"],
            "summary_level": item["summary_level"],
        })
        summaries_created += 1

logger.info("summaries_generated", count=summaries_created)
```

---

## Change 3: Tests

**New file:** `tests/test_batch_summaries.py`

1. **test_format_batch_prompt** — verify prompt includes numbered items with source
2. **test_extract_json_array_clean** — `[{"index":1,"summary":"..."}]` → parsed
3. **test_extract_json_array_with_fences** — ` ```json [...] ``` ` → parsed
4. **test_extract_json_array_with_preamble** — `"Here are the summaries:\n[...]"` → parsed
5. **test_extract_json_array_malformed** — `"not json at all"` → None
6. **test_batch_index_matching** — verify items matched back by index, not name
7. **test_skip_existing_summaries** — items with existing summaries excluded from batch

---

## Verification

1. Run tests: `python -m pytest tests/test_batch_summaries.py -v`
2. Run full suite: `python -m pytest tests/ -v`
3. Test with a small repo (FCS Admin, ~500 symbols):
   - Time the current sequential approach
   - Time the batched approach
   - Compare summary quality (spot-check 10 summaries)
4. Test with taggable-server (~12K symbols):
   - Monitor batch progress logging
   - Verify all summaries persisted
   - Verify skip-existing works on re-run
