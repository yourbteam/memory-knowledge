from __future__ import annotations

import asyncio
import threading

import structlog

from memory_knowledge.config import Settings

logger = structlog.get_logger()

# fastembed's TextEmbedding is synchronous and loads the ONNX model into memory
# once. We hold a single lazily-initialized instance per model name.
_model = None
_model_name: str | None = None
_lock = threading.Lock()

# Texts are embedded in bounded batches to cap peak memory on the shared host.
BATCH_SIZE = 64


def _get_model(model_name: str):
    """Return a process-wide singleton TextEmbedding for the given model."""
    global _model, _model_name
    if _model is not None and _model_name == model_name:
        return _model
    with _lock:
        if _model is None or _model_name != model_name:
            from fastembed import TextEmbedding

            logger.info("local_embed_model_loading", model=model_name)
            _model = TextEmbedding(model_name=model_name)
            _model_name = model_name
            logger.info("local_embed_model_loaded", model=model_name)
    return _model


def _embed_sync(texts: list[str], model_name: str) -> list[list[float]]:
    model = _get_model(model_name)
    # fastembed returns a generator of numpy float32 arrays, in input order.
    return [vec.tolist() for vec in model.embed(texts, batch_size=BATCH_SIZE)]


async def embed_texts(texts: list[str], settings: Settings) -> list[list[float]]:
    """Embed texts with the in-process fastembed model. No network, no API key."""
    if not texts:
        return []
    return await asyncio.to_thread(_embed_sync, texts, settings.embedding_model)
