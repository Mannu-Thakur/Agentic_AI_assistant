"""
app/resume/parser.py — Production-Grade Document AI Parsing & Extraction Engine.

Architecture:
  1. Adaptive Parser Selection (Native PyMuPDF/pypdf/docx -> OCR decision)
  2. Text Artifact Normalization & Cleaning
  3. Deterministic Rule-Based Extraction (Email, Phone, LinkedIn, GitHub, URLs, Dates, CGPA)
  4. LLM Semantic Structured Extraction (Summary, Experience, Projects, Education, Skills)
  5. JSON Repair Mechanics & Schema Recovery
  6. Pydantic Validation & Sanitization
  7. Automated 9-Category Skill Categorization
  8. Multi-Dimensional Weighted Confidence Scoring Engine
  9. Document AI Telemetry & Observability Logging
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from app.resume.models import (
    ResumeData, PersonalInfo, ExperienceEntry, ProjectEntry,
    EducationEntry, CertificationEntry, AchievementEntry, LanguageEntry, SkillGroup
)
from app.resume.prompts import PARSE_RESUME_SYSTEM, PARSE_RESUME_USER
from app.resume.normalizer import normalize_resume_text, fix_email_artifacts
from app.resume.extractor import run_deterministic_extraction
from app.resume.validator import validate_and_sanitize_resume, validate_email, validate_phone, validate_url
from app.resume.skill_categorizer import categorize_skills
from app.resume.confidence import compute_weighted_confidence
from app.resume.metrics import ParseTelemetry, log_parse_metrics

logger = logging.getLogger("app.resume.parser")


def _is_text_sparse_or_corrupted(text: str) -> bool:
    """
    Adaptive Parser Selection Decision Logic:
    Evaluates extracted text density, printable character ratio, and length.
    If text length < 120 characters or letter ratio < 35%, native parser is sparse/corrupted,
    requiring OCR fallback.
    """
    if not text:
        return True
    
    clean_stripped = text.strip()
    if len(clean_stripped) < 120:
        return True
    
    letters = sum(1 for c in clean_stripped if c.isalpha())
    letter_ratio = letters / max(len(clean_stripped), 1)
    
    if letter_ratio < 0.35:
        logger.info(f"[AdaptiveParser] Low letter ratio ({letter_ratio:.2f}); triggering OCR pipeline.")
        return True

    return False


def _extract_text_adaptive(file_path: str, file_ext: str) -> Tuple[str, str, str]:
    """
    Extract document text using Adaptive Parser Selection.
    Returns (extracted_text, method_used, detected_layout).
    """
    from app.services.parser_service import ParserService

    ext = file_ext.lower().lstrip(".")
    detected_layout = "single_column"

    if ext == "pdf":
        native_text = ""
        try:
            native_text, page_meta = ParserService.extract_layout_markdown_pymupdf(file_path)
            # Detect two-column layout heuristic (short lines + multiple offset columns)
            if native_text and "  " in native_text and "\n" in native_text:
                avg_line_len = sum(len(l) for l in native_text.splitlines() if l.strip()) / max(len(native_text.splitlines()), 1)
                if avg_line_len < 40:
                    detected_layout = "two_column"

            if not _is_text_sparse_or_corrupted(native_text):
                return native_text, "pdf_layout_pymupdf", detected_layout
        except Exception as e:
            logger.warning(f"[AdaptiveParser] PyMuPDF layout extraction failed: {e}")
            try:
                native_text, page_meta = ParserService.extract_text_pdf(file_path)
                if not _is_text_sparse_or_corrupted(native_text):
                    return native_text, "pdf_native_fallback", detected_layout
            except Exception as exc:
                logger.warning(f"[AdaptiveParser] PDF fallback failed: {exc}")

        # Trigger OCR pipeline for scanned/image PDFs
        try:
            ocr_result = ParserService.extract_text_pdf_ocr(file_path)
            if ocr_result and ocr_result.text and len(ocr_result.text.strip()) > 30:
                return ocr_result.text, "pdf_ocr", "scanned_document"
        except Exception as e:
            logger.warning(f"[AdaptiveParser] PDF OCR fallback failed: {e}")

        if native_text:
            return native_text, "pdf_native_sparse", detected_layout

        raise ValueError("Could not extract readable text from PDF file.")


    elif ext in ("docx", "doc"):
        try:
            text = ParserService.extract_text_docx(file_path)
            if text:
                return text, "docx", "single_column"
        except Exception as e:
            logger.warning(f"[AdaptiveParser] DOCX extraction failed: {e}")
        raise ValueError("Could not extract text from DOCX document.")

    elif ext == "txt":
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        return text, "txt", "single_column"

    elif ext in ("png", "jpg", "jpeg", "bmp", "tiff", "webp"):
        try:
            ocr_res = ParserService.extract_text_image(file_path)
            if ocr_res and ocr_res.text:
                return ocr_res.text, "image_ocr", "image_document"
        except Exception as e:
            logger.warning(f"[AdaptiveParser] Image OCR failed: {e}")
        raise ValueError("Could not extract text from image file.")

    raise ValueError(f"Unsupported file format: .{ext}")


def _repair_malformed_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Robust JSON Repair Mechanic:
    Extracts JSON candidates using bracket matching and repairs missing trailing braces or quotes.
    """
    if not text:
        return None

    # Clean markdown fences
    clean_t = re.sub(r"```(?:json)?\s*", "", text)
    clean_t = re.sub(r"```\s*$", "", clean_t, flags=re.MULTILINE).strip()

    # Attempt direct parse
    try:
        return json.loads(clean_t)
    except json.JSONDecodeError:
        pass

    # Balance unclosed braces/brackets if LLM output was truncated
    open_braces = clean_t.count("{")
    close_braces = clean_t.count("}")
    if open_braces > close_braces:
        repaired_t = clean_t + ("\n}" * (open_braces - close_braces))
        try:
            return json.loads(repaired_t)
        except json.JSONDecodeError:
            pass

    # Extract JSON object span
    start_idx = clean_t.find("{")
    end_idx = clean_t.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        candidate = clean_t[start_idx:end_idx + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None


async def _parse_with_llm_and_repair(
    normalized_text: str,
    deterministic_findings: Dict[str, Any],
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[Optional[ResumeData], bool]:
    """
    Call LLM for semantic extraction with JSON repair mechanics.
    Returns (ResumeData_or_None, llm_succeeded_boolean).
    """
    from app.resume.llm import call_llm_json

    prompt = PARSE_RESUME_USER.format(
        resume_text=normalized_text[:10000],
        email_hint=deterministic_findings.get("email", ""),
        phone_hint=deterministic_findings.get("phone", ""),
        linkedin_hint=deterministic_findings.get("linkedin", ""),
        github_hint=deterministic_findings.get("github", ""),
    )

    try:
        raw_result = await call_llm_json(
            system=PARSE_RESUME_SYSTEM,
            user=prompt,
            api_key=api_key,
            model=model,
            max_tokens=4096,
        )
        if isinstance(raw_result, str):
            repaired_dict = _repair_malformed_json(raw_result)
            if repaired_dict:
                return ResumeData(**repaired_dict), True
        elif isinstance(raw_result, dict):
            return ResumeData(**raw_result), True
    except Exception as e:
        logger.warning(f"[DocumentAI Parser] LLM call failed ({e}). Triggering JSON repair & rule-based fallback.")

    return None, False


def _regex_fallback_parser(text: str, deterministic_findings: Dict[str, Any]) -> ResumeData:
    """
    Rule-based fallback parser used when LLM is unavailable or fails.
    Converts deterministic findings and pattern matches into valid ResumeData using section_segmenter.
    """
    from app.resume.section_segmenter import segment_resume_sections

    resume = ResumeData()
    sections = segment_resume_sections(text)

    # 1. Contact / Personal Info
    resume.personal.email = deterministic_findings.get("email", "") or validate_email("", text)
    resume.personal.phone = deterministic_findings.get("phone", "") or validate_phone("", text)
    resume.personal.linkedin = deterministic_findings.get("linkedin", "")
    resume.personal.github = deterministic_findings.get("github", "")

    # Extract name & location from personal block or document header
    p_text = sections.get("personal", "") or text
    lines = [l.strip() for l in p_text.splitlines() if l.strip()]
    for l in lines[:5]:
        if "@" not in l and not re.search(r"\b(resume|curriculum|cv|summary|experience|skills|education)\b", l, re.I):
            if 2 <= len(l.split()) <= 4:
                resume.personal.name = l
                break

    loc_match = re.search(r"(?:location|city|address)[:\s]+([^\n,]+(?:,\s*[^\n]+)?)", text, re.I)
    if not loc_match:
        loc_match = re.search(r"\b([A-Z][a-zA-Z\s]+,\s*(?:India|USA|UK|Canada|California|CA|NY|MA|TX|FL))\b", text)
    if loc_match:
        resume.personal.location = loc_match.group(1).strip()

    # 2. Professional Summary
    if sections.get("summary"):
        resume.summary = sections["summary"][:600].strip()
    elif sections.get("personal"):
        p_lines = [l.strip() for l in sections["personal"].splitlines() if l.strip()]
        summary_candidates = []
        for line in p_lines:
            if "@" in line or re.search(r"\+?\d[\d\s\-\(\)\.]{7,}", line) or "linkedin.com" in line or "github.com" in line or "http" in line:
                continue
            if line == resume.personal.name or re.search(r"^(?:full\s+name|email|phone|location|linkedin|github)\b", line, re.I):
                continue
            summary_candidates.append(line)
        if summary_candidates:
            cand_text = " ".join(summary_candidates).strip()
            if len(cand_text.split()) >= 6:
                resume.summary = cand_text[:600]

    # 3. Skills (parsed cleanly within sections["skills"])
    if sections.get("skills"):
        resume.skills = categorize_skills([sections["skills"]])

    # 4. Education Section Parsing
    if sections.get("education"):
        edu_block = sections["education"]
        inst_match = re.search(r"(?:International\s+Institute\s+of\s+Information\s+Technology|IIIT|Stanford|IIT|MIT|[A-Z][A-Za-z\s,&]+\s+(?:University|Institute|College|School))", edu_block, re.I)
        deg_match = re.search(r"(?:B\.Tech|M\.Tech|Bachelor|Master|B\.S\.|M\.S\.|Ph\.D\.|Diploma)[^\n,]*", edu_block, re.I)
        dates_match = re.search(r"\b20\d{2}\s*(?:–|-|to)\s*20\d{2}\b", edu_block)
        gpa_match = re.search(r"(?:CGPA|GPA)[:\s\(\)]*([0-9]\.[0-9]{1,2})", edu_block, re.I)

        inst = inst_match.group(0).strip() if inst_match else ""
        raw_deg = deg_match.group(0).strip() if deg_match else ""
        deg = re.sub(r"(?:CGPA|GPA)[:\s\(\)]*[0-9]\.[0-9]{1,2}.*", "", raw_deg, flags=re.I).strip()
        gpa = gpa_match.group(1).strip() if gpa_match else deterministic_findings.get("gpa", "")
        start_d = dates_match.group(0).split("–")[0].split("-")[0].strip() if dates_match else ""
        end_d = dates_match.group(0).split("–")[-1].split("-")[-1].strip() if dates_match else ""

        if inst or deg:
            resume.education.append(EducationEntry(
                id="edu_1",
                institution=inst,
                degree=deg,
                gpa=gpa,
                start_date=start_d,
                end_date=end_d
            ))

    # 5. Experience Section Parsing
    if sections.get("experience"):
        exp_block = sections["experience"]
        lines = [l.strip() for l in exp_block.splitlines() if l.strip()]
        if lines:
            role_m = re.search(r"(?:Frontend|Backend|Software|Full[- ]Stack|AI|ML|Data|DevOps|System)?\s*(?:Developer|Engineer|Intern|Architect|Manager|Lead)\b", exp_block, re.I)
            comp_m = re.search(r"([A-Z][A-Za-z0-9\s,&]{2,35}\s+(?:Pvt\.\s*Ltd\.|Inc\.|LLC|Corp|Solutions|Tech|Systems|Technologies))", exp_block, re.I)
            dates_m = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\s*(?:-|–|to)\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Present|Current)[a-z]*\.?\s*(?:\d{4})?\b", exp_block, re.I)
            
            raw_comp = comp_m.group(1).strip() if comp_m else ""
            # Clean dates/months prepended to company name (e.g. 'Jul 2026Nemhans' -> 'Nemhans')
            comp = re.sub(r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}\s*", "", raw_comp, flags=re.I).strip()
            comp = re.sub(r"^\d{4}\s*", "", comp).strip()

            # Filter lines for valid bullet points (exclude role titles, dates, company names, locations, and 'Technologies:' headers)
            bullets = []
            for line in lines:
                clean_l = line.lstrip("•-· ").strip()
                if not clean_l or len(clean_l.split()) < 3:
                    continue
                if clean_l.lower().startswith("technologies:"):
                    continue
                if re.search(r"\b(Intern|Developer|Engineer|Architect|Manager|Lead)\b.*\b(20\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", clean_l, re.I):
                    continue
                if re.search(r"(?:Pvt\.\s*Ltd\.|Inc\.|LLC|Corp|Bhubaneswar|India)", clean_l, re.I) and not re.search(r"\b(developed|built|created|designed|implemented|collaborated|led|managed|engineered|architected)\b", clean_l, re.I):
                    continue
                bullets.append(clean_l)

            start_d = dates_m.group(0).split("–")[0].split("-")[0].strip() if dates_m else ""
            end_d = dates_m.group(0).split("–")[-1].split("-")[-1].strip() if dates_m else ""
            role_str = role_m.group(0).strip() if role_m else ""

            if comp or role_str or bullets:
                resume.experience.append(ExperienceEntry(
                    id="exp_1",
                    company=comp,
                    role=role_str,
                    start_date=start_d,
                    end_date=end_d,
                    bullets=bullets[:6]
                ))

    # 6. Projects Section Parsing
    if sections.get("projects"):
        proj_block = sections["projects"]
        lines = [l.strip() for l in proj_block.splitlines() if l.strip()]
        cur_proj = None
        proj_idx = 1
        i = 0
        while i < len(lines):
            line = lines[i]
            clean_l = line.lstrip("•-–—·* ").strip()
            is_tech = clean_l.lower().startswith(("technologies:", "tech:", "tech stack:", "technologies used:"))
            
            next_is_tech = False
            if i + 1 < len(lines):
                next_clean = lines[i+1].lstrip("•-–—·* ").strip()
                next_is_tech = next_clean.lower().startswith(("technologies:", "tech:", "tech stack:", "technologies used:"))
            
            if next_is_tech or (not is_tech and not line.startswith(("•", "-", "–", "—", "*", "·")) and cur_proj is None):
                if cur_proj and cur_proj.get("name"):
                    resume.projects.append(ProjectEntry(**cur_proj))
                    proj_idx += 1
                name_clean = re.sub(r"\s+\d+$", "", clean_l)
                name_clean = re.sub(r"\s*/\s*external-link-alt.*$", "", name_clean, flags=re.I).strip()
                cur_proj = {
                    "id": f"proj_{proj_idx}",
                    "name": name_clean,
                    "technologies": [],
                    "description": "",
                    "bullets": []
                }
                i += 1
                continue
                
            if cur_proj:
                if is_tech:
                    tech_str = re.sub(r"^(?:technologies|tech|tech stack|technologies used)[:\s]*", "", clean_l, flags=re.I)
                    cur_proj["technologies"] = [t.strip() for t in tech_str.split(",") if t.strip()]
                else:
                    if cur_proj["bullets"] and not line.startswith(("•", "-", "–", "—", "*", "·")) and not cur_proj["bullets"][-1].endswith((".", "!", ";")):
                        cur_proj["bullets"][-1] += " " + clean_l
                    else:
                        cur_proj["bullets"].append(clean_l)
            i += 1

        if cur_proj and cur_proj.get("name"):
            resume.projects.append(ProjectEntry(**cur_proj))

    # 7. Achievements Section Parsing
    if sections.get("achievements"):
        ach_block = sections["achievements"]
        lines = [l.strip() for l in ach_block.splitlines() if l.strip()]
        ach_items = []
        for line in lines:
            is_bullet = line.startswith(("•", "-", "–", "—", "*", "·"))
            clean_l = line.lstrip("•-–—·* ").strip()
            if not clean_l:
                continue
            if is_bullet or not ach_items:
                ach_items.append(clean_l)
            else:
                ach_items[-1] += " " + clean_l

        for idx, item in enumerate(ach_items, start=1):
            colon_split = item.split(":", 1)
            if len(colon_split) == 2 and len(colon_split[0].split()) <= 6:
                title = colon_split[0].strip()
                desc = item.strip()
            else:
                title = item[:60].strip()
                desc = item.strip()

            resume.achievements.append(AchievementEntry(
                id=f"ach_{idx}",
                title=title,
                description=desc
            ))

    return resume


# ─────────────────────────────────────────────────────────────────────────────
#  Public Document AI API Entry Point
# ─────────────────────────────────────────────────────────────────────────────

async def parse_resume_file(
    file_path: str,
    file_ext: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Enterprise Entry Point: Document file → validated structured ResumeData JSON.

    Pipeline Steps:
      1. Adaptive Parser Selection (Native -> OCR)
      2. Text Normalization & Artifact Stripping
      3. Deterministic Rule-Based Pre-Extraction
      4. LLM Semantic Extraction + JSON Repair
      5. Fallback Recovery
      6. Validation & Deduplication
      7. 9-Category Skill Classification
      8. Multi-Dimensional Confidence Scoring
      9. Document AI Telemetry Logging
    """
    telemetry = ParseTelemetry(file_ext=file_ext)

    # 1. Adaptive Parser Selection
    raw_text, parsing_method, layout = _extract_text_adaptive(file_path, file_ext)
    telemetry.raw_text_length = len(raw_text)
    telemetry.parser_selection = parsing_method
    telemetry.resume_layout = layout
    telemetry.ocr_triggered = "ocr" in parsing_method

    # 2. Text Normalization
    normalized_text = normalize_resume_text(raw_text)

    # 3. Deterministic Rule-Based Extraction
    deterministic_findings = run_deterministic_extraction(normalized_text)

    # 4. LLM Extraction & JSON Repair
    llm_resume, llm_succeeded = await _parse_with_llm_and_repair(
        normalized_text, deterministic_findings, api_key=api_key, model=model
    )
    telemetry.llm_used = True
    telemetry.llm_fallback_triggered = not llm_succeeded

    if not llm_succeeded or not llm_resume:
        logger.info("[DocumentAI Parser] LLM fallback active; extracting via rule-based engine.")
        raw_resume = _regex_fallback_parser(normalized_text, deterministic_findings)
    else:
        raw_resume = llm_resume

    # Override deterministic fields to guarantee 100% precision for contact info
    if deterministic_findings.get("email"):
        raw_resume.personal.email = deterministic_findings["email"]
    if deterministic_findings.get("phone"):
        raw_resume.personal.phone = deterministic_findings["phone"]
    if deterministic_findings.get("linkedin"):
        raw_resume.personal.linkedin = deterministic_findings["linkedin"]
    if deterministic_findings.get("github"):
        raw_resume.personal.github = deterministic_findings["github"]

    # 5. Pydantic Validation & 9-Category Skill Classification
    validated_resume = validate_and_sanitize_resume(raw_resume, raw_text=normalized_text)

    # 6. Multi-Dimensional Weighted Confidence Scoring
    overall_conf, low_fields, sec_confs = compute_weighted_confidence(
        validated_resume,
        parsing_method=parsing_method,
        deterministic_hits=deterministic_findings,
        llm_succeeded=llm_succeeded,
        raw_text_length=telemetry.raw_text_length,
    )

    # 7. Telemetry & Metrics Logging
    telemetry.overall_confidence = overall_conf
    telemetry.section_confidences = sec_confs
    telemetry.low_confidence_fields = low_fields
    log_parse_metrics(telemetry)

    return {
        "resume": validated_resume,
        "parse_confidence": overall_conf,
        "low_confidence_fields": low_fields,
        "section_confidences": sec_confs,
        "raw_text_length": telemetry.raw_text_length,
        "parsing_method": parsing_method,
        "resume_layout": layout,
    }
