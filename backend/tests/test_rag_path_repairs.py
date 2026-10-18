from unittest.mock import AsyncMock

import pytest

from app.retrieval.bm25_index import BM25IndexManager, _BM25Index
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.vector_store import VectorStore


@pytest.mark.anyio
async def test_incremental_bm25_update_keeps_searchable_chunk_text():
    manager = BM25IndexManager()
    user_id = "rag-repair-bm25-user"
    manager._indexes[user_id] = _BM25Index.build(
        ["An unrelated project note"],
        [{"user_id": user_id, "document_id": "old-doc", "chunk_index": 0}],
    )

    try:
        new_text = "The project uses hybrid retrieval with BM25 and dense semantic vectors."
        await manager.add_chunks(
            user_id,
            [new_text],
            [{"user_id": user_id, "document_id": "new-doc", "chunk_index": 0}],
        )

        results = await manager.query(user_id, "dense semantic vectors", top_k=5)
        assert results
        assert results[0]["text"] == new_text
        assert results[0]["meta"]["document_id"] == "new-doc"
    finally:
        manager.invalidate(user_id)


@pytest.mark.anyio
async def test_incremental_bm25_update_is_idempotent_for_concurrent_uploads():
    manager = BM25IndexManager()
    user_id = "rag-repair-bm25-concurrent-user"
    first_text = "Shared first uploaded passage about vector search."
    second_text = "Shared second uploaded passage about keyword search."
    first_meta = {"user_id": user_id, "document_id": "same-doc", "chunk_index": 0}
    second_meta = {"user_id": user_id, "document_id": "same-doc", "chunk_index": 1}
    manager._indexes[user_id] = _BM25Index.build([first_text], [first_meta])

    try:
        await manager.add_chunks(user_id, [first_text, second_text], [first_meta, second_meta])

        index = manager._indexes[user_id]
        assert index.size == 2
        assert index.corpus_texts == [first_text, second_text]
        results = await manager.query(user_id, "keyword search", top_k=5)
        assert len(results) == 2
        assert sum(result["meta"]["chunk_index"] == 1 for result in results) == 1
    finally:
        manager.invalidate(user_id)


@pytest.mark.anyio
async def test_lexical_reranker_reorders_hybrid_candidates_without_optional_model():
    reranker = CrossEncoderReranker()
    reranker._loaded = True
    reranker._model = None
    chunks = [
        {"content": "This section covers travel reimbursement policy.", "chunk_id": 1},
        {"content": "BM25 and semantic vectors are fused, then relevant passages are reranked.", "chunk_id": 2},
    ]

    result = await reranker.rerank("BM25 semantic vectors reranked", chunks)

    assert result[0]["chunk_id"] == 2
    assert result[0]["reranker_method"] == "lexical_fallback"
    assert "rerank_score" in result[0]


@pytest.mark.anyio
async def test_rag_agent_search_adapter_runs_hybrid_retrieval_then_reranking():
    store = object.__new__(VectorStore)
    retrieved = [
        {"content": "retrieved text", "filename": "guide.txt", "confidence": 0.8},
    ]
    reranked = [
        {**retrieved[0], "reranker_method": "lexical_fallback", "rerank_score": 1.2},
    ]
    store.query_relevant_chunks = AsyncMock(return_value=retrieved)
    store.rerank_chunks = AsyncMock(return_value=reranked)

    result = await VectorStore.search(
        store,
        query="find the guide",
        user_id="rag-repair-search-user",
        top_k=1,
        api_key="temporary-google-key",
    )

    assert result == reranked
    store.query_relevant_chunks.assert_awaited_once_with(
        user_id="rag-repair-search-user",
        query="find the guide",
        k=20,
        api_key="temporary-google-key",
    )
    store.rerank_chunks.assert_awaited_once()


def test_context_compression_preserves_reranked_order():
    chunks = [
        {"content": "Top reranked evidence passage.", "confidence": 0.45},
        {"content": "Lower reranked evidence passage.", "confidence": 0.98},
    ]

    compressed = VectorStore.compress_context(chunks)

    assert compressed == chunks
