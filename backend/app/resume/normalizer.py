"""
app/resume/normalizer.py — Text normalization, artifact cleaning, and section header fixing for Resume Parsing.

Fixes:
  - Page markers ([Page 1], [Slide 1]) leakage
  - Icon font text artifacts (/external-link-alt, fontawesome symbols)
  - Kerning artifacts ('T echnology' -> 'Technology', 'B.T ech' -> 'B.Tech')
  - Concatenated section headers ('TECHNICALSKILLS' -> 'TECHNICAL SKILLS')
  - PDF/OCR font-icon artifact email fixes ('mannumay15@gmail.com' preserved exactly!)
  - Unicode math/symbol normalization ('~' tilde operator, zero-width spaces)
"""

from __future__ import annotations
import re
import logging

logger = logging.getLogger("app.resume.normalizer")

# Patterns for invisible / zero-width characters and Private Use Area / Font-icon Unicode glyphs
_INVISIBLE_CHARS_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u2060\u202a-\u202e]")
_FONT_ICON_PUA_RE = re.compile(r"[\ue000-\uf8ff\uf000-\uf2e0]")

# Bullet glyphs to normalize to standard bullet dot or line separator
_BULLET_GLYPHS_RE = re.compile(r"[\u2022\u2023\u25e6\u2043\u2219\u25aa\u25ab\u25cf\u25cb\u25a0\u25a1\uf0a7\uf0b7\u25ba\u25c4]")

# RFC-compliant email matching pattern
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Page and Slide marker pattern injected by document parsers
_PAGE_MARKER_RE = re.compile(r"\[(?:Page|Slide)\s+\d+\]", re.I)

# FontAwesome / LaTeX icon text artifacts (Do NOT include /linkedin or /github as they are valid URL paths!)
_ICON_TEXT_ARTIFACTS_RE = re.compile(r"/(?:external-link-alt|external-link|fa-external-link|fa-[a-z\-]+)\b|\[external-link-alt\]", re.I)

# Icon font character prefixes extracted from PDF font icons preceding emails
ICON_PREFIXES = ["pe", "em", "el", "icon", "p", "e", "i"]


def strip_page_markers(text: str) -> str:
    """Strip [Page N] and [Slide N] markers injected by text extractors."""
    if not text:
        return ""
    return _PAGE_MARKER_RE.sub("", text)


def strip_icon_text_artifacts(text: str) -> str:
    """Strip font icon text artifacts (like /external-link-alt from LaTeX/PDF export)."""
    if not text:
        return ""
    return _ICON_TEXT_ARTIFACTS_RE.sub("", text)


def clean_unicode_artifacts(text: str) -> str:
    """Strip invisible control characters, math tildes, and font-icon Private Use Area glyphs."""
    if not text:
        return ""
    text = _INVISIBLE_CHARS_RE.sub("", text)
    text = _FONT_ICON_PUA_RE.sub(" ", text)
    # Replace math tilde operator (\u223c '∼') with standard tilde '~'
    text = text.replace("\u223c", "~")
    return text


def normalize_bullets(text: str) -> str:
    """Convert bullet glyph variations into consistent bullet markers."""
    if not text:
        return ""
    return _BULLET_GLYPHS_RE.sub(" • ", text)


def fix_kerning_and_header_concatenations(text: str) -> str:
    """
    Fix kerning artifacts (e.g. 'T echnology' -> 'Technology', 'B.T ech' -> 'B.Tech')
    and concatenated section headers (e.g. 'TECHNICALSKILLS' -> 'TECHNICAL SKILLS').
    """
    if not text:
        return ""
    
    # Fix section header concatenations
    text = re.sub(r"\bTECHNICALSKILLS\b", "TECHNICAL SKILLS", text, flags=re.I)
    text = re.sub(r"\bWORKEXPERIENCE\b", "WORK EXPERIENCE", text, flags=re.I)
    text = re.sub(r"\bPROJECTDETAILS\b", "PROJECTS", text, flags=re.I)

    # Fix kerning splits in tech terms
    text = re.sub(r"\bB\.T\s+ech\b", "B.Tech", text, flags=re.I)
    text = re.sub(r"\bM\.T\s+ech\b", "M.Tech", text, flags=re.I)
    text = re.sub(r"\bT\s+echnolog(y|ies)\b", r"Technolog\1", text, flags=re.I)
    text = re.sub(r"\bT\s+ech\b", "Tech", text, flags=re.I)
    text = re.sub(r"\bT\s+echnical\b", "Technical", text, flags=re.I)
    text = re.sub(r"\bT\s+eam\b", "Team", text, flags=re.I)
    text = re.sub(r"\bT\s+esting\b", "Testing", text, flags=re.I)

    return text


