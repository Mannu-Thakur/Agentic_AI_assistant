"""
app/resume/jd_analyzer.py — Job Description structured extraction.

The JD is never forwarded raw to the LLM for tailoring.
It is first converted to a structured JDAnalysis object.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from app.resume.models import JDAnalysis
from app.resume.prompts import ANALYZE_JD_SYSTEM, ANALYZE_JD_USER

logger = logging.getLogger("app.resume.jd_analyzer")


async def analyze_job_description(
    jd_text: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> JDAnalysis:
    """
    Extract structured JDAnalysis from raw job description text.
    Returns a structured JDAnalysis object — never passes raw JD to tailoring.
    """
    from app.resume.llm import call_llm_json

    prompt = ANALYZE_JD_USER.format(jd_text=jd_text[:6000])

    try:
        result = await call_llm_json(
            system=ANALYZE_JD_SYSTEM,
            user=prompt,
            api_key=api_key,
            model=model,
            max_tokens=2048,
        )
        return JDAnalysis(**result)
    except Exception as e:
        logger.warning(f"[JDAnalyzer] LLM analysis failed: {e}. Using regex fallback.")
        return _regex_jd_fallback(jd_text)


def _regex_jd_fallback(jd_text: str) -> JDAnalysis:
    """Rule-based fallback JD parsing when LLM is unavailable."""
    import re

    jd = JDAnalysis()

    # Common tech keywords to extract
    tech_pattern = re.compile(
        r"\b(Python|JavaScript|TypeScript|Java|C\+\+|Go|Rust|Kotlin|Swift|"
        r"React|Vue|Angular|Node\.js|FastAPI|Django|Flask|Spring|"
        r"PostgreSQL|MySQL|MongoDB|Redis|Elasticsearch|"
        r"AWS|GCP|Azure|Docker|Kubernetes|Terraform|CI\/CD|"
        r"TensorFlow|PyTorch|scikit-learn|LangChain|"
        r"REST|GraphQL|gRPC|Kafka|RabbitMQ)\b",
        re.I
    )

    found_tech = list(set(tech_pattern.findall(jd_text)))
    jd.technologies = found_tech[:20]
    jd.keywords = found_tech[:30]

    # Experience level
    if re.search(r"\b(10\+|senior staff|principal|distinguished)\b", jd_text, re.I):
        jd.experience_level = "Principal"
    elif re.search(r"\b(7\+|8\+|9\+|staff|lead engineer)\b", jd_text, re.I):
        jd.experience_level = "Staff"
    elif re.search(r"\b(5\+|6\+|senior)\b", jd_text, re.I):
        jd.experience_level = "Senior"
    elif re.search(r"\b(3\+|4\+|mid[- ]level)\b", jd_text, re.I):
        jd.experience_level = "Mid"
    elif re.search(r"\b(0-2|entry[- ]level|junior|new grad)\b", jd_text, re.I):
        jd.experience_level = "Entry"
    else:
        jd.experience_level = "Mid"

    # Remote/Hybrid/On-site
    if re.search(r"\b(fully remote|100% remote|work from home)\b", jd_text, re.I):
        jd.work_type = "Remote"
    elif re.search(r"\bhybrid\b", jd_text, re.I):
        jd.work_type = "Hybrid"
    elif re.search(r"\bon[- ]?site|in[- ]?office\b", jd_text, re.I):
        jd.work_type = "On-site"

    return jd
