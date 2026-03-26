from __future__ import annotations

from memory_knowledge.config import Settings
from memory_knowledge.llm.openai_client import complete


async def llm_complete(
    prompt: str,
    settings: Settings,
    system_prompt: str | None = None,
) -> str:
    """Call OpenAI chat completions with retry on transient errors."""
    return await complete(prompt, settings, system_prompt)
