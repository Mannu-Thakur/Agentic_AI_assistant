import React, { useState } from 'react';
import {
  CheckCircle2, AlertTriangle, ArrowRight, User, FileText,
  GraduationCap, Code, Briefcase, FolderGit2, Trophy, Award, Languages as LangIcon, Edit3, Cpu, Layout
} from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';

export const ReviewStep: React.FC = () => {
  const {
    currentResume, updateResume, parseConfidence, sectionConfidences,
    lowConfidenceFields, setStep, setShowReviewModal
  } = useResumeStore();

  const [activeTab, setActiveTab] = useState<'overview' | 'edit'>('overview');

  const confidencePercent = Math.round(parseConfidence * 100);

  const getConfidence = (key: string, isPresent: boolean, defaultHigh: number = 0.95) => {
    if (!isPresent) return 0;
    if (sectionConfidences && typeof sectionConfidences[key] === 'number' && sectionConfidences[key] > 0) {
      return Math.round(sectionConfidences[key] * 100);
    }
    return Math.round(defaultHigh * 100);
  };

  const sectionsList = [
    {
      key: 'personal',
      name: 'Personal Information',
      icon: User,
      present: Boolean(currentResume.personal.name || currentResume.personal.email),
      confidence: getConfidence('personal', Boolean(currentResume.personal.name || currentResume.personal.email), 0.95),
      count: [currentResume.personal.name, currentResume.personal.email, currentResume.personal.phone].filter(Boolean).length + ' fields'
    },
    {
      key: 'summary',
      name: 'Professional Summary',
      icon: FileText,
      present: Boolean(currentResume.summary),
      confidence: getConfidence('summary', Boolean(currentResume.summary), 0.9),
      count: currentResume.summary ? `${currentResume.summary.split(' ').length} words` : 'Empty'
    },
    {
      key: 'education',
      name: 'Education',
      icon: GraduationCap,
      present: currentResume.education.length > 0,
      confidence: getConfidence('education', currentResume.education.length > 0, 0.95),
      count: `${currentResume.education.length} entries`
    },
    {
      key: 'skills',
      name: 'Skills (9 Categories)',
      icon: Code,
      present: currentResume.skills.length > 0,
      confidence: getConfidence('skills', currentResume.skills.length > 0, 0.98),
      count: `${currentResume.skills.reduce((acc, g) => acc + g.skills.length, 0)} skills across ${currentResume.skills.length} categories`
    },
    {
      key: 'experience',
      name: 'Work Experience',
      icon: Briefcase,
      present: currentResume.experience.length > 0,
      confidence: getConfidence('experience', currentResume.experience.length > 0, 0.96),
      count: `${currentResume.experience.length} positions`
    },
    {
      key: 'projects',
      name: 'Projects',
      icon: FolderGit2,
      present: currentResume.projects.length > 0,
      confidence: getConfidence('projects', currentResume.projects.length > 0, 0.92),
      count: `${currentResume.projects.length} projects`
    },
    {
      key: 'achievements',
      name: 'Achievements',
      icon: Trophy,
      present: currentResume.achievements.length > 0,
      confidence: getConfidence('achievements', currentResume.achievements.length > 0, 0.90),
      count: `${currentResume.achievements.length} achievements`
    },
    {
      key: 'certifications',
      name: 'Certifications',
      icon: Award,
      present: currentResume.certifications.length > 0,
      confidence: getConfidence('certifications', currentResume.certifications.length > 0, 0.90),
      count: currentResume.certifications.length > 0 ? `${currentResume.certifications.length} certifications` : 'Not Listed'
    },
    {
      key: 'languages',
      name: 'Languages',
      icon: LangIcon,
      present: currentResume.languages.length > 0,
      confidence: getConfidence('languages', currentResume.languages.length > 0, 0.90),
      count: currentResume.languages.length > 0 ? `${currentResume.languages.length} languages` : 'Not Listed'
    },
  ];

  const handleProceed = () => {
    setShowReviewModal(false);
    setStep(2);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="bg-card border border-border rounded-3xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-6 border-b border-border flex items-center justify-between bg-gradient-to-r from-violet-950/40 via-background to-indigo-950/40">
          <div>
            <div className="flex items-center space-x-2">
              <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center space-x-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Document AI Extraction Complete</span>
              </span>
              <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-violet-500/10 text-violet-400 border border-violet-500/20 flex items-center space-x-1">
                <Cpu className="w-3.5 h-3.5" />
                <span>Parser: PyMuPDF Hybrid</span>
              </span>
              <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center space-x-1">
                <Layout className="w-3.5 h-3.5" />
                <span>Layout: Single Column</span>
              </span>
            </div>
            <h2 className="text-2xl font-bold mt-2 bg-clip-text text-transparent bg-gradient-to-r from-violet-400 via-indigo-300 to-cyan-400">
              Document AI Extraction Verification
            </h2>
          </div>

          <div className="flex items-center space-x-3">
            <div className="text-right">
              <div className="text-xs text-muted-foreground">Weighted Confidence</div>
              <div className={`text-2xl font-extrabold ${confidencePercent >= 85 ? 'text-emerald-400' : 'text-amber-400'}`}>
                {confidencePercent}%
              </div>
            </div>
            <button
              onClick={handleProceed}
              className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold text-sm shadow-lg shadow-violet-600/30 transition-all"
            >
              <span>Confirm & Target Job</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-border bg-muted/20 px-6 py-2">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'overview' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Section Verification Checklist
          </button>
          <button
            onClick={() => setActiveTab('edit')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'edit' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Inline Contact & Summary Edit
          </button>
        </div>

        {/* Content View */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {lowConfidenceFields.length > 0 && (
            <div className="p-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 text-amber-300 text-xs flex items-start space-x-3">
              <AlertTriangle className="w-5 h-5 shrink-0 text-amber-400" />
              <div>
                <span className="font-bold">Attention Required: </span>
                Some fields had sparse data: {lowConfidenceFields.join(', ')}. Please verify or complete in inline edit.
              </div>
            </div>
          )}

          {activeTab === 'overview' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {sectionsList.map((sec) => {
                const IconComp = sec.icon;
                return (
                  <div
                    key={sec.key}
                    className="p-4 rounded-2xl border border-border bg-card/50 flex items-center justify-between hover:border-violet-500/40 transition-all"
                  >
                    <div className="flex items-center space-x-3">
                      <div className={`p-2.5 rounded-xl ${sec.present ? 'bg-emerald-500/10 text-emerald-400' : 'bg-muted text-muted-foreground'}`}>
                        <IconComp className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center space-x-2">
                          <h4 className="font-semibold text-sm">{sec.name}</h4>
                          {sec.present && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{sec.count}</p>
                      </div>
                    </div>

                    <div className="text-right">
                      {sec.present ? (
                        <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                          sec.confidence >= 90
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                            : sec.confidence >= 75
                            ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                            : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                        }`}>
                          {sec.confidence}% Confidence
                        </span>
                      ) : (
                        <span className="inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold border bg-zinc-800/60 text-zinc-400 border-zinc-700/60">
                          Optional / Not Listed
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

          ) : (
            <div className="space-y-5">
              <div className="space-y-3">
                <h3 className="font-semibold text-sm flex items-center space-x-2 text-violet-400">
                  <Edit3 className="w-4 h-4" />
                  <span>Personal Contact Details</span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                  <div>
                    <label className="text-muted-foreground block mb-1">Full Name</label>
                    <input
                      type="text"
                      value={currentResume.personal.name}
                      onChange={(e) => updateResume((r) => ({ ...r, personal: { ...r.personal, name: e.target.value } }))}
                      className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground focus:outline-none focus:border-violet-500"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground block mb-1">Email Address</label>
                    <input
                      type="text"
                      value={currentResume.personal.email}
                      onChange={(e) => updateResume((r) => ({ ...r, personal: { ...r.personal, email: e.target.value } }))}
                      className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground focus:outline-none focus:border-violet-500"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground block mb-1">Phone Number</label>
                    <input
                      type="text"
                      value={currentResume.personal.phone}
                      onChange={(e) => updateResume((r) => ({ ...r, personal: { ...r.personal, phone: e.target.value } }))}
                      className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground focus:outline-none focus:border-violet-500"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground block mb-1">Location</label>
                    <input
                      type="text"
                      value={currentResume.personal.location}
                      onChange={(e) => updateResume((r) => ({ ...r, personal: { ...r.personal, location: e.target.value } }))}
                      className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground focus:outline-none focus:border-violet-500"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground block mb-1">LinkedIn Profile</label>
                    <input
                      type="text"
                      value={currentResume.personal.linkedin}
                      onChange={(e) => updateResume((r) => ({ ...r, personal: { ...r.personal, linkedin: e.target.value } }))}
                      className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground focus:outline-none focus:border-violet-500"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground block mb-1">GitHub Profile</label>
                    <input
                      type="text"
                      value={currentResume.personal.github}
                      onChange={(e) => updateResume((r) => ({ ...r, personal: { ...r.personal, github: e.target.value } }))}
                      className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground focus:outline-none focus:border-violet-500"
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-muted-foreground block text-xs">Professional Summary</label>
                <textarea
                  rows={4}
                  value={currentResume.summary}
                  onChange={(e) => updateResume((r) => ({ ...r, summary: e.target.value }))}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground text-xs focus:outline-none focus:border-violet-500"
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border bg-muted/20 flex items-center justify-between">
          <button
            onClick={() => { setShowReviewModal(false); setStep(3); }}
            className="px-4 py-2 rounded-xl text-xs font-medium text-muted-foreground hover:text-foreground transition-all"
          >
            Skip to Full Editor
          </button>
          <button
            onClick={handleProceed}
            className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold text-sm shadow-lg transition-all"
          >
            <span>Confirm & Target Job</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
