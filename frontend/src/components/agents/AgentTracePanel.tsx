/**
 * AgentTracePanel.tsx — Visual Multi-Agent Execution Trace
 *
 * Renders a real-time timeline of the supervisor graph execution:
 *   Plan → Agents → Tools → Critic → Status → Artifacts
 *
 * Consumes the `supervisor_trace` array from the mission SSE stream
 * and the existing `execution_trace` from the single-agent graph.
 *
 * Features:
 *  - Animated node cards that update live as agents complete
 *  - Expandable per-agent output previews
 *  - Critic score badge with color coding
 *  - HITL approval buttons when human gate is triggered
 *  - Artifact list with download links
 *  - Collapsible panel that doesn't block the chat view
 */

import React, { useState } from 'react';
import {
  ChevronDown, ChevronUp, CheckCircle2, XCircle, Clock,
  Loader2, AlertTriangle, Download, FileText, Code2,
  Globe, BarChart2, Shield, Cpu, Sparkles,
  ThumbsUp, ThumbsDown
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────
//  Types
// ─────────────────────────────────────────────────────────────

export interface TraceNode {
  name: string;
  status: 'EXECUTED' | 'BYPASSED' | 'FAILED' | 'RUNNING' | 'PENDING';
  duration_ms?: number;
  reason?: string;
  metadata?: Record<string, any>;
  error?: string;
}

export interface AgentStepEvent {
  agent: string;
  status: 'running' | 'done' | 'failed';
  output?: string;
  artifacts?: ArtifactItem[];
  duration_ms?: number;
}

export interface ArtifactItem {
  id: string;
  type: string;
  filename: string;
  size_bytes: number;
  download_url: string;
  description?: string;
  preview?: string;
}

export interface CriticResult {
  score: number;
  passes: boolean;
  feedback: string;
}

export interface HITLRequest {
  mission_id: string;
  reason: string;
  approve_url: string;
  reject_url: string;
}

export interface AgentTracePanelProps {
  // Single-agent graph trace (existing)
  executionTrace?: TraceNode[];
  // Multi-agent supervisor events (new Mission Mode)
  agentSteps?: AgentStepEvent[];
  critcResult?: CriticResult;
  hitlRequest?: HITLRequest | null;
  artifacts?: ArtifactItem[];
  missionId?: string;
  isRunning?: boolean;
  onHITLApprove?: (missionId: string) => void;
  onHITLReject?: (missionId: string) => void;
}

// ─────────────────────────────────────────────────────────────
//  Agent Icon mapping
// ─────────────────────────────────────────────────────────────

const AGENT_ICONS: Record<string, React.ElementType> = {
  web_research:     Globe,
  code:             Code2,
  data_analysis:    BarChart2,
  rag:              FileText,
  critic:           Shield,
  supervisor:       Cpu,
  synthesizer:      Sparkles,
  default:          Cpu,
};

const AGENT_COLORS: Record<string, string> = {
  web_research:     'text-blue-400 bg-blue-500/10 border-blue-500/20',
  code:             'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  data_analysis:    'text-purple-400 bg-purple-500/10 border-purple-500/20',
  rag:              'text-amber-400 bg-amber-500/10 border-amber-500/20',
  critic:           'text-rose-400 bg-rose-500/10 border-rose-500/20',
  supervisor:       'text-indigo-400 bg-indigo-500/10 border-indigo-500/20',
  synthesizer:      'text-violet-400 bg-violet-500/10 border-violet-500/20',
  default:          'text-gray-400 bg-gray-500/10 border-gray-500/20',
};

function getAgentColors(name: string) {
  return AGENT_COLORS[name] || AGENT_COLORS.default;
}

// ─────────────────────────────────────────────────────────────
//  Status indicator
// ─────────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'EXECUTED':
    case 'done':
      return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />;
    case 'FAILED':
    case 'failed':
      return <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />;
    case 'BYPASSED':
      return <Clock className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" />;
    case 'RUNNING':
    case 'running':
      return <Loader2 className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 animate-spin" />;
    default:
      return <Clock className="w-3.5 h-3.5 text-gray-600 flex-shrink-0" />;
  }
}

// ─────────────────────────────────────────────────────────────
//  Single-agent graph trace row
// ─────────────────────────────────────────────────────────────

