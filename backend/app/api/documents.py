import asyncio
import logging
import os
import uuid
import re
import zipfile
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.api.auth import get_current_user
from app.schemas.auth import UserOut
from app.schemas.document import DocumentOut
from app.services.document_service import DocumentService
from app.services.parser_service import ParserService
from app.core.config import settings
from app.core.security import decrypt_api_key
from app.models.user import ApiKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["RAG Documents"])

ALLOWED_MIME_TYPES = {
    ".pdf":  ["application/pdf"],
    ".docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    ".doc":  ["application/msword"],
    ".xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    ".xls":  ["application/vnd.ms-excel"],
    ".pptx": ["application/vnd.openxmlformats-officedocument.presentationml.presentation"],
    ".ppt":  ["application/vnd.ms-powerpoint"],
    ".txt":  ["text/plain"],
    ".md":   ["text/markdown", "text/plain"],
    ".json": ["application/json", "text/plain"],
    ".csv":  ["text/csv", "application/csv", "text/plain"],
    ".png":  ["image/png"],
    ".jpg":  ["image/jpeg"],
    ".jpeg": ["image/jpeg"],
    ".bmp":  ["image/bmp", "image/x-ms-bmp"],
    ".gif":  ["image/gif"],
    ".tiff": ["image/tiff"],
    ".webp": ["image/webp"],
    ".heic": ["image/heic"],
    ".heif": ["image/heif"],
}

# ---------------------------------------------------------------------------
# Executable magic-byte signatures to reject
# ELF (Linux), PE/MZ (Windows), Mach-O (macOS), Java .class, shebangs
# ---------------------------------------------------------------------------
_EXECUTABLE_MAGIC: list[tuple[bytes, str]] = [
    (b"\x7fELF",          "ELF binary"),
    (b"MZ",               "PE/DOS executable"),
    (b"\xfe\xed\xfa\xce", "Mach-O 32-bit"),
    (b"\xfe\xed\xfa\xcf", "Mach-O 64-bit"),
    (b"\xce\xfa\xed\xfe", "Mach-O 32-bit (reversed)"),
    (b"\xcf\xfa\xed\xfe", "Mach-O 64-bit (reversed)"),
    (b"\xca\xfe\xba\xbe", "Java class / Mach-O FAT"),
    (b"#!/",              "shell/script shebang"),
    (b"#! /",             "shell/script shebang (space)"),
]

# ZIP-based file extensions (Office Open XML formats are ZIP archives)
_ZIP_BASED_EXTS = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"}

# ZIP bomb limits
_ZIP_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024   # 200 MB decompressed cap
_ZIP_MAX_RATIO = 100                               # max compressed:uncompressed ratio

# Text-based extensions eligible for prompt-injection scanning
_TEXT_EXTS = {".txt", ".md", ".json", ".csv"}

# Known prompt-injection patterns (case-insensitive)
_PROMPT_INJECTION_PATTERNS: list[str] = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "forget your instructions",
    "new instructions:",
    "act as jailbreak",
    "dan mode",
    "developer mode on",
    "[system]",
    "<!--system",
    "<|system|>",
    "role: system",
]


# ---------------------------------------------------------------------------
# Security scan helpers
# ---------------------------------------------------------------------------

def scan_file_for_malware(contents: bytes) -> bool:
    """Returns False (reject) if the EICAR test signature is found."""
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    return eicar not in contents


def _check_executable_magic(contents: bytes) -> str | None:
    """Returns a description if the file starts with a known executable magic sequence."""
    for magic, description in _EXECUTABLE_MAGIC:
        if contents[: len(magic)] == magic:
            return description
    return None


