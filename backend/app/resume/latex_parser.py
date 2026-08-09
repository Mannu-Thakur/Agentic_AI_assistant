"""
app/resume/latex_parser.py — Parser for converting raw LaTeX resume code into canonical ResumeData.

Extracts structured personal info, summary, skills, experience, projects, education,
certifications, and achievements from standard & custom LaTeX resume files.
"""

import re
import uuid
from typing import Dict, List, Any
from app.resume.models import (
    ResumeData, PersonalInfo, SkillGroup, ExperienceEntry,
    ProjectEntry, EducationEntry, CertificationEntry, AchievementEntry, LanguageEntry
)

def unescape_latex_text(text: str) -> str:
    """Remove LaTeX escape characters and formatting macros."""
    if not text:
        return ""
    
    # Replace LaTeX escaped chars
    s = text
    s = s.replace(r'\_', '_').replace(r'\&', '&').replace(r'\%', '%')
    s = s.replace(r'\$', '$').replace(r'\{', '{').replace(r'\}', '}')
    s = s.replace(r'\#', '#').replace(r'\~', '~').replace(r'\^', '^')
    s = s.replace(r'\cdot', '•').replace(r'\bullet', '•')
    
    # Remove text styling tags like \textbf{...}, \textit{...}, \small{...}, \color{...}{...}
    s = re.sub(r'\\textbf\{([^}]+)\}', r'\1', s)
    s = re.sub(r'\\textit\{([^}]+)\}', r'\1', s)
    s = re.sub(r'\\emph\{([^}]+)\}', r'\1', s)
    s = re.sub(r'\\underline\{([^}]+)\}', r'\1', s)
    s = re.sub(r'\\color\{[^}]+\}\{([^}]+)\}', r'\1', s)
    s = re.sub(r'\\color\{[^}]+\}', '', s)
    s = re.sub(r'\\small\b', '', s)
    s = re.sub(r'\\Large\b', '', s)
    s = re.sub(r'\\Huge\b', '', s)
    s = re.sub(r'\\large\b', '', s)
    s = re.sub(r'\\bfseries\b', '', s)
    s = re.sub(r'\\itshape\b', '', s)
    
    # Remove hrefs but keep display text
    s = re.sub(r'\\href\{[^}]+\}\{([^}]+)\}', r'\1', s)
    
    # Remove icons like \faEnvelope, \faPhone, \faGithub, etc.
    s = re.sub(r'\\fa[A-Za-z0-9]+\b', '', s)
    
    # Remove spacing macros like \\, \vspace{...}, \hfill, \noindent, \titlerule
    s = s.replace(r'\\', ' ')
    s = re.sub(r'\\vspace\{[^}]+\}', '', s)
    s = re.sub(r'\\hspace\{[^}]+\}', '', s)
    s = re.sub(r'\\hfill\b', ' ', s)
    s = s.replace(r'\noindent', '')
    s = s.replace(r'\titlerule', '')
    
    # Clean up whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def extract_urls_and_emails(text: str) -> Dict[str, str]:
    """Extract email, linkedin, github, website from LaTeX href or text."""
    res = {}
    
    # Search hrefs
    hrefs = re.findall(r'\\href\{([^}]+)\}\{([^}]+)\}', text)
    for target, label in hrefs:
        target_lower = target.lower()
        if "mailto:" in target_lower or "@" in target:
            res['email'] = target.replace("mailto:", "").strip()
        elif "linkedin.com" in target_lower:
            res['linkedin'] = target.strip()
        elif "github.com" in target_lower:
            res['github'] = target.strip()
        elif target.startswith("http"):
            res['website'] = target.strip()
            
    # Search raw text for email if not found
    if 'email' not in res:
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        if email_match:
            res['email'] = email_match.group(0)
            
    # Search phone numbers
    phone_match = re.search(r'(\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}', text)
    if phone_match:
        res['phone'] = phone_match.group(0)
        
    return res

