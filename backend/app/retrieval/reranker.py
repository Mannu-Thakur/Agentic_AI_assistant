"""
app/retrieval/reranker.py — Production-grade cross-encoder reranker.

PRODUCTION FIX: Replaces the LLM-as-reranker pattern that fired 10 separate
API calls (one per chunk) per query, consuming Groq/Gemini quota and adding
up to 20 seconds of latency.

New approach
────────────
Uses ``sentence-transformers`` ``CrossEncoder`` model which runs locally (no API
key, no network call) and scores all chunks in a single batched forward pass:

  Model:   cross-encoder/ms-marco-MiniLM-L-6-v2
  Size:    ~22 MB (downloaded once, cached in ~/.cache/huggingface)
  Latency: ~50–200 ms for 10 chunks on CPU  (vs. 5–20 s for 10 LLM calls)
  Quality: MS-MARCO trained — matches or exceeds LLM judge for passage ranking

Graceful fallback
─────────────────
If ``sentence-transformers`` is not installed, or if the model fails to load,
``CrossEncoderReranker.rerank()`` falls back silently to returning the input
chunks in their original order.  No exception is raised to the caller.

Thread safety / async compat
─────────────────────────────
CrossEncoder.predict() is CPU-bound synchronous code.  It is wrapped in
``asyncio.get_event_loop().run_in_executor(None, ...)`` so the event loop
is never blocked during inference.

Singleton
─────────
One ``CrossEncoderReranker`` instance is created at module import time and
reused for all requests.  Model loading happens lazily on first call.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("app.retrieval.reranker")

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_MAX_CHUNK_CHARS = 512   # truncate chunk text fed to the cross-encoder


class CrossEncoderReranker:
    """
    Wraps a ``sentence_transformers.CrossEncoder`` and exposes an async
    ``rerank()`` interface compatible with ``VectorStore.rerank_chunks()``.
    """

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self._model_name  = model_name
        self._model       = None          # lazy-loaded on first call
        self._load_error: Optional[str] = None
        self._loaded      = False

    def _load_model(self) -> None:
        """Synchronous model load — called once from the thread pool."""
        if self._loaded:
            return
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import]
            t0 = time.perf_counter()
            self._model = CrossEncoder(self._model_name)
            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            logger.info(
                f"[Reranker] Loaded '{self._model_name}' in {elapsed} ms"
            )
        except ImportError:
            self._load_error = (
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers  "
                "Falling back to original chunk order."
            )
            logger.warning(f"[Reranker] {self._load_error}")
        except Exception as exc:
            self._load_error = f"Model load failed: {exc}"
            logger.warning(f"[Reranker] {self._load_error}")
        finally:
            self._loaded = True

    def _predict_sync(
        self,
        query:  str,
        chunks: List[Dict[str, Any]],
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Synchronous prediction — runs inside run_in_executor.
        Returns ``[(score, chunk), ...]`` sorted descending by score.
        """
        self._load_model()
        if self._model is None:
            # Model unavailable — return original order with neutral scores
            return [(0.5, c) for c in chunks]

        pairs = [
            (query, c.get("content", "")[:_MAX_CHUNK_CHARS])
            for c in chunks
        ]
        scores = self._model.predict(pairs)
        scored = list(zip(scores.tolist(), chunks))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    async def rerank(
        self,
        query:     str,
        chunks:    List[Dict[str, Any]],
        threshold: float = 0.0,
        top_k:     Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Async entry point — compatible with the existing VectorStore.rerank_chunks()
        call signature.

        Args:
            query:     User query string.
            chunks:    Candidate chunks from hybrid retrieval.
            threshold: Minimum cross-encoder score to retain (0.0 = keep all).
                       Note: cross-encoder scores are logits, not probabilities.
                       Typical range is -10 to +10.  Use 0.0 as a safe default.
            top_k:     Maximum number of chunks to return (None = all above threshold).

        Returns:
            Re-ranked chunks with ``rerank_score`` field added.
            Falls back to original order if model is unavailable.
        """
        if not chunks:
            return []

        t_start = time.perf_counter()
        candidates = chunks[:10]   # match the existing cap of 10

        try:
            loop = asyncio.get_event_loop()
            scored = await loop.run_in_executor(
                None, self._predict_sync, query, candidates
            )
        except Exception as exc:
            logger.warning(
                f"[Reranker] Inference failed (using original order): {exc}"
            )
            return chunks

        result: List[Dict[str, Any]] = []
        for score, chunk in scored:
            if score < threshold:
                continue
            enriched = dict(chunk)
            enriched["rerank_score"] = round(float(score), 4)
            # Blend cross-encoder score with existing confidence
            # Use sigmoid-like rescaling: sigmoid(score) ≈ confidence
            import math
            sigmoid_score = round(1.0 / (1.0 + math.exp(-float(score))), 3)
            enriched["confidence"] = round(
                max(enriched.get("confidence", sigmoid_score), sigmoid_score), 3
            )
            result.append(enriched)
            if top_k and len(result) >= top_k:
                break

        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 1)
        initial_ids = [c.get("chunk_id", f"idx_{i}") for i, c in enumerate(candidates)]
        final_ids   = [c.get("chunk_id", f"idx_{i}") for i, c in enumerate(result)]
        logger.info(
            f"[Reranker] Completed in {elapsed_ms} ms | "
            f"model='{self._model_name}' | "
            f"{len(candidates)} → {len(result)} chunks | "
            f"ranking: {initial_ids} → {final_ids}"
        )
        return result if result else chunks   # fallback: never return empty


# ─────────────────────────────────────────────────────────────────────────────
#  Module-level singleton — import this in vector_store.py
# ─────────────────────────────────────────────────────────────────────────────

cross_encoder_reranker = CrossEncoderReranker()
