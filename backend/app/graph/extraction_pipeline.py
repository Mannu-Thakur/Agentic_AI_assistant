"""
app/graph/extraction_pipeline.py — Orchestrates entity extraction from document chunks.

This pipeline runs asynchronously (via background tasks) when a document is ingested.
It:
  1. Fetches chunks from ChromaDB for the document
  2. Calls entity_extractor for each chunk
  3. Validates and persists entities + relationships to Neo4j
  4. Updates document metadata with extraction status

If Neo4j is unavailable, the pipeline skips silently without affecting ingestion.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.graph.neo4j_client import neo4j_client
from app.graph.entity_extractor import extract_entities_from_chunk
from app.graph.graph_store import upsert_entities, upsert_relationships

logger = logging.getLogger("app.graph.extraction_pipeline")

# Limit concurrent LLM calls during extraction to avoid rate limits
_EXTRACTION_SEMAPHORE = asyncio.Semaphore(3)


async def run_extraction_pipeline(
    doc_id: str,
    chunks: List[Dict[str, Any]],
    max_chunks: int = 50,
) -> Dict[str, int]:
    """
    Run the full entity extraction pipeline for a document.

    Args:
        doc_id: Document ID (for provenance)
        chunks: List of {id, text, metadata} dicts from ChromaDB
        max_chunks: Maximum chunks to process (to control cost)

    Returns:
        {"entities_extracted": N, "relationships_extracted": M, "chunks_processed": K}
    """
    if not neo4j_client.is_available or not settings.GRAPHRAG_ENABLED:
        logger.info(f"[ExtractionPipeline] Skipping graph extraction for doc {doc_id} (Neo4j unavailable or GRAPHRAG_ENABLED=false)")
        return {"entities_extracted": 0, "relationships_extracted": 0, "chunks_processed": 0}

    if not chunks:
        return {"entities_extracted": 0, "relationships_extracted": 0, "chunks_processed": 0}

    # Process up to max_chunks to control API cost
    chunks_to_process = chunks[:max_chunks]
    total_entities = []
    total_relationships = []

    async def process_chunk(chunk: Dict[str, Any]) -> None:
        async with _EXTRACTION_SEMAPHORE:
            chunk_id = chunk.get("id", "")
            chunk_text = chunk.get("text", chunk.get("document", ""))
            if not chunk_text:
                return
            try:
                entities, relationships = await extract_entities_from_chunk(
                    chunk_text=chunk_text,
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                )
                total_entities.extend(entities)
                total_relationships.extend(relationships)
            except Exception as e:
                logger.warning(f"[ExtractionPipeline] Chunk {chunk_id} failed: {e}")

    # Run chunk processing concurrently (bounded by semaphore)
    await asyncio.gather(*[process_chunk(c) for c in chunks_to_process])

    # Persist to Neo4j
    written_entities = await upsert_entities(total_entities)
    written_rels = await upsert_relationships(total_relationships)

    result = {
        "entities_extracted": len(total_entities),
        "relationships_extracted": len(total_relationships),
        "entities_written": written_entities,
        "relationships_written": written_rels,
        "chunks_processed": len(chunks_to_process),
    }
    logger.info(f"[ExtractionPipeline] doc={doc_id}: {result}")
    return result
