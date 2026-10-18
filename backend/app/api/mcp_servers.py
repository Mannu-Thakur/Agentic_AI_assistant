import asyncio
import re
import time
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.redis_client import cache_get, cache_set, cache_delete
from app.models.user import User
from app.models.mcp_server import RemoteMcpServer
from app.api.auth import get_current_user
from app.tools.mcp_client import McpHttpClient
from app.tools.registry import ToolRegistry
from app.tools.registry import remote_server_key
from app.tools.network_safety import UnsafeOutboundUrl, assert_public_dns_resolution, normalise_outbound_url
from app.core.config import settings
from app.core.security import encrypt_api_key

logger = logging.getLogger("app.api.mcp_servers")

router = APIRouter(prefix="/mcp/servers", tags=["mcp_servers"])

REDIS_TTL_MCP = 600  # 10 minutes
_MCP_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,62}$")


def _allow_insecure_mcp() -> bool:
    return settings.ENVIRONMENT == "development" and settings.ALLOW_INSECURE_MCP_IN_DEVELOPMENT


def _normalise_mcp_url(value: str) -> str:
    return normalise_outbound_url(value, allow_http=_allow_insecure_mcp())


async def _verify_mcp_destination(value: str) -> str:
    return await assert_public_dns_resolution(value, allow_http=_allow_insecure_mcp())


