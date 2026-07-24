"""
app/services/audit_service.py

Uses db.flush() + db.refresh() instead of db.commit() so audit records are
written within the current request's transaction without prematurely committing
the outer session.  The request lifecycle middleware (get_db) commits on clean
exit, so audit entries are always atomically grouped with the triggering action.
"""
import logging
import json
from typing import Optional, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import AuditLog

logger = logging.getLogger("app.audit")


class AuditService:
    @staticmethod
    async def log_event(
        db: AsyncSession,
        user_id: Optional[str],
        event_type: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Logs a security or audit event to PostgreSQL/SQLite and to structured logs.

        Uses flush() instead of commit() so the audit entry is grouped with the
        caller's outer transaction — the outer get_db() dependency commits on
        success and rolls back on failure.
        """
        audit = AuditLog(
            user_id=user_id,
            event_type=event_type,
            details=details or {},
            ip_address=ip_address,
        )
        db.add(audit)
        try:
            await db.flush()
            await db.refresh(audit)
        except Exception as e:
            # Non-fatal: log to structured output even if DB write fails
            logger.error(f"Failed to flush audit log to DB: {e}")
            import uuid
            from datetime import datetime, timezone
            audit.id = str(uuid.uuid4())
            audit.created_at = datetime.now(timezone.utc)

        # Emit structured JSON log regardless of DB outcome
        logger.info(json.dumps({
            "event":       "audit",
            "audit_id":    audit.id,
            "user_id":     user_id,
            "event_type":  event_type,
            "details":     details or {},
            "ip_address":  ip_address,
            "timestamp":   str(audit.created_at),
        }))
        return audit
