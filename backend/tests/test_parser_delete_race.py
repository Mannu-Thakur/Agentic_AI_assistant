"""Regression coverage for deleting documents during background ingestion."""

from unittest.mock import AsyncMock

import pytest

from app.services import parser_service


@pytest.mark.asyncio
async def test_ingestion_removes_chunks_if_document_is_deleted_during_indexing(
    monkeypatch, tmp_path
):
    document_id = "deleted-during-ingestion"
    exists = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(parser_service.ParserService, "_document_exists", exists)
    monkeypatch.setattr(
        parser_service.ParserService,
        "_set_ingestion_progress",
        AsyncMock(),
    )
    monkeypatch.setattr(
        parser_service.ParserService,
        "extract_text",
        lambda *_args: "Small document content for the ingestion race test.",
    )
    monkeypatch.setattr(
        parser_service.ParserService,
        "split_text",
        lambda _text, metadata: [
            {"content": "Small document content", **metadata, "chunk_index": 0}
        ],
    )

    class FakeVectorStore:
        def __init__(self):
            self.deleted = []
            self.added = False

        async def delete_document_chunks(self, doc_id, user_id=""):
            self.deleted.append((doc_id, user_id))

        async def add_document_chunks(self, **_kwargs):
            self.added = True

    store = FakeVectorStore()
    monkeypatch.setattr(parser_service, "VectorStore", lambda: store)

    await parser_service.ParserService.process_document_ingestion(
        document_id=document_id,
        user_id="audit-user",
        file_path=str(tmp_path / "notes.txt"),
        filename="notes.txt",
        file_type="text/plain",
    )

    assert store.added is True
    assert store.deleted == [
        (document_id, ""),
        (document_id, "audit-user"),
    ]
    assert exists.await_count == 2
