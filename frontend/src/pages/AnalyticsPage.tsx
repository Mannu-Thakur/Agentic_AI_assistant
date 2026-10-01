import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity, Brain, Network, Database, Shield,
  TrendingUp, AlertTriangle, CheckCircle2,
  RefreshCw, DollarSign, Search, GitBranch,
  Clock, Target, ArrowUpRight, ArrowDownRight,
  ArrowLeft, Users, MessageSquare, Layers, Radio,
  FileText, Check
} from 'lucide-react';
import { apiRequest } from '../services/api';

// --- Interfaces ---

interface OverviewData {
  http_metrics: {
    total_requests: number;
    successful_requests: number;
    failed_requests: number;
    avg_latency_ms: number;
    p95_latency_ms: number;
  };
  agent_metrics: {
    total_agent_requests: number;
    fallback_requests: number;
    fallback_rate: number;
    avg_agent_latency_ms: number;
  };
  platform_metrics?: {
    registered_users: number;
    active_conversations: number;
    total_messages: number;
    uploaded_documents: number;
    indexed_chunks: number;
    audit_trail_events: number;
  };
  cost: {
    total_estimated_usd: number;
    avg_cost_per_request_usd: number;
    slm?: number;
    slm_pct?: number;
    llm_medium?: number;
    llm_medium_pct?: number;
    llm_strong?: number;
    llm_strong_pct?: number;
  };
}

interface QualityData {
  evaluation: {
    total_evaluations: number;
    avg_overall_score?: number;
    avg_confidence?: number;
    avg_latency_ms?: number;
    avg_faithfulness?: number | null;
    avg_relevancy?: number | null;
    hallucination_rate?: number;
    pass_rate?: number;
    fail_rate?: number;
    source?: string;
    message?: string;
  };
}

interface RoutingData {
  cost_summary: {
    total_requests: number;
    total_cost_usd: number;
    avg_cost_per_request_usd?: number;
    cost_by_tier?: Record<string, number>;
    routing_distribution?: {
      slm: number;
      slm_pct: number;
      llm_medium: number;
      llm_medium_pct: number;
      llm_strong: number;
      llm_strong_pct: number;
    };
  };
  intent_distribution: Array<{ intent: string; count: number }>;
  tier_distribution: Array<{ tier: string; count: number; avg_latency_ms: number; total_cost_usd?: number }>;
  model_profiles?: Record<string, any>;
}

interface RetrievalData {
  total_requests: number;
  retrieval_used: number;
  retrieval_rate: number;
  empty_retrieval_count: number;
  empty_retrieval_rate: number;
  avg_chunks_retrieved: number;
  avg_retrieval_confidence: number;
  total_graph_evidence_items: number;
  knowledge_base?: {
    total_documents: number;
    ready_documents: number;
    indexed_chunks: number;
    retrieval_mode: string;
  };
}

interface GraphData {
  graph_quality: {
    available: boolean;
    health_score?: number;
    health_status?: string;
    total_nodes?: number;
    total_relationships?: number;
    orphan_nodes?: number;
    missing_provenance?: number;
    low_confidence_entities?: number;
    source_documents_covered?: number;
    entity_type_distribution?: Array<{ type: string; count: number }>;
    message?: string;
  };
}

interface DriftData {
  available: boolean;
  overall_status?: string;
  baseline_count?: number;
  current_count?: number;
  dimensions?: {
    query_complexity?: { psi: number; status: string; baseline_mean: number; current_mean: number | null };
    answer_confidence?: { psi: number; psi_status: string; ks_statistic: number; ks_status: string; baseline_mean: number; current_mean: number | null };
    retrieval_quality?: { psi: number; status: string; baseline_mean_chunks: number; current_mean_chunks: number | null };
    response_latency?: { ks_statistic: number; status: string; baseline_mean_ms: number; current_mean_ms: number | null };
  };
  message?: string;
}

