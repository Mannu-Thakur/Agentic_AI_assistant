"""
app/proactive/engine.py — Proactive Intelligence Engine orchestrator.

The engine is the single entry-point for all proactive scanning:

  run_on_document_upload(user_id, doc_id)
      Called immediately after a document finishes indexing.
      Runs the document-aware scanners (cross-doc entity, temporal anomaly).

  run_system_scanners(user_id)
      Runs the system-health scanners (drift, hallucination spike, cost spike).
      Called by the background scheduler every 30 minutes for connected users.

  run_morning_briefing(user_id)
      Runs the daily briefing scanner — called once at 7am per user.

For each scanner output:
  1. Persist to DB via store.save_alert() (dedup-safe).
  2. If alert.should_push → broadcast via broadcaster.broadcast_to_user().

All scanner failures are silently absorbed — the engine never crashes the caller.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from app.proactive.models import ProactiveAlert
from app.proactive import broadcaster

logger = logging.getLogger("app.proactive.engine")


class ProactiveIntelligenceEngine:
    """
    Stateless orchestrator. Instantiate once (or call class methods directly).
    Uses AsyncSessionLocal internally — does NOT accept an injected session,
    because it runs from background tasks that have no request lifecycle.
    """

    # ── Document-triggered scan ───────────────────────────────────────────────

    @staticmethod
    async def run_on_document_upload(
        user_id: str,
        doc_id: str,
    ) -> None:
        """
        Entry point: called from documents.py after a document finishes ingestion.
        Runs fast, document-aware scanners in parallel.
        """
        from app.proactive.scanners import (
            scan_cross_document_entities,
            scan_temporal_anomalies,
        )

        logger.info(f"[Engine] Document scan triggered: user={user_id[:8]} doc={doc_id[:8]}")

        alerts = await _run_scanners_parallel([
            scan_cross_document_entities(user_id, trigger_doc_id=doc_id),
            scan_temporal_anomalies(user_id, trigger_doc_id=doc_id),
        ])

        await _persist_and_broadcast(user_id, alerts)

    # ── Periodic system scan (every 30 min) ───────────────────────────────────

    @staticmethod
    async def run_system_scanners(user_id: str) -> None:
        """
        Runs background health scanners for a connected user.
        Called by the scheduler for every user with an active SSE connection.
        """
        from app.proactive.scanners import (
            scan_drift_alert,
            scan_hallucination_spike,
            scan_cost_spike,
        )

        logger.debug(f"[Engine] System scan for user={user_id[:8]}")

        alerts = await _run_scanners_parallel([
            scan_drift_alert(user_id),
            scan_hallucination_spike(user_id),
            scan_cost_spike(user_id),
        ])

        await _persist_and_broadcast(user_id, alerts)

    # ── Morning briefing (once per day) ──────────────────────────────────────

    @staticmethod
    async def run_morning_briefing(user_id: str) -> None:
        """Daily 7am briefing for a user."""
        from app.proactive.scanners import build_morning_briefing

        logger.info(f"[Engine] Morning briefing for user={user_id[:8]}")
        alerts = await build_morning_briefing(user_id)
        await _persist_and_broadcast(user_id, alerts)

    # ── Full scan (manual trigger via API) ────────────────────────────────────

    @staticmethod
    async def run_full_scan(user_id: str) -> List[ProactiveAlert]:
        """
        Runs ALL scanners. Used by the manual-trigger REST endpoint.
        Returns the list of new (non-duplicate) alerts that were saved.
        """
        from app.proactive.scanners import (
            scan_cross_document_entities,
            scan_temporal_anomalies,
            scan_drift_alert,
            scan_hallucination_spike,
            scan_cost_spike,
            build_morning_briefing,
        )

        alerts = await _run_scanners_parallel([
            scan_cross_document_entities(user_id),
            scan_temporal_anomalies(user_id),
            scan_drift_alert(user_id),
            scan_hallucination_spike(user_id),
            scan_cost_spike(user_id),
            build_morning_briefing(user_id),
        ])

        saved = await _persist_and_broadcast(user_id, alerts)
        return saved


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _run_scanners_parallel(coroutines) -> List[ProactiveAlert]:
    """Gather all scanner coroutines in parallel; flatten results."""
    results = await asyncio.gather(*coroutines, return_exceptions=True)
    alerts: List[ProactiveAlert] = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning(f"[Engine] Scanner raised: {r}")
        elif isinstance(r, list):
            alerts.extend(r)
    return alerts


async def _persist_and_broadcast(
    user_id: str,
    alerts: List[ProactiveAlert],
) -> List[ProactiveAlert]:
    """
    For each alert:
      1. Save to DB (dedup-safe).
      2. If should_push → broadcast via SSE.
    Returns list of alerts that were actually saved (non-duplicates).
    """
    from app.core.database import AsyncSessionLocal
    from app.proactive.store import save_alert

    saved: List[ProactiveAlert] = []

    async with AsyncSessionLocal() as db:
        for alert in alerts:
            try:
                record = await save_alert(db, alert)
                if record is None:
                    continue   # duplicate — skipped

                saved.append(alert)
                logger.info(
                    f"[Engine] Alert saved: {alert.alert_type.value} "
                    f"conf={alert.confidence:.2f} push={alert.should_push}"
                )

                if alert.should_push:
                    sent = await broadcaster.broadcast_to_user(user_id, alert.to_dict())
                    logger.debug(f"[Engine] Broadcast to {sent} SSE connections")

            except Exception as exc:
                logger.warning(f"[Engine] Failed to persist/broadcast alert: {exc}")

    return saved
