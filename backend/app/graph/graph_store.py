"""
app/graph/graph_store.py — Persist entities and relationships to Neo4j.

Every entity and relationship is stored with full source provenance:
  source_doc_id, source_chunk_id, source_text_snippet, confidence.
"""
from __future__ import annotations

import logging
from typing import List

from app.graph.neo4j_client import neo4j_client
from app.graph.entity_extractor import Entity, Relationship

logger = logging.getLogger("app.graph.graph_store")


async def upsert_entities(entities: List[Entity]) -> int:
    """
    Upsert entities into Neo4j. Uses MERGE on (name, type) to avoid duplicates.
    Returns count of entities written.
    """
    if not neo4j_client.is_available or not entities:
        return 0

    written = 0
    for entity in entities:
        cypher = """
        MERGE (e:Entity {name: $name, type: $type})
        ON CREATE SET
            e.id               = $id,
            e.description      = $description,
            e.confidence       = $confidence,
            e.source_doc_id    = $source_doc_id,
            e.source_chunk_id  = $source_chunk_id,
            e.source_text      = $source_text,
            e.created_at       = timestamp()
        ON MATCH SET
            e.confidence       = CASE WHEN $confidence > e.confidence THEN $confidence ELSE e.confidence END,
            e.updated_at       = timestamp()
        """
        success = await neo4j_client.run_write(cypher, {
            "name": entity.name,
            "type": entity.type,
            "id": entity.id,
            "description": entity.description,
            "confidence": entity.confidence,
            "source_doc_id": entity.source_doc_id,
            "source_chunk_id": entity.source_chunk_id,
            "source_text": entity.source_text_snippet,
        })
        if success:
            written += 1

    logger.info(f"[GraphStore] Upserted {written}/{len(entities)} entities")
    return written


async def upsert_relationships(relationships: List[Relationship]) -> int:
    """
    Upsert relationships between existing entities.
    Returns count of relationships written.
    """
    if not neo4j_client.is_available or not relationships:
        return 0

    written = 0
    for rel in relationships:
        cypher = """
        MATCH (src:Entity {name: $source})
        MATCH (tgt:Entity {name: $target})
        MERGE (src)-[r:RELATES {type: $rel_type}]->(tgt)
        ON CREATE SET
            r.id              = $id,
            r.confidence      = $confidence,
            r.source_doc_id   = $source_doc_id,
            r.source_chunk_id = $source_chunk_id,
            r.created_at      = timestamp()
        ON MATCH SET
            r.confidence      = CASE WHEN $confidence > r.confidence THEN $confidence ELSE r.confidence END,
            r.updated_at      = timestamp()
        """
        success = await neo4j_client.run_write(cypher, {
            "source": rel.source_name,
            "target": rel.target_name,
            "rel_type": rel.relationship_type,
            "id": rel.id,
            "confidence": rel.confidence,
            "source_doc_id": rel.source_doc_id,
            "source_chunk_id": rel.source_chunk_id,
        })
        if success:
            written += 1

    logger.info(f"[GraphStore] Upserted {written}/{len(relationships)} relationships")
    return written


async def delete_document_entities(doc_id: str) -> None:
    """Remove all entities from a specific document (used when document is deleted)."""
    if not neo4j_client.is_available:
        return
    await neo4j_client.run_write(
        "MATCH (e:Entity {source_doc_id: $doc_id}) DETACH DELETE e",
        {"doc_id": doc_id},
    )
    logger.info(f"[GraphStore] Deleted entities for doc {doc_id}")
