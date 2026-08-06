import React, { useState } from 'react';
import { GitCompare, Plus, Minus, Edit3 } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';

export const DiffViewer: React.FC = () => {
  const { diffResult, isTailoring } = useResumeStore();
  const [viewMode, setViewMode] = useState<'inline' | 'side-by-side'>('inline');

  if (isTailoring) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-10 h-10 border-4 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-muted-foreground">Generating GitHub-style diff comparison...</p>
      </div>
    );
  }

  if (!diffResult || diffResult.sections.length === 0) {
    return (
      <div className="py-20 text-center space-y-3">
        <GitCompare className="w-12 h-12 text-muted-foreground mx-auto" />
        <h3 className="font-semibold text-lg">No Content Differences</h3>
        <p className="text-xs text-muted-foreground max-w-sm mx-auto">
          Tailor your resume using AI in the top actions bar to see a side-by-side GitHub diff of changes.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6 max-w-4xl mx-auto overflow-y-auto max-h-[calc(100vh-140px)] custom-scrollbar">
      {/* Diff Metrics Bar */}
      <div className="flex items-center justify-between p-4 rounded-2xl border border-border bg-card/60 text-xs">
        <div className="flex items-center space-x-4">
          <span className="flex items-center space-x-1 text-emerald-400 font-semibold">
            <Plus className="w-3.5 h-3.5" />
            <span>{diffResult.total_additions} Additions</span>
          </span>
          <span className="flex items-center space-x-1 text-red-400 font-semibold">
            <Minus className="w-3.5 h-3.5" />
            <span>{diffResult.total_removals} Removals</span>
          </span>
          <span className="flex items-center space-x-1 text-amber-400 font-semibold">
            <Edit3 className="w-3.5 h-3.5" />
            <span>{diffResult.total_modifications} Modifications</span>
          </span>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => setViewMode('inline')}
            className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
              viewMode === 'inline' ? 'border-violet-500/50 bg-violet-500/10 text-violet-400' : 'border-border bg-secondary text-muted-foreground'
            }`}
          >
            Inline
          </button>
          <button
            onClick={() => setViewMode('side-by-side')}
            className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
              viewMode === 'side-by-side' ? 'border-violet-500/50 bg-violet-500/10 text-violet-400' : 'border-border bg-secondary text-muted-foreground'
            }`}
          >
            Side-by-Side
          </button>
        </div>
      </div>

      {/* Diff Sections */}
      <div className="space-y-4">
        {diffResult.sections.map((sec, idx) => (
          <div key={idx} className="p-5 rounded-2xl border border-border bg-card/40 space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between pb-2 border-b border-border/50 text-muted-foreground">
              <span className="font-semibold text-violet-400 uppercase tracking-wider">{sec.section} — {sec.field}</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-sans font-semibold uppercase ${
                sec.diff_type === 'added' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                sec.diff_type === 'removed' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                'bg-amber-500/10 text-amber-400 border border-amber-500/20'
              }`}>
                {sec.diff_type}
              </span>
            </div>

            {viewMode === 'inline' ? (
              <div className="p-3 rounded-xl bg-background/80 leading-relaxed font-sans">
                {sec.chunks.map((chk, i) => (
                  <span
                    key={i}
                    className={
                      chk.type === 'added' ? 'bg-emerald-500/20 text-emerald-300 font-medium px-1 rounded' :
                      chk.type === 'removed' ? 'bg-red-500/20 text-red-300 line-through px-1 rounded' :
                      'text-foreground'
                    }
                  >
                    {chk.text}{' '}
                  </span>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4 font-sans text-xs">
                <div className="p-3 rounded-xl bg-red-500/5 border border-red-500/20 space-y-1">
                  <span className="text-[10px] font-semibold uppercase text-red-400">Original</span>
                  <p className="text-muted-foreground leading-relaxed">{sec.original_text || '(Empty)'}</p>
                </div>
                <div className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20 space-y-1">
                  <span className="text-[10px] font-semibold uppercase text-emerald-400">AI Tailored</span>
                  <p className="text-foreground leading-relaxed">{sec.new_text || '(Empty)'}</p>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
