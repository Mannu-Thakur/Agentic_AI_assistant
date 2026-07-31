"""
core/redis_client.py — Async Redis client wrapper.

Provides:
  • A lazy-initialized connection pool (one per process).
  • get / set / delete helpers with automatic JSON serialisation.
  • TTL-aware caching helpers used by MemoryService and future rate-limiting.

The module degrades gracefully: if Redis is unreachable every helper returns
None / False instead of raising, so the app continues to work without caching.
"""

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("core.redis_client")

_redis_client = None
_last_failed_time = 0.0
_FAIL_COOLDOWN_SECONDS = 15.0


async def get_redis():
    """
    Return a singleton async Redis client.
    Import is deferred so the module can be loaded even when redis is not
    installed (though it IS in requirements.txt).
    Only caches the client on a successful connection — failed attempts
    are retried after a 15s cooldown rather than blocking every request.
    """
    global _redis_client, _last_failed_time
    if _redis_client is not None:
        return _redis_client

    now = time.monotonic()
    if now - _last_failed_time < _FAIL_COOLDOWN_SECONDS:
        return None

    try:
        import redis.asyncio as aioredis
        from app.core.config import settings

        client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            protocol=2,  # Force RESP2 compatibility with Redis 5
        )
        # Verify connection before caching
        await client.ping()
        _redis_client = client
        logger.info(f"Redis connected: {settings.REDIS_URL}")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}) — caching disabled.")
        _redis_client = None
        _last_failed_time = time.monotonic()
        try:
            await client.aclose()
        except Exception:
            pass

    return _redis_client


async def cache_get(key: str) -> Optional[Any]:
    """Return a cached value (deserialised from JSON) or None on miss/error."""
    try:
        r = await get_redis()
        if r is None:
            return None
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.debug(f"cache_get({key}) error: {e}")
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """
    Serialise *value* to JSON and store it with a TTL.
    Returns True on success, False on error.
    """
    try:
        r = await get_redis()
        if r is None:
            return False
        await r.setex(key, ttl_seconds, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.debug(f"cache_set({key}) error: {e}")
        return False


async def cache_delete(key: str) -> bool:
    """Delete a cache key.  Returns True if the key existed, False otherwise."""
    try:
        r = await get_redis()
        if r is None:
            return False
        deleted = await r.delete(key)
        return deleted > 0
    except Exception as e:
        logger.debug(f"cache_delete({key}) error: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching *pattern* (e.g. 'memories:user_123:*').
    Returns the number of keys deleted.
    """
    try:
        r = await get_redis()
        if r is None:
            return 0
        keys = [k async for k in r.scan_iter(pattern)]
        if not keys:
            return 0
        return await r.delete(*keys)
    except Exception as e:
        logger.debug(f"cache_delete_pattern({pattern}) error: {e}")
        return 0


async def rate_limit_check(key: str, limit: int, window_seconds: int = 60) -> bool:
    """
    Sliding-window rate limiter.

    Returns True  when the caller is WITHIN the limit (request allowed).
    Returns False when the limit has been exceeded.

    Uses Redis INCR + EXPIRE so the window resets automatically.
    Fails open (returns True) if Redis is unavailable.
    """
    try:
        r = await get_redis()
        if r is None:
            return True  # fail open
        current = await r.incr(key)
        if current == 1:
            await r.expire(key, window_seconds)
        return current <= limit
    except Exception as e:
        logger.debug(f"rate_limit_check({key}) error: {e}")
        return True  # fail open
