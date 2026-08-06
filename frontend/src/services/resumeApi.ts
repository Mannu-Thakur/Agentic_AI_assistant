import { apiRequest } from './api';
import {
  ResumeData, JDAnalysis, ATSScoreBreakdown,
  DiffResponse, TemplateType
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

  async downloadExport(params: {
    resume: ResumeData;
    format: 'pdf' | 'docx' | 'markdown' | 'json';
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
};
