"""
app/resume/services.py — Orchestration layer for tailoring, suggestions, and ATS evaluation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from app.resume.models import ResumeData, JDAnalysis, SkillGroup, ExperienceEntry, ProjectEntry
from app.resume.schemas import TailorResumeRequest, TailorResumeResponse, SuggestionResult
from app.resume.prompts import (
    TAILOR_SYSTEM, TAILOR_ALL_USER, TAILOR_SUMMARY_USER,
    TAILOR_SKILLS_USER, TAILOR_EXPERIENCE_USER, TAILOR_PROJECTS_USER,
    SUGGESTION_PROMPTS
)
from app.resume.llm import call_llm_json

logger = logging.getLogger("app.resume.services")


def _rule_based_tailor_fallback(resume: ResumeData, jd: JDAnalysis, section: str, style: str) -> ResumeData:
    """Align existing resume facts without creating candidate biography."""
    tailored = resume.model_copy(deep=True)

    # A target role is a positioning choice. The JD alone is never evidence for
    # skills, experience, projects, or education.
    if not tailored.headline and jd.role:
        tailored.headline = jd.role

    if section in ("all", "skills"):
        evidence = list(dict.fromkeys(
            [skill for group in resume.skills for skill in group.skills]
            + [tech for entry in resume.experience for tech in entry.technologies]
            + [tech for project in resume.projects for tech in project.technologies]
        ))
        if not tailored.skills and evidence:
            tailored.skills = [SkillGroup(category="Technical Skills", skills=evidence)]
        elif tailored.skills:
            relevant = {
                value.casefold()
                for value in (jd.required_skills + jd.technologies + jd.keywords)
            }
            for group in tailored.skills:
                group.skills = sorted(
                    dict.fromkeys(group.skills),
                    key=lambda value: (value.casefold() not in relevant, value.casefold()),
                )

    return tailored


def _number_claims(text: str) -> set[str]:
    return {match.replace(",", "") for match in re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", text or "")}


def _preserve_source_facts(source: ResumeData, tailored: ResumeData, jd: JDAnalysis) -> ResumeData:
    """Reject model-created entities, contact changes, and unsupported metrics."""
    tailored.personal = source.personal.model_copy(deep=True)

    if not source.summary:
        tailored.summary = ""
    elif not _number_claims(tailored.summary).issubset(_number_claims(source.summary)):
        tailored.summary = source.summary

    skill_evidence = {
        value.strip().casefold(): value.strip()
        for value in (
            [skill for group in source.skills for skill in group.skills]
            + [tech for entry in source.experience for tech in entry.technologies]
            + [tech for project in source.projects for tech in project.technologies]
        )
        if value and value.strip()
    }
    if not skill_evidence:
        tailored.skills = []
    else:
        filtered_groups = []
        for group in tailored.skills:
            allowed = list(dict.fromkeys(
                skill_evidence[skill.strip().casefold()]
                for skill in group.skills
                if skill.strip().casefold() in skill_evidence
            ))
            if allowed:
                filtered_groups.append(SkillGroup(category=group.category, skills=allowed))
        if not filtered_groups and source.skills:
            filtered_groups = [group.model_copy(deep=True) for group in source.skills]
        elif not filtered_groups and skill_evidence:
            filtered_groups = [SkillGroup(category="Technical Skills", skills=list(skill_evidence.values()))]
        tailored.skills = filtered_groups

    if not source.experience or len(tailored.experience) != len(source.experience):
        tailored.experience = [entry.model_copy(deep=True) for entry in source.experience]
    else:
        for original, updated in zip(source.experience, tailored.experience):
            for field in ("id", "company", "role", "location", "start_date", "end_date", "is_current"):
                setattr(updated, field, getattr(original, field))
            updated.technologies = list(original.technologies)
            source_numbers = _number_claims(" ".join(original.bullets))
            added_numbers = _number_claims(" ".join(updated.bullets)) - source_numbers
            if not original.bullets or len(updated.bullets) != len(original.bullets) or added_numbers:
                updated.bullets = list(original.bullets)

    if not source.projects or len(tailored.projects) != len(source.projects):
        tailored.projects = [project.model_copy(deep=True) for project in source.projects]
    else:
        for original, updated in zip(source.projects, tailored.projects):
            for field in ("id", "name", "url", "github_url", "start_date", "end_date"):
                setattr(updated, field, getattr(original, field))
            updated.technologies = list(original.technologies)
            if not original.description or _number_claims(updated.description) - _number_claims(original.description):
                updated.description = original.description
            source_numbers = _number_claims(" ".join(original.bullets))
            added_numbers = _number_claims(" ".join(updated.bullets)) - source_numbers
            if not original.bullets or len(updated.bullets) != len(original.bullets) or added_numbers:
                updated.bullets = list(original.bullets)

    # These sections are not requested for rewriting and must remain grounded.
    tailored.education = [entry.model_copy(deep=True) for entry in source.education]
    tailored.certifications = [entry.model_copy(deep=True) for entry in source.certifications]
    tailored.achievements = [entry.model_copy(deep=True) for entry in source.achievements]
    tailored.languages = [entry.model_copy(deep=True) for entry in source.languages]

    tailored.headline = source.headline or jd.role or tailored.headline
    return tailored

def _rule_based_suggestion_fallback(resume: ResumeData, suggestion_type: str, jd: Optional[JDAnalysis]) -> ResumeData:
    """Deterministic fallback suggestion application when LLM API providers are unavailable."""
    updated = resume.model_copy(deep=True)

    if suggestion_type == "add_missing_skills" and jd:
        existing = {s.lower() for sg in updated.skills for s in sg.skills}
        source_evidence = " ".join(
            [resume.summary]
            + [bullet for entry in resume.experience for bullet in entry.bullets]
            + [tech for entry in resume.experience for tech in entry.technologies]
            + [project.description for project in resume.projects]
            + [bullet for project in resume.projects for bullet in project.bullets]
            + [tech for project in resume.projects for tech in project.technologies]
        ).casefold()
        req_skills = jd.required_skills or []
        techs = jd.technologies or []
        missing = [
            skill for skill in dict.fromkeys(req_skills + techs)
            if skill.casefold() not in existing and skill.casefold() in source_evidence
        ]
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


def _unwrap_resume_json(data: dict) -> dict:
    """Unwrap top-level wrapper keys commonly produced by LLMs like {'resume': {...}}."""
    if not isinstance(data, dict):
        return {}
    for wrapper in ("resume", "tailored_resume", "tailored", "data", "output", "improved_resume"):
        if wrapper in data and isinstance(data[wrapper], dict):
            inner = data[wrapper]
            if any(k in inner for k in ("personal", "headline", "summary", "skills", "experience", "projects", "education")):
                return inner
    return data


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
        from app.core.config import settings
        model_used = req.model or settings.GEMINI_MODEL

        role = jd.role or "Senior Full Stack AI Engineer"
        company = jd.company or "Target Company"
        required_skills = jd.required_skills or []
        keywords = jd.keywords or []
        technologies = jd.technologies or []
        experience_level = jd.experience_level or "Mid"

        try:
            if section == "all":
                prompt = TAILOR_ALL_USER.format(
                    style=style,
                    role=role,
                    company=company,
                    required_skills=", ".join(required_skills),
                    keywords=", ".join(keywords[:15]),
                    experience_level=experience_level,
                    resume_json=resume.model_dump_json(indent=2),
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                unwrapped = _unwrap_resume_json(result)
                tailored = ResumeData(**unwrapped)
                changes_summary.append(f"Tailored entire resume with style: {style}")

            elif section == "summary":
                prompt = TAILOR_SUMMARY_USER.format(
                    style=style,
                    role=role,
                    company=company,
                    required_skills=", ".join(required_skills),
                    keywords=", ".join(keywords[:15]),
                    summary=resume.summary,
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                tailored = resume.model_copy(deep=True)
                unwrapped = _unwrap_resume_json(result)
                if "summary" in unwrapped:
                    tailored.summary = unwrapped["summary"]
                elif "summary" in result:
                    tailored.summary = result["summary"]
                changes_summary.append("Tailored professional summary")

            elif section == "skills":
                prompt = TAILOR_SKILLS_USER.format(
                    style=style,
                    technologies=", ".join(technologies),
                    keywords=", ".join(keywords[:15]),
                    skills_json=json.dumps([s.model_dump() for s in resume.skills]),
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                tailored = resume.model_copy(deep=True)
                unwrapped = _unwrap_resume_json(result)
                skills_raw = unwrapped.get("skills") or result.get("skills")
                if skills_raw and isinstance(skills_raw, list):
                    tailored.skills = [SkillGroup(**sg) for sg in skills_raw if isinstance(sg, dict)]
                changes_summary.append("Optimized skills section for JD keywords")

            elif section == "experience":
                prompt = TAILOR_EXPERIENCE_USER.format(
                    style=style,
                    role=role,
                    required_skills=", ".join(required_skills),
                    keywords=", ".join(keywords[:15]),
                    experience_json=json.dumps([e.model_dump() for e in resume.experience]),
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                tailored = resume.model_copy(deep=True)
                unwrapped = _unwrap_resume_json(result)
                exp_raw = unwrapped.get("experience") or result.get("experience")
                if exp_raw and isinstance(exp_raw, list):
                    tailored.experience = [ExperienceEntry(**exp) for exp in exp_raw if isinstance(exp, dict)]
                changes_summary.append(f"Enhanced experience bullet points ({style})")

            elif section == "projects":
                prompt = TAILOR_PROJECTS_USER.format(
                    style=style,
                    role=role,
                    technologies=", ".join(technologies),
                    projects_json=json.dumps([p.model_dump() for p in resume.projects]),
                )
                result = await call_llm_json(
                    system=TAILOR_SYSTEM,
                    user=prompt,
                    api_key=req.api_key,
                    model=req.model,
                )
                tailored = resume.model_copy(deep=True)
                unwrapped = _unwrap_resume_json(result)
                proj_raw = unwrapped.get("projects") or result.get("projects")
                if proj_raw and isinstance(proj_raw, list):
                    tailored.projects = [ProjectEntry(**proj) for proj in proj_raw if isinstance(proj, dict)]
                changes_summary.append("Refined project descriptions and tech stacks")
            else:
                tailored = resume
        except Exception as exc:
            logger.warning(f"[ResumeService] LLM tailoring unavailable ({exc}). Using deterministic fallback.")
            tailored = _rule_based_tailor_fallback(resume, jd, section, style)
            changes_summary.append(f"Tailored section '{section}' using deterministic keyword alignment fallback")
            model_used = "rule-based-fallback"

        tailored = _preserve_source_facts(resume, tailored, jd)

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

            updated_resume = ResumeData(**_unwrap_resume_json(result))
            updated_resume = _preserve_source_facts(resume, updated_resume, jd or JDAnalysis())
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
