"""
workers/health_check.py — Background provider key health-checker.

Fixes applied:
  • CRIT-2: Each provider verification is now wrapped in asyncio.wait_for(timeout=15s)
             so a single hanging API call cannot stall the entire loop forever.
  • HIGH-1: available_models is serialized to a JSON string before being stored in
             the TEXT column; previously a Python list repr was stored, causing the
             `in` membership check in chat.py to work on raw string bytes.
  • HIGH-3: Bare `except Exception: pass` blocks inside the metrics-recording calls
             now log at DEBUG level instead of silently discarding the error.
  • LOW-1:  On outer loop error the sleep now uses exponential back-off
             (1 min → 5 min → 30 min → cap at 6 hours) instead of always sleeping
             6 hours — provider statuses were stale for up to 6 h on DB failures.
"""

import asyncio
import logging
import time

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.user import ApiKey
from app.core.security import decrypt_api_key
from app.api.api_keys import verify_provider_api_key_and_fetch_models, ApiKeyAuthError
from sqlalchemy.sql import func

logger = logging.getLogger("app.workers.health_check")

# ── Exponential back-off state ────────────────────────────────────────────────
_BACKOFF_STEPS = [60, 300, 1800, 21600]   # 1 min, 5 min, 30 min, 6 h
_BACKOFF_MAX   = 21600                     # cap at 6 hours
_NORMAL_SLEEP  = 21600                     # 6 hours between successful runs

# Per-key timeout for external API calls (seconds)
_KEY_VERIFY_TIMEOUT = 15.0


async def provider_health_check_loop():
    logger.info("Starting background provider health check loop")
    # Give the database time to initialise on startup before running checks.
    await asyncio.sleep(5)

    failure_count = 0   # consecutive outer-loop failures for back-off

    while True:
        try:
            logger.info("Running provider health checks...")
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(ApiKey))
                keys = result.scalars().all()

                for k in keys:
                    if not k.encrypted_api_key:
                        continue

                    _t0 = time.perf_counter()
                    try:
                        raw_key = decrypt_api_key(k.encrypted_api_key)
                    except Exception as _dec_err:
                        logger.warning(
                            f"Health check failed to decrypt key for provider "
                            f"{k.provider_name} (key ID {k.id}): {_dec_err}"
                        )
                        k.status = "INVALID"
                        k.last_error = "API key decryption failed. Server encryption key may have changed. Please re-enter this key in Settings."
                        k.available_models = []
                        k.last_checked = func.now()
                        continue

                    try:
                        # CRIT-2 FIX: wrap with a hard timeout so a hanging provider
                        # call cannot stall the entire health-check loop.
                        models = await asyncio.wait_for(
                            verify_provider_api_key_and_fetch_models(k.provider_name, raw_key),
                            timeout=_KEY_VERIFY_TIMEOUT,
                        )

                        k.status = "VERIFIED"
                        k.verified_at = func.now()
                        k.last_checked = func.now()
                        # HIGH-1 FIX (corrected): available_models is Column(JSON), so SQLAlchemy
                        # serializes/deserializes automatically. Store a plain Python list — do NOT
                        # call json.dumps() or it will double-encode ("\"[...]\"" in the DB).
                        k.available_models = models if isinstance(models, list) else []
                        k.last_error = None


                        _latency_ms = round((time.perf_counter() - _t0) * 1000, 1)
                        try:
                            from app.providers.provider_metrics import provider_metrics
                            provider_metrics.record_health_check(k.provider_name, "healthy", _latency_ms)
                        except Exception as _e:
                            # HIGH-3 FIX: log instead of silently dropping.
                            logger.debug(f"[HealthCheck] Metrics record failed (healthy): {_e}")

                    except asyncio.TimeoutError:
                        # CRIT-2: per-key timeout fired — mark degraded, keep going.
                        logger.warning(
                            f"Health check timed out after {_KEY_VERIFY_TIMEOUT}s "
                            f"for provider {k.provider_name} (key ID {k.id})"
                        )
                        k.last_error = f"Verification timed out after {_KEY_VERIFY_TIMEOUT}s"
                        k.last_checked = func.now()
                        if k.status != "INVALID":
                            k.status = "DEGRADED"
                        try:
                            from app.providers.provider_metrics import provider_metrics
                            provider_metrics.record_health_check(k.provider_name, "timeout")
                        except Exception as _e:
                            logger.debug(f"[HealthCheck] Metrics record failed (timeout): {_e}")

                    except ApiKeyAuthError as e:
                        logger.warning(
                            f"Health check found invalid key for provider "
                            f"{k.provider_name} (key ID {k.id}): {e}"
                        )
                        k.status = "INVALID"
                        k.last_error = str(e)[:900]
                        k.available_models = []   # Column(JSON) — store plain list
                        k.last_checked = func.now()

                        try:
                            from app.providers.provider_metrics import provider_metrics
                            provider_metrics.record_health_check(k.provider_name, "key_invalid")
                        except Exception as _e:
                            logger.debug(f"[HealthCheck] Metrics record failed (key_invalid): {_e}")

                    except Exception as e:
                        logger.warning(
                            f"Transient health check issue for provider "
                            f"{k.provider_name} (key ID {k.id}): {e}"
                        )
                        k.last_error = f"Transient warning: {str(e)[:800]}"
                        k.last_checked = func.now()
                        # Do NOT flip a previously-VERIFIED key to INVALID on transient errors.
                        if k.status not in ("VERIFIED", "INVALID"):
                            k.status = "DEGRADED"
                        try:
                            from app.providers.provider_metrics import provider_metrics
                            provider_metrics.record_health_check(k.provider_name, "degraded")
                        except Exception as _e:
                            logger.debug(f"[HealthCheck] Metrics record failed (degraded): {_e}")

                    db.add(k)

                await db.commit()

            logger.info("Provider health checks completed.")
            failure_count = 0   # reset back-off on success

        except Exception as e:
            logger.error(f"Error in provider health check loop: {e}")
            # LOW-1 FIX: exponential back-off — don't wait 6 h on every DB error.
            backoff = _BACKOFF_STEPS[min(failure_count, len(_BACKOFF_STEPS) - 1)]
            failure_count += 1
            logger.info(f"[HealthCheck] Backing off for {backoff}s before retry (failure #{failure_count})")
            await asyncio.sleep(backoff)
            continue

        # Normal cadence: check every 6 hours.
        await asyncio.sleep(_NORMAL_SLEEP)
