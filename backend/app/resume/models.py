"""
app/resume/models.py — Structured resume data models.

CORE DESIGN PRINCIPLE: Everything operates on ResumeData JSON.
Raw text is NEVER passed between components after initial parsing.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
#  Sub-models
# ─────────────────────────────────────────────────────────────────────────────

class PersonalInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    portfolio: str = ""


class ExperienceEntry(BaseModel):
    id: str = ""
    company: str = ""
    role: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""          # "Present" for current
    is_current: bool = False
    bullets: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    technologies: List[str] = Field(default_factory=list)
    url: str = ""
    github_url: str = ""
    link: str = ""
    bullets: List[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""



class EducationEntry(BaseModel):
    id: str = ""
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    gpa: str = ""
    honors: str = ""
    relevant_courses: List[str] = Field(default_factory=list)


class CertificationEntry(BaseModel):
    id: str = ""
    name: str = ""
    issuer: str = ""
    date: str = ""
    url: str = ""
    expiry: str = ""


class AchievementEntry(BaseModel):
    id: str = ""
    title: str = ""
    description: str = ""
    date: str = ""


class LanguageEntry(BaseModel):
    language: str = ""
    proficiency: str = ""   # Native, Fluent, Professional, Conversational, Basic


class SkillGroup(BaseModel):
    category: str = ""          # e.g. "Languages", "Frameworks", "Tools", "Cloud"
    skills: List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
#  Root Resume Model
# ─────────────────────────────────────────────────────────────────────────────

class ResumeData(BaseModel):
    """
    The canonical structured resume representation.
    Every component (ATS, Tailoring, Preview, Export) consumes this model.
    Raw text is NEVER stored or passed after initial parse.
    """
    personal: PersonalInfo = Field(default_factory=PersonalInfo)
    headline: str = ""
    summary: str = ""
    skills: List[SkillGroup] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    certifications: List[CertificationEntry] = Field(default_factory=list)
    achievements: List[AchievementEntry] = Field(default_factory=list)
    languages: List[LanguageEntry] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
#  JD Analysis Model
# ─────────────────────────────────────────────────────────────────────────────

class JDAnalysis(BaseModel):
    company: str = ""
    role: str = ""
    experience_level: str = ""       # Entry, Mid, Senior, Lead, Principal, Staff
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)
    industry: str = ""
    work_type: str = ""             # Remote, Hybrid, On-site


# ─────────────────────────────────────────────────────────────────────────────
#  ATS Score Model
# ─────────────────────────────────────────────────────────────────────────────

class ATSScoreBreakdown(BaseModel):
    overall: int = 0                    # 0-100
    keyword_match: int = 0              # % of JD keywords found in resume
    section_completeness: int = 0       # % of important sections present
    formatting_quality: int = 0         # bullet consistency, length
    readability: int = 0                # sentence clarity score
    contact_info: int = 0               # all contact fields present
    action_verbs: int = 0               # % bullets starting with action verb
    quantified_achievements: int = 0    # % bullets with numbers/metrics
    technical_skills_coverage: int = 0  # % JD tech skills found in resume
    resume_length_score: int = 0        # optimal 400-700 words for 1 page
    matched_keywords: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    duplicate_skills: List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
#  Resume Version (for history)
# ─────────────────────────────────────────────────────────────────────────────

class ResumeVersion(BaseModel):
    version_id: str
    label: str                      # "Original", "Tailored for Google", etc.
    resume: ResumeData
    ats_score: Optional[ATSScoreBreakdown] = None
    created_at: str = ""
    description: str = ""           # What changed in this version
