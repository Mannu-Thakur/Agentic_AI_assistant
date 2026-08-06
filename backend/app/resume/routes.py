"""
app/resume/routes.py — FastAPI endpoints for the AI Resume Builder.

Isolated router under prefix /api/v1/resume.
Reuses existing auth (get_current_user) and provider ecosystem.
"""

from __future__ import annotations

import os
import tempfile
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Response
from fastapi.responses import FileResponse, StreamingResponse

from app.api.auth import get_current_user_optional
from app.schemas.auth import UserOut
from app.resume.models import ResumeData, JDAnalysis
from app.resume.schemas import (
    AnalyzeResumeResponse, AnalyzeJDRequest, AnalyzeJDResponse,
    TailorResumeRequest, TailorResumeResponse,
    ComputeATSRequest, ATSResponse,
    DiffRequest, DiffResponse,
    ExportRequest, ApplySuggestionRequest, SuggestionResult,
    HealthResponse,
)
from app.resume.parser import parse_resume_file
from app.resume.jd_analyzer import analyze_job_description
from app.resume.ats import compute_ats_score
from app.resume.services import ResumeService
from app.resume.diff import compute_resume_diff
from app.resume.renderer import export_resume

logger = logging.getLogger("app.resume.routes")

router = APIRouter(prefix="/resume", tags=["AI Resume Builder"])


@router.get("/health", response_model=HealthResponse)
async def resume_health():
    """Health check for the resume builder subsystem."""
    return HealthResponse(status="healthy", module="ai_resume_builder")


@router.post("/analyze", response_model=AnalyzeResumeResponse)
async def analyze_resume(
    file: UploadFile = File(...),
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
):
    """
    Upload an existing resume (PDF/DOCX/TXT).
    Extracts text using OCR/native parser and converts it into structured ResumeData JSON.
    """
    filename = file.filename or "resume.pdf"
    ext = os.path.splitext(filename)[1].lower().lstrip(".")

    if ext not in ("pdf", "docx", "doc", "txt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '.{ext}'. Please upload a PDF, DOCX, or TXT file.",
        )

    contents = await file.read()
    if len(contents) > 15 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 15 MB limit.",
        )

    # Save to temp file for parsing
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"resume_{uuid.uuid4().hex}.{ext}")
    with open(temp_path, "wb") as f:
        f.write(contents)

    try:
        result = await parse_resume_file(temp_path, ext)
        return AnalyzeResumeResponse(
            resume=result["resume"],
            parse_confidence=result["parse_confidence"],
            low_confidence_fields=result["low_confidence_fields"],
            raw_text_length=result["raw_text_length"],
            parsing_method=result["parsing_method"],
        )
    except Exception as exc:
        logger.error(f"[ResumeRoutes] Analysis failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse resume: {str(exc)}",
        )
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@router.post("/analyze-jd", response_model=AnalyzeJDResponse)
async def analyze_jd_endpoint(
    req: AnalyzeJDRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
):
    """
    Analyze a Job Description.
    Extracts required skills, preferred skills, technologies, experience level, and ATS keywords into structured JSON.
    """
    try:
        jd_analysis = await analyze_job_description(req.jd_text)
        return AnalyzeJDResponse(
            jd_analysis=jd_analysis,
            keyword_count=len(jd_analysis.keywords),
            analysis_confidence=1.0,
        )
    except Exception as exc:
        logger.error(f"[ResumeRoutes] JD analysis failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze Job Description: {str(exc)}",
        )


@router.post("/tailor", response_model=TailorResumeResponse)
async def tailor_resume_endpoint(
    req: TailorResumeRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
):
    """
    Tailor resume content using AI for a specific Job Description.
    Operates strictly on structured ResumeData JSON — never raw formatting.
    """
    try:
        return await ResumeService.tailor_resume(req)
    except Exception as exc:
        logger.error(f"[ResumeRoutes] Tailoring failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to tailor resume: {str(exc)}",
        )


@router.post("/ats", response_model=ATSResponse)
async def compute_ats_endpoint(
    req: ComputeATSRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
):
    """
    Compute algorithmic ATS score.
    NEVER hallucinated by LLM — computed deterministically across 10 dimensions.
    """
    try:
        score = compute_ats_score(req.resume, req.jd_analysis)
        return ATSResponse(score=score)
    except Exception as exc:
        logger.error(f"[ResumeRoutes] ATS computation failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute ATS score: {str(exc)}",
        )


@router.post("/diff", response_model=DiffResponse)
async def compute_diff_endpoint(
    req: DiffRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
):
    """
    Compute GitHub-style word-level diff between original and tailored resume.
    """
    try:
        return compute_resume_diff(req.original, req.tailored, req.section)
    except Exception as exc:
        logger.error(f"[ResumeRoutes] Diff computation failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute diff: {str(exc)}",
        )


@router.post("/suggest", response_model=SuggestionResult)
async def apply_suggestion_endpoint(
    req: ApplySuggestionRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
):
    """
    Apply a one-click AI improvement suggestion to the resume.
    """
    try:
        return await ResumeService.apply_suggestion(
            resume=req.resume,
            suggestion_type=req.suggestion_type,
            jd=req.jd_analysis,
            api_key=req.api_key,
            model=req.model,
        )
    except Exception as exc:
        logger.error(f"[ResumeRoutes] Suggestion application failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply suggestion: {str(exc)}",
        )


@router.post("/export")
async def export_resume_endpoint(
    req: ExportRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
):
    """
    Export resume to PDF, DOCX, Markdown, or JSON.
    Generates deterministic layout directly from ResumeData JSON using Python renderers.
    """
    try:
        content_bytes, media_type, filename = export_resume(
            req.resume, format=req.format, template=req.template
        )
        return Response(
            content=content_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        logger.error(f"[ResumeRoutes] Export failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export resume: {str(exc)}",
        )


@router.post("/render")
async def render_resume_endpoint(
    req: ExportRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
):
    """
    Render PDF/DOCX preview stream.
    Alias endpoint for live PDF generation preview.
    """
    return await export_resume_endpoint(req, current_user)
