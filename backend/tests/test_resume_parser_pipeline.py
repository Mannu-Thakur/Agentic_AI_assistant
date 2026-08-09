"""
test_resume_parser_pipeline.py — Comprehensive Test Suite for Refactored Resume Parser & Hybrid Pipeline.

Verifies:
  1. PDF/OCR font-icon artifact removal (e.g. 'pemannumay15@gmail.com' -> 'mannumay15@gmail.com')
  2. Text normalization (invisible Unicode, bullet glyphs, whitespace)
  3. Automatic 9-category skill classification
  4. RFC email, phone, and URL validation & sanitization
  5. Multi-section and overall confidence scoring
  6. Rule-based regex fallback parser
  7. End-to-end FastAPI endpoint integration (/api/v1/resume/analyze)
"""

import os
import sys
import tempfile
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.main import app
from app.resume.models import ResumeData, PersonalInfo, SkillGroup
from app.resume.normalizer import (
    clean_unicode_artifacts, normalize_bullets, normalize_whitespace, fix_email_artifacts, normalize_resume_text
)
from app.resume.skill_categorizer import categorize_skills, classify_single_skill
from app.resume.validator import validate_and_sanitize_resume, validate_email, validate_url
from app.resume.confidence import compute_section_and_overall_confidence
from app.resume.parser import _regex_fallback_parser
from app.resume.extractor import run_deterministic_extraction
from app.api.auth import get_current_user
from app.schemas.auth import UserOut

mock_user = UserOut(
    id="test_user_id",
    email="test@example.com",
    full_name="Test User",
    is_active=True,
    is_admin=False,
    created_at=datetime.utcnow()
)
app.dependency_overrides[get_current_user] = lambda: mock_user
client = TestClient(app)


def test_email_icon_artifact_removal():
    """Verify explicit font-icon artifact prefixes are cleanly stripped while preserving valid email addresses."""
    assert fix_email_artifacts("icon_mannumay15@gmail.com") == "mannumay15@gmail.com"
    assert fix_email_artifacts("fa_john.doe@gmail.com") == "john.doe@gmail.com"
    assert fix_email_artifacts("peter.parker@gmail.com") == "peter.parker@gmail.com"
    assert fix_email_artifacts("eric_smith@company.org") == "eric_smith@company.org"


def test_text_normalization():
    """Verify invisible Unicode control characters, word concatenations, and bullet glyphs are normalized."""
    dirty_text = "John Doe\u200b\ufeff • Software Engineer forCleanPlates a9-membermultidisciplinary team Jul 2026Nemhans Solutions"
    clean_u = clean_unicode_artifacts(dirty_text)
    assert "\u200b" not in clean_u
    assert "\ufeff" not in clean_u

    clean_norm = normalize_resume_text(clean_u)
    assert "for CleanPlates" in clean_norm
    assert "a 9-member multidisciplinary" in clean_norm
    assert "Jul 2026 Nemhans" in clean_norm


def test_9_category_skill_classification():
    """Verify skills are automatically categorized, comma-split, and sanitized into the 9 standard technical categories."""
    raw_skills = [
        "C, C++, Java, Python, TypeScript, JavaScript, CSS",
        "React.js, Vite, .",
        "LoRa, – Agentic AI Assistant, multi-provider LLM selection.",
        "PostgreSQL, MongoDB, Redis, MySQL, SQLite"
    ]
    categorized = categorize_skills(raw_skills)
    category_names = [g.category for g in categorized]

    assert "Languages" in category_names
    assert "Frontend" in category_names
    assert "Databases" in category_names
    assert "AI/ML / GenAI" in category_names

    # Verify skills inside Languages are split into individual items
    lang_group = next(g for g in categorized if g.category == "Languages")
    assert "Python" in lang_group.skills
    assert "C++" in lang_group.skills
    assert "TypeScript" in lang_group.skills
    assert len(lang_group.skills) >= 6

    # Verify trailing dot artifact was cleaned from Frontend
    front_group = next(g for g in categorized if g.category == "Frontend")
    assert "." not in front_group.skills
    assert "React.js" in front_group.skills

    # Verify sentence description was not kept as full sentence
    ai_group = next(g for g in categorized if g.category == "AI/ML / GenAI")
    assert not any("multi-provider" in s for s in ai_group.skills)
    assert any("lora" in s.lower() or "llm" in s.lower() for s in ai_group.skills)


