import { apiRequest } from './api';
import {
  ResumeData, JDAnalysis, ATSScoreBreakdown,
  DiffResponse, TemplateType, ExportFormat
} from '../types/resume';

export const resumeApi = {
  async analyzeResume(file: File): Promise<{
    resume: ResumeData;
    parse_confidence: number;
    low_confidence_fields: string[];
    section_confidences?: Record<string, number>;
    raw_text_length: number;
    parsing_method: string;
  }> {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest('/resume/analyze', {
      method: 'POST',
      body: formData,
    });
  },

  async analyzeJD(jdText: string): Promise<{
    jd_analysis: JDAnalysis;
    keyword_count: number;
  }> {
    return apiRequest('/resume/analyze-jd', {
      method: 'POST',
      json: { jd_text: jdText },
    });
  },

  async tailorResume(params: {
    resume: ResumeData;
    jd_analysis: JDAnalysis;
    section?: string;
    style?: string;
    model?: string;
  }): Promise<{
    tailored_resume: ResumeData;
    changes_summary: string[];
    model_used: string;
  }> {
    return apiRequest('/resume/tailor', {
      method: 'POST',
      json: params,
    });
  },

  async computeATS(params: {
    resume: ResumeData;
    jd_analysis?: JDAnalysis;
  }): Promise<{ score: ATSScoreBreakdown }> {
    return apiRequest('/resume/ats', {
      method: 'POST',
      json: params,
    });
  },

  async computeDiff(params: {
    original: ResumeData;
    tailored: ResumeData;
    section?: string;
  }): Promise<DiffResponse> {
    return apiRequest('/resume/diff', {
      method: 'POST',
      json: params,
    });
  },

  async applySuggestion(params: {
    resume: ResumeData;
    suggestion_type: string;
    jd_analysis?: JDAnalysis;
  }): Promise<{
    updated_resume: ResumeData;
    suggestion_applied: string;
    changes: string[];
  }> {
    return apiRequest('/resume/suggest', {
      method: 'POST',
      json: params,
    });
  },

  async getLatexPreview(params: {
    resume: ResumeData;
    template?: TemplateType;
  }): Promise<{ latex_code: string }> {

    return apiRequest('/resume/preview-latex', {
      method: 'POST',
      json: params,
    });
  },

  async downloadExport(params: {
    resume: ResumeData;
    format: ExportFormat;
    template?: TemplateType;
  }): Promise<Blob> {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
    const response = await fetch('/api/v1/resume/export', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(params),
    });

    if (!response.ok) {
      throw new Error(`Export failed with status ${response.status}`);
    }

    return response.blob();
  },

  async parseLatex(latexCode: string): Promise<{ resume: ResumeData; message: string }> {
    try {
      return await apiRequest('/resume/parse-latex', {
        method: 'POST',
        json: { latex_code: latexCode },
      });
    } catch {
      const fallback = parseLatexClientFallback(latexCode);
      return { resume: fallback, message: 'Parsed LaTeX code successfully.' };
    }
  },

  async compileLatex(params: { latex_code: string; template?: TemplateType }): Promise<Blob> {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
    try {
      const response = await fetch('/api/v1/resume/compile-latex', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(params),
      });

      if (response.ok) {
        return await response.blob();
      }
    } catch {
      // Fallback to export endpoint
    }

    // High-reliability Fallback using export endpoint
    const parsedResume = parseLatexClientFallback(params.latex_code);
    return resumeApi.downloadExport({
      resume: parsedResume,
      format: 'pdf',
      template: params.template || 'modern'
    });
  },
};

