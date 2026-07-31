"""
app/memory/memory_store.py — Vector Store for Semantic User Memory Retrieval.

Indexes user memory items (facts, preferences, goals, project context) into ChromaDB
under the 'user_memories' collection. Allows semantic vector similarity search
for memory retrieval during context assembly.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import chromadb
from app.core.config import settings
from app.embeddings.embedding_service import EmbeddingService

logger = logging.getLogger("app.memory.memory_store")


class MemoryVectorStore:
    _instance = None
    _lock = None

    def __new__(cls, *args, **kwargs):
        import threading
        if cls._lock is None:
            cls._lock = threading.Lock()
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
                cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        os.makedirs(settings.VECTOR_DB_DIR, exist_ok=True)
        self.client = chromadb.PersistentClient(path=settings.VECTOR_DB_DIR)

    def get_collection(self, name: str = "user_memories"):
        return self.client.get_or_create_collection(name=name)

    async def add_memory_item(
        self,
        memory_id: str,
        user_id: str,
        category: str,
        content: str,
        importance_score: int = 5,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """Indexes a memory item into ChromaDB for vector retrieval."""
        if not content.strip():
            return

        collection = self.get_collection()
        embedding = await EmbeddingService.get_embedding(content)

        metadata: Dict[str, Any] = {
            "memory_id":        memory_id,
            "user_id":          user_id,
            "category":         category,
            "importance_score": importance_score,
            "project_id":       project_id or "",
            "session_id":       session_id or "",
        }

        collection.upsert(
            ids=[f"mem_{memory_id}"],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[content],
        )
        logger.info(f"[MemoryVectorStore] Indexed memory {memory_id} for user {user_id} ({category})")

    async def search_memories(
        self,
        user_id: str,
        query: str,
        k: int = 5,
        category_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Performs semantic vector search against user memories in ChromaDB.
        Filters strictly by user_id for multi-tenant isolation.
        """
        if not query.strip():
            return []

        collection = self.get_collection()
        query_embedding = await EmbeddingService.get_embedding(query)

        where_filter: Dict[str, Any] = {"user_id": user_id}
        if category_filter:
            where_filter = {
                "$and": [
                    {"user_id": user_id},
                    {"category": category_filter},
                ]
            }

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where_filter,
            )
        except Exception as exc:
            logger.error(f"[MemoryVectorStore] Search failed: {exc}")
            return []

        if not (results and results.get("documents") and results["documents"][0]):
            return []

        docs = results["documents"][0]
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

        memories: List[Dict[str, Any]] = []
        for doc, meta, dist in zip(docs, metas, distances):
            confidence = round(max(0.0, 1.0 - float(dist)), 3)
            memories.append({
                "type":             "memory",
                "id":               meta.get("memory_id"),
                "category":         meta.get("category", "fact"),
                "content":          doc,
                "importance_score": meta.get("importance_score", 5),
                "confidence":       confidence,
                "distance":         float(dist),
            })

        return memories

    async def delete_memory_item(self, memory_id: str):
        """Deletes a memory item from ChromaDB."""
        collection = self.get_collection()
        try:
            collection.delete(ids=[f"mem_{memory_id}"])
            logger.info(f"[MemoryVectorStore] Deleted memory {memory_id} from vector store")
        except Exception as exc:
            logger.warning(f"[MemoryVectorStore] Failed to delete memory {memory_id}: {exc}")
