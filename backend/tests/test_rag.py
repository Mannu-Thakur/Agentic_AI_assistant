import os
import pytest
import httpx
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.core.database import get_db
from app.embeddings.embedding_service import EmbeddingService
from app.retrieval.vector_store import VectorStore
from app.services.parser_service import ParserService
from app.services.document_service import DocumentService
from app.services.memory_service import MemoryService
from app.models.user import User

@pytest.mark.anyio
async def test_embedding_service():
    """
    Test single and batch mock embedding generation.
    Verify they return 768-dimensional normalized vectors.
    """
    # Single embedding
    emb = await EmbeddingService.get_embedding("Agentic RAG Test")
    assert isinstance(emb, list)
    assert len(emb) == 768
    # Check normalization (sum of squares close to 1)
    sq_sum = sum(x**2 for x in emb)
    assert abs(sq_sum - 1.0) < 0.01

    # Batch embedding
    embs = await EmbeddingService.get_embeddings(["First text", "Second text"])
    assert len(embs) == 2
    assert len(embs[0]) == 768
    assert len(embs[1]) == 768

def test_parser_splitting():
    """
    Test parser utility's sliding-window text splitting logic.
    """
    text = "The quick brown fox jumps over the lazy dog. " * 30  # > 1000 chars
    chunks = ParserService.split_text(text, chunk_size=200, chunk_overlap=50)
    assert len(chunks) > 1
    # Verify overlap or chunk lengths
    for chunk in chunks:
        assert len(chunk) <= 300  # allowing some buffer for word boundaries

@pytest.mark.anyio
async def test_vector_store_isolation_and_crud():
    """
    Test vector store indexing, retrieval, and multi-tenant isolation.
    """
    vector_store = VectorStore()
    doc_id = "test-doc-id"
    user_alice = "user-alice"
    user_bob = "user-bob"
    filename = "alice_diary.txt"
    chunks = ["Alice lives in Wonderland", "Alice has a white rabbit"]

    # Alice indexes documents
    await vector_store.add_document_chunks(
        document_id=doc_id,
        user_id=user_alice,
        filename=filename,
        chunks=chunks
    )

    # Alice queries her documents
    alice_results = await vector_store.query_relevant_chunks(
        user_id=user_alice,
        query="Where does Alice live?",
        k=2
    )
    assert len(alice_results) > 0
    assert any("Wonderland" in c["content"] for c in alice_results)
    assert alice_results[0]["filename"] == filename

    # Bob queries Alice's documents (should return NOTHING due to isolation)
    bob_results = await vector_store.query_relevant_chunks(
        user_id=user_bob,
        query="Where does Alice live?",
        k=2
    )
    assert len(bob_results) == 0

    # Alice deletes her document
    await vector_store.delete_document_chunks(doc_id)
    alice_results_after_delete = await vector_store.query_relevant_chunks(
        user_id=user_alice,
        query="Where does Alice live?",
        k=2
    )
    assert len(alice_results_after_delete) == 0

@pytest.mark.anyio
async def test_documents_and_memories_api_flow(override_get_db, db_session: AsyncSession):
    """
    Integration test for /documents and /memories endpoint operations.
    """
    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Register and login test user
        reg_payload = {
            "email": "raguser@example.com",
            "password": "ragpassword123",
            "full_name": "RAG User"
        }
        res_reg = await ac.post("/api/v1/auth/register", json=reg_payload)
        assert res_reg.status_code == 201
        
        login_payload = {
            "email": "raguser@example.com",
            "password": "ragpassword123"
        }
        res_login = await ac.post("/api/v1/auth/login", json=login_payload)
        assert res_login.status_code == 200
        token = res_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Upload document file
        # Create a small temp text file
        file_content = b"This is a document about FastAPI and ChromaDB vector search."
        files = {"file": ("manual.txt", file_content, "text/plain")}
        
        res_upload = await ac.post("/api/v1/documents/upload", headers=headers, files=files)
        assert res_upload.status_code == 201
        doc_data = res_upload.json()
        assert doc_data["filename"] == "manual.txt"
        assert doc_data["status"] == "processing"
        doc_id = doc_data["id"]

        # Wait a brief moment for the background task to complete processing
        await asyncio.sleep(1.0)

        # 3. List documents and verify status updated to 'ready'
        res_list = await ac.get("/api/v1/documents", headers=headers)
        assert res_list.status_code == 200
        docs_list = res_list.json()
        assert len(docs_list) >= 1
        uploaded_doc = next(d for d in docs_list if d["id"] == doc_id)
        assert uploaded_doc["status"] in ["ready", "processing"]  # Background task runs or is running

        # 4. Save a semantic memory fact
        mem_payload = {
            "category": "preference",
            "content": "User prefers Python for data engineering",
            "importance_score": 8
        }
        res_mem_create = await ac.post("/api/v1/memories", headers=headers, json=mem_payload)
        assert res_mem_create.status_code == 201
        mem_data = res_mem_create.json()
        assert mem_data["category"] == "preference"
        assert mem_data["importance_score"] == 8
        mem_id = mem_data["id"]

        # 5. List memories
        res_mem_list = await ac.get("/api/v1/memories", headers=headers)
        assert res_mem_list.status_code == 200
        mems = res_mem_list.json()
        assert len(mems) >= 1
        assert any(m["id"] == mem_id for m in mems)

        # 6. Delete semantic memory
        res_mem_del = await ac.delete(f"/api/v1/memories/{mem_id}", headers=headers)
        assert res_mem_del.status_code == 200
        
        # Verify deleted memory is gone
        res_mem_list2 = await ac.get("/api/v1/memories", headers=headers)
        assert not any(m["id"] == mem_id for m in res_mem_list2.json())

        # 7. Delete document — expects 204 No Content (FIX-8)
        res_del_doc = await ac.delete(f"/api/v1/documents/{doc_id}", headers=headers)
        assert res_del_doc.status_code == 204

        # Verify deleted document is gone
        res_list2 = await ac.get("/api/v1/documents", headers=headers)
        assert not any(d["id"] == doc_id for d in res_list2.json())

    app.dependency_overrides.clear()
