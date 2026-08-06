"""
app/resume/schemas.py — API request/response schemas for the Resume Builder.
"""

from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

from app.resume.models import ResumeData, JDAnalysis, ATSScoreBreakdown, ResumeVersion


# ─────────────────────────────────────────────────────────────────────────────
#  Request schemas
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeResumeRequest(BaseModel):
    """File upload handled via UploadFile — no body schema needed for /analyze."""
    pass


class AnalyzeJDRequest(BaseModel):
    jd_text: str = Field(..., min_length=50, max_length=20000,
                         description="Raw job description text")


class TailorResumeRequest(BaseModel):
    resume: ResumeData
    jd_analysis: JDAnalysis
    section: Literal["all", "summary", "skills", "experience", "projects"] = "all"
    style: Literal[
        "rewrite", "shorten", "expand", "quantify",
        "technical_tone", "leadership_tone", "star_format"
    ] = "rewrite"
    model: Optional[str] = None         # Falls back to best available
    api_key: Optional[str] = None       # User's BYOK key


class ComputeATSRequest(BaseModel):
    resume: ResumeData
    jd_analysis: Optional[JDAnalysis] = None


class DiffRequest(BaseModel):
    original: ResumeData
    tailored: ResumeData
    section: Optional[str] = None      # If None, diff entire resume


class ExportRequest(BaseModel):
    resume: ResumeData
    format: Literal["pdf", "docx", "markdown", "json"] = "pdf"
    template: Literal[
        "classic_ats", "modern", "minimal", "executive", "developer", "academic"
    ] = "modern"


class ApplySuggestionRequest(BaseModel):
    resume: ResumeData
    suggestion_type: Literal[
        "add_achievements", "improve_action_verbs", "remove_repetition",
        "add_missing_skills", "improve_ats", "reduce_to_one_page",
        "improve_technical_wording", "improve_leadership_wording"
    ]
    jd_analysis: Optional[JDAnalysis] = None
    model: Optional[str] = None
    api_key: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
#  Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeResumeResponse(BaseModel):
    resume: ResumeData
    parse_confidence: float = Field(ge=0.0, le=1.0)
    low_confidence_fields: List[str] = Field(default_factory=list)
    raw_text_length: int = 0
    parsing_method: str = ""    # "pdf_native", "pdf_ocr", "docx"


class AnalyzeJDResponse(BaseModel):
    jd_analysis: JDAnalysis
    keyword_count: int = 0
    analysis_confidence: float = 1.0


class TailorResumeResponse(BaseModel):
    tailored_resume: ResumeData
    changes_summary: List[str] = Field(default_factory=list)
    model_used: str = ""
    tokens_used: int = 0


class ATSResponse(BaseModel):
    score: ATSScoreBreakdown


class DiffSection(BaseModel):
    section: str
    field: str
    diff_type: Literal["added", "removed", "modified", "unchanged"]
    original_text: str = ""
    new_text: str = ""
    chunks: List[dict] = Field(default_factory=list)    # word-level diff chunks


class DiffResponse(BaseModel):
    sections: List[DiffSection] = Field(default_factory=list)
    total_additions: int = 0
    total_removals: int = 0
    total_modifications: int = 0
    change_percentage: float = 0.0


class SuggestionResult(BaseModel):
    updated_resume: ResumeData
    suggestion_applied: str
    changes: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    module: str = "resume_builder"
