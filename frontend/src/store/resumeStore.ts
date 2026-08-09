import { create } from 'zustand';
import {
  ResumeData, JDAnalysis, ATSScoreBreakdown,
  ResumeVersion, TemplateType, DiffResponse
} from '../types/resume';
import { resumeApi } from '../services/resumeApi';

export const createEmptyResume = (): ResumeData => ({
  personal: {
    name: '',
    email: '',
    phone: '',
    location: '',
    linkedin: '',
    github: '',
    website: '',
    portfolio: '',
  },
  headline: '',
  summary: '',
  skills: [
    { category: 'Technical Skills', skills: [] },
  ],
  experience: [],
  projects: [],
  education: [],
  certifications: [],
  achievements: [],
  languages: [],
});

interface ResumeState {
  // Step & Tab management
  step: 1 | 2 | 3;
  activeTab: 'editor' | 'preview' | 'diff' | 'ats' | 'suggestions' | 'versions' | 'templates' | 'export' | 'latex';
  
  // Data
  currentResume: ResumeData;
  originalResume: ResumeData | null;
  jdAnalysis: JDAnalysis | null;
  atsScore: ATSScoreBreakdown | null;
  diffResult: DiffResponse | null;
  versions: ResumeVersion[];
  selectedTemplate: TemplateType;

  // Loading states
  isAnalyzingResume: boolean;
  isAnalyzingJD: boolean;
  isTailoring: boolean;
  isComputingATS: boolean;
  isApplyingSuggestion: boolean;
  parseConfidence: number;
  lowConfidenceFields: string[];
  sectionConfidences: Record<string, number>;
  showReviewModal: boolean;

  // Actions
  setStep: (step: 1 | 2 | 3) => void;
  setActiveTab: (tab: ResumeState['activeTab']) => void;
  setTemplate: (template: TemplateType) => void;
  setShowReviewModal: (show: boolean) => void;
  updateResume: (updater: (prev: ResumeData) => ResumeData) => void;
  setResumeData: (data: ResumeData) => void;

  // Async actions
  uploadAndParseResume: (file: File) => Promise<void>;
  analyzeJD: (jdText: string) => Promise<void>;
  tailorResume: (section?: string, style?: string) => Promise<void>;
  recomputeATS: () => Promise<void>;
  computeDiff: () => Promise<void>;
  applySuggestion: (type: string) => Promise<void>;
  pushVersion: (label: string, description: string) => void;
  restoreVersion: (versionId: string) => void;
  resetAll: () => void;
}

