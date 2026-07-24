from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.core.database import get_db
from app.api.auth import get_current_user
from app.schemas.auth import UserOut
from app.models.user import User
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/admin", tags=["Admin Operations"])

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # FIX-12: Pydantic V2 style

    id: str
    user_id: Optional[str]
    event_type: str
    details: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime

def get_current_active_admin(current_user: User = Depends(get_current_user)):
    """Validates that the current user has admin privileges."""
    if getattr(current_user, "role", "user") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required."
        )
    return current_user

@router.get("/users", response_model=List[UserOut])
async def list_all_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_active_admin)
):
    """Retrieves all users registered on the platform (Admin-only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    
    from app.services.audit_service import AuditService
    await AuditService.log_event(db, admin.id, "admin_action", {"action": "list_all_users"})
    
    return users

@router.get("/audit-logs", response_model=List[AuditLogOut])
async def list_all_audit_logs(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_active_admin)
):
    """Retrieves the last 100 system audit logs (Admin-only)."""
    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100))
    logs = result.scalars().all()
    
    from app.services.audit_service import AuditService
    await AuditService.log_event(db, admin.id, "admin_action", {"action": "list_all_audit_logs"})
    
    return logs
