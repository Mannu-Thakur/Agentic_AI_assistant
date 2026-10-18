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
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.agents.job_queue import job_queue, Job
from app.core.config import settings
from app.core.database import get_db
from app.services.provider_key_service import get_request_provider_keys

logger = logging.getLogger("api.mission")
router = APIRouter(prefix="/mission", tags=["mission"])


class MissionRequest(BaseModel):
    query: str = Field(min_length=1, max_length=12_000)
    model: Optional[str] = Field(default=None, max_length=200)
    session_id: Optional[str] = None

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        import re
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
            raise ValueError("session_id must contain only letters, digits, _ or -")
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        import re
        if not re.fullmatch(r"[A-Za-z0-9._:/-]+", value):
            raise ValueError("Invalid model identifier")
        return value


# ─────────────────────────────────────────────────────────────────────────────
#  POST /mission/run  — enqueue and return immediately
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_mission(
    req: MissionRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueue a mission. Returns job_id + stream URL immediately.
    The mission runs in the background — connect to /stream for progress.
    """
    if not settings.ENABLE_MISSION_MODE:
        raise HTTPException(status_code=404, detail="Mission mode is not enabled")
    user_id    = str(current_user.id)
    session_id = req.session_id or f"mission_{user_id.replace('-', '')[:24]}"

    # Validate temporary keys before the shared request-scoped key loader
    # overlays them onto the user's encrypted saved provider credentials.
    allowed_key_providers = {
        "gemini", "google", "groq", "openai", "openrouter",
        "tavily", "serpapi", "exa",
    }
    raw_keys = request.headers.get("x-api-keys", "")
    if raw_keys:
        try:
            parsed_keys = json.loads(raw_keys)
            if not isinstance(parsed_keys, dict):
                raise ValueError("API keys must be an object")
            if any(
                str(provider).lower() not in allowed_key_providers
                or not (0 < len(str(key)) <= 4096)
                for provider, key in parsed_keys.items()
            ):
                raise ValueError("Unsupported or invalid API key")
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid x-api-keys header")

    api_keys = await get_request_provider_keys(db, current_user.id, request)
    api_keys = {
        provider: key for provider, key in api_keys.items()
        if provider in allowed_key_providers and 0 < len(key) <= 4096
    }

    try:
        job = await job_queue.enqueue(
            query=req.query,
            user_id=user_id,
            session_id=session_id,
            model=req.model or settings.GEMINI_MODEL,
            api_keys=api_keys,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

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
    event_id = from_index
    emitted_terminal = False
    async for event in job_queue.tail_events(job.id, from_index=from_index, timeout=300.0):
        event_id += 1
        data = json.dumps({**event.data, "event_type": event.event_type})
        yield f"id: {event_id}\n"
        yield f"event: {event.event_type}\n"
        yield f"data: {data}\n\n"
        emitted_terminal = emitted_terminal or event.event_type in {"mission_complete", "error"}

    # Legacy or interrupted records can lack a terminal event.  Normal graph
    # completion already streamed one and must not be duplicated.
    if not emitted_terminal and job.status == "complete":
        terminal = json.dumps({
            "job_id":   job.id,
            "response": job.result or "",
            "status":   "complete",
        })
        yield f"event: mission_complete\ndata: {terminal}\n\n"
    elif not emitted_terminal and job.status == "error":
        yield f"event: error\ndata: {json.dumps({'job_id': job.id, 'error': job.error})}\n\n"


@router.get("/{job_id}/stream")
async def stream_mission(
    job_id: str,
    request: Request,
    current_user=Depends(get_current_user),
):
    """SSE stream for mission progress. Supports Last-Event-ID for reconnection."""
    job = await job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Support reconnection via Last-Event-ID
    last_id_header = request.headers.get("last-event-id", "0")
    try:
        from_index = max(0, int(last_id_header))
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
    job = await job_queue.get_job(job_id)
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
    jobs = await job_queue.user_jobs(str(current_user.id))
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
