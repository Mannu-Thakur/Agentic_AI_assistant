/**
 * components/ProactiveAlerts/AlertPanel.tsx
 *
 * Dropdown panel that lists all proactive intelligence alerts.
 * Rendered below the NotificationBell when the bell is clicked.
 *
 * Features:
 *  - Severity colour-coding (info=blue, warning=amber, critical=red)
 *  - Unread bold styling
 *  - Relative timestamps ("2 minutes ago")
 *  - Markdown-lite rendering (bold via **)
 *  - Click-to-expand full message
 *  - "Mark all read" button
 *  - Manual scan trigger with loading state
 */

import React, { useState } from 'react';
import {
  AlertCircle, AlertTriangle, Info, X, CheckCheck,
  RefreshCw, ChevronDown, ChevronUp, Zap,
} from 'lucide-react';
import { useAlertStore, ProactiveAlert, AlertSeverity } from '../../store/alertStore';
import { BASE_URL } from '../../services/api';
import { useAuthStore } from '../../store/authStore';

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(unixSeconds: number): string {
  const diff = Math.floor(Date.now() / 1000 - unixSeconds);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function renderMarkdownLite(text: string): React.ReactNode {
  // Simple **bold** renderer — no dependencies
  const parts = text.split(/\*\*(.*?)\*\*/g);
  return parts.map((p, i) =>
    i % 2 === 1 ? <strong key={i}>{p}</strong> : <span key={i}>{p}</span>
  );
}

const SEVERITY_STYLES: Record<AlertSeverity, { border: string; icon: React.ReactNode; badge: string }> = {
  info:     { border: 'border-l-blue-500',   icon: <Info className="w-4 h-4 text-blue-400 flex-shrink-0" />,          badge: 'bg-blue-500/20 text-blue-300' },
  warning:  { border: 'border-l-amber-500',  icon: <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />, badge: 'bg-amber-500/20 text-amber-300' },
  critical: { border: 'border-l-red-500',    icon: <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />,    badge: 'bg-red-500/20 text-red-300' },
};

// ── Alert row ─────────────────────────────────────────────────────────────────

function AlertRow({ alert, onRead }: { alert: ProactiveAlert; onRead: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const styles = SEVERITY_STYLES[alert.severity] ?? SEVERITY_STYLES.info;

  return (
    <div
      className={`border-l-2 ${styles.border} pl-3 pr-2 py-2.5 rounded-r-md transition-colors
        ${alert.is_read ? 'bg-white/3' : 'bg-white/8 hover:bg-white/10'} cursor-pointer`}
      onClick={() => {
        setExpanded((e) => !e);
        if (!alert.is_read) onRead(alert.id);
      }}
    >
      {/* Header row */}
      <div className="flex items-start gap-2">
        {styles.icon}
        <div className="flex-1 min-w-0">
          <p className={`text-xs leading-snug ${alert.is_read ? 'text-white/70' : 'text-white font-semibold'}`}>
            {alert.title}
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${styles.badge}`}>
              {alert.severity}
            </span>
            <span className="text-[10px] text-white/40">{timeAgo(alert.created_at)}</span>
            {!alert.is_read && (
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0" />
            )}
          </div>
        </div>
        {expanded
          ? <ChevronUp className="w-3.5 h-3.5 text-white/30 flex-shrink-0 mt-0.5" />
          : <ChevronDown className="w-3.5 h-3.5 text-white/30 flex-shrink-0 mt-0.5" />
        }
      </div>

      {/* Expanded message */}
      {expanded && (
        <div className="mt-2 text-[11px] text-white/70 leading-relaxed whitespace-pre-line pl-6">
          {alert.message.split('\n').map((line, i) => (
            <p key={i} className="mb-1">{renderMarkdownLite(line)}</p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

interface AlertPanelProps {
  onClose: () => void;
}

export function AlertPanel({ onClose }: AlertPanelProps) {
  const { alerts, isLoading, markAllRead, markOneRead, fetchAlerts } = useAlertStore();
  const token = useAuthStore((s) => s.token);
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState('');

  const unread = alerts.filter((a) => !a.is_read).length;

  const handleScan = async () => {
    setScanning(true);
    setScanMsg('');
    try {
      const res = await fetch(`${BASE_URL}/proactive/scan`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setScanMsg(data.new_alerts > 0
        ? `Found ${data.new_alerts} new insight${data.new_alerts > 1 ? 's' : ''}`
        : 'No new insights found');
      await fetchAlerts();
    } catch {
      setScanMsg('Scan failed');
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="absolute right-0 top-full mt-2 w-80 sm:w-96 z-50
      bg-zinc-900 border border-white/10 rounded-xl shadow-2xl
      flex flex-col max-h-[480px] overflow-hidden">

      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-400" />
          <span className="text-sm font-semibold text-white">Proactive Intelligence</span>
          {unread > 0 && (
            <span className="text-[10px] bg-red-500 text-white rounded-full px-1.5 py-0.5 font-bold">
              {unread}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {unread > 0 && (
            <button
              onClick={markAllRead}
              className="text-[10px] text-white/50 hover:text-white/80 flex items-center gap-1 transition-colors"
              title="Mark all read"
            >
              <CheckCheck className="w-3.5 h-3.5" /> All read
            </button>
          )}
          <button
            onClick={onClose}
            className="text-white/40 hover:text-white/70 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ── Alert list ── */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5 scrollbar-thin scrollbar-thumb-white/10">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="w-5 h-5 text-white/30 animate-spin" />
          </div>
        ) : alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Zap className="w-8 h-8 text-white/20 mb-2" />
            <p className="text-xs text-white/40">No alerts yet.</p>
            <p className="text-[10px] text-white/25 mt-1">Upload documents to activate intelligence scanning.</p>
          </div>
        ) : (
          alerts.map((alert) => (
            <AlertRow key={alert.id} alert={alert} onRead={markOneRead} />
          ))
        )}
      </div>

      {/* ── Footer: manual scan ── */}
      <div className="border-t border-white/10 px-4 py-2.5 flex items-center justify-between">
        <span className="text-[10px] text-white/30 italic">{scanMsg}</span>
        <button
          onClick={handleScan}
          disabled={scanning}
          className="flex items-center gap-1.5 text-xs text-white/60 hover:text-white
            bg-white/5 hover:bg-white/10 px-3 py-1.5 rounded-lg transition-all
            disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
          {scanning ? 'Scanning…' : 'Run Scan'}
        </button>
      </div>
    </div>
  );
}
