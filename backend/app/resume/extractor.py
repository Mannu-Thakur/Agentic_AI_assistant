"""
app/resume/extractor.py — Deterministic Rule-Based Extraction Engine for Document AI.

Extracts core deterministic fields directly from text prior to LLM calls:
  - Email (RFC 5322 compliant with font-icon artifact removal)
  - Phone (International & domestic patterns)
  - LinkedIn & GitHub URLs
  - Web & Portfolio URLs
  - Date Ranges & Work Durations
  - Academic Metrics (CGPA, GPA, Marks, Percentages)
"""

from __future__ import annotations
import re
import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from app.resume.normalizer import EMAIL_REGEX, fix_email_artifacts

logger = logging.getLogger("app.resume.extractor")

# Deterministic Regex Patterns
PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+\d{10,14}\b"
)
LINKEDIN_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/([\w\-]+)", re.I
)
GITHUB_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([\w\-]+)", re.I
)
GENERIC_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?", re.I
)
DATE_RANGE_PATTERN = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\s*(?:-|–|—|to)\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\b\d{4}\s*(?:-|–|—|to)\s*(?:\d{4}|Present|Current)\b",
    re.I
)
GPA_CGPA_PATTERN = re.compile(
    r"\b(?:CGPA|GPA|Marks|Percentage)[:\s]*([0-9]\.[0-9]{1,2}(?:\s*/\s*[0-9](?:\.0)?)?|[1-9][0-9](?:\.[0-9]{1,2})?%?)\b",
    re.I
)


def extract_email_deterministic(text: str) -> str:
    """Extract email using RFC regex and artifact cleaning."""
    if not text:
        return ""
    match = EMAIL_REGEX.search(text)
    if match:
        raw_email = match.group(0)
        return fix_email_artifacts(raw_email, text)
    return ""


def extract_phone_deterministic(text: str) -> str:
    """Extract phone number using international/domestic regex."""
    if not text:
        return ""
    match = PHONE_PATTERN.search(text)
    if match:
        return match.group(0).strip()
    return ""


def extract_linkedin_deterministic(text: str) -> str:
    """Extract LinkedIn profile URL."""
    if not text:
        return ""
    match = LINKEDIN_PATTERN.search(text)
    if match:
        handle = match.group(1)
        return f"https://linkedin.com/in/{handle}"
    return ""


def extract_github_deterministic(text: str) -> str:
    """Extract GitHub profile URL."""
    if not text:
        return ""
    match = GITHUB_PATTERN.search(text)
    if match:
        handle = match.group(1)
        return f"https://github.com/{handle}"
    return ""


def extract_urls_deterministic(text: str) -> List[str]:
    """Extract all web URLs excluding LinkedIn and GitHub."""
    if not text:
        return []
    urls = []
    for match in GENERIC_URL_PATTERN.finditer(text):
        url = match.group(0).strip().rstrip(".,;)")
        if "linkedin.com" not in url and "github.com" not in url:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            try:
                parsed = urlparse(url)
                if parsed.netloc and "." in parsed.netloc:
                    urls.append(url)
            except Exception:
                pass
    return list(dict.fromkeys(urls))  # Order-preserving deduplication


def extract_cgpa_deterministic(text: str) -> str:
    """Extract CGPA, GPA, or percentage marks."""
    if not text:
        return ""
    match = GPA_CGPA_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return ""


def extract_date_ranges_deterministic(text: str) -> List[str]:
    """Extract experience and education date ranges."""
    if not text:
        return []
    matches = DATE_RANGE_PATTERN.findall(text)
    return [m.strip() for m in matches if m.strip()]


def run_deterministic_extraction(text: str) -> Dict[str, Any]:
    """
    Run full deterministic rule-based extraction pipeline on resume text.
    Returns dict containing deterministic findings.
    """
    return {
        "email": extract_email_deterministic(text),
        "phone": extract_phone_deterministic(text),
        "linkedin": extract_linkedin_deterministic(text),
        "github": extract_github_deterministic(text),
        "urls": extract_urls_deterministic(text),
        "gpa": extract_cgpa_deterministic(text),
        "date_ranges": extract_date_ranges_deterministic(text),
    }
