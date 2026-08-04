"""
Quick import smoke test — run from backend/ directory.
"""
import sys
import traceback

TESTS = [
    ("redis_client module",
     "from app.core.redis_client import cache_get, cache_set, cache_delete, rate_limit_check"),
    ("circuit_breaker module",
     "from app.providers.circuit_breaker import CircuitBreaker, gemini_breaker, groq_breaker, openrouter_breaker"),
    ("registry module",
     "from app.providers.registry import provider_registry"),
    ("circuit_breaker 30s cooldown",
     "from app.providers.circuit_breaker import gemini_breaker; assert gemini_breaker.cooldown_seconds == 30, f'Expected 30s got {gemini_breaker.cooldown_seconds}'"),
]

ok = True
for name, code in TESTS:
    try:
        exec(code)
        print(f"OK  {name}")
    except Exception as e:
        print(f"ERR {name}: {e}")
        ok = False

# Async tests for redis in-memory fallback
import asyncio
from app.core.redis_client import cache_set, cache_get, rate_limit_check, _mem_get, _mem_set

async def _async_tests():
    global ok
    # Direct in-memory read/write
    await _mem_set("test_key", {"hello": "world"}, ttl_seconds=60)
    val = await _mem_get("test_key")
    assert val == {"hello": "world"}, f"Got {val}"
    print("OK  in-memory write/read")

    # cache_set fallback
    res = await cache_set("cache_key_test", [1, 2, 3], ttl_seconds=60)
    assert res, "cache_set returned False"
    print("OK  cache_set (Redis offline) -> in-memory fallback")

    # cache_get from in-memory
    got = await cache_get("cache_key_test")
    assert got == [1, 2, 3], f"Got {got}"
    print("OK  cache_get (Redis offline) -> in-memory fallback")

    # rate_limit: allow 3 of 5
    for i in range(3):
        allowed = await rate_limit_check("rl_test", limit=5, window_seconds=60)
        assert allowed, f"Should be allowed at {i+1}"
    print("OK  rate_limit_check in-memory (3/5 allowed)")

asyncio.run(_async_tests())

print()
print("ALL TESTS PASSED" if ok else "SOME TESTS FAILED")
sys.exit(0 if ok else 1)
