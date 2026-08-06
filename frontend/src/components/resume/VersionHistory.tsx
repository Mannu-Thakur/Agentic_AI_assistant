import React from 'react';
import { History, RotateCcw, Clock } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';

export const VersionHistory: React.FC = () => {
  const { versions, restoreVersion } = useResumeStore();

  if (versions.length === 0) {
    return (
      <div className="py-20 text-center space-y-3">
        <History className="w-12 h-12 text-muted-foreground mx-auto" />
        <h3 className="font-semibold text-lg">No Previous Versions</h3>
        <p className="text-xs text-muted-foreground max-w-sm mx-auto">
          Every AI tailoring cycle or suggestion creates a version snapshot so you can restore anytime.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6 max-w-4xl mx-auto overflow-y-auto max-h-[calc(100vh-140px)] custom-scrollbar">
      <div className="space-y-1">
        <h3 className="font-semibold text-lg flex items-center space-x-2 text-foreground">
          <History className="w-5 h-5 text-indigo-400" />
          <span>Resume Version Control</span>
        </h3>
        <p className="text-xs text-muted-foreground">
          Complete audit trial of all changes. Revert or compare any previous snapshot instantly.
        </p>
      </div>

      <div className="space-y-3">
        {versions.map((ver) => (
          <div
            key={ver.version_id}
            className="p-5 rounded-2xl border border-border bg-card/60 flex items-center justify-between hover:border-violet-500/40 transition-all"
          >
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-sm text-foreground">{ver.label}</span>
                {ver.ats_score && (
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20">
                    ATS: {ver.ats_score.overall}%
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">{ver.description}</p>
              <div className="flex items-center space-x-1 text-[11px] text-muted-foreground/60 pt-0.5">
                <Clock className="w-3 h-3" />
                <span>{ver.created_at}</span>
              </div>
            </div>

            <button
              onClick={() => restoreVersion(ver.version_id)}
              className="flex items-center space-x-1.5 px-4 py-2 rounded-xl border border-border bg-secondary hover:bg-muted text-xs font-medium transition-all"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Restore</span>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
