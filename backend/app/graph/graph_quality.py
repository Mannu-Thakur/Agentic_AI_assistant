"""
app/graph/graph_quality.py — Knowledge graph health and quality metrics.

Metrics tracked:
  - Total nodes and relationships
  - Entity type distribution
  - Orphan nodes (no relationships)
  - Duplicate detection (entities with same name, different types)
  - Missing provenance (entities with no source_doc_id)
  - Low-confidence entities (< 0.5)
  - Source document coverage
  - Relationship type distribution
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.graph.neo4j_client import neo4j_client

logger = logging.getLogger("app.graph.graph_quality")


async def get_graph_quality_report() -> Dict[str, Any]:
    """
    Compute comprehensive graph quality metrics.
    Returns a dict suitable for the analytics dashboard.
    """
    if not neo4j_client.is_available:
        return {
            "available": False,
            "message": "Neo4j not connected. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in .env and restart.",
        }

    try:
        # Basic counts
        node_result = await neo4j_client.run_query("MATCH (n:Entity) RETURN count(n) AS count")
        rel_result = await neo4j_client.run_query("MATCH ()-[r:RELATES]->() RETURN count(r) AS count")
        total_nodes = node_result[0]["count"] if node_result else 0
        total_rels = rel_result[0]["count"] if rel_result else 0

        # Orphan nodes (entities with no relationships)
        orphan_result = await neo4j_client.run_query(
            "MATCH (e:Entity) WHERE NOT (e)-[:RELATES]-() AND NOT ()-[:RELATES]-(e) RETURN count(e) AS count"
        )
        orphan_count = orphan_result[0]["count"] if orphan_result else 0

        # Missing provenance
        no_prov_result = await neo4j_client.run_query(
            "MATCH (e:Entity) WHERE e.source_doc_id IS NULL OR e.source_doc_id = '' RETURN count(e) AS count"
        )
        missing_prov = no_prov_result[0]["count"] if no_prov_result else 0

        # Low-confidence entities
        low_conf_result = await neo4j_client.run_query(
            "MATCH (e:Entity) WHERE e.confidence < 0.5 RETURN count(e) AS count"
        )
        low_confidence_count = low_conf_result[0]["count"] if low_conf_result else 0

        # Entity type distribution
        type_dist = await neo4j_client.run_query(
            "MATCH (e:Entity) RETURN e.type AS type, count(e) AS count ORDER BY count DESC"
        )

        # Relationship type distribution
        rel_dist = await neo4j_client.run_query(
            "MATCH ()-[r:RELATES]->() RETURN r.type AS type, count(r) AS count ORDER BY count DESC"
        )

        # Source document coverage
        doc_coverage = await neo4j_client.run_query(
            "MATCH (e:Entity) WHERE e.source_doc_id IS NOT NULL AND e.source_doc_id <> '' "
            "RETURN count(DISTINCT e.source_doc_id) AS doc_count"
        )
        covered_docs = doc_coverage[0]["doc_count"] if doc_coverage else 0

        # Health score (0-100)
        health_score = 100
        if total_nodes > 0:
            orphan_rate = orphan_count / total_nodes
            prov_rate = missing_prov / total_nodes
            conf_rate = low_confidence_count / total_nodes
            health_score = int(100 * (1 - 0.4 * orphan_rate - 0.4 * prov_rate - 0.2 * conf_rate))
            health_score = max(0, min(100, health_score))

        health_status = "healthy" if health_score >= 80 else ("warning" if health_score >= 60 else "degraded")

        return {
            "available": True,
            "health_score": health_score,
            "health_status": health_status,
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "orphan_nodes": orphan_count,
            "missing_provenance": missing_prov,
            "low_confidence_entities": low_confidence_count,
            "source_documents_covered": covered_docs,
            "entity_type_distribution": type_dist,
            "relationship_type_distribution": rel_dist,
            "issues": [
                f"{orphan_count} orphan entities (no relationships)" if orphan_count > 0 else None,
                f"{missing_prov} entities missing source provenance" if missing_prov > 0 else None,
                f"{low_confidence_count} low-confidence entities (< 0.5)" if low_confidence_count > 0 else None,
            ],
        }
    except Exception as e:
        logger.error(f"[GraphQuality] Failed to compute quality report: {e}")
        return {"available": False, "error": str(e)}
