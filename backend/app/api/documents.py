import os
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.auth import get_current_user
from app.schemas.auth import UserOut
from app.schemas.document import DocumentOut
from app.services.document_service import DocumentService
from app.services.parser_service import ParserService
from app.core.config import settings

router = APIRouter(prefix="/documents", tags=["RAG Documents"])

@router.get("", response_model=List[DocumentOut])
async def list_documents(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Lists all RAG documents uploaded by the authenticated user.
    """
    return await DocumentService.get_user_documents(db, current_user.id)

@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads a document (PDF, Word, Excel, PowerPoint, Text, Image),
    registers it in SQL DB, and kicks off async background parsing and indexing.
    """
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    allowed_extensions = {
        ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
        ".txt", ".md", ".json", ".csv",
        ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff"
    }

    # 1. Enforce file extensions
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not supported. Supported: {', '.join(allowed_extensions)}"
        )

    # 2. Read content to check file size limits
    contents = await file.read()
    size_bytes = len(contents)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum upload limit of {settings.MAX_UPLOAD_SIZE_MB}MB."
        )

    # Reset file read pointer
    await file.seek(0)

    # 3. Save physical file locally
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    unique_filename = f"{uuid.uuid4()}{ext}"
    storage_path = os.path.join(settings.UPLOAD_DIR, unique_filename)

    with open(storage_path, "wb") as f:
        f.write(contents)

    # 4. Create document entry
    file_type_cleaned = ext.lstrip(".") or "text"
    doc = await DocumentService.create_document(
        db=db,
        user_id=current_user.id,
        filename=filename,
        file_type=file_type_cleaned,
        storage_path=storage_path,
        size_bytes=size_bytes
    )

    # 5. Dispatch async background task to parse, chunk, embed, and index
    background_tasks.add_task(
        ParserService.process_document_ingestion,
        document_id=doc.id,
        user_id=current_user.id,
        file_path=storage_path,
        filename=filename,
        file_type=file_type_cleaned
    )

    return doc

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletes the document matching document_id from PostgreSQL/SQLite, ChromaDB, and local disk.
    """
    success = await DocumentService.delete_document(db, document_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or access denied."
        )
    return {"detail": "Document successfully deleted."}
