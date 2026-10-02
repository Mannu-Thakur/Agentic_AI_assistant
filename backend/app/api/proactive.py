"""
app/api/proactive.py — REST + SSE API for the Proactive Intelligence Engine.

Endpoints
─────────
GET  /api/v1/proactive/stream
    SSE stream: pushes real-time alert events to the frontend.
    Authenticated via ?token= query param (SSE cannot send headers).
    Sends a keepalive "ping" every 25s to prevent proxy timeouts.

GET  /api/v1/proactive/alerts
    Paginated list of stored alerts for the current user.
    Query params: limit (default 50), unread_only (bool).

GET  /api/v1/proactive/alerts/unread-count
    Returns { "count": N } — used by the notification bell badge.

POST /api/v1/proactive/alerts/mark-read
    Body: { "alert_id": "..." } or {} to mark all as read.

POST /api/v1/proactive/scan
    Manually trigger a full scan for the current user.
    Returns the list of newly generated (non-duplicate) alerts.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.auth import get_current_user
from app.schemas.auth import UserOut
from app.proactive import broadcaster
from app.proactive.store import (
    get_user_alerts,
    get_unread_count,
    mark_read,
)
from app.proactive.engine import ProactiveIntelligenceEngine

logger = logging.getLogger("api.proactive")

router = APIRouter(prefix="/proactive", tags=["Proactive Intelligence"])


# ── SSE Stream ────────────────────────────────────────────────────────────────

@router.get("/stream")
async def proactive_sse_stream(
    token: str = Query(..., description="JWT access token (SSE cannot send Authorization header)"),
):
    """
    Server-Sent Events stream for real-time proactive alerts.

    The frontend connects with:
        new EventSource(`/api/v1/proactive/stream?token=${accessToken}`)

    Each event is a JSON-encoded ProactiveAlert dict.
    A 'ping' event is sent every 25s to keep the connection alive.
    """
    # Validate the token manually (SSE can't send Authorization headers)
    from app.core.security import verify_token

    try:
        user_id = verify_token(token, token_type="access")
        if not user_id:
            raise ValueError("Empty user_id from token")
    except Exception as exc:
        logger.warning(f"[ProactiveSSE] Auth failed: {exc}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    async def event_generator():
        queue = await broadcaster.register(user_id)
        try:
            # Send a connected acknowledgement immediately
            yield _sse_event("connected", json.dumps({"status": "connected", "user_id": user_id}))

            while True:
                try:
                    # Wait for an alert or timeout for keepalive ping
                    payload_str = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield _sse_event("alert", payload_str)
                except asyncio.TimeoutError:
                    yield _sse_event("ping", "{}")
                except asyncio.CancelledError:
                    break
        finally:
            await broadcaster.deregister(user_id, queue)
            logger.debug(f"[ProactiveSSE] Stream closed for user={user_id[:8]}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


def _sse_event(event_name: str, data: str) -> str:
    return f"event: {event_name}\ndata: {data}\n\n"


# ── REST: List alerts ─────────────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent stored alerts for the current user."""
    records = await get_user_alerts(
        db,
        user_id=current_user.id,
        limit=limit,
        unread_only=unread_only,
    )
    return [_record_to_dict(r) for r in records]


# ── REST: Unread badge count ──────────────────────────────────────────────────

@router.get("/alerts/unread-count")
async def unread_alert_count(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return { count: N } for the notification bell badge."""
    count = await get_unread_count(db, current_user.id)
    return {"count": count}


# ── REST: Mark read ───────────────────────────────────────────────────────────

class MarkReadRequest(BaseModel):
    alert_record_id: Optional[str] = None   # None = mark ALL as read


@router.post("/alerts/mark-read")
async def mark_alerts_read(
    body: MarkReadRequest = MarkReadRequest(),
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark one alert (by DB record id) or all alerts as read."""
    updated = await mark_read(db, current_user.id, body.alert_record_id)
    return {"updated": updated}


# ── REST: Manual full scan ────────────────────────────────────────────────────

@router.post("/scan")
async def trigger_manual_scan(
    current_user: UserOut = Depends(get_current_user),
):
    """
    Manually trigger a full proactive scan for the current user.
    Returns the list of new alerts generated (duplicates suppressed).
    """
    logger.info(f"[Proactive] Manual scan triggered by user={current_user.id[:8]}")
    saved = await ProactiveIntelligenceEngine.run_full_scan(current_user.id)
    return {
        "scanned": True,
        "new_alerts": len(saved),
        "alerts": [a.to_dict() for a in saved],
    }


# ── Helper ────────────────────────────────────────────────────────────────────

def _record_to_dict(record) -> dict:
    return {
        "id":             record.id,
        "alert_id":       record.alert_id,
        "alert_type":     record.alert_type,
        "severity":       record.severity,
        "title":          record.title,
        "message":        record.message,
        "confidence":     record.confidence,
        "entity_key":     record.entity_key,
        "source_doc_ids": record.source_doc_ids or [],
        "metadata":       record.extra_meta or {},
        "is_read":        record.is_read,
        "created_at":     record.created_at,
    }
