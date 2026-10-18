"""
app/resume/prompts.py — All LLM prompt templates for the Resume Builder.

Prompts are centralized here and versioned.
The LLM is NEVER asked to generate formatting or compute scores.
It only improves text content.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
#  Resume Parsing Prompts
# ─────────────────────────────────────────────────────────────────────────────

PARSE_RESUME_SYSTEM = """You are a world-class precise layout-aware resume parser and extraction architect.
Your task is to extract high-fidelity structured information from resume text into valid JSON matching the target schema.

CRITICAL EXTRACTION RULES:
- Extract EXACTLY what is present in the text — NEVER fabricate, infer, or hallucinate companies, degrees, dates, skills, or projects.
- SECTION AGNOSTICISM: Identify sections based on contextual meaning and layout cues (Markdown headers like # and ##), not exact wording. A section starting with an introductory paragraph before work experience is the 'summary', regardless of its title.
- ARRAY SEGMENTATION: For 'Work Experience' and 'Projects', look for Markdown bolding (**text**) or repeating structural patterns (e.g., Title, Date, Description) to segment distinct entries. Never merge distinct roles or projects into a single array item.
- BULLET POINT COHESION: Do not treat raw newline characters as new bullet points. Read the contextual flow. If a sentence continues onto the next line, merge it into a single string for that array entry.
- FALLBACK NORMALIZATION & EMPTY SECTIONS: If a section or field is missing in the document, return empty list [] or empty string "" rather than hallucinating or copying template placeholders.
- Extract ALL sections if present:
  1. Personal Information (name, email, phone, location, linkedin, github, website, portfolio)
  2. Professional Summary
  3. Work Experience (company, role, location, start_date, end_date, is_current, bullets, technologies)
  4. Projects (name, description, technologies, url, github_url, bullets, start_date, end_date)
  5. Education (institution, degree, field_of_study, location, start_date, end_date, gpa, honors, relevant_courses)
  6. Certifications (name, issuer, date, url, expiry)
  7. Achievements (title, description, date)
  8. Languages (language, proficiency)
  9. Skills (categorized into: Languages, Frontend, Backend, Databases, DevOps, AI/ML / GenAI, Developer Tools, Core CS, Others)
- Return ONLY valid JSON, no markdown formatting, no explanations."""


PARSE_RESUME_USER = """Parse this resume text into structured JSON matching this exact schema:

{{
  "personal": {{"name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": "", "website": "", "portfolio": ""}},
  "headline": "",
  "summary": "",
  "skills": [
    {{"category": "Languages", "skills": []}},
    {{"category": "Frontend", "skills": []}},
    {{"category": "Backend", "skills": []}},
    {{"category": "Databases", "skills": []}},
    {{"category": "DevOps", "skills": []}},
    {{"category": "AI/ML / GenAI", "skills": []}},
    {{"category": "Developer Tools", "skills": []}},
    {{"category": "Core CS", "skills": []}},
    {{"category": "Others", "skills": []}}
  ],
  "experience": [{{
    "id": "exp_1",
    "company": "", "role": "", "location": "",
    "start_date": "", "end_date": "", "is_current": false,
    "bullets": [], "technologies": []
  }}],
  "projects": [{{
    "id": "proj_1",
    "name": "", "description": "", "technologies": [],
    "url": "", "github_url": "", "bullets": [],
    "start_date": "", "end_date": ""
  }}],
  "education": [{{
    "id": "edu_1",
    "institution": "", "degree": "", "field_of_study": "",
    "location": "", "start_date": "", "end_date": "",
    "gpa": "", "honors": "", "relevant_courses": []
  }}],
  "certifications": [{{"id": "cert_1", "name": "", "issuer": "", "date": "", "url": "", "expiry": ""}}],
  "achievements": [{{"id": "ach_1", "title": "", "description": "", "date": ""}}],
  "languages": [{{"language": "", "proficiency": ""}}]
}}

Pre-extracted contact hints (if any):
- Email hint: {email_hint}
- Phone hint: {phone_hint}
- LinkedIn hint: {linkedin_hint}
- GitHub hint: {github_hint}

Resume text:
{resume_text}"""


# ─────────────────────────────────────────────────────────────────────────────
#  Job Description Analysis Prompts
# ─────────────────────────────────────────────────────────────────────────────

ANALYZE_JD_SYSTEM = """You are an expert talent acquisition specialist and ATS system analyst.
Extract structured information from job descriptions. Return ONLY valid JSON. No markdown."""

ANALYZE_JD_USER = """Analyze this job description and extract structured data:

{{
  "company": "",
  "role": "",
  "experience_level": "",
  "required_skills": [],
  "preferred_skills": [],
  "technologies": [],
  "responsibilities": [],
  "soft_skills": [],
  "keywords": [],
  "nice_to_have": [],
  "industry": "",
  "work_type": ""
}}

Rules:
- experience_level: one of "Entry", "Mid", "Senior", "Lead", "Principal", "Staff"
- keywords: all important searchable terms an ATS would look for (include tools, methodologies, domain terms)
- technologies: only specific tech (languages, frameworks, platforms, tools)
- work_type: "Remote", "Hybrid", "On-site", or ""

Job Description:
{jd_text}"""


# ─────────────────────────────────────────────────────────────────────────────
#  Tailoring Prompts
# ─────────────────────────────────────────────────────────────────────────────

TAILOR_SYSTEM = """You are an expert resume writer with 15+ years of experience at top tech companies.
You are improving and tailoring resume content to match a specific job description.

CRITICAL RULES:
- Return ONLY valid JSON matching the input schema exactly.
- NEVER invent or infer facts: do not create employers, roles, dates, degrees, certifications, projects, skills, responsibilities, achievements, team sizes, or metrics.
- PRESERVE SOURCE FACTS: Keep contact information and factual fields exactly as supplied. Rewrite only wording already supported by the source resume.
- KEEP MISSING DATA EMPTY: Empty sections and missing entries must remain empty. A job description describes the target, not the candidate's history or qualifications.
- SKILLS CATEGORIZATION: Group skills logically into categories (e.g., Languages, Frameworks & AI, Databases & Storage, Cloud & DevOps).
- BULLET QUALITY: Improve clarity without changing the underlying claim, adding responsibilities, or adding any number/metric absent from the source.
- Return a complete JSON object while preserving empty values; never fill emptiness with examples or placeholders."""

TAILOR_ALL_USER = """Tailor this resume to the target job using only facts in the source resume.
Style: {style}

Target Job Details:
- Role: {role} at {company}
- Required Skills: {required_skills}
- Key Keywords: {keywords}
- Experience Level: {experience_level}

Current Resume JSON:
{resume_json}

INSTRUCTIONS:
1. Preserve the existing headline; if it is empty, use the target role title {role} as a desired headline.
2. Rewrite a non-empty summary only with facts stated in that summary. Leave an empty summary empty.
3. Reorder existing skills for relevance. Do not add JD skills unless they already appear in the resume's skills, experience technologies, or project technologies.
4. Rewrite existing experience bullets without changing the underlying claims, adding numbers, or creating entries. Preserve company, role, dates, location, and technologies exactly.
5. Preserve project, education, certification, achievement, and language entries exactly. Keep empty sections empty.

Return the complete tailored resume as valid JSON matching the exact schema."""

TAILOR_SUMMARY_USER = """Rewrite ONLY the summary section of this resume to better match the job.
Style: {style}

Target Role: {role} at {company}
Key Requirements: {required_skills}
Keywords to include naturally: {keywords}

Current summary:
{summary}

Return JSON: {{"summary": "..."}}
- If the current summary is empty, return an empty string.
- Otherwise, use only the facts already stated in the current summary.
- Do not add years, credentials, skills, responsibilities, accomplishments, or metrics that are not present in it."""

TAILOR_SKILLS_USER = """Reorganize and optimize ONLY the skills section to match this job.
Style: {style}

Job Technologies Required: {technologies}
Job Keywords: {keywords}

Current skills:
{skills_json}

Return JSON: {{"skills": [same structure with skills prioritized for this role]}}
- Put most JD-relevant skills first within each category
- Do not add a skill unless it already appears in the current skills or is explicitly listed as a technology in the source experience/projects
- Remove clearly irrelevant skills if requested
- Keep category structure"""

TAILOR_EXPERIENCE_USER = """Improve ONLY the experience bullets to better match this job.
Style: {style}

Target Role: {role}
Key Skills: {required_skills}
Keywords: {keywords}

Current experience:
{experience_json}

Return JSON: {{"experience": [same structure with improved bullets]}}
Rules:
- Clarify and reorder existing bullets only; do not create entries or bullets
- Do not add metrics, outcomes, responsibilities, or claims, even if they seem implied
- Include relevant keywords naturally
- Keep company, role, dates, location, technologies, and number of bullets EXACTLY the same"""

TAILOR_PROJECTS_USER = """Improve ONLY the projects section bullets to match this job.
Style: {style}

Target Role: {role}
Key Technologies: {technologies}

Current projects:
{projects_json}

Return JSON: {{"projects": [same structure with improved descriptions and bullets]}}
Rules:
- Improve wording using only the existing description and bullets; do not add outcomes, facts, technologies, or quantified claims
- Keep project count, names, dates, URLs, technologies, and number of bullets EXACTLY the same
- Keep empty project fields empty"""


# ─────────────────────────────────────────────────────────────────────────────
#  AI Suggestions Prompts
# ─────────────────────────────────────────────────────────────────────────────

SUGGESTION_PROMPTS = {
    "add_achievements": """Improve the wording of achievements already present in the resume.
Never invent a measurable outcome, estimate, responsibility, or experience. If no achievement is supplied, return the resume unchanged.
Resume JSON: {resume_json}
Return improved full resume JSON.""",

    "improve_action_verbs": """Replace weak or passive verbs with strong action verbs.
Bad examples: "responsible for", "helped with", "worked on", "assisted in"
Good examples: "Led", "Engineered", "Reduced", "Launched", "Architected", "Optimized"
Resume JSON: {resume_json}
Return improved full resume JSON.""",

    "remove_repetition": """Remove repeated phrases, buzzwords, and duplicate information.
Look for the same words used across multiple bullets and vary the language.
Resume JSON: {resume_json}
Return improved full resume JSON.""",

    "add_missing_skills": """Add skills that are clearly implied by the experience but missing from the skills section.
Only add skills that are EVIDENCED by the experience bullets.
JD required skills: {jd_keywords}
Resume JSON: {resume_json}
Return improved full resume JSON.""",

    "improve_ats": """Optimize formatting and wording for ATS systems using only evidence in the resume.
Do not add a JD keyword unless the corresponding skill or experience is already present in the resume.
JD keywords missing from resume: {missing_keywords}
Resume JSON: {resume_json}
Return improved full resume JSON.""",

    "reduce_to_one_page": """Shorten the resume to fit one page.
Remove oldest/least relevant experience bullets.
Shorten the summary to 2-3 sentences.
Keep all sections but reduce bullet count to 2-3 per role.
Resume JSON: {resume_json}
Return improved full resume JSON.""",

    "improve_technical_wording": """Improve technical precision and depth.
Use proper technical terminology, specific tool names, and engineering vocabulary.
Resume JSON: {resume_json}
Return improved full resume JSON.""",

    "improve_leadership_wording": """Emphasize leadership, ownership, and cross-functional impact.
Highlight team sizes, stakeholder management, and organizational impact.
Resume JSON: {resume_json}
Return improved full resume JSON.""",
}
