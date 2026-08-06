import React from 'react';
import { ShieldCheck, CheckCircle2, XCircle, Lightbulb, Target, Zap } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';

export const ATSDashboard: React.FC = () => {
  const { atsScore, jdAnalysis, isComputingATS } = useResumeStore();

  if (isComputingATS) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-10 h-10 border-4 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-muted-foreground">Computing ATS compatibility metrics...</p>
      </div>
    );
  }

  if (!atsScore) {
    return (
      <div className="py-20 text-center space-y-3">
        <ShieldCheck className="w-12 h-12 text-muted-foreground mx-auto" />
        <h3 className="font-semibold text-lg">No ATS Score Available</h3>
        <p className="text-xs text-muted-foreground max-w-sm mx-auto">
          Paste a Job Description in Step 2 to compute real keyword match % and alignment metrics.
        </p>
      </div>
    );
  }

  const scoreColor =
    atsScore.overall >= 80 ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' :
    atsScore.overall >= 60 ? 'text-amber-400 border-amber-500/30 bg-amber-500/10' :
    'text-red-400 border-red-500/30 bg-red-500/10';

  const subScores = [
    { label: 'Keyword Match', value: atsScore.keyword_match, weight: '25%' },
    { label: 'Action Verbs', value: atsScore.action_verbs, weight: '10%' },
    { label: 'Quantified Metrics', value: atsScore.quantified_achievements, weight: '10%' },
    { label: 'Technical Depth', value: atsScore.technical_skills_coverage, weight: '10%' },
    { label: 'Formatting Quality', value: atsScore.formatting_quality, weight: '10%' },
    { label: 'Readability', value: atsScore.readability, weight: '10%' },
    { label: 'Section Completeness', value: atsScore.section_completeness, weight: '15%' },
  ];

  return (
    <div className="space-y-8 p-6 max-w-4xl mx-auto overflow-y-auto max-h-[calc(100vh-140px)] custom-scrollbar">
      {/* Top Header Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Overall Score Gauge */}
        <div className={`p-6 rounded-3xl border ${scoreColor} flex flex-col items-center justify-center text-center space-y-2 relative overflow-hidden shadow-xl`}>
          <span className="text-xs font-semibold uppercase tracking-wider opacity-80">ATS Score</span>
          <div className="text-6xl font-extrabold tracking-tight">{atsScore.overall}%</div>
          <span className="text-xs opacity-90 font-medium">
            {atsScore.overall >= 80 ? '🚀 Highly Optimized' : atsScore.overall >= 60 ? '⚡ Needs Keyword Tuning' : '⚠️ Action Required'}
          </span>
        </div>

        {/* JD Context summary */}
        <div className="md:col-span-2 p-6 rounded-3xl border border-border bg-card/60 space-y-3">
          <div className="flex items-center space-x-2 text-violet-400 font-semibold text-sm">
            <Target className="w-4 h-4" />
            <span>Target Role Alignment</span>
          </div>
          {jdAnalysis ? (
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Target Role:</span>
                <span className="font-semibold text-foreground">{jdAnalysis.role || 'Software Engineer'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Experience Level:</span>
                <span className="font-semibold text-indigo-400">{jdAnalysis.experience_level || 'Mid-Senior'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Keywords Extracted:</span>
                <span className="font-semibold text-cyan-400">{jdAnalysis.keywords.length} keywords</span>
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No specific Job Description attached. Showing general ATS health metrics.</p>
          )}
        </div>
      </div>

      {/* Sub-scores Progress Bars */}
      <div className="p-6 rounded-3xl border border-border bg-card/60 space-y-4">
        <h3 className="font-semibold text-sm flex items-center space-x-2 text-foreground">
          <Zap className="w-4 h-4 text-amber-400" />
          <span>Algorithmic ATS Metric Breakdown</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          {subScores.map((item, idx) => (
            <div key={idx} className="space-y-1.5 p-3 rounded-xl border border-border/50 bg-background/40">
              <div className="flex justify-between font-medium">
                <span className="text-muted-foreground">{item.label}</span>
                <span className="text-foreground font-semibold">{item.value}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-secondary overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    item.value >= 75 ? 'bg-emerald-500' : item.value >= 50 ? 'bg-amber-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${item.value}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Keywords Chips */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Matched Keywords */}
        <div className="p-6 rounded-3xl border border-emerald-500/20 bg-emerald-500/5 space-y-3">
          <h4 className="font-semibold text-xs text-emerald-400 flex items-center space-x-1.5">
            <CheckCircle2 className="w-4 h-4" />
            <span>Matched Keywords ({atsScore.matched_keywords.length})</span>
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {atsScore.matched_keywords.map((kw, i) => (
              <span key={i} className="px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[11px]">
                ✓ {kw}
              </span>
            ))}
          </div>
        </div>

        {/* Missing Keywords */}
        <div className="p-6 rounded-3xl border border-red-500/20 bg-red-500/5 space-y-3">
          <h4 className="font-semibold text-xs text-red-400 flex items-center space-x-1.5">
            <XCircle className="w-4 h-4" />
            <span>Missing JD Keywords ({atsScore.missing_keywords.length})</span>
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {atsScore.missing_keywords.map((kw, i) => (
              <span key={i} className="px-2.5 py-1 rounded-lg bg-red-500/10 text-red-300 border border-red-500/20 text-[11px]">
                ✗ {kw}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Recommendations */}
      <div className="p-6 rounded-3xl border border-border bg-card/60 space-y-4">
        <h3 className="font-semibold text-sm flex items-center space-x-2 text-violet-400">
          <Lightbulb className="w-4 h-4" />
          <span>Actionable ATS Improvement Recommendations</span>
        </h3>
        <ul className="space-y-2.5 text-xs text-muted-foreground">
          {atsScore.recommendations.map((rec, i) => (
            <li key={i} className="flex items-start space-x-2.5 p-3 rounded-xl border border-border/40 bg-background/30">
              <span className="text-violet-400 font-bold">•</span>
              <span className="leading-relaxed text-foreground">{rec}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
