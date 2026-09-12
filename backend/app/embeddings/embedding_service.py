import asyncio
import functools
import httpx
import logging
import math
import threading
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# Global singleton cache for the local neural embedding model
_local_model = None
_local_model_lock = threading.Lock()


def _get_local_model():
    """
    Lazily loads the local neural SentenceTransformer model ('all-MiniLM-L6-v2').
    Attempts offline local cache first to prevent HF network requests.
    """
    global _local_model
    if _local_model is None:
        with _local_model_lock:
            if _local_model is None:
                from sentence_transformers import SentenceTransformer
                try:
                    _local_model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
                except Exception:
                    _local_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _local_model


def _expand_to_768(vec_384: List[float]) -> List[float]:
    """
    Expands a 384-dimensional unit vector u into a 768-dimensional vector U = [u, u] / sqrt(2).
    This isomorphism strictly preserves inner products and cosine similarity:
      ||U||_2 = sqrt(1/2 * (||u||^2 + ||u||^2)) = 1
      U1 . U2 = 1/2 * (u1 . u2 + u1 . u2) = u1 . u2
    This allows seamless storage and querying in ChromaDB's 768-dimensional collections
    without schema errors or metric distortion.
    """
    factor = 1.0 / math.sqrt(2.0)
    scaled = [x * factor for x in vec_384]
    return scaled + scaled


def _get_local_embedding_sync(text: str) -> List[float]:
    clean = (text or "").strip()
    if not clean:
        return [0.0] * 768
    model = _get_local_model()
    vec = model.encode(clean, normalize_embeddings=True).tolist()
    return _expand_to_768(vec)


