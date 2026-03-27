from __future__ import annotations

import openai
import structlog
from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from memory_knowledge.config import Settings

logger = structlog.get_logger()

EMBED_BATCH_SIZE = 100

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
                raise RuntimeError(
                    "Codex OAuth token rejected — run 'codex auth' to re-authenticate"
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
    """Call OpenAI chat completions with retry on transient errors."""
    api_key = await _get_api_key(settings)
    client = AsyncOpenAI(api_key=api_key)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await client.chat.completions.create(
            model=settings.completion_model,
            messages=messages,
            max_tokens=settings.max_completion_tokens,
        )
    except openai.AuthenticationError:
        if settings.auth_mode == "codex":
            raise RuntimeError(
                "Codex OAuth token rejected — run 'codex auth' to re-authenticate"
            )
        raise

    return response.choices[0].message.content or ""
