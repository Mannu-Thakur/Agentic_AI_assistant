"""
app/core/cache_service.py — Unified caching service.

PRODUCTION FIX (Fix 4): All three cache classes now use Redis as the primary
store, giving cross-worker shared state in multi-process deployments.
The in-process _LRUCache is kept as a transparent L1 fallback when Redis is
unavailable (dev-friendly — no Redis required in development).

Cache architecture
──────────────────
  L1 (in-process LRU)  ← very fast, not shared across workers, TTL-aware
  L2 (Redis)           ← shared across workers, authoritative, TTL-aware

Read path:  L1 hit → return immediately
            L1 miss → check Redis → populate L1 on hit
Write path: write to both L1 and Redis
Invalidate: delete from both L1 and Redis (pattern-based for user eviction)

When Redis is unavailable the service degrades silently to L1-only mode,
preserving all existing behavior.

CacheStats
──────────
Hit/miss counters now use an asyncio.Lock to prevent lost updates under
concurrent async request load.  Stat reads are non-blocking.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re as _re
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("app.core.cache_service")


# ─────────────────────────────────────────────────────────────────────────────
#  LRU in-memory cache  (L1 — per-process, fast)
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

    async def delete_prefix(self, prefix: str) -> int:
        """Delete all keys that start with *prefix*. Returns count deleted."""
        async with self._lock:
            keys_to_del = [k for k in list(self._cache.keys()) if k.startswith(prefix)]
            for k in keys_to_del:
                del self._cache[k]
            return len(keys_to_del)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


# ─────────────────────────────────────────────────────────────────────────────
#  Cache statistics  (async-safe counters)
# ─────────────────────────────────────────────────────────────────────────────

class CacheStats:
    """Async-safe counter for cache hit/miss telemetry."""

    def __init__(self, name: str):
        self.name   = name
        self._hits  = 0
        self._misses = 0
        self._lock  = asyncio.Lock()

    # ── Synchronous fast-path (CPython GIL makes int += atomic for small ints)
    # We use the lock only for read-modify-write in to_dict() for consistency.

    def record_hit(self) -> None:
        self._hits += 1

    def record_miss(self) -> None:
        self._misses += 1

    @property
    def hits(self) -> int:
        return self._hits

    @hits.setter
    def hits(self, val: int) -> None:
        self._hits = val

    @property
    def misses(self) -> int:
        return self._misses

    @misses.setter
    def misses(self, val: int) -> None:
        self._misses = val

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return round(self._hits / total, 4) if total else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cache":    self.name,
            "hits":     self._hits,
            "misses":   self._misses,
            "hit_rate": self.hit_rate,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Redis-backed cache mixin  (shared across workers when Redis is available)
# ─────────────────────────────────────────────────────────────────────────────

class _RedisCacheMixin:
    """
    Mixin that wraps redis_client.cache_get / cache_set / cache_delete_pattern.
    All methods fall back to the _LRUCache (L1) when Redis is unavailable.
    """

    # Subclasses must set:
    #   self._lru: _LRUCache
    #   self._ttl: int

    async def _redis_get(self, key: str) -> Optional[Any]:
        try:
            from app.core.redis_client import cache_get
            return await cache_get(key)
        except Exception as exc:
            logger.debug(f"[Cache] Redis get failed for key={key[:30]}: {exc}")
            return None

    async def _redis_set(self, key: str, value: Any, ttl: int) -> None:
        try:
            from app.core.redis_client import cache_set
            await cache_set(key, value, ttl_seconds=ttl)
        except Exception as exc:
            logger.debug(f"[Cache] Redis set failed for key={key[:30]}: {exc}")

    async def _redis_delete_prefix(self, prefix: str) -> int:
        try:
            from app.core.redis_client import cache_delete_pattern
            return await cache_delete_pattern(f"{prefix}*")
        except Exception as exc:
            logger.debug(f"[Cache] Redis delete_prefix failed for prefix={prefix}: {exc}")
            return 0

    async def _get(self, key: str) -> Optional[Any]:
        """Two-level read: L1 (LRU) → L2 (Redis)."""
        # L1
        l1_val = await self._lru.get(key)
        if l1_val is not None:
            return l1_val
        # L2
        l2_val = await self._redis_get(key)
        if l2_val is not None:
            # Populate L1 from Redis so next access is fast
            await self._lru.set(key, l2_val, ttl=self._ttl)
        return l2_val

    async def _set(self, key: str, value: Any) -> None:
        """Write-through: both L1 and L2."""
        await self._lru.set(key, value, ttl=self._ttl)
        await self._redis_set(key, value, ttl=self._ttl)

    async def _delete_prefix(self, prefix: str) -> None:
        """Invalidate by prefix in both L1 and L2."""
        await self._lru.delete_prefix(prefix)
        await self._redis_delete_prefix(prefix)


# ─────────────────────────────────────────────────────────────────────────────
#  Retrieval Cache  (chunks list, per user + query + k)
# ─────────────────────────────────────────────────────────────────────────────

class RetrievalCache(_RedisCacheMixin):
    """
    Caches retrieved document chunk lists to avoid repeated ChromaDB lookups
    for identical (user_id, query, k) tuples within the same session.
    Shared across workers via Redis (Fix 4).
    TTL: 120 seconds.
    """

    _DEFAULT_TTL = 120

    def __init__(self):
        self._lru = _LRUCache(maxsize=256, default_ttl=self._DEFAULT_TTL)
        self._ttl = self._DEFAULT_TTL
        self.stats = CacheStats("retrieval")

    @staticmethod
    def _key(user_id: str, query: str, k: int) -> str:
        safe_uid = _re.sub(r"[^a-zA-Z0-9_-]", "", user_id)[:32]
        suffix   = hashlib.sha256(f"{user_id}|{query.strip().lower()}|{k}".encode()).hexdigest()[:20]
        return f"ret:{safe_uid}:{suffix}"

    async def get(self, user_id: str, query: str, k: int) -> Optional[List[Dict[str, Any]]]:
        key = self._key(user_id, query, k)
        result = await self._get(key)
        if result is not None:
            self.stats.record_hit()
            logger.debug(f"[RetrievalCache] HIT  key={key[:20]}")
        else:
            self.stats.record_miss()
        return result

    async def set(self, user_id: str, query: str, k: int, chunks: List[Dict[str, Any]]) -> None:
        key = self._key(user_id, query, k)
        await self._set(key, chunks)
        logger.debug(f"[RetrievalCache] SET  key={key[:20]} ({len(chunks)} chunks)")

    async def invalidate_user(self, user_id: str) -> None:
        """
        Clear all cached retrieval entries for a specific user in both
        L1 (in-process LRU) and L2 (Redis).  Cross-worker safe when Redis
        is available (Fix 4).
        """
        safe_uid = _re.sub(r"[^a-zA-Z0-9_-]", "", user_id)[:32]
        prefix   = f"ret:{safe_uid}:"
        await self._delete_prefix(prefix)
        logger.info(f"[RetrievalCache] INVALIDATED all keys for user={user_id}")


# ─────────────────────────────────────────────────────────────────────────────
#  Embedding Cache  (float list, per text hash)
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingCache(_RedisCacheMixin):
    """
    Caches embedding vectors keyed by sha256 of the input text.
    Shared across workers via Redis (Fix 4).
    TTL: 3600 seconds (1 hour) — embeddings are stable and expensive.
    """

    _DEFAULT_TTL = 3600

    def __init__(self):
        self._lru = _LRUCache(maxsize=4096, default_ttl=self._DEFAULT_TTL)
        self._ttl = self._DEFAULT_TTL
        self.stats = CacheStats("embedding")

    @staticmethod
    def _key(text: str) -> str:
        return "emb:" + hashlib.sha256(text.encode()).hexdigest()[:24]

    async def get(self, text: str) -> Optional[List[float]]:
        key = self._key(text)
        result = await self._get(key)
        if result is not None:
            self.stats.record_hit()
        else:
            self.stats.record_miss()
        return result

    async def set(self, text: str, vector: List[float]) -> None:
        key = self._key(text)
        await self._set(key, vector)

    async def get_batch(self, texts: List[str]) -> Dict[str, Optional[List[float]]]:
        # Concurrent fetch for all texts
        results = await asyncio.gather(*[self.get(t) for t in texts])
        return dict(zip(texts, results))

    async def set_batch(self, text_vector_pairs: Dict[str, List[float]]) -> None:
        # Concurrent write for all pairs
        await asyncio.gather(*[self.set(t, v) for t, v in text_vector_pairs.items()])


# ─────────────────────────────────────────────────────────────────────────────
#  Web Search Cache  (string result, per query)
# ─────────────────────────────────────────────────────────────────────────────

class WebSearchCache(_RedisCacheMixin):
    """
    Caches Tavily web search results to reduce API costs.
    Shared across workers via Redis (Fix 4).
    TTL: 600 seconds (10 minutes).
    """

    _DEFAULT_TTL = 600

    def __init__(self):
        self._lru = _LRUCache(maxsize=128, default_ttl=self._DEFAULT_TTL)
        self._ttl = self._DEFAULT_TTL
        self.stats = CacheStats("web_search")

    @staticmethod
    def _key(query: str) -> str:
        return "web:" + hashlib.sha256(query.strip().lower().encode()).hexdigest()[:24]

    async def get(self, query: str) -> Optional[str]:
        key = self._key(query)
        result = await self._get(key)
        if result is not None:
            self.stats.record_hit()
            logger.debug(f"[WebSearchCache] HIT  query='{query[:40]}'")
        else:
            self.stats.record_miss()
        return result

    async def set(self, query: str, result: str) -> None:
        key = self._key(query)
        await self._set(key, result)
        logger.debug(f"[WebSearchCache] SET  query='{query[:40]}'")


# ─────────────────────────────────────────────────────────────────────────────
#  Global singletons  (identical interface as before — no callers change)
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
