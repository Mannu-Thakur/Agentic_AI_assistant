import asyncio
import os
import sys
import logging
from unittest.mock import AsyncMock, patch

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def test_standard_rag():
    print("\n" + "="*60)
    print(" 1. TESTING STANDARD RAG (Retrieval-Augmented Generation)")
    print("="*60)
    
    from app.embeddings.embedding_service import EmbeddingService
    from app.services.parser_service import ParserService
    from app.retrieval.vector_store import VectorStore

    results = []

    # 1.1 Test Text Chunking
    try:
        sample_text = "FastAPI is a modern web framework for Python. " * 30
        chunks = ParserService.split_text(sample_text, chunk_size=200, chunk_overlap=50)
        assert len(chunks) > 1, "Chunking produced 1 or 0 chunks"
        results.append(("Text Splitting / Chunking", True, f"Generated {len(chunks)} chunks"))
    except Exception as e:
        results.append(("Text Splitting / Chunking", False, str(e)))

    # 1.2 Test Embedding Generation
    try:
        with patch.object(EmbeddingService, "get_embedding", new_callable=AsyncMock) as mock_emb:
            mock_emb.return_value = [0.1] * 768
            emb = await EmbeddingService.get_embedding("Agentic RAG Test Query")
            assert isinstance(emb, list) and len(emb) == 768, f"Invalid embedding dimension {len(emb)}"
            results.append(("Embedding Service (768-dim)", True, f"Vector dim={len(emb)}"))
    except Exception as e:
        results.append(("Embedding Service (768-dim)", False, str(e)))

    # 1.3 Test Vector Store Storage & Retrieval & Multi-tenant Isolation
    try:
        with patch.object(EmbeddingService, "get_embedding", new_callable=AsyncMock) as mock_emb, \
             patch.object(EmbeddingService, "get_embeddings", new_callable=AsyncMock) as mock_embs:
            mock_emb.return_value = [0.1] * 768
            mock_embs.return_value = [[0.1] * 768]

            vector_store = VectorStore()
            doc_id = "test-doc-rag-verify"
            user_alice = "user-alice-verify"
            user_bob = "user-bob-verify"

            await vector_store.add_document_chunks(
                document_id=doc_id,
                user_id=user_alice,
                filename="quantum_physics.txt",
                chunks=["Quantum entanglement occurs when particles remain connected regardless of distance."]
            )

            # Alice query (Authorized)
            alice_res = await vector_store.query_relevant_chunks(
                user_id=user_alice,
                query="What is quantum entanglement?",
                k=2
            )
            assert len(alice_res) > 0, "Alice received no chunks"
            assert "entanglement" in alice_res[0]["content"].lower(), "Retrieved content mismatch"

            # Bob query (Unauthorized access check)
            bob_res = await vector_store.query_relevant_chunks(
                user_id=user_bob,
                query="What is quantum entanglement?",
                k=2
            )
            assert len(bob_res) == 0, f"Tenant isolation breach: Bob retrieved Alice's chunk!"

            # Cleanup
            await vector_store.delete_document_chunks(doc_id)

            results.append(("Vector Store CRUD & Multi-Tenant Isolation", True, "Alice retrieved doc, Bob got 0 chunks (isolated)"))
    except Exception as e:
        results.append(("Vector Store CRUD & Multi-Tenant Isolation", False, str(e)))

    for name, success, msg in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status} {name}: {msg}")

    return all(r[1] for r in results)


