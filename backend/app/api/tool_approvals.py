import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.tool_approval import ToolApproval
from app.schemas.auth import UserOut
from app.services.tool_approval_service import ApprovalError, claim_approval, get_owned_approval
from app.tools.registry import ToolRegistry, tool_requires_confirmation

router = APIRouter(prefix="/tool-approvals", tags=["Tool approvals"])
logger = logging.getLogger(__name__)


class ToolApprovalOut(BaseModel):
    id: str
    chat_id: str | None
    tool_name: str
    server_name: str
    arguments: Dict[str, Any]
    status: str
    result: str | None = None


def _to_out(record: ToolApproval) -> ToolApprovalOut:
    return ToolApprovalOut(
        id=record.id, chat_id=record.chat_id, tool_name=record.tool_name,
        server_name=record.server_name, arguments=record.arguments or {}, status=record.status, result=record.result,
    )


@router.get("", response_model=List[ToolApprovalOut])
async def list_approvals(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ToolApproval).where(ToolApproval.user_id == str(current_user.id)).order_by(ToolApproval.created_at.desc()).limit(50)
    )
    return [_to_out(record) for record in result.scalars().all()]


@router.post("/{approval_id}/reject", response_model=ToolApprovalOut)
async def reject_approval(
    approval_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        record = await get_owned_approval(db, approval_id, current_user.id)
    except ApprovalError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if record.status != "pending":
        raise HTTPException(status_code=409, detail="This approval request has already been decided.")
    record.status = "rejected"
    record.result = "Rejected by user; no external action was performed."
    await db.commit()
    await db.refresh(record)
    return _to_out(record)


@router.post("/{approval_id}/approve", response_model=ToolApprovalOut)
async def approve_approval(
    approval_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        record = await claim_approval(db, approval_id, current_user.id)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    registry = ToolRegistry()
    try:
        # A process restart leaves the singleton empty.  Reload only the
        # current user's persisted remote servers before executing the exact
        # server/tool pair captured in the approval record.
        await registry.sync_remote_servers(str(current_user.id))
        if registry.mcp_tools_map.get(record.tool_name) != record.server_name or not tool_requires_confirmation(record.tool_name, True):
            raise ApprovalError("The requested external action is no longer available.")
        output = await registry.call_tool(
            record.tool_name,
            record.arguments or {},
            user_id=current_user.id,
            approved=True,
            raise_on_error=True,
        )
        record.status = "completed"
        record.result = output[:20_000]
    except ApprovalError as exc:
        record.status = "failed"
        record.result = "External action is no longer available; no action was performed."
        await db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=record.result) from exc
    except Exception as exc:
        record.status = "failed"
        record.result = "External action failed; it was not retried automatically."
        await db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=record.result) from exc
    finally:
        try:
            await registry.shutdown()
        except Exception as shutdown_error:
            # Cleanup must never replace a completed external-action outcome.
            logger.warning("Failed to close temporary MCP registry: %s", type(shutdown_error).__name__)

    await db.commit()
    await db.refresh(record)
    return _to_out(record)
