"""Embedding service for generating vectors from text."""

from __future__ import annotations

import asyncio
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(self, model_name: str, cache_folder: str | None = None):
        self.model = SentenceTransformer(model_name, cache_folder=cache_folder)

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for a given string."""
        loop = asyncio.get_running_loop()
        # Run CPU-bound encoding in executor to avoid blocking event loop
        embeddings = await loop.run_in_executor(None, self.model.encode, text)
        return embeddings.tolist()


_instance: EmbeddingService | None = None


def get_embedding_service(model_name: str, cache_folder: str | None = None) -> EmbeddingService:
    global _instance
    if _instance is None:
        _instance = EmbeddingService(model_name, cache_folder)
    return _instance
