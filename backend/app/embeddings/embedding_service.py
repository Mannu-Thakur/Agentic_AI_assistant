import httpx
import logging
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Generates real embedding vectors via Gemini embedding models (gemini-embedding-001).

    Design contract:
      - NEVER falls back to mock/random vectors in production.
      - Tries primary embedding model (gemini-embedding-001) with fallback to secondary models.
      - Raises RuntimeError immediately if the API key is missing or calls fail.
    """

    CANDIDATE_MODELS = [
        "models/gemini-embedding-001",
        "models/gemini-embedding-2-preview",
        "models/text-embedding-004",
    ]

    @classmethod
    async def get_embedding(cls, text: str, api_key: Optional[str] = None) -> List[float]:
        """
        Generates an embedding vector for a single text using Gemini embedding models.
        """
        key_to_use = api_key or settings.GEMINI_API_KEY

        if not key_to_use:
            raise RuntimeError(
                "Gemini API key is not configured. "
                "Add your Google Gemini API key in Settings → AI Models → Google Gemini."
            )

        last_error = ""
        for model in cls.CANDIDATE_MODELS:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"{model}:embedContent?key={key_to_use}"
            )
            payload = {
                "model": model,
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": 768,
            }

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    return data["embedding"]["values"]
                
                last_error = f"HTTP {response.status_code}: {response.text}"
                if response.status_code == 404:
                    continue  # try next candidate model

            except httpx.RequestError as exc:
                last_error = f"Network error calling Gemini embedding API ({model}): {exc}"

        raise RuntimeError(f"Gemini embedding API failed across models: {last_error}")

    @classmethod
    async def get_embeddings(
        cls, texts: List[str], api_key: Optional[str] = None
    ) -> List[List[float]]:
        """
        Generates embedding vectors for a batch of texts via Gemini batchEmbedContents.
        """
        if not texts:
            return []

        key_to_use = api_key or settings.GEMINI_API_KEY

        if not key_to_use:
            raise RuntimeError(
                "Gemini API key is not configured. "
                "Add your Google Gemini API key in Settings → AI Models → Google Gemini."
            )

        last_error = ""
        for model in cls.CANDIDATE_MODELS:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"{model}:batchEmbedContents?key={key_to_use}"
            )
            payload = {
                "requests": [
                    {
                        "model": model,
                        "content": {"parts": [{"text": text}]},
                        "outputDimensionality": 768,
                    }
                    for text in texts
                ]
            }

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    return [item["values"] for item in data["embeddings"]]

                last_error = f"HTTP {response.status_code}: {response.text}"
                if response.status_code == 404:
                    continue  # try next candidate model

            except httpx.RequestError as exc:
                last_error = f"Network error calling Gemini batch embedding API ({model}): {exc}"

        raise RuntimeError(f"Gemini batch embedding API failed across models: {last_error}")