class RemoteMcpServerCreate(BaseModel):
    name: str
    url: str
    transport_type: Optional[str] = "http_jsonrpc"
    auth_header: Optional[str] = None
    is_enabled: Optional[bool] = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _normalise_mcp_url(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not _MCP_SERVER_NAME_RE.fullmatch(value):
            raise ValueError("Server name must be 1-63 letters, digits, spaces, dots, underscores, or hyphens.")
        return value

    @field_validator("auth_header")
    @classmethod
    def validate_auth_header(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 4096 or "\r" in value or "\n" in value:
            raise ValueError("Authorization value is invalid.")
        return value


class RemoteMcpServerUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    auth_header: Optional[str] = None
    is_enabled: Optional[bool] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: Optional[str]) -> Optional[str]:
        return _normalise_mcp_url(value) if value is not None else value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not _MCP_SERVER_NAME_RE.fullmatch(value):
            raise ValueError("Server name must be 1-63 letters, digits, spaces, dots, underscores, or hyphens.")
        return value

    @field_validator("auth_header")
    @classmethod
    def validate_auth_header(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 4096 or "\r" in value or "\n" in value:
            raise ValueError("Authorization value is invalid.")
        return value


class TestConnectionRequest(BaseModel):
    url: str
    auth_header: Optional[str] = None
    transport_type: Optional[str] = "http_jsonrpc"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _normalise_mcp_url(value)


@router.get("", response_model=List[Dict[str, Any]])
async def list_remote_mcp_servers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all registered remote MCP servers for the user, with Redis caching."""
    cache_key = f"mcp:servers:{current_user.id}"
    cached = await cache_get(cache_key)
    if cached and isinstance(cached, list):
        return cached

    stmt = select(RemoteMcpServer).where(
        (RemoteMcpServer.user_id == current_user.id) | (RemoteMcpServer.user_id.is_(None))
    ).order_by(RemoteMcpServer.created_at.desc())
    
    result = await db.execute(stmt)
    servers = result.scalars().all()

    registry = ToolRegistry()
    try:
        await registry.sync_remote_servers(str(current_user.id))
        out = []
        for s in servers:
            # Find tools belonging to this server key if registered
            server_key = remote_server_key(s.name)
            tools_list = []
            for t_name, s_name in registry.mcp_tools_map.items():
                if s_name == server_key:
                    schema_info = registry.mcp_tools_schemas.get(t_name, {})
                    tools_list.append({
                        "name": registry.mcp_tool_original_names.get(t_name, t_name),
                        "registered_name": t_name,
                        "description": schema_info.get("description", ""),
                        "schema": schema_info.get("schema", {})
                    })

            out.append({
                "id": s.id,
                "name": s.name,
                "url": s.url,
                "transport_type": s.transport_type,
                "auth_header": "*****" if s.auth_header else None,
                "is_enabled": s.is_enabled,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "discovered_tools": tools_list,
                "tool_count": len(tools_list),
            })
    finally:
        await registry.shutdown()

    await cache_set(cache_key, out, ttl_seconds=REDIS_TTL_MCP)
    return out


@router.post("/test")
async def test_mcp_server_connection(
    req: TestConnectionRequest,
    current_user: User = Depends(get_current_user),
):
    """Test connection and tool discovery for a remote MCP server URL before saving."""
    t0 = time.perf_counter()
    try:
        url = await _verify_mcp_destination(req.url)
    except UnsafeOutboundUrl as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    client = McpHttpClient(url=url, auth_header=req.auth_header, transport_type=req.transport_type)
    try:
        await asyncio.wait_for(client.connect(), timeout=12.0)
        tools = await asyncio.wait_for(client.list_tools(), timeout=12.0)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        tool_summaries = []
        for t in tools:
            tool_summaries.append({
                "name": t.get("name"),
                "description": t.get("description", ""),
                "schema": t.get("inputSchema", {})
            })

        return {
            "status": "success",
            "message": f"Successfully connected to remote MCP server. Discovered {len(tools)} tools.",
            "latency_ms": latency_ms,
            "tool_count": len(tools),
            "tools": tool_summaries,
        }
    except (asyncio.TimeoutError, TimeoutError):
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "status": "error",
            "message": "Connection timed out (12s). The remote server took too long to respond. If hosted on a free cloud tier, it may still be spinning up.",
            "latency_ms": latency_ms,
            "tools": [],
        }
    except Exception as e:
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        err_msg = str(e).strip() or type(e).__name__
        return {
            "status": "error",
            "message": f"Connection failed: {err_msg}",
            "latency_ms": latency_ms,
            "tools": [],
        }
    finally:
        try:
            await client.close()
        except Exception:
            pass


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_remote_mcp_server(
    payload: RemoteMcpServerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add or update a remote MCP server, register in DB, cache in Redis, and bind tools."""
    discovered_tools = []
    connection_warning = None

    try:
        url = await _verify_mcp_destination(payload.url)
    except UnsafeOutboundUrl as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Test connection gracefully (8.0s timeout to allow for cloud cold starts like Render/Railway)
    client = McpHttpClient(url=url, auth_header=payload.auth_header, transport_type=payload.transport_type)
    try:
        await asyncio.wait_for(client.connect(), timeout=8.0)
        discovered_tools = await asyncio.wait_for(client.list_tools(), timeout=8.0)
    except Exception as e:
        logger.warning("[MCP Save] Refusing to save unverified remote endpoint: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The remote MCP server could not complete a tools discovery handshake and was not saved.",
        ) from e
    finally:
        try:
            await client.close()
        except Exception:
            pass

    # Check if a server with this URL or Name already exists for this user (upsert)
    stmt = select(RemoteMcpServer).where(
        ((RemoteMcpServer.url == url) | (RemoteMcpServer.name == payload.name.strip())) &
        ((RemoteMcpServer.user_id == current_user.id) | (RemoteMcpServer.user_id.is_(None)))
    )
    res = await db.execute(stmt)
    existing_server = res.scalars().first()

    if existing_server:
        existing_server.name = payload.name
        existing_server.url = url
        existing_server.transport_type = payload.transport_type or "http_jsonrpc"
        if payload.auth_header is not None:
            existing_server.auth_header = encrypt_api_key(payload.auth_header) if payload.auth_header else None
        if payload.is_enabled is not None:
            existing_server.is_enabled = payload.is_enabled
        server_obj = existing_server
    else:
        server_obj = RemoteMcpServer(
            user_id=current_user.id,
            name=payload.name,
            url=url,
            transport_type=payload.transport_type or "http_jsonrpc",
            auth_header=encrypt_api_key(payload.auth_header) if payload.auth_header else None,
            is_enabled=payload.is_enabled if payload.is_enabled is not None else True,
        )
        db.add(server_obj)

    await db.commit()
    await db.refresh(server_obj)

    # Invalidate Redis cache
    cache_key = f"mcp:servers:{current_user.id}"
    await cache_delete(cache_key)

    return {
        "id": server_obj.id,
        "name": server_obj.name,
        "url": server_obj.url,
        "is_enabled": server_obj.is_enabled,
        "discovered_tools_count": len(discovered_tools),
        "warning": connection_warning,
        "message": connection_warning or "Remote MCP server saved to database and Redis successfully."
    }


@router.patch("/{server_id}")
async def update_remote_mcp_server(
    server_id: str,
    payload: RemoteMcpServerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update or toggle enabled state of a remote MCP server."""
    stmt = select(RemoteMcpServer).where(
        RemoteMcpServer.id == server_id,
        (RemoteMcpServer.user_id == current_user.id) | (RemoteMcpServer.user_id.is_(None))
    )
    res = await db.execute(stmt)
    server = res.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Remote MCP Server not found.")

    if payload.name is not None:
        server.name = payload.name
    if payload.url is not None:
        try:
            server.url = await _verify_mcp_destination(payload.url)
        except UnsafeOutboundUrl as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if payload.auth_header is not None:
        server.auth_header = encrypt_api_key(payload.auth_header) if payload.auth_header else None
    if payload.is_enabled is not None:
        server.is_enabled = payload.is_enabled

    await db.commit()
    await db.refresh(server)

    # Invalidate Redis cache
    cache_key = f"mcp:servers:{current_user.id}"
    await cache_delete(cache_key)

    return {
        "id": server.id,
        "name": server.name,
        "is_enabled": server.is_enabled,
        "message": "Remote MCP Server updated successfully."
    }


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_remote_mcp_server(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a remote MCP server configuration."""
    stmt = select(RemoteMcpServer).where(
        RemoteMcpServer.id == server_id,
        (RemoteMcpServer.user_id == current_user.id) | (RemoteMcpServer.user_id.is_(None))
    )
    res = await db.execute(stmt)
    server = res.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Remote MCP Server not found.")

    await db.delete(server)
    await db.commit()

    # Invalidate Redis cache
    cache_key = f"mcp:servers:{current_user.id}"
    await cache_delete(cache_key)

    return None
