// Types for AI Resume Builder

export interface PersonalInfo {
  name: string;
  email: string;
  phone: string;
  location: string;
  linkedin: string;
  github: string;
  website: string;
  portfolio: string;
}

export interface ExperienceEntry {
  id: string;
  company: string;
  role: string;
  location: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  bullets: string[];
  technologies: string[];
}

export interface ProjectEntry {
  id: string;
  name: string;
  description: string;
  technologies: string[];
  url: string;
  github_url: string;
  bullets: string[];
  start_date: string;
  end_date: string;
}

export interface EducationEntry {
  id: string;
  institution: string;
  degree: string;
  field_of_study: string;
  location: string;
  start_date: string;
  end_date: string;
  gpa: string;
  honors: string;
  relevant_courses: string[];
}

export interface CertificationEntry {
  id: string;
  name: string;
  issuer: string;
  date: string;
  url: string;
  expiry: string;
}

export interface AchievementEntry {
  id: string;
  title: string;
  description: string;
  date: string;
}

export interface LanguageEntry {
  language: string;
  proficiency: string;
}

export interface SkillGroup {
  category: string;
  skills: string[];
}

export interface ResumeData {
  personal: PersonalInfo;
  headline: string;
  summary: string;
  skills: SkillGroup[];
  experience: ExperienceEntry[];
  projects: ProjectEntry[];
  education: EducationEntry[];
  certifications: CertificationEntry[];
  achievements: AchievementEntry[];
  languages: LanguageEntry[];
}

export interface JDAnalysis {
  company: string;
  role: string;
  experience_level: string;
  required_skills: string[];
  preferred_skills: string[];
  technologies: string[];
  responsibilities: string[];
  soft_skills: string[];
  keywords: string[];
  nice_to_have: string[];
  industry: string;
  work_type: string;
}

export interface ATSScoreBreakdown {
  overall: number;
  keyword_match: number;
  section_completeness: number;
  formatting_quality: number;
  readability: number;
  contact_info: number;
  action_verbs: number;
  quantified_achievements: number;
  technical_skills_coverage: number;
  resume_length_score: number;
  matched_keywords: string[];
  missing_keywords: string[];
  recommendations: string[];
  duplicate_skills: string[];
}

export interface ResumeVersion {
  version_id: string;
  label: string;
  resume: ResumeData;
  ats_score?: ATSScoreBreakdown;
  created_at: string;
  description: string;
}

export interface DiffChunk {
  type: 'added' | 'removed' | 'unchanged';
  text: string;
}

export interface DiffSection {
  section: string;
  field: string;
  diff_type: 'added' | 'removed' | 'modified' | 'unchanged';
  original_text: string;
  new_text: string;
  chunks: DiffChunk[];
}

export interface DiffResponse {
  sections: DiffSection[];
  total_additions: number;
  total_removals: number;
  total_modifications: number;
  change_percentage: number;
}

export type TemplateType = 'classic_ats' | 'modern' | 'minimal' | 'executive' | 'developer' | 'academic';