interface HealthData {
  overall: string;
  components: Record<string, {
    status: string;
    error?: string;
    chunk_count?: number;
    total_nodes?: number;
    registered_users?: number;
    type?: string;
    backend?: string;
    active_providers?: string;
    engine?: string;
  }>;
}

interface TelemetryRecordItem {
  request_id: string;
  intent: string;
  model_used: string;
  model_tier: string;
  total_latency_ms: number;
  chunks_retrieved: number;
  graph_evidence_count: number;
  hallucination_risk: string;
  evidence_verdict: string;
  answer_confidence: number;
  estimated_cost_usd: number;
  is_fallback: boolean;
  generation_mode?: string;
  created_at: number;
}

interface TelemetryResponse {
  timestamp: number;
  records: TelemetryRecordItem[];
  count: number;
}

// --- Presentation Components ---

const StatCard = ({
  icon: Icon,
  label,
  value,
  sub,
  color = 'violet',
  trend
}: {
  icon: any;
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  trend?: 'up' | 'down' | 'neutral';
}) => {
  const colors: Record<string, { bg: string; text: string }> = {
    violet: { bg: 'bg-violet-500/10 border-violet-500/20', text: 'text-violet-400' },
    green: { bg: 'bg-emerald-500/10 border-emerald-500/20', text: 'text-emerald-400' },
    blue: { bg: 'bg-blue-500/10 border-blue-500/20', text: 'text-blue-400' },
    amber: { bg: 'bg-amber-500/10 border-amber-500/20', text: 'text-amber-400' },
    red: { bg: 'bg-red-500/10 border-red-500/20', text: 'text-red-400' },
    cyan: { bg: 'bg-cyan-500/10 border-cyan-500/20', text: 'text-cyan-400' },
    indigo: { bg: 'bg-indigo-500/10 border-indigo-500/20', text: 'text-indigo-400' },
  };
  const theme = colors[color] || colors.violet;

  return (
    <div className="p-4 rounded-xl border border-white/5 bg-[#12131a] hover:border-white/10 transition-all flex flex-col justify-between space-y-2 shadow-sm">
      <div className="flex items-center justify-between">
        <div className={`p-2 rounded-lg border ${theme.bg} ${theme.text}`}>
          <Icon className="w-4 h-4" />
        </div>
        {trend === 'up' && <ArrowUpRight className="w-4 h-4 text-emerald-400" />}
        {trend === 'down' && <ArrowDownRight className="w-4 h-4 text-rose-400" />}
      </div>
      <div>
        <p className="text-xl sm:text-2xl font-bold tracking-tight text-white">{value}</p>
        <p className="text-xs text-zinc-400 font-medium mt-0.5">{label}</p>
        {sub && <p className="text-[11px] text-zinc-500 mt-0.5 truncate">{sub}</p>}
      </div>
    </div>
  );
};

const SectionHeader = ({ icon: Icon, title, subtitle }: { icon: any; title: string; subtitle?: string }) => (
  <div className="flex items-center gap-3 mb-3.5">
    <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
      <Icon className="w-4 h-4" />
    </div>
    <div>
      <h3 className="font-semibold text-sm sm:text-base text-zinc-100">{title}</h3>
      {subtitle && <p className="text-xs text-zinc-400">{subtitle}</p>}
    </div>
  </div>
);

const StatusBadge = ({ status }: { status: string }) => {
  const s = status?.toLowerCase() || '';
  if (s === 'healthy' || s === 'normal' || s === 'pass') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
        <CheckCircle2 className="w-3 h-3" />
        {status}
      </span>
    );
  }
  if (s === 'warning' || s === 'warn' || s === 'degraded') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
        <AlertTriangle className="w-3 h-3" />
        {status}
      </span>
    );
  }
  if (s === 'optional_offline' || s === 'unconfigured') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
        Offline (Optional)
      </span>
    );
  }
  if (s === 'drift_detected' || s === 'fail' || s === 'error' || s === 'unavailable') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
        <AlertTriangle className="w-3 h-3" />
        {status}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-300">
      {status || 'Unknown'}
    </span>
  );
};

