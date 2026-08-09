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
        query = select(Document).where(Document.user_id == user_id)
        if chat_id:
            query = query.where(or_(Document.chat_id == chat_id, Document.chat_id.is_(None)))
        query = query.order_by(desc(Document.uploaded_at))
        result = await db.execute(query)
        return list(result.scalars().all())

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

        # 1. Clean up physical file on disk
        if os.path.exists(doc.storage_path):
            try:
                os.remove(doc.storage_path)
            except Exception as e:
                logger.error(f"Failed to delete file {doc.storage_path} from disk: {str(e)}")

        # 2. Clean up vectorized chunks in ChromaDB and invalidate user BM25 index
        try:
            vector_store = VectorStore()
            await vector_store.delete_document_chunks(doc.id, user_id=user_id)
        except Exception as e:
            logger.error(f"Failed to delete ChromaDB chunks for document {doc.id}: {str(e)}")

        # 3. Remove relational entry
        await db.delete(doc)
        await db.commit()
        # Invalidate routing signal cache so deleted filename is no longer a signal
        invalidate_user_signals(user_id)
        return True
