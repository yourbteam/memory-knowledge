from __future__ import annotations

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
) -> str:
    """Call LLM for text completion. Uses Codex CLI in codex mode, OpenAI API otherwise."""
    if settings.auth_mode == "codex":
        return await _complete_via_codex(prompt, system_prompt)

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


async def _complete_via_codex(prompt: str, system_prompt: str | None = None) -> str:
    """Route completions through the Codex CLI MCP server subprocess."""
    from memory_knowledge.llm.codex_mcp import CodexMcpClient

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    client = CodexMcpClient.get()
    return await client.complete(full_prompt)
