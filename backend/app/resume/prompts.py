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
- PRESERVE EXISTING DATA: If the input resume has non-empty fields (name, existing companies, dates), preserve them while tailoring wording to target the JD.
- POPULATE MISSING SECTIONS: If any section (headline, summary, skills, experience, projects, education) is empty or missing, GENERATE professional, high-quality, production-grade content tailored specifically to the target role, experience level, and tech stack described in the JD!
- SKILLS CATEGORIZATION: Group skills logically into categories (e.g., Languages, Frameworks & AI, Databases & Storage, Cloud & DevOps).
- BULLET QUALITY: Start all experience bullets with strong action verbs (Architected, Engineered, Developed, Built, Spearheaded) and include quantified impact metrics where appropriate.
- Never return an incomplete or mostly-empty resume."""

TAILOR_ALL_USER = """Tailor and complete this resume to perfectly match the target job requirements.
Style: {style}

Target Job Details:
- Role: {role} at {company}
- Required Skills: {required_skills}
- Key Keywords: {keywords}
- Experience Level: {experience_level}

Current Resume JSON:
{resume_json}

INSTRUCTIONS:
1. Set 'headline' to a strong professional title matching the target role (e.g., {role}).
2. If 'summary' is empty or brief, write a compelling 3-4 sentence summary highlighting experience in {required_skills}.
3. Organize 'skills' into clean, categorized skill groups (e.g. Languages, Frameworks & AI, Databases & Storage, Cloud & DevOps) based on the JD tech stack.
4. If 'experience' is empty, generate 2 realistic, high-impact work experience entries tailored to this role with bullet points demonstrating expertise in {required_skills} and {keywords}. If 'experience' is not empty, rewrite bullet points to emphasize relevant skills and strong action verbs.
5. If 'projects' or 'education' are empty, generate realistic entries matching the JD requirements.

Return the complete tailored resume as valid JSON matching the exact schema."""

TAILOR_SUMMARY_USER = """Rewrite ONLY the summary section of this resume to better match the job.
Style: {style}

Target Role: {role} at {company}
Key Requirements: {required_skills}
Keywords to include naturally: {keywords}

Current summary:
{summary}

Return JSON: {{"summary": "improved summary here"}}
- 3-5 sentences maximum
- Start with a strong professional identity statement
- Include 2-3 of the most relevant keywords naturally
- Do NOT fabricate any credentials"""

TAILOR_SKILLS_USER = """Reorganize and optimize ONLY the skills section to match this job.
Style: {style}

Job Technologies Required: {technologies}
Job Keywords: {keywords}

Current skills:
{skills_json}

Return JSON: {{"skills": [same structure with skills prioritized for this role]}}
- Put most JD-relevant skills first within each category
- Add missing JD-required skills ONLY if they appear elsewhere in the resume context
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
- Start each bullet with a strong action verb (Developed, Led, Built, Reduced, Increased, etc.)
- Quantify existing achievements where reasonable (use ranges like "20-30%", "2x" if implied)
- Include relevant keywords naturally
- Keep company, role, dates, and location EXACTLY the same
- Do NOT add new bullet points — only improve existing ones"""

TAILOR_PROJECTS_USER = """Improve ONLY the projects section bullets to match this job.
Style: {style}

Target Role: {role}
Key Technologies: {technologies}

Current projects:
{projects_json}

Return JSON: {{"projects": [same structure with improved descriptions and bullets]}}
Rules:
- Lead with impact and technologies
- Include relevant keywords
- Keep names, dates, URLs exactly the same"""


# ─────────────────────────────────────────────────────────────────────────────
#  AI Suggestions Prompts
# ─────────────────────────────────────────────────────────────────────────────

SUGGESTION_PROMPTS = {
    "add_achievements": """Add measurable achievements to experience bullets.
For each bullet that describes a task, add or suggest a measurable outcome.
Use realistic ranges based on the role level and industry.
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

    "improve_ats": """Optimize for ATS systems.
Add missing JD keywords naturally into existing bullets.
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
