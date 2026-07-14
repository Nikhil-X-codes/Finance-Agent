"""Embedding service for generating vectors using the Hugging Face Serverless Inference API."""

from __future__ import annotations

import asyncio
import httpx
from src.config.settings import settings


class EmbeddingService:
    def __init__(self, model_name: str, cache_folder: str | None = None):
        self.model_name = model_name
        self.client = httpx.AsyncClient(timeout=30.0)

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector using Hugging Face Serverless Inference API."""
        headers = {"Authorization": f"Bearer {settings.hf_token}"}
        payload = {"inputs": text}
        
        # Use Hugging Face Feature Extraction endpoint
        api_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.model_name}"
        
        # Retry logic in case the model is still loading on the serverless instance
        for attempt in range(5):
            try:
                response = await self.client.post(api_url, headers=headers, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    # HF feature-extraction returns a list of floats for a single string
                    if isinstance(result, list) and len(result) > 0:
                        # Handle nested lists if returned
                        if isinstance(result[0], list):
                            return [float(x) for x in result[0]]
                        return [float(x) for x in result]
                    raise ValueError("Unexpected HF response format")
                elif response.status_code == 503:
                    # Model loading, wait and retry
                    err_data = response.json()
                    estimated_time = err_data.get("estimated_time", 5.0)
                    await asyncio.sleep(min(estimated_time, 2.0))
                else:
                    response.raise_for_status()
            except Exception as e:
                if attempt == 4:
                    raise e
                await asyncio.sleep(1.0)
                
        raise RuntimeError(f"Failed to generate embedding: HF API returned status {response.status_code}")


_instance: EmbeddingService | None = None


def get_embedding_service(model_name: str, cache_folder: str | None = None) -> EmbeddingService:
    global _instance
    if _instance is None:
        _instance = EmbeddingService(model_name, cache_folder)
    return _instance
