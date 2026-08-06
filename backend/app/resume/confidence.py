"""
app/resume/confidence.py — Multi-Dimensional Weighted Confidence Engine for Document AI.

Formula:
  Overall Confidence = (0.15 * NativeParserScore) +
                       (0.25 * RegexValidationScore) +
                       (0.20 * LLMScore) +
                       (0.25 * SectionCompletenessScore) +
                       (0.15 * SchemaValidationScore)

Computes per-section confidences and identifies low-confidence fields for UI highlighting.
"""

from __future__ import annotations
from typing import Tuple, List, Dict, Any
from app.resume.models import ResumeData


def compute_weighted_confidence(
    resume: ResumeData,
    parsing_method: str = "pdf_native",
    deterministic_hits: Dict[str, Any] = None,
    llm_succeeded: bool = True,
    raw_text_length: int = 0
) -> Tuple[float, List[str], Dict[str, float]]:
    """
    Compute multi-dimensional weighted confidence score and per-section confidence pills.

    Returns:
        (overall_confidence_0_to_1, low_confidence_fields, section_confidences_dict)
    """
    section_confidences: Dict[str, float] = {}
    low_confidence_fields: List[str] = []
    deterministic_hits = deterministic_hits or {}

    # 1. Native Parser Score (15%)
    if parsing_method in ("pdf_native", "docx", "txt"):
        native_score = 1.0
    elif parsing_method == "pdf_ocr":
        native_score = 0.85
    elif parsing_method == "image_ocr":
        native_score = 0.75
    else:
        native_score = 0.5

    # 2. Regex Validation Score (25%) & Personal Section Confidence
    p = resume.personal
    if p.name and p.email and p.phone:
        sec_personal = 1.0
    elif p.name and p.email:
        sec_personal = 0.85
    elif p.name or p.email:
        sec_personal = 0.60
    else:
        sec_personal = 0.20
        low_confidence_fields.append("personal.name")
        low_confidence_fields.append("personal.email")

    section_confidences["personal"] = sec_personal
    regex_score = sec_personal

    # 3. LLM Extraction Score (20%)
    llm_score = 1.0 if llm_succeeded else 0.5

    # 4. Section Completeness Score (25%) & Per-Section Confidence
    completeness_points = 0.0
    total_sections = 9.0

    if sec_personal >= 0.75:
        completeness_points += 1.0

    # Summary Section Confidence
    sum_len = len(resume.summary.strip())
    if sum_len >= 80:
        sec_summary = 1.0
    elif sum_len > 0:
        sec_summary = 0.65
    else:
        sec_summary = 0.0
        low_confidence_fields.append("summary")
    section_confidences["summary"] = sec_summary
    if sec_summary >= 0.65:
        completeness_points += 1.0

    # Education Section Confidence
    if resume.education:
        edu_valid = [e for e in resume.education if e.institution or e.degree]
        sec_edu = round(len(edu_valid) / max(len(resume.education), 1), 2)
        if sec_edu >= 0.5:
            completeness_points += 1.0
    else:
        sec_edu = 0.0
        low_confidence_fields.append("education")
    section_confidences["education"] = sec_edu

    # Skills Section Confidence
    total_skills = sum(len(g.skills) for g in resume.skills)
    if total_skills >= 8:
        sec_skills = 1.0
        completeness_points += 1.0
    elif total_skills >= 2:
        sec_skills = 0.85
        completeness_points += 1.0
    else:
        sec_skills = 0.0
        low_confidence_fields.append("skills")
    section_confidences["skills"] = sec_skills

    # Work Experience Section Confidence
    if resume.experience:
        exp_valid = [e for e in resume.experience if (e.company or e.role)]
        sec_exp = round(len(exp_valid) / max(len(resume.experience), 1), 2)
        if sec_exp >= 0.5:
            completeness_points += 1.0
    else:
        sec_exp = 0.0
        low_confidence_fields.append("experience")
    section_confidences["experience"] = sec_exp

    # Projects Section Confidence
    if resume.projects:
        sec_proj = 0.95
        completeness_points += 1.0
    else:
        sec_proj = 0.0
    section_confidences["projects"] = sec_proj

    # Achievements Confidence
    if resume.achievements:
        sec_ach = 0.95
        completeness_points += 1.0
    else:
        sec_ach = 0.0
    section_confidences["achievements"] = sec_ach

    # Certifications Confidence
    if resume.certifications:
        sec_cert = 0.95
        completeness_points += 0.5
    else:
        sec_cert = 0.0
    section_confidences["certifications"] = sec_cert

    # Languages Confidence
    if resume.languages:
        sec_lang = 1.0
        completeness_points += 0.5
    else:
        sec_lang = 0.0
    section_confidences["languages"] = sec_lang

    # Base completeness requires core 4 sections (Personal, Edu, Skills, Exp/Proj) = 4.0 points
    section_completeness_score = round(min(1.0, completeness_points / 4.0), 2)

    # 5. Schema Validation Score (15%)
    schema_score = 1.0 if not low_confidence_fields else max(0.6, 1.0 - (len(low_confidence_fields) * 0.08))

    # Overall Multi-Dimensional Weighted Score
    overall_confidence = (
        (0.15 * native_score) +
        (0.25 * regex_score) +
        (0.20 * llm_score) +
        (0.25 * section_completeness_score) +
        (0.15 * schema_score)
    )

    overall_confidence = round(min(1.0, max(0.0, overall_confidence)), 2)

    return overall_confidence, low_confidence_fields, section_confidences



# Backward compatibility alias
def compute_section_and_overall_confidence(resume: ResumeData, raw_text_length: int = 0):
    return compute_weighted_confidence(resume, raw_text_length=raw_text_length)
