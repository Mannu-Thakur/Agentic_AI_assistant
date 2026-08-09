import { Terminal, Cpu, Database, Activity } from 'lucide-react';

interface DeveloperPanelProps {
  metrics?: Record<string, any>;
  logs?: string[];
  onClose?: () => void;
}

export function DeveloperPanel({ metrics, logs = [], onClose }: DeveloperPanelProps) {
  return (
    <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-4 text-xs font-mono text-slate-300">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <h3 className="font-semibold text-sm text-blue-400 flex items-center gap-2">
          <Terminal className="w-4 h-4" />
          Developer Debug Console
        </h3>
        {onClose && (
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            ×
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="p-2 bg-slate-950 rounded border border-slate-850">
          <div className="text-slate-500 flex items-center gap-1">
            <Cpu className="w-3 h-3 text-purple-400" /> Model Latency
          </div>
          <div className="font-bold text-slate-200 mt-1">
            {metrics?.llm_latency_ms ? `${metrics.llm_latency_ms} ms` : 'N/A'}
          </div>
        </div>

        <div className="p-2 bg-slate-950 rounded border border-slate-850">
          <div className="text-slate-500 flex items-center gap-1">
            <Database className="w-3 h-3 text-emerald-400" /> Chunks Used
          </div>
          <div className="font-bold text-slate-200 mt-1">
            {metrics?.chunks_used ?? 0}
          </div>
        </div>
      </div>

      {logs.length > 0 && (
        <div className="space-y-1">
          <div className="text-slate-500 flex items-center gap-1">
            <Activity className="w-3 h-3 text-amber-400" /> Trace Stream
          </div>
          <div className="max-h-32 overflow-y-auto p-2 bg-slate-950 rounded text-slate-400 space-y-1">
            {logs.map((log, idx) => (
              <div key={idx} className="truncate">{log}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
