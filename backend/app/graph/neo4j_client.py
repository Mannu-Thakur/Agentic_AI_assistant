"""
app/graph/neo4j_client.py — Async Neo4j client with graceful fallback.

When NEO4J_URI is not configured or Neo4j is unreachable, all operations
return empty results rather than raising errors. This ensures the existing
vector RAG pipeline is never disrupted by graph unavailability.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger("app.graph.neo4j_client")


class Neo4jClient:
    """Thread-safe async Neo4j client singleton."""

    _instance: Optional["Neo4jClient"] = None
    _driver = None
    _available: bool = False

    def __new__(cls) -> "Neo4jClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self) -> bool:
        """Attempt to connect to Neo4j. Returns True if successful."""
        if not settings.NEO4J_URI or not settings.NEO4J_PASSWORD:
            logger.info("[GraphRAG] NEO4J_URI or NEO4J_PASSWORD not configured — GraphRAG disabled.")
            self._available = False
            return False
        try:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            self._available = True
            logger.info(f"[GraphRAG] Connected to Neo4j at {settings.NEO4J_URI}")
            await self._ensure_schema()
            return True
        except Exception as e:
            logger.warning(f"[GraphRAG] Neo4j unavailable: {e} — falling back to vector-only RAG.")
            self._available = False
            if self._driver:
                try:
                    await self._driver.close()
                except Exception:
                    pass
            self._driver = None
            return False

    async def _ensure_schema(self) -> None:
        """Create Neo4j schema constraints and indexes for known entity types."""
        constraints = [
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
            "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
            "CREATE INDEX entity_doc IF NOT EXISTS FOR (e:Entity) ON (e.source_doc_id)",
        ]
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            for stmt in constraints:
                try:
                    await session.run(stmt)
                except Exception as e:
                    logger.debug(f"[GraphRAG] Schema statement skipped: {e}")

    @property
    def is_available(self) -> bool:
        return self._available and self._driver is not None

    async def run_query(
        self, cypher: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a read Cypher query. Returns [] if Neo4j unavailable."""
        if not self.is_available:
            return []
        try:
            async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
                result = await session.run(cypher, params or {})
                records = await result.data()
                return records
        except Exception as e:
            logger.warning(f"[GraphRAG] Query failed: {e}")
            return []

    async def run_write(
        self, cypher: str, params: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Execute a write Cypher query. Returns False if Neo4j unavailable."""
        if not self.is_available:
            return False
        try:
            async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
                await session.run(cypher, params or {})
                return True
        except Exception as e:
            logger.warning(f"[GraphRAG] Write failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver:
            try:
                await self._driver.close()
            except Exception:
                pass
            self._driver = None
            self._available = False

    async def get_stats(self) -> Dict[str, Any]:
        """Return basic graph statistics."""
        if not self.is_available:
            return {"available": False}
        try:
            node_count = await self.run_query("MATCH (n) RETURN count(n) AS count")
            rel_count = await self.run_query("MATCH ()-[r]->() RETURN count(r) AS count")
            entity_counts = await self.run_query(
                "MATCH (e:Entity) RETURN e.type AS type, count(e) AS count ORDER BY count DESC LIMIT 20"
            )
            return {
                "available": True,
                "total_nodes": node_count[0]["count"] if node_count else 0,
                "total_relationships": rel_count[0]["count"] if rel_count else 0,
                "entity_types": entity_counts,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}


# Global singleton instance
neo4j_client = Neo4jClient()