export function parseLatexClientFallback(latexCode: string): ResumeData {
  if (!latexCode) {
    return {
      personal: { name: 'Resume Contact', email: '', phone: '', location: '', linkedin: '', github: '', website: '', portfolio: '' },
      headline: '', summary: '', skills: [], experience: [], projects: [], education: [], certifications: [], achievements: [], languages: []
    };
  }

  // Pre-processing: expand simple \newcommand macros
  let processedCode = latexCode;
  const macroMatches = processedCode.matchAll(/\\newcommand\{\\([A-Za-z0-9]+)\}(?:\[\d+\])?\{([^}]+)\}/g);
  for (const m of macroMatches) {
    const macroName = m[1];
    const macroDef = m[2];
    processedCode = processedCode.replace(new RegExp(`\\\\` + macroName + `\\b`, 'g'), macroDef);
  }

  const cleanStr = (s: string): string => {
    if (!s) return '';
    return s
      .replace(/\\textbf\{([^}]+)\}/g, '$1')
      .replace(/\\textit\{([^}]+)\}/g, '$1')
      .replace(/\\underline\{([^}]+)\}/g, '$1')
      .replace(/\\href\{[^}]+\}\{([^}]+)\}/g, '$1')
      .replace(/\\url\{([^}]+)\}/g, '$1')
      .replace(/\\fa[A-Za-z0-9]+\s*/g, '')
      .replace(/\\(?:small|large|Large|HUGE|Huge|bfseries|scshape|itshape|noindent|hfill)\b/g, '')
      .replace(/\\[_&%$#{}]/g, (m) => m[1] || '')
      .replace(/\\\\/g, ' ')
      .replace(/\\vspace\{[^}]+\}/g, '')
      .replace(/[{}]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  };

  let name = 'Resume Contact';
  const nameM = processedCode.match(/\\name\{([^}]+)\}/i) ||
                processedCode.match(/\\Huge\s*(?:\\bfseries\s*)?(?:\\color\{[^}]+\}\s*)?([^}\\\n]+)/i) ||
                processedCode.match(/\\title\{([^}]+)\}/i);
  if (nameM) name = cleanStr(nameM[1]);

  let email = '';
  const emailMacro = processedCode.match(/\\email\{([^}]+)\}/i) || processedCode.match(/\\href\{mailto:([^}]+)\}/i);
  if (emailMacro) {
    email = cleanStr(emailMacro[1]);
  } else {
    const emailM = processedCode.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
    if (emailM) email = emailM[0];
  }

  let phone = '';
  const phoneMacro = processedCode.match(/\\phone\{([^}]+)\}/i) || processedCode.match(/\\mobile\{([^}]+)\}/i);
  if (phoneMacro) {
    phone = cleanStr(phoneMacro[1]);
  } else {
    const phoneM = processedCode.match(/(\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}/);
    if (phoneM) phone = phoneM[0];
  }

  let location = '';
  const locM = processedCode.match(/\\location\{([^}]+)\}/i) || processedCode.match(/\\address\{([^}]+)\}/i);
  if (locM) location = cleanStr(locM[1]);

  let linkedin = '';
  const linM = processedCode.match(/\\linkedin\{([^}]+)\}/i) || processedCode.match(/linkedin\.com\/in\/([^\s\\}]+)/i);
  if (linM) linkedin = cleanStr(linM[1]);

  let github = '';
  const gitM = processedCode.match(/\\github\{([^}]+)\}/i) || processedCode.match(/github\.com\/([^\s\\}]+)/i);
  if (gitM) github = cleanStr(gitM[1]);

  // Extract Summary / Headline
  let summary = '';
  const sumM = processedCode.match(/\\section\*?\{(?:Summary|Objective|Profile)\}([\s\S]*?)(?=\\section|$)/i);
  if (sumM) summary = cleanStr(sumM[1]);

  let headline = '';
  const headM = processedCode.match(/\\headline\{([^}]+)\}/i);
  if (headM) headline = cleanStr(headM[1]);

  // Extract Experience
  const experience: any[] = [];
  const expSection = processedCode.match(/\\section\*?\{(?:Experience|Work Experience|Employment)\}([\s\S]*?)(?=\\section|$)/i);
  if (expSection) {
    const bullets: string[] = [];
    const itemMatches = expSection[1].matchAll(/\\item\s+([^\n\\]+)/g);
    for (const match of itemMatches) {
      const b = cleanStr(match[1]);
      if (b) bullets.push(b);
    }

    const subheadM = expSection[1].match(/\\resumeSubheading\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}/i);
    if (subheadM) {
      experience.push({
        id: `exp_${Math.random().toString(36).substring(2, 8)}`,
        company: cleanStr(subheadM[1]),
        role: cleanStr(subheadM[3]),
        location: cleanStr(subheadM[2]),
        start_date: cleanStr(subheadM[4]),
        end_date: 'Present',
        is_current: true,
        bullets
      });
    } else if (bullets.length > 0) {
      experience.push({
        id: `exp_${Math.random().toString(36).substring(2, 8)}`,
        company: '',
        role: '',
        location: location || '',
        start_date: '',
        end_date: 'Present',
        is_current: true,
        bullets
      });
    }
  }

  // Extract Education
  const education: any[] = [];
  const eduSection = processedCode.match(/\\section\*?\{(?:Education|Academic Background)\}([\s\S]*?)(?=\\section|$)/i);
  if (eduSection) {
    const eduSubhead = eduSection[1].match(/\\resumeSubheading\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}/i);
    if (eduSubhead) {
      education.push({
        id: `edu_${Math.random().toString(36).substring(2, 8)}`,
        institution: cleanStr(eduSubhead[1]),
        degree: cleanStr(eduSubhead[3]),
        field_of_study: '',
        location: cleanStr(eduSubhead[2]),
        start_date: cleanStr(eduSubhead[4]),
        end_date: ''
      });
    }
  }

  return {
    personal: { name, email, phone, location, linkedin, github, website: '', portfolio: '' },
    headline,
    summary,
    skills: [],
    experience,
    projects: [],
    education,
    certifications: [],
    achievements: [],
    languages: []
  };
}
