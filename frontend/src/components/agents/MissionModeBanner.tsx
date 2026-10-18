/** Mission Mode control and live status for the chat composer. */

import React from 'react';
import {
  Zap, Loader2, CheckCircle2, XCircle, AlertTriangle,
  ThumbsUp, ThumbsDown, X, FileText, Code2, Globe,
  BarChart2, Shield, ChevronDown, ChevronUp,
} from 'lucide-react';

interface AgentStatus {
  agent: string;
  status: 'running' | 'done' | 'failed';
}

interface HITLRequest {
  mission_id: string;
  reason: string;
  approve_url: string;
  reject_url: string;
}

interface MissionModeBannerProps {
  isActive: boolean;
  status: 'idle' | 'queued' | 'classifying' | 'running' | 'awaiting_approval' | 'complete' | 'delegated' | 'error';
  agentSteps: AgentStatus[];
  critcResult: { score: number; passes: boolean; feedback: string } | null;
  hitlRequest: HITLRequest | null;
  artifactCount: number;
  error: string;
  missionId: string;
  onToggle: () => void;
  onApprove: () => void;
  onReject: () => void;
  onDismiss: () => void;
}

const AGENT_META: Record<string, { icon: React.ElementType; label: string; color: string }> = {
  web_research:  { icon: Globe,     label: 'Web Research', color: 'text-blue-400' },
  code:          { icon: Code2,     label: 'Code',         color: 'text-emerald-400' },
  data_analysis: { icon: BarChart2, label: 'Data Analysis',color: 'text-purple-400' },
  critic:        { icon: Shield,    label: 'Critic',       color: 'text-rose-400' },
  rag:           { icon: FileText,  label: 'Knowledge',    color: 'text-amber-400' },
};

