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

import asyncio
import functools
import logging
import math
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


def _run_sync(fn, /, *args, **kwargs):
    """
    Run a synchronous callable in the default ThreadPoolExecutor so that
    blocking ChromaDB I/O does not stall the async event loop.
    """
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))

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
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )

    # ── Indexing ───────────────────────────────────────────────────────────────

    async def add_document_chunks(
        self,
        document_id: str,
        user_id: str,
        filename: str,
        chunks: List[str],
        chunk_metadatas: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
    ):
        """
        Generates embeddings with cache-awareness and indexes chunks into ChromaDB.
        chunk_metadatas: optional per-chunk extra metadata (e.g., page_number).
        api_key: user's runtime Gemini API key. Must be passed so ingestion uses
                 real semantic embeddings instead of mock random vectors.
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
            fresh = await EmbeddingService.get_embeddings(uncached_texts, api_key=api_key)
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

        await _run_sync(collection.add, ids=ids, embeddings=embeddings, metadatas=metadatas, documents=chunks)
        logger.info(f"[VectorStore] Indexed {len(chunks)} chunks for document {document_id}")

    async def delete_document_chunks(self, document_id: str, user_id: str = ""):
        """Delete all chunks for a document and invalidate only that user's retrieval cache.

        P1-2 FIX: Pass user_id so only the owning user's cached results are cleared,
        rather than flushing the entire cache for all users.
        """
        collection = self.get_collection()

        # If user_id was not passed, try to resolve it from stored chunk metadata
        # so we still invalidate the correct per-user cache slice.
        if not user_id:
            try:
                existing = await _run_sync(
                    collection.get,
                    where={"document_id": document_id},
                    include=["metadatas"],
                    limit=1,
                )
                if existing and existing.get("metadatas"):
                    user_id = existing["metadatas"][0].get("user_id", "")
            except Exception:
                pass

        await _run_sync(collection.delete, where={"document_id": document_id})
        # Invalidate only this user's retrieval cache (not all users)
        await retrieval_cache.invalidate_user(user_id)

    # ── Hybrid Retrieval ───────────────────────────────────────────────────────

    async def query_relevant_chunks(
        self,
        user_id: str,
        query: str,
        k: int = 5,
        dense_weight: float = 0.7,
        bm25_weight: float = 0.3,
        where_filter: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
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
        query_embedding = await self._get_query_embedding(query, api_key=api_key)
        collection = self.get_collection()

        # Build ChromaDB filter combining user_id with any optional metadata filters
        chroma_filter: Dict[str, Any] = {"user_id": user_id}
        if where_filter:
            # Combine where_filter keys with user_id
            # NOTE: Use fk/fv to avoid shadowing the function parameter `k` (retrieval depth)
            for fk, fv in where_filter.items():
                if fk != "user_id" and fv is not None:
                    chroma_filter[fk] = fv

        filter_clause = chroma_filter if len(chroma_filter) == 1 else {"$and": [{fk: fv} for fk, fv in chroma_filter.items()]}

        # 1. Fetch dense vector query candidates
        dense_docs, dense_metas, dense_dists = [], [], []
        try:
            results = await _run_sync(
                collection.query,
                query_embeddings=[query_embedding],
                n_results=max(k * 5, 50),
                where=filter_clause,
            )
            if results and results.get("documents") and results["documents"][0]:
                dense_docs = results["documents"][0]
                dense_metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(dense_docs)
                dense_dists = results["distances"][0] if results.get("distances") else [0.0] * len(dense_docs)
        except Exception as exc:
            logger.error(f"[VectorStore] ChromaDB dense query failed: {exc}")

        # 2. Fetch full corpus chunks for BM25 keyword matching across all user files
        corpus_docs, corpus_metas = [], []
        try:
            corpus_res = await _run_sync(
                collection.get,
                where=filter_clause,
                include=["documents", "metadatas"],
            )
            if corpus_res and corpus_res.get("documents"):
                corpus_docs = corpus_res["documents"]
                corpus_metas = corpus_res["metadatas"] if corpus_res.get("metadatas") else [{}] * len(corpus_docs)
        except Exception as exc:
            logger.error(f"[VectorStore] ChromaDB corpus fetch failed: {exc}")

        # Combine candidates (deduplicated by doc_id + chunk_index + content)
        candidate_map: Dict[Tuple[str, int, str], Dict[str, Any]] = {}
        
        # Dense ranks
        for rank, i in enumerate(range(len(dense_docs))):
            meta = dense_metas[i] if i < len(dense_metas) else {}
            key = (str(meta.get("document_id")), int(meta.get("chunk_index", 0)), dense_docs[i][:100])
            candidate_map[key] = {
                "doc": dense_docs[i],
                "meta": meta,
                "dist": dense_dists[i] if i < len(dense_dists) else 0.0,
                "dense_rank": rank,
            }

        # BM25 ranking across full corpus
        bm25_ranks = _bm25_rank(query, corpus_docs) if corpus_docs else {}
        for idx, rank in bm25_ranks.items():
            if rank < 30:  # Top 30 BM25 matches
                meta = corpus_metas[idx] if idx < len(corpus_metas) else {}
                key = (str(meta.get("document_id")), int(meta.get("chunk_index", 0)), corpus_docs[idx][:100])
                if key in candidate_map:
                    candidate_map[key]["bm25_rank"] = rank
                else:
                    candidate_map[key] = {
                        "doc": corpus_docs[idx],
                        "meta": meta,
                        "dist": 0.3 if rank == 0 else 0.5,
                        "dense_rank": 999,
                        "bm25_rank": rank,
                    }

        if not candidate_map:
            return []

        # 3. RRF Fusion
        fused_items: List[Dict[str, Any]] = []
        for key, item in candidate_map.items():
            d_rank = item.get("dense_rank", 999)
            b_rank = item.get("bm25_rank", 999)
            d_score = dense_weight / (_RRF_K + d_rank + 1)
            b_score = bm25_weight / (_RRF_K + b_rank + 1)
            fused_score = d_score + b_score

            dist = item.get("dist", 0.0)
            confidence = round(max(0.0, 1.0 - float(dist)), 3)
            if b_rank == 0:
                confidence = max(confidence, 0.90)
            elif b_rank < 3:
                confidence = max(confidence, 0.75)

            meta = item["meta"]
            fused_items.append({
                "type":        "chunk",
                "content":     item["doc"],
                "filename":    meta.get("filename", "unknown"),
                "document_id": meta.get("document_id"),
                "chunk_id":    meta.get("chunk_index"),
                "page_number": meta.get("page_number", 1),
                "distance":    float(dist),
                "confidence":  confidence,
                "rrf_score":   round(fused_score, 6),
            })

        fused_items.sort(key=lambda x: x["rrf_score"], reverse=True)
        chunks = fused_items[:k]

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

        import time
        start_t = time.perf_counter()
        candidate_chunks = chunks[:10]
        initial_rank_ids = [c.get("chunk_id", f"idx_{i}") for i, c in enumerate(candidate_chunks)]

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
            # Dynamic timeout: allow 3s per chunk, capped at 20s total.
            # Previously hardcoded at 2.0s which was always less than the 8s
            # per-call timeout inside _call_llm_judge, causing silent fallback.
            _rerank_timeout = min(20.0, len(candidate_chunks) * 3.0)
            scored = await asyncio.wait_for(
                asyncio.gather(*[score_chunk(c) for c in candidate_chunks]),
                timeout=_rerank_timeout
            )

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

            elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
            final_rank_ids = [c.get("chunk_id", f"idx_{i}") for i, c in enumerate(result)]

            logger.info(
                f"[VectorStore] Cross-Encoder Rerank Completed in {elapsed_ms}ms | "
                f"Initial Ranking: {initial_rank_ids} -> Final Ranking: {final_rank_ids} | "
                f"Count: {len(chunks)} -> {len(result)} (threshold={threshold})"
            )
            return result

        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
            logger.warning(f"[VectorStore] Cross-encoder rerank failed after {elapsed_ms}ms (using original): {exc}")
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
    async def _get_query_embedding(query: str, api_key: Optional[str] = None) -> List[float]:
        """Get query embedding with cache support."""
        cached = await embedding_cache.get(query)
        if cached is not None:
            return cached
        vec = await EmbeddingService.get_embedding(query, api_key=api_key)
        await embedding_cache.set(query, vec)
        return vec


# ─────────────────────────────────────────────────────────────────────────────
#  BM25 ranking helper (no external library needed)
# ─────────────────────────────────────────────────────────────────────────────

_BM25_STOPWORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves"
})

def _bm25_rank(
    query: str,
    docs: List[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> Dict[int, int]:
    """
    Compute BM25 scores for each document and return a rank dict {doc_index: rank}.
    Rank 0 = highest relevance. Stopwords are filtered to prevent precision degradation.
    """
    all_terms = re.findall(r"\w+", query.lower())
    query_terms = [t for t in all_terms if t not in _BM25_STOPWORDS and len(t) > 1]
    if not query_terms:
        query_terms = all_terms
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
