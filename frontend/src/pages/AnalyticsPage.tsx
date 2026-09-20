import { useState, useEffect, useCallback } from 'react';
import {
  Activity, Brain, Network, Database, Shield,
  TrendingUp, AlertTriangle, CheckCircle2,
  RefreshCw, DollarSign, Search, GitBranch,
  Clock, Target, Eye, ArrowUpRight, ArrowDownRight
} from 'lucide-react';

// --- Types ---

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
    avg_overall_score: number;
    avg_confidence: number;
    avg_latency_ms: number;
    avg_faithfulness: number | null;
    avg_relevancy: number | null;
    hallucination_rate: number;
    pass_rate: number;
    fail_rate: number;
    message?: string;
  };
}

interface RoutingData {
  cost_summary: {
    total_requests: number;
    total_cost_usd: number;
    cost_by_tier: Record<string, number>;
    routing_distribution: {
      slm: number;
      slm_pct: number;
      llm_medium: number;
      llm_medium_pct: number;
      llm_strong: number;
      llm_strong_pct: number;
    };
  };
  intent_distribution: Array<{ intent: string; count: number }>;
  tier_distribution: Array<{ tier: string; count: number; avg_latency_ms: number }>;
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
}

interface GraphData {
  graph_quality: {
    available: boolean;
    health_score: number;
    health_status: string;
    total_nodes: number;
    total_relationships: number;
    orphan_nodes: number;
    missing_provenance: number;
    low_confidence_entities: number;
    source_documents_covered: number;
    entity_type_distribution: Array<{ type: string; count: number }>;
    message?: string;
  };
}

interface DriftData {
  available: boolean;
  overall_status: string;
  baseline_count: number;
  current_count: number;
  dimensions: {
    query_complexity: { psi: number; status: string; baseline_mean: number; current_mean: number | null };
    answer_confidence: { psi: number; psi_status: string; ks_statistic: number; ks_status: string; baseline_mean: number; current_mean: number | null };
    retrieval_quality: { psi: number; status: string; baseline_mean_chunks: number; current_mean_chunks: number | null };
    response_latency: { ks_statistic: number; status: string; baseline_mean_ms: number; current_mean_ms: number | null };
  };
  message?: string;
}

interface HealthData {
  overall: string;
  components: Record<string, { status: string; error?: string; chunk_count?: number; total_nodes?: number }>;
}

// --- Utility components ---

