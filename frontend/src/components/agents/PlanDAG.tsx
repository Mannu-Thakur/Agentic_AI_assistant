/**
 * PlanDAG.tsx — Mission Plan DAG Visualization
 *
 * Shows the supervisor's execution plan as an interactive DAG:
 *  - Nodes = agents (with status, duration, artifact count)
 *  - Edges = execution flow
 *  - Critic score badge
 *  - Real-time status updates as agents complete
 *
 * Renders inline in the chat above the ChatInput when a mission is active.
 */

import React from 'react';
import {
  Code2, Globe, FileText, BarChart2, Eye, Shield,
  Database, CheckCircle2, XCircle, Loader2, Clock,
  ArrowRight, Zap
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AgentNodeState {
  agent: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  duration_ms?: number;
  artifacts?: any[];
  output_preview?: string;
}

interface PlanDAGProps {
  planReason: string;
  agentSteps: AgentNodeState[];
  criticScore?: number | null;
  criticPasses?: boolean | null;
  criticFeedback?: string;
  retryCount?: number;
  isVisible: boolean;
}

// ─── Agent config ─────────────────────────────────────────────────────────────

const AGENT_CONFIG: Record<string, { icon: React.ElementType; label: string; color: string; bg: string }> = {
  web_research:  { icon: Globe,        label: 'Web Research',  color: 'text-blue-400',    bg: 'bg-blue-500/10 border-blue-500/30' },
  code:          { icon: Code2,        label: 'Code',          color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/30' },
  rag:           { icon: Database,     label: 'Knowledge Base',color: 'text-amber-400',   bg: 'bg-amber-500/10 border-amber-500/30' },
  data_analysis: { icon: BarChart2,    label: 'Data Analysis', color: 'text-purple-400',  bg: 'bg-purple-500/10 border-purple-500/30' },
  document:      { icon: FileText,     label: 'Document',      color: 'text-orange-400',  bg: 'bg-orange-500/10 border-orange-500/30' },
  vision:        { icon: Eye,          label: 'Vision',        color: 'text-rose-400',    bg: 'bg-rose-500/10 border-rose-500/30' },
  critic:        { icon: Shield,       label: 'Critic',        color: 'text-red-400',     bg: 'bg-red-500/10 border-red-500/30' },
};

const DEFAULT_CONFIG = { icon: Zap, label: 'Agent', color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-500/30' };

function getConfig(agent: string) {
  return AGENT_CONFIG[agent] ?? DEFAULT_CONFIG;
}

// ─── Status indicator ─────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: AgentNodeState['status'] }) {
  switch (status) {
    case 'done':    return <CheckCircle2 className="w-3 h-3 text-emerald-400 flex-shrink-0" />;
    case 'failed':  return <XCircle      className="w-3 h-3 text-red-400 flex-shrink-0" />;
    case 'running': return <Loader2      className="w-3 h-3 text-blue-400 animate-spin flex-shrink-0" />;
    default:        return <Clock        className="w-3 h-3 text-foreground-3 flex-shrink-0" />;
  }
}

// ─── Agent Node Card ──────────────────────────────────────────────────────────

function AgentNode({ step }: { step: AgentNodeState }) {
  const cfg = getConfig(step.agent);
  const Icon = cfg.icon;
  const isActive = step.status === 'running';

  return (
    <div
      className={`
        relative flex flex-col gap-1.5 p-3 rounded-xl border min-w-[130px] max-w-[160px]
        transition-all duration-300
        ${cfg.bg}
        ${isActive ? 'ring-1 ring-blue-400/40 shadow-lg shadow-blue-500/10' : ''}
        ${step.status === 'done' ? 'opacity-100' : step.status === 'pending' ? 'opacity-60' : 'opacity-100'}
      `}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className={`p-1.5 rounded-lg ${cfg.bg}`}>
          <Icon className={`w-3 h-3 ${cfg.color}`} />
        </div>
        <StatusIcon status={step.status} />
      </div>

      {/* Label */}
      <p className={`text-[11px] font-semibold ${cfg.color} leading-tight`}>
        {cfg.label}
      </p>

      {/* Duration */}
      {step.duration_ms && step.duration_ms > 0 && (
        <p className="text-[10px] text-foreground-3 font-mono">
          {step.duration_ms < 1000
            ? `${step.duration_ms}ms`
            : `${(step.duration_ms / 1000).toFixed(1)}s`}
        </p>
      )}

      {/* Artifacts badge */}
      {step.artifacts && step.artifacts.length > 0 && (
        <span className="self-start text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-accent border border-accent/20">
          {step.artifacts.length} file{step.artifacts.length > 1 ? 's' : ''}
        </span>
      )}

      {/* Running pulse */}
      {isActive && (
        <div className="absolute inset-0 rounded-xl animate-pulse bg-blue-500/5 pointer-events-none" />
      )}
    </div>
  );
}

// ─── Connector Arrow ─────────────────────────────────────────────────────────

function Connector() {
  return (
    <div className="flex items-center self-center flex-shrink-0">
      <div className="w-4 h-px bg-border" />
      <ArrowRight className="w-3 h-3 text-foreground-3" />
    </div>
  );
}

// ─── Critic Score Badge ───────────────────────────────────────────────────────

function CriticBadge({
  score, passes, feedback, retryCount
}: {
  score: number; passes: boolean; feedback?: string; retryCount?: number;
}) {
  const pct = Math.round(score * 100);
  const color = passes
    ? pct >= 80 ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
               : 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'
    : 'text-red-400 bg-red-500/10 border-red-500/30';

  return (
    <div className={`flex flex-col gap-1 px-3 py-2 rounded-xl border ${color}`}>
      <div className="flex items-center gap-1.5">
        <Shield className="w-3 h-3 flex-shrink-0" />
        <span className="text-[11px] font-semibold">
          Critic: {pct}%
        </span>
        {passes
          ? <CheckCircle2 className="w-3 h-3 text-emerald-400" />
          : <XCircle className="w-3 h-3 text-red-400" />}
        {retryCount && retryCount > 0 && (
          <span className="text-[10px] opacity-70">retry #{retryCount}</span>
        )}
      </div>
      {feedback && !passes && (
        <p className="text-[10px] opacity-80 leading-tight max-w-[160px] line-clamp-2">
          {feedback}
        </p>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function PlanDAG({
  planReason,
  agentSteps,
  criticScore,
  criticPasses,
  criticFeedback,
  retryCount,
  isVisible,
}: PlanDAGProps) {
  if (!isVisible || agentSteps.length === 0) return null;

  const doneCount    = agentSteps.filter(s => s.status === 'done').length;
  const failedCount  = agentSteps.filter(s => s.status === 'failed').length;
  const runningCount = agentSteps.filter(s => s.status === 'running').length;

  return (
    <div className="rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-500/5 to-transparent p-4 space-y-3">
      {/* Plan header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-violet-400 flex-shrink-0" />
          <div>
            <p className="text-xs font-semibold text-violet-300">Mission Plan</p>
            {planReason && (
              <p className="text-[11px] text-foreground-3 leading-tight mt-0.5 line-clamp-2">
                {planReason}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-400 border border-violet-500/20 font-medium">
            {doneCount}/{agentSteps.length} done
          </span>
          {failedCount > 0 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/20">
              {failedCount} failed
            </span>
          )}
        </div>
      </div>

      {/* DAG: agents in parallel fan-out view */}
      <div className="flex items-start gap-1 overflow-x-auto pb-1">
        {/* Entry node */}
        <div className="flex flex-col items-center gap-1 self-center flex-shrink-0">
          <div className="w-8 h-8 rounded-full bg-violet-500/20 border border-violet-500/40 flex items-center justify-center">
            <Zap className="w-3.5 h-3.5 text-violet-400" />
          </div>
          <span className="text-[9px] text-foreground-3">START</span>
        </div>

        <Connector />

        {/* Agent nodes (parallel — shown in a row) */}
        <div className="flex items-center gap-1">
          {agentSteps.map((step, i) => (
            <React.Fragment key={step.agent}>
              {i > 0 && <div className="w-1.5 h-px bg-border mx-0.5" />}
              <AgentNode step={step} />
            </React.Fragment>
          ))}
        </div>

        <Connector />

        {/* Critic node */}
        {criticScore !== null && criticScore !== undefined ? (
          <CriticBadge
            score={criticScore}
            passes={criticPasses ?? true}
            feedback={criticFeedback}
            retryCount={retryCount}
          />
        ) : (
          <div className="flex flex-col items-center gap-1 self-center flex-shrink-0">
            <div className={`
              w-8 h-8 rounded-full border flex items-center justify-center
              ${runningCount > 0 || doneCount < agentSteps.length
                ? 'bg-surface-2 border-border'
                : 'bg-red-500/10 border-red-500/30'}
            `}>
              <Shield className={`w-3.5 h-3.5 ${doneCount === agentSteps.length ? 'text-red-400' : 'text-foreground-3'}`} />
            </div>
            <span className="text-[9px] text-foreground-3">CRITIC</span>
          </div>
        )}

        <Connector />

        {/* Synthesize node */}
        <div className="flex flex-col items-center gap-1 self-center flex-shrink-0">
          <div className={`
            w-8 h-8 rounded-full border flex items-center justify-center
            ${criticScore !== null && (criticPasses ?? true)
              ? 'bg-emerald-500/10 border-emerald-500/30'
              : 'bg-surface-2 border-border'}
          `}>
            <CheckCircle2 className={`w-3.5 h-3.5 ${criticScore !== null && (criticPasses ?? true) ? 'text-emerald-400' : 'text-foreground-3'}`} />
          </div>
          <span className="text-[9px] text-foreground-3">DONE</span>
        </div>
      </div>
    </div>
  );
}

export default PlanDAG;
