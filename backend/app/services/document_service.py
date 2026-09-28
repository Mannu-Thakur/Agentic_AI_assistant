import os
import logging
from typing import List, Optional
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document
from app.retrieval.vector_store import VectorStore
from app.agent.doc_signals import invalidate_user_signals

logger = logging.getLogger(__name__)

class DocumentService:
    @staticmethod
    async def get_user_documents(db: AsyncSession, user_id: str, chat_id: Optional[str] = None) -> List[Document]:
        """
        Retrieves all documents owned by a specific user, optionally filtered by chat_id.
        """
        from sqlalchemy import or_
        from datetime import datetime, timezone
        query = select(Document).where(Document.user_id == user_id)
        if chat_id:
            query = query.where(or_(Document.chat_id == chat_id, Document.chat_id.is_(None)))
        query = query.order_by(desc(Document.uploaded_at))
        result = await db.execute(query)
        docs = list(result.scalars().all())

        # Auto-heal: If any document has been in 'processing' for longer than
        # PROCESSING_TIMEOUT_SECONDS (default 600s, configurable via settings),
        # it was interrupted by server crash/reload/worker timeout. Mark it as 'failed'
        # so the client receives a non-spinning state and shows the Retry button.
        from app.core.config import settings as _settings
        PROCESSING_TIMEOUT_SECONDS = int(getattr(_settings, 'DOCUMENT_PROCESSING_TIMEOUT', 600))
        now = datetime.now(timezone.utc)
        has_auto_healed = False
        for doc in docs:
            if doc.status == "processing" and doc.uploaded_at:
                up_time = doc.uploaded_at
                if up_time.tzinfo is None:
                    up_time = up_time.replace(tzinfo=timezone.utc)
                if (now - up_time).total_seconds() > PROCESSING_TIMEOUT_SECONDS:
                    doc.status = "failed"
                    doc.error_message = "Indexing timed out on server. Click Retry to re-index."
                    has_auto_healed = True

        if has_auto_healed:
            try:
                await db.commit()
            except Exception as e:
                logger.warning(f"[DocumentService] Failed to commit auto-healed document statuses: {e}")

        return docs

    @staticmethod
    async def create_document(
        db: AsyncSession,
        user_id: str,
        filename: str,
        file_type: str,
        storage_path: str,
        size_bytes: int,
        chat_id: Optional[str] = None
    ) -> Document:
        """
        Registers a new document with 'processing' status in the database.
        """
        doc = Document(
            user_id=user_id,
            chat_id=chat_id,
            filename=filename,
            file_type=file_type,
            storage_path=storage_path,
            size_bytes=size_bytes,
            status="processing"
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        # Invalidate routing signal cache so next query picks up this new filename
        invalidate_user_signals(user_id)
        return doc

    @staticmethod
    async def get_document_by_id(db: AsyncSession, doc_id: str, user_id: str) -> Optional[Document]:
        """
        Fetches a single document by ID, validating ownership.
        """
        result = await db.execute(
            select(Document).where(Document.id == doc_id, Document.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_document(db: AsyncSession, doc_id: str, user_id: str) -> bool:
        """
        Deletes a document from SQL, local storage, and ChromaDB.
        """
        doc = await DocumentService.get_document_by_id(db, doc_id, user_id)
        if not doc:
            return False

        storage_path = doc.storage_path

        # 1. Remove relational database entry first — DB is clean even if vector/file cleanup fails
        await db.delete(doc)
        await db.commit()

        # 2. Clean up vectorized chunks in ChromaDB and invalidate user BM25 index
        try:
            vector_store = VectorStore()
            await vector_store.delete_document_chunks(doc_id, user_id=user_id)
        except Exception as e:
            logger.error(f"Failed to delete ChromaDB chunks for document {doc_id}: {str(e)}")

        # 3. Clean up physical file on disk last
        if storage_path and os.path.exists(storage_path):
            try:
                os.remove(storage_path)
            except Exception as e:
                logger.error(f"Failed to delete file {storage_path} from disk: {str(e)}")

        # Invalidate routing signal cache so deleted filename is no longer a signal
        invalidate_user_signals(user_id)
        return True
