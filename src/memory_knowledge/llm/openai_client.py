from __future__ import annotations

import json
import re
from typing import Any

import openai
import structlog
from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from memory_knowledge.config import Settings

logger = structlog.get_logger()

EMBED_BATCH_SIZE = 32  # ~8K chars per chunk × 32 = ~256K chars ≈ 64K tokens, well under 300K limit

_RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
)


async def _get_api_key(settings: Settings) -> str:
    """Resolve the OpenAI API key based on auth_mode."""
    if settings.auth_mode == "codex":
        from memory_knowledge.auth.codex import codex_token_provider

        return await codex_token_provider(settings.codex_auth_path)
    return settings.openai_api_key or ""


async def _refresh_and_get_api_key(settings: Settings) -> str:
    """Force-refresh the Codex token and return the new key."""
    from memory_knowledge.auth.credential_refresh import refresh_codex_token

    success, error = await refresh_codex_token(settings.codex_auth_path)
    if success:
        logger.info("codex_token_refreshed_on_401")
    else:
        logger.error("codex_token_refresh_failed_on_401", error=error)
    return await _get_api_key(settings)


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    wait=wait_exponential(min=1, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def embed(
    texts: list[str], settings: Settings
) -> list[list[float]]:
    """Embed texts using OpenAI with retry on transient errors. Batches at 100."""
    if not texts:
        return []

    api_key = await _get_api_key(settings)
    client = AsyncOpenAI(api_key=api_key)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        try:
            response = await client.embeddings.create(
                model=settings.embedding_model,
                input=batch,
                dimensions=settings.embedding_dimensions,
            )
            batch_embeddings = [d.embedding for d in response.data]
            if len(batch_embeddings) != len(batch):
                raise ValueError(
                    f"Embedding count mismatch: expected {len(batch)}, got {len(batch_embeddings)}"
                )
            for emb in batch_embeddings:
                if len(emb) != settings.embedding_dimensions:
                    raise ValueError(
                        f"Embedding dimension mismatch: expected {settings.embedding_dimensions}, "
                        f"got {len(emb)}"
                    )
            all_embeddings.extend(batch_embeddings)
        except openai.AuthenticationError:
            if settings.auth_mode == "codex":
                api_key = await _refresh_and_get_api_key(settings)
                client = AsyncOpenAI(api_key=api_key)
                try:
                    response = await client.embeddings.create(
                        model=settings.embedding_model,
                        input=batch,
                        dimensions=settings.embedding_dimensions,
                    )
                    batch_embeddings = [d.embedding for d in response.data]
                    if len(batch_embeddings) != len(batch):
                        raise ValueError(
                            f"Embedding count mismatch: expected {len(batch)}, got {len(batch_embeddings)}"
                        )
                    for emb in batch_embeddings:
                        if len(emb) != settings.embedding_dimensions:
                            raise ValueError(
                                f"Embedding dimension mismatch: expected {settings.embedding_dimensions}, "
                                f"got {len(emb)}"
                            )
                    all_embeddings.extend(batch_embeddings)
                    continue
                except openai.AuthenticationError:
                    raise RuntimeError(
                        "Codex OAuth token rejected after refresh — run 'codex auth' to re-authenticate"
                    )
            raise

    return all_embeddings


async def embed_single(text: str, settings: Settings) -> list[float]:
    """Embed a single text string. Returns one embedding vector."""
    if not text:
        raise ValueError("Cannot embed empty text")
    result = await embed([text], settings)
    if not result:
        raise ValueError("Empty embedding response for single text")
    return result[0]


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    wait=wait_exponential(min=1, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def complete(
    prompt: str,
    settings: Settings,
    system_prompt: str | None = None,
    timeout: float | None = None,
) -> str:
    """Call LLM for text completion. Uses Codex CLI in codex mode, OpenAI API otherwise."""
    if settings.auth_mode == "codex":
        return await _complete_via_codex(prompt, system_prompt, timeout=timeout)

    api_key = await _get_api_key(settings)
    client = AsyncOpenAI(api_key=api_key)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model=settings.completion_model,
        messages=messages,
        max_tokens=settings.max_completion_tokens,
    )
    return response.choices[0].message.content or ""


async def _complete_via_codex(
    prompt: str, system_prompt: str | None = None, timeout: float | None = None
) -> str:
    """Route completions through the Codex CLI MCP server subprocess."""
    from memory_knowledge.llm.codex_mcp import CodexMcpClient

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    client = CodexMcpClient.get()
    if timeout is not None:
        return await client.complete(full_prompt, timeout=timeout)
    return await client.complete(full_prompt)


# ── Batch summary generation ────────────────────────────────────────


def _format_batch_prompt(items: list[dict[str, Any]], language: str) -> str:
    """Format a batch of symbols/files into a single summary prompt."""
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


def _extract_json_array(text: str) -> list[dict[str, Any]] | None:
    """Extract a JSON array from LLM text that may include markdown fences and commentary.

    Tries multiple strategies because the source code in the prompt may contain
    brackets that confuse simple substring extraction.
    """
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```", "", cleaned)

    # Strategy 1: Find a JSON array that starts with [{"index"
    # This is the most reliable since our prompt asks for {"index": N, "summary": "..."}
    match = re.search(r'\[\s*\{\s*"index"', cleaned)
    if match:
        start = match.start()
        # Find the matching closing bracket by counting depth
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == "[":
                depth += 1
            elif cleaned[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except json.JSONDecodeError:
                        break

    # Strategy 2: Try all [ positions from the end (last array is most likely the answer)
    positions = [m.start() for m in re.finditer(r"\[", cleaned)]
    for start in reversed(positions):
        end = cleaned.rfind("]", start)
        if end <= start:
            continue
        try:
            result = json.loads(cleaned[start : end + 1])
            if isinstance(result, list) and result and isinstance(result[0], dict):
                return result
        except json.JSONDecodeError:
            continue

    # Strategy 3: The response might be individual JSON objects, one per line
    lines = cleaned.strip().splitlines()
    objects = []
    for line in lines:
        line = line.strip().rstrip(",")
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                if "index" in obj and "summary" in obj:
                    objects.append(obj)
            except json.JSONDecodeError:
                continue
    if objects:
        return objects

    return None


def _extract_partial_json(text: str) -> list[dict[str, Any]]:
    """Extract individual JSON objects from a truncated response.

    When the LLM output is cut off mid-array, this salvages any complete
    objects that appeared before the truncation point.
    """
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)

    objects = []
    # Find all complete {"index": N, "summary": "..."} objects
    for match in re.finditer(r'\{[^{}]*"index"\s*:\s*\d+[^{}]*"summary"\s*:\s*"[^"]*"[^{}]*\}', text):
        try:
            obj = json.loads(match.group())
            if "index" in obj and "summary" in obj:
                objects.append(obj)
        except json.JSONDecodeError:
            continue
    return objects


async def _retry_individual(
    item: dict[str, Any], settings: Settings, language: str
) -> dict[str, Any] | None:
    """Fall back to a single-item summary call when batch parsing fails."""
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


async def complete_batch_summaries(
    items: list[dict[str, Any]],
    settings: Settings,
    language: str,
    batch_size: int = 50,
    on_batch_complete: Any = None,
) -> list[dict[str, Any]]:
    """Generate summaries for multiple symbols/files in batched LLM calls.

    Returns [{"index": N, "summary": "..."}, ...] for all successfully summarized items.
    If on_batch_complete is provided, it is called with each batch's results immediately
    after generation (before the next batch starts), enabling incremental persistence.
    """
    all_summaries: list[dict[str, Any]] = []

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start : batch_start + batch_size]
        prompt = _format_batch_prompt(batch, language)
        batch_results: list[dict[str, Any]] = []

        timeout = max(120, len(batch) * 3)
        try:
            response = await complete(prompt, settings, timeout=timeout)
        except Exception as exc:
            logger.warning("batch_summary_call_failed", error=str(exc), batch_size=len(batch))
            for item in batch:
                individual = await _retry_individual(item, settings, language)
                if individual:
                    batch_results.append(individual)
            all_summaries.extend(batch_results)
            if on_batch_complete and batch_results:
                await on_batch_complete(batch_results)
            continue

        parsed = _extract_json_array(response)
        if parsed:
            index_to_summary = {
                r["index"]: r["summary"]
                for r in parsed
                if isinstance(r, dict) and "index" in r and "summary" in r
            }
            missing_items = []
            for item in batch:
                if item["index"] in index_to_summary:
                    batch_results.append(
                        {"index": item["index"], "summary": index_to_summary[item["index"]]}
                    )
                else:
                    missing_items.append(item)
            if missing_items:
                logger.info("batch_partial_retry", missing=len(missing_items), got=len(index_to_summary))
                if len(missing_items) <= 5:
                    for item in missing_items:
                        individual = await _retry_individual(item, settings, language)
                        if individual:
                            batch_results.append(individual)
                else:
                    sub_results = await complete_batch_summaries(
                        missing_items, settings, language,
                        batch_size=max(10, len(missing_items) // 2),
                        on_batch_complete=on_batch_complete,
                    )
                    batch_results.extend(sub_results)
        else:
            partial = _extract_partial_json(response)
            if partial:
                logger.warning("batch_json_partial_salvage", batch_size=len(batch), salvaged=len(partial))
                salvaged_indices = set()
                for r in partial:
                    if isinstance(r, dict) and "index" in r and "summary" in r:
                        batch_results.append({"index": r["index"], "summary": r["summary"]})
                        salvaged_indices.add(r["index"])
                unsalvaged = [item for item in batch if item["index"] not in salvaged_indices]
                if unsalvaged:
                    sub_results = await complete_batch_summaries(
                        unsalvaged, settings, language,
                        batch_size=max(10, len(unsalvaged) // 2),
                        on_batch_complete=on_batch_complete,
                    )
                    batch_results.extend(sub_results)
            else:
                logger.warning("batch_json_extraction_failed", batch_size=len(batch), raw_response=response[:500])
                sub_results = await complete_batch_summaries(
                    batch, settings, language,
                    batch_size=max(10, len(batch) // 2),
                    on_batch_complete=on_batch_complete,
                )
                batch_results.extend(sub_results)

        # Persist this batch immediately
        all_summaries.extend(batch_results)
        if on_batch_complete and batch_results:
            await on_batch_complete(batch_results)

        logger.info(
            "batch_summaries_progress",
            completed=len(all_summaries),
            total=len(items),
            batch_size=len(batch),
        )

    return all_summaries
