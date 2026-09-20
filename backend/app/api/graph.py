"""
app/api/graph.py — Knowledge Graph REST API.

Endpoints:
  GET /graph/status          — Neo4j connection status
  GET /graph/quality         — Graph quality metrics
  GET /graph/stats           — Basic graph statistics
  GET /graph/entities        — Search entities by name/type
  GET /graph/entity/{name}   — Get entity with neighbors
  POST /graph/extract/{doc_id} — Trigger extraction for a document
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional


from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.core.config import settings
from app.graph.neo4j_client import neo4j_client
from app.graph.graph_quality import get_graph_quality_report
from app.graph.graph_retriever import retrieve_graph_context
from app.schemas.auth import UserOut

logger = logging.getLogger("app.api.graph")

# CRIT-1 FIX: Strong reference to fire-and-forget extraction tasks.
_background_tasks: set = set()


def _make_background_task(coro):
    """Anchor a fire-and-forget task to prevent GC before completion."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


router = APIRouter(prefix="/graph", tags=["Knowledge Graph"])


class GraphStatusOut(BaseModel):
    available: bool
    uri: Optional[str] = None
    graphrag_enabled: bool
    message: str


@router.get("/status", response_model=GraphStatusOut)
async def graph_status(
    current_user: UserOut = Depends(get_current_user),
):
    """Check Neo4j connection status and GraphRAG configuration."""
    available = neo4j_client.is_available
    uri = settings.NEO4J_URI or None
    return GraphStatusOut(
        available=available,
        uri=uri if uri else None,
        graphrag_enabled=settings.GRAPHRAG_ENABLED,
        message="Connected" if available else "Neo4j not connected. Set NEO4J_URI in .env to enable GraphRAG.",
    )


@router.get("/quality")
async def graph_quality(
    current_user: UserOut = Depends(get_current_user),
):
    """Get comprehensive knowledge graph quality metrics."""
    return await get_graph_quality_report()


@router.get("/stats")
async def graph_stats(
    current_user: UserOut = Depends(get_current_user),
):
    """Get basic graph statistics."""
    return await neo4j_client.get_stats()


@router.get("/entities")
async def search_entities(
    q: str = Query(..., min_length=1, max_length=200, description="Search term"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserOut = Depends(get_current_user),
):
    """Search entities in the knowledge graph by name or type."""
    if not neo4j_client.is_available:
        return {"entities": [], "message": "Neo4j not connected"}

    if entity_type:
        cypher = """
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($q) AND e.type = $type
        RETURN e.name AS name, e.type AS type, e.description AS description,
               e.confidence AS confidence, e.source_doc_id AS source_doc
        ORDER BY e.confidence DESC LIMIT $limit
        """
        rows = await neo4j_client.run_query(cypher, {"q": q, "type": entity_type, "limit": limit})
    else:
        cypher = """
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($q)
        RETURN e.name AS name, e.type AS type, e.description AS description,
               e.confidence AS confidence, e.source_doc_id AS source_doc
        ORDER BY e.confidence DESC LIMIT $limit
        """
        rows = await neo4j_client.run_query(cypher, {"q": q, "limit": limit})

    return {"entities": rows, "total": len(rows)}


@router.get("/entity/{entity_name}")
async def get_entity(
    entity_name: str,
    current_user: UserOut = Depends(get_current_user),
):
    """Get a specific entity with all its neighbors and relationships."""
    if not neo4j_client.is_available:
        raise HTTPException(status_code=503, detail="Neo4j not connected")

    cypher = """
    MATCH (e:Entity {name: $name})
    OPTIONAL MATCH (e)-[r:RELATES]->(neighbor:Entity)
    OPTIONAL MATCH (incoming:Entity)-[ir:RELATES]->(e)
    RETURN e.name AS name, e.type AS type, e.description AS description,
           e.confidence AS confidence, e.source_doc_id AS source_doc,
           e.source_text AS source_text,
           collect(DISTINCT {target: neighbor.name, target_type: neighbor.type, rel: r.type, confidence: r.confidence}) AS outgoing,
           collect(DISTINCT {source: incoming.name, source_type: incoming.type, rel: ir.type, confidence: ir.confidence}) AS incoming
    LIMIT 1
    """
    rows = await neo4j_client.run_query(cypher, {"name": entity_name})
    if not rows:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_name}' not found in knowledge graph")

    return rows[0]


@router.get("/retrieve")
async def retrieve_graph(
    q: str = Query(..., min_length=1, max_length=500, description="Query for graph retrieval"),
    limit: int = Query(10, ge=1, le=50),
    current_user: UserOut = Depends(get_current_user),
):
    """Retrieve graph context relevant to a query (for testing GraphRAG)."""
    results = await retrieve_graph_context(query=q, max_results=limit)
    return {"query": q, "graph_evidence": results, "count": len(results)}


@router.post("/extract/{doc_id}")
async def trigger_extraction(
    doc_id: str,
    current_user: UserOut = Depends(get_current_user),
):
    """
    Trigger entity extraction for a document that has already been ingested.
    The document's chunks must already be in ChromaDB.
    """
    if not neo4j_client.is_available:
        return {"message": "Neo4j not connected — GraphRAG disabled", "doc_id": doc_id}
    if not settings.GRAPHRAG_ENABLED:
        return {"message": "GRAPHRAG_ENABLED=false — set to true in .env to enable", "doc_id": doc_id}

    from app.retrieval.vector_store import VectorStore
    from app.graph.extraction_pipeline import run_extraction_pipeline
    import asyncio

    try:
        vs = VectorStore()
        collection = vs.get_collection()
        results = collection.get(where={"doc_id": doc_id}, include=["documents", "metadatas", "ids"])
        if not results or not results.get("ids"):
            raise HTTPException(status_code=404, detail=f"No chunks found for document {doc_id}")

        chunks = [
            {"id": cid, "text": cdoc}
            for cid, cdoc in zip(results["ids"], results["documents"])
        ]

        # CRIT-1 FIX: anchor in _background_tasks to prevent GC before completion.
        _make_background_task(run_extraction_pipeline(doc_id=doc_id, chunks=chunks))


        return {
            "message": "Extraction started",
            "doc_id": doc_id,
            "chunks_queued": len(chunks),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GraphAPI] Extraction trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