def _check_zip_bomb(contents: bytes) -> str | None:
    """
    Inspects ZIP-based archives for bomb conditions.
    Returns an error message string if suspicious, else None.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            compressed_size = len(contents)
            if total_uncompressed > _ZIP_MAX_UNCOMPRESSED_BYTES:
                mb = total_uncompressed // (1024 * 1024)
                limit_mb = _ZIP_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)
                return f"Archive decompresses to {mb} MB which exceeds the {limit_mb} MB limit."
            if compressed_size > 0:
                ratio = total_uncompressed / compressed_size
                if ratio > _ZIP_MAX_RATIO:
                    return (
                        f"Compression ratio {int(ratio)}:1 exceeds the maximum "
                        f"allowed {_ZIP_MAX_RATIO}:1 (possible ZIP bomb)."
                    )
    except zipfile.BadZipFile:
        pass  # Not a ZIP — skip silently
    return None


def _check_prompt_injection(contents: bytes) -> str | None:
    """
    Scans decoded text for known prompt-injection phrases.
    Returns the matched pattern or None if clean.
    """
    try:
        text = contents.decode("utf-8", errors="ignore").lower()
    except Exception:
        return None
    for pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern in text:
            return pattern
    return None


async def _scan_with_clamav(contents: bytes) -> tuple[bool, str]:
    """
    Stream file bytes to ClamAV daemon via TCP INSTREAM protocol.

    Returns (is_clean, message).
    Fails OPEN (returns True) when ClamAV is not configured or unreachable,
    so the upload is never blocked by a missing/offline antivirus daemon.
    """
    if not settings.CLAMAV_HOST:
        return True, "skipped"

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.CLAMAV_HOST, settings.CLAMAV_PORT),
            timeout=5.0,
        )
        # INSTREAM protocol: "zINSTREAM\0" | 4-byte big-endian length | data | 4-byte zero
        writer.write(b"zINSTREAM\0")
        writer.write(len(contents).to_bytes(4, "big"))
        writer.write(contents)
        writer.write((0).to_bytes(4, "big"))
        await writer.drain()

        response = await asyncio.wait_for(reader.read(100), timeout=10.0)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

        result = response.decode("utf-8", errors="ignore").strip().rstrip("\x00")
        logger.info(f"[ClamAV] scan result: {result!r}")

        if "FOUND" in result:
            virus = result.split(":")[1].strip().replace(" FOUND", "") if ":" in result else "UNKNOWN"
            return False, f"Malware detected: {virus}"
        return True, "clean"

    except asyncio.TimeoutError:
        logger.warning("[ClamAV] scan timed out — fail-open.")
        return True, "timeout"
    except (ConnectionRefusedError, OSError):
        logger.warning(
            f"[ClamAV] Cannot connect to {settings.CLAMAV_HOST}:{settings.CLAMAV_PORT} — fail-open."
        )
        return True, "unavailable"
    except Exception as exc:
        logger.warning(f"[ClamAV] Unexpected error: {exc} — fail-open.")
        return True, "error"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[DocumentOut])
async def list_documents(
    chat_id: Optional[str] = None,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists RAG documents uploaded by the authenticated user, optionally filtered by chat_id."""
    return await DocumentService.get_user_documents(db, current_user.id, chat_id=chat_id)


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    chat_id: Optional[str] = Form(None),
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Uploads a document with comprehensive security hardening:
      1. File extension allow-listing
      2. MIME type validation
      3. File size enforcement
      4. Executable magic-byte rejection  (ELF, PE, Mach-O, shebang)
      5. ZIP bomb: ratio + decompressed-size guard
      6. EICAR signature scan
      7. ClamAV INSTREAM scan             (optional, fail-open)
      8. Prompt injection content scan    (text formats only)
      9. Filename sanitisation & path traversal prevention
     10. Atomic DB registration + background ingestion task
    """
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()

    # ── 1. Extension allow-list ──────────────────────────────────────────────
    if ext not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not supported.",
        )

    # ── 2. MIME type validation ──────────────────────────────────────────────
    client_mime = file.content_type
    if client_mime and client_mime not in ALLOWED_MIME_TYPES[ext]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME type '{client_mime}' does not match extension '{ext}'.",
        )

    # ── 3. Size enforcement ──────────────────────────────────────────────────
    contents = await file.read()
    size_bytes = len(contents)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size {size_bytes // (1024 * 1024)} MB exceeds "
                f"the {settings.MAX_UPLOAD_SIZE_MB} MB limit."
            ),
        )

    # ── 4. Executable magic-byte rejection ──────────────────────────────────
    exec_type = _check_executable_magic(contents)
    if exec_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Executable content rejected ({exec_type}).",
        )

    # ── 5. ZIP bomb guard ────────────────────────────────────────────────────
    if ext in _ZIP_BASED_EXTS:
        zip_err = _check_zip_bomb(contents)
        if zip_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ZIP bomb detected: {zip_err}",
            )

    # ── 6. EICAR signature scan ──────────────────────────────────────────────
    if not scan_file_for_malware(contents):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malware signature detected — upload aborted.",
        )

    # ── 7. ClamAV INSTREAM scan ──────────────────────────────────────────────
    is_clean, clam_msg = await _scan_with_clamav(contents)
    if not is_clean:
        logger.warning(f"[Upload] ClamAV blocked '{filename}': {clam_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File rejected by antivirus: {clam_msg}",
        )

    # ── 8. Prompt injection scan ─────────────────────────────────────────────
    if ext in _TEXT_EXTS:
        hit = _check_prompt_injection(contents)
        if hit:
            logger.warning(f"[Upload] Prompt injection in '{filename}': {hit!r}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content contains disallowed prompt injection patterns.",
            )

    await file.seek(0)

    # ── 9. Filename sanitisation ─────────────────────────────────────────────
    temp_name = filename.replace("..", "").replace("/", "").replace("\\", "")
    sanitized_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", temp_name)

    # ── 10. Persist & schedule ingestion ─────────────────────────────────────
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    unique_filename = f"{uuid.uuid4()}{ext}"
    storage_path = os.path.join(settings.UPLOAD_DIR, unique_filename)

    try:
        with open(storage_path, "wb") as fh:
            fh.write(contents)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file to storage: {exc}",
        )

    try:
        file_type_cleaned = ext.lstrip(".") or "text"
        doc = await DocumentService.create_document(
            db=db,
            user_id=current_user.id,
            filename=sanitized_filename,
            file_type=file_type_cleaned,
            storage_path=storage_path,
            size_bytes=size_bytes,
            chat_id=chat_id,
        )

        # ── Resolve user's Gemini API key for real semantic ingestion ────────
        # User keys are stored encrypted in the DB — decrypt and pass to
        # the ingestion pipeline so chunks get real Gemini embeddings.
        user_api_key: Optional[str] = None
        try:
            key_result = await db.execute(
                select(ApiKey).where(
                    ApiKey.user_id == current_user.id,
                    ApiKey.provider_name.in_(["google", "gemini"]),
                )
            )
            db_key = key_result.scalar_one_or_none()
            if db_key and db_key.encrypted_api_key:
                user_api_key = decrypt_api_key(db_key.encrypted_api_key)
        except Exception as _key_exc:
            logger.warning(f"[Upload] Could not fetch user Gemini key for ingestion: {_key_exc}")
        # Fall back to server-level key if user key is absent
        if not user_api_key:
            user_api_key = settings.GEMINI_API_KEY or None

        asyncio.create_task(
            ParserService.process_document_ingestion(
                document_id=doc.id,
                user_id=current_user.id,
                file_path=storage_path,
                filename=sanitized_filename,
                file_type=file_type_cleaned,
                api_key=user_api_key,  # FIX-12: pass real key for semantic embeddings
            )
        )
        logger.info(f"[Upload] Scheduled ingestion for doc {doc.id} ({sanitized_filename})")

        from app.services.audit_service import AuditService
        await AuditService.log_event(
            db,
            current_user.id,
            "document_upload",
            {"document_id": doc.id, "filename": sanitized_filename, "size_bytes": size_bytes},
        )

        return doc

    except Exception as exc:
        if os.path.exists(storage_path):
            try:
                os.remove(storage_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register uploaded document: {exc}",
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes the document from PostgreSQL/SQLite, ChromaDB, and local disk.
    Returns 204 No Content on success, 404 if not found or access denied.
    """
    success = await DocumentService.delete_document(db, document_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or access denied.",
        )


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Downloads the physical file of the document.
    """
    from fastapi.responses import FileResponse
    doc = await DocumentService.get_document_by_id(db, document_id, current_user.id)
    if not doc or not os.path.exists(doc.storage_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or file missing on disk.",
        )
    return FileResponse(
        path=doc.storage_path,
        filename=doc.filename,
        media_type="application/octet-stream"
    )
