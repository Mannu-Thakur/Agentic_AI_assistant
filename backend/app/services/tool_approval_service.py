"""Durable, one-time confirmation records for remote action tools."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool_approval import ToolApproval

APPROVAL_TTL_MINUTES = 10


class ApprovalError(ValueError):
    pass


async def create_approval(
    db: AsyncSession,
    *,
    user_id: str,
    chat_id: str | None,
    tool_name: str,
    arguments: Dict[str, Any],
    server_name: str,
) -> ToolApproval:
    record = ToolApproval(
        user_id=str(user_id),
        chat_id=str(chat_id) if chat_id else None,
        tool_name=tool_name,
        arguments=arguments or {},
        server_name=server_name,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=APPROVAL_TTL_MINUTES),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_owned_approval(db: AsyncSession, approval_id: str, user_id: str) -> ToolApproval:
    result = await db.execute(
        select(ToolApproval).where(ToolApproval.id == approval_id, ToolApproval.user_id == str(user_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise ApprovalError("Approval request not found.")
    return record


async def claim_approval(db: AsyncSession, approval_id: str, user_id: str) -> ToolApproval:
    now = datetime.now(timezone.utc)
    # Compare-and-set transitions pending -> executing.  It is deliberately a
    # single UPDATE instead of read-then-write, so two browser tabs cannot both
    # obtain permission to execute the same external action.
    transition = await db.execute(
        update(ToolApproval)
        .where(
            ToolApproval.id == approval_id,
            ToolApproval.user_id == str(user_id),
            ToolApproval.status == "pending",
            ToolApproval.expires_at > now,
        )
        .values(status="executing", consumed_at=now)
    )
    if transition.rowcount != 1:
        await db.rollback()
        record = await get_owned_approval(db, approval_id, user_id)
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if record.status == "pending" and expires_at <= now:
            record.status = "expired"
            await db.commit()
            raise ApprovalError("This approval request expired. Ask the assistant to prepare the action again.")
        raise ApprovalError("This approval request has already been decided.")

    # Persist this state transition before the network call so a request retry
    # can never replay the side effect.  A later failure stays failed, never
    # returns to pending.
    await db.commit()
    return await get_owned_approval(db, approval_id, user_id)