const StatCard = ({ icon: Icon, label, value, sub, color = 'violet', trend }: {
  icon: any; label: string; value: string | number; sub?: string;
  color?: string; trend?: 'up' | 'down' | 'neutral';
}) => {
  const colors: Record<string, string> = {
    violet: 'bg-violet-600/10 text-violet-400',
    green: 'bg-green-600/10 text-green-400',
    blue: 'bg-blue-600/10 text-blue-400',
    amber: 'bg-amber-600/10 text-amber-400',
    red: 'bg-red-600/10 text-red-400',
    cyan: 'bg-cyan-600/10 text-cyan-400',
    indigo: 'bg-indigo-600/10 text-indigo-400',
  };
  return (
    <div className="p-5 rounded-2xl border border-border bg-card shadow-sm flex flex-col space-y-3">
      <div className="flex items-center justify-between">
        <div className={`p-2.5 rounded-xl ${colors[color] || colors.violet}`}>
          <Icon className="w-5 h-5" />
        </div>
        {trend === 'up' && <ArrowUpRight className="w-4 h-4 text-green-400" />}
        {trend === 'down' && <ArrowDownRight className="w-4 h-4 text-red-400" />}
      </div>
      <div>
        <p className="text-2xl font-bold tracking-tight">{value}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
        {sub && <p className="text-xs text-muted-foreground/70 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
};

const SectionHeader = ({ icon: Icon, title, subtitle }: { icon: any; title: string; subtitle?: string }) => (
  <div className="flex items-center gap-3 mb-4">
    <div className="p-2 rounded-lg bg-violet-600/10">
      <Icon className="w-5 h-5 text-violet-400" />
    </div>
    <div>
      <h3 className="font-semibold text-base">{title}</h3>
      {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
    </div>
  </div>
);

const StatusBadge = ({ status }: { status: string }) => {
  const s = status?.toLowerCase() || '';
  if (s === 'healthy' || s === 'normal' || s === 'pass') {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-400"><CheckCircle2 className="w-3 h-3" />{status}</span>;
  }
  if (s === 'warning' || s === 'warn' || s === 'degraded') {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400"><AlertTriangle className="w-3 h-3" />{status}</span>;
  }
  if (s === 'drift_detected' || s === 'fail' || s === 'error' || s === 'unavailable') {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/10 text-red-400"><AlertTriangle className="w-3 h-3" />{status}</span>;
  }
  return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground">{status || 'unknown'}</span>;
};

const ScoreBar = ({ value, label, color = '#8b5cf6' }: { value: number; label?: string; color?: string }) => (
  <div className="flex items-center gap-3">
    {label && <span className="text-xs text-muted-foreground w-28 shrink-0">{label}</span>}
    <div className="flex-1 bg-muted rounded-full h-2 overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{ width: `${Math.max(0, Math.min(100, value * 100))}%`, backgroundColor: color }}
      />
    </div>
    <span className="text-xs font-medium w-10 text-right">{(value * 100).toFixed(0)}%</span>
  </div>
);

// --- Main Page ---

export default function AnalyticsPage() {
  const [loading, setLoading] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [quality, setQuality] = useState<QualityData | null>(null);
  const [routing, setRouting] = useState<RoutingData | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalData | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [drift, setDrift] = useState<DriftData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const base = '/api/v1';
    const opts = { credentials: 'include' as RequestCredentials };

    const safe = async (url: string) => {
      try {
        const r = await fetch(base + url, opts);
        if (!r.ok) return null;
        return await r.json();
      } catch { return null; }
    };

    const [ov, qu, ro, re, gr, dr, he] = await Promise.all([
      safe('/analytics/overview'),
      safe('/analytics/quality'),
      safe('/analytics/routing'),
      safe('/analytics/retrieval'),
      safe('/analytics/graph'),
      safe('/monitoring/drift'),
      safe('/monitoring/health'),
    ]);

    setOverview(ov);
    setQuality(qu);
    setRouting(ro);
    setRetrieval(re);
    setGraphData(gr);
    setDrift(dr);
    setHealth(he);
    setLastRefreshed(new Date());
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const fmt = (n: number | null | undefined, decimals = 0) =>
    n == null ? '—' : n.toFixed(decimals);
  const fmtPct = (n: number | null | undefined) =>
    n == null ? '—' : `${(n * 100).toFixed(1)}%`;
  const fmtMs = (n: number | null | undefined) =>
    n == null ? '—' : `${n.toFixed(0)}ms`;
  const fmtCost = (n: number | null | undefined) =>
    n == null ? '—' : `$${n.toFixed(4)}`;

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-8">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-indigo-500">
            Enterprise Analytics
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time operational metrics — all data from live application telemetry
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefreshed && (
            <span className="text-xs text-muted-foreground">
              Updated {lastRefreshed.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchAll}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-secondary text-sm hover:bg-muted transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── Section 1: System Overview ─────────────────────────────────── */}
      <section>
        <SectionHeader icon={Activity} title="System Overview" subtitle="HTTP and agent request metrics" />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <StatCard icon={Activity} label="Total HTTP Requests" color="violet"
            value={fmt(overview?.http_metrics?.total_requests)} />
          <StatCard icon={CheckCircle2} label="Successful" color="green"
            value={fmt(overview?.http_metrics?.successful_requests)} />
          <StatCard icon={Brain} label="Agent Requests" color="blue"
            value={fmt(overview?.agent_metrics?.total_agent_requests)} />
          <StatCard icon={Clock} label="Avg Latency" color="indigo"
            value={fmtMs(overview?.http_metrics?.avg_latency_ms)}
            sub={`p95: ${fmtMs(overview?.http_metrics?.p95_latency_ms)}`} />
          <StatCard icon={DollarSign} label="Est. Total Cost" color="amber"
            value={fmtCost(overview?.cost?.total_estimated_usd)}
            sub={`avg ${fmtCost(overview?.cost?.avg_cost_per_request_usd)}/req`} />
        </div>
      </section>

      {/* ── Section 2: GenAI Quality ───────────────────────────────────── */}
      <section>
        <SectionHeader icon={Target} title="GenAI Quality" subtitle="From evaluation framework — post-generation metrics" />
        {quality?.evaluation?.message ? (
          <div className="p-4 rounded-xl border border-border bg-card text-sm text-muted-foreground">
            {quality.evaluation.message}
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="p-5 rounded-2xl border border-border bg-card space-y-4">
              <h4 className="text-sm font-medium">Quality Scores</h4>
              <ScoreBar label="Overall Score" value={quality?.evaluation?.avg_overall_score ?? 0} />
              <ScoreBar label="Avg Confidence" value={quality?.evaluation?.avg_confidence ?? 0} color="#22c55e" />
              {quality?.evaluation?.avg_faithfulness != null && (
                <ScoreBar label="RAGAS Faithfulness" value={quality.evaluation.avg_faithfulness} color="#06b6d4" />
              )}
              {quality?.evaluation?.avg_relevancy != null && (
                <ScoreBar label="RAGAS Relevancy" value={quality.evaluation.avg_relevancy} color="#a78bfa" />
              )}
            </div>
            <div className="p-5 rounded-2xl border border-border bg-card">
              <h4 className="text-sm font-medium mb-4">Quality Gate Distribution</h4>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Total Evaluations</span>
                  <span className="font-medium">{fmt(quality?.evaluation?.total_evaluations)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Pass Rate</span>
                  <span className="font-medium text-green-400">{fmtPct(quality?.evaluation?.pass_rate)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Hallucination Rate</span>
                  <span className="font-medium text-red-400">{fmtPct(quality?.evaluation?.hallucination_rate)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Avg Latency</span>
                  <span className="font-medium">{fmtMs(quality?.evaluation?.avg_latency_ms)}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── Section 3: Model Routing ───────────────────────────────────── */}
      <section>
        <SectionHeader icon={GitBranch} title="Intelligent Model Routing" subtitle="LLM/SLM tier distribution and cost breakdown" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="p-5 rounded-2xl border border-border bg-card">
            <h4 className="text-sm font-medium mb-4">Tier Distribution</h4>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-green-400" />
                  <span className="text-sm">SLM (Fast/Cheap)</span>
                </div>
                <div className="text-right">
                  <span className="font-medium">{routing?.cost_summary?.routing_distribution?.slm ?? 0}</span>
                  <span className="text-xs text-muted-foreground ml-2">{routing?.cost_summary?.routing_distribution?.slm_pct ?? 0}%</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-blue-400" />
                  <span className="text-sm">LLM Medium</span>
                </div>
                <div className="text-right">
                  <span className="font-medium">{routing?.cost_summary?.routing_distribution?.llm_medium ?? 0}</span>
                  <span className="text-xs text-muted-foreground ml-2">{routing?.cost_summary?.routing_distribution?.llm_medium_pct ?? 0}%</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-violet-400" />
                  <span className="text-sm">LLM Strong</span>
                </div>
                <div className="text-right">
                  <span className="font-medium">{routing?.cost_summary?.routing_distribution?.llm_strong ?? 0}</span>
                  <span className="text-xs text-muted-foreground ml-2">{routing?.cost_summary?.routing_distribution?.llm_strong_pct ?? 0}%</span>
                </div>
              </div>
            </div>
            {/* Visual bar */}
            <div className="mt-4 flex h-3 rounded-full overflow-hidden gap-px">
              <div className="bg-green-400 transition-all" style={{ width: `${routing?.cost_summary?.routing_distribution?.slm_pct ?? 0}%` }} />
              <div className="bg-blue-400 transition-all" style={{ width: `${routing?.cost_summary?.routing_distribution?.llm_medium_pct ?? 0}%` }} />
              <div className="bg-violet-400 transition-all" style={{ width: `${routing?.cost_summary?.routing_distribution?.llm_strong_pct ?? 0}%` }} />
            </div>
          </div>
          <div className="p-5 rounded-2xl border border-border bg-card">
            <h4 className="text-sm font-medium mb-4">Intent Distribution</h4>
            <div className="space-y-2">
              {(routing?.intent_distribution || []).slice(0, 8).map((row) => (
                <div key={row.intent} className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground font-mono">{row.intent || 'UNKNOWN'}</span>
                  <span className="text-xs font-medium">{row.count}</span>
                </div>
              ))}
              {!routing?.intent_distribution?.length && (
                <p className="text-xs text-muted-foreground">No routing data yet — make some requests first.</p>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Section 4: RAG Retrieval ───────────────────────────────────── */}
      <section>
        <SectionHeader icon={Search} title="RAG Retrieval Quality" subtitle="Vector and hybrid retrieval metrics" />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <StatCard icon={Database} label="Retrieval Used" color="blue"
            value={fmtPct(retrieval?.retrieval_rate)}
            sub={`${fmt(retrieval?.retrieval_used)} requests`} />
          <StatCard icon={Search} label="Avg Chunks" color="indigo"
            value={fmt(retrieval?.avg_chunks_retrieved, 1)} />
          <StatCard icon={Target} label="Avg Confidence" color="cyan"
            value={fmtPct(retrieval?.avg_retrieval_confidence)} />
          <StatCard icon={AlertTriangle} label="Empty Retrieval" color="amber"
            value={fmtPct(retrieval?.empty_retrieval_rate)}
            sub={`${fmt(retrieval?.empty_retrieval_count)} times`} />
          <StatCard icon={Network} label="Graph Evidence" color="violet"
            value={fmt(retrieval?.total_graph_evidence_items)}
            sub="total items" />
        </div>
      </section>

      {/* ── Section 5: Knowledge Graph ─────────────────────────────────── */}
      <section>
        <SectionHeader icon={Network} title="Knowledge Graph" subtitle="Neo4j entity and relationship health" />
        {!graphData?.graph_quality?.available ? (
          <div className="p-5 rounded-2xl border border-border bg-card">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
              <div>
                <p className="text-sm font-medium">Neo4j Not Connected</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {graphData?.graph_quality?.message || 'Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in .env and set GRAPHRAG_ENABLED=true to enable Knowledge Graph features.'}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="grid grid-cols-2 gap-4">
              <StatCard icon={Network} label="Total Entities" color="violet"
                value={fmt(graphData.graph_quality.total_nodes)} />
              <StatCard icon={GitBranch} label="Relationships" color="blue"
                value={fmt(graphData.graph_quality.total_relationships)} />
              <StatCard icon={AlertTriangle} label="Orphan Nodes" color="amber"
                value={fmt(graphData.graph_quality.orphan_nodes)} />
              <StatCard icon={Eye} label="Docs Covered" color="green"
                value={fmt(graphData.graph_quality.source_documents_covered)} />
            </div>
            <div className="p-5 rounded-2xl border border-border bg-card">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-sm font-medium">Graph Health</h4>
                <StatusBadge status={graphData.graph_quality.health_status} />
              </div>
              <div className="text-3xl font-bold mb-2">{graphData.graph_quality.health_score}<span className="text-sm text-muted-foreground">/100</span></div>
              <ScoreBar value={graphData.graph_quality.health_score / 100} />
              <div className="mt-4 space-y-2">
                {(graphData.graph_quality.entity_type_distribution || []).slice(0, 6).map((row: any) => (
                  <div key={row.type} className="flex justify-between text-xs">
                    <span className="text-muted-foreground">{row.type}</span>
                    <span className="font-medium">{row.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── Section 6: Data Drift ──────────────────────────────────────── */}
      <section>
        <SectionHeader icon={TrendingUp} title="Data Drift Detection" subtitle="PSI and KS tests on live telemetry distributions" />
        {!drift?.available ? (
          <div className="p-5 rounded-2xl border border-border bg-card">
            <p className="text-sm text-muted-foreground">{drift?.message || 'Insufficient data for drift analysis. Send more requests to build baseline.'}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="p-5 rounded-2xl border border-border bg-card">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-sm font-medium">Overall Drift Status</h4>
                <StatusBadge status={drift.overall_status} />
              </div>
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Baseline samples</span>
                  <span className="font-medium">{drift.baseline_count}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Current samples</span>
                  <span className="font-medium">{drift.current_count}</span>
                </div>
              </div>
            </div>
            <div className="p-5 rounded-2xl border border-border bg-card">
              <h4 className="text-sm font-medium mb-4">Dimension Analysis</h4>
              <div className="space-y-3">
                {drift.dimensions && Object.entries(drift.dimensions).map(([key, dim]: [string, any]) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</span>
                    <StatusBadge status={dim.status || dim.psi_status || dim.ks_status || 'unknown'} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── Section 7: System Health ───────────────────────────────────── */}
      <section>
        <SectionHeader icon={Shield} title="System Health" subtitle="Live dependency status" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {health ? Object.entries(health.components).map(([name, comp]) => (
            <div key={name} className="p-4 rounded-xl border border-border bg-card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium capitalize">{name.replace(/_/g, ' ')}</span>
                <StatusBadge status={comp.status} />
              </div>
              {comp.chunk_count != null && (
                <p className="text-xs text-muted-foreground">{comp.chunk_count} chunks indexed</p>
              )}
              {comp.total_nodes != null && (
                <p className="text-xs text-muted-foreground">{comp.total_nodes} nodes</p>
              )}
              {comp.error && (
                <p className="text-xs text-red-400 mt-1 truncate" title={comp.error}>{comp.error}</p>
              )}
            </div>
          )) : (
            <div className="col-span-4 text-sm text-muted-foreground">Loading health status...</div>
          )}
        </div>
      </section>
    </div>
  );
}