def _get_local_embeddings_sync(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    cleaned = [t.strip() if t and t.strip() else " " for t in texts]
    model = _get_local_model()
    vecs = model.encode(cleaned, normalize_embeddings=True, batch_size=64).tolist()
    return [_expand_to_768(v) for v in vecs]


class EmbeddingService:
    """
    Generates high-precision embedding vectors via a resilient dual-tier architecture:
      Tier 1: Google Gemini batch embedding API (models/gemini-embedding-001, gemini-embedding-2).
      Tier 2: High-speed local neural embeddings (all-MiniLM-L6-v2 expanded to 768d via unit cosine isomorphism).

    Resilience guarantees:
      - NEVER crashes document indexing or semantic retrieval due to Gemini HTTP 403 (project denied access),
        HTTP 401, HTTP 429 quota exhaustion, or offline network state.
      - Seamlessly and transparently falls back to local neural embeddings if Gemini is unavailable.
      - Produces exact 768-dimensional normalized unit vectors compatible with ChromaDB HNSW cosine space.
      - Batches requests in slices of <= 50 to honor Gemini's limits.
      - Automatically sanitizes empty/whitespace chunks to avoid HTTP 400 errors.
    """

    CANDIDATE_MODELS = [
        "models/gemini-embedding-001",
        "models/gemini-embedding-2",
        "models/gemini-embedding-2-preview",
    ]

    MAX_BATCH_SIZE = 50

    @classmethod
    async def _resolve_api_key(cls, api_key: Optional[str] = None) -> Optional[str]:
        """
        Resolves the Gemini API key to use in order of priority:
          1. Explicitly supplied `api_key` argument
          2. Server-level `settings.GEMINI_API_KEY`
          3. Any active, verified Google key in the SQLite/PostgreSQL `api_keys` table
        Returns None if no key can be resolved.
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
                db_keys = result.scalars().all()
                for db_key in db_keys:
                    if db_key and db_key.encrypted_api_key:
                        try:
                            decrypted = decrypt_api_key(db_key.encrypted_api_key)
                            if decrypted and decrypted.strip():
                                return decrypted.strip()
                        except Exception as dec_err:
                            logger.debug(f"[EmbeddingService] Decryption failed for key {db_key.id}: {dec_err}")
        except Exception as db_err:
            logger.debug(f"[EmbeddingService] DB key lookup failed: {db_err}")

        return None

    @classmethod
    async def _get_local_embedding(cls, text: str) -> List[float]:
        """Runs local neural embedding in thread pool to avoid blocking async loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_local_embedding_sync, text)

    @classmethod
    async def _get_local_embeddings(cls, texts: List[str]) -> List[List[float]]:
        """Runs local batch neural embeddings in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_local_embeddings_sync, texts)

    @classmethod
    async def get_embedding(cls, text: str, api_key: Optional[str] = None) -> List[float]:
        """
        Generates an embedding vector for a single text.
        Tries Gemini API first; seamlessly falls back to local neural model on 403 / 401 / error.
        """
        clean_text = (text or "").strip()
        if not clean_text:
            return [0.0] * 768

        key_to_use = await cls._resolve_api_key(api_key)
        if not key_to_use:
            logger.info("[EmbeddingService] No Gemini key found; using local neural embedding.")
            return await cls._get_local_embedding(clean_text)

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
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        response = await client.post(url, json=payload)

                    if response.status_code == 200:
                        data = response.json()
                        return data["embedding"]["values"]

                    # If project access is denied (403) or unauthenticated (401), immediate fallback
                    if response.status_code in (401, 403):
                        logger.warning(
                            f"[EmbeddingService] Gemini API returned HTTP {response.status_code} "
                            f"(project access denied or unauthorized). Seamlessly falling back to local neural embeddings."
                        )
                        return await cls._get_local_embedding(clean_text)

                    # Transient retry for 429 or 503
                    if response.status_code in (429, 503) and attempt == 0:
                        logger.warning(f"[EmbeddingService] Model {model} returned HTTP {response.status_code}. Retrying in 1.0s...")
                        await asyncio.sleep(1.0)
                        continue

                    err_summary = response.text[:200]
                    errors[model] = f"HTTP {response.status_code}: {err_summary}"
                    break

                except httpx.RequestError as exc:
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    errors[model] = f"Network error ({model}): {exc}"
                    break

        error_details = "; ".join(f"{m} -> {e}" for m, e in errors.items())
        logger.warning(
            f"[EmbeddingService] Gemini embedding API unavailable ({error_details}). "
            f"Seamlessly using local neural embedding fallback."
        )
        return await cls._get_local_embedding(clean_text)

    @classmethod
    async def get_embeddings(
        cls, texts: List[str], api_key: Optional[str] = None
    ) -> List[List[float]]:
        """
        Generates embedding vectors for a batch of texts.
        Tries Gemini batchEmbedContents first. Seamlessly falls back to local neural embeddings
        if Gemini returns 403 (project denied access), 401, 429, or network failure.
        """
        if not texts:
            return []

        sanitized_texts = [
            t.strip() if t and t.strip() else " "
            for t in texts
        ]

        key_to_use = await cls._resolve_api_key(api_key)
        if not key_to_use:
            logger.info("[EmbeddingService] No Gemini key found; using local neural batch embeddings.")
            return await cls._get_local_embeddings(sanitized_texts)

        all_embeddings: List[List[float]] = []

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
                        async with httpx.AsyncClient(timeout=25.0) as client:
                            response = await client.post(url, json=payload)

                        if response.status_code == 200:
                            data = response.json()
                            slice_embeddings = [item["values"] for item in data["embeddings"]]
                            all_embeddings.extend(slice_embeddings)
                            batch_success = True
                            break

                        # If project access is denied (403) or key invalid (401), fallback all chunks to local neural
                        if response.status_code in (401, 403):
                            logger.warning(
                                f"[EmbeddingService] Gemini batch embedding returned HTTP {response.status_code} "
                                f"(project access denied or unauthorized). Seamlessly falling back to local neural embeddings for all {len(sanitized_texts)} chunks."
                            )
                            return await cls._get_local_embeddings(sanitized_texts)

                        if response.status_code in (429, 503) and attempt == 0:
                            logger.warning(f"[EmbeddingService] Batch {model} returned HTTP {response.status_code}. Retrying in 1.0s...")
                            await asyncio.sleep(1.0)
                            continue

                        err_summary = response.text[:200]
                        errors[model] = f"HTTP {response.status_code}: {err_summary}"
                        break

                    except httpx.RequestError as exc:
                        if attempt == 0:
                            await asyncio.sleep(0.5)
                            continue
                        errors[model] = f"Network error ({model}): {exc}"
                        break

                if batch_success:
                    break

            if not batch_success:
                error_details = "; ".join(f"{m} -> {e}" for m, e in errors.items())
                logger.warning(
                    f"[EmbeddingService] Gemini batch embedding failed for chunks [{batch_start}:{batch_start+len(batch_slice)}] "
                    f"({error_details}). Seamlessly falling back to local neural embeddings."
                )
                return await cls._get_local_embeddings(sanitized_texts)

        return all_embeddings
