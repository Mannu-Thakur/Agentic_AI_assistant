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

# Prefix matching line start/newline, optional spaces, markdown #/bold/bullet/numbering tags
_HEADER_PREFIX = r"(?:^|\n)[ \t]*(?:[#*\-_•\u2022]+[ \t]*)*(?:\d+\.|\w\.)?[ \t]*\**[ \t]*"
# Postfix matching trailing bold tags, optional colon, and lookahead to line end/newline
_HEADER_POSTFIX = r"[ \t]*\**[ \t]*(?::[ \t]*$|:?[ \t]*(?=\n|$))"

# Top-level section header patterns (standalone lines, markdown headers, or bold headers)
SECTION_HEADER_PATTERNS = [
    ("summary", re.compile(_HEADER_PREFIX + r"(?:PROFESSIONAL\s+SUMMARY|SUMMARY\s+OF\s+QUALIFICATIONS|EXECUTIVE\s+SUMMARY|CAREER\s+SUMMARY|SUMMARY|PROFILE|PROFESSIONAL\s+PROFILE|OBJECTIVE|CAREER\s+OBJECTIVE|ABOUT\s+ME|OVERVIEW)" + _HEADER_POSTFIX, re.I)),
    ("education", re.compile(_HEADER_PREFIX + r"(?:EDUCATION\s+AND\s+TRAINING|EDUCATION\s+&\s+QUALIFICATIONS|EDUCATIONAL\s+BACKGROUND|ACADEMIC\s+BACKGROUND|ACADEMIC\s+QUALIFICATIONS|QUALIFICATIONS|EDUCATION|ACADEMICS)" + _HEADER_POSTFIX, re.I)),
    ("skills", re.compile(_HEADER_PREFIX + r"(?:TECHNICAL\s+SKILLS|TECHNICALSKILLS|SKILLS\s+&\s+EXPERTISE|SKILLS\s+&\s+TECHNOLOGIES|SKILLS\s+/\s+TECHNOLOGIES|TOOLS\s+&\s+TECHNOLOGIES|TOOLS\s+AND\s+TECHNOLOGIES|CORE\s+COMPETENCIES|TECHNICAL\s+PROFICIENCIES|AREAS\s+OF\s+EXPERTISE|TECHNICAL\s+SUMMARY|SKILLS)" + _HEADER_POSTFIX, re.I)),
    ("experience", re.compile(_HEADER_PREFIX + r"(?:WORK\s+EXPERIENCE|WORKEXPERIENCE|PROFESSIONAL\s+EXPERIENCE|EMPLOYMENT\s+HISTORY|RELEVANT\s+EXPERIENCE|CAREER\s+HISTORY|WORK\s+HISTORY|EXPERIENCE|EMPLOYMENT|INTERNSHIPS)" + _HEADER_POSTFIX, re.I)),
    ("projects", re.compile(_HEADER_PREFIX + r"(?:KEY\s+PROJECTS|PERSONAL\s+PROJECTS|ACADEMIC\s+PROJECTS|FEATURED\s+PROJECTS|TECHNICAL\s+PROJECTS|RELEVANT\s+PROJECTS|PROJECTS)" + _HEADER_POSTFIX, re.I)),
    ("achievements", re.compile(_HEADER_PREFIX + r"(?:ACHIEVEMENTS|ACCOMPLISHMENTS|HONORS\s*&\s*AWARDS|HONORS\s+AND\s+AWARDS|AWARDS\s*&\s*ACHIEVEMENTS|AWARDS|HONORS|COMPETITIVE\s+PROGRAMMING|KEY\s+ACHIEVEMENTS)" + _HEADER_POSTFIX, re.I)),
    ("certifications", re.compile(_HEADER_PREFIX + r"(?:CERTIFICATIONS\s+&\s+LICENSES|LICENSES\s+&\s+CERTIFICATIONS|PROFESSIONAL\s+CERTIFICATIONS|CERTIFICATIONS|CERTIFICATES|LICENSES)" + _HEADER_POSTFIX, re.I)),
    ("languages", re.compile(_HEADER_PREFIX + r"(?:LANGUAGES\s+SPOKEN|FOREIGN\s+LANGUAGES|LANGUAGE\s+PROFICIENCY|LANGUAGES)" + _HEADER_POSTFIX, re.I)),
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
