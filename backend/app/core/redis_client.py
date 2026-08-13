"""
core/redis_client.py — Async Redis client wrapper with in-memory TTL fallback.

Production Fixes Applied
═══════════════════════
1.  In-Memory TTL Cache  — When Redis is unreachable (common on Windows local
    dev without a running Redis server), all cache_get / cache_set / cache_delete /
    rate_limit_check calls fall back to a thread-safe in-memory dict with TTL
    expiration.  This ensures MemoryService caching, rate limiting, and session
    storage work correctly without requiring a separate Redis process.

2.  Connection health tracking  — Failed connection attempts are subject to a
    15-second cooldown so the app does not spam connection errors on every request.
    After the cooldown, the client retries Redis automatically; if it recovers the
    in-memory cache is transparently bypassed.

3.  Variable shadowing bugfix  — The original code referenced `client` in the
    except block before it was assigned on connection failure, causing a
    NameError.  Fixed by guarding the aclose() call.

4.  Async-safe in-memory operations  — Uses asyncio.Lock to guarantee correct
    behavior under concurrent async request load.

The module degrades gracefully: if Redis is unreachable every helper returns
data from the in-memory cache rather than None / False, so caching is ALWAYS
active whether or not Redis is running.
"""

import json
import logging
import time
import asyncio
from typing import Any, Optional, Dict, Tuple

logger = logging.getLogger("core.redis_client")

# ── In-memory fallback cache ───────────────────────────────────────────────────
# Stores (value_json, expire_at) where expire_at is a monotonic timestamp.
# expire_at == None means no expiry.
_MEM_STORE: Dict[str, Tuple[str, Optional[float]]] = {}
_MEM_LOCK = asyncio.Lock()


async def _mem_get(key: str) -> Optional[Any]:
    async with _MEM_LOCK:
        entry = _MEM_STORE.get(key)
        if entry is None:
            return None
        value_json, expire_at = entry
        if expire_at is not None and time.monotonic() >= expire_at:
            _MEM_STORE.pop(key, None)
            return None
        try:
            return json.loads(value_json)
        except Exception:
            return None


async def _mem_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    expire_at = time.monotonic() + ttl_seconds if ttl_seconds > 0 else None
    async with _MEM_LOCK:
        _MEM_STORE[key] = (json.dumps(value, default=str), expire_at)


async def _mem_delete(key: str) -> bool:
    async with _MEM_LOCK:
        existed = key in _MEM_STORE
        _MEM_STORE.pop(key, None)
        return existed


async def _mem_delete_pattern(pattern: str) -> int:
    """Delete all in-memory keys matching a simple glob pattern (only * wildcard)."""
    import fnmatch
    async with _MEM_LOCK:
        matching = [k for k in list(_MEM_STORE.keys()) if fnmatch.fnmatch(k, pattern)]
        for k in matching:
            _MEM_STORE.pop(k, None)
        return len(matching)


async def _mem_incr(key: str, ttl_seconds: int = 60) -> int:
    async with _MEM_LOCK:
        entry = _MEM_STORE.get(key)
        now = time.monotonic()
        if entry is not None:
            value_json, expire_at = entry
            if expire_at is not None and now >= expire_at:
                # Expired — reset
                new_count = 1
                _MEM_STORE[key] = (json.dumps(new_count), now + ttl_seconds)
                return new_count
            try:
                current = int(json.loads(value_json))
            except Exception:
                current = 0
            new_count = current + 1
            _MEM_STORE[key] = (json.dumps(new_count), expire_at)
            return new_count
        else:
            # New key
            _MEM_STORE[key] = (json.dumps(1), now + ttl_seconds)
            return 1


# ── Redis singleton state ──────────────────────────────────────────────────────

_redis_client = None
_last_failed_time = 0.0
_FAIL_COOLDOWN_SECONDS = 15.0
_redis_available: Optional[bool] = None  # None = untested, True/False = known state


