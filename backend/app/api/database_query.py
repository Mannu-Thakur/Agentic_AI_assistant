"""
api/database_query.py — Read-only database introspection & query endpoints.

GET  /api/v1/database/tables           — List all tables
GET  /api/v1/database/tables/{name}    — Describe a table's schema
POST /api/v1/database/query            — Execute a read-only SQL query
"""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from typing import Optional
from app.api.admin import get_current_active_admin
from app.core.config import settings

router = APIRouter(prefix="/database", tags=["Database"])


def _require_database_inspector() -> None:
    if not settings.ENABLE_ADMIN_DATABASE_INSPECTOR:
        # Do not advertise this high-impact endpoint on a public installation.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# ── List Tables ───────────────────────────────────────────────────────────────

@router.get("/tables", summary="List all database tables")
async def list_tables_endpoint(admin=Depends(get_current_active_admin)):
    """
    Return a markdown-formatted list of all tables in the application SQLite database.
    """
    _require_database_inspector()
    from app.tools.advanced_tools import list_tables
    result = await list_tables()
    if result.startswith("Error"):
        raise HTTPException(status_code=500, detail=result)
    return {"result": result}


# ── Describe Table ────────────────────────────────────────────────────────────

@router.get("/tables/{table_name}", summary="Describe a table's schema")
async def describe_table_endpoint(
    table_name: str = Path(..., description="Name of the table to describe", min_length=1, max_length=64),
    admin=Depends(get_current_active_admin),
):
    """
    Return the column names, types, nullability, and row count for the given table.
    """
    _require_database_inspector()
    from app.tools.advanced_tools import describe_table
    result = await describe_table(table_name=table_name)
    if result.startswith("Error"):
        raise HTTPException(status_code=400, detail=result)
    return {"table": table_name, "result": result}


# ── Execute Query ─────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., description="Read-only SQL query (SELECT / PRAGMA / EXPLAIN / WITH)", min_length=1)
    max_rows: Optional[int] = Field(50, description="Maximum rows to return (default 50, max 200)", ge=1, le=200)


class QueryResponse(BaseModel):
    query: str
    result: str
    max_rows: int


@router.post("/query", response_model=QueryResponse, summary="Execute a read-only SQL query")
async def execute_query_endpoint(body: QueryRequest, admin=Depends(get_current_active_admin)):
    """
    Execute a **read-only** SQL query (SELECT, PRAGMA, EXPLAIN, WITH) against
    the application's SQLite database.

    INSERT, UPDATE, DELETE, DROP, and all other destructive operations are blocked.
    """
    _require_database_inspector()
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")

    from app.tools.advanced_tools import execute_sql
    result = await execute_sql(query=body.query, max_rows=body.max_rows or 50)

    if result.startswith("Error") or result.startswith("SQL Error"):
        raise HTTPException(status_code=400, detail=result)

    return QueryResponse(
        query=body.query,
        result=result,
        max_rows=body.max_rows or 50,
    )
