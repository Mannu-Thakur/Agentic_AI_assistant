"""
test_resume_builder_realtime.py — Comprehensive Real-time Verification for AI Resume Builder

Tests every endpoint and subsystem in real time:
1. Health check
2. Resume file analysis (Parsing PDF / TXT via Parser & LLM)
3. Job Description (JD) real-time extraction via LLM
4. Algorithmic ATS scoring computation
5. Real-time AI Resume Tailoring (Summary, Skills, Experience) via LLM
6. Word-level GitHub-style diff computation
7. One-click AI suggestion application via LLM
8. Resume Export (PDF, DOCX, Markdown, JSON) binary output generation
"""

import os
import sys
import tempfile
from datetime import datetime
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.main import app
from app.resume.models import ResumeData
from app.api.auth import get_current_user
from app.schemas.auth import UserOut

# Override auth dependency for test client
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

def _run_health_check():
    res = client.get("/api/v1/resume/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["module"] == "ai_resume_builder"

def _run_analyze_resume():
    sample_resume = """
    John Doe
    Software Engineer
    john.doe@example.com | +1 555-0199 | San Francisco, CA
    https://linkedin.com/in/johndoe | https://github.com/johndoe

    SUMMARY
    Results-driven Software Engineer with 5 years of experience in Python, FastAPI, React, and AWS cloud infrastructure.

    TECHNICAL SKILLS
    Languages: Python, TypeScript, SQL, HTML/CSS
    Frameworks: FastAPI, Django, React, Next.js
    Cloud & Tools: AWS, Docker, Git, PostgreSQL, Redis

    WORK EXPERIENCE
    Senior Software Engineer | TechCorp Inc | San Francisco, CA | 2022 - Present
    - Spearheaded microservices migration reducing API latency by 40%.
    - Built real-time WebSocket dashboard handling 50k active users.
    - Mentored 4 junior engineers and conducted technical interviews.
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
        return data["resume"]
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def _run_analyze_jd():
    jd_text = """
    Senior Full-Stack AI Engineer
    Company: CloudInnovate AI
    Location: Remote
    Experience: 4+ years

    Required Skills:
    - 4+ years experience with Python, FastAPI, PyDantic, and AsyncIO.
    - Expertise in React, TypeScript, and modern frontend state management.
    - Hands-on experience with LLMs, RAG pipelines, and Vector DBs.
    - Experience with Docker, Kubernetes, AWS, and CI/CD pipelines.
    """

    res = client.post(
        "/api/v1/resume/analyze-jd",
        json={"jd_text": jd_text}
    )
    assert res.status_code == 200
    data = res.json()
    return data["jd_analysis"]

def _run_compute_ats(resume_data, jd_analysis):
    res = client.post(
        "/api/v1/resume/ats",
        json={"resume": resume_data, "jd_analysis": jd_analysis}
    )
    assert res.status_code == 200
    data = res.json()
    score = data["score"]
    assert "overall" in score
    assert 0 <= score["overall"] <= 100
    return score

def _run_tailor(resume_data, jd_analysis):
    res = client.post(
        "/api/v1/resume/tailor",
        json={
            "resume": resume_data,
            "jd_analysis": jd_analysis,
            "section": "all",
            "style": "quantify"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert "tailored_resume" in data
    return data["tailored_resume"]

def _run_diff(original_resume, tailored_resume):
    res = client.post(
        "/api/v1/resume/diff",
        json={
            "original": original_resume,
            "tailored": tailored_resume
        }
    )
    assert res.status_code == 200
    diff = res.json()
    assert "change_percentage" in diff

def _run_suggest(resume_data, jd_analysis):
    res = client.post(
        "/api/v1/resume/suggest",
        json={
            "resume": resume_data,
            "suggestion_type": "improve_action_verbs",
            "jd_analysis": jd_analysis
        }
    )
    assert res.status_code == 200
    sug = res.json()
    assert "updated_resume" in sug

def _run_export(resume_data):
    formats = ["pdf", "docx", "markdown", "json", "latex", "tex"]
    for fmt in formats:
        res = client.post(
            "/api/v1/resume/export",
            json={
                "resume": resume_data,
                "format": fmt,
                "template": "modern"
            }
        )
        assert res.status_code == 200
        assert len(res.content) > 0
        if fmt in ("latex", "tex"):
            tex_str = res.content.decode("utf-8")
            assert r"\usepackage{hyperref}" in tex_str
            assert r"\documentclass" in tex_str

    # Test LaTeX raw string preview endpoint
    res_preview = client.post(
        "/api/v1/resume/preview-latex",
        json={
            "resume": resume_data,
            "template": "modern"
        }
    )
    assert res_preview.status_code == 200
    preview_data = res_preview.json()
    assert "latex_code" in preview_data
    latex_code = preview_data["latex_code"]
    assert r"\usepackage{hyperref}" in latex_code
    assert r"\begin{document}" in latex_code

def test_full_resume_pipeline():
    _run_health_check()
    resume_data = _run_analyze_resume()
    jd_analysis = _run_analyze_jd()
    _run_compute_ats(resume_data, jd_analysis)
    tailored = _run_tailor(resume_data, jd_analysis)
    _run_diff(resume_data, tailored)
    _run_suggest(resume_data, jd_analysis)
    _run_export(tailored)


def test_tailor_empty_resume_populates_all_sections():
    empty_resume = ResumeData().model_dump()
    jd_analysis = {
        "role": "Senior Full Stack AI Engineer",
        "company": "CloudInnovate AI",
        "experience_level": "Senior",
        "required_skills": ["Python", "FastAPI", "React", "LangChain", "Kubernetes"],
        "technologies": ["PostgreSQL", "Redis", "Docker", "Terraform", "Pinecone"],
        "keywords": ["RAG", "Vector Search", "LLMs", "Microservices"]
    }

    res = client.post(
        "/api/v1/resume/tailor",
        json={
            "resume": empty_resume,
            "jd_analysis": jd_analysis,
            "section": "all",
            "style": "rewrite"
        }
    )
    assert res.status_code == 200
    data = res.json()
    tailored = data["tailored_resume"]

    assert tailored["headline"] != ""
    assert len(tailored["summary"]) > 20
    assert len(tailored["skills"]) >= 2
    assert len(tailored["experience"]) >= 1
    assert len(tailored["projects"]) >= 1
    assert len(tailored["education"]) >= 1


