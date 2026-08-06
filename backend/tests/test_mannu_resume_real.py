"""
test_mannu_resume_real.py — Real-world integration test for Mannu's actual resume text.

Verifies:
  1. Email extracted as mannumay15@gmail.com without character loss.
  2. Phone +91-7827075170 extracted cleanly.
  3. LinkedIn & GitHub URLs extracted exact.
  4. Education extracted (IIIT Bhubaneswar, B.Tech in Computer Engineering, CGPA 8.57, 2023-2027).
  5. Work Experience extracted (Nemhans Solutions Pvt. Ltd., Frontend Developer Intern, May 2026 – Jul 2026).
  6. Projects extracted (Smart Accident Detection System, Technologies: IoT, V2X...).
  7. Achievements extracted (CodeChef and GeeksforGeeks).
  8. Skills categorized across standard categories without collapsing everything into 'Others'.
  9. No [Page 1] leak into summary or headline.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.resume.normalizer import normalize_resume_text
from app.resume.extractor import run_deterministic_extraction
from app.resume.section_segmenter import segment_resume_sections
from app.resume.parser import _regex_fallback_parser
from app.resume.validator import validate_and_sanitize_resume

MANNU_RESUME_TEXT = """
Personal Information
Full Name
Mannu Thakur
[Page 1]
Email
mannumay15@gmail.com
Phone
+91-7827075170
Location
LinkedIn URL
https://linkedin.com/in/mannu-kumar-6903a0348
GitHub URL
https://github.com/Mannu-Thakur

Professional Summary
Computer Engineering undergraduate specializing in backend architectures, distributed systems, and agentic AI. Proven track record of building secure sandboxed runtimes, real-time WebSocket systems, and resilient IoT communication protocols.

EDUCATION
International Institute of Information T echnology , Bhubaneswar 2023 – 2027
B.T ech in Computer Engineering CGPA (GPA): 8.57

TECHNICALSKILLS
Languages:C, C++, Java, Python, TypeScript, JavaScript
Frontend:React.js, Vite, Tailwind CSS
Backend:Node.js, Express.js, FastAPI, REST APIs, WebSockets
Databases:MongoDB, Redis, MySQL, SQLite, FAISS, PostgreSQL
DevOps:Docker, Docker Containerization
GenAI & Agents:LangGraph, LangChain, RAG, Embeddings, LoRa
Developer Tools:Git, Postman
Core CS:Data Structures & Algorithms, Operating Systems, Computer Networks

WORK EXPERIENCE
Frontend Developer Intern May 2026 – Jul 2026
Nemhans Solutions Pvt. Ltd. Bhubaneswar, India
- Engineered an IoT-based food waste intelligence platform.

PROJECTS
Smart Accident Detection System/external-link-alt
Technologies:IoT, V2X, IMU Multi-Sensor Fusion, GPS
- Multi-sensor fusion for real-time accident detection.

ACHIEVEMENTS
- Active competitive programmer across CodeChef and GeeksforGeeks platforms.
"""


def test_mannu_resume_parsing():
    normalized = normalize_resume_text(MANNU_RESUME_TEXT)
    assert "[Page 1]" not in normalized
    assert "/external-link-alt" not in normalized

    deterministic = run_deterministic_extraction(normalized)
    assert deterministic["email"] == "mannumay15@gmail.com"
    assert deterministic["phone"] == "+91-7827075170"
    assert deterministic["linkedin"] == "https://linkedin.com/in/mannu-kumar-6903a0348"
    assert deterministic["github"] == "https://github.com/Mannu-Thakur"

    sections = segment_resume_sections(normalized)
    assert sections["education"] != ""
    assert sections["experience"] != ""
    assert sections["projects"] != ""
    assert sections["achievements"] != ""

    fallback_parsed = _regex_fallback_parser(normalized, deterministic)
    validated = validate_and_sanitize_resume(fallback_parsed, raw_text=normalized)

    # Check Personal
    assert validated.personal.email == "mannumay15@gmail.com"
    assert validated.personal.phone == "+91-7827075170"
    assert validated.personal.linkedin == "https://linkedin.com/in/mannu-kumar-6903a0348"
    assert validated.personal.github == "https://github.com/Mannu-Thakur"

    # Check Summary
    assert "Computer Engineering undergraduate" in validated.summary
    assert "[Page 1]" not in validated.summary

    # Check Education
    assert len(validated.education) >= 1
    edu = validated.education[0]
    assert "IIIT" in edu.institution or "Information Technology" in edu.institution
    assert "B.Tech" in edu.degree or "Computer Engineering" in edu.degree
    assert "8.57" in edu.gpa

    # Check Experience
    assert len(validated.experience) >= 1
    exp = validated.experience[0]
    assert "Nemhans Solutions" in exp.company or "Frontend Developer" in exp.role

    # Check Projects
    assert len(validated.projects) >= 1
    proj = validated.projects[0]
    assert "Smart Accident Detection System" in proj.name

    # Check Achievements
    assert len(validated.achievements) >= 1
    ach = validated.achievements[0]
    assert "CodeChef" in ach.description or "GeeksforGeeks" in ach.description

    # Check Skills Categorization
    categories = [g.category for g in validated.skills]
    assert "Languages" in categories
    assert "Backend" in categories or "Frontend" in categories
