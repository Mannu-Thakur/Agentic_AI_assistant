"""
app/resume/ats.py — Algorithmic ATS Scoring Engine.

CRITICAL: The ATS score is computed algorithmically — never hallucinated by LLM.
The LLM may only EXPLAIN the score, never compute it.

Evaluated dimensions:
  1. Keyword Match         — JD keywords found in resume text
  2. Section Completeness  — Important sections present
  3. Formatting Quality    — Bullet consistency, length
  4. Readability           — Sentence clarity
  5. Contact Info          — All fields present
  6. Action Verbs          — % bullets starting with strong verbs
  7. Quantified Metrics    — % bullets with numbers/percentages
  8. Technical Skills      — JD tech coverage
  9. Resume Length         — Optimal word count
 10. Duplicate Skills      — Penalize repetition
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.resume.models import ResumeData, JDAnalysis, ATSScoreBreakdown


# ─────────────────────────────────────────────────────────────────────────────
#  Word Lists
# ─────────────────────────────────────────────────────────────────────────────

_STRONG_ACTION_VERBS = {
    "accelerated", "achieved", "acquired", "administered", "advanced",
    "analyzed", "architected", "automated", "built", "championed",
    "coached", "collaborated", "conceptualized", "consolidated",
    "constructed", "coordinated", "created", "cut", "debugged",
    "delivered", "deployed", "designed", "developed", "devised",
    "directed", "drove", "eliminated", "engineered", "enhanced",
    "established", "evaluated", "executed", "expanded", "facilitated",
    "generated", "grew", "guided", "implemented", "improved",
    "increased", "initiated", "integrated", "introduced", "launched",
    "led", "maintained", "managed", "mentored", "migrated",
    "modernized", "optimized", "orchestrated", "oversaw", "partnered",
    "pioneered", "planned", "produced", "programmed", "proposed",
    "published", "rebuilt", "redesigned", "reduced", "refactored",
    "released", "resolved", "reviewed", "scaled", "secured",
    "spearheaded", "streamlined", "transformed", "unified", "upgraded",
}

_WEAK_VERBS = {
    "responsible for", "helped", "assisted", "worked on", "was involved",
    "participated in", "contributed to", "dealt with", "handled",
}

_CONTACT_FIELDS = ["name", "email", "phone"]
_IMPORTANT_SECTIONS = ["summary", "skills", "experience", "education"]


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _flatten_resume_text(resume: ResumeData) -> str:
    """Get all text from the resume for keyword matching."""
    parts = [
        resume.personal.name,
        resume.headline,
        resume.summary,
    ]
    for sg in resume.skills:
        parts.extend(sg.skills)
    for exp in resume.experience:
        parts.append(exp.company)
        parts.append(exp.role)
        parts.extend(exp.bullets)
        parts.extend(exp.technologies)
    for proj in resume.projects:
        parts.append(proj.name)
        parts.append(proj.description)
        parts.extend(proj.bullets)
        parts.extend(proj.technologies)
    for edu in resume.education:
        parts.append(edu.institution)
        parts.append(edu.degree)
        parts.append(edu.field_of_study)
    for cert in resume.certifications:
        parts.append(cert.name)

    return " ".join(p for p in parts if p).lower()


def _get_all_bullets(resume: ResumeData) -> List[str]:
    bullets = []
    for exp in resume.experience:
        bullets.extend(exp.bullets)
    for proj in resume.projects:
        bullets.extend(proj.bullets)
    return bullets


def _starts_with_action_verb(bullet: str) -> bool:
    first_word = bullet.strip().split()[0].lower().rstrip(".,;:") if bullet.strip() else ""
    return first_word in _STRONG_ACTION_VERBS


def _has_metric(text: str) -> bool:
    """Check if text contains a quantified metric."""
    patterns = [
        r"\d+%",            # 30%
        r"\d+x",            # 2x
        r"\$\d+",           # $1M
        r"\d+\+",           # 100+
        r"\d+k\b",          # 50k
        r"\d+m\b",          # 10m
        r"\d+[,\d]+",       # 10,000
        r"\d+ (users|requests|services|teams|people|engineers|clients|customers)",
        r"(increased|decreased|reduced|improved|grew|boosted) (by )?(\d+|\d+%)",
    ]
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in patterns)


# ─────────────────────────────────────────────────────────────────────────────
#  Scoring Functions
# ─────────────────────────────────────────────────────────────────────────────

def _score_keyword_match(
    resume_text: str,
    jd: Optional[JDAnalysis],
) -> Tuple[int, List[str], List[str]]:
    """Returns (score 0-100, matched_keywords, missing_keywords)."""
    if not jd or not jd.keywords:
        return 75, [], []

    all_keywords = list(set(jd.keywords + jd.required_skills + jd.technologies))
    if not all_keywords:
        return 75, [], []

    matched = []
    missing = []
    for kw in all_keywords:
        kw_lower = kw.lower()
        if kw_lower in resume_text:
            matched.append(kw)
        else:
            missing.append(kw)

    score = int((len(matched) / len(all_keywords)) * 100) if all_keywords else 75
    return min(score, 100), matched[:30], missing[:20]


def _score_section_completeness(resume: ResumeData) -> int:
    """Check presence of important sections."""
    checks = {
        "summary": bool(resume.summary),
        "skills": bool(resume.skills),
        "experience": bool(resume.experience),
        "education": bool(resume.education),
        "contact_name": bool(resume.personal.name),
        "contact_email": bool(resume.personal.email),
    }
    score = int(sum(1 for v in checks.values() if v) / len(checks) * 100)
    return score


def _score_contact_info(resume: ResumeData) -> int:
    fields = {
        "name": resume.personal.name,
        "email": resume.personal.email,
        "phone": resume.personal.phone,
        "location": resume.personal.location,
        "linkedin": resume.personal.linkedin,
    }
    filled = sum(1 for v in fields.values() if v)
    return int(filled / len(fields) * 100)


def _score_action_verbs(bullets: List[str]) -> int:
    if not bullets:
        return 50
    good = sum(1 for b in bullets if _starts_with_action_verb(b))
    return min(int(good / len(bullets) * 100), 100)


def _score_quantified_achievements(bullets: List[str]) -> int:
    if not bullets:
        return 50
    quantified = sum(1 for b in bullets if _has_metric(b))
    # Target: ~40% of bullets quantified for a 100 score
    ratio = quantified / len(bullets)
    return min(int(ratio / 0.4 * 100), 100)


def _score_resume_length(resume: ResumeData) -> int:
    """Optimal resume length is 400-700 words for a 1-page, 700-1200 for 2-page."""
    all_text = _flatten_resume_text(resume)
    word_count = len(all_text.split())

    if 400 <= word_count <= 700:
        return 100
    elif 300 <= word_count < 400 or 700 < word_count <= 900:
        return 85
    elif 200 <= word_count < 300 or 900 < word_count <= 1200:
        return 70
    elif word_count < 200:
        return 40
    else:
        return 55  # Very long


def _score_formatting_quality(resume: ResumeData) -> int:
    """Evaluate bullet consistency and formatting."""
    bullets = _get_all_bullets(resume)
    if not bullets:
        return 60

    score = 100

    # Check bullet length consistency (ideal: 15-30 words)
    too_short = sum(1 for b in bullets if len(b.split()) < 5)
    too_long = sum(1 for b in bullets if len(b.split()) > 40)
    score -= int((too_short + too_long) / len(bullets) * 40)

    # Penalize for weak verb usage
    weak = sum(1 for b in bullets if any(w in b.lower() for w in _WEAK_VERBS))
    score -= int(weak / len(bullets) * 30)

    return max(score, 30)


def _score_technical_skills_coverage(
    resume: ResumeData,
    resume_text: str,
    jd: Optional[JDAnalysis],
) -> int:
    if not jd or not jd.technologies:
        # No JD → score based on having skills section
        return 80 if resume.skills else 40

    found = sum(1 for t in jd.technologies if t.lower() in resume_text)
    if not jd.technologies:
        return 80
    return min(int(found / len(jd.technologies) * 100), 100)


def _find_duplicate_skills(resume: ResumeData) -> List[str]:
    """Find skills duplicated across categories."""
    seen = {}
    duplicates = []
    for sg in resume.skills:
        for skill in sg.skills:
            skill_lower = skill.lower()
            if skill_lower in seen:
                duplicates.append(skill)
            else:
                seen[skill_lower] = True
    return duplicates[:10]


def _build_recommendations(
    resume: ResumeData,
    score: ATSScoreBreakdown,
    jd: Optional[JDAnalysis],
) -> List[str]:
    recs = []

    if score.keyword_match < 60:
        recs.append(f"Add more JD keywords. Missing: {', '.join(score.missing_keywords[:5])}")
    if score.action_verbs < 70:
        recs.append("Start more bullets with strong action verbs (Led, Built, Developed, Reduced)")
    if score.quantified_achievements < 50:
        recs.append("Quantify at least 30-40% of your achievements with numbers or percentages")
    if not resume.personal.linkedin:
        recs.append("Add your LinkedIn profile URL")
    if not resume.summary:
        recs.append("Add a professional summary (3-5 sentences)")
    if score.resume_length_score < 70:
        word_count = len(_flatten_resume_text(resume).split())
        if word_count < 400:
            recs.append("Resume may be too short — expand experience bullets with more detail")
        else:
            recs.append("Resume may be too long — consider condensing to 1-2 pages")
    if score.duplicate_skills:
        recs.append(f"Remove duplicate skills: {', '.join(score.duplicate_skills[:3])}")
    if jd and score.technical_skills_coverage < 60:
        missing_tech = [t for t in jd.technologies if t.lower() not in _flatten_resume_text(resume)]
        if missing_tech:
            recs.append(f"Add missing required technologies: {', '.join(missing_tech[:4])}")

    return recs[:8]


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def compute_ats_score(
    resume: ResumeData,
    jd: Optional[JDAnalysis] = None,
) -> ATSScoreBreakdown:
    """
    Compute a fully algorithmic ATS score.
    The LLM is NEVER called from this function.
    All scores are computed deterministically.
    """
    resume_text = _flatten_resume_text(resume)
    bullets = _get_all_bullets(resume)

    # Compute individual dimensions
    kw_score, matched_kws, missing_kws = _score_keyword_match(resume_text, jd)
    section_score = _score_section_completeness(resume)
    contact_score = _score_contact_info(resume)
    action_score = _score_action_verbs(bullets)
    quantified_score = _score_quantified_achievements(bullets)
    length_score = _score_resume_length(resume)
    formatting_score = _score_formatting_quality(resume)
    tech_score = _score_technical_skills_coverage(resume, resume_text, jd)
    duplicate_skills = _find_duplicate_skills(resume)
    readability_score = min(int((action_score + formatting_score) / 2), 100)

    # Weighted overall score
    weights = {
        "keyword_match": 0.25 if jd else 0.05,
        "section_completeness": 0.15,
        "formatting_quality": 0.10,
        "readability": 0.10,
        "contact_info": 0.05,
        "action_verbs": 0.10,
        "quantified_achievements": 0.10,
        "technical_skills_coverage": 0.10 if jd else 0.05,
        "resume_length_score": 0.05,
    }
    if not jd:
        # Redistribute JD-dependent weights
        weights["section_completeness"] = 0.25
        weights["formatting_quality"] = 0.15
        weights["action_verbs"] = 0.15
        weights["quantified_achievements"] = 0.15
        weights["resume_length_score"] = 0.10
        weights["contact_info"] = 0.10
        weights["readability"] = 0.10

    raw_scores = {
        "keyword_match": kw_score,
        "section_completeness": section_score,
        "formatting_quality": formatting_score,
        "readability": readability_score,
        "contact_info": contact_score,
        "action_verbs": action_score,
        "quantified_achievements": quantified_score,
        "technical_skills_coverage": tech_score,
        "resume_length_score": length_score,
    }

    overall = int(sum(raw_scores[k] * weights[k] for k in weights))
    overall = max(0, min(100, overall))

    score = ATSScoreBreakdown(
        overall=overall,
        keyword_match=kw_score,
        section_completeness=section_score,
        formatting_quality=formatting_score,
        readability=readability_score,
        contact_info=contact_score,
        action_verbs=action_score,
        quantified_achievements=quantified_score,
        technical_skills_coverage=tech_score,
        resume_length_score=length_score,
        matched_keywords=matched_kws,
        missing_keywords=missing_kws,
        duplicate_skills=duplicate_skills,
    )

    # Build recommendations
    score.recommendations = _build_recommendations(resume, score, jd)

    return score
