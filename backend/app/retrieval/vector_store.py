import os
import chromadb
from typing import List, Dict, Any
from app.core.config import settings
from app.embeddings.embedding_service import EmbeddingService

class VectorStore:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(VectorStore, cls).__new__(cls, *args, **kwargs)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        """
        Initializes the persistent ChromaDB client using the configured storage path.
        """
        os.makedirs(settings.VECTOR_DB_DIR, exist_ok=True)
        self.client = chromadb.PersistentClient(path=settings.VECTOR_DB_DIR)

    def get_collection(self, name: str = "document_chunks"):
        """
        Retrieves or creates a ChromaDB collection.
        We do not supply a default embedding function here because we handle embeddings
        manually using EmbeddingService.
        """
        return self.client.get_or_create_collection(name=name)

    async def add_document_chunks(
        self,
        document_id: str,
        user_id: str,
        filename: str,
        chunks: List[str]
    ):
        """
        Generates embeddings for chunks in batch and adds them to ChromaDB.
        """
        if not chunks:
            return

        collection = self.get_collection()

        # 1. Generate embeddings for all text chunks in batch
        embeddings = await EmbeddingService.get_embeddings(chunks)

        # 2. Construct structural lists for ChromaDB ingestion
        ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "document_id": document_id,
                "user_id": user_id,
                "filename": filename,
                "chunk_index": i
            }
            for i in range(len(chunks))
        ]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=chunks
        )

    async def delete_document_chunks(self, document_id: str):
        """
        Deletes all chunks belonging to a specific document.
        """
        collection = self.get_collection()
        collection.delete(where={"document_id": document_id})

    async def query_relevant_chunks(
        self,
        user_id: str,
        query: str,
        k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Queries ChromaDB for chunks relevant to the user query.
        Uses metadata filters to enforce multi-tenant isolation.
        """
        # 1. Generate embedding for query text
        query_embedding = await EmbeddingService.get_embedding(query)

        collection = self.get_collection()
        
        # 2. Query with user_id filter
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where={"user_id": user_id}
        )

        chunks = []
        if results and results["documents"] and results["documents"][0]:
            docs = results["documents"][0]
            metadatas = results["metadatas"][0] if results["metadatas"] else []
            distances = results["distances"][0] if results["distances"] else []

            for i in range(len(docs)):
                meta = metadatas[i] if i < len(metadatas) else {}
                dist = distances[i] if i < len(distances) else 0.0
                chunks.append({
                    "type": "chunk",
                    "content": docs[i],
                    "filename": meta.get("filename", "unknown"),
                    "document_id": meta.get("document_id"),
                    "chunk_index": meta.get("chunk_index"),
                    "distance": float(dist)
                })

        return chunks
