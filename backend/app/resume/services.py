"""
app/resume/services.py — Orchestration layer for tailoring, suggestions, and ATS evaluation.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.resume.models import ResumeData, JDAnalysis, ATSScoreBreakdown, SkillGroup, ExperienceEntry, ProjectEntry
from app.resume.schemas import TailorResumeRequest, TailorResumeResponse, SuggestionResult
from app.resume.prompts import (
    TAILOR_SYSTEM, TAILOR_ALL_USER, TAILOR_SUMMARY_USER,
    TAILOR_SKILLS_USER, TAILOR_EXPERIENCE_USER, TAILOR_PROJECTS_USER,
    SUGGESTION_PROMPTS
)
from app.resume.llm import call_llm_json

logger = logging.getLogger("app.resume.services")


def _rule_based_tailor_fallback(resume: ResumeData, jd: JDAnalysis, section: str, style: str) -> ResumeData:
    """Deterministic fallback tailoring when LLM API providers are unavailable."""
    tailored = resume.model_copy(deep=True)

    if section in ("all", "summary"):
        if jd.role and jd.company:
            tailored.headline = f"{jd.role} | Tailored for {jd.company}"
        elif jd.role:
            tailored.headline = f"{jd.role}"

        if jd.required_skills:
            req_str = ", ".join(jd.required_skills[:5])
            if not tailored.summary:
                tailored.summary = f"Results-driven software professional specializing in {req_str}."
            elif req_str.lower() not in tailored.summary.lower():
                tailored.summary = f"{tailored.summary} Proficient in {req_str}."

    if section in ("all", "skills"):
        existing_skills = set()
        for sg in tailored.skills:
            existing_skills.update(s.lower() for s in sg.skills)

        new_skills = [tech for tech in (jd.technologies + jd.required_skills) if tech.lower() not in existing_skills]
        if new_skills:
            if tailored.skills:
                tailored.skills[0].skills.extend(new_skills[:10])
            else:
                tailored.skills = [SkillGroup(category="Technical Skills", skills=new_skills[:10])]

    return tailored


def _rule_based_suggestion_fallback(resume: ResumeData, suggestion_type: str, jd: Optional[JDAnalysis]) -> ResumeData:
    """Deterministic fallback suggestion application when LLM API providers are unavailable."""
    updated = resume.model_copy(deep=True)

    if suggestion_type == "add_missing_skills" and jd:
        existing = {s.lower() for sg in updated.skills for s in sg.skills}
        missing = [k for k in (jd.required_skills + jd.technologies) if k.lower() not in existing]
        if missing:
            if updated.skills:
                updated.skills[0].skills.extend(missing[:5])
            else:
                updated.skills = [SkillGroup(category="Technical Skills", skills=missing[:5])]

    elif suggestion_type == "improve_action_verbs":
        strong_verbs = ["Architected", "Spearheaded", "Optimized", "Engineered", "Launched"]
        for i, exp in enumerate(updated.experience):
            new_bullets = []
            for b_idx, bullet in enumerate(exp.bullets):
                words = bullet.split()
                if words and not words[0].endswith("ed"):
                    verb = strong_verbs[b_idx % len(strong_verbs)]
                    bullet = f"{verb} {bullet[0].lower() + bullet[1:] if len(bullet) > 1 else bullet}"
                new_bullets.append(bullet)
            exp.bullets = new_bullets

    return updated


class ResumeService:

    @staticmethod
    async def tailor_resume(req: TailorResumeRequest) -> TailorResumeResponse:
        """
        Tailor a resume based on JDAnalysis and target section/style.
        Only modifies content text; never raw formatting or layout.
        """
        section = req.section
        style = req.style
        jd = req.jd_analysis
        resume = req.resume

        changes_summary = []
        model_used = req.model or "gemini-2.0-flash"

        try:
            if section == "all":
                prompt = TAILOR_ALL_USER.format(
                    style=style,
                    role=jd.role,
                    company=jd.company,
                    required_skills=", ".join(jd.required_skills),
                    keywords=", ".join(jd.keywords[:15]),
                    experience_level=jd.experience_level,
                    resume_json=resume.model_dump_json(indent=2),
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                tailored = ResumeData(**result)
                changes_summary.append(f"Tailored entire resume with style: {style}")

            elif section == "summary":
                prompt = TAILOR_SUMMARY_USER.format(
                    style=style,
                    role=jd.role,
                    company=jd.company,
                    required_skills=", ".join(jd.required_skills),
                    keywords=", ".join(jd.keywords[:15]),
                    summary=resume.summary,
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                tailored = resume.model_copy(deep=True)
                if "summary" in result:
                    tailored.summary = result["summary"]
                changes_summary.append("Tailored professional summary")

            elif section == "skills":
                prompt = TAILOR_SKILLS_USER.format(
                    style=style,
                    technologies=", ".join(jd.technologies),
                    keywords=", ".join(jd.keywords[:15]),
                    skills_json=json.dumps([s.model_dump() for s in resume.skills]),
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                tailored = resume.model_copy(deep=True)
                if "skills" in result:
                    tailored.skills = [SkillGroup(**sg) for sg in result["skills"]]
                changes_summary.append("Optimized skills section for JD keywords")

            elif section == "experience":
                prompt = TAILOR_EXPERIENCE_USER.format(
                    style=style,
                    role=jd.role,
                    required_skills=", ".join(jd.required_skills),
                    keywords=", ".join(jd.keywords[:15]),
                    experience_json=json.dumps([e.model_dump() for e in resume.experience]),
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                tailored = resume.model_copy(deep=True)
                if "experience" in result:
                    tailored.experience = [ExperienceEntry(**exp) for exp in result["experience"]]
                changes_summary.append(f"Enhanced experience bullet points ({style})")

            elif section == "projects":
                prompt = TAILOR_PROJECTS_USER.format(
                    style=style,
                    role=jd.role,
                    technologies=", ".join(jd.technologies),
                    projects_json=json.dumps([p.model_dump() for p in resume.projects]),
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                tailored = resume.model_copy(deep=True)
                if "projects" in result:
                    tailored.projects = [ProjectEntry(**proj) for proj in result["projects"]]
                changes_summary.append("Refined project descriptions and tech stacks")
            else:
                tailored = resume
        except Exception as exc:
            logger.warning(f"[ResumeService] LLM tailoring unavailable ({exc}). Using deterministic fallback.")
            tailored = _rule_based_tailor_fallback(resume, jd, section, style)
            changes_summary.append(f"Tailored section '{section}' using deterministic keyword alignment fallback")
            model_used = "rule-based-fallback"

        return TailorResumeResponse(
            tailored_resume=tailored,
            changes_summary=changes_summary,
            model_used=model_used,
        )

    @staticmethod
    async def apply_suggestion(
        resume: ResumeData,
        suggestion_type: str,
        jd: Optional[JDAnalysis] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> SuggestionResult:
        """Apply a one-click AI suggestion to the resume."""
        template_str = SUGGESTION_PROMPTS.get(suggestion_type)
        if not template_str:
            raise ValueError(f"Unknown suggestion type: {suggestion_type}")

        try:
            prompt = template_str.format(
                resume_json=resume.model_dump_json(indent=2),
                jd_keywords=", ".join(jd.keywords) if jd else "",
                missing_keywords=", ".join(jd.required_skills) if jd else "",
            )

            result = await call_llm_json(
                system=TAILOR_SYSTEM,
                user=prompt,
                api_key=api_key,
                model=model,
            )

            updated_resume = ResumeData(**result)
            changes = [f"Applied AI suggestion: {suggestion_type.replace('_', ' ').title()}"]
        except Exception as exc:
            logger.warning(f"[ResumeService] LLM suggestion unavailable ({exc}). Using deterministic fallback.")
            updated_resume = _rule_based_suggestion_fallback(resume, suggestion_type, jd)
            changes = [f"Applied suggestion ({suggestion_type.replace('_', ' ').title()}) via fallback"]

        return SuggestionResult(
            updated_resume=updated_resume,
            suggestion_applied=suggestion_type,
            changes=changes,
        )
