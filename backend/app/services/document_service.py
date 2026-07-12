import os
import logging
from typing import List, Optional
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document
from app.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)

class DocumentService:
    @staticmethod
    async def get_user_documents(db: AsyncSession, user_id: str) -> List[Document]:
        """
        Retrieves all documents owned by a specific user.
        """
        result = await db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(desc(Document.uploaded_at))
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_document(
        db: AsyncSession,
        user_id: str,
        filename: str,
        file_type: str,
        storage_path: str,
        size_bytes: int
    ) -> Document:
        """
        Registers a new document with 'processing' status in the database.
        """
        doc = Document(
            user_id=user_id,
            filename=filename,
            file_type=file_type,
            storage_path=storage_path,
            size_bytes=size_bytes,
            status="processing"
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
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

        # 2. Clean up vectorized chunks in ChromaDB
        try:
            vector_store = VectorStore()
            await vector_store.delete_document_chunks(doc.id)
        except Exception as e:
            logger.error(f"Failed to delete ChromaDB chunks for document {doc.id}: {str(e)}")

        # 3. Remove relational entry
        await db.delete(doc)
        await db.commit()
        return True