def parse_latex_to_resume(latex_code: str) -> ResumeData:
    """
    Parse a LaTeX code string into a ResumeData Pydantic model.
    """
    personal = PersonalInfo(
        name="", email="", phone="", location="",
        linkedin="", github="", website="", portfolio=""
    )
    
    headline = ""
    summary = ""
    skills: List[SkillGroup] = []
    experience: List[ExperienceEntry] = []
    projects: List[ProjectEntry] = []
    education: List[EducationEntry] = []
    certifications: List[CertificationEntry] = []
    achievements: List[AchievementEntry] = []
    languages: List[LanguageEntry] = []

    # 1. Extract Header & Personal Info
    # Look for name: {\Huge \bfseries ... Name ...} or \name{...}
    name_match = re.search(r'\\name\{([^}]+)\}', latex_code)
    if not name_match:
        name_match = re.search(r'\\Huge\s+(?:\\bfseries\s+)?(?:\\color\{[^}]+\}\s+)?([^}\\\n]+)', latex_code)
    if not name_match:
        name_match = re.search(r'\\begin\{center\}\s*\{?\\Huge\s+([^}\\\n]+)', latex_code)
        
    if name_match:
        personal.name = unescape_latex_text(name_match.group(1))
        
    # Headline check
    headline_match = re.search(r'\\textit\{([^}]+)\}', latex_code[:1000])
    if headline_match:
        headline_cand = unescape_latex_text(headline_match.group(1))
        if len(headline_cand) < 80 and not any(k in headline_cand.lower() for k in ['http', 'email', '@', 'phone']):
            headline = headline_cand

    # Contact details extraction
    contact_data = extract_urls_and_emails(latex_code)
    if 'email' in contact_data:
        personal.email = contact_data['email']
    if 'phone' in contact_data:
        personal.phone = contact_data['phone']
    if 'linkedin' in contact_data:
        personal.linkedin = contact_data['linkedin']
    if 'github' in contact_data:
        personal.github = contact_data['github']
    if 'website' in contact_data:
        personal.website = contact_data['website']

    # Location search in top section
    loc_match = re.search(r'\\faMapMarkerAlt\\\s*([^\\$\n]+)', latex_code) or re.search(r'\\faMapMarker\\\s*([^\\$\n]+)', latex_code)
    if loc_match:
        personal.location = unescape_latex_text(loc_match.group(1))

    # 2. Split Document into Sections
    # Find all \section*{Title} or \section{Title}
    section_splits = re.split(r'\\section\*?\{([^}]+)\}', latex_code)
    
    if len(section_splits) > 1:
        # First chunk before section title is document preamble / header
        for i in range(1, len(section_splits), 2):
            sec_title = section_splits[i].strip().lower()
            sec_content = section_splits[i+1] if i+1 < len(section_splits) else ""
            
            # --- Professional Summary ---
            if any(k in sec_title for k in ['summary', 'profile', 'objective', 'about']):
                clean_sum = unescape_latex_text(sec_content)
                summary = clean_sum
                
            # --- Skills ---
            elif any(k in sec_title for k in ['skills', 'technologies', 'competencies']):
                items = re.findall(r'\\item\s*(\\textbf\{([^}]+)\}:?)?\s*([^\n\\]+)', sec_content)
                if items:
                    for item in items:
                        cat = unescape_latex_text(item[1]) if item[1] else "General"
                        sk_str = unescape_latex_text(item[2])
                        sk_list = [s.strip() for s in sk_str.split(',') if s.strip()]
                        if sk_list:
                            skills.append(SkillGroup(category=cat, skills=sk_list))
                else:
                    # Fallback plain text parse
                    lines = [unescape_latex_text(l) for l in sec_content.split('\n') if unescape_latex_text(l)]
                    if lines:
                        skills.append(SkillGroup(category="Technical Skills", skills=lines))

            # --- Work Experience ---
            elif any(k in sec_title for k in ['experience', 'employment', 'work', 'history']):
                # Look for bold role/company lines
                blocks = re.split(r'\\textbf\{([^}]+)\}', sec_content)
                if len(blocks) > 1:
                    for b_idx in range(1, len(blocks), 2):
                        role_name = unescape_latex_text(blocks[b_idx])
                        block_body = blocks[b_idx+1] if b_idx+1 < len(blocks) else ""
                        
                        # Date search in top of block_body
                        date_match = re.search(r'\\hfill\s*\{?[^}]*?([A-Za-z0-9\s–\--]+)\}?', block_body)
                        date_str = unescape_latex_text(date_match.group(1)) if date_match else ""
                        
                        # Company search
                        comp_match = re.search(r'\\textit\{([^}]+)\}', block_body)
                        comp_name = unescape_latex_text(comp_match.group(1)) if comp_match else ""
                        
                        # Bullets
                        bullets = [unescape_latex_text(b) for b in re.findall(r'\\item\s+([^\n\\]+)', block_body)]
                        bullets = [b for b in bullets if b]
                        
                        if role_name or comp_name:
                            experience.append(ExperienceEntry(
                                id=f"exp_{uuid.uuid4().hex[:6]}",
                                company=comp_name or "",
                                role=role_name or "",
                                location="",
                                start_date=date_str,
                                end_date="Present" if "present" in date_str.lower() else "",
                                is_current="present" in date_str.lower(),
                                bullets=bullets,
                                technologies=[]
                            ))

            # --- Projects ---
            elif any(k in sec_title for k in ['project', 'portfolio']):
                blocks = re.split(r'\\textbf\{([^}]+)\}', sec_content)
                if len(blocks) > 1:
                    for b_idx in range(1, len(blocks), 2):
                        proj_title = unescape_latex_text(blocks[b_idx])
                        block_body = blocks[b_idx+1] if b_idx+1 < len(blocks) else ""
                        
                        techs = []
                        tech_match = re.search(r'\(([^)]+)\)', block_body)
                        if tech_match:
                            techs = [t.strip() for t in unescape_latex_text(tech_match.group(1)).split(',')]
                            
                        bullets = [unescape_latex_text(b) for b in re.findall(r'\\item\s+([^\n\\]+)', block_body)]
                        bullets = [b for b in bullets if b]
                        
                        if proj_title:
                            projects.append(ProjectEntry(
                                id=f"proj_{uuid.uuid4().hex[:6]}",
                                name=proj_title,
                                description="",
                                technologies=techs,
                                url="",
                                github_url="",
                                bullets=bullets,
                                start_date="",
                                end_date=""
                            ))

            # --- Education ---
            elif any(k in sec_title for k in ['education', 'academic']):
                blocks = re.split(r'\\textbf\{([^}]+)\}', sec_content)
                if len(blocks) > 1:
                    for b_idx in range(1, len(blocks), 2):
                        inst_name = unescape_latex_text(blocks[b_idx])
                        block_body = blocks[b_idx+1] if b_idx+1 < len(blocks) else ""
                        
                        deg_match = re.search(r'\\textit\{([^}]+)\}', block_body)
                        deg_name = unescape_latex_text(deg_match.group(1)) if deg_match else ""
                        
                        date_match = re.search(r'\\hfill\s*\{?[^}]*?([A-Za-z0-9\s–\--]+)\}?', block_body)
                        date_str = unescape_latex_text(date_match.group(1)) if date_match else ""
                        
                        gpa_match = re.search(r'GPA:\s*([0-9.]+)', block_body, re.IGNORECASE)
                        gpa_val = gpa_match.group(1) if gpa_match else ""
                        
                        if inst_name:
                            education.append(EducationEntry(
                                id=f"edu_{uuid.uuid4().hex[:6]}",
                                institution=inst_name,
                                degree=deg_name,
                                field_of_study="",
                                location="",
                                start_date=date_str,
                                end_date="",
                                gpa=gpa_val,
                                honors="",
                                relevant_courses=[]
                            ))

            # --- Certifications ---
            elif any(k in sec_title for k in ['certif', 'credential', 'license']):
                items = re.findall(r'\\item\s+([^\n\\]+)', sec_content)
                for it in items:
                    cert_txt = unescape_latex_text(it)
                    if cert_txt:
                        certifications.append(CertificationEntry(
                            id=f"cert_{uuid.uuid4().hex[:6]}",
                            name=cert_txt,
                            issuer="",
                            date="",
                            url="",
                            expiry=""
                        ))

            # --- Achievements ---
            elif any(k in sec_title for k in ['achievement', 'award', 'honor']):
                items = re.findall(r'\\item\s+([^\n\\]+)', sec_content)
                for it in items:
                    ach_txt = unescape_latex_text(it)
                    if ach_txt:
                        achievements.append(AchievementEntry(
                            id=f"ach_{uuid.uuid4().hex[:6]}",
                            title=ach_txt[:50],
                            description=ach_txt,
                            date=""
                        ))

    # Return ResumeData built from parsed contents
    return ResumeData(
        personal=personal,
        headline=headline,
        summary=summary,
        skills=skills,
        experience=experience,
        projects=projects,
        education=education,
        certifications=certifications,
        achievements=achievements,
        languages=languages
    )
