"""
app/proactive/store.py — Alert persistence and deduplication layer.

Responsibilities
────────────────
1. save_alert()        — persist a ProactiveAlert to DB (idempotent via dedup).
2. is_duplicate()      — return True if an identical alert was fired recently.
3. get_user_alerts()   — paginated list for the REST /alerts endpoint.
4. mark_read()         — mark one or all alerts as read.
5. get_unread_count()  — badge count for the notification bell.

All public functions accept an AsyncSession injected from the caller.
The store is stateless — no singleton, no caching — so it remains safe
under concurrent async workers.
"""
from __future__ import annotations

import time
import logging
from typing import List, Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.proactive.models import ProactiveAlert, DEDUP_WINDOW_HOURS
from app.proactive.db_models import ProactiveAlertRecord

logger = logging.getLogger("app.proactive.store")


async def is_duplicate(db: AsyncSession, alert: ProactiveAlert) -> bool:
    """
    Returns True if an alert with the same alert_id was stored within
    DEDUP_WINDOW_HOURS hours for this user — prevents alert fatigue.
    """
    cutoff = time.time() - (DEDUP_WINDOW_HOURS * 3600)
    result = await db.execute(
        select(ProactiveAlertRecord.id)
        .where(
            ProactiveAlertRecord.user_id   == alert.user_id,
            ProactiveAlertRecord.alert_id  == alert.alert_id,
            ProactiveAlertRecord.created_at >= cutoff,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def save_alert(db: AsyncSession, alert: ProactiveAlert) -> Optional[ProactiveAlertRecord]:
    """
    Persist an alert if it is not a duplicate.
    Returns the saved record, or None if skipped as a duplicate.
    """
    if await is_duplicate(db, alert):
        logger.debug(f"[ProactiveStore] Duplicate suppressed: {alert.alert_id[:8]} for user={alert.user_id[:8]}")
        return None

    record = ProactiveAlertRecord(
        alert_id      = alert.alert_id,
        user_id       = alert.user_id,
        alert_type    = alert.alert_type.value,
        severity      = alert.severity.value,
        title         = alert.title,
        message       = alert.message,
        confidence    = alert.confidence,
        entity_key    = alert.entity_key,
        source_doc_ids= alert.source_doc_ids,
        extra_meta    = alert.metadata,
        is_read       = False,
        created_at    = alert.created_at,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info(f"[ProactiveStore] Saved alert {alert.alert_type.value} ({alert.severity.value}) for user={alert.user_id[:8]}")
    return record


async def get_user_alerts(
    db: AsyncSession,
    user_id: str,
    limit: int = 50,
    unread_only: bool = False,
) -> List[ProactiveAlertRecord]:
    """Fetch the most recent alerts for a user, newest first."""
    q = (
        select(ProactiveAlertRecord)
        .where(ProactiveAlertRecord.user_id == user_id)
        .order_by(ProactiveAlertRecord.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        q = q.where(ProactiveAlertRecord.is_read == False)  # noqa: E712
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_unread_count(db: AsyncSession, user_id: str) -> int:
    """Return the number of unread alerts — used for the notification bell badge."""
    result = await db.execute(
        select(func.count(ProactiveAlertRecord.id))
        .where(
            ProactiveAlertRecord.user_id == user_id,
            ProactiveAlertRecord.is_read == False,  # noqa: E712
        )
    )
    return result.scalar_one() or 0


async def mark_read(
    db: AsyncSession,
    user_id: str,
    alert_record_id: Optional[str] = None,
) -> int:
    """
    Mark alerts as read.
    If alert_record_id is given, marks only that alert.
    If None, marks ALL unread alerts for the user.
    Returns the number of rows updated.
    """
    q = (
        update(ProactiveAlertRecord)
        .where(
            ProactiveAlertRecord.user_id == user_id,
            ProactiveAlertRecord.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    if alert_record_id:
        q = q.where(ProactiveAlertRecord.id == alert_record_id)

    result = await db.execute(q)
    await db.commit()
    return result.rowcount