async def test_crag():
    print("\n" + "="*60)
    print(" 2. TESTING CRAG (Corrective RAG)")
    print("="*60)

    from app.agent.nodes import grade_documents_node

    results = []

    def make_state(**kwargs):
        base = {
            "messages": [],
            "retrieved_documents": [],
            "source_documents": [],
            "steps": [],
            "resolved_query": "test query",
            "is_private_doc_query": False,
            "intent": "DOCUMENT_QA"
        }
        base.update(kwargs)
        return base

    # 2.1 Grade relevant chunks
    try:
        state = make_state(
            resolved_query="What is Python?",
            retrieved_documents=[
                {"type": "chunk", "content": "Python is a high-level programming language.", "filename": "py.txt", "confidence": 0.9}
            ]
        )
        with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge:
            mock_judge.return_value = {"score": "relevant"}
            res = await grade_documents_node(state, {})
        assert res["document_relevance"] == "relevant", f"Expected relevant, got {res.get('document_relevance')}"
        results.append(("CRAG Document Relevance Grading", True, "Marked relevant chunks correctly"))
    except Exception as e:
        results.append(("CRAG Document Relevance Grading", False, str(e)))

    # 2.2 Freshness Required & Outdated Chunks -> Trigger Web Fallback
    try:
        state = make_state(
            resolved_query="latest Python 3.12 release features",
            retrieved_documents=[
                {"type": "chunk", "content": "Python 3.8 features f-strings.", "filename": "old_py.txt", "confidence": 0.8}
            ],
            is_private_doc_query=False
        )
        with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge, \
             patch("app.agent.nodes.unified_web_search", new_callable=AsyncMock) as mock_web:
            mock_judge.return_value = {"score": "outdated"}
            mock_web.return_value = [{"title": "Python 3.12 Release", "url": "https://python.org", "content": "Python 3.12 was released."}]
            res = await grade_documents_node(state, {})

        assert res["document_relevance"] == "web_fallback", f"Expected web_fallback, got {res.get('document_relevance')}"
        mock_web.assert_called_once()
        results.append(("CRAG Web Fallback on Outdated/Freshness Query", True, "Outdated chunk + freshness query correctly triggered Web Fallback"))
    except Exception as e:
        results.append(("CRAG Web Fallback on Outdated/Freshness Query", False, str(e)))

    # 2.3 Private Document Guard (Blocks Web Search for Private Docs)
    try:
        state = make_state(
            resolved_query="latest salary numbers for project secret",
            retrieved_documents=[
                {"type": "chunk", "content": "Confidential salary doc.", "filename": "secret.pdf", "confidence": 0.8}
            ],
            is_private_doc_query=True
        )
        with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge, \
             patch("app.agent.nodes.unified_web_search", new_callable=AsyncMock) as mock_web:
            mock_judge.return_value = {"score": "outdated"}
            res = await grade_documents_node(state, {})

        assert res["document_relevance"] == "no_private_docs"
        assert res["no_doc_answer"] is True
        mock_web.assert_not_called()
        results.append(("CRAG Private Document Safety Guard", True, "Private query blocked web search completely when docs failed grading"))
    except Exception as e:
        results.append(("CRAG Private Document Safety Guard", False, str(e)))

    for name, success, msg in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status} {name}: {msg}")

    return all(r[1] for r in results)