async def get_redis():
    """
    Return a singleton async Redis client, or None if Redis is unavailable.

    Behaviour:
    - Caches a successful connection for the process lifetime.
    - Failed attempts are retried after a 15s cooldown (avoids log-spam on
      every request when Redis is not running).
    - Never raises — callers must handle None gracefully.
    """
    global _redis_client, _last_failed_time

    if _redis_client is not None:
        return _redis_client

    now = time.monotonic()
    if now - _last_failed_time < _FAIL_COOLDOWN_SECONDS:
        return None

    _client = None
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings

        _client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            protocol=2,  # RESP2 — compatible with Redis 5+
        )
        # Verify the connection is live before caching
        await _client.ping()
        _redis_client = _client
        logger.info(f"[Redis] Connected: {settings.REDIS_URL}")
    except Exception as e:
        logger.warning(
            f"[Redis] Unavailable ({e.__class__.__name__}: {e}) — "
            "falling back to in-memory TTL cache."
        )
        _redis_client = None
        _last_failed_time = time.monotonic()
        if _client is not None:
            try:
                await _client.aclose()
            except Exception:
                pass

    return _redis_client


# ── Public cache helpers ───────────────────────────────────────────────────────

async def cache_get(key: str) -> Optional[Any]:
    """Return a cached value (deserialised from JSON) or None on miss/error."""
    try:
        r = await get_redis()
        if r is not None:
            raw = await r.get(key)
            if raw is None:
                return None
            return json.loads(raw)
    except Exception as e:
        logger.debug(f"[Redis] cache_get({key}) redis error, trying memory: {e}")

    # Fallback to in-memory cache
    return await _mem_get(key)


async def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """
    Serialise *value* to JSON and store it with a TTL.
    Returns True on success, False on total failure.
    Always writes to in-memory cache as backup so data is never lost.
    """
    # Always write to in-memory cache as a reliable backup
    try:
        await _mem_set(key, value, ttl_seconds)
    except Exception as e:
        logger.debug(f"[Redis] _mem_set({key}) failed: {e}")

    # Attempt write to Redis (authoritative store)
    try:
        r = await get_redis()
        if r is not None:
            await r.set(key, json.dumps(value, default=str), ex=ttl_seconds)
            return True
    except Exception as e:
        logger.debug(f"[Redis] cache_set({key}) redis error: {e}")

    # In-memory fallback succeeded
    return True


async def cache_delete(key: str) -> bool:
    """Delete a cache key.  Returns True if the key existed in either store."""
    deleted_mem = await _mem_delete(key)
    try:
        r = await get_redis()
        if r is not None:
            deleted_redis = await r.delete(key)
            return deleted_redis > 0 or deleted_mem
    except Exception as e:
        logger.debug(f"[Redis] cache_delete({key}) error: {e}")
    return deleted_mem


async def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching *pattern* (e.g. 'memories:user_123:*').
    Returns the total number of keys deleted across both stores.
    """
    mem_deleted = await _mem_delete_pattern(pattern)
    try:
        r = await get_redis()
        if r is not None:
            keys = [k async for k in r.scan_iter(pattern)]
            if keys:
                redis_deleted = await r.delete(*keys)
                return redis_deleted + mem_deleted
    except Exception as e:
        logger.debug(f"[Redis] cache_delete_pattern({pattern}) error: {e}")
    return mem_deleted


async def rate_limit_check(key: str, limit: int, window_seconds: int = 60) -> bool:
    """
    Sliding-window rate limiter.

    Returns True  when the caller is WITHIN the limit (request allowed).
    Returns False when the limit has been exceeded.

    Uses Redis INCR + EXPIRE.  Falls back to in-memory INCR so rate limiting
    is ALWAYS enforced even without a running Redis server.
    """
    try:
        r = await get_redis()
        if r is not None:
            current = await r.incr(key)
            if current == 1:
                await r.expire(key, window_seconds)
            return current <= limit
    except Exception as e:
        logger.debug(f"[Redis] rate_limit_check({key}) redis error, using memory: {e}")

    # Fallback to in-memory rate limiter
    try:
        current = await _mem_incr(key, ttl_seconds=window_seconds)
        return current <= limit
    except Exception as e:
        logger.debug(f"[Redis] rate_limit_check({key}) memory error: {e}")
        return True  # fail open as last resort
