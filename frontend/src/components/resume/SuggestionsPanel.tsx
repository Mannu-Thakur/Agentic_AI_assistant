import React from 'react';
import { Lightbulb, Sparkles, Zap, CheckCircle2, ArrowRight } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';

const SUGGESTIONS = [
  { id: 'add_achievements', title: 'Add Quantified Metrics', desc: 'Convert task statements into measurable outcomes with numbers and percentages', badge: 'High Impact', icon: Zap },
  { id: 'improve_action_verbs', title: 'Strong Action Verbs', desc: 'Replace passive phrases like "helped with" with "Spearheaded", "Engineered", "Reduced"', badge: 'ATS Boost', icon: Sparkles },
  { id: 'add_missing_skills', title: 'Add Missing JD Skills', desc: 'Extract missing skills from experience text and inject into Skills section', badge: 'Keyword Gap', icon: Lightbulb },
  { id: 'improve_ats', title: 'Optimize for ATS Systems', desc: 'Align vocabulary and bullet structure with automated resume screeners', badge: 'ATS Safe', icon: CheckCircle2 },
  { id: 'reduce_to_one_page', title: 'Condense to 1 Page', desc: 'Trim low-impact bullets to fit cleanly on a single page', badge: 'Formatting', icon: Zap },
  { id: 'improve_technical_wording', title: 'Technical Depth Upgrade', desc: 'Use proper engineering terminology, system architecture keywords', badge: 'Technical', icon: Sparkles },
  { id: 'improve_leadership_wording', title: 'Leadership & Ownership', desc: 'Highlight cross-functional impact, team leadership, project ownership', badge: 'Management', icon: Lightbulb },
  { id: 'remove_repetition', title: 'Eliminate Repetitive Words', desc: 'Vary action verbs and remove redundant bullet phrasing', badge: 'Clarity', icon: CheckCircle2 },
];

export const SuggestionsPanel: React.FC = () => {
  const { applySuggestion, isApplyingSuggestion } = useResumeStore();

  const handleApply = async (type: string) => {
    try {
      await applySuggestion(type);
    } catch (err: any) {
      alert(err.message || 'Failed to apply suggestion');
    }
  };

  return (
    <div className="space-y-6 p-6 max-w-4xl mx-auto overflow-y-auto max-h-[calc(100vh-140px)] custom-scrollbar">
      <div className="space-y-1">
        <h3 className="font-semibold text-lg flex items-center space-x-2 text-foreground">
          <Lightbulb className="w-5 h-5 text-amber-400" />
          <span>One-Click AI Resume Enhancements</span>
        </h3>
        <p className="text-xs text-muted-foreground">
          Select any suggestion to apply AI improvements specifically targeted to that aspect.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {SUGGESTIONS.map((sug) => {
          const IconComp = sug.icon;
          return (
            <div
              key={sug.id}
              className="p-5 rounded-2xl border border-border bg-card/60 space-y-3 hover:border-violet-500/40 transition-all flex flex-col justify-between"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2 text-violet-400">
                    <IconComp className="w-4 h-4" />
                    <h4 className="font-semibold text-sm text-foreground">{sug.title}</h4>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-violet-500/10 text-violet-300 font-medium border border-violet-500/20">
                    {sug.badge}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">{sug.desc}</p>
              </div>

              <button
                onClick={() => handleApply(sug.id)}
                disabled={isApplyingSuggestion}
                className="flex items-center justify-center space-x-1.5 w-full py-2 rounded-xl bg-secondary hover:bg-violet-600 hover:text-white text-xs font-medium transition-all disabled:opacity-50"
              >
                <span>Apply Enhancement</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};