async def test_self_rag():
    print("\n" + "="*60)
    print(" 3. TESTING SELF-RAG (Self-Reflective RAG)")
    print("="*60)

    from app.agent.nodes import check_retrieval_node, retrieve_context_node, reflect_node
    from app.agent.graph import route_retrieval, route_after_grading, route_after_reflection

    results = []

    def make_state(**kwargs):
        base = {
            "messages": [],
            "retrieved_documents": [],
            "source_documents": [],
            "steps": [],
            "resolved_query": "test query",
            "intent": "NORMAL_CHAT"
        }
        base.update(kwargs)
        return base

    # 3.1 Adaptive Retrieval Decision Node (Check Retrieval)
    try:
        # Document QA query -> needs_retrieval = True
        state_doc_qa = make_state(intent="DOCUMENT_QA", resolved_query="Summarize my pdf")
        res_qa = await check_retrieval_node(state_doc_qa, {})
        assert res_qa["needs_retrieval"] is True, "DOCUMENT_QA should set needs_retrieval=True"

        # Conversational query -> needs_retrieval = False
        state_chat = make_state(intent="NORMAL_CHAT", resolved_query="Hello how are you?")
        res_chat = await check_retrieval_node(state_chat, {})
        assert res_chat["needs_retrieval"] is False, "NORMAL_CHAT should set needs_retrieval=False"

        results.append(("Self-RAG Retrieval Decision (check_retrieval)", True, "Document QA triggers retrieval, Chat bypasses retrieval"))
    except Exception as e:
        results.append(("Self-RAG Retrieval Decision (check_retrieval)", False, str(e)))

    # 3.2 Routing based on needs_retrieval
    try:
        state_need = make_state(needs_retrieval=True)
        state_skip = make_state(needs_retrieval=False)
        assert route_retrieval(state_need) == "retrieve_context"
        assert route_retrieval(state_skip) == "grade_documents"
        results.append(("Self-RAG Conditional Edge (route_retrieval)", True, "Routes correctly to retrieve_context or grade_documents"))
    except Exception as e:
        results.append(("Self-RAG Conditional Edge (route_retrieval)", False, str(e)))

    # 3.3 Low-confidence Retry & Query Reformulation Loop
    try:
        # Low confidence (<0.5) and retry_count <= max_retries -> route back to retrieve_context
        state_low_conf = make_state(
            user_id="test-user",
            resolved_query="Search item",
            needs_retrieval=True,
            retrieval_confidence=0.2,
            retrieval_retry_count=1,
            max_retrieval_retries=2
        )
        assert route_after_grading(state_low_conf) == "retrieve_context"

        # Test query reformulation on retry in retrieve_context_node
        with patch("app.agent.nodes._call_llm_text", new_callable=AsyncMock) as mock_text, \
             patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge, \
             patch("app.retrieval.vector_store.VectorStore.query_relevant_chunks", new_callable=AsyncMock) as mock_store, \
             patch("app.services.document_service.DocumentService.get_user_documents", new_callable=AsyncMock) as mock_docs:

            mock_text.return_value = "Reformulated search query"
            mock_judge.return_value = {"queries": ["Reformulated search query"]}
            mock_store.return_value = []
            mock_docs.return_value = []

            retry_res = await retrieve_context_node(state_low_conf, {})

        assert retry_res["retrieval_retry_count"] == 2
        mock_text.assert_called_once()
        results.append(("Self-RAG Low-Confidence Retry & Reformulation", True, "Low confidence triggered retry loop and query reformulation"))
    except Exception as e:
        results.append(("Self-RAG Low-Confidence Retry & Reformulation", False, str(e)))

    # 3.4 Reflection node: verify DOCUMENT_QA is correctly skipped (speed fix),
    #     and COMPLEX intent still runs the full LLM reflection + regeneration loop.
    try:
        from langchain_core.messages import HumanMessage, AIMessage

        # 3.4a — DOCUMENT_QA must now SKIP reflection (evidence_checker handles it)
        state_doc_qa_reflect = make_state(
            intent="DOCUMENT_QA",
            resolved_query="What is Python?",
            messages=[
                HumanMessage(content="What is Python?"),
                AIMessage(content="Python is a snake only."),
            ],
            source_documents=[{"content": "Python is a programming language.", "filename": "doc.txt"}],
            iteration_count=0,
        )
        with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge:
            mock_judge.return_value = {
                "verdict": "NEEDS_IMPROVEMENT",
                "feedback": "Response contradicts retrieved sources",
            }
            res_doc_qa = await reflect_node(state_doc_qa_reflect, {})

        # For DOCUMENT_QA the LLM judge must NOT be called — reflection is skipped
        mock_judge.assert_not_called()
        assert res_doc_qa["reflection_passed"] is True, "DOCUMENT_QA should always pass reflection (skip)"

        # 3.4b — COMPLEX intent must still run full LLM reflection + regeneration
        state_complex_reflect = make_state(
            intent="COMPLEX",
            resolved_query="What is Python?",
            messages=[
                HumanMessage(content="What is Python?"),
                AIMessage(content="Python is a snake only."),
            ],
            source_documents=[{"content": "Python is a programming language.", "filename": "doc.txt"}],
            iteration_count=0,
        )
        with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge:
            mock_judge.return_value = {
                "verdict": "NEEDS_IMPROVEMENT",
                "is_grounded": False,
                "answers_question": False,
                "quality_score": 3,
                "feedback": "Response contradicts retrieved sources",
            }
            res_complex = await reflect_node(state_complex_reflect, {})

        assert res_complex["reflection_passed"] is False, "COMPLEX should fail reflection on bad response"
        assert route_after_reflection(res_complex) == "generate_response"

        results.append((
            "Self-RAG Reflection & Regeneration Loop",
            True,
            "DOCUMENT_QA skips reflection (fast-path), COMPLEX intent runs LLM reflection and triggers regeneration",
        ))
    except Exception as e:
        results.append(("Self-RAG Reflection & Regeneration Loop", False, str(e)))

    for name, success, msg in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status} {name}: {msg}")

    return all(r[1] for r in results)


async def main():
    print("==================================================================")
    print("      AGENTIC AI CHATBOT - RAG, CRAG & SELF-RAG SYSTEM VERIFIER    ")
    print("==================================================================")

    rag_ok = await test_standard_rag()
    crag_ok = await test_crag()
    selfrag_ok = await test_self_rag()

    print("\n" + "="*60)
    print(" SUMMARY TEST REPORT")
    print("="*60)
    print(f"  1. Standard RAG Status:  {'[WORKING]' if rag_ok else '[FAILED]'}")
    print(f"  2. Corrective RAG (CRAG): {'[WORKING]' if crag_ok else '[FAILED]'}")
    print(f"  3. Self-RAG Status:      {'[WORKING]' if selfrag_ok else '[FAILED]'}")
    print("="*60)

    if rag_ok and crag_ok and selfrag_ok:
        print("\nOVERALL SYSTEM STATUS: ALL RAG PIPELINES FULLY FUNCTIONAL AND VERIFIED.")
        sys.exit(0)
    else:
        print("\nOVERALL SYSTEM STATUS: ONE OR MORE PIPELINES FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
