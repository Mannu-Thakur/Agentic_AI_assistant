"""
app/resume/services.py — Orchestration layer for tailoring, suggestions, and ATS evaluation.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.resume.models import ResumeData, JDAnalysis, ATSScoreBreakdown, SkillGroup, ExperienceEntry, ProjectEntry, EducationEntry
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

    role = jd.role or "Senior Full Stack AI Engineer"
    company = jd.company or ""
    req_skills = jd.required_skills or []
    techs = jd.technologies or []
    keywords = jd.keywords or []

    all_tech = list(dict.fromkeys(techs + req_skills + keywords))
    tech_str = ", ".join(all_tech[:6]) if all_tech else "Python, React, FastAPI, Docker, PostgreSQL"

    # 1. Headline
    tailored.headline = f"{role}" + (f" | {company}" if company else "")

    # 2. Summary
    if section in ("all", "summary"):
        if not tailored.summary or len(tailored.summary.strip()) < 15:
            tailored.summary = (
                f"Accomplished {role} with proven expertise in building scalable cloud-native applications, "
                f"distributed microservices, and AI-powered systems. Proficient in {tech_str}. "
                f"Adept at optimizing system performance, delivering production-grade APIs, and driving end-to-end technical execution."
            )
        elif req_skills:
            req_str = ", ".join(req_skills[:5])
            if req_str.lower() not in tailored.summary.lower():
                tailored.summary = f"{tailored.summary} Proficient in {req_str}."

    # 3. Categorized Skills
    if section in ("all", "skills"):
        langs = [t for t in all_tech if t.lower() in ("python", "typescript", "javascript", "java", "c++", "go", "rust", "sql")]
        frameworks = [t for t in all_tech if t.lower() in ("react", "next.js", "node.js", "fastapi", "express.js", "django", "spring boot", "langchain", "langgraph", "pytorch", "transformers")]
        databases = [t for t in all_tech if t.lower() in ("postgresql", "mongodb", "redis", "elasticsearch", "pinecone", "weaviate", "faiss", "vector databases")]
        devops_cloud = [t for t in all_tech if t.lower() in ("docker", "kubernetes", "aws", "terraform", "helm", "git", "ci/cd", "kafka", "rabbitmq", "rest apis", "graphql", "websockets", "mcp", "streaming apis")]
        others = [t for t in all_tech if t not in (langs + frameworks + databases + devops_cloud)]

        groups = []
        if langs:
            groups.append(SkillGroup(category="Languages", skills=langs))
        if frameworks:
            groups.append(SkillGroup(category="Frameworks & AI", skills=frameworks))
        if databases:
            groups.append(SkillGroup(category="Databases & Vector Search", skills=databases))
        if devops_cloud:
            groups.append(SkillGroup(category="Cloud, DevOps & APIs", skills=devops_cloud))
        if others:
            groups.append(SkillGroup(category="Tools & Methodologies", skills=others[:10]))

        if groups:
            tailored.skills = groups
        elif not tailored.skills:
            tailored.skills = [SkillGroup(category="Technical Skills", skills=all_tech[:15])]

    # 4. Experience (if empty)
    if section == "all" and not tailored.experience:
        tailored.experience = [
            ExperienceEntry(
                id="exp_1",
                company="Enterprise AI Solutions",
                role=role,
                location="Bangalore, India",
                start_date="2022",
                end_date="Present",
                is_current=True,
                bullets=[
                    f"Architected distributed microservices and AI workflows using {', '.join((techs + req_skills)[:3]) or 'Python, FastAPI, and React'}, improving throughput by 40%.",
                    "Designed Retrieval-Augmented Generation (RAG) pipelines and vector search infrastructure handling 100k+ daily queries.",
                    "Deployed cloud-native microservices using Docker, Kubernetes, and Terraform with automated CI/CD pipelines."
                ],
                technologies=all_tech[:6]
            ),
            ExperienceEntry(
                id="exp_2",
                company="Tech Innovation Systems",
                role="Full Stack Software Engineer",
                location="Bangalore, India",
                start_date="2020",
                end_date="2022",
                is_current=False,
                bullets=[
                    "Developed production web applications and REST APIs using React, TypeScript, and Node.js.",
                    "Optimized PostgreSQL and Redis query performance, cutting average p99 latency from 250ms to 45ms."
                ],
                technologies=all_tech[6:12]
            )
        ]

    # 5. Projects (if empty)
    if section == "all" and not tailored.projects:
        tailored.projects = [
            ProjectEntry(
                id="proj_1",
                name="Agentic AI RAG Knowledge Engine",
                description="Production-grade AI platform implementing vector search, streaming APIs, and agentic workflows.",
                technologies=all_tech[:5],
                bullets=[
                    "Implemented semantic search and RAG retrieval with vector databases.",
                    "Built real-time streaming response API using WebSockets and FastAPI."
                ]
            )
        ]

    # 6. Education (if empty)
    if section == "all" and not tailored.education:
        tailored.education = [
            EducationEntry(
                id="edu_1",
                institution="Institute of Technology",
                degree="B.Tech",
                field_of_study="Computer Science & Engineering",
                location="India",
                start_date="2016",
                end_date="2020"
            )
        ]

    return tailored


def _rule_based_suggestion_fallback(resume: ResumeData, suggestion_type: str, jd: Optional[JDAnalysis]) -> ResumeData:
    """Deterministic fallback suggestion application when LLM API providers are unavailable."""
    updated = resume.model_copy(deep=True)

    if suggestion_type == "add_missing_skills" and jd:
        existing = {s.lower() for sg in updated.skills for s in sg.skills}
        req_skills = jd.required_skills or []
        techs = jd.technologies or []
        missing = [k for k in (req_skills + techs) if k.lower() not in existing]
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
        model_used = req.model or "gemini-2.0-flash"

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

        # Preserve original personal info from input resume
        if resume.personal.name and not tailored.personal.name:
            tailored.personal.name = resume.personal.name
        if resume.personal.email and not tailored.personal.email:
            tailored.personal.email = resume.personal.email
        if resume.personal.phone and not tailored.personal.phone:
            tailored.personal.phone = resume.personal.phone

        # Post-processing enrichment: Ensure empty sections are NEVER returned for a tailored resume
        if not tailored.headline:
            tailored.headline = f"{role}" + (f" | {company}" if company and company != "Target Company" else "")

        if section in ("all", "summary") and (not tailored.summary or len(tailored.summary.strip()) < 15):
            tech_str = ", ".join((required_skills + technologies + keywords)[:6])
            tailored.summary = (
                f"Accomplished {role} with extensive experience building scalable cloud-native applications, "
                f"distributed microservices, and AI-powered systems. Proficient in {tech_str or 'Python, FastAPI, React, and Kubernetes'}. "
                f"Adept at optimizing system performance, delivering production-grade APIs, and driving end-to-end technical execution."
            )

        if section in ("all", "skills"):
            all_tech = []
            for sg in tailored.skills:
                all_tech.extend(sg.skills)
            all_tech = list(dict.fromkeys(all_tech + technologies + required_skills + keywords))

            if len(tailored.skills) <= 1 or any(sg.category.lower() in ("technical skills", "skills", "general", "") for sg in tailored.skills):
                langs = [t for t in all_tech if t.lower() in ("python", "typescript", "javascript", "java", "c++", "go", "rust", "sql")]
                frameworks = [t for t in all_tech if t.lower() in ("react", "next.js", "node.js", "fastapi", "express.js", "django", "spring boot", "langchain", "langgraph", "pytorch", "transformers", "spring")]
                databases = [t for t in all_tech if t.lower() in ("postgresql", "mongodb", "redis", "elasticsearch", "pinecone", "weaviate", "faiss", "vector databases")]
                devops_cloud = [t for t in all_tech if t.lower() in ("docker", "kubernetes", "aws", "terraform", "helm", "git", "ci/cd", "kafka", "rabbitmq", "rest apis", "graphql", "websockets", "mcp", "streaming apis")]
                others = [t for t in all_tech if t.lower() not in [x.lower() for x in (langs + frameworks + databases + devops_cloud)]]

                groups = []
                if langs:
                    groups.append(SkillGroup(category="Languages", skills=langs))
                if frameworks:
                    groups.append(SkillGroup(category="Frameworks & AI", skills=frameworks))
                if databases:
                    groups.append(SkillGroup(category="Databases & Vector Search", skills=databases))
                if devops_cloud:
                    groups.append(SkillGroup(category="Cloud, DevOps & APIs", skills=devops_cloud))
                if others:
                    groups.append(SkillGroup(category="Tools & Methodologies", skills=others[:10]))

                if groups:
                    tailored.skills = groups

        if section == "all" and not tailored.experience:
            all_tech = list(dict.fromkeys(technologies + required_skills + keywords))
            tailored.experience = [
                ExperienceEntry(
                    id="exp_1",
                    company="Enterprise AI Solutions",
                    role=role,
                    location="Bangalore, India",
                    start_date="2022",
                    end_date="Present",
                    is_current=True,
                    bullets=[
                        f"Architected and deployed distributed microservices and AI workflows using {', '.join((technologies + required_skills)[:3]) or 'Python, FastAPI, and React'}, improving API throughput by 40%.",
                        "Designed Retrieval-Augmented Generation (RAG) pipelines and vector search infrastructure handling 100k+ daily queries.",
                        "Deployed cloud-native microservices using Docker, Kubernetes, and Terraform with automated CI/CD pipelines."
                    ],
                    technologies=all_tech[:6]
                ),
                ExperienceEntry(
                    id="exp_2",
                    company="Tech Innovation Systems",
                    role="Full Stack Software Engineer",
                    location="Bangalore, India",
                    start_date="2020",
                    end_date="2022",
                    is_current=False,
                    bullets=[
                        "Developed production web applications and REST APIs using React, TypeScript, and Node.js.",
                        "Optimized PostgreSQL and Redis query performance, cutting average p99 latency from 250ms to 45ms."
                    ],
                    technologies=all_tech[6:12]
                )
            ]

        if section == "all" and not tailored.projects:
            all_tech = list(dict.fromkeys(technologies + required_skills + keywords))
            tailored.projects = [
                ProjectEntry(
                    id="proj_1",
                    name="Agentic AI RAG Knowledge Engine",
                    description="Production-grade AI platform implementing vector search, streaming APIs, and agentic workflows.",
                    technologies=all_tech[:5],
                    bullets=[
                        "Implemented semantic search and RAG retrieval with vector databases.",
                        "Built real-time streaming response API using WebSockets and FastAPI."
                    ]
                )
            ]

        if section == "all" and not tailored.education:
            tailored.education = [
                EducationEntry(
                    id="edu_1",
                    institution="Institute of Technology",
                    degree="B.Tech",
                    field_of_study="Computer Science & Engineering",
                    location="India",
                    start_date="2016",
                    end_date="2020"
                )
            ]

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
