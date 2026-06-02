import os
import types

import pytest

from memory_knowledge.llm import local_embed, openai_client


@pytest.mark.asyncio
async def test_embed_empty_returns_empty():
    assert await openai_client.embed([], types.SimpleNamespace(embedding_provider="local")) == []


@pytest.mark.asyncio
async def test_embed_local_provider_uses_local_backend(monkeypatch):
    """embed() routes to the local backend (no OpenAI call) when provider=local."""
    captured: dict = {}

    async def fake_embed_texts(texts, settings):
        captured["texts"] = texts
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(local_embed, "embed_texts", fake_embed_texts)
    out = await openai_client.embed(["a", "b"], types.SimpleNamespace(embedding_provider="local"))

    assert out == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert captured["texts"] == ["a", "b"]


@pytest.mark.skipif(
    not os.environ.get("RUN_EMBED_INTEGRATION"),
    reason="downloads the bge-base model; set RUN_EMBED_INTEGRATION=1 to run",
)
@pytest.mark.asyncio
async def test_local_embed_real_model_768():
    settings = types.SimpleNamespace(embedding_model="BAAI/bge-base-en-v1.5")
    vecs = await local_embed.embed_texts(["hello world"], settings)
    assert len(vecs) == 1
    assert len(vecs[0]) == 768
    assert all(isinstance(x, float) for x in vecs[0])