function AgentPill({ agent, status }: AgentStatus) {
  const meta = AGENT_META[agent] || { icon: Zap, label: agent, color: 'text-gray-400' };
  const Icon = meta.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
      status === 'running' ? 'border-blue-500/25 bg-blue-500/10 text-blue-200' :
      status === 'done' ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200' :
      'border-rose-500/25 bg-rose-500/10 text-rose-200'
    }`}>
      {status === 'running' ? <Loader2 className="h-3 w-3 animate-spin" /> :
        status === 'done' ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      <Icon className={`h-3 w-3 ${meta.color}`} />
      {meta.label}
    </span>
  );
}

export function MissionModeBanner({
  isActive,
  status,
  agentSteps,
  critcResult,
  hitlRequest,
  artifactCount,
  error,
  missionId,
  onToggle,
  onApprove,
  onReject,
  onDismiss,
}: MissionModeBannerProps) {
  const [collapsed, setCollapsed] = React.useState(false);

  if (hitlRequest) {
    return (
      <section className="rounded-2xl border border-amber-400/25 bg-amber-400/[0.06] p-3.5 text-sm shadow-[0_8px_28px_rgba(0,0,0,0.16)]">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-amber-400/20 bg-amber-400/10">
            <AlertTriangle className="h-4 w-4 text-amber-300" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold text-amber-100">Approval needed to continue</h3>
            <p className="text-xs text-foreground-3">Review this step before the agents proceed.</p>
          </div>
          <span className="hidden font-mono text-[10px] text-foreground-3 sm:inline">{missionId.slice(0, 8)}</span>
        </div>
        <p className="mb-3 mt-3 text-xs leading-relaxed text-foreground-2">{hitlRequest.reason}</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={onApprove} className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-400/25 bg-emerald-400/10 px-3 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-400/15">
            <ThumbsUp className="h-3.5 w-3.5" /> Approve and continue
          </button>
          <button type="button" onClick={onReject} className="inline-flex items-center gap-1.5 rounded-xl border border-rose-400/25 bg-rose-400/10 px-3 py-2 text-xs font-semibold text-rose-200 transition hover:bg-rose-400/15">
            <ThumbsDown className="h-3.5 w-3.5" /> Reject
          </button>
        </div>
      </section>
    );
  }

  if (status === 'idle') {
    return (
      <section className={`relative flex min-h-12 items-center gap-3 overflow-hidden rounded-2xl border px-3 py-2 transition-all duration-200 ${
        isActive
          ? 'border-violet-400/25 bg-gradient-to-r from-violet-500/[0.12] via-violet-500/[0.055] to-surface/75 shadow-[0_8px_28px_rgba(91,33,182,0.08)]'
          : 'border-border/70 bg-surface/75 hover:border-violet-400/25 hover:bg-surface-2/70'
      }`}>
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border transition-colors ${
          isActive ? 'border-violet-400/25 bg-violet-400/15 text-violet-200' : 'border-border/80 bg-surface-2 text-foreground-3'
        }`}>
          <Zap className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-semibold text-foreground">Mission Mode</h3>
            {isActive && <span className="rounded-full border border-violet-300/20 bg-violet-300/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-violet-200">On</span>}
          </div>
          <p className="mt-0.5 hidden text-[11px] leading-4 text-foreground-3 sm:block">
            {isActive ? 'Complex requests can be planned across specialist agents.' : 'Coordinate specialist agents for larger, multi-step tasks.'}
          </p>
        </div>
        <button
          type="button"
          aria-pressed={isActive}
          onClick={onToggle}
          className={`shrink-0 rounded-full border px-3.5 py-1.5 text-[11px] font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/60 ${
            isActive
              ? 'border-violet-300/20 bg-violet-400/10 text-violet-100 hover:bg-violet-400/15'
              : 'border-border/80 bg-surface-2/80 text-foreground-2 hover:border-violet-400/25 hover:text-foreground'
          }`}
        >
          {isActive ? 'Turn off' : 'Enable'}
        </button>
      </section>
    );
  }

  const running = status === 'queued' || status === 'classifying' || status === 'running';
  const title = status === 'queued' ? 'Mission queued' :
    status === 'classifying' ? 'Planning mission' :
    status === 'running' ? 'Mission in progress' :
    status === 'complete' ? 'Mission complete' :
    status === 'delegated' ? 'Continuing in chat' : 'Mission failed';
  const tone = status === 'error' ? 'rose' : status === 'complete' ? 'emerald' : status === 'delegated' ? 'blue' : 'violet';
  const toneClasses = {
    rose: 'border-rose-400/25 bg-rose-400/[0.06] text-rose-200',
    emerald: 'border-emerald-400/20 bg-emerald-400/[0.05] text-emerald-200',
    blue: 'border-blue-400/20 bg-blue-400/[0.05] text-blue-200',
    violet: 'border-violet-400/20 bg-violet-400/[0.06] text-violet-200',
  }[tone];

  return (
    <section className={`rounded-2xl border px-3.5 py-3 shadow-[0_8px_28px_rgba(0,0,0,0.15)] ${toneClasses}`}>
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-black/10">
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> :
            status === 'complete' ? <CheckCircle2 className="h-4 w-4" /> :
            status === 'error' ? <XCircle className="h-4 w-4" /> : <Zap className="h-4 w-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-xs font-semibold">{title}</h3>
            {missionId && <span className="rounded-md bg-black/15 px-1.5 py-0.5 font-mono text-[10px] text-foreground-3">{missionId.slice(0, 8)}</span>}
            {artifactCount > 0 && <span className="rounded-full border border-accent/20 bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">{artifactCount} artifact{artifactCount === 1 ? '' : 's'}</span>}
          </div>
          <p className="mt-0.5 text-[11px] leading-4 text-foreground-3">
            {error ? error : status === 'delegated' ? 'This request did not need multi-agent planning.' :
              status === 'complete' ? 'The agent plan and execution trace are available above in the conversation.' :
              status === 'error' ? 'Review the failure details below, then dismiss to try again.' :
              'Specialist agents are working through the plan.'}
          </p>
        </div>
        {critcResult && (
          <span className="hidden items-center gap-1 rounded-lg bg-black/10 px-2 py-1 text-[10px] font-bold sm:inline-flex">
            <Shield className="h-3 w-3" /> {Math.round(critcResult.score * 100)}%
          </span>
        )}
        {agentSteps.length > 0 && (
          <button type="button" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? 'Show mission agents' : 'Hide mission agents'} aria-expanded={!collapsed} className="rounded-lg p-1.5 text-foreground-3 transition hover:bg-black/10 hover:text-foreground">
            {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </button>
        )}
        <button type="button" onClick={onDismiss} aria-label="Dismiss Mission Mode status" className="rounded-lg p-1.5 text-foreground-3 transition hover:bg-black/10 hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>
      {!collapsed && agentSteps.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-white/5 pt-3">
          {agentSteps.map((step, index) => <AgentPill key={`${step.agent}-${index}`} {...step} />)}
        </div>
      )}
      {status === 'error' && error && <p className="mt-2 border-t border-rose-400/10 pt-2 text-xs leading-relaxed text-rose-200/90">{error.slice(0, 300)}</p>}
    </section>
  );
}

export default MissionModeBanner;
