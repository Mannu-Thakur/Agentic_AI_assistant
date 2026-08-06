import React, { useState } from 'react';
import { Briefcase, Sparkles, ArrowRight, ArrowLeft } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';

export const JDStep: React.FC = () => {
  const [jdText, setJdText] = useState('');
  const { analyzeJD, isAnalyzingJD, setStep } = useResumeStore();

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
    <div className="max-w-3xl mx-auto py-12 px-6 space-y-8 animate-in fade-in duration-300">
      {/* Title */}
      <div className="text-center space-y-3">
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-400 text-xs font-semibold">
          <Briefcase className="w-3.5 h-3.5" />
          <span>Step 2 of 3 — Target Job Description</span>
        </div>
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 via-violet-400 to-cyan-400">
          Paste the Job Description
        </h1>
        <p className="text-muted-foreground text-sm max-w-xl mx-auto leading-relaxed">
          AI will extract required skills, keywords, experience level, and tech stack to compute a precise ATS compatibility score.
        </p>
      </div>

      {/* JD Textarea Card */}
      <div className="p-6 rounded-3xl border border-border bg-card/50 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <label className="text-sm font-semibold text-foreground flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-violet-400" />
            <span>Job Description Text</span>
          </label>
          <span className="text-xs text-muted-foreground">{jdText.length} characters</span>
        </div>

        <textarea
          rows={10}
          value={jdText}
          onChange={(e) => setJdText(e.target.value)}
          placeholder="Paste the full job posting here (e.g. Senior Software Engineer at Google... required skills: Python, React, PostgreSQL, Docker)..."
          className="w-full p-4 rounded-2xl border border-border bg-background/80 text-foreground placeholder:text-muted-foreground/50 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/50 resize-y leading-relaxed"
        />

        {/* Buttons */}
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => setStep(1)}
            className="flex items-center space-x-1.5 px-4 py-2.5 rounded-xl border border-border bg-secondary hover:bg-muted text-xs font-medium transition-all"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Upload</span>
          </button>

          <div className="flex items-center space-x-3">
            <button
              onClick={handleSkip}
              className="px-4 py-2.5 rounded-xl border border-border bg-transparent hover:bg-card text-xs font-medium text-muted-foreground hover:text-foreground transition-all"
            >
              Skip for General Resume
            </button>
            <button
              onClick={handleAnalyze}
              disabled={isAnalyzingJD || !jdText.trim()}
              className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-50 text-white font-medium text-sm transition-all shadow-lg shadow-violet-600/25"
            >
              {isAnalyzingJD ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Analyzing Keywords...</span>
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
