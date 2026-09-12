import asyncio
import time
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.redis_client import cache_get, cache_set, cache_delete
from app.models.user import User
from app.models.mcp_server import RemoteMcpServer
from app.api.auth import get_current_user
from app.tools.mcp_client import McpHttpClient
from app.tools.registry import ToolRegistry

logger = logging.getLogger("app.api.mcp_servers")

router = APIRouter(prefix="/mcp/servers", tags=["mcp_servers"])

REDIS_TTL_MCP = 600  # 10 minutes


class RemoteMcpServerCreate(BaseModel):
    name: str
    url: str
    transport_type: Optional[str] = "http_jsonrpc"
    auth_header: Optional[str] = None
    is_enabled: Optional[bool] = True


class RemoteMcpServerUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    auth_header: Optional[str] = None
    is_enabled: Optional[bool] = None


class TestConnectionRequest(BaseModel):
    url: str
    auth_header: Optional[str] = None
    transport_type: Optional[str] = "http_jsonrpc"


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
    out = []
    for s in servers:
        # Find tools belonging to this server key if registered
        server_key = f"remote_{s.name.replace(' ', '_').lower()}"
        tools_list = []
        for t_name, s_name in registry.mcp_tools_map.items():
            if s_name == server_key:
                schema_info = registry.mcp_tools_schemas.get(t_name, {})
                tools_list.append({
                    "name": t_name,
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

    await cache_set(cache_key, out, ttl_seconds=REDIS_TTL_MCP)
    return out


@router.post("/test")
async def test_mcp_server_connection(req: TestConnectionRequest):
    """Test connection and tool discovery for a remote MCP server URL before saving."""
    t0 = time.perf_counter()
    client = McpHttpClient(url=req.url, auth_header=req.auth_header, transport_type=req.transport_type)
    try:
        await asyncio.wait_for(client.connect(), timeout=15.0)
        tools = await asyncio.wait_for(client.list_tools(), timeout=15.0)
        await client.close()
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
        await client.close()
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "status": "error",
            "message": "Connection timed out (15s). The remote server took too long to respond. If hosted on Render free tier, it may still be waking up from sleep.",
            "latency_ms": latency_ms,
            "tools": [],
        }
    except Exception as e:
        await client.close()
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        err_msg = str(e).strip() or type(e).__name__
        return {
            "status": "error",
            "message": f"Connection failed: {err_msg}",
            "latency_ms": latency_ms,
            "tools": [],
        }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_remote_mcp_server(
    payload: RemoteMcpServerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add or update a remote MCP server, register in DB, cache in Redis, and bind tools."""
    discovered_tools = []
    connection_warning = None

    # Test connection gracefully (fail-safe so user is never blocked from saving)
    client = McpHttpClient(url=payload.url, auth_header=payload.auth_header, transport_type=payload.transport_type)
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)
        discovered_tools = await asyncio.wait_for(client.list_tools(), timeout=10.0)
        await client.close()
    except Exception as e:
        await client.close()
        connection_warning = f"Server saved to DB & Redis, but remote endpoint did not respond immediately ({str(e)[:90]}). Tools will be discovered when server is reachable."
        logger.warning(f"[MCP Save] Server endpoint offline/slow during save: {e}")

    # Check if a server with this URL or Name already exists for this user (upsert)
    stmt = select(RemoteMcpServer).where(
        ((RemoteMcpServer.url == payload.url) | (RemoteMcpServer.name == payload.name)) &
        ((RemoteMcpServer.user_id == current_user.id) | (RemoteMcpServer.user_id.is_(None)))
    )
    res = await db.execute(stmt)
    existing_server = res.scalars().first()

    if existing_server:
        existing_server.name = payload.name
        existing_server.url = payload.url
        existing_server.transport_type = payload.transport_type or "http_jsonrpc"
        if payload.auth_header is not None:
            existing_server.auth_header = payload.auth_header
        if payload.is_enabled is not None:
            existing_server.is_enabled = payload.is_enabled
        server_obj = existing_server
    else:
        server_obj = RemoteMcpServer(
            user_id=current_user.id,
            name=payload.name,
            url=payload.url,
            transport_type=payload.transport_type or "http_jsonrpc",
            auth_header=payload.auth_header,
            is_enabled=payload.is_enabled if payload.is_enabled is not None else True,
        )
        db.add(server_obj)

    await db.commit()
    await db.refresh(server_obj)

    # Invalidate Redis cache
    cache_key = f"mcp:servers:{current_user.id}"
    await cache_delete(cache_key)

    # Register tools into live ToolRegistry if connected & enabled
    if server_obj.is_enabled and discovered_tools:
        registry = ToolRegistry()
        try:
            await registry.register_remote_server(
                name=server_obj.name,
                url=server_obj.url,
                auth_header=server_obj.auth_header,
                transport_type=server_obj.transport_type
            )
        except Exception as reg_exc:
            logger.warning(f"Failed live registration for server '{server_obj.name}': {reg_exc}")

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
        server.url = payload.url
    if payload.auth_header is not None:
        server.auth_header = payload.auth_header
    if payload.is_enabled is not None:
        server.is_enabled = payload.is_enabled

    await db.commit()
    await db.refresh(server)

    # Invalidate Redis cache
    cache_key = f"mcp:servers:{current_user.id}"
    await cache_delete(cache_key)

    # Re-initialize registry to refresh tool bindings
    registry = ToolRegistry()
    registry.is_initialized = False
    await registry.initialize()

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

    # Re-initialize registry to remove tool bindings
    registry = ToolRegistry()
    registry.is_initialized = False
    await registry.initialize()

    return None
