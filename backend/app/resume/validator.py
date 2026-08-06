"""
app/resume/validator.py — Validation, sanitization, and deduplication layer for ResumeData.

Enforces:
  - RFC-compliant email validation & artifact removal (e.g. 'pemannumay15@gmail.com' -> 'mannumay15@gmail.com')
  - Phone number sanitization
  - URL format validation (LinkedIn, GitHub, Website)
  - String trimming & null string normalization
  - Value deduplication across skills, languages, bullets, projects
  - Unique ID assignment (exp_1, proj_1, edu_1, cert_1, ach_1)
"""

from __future__ import annotations
import re
import logging
from typing import List, Optional
from urllib.parse import urlparse

from app.resume.models import (
    ResumeData, PersonalInfo, ExperienceEntry, ProjectEntry,
    EducationEntry, CertificationEntry, AchievementEntry, LanguageEntry
)
from app.resume.normalizer import fix_email_artifacts, EMAIL_REGEX
from app.resume.skill_categorizer import categorize_skills

logger = logging.getLogger("app.resume.validator")

# Regex pattern for phone numbers
PHONE_REGEX = re.compile(r"[\+]?[\d][\d\s\-\(\)\.]{7,15}[\d]")
# Regex pattern for basic URL structure
URL_REGEX = re.compile(r"^(https?://)?[a-zA-Z0-9.\-]+(?::\d+)?(/.*)?$")


def validate_email(raw_email: str, raw_text_context: str = "") -> str:
    """Validate email against RFC regex and fix PDF/OCR font-icon prefix artifacts."""
    if not raw_email:
        # Attempt to extract email directly from raw_text_context if present
        if raw_text_context:
            match = EMAIL_REGEX.search(raw_text_context)
            if match:
                return fix_email_artifacts(match.group(0), raw_text_context)
        return ""

    cleaned = fix_email_artifacts(raw_email, raw_text_context)
    if EMAIL_REGEX.match(cleaned):
        return cleaned
    
    # If cleaned failed, search for any valid email within the string
    match = EMAIL_REGEX.search(raw_email)
    if match:
        return fix_email_artifacts(match.group(0), raw_text_context)
        
    return ""


def validate_phone(raw_phone: str, raw_text_context: str = "") -> str:
    """Sanitize and format phone number."""
    if not raw_phone:
        if raw_text_context:
            match = PHONE_REGEX.search(raw_text_context)
            if match:
                return match.group(0).strip()
        return ""
    
    match = PHONE_REGEX.search(raw_phone)
    if match:
        return match.group(0).strip()
    return raw_phone.strip()


def validate_url(url_str: str, default_prefix: str = "https://") -> str:
    """Validate web URL and ensure proper protocol prefix."""
    if not url_str:
        return ""
    
    url = url_str.strip()
    # Strip trailing punctuation often extracted from text (like commas or periods)
    url = re.sub(r"[.,;>\])]+$", "", url)

    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = default_prefix + url

    try:
        parsed = urlparse(url)
        if parsed.netloc and "." in parsed.netloc:
            return url
    except Exception:
        pass
        
    return ""


def sanitize_string(val: Optional[str]) -> str:
    """Trim string and return empty string for None or whitespace-only inputs."""
    if not val:
        return ""
    s = str(val).strip()
    return s if s and s.lower() != "null" and s.lower() != "none" else ""


# Bullet glyphs and stray dashes prefix pattern
STRAY_BULLET_PREFIX_RE = re.compile(
    r"^[\s\u2022\u2023\u25e6\u2043\u2219\u25aa\u25ab\u25cf\u25cb\u25a0\u25a1\uf0a7\uf0b7\u25ba\u25c4\*\-\–\—\.]+\s*"
)


def sanitize_bullet_point(val: Optional[str]) -> str:
    """
    Strip leading bullet characters (e.g. '•', '*', '-', '–'), stray dashes,
    and whitespace from extracted bullet strings.
    """
    if not val:
        return ""
    s = str(val).strip()
    s = STRAY_BULLET_PREFIX_RE.sub("", s).strip()
    return s if s and s.lower() not in ("null", "none") else ""


def deduplicate_list(items: List[str], is_bullets: bool = False) -> List[str]:
    """Deduplicate a list of strings while preserving order and stripping bullet prefixes."""
    seen = set()
    result = []
    for item in items:
        cleaned = sanitize_bullet_point(item) if is_bullets else sanitize_string(item)
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            result.append(cleaned)
    return result