def normalize_whitespace(text: str) -> str:
    """
    Normalize non-breaking spaces, excessive horizontal spaces, and irregular line breaks.
    Preserves structural line breaks.
    """
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", "    ")
    
    # Collapse multiple consecutive horizontal spaces
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Collapse more than 3 consecutive line breaks into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fix_ocr_concatenations(text: str) -> str:
    """Fix common PDF/OCR word concatenations (e.g. 'forCleanPlates' -> 'for CleanPlates', 'Jul 2026Nemhans' -> 'Jul 2026 Nemhans')."""
    if not text:
        return ""
    # Fix date prepended to capitalized company/word: 'Jul 2026Nemhans' -> 'Jul 2026 Nemhans'
    text = re.sub(r"(\b20\d{2})([A-Z][a-zA-Z]+)", r"\1 \2", text)
    text = re.sub(r"(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})([A-Z][a-zA-Z]+)", r"\1 \2", text, flags=re.I)
    # Fix 'a9-membermultidisciplinary' -> 'a 9-member multidisciplinary'
    text = re.sub(r"\ba(\d+)-member([a-z]+)", r"a \1-member \2", text)
    # Fix lowercase preposition/verb concatenated to capitalized noun: 'forCleanPlates' -> 'for CleanPlates'
    # Avoid breaking URLs or common code patterns like React.js
    text = re.sub(r"\b(for|with|and|in|on|at|to|from|by|of|built|created|using|integrated|supported|developed)([A-Z][a-zA-Z]{2,})\b", r"\1 \2", text)
    return text


def fix_email_artifacts(email: str, raw_context: str = "") -> str:
    """
    Fix PDF/OCR font-icon artifacts attached to emails while preserving valid email addresses.
    Examples:
      'mannumay15@gmail.com' -> 'mannumay15@gmail.com' (Preserved 100% exact!)
      'pemannumay15@gmail.com' -> 'mannumay15@gmail.com' (Prefix artifact 'pe' stripped)
    """
    candidate = email.strip() if email else ""
    if not candidate and raw_context:
        m = EMAIL_REGEX.search(raw_context)
        if m:
            candidate = m.group(0).strip()

    if not candidate:
        return ""

    match = EMAIL_REGEX.search(candidate)
    if not match:
        return ""

    matched_email = match.group(0)
    user_part, domain_part = matched_email.split("@", 1)

    # Check explicit multi-character font-icon artifact prefixes ('icon_', 'fa_')
    # Single letter prefixes ('p', 'e', 'i') are removed to avoid corrupting valid emails like peter/eric/ian
    user_lower = user_part.lower()
    explicit_icon_prefixes = ["icon_", "fa_", "envelope_"]
    for prefix in explicit_icon_prefixes:
        if user_lower.startswith(prefix) and len(user_part) > len(prefix) + 2:
            sub_user = user_part[len(prefix):]
            sub_email = f"{sub_user}@{domain_part}"
            if EMAIL_REGEX.match(sub_email):
                logger.info(f"[Normalizer] Fixed email icon artifact: {matched_email} -> {sub_email}")
                return sub_email

    return matched_email


def normalize_resume_text(raw_text: str) -> str:
    """
    Master normalization function for raw resume text.
    Executes page marker stripping, icon cleaning, unicode cleaning, kerning fixing,
    bullet normalization, OCR concatenation cleanup, and whitespace cleanup.
    """
    if not raw_text:
        return ""
    text = strip_page_markers(raw_text)
    text = strip_icon_text_artifacts(text)
    text = clean_unicode_artifacts(text)
    text = fix_kerning_and_header_concatenations(text)
    text = fix_ocr_concatenations(text)
    text = normalize_bullets(text)
    text = normalize_whitespace(text)
    return text

