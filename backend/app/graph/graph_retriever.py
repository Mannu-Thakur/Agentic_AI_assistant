"""
app/graph/graph_retriever.py — Graph-based retrieval for GraphRAG.

Provides hybrid graph retrieval:
  1. Entity-centric: find entities matching query keywords → expand to neighbors
  2. Relationship-centric: find relationship paths between query entities
  3. Community-centric: return clusters of highly connected entities

Gracefully returns [] when Neo4j is unavailable.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.graph.neo4j_client import neo4j_client

logger = logging.getLogger("app.graph.graph_retriever")


async def retrieve_graph_context(
    query: str,
    max_results: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Main entry point: retrieve relevant graph context for a user query.

    Returns a list of graph evidence dicts, each with:
      - entity names and types
      - relationships between them
      - source provenance (doc_id, chunk_id)
      - relevance description

    Returns [] when Neo4j is unavailable.
    """
    if not neo4j_client.is_available:
        return []

    if not settings.GRAPHRAG_ENABLED:
        return []

    limit = max_results or settings.GRAPHRAG_MAX_GRAPH_RESULTS
    query_lower = query.lower()

    # Extract potential entity name keywords from query (simple approach)
    # In production, this can be upgraded to NER-based keyword extraction
    keywords = [w.strip('.,?!') for w in query.split() if len(w) > 3]
    keywords = list(set(keywords))[:10]  # cap to avoid query explosion

    results: List[Dict[str, Any]] = []

    # ── Strategy 1: Entity name search ────────────────────────────────────────
    for keyword in keywords[:5]:
        cypher = """
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($keyword)
           OR toLower(e.description) CONTAINS toLower($keyword)
        WITH e LIMIT 5
        OPTIONAL MATCH (e)-[r:RELATES]->(neighbor:Entity)
        RETURN e.name AS entity,
               e.type AS entity_type,
               e.description AS entity_description,
               e.confidence AS entity_confidence,
               e.source_doc_id AS source_doc,
               collect(DISTINCT {target: neighbor.name, rel: r.type, confidence: r.confidence}) AS neighbors
        LIMIT $limit
        """
        rows = await neo4j_client.run_query(cypher, {"keyword": keyword, "limit": limit})
        for row in rows:
            if row.get("entity"):
                results.append({
                    "source": "graph",
                    "entity": row["entity"],
                    "entity_type": row["entity_type"],
                    "description": row.get("entity_description", ""),
                    "confidence": row.get("entity_confidence", 0.7),
                    "source_doc_id": row.get("source_doc", ""),
                    "neighbors": [
                        n for n in (row.get("neighbors") or []) if n.get("target")
                    ],
                    "relevance": f"Entity '{row['entity']}' matches query keyword '{keyword}'",
                })

    # ── Strategy 2: Relationship path search (2-hop) ───────────────────────────
    if len(keywords) >= 2:
        k1, k2 = keywords[0], keywords[1]
        cypher = """
        MATCH path = (a:Entity)-[r:RELATES*1..2]->(b:Entity)
        WHERE (toLower(a.name) CONTAINS toLower($k1) OR toLower(b.name) CONTAINS toLower($k1))
          AND (toLower(a.name) CONTAINS toLower($k2) OR toLower(b.name) CONTAINS toLower($k2))
        RETURN a.name AS from_entity, a.type AS from_type,
               b.name AS to_entity, b.type AS to_type,
               [rel in relationships(path) | rel.type] AS rel_chain,
               a.source_doc_id AS source_doc
        LIMIT 5
        """
        rows = await neo4j_client.run_query(cypher, {"k1": k1, "k2": k2})
        for row in rows:
            if row.get("from_entity") and row.get("to_entity"):
                results.append({
                    "source": "graph_path",
                    "entity": row["from_entity"],
                    "entity_type": row["from_type"],
                    "related_entity": row["to_entity"],
                    "related_type": row["to_type"],
                    "relationship_chain": row.get("rel_chain", []),
                    "source_doc_id": row.get("source_doc", ""),
                    "confidence": 0.75,
                    "relevance": f"Relationship path: {row['from_entity']} → {row['to_entity']}",
                })

    # Deduplicate by entity name
    seen = set()
    unique_results = []
    for r in results:
        key = r.get("entity", "") + r.get("related_entity", "")
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    logger.info(f"[GraphRetriever] Query returned {len(unique_results)} graph evidence items")
    return unique_results[:limit]


def format_graph_context_for_llm(graph_results: List[Dict[str, Any]]) -> str:
    """
    Format graph evidence into a structured string for LLM context injection.
    """
    if not graph_results:
        return ""

    lines = ["\n## Knowledge Graph Evidence\n"]
    for i, item in enumerate(graph_results, 1):
        entity = item.get("entity", "Unknown")
        etype = item.get("entity_type", "Entity")
        desc = item.get("description", "")
        confidence = item.get("confidence", 0.0)
        source = item.get("source_doc_id", "")
        neighbors = item.get("neighbors", [])
        related = item.get("related_entity", "")
        rel_chain = item.get("relationship_chain", [])

        lines.append(f"### [{i}] {entity} ({etype}) [confidence: {confidence:.0%}]")
        if desc:
            lines.append(f"  Description: {desc}")
        if source:
            lines.append(f"  Source document: {source}")
        if neighbors:
            for n in neighbors[:5]:
                if n.get("target"):
                    lines.append(f"  → {n['rel'] or 'RELATES'}: {n['target']}")
        if related and rel_chain:
            chain = " → ".join(rel_chain)
            lines.append(f"  Relationship path to '{related}': {chain}")
        lines.append("")

    return "\n".join(lines)
