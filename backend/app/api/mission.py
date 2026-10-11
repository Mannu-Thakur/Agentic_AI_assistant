"""
app/api/mission.py — Mission Mode API (v2 with background job queue)

Endpoints
---------
  POST /api/v1/mission/run
      Enqueues a mission and immediately returns a job_id.
      Response: {"job_id": "...", "stream_url": "/api/v1/mission/.../stream"}

  GET  /api/v1/mission/{job_id}/stream
      SSE stream of mission progress events (reconnectable).
      Client can reconnect using Last-Event-ID to continue from where it left off.

  GET  /api/v1/mission/{job_id}
      Current job status + final result (polling endpoint).

  POST /api/v1/mission/{job_id}/approve
      Approve a HITL gate (resumes the mission).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.agents.job_queue import job_queue, Job

logger = logging.getLogger("api.mission")
router = APIRouter(prefix="/mission", tags=["mission"])


class MissionRequest(BaseModel):
    query: str
    model: Optional[str] = "gemini-2.0-flash"
    session_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
#  POST /mission/run  — enqueue and return immediately
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_mission(
    req: MissionRequest,
    request: Request,
    current_user=Depends(get_current_user),
):
    """
    Enqueue a mission. Returns job_id + stream URL immediately.
    The mission runs in the background — connect to /stream for progress.
    """
    user_id    = str(current_user.id)
    session_id = req.session_id or f"mission_{user_id}"

    # Extract API keys from header
    api_keys: Dict[str, str] = {}
    raw_keys = request.headers.get("x-api-keys", "")
    if raw_keys:
        try:
            api_keys = json.loads(raw_keys)
        except Exception:
            pass

    job = job_queue.enqueue(
        query=req.query,
        user_id=user_id,
        session_id=session_id,
        model=req.model or "gemini-2.0-flash",
        api_keys=api_keys,
    )

    logger.info(f"[Mission] Enqueued job={job.id} user={user_id}")

    return JSONResponse({
        "job_id":     job.id,
        "status":     job.status,
        "stream_url": f"/api/v1/mission/{job.id}/stream",
        "query":      req.query,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  GET /mission/{job_id}/stream  — SSE progress stream (reconnectable)
# ─────────────────────────────────────────────────────────────────────────────

async def _sse_stream(job: Job, from_index: int) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted events for a job."""
    async for event in job_queue.tail_events(job.id, from_index=from_index, timeout=300.0):
        data = json.dumps({**event.data, "event_type": event.event_type})
        yield f"id: {len(job.events)}\n"
        yield f"event: {event.event_type}\n"
        yield f"data: {data}\n\n"

    # Send terminal event
    if job.status == "complete":
        terminal = json.dumps({
            "job_id":   job.id,
            "response": job.result or "",
            "status":   "complete",
        })
        yield f"event: mission_complete\ndata: {terminal}\n\n"
    elif job.status == "error":
        yield f"event: error\ndata: {json.dumps({'job_id': job.id, 'error': job.error})}\n\n"


@router.get("/{job_id}/stream")
async def stream_mission(
    job_id: str,
    request: Request,
    current_user=Depends(get_current_user),
):
    """SSE stream for mission progress. Supports Last-Event-ID for reconnection."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Support reconnection via Last-Event-ID
    last_id_header = request.headers.get("last-event-id", "0")
    try:
        from_index = int(last_id_header)
    except ValueError:
        from_index = 0

    return StreamingResponse(
        _sse_stream(job, from_index),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "X-Job-ID":          job_id,
            "Connection":        "keep-alive",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
#  GET /mission/{job_id}  — poll status
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{job_id}")
async def get_mission_status(
    job_id: str,
    current_user=Depends(get_current_user),
):
    """Poll mission status and final result."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "job_id":      job.id,
        "status":      job.status,
        "query":       job.query,
        "result":      job.result,
        "error":       job.error,
        "event_count": len(job.events),
        "created_at":  job.created_at,
        "finished_at": job.finished_at,
        "duration_s":  round(job.finished_at - job.created_at, 2) if job.finished_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  GET /mission/  — list user's missions
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_missions(current_user=Depends(get_current_user)):
    """List all missions for the current user."""
    jobs = job_queue.user_jobs(str(current_user.id))
    return {
        "missions": [
            {
                "job_id":     j.id,
                "query":      j.query[:100],
                "status":     j.status,
                "created_at": j.created_at,
                "finished_at": j.finished_at,
            }
            for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)
        ],
        "total": len(jobs),
    }
