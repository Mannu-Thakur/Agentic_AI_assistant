import os
import logging
import traceback
from typing import List

from app.models.document import Document
from app.retrieval.vector_store import VectorStore
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

class ParserService:
    @staticmethod
    def extract_text_pdf(file_path: str) -> str:
        """
        Extract text from a PDF file using pypdf.
        """
        import pypdf
        reader = pypdf.PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n".join(text_parts)

    @staticmethod
    def extract_text_docx(file_path: str) -> str:
        """
        Extract text from a Word document using python-docx.
        """
        import docx
        doc = docx.Document(file_path)
        text_parts = [p.text for p in doc.paragraphs]
        return "\n".join(text_parts)

    @staticmethod
    def extract_text_xlsx(file_path: str) -> str:
        """
        Extract text from an Excel sheet using openpyxl.
        """
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        text_parts = []
        for sheet in wb.worksheets:
            text_parts.append(f"--- Sheet: {sheet.title} ---")
            for row in sheet.iter_rows(values_only=True):
                row_str = " | ".join(str(cell) for cell in row if cell is not None)
                if row_str.strip():
                    text_parts.append(row_str)
        return "\n".join(text_parts)

    @staticmethod
    def extract_text_pptx(file_path: str) -> str:
        """
        Extract text from a PowerPoint presentation using python-pptx.
        """
        import pptx
        prs = pptx.Presentation(file_path)
        text_parts = []
        for i, slide in enumerate(prs.slides):
            text_parts.append(f"--- Slide {i+1} ---")
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    text_parts.append(shape.text)
        return "\n".join(text_parts)

    @staticmethod
    def extract_text_image(file_path: str) -> str:
        """
        Extract text from an image using Pillow and pytesseract OCR.
        Falls back gracefully if Tesseract is not installed.
        """
        from PIL import Image
        import pytesseract
        try:
            img = Image.open(file_path)
            return pytesseract.image_to_string(img)
        except Exception as e:
            logger.warning(f"Tesseract OCR failed or not configured: {str(e)}")
            return f"[OCR Ingestion failed/not configured for image: {os.path.basename(file_path)}]"

    @classmethod
    def extract_text(cls, file_path: str, file_type: str) -> str:
        """
        Route to the correct extraction handler based on file extension.
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            return cls.extract_text_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            return cls.extract_text_docx(file_path)
        elif ext in [".xlsx", ".xls"]:
            return cls.extract_text_xlsx(file_path)
        elif ext in [".pptx", ".ppt"]:
            return cls.extract_text_pptx(file_path)
        elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff"]:
            return cls.extract_text_image(file_path)
        else:
            # Standard text or markdown file read
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read file as text: {str(e)}")
                raise e

    @staticmethod
    def split_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
        """
        Split a document string into smaller word-based character chunks.
        """
        chunks = []
        text = text.strip()
        if not text:
            return chunks

        words = text.split()
        current_chunk = []
        current_length = 0

        for word in words:
            word_len = len(word) + 1  # count the word plus a space
            if current_length + word_len > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                
                # Backtrack to implement overlapping chunks
                overlap_words = []
                overlap_len = 0
                for w in reversed(current_chunk):
                    if overlap_len + len(w) + 1 > chunk_overlap:
                        break
                    overlap_words.insert(0, w)
                    overlap_len += len(w) + 1
                current_chunk = overlap_words
                current_length = overlap_len

            current_chunk.append(word)
            current_length += word_len

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    @classmethod
    async def process_document_ingestion(
        cls,
        document_id: str,
        user_id: str,
        file_path: str,
        filename: str,
        file_type: str
    ):
        """
        FastAPI Background Task to extract, chunk, embed, and index a document.
        Keeps database state updated.
        """
        logger.info(f"Background task starting for document {document_id} ({filename})")
        try:
            # 1. Parse text from file
            text = cls.extract_text(file_path, file_type)

            # 2. Chunk text
            chunks = cls.split_text(text)
            if not chunks:
                raise ValueError("No extractable text content found in document.")

            # 3. Embed chunks and index into ChromaDB
            vector_store = VectorStore()
            await vector_store.add_document_chunks(
                document_id=document_id,
                user_id=user_id,
                filename=filename,
                chunks=chunks
            )

            # 4. Set SQL status to 'ready'
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                result = await db.execute(select(Document).where(Document.id == document_id))
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = "ready"
                    await db.commit()

            logger.info(f"Successfully vectorized document {document_id}")

        except Exception as e:
            logger.error(f"Failed to ingest document {document_id}: {str(e)}")
            logger.error(traceback.format_exc())

            # Set SQL status to 'failed'
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                result = await db.execute(select(Document).where(Document.id == document_id))
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = "failed"
                    await db.commit()
