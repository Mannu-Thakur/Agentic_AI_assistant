import httpx
import logging
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    @staticmethod
    def _generate_mock_embedding(text: str, dimension: int = 768) -> List[float]:
        """
        Generate a deterministic unit-normalized mock embedding based on SHA-256 hash.
        This provides consistent vectors for the same input across all process restarts.
        """
        import random
        import hashlib
        import struct

        # Convert text to a 32-bit deterministic seed via SHA-256
        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        seed = struct.unpack(">I", hash_bytes[:4])[0]
        rng = random.Random(seed)
        vec = [rng.gauss(0, 1) for _ in range(dimension)]
        # Normalize the vector to unit length
        norm = sum(x**2 for x in vec)**0.5
        if norm > 0:
            return [x / norm for x in vec]
        return vec

    @classmethod
    async def get_embedding(cls, text: str, api_key: Optional[str] = None) -> List[float]:
        """
        Generates a 768-dimensional embedding vector for a single text using text-embedding-004.
        """
        key_to_use = api_key or settings.GEMINI_API_KEY
        if not key_to_use or str(key_to_use).startswith("mock_"):
            return cls._generate_mock_embedding(text)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={key_to_use}"
        payload = {
            "model": "models/text-embedding-004",
            "content": {
                "parts": [{"text": text}]
            }
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data["embedding"]["values"]
                else:
                    logger.error(f"Gemini embedding API failed with code {response.status_code}: {response.text}")
                    return cls._generate_mock_embedding(text)
        except Exception as e:
            logger.error(f"Error calling Gemini embedding API: {str(e)}")
            return cls._generate_mock_embedding(text)

    @classmethod
    async def get_embeddings(cls, texts: List[str], api_key: Optional[str] = None) -> List[List[float]]:
        """
        Generates 768-dimensional embedding vectors for a list of texts in batch.
        """
        if not texts:
            return []

        key_to_use = api_key or settings.GEMINI_API_KEY
        if not key_to_use or str(key_to_use).startswith("mock_"):
            return [cls._generate_mock_embedding(t) for t in texts]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents?key={key_to_use}"
        payload = {
            "requests": [
                {
                    "model": "models/text-embedding-004",
                    "content": {
                        "parts": [{"text": text}]
                    }
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
                else:
                    logger.error(f"Gemini batch embedding API failed with code {response.status_code}: {response.text}")
                    return [cls._generate_mock_embedding(t) for t in texts]
        except Exception as e:
            logger.error(f"Error calling Gemini batch embedding API: {str(e)}")
            return [cls._generate_mock_embedding(t) for t in texts]