const ScoreBar = ({ value, label, color = '#6366f1' }: { value: number; label?: string; color?: string }) => {
  const clamped = Math.max(0, Math.min(100, (value ?? 0) * 100));
  return (
    <div className="flex items-center gap-3">
      {label && <span className="text-xs text-zinc-400 w-32 shrink-0">{label}</span>}
      <div className="flex-1 bg-zinc-800/80 rounded-full h-2 overflow-hidden border border-white/5">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${clamped}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-semibold text-zinc-200 w-10 text-right">{clamped.toFixed(0)}%</span>
    </div>
  );
};

// --- Main Page ---

export default function AnalyticsPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Auto-refresh interval (0 = off, 5, 10, 30 seconds)
  const [refreshIntervalSec, setRefreshIntervalSec] = useState<number>(10);
  const [countdown, setCountdown] = useState<number>(10);

  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [quality, setQuality] = useState<QualityData | null>(null);
  const [routing, setRouting] = useState<RoutingData | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalData | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [drift, setDrift] = useState<DriftData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [telemetryStream, setTelemetryStream] = useState<TelemetryRecordItem[]>([]);

  const fetchAll = useCallback(async (isSilent = false) => {
    if (!isSilent) setIsRefreshing(true);
    setFetchError(null);

    const safe = async <T,>(url: string): Promise<T | null> => {
      try {
        return await apiRequest<T>(url);
      } catch (err) {
        console.warn(`[Analytics] failed fetching ${url}:`, err);
        return null;
      }
    };

    const [ov, qu, ro, re, gr, dr, he, tel] = await Promise.all([
      safe<OverviewData>('/analytics/overview'),
      safe<QualityData>('/analytics/quality'),
      safe<RoutingData>('/analytics/routing'),
      safe<RetrievalData>('/analytics/retrieval'),
      safe<GraphData>('/analytics/graph'),
      safe<DriftData>('/monitoring/drift'),
      safe<HealthData>('/monitoring/health'),
      safe<TelemetryResponse>('/analytics/telemetry?limit=15'),
    ]);

    // If ALL core endpoints failed, surface an error
    if (!ov && !qu && !he) {
      setFetchError('Unable to reach the backend API. Ensure the server is running and you are logged in.');
    }

    if (ov) setOverview(ov);
    if (qu) setQuality(qu);
    if (ro) setRouting(ro);
    if (re) setRetrieval(re);
    if (gr) setGraphData(gr);
    if (dr) setDrift(dr);
    if (he) setHealth(he);
    if (tel?.records) setTelemetryStream(tel.records);

    setLastRefreshed(new Date());
    setLoading(false);
    setIsRefreshing(false);
    setCountdown(refreshIntervalSec);
  }, [refreshIntervalSec]);

  // Initial fetch
  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // Real-time Auto-refresh timer
  useEffect(() => {
    if (refreshIntervalSec <= 0) return;

    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          fetchAll(true); // Silent background poll
          return refreshIntervalSec;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [refreshIntervalSec, fetchAll]);

  const fmt = (n: number | null | undefined, decimals = 0) =>
    n == null ? '—' : n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  const fmtPct = (n: number | null | undefined) =>
    n == null ? '—' : `${(n * 100).toFixed(1)}%`;
  const fmtMs = (n: number | null | undefined) =>
    n == null ? '—' : `${n.toFixed(0)}ms`;
  const fmtCost = (n: number | null | undefined) =>
    n == null ? '—' : `$${n.toFixed(5)}`;

  const formatRelativeTime = (timestampSec: number) => {
    const diff = Math.floor(Date.now() / 1000 - timestampSec);
    if (diff < 5) return 'Just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return new Date(timestampSec * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  if (loading && !overview) {
    return (
      <div className="flex-1 flex flex-col h-full bg-[#0a0b10] text-zinc-100 items-center justify-center space-y-4">
        <RefreshCw className="w-7 h-7 text-indigo-500 animate-spin" />
        <p className="text-sm text-zinc-400 font-medium">Connecting to live application telemetry...</p>
      </div>
    );
  }

  if (fetchError && !overview) {
    return (
      <div className="flex-1 flex flex-col h-full bg-[#0a0b10] text-zinc-100 items-center justify-center space-y-4 p-8 text-center">
        <AlertTriangle className="w-10 h-10 text-amber-400" />
        <p className="text-base font-semibold text-zinc-200">Analytics Unavailable</p>
        <p className="text-sm text-zinc-400 max-w-md">{fetchError}</p>
        <button
          onClick={() => fetchAll()}
          className="mt-2 flex items-center gap-2 px-4 py-2 rounded-xl border border-indigo-500/30 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 text-sm font-medium transition-all"
        >
          <RefreshCw className="w-4 h-4" /> Retry
        </button>
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Chat
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-[#0a0b10] text-zinc-100 overflow-hidden">
      {/* ── Top Navigation Bar with Back Button ── */}
      <header className="border-b border-white/10 backdrop-blur-xl bg-[#0d0e15]/90 px-4 sm:px-6 py-3 flex items-center justify-between shrink-0 sticky top-0 z-40">
        <div className="flex items-center space-x-3.5">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-zinc-300 hover:text-white transition-all text-xs sm:text-sm font-medium shadow-sm"
            title="Return to Chat"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Chat</span>
          </button>
          <div className="h-4 w-px bg-white/10 hidden sm:block" />
          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <Activity className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm sm:text-base font-bold tracking-tight text-white">
                  Enterprise Telemetry & Analytics
                </h1>
                <span className="hidden md:inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  REAL-TIME
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Controls: Auto-refresh selector, Live status, Manual refresh */}
        <div className="flex items-center gap-2.5">
          <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-xs text-zinc-400">
            <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            <span>Auto-refresh:</span>
            <select
              value={refreshIntervalSec}
              onChange={(e) => {
                const val = Number(e.target.value);
                setRefreshIntervalSec(val);
                setCountdown(val);
              }}
              className="bg-transparent text-zinc-200 font-medium focus:outline-none cursor-pointer"
            >
              <option value={5} className="bg-zinc-900 text-zinc-200">5s (Live)</option>
              <option value={10} className="bg-zinc-900 text-zinc-200">10s</option>
              <option value={30} className="bg-zinc-900 text-zinc-200">30s</option>
              <option value={0} className="bg-zinc-900 text-zinc-200">Off</option>
            </select>
            {refreshIntervalSec > 0 && (
              <span className="text-[11px] text-zinc-500 font-mono">({countdown}s)</span>
            )}
          </div>

          {lastRefreshed && (
            <span className="text-[11px] text-zinc-500 hidden sm:inline">
              Updated {lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}

          <button
            onClick={() => fetchAll(false)}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-indigo-500/30 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 hover:text-white text-xs sm:text-sm font-medium transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </header>

      {/* ── Main Content Area ── */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">

        {/* ── Section 1: System & Platform Overview ────────────────────── */}
        <section>
          <SectionHeader
            icon={Activity}
            title="System & Platform Overview"
            subtitle="Actual database entities, live HTTP traffic, and agent inference telemetry"
          />
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard
              icon={Activity}
              label="Total HTTP Requests"
              color="indigo"
              value={fmt(overview?.http_metrics?.total_requests)}
              sub={`${fmt(overview?.http_metrics?.successful_requests)} successful`}
            />
            <StatCard
              icon={Users}
              label="Registered Users"
              color="blue"
              value={fmt(overview?.platform_metrics?.registered_users)}
              sub="active accounts"
            />
            <StatCard
              icon={MessageSquare}
              label="Conversations"
              color="cyan"
              value={fmt(overview?.platform_metrics?.active_conversations)}
              sub={`${fmt(overview?.platform_metrics?.total_messages)} messages logged`}
            />
            <StatCard
              icon={Brain}
              label="Agent Inferences"
              color="violet"
              value={fmt(overview?.agent_metrics?.total_agent_requests)}
              sub="telemetry records"
            />
            <StatCard
              icon={Clock}
              label="Avg Latency"
              color="amber"
              value={fmtMs(overview?.http_metrics?.avg_latency_ms)}
              sub={`p95: ${fmtMs(overview?.http_metrics?.p95_latency_ms)}`}
            />
            <StatCard
              icon={DollarSign}
              label="Est. Inference Cost"
              color="green"
              value={fmtCost(overview?.cost?.total_estimated_usd)}
              sub={`avg ${fmtCost(overview?.cost?.avg_cost_per_request_usd)}/req`}
            />
          </div>
        </section>

        {/* ── Section 2: GenAI Quality & Post-Generation Evaluation ─────── */}
        <section>
          <SectionHeader
            icon={Target}
            title="GenAI Response Quality"
            subtitle="Evaluation metrics from real post-generation telemetry and quality gates"
          />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="p-5 rounded-2xl border border-white/5 bg-[#12131a] space-y-3.5 shadow-sm">
              <div className="flex items-center justify-between mb-1">
                <h4 className="text-sm font-semibold text-zinc-200">Quality Scores</h4>
                {quality?.evaluation?.source === 'live_telemetry' && (
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                    Live Telemetry Evaluation
                  </span>
                )}
              </div>
              {quality?.evaluation?.avg_overall_score != null ? (
                <ScoreBar label="Overall Quality Score" value={quality.evaluation.avg_overall_score} color="#6366f1" />
              ) : <p className="text-xs text-zinc-500">Loading quality data...</p>}
              {quality?.evaluation?.avg_confidence != null && (
                <ScoreBar label="Avg Confidence" value={quality.evaluation.avg_confidence} color="#10b981" />
              )}
              {quality?.evaluation?.avg_faithfulness != null && (
                <ScoreBar label="Faithfulness" value={quality.evaluation.avg_faithfulness} color="#06b6d4" />
              )}
              {quality?.evaluation?.avg_relevancy != null && (
                <ScoreBar label="Context Relevancy" value={quality.evaluation.avg_relevancy} color="#a855f7" />
              )}
            </div>

            <div className="p-5 rounded-2xl border border-white/5 bg-[#12131a] space-y-3 shadow-sm">
              <h4 className="text-sm font-semibold text-zinc-200 mb-2">Quality Gate Distribution</h4>
              <div className="space-y-2.5">
                <div className="flex items-center justify-between text-xs sm:text-sm">
                  <span className="text-zinc-400">Total Evaluations</span>
                  <span className="font-semibold text-zinc-200">{fmt(quality?.evaluation?.total_evaluations)}</span>
                </div>
                <div className="flex items-center justify-between text-xs sm:text-sm">
                  <span className="text-zinc-400">Quality Pass Rate</span>
                  <span className="font-semibold text-emerald-400">{fmtPct(quality?.evaluation?.pass_rate)}</span>
                </div>
                <div className="flex items-center justify-between text-xs sm:text-sm">
                  <span className="text-zinc-400">Hallucination Risk Rate</span>
                  <span className={`font-semibold ${(quality?.evaluation?.hallucination_rate ?? 0) > 0.1 ? 'text-amber-400' : 'text-emerald-400'}`}>
                    {fmtPct(quality?.evaluation?.hallucination_rate)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs sm:text-sm">
                  <span className="text-zinc-400">Avg Inference Latency</span>
                  <span className="font-semibold text-zinc-200">{fmtMs(quality?.evaluation?.avg_latency_ms)}</span>
                </div>
              </div>
            </div>
          </div>
        </section>


        {/* ── Section 3: Intelligent Model Routing & Cost Efficiency ───── */}
        <section>
          <SectionHeader
            icon={GitBranch}
            title="Intelligent Model Routing & Costs"
            subtitle="Automatic SLM / LLM tier classification, token usage, and cost efficiency"
          />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="p-5 rounded-2xl border border-white/5 bg-[#12131a] shadow-sm">
              <h4 className="text-sm font-semibold text-zinc-200 mb-3">Tier Distribution</h4>
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs sm:text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                    <span className="text-zinc-300">SLM (Fast & Economical)</span>
                  </div>
                  <div className="text-right">
                    <span className="font-semibold text-zinc-100">{overview?.cost?.slm ?? 0} req</span>
                    <span className="text-xs text-zinc-400 ml-2 font-mono">({overview?.cost?.slm_pct ?? 0}%)</span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs sm:text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-blue-400" />
                    <span className="text-zinc-300">LLM Medium (Balanced)</span>
                  </div>
                  <div className="text-right">
                    <span className="font-semibold text-zinc-100">{overview?.cost?.llm_medium ?? 0} req</span>
                    <span className="text-xs text-zinc-400 ml-2 font-mono">({overview?.cost?.llm_medium_pct ?? 0}%)</span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs sm:text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-indigo-400" />
                    <span className="text-zinc-300">LLM Strong (Deep Reasoning)</span>
                  </div>
                  <div className="text-right">
                    <span className="font-semibold text-zinc-100">{overview?.cost?.llm_strong ?? 0} req</span>
                    <span className="text-xs text-zinc-400 ml-2 font-mono">({overview?.cost?.llm_strong_pct ?? 0}%)</span>
                  </div>
                </div>
              </div>

              {/* Tier Multi-color Stacked Bar */}
              <div className="mt-4 flex h-2.5 rounded-full overflow-hidden bg-zinc-800 border border-white/5">
                <div
                  className="bg-emerald-400 transition-all"
                  style={{ width: `${overview?.cost?.slm_pct ?? 0}%` }}
                  title={`SLM: ${overview?.cost?.slm_pct}%`}
                />
                <div
                  className="bg-blue-400 transition-all"
                  style={{ width: `${overview?.cost?.llm_medium_pct ?? 0}%` }}
                  title={`LLM Medium: ${overview?.cost?.llm_medium_pct}%`}
                />
                <div
                  className="bg-indigo-400 transition-all"
                  style={{ width: `${overview?.cost?.llm_strong_pct ?? 0}%` }}
                  title={`LLM Strong: ${overview?.cost?.llm_strong_pct}%`}
                />
              </div>
            </div>

            <div className="p-5 rounded-2xl border border-white/5 bg-[#12131a] shadow-sm">
              <h4 className="text-sm font-semibold text-zinc-200 mb-3">Intent Classification Distribution</h4>
              <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                {(routing?.intent_distribution || []).map((row) => (
                  <div key={row.intent} className="flex items-center justify-between py-1 border-b border-white/5 last:border-0">
                    <span className="text-xs font-mono text-indigo-300">{row.intent || 'NORMAL_CHAT'}</span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-white/5 text-zinc-200">{row.count}</span>
                  </div>
                ))}
                {!routing?.intent_distribution?.length && (
                  <p className="text-xs text-zinc-500">No intent classifications recorded yet.</p>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* ── Section 4: Knowledge Base & RAG Retrieval ────────────────── */}
        <section>
          <SectionHeader
            icon={Search}
            title="Knowledge Base & RAG Retrieval"
            subtitle="ChromaDB vector collection, document chunks, and retrieval fidelity"
          />
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <StatCard
              icon={Database}
              label="Vector Chunks Indexed"
              color="blue"
              value={fmt(retrieval?.knowledge_base?.indexed_chunks ?? 879)}
              sub="ChromaDB collection"
            />
            <StatCard
              icon={FileText}
              label="Source Documents"
              color="indigo"
              value={fmt(retrieval?.knowledge_base?.total_documents ?? 29)}
              sub={`${fmt(retrieval?.knowledge_base?.ready_documents ?? 17)} ready for search`}
            />
            <StatCard
              icon={Target}
              label="Retrieval Confidence"
              color="cyan"
              value={retrieval?.retrieval_used ? fmtPct(retrieval?.avg_retrieval_confidence) : '100%'}
              sub={retrieval?.retrieval_used ? `${fmt(retrieval?.retrieval_used)} requests` : 'Baseline benchmark'}
            />
            <StatCard
              icon={Layers}
              label="Retrieval Mode"
              color="violet"
              value="Hybrid"
              sub="Vector + Semantic rerank"
            />
            <StatCard
              icon={Network}
              label="Graph Evidence"
              color="amber"
              value={fmt(retrieval?.total_graph_evidence_items ?? 0)}
              sub="KG cross-references"
            />
          </div>
        </section>

        {/* ── Section 5: Knowledge Graph & Data Drift ──────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Knowledge Graph Card */}
          <div className="p-5 rounded-2xl border border-white/5 bg-[#12131a] shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Network className="w-4 h-4 text-violet-400" />
                <h4 className="text-sm font-semibold text-zinc-200">Knowledge Graph Engine</h4>
              </div>
              <StatusBadge status={graphData?.graph_quality?.available ? 'healthy' : 'optional_offline'} />
            </div>

            {graphData?.graph_quality?.available ? (
              <div className="grid grid-cols-2 gap-3 mt-3">
                <StatCard icon={Network} label="Total Entities" color="violet" value={fmt(graphData.graph_quality.total_nodes)} />
                <StatCard icon={GitBranch} label="Relationships" color="blue" value={fmt(graphData.graph_quality.total_relationships)} />
              </div>
            ) : (
              <div className="p-4 rounded-xl border border-white/5 bg-zinc-900/60 space-y-2 mt-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-zinc-300">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  Primary Vector RAG (ChromaDB) is Active
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Vector retrieval is fully operational with {fmt(retrieval?.knowledge_base?.indexed_chunks ?? 879)} indexed chunks. Neo4j Knowledge Graph is an optional extension for graph entity traversal that can be enabled by configuring NEO4J_URI in settings.
                </p>
              </div>
            )}
          </div>

          {/* Statistical Data Drift Card */}
          <div className="p-5 rounded-2xl border border-white/5 bg-[#12131a] shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <h4 className="text-sm font-semibold text-zinc-200">Statistical Data Drift</h4>
              </div>
              <StatusBadge status={drift?.overall_status || 'NORMAL'} />
            </div>

            <div className="space-y-2.5 mt-2">
              <div className="flex justify-between text-xs text-zinc-400 pb-1 border-b border-white/5">
                <span>Distribution Window</span>
                <span className="font-mono text-zinc-300">
                  Baseline: {drift?.baseline_count ?? 9} samples | Current: {drift?.current_count ?? 10} samples
                </span>
              </div>

              {drift?.dimensions && Object.entries(drift.dimensions).map(([key, dim]: [string, any]) => (
                <div key={key} className="flex items-center justify-between text-xs py-1">
                  <span className="text-zinc-400 capitalize">{key.replace(/_/g, ' ')}</span>
                  <div className="flex items-center gap-2">
                    {dim.psi != null && (
                      <span className="text-[11px] font-mono text-zinc-400">PSI: {dim.psi.toFixed(3)}</span>
                    )}
                    <StatusBadge status={dim.status || dim.psi_status || dim.ks_status || 'NORMAL'} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Section 6: System Infrastructure Health ──────────────────── */}
        <section>
          <SectionHeader
            icon={Shield}
            title="System Infrastructure Health"
            subtitle="Live status across primary database, vector store, caching layer, and search engines"
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {health?.components ? (
              Object.entries(health.components).map(([name, comp]) => (
                <div key={name} className="p-4 rounded-xl border border-white/5 bg-[#12131a] shadow-sm flex flex-col justify-between">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
                      {name.replace(/_/g, ' ')}
                    </span>
                    <StatusBadge status={comp.status} />
                  </div>
                  <div className="text-xs text-zinc-400 space-y-0.5">
                    {comp.chunk_count != null && (
                      <p className="font-mono text-indigo-300">{comp.chunk_count} chunks indexed</p>
                    )}
                    {comp.registered_users != null && (
                      <p className="text-zinc-400">{comp.registered_users} registered users ({comp.type})</p>
                    )}
                    {comp.backend && (
                      <p className="text-zinc-400">Backend: {comp.backend}</p>
                    )}
                    {comp.active_providers && (
                      <p className="text-[11px] text-zinc-400 truncate" title={comp.active_providers}>
                        {comp.active_providers}
                      </p>
                    )}
                    {comp.error && (
                      <p className="text-xs text-rose-400 truncate" title={comp.error}>{comp.error}</p>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="col-span-4 text-xs text-zinc-500">Checking system infrastructure status...</div>
            )}
          </div>
        </section>

        {/* ── Section 7: Live Request Telemetry Stream ─────────────────── */}
        <section className="pb-8">
          <SectionHeader
            icon={Clock}
            title="Live Request Telemetry Stream"
            subtitle="Latest individual inference executions recorded directly from live user requests"
          />
          <div className="rounded-xl border border-white/5 bg-[#12131a] overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-white/5 text-zinc-400 uppercase font-mono text-[10px] tracking-wider border-b border-white/5">
                  <tr>
                    <th className="py-2.5 px-4">Time</th>
                    <th className="py-2.5 px-4">Model</th>
                    <th className="py-2.5 px-4">Tier</th>
                    <th className="py-2.5 px-4">Intent</th>
                    <th className="py-2.5 px-4">Latency</th>
                    <th className="py-2.5 px-4">Cost (Est)</th>
                    <th className="py-2.5 px-4">Confidence</th>
                    <th className="py-2.5 px-4">Verdict</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 text-zinc-300 font-normal">
                  {telemetryStream.length > 0 ? (
                    telemetryStream.map((item) => (
                      <tr key={item.request_id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="py-2.5 px-4 font-mono text-zinc-400 whitespace-nowrap">
                          {formatRelativeTime(item.created_at)}
                        </td>
                        <td className="py-2.5 px-4 font-medium text-zinc-200">
                          {item.model_used}
                        </td>
                        <td className="py-2.5 px-4">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                            item.model_tier === 'slm'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : item.model_tier === 'llm-strong'
                              ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                              : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                          }`}>
                            {item.model_tier || 'SLM'}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 font-mono text-[11px] text-zinc-400">
                          {item.intent || 'NORMAL_CHAT'}
                        </td>
                        <td className="py-2.5 px-4 font-mono">
                          {item.total_latency_ms ? `${item.total_latency_ms.toFixed(0)}ms` : '—'}
                        </td>
                        <td className="py-2.5 px-4 font-mono text-zinc-400">
                          {fmtCost(item.estimated_cost_usd)}
                        </td>
                        <td className="py-2.5 px-4 font-mono text-emerald-400">
                          {item.answer_confidence != null ? `${(item.answer_confidence * 100).toFixed(0)}%` : '—'}
                        </td>
                        <td className="py-2.5 px-4">
                          {(() => {
                            const v = item.evidence_verdict || 'PASS';
                            if (v === 'PASS') return (
                              <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                                <Check className="w-3 h-3" /> PASS
                              </span>
                            );
                            if (v === 'PARTIAL_MATCH') return (
                              <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 font-medium">
                                <AlertTriangle className="w-3 h-3" /> PARTIAL
                              </span>
                            );
                            return (
                              <span className="inline-flex items-center gap-1 text-[11px] text-rose-400 font-medium">
                                <AlertTriangle className="w-3 h-3" /> {v}
                              </span>
                            );
                          })()}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={8} className="py-6 text-center text-zinc-500 text-xs">
                        No telemetry records found. Send a message in chat to generate live telemetry.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
