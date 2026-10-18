"""
api/summarize.py — Text summarization endpoint.

POST /api/v1/summarize
  Summarize text in bullet, paragraph, or tldr style.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, Literal
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import get_current_user
from app.core.database import get_db
from app.schemas.auth import UserOut
from app.services.provider_key_service import get_request_provider_keys

router = APIRouter(prefix="/summarize", tags=["Summarization"])


class SummarizeRequest(BaseModel):
    text: str = Field(..., description="The text to summarize", min_length=1)
    style: Literal["bullet", "paragraph", "tldr"] = Field(
        "bullet", description="Summary style: 'bullet', 'paragraph', or 'tldr'"
    )
    max_length: Optional[int] = Field(500, description="Approximate max words in the summary", ge=10, le=2000)


class SummarizeResponse(BaseModel):
    result: str
    style: str
    word_count_input: int
    max_length: int


@router.post("", response_model=SummarizeResponse, summary="Summarize text")
async def summarize_endpoint(
    body: SummarizeRequest,
    request: Request,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Summarize text in one of three styles:
    - **bullet**: Key points as a markdown bullet list (default)
    - **paragraph**: A concise prose summary paragraph
    - **tldr**: A single TL;DR sentence
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty.")

    from app.tools.advanced_tools import summarize_text
    api_keys = await get_request_provider_keys(db, current_user.id, request)
    result = await summarize_text(
        text=body.text,
        style=body.style,
        max_length=body.max_length or 500,
        api_keys=api_keys,
    )

    if result.startswith("Error:"):
        raise HTTPException(status_code=422, detail=result)

    return SummarizeResponse(
        result=result,
        style=body.style,
        word_count_input=len(body.text.split()),
        max_length=body.max_length or 500,
    )
