/**
 * MissionModeBanner.tsx — Mission Mode Trigger & Status Banner
 *
 * A self-contained banner that:
 * 1. Shows a "⚡ Mission Mode" toggle button the user can click to activate
 * 2. When active, shows which agents are running with animated status
 * 3. Shows HITL approval prompts inline
 * 4. Shows final mission status + artifact count
 *
 * This component integrates with useMission() hook in the parent.
 * Place it just above ChatInput inside ChatPage.
 */

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
  onToggle: () => void;       // Toggle mission mode on/off
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
    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-medium transition-all ${
      status === 'running' ? 'border-blue-500/30 bg-blue-500/10 text-blue-300' :
      status === 'done'    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' :
                             'border-red-500/30 bg-red-500/10 text-red-300'
    }`}>
      {status === 'running'
        ? <Loader2 className="w-2.5 h-2.5 animate-spin" />
        : status === 'done'
          ? <CheckCircle2 className="w-2.5 h-2.5" />
          : <XCircle className="w-2.5 h-2.5" />}
      <Icon className={`w-2.5 h-2.5 ${meta.color}`} />
      <span>{meta.label}</span>
    </div>
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

  // HITL prompt takes priority
  if (hitlRequest) {
    return (
      <div className="mx-2 mb-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-xs animate-fade-in">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
          <span className="font-semibold text-amber-300">⏸ Human Approval Required</span>
          <span className="ml-auto text-[10px] font-mono text-foreground-3">{missionId}</span>
        </div>
        <p className="text-foreground-3 mb-3 pl-6 text-[11px] leading-relaxed">{hitlRequest.reason}</p>
        <div className="flex gap-2 pl-6">
          <button
            onClick={onApprove}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/30 transition-colors font-medium text-[11px]"
          >
            <ThumbsUp className="w-3 h-3" /> Approve & Continue
          </button>
          <button
            onClick={onReject}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/20 border border-red-500/30 text-red-300 hover:bg-red-500/30 transition-colors font-medium text-[11px]"
          >
            <ThumbsDown className="w-3 h-3" /> Reject
          </button>
        </div>
      </div>
    );
  }

  // Idle — just show the toggle button hint
  if (!isActive && status === 'idle') {
    return (
      <button
        onClick={onToggle}
        className="mx-2 mb-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-violet-500/20 bg-violet-500/5 text-violet-400 hover:bg-violet-500/10 hover:border-violet-500/30 transition-all text-[11px] font-semibold"
        title="Activate Mission Mode for complex multi-agent tasks"
      >
        <Zap className="w-3 h-3" />
        Mission Mode
      </button>
    );
  }

  // Running / Complete
  return (
    <div className={`mx-2 mb-2 rounded-xl border text-xs transition-all animate-fade-in ${
      status === 'error'    ? 'border-red-500/30 bg-red-500/5' :
      status === 'complete' ? 'border-emerald-500/20 bg-emerald-500/5' :
                              'border-violet-500/20 bg-violet-500/5'
    }`}>
      {/* Header bar */}
      <div className="flex items-center gap-2 px-3 py-2">
        {status === 'running' || status === 'classifying' || status === 'queued'
          ? <Loader2 className="w-3.5 h-3.5 text-violet-400 animate-spin flex-shrink-0" />
          : status === 'complete'
            ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
            : status === 'error'
              ? <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
              : <Zap className="w-3.5 h-3.5 text-violet-400 flex-shrink-0" />}

        <span className={`font-semibold ${
          status === 'complete' ? 'text-emerald-300' :
          status === 'error'   ? 'text-red-300'     : 'text-violet-300'
        }`}>
          {status === 'queued'        && '⚡ Queued...'}
          {status === 'classifying'   && '⚡ Planning mission...'}
          {status === 'running'       && '⚡ Mission Running'}
          {status === 'complete'      && '✅ Mission Complete'}
          {status === 'error'         && '❌ Mission Failed'}
        </span>

        {missionId && (
          <span className="text-[10px] font-mono text-foreground-3 bg-black/20 px-1.5 py-0.5 rounded">
            {missionId.slice(0, 8)}
          </span>
        )}

        {artifactCount > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/15 text-accent border border-accent/20">
            {artifactCount} artifact{artifactCount !== 1 ? 's' : ''}
          </span>
        )}

        {/* Critic score */}
        {critcResult && (
          <span className={`text-[10px] font-bold ml-auto ${
            critcResult.score >= 0.8 ? 'text-emerald-400' :
            critcResult.score >= 0.6 ? 'text-amber-400' : 'text-red-400'
          }`}>
            <Shield className="w-2.5 h-2.5 inline mr-0.5" />
            {Math.round(critcResult.score * 100)}%
          </span>
        )}

        <div className="flex items-center gap-1 ml-auto">
          {agentSteps.length > 0 && (
            <button onClick={() => setCollapsed(p => !p)} className="text-foreground-3 hover:text-foreground">
              {collapsed ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
            </button>
          )}
          <button onClick={onDismiss} className="text-foreground-3 hover:text-foreground">
            <X className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Agent pills */}
      {!collapsed && agentSteps.length > 0 && (
        <div className="px-3 pb-2 flex flex-wrap gap-1.5">
          {agentSteps.map((step, i) => (
            <AgentPill key={`${step.agent}-${i}`} {...step} />
          ))}
        </div>
      )}

      {/* Error */}
      {status === 'error' && error && (
        <p className="px-3 pb-2 text-[10px] text-red-400">{error.slice(0, 200)}</p>
      )}
    </div>
  );
}

export default MissionModeBanner;