export const useResumeStore = create<ResumeState>((set, get) => ({
  step: 1,
  activeTab: 'editor',
  currentResume: createEmptyResume(),
  originalResume: null,
  jdAnalysis: null,
  atsScore: null,
  diffResult: null,
  versions: [],
  selectedTemplate: 'modern',

  isAnalyzingResume: false,
  isAnalyzingJD: false,
  isTailoring: false,
  isComputingATS: false,
  isApplyingSuggestion: false,
  parseConfidence: 1.0,
  lowConfidenceFields: [],
  sectionConfidences: {},
  showReviewModal: false,

  setStep: (step) => set({ step }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setTemplate: (template) => set({ selectedTemplate: template }),
  setShowReviewModal: (show) => set({ showReviewModal: show }),

  updateResume: (updater) => {
    const next = updater(get().currentResume);
    set({ currentResume: next });
    // Auto-recompute ATS score locally or via API if JD present
    get().recomputeATS();
  },

  setResumeData: (data) => {
    set({ currentResume: data });
    get().recomputeATS();
  },

  uploadAndParseResume: async (file) => {
    set({ isAnalyzingResume: true });
    try {
      const res = await resumeApi.analyzeResume(file);
      set({
        currentResume: res.resume,
        originalResume: res.resume,
        parseConfidence: res.parse_confidence,
        lowConfidenceFields: res.low_confidence_fields,
        sectionConfidences: res.section_confidences || {},
        showReviewModal: true,
      });

      // Initial version push
      get().pushVersion('Original Resume', `Parsed from ${file.name}`);
      get().recomputeATS();
    } catch (err: any) {
      const message = err?.message || 'Failed to parse resume. Please try again.';
      console.error('[Store] uploadAndParseResume failed:', err);
      throw new Error(message);
    } finally {
      set({ isAnalyzingResume: false });
    }
  },

  analyzeJD: async (jdText) => {
    set({ isAnalyzingJD: true });
    try {
      const res = await resumeApi.analyzeJD(jdText);
      set({ jdAnalysis: res.jd_analysis });
      // Navigate to step 3 so the user can review extracted keywords
      // and choose tailoring options themselves — do NOT auto-trigger tailorResume.
      set({ step: 3, activeTab: 'editor' });
    } catch (err: any) {
      const message = err?.message || 'Failed to analyze job description. Please try again.';
      console.error('[Store] analyzeJD failed:', err);
      throw new Error(message);
    } finally {
      set({ isAnalyzingJD: false });
    }
  },

  tailorResume: async (section = 'all', style = 'rewrite') => {
    const { currentResume, jdAnalysis } = get();
    if (!jdAnalysis) return;

    set({ isTailoring: true });
    try {
      const res = await resumeApi.tailorResume({
        resume: currentResume,
        jd_analysis: jdAnalysis,
        section,
        style,
      });

      const updated = res.tailored_resume;
      set({ currentResume: updated });
      get().pushVersion(`AI Tailored (${section})`, res.changes_summary.join(', '));
      await get().recomputeATS();
      await get().computeDiff();
      set({ activeTab: 'preview' });
    } catch (err: any) {
      const message = err?.message || 'Failed to tailor resume. Please try again.';
      console.error('[Store] tailorResume failed:', err);
      throw new Error(message);
    } finally {
      set({ isTailoring: false });
    }
  },

  recomputeATS: async () => {
    const { currentResume, jdAnalysis } = get();
    set({ isComputingATS: true });
    try {
      const res = await resumeApi.computeATS({
        resume: currentResume,
        jd_analysis: jdAnalysis || undefined,
      });
      set({ atsScore: res.score });
    } catch {
      // Non-blocking
    } finally {
      set({ isComputingATS: false });
    }
  },

  computeDiff: async () => {
    const { originalResume, currentResume } = get();
    if (!originalResume) return;

    try {
      const res = await resumeApi.computeDiff({
        original: originalResume,
        tailored: currentResume,
      });
      set({ diffResult: res });
    } catch {
      // Non-blocking
    }
  },

  applySuggestion: async (type) => {
    const { currentResume, jdAnalysis } = get();
    set({ isApplyingSuggestion: true });
    try {
      const res = await resumeApi.applySuggestion({
        resume: currentResume,
        suggestion_type: type,
        jd_analysis: jdAnalysis || undefined,
      });
      set({ currentResume: res.updated_resume });
      get().pushVersion(`Suggestion: ${type}`, res.changes.join(', '));
      await get().recomputeATS();
    } catch (err: any) {
      const message = err?.message || 'Failed to apply suggestion. Please try again.';
      console.error('[Store] applySuggestion failed:', err);
      throw new Error(message);
    } finally {
      set({ isApplyingSuggestion: false });
    }
  },

  pushVersion: (label, description) => {
    const { currentResume, atsScore, versions } = get();
    const newVer: ResumeVersion = {
      version_id: `v_${Date.now()}`,
      label,
      resume: JSON.parse(JSON.stringify(currentResume)),
      ats_score: atsScore || undefined,
      created_at: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      description,
    };
    set({ versions: [newVer, ...versions] });
  },

  restoreVersion: (versionId) => {
    const ver = get().versions.find((v) => v.version_id === versionId);
    if (ver) {
      set({ currentResume: JSON.parse(JSON.stringify(ver.resume)) });
      get().recomputeATS();
    }
  },

  resetAll: () => {
    set({
      step: 1,
      activeTab: 'editor',
      currentResume: createEmptyResume(),
      originalResume: null,
      jdAnalysis: null,
      atsScore: null,
      diffResult: null,
      versions: [],
      parseConfidence: 1.0,
      lowConfidenceFields: [],
      sectionConfidences: {},
      showReviewModal: false,
    });
  },
}));