def validate_and_sanitize_resume(resume: ResumeData, raw_text: str = "") -> ResumeData:
    """
    Master validation and sanitization entry point.
    Mutates/returns a clean, non-hallucinated, schema-compliant ResumeData object.
    """
    # 1. Personal Information Validation
    p = resume.personal
    p.name = sanitize_string(p.name)
    p.email = validate_email(p.email, raw_text)
    p.phone = validate_phone(p.phone, raw_text)
    p.location = sanitize_string(p.location)
    p.linkedin = validate_url(p.linkedin)
    p.github = validate_url(p.github)
    p.website = validate_url(p.website)
    p.portfolio = validate_url(p.portfolio)

    # 2. Headline & Summary
    resume.headline = sanitize_string(resume.headline)
    resume.summary = sanitize_string(resume.summary)

    # 3. Categorize & Deduplicate Skills
    resume.skills = categorize_skills(resume.skills)

    # 4. Experience Entries Validation & ID Assignment
    clean_exp: List[ExperienceEntry] = []
    for i, exp in enumerate(resume.experience, start=1):
        company = sanitize_string(exp.company)
        role = sanitize_string(exp.role)
        if not company and not role and not exp.bullets:
            continue  # Skip empty entries
        
        exp.id = exp.id or f"exp_{i}"
        exp.company = company
        exp.role = role
        exp.location = sanitize_string(exp.location)
        exp.start_date = sanitize_string(exp.start_date)
        exp.end_date = sanitize_string(exp.end_date)
        if exp.end_date.lower() in ("present", "current", "now"):
            exp.end_date = "Present"
            exp.is_current = True
        exp.bullets = deduplicate_list(exp.bullets, is_bullets=True)
        exp.technologies = deduplicate_list(exp.technologies)
        clean_exp.append(exp)
    resume.experience = clean_exp

    # 5. Project Entries Validation & ID Assignment
    clean_proj: List[ProjectEntry] = []
    for i, proj in enumerate(resume.projects, start=1):
        name = sanitize_string(proj.name)
        if not name and not proj.description and not proj.bullets:
            continue
        
        proj.id = proj.id or f"proj_{i}"
        proj.name = name
        proj.description = sanitize_string(proj.description)
        proj.url = validate_url(proj.url)
        proj.github_url = validate_url(proj.github_url)
        proj.bullets = deduplicate_list(proj.bullets, is_bullets=True)
        proj.technologies = deduplicate_list(proj.technologies)

        proj.start_date = sanitize_string(proj.start_date)
        proj.end_date = sanitize_string(proj.end_date)
        clean_proj.append(proj)
    resume.projects = clean_proj

    # 6. Education Entries Validation & ID Assignment
    clean_edu: List[EducationEntry] = []
    for i, edu in enumerate(resume.education, start=1):
        institution = sanitize_string(edu.institution)
        degree = sanitize_string(edu.degree)
        if not institution and not degree:
            continue
        
        edu.id = edu.id or f"edu_{i}"
        edu.institution = institution
        edu.degree = degree
        edu.field_of_study = sanitize_string(edu.field_of_study)
        edu.location = sanitize_string(edu.location)
        edu.start_date = sanitize_string(edu.start_date)
        edu.end_date = sanitize_string(edu.end_date)
        edu.gpa = sanitize_string(edu.gpa)
        edu.honors = sanitize_string(edu.honors)
        edu.relevant_courses = deduplicate_list(edu.relevant_courses)
        clean_edu.append(edu)
    resume.education = clean_edu

    # 7. Certifications
    clean_cert: List[CertificationEntry] = []
    for i, cert in enumerate(resume.certifications, start=1):
        c_name = sanitize_string(cert.name)
        if not c_name:
            continue
        cert.id = cert.id or f"cert_{i}"
        cert.name = c_name
        cert.issuer = sanitize_string(cert.issuer)
        cert.date = sanitize_string(cert.date)
        cert.url = validate_url(cert.url)
        cert.expiry = sanitize_string(cert.expiry)
        clean_cert.append(cert)
    resume.certifications = clean_cert

    # 8. Achievements
    clean_ach: List[AchievementEntry] = []
    for i, ach in enumerate(resume.achievements, start=1):
        title = sanitize_string(ach.title)
        desc = sanitize_string(ach.description)
        if not title and not desc:
            continue
        ach.id = ach.id or f"ach_{i}"
        ach.title = title or desc[:50]
        ach.description = desc
        ach.date = sanitize_string(ach.date)
        clean_ach.append(ach)
    resume.achievements = clean_ach

    # 9. Languages
    clean_lang: List[LanguageEntry] = []
    seen_langs = set()
    for lang in resume.languages:
        l_name = sanitize_string(lang.language)
        if l_name and l_name.lower() not in seen_langs:
            seen_langs.add(l_name.lower())
            lang.language = l_name
            lang.proficiency = sanitize_string(lang.proficiency) or "Native/Professional"
            clean_lang.append(lang)
    resume.languages = clean_lang

    return resume
