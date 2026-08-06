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

PARSE_RESUME_SYSTEM = """You are a precise resume parser. Your job is to extract structured information from resume text and return ONLY valid JSON.

Rules:
- Extract exactly what is written — do NOT infer, fabricate, or embellish
- If a field is not present, use an empty string "" or empty list []
- For skills, group them by category (Languages, Frameworks, Tools, Databases, Cloud, etc.)
- For experience bullets, preserve the original text exactly
- Dates should be kept as-is from the document (e.g. "Jan 2022", "2020 - 2022", "Present")
- Generate a short unique id for each experience, project, education, cert (use format "exp_1", "proj_1", etc.)
- Return ONLY the JSON object, no markdown, no explanation"""

PARSE_RESUME_USER = """Parse this resume text into structured JSON matching exactly this schema:

{{
  "personal": {{"name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": "", "website": "", "portfolio": ""}},
  "headline": "",
  "summary": "",
  "skills": [{{"category": "", "skills": []}}],
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
You are improving resume content to better match a job description.

CRITICAL RULES:
- Return ONLY valid JSON matching the input schema exactly
- NEVER add fake experiences, companies, degrees, or dates
- NEVER invent metrics or numbers that weren't in the original
- You MAY rewrite existing bullet points to use stronger action verbs
- You MAY quantify existing achievements with plausible ranges ONLY if the original implies it
- You MAY reorganize and prioritize skills to match JD requirements
- Do NOT change any dates, company names, or job titles
- Keep the same overall structure as the input"""

TAILOR_ALL_USER = """Improve this resume to better match the job requirements.
Style: {style}

Job Requirements:
- Role: {role} at {company}
- Required Skills: {required_skills}
- Key Keywords: {keywords}
- Experience Level: {experience_level}

Current Resume JSON:
{resume_json}

Return the improved resume as valid JSON with the exact same structure.
Focus on: stronger action verbs, keyword alignment, ATS optimization.
Do NOT fabricate any data. Improve only the wording and emphasis."""

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
