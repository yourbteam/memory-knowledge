from __future__ import annotations

import openai
import structlog
from openai import AsyncOpenAI

from memory_knowledge.config import Settings

logger = structlog.get_logger()


async def llm_complete(
    prompt: str,
    settings: Settings,
    system_prompt: str | None = None,
) -> str:
    """Call OpenAI chat completions using the configured auth_mode."""
    if settings.auth_mode == "codex":
        from memory_knowledge.auth.codex import codex_token_provider

        api_key = await codex_token_provider(settings.codex_auth_path)
    else:
        api_key = settings.openai_api_key

    client = AsyncOpenAI(api_key=api_key)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await client.chat.completions.create(
            model=settings.completion_model,
            messages=messages,
        )
    except openai.AuthenticationError:
        if settings.auth_mode == "codex":
            raise RuntimeError(
                "Codex OAuth token rejected — run 'codex auth' to re-authenticate"
            )
        raise

    return response.choices[0].message.content or ""
