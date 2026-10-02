"""
app/workers/proactive_scheduler.py — Background scheduler for the Proactive Engine.

Runs as a long-lived asyncio task started in main.py lifespan.

Schedule
────────
Every 30 minutes:
  - For every user with an active SSE connection, run system scanners
    (drift, hallucination spike, cost spike).

Every day at 07:00 (IST-aware, or UTC+0 fallback):
  - For every user with an active SSE connection, run morning briefing.

Design
──────
- Only scans users who have an active SSE connection (no wasted compute on
  offline users — they'll catch up when they next open the app).
- Completely fail-safe: any exception is absorbed and logged.
- Respects the existing asyncio event loop — no threads, no subprocesses.
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger("app.workers.proactive_scheduler")

# Scan interval in seconds (30 minutes)
SYSTEM_SCAN_INTERVAL_S = 30 * 60

# Morning briefing hour (local server hour, 0–23)
MORNING_BRIEFING_HOUR = 7

# Track last briefing timestamp to avoid double-firing
_last_briefing_date: str = ""


async def proactive_scheduler_loop() -> None:
    """
    Main scheduler loop. Runs forever until the task is cancelled on shutdown.
    """
    logger.info("[ProactiveScheduler] Background scheduler started.")
    last_system_scan = 0.0

    while True:
        try:
            now = time.time()

            # ── System scan (every 30 min) ────────────────────────────────────
            if now - last_system_scan >= SYSTEM_SCAN_INTERVAL_S:
                last_system_scan = now
                await _run_system_scan_for_connected_users()

            # ── Morning briefing (once per day at 07:xx) ──────────────────────
            await _maybe_run_morning_briefings()

        except asyncio.CancelledError:
            logger.info("[ProactiveScheduler] Scheduler cancelled — shutting down.")
            break
        except Exception as exc:
            logger.warning(f"[ProactiveScheduler] Unhandled error (non-fatal): {exc}")

        # Sleep 60 seconds between loop iterations (granularity for briefing check)
        await asyncio.sleep(60)


async def _run_system_scan_for_connected_users() -> None:
    """Run system scanners for every user currently connected via SSE."""
    from app.proactive.broadcaster import connected_user_ids
    from app.proactive.engine import ProactiveIntelligenceEngine

    user_ids = connected_user_ids()
    if not user_ids:
        logger.debug("[ProactiveScheduler] No connected users — system scan skipped.")
        return

    logger.info(f"[ProactiveScheduler] System scan for {len(user_ids)} connected user(s).")

    for uid in user_ids:
        try:
            await ProactiveIntelligenceEngine.run_system_scanners(uid)
        except Exception as exc:
            logger.warning(f"[ProactiveScheduler] System scan failed for user={uid[:8]}: {exc}")


async def _maybe_run_morning_briefings() -> None:
    """Fire morning briefings at 07:xx local server time, once per day."""
    global _last_briefing_date

    import datetime
    now_local = datetime.datetime.now()
    today_str = now_local.strftime("%Y-%m-%d")

    if now_local.hour != MORNING_BRIEFING_HOUR:
        return

    if _last_briefing_date == today_str:
        return   # Already fired today

    _last_briefing_date = today_str
    logger.info(f"[ProactiveScheduler] Morning briefing firing for {today_str}")

    from app.proactive.broadcaster import connected_user_ids
    from app.proactive.engine import ProactiveIntelligenceEngine

    for uid in connected_user_ids():
        try:
            await ProactiveIntelligenceEngine.run_morning_briefing(uid)
        except Exception as exc:
            logger.warning(f"[ProactiveScheduler] Briefing failed for user={uid[:8]}: {exc}")
