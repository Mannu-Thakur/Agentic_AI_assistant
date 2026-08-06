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
  const cleanStr = (s: string) => {
    if (!s) return '';
    return s
      .replace(/\\textbf\{([^}]+)\}/g, '$1')
      .replace(/\\textit\{([^}]+)\}/g, '$1')
      .replace(/\\href\{[^}]+\}\{([^}]+)\}/g, '$1')
      .replace(/\\fa[A-Za-z0-9]+\s*/g, '')
      .replace(/\\[_&%$#{}]/g, (m) => m[1])
      .replace(/\\\\/g, ' ')
      .replace(/\\vspace\{[^}]+\}/g, '')
      .replace(/\\hfill/g, ' ')
      .replace(/\\noindent/g, '')
      .trim();
  };

  let name = 'Resume Contact';
  const nameM = latexCode.match(/\\Huge\s+(?:\\bfseries\s+)?(?:\\color\{[^}]+\}\s+)?([^}\\\n]+)/i) ||
                latexCode.match(/\\name\{([^}]+)\}/i);
  if (nameM) name = cleanStr(nameM[1]);

  let email = '';
  const emailM = latexCode.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
  if (emailM) email = emailM[0];

  let phone = '';
  const phoneM = latexCode.match(/(\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}/);
  if (phoneM) phone = phoneM[0];

  let headline = '';
  const headM = latexCode.match(/\\textit\{([^}]+)\}/i);
  if (headM && headM[1].length < 80) headline = cleanStr(headM[1]);

  let summary = '';
  const sumM = latexCode.match(/\\section\*?\{Professional Summary\}[\s\S]*?\n\n/i) ||
               latexCode.match(/\\section\*?\{Summary\}[\s\S]*?\n\n/i);
  if (sumM) summary = cleanStr(sumM[0]);

  return {
    personal: {
      name, email, phone, location: '', linkedin: '', github: '', website: '', portfolio: ''
    },
    headline,
    summary,
    skills: [{ category: 'Technical Skills', skills: [] }],
    experience: [],
    projects: [],
    education: [],
    certifications: [],
    achievements: [],
    languages: []
  };
}

