"""
api/translate.py — Translation endpoint.

POST /api/v1/translate
  Translate text from one language to another using the translate_text tool.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import get_current_user
from app.core.database import get_db
from app.schemas.auth import UserOut
from app.services.provider_key_service import get_request_provider_keys

router = APIRouter(prefix="/translate", tags=["Translation"])


class TranslateRequest(BaseModel):
    text: str = Field(..., description="The text to translate", min_length=1)
    target_language: str = Field(..., description="Target language name or ISO code (e.g. 'French', 'fr')")
    source_language: Optional[str] = Field("auto", description="Source language or 'auto' for detection")


class TranslateResponse(BaseModel):
    result: str
    target_language: str
    source_language: str
    char_count: int


@router.post("", response_model=TranslateResponse, summary="Translate text to another language")
async def translate_endpoint(
    body: TranslateRequest,
    request: Request,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Translate text into the target language.

    Uses Google Translate (via deep-translator) with an LLM fallback if the
    translation library is not installed or the request fails.
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty.")
    if not body.target_language.strip():
        raise HTTPException(status_code=400, detail="target_language must not be empty.")

    from app.tools.advanced_tools import translate_text
    api_keys = await get_request_provider_keys(db, current_user.id, request)
    result = await translate_text(
        text=body.text,
        target_language=body.target_language,
        source_language=body.source_language or "auto",
        api_keys=api_keys,
    )

    if result.startswith("Error:"):
        raise HTTPException(status_code=422, detail=result)

    return TranslateResponse(
        result=result,
        target_language=body.target_language,
        source_language=body.source_language or "auto",
        char_count=len(body.text),
    )