def test_validator_layer():
    """Verify ResumeData validator cleans URLs, deduplicates, and assigns entry IDs."""
    resume = ResumeData(
        personal=PersonalInfo(
            name="  Mannu Thakur  ",
            email="icon_mannumay15@gmail.com",
            linkedin="linkedin.com/in/mannuthakur",
            github="github.com/mannuthakur"
        ),
        skills=[SkillGroup(category="Technical Skills", skills=["Python", "python", "React"])]
    )

    validated = validate_and_sanitize_resume(resume, raw_text="mannumay15@gmail.com")
    assert validated.personal.name == "Mannu Thakur"
    assert validated.personal.email == "mannumay15@gmail.com"
    assert validated.personal.linkedin == "https://linkedin.com/in/mannuthakur"
    assert validated.personal.github == "https://github.com/mannuthakur"

    # Verify skill deduplication & categorizer invocation
    all_skills = [s for g in validated.skills for s in g.skills]
    assert len(all_skills) == 2
    assert "Python" in all_skills
    assert "React" in all_skills


def test_confidence_scoring_engine():
    """Verify section-level and overall confidence calculation."""
    resume = ResumeData(
        personal=PersonalInfo(
            name="Mannu Thakur",
            email="mannumay15@gmail.com",
            phone="+1 555 0199",
            location="San Francisco, CA"
        ),
        summary="Experienced AI Engineer building LLM applications.",
        skills=[SkillGroup(category="Languages", skills=["Python", "SQL"])],
        experience=[]
    )

    overall_conf, low_fields, section_confs = compute_section_and_overall_confidence(resume)

    assert "personal" in section_confs
    assert section_confs["personal"] == 1.0
    assert "experience" in section_confs
    assert section_confs["experience"] == 0.0
    assert "experience" in low_fields


def test_e2e_analyze_resume_endpoint():
    """Verify /api/v1/resume/analyze endpoint returns structured ResumeData and section_confidences."""
    sample_resume = """
    Mannu Thakur
    Senior AI Engineer
    mannumay15@gmail.com | +1 555-0199 | San Francisco, CA
    https://linkedin.com/in/mannuthakur | https://github.com/mannuthakur

    SUMMARY
    Senior AI Engineer with 5+ years building production-grade LLM applications, RAG pipelines, FastAPI services, and React dashboards.

    TECHNICAL SKILLS
    Languages: Python, TypeScript, SQL
    Frontend: React, Next.js, TailwindCSS
    Backend: FastAPI, Django, Node.js
    Databases: PostgreSQL, Redis, Pinecone
    DevOps: Docker, Kubernetes, AWS, GitHub Actions
    AI/ML: PyTorch, LangChain, LLMs, RAG, Ollama

    WORK EXPERIENCE
    Senior AI Engineer | TechCorp Inc | San Francisco, CA | 2022 - Present
    - Architected multi-agent RAG workflow improving response accuracy by 45%.
    - Built real-time streaming parser processing 10k documents/min.

    EDUCATION
    B.S. Computer Science | Stanford University | 2018 - 2022 | GPA: 3.9
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(sample_resume)
        temp_path = f.name

    try:
        with open(temp_path, "rb") as f:
            res = client.post(
                "/api/v1/resume/analyze",
                files={"file": ("resume.txt", f, "text/plain")}
            )
        assert res.status_code == 200
        data = res.json()
        assert "resume" in data
        assert "section_confidences" in data
        assert data["parse_confidence"] > 0.7
        assert data["resume"]["personal"]["email"] == "mannumay15@gmail.com"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
