import { useNavigate } from 'react-router-dom';
import {
  Sparkles, ArrowLeft, FileText,
  ShieldCheck, GitCompare, Layout, Lightbulb, History,
  Download, RefreshCw, Wand2
} from 'lucide-react';
import { useResumeStore } from '../store/resumeStore';
import { UploadStep } from '../components/resume/UploadStep';
import { JDStep } from '../components/resume/JDStep';
import { ResumeEditor } from '../components/resume/ResumeEditor';
import { ATSDashboard } from '../components/resume/ATSDashboard';
import { DiffViewer } from '../components/resume/DiffViewer';
import { LivePreview } from '../components/resume/LivePreview';
import { TemplateSelector } from '../components/resume/TemplateSelector';
import { VersionHistory } from '../components/resume/VersionHistory';
import { SuggestionsPanel } from '../components/resume/SuggestionsPanel';
import { ExportPanel } from '../components/resume/ExportPanel';

export default function ResumePage() {
  const navigate = useNavigate();
  const {
    step, setStep, activeTab, setActiveTab,
    atsScore, isTailoring, tailorResume, resetAll
  } = useResumeStore();

  const handleTailorClick = (style = 'rewrite') => {
    tailorResume('all', style);
  };

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-background text-foreground">
      {/* ── Top Header Bar ── */}
      <header className="border-b border-border glass px-6 py-3 flex items-center justify-between sticky top-0 z-50 shrink-0">
        <div className="flex items-center space-x-3">
          <button
            onClick={() => navigate('/')}
            className="p-2 rounded-xl border border-border bg-secondary hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
            title="Back to Workspace"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-violet-900/20">
              <Sparkles className="w-4 h-4" />
            </div>
            <span className="font-bold text-base tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-indigo-400">
              AI Resume Builder
            </span>
          </div>
        </div>

        {/* Wizard Step Indicators */}
        <div className="hidden sm:flex items-center space-x-2 bg-secondary/50 p-1 rounded-xl border border-border text-xs font-medium">
          <button
            onClick={() => setStep(1)}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              step === 1 ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            1. Upload
          </button>
          <button
            onClick={() => setStep(2)}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              step === 2 ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            2. Target Job
          </button>
          <button
            onClick={() => setStep(3)}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              step === 3 ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            3. Review & Export
          </button>
        </div>

        {/* Right Actions */}
        <div className="flex items-center space-x-2">
          {atsScore && step === 3 && (
            <div className="flex items-center space-x-1.5 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-bold">
              <span>ATS Score: {atsScore.overall}%</span>
            </div>
          )}
          <button
            onClick={resetAll}
            className="p-2 rounded-xl border border-border bg-secondary hover:bg-muted text-xs font-medium text-muted-foreground hover:text-foreground transition-all"
            title="Reset All Data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* ── Main View Content ── */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {step === 1 && <UploadStep />}
        {step === 2 && <JDStep />}
        {step === 3 && (
          <div className="flex-1 min-h-0 flex flex-col">
            {/* Step 3 Sub-Navigation Tabs & AI Tailor Actions */}
            <div className="border-b border-border bg-card/40 px-6 py-2 flex items-center justify-between shrink-0 overflow-x-auto">
              <div className="flex items-center space-x-1">
                <button
                  onClick={() => setActiveTab('editor')}
                  className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium transition-all ${
                    activeTab === 'editor' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>Editor</span>
                </button>
                <button
                  onClick={() => setActiveTab('preview')}
                  className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium transition-all ${
                    activeTab === 'preview' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Live Preview</span>
                </button>
                <button
                  onClick={() => setActiveTab('ats')}
                  className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium transition-all ${
                    activeTab === 'ats' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>ATS Score</span>
                </button>
                <button
                  onClick={() => setActiveTab('diff')}
                  className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium transition-all ${
                    activeTab === 'diff' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <GitCompare className="w-3.5 h-3.5" />
                  <span>Diff</span>
                </button>
                <button
                  onClick={() => setActiveTab('templates')}
                  className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium transition-all ${
                    activeTab === 'templates' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Layout className="w-3.5 h-3.5" />
                  <span>Templates</span>
                </button>
                <button
                  onClick={() => setActiveTab('suggestions')}
                  className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium transition-all ${
                    activeTab === 'suggestions' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Lightbulb className="w-3.5 h-3.5" />
                  <span>AI Tips</span>
                </button>
                <button
                  onClick={() => setActiveTab('versions')}
                  className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium transition-all ${
                    activeTab === 'versions' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <History className="w-3.5 h-3.5" />
                  <span>History</span>
                </button>
                <button
                  onClick={() => setActiveTab('export')}
                  className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium transition-all ${
                    activeTab === 'export' ? 'bg-violet-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Export</span>
                </button>
              </div>

              {/* AI Tailor Action Button */}
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleTailorClick('rewrite')}
                  disabled={isTailoring}
                  className="flex items-center space-x-2 px-4 py-1.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-violet-600/25 disabled:opacity-50 transition-all"
                >
                  {isTailoring ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Tailoring Content...</span>
                    </>
                  ) : (
                    <>
                      <Wand2 className="w-3.5 h-3.5" />
                      <span>AI Tailor Resume</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Step 3 Active Tab View */}
            <div className="flex-1 min-h-0 overflow-y-auto">
              {activeTab === 'editor' && <ResumeEditor />}
              {activeTab === 'preview' && <LivePreview />}
              {activeTab === 'ats' && <ATSDashboard />}
              {activeTab === 'diff' && <DiffViewer />}
              {activeTab === 'templates' && <TemplateSelector />}
              {activeTab === 'suggestions' && <SuggestionsPanel />}
              {activeTab === 'versions' && <VersionHistory />}
              {activeTab === 'export' && <ExportPanel />}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
