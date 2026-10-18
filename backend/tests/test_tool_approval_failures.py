from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import tool_approvals
from app.models.tool_approval import ToolApproval
from app.schemas.auth import UserOut


@pytest.mark.anyio
async def test_indeterminate_mcp_failure_is_not_marked_completed(monkeypatch):
    record = ToolApproval(
        id="approval-1",
        user_id="user-1",
        chat_id=None,
        tool_name="remote_send_email",
        arguments={"to": "person@example.com"},
        server_name="remote_mail",
        status="executing",
        expires_at=datetime.now(timezone.utc),
    )

    async def claim(*_args):
        return record

    class FakeRegistry:
        def __init__(self):
            self.mcp_tools_map = {record.tool_name: record.server_name}

        async def sync_remote_servers(self, _user_id):
            return None

        async def call_tool(self, *_args, **kwargs):
            assert kwargs["raise_on_error"] is True
            raise RuntimeError(
                "Tool execution failed and was not retried because its completion state is unknown."
            )

        async def shutdown(self):
            return None

    class FakeDB:
        async def commit(self):
            return None

        async def refresh(self, _record):
            return None

    monkeypatch.setattr(tool_approvals, "claim_approval", claim)
    monkeypatch.setattr(tool_approvals, "ToolRegistry", FakeRegistry)
    monkeypatch.setattr(tool_approvals, "tool_requires_confirmation", lambda *_: True)
    user = UserOut(
        id="user-1",
        email="user@example.com",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(HTTPException) as exc_info:
        await tool_approvals.approve_approval("approval-1", user, FakeDB())

    assert exc_info.value.status_code == 502
    assert record.status == "failed"
    assert record.status != "completed"
    assert "not retried" in record.result
