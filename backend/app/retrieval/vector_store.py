"""
app/retrieval/vector_store.py — Phase 3 Hybrid Retrieval Engine.

Enhancements:
  • Dense + BM25 hybrid retrieval with Reciprocal Rank Fusion (RRF)
  • Configurable dense/BM25 weights (default 0.7 / 0.3)
  • Cross-encoder re-ranking using LLM relevance judge
  • Context compression: deduplication + token-budget enforcement
  • Page-number metadata stored and returned per chunk
  • Embedding cache integration (EmbeddingCache from cache_service)
  • Retrieval result cache (RetrievalCache from cache_service)
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import chromadb

from app.core.config import settings
from app.embeddings.embedding_service import EmbeddingService
from app.core.cache_service import retrieval_cache, embedding_cache

logger = logging.getLogger("app.retrieval.vector_store")

# RRF rank constant (standard = 60)
_RRF_K = 60

# Maximum tokens to allow in combined context (rough char estimate at 4 chars/token)
_MAX_CONTEXT_CHARS = 12_000  # ≈ 3 000 tokens


class VectorStore:
    _instance = None
    _lock = None  # Initialized lazily to avoid import-time threading cost

    def __new__(cls, *args, **kwargs):
        import threading
        if cls._lock is None:
            cls._lock = threading.Lock()
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
                cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        os.makedirs(settings.VECTOR_DB_DIR, exist_ok=True)
        self.client = chromadb.PersistentClient(path=settings.VECTOR_DB_DIR)

    def get_collection(self, name: str = "document_chunks"):
        return self.client.get_or_create_collection(name=name)

    # ── Indexing ───────────────────────────────────────────────────────────────

    async def add_document_chunks(
        self,
        document_id: str,
        user_id: str,
        filename: str,
        chunks: List[str],
        chunk_metadatas: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Generates embeddings with cache-awareness and indexes chunks into ChromaDB.
        chunk_metadatas: optional per-chunk extra metadata (e.g., page_number).
        """
        if not chunks:
            return

        collection = self.get_collection()

        # ── Embedding with cache ───────────────────────────────────────────────
        cached_map = await embedding_cache.get_batch(chunks)
        embeddings: List[List[float]] = []
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for i, text in enumerate(chunks):
            cached = cached_map.get(text)
            if cached is not None:
                embeddings.append(cached)
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)
                embeddings.append([])  # placeholder

        if uncached_texts:
            fresh = await EmbeddingService.get_embeddings(uncached_texts)
            for idx, vec in zip(uncached_indices, fresh):
                embeddings[idx] = vec
            await embedding_cache.set_batch(dict(zip(uncached_texts, fresh)))

        # ── Build metadata ─────────────────────────────────────────────────────
        ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = []
        for i in range(len(chunks)):
            meta: Dict[str, Any] = {
                "document_id": document_id,
                "user_id":     user_id,
                "filename":    filename,
                "chunk_index": i,
                "page_number": 1,
            }
            if chunk_metadatas and i < len(chunk_metadatas):
                meta.update(chunk_metadatas[i])
            metadatas.append(meta)

        collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=chunks)
        logger.info(f"[VectorStore] Indexed {len(chunks)} chunks for document {document_id}")

    async def delete_document_chunks(self, document_id: str):
        collection = self.get_collection()
        collection.delete(where={"document_id": document_id})
        # Invalidate cached query results to prevent returning deleted documents
        await retrieval_cache.invalidate_user("")

    # ── Hybrid Retrieval ───────────────────────────────────────────────────────

    async def query_relevant_chunks(
        self,
        user_id: str,
        query: str,
        k: int = 5,
        dense_weight: float = 0.7,
        bm25_weight: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval: Dense + BM25 fused via Reciprocal Rank Fusion (RRF).

        1. Check retrieval cache.
        2. Dense vector query against ChromaDB.
        3. BM25 keyword search over fetched corpus.
        4. RRF fusion of both ranked lists.
        5. Return top-k fused results with confidence scores.
        """
        # Cache check
        cached = await retrieval_cache.get(user_id, query, k)
        if cached is not None:
            logger.debug(f"[VectorStore] Retrieval cache HIT for query='{query[:40]}'")
            return cached

        # ── Dense retrieval ────────────────────────────────────────────────────
        query_embedding = await self._get_query_embedding(query)
        collection = self.get_collection()

        # Fetch more candidates for re-ranking (3x)
        n_dense = min(k * 3, 50)
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_dense,
                where={"user_id": user_id},
            )
        except Exception as exc:
            logger.error(f"[VectorStore] ChromaDB query failed: {exc}")
            return []

        if not (results and results.get("documents") and results["documents"][0]):
            return []

        docs      = results["documents"][0]
        metas     = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

        # ── BM25 ranking ───────────────────────────────────────────────────────
        bm25_ranks = _bm25_rank(query, docs)  # {doc_index: rank}

        # ── RRF fusion ─────────────────────────────────────────────────────────
        fused_scores: Dict[int, float] = {}
        for dense_rank, i in enumerate(range(len(docs))):
            dense_score = dense_weight / (_RRF_K + dense_rank + 1)
            bm25_rank   = bm25_ranks.get(i, len(docs))
            bm25_score  = bm25_weight / (_RRF_K + bm25_rank + 1)
            fused_scores[i] = dense_score + bm25_score

        sorted_indices = sorted(fused_scores, key=lambda x: fused_scores[x], reverse=True)

        # ── Build result list ─────────────────────────────────────────────────
        chunks: List[Dict[str, Any]] = []
        for i in sorted_indices[:k]:
            meta = metas[i] if i < len(metas) else {}
            dist = distances[i] if i < len(distances) else 0.0
            # Convert distance to confidence: lower distance = higher confidence
            confidence = round(max(0.0, 1.0 - float(dist)), 3)
            chunks.append({
                "type":        "chunk",
                "content":     docs[i],
                "filename":    meta.get("filename", "unknown"),
                "document_id": meta.get("document_id"),
                "chunk_id":    meta.get("chunk_index"),
                "page_number": meta.get("page_number", 1),
                "distance":    float(dist),
                "confidence":  confidence,
                "rrf_score":   round(fused_scores[i], 6),
            })

        # ── Cache and return ──────────────────────────────────────────────────
        await retrieval_cache.set(user_id, query, k, chunks)
        return chunks

    # ── Cross-encoder re-ranking ───────────────────────────────────────────────

    @staticmethod
    async def rerank_chunks(
        query: str,
        chunks: List[Dict[str, Any]],
        config: dict,
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Re-rank chunks using an LLM relevance judge, filtering out semantically
        weak chunks below the confidence threshold.

        Args:
            query:     The user query.
            chunks:    Retrieved chunks from query_relevant_chunks().
            config:    LangGraph config dict (used for LLM key injection).
            threshold: Minimum confidence to retain a chunk (0.0–1.0).

        Returns:
            Filtered and re-ranked chunks (highest relevance first).
        """
        if not chunks:
            return []

        try:
            from app.agent.nodes import _call_llm_judge

            RERANK_PROMPT = (
                "You are a relevance scorer. Given the query and document chunk, "
                "rate the relevance on a scale 0.0 to 1.0. "
                "Reply with ONLY a JSON object: {{\"score\": <float>}}\n\n"
                "Query: {query}\n\nChunk:\n{chunk}"
            )

            async def score_chunk(chunk: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
                prompt = RERANK_PROMPT.format(
                    query=query,
                    chunk=chunk.get("content", "")[:600],
                )
                parsed = await _call_llm_judge(prompt, config)
                score = float(parsed.get("score", 0.5)) if parsed else 0.5
                return score, chunk

            import asyncio
            scored = await asyncio.gather(*[score_chunk(c) for c in chunks])

            reranked = sorted(
                [(score, chunk) for score, chunk in scored if score >= threshold],
                key=lambda x: x[0],
                reverse=True,
            )
            result = []
            for score, chunk in reranked:
                chunk["rerank_score"] = round(score, 3)
                chunk["confidence"]   = round(max(chunk.get("confidence", score), score), 3)
                result.append(chunk)

            logger.info(
                f"[VectorStore] Reranked {len(chunks)} → {len(result)} chunks "
                f"(threshold={threshold})"
            )
            return result

        except Exception as exc:
            logger.warning(f"[VectorStore] Cross-encoder rerank failed (using original): {exc}")
            return chunks

    # ── Context compression ────────────────────────────────────────────────────

    @staticmethod
    def compress_context(
        chunks: List[Dict[str, Any]],
        max_chars: int = _MAX_CONTEXT_CHARS,
    ) -> List[Dict[str, Any]]:
        """
        Remove duplicate and near-duplicate chunks, then enforce a token budget.

        Strategy:
          1. Exact deduplication by content hash.
          2. Near-duplicate removal (>80% word overlap).
          3. Token-budget truncation (highest confidence chunks kept first).
        """
        if not chunks:
            return []

        # Sort by confidence (descending) before dedup so we keep the best copy
        sorted_chunks = sorted(chunks, key=lambda c: c.get("confidence", 0), reverse=True)

        seen_contents: List[str] = []
        deduped: List[Dict[str, Any]] = []

        for chunk in sorted_chunks:
            content = chunk.get("content", "")
            if not content.strip():
                continue

            # Exact match
            if content in seen_contents:
                continue

            # Near-duplicate (80% word overlap)
            c_words = set(content.lower().split())
            is_near_dup = False
            for seen in seen_contents:
                s_words = set(seen.lower().split())
                if s_words:
                    overlap = len(c_words & s_words) / max(len(c_words), len(s_words))
                    if overlap > 0.80:
                        is_near_dup = True
                        break

            if not is_near_dup:
                deduped.append(chunk)
                seen_contents.append(content)

        # Token-budget enforcement
        budget_chunks: List[Dict[str, Any]] = []
        total_chars = 0
        for chunk in deduped:
            length = len(chunk.get("content", ""))
            if total_chars + length > max_chars:
                # Truncate this chunk to fit remaining budget
                remaining = max_chars - total_chars
                if remaining > 100:
                    truncated = dict(chunk)
                    truncated["content"] = chunk["content"][:remaining] + "…"
                    budget_chunks.append(truncated)
                break
            budget_chunks.append(chunk)
            total_chars += length

        logger.info(
            f"[VectorStore] Compression: {len(chunks)} → {len(deduped)} (dedup) "
            f"→ {len(budget_chunks)} (budget)"
        )
        return budget_chunks

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    async def _get_query_embedding(query: str) -> List[float]:
        """Get query embedding with cache support."""
        cached = await embedding_cache.get(query)
        if cached is not None:
            return cached
        vec = await EmbeddingService.get_embedding(query)
        await embedding_cache.set(query, vec)
        return vec


# ─────────────────────────────────────────────────────────────────────────────
#  BM25 ranking helper (no external library needed)
# ─────────────────────────────────────────────────────────────────────────────

def _bm25_rank(
    query: str,
    docs: List[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> Dict[int, int]:
    """
    Compute BM25 scores for each document and return a rank dict {doc_index: rank}.
    Rank 0 = highest relevance.
    """
    query_terms = re.findall(r"\w+", query.lower())
    if not query_terms:
        return {}

    tokenized = [re.findall(r"\w+", d.lower()) for d in docs]
    doc_lengths = [len(t) for t in tokenized]
    avg_dl = sum(doc_lengths) / max(len(doc_lengths), 1)
    N = len(docs)

    # Document frequency
    df: Dict[str, int] = defaultdict(int)
    for tokens in tokenized:
        for term in set(tokens):
            df[term] += 1

    scores: List[float] = []
    for i, tokens in enumerate(tokenized):
        tf_map: Dict[str, int] = defaultdict(int)
        for t in tokens:
            tf_map[t] += 1

        score = 0.0
        for term in query_terms:
            tf  = tf_map.get(term, 0)
            idf = math.log((N - df[term] + 0.5) / (df[term] + 0.5) + 1)
            dl  = doc_lengths[i]
            tf_norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avg_dl))
            score += idf * tf_norm
        scores.append(score)

    # Rank by score (descending) → index: rank
    ranked = sorted(range(len(scores)), key=lambda x: scores[x], reverse=True)
    return {doc_idx: rank for rank, doc_idx in enumerate(ranked)}
