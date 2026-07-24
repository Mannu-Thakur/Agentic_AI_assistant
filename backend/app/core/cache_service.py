"""
app/core/cache_service.py — Unified caching service for Phase 3.

Provides:
  - RetrievalCache   : keyed by (user_id, query_text, k)
  - EmbeddingCache   : keyed by sha256 of text — avoids re-embedding duplicates
  - WebSearchCache   : keyed by search query — respects configurable TTL
  - CacheStats       : counters for hit/miss ratio telemetry
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("app.core.cache_service")


# ─────────────────────────────────────────────────────────────────────────────
#  LRU in-memory cache (fallback when Redis is unavailable)
# ─────────────────────────────────────────────────────────────────────────────

class _LRUCache:
    """Thread-safe, time-aware LRU cache with configurable max size and TTL."""

    def __init__(self, maxsize: int = 512, default_ttl: int = 300):
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                return None
            value, expires_at = self._cache[key]
            if time.monotonic() > expires_at:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        async with self._lock:
            ttl = ttl if ttl is not None else self._default_ttl
            expires_at = time.monotonic() + ttl
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, expires_at)
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)  # evict LRU

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


# ─────────────────────────────────────────────────────────────────────────────
#  Cache statistics
# ─────────────────────────────────────────────────────────────────────────────

class CacheStats:
    """Thread-safe counter for cache hit/miss telemetry."""

    def __init__(self, name: str):
        self.name = name
        self.hits = 0
        self.misses = 0

    def record_hit(self) -> None:
        self.hits += 1

    def record_miss(self) -> None:
        self.misses += 1

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cache": self.name,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hit_rate,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Retrieval Cache  (chunks list, per user + query + k)
# ─────────────────────────────────────────────────────────────────────────────

class RetrievalCache:
    """
    Caches retrieved document chunk lists to avoid repeated ChromaDB lookups
    for identical (user_id, query, k) tuples within the same session.
    TTL: 120 seconds by default.
    """

    _DEFAULT_TTL = 120

    def __init__(self):
        self._lru = _LRUCache(maxsize=256, default_ttl=self._DEFAULT_TTL)
        self.stats = CacheStats("retrieval")

    @staticmethod
    def _key(user_id: str, query: str, k: int) -> str:
        raw = f"{user_id}|{query.strip().lower()}|{k}"
        return "ret:" + hashlib.sha256(raw.encode()).hexdigest()[:24]

    async def get(self, user_id: str, query: str, k: int) -> Optional[List[Dict[str, Any]]]:
        key = self._key(user_id, query, k)
        result = await self._lru.get(key)
        if result is not None:
            self.stats.record_hit()
            logger.debug(f"[RetrievalCache] HIT  key={key[:12]}")
        else:
            self.stats.record_miss()
        return result

    async def set(self, user_id: str, query: str, k: int, chunks: List[Dict[str, Any]]) -> None:
        key = self._key(user_id, query, k)
        await self._lru.set(key, chunks, ttl=self._DEFAULT_TTL)
        logger.debug(f"[RetrievalCache] SET  key={key[:12]} ({len(chunks)} chunks)")

    async def invalidate_user(self, user_id: str) -> None:
        """Clear all cached retrieval entries for a user (called after document upload)."""
        await self._lru.clear()
        logger.debug(f"[RetrievalCache] INVALIDATED for user {user_id}")


# ─────────────────────────────────────────────────────────────────────────────
#  Embedding Cache  (float list, per text hash)
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingCache:
    """
    Caches embedding vectors keyed by sha256 of the input text.
    TTL: 3600 seconds (1 hour) — embeddings are stable.
    """

    _DEFAULT_TTL = 3600

    def __init__(self):
        self._lru = _LRUCache(maxsize=4096, default_ttl=self._DEFAULT_TTL)
        self.stats = CacheStats("embedding")

    @staticmethod
    def _key(text: str) -> str:
        return "emb:" + hashlib.sha256(text.encode()).hexdigest()[:24]

    async def get(self, text: str) -> Optional[List[float]]:
        key = self._key(text)
        result = await self._lru.get(key)
        if result is not None:
            self.stats.record_hit()
        else:
            self.stats.record_miss()
        return result

    async def set(self, text: str, vector: List[float]) -> None:
        key = self._key(text)
        await self._lru.set(key, vector, ttl=self._DEFAULT_TTL)

    async def get_batch(self, texts: List[str]) -> Dict[str, Optional[List[float]]]:
        results = {}
        for text in texts:
            results[text] = await self.get(text)
        return results

    async def set_batch(self, text_vector_pairs: Dict[str, List[float]]) -> None:
        for text, vector in text_vector_pairs.items():
            await self.set(text, vector)


# ─────────────────────────────────────────────────────────────────────────────
#  Web Search Cache  (string result, per query)
# ─────────────────────────────────────────────────────────────────────────────

class WebSearchCache:
    """
    Caches Tavily web search results to reduce API costs.
    TTL: 600 seconds (10 minutes).
    """

    _DEFAULT_TTL = 600

    def __init__(self):
        self._lru = _LRUCache(maxsize=128, default_ttl=self._DEFAULT_TTL)
        self.stats = CacheStats("web_search")

    @staticmethod
    def _key(query: str) -> str:
        return "web:" + hashlib.sha256(query.strip().lower().encode()).hexdigest()[:24]

    async def get(self, query: str) -> Optional[str]:
        key = self._key(query)
        result = await self._lru.get(key)
        if result is not None:
            self.stats.record_hit()
            logger.debug(f"[WebSearchCache] HIT  query='{query[:40]}'")
        else:
            self.stats.record_miss()
        return result

    async def set(self, query: str, result: str) -> None:
        key = self._key(query)
        await self._lru.set(key, result, ttl=self._DEFAULT_TTL)
        logger.debug(f"[WebSearchCache] SET  query='{query[:40]}'")


# ─────────────────────────────────────────────────────────────────────────────
#  Global singletons
# ─────────────────────────────────────────────────────────────────────────────

retrieval_cache  = RetrievalCache()
embedding_cache  = EmbeddingCache()
web_search_cache = WebSearchCache()


def get_all_cache_stats() -> List[Dict[str, Any]]:
    """Returns stats from all caches — used by the telemetry module."""
    return [
        retrieval_cache.stats.to_dict(),
        embedding_cache.stats.to_dict(),
        web_search_cache.stats.to_dict(),
    ]
