import asyncio
import time
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.mcp_server import RemoteMcpServer
from app.api.auth import get_current_user
from app.tools.mcp_client import McpHttpClient
from app.tools.registry import ToolRegistry

logger = logging.getLogger("app.api.mcp_servers")

router = APIRouter(prefix="/mcp/servers", tags=["mcp_servers"])


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
    """List all registered remote MCP servers for the user."""
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

    return out


@router.post("/test")
async def test_mcp_server_connection(req: TestConnectionRequest):
    """Test connection and tool discovery for a remote MCP server URL before saving."""
    t0 = time.perf_counter()
    client = McpHttpClient(url=req.url, auth_header=req.auth_header, transport_type=req.transport_type)
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)
        tools = await asyncio.wait_for(client.list_tools(), timeout=10.0)
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
    except Exception as e:
        await client.close()
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "status": "error",
            "message": f"Connection failed: {str(e)}",
            "latency_ms": latency_ms,
            "tools": [],
        }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_remote_mcp_server(
    payload: RemoteMcpServerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a new remote MCP server, test connection, and register exposed tools."""
    # Test connection first
    client = McpHttpClient(url=payload.url, auth_header=payload.auth_header, transport_type=payload.transport_type)
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)
        discovered_tools = await asyncio.wait_for(client.list_tools(), timeout=10.0)
        await client.close()
    except asyncio.TimeoutError:
        await client.close()
        raise HTTPException(
            status_code=408,
            detail=f"Remote MCP Server connection timed out after 10s ({payload.url}). Check URL and server health."
        )
    except Exception as e:
        await client.close()
        raise HTTPException(
            status_code=400,
            detail=f"Could not connect to Remote MCP Server URL ({payload.url}): {str(e)}"
        )

    new_server = RemoteMcpServer(
        user_id=current_user.id,
        name=payload.name,
        url=payload.url,
        transport_type=payload.transport_type or "http_jsonrpc",
        auth_header=payload.auth_header,
        is_enabled=payload.is_enabled if payload.is_enabled is not None else True,
    )
    db.add(new_server)
    await db.commit()
    await db.refresh(new_server)

    # Register tools into live ToolRegistry
    if new_server.is_enabled:
        registry = ToolRegistry()
        try:
            await registry.register_remote_server(
                name=new_server.name,
                url=new_server.url,
                auth_header=new_server.auth_header,
                transport_type=new_server.transport_type
            )
        except Exception as reg_exc:
            logger.warning(f"Failed live registration for new server '{new_server.name}': {reg_exc}")

    return {
        "id": new_server.id,
        "name": new_server.name,
        "url": new_server.url,
        "is_enabled": new_server.is_enabled,
        "discovered_tools_count": len(discovered_tools),
        "message": "Remote MCP server added and registered successfully."
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

    # Re-initialize registry to remove tool bindings
    registry = ToolRegistry()
    registry.is_initialized = False
    await registry.initialize()

    return None