function TraceRow({ node }: { node: TraceNode }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = node.error || node.reason || (node.metadata && Object.keys(node.metadata).length > 0);

  return (
    <div className={`border rounded-lg px-3 py-2 text-xs transition-all ${
      node.status === 'EXECUTED' ? 'border-border bg-surface-1' :
      node.status === 'FAILED'   ? 'border-red-500/20 bg-red-500/5' :
                                   'border-border/40 bg-surface-2/40 opacity-50'
    }`}>
      <div className="flex items-center gap-2">
        <StatusIcon status={node.status} />
        <span className={`font-mono font-medium ${
          node.status === 'EXECUTED' ? 'text-foreground' :
          node.status === 'FAILED'   ? 'text-red-400' : 'text-foreground-3'
        }`}>
          {node.name}
        </span>
        {node.duration_ms != null && node.status === 'EXECUTED' && (
          <span className="ml-auto text-[10px] font-mono text-foreground-3">
            {node.duration_ms.toFixed(0)}ms
          </span>
        )}
        {hasDetail && (
          <button
            onClick={() => setExpanded(p => !p)}
            className="ml-auto text-foreground-3 hover:text-foreground"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        )}
      </div>
      {expanded && (
        <div className="mt-2 pl-5 text-[10px] text-foreground-3 space-y-1">
          {node.reason && <p>Reason: {node.reason}</p>}
          {node.error  && <p className="text-red-400">Error: {node.error}</p>}
          {node.metadata && Object.entries(node.metadata).slice(0, 5).map(([k, v]) => (
            <p key={k}>{k}: <span className="font-mono">{String(v)}</span></p>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Agent step card (Mission Mode)
// ─────────────────────────────────────────────────────────────

function AgentCard({ step }: { step: AgentStepEvent }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = AGENT_ICONS[step.agent] || AGENT_ICONS.default;
  const colors = getAgentColors(step.agent);

  return (
    <div className={`border rounded-xl p-3 text-xs transition-all ${colors}`}>
      <div className="flex items-center gap-2">
        <div className={`p-1.5 rounded-lg ${colors} border`}>
          <Icon className="w-3.5 h-3.5" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold capitalize">{step.agent.replace(/_/g, ' ')} Agent</p>
          {step.duration_ms != null && (
            <p className="text-[10px] opacity-70">{step.duration_ms.toFixed(0)}ms</p>
          )}
        </div>
        <StatusIcon status={step.status} />
        {step.output && (
          <button
            onClick={() => setExpanded(p => !p)}
            className="opacity-60 hover:opacity-100"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        )}
      </div>

      {/* Artifacts */}
      {step.artifacts && step.artifacts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {step.artifacts.map(art => (
            <a
              key={art.id}
              href={art.download_url}
              download={art.filename}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[9px] font-medium hover:opacity-80 transition-opacity"
            >
              <Download className="w-2.5 h-2.5" />
              {art.filename}
            </a>
          ))}
        </div>
      )}

      {/* Output preview */}
      {expanded && step.output && (
        <div className="mt-2 p-2 rounded-lg bg-black/20 font-mono text-[10px] max-h-32 overflow-y-auto whitespace-pre-wrap border border-white/5">
          {step.output.slice(0, 800)}
          {step.output.length > 800 && '…'}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Critic score badge
// ─────────────────────────────────────────────────────────────

function CriticBadge({ result }: { result: CriticResult }) {
  const [expanded, setExpanded] = useState(false);
  const pct = Math.round(result.score * 100);
  const color = pct >= 80 ? 'text-emerald-400' : pct >= 60 ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="border border-border rounded-xl p-3 text-xs bg-surface-1">
      <div className="flex items-center gap-2">
        <Shield className={`w-3.5 h-3.5 ${color}`} />
        <span className="font-semibold text-foreground">Critic Verification</span>
        <span className={`ml-auto font-bold text-sm ${color}`}>{pct}%</span>
        {result.passes
          ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          : <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />}
        {result.feedback && (
          <button onClick={() => setExpanded(p => !p)} className="opacity-60 hover:opacity-100">
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        )}
      </div>
      {expanded && result.feedback && (
        <p className="mt-2 text-[10px] text-foreground-3 pl-5 leading-relaxed">
          {result.feedback.slice(0, 400)}
        </p>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  HITL Approval card
// ─────────────────────────────────────────────────────────────

function HITLCard({
  request,
  onApprove,
  onReject,
}: {
  request: HITLRequest;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <div className="border border-amber-500/30 rounded-xl p-3 bg-amber-500/5 text-xs">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
        <span className="font-semibold text-amber-300">Human Approval Required</span>
      </div>
      <p className="text-foreground-3 mb-3 leading-relaxed pl-6">{request.reason}</p>
      <div className="flex gap-2 pl-6">
        <button
          onClick={onApprove}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/30 transition-colors font-medium"
        >
          <ThumbsUp className="w-3 h-3" /> Approve
        </button>
        <button
          onClick={onReject}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/20 border border-red-500/30 text-red-300 hover:bg-red-500/30 transition-colors font-medium"
        >
          <ThumbsDown className="w-3 h-3" /> Reject
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Artifact row
// ─────────────────────────────────────────────────────────────

const TYPE_ICONS: Record<string, React.ElementType> = {
  code:   Code2,
  report: FileText,
  pptx:   FileText,
  docx:   FileText,
  csv:    BarChart2,
  image:  Globe,
  pdf:    FileText,
};

function ArtifactRow({ art }: { art: ArtifactItem }) {
  const Icon = TYPE_ICONS[art.type] || FileText;
  const sizeKb = (art.size_bytes / 1024).toFixed(1);

  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-surface-1 text-xs hover:bg-surface-2 transition-colors group">
      <Icon className="w-3.5 h-3.5 text-accent flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="font-medium text-foreground truncate">{art.filename}</p>
        {art.description && (
          <p className="text-[10px] text-foreground-3 truncate">{art.description}</p>
        )}
      </div>
      <span className="text-[10px] text-foreground-3 flex-shrink-0">{sizeKb} KB</span>
      <a
        href={art.download_url}
        download={art.filename}
        className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
        title="Download"
      >
        <Download className="w-3.5 h-3.5 text-accent" />
      </a>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Main Panel
// ─────────────────────────────────────────────────────────────

export function AgentTracePanel({
  executionTrace = [],
  agentSteps = [],
  critcResult,
  hitlRequest,
  artifacts = [],
  missionId,
  isRunning = false,
  onHITLApprove,
  onHITLReject,
}: AgentTracePanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<'trace' | 'agents' | 'artifacts'>('agents');

  const isMission = agentSteps.length > 0 || !!missionId;

  const hasContent =
    executionTrace.length > 0 ||
    agentSteps.length > 0 ||
    artifacts.length > 0;

  if (!hasContent && !isRunning && !hitlRequest) return null;

  const tabs = [
    ...(isMission ? [{ id: 'agents', label: 'Agents', count: agentSteps.length }] : []),
    { id: 'trace', label: 'Trace', count: executionTrace.length },
    { id: 'artifacts', label: 'Artifacts', count: artifacts.length },
  ] as { id: 'trace' | 'agents' | 'artifacts'; label: string; count: number }[];

  return (
    <div className="border border-border rounded-2xl bg-card/50 overflow-hidden text-xs shadow-sm">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5 border-b border-border/60 cursor-pointer hover:bg-surface-1 transition-colors"
        onClick={() => setCollapsed(p => !p)}
      >
        {isRunning
          ? <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />
          : <Cpu className="w-3.5 h-3.5 text-accent" />}
        <span className="font-semibold text-foreground">
          {isMission ? '⚡ Mission Execution' : '🔍 Agent Execution Trace'}
        </span>
        {missionId && (
          <span className="text-[10px] font-mono text-foreground-3 bg-surface-2 px-1.5 py-0.5 rounded">
            {missionId}
          </span>
        )}
        {isRunning && (
          <span className="ml-auto text-[10px] text-blue-400 font-medium animate-pulse">
            Running...
          </span>
        )}
        <span className={`${isRunning ? '' : 'ml-auto'} text-foreground-3`}>
          {collapsed
            ? <ChevronDown className="w-3.5 h-3.5" />
            : <ChevronUp className="w-3.5 h-3.5" />}
        </span>
      </div>

      {!collapsed && (
        <div className="p-3 space-y-3">
          {/* HITL Gate */}
          {hitlRequest && onHITLApprove && onHITLReject && (
            <HITLCard
              request={hitlRequest}
              onApprove={() => onHITLApprove(hitlRequest.mission_id)}
              onReject={() => onHITLReject(hitlRequest.mission_id)}
            />
          )}

          {/* Critic Badge */}
          {critcResult && <CriticBadge result={critcResult} />}

          {/* Tabs */}
          {tabs.length > 1 && (
            <div className="flex gap-1 border-b border-border/40 pb-2">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors ${
                    activeTab === tab.id
                      ? 'bg-accent/15 text-accent border border-accent/20'
                      : 'text-foreground-3 hover:text-foreground'
                  }`}
                >
                  {tab.label}
                  {tab.count > 0 && (
                    <span className="ml-1 opacity-70">({tab.count})</span>
                  )}
                </button>
              ))}
            </div>
          )}

          {/* Agents tab */}
          {(activeTab === 'agents' || !isMission) && agentSteps.length > 0 && (
            <div className="space-y-2">
              {agentSteps.map((step, i) => (
                <AgentCard key={`${step.agent}-${i}`} step={step} />
              ))}
            </div>
          )}

          {/* Trace tab */}
          {activeTab === 'trace' && executionTrace.length > 0 && (
            <div className="space-y-1.5">
              {executionTrace.map((node, i) => (
                <TraceRow key={`${node.name}-${i}`} node={node} />
              ))}
            </div>
          )}

          {/* Artifacts tab */}
          {activeTab === 'artifacts' && (
            <div className="space-y-1.5">
              {artifacts.length === 0 ? (
                <p className="text-center text-foreground-3 py-3">
                  No artifacts produced yet
                </p>
              ) : (
                artifacts.map(art => (
                  <ArtifactRow key={art.id} art={art} />
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default AgentTracePanel;
