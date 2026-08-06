"""
app/resume/parser.py — Resume document parsing into structured ResumeData JSON.

Reuses the existing ParserService for text extraction (PDF/DOCX/OCR pipeline).
Calls LLM to convert extracted text → structured ResumeData.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Optional, Tuple

from app.resume.models import ResumeData, PersonalInfo, SkillGroup
from app.resume.prompts import PARSE_RESUME_SYSTEM, PARSE_RESUME_USER

logger = logging.getLogger("app.resume.parser")

# ── Action verbs for confidence scoring ──────────────────────────────────────
_ACTION_VERBS = {
    "developed", "built", "designed", "implemented", "led", "managed",
    "created", "architected", "deployed", "optimized", "reduced", "increased",
    "launched", "engineered", "delivered", "collaborated", "mentored",
    "established", "drove", "achieved", "automated", "migrated", "improved",
    "spearheaded", "coordinated", "integrated", "streamlined", "maintained",
}


def _extract_text_from_file(file_path: str, file_ext: str) -> Tuple[str, str]:
    """
    Extract raw text from PDF or DOCX using the existing ParserService pipeline.
    Returns (text, method_used).
    """
    from app.services.parser_service import ParserService

    ext = file_ext.lower().lstrip(".")

    if ext == "pdf":
        try:
            text, _ = ParserService.extract_text_pdf(file_path)
            if text and len(text.strip()) > 100:
                return text, "pdf_native"
        except Exception as e:
            logger.warning(f"[ResumeParser] PDF native extraction failed: {e}")

        # Fallback to OCR
        try:
            ocr_result = ParserService.extract_text_ocr(file_path)
            if ocr_result and ocr_result.text:
                return ocr_result.text, "pdf_ocr"
        except Exception as e:
            logger.warning(f"[ResumeParser] PDF OCR fallback failed: {e}")

        raise ValueError("Could not extract text from PDF. Try a different file.")

    elif ext in ("docx", "doc"):
        try:
            text, _ = ParserService.extract_text_docx(file_path)
            if text:
                return text, "docx"
        except Exception as e:
            logger.warning(f"[ResumeParser] DOCX extraction failed: {e}")
        raise ValueError("Could not extract text from DOCX.")

    elif ext == "txt":
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        return text, "txt"

    raise ValueError(f"Unsupported file format: .{ext}")


async def _parse_with_llm(
    raw_text: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> ResumeData:
    """
    Use LLM to convert raw resume text → structured ResumeData JSON.
    Falls back to regex-based parsing if LLM fails.
    """
    from app.resume.llm import call_llm_json

    prompt = PARSE_RESUME_USER.format(resume_text=raw_text[:8000])

    try:
        result = await call_llm_json(
            system=PARSE_RESUME_SYSTEM,
            user=prompt,
            api_key=api_key,
            model=model,
            max_tokens=4096,
        )
        resume = ResumeData(**result)
        # Assign IDs if missing
        _ensure_ids(resume)
        return resume
    except Exception as e:
        logger.warning(f"[ResumeParser] LLM parse failed: {e}. Using regex fallback.")
        return _regex_parse_fallback(raw_text)


def _ensure_ids(resume: ResumeData) -> None:
    """Ensure every entry has a unique id."""
    for i, exp in enumerate(resume.experience):
        if not exp.id:
            exp.id = f"exp_{i + 1}"
    for i, proj in enumerate(resume.projects):
        if not proj.id:
            proj.id = f"proj_{i + 1}"
    for i, edu in enumerate(resume.education):
        if not edu.id:
            edu.id = f"edu_{i + 1}"
    for i, cert in enumerate(resume.certifications):
        if not cert.id:
            cert.id = f"cert_{i + 1}"
    for i, ach in enumerate(resume.achievements):
        if not ach.id:
            ach.id = f"ach_{i + 1}"


def _regex_parse_fallback(text: str) -> ResumeData:
    """
    Rule-based fallback parser for when LLM is unavailable.
    Extracts common resume patterns using regex.
    """
    resume = ResumeData()

    # Email
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
    if email_match:
        resume.personal.email = email_match.group()

    # Phone
    phone_match = re.search(r"[\+]?[\d][\d\s\-\(\)]{8,14}[\d]", text)
    if phone_match:
        resume.personal.phone = phone_match.group().strip()

    # LinkedIn
    linkedin_match = re.search(r"linkedin\.com/in/[\w\-]+", text, re.I)
    if linkedin_match:
        resume.personal.linkedin = "https://" + linkedin_match.group()

    # GitHub
    github_match = re.search(r"github\.com/[\w\-]+", text, re.I)
    if github_match:
        resume.personal.github = "https://" + github_match.group()

    # Name — usually first non-empty line
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        first_line = lines[0]
        if len(first_line.split()) <= 5 and not "@" in first_line:
            resume.personal.name = first_line

    # Extract skills (lines with common delimiters like: Skills: Python, Java, React)
    skills_match = re.search(
        r"(?:skills?|technical skills?|technologies?)[:\s]+(.*?)(?:\n\n|\n[A-Z])",
        text, re.I | re.S
    )
    if skills_match:
        skills_text = skills_match.group(1)
        skills_list = re.split(r"[,|•·]|\n", skills_text)
        skills_clean = [s.strip() for s in skills_list if s.strip() and len(s.strip()) < 40]
        if skills_clean:
            resume.skills = [SkillGroup(category="Technical Skills", skills=skills_clean[:30])]

    return resume


def _compute_confidence(resume: ResumeData, raw_text_length: int) -> Tuple[float, list]:
    """
    Compute parse confidence score and identify low-confidence fields.
    Returns (confidence_0_to_1, list_of_low_confidence_fields).
    """
    score = 0.0
    total = 0.0
    low_confidence = []

    def check(field_name: str, value, weight: float = 1.0):
        nonlocal score, total
        total += weight
        has_value = bool(value) if not isinstance(value, list) else len(value) > 0
        if has_value:
            score += weight
        else:
            low_confidence.append(field_name)

    check("name", resume.personal.name, 2.0)
    check("email", resume.personal.email, 2.0)
    check("phone", resume.personal.phone, 1.0)
    check("summary", resume.summary, 1.5)
    check("skills", resume.skills, 2.0)
    check("experience", resume.experience, 3.0)
    check("education", resume.education, 1.5)

    confidence = score / total if total > 0 else 0.0
    return round(confidence, 2), low_confidence


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

async def parse_resume_file(
    file_path: str,
    file_ext: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Main entry point: file → structured ResumeData.

    Returns dict with:
      - resume: ResumeData
      - parse_confidence: float
      - low_confidence_fields: list[str]
      - raw_text_length: int
      - parsing_method: str
    """
    raw_text, method = _extract_text_from_file(file_path, file_ext)
    raw_text_length = len(raw_text)
    logger.info(f"[ResumeParser] Extracted {raw_text_length} chars via {method}")

    resume = await _parse_with_llm(raw_text, api_key=api_key, model=model)
    confidence, low_conf_fields = _compute_confidence(resume, raw_text_length)

    return {
        "resume": resume,
        "parse_confidence": confidence,
        "low_confidence_fields": low_conf_fields,
        "raw_text_length": raw_text_length,
        "parsing_method": method,
    }
