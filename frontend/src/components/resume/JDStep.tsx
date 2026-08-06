import React, { useState } from 'react';
import { Briefcase, Sparkles, ArrowRight, ArrowLeft } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';

export const JDStep: React.FC = () => {
  const [jdText, setJdText] = useState('');
  const { analyzeJD, isAnalyzingJD, isTailoring, setStep } = useResumeStore();

  const isLoading = isAnalyzingJD || isTailoring;

  const handleAnalyze = async () => {
    if (!jdText.trim() || jdText.trim().length < 30) {
      alert('Please paste a job description with at least 30 characters.');
      return;
    }
    try {
      await analyzeJD(jdText);
    } catch (err: any) {
      alert(err.message || 'Failed to analyze Job Description');
    }
  };

  const handleSkip = () => {
    setStep(3);
  };

  return (
    <div className="max-w-4xl mx-auto py-10 px-6 space-y-8 animate-in fade-in duration-300">
      {/* Title */}
      <div className="text-center space-y-4">
        <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-xs font-semibold backdrop-blur-md shadow-lg shadow-indigo-950/40">
          <Briefcase className="w-4 h-4 text-indigo-400" />
          <span>Step 2 of 3 — Target Job Matching</span>
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-indigo-300 via-violet-200 to-cyan-300 leading-tight">
          Paste the Job Description
        </h1>
        <p className="text-muted-foreground text-sm max-w-xl mx-auto leading-relaxed">
          AI will extract required skills, keywords, experience level, and tech stack to compute a precise ATS compatibility score and tailor your resume.
        </p>
      </div>

      {/* JD Textarea Card */}
      <div className="glass-card-premium p-6 rounded-3xl border border-white/10 shadow-2xl space-y-5">
        <div className="flex items-center justify-between">
          <label className="text-sm font-bold text-foreground flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-violet-400 animate-pulse" />
            <span>Job Description Text</span>
          </label>
          <span className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-xs text-muted-foreground font-mono">
            {jdText.length} characters
          </span>
        </div>

        <textarea
          rows={10}
          value={jdText}
          disabled={isLoading}
          onChange={(e) => setJdText(e.target.value)}
          placeholder="Paste the full job posting here (e.g. Senior Software Engineer at Google... required skills: Python, React, PostgreSQL, Docker)..."
          className="w-full p-4 rounded-2xl border border-white/10 bg-black/40 text-foreground placeholder:text-muted-foreground/40 text-sm focus:outline-none focus:border-violet-500/60 focus:ring-2 focus:ring-violet-500/20 resize-y leading-relaxed backdrop-blur-sm transition-all disabled:opacity-60"
        />

        {/* Buttons */}
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => setStep(1)}
            disabled={isLoading}
            className="flex items-center space-x-2 px-4 py-2.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-xs font-semibold transition-all hover:scale-105 active:scale-95 disabled:opacity-50"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Upload</span>
          </button>

          <div className="flex items-center space-x-3">
            <button
              onClick={handleSkip}
              disabled={isLoading}
              className="px-4 py-2.5 rounded-xl border border-white/10 bg-transparent hover:bg-white/5 text-xs font-medium text-muted-foreground hover:text-foreground transition-all disabled:opacity-50"
            >
              Skip for General Resume
            </button>
            <button
              onClick={handleAnalyze}
              disabled={isLoading || !jdText.trim()}
              className="glow-button flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 via-indigo-600 to-cyan-600 hover:from-violet-500 hover:to-cyan-500 disabled:opacity-50 text-white font-semibold text-sm transition-all shadow-xl shadow-violet-600/30 ring-1 ring-white/20"
            >
              {isLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>{isAnalyzingJD ? "Extracting Keywords..." : "Tailoring Resume with AI..."}</span>
                </>
              ) : (
                <>
                  <span>Analyze & Tailor</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
