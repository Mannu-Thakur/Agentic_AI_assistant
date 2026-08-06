"""
app/resume/section_segmenter.py — Robust Resume Section Segmentation Engine.

Splits raw resume text into distinct named top-level section blocks:
  - personal / contact
  - summary
  - education
  - skills
  - experience
  - projects
  - achievements
  - certifications
  - languages
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple

# Top-level section header patterns (standalone lines or bold headers)
SECTION_HEADER_PATTERNS = [
    ("summary", re.compile(r"(?:\n|^)[ \t]*(?:PROFESSIONAL\s+SUMMARY|SUMMARY|PROFILE|OBJECTIVE|ABOUT\s+ME)[ \t]*(?::|\n|$)", re.I)),
    ("education", re.compile(r"(?:\n|^)[ \t]*(?:EDUCATION|ACADEMIC\s+BACKGROUND|QUALIFICATIONS|ACADEMICS)[ \t]*(?::|\n|$)", re.I)),
    ("skills", re.compile(r"(?:\n|^)[ \t]*(?:TECHNICAL\s+SKILLS|TECHNICALSKILLS|SKILLS|TECHNOLOGIES|CORE\s+COMPETENCIES)[ \t]*(?::|\n|$)", re.I)),
    ("experience", re.compile(r"(?:\n|^)[ \t]*(?:WORK\s+EXPERIENCE|WORKEXPERIENCE|EXPERIENCE|PROFESSIONAL\s+EXPERIENCE|EMPLOYMENT\s+HISTORY|INTERNSHIPS)[ \t]*(?::|\n|$)", re.I)),
    ("projects", re.compile(r"(?:\n|^)[ \t]*(?:PROJECTS|KEY\s+PROJECTS|PERSONAL\s+PROJECTS)[ \t]*(?::|\n|$)", re.I)),
    ("achievements", re.compile(r"(?:\n|^)[ \t]*(?:ACHIEVEMENTS|ACCOMPLISHMENTS|HONORS\s*&\s*AWARDS|AWARDS|COMPETITIVE\s+PROGRAMMING)[ \t]*(?::|\n|$)", re.I)),
    ("certifications", re.compile(r"(?:\n|^)[ \t]*(?:CERTIFICATIONS|CERTIFICATES|LICENSES)[ \t]*(?::|\n|$)", re.I)),
    ("languages", re.compile(r"(?:\n|^)[ \t]*(?:LANGUAGES\s+SPOKEN|FOREIGN\s+LANGUAGES)[ \t]*(?::|\n|$)", re.I)),
]


def segment_resume_sections(text: str) -> Dict[str, str]:
    """
    Segment resume raw text into distinct section blocks by detecting section header boundaries.
    Returns dict mapping section_key -> section_text.
    """
    sections: Dict[str, str] = {
        "personal": "",
        "summary": "",
        "education": "",
        "skills": "",
        "experience": "",
        "projects": "",
        "achievements": "",
        "certifications": "",
        "languages": "",
    }

    if not text:
        return sections

    # Find all section header match positions in text
    matches: List[Tuple[int, int, str]] = []  # (start_idx, end_idx, section_key)
    for sec_key, pattern in SECTION_HEADER_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), sec_key))

    # Sort matches by character position in document
    matches.sort(key=lambda x: x[0])

    # Filter out overlapping matches
    filtered_matches: List[Tuple[int, int, str]] = []
    for m in matches:
        if not filtered_matches:
            filtered_matches.append(m)
        else:
            prev = filtered_matches[-1]
            if m[0] >= prev[1]:  # Non-overlapping
                filtered_matches.append(m)

    if not filtered_matches:
        # No section headers found; put all text in summary
        sections["summary"] = text.strip()
        return sections

    # Personal info is everything before the first section header
    first_start = filtered_matches[0][0]
    sections["personal"] = text[:first_start].strip()

    # Extract text between consecutive section headers
    for i, (start_idx, end_idx, sec_key) in enumerate(filtered_matches):
        next_start = filtered_matches[i + 1][0] if i + 1 < len(filtered_matches) else len(text)
        content = text[end_idx:next_start].strip()
        content = re.sub(r"^[:\-\s]+", "", content).strip()
        
        if sections[sec_key]:
            sections[sec_key] += "\n" + content
        else:
            sections[sec_key] = content

    return sections
