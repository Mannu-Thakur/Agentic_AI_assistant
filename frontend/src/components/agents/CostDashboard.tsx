/**
 * CostDashboard.tsx — Real-time Provider Cost & Latency Dashboard
 *
 * Surfaces provider_metrics.py data:
 * - Per-provider call counts, success rate, avg/p95 latency
 * - Token usage and estimated cost
 * - Recent fallbacks and circuit breaker events
 * - Health status indicators
 *
 * Connects to GET /api/v1/metrics/providers (polled every 30s)
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Activity, AlertTriangle, CheckCircle2, XCircle,
  RefreshCw, ChevronDown, ChevronUp,
  Loader2, Circle
} from 'lucide-react';
import { BASE_URL } from '../../services/api';
import { useAuthStore } from '../../store/authStore';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ProviderStat {
  total_calls: number;
  successes: number;
  failures: number;
  retries: number;
  fallback_times_used: number;
  rate_limit_hits: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_tokens_in: number;
  total_tokens_out: number;
  last_health_check: { status: string; latency_ms: number | null; timestamp: number } | null;
}

interface MetricsSummary {
  providers: Record<string, ProviderStat>;
  recent_fallbacks: Array<{ from_provider: string; to_provider: string; reason: string; timestamp: number }>;
  recent_circuit_events: Array<{ provider: string; old_state: string; new_state: string; reason: string }>;
}

// ─── Cost estimation (rough per 1M tokens) ───────────────────────────────────

const COST_PER_M_TOKENS: Record<string, { in: number; out: number }> = {
  gemini:    { in: 0.075, out: 0.30  },
  openai:    { in: 2.50,  out: 10.0  },
  anthropic: { in: 3.00,  out: 15.0  },
  groq:      { in: 0.05,  out: 0.08  },
  openrouter:{ in: 1.00,  out: 3.00  },
};

function estimateCost(provider: string, tokensIn: number, tokensOut: number): number {
  const key = Object.keys(COST_PER_M_TOKENS).find(k => provider.toLowerCase().includes(k)) ?? 'gemini';
  const rates = COST_PER_M_TOKENS[key];
  return ((tokensIn / 1_000_000) * rates.in) + ((tokensOut / 1_000_000) * rates.out);
}

// ─── Status badge ─────────────────────────────────────────────────────────────

function HealthBadge({ status }: { status: string | undefined }) {
  if (!status) return <Circle className="w-2 h-2 text-gray-500" />;
  if (status === 'healthy') return <CheckCircle2 className="w-3 h-3 text-emerald-400" />;
  if (status === 'degraded') return <AlertTriangle className="w-3 h-3 text-yellow-400" />;
  return <XCircle className="w-3 h-3 text-red-400" />;
}

function SuccessRate({ successes, total }: { successes: number; total: number }) {
  if (total === 0) return <span className="text-foreground-3">—</span>;
  const rate = (successes / total) * 100;
  const color = rate >= 95 ? 'text-emerald-400' : rate >= 80 ? 'text-yellow-400' : 'text-red-400';
  return <span className={`font-mono text-xs ${color}`}>{rate.toFixed(1)}%</span>;
}

function Latency({ ms }: { ms: number | null }) {
  if (ms === null) return <span className="text-foreground-3 text-xs">—</span>;
  const color = ms < 1000 ? 'text-emerald-400' : ms < 3000 ? 'text-yellow-400' : 'text-red-400';
  return <span className={`font-mono text-xs ${color}`}>{ms < 1000 ? `${ms}ms` : `${(ms/1000).toFixed(1)}s`}</span>;
}

// ─── Provider Row ─────────────────────────────────────────────────────────────

function ProviderRow({ name, stat }: { name: string; stat: ProviderStat }) {
  const cost = estimateCost(name, stat.total_tokens_in, stat.total_tokens_out);
  const totalTokens = stat.total_tokens_in + stat.total_tokens_out;

  return (
    <tr className="border-b border-border/40 hover:bg-surface-1 transition-colors">
      <td className="py-2 px-3">
        <div className="flex items-center gap-2">
          <HealthBadge status={stat.last_health_check?.status} />
          <span className="font-medium text-xs text-foreground capitalize">{name}</span>
        </div>
      </td>
      <td className="py-2 px-3 text-center">
        <span className="font-mono text-xs text-foreground">{stat.total_calls.toLocaleString()}</span>
      </td>
      <td className="py-2 px-3 text-center">
        <SuccessRate successes={stat.successes} total={stat.total_calls} />
      </td>
      <td className="py-2 px-3 text-center">
        <Latency ms={stat.avg_latency_ms} />
      </td>
      <td className="py-2 px-3 text-center">
        <Latency ms={stat.p95_latency_ms} />
      </td>
      <td className="py-2 px-3 text-center">
        <span className="font-mono text-xs text-purple-400">
          {totalTokens > 0 ? `${(totalTokens / 1000).toFixed(1)}k` : '—'}
        </span>
      </td>
      <td className="py-2 px-3 text-center">
        <span className="font-mono text-xs text-emerald-400">
          {cost > 0 ? `$${cost.toFixed(4)}` : '—'}
        </span>
      </td>
      <td className="py-2 px-3 text-center">
        {stat.rate_limit_hits > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-500/15 text-yellow-400 border border-yellow-500/20">
            {stat.rate_limit_hits} RL
          </span>
        )}
      </td>
    </tr>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function CostDashboard() {
  const { token } = useAuthStore();
  const [data, setData]         = useState<MetricsSummary | null>(null);
  const [loading, setLoading]   = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`${BASE_URL}/api/v1/metrics/providers`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.ok) {
        const json = await res.json();
        setData(json);
        setLastUpdate(new Date());
      }
    } catch (e) {
      console.warn('Cost dashboard fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);
  // Auto-refresh every 30 seconds
  useEffect(() => {
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  // Totals
  const providers = data ? Object.entries(data.providers) : [];
  const totalCalls   = providers.reduce((s, [, p]) => s + p.total_calls, 0);
  const totalTokens  = providers.reduce((s, [, p]) => s + p.total_tokens_in + p.total_tokens_out, 0);
  const totalCost    = providers.reduce((s, [n, p]) => s + estimateCost(n, p.total_tokens_in, p.total_tokens_out), 0);
  const totalFailures = providers.reduce((s, [, p]) => s + p.failures, 0);

  return (
    <div className="border border-border rounded-2xl bg-card/50 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-3 border-b border-border/60 cursor-pointer hover:bg-surface-1 transition-colors"
        onClick={() => setCollapsed(p => !p)}
      >
        <Activity className="w-4 h-4 text-accent" />
        <span className="font-semibold text-sm text-foreground">Provider Cost & Latency</span>

        {/* Summary pills */}
        {data && (
          <div className="flex items-center gap-2 ml-1">
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
              {totalCalls.toLocaleString()} calls
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
              {(totalTokens / 1000).toFixed(1)}k tokens
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              ${totalCost.toFixed(4)}
            </span>
            {totalFailures > 0 && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
                {totalFailures} err
              </span>
            )}
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          {lastUpdate && (
            <span className="text-[10px] text-foreground-3">
              {lastUpdate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
          <button
            onClick={e => { e.stopPropagation(); load(); }}
            className="p-1 rounded-lg hover:bg-surface-2 text-foreground-3 hover:text-foreground transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {collapsed ? <ChevronDown className="w-3.5 h-3.5 text-foreground-3" /> : <ChevronUp className="w-3.5 h-3.5 text-foreground-3" />}
        </div>
      </div>

      {!collapsed && (
        <div className="p-3 space-y-3">
          {/* Provider Table */}
          {loading && !data ? (
            <div className="flex items-center justify-center py-6 gap-2 text-foreground-3">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-xs">Loading metrics...</span>
            </div>
          ) : providers.length === 0 ? (
            <p className="text-center text-xs text-foreground-3 py-6">
              No provider calls recorded yet. Start chatting to see metrics.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border/60">
                    {['Provider', 'Calls', 'Success', 'Avg Lat', 'P95 Lat', 'Tokens', 'Cost', 'Alerts'].map(h => (
                      <th key={h} className="pb-2 px-3 text-[10px] font-semibold text-foreground-3 uppercase tracking-wide text-center first:text-left">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {providers.map(([name, stat]) => (
                    <ProviderRow key={name} name={name} stat={stat} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Recent Fallbacks */}
          {data && data.recent_fallbacks.length > 0 && (
            <div className="border border-yellow-500/20 rounded-xl p-3 bg-yellow-500/5">
              <p className="text-[10px] font-semibold text-yellow-400 uppercase tracking-wide mb-2">
                Recent Fallbacks
              </p>
              <div className="space-y-1">
                {data.recent_fallbacks.slice(-3).map((f, i) => (
                  <p key={i} className="text-[11px] text-foreground-3">
                    <span className="text-foreground">{f.from_provider}</span>
                    {' → '}
                    <span className="text-foreground">{f.to_provider}</span>
                    {' — '}
                    <span>{f.reason}</span>
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default CostDashboard;
