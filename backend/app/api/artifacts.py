"""
app/api/artifacts.py — Artifact Management API

Endpoints
---------
  GET  /api/v1/artifacts                     List artifacts for current user
  GET  /api/v1/artifacts/session/{session_id} List artifacts for a chat session
  GET  /api/v1/artifacts/{artifact_id}       Get artifact metadata
  GET  /api/v1/artifacts/{artifact_id}/download  Download artifact file
  DELETE /api/v1/artifacts/{artifact_id}     Delete artifact

  POST /api/v1/hitl/approve/{mission_id}    Approve pending HITL action
  POST /api/v1/hitl/reject/{mission_id}     Reject pending HITL action
  GET  /api/v1/hitl/pending                 List pending HITL requests
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.auth import get_current_user
from app.agents.artifacts import artifact_store, Artifact

logger = logging.getLogger("api.artifacts")
router = APIRouter(prefix="/artifacts", tags=["artifacts"])
hitl_router = APIRouter(prefix="/hitl", tags=["hitl"])

# ── In-memory HITL request store ─────────────────────────────────────────────
# In production this would be backed by Redis or DB.
_hitl_pending: Dict[str, Dict[str, Any]] = {}
_hitl_events:  Dict[str, asyncio.Event]  = {}


# ─────────────────────────────────────────────────────────────────────────────
#  Artifact endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("")
async def list_artifacts(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all artifacts for the current user."""
    user_id = str(current_user.id)
    arts = artifact_store.list_by_user(user_id)
    return {
        "artifacts": [a.to_dict() for a in arts],
        "total": len(arts),
        "stats": artifact_store.stats(),
    }


@router.get("/session/{session_id}")
async def list_session_artifacts(
    session_id: str,
    current_user=Depends(get_current_user),
):
    """List all artifacts produced during a specific chat session."""
    arts = artifact_store.list_by_session(session_id)
    # Security: only return artifacts owned by this user
    user_id = str(current_user.id)
    arts = [a for a in arts if a.user_id == user_id]
    return {
        "session_id": session_id,
        "artifacts": [a.to_dict() for a in arts],
        "total": len(arts),
    }


@router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    current_user=Depends(get_current_user),
):
    """Get artifact metadata by ID."""
    art = artifact_store.get(artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if art.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    return art.to_dict()


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    current_user=Depends(get_current_user),
):
    """Download the artifact file."""
    art = artifact_store.get(artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if art.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = artifact_store.get_path(artifact_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=art.filename,
        media_type=art.mime_type,
    )


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: str,
    current_user=Depends(get_current_user),
):
    """Delete an artifact and its file."""
    art = artifact_store.get(artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if art.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    await artifact_store.delete(artifact_id)
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  HITL (Human-in-the-Loop) endpoints
# ─────────────────────────────────────────────────────────────────────────────

class HITLRequest(BaseModel):
    mission_id: str
    agent_name: str
    action_type: str      # "code_execution" | "file_write" | "api_call"
    action_description: str
    risk_level: str       # "low" | "medium" | "high"
    code_preview: Optional[str] = None
    user_id: str


class HITLDecision(BaseModel):
    reason: Optional[str] = None


def register_hitl_request(request: HITLRequest) -> asyncio.Event:
    """Register a HITL request and return an Event to await approval."""
    _hitl_pending[request.mission_id] = request.dict()
    event = asyncio.Event()
    _hitl_events[request.mission_id] = event
    logger.info(
        f"[HITL] Registered request for mission {request.mission_id} "
        f"action={request.action_type} risk={request.risk_level}"
    )
    return event


async def wait_for_hitl_approval(mission_id: str, timeout: float = 300.0) -> bool:
    """
    Wait for a human to approve/reject the HITL request.
    Returns True if approved, False if rejected or timed out.
    """
    event = _hitl_events.get(mission_id)
    if not event:
        return False
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        req = _hitl_pending.get(mission_id, {})
        return req.get("_decision") == "approved"
    except asyncio.TimeoutError:
        logger.warning(f"[HITL] Timeout waiting for approval: mission={mission_id}")
        return False
    finally:
        _hitl_pending.pop(mission_id, None)
        _hitl_events.pop(mission_id, None)


@hitl_router.get("/pending")
async def list_pending_hitl(current_user=Depends(get_current_user)):
    """List all pending HITL approval requests for this user."""
    user_id = str(current_user.id)
    pending = [
        req for req in _hitl_pending.values()
        if req.get("user_id") == user_id
    ]
    return {"pending": pending, "count": len(pending)}


@hitl_router.post("/approve/{mission_id}")
async def approve_hitl(
    mission_id: str,
    decision: HITLDecision,
    current_user=Depends(get_current_user),
):
    """Approve a pending HITL request — allows the agent to proceed."""
    req = _hitl_pending.get(mission_id)
    if not req:
        raise HTTPException(status_code=404, detail="No pending request for this mission")
    if req.get("user_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    req["_decision"] = "approved"
    req["_reason"]   = decision.reason
    event = _hitl_events.get(mission_id)
    if event:
        event.set()

    logger.info(f"[HITL] ✓ Approved mission={mission_id} by user={current_user.id}")
    return {"mission_id": mission_id, "status": "approved"}


@hitl_router.post("/reject/{mission_id}")
async def reject_hitl(
    mission_id: str,
    decision: HITLDecision,
    current_user=Depends(get_current_user),
):
    """Reject a pending HITL request — cancels the risky action."""
    req = _hitl_pending.get(mission_id)
    if not req:
        raise HTTPException(status_code=404, detail="No pending request for this mission")
    if req.get("user_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    req["_decision"] = "rejected"
    req["_reason"]   = decision.reason
    event = _hitl_events.get(mission_id)
    if event:
        event.set()

    logger.info(f"[HITL] ✗ Rejected mission={mission_id} by user={current_user.id}")
    return {"mission_id": mission_id, "status": "rejected"}
