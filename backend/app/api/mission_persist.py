"""
app/api/mission_persist.py — Mission message persistence endpoint

After a mission completes, the frontend calls this endpoint to save
both the user query and the AI response as real DB messages in the
chat thread. This makes mission responses survive page refreshes.

POST /api/v1/mission/persist
Body: { chat_id, query, response, model, critic_score, artifacts, agent_names }
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.config import settings
from app.services.chat_service import ChatService

logger = logging.getLogger("api.mission_persist")
router = APIRouter(prefix="/mission", tags=["mission"])


class PersistMissionRequest(BaseModel):
    chat_id:      str
    query:        str
    response:     str
    model:        str              = settings.GEMINI_MODEL
    critic_score: float            = 0.8
    agent_names:  List[str]        = []
    artifacts:    List[Dict]       = []
    job_id:       Optional[str]    = None


class PersistMissionResponse(BaseModel):
    user_message_id:      str
    assistant_message_id: str
    chat_id:              str


@router.post("/persist", response_model=PersistMissionResponse)
async def persist_mission_messages(
    req: PersistMissionRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save the user query + mission response as real DB messages.
    Called by the frontend after mission_complete event is received.
    """
    user_id = str(current_user.id)
    logger.info(f"[MissionPersist] chat={req.chat_id} user={user_id} job={req.job_id}")

    # Verify the chat belongs to this user
    chat = await ChatService.get_chat_by_id(db, req.chat_id, user_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    now = datetime.now(timezone.utc)

    # ── Save user message ─────────────────────────────────────────────────────
    from app.models.chat import Message as MessageModel
    user_msg = MessageModel(
        id=str(uuid.uuid4()),
        chat_id=req.chat_id,
        parent_id=None,
        role="user",
        content=req.query,
        tool_calls=None,
        developer_metrics=None,
        created_at=now,
    )
    db.add(user_msg)
    await db.flush()  # get the ID before using as parent

    # ── Build developer_metrics for the assistant message ─────────────────────
    import json
    dev_metrics = {
        "model_used":       req.model,
        "latency_ms":       0,
        "tokens_input":     0,
        "tokens_output":    0,
        "cost_estimate":    0.0,
        "confidence_score": req.critic_score,
        "memory_hits":      0,
        "generation_mode":  "normal_rag",
        "steps":            [f"[Mission] {a}" for a in req.agent_names],
        "source_documents": [
            {
                "index":    i + 1,
                "filename": art.get("filename", f"artifact_{i+1}"),
                "content":  art.get("preview", "")[:200],
                "used":     True,
                "url":      art.get("download_url", ""),
            }
            for i, art in enumerate(req.artifacts)
        ],
    }

    # ── Save assistant message ────────────────────────────────────────────────
    asst_msg = MessageModel(
        id=str(uuid.uuid4()),
        chat_id=req.chat_id,
        parent_id=user_msg.id,
        role="assistant",
        content=req.response,
        tool_calls=None,
        developer_metrics=dev_metrics,
        created_at=now,
    )
    db.add(asst_msg)
    await db.commit()

    # ── Update chat title if it's still "New Chat" ───────────────────────────
    try:
        if chat.title in ("New Chat", "New chat", ""):
            title = req.query[:60].strip()
            if len(req.query) > 60:
                title += "..."
            await ChatService.update_chat(db, req.chat_id, user_id, title=title)
    except Exception as exc:
        logger.warning(f"[MissionPersist] Title update failed (non-fatal): {exc}")

    logger.info(
        f"[MissionPersist] Saved user={user_msg.id} asst={asst_msg.id} "
        f"chat={req.chat_id}"
    )

    return PersistMissionResponse(
        user_message_id=user_msg.id,
        assistant_message_id=asst_msg.id,
        chat_id=req.chat_id,
    )
