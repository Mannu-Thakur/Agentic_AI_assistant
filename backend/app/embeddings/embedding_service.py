import asyncio
import httpx
import logging
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Generates real embedding vectors via Google Gemini embedding models:
      - models/gemini-embedding-001
      - models/gemini-embedding-2
      - models/gemini-embedding-2-preview

    Design contract:
      - NEVER falls back to mock/random vectors in production.
      - Uses active, verified Gemini embedding models (outputDimensionality: 768).
      - Batches requests in slices of <= 50 to honor Gemini's 100-request limit.
      - Automatically sanitizes empty/whitespace chunks to avoid HTTP 400.
      - Auto-resolves verified Google key from DB if not explicitly passed.
      - Retries transient rate limits (HTTP 429) or service unavailable (503).
    """

    CANDIDATE_MODELS = [
        "models/gemini-embedding-001",
        "models/gemini-embedding-2",
        "models/gemini-embedding-2-preview",
    ]

    MAX_BATCH_SIZE = 50

    @classmethod
    async def _resolve_api_key(cls, api_key: Optional[str] = None) -> str:
        """
        Resolves the Gemini API key to use in order of priority:
          1. Explicitly supplied `api_key` argument
          2. Server-level `settings.GEMINI_API_KEY`
          3. Any active, verified Google key in the SQLite/PostgreSQL `api_keys` table
        """
        if api_key and api_key.strip():
            return api_key.strip()

        if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip():
            return settings.GEMINI_API_KEY.strip()

        # Database fallback
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.user import ApiKey
            from app.core.security import decrypt_api_key
            from sqlalchemy.future import select

            async with AsyncSessionLocal() as session:
                stmt = select(ApiKey).where(
                    ApiKey.provider_name.in_(["google", "gemini"]),
                    ApiKey.status == "VERIFIED",
                ).order_by(ApiKey.verified_at.desc())
                result = await session.execute(stmt)
                db_key = result.scalars().first()
                if db_key and db_key.encrypted_api_key:
                    try:
                        decrypted = decrypt_api_key(db_key.encrypted_api_key)
                        if decrypted and decrypted.strip():
                            return decrypted.strip()
                    except Exception as dec_err:
                        logger.warning(f"[EmbeddingService] Failed to decrypt DB Google key: {dec_err}")
        except Exception as db_err:
            logger.warning(f"[EmbeddingService] DB key lookup failed: {db_err}")

        raise RuntimeError(
            "Google Gemini API key is not configured. "
            "Please add and verify your Google Gemini API key in Settings → AI Models → Google Gemini."
        )

    @classmethod
    async def get_embedding(cls, text: str, api_key: Optional[str] = None) -> List[float]:
        """
        Generates an embedding vector for a single text using Gemini embedding models.
        """
        clean_text = (text or "").strip()
        if not clean_text:
            return [0.0] * 768

        key_to_use = await cls._resolve_api_key(api_key)
        errors: dict[str, str] = {}

        for model in cls.CANDIDATE_MODELS:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"{model}:embedContent?key={key_to_use}"
            )
            payload = {
                "model": model,
                "content": {"parts": [{"text": clean_text}]},
                "outputDimensionality": 768,
            }

            for attempt in range(2):
                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        response = await client.post(url, json=payload)

                    if response.status_code == 200:
                        data = response.json()
                        return data["embedding"]["values"]

                    # Transient retry for 429 or 503
                    if response.status_code in (429, 503) and attempt == 0:
                        logger.warning(f"[EmbeddingService] Model {model} returned HTTP {response.status_code}. Retrying in 1.5s...")
                        await asyncio.sleep(1.5)
                        continue

                    err_summary = response.text[:300]
                    errors[model] = f"HTTP {response.status_code}: {err_summary}"
                    logger.warning(f"[EmbeddingService] Model {model} failed: {errors[model]}")
                    break

                except httpx.RequestError as exc:
                    if attempt == 0:
                        await asyncio.sleep(1.0)
                        continue
                    errors[model] = f"Network error ({model}): {exc}"
                    logger.warning(f"[EmbeddingService] Network error on {model}: {exc}")
                    break

        error_details = "; ".join(f"{m} -> {e}" for m, e in errors.items())
        raise RuntimeError(f"Gemini embedding API failed across active models: {error_details}")

    @classmethod
    async def get_embeddings(
        cls, texts: List[str], api_key: Optional[str] = None
    ) -> List[List[float]]:
        """
        Generates embedding vectors for a batch of texts via Gemini batchEmbedContents.
        Batches texts into slices of <= 50 to strictly respect Gemini limits.
        """
        if not texts:
            return []

        key_to_use = await cls._resolve_api_key(api_key)

        # Sanitize texts: Gemini rejects empty string parts with HTTP 400
        sanitized_texts = [
            t.strip() if t and t.strip() else " "
            for t in texts
        ]

        all_embeddings: List[List[float]] = []

        # Process in batches of MAX_BATCH_SIZE (50)
        for batch_start in range(0, len(sanitized_texts), cls.MAX_BATCH_SIZE):
            batch_slice = sanitized_texts[batch_start : batch_start + cls.MAX_BATCH_SIZE]
            batch_success = False
            errors: dict[str, str] = {}

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
                        for text in batch_slice
                    ]
                }

                for attempt in range(2):
                    try:
                        async with httpx.AsyncClient(timeout=40.0) as client:
                            response = await client.post(url, json=payload)

                        if response.status_code == 200:
                            data = response.json()
                            slice_embeddings = [item["values"] for item in data["embeddings"]]
                            all_embeddings.extend(slice_embeddings)
                            batch_success = True
                            break

                        if response.status_code in (429, 503) and attempt == 0:
                            logger.warning(f"[EmbeddingService] Batch {model} returned HTTP {response.status_code}. Retrying in 1.5s...")
                            await asyncio.sleep(1.5)
                            continue

                        err_summary = response.text[:300]
                        errors[model] = f"HTTP {response.status_code}: {err_summary}"
                        logger.warning(f"[EmbeddingService] Batch {model} failed: {errors[model]}")
                        break

                    except httpx.RequestError as exc:
                        if attempt == 0:
                            await asyncio.sleep(1.0)
                            continue
                        errors[model] = f"Network error ({model}): {exc}"
                        logger.warning(f"[EmbeddingService] Batch network error on {model}: {exc}")
                        break

                if batch_success:
                    break

            if not batch_success:
                error_details = "; ".join(f"{m} -> {e}" for m, e in errors.items())
                raise RuntimeError(
                    f"Gemini batch embedding API failed for chunks [{batch_start}:{batch_start+len(batch_slice)}] across active models: {error_details}"
                )

        return all_embeddings
